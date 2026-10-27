"""Files given beside a run, kept with it: what onetrace-verify reads besides the run's own folder,
and the trace the trace panel reads.

onetrace 0.5's worked example keeps, beside the folder of runs, the onedoor decision export
(`decisions.jsonl`, with its `decisions.jsonl.sha256` sidecar) and the permit issuers the reader
trusts (`permit-issuers.json`). Where a folder load finds them beside a run's folder, the console
keeps their bytes in the store, under the run, and its check passes them to the verifier as
`--decisions` and `--permit-issuers`; where they are not there, the verifier's decision rows read
NOT-RUN with its own reason. A trace file the person gives, `traces/<run folder>.json` (OTLP/JSON),
is kept the same way; with none, the check keeps the SDK's own export of the run (`onetrace export
otel`), so the trace panel always says which it read.

Kept in `beside/<run key>.json` in the store: each name, the key of its bytes in the store's objects.
"""
from __future__ import annotations

import json
from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded

FOLDER = "beside"
DECISIONS, SIDECAR, ISSUERS = "decisions.jsonl", "decisions.jsonl.sha256", "permit-issuers.json"
TRACES = "traces"
#: How the trace was got: the person's file, or the SDK's export of the run.
GIVEN, EXPORT = "given", "export"


def _path(store, key: str) -> Path:
    return Path(store.root) / FOLDER / f"{key}.json"


def read(store, key: str) -> dict:
    """{name: object key}, and "trace_source"; {} where nothing is kept."""
    try:
        got = load_json_bounded(_path(store, key).read_text(encoding="utf-8"), FOLDER)
    except (OSError, ValueError, RecursionError):
        return {}
    return got if isinstance(got, dict) else {}


def keep(store, key: str, **items) -> None:
    """Add to what is kept beside run `key`: name=bytes, or trace_source=str."""
    held = read(store, key)
    for name, value in items.items():
        held[name] = value if isinstance(value, str) else store.put(value)
    p = _path(store, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(held, sort_keys=True), encoding="utf-8")
    tmp.replace(p)


def from_folder(store, key: str, run_dir: Path) -> None:
    """At a folder load: the decision files beside the run's folder, and `traces/<folder>.json`."""
    parent = Path(run_dir).parent
    found = {}
    if (parent / DECISIONS).is_file() and (parent / ISSUERS).is_file():
        found["decisions"] = (parent / DECISIONS).read_bytes()
        found["permit_issuers"] = (parent / ISSUERS).read_bytes()
        if (parent / SIDECAR).is_file():
            found["decisions_sha256"] = (parent / SIDECAR).read_bytes()
    trace = parent / TRACES / f"{Path(run_dir).name}.json"
    if trace.is_file():
        found["trace"] = trace.read_bytes()
        found["trace_source"] = GIVEN
    if found:
        keep(store, key, **found)


def verifier_files(store, key: str, folder: Path, run_dir: Path) -> tuple[str, ...]:
    """Write the kept decision files into `folder`; the verifier's options naming them, or (). Named
    relative to `run_dir`, where the verifier runs, so no path of this machine is recorded."""
    import os
    held = read(store, key)
    if not ("decisions" in held and "permit_issuers" in held):
        return ()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / DECISIONS).write_bytes(store.get(held["decisions"]))
    (folder / ISSUERS).write_bytes(store.get(held["permit_issuers"]))
    if "decisions_sha256" in held:
        (folder / SIDECAR).write_bytes(store.get(held["decisions_sha256"]))
    rel = lambda p: Path(os.path.relpath(p, run_dir)).as_posix()  # noqa: E731
    return ("--decisions", rel(folder / DECISIONS), "--permit-issuers", rel(folder / ISSUERS))


def trace(store, key: str) -> tuple[bytes | None, str]:
    """(the run's OTLP/JSON trace bytes, how they were got), or (None, "")."""
    held = read(store, key)
    if "trace" not in held:
        return None, ""
    try:
        return store.get(held["trace"]), str(held.get("trace_source", ""))
    except Exception:  # noqa: BLE001 - a missing object is no trace
        return None, ""
