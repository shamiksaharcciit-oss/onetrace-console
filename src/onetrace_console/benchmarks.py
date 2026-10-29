"""Benchmarks: runs a person vouches for as the ones to compare against.

A mark lives in the console's store, beside the runs and never in a run's record: one file per
marked run under `benchmarks/`, holding the run's key and id, who marked it, when, and an optional
note. On a local console a run's page offers "Mark as benchmark" and its undo, each a `POST` with
the CSRF token; on a public console the marks are its build's (the demo's baselines) and read-only.

A benchmark is a statement that this run is the one to compare against, not that it is correct: the
badge reads "benchmark", and nothing a run's own record, check or count reads changes for a marked
run. What a mark does: the badge, the note, the order "What changed?" takes its candidates in, and
the reference its pipeline's runs are read against (`verdicts`): made by onetrace from the
pipeline's benchmark and its repeats.

A repeat is a run of the same pipeline whose manifest names the benchmark in `repeat_of` (or that
the benchmark's names), and otherwise a run with the same inputs from outside its steps
(`render.own_inputs`), settings and instruments (with their configuration fingerprints) at every
step. A benchmark recorded again shows onetrace's variation profile of it and its repeats
(`verdicts.profile_section`).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from onetrace_console.words import escape

FOLDER = "benchmarks"
FORMAT = "onetrace-console-benchmark/0.1"
BADGE = "benchmark"
MARK = "Mark as benchmark"
UNMARK = "Remove the benchmark mark"
#: The most a note holds; a longer one is refused with this number.
NOTE_CHARS = 280
NOT_CORRECT = ("A benchmark is the run to compare against, not a statement that it is correct: its own "
               "record and check read the same marked or not; its pipeline's runs are read against a "
               "reference onetrace makes from it.")
#: Beside the local mark and its undo: what pressing it does to the pipeline's verdicts (`verdicts`).
MARK_MOVES = ("Marking this run moves {pipeline}'s reference: onetrace makes a new one from this run, and "
              "every verdict in {pipeline} is then read against the new one.")
UNMARK_MOVES = ("Removing the mark moves {pipeline}'s reference to the benchmark marked before this one, where "
                "there is one, and every verdict in {pipeline} is then read against that; with none, no run "
                "in {pipeline} has a verdict.")
#: Who marked the public demo's benchmarks, and the note each carries.
DEMO_WHO = "the demo's build"
DEMO_NOTE = "The baseline this demo compares its pipeline's runs against."
_KEY = re.compile(r"[0-9a-f]{64}")


class MarkError(ValueError):
    """A mark refused, said in words."""


def _folder(store) -> Path:
    return Path(store.root) / FOLDER


def _path(store, key: str) -> Path:
    if not _KEY.fullmatch(key or ""):
        raise MarkError(f"not a run key: {key!r}")
    return _folder(store) / f"{key}.json"


def marks(store) -> dict[str, dict]:
    """{run key: its mark} for every mark the store holds that reads; one that does not is left out."""
    read = store._read()
    if read is not None and FOLDER in read:
        return read[FOLDER]
    from onetrace_console.bounded_json import load_json_bounded
    out = {}
    folder = _folder(store)
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else ():
        try:
            mark = load_json_bounded(p.read_text(encoding="utf-8"), "a benchmark mark")
        except (OSError, ValueError, UnicodeDecodeError, RecursionError):
            continue
        if isinstance(mark, dict) and mark.get("format") == FORMAT and mark.get("run") == p.stem:
            out[p.stem] = {k: str(mark.get(k, "")) for k in ("run_id", "who", "when", "note")}
    if read is not None:
        read[FOLDER] = out
    return out


def mark_of(store, key: str) -> dict | None:
    return marks(store).get(key)


def mark(store, run, *, who: str, note: str = "", when: str | None = None) -> dict:
    """Mark `run` as a benchmark, replacing any earlier mark of it."""
    note = (note or "").strip()
    if len(note) > NOTE_CHARS:
        raise MarkError(f"the note is {len(note)} characters; a note holds at most {NOTE_CHARS}")
    from onetrace_console.store import _atomic_write
    entry = {"format": FORMAT, "run": run.key, "run_id": run.run_id, "who": who,
             "when": when or datetime.now(timezone.utc).isoformat(timespec="seconds"), "note": note}
    path = _path(store, run.key)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(entry, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    store._forget()
    return entry


def unmark(store, key: str) -> bool:
    """Remove `key`'s mark; whether there was one."""
    path = _path(store, key)
    had = path.is_file()
    path.unlink(missing_ok=True)
    store._forget()
    return had


def mark_build(store, folders: list[str], when: str) -> list[str]:
    """The public demo's marks: each pipeline's baseline among `folders` (`demo_store.BENCHMARKS`)."""
    from onetrace_console.demo_store import BENCHMARK_BESIDE_KEPT, BENCHMARKS
    done = []
    for run in store.runs():
        if run.folder and Path(run.folder).name in BENCHMARKS and Path(run.folder).name in folders:
            mark(store, run, who=DEMO_WHO, note=DEMO_NOTE, when=when)
            done.append(run.run_id)
    #: On a build from an earlier build's runs, P10's 1.0 baseline, marked after the kept one: the
    #: most recently marked, so P10's reference is made from it (`verdicts.chosen`).
    later = (datetime.fromisoformat(when) + timedelta(seconds=1)).isoformat(timespec="seconds")
    for run in store.runs():
        if run.folder and Path(run.folder).name == BENCHMARK_BESIDE_KEPT and BENCHMARK_BESIDE_KEPT in folders:
            mark(store, run, who=DEMO_WHO, note=DEMO_NOTE, when=later)
            done.append(run.run_id)
    return done


