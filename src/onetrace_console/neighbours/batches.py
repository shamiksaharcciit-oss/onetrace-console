"""Each embedding batch is a recorded onetrace run, and the vectors are a derived file rebuilt from them.

**A batch run** is one `embed` stage, recorded with onetrace's Recorder under the store's
`neighbours/runs/<run id>/`, as onetrace-explain records each explanation as a run of its own. The stage
reads each text by its stored bytes, so its inputs carry the very digests the console's records give
them (`ctx.read_memory`: the bytes are digested and never copied into the batch's folder), and writes:

- `embedder.json`: the embedder's identity, the model-call record's fields that describe the embedder
  and not the call. Its digest, as the batch's receipt records it, is the **embedder record digest**;
- `model_call.json`, `model_call.2.json`, ...: one `model-call-record/1.0` per text, built and checked
  with onetrace 0.6.0's own helpers (`onetrace.model_call.record_bytes`, `write`), `call.kind`
  `self-hosted`, every field the call does not have `not applicable` or `not observed`;
- `vectors.json`: each text's vector, by its input's name and digest, as base64 of little-endian
  float32 (a stage output holds no JSON number).

**The derived file**, `neighbours/vectors.json`, holds every batch run's vectors keyed by (input digest,
embedder record digest), rebuilt from the batch runs alone (`rebuild`): deleting it and rebuilding gives
the same file, byte for byte. A vector under another embedder's digest is never read for the embedder in
use, so a changed embedder invalidates every vector until its own batches are recorded.
"""
from __future__ import annotations

import base64
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded

FORMAT = "onetrace-console-neighbours-vectors/0.1"
EMBEDDER_FORMAT = "onetrace-console-embedder/0.1"
DERIVED = "vectors.json"
RUNS = "runs"
STAGE = "embed"
#: Texts per batch.
BATCH = 32
INSTRUMENT_ID = "onetrace-console-neighbours"


def _root(store) -> Path:
    from onetrace_console.neighbours import FOLDER
    return Path(store.root) / FOLDER


def identity_bytes(embedder) -> bytes:
    """`embedder.json` as the batch's stage writes it: canonical, as the SDK's `write_json` writes."""
    from onetrace.canonical import canonicalize
    return canonicalize({"format": EMBEDDER_FORMAT, **embedder.identity()})


def embedder_digest(embedder) -> str:
    """The embedder record digest: the digest the batch's receipt records for its `embedder.json`."""
    from onetrace.canonical import digest
    return digest(identity_bytes(embedder))


def encode(vector) -> str:
    import numpy as np
    return base64.b64encode(np.asarray(vector, dtype="<f4").tobytes()).decode("ascii")


def decode(text: str):
    import numpy as np
    return np.frombuffer(base64.b64decode(text), dtype="<f4")


def _run_id() -> str:
    return "embed-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def record_batch(store, embedder, items: list) -> str:
    """Embed `items` (each with `.digest`, `.text`, `.data`, `.trust_class`) as one recorded run; its id."""
    from onetrace import __version__ as sdk_version
    from onetrace import model_call
    from onetrace.emit import Instrument, Recorder
    from onetrace_console import __version__
    run_id = _run_id()
    out = _root(store) / RUNS / run_id
    out.parent.mkdir(parents=True, exist_ok=True)
    ident = load_json_bounded(identity_bytes(embedder), "embedder.json")
    #: The instrument's configuration: what the embedder is, as its own identity names it.
    config = {"embedder": embedder.kind, "api": embedder.API, "onetrace": sdk_version,
              "model": str(ident["model.requested"].get("value", ""))}
    rec = Recorder(str(out), run_id=run_id, declared_stages=[STAGE], manifest=Path(__file__), policy="fail-closed",
                   anchor_reason="an embedding batch of this console's neighbours; not anchored")

    def embed(ctx):
        names = []
        for n, item in enumerate(items, start=1):
            name = f"text-{n:03d}"
            ctx.read_memory(item.data, "application/json" if item.data[:1] in b'"{[' else "text/plain",
                            name=name, trust_class=item.trust_class or "externally-sourced")
            names.append(name)
        ctx.write_json("embedder.json", ident)
        started = datetime.now(timezone.utc).isoformat(timespec="seconds")
        t0 = time.perf_counter()
        batch = embedder.embed([item.text for item in items])
        seconds = time.perf_counter() - t0
        ended = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for j in range(len(items)):
            fields = {"format": model_call.FORMAT, **batch.shared, **batch.rows[j], "fingerprints": []}
            raw = model_call.record_bytes(fields)
            model_call.write(raw, model_call.timing(raw, started, ended, seconds), ctx=ctx)
        ctx.write_json("vectors.json", {"format": FORMAT, "dimensions": str(len(batch.vectors[0])),
                                        "vectors": [{"input": name, "digest": item.digest, "vector": encode(v)}
                                                    for name, item, v in zip(names, items, batch.vectors)]})
        return None

    rec.run_node(STAGE, None, Instrument(INSTRUMENT_ID, "embedder", __version__, config), embed)
    rec.close()
    return run_id


