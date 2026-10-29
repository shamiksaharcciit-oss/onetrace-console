"""What is embedded: a run's kept inputs, and, for the nearness ladder, its kept outputs. Nothing else.

- **A kept input** is what the console already shows as one (`kept_inputs.read_kept` reads "shown"):
  listed by its step as kept, under the SDK's per-input opt-in, and its file matching its digest.
- **A kept output** is a step's stored output whose bytes match its digest and whose media type is
  text, in a run that keeps at least one input and whose manifest keeps its outputs: the outputs come
  under the same per-input opt-in, so a run that kept nothing has nothing embedded at all.
- **An input read from an earlier step's output** is that output, by its digest, kept or not as it is.

Never a digest, a setting, a receipt, a manifest or any other part of a record: the texts are the kept
files' own words. Each is keyed by its recorded digest, so equal digests are equal by the record and
need no embedding.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from onetrace_console.bounded_json import load_json_bounded

INPUT, OUTPUT = "input", "output"
#: What a part reads where it has no text to embed.
NOT_KEPT = "not kept"


@dataclass(frozen=True)
class Part:
    """One input or output of one step: its recorded name and digest, and its kept text or None."""
    step: str
    index: str
    kind: str
    name: str
    digest: str
    text: str | None
    #: The stored bytes the digest is computed over, and the trust class the record gives them: what
    #: an embedding batch reads, so its run records the same digest. Never shown.
    data: bytes | None = field(default=None, repr=False, compare=False)
    trust_class: str = ""


def _version(steps):
    from onetrace_console.kept_inputs import recorded_with
    return recorded_with(steps)


def _output_text(blob: bytes | None, digest: str, media: str) -> str | None:
    from onetrace_console.stage_pages import _is_text, _verified
    if blob is None or not _verified(blob, digest) or not _is_text(media):
        return None
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if media == "application/json":
        try:
            value = load_json_bounded(text, "a kept output")
        except (ValueError, RecursionError):
            return text
        return value if isinstance(value, str) else text
    return text


def parts(run, store) -> list[Part]:
    """Every input and output of every step of `run`, in the chain's order, each with its kept text."""
    from onetrace_console.kept_inputs import FOLDER as KEPT_FOLDER, _stem, read_kept
    from onetrace_console.run_panels import manifest_of
    from onetrace_console.stage_pages import _artifact_path, _files, _read, _stage_name, _steps
    files, steps = _files(run, store), _steps(run, store)
    version = _version(steps)

    def read(path):
        return _read(files, store, path)

    own: list[Part] = []
    for s in steps:
        receipt = s["receipt"]
        for item in receipt.get("inputs") or []:
            if not isinstance(item, dict) or str(item.get("name", "")).startswith("receipt:"):
                continue
            k = read_kept(item, receipt, s["file"], read, version)
            name = str(item.get("name", ""))
            shown = k is not None and k.state == "shown"
            own.append(Part(_stage_name(receipt), str(s["index"]), INPUT, name, str(item.get("digest", "")),
                            k.text if shown else None,
                            read(f"{KEPT_FOLDER}/{_stem(s['file'])}/{name}.json") if shown else None,
                            str(item.get("trust_class", ""))))
    keeps = any(p.text is not None for p in own)
    outputs_kept = manifest_of(run, store).get("outputs_kept") != "none"
    out: list[Part] = []
    produced: dict[str, Part] = {}
    for s in steps:
        receipt = s["receipt"]
        stage = _stage_name(receipt)
        for item in receipt.get("inputs") or []:
            if not isinstance(item, dict) or str(item.get("name", "")).startswith("receipt:"):
                continue
            name, digest = str(item.get("name", "")), str(item.get("digest", ""))
            mine = next((p for p in own if (p.index, p.name) == (str(s["index"]), name)), None)
            source = mine if mine is not None and mine.text is not None else produced.get(digest)
            kept = keeps and source is not None and source.text is not None
            out.append(Part(stage, str(s["index"]), INPUT, name, digest, source.text if kept else None,
                            source.data if kept else None, str(item.get("trust_class", ""))))
        for item in receipt.get("outputs") or []:
            if not isinstance(item, dict):
                continue
            name, digest = str(item.get("name", "")), str(item.get("digest", ""))
            text, blob = None, None
            if keeps and outputs_kept:
                blob = read(_artifact_path(s["file"], name))
                text = _output_text(blob, digest, str(item.get("media_type", "")))
            part = Part(stage, str(s["index"]), OUTPUT, name, digest, text, blob if text is not None else None,
                        str(item.get("trust_class", "")))
            produced.setdefault(digest, part)
            out.append(part)
    return out


def _later(q: Part, p: Part) -> bool:
    try:
        return int(q.index) < int(p.index)
    except ValueError:
        return False


def kept_inputs(run, store) -> list[Part]:
    """The run's own kept inputs: what its page's suggestions are made from."""
    every = parts(run, store)
    return [p for p in every if p.kind == INPUT and p.text is not None and not _produced(p, every)]


def _produced(p: Part, every: list[Part]) -> bool:
    """`p` is an input read from an earlier step's output, not one from outside the run."""
    return any(q.kind == OUTPUT and q.digest == p.digest and _later(q, p) for q in every)


def keeps_anything(run, store) -> bool:
    return bool(kept_inputs(run, store))
