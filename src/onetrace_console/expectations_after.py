"""Expectations declared after the run (onetrace 0.7; onetrace's manual, 16.22): an
`onetrace-expectations/1` file, written by `onetrace expect write` and sealed, that the person names on a
local console's run page. The console checks the run against it with onetrace-verify (`--expectations`),
keeps what the check said in its own store (never in the record), and shows those rows apart from the
expectations the run declared, labelled "declared after the run".

The file is read only where the person names it, on this machine: a local console only, a file of at
most `MAX_BYTES`, read whole once and copied beside the run's folder for the check; nothing is fetched.
The rows are the verifier's own: the file's seal (`expectations file`), and one row for each entry
(`expect <step>.<name> (declared after the run, <seal>)`). Naming another file replaces what was kept.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from onetrace_console.words import escape

FOLDER = "expectations-after"
FORMAT = "onetrace-console-expectations-after/1"
FILE_FORMAT = "onetrace-expectations/1"
#: The most a named file may hold. An expectations file is a list of short declarations.
MAX_BYTES = 1_000_000
#: The formats whose runs the press is offered on: the expectations onetrace 0.7 reads are its own.
FORMATS = ("stage-receipt-chain/0.4",)
LABEL = "declared after the run"
HEADING = "Expectations declared after the run"
#: The manual's own words (16.22).
SAYS_NOTHING = "An expectation declared after the run says nothing about what was expected when the run was made."
FROM = "Checked against {file}, its seal {seal}, {when}."
PRESS = "Check against an expectations file"
FIELD = "The file's path on this machine (an onetrace-expectations/1 file, as onetrace expect write writes it)"
ROW_FILE = "expectations file"
AFTER = "(declared after the run"
_KEY = re.compile(r"[0-9a-f]{64}")


class ExpectationsError(ValueError):
    """A file refused, said in words."""


def _path(store, key: str) -> Path:
    if not _KEY.fullmatch(key or ""):
        raise ExpectationsError(f"not a run key: {key!r}")
    return Path(store.root) / FOLDER / f"{key}.json"


def kept(store, key: str) -> dict | None:
    """What the console kept for `key`'s run, or None."""
    from onetrace_console.bounded_json import load_json_bounded
    try:
        doc = load_json_bounded(_path(store, key).read_text(encoding="utf-8"), "expectations declared after the run")
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not (isinstance(doc, dict) and doc.get("format") == FORMAT and doc.get("run") == key
            and isinstance(doc.get("rows"), list)):
        return None
    return doc


def read_file(named: str) -> tuple[bytes, dict]:
    """The named file's bytes and its JSON, or `ExpectationsError` saying why it is refused."""
    path = Path(named).expanduser()
    if not named or not path.is_absolute():
        raise ExpectationsError("name the file by its whole path on this machine")
    if not path.is_file():
        raise ExpectationsError(f"there is no file at {named}")
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise ExpectationsError(f"the file holds {size} bytes; an expectations file here holds at most {MAX_BYTES}")
    data = path.read_bytes()[:MAX_BYTES + 1]
    from onetrace_console.bounded_json import load_json_bounded
    try:
        doc = load_json_bounded(data.decode("utf-8"), "the expectations file")
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ExpectationsError("the file is not JSON") from None
    if not isinstance(doc, dict) or doc.get("format") != FILE_FORMAT:
        raise ExpectationsError(f"the file is not an {FILE_FORMAT} file")
    return data, doc


def rows_of(envelope: dict) -> list[dict]:
    """The verifier's rows about the file and the expectations it declares, in its order."""
    from onetrace_console.expectations import rows_of as all_rows
    return [r for r in all_rows(envelope)
            if r.get("name") == ROW_FILE or (str(r.get("name", "")).startswith("expect ") and AFTER in str(r.get("name", "")))]


def check(store, run, named: str, *, when: str | None = None) -> dict:
    """Check `run` against the named file and keep what the verifier said. Refused, with
    `ExpectationsError`, for a file it does not read; the check's own rows otherwise."""
    from onetrace_console.checks import check as verify, materialise
    from onetrace_console.store import _atomic_write
    if run.format not in FORMATS:
        raise ExpectationsError(f"this run is recorded in {run.format}; expectations are read on {', '.join(FORMATS)} runs")
    data, doc = read_file(named)
    with tempfile.TemporaryDirectory(prefix="onetrace-expectations-") as tmp:
        folder = materialise(run, store, Path(tmp) / "run")
        (Path(tmp) / "expectations.json").write_bytes(data)
        envelope = verify(folder, extra=("--expectations", "../expectations.json")).envelope
    rows = rows_of(envelope)
    if not rows:
        raise ExpectationsError("the check gave no row about the file")
    entry = {"format": FORMAT, "run": run.key, "file": Path(named).name,
             "file_sha256": hashlib.sha256(data).hexdigest(), "seal": str(doc.get("seal", "")),
             "when": when or datetime.now(timezone.utc).isoformat(timespec="seconds"), "rows": rows}
    path = _path(store, run.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(entry, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    store._forget()
    return entry


def section(run, store, *, public: bool) -> str:
    """The run's page: what was kept, apart and labelled, and on a local console the press that names a
    file. Empty where nothing was kept and no press is offered."""
    from onetrace_console.expectations import _row, count_line
    entry = kept(store, run.key)
    said = ""
    if entry is not None:
        from onetrace_console.words import time_html
        expect = [r for r in entry["rows"] if r.get("name") != ROW_FILE]
        said = (f'<p data-expectations-after="label">{escape(LABEL.capitalize())}.</p>'
                f'<p data-expectations-after="from">{escape(FROM.split("{file}")[0])}<span class="mono" data-words="record">'
                f'{escape(entry["file"])}</span>, its seal <span class="mono" data-words="record">{escape(entry["seal"])}</span>, '
                f'{time_html(entry["when"])}.</p>'
                + (f'<p data-expectations="count">{escape(count_line(expect))}</p>' if expect else "")
                + f'<p data-expectations-after="says-nothing">{escape(SAYS_NOTHING)}</p>'
                f'<ul class="plain" data-expectations-after="rows">{"".join(_row(r) for r in entry["rows"])}</ul>')
    if public or run.format not in FORMATS:
        if entry is None:
            return ""
        return f'<section data-section="expectations-after" class="expectations">{_h2()}{said}</section>'
    from onetrace_console.expectations_script import EXPECTATIONS_SCRIPT
    control = (f'<label hidden data-expectations-after-field>{escape(FIELD)} <input type="text" '
               f'data-expectations-after-path></label> <button type="button" hidden '
               f'data-expectations-after-post="/expectations?run={run.key}">{escape(PRESS)}</button>')
    return (f'<section data-section="expectations-after" class="expectations">{_h2()}{said}'
            f'<p>{control}<span data-expectations-after-said></span></p>{EXPECTATIONS_SCRIPT}</section>')


def _h2() -> str:
    return f"<h2>{escape(HEADING)}</h2>"
