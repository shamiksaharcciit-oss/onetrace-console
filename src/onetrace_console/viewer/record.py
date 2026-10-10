"""Read a run directory: the manifest and its receipts, exactly as recorded.

019 §1.2: the generator reads a run directory, the check's report for that run, and the
verbs' reports where present — **and nothing else**: no logs, no source, no database.

This module reads. It does not decide validity and it computes no fingerprint: whether the
bytes are what the manifest says they are is the check's question, and its answer arrives
in the report (`viewer/report.py`). Relations shown on the page are the ones the record
states — a step's `prev` names the step before it by fingerprint — never inferred from
names, order on disk, or timing.

A manifest entry that points outside the run directory is refused rather than followed.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.bounded_json import TooDeep, load_json_bounded
from onetrace_console.viewer.depth import too_deep


class RecordError(ValueError):
    """The run directory cannot be read as a record. Surfaced, never skipped."""


class RecordUnreadable(RecordError):
    """A part of a receipt the pages read is not in the shape the format gives it.

    Raised by `viewer.model.build_model` before it reads anything, not by `read_record`: this
    module reads and decides no validity. Refused, never read around.
    """


@dataclass(frozen=True, slots=True)
class Step:
    """One receipt, carried as recorded."""

    file: str              # path inside the run directory, as the manifest names it
    manifest_index: str    # the manifest's own index string
    manifest_stage: str
    manifest_fingerprint: str
    raw: bytes             # the receipt's bytes, verbatim
    data: dict             # the same bytes, parsed; never re-serialised for display


@dataclass(frozen=True, slots=True)
class Record:
    run_dir: Path
    manifest_raw: bytes
    manifest: dict
    steps: tuple[Step, ...]

    @property
    def run_id(self) -> str:
        return str(self.manifest.get("run_id", ""))

    @property
    def is_preview(self) -> bool:
        """The format declares itself a preview. Read from the record, not assumed."""
        fmt = str(self.manifest.get("format", ""))
        return fmt.endswith("-preview")


def unshowable(obj, *, surrogates: bool = False) -> str | None:
    """Why parsed JSON cannot be shown on a page, or None.

    Found by a review of the rule that no input may crash a page. Two
    kinds of input pass `json.loads` and every shape rule, and then crash the page. One is
    nesting deeper than the page's own indented encoder reaches. The other is a lone surrogate
    escape, which is valid JSON but cannot be written as UTF-8, and every page is UTF-8. Measured
    the way the page will meet it: written indented, then encoded.

    `surrogates=True` is for a record's own words: a lone surrogate in them
    is shown escaped, as `display` shows it, and never makes a run unshowable. Nesting past what
    can be drawn is still refused.
    """
    #: The viewer's own depth rule decides first, the same on every interpreter (viewer/depth.py).
    #: The `RecursionError` below is only a backstop now.
    if too_deep(obj):
        return "it is nested too deeply to show"
    try:
        json.dumps(obj, ensure_ascii=surrogates, indent=1).encode("utf-8")
    except RecursionError:
        return "it is nested too deeply to show"
    except UnicodeEncodeError:
        return "it holds text that is not valid UTF-8 (a lone surrogate escape)"
    return None


#: What `unshowable` found, keyed by the very bytes it was found in -- exact, and no digest:
#: this module computes no fingerprint (test_structure.py). The answer depends only on the
#: bytes, and writing a 10 MB receipt out in full took seconds on every render of every list
#: (the second confirmation review, N4). Bounded by the bytes it holds; cleared whole when full.
_SHOWABLE: dict[tuple[bool, bytes], str | None] = {}
_SHOWABLE_MAX_BYTES = 64 * 1024 * 1024


def unshowable_bytes(raw: bytes, obj, *, surrogates: bool = False) -> str | None:
    """`unshowable(obj)` for `obj` parsed from `raw`, measured once per bytes."""
    key = (surrogates, raw)
    if key not in _SHOWABLE:
        if sum(len(r) for _, r in _SHOWABLE) + len(raw) > _SHOWABLE_MAX_BYTES:
            _SHOWABLE.clear()
        _SHOWABLE[key] = unshowable(obj, surrogates=surrogates)
    return _SHOWABLE[key]


def _load_json(raw: bytes, where: str) -> dict:
    try:
        obj = load_json_bounded(raw.decode("utf-8"), where, "show")
    except TooDeep:
        raise RecordError(f"{where} is nested too deeply to show") from None
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RecordError(f"{where} is not readable JSON: {e}") from None
    except RecursionError:
        raise RecordError(f"{where} is nested too deeply to show") from None
    if not isinstance(obj, dict):
        raise RecordError(f"{where} is not a JSON object")
    why = unshowable_bytes(raw, obj, surrogates=True)
    if why is not None:
        raise RecordError(f"{where} cannot be shown: {why}")
    return obj


def read_record(run_dir: Path, manifest_name: str = "MANIFEST.json") -> Record:
    run_dir = Path(run_dir)
    manifest_path = run_dir / manifest_name
    if not manifest_path.is_file():
        raise RecordError(f"no {manifest_name} in {run_dir}")
    manifest_raw = manifest_path.read_bytes()
    manifest = _load_json(manifest_raw, manifest_name)
    chain = manifest.get("chain")
    if not isinstance(chain, list) or not chain:
        raise RecordError(f"{manifest_name} declares no steps")

    root = run_dir.resolve()
    steps = []
    named: set[str] = set()
    for i, entry in enumerate(chain):
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            raise RecordError(f"{manifest_name} chain entry {i} names no file")
        rel = entry["file"]
        target = (run_dir / rel).resolve()
        # A receipt is one step. A list of steps naming one file again and again drew pages of
        # hundreds of MB from a small upload, and exhausted memory (the third confirmation
        # review, NEW-1); so did the same file under other spellings -- './', 'x/../', another
        # case on Windows (round 4, B1). The name compared is the file it resolves to, as this
        # machine opens it, and a second one is refused before anything is read past it.
        same = os.path.normcase(str(target))
        if same in named:
            raise RecordError(f"{manifest_name} names {rel} more than once in its list of "
                              f"steps (entry {i}); a receipt is one step")
        named.add(same)
        if not target.is_relative_to(root):
            raise RecordError(f"{manifest_name} chain entry {i} points outside the run: {rel}")
        if not target.is_file():
            raise RecordError(f"{manifest_name} names {rel}, which is not in the run directory")
        raw = target.read_bytes()
        steps.append(Step(file=rel,
                          manifest_index=str(entry.get("index", "")),
                          manifest_stage=str(entry.get("stage", "")),
                          manifest_fingerprint=str(entry.get("digest", "")),
                          raw=raw,
                          data=_load_json(raw, rel)))
    return Record(run_dir=run_dir, manifest_raw=manifest_raw, manifest=manifest,
                  steps=tuple(steps))