def badge(store, key: str) -> str:
    """The badge beside a listed run that is a benchmark, its note (and who and when) on hover; ""
    for any other run."""
    m = mark_of(store, key)
    if m is None:
        return ""
    said = "; ".join(x for x in (m["note"], f"marked by {m['who']}, {m['when']}") if x)
    return f' <span class="pill neu" data-benchmark title="{escape(said)}">{BADGE}</span>'


# ------------------------------------------------------------------------- the run's page

def mark_section(run, store, *, public: bool) -> str:
    """The run's page: the badge and its note, and on a local console the mark or its undo."""
    m = mark_of(store, run.key)
    said = ""
    if m is not None:
        from onetrace_console.words import time_html
        said = (f'<p data-benchmark-mark>{badge(store, run.key).strip()} Marked by {escape(m["who"])}, '
                f'{time_html(m["when"])}' + (f': {escape(m["note"])}' if m["note"] else ".") + "</p>")
    if public:
        if m is None:
            return ""
        return (f'<section data-section="benchmark" class="benchmark"><h2>Benchmark</h2>{said}'
                f"<p class=\"note\">{escape(NOT_CORRECT)}</p></section>")
    from onetrace_console.benchmark_script import BENCHMARK_SCRIPT
    if m is None:
        control = (f'<label hidden data-benchmark-note>Note (optional) <input type="text" maxlength="{NOTE_CHARS}" '
                   f'data-benchmark-note-input></label> <button type="button" hidden '
                   f'data-benchmark-post="/benchmark?run={run.key}&amp;mark=yes">{escape(MARK)}</button>')
    else:
        control = (f'<button type="button" hidden data-benchmark-post="/benchmark?run={run.key}&amp;mark=no">'
                   f"{escape(UNMARK)}</button>")
    #: What the press does to the pipeline's reference, said beside it, on the run's own pipeline.
    from onetrace_console.verdicts import pipeline_of
    pipeline = pipeline_of(run, store)
    moves = ""
    if pipeline is not None:
        words = (MARK_MOVES if m is None else UNMARK_MOVES).format(pipeline=pipeline.label)
        moves = f'<p data-benchmark-moves>{escape(words)}</p>'
    return (f'<section data-section="benchmark" class="benchmark"><h2>Benchmark</h2>{said}'
            f'<p>{control}<span data-benchmark-said></span></p>{moves}'
            f'<p class="note">{escape(NOT_CORRECT)}</p>{BENCHMARK_SCRIPT}</section>')


def _facts(run, store) -> list[dict]:
    """Each step's name, settings, instrument, inputs and outputs, as its receipt records them."""
    from onetrace_console.render import _receipts_in_order, _stage_of, own_inputs
    from onetrace_console.run_index import _named, _settings
    out = []
    receipts = _receipts_in_order(run.key, store)
    own = own_inputs(receipts)
    for r in receipts:
        instrument = r.get("instrument") if isinstance(r.get("instrument"), dict) else {}
        out.append({"name": _stage_of(r), "settings": _settings(r), "own": sorted(own.get(_stage_of(r), {}).items()),
                    #: The instrument by name, version and configuration fingerprint: a configuration
                    #: the record names only by its digest is a configuration all the same.
                    "instrument": tuple(str(instrument.get(k, "")) for k in ("id", "version", "config_digest")),
                    "inputs": sorted(tuple(x) for x in _named(r.get("inputs")) if not x[0].startswith("receipt:")),
                    "outputs": sorted(tuple(x) for x in _named(r.get("outputs")))})
    return out


def _repeat_of(run, store) -> str:
    from onetrace_console.run_panels import manifest_of
    said = manifest_of(run, store).get("repeat_of")
    return said if isinstance(said, str) else ""


def repeats(run, store) -> list[tuple[object, str]]:
    """[(a repeat of `run`, how it is known)]: a declared `repeat_of` either way, else the same
    first-step inputs with the same settings and instruments at every step; same pipeline only."""
    from onetrace_console.overview import declared_list
    from onetrace_console.store import arrival_order
    mine = _facts(run, store)
    if not mine:
        return []
    out = []
    for other in arrival_order(store.runs(), newest_first=False):
        if other.key == run.key or declared_list(other) != declared_list(run):
            continue
        if (_repeat_of(other, store) == run.run_id and run.run_id) or \
                (_repeat_of(run, store) == other.run_id and other.run_id):
            out.append((other, "its manifest's repeat_of"))
            continue
        theirs = _facts(other, store)
        if (len(theirs) == len(mine)
                and all((a["name"], a["own"], a["settings"], a["instrument"])
                        == (b["name"], b["own"], b["settings"], b["instrument"]) for a, b in zip(mine, theirs))):
            out.append((other, "the same inputs, settings and configuration"))
    return out