# ------------------------------------------------------------------------------ the derived file

def _verified_output(folder: Path, receipt: dict, name: str) -> tuple[bytes, str] | None:
    import hashlib
    item = next((o for o in receipt.get("outputs") or [] if isinstance(o, dict) and o.get("name") == name), None)
    if item is None:
        return None
    path = folder / "artifacts" / "01-embed" / name
    try:
        data = path.read_bytes()
    except OSError:
        return None
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    return (data, digest) if digest == item.get("digest") else None


def _batch(folder: Path) -> tuple[str, dict[str, str]] | None:
    """(embedder record digest, {input digest: vector}) of one batch run, where its receipt's outputs
    match their stored bytes and each vector's input is one the receipt records by that digest."""
    try:
        receipt = load_json_bounded((folder / "receipts" / "01-embed.json").read_text(encoding="utf-8"),
                                    "an embedding batch's receipt")
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(receipt, dict):
        return None
    ident, vectors = _verified_output(folder, receipt, "embedder.json"), _verified_output(folder, receipt, "vectors.json")
    if ident is None or vectors is None:
        return None
    inputs = {str(i.get("name")): str(i.get("digest")) for i in receipt.get("inputs") or [] if isinstance(i, dict)}
    try:
        doc = load_json_bounded(vectors[0], "vectors.json")
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(doc, dict):
        return None
    out = {}
    for v in doc.get("vectors") or []:
        if isinstance(v, dict) and inputs.get(str(v.get("input"))) == v.get("digest") and isinstance(v.get("vector"), str):
            out[str(v["digest"])] = v["vector"]
    return ident[1], out


def build(store) -> dict:
    """The derived file's content, from the batch runs alone, the earliest batch first for a text
    embedded twice by one embedder."""
    runs = _root(store) / RUNS
    table: dict[str, dict[str, dict[str, str]]] = {}
    for folder in sorted(p for p in runs.iterdir() if p.is_dir() and re.fullmatch(r"embed-[0-9TZ]+", p.name)) \
            if runs.is_dir() else ():
        got = _batch(folder)
        if got is None:
            continue
        who, vectors = got
        mine = table.setdefault(who, {})
        for digest, vector in vectors.items():
            mine.setdefault(digest, {"vector": vector, "run": folder.name})
    return {"format": FORMAT, "embedders": table}


def encode_file(doc: dict) -> bytes:
    return (json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def rebuild(store) -> Path:
    from onetrace_console.store import _atomic_write
    path = _root(store) / DERIVED
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, encode_file(build(store)))
    return path


def read(store) -> dict | None:
    try:
        doc = load_json_bounded((_root(store) / DERIVED).read_text(encoding="utf-8"), DERIVED)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    return doc if isinstance(doc, dict) and doc.get("format") == FORMAT else None


def vectors_for(store, who: str) -> dict[str, str]:
    """{input digest: vector} for the embedder whose record digest is `who`; nothing for any other."""
    doc = read(store) or {}
    return {d: v["vector"] for d, v in (doc.get("embedders") or {}).get(who, {}).items()}


# ------------------------------------------------------------------------------ keeping up

def wanted(store) -> list:
    """Every kept text of every run that keeps inputs, once per digest, in the order of arrival."""
    from onetrace_console.neighbours import kept
    from onetrace_console.store import arrival_order
    seen, out = set(), []
    for run in arrival_order(store.runs(), newest_first=False):
        try:
            parts = kept.parts(run, store)
        except Exception:  # noqa: BLE001 - a run that can't be read has nothing to embed
            continue
        for p in parts:
            if p.text is not None and p.data is not None and p.digest not in seen:
                seen.add(p.digest)
                out.append(p)
    return out


def refresh(store) -> int:
    """Where neighbours are on: rebuild the derived file, embed every kept text it lacks for the
    embedder in use as recorded batches, and rebuild it again. The number of texts embedded."""
    from onetrace_console.neighbours import embedder as embedders, settings
    setting = settings.read(store)
    if setting is None:
        return 0
    rebuild(store)
    emb = embedders.make(store, setting["embedder"])
    have = vectors_for(store, embedder_digest(emb))
    missing = [p for p in wanted(store) if p.digest not in have]
    for i in range(0, len(missing), BATCH):
        record_batch(store, emb, missing[i:i + BATCH])
    if missing:
        rebuild(store)
    return len(missing)


def current(store) -> tuple[str, dict[str, str]] | None:
    """(the embedder record digest in use, its vectors), where neighbours are on and the embedder can be
    named; None otherwise. Reads the derived file; embeds nothing, fetches nothing."""
    from onetrace_console.neighbours import embedder as embedders, settings
    setting = settings.read(store)
    if setting is None:
        return None
    try:
        emb = embedders.make(store, setting["embedder"])
    except embedders.Refused:
        return None
    who = embedder_digest(emb)
    return who, vectors_for(store, who)
