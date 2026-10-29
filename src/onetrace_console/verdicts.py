"""A run's verdict against its pipeline's reference, and a repeat set's variation profile: the SDK's
own commands over stored runs, read as they report.

The reference. A pipeline's reference is made by `python -m onetrace reference make` from its
benchmark (`benchmarks`), with the benchmark's repeats where it has any, so the reference carries
their timing range: the benchmark marked most recently, where the pipeline has more than one. A
reference is never made from a run whose records could not be checked: where the benchmark's own
check does not say its records agree, no reference is made and the reason is kept; a repeat whose
records could not be checked is left out of it, and said.

The verdict. Each run of the pipeline is read against that reference by `python -m onetrace verdict
--reference REF RUN --json`: the run's own word (identical, diverged at a step, refused, could not
check) and each step's word with the record item it rests on, as the SDK gives them. The console
adds no verdict, fits no threshold and changes no word.

The profile. Where the benchmark has repeats, `python -m onetrace profile` over the benchmark and its
repeats gives, per step, how many of the runs differ and of what kind, as numbers in the SDK's order.

The runs are laid out as `run-1`, `run-2`, ... in a scratch folder, so nothing kept names a folder
of this machine. Each record is kept under the store's `references/`, `verdicts/` or `profiles/`,
keyed by the runs' bundle digests, the reference's seal where it has one, and the SDK's build: the
same runs read the same record. A public console never runs a command; it reads what its build kept
(`ensure_all`).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from onetrace_console.store import Store, StoreError
from onetrace_console.words import escape

FORMAT = "onetrace-console/verdict/0.1"
TIMEOUT = 300
#: The page's words.
HEADING = "Verdict against this pipeline's reference"
LABEL = ("onetrace's own verdict of this run against the pipeline's reference, in its words: the run's "
         "word, then each step's with the record item it rests on.")
REFERENCE_HEAD = "The reference"
HOW = "Made by onetrace from this pipeline's benchmark, {run}{which}{repeats}."
#: Where no reference was made: the benchmark it would be made from, and nothing said made.
HOW_NONE = "This pipeline's benchmark is {run}{which}{repeats}."
WHICH_MOST_RECENT = ", the one marked most recently of its {n} benchmarks"
WITH_REPEATS = ", and its {k} repeat{s} recorded on the same configuration"
LEFT_OUT = "Left out of the reference, its records not checked as agreeing: {runs}."
NO_REFERENCE = "No reference: {why}."
NOT_CHECKED = "the benchmark's records could not be checked as agreeing, and a reference is made from a known-good run"
NOT_KEPT = "This console holds no verdict of this run against the reference."
OWN_RUN = "This run is one the reference was made from."
#: A run whose own records could not be checked: no verdict word, whatever the reference.
UNCHECKED = "No verdict: this run's records could not be checked."
PROFILE_HEAD = "The variation profile of this benchmark's repeats"
PROFILE_COLUMNS = ("Step", "Runs", "Differ", "Distinct outputs", "Output only", "Input differs",
                   "Setting differs", "Varies on its own", "may_vary declared")


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def _bundles(store: Store, runs) -> list[str]:
    from onetrace_console.ingest import bundle
    from onetrace_console.store import digest
    return [digest(bundle(r, store)) for r in runs]


def _key(*parts) -> str:
    from onetrace_console.compare import sdk_build_digest, sdk_distribution_version
    return hashlib.sha256(json.dumps([*parts, sdk_distribution_version(), sdk_build_digest()]).encode("utf-8")).hexdigest()


def _agree(run, store) -> bool:
    from onetrace_console import records
    return records.state(run, store) == records.YES


# ---- which reference --------------------------------------------------------------------------

def pipeline_of(run, store):
    from onetrace_console.overview import pipelines
    return next((p for p in pipelines(store) if any(r.key == run.key for r in p.runs)), None)


def chosen(pipeline, store) -> dict | None:
    """The pipeline's reference runs, and how they were chosen: {"benchmark", "of", "repeats",
    "left_out"}; None where the pipeline has no benchmark."""
    from onetrace_console.benchmarks import marks, repeats
    held = marks(store)
    marked = [(i, r) for i, r in enumerate(pipeline.runs) if r.key in held]
    if not marked:
        return None
    _, bench = max(marked, key=lambda ir: (str(held[ir[1].key].get("when", "")), ir[0]))
    found = [o for o, _how in repeats(bench, store)]
    return {"benchmark": bench, "of": len(marked), "repeats": [o for o in found if _agree(o, store)],
            "left_out": [o for o in found if not _agree(o, store)]}


def _run_in(store: Store, runs, argv: list[str], outputs: list[str], *, timeout: int = TIMEOUT) -> dict:
    """Lay `runs` out as run-1..run-n, run `python -m onetrace <argv>` there, and read what it wrote."""
    from onetrace_console.checks import materialise
    from onetrace_console.child import utf8_env
    got = {"exit": "", "note": "", "files": {}}
    with tempfile.TemporaryDirectory(prefix="onetrace-verdict-") as tmp:
        root = Path(tmp)
        for i, run in enumerate(runs, start=1):
            materialise(run, store, root / f"run-{i}")
        try:
            proc = subprocess.run([sys.executable, "-m", "onetrace", *argv], cwd=root, capture_output=True,
                                  timeout=timeout, env=utf8_env())
        except subprocess.TimeoutExpired:
            got["note"] = f"timed out after {timeout}s"
            return got
        got["exit"] = str(proc.returncode)
        got["stderr"] = proc.stderr.decode("utf-8", "replace")[-2000:]
        for name in outputs:
            path = root / name
            if path.is_file():
                got["files"][name] = path.read_bytes()
    return got


def reference_record(pipeline, store: Store, *, compute: bool) -> dict | None:
    """The kept reference of the pipeline's chosen runs, made now if `compute` and none is kept."""
    pick = chosen(pipeline, store)
    if pick is None:
        return None
    runs = [pick["benchmark"], *pick["repeats"]]
    key = _key("reference", _bundles(store, runs))
    held = store.get_kept("references", key)
    if held is not None or not compute:
        return held
    from onetrace_console.compare import sdk_build_digest, sdk_version
    record = {"format": FORMAT, "kind": "reference", "key": key, "runs": [r.key for r in runs],
              "left_out": [r.key for r in pick["left_out"]], "of": pick["of"],
              "sdk_version": sdk_version(), "sdk_build_digest": sdk_build_digest(),
              "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "refused": "", "exit": "", "note": "", "reference": None}
    if not _agree(pick["benchmark"], store):
        record["refused"] = NOT_CHECKED
    else:
        names = [f"run-{i}" for i in range(1, len(runs) + 1)]
        got = _run_in(store, runs, ["reference", "make", *names, "--out", "ref.json"], ["ref.json"])
        record.update(exit=got["exit"], note=got["note"])
        if "ref.json" in got["files"]:
            from onetrace_console.bounded_json import load_json_bounded
            record["reference"] = load_json_bounded(got["files"]["ref.json"].decode("utf-8"), "ref.json")
        elif got["exit"]:
            #: The command's own last line says why it made none (the SDK's ReferenceError).
            said = (got.get("stderr") or "").strip().splitlines()
            record["refused"] = said[-1] if said else f"the command's exit was {got['exit']}"
    store.put_kept("references", key, record)
    return record


def unchecked(run, store: Store) -> bool:
    """The run's own check could not say whether its records agree: no verdict is read for it."""
    from onetrace_console import records
    return records.state(run, store) == records.COULDNT


def verdict_record(run, store: Store, *, compute: bool) -> tuple[dict | None, dict | None]:
    """(the pipeline's reference record, the run's kept verdict against it), each made now if
    `compute` and none is kept; (None, None) where the run's pipeline has no benchmark. A run whose
    own records could not be checked is never read against the reference: (the reference, None)."""
    pipeline = pipeline_of(run, store)
    if pipeline is None:
        return None, None
    ref = reference_record(pipeline, store, compute=compute)
    if ref is None or not ref.get("reference") or unchecked(run, store):
        return ref, None
    seal = str(ref["reference"].get("seal", ""))
    key = _key("verdict", _bundles(store, [run]), seal)
    held = store.get_kept("verdicts", key)
    if held is not None or not compute:
        return ref, held
    from onetrace_console.compare import sdk_build_digest, sdk_version
    record = {"format": FORMAT, "kind": "verdict", "key": key, "run": run.key, "reference_key": ref["key"],
              "seal": seal, "sdk_version": sdk_version(), "sdk_build_digest": sdk_build_digest(),
              "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "exit": "", "note": "",
              "verdict": None}
    with tempfile.TemporaryDirectory(prefix="onetrace-ref-") as tmp:
        ref_file = Path(tmp) / "ref.json"
        ref_file.write_text(json.dumps(ref["reference"], sort_keys=True), encoding="utf-8")
        got = _run_in(store, [run], ["verdict", "--reference", str(ref_file), "run-1", "--json", "--quiet",
                                     "--out", "out"], ["out/verdict.json"])
    record.update(exit=got["exit"], note=got["note"])
    if "out/verdict.json" in got["files"]:
        from onetrace_console.bounded_json import load_json_bounded
        doc = load_json_bounded(got["files"]["out/verdict.json"].decode("utf-8"), "verdict.json")
        #: The reference file's path is this console's scratch folder: kept as the reference's name.
        if isinstance(doc, dict):
            doc["reference"] = "the pipeline's reference"
        record["verdict"] = doc
    store.put_kept("verdicts", key, record)
    return ref, record


def profile_record(pipeline, store: Store, *, compute: bool) -> dict | None:
    """The kept profile of the benchmark and its repeats, made now if `compute`; None without repeats."""
    pick = chosen(pipeline, store)
    if pick is None or not pick["repeats"]:
        return None
    runs = [pick["benchmark"], *pick["repeats"]]
    key = _key("profile", _bundles(store, runs))
    held = store.get_kept("profiles", key)
    if held is not None or not compute:
        return held
    from onetrace_console.compare import sdk_build_digest, sdk_version
    names = [f"run-{i}" for i in range(1, len(runs) + 1)]
    got = _run_in(store, runs, ["profile", *names, "--json", "--quiet", "--out", "out"], ["out/profile.json"])
    record = {"format": FORMAT, "kind": "profile", "key": key, "runs": [r.key for r in runs],
              "sdk_version": sdk_version(), "sdk_build_digest": sdk_build_digest(),
              "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "exit": got["exit"], "note": got["note"], "profile": None}
    if "out/profile.json" in got["files"]:
        from onetrace_console.bounded_json import load_json_bounded
        record["profile"] = load_json_bounded(got["files"]["out/profile.json"].decode("utf-8"), "profile.json")
    store.put_kept("profiles", key, record)
    return record


def ensure_all(store: Store) -> None:
    """Every pipeline's reference and profile, and each of its runs' verdicts, made where none is
    kept: what a public demo's build keeps."""
    from onetrace_console.overview import pipelines
    for p in pipelines(store):
        if reference_record(p, store, compute=True) is None:
            continue
        profile_record(p, store, compute=True)
        for run in p.runs:
            verdict_record(run, store, compute=True)


# ---- drawn --------------------------------------------------------------------------------------

def word_of(run, store: Store) -> tuple[str, str] | None:
    """(the run's verdict word as the SDK gives it, "at <step>" or ""), from what is kept; never made."""
    try:
        _ref, rec = verdict_record(run, store, compute=False)
    except (StoreError, ValueError):
        return None
    doc = (rec or {}).get("verdict")
    if not isinstance(doc, dict) or not isinstance(doc.get("verdict"), str):
        return None
    return doc["verdict"], (f"at {doc['diverged_at']}" if isinstance(doc.get("diverged_at"), str) else "")


def seal_of(run, store: Store) -> str | None:
    """The seal of the reference the run's kept verdict was read against; never made."""
    try:
        _ref, rec = verdict_record(run, store, compute=False)
    except (StoreError, ValueError):
        return None
    seal = (rec or {}).get("seal")
    return seal if isinstance(seal, str) and seal and isinstance((rec or {}).get("verdict"), dict) else None


AGAINST = "against the reference "


def against_html(seal: str) -> str:
    """A verdict's reference, by its seal, short: in a table's row, where a whole digest would widen it.
    The table's `seals_note` holds each seal whole, on the same page."""
    from onetrace_console.viewer.page import FINGERPRINT_SHOWN
    algo, _, hexed = seal.partition(":")
    shown = f"{algo}:{hexed[:FINGERPRINT_SHOWN]}…" if hexed else seal
    return (f'<span data-verdict-seal="{escape(seal)}">{escape(AGAINST)}'
            f'<span class="mono">{escape(shown)}</span></span>')


SEALS_NOTE = "Each reference these verdicts were read against, whole:"


def seals_note(seals) -> str:
    """Under a table of verdicts: each distinct seal its rows name short, whole, one fold each; "" with none."""
    from onetrace_console.viewer.page import fingerprint_html
    seen = list(dict.fromkeys(s for s in seals if s))
    if not seen:
        return ""
    return (f'<div data-section="reference-seals"><p>{escape(SEALS_NOTE)}</p>'
            + "".join(f"<div>{fingerprint_html(s)}</div>" for s in seen) + "</div>")


def _reference_block(ref: dict, store: Store, up: str) -> str:
    from onetrace_console.viewer.page import fingerprint_html
    from onetrace_console.words import run_named
    keys = ref.get("runs") or []
    bench, repeats = (keys[0] if keys else ""), keys[1:]
    named = (f'<a href="{up}runs/{escape(bench)}/case.html">{run_named(store, bench)}</a>' if bench else "")
    which = WHICH_MOST_RECENT.format(n=ref.get("of")) if int(ref.get("of") or 1) > 1 else ""
    reps = WITH_REPEATS.format(k=len(repeats), s="" if len(repeats) == 1 else "s") if repeats else ""
    head, tail = (HOW if ref.get("reference") else HOW_NONE).split("{run}")
    how = f"<p data-reference-how>{escape(head)}{named}{escape(tail.format(which=which, repeats=reps))}</p>"
    left = ""
    if ref.get("left_out"):
        names = ", ".join(run_named(store, k) for k in ref["left_out"])
        h, t = LEFT_OUT.split("{runs}")
        left = f"<p data-reference-left-out>{escape(h)}{names}{escape(t)}</p>"
    if not ref.get("reference"):
        why = ref.get("refused") or ref.get("note") or f"the command's exit was {ref.get('exit')}"
        return how + left + f'<p data-reference="none">{escape(NO_REFERENCE.format(why=why))}</p>'
    doc = ref["reference"]
    made = doc.get("made_from") if isinstance(doc.get("made_from"), dict) else {}
    lines = (f"<li>seal {fingerprint_html(str(doc.get('seal', '')))}</li>"
             f"<li>format <code>{escape(str(doc.get('format', '')))}</code></li>"
             f"<li>made from {escape(str(made.get('count', '')))} run(s): "
             f"{escape(', '.join(str(x) for x in made.get('run_ids') or []))}</li>"
             f"<li>signature: {escape('none' if not isinstance(doc.get('signature'), dict) else 'present')}</li>")
    return how + left + f'<ul class="plain" data-reference>{lines}</ul>'


def section(run, store: Store, *, up: str = "../../") -> str:
    """A run's verdict section, or "" where its pipeline has no benchmark. On a local console the
    reference and the verdict are made where none is kept; a public console reads what is kept."""
    try:
        ref, rec = verdict_record(run, store, compute=not _public())
    except (StoreError, ValueError):
        return ""
    if ref is None:
        return ""
    out = (f'<section data-section="verdict" class="verdict"><h2>{escape(HEADING)}</h2>'
           f'<p class="label">{escape(LABEL)}</p>')
    doc = (rec or {}).get("verdict")
    if unchecked(run, store):
        out += f'<p data-verdict="unchecked">{escape(UNCHECKED)}</p>'
    elif ref.get("reference") and isinstance(doc, dict):
        from onetrace import reference as sdk_reference
        text = sdk_reference.verdict_text(doc).rstrip("\n").splitlines()
        items = []
        for n, line in enumerate(text):
            if not line.strip():
                continue
            tag = ' data-verdict-word' if n == 0 else ""
            items.append(f"<li{tag}>{escape(line.strip())}</li>")
        out += f'<ul class="plain" data-verdict-lines>{"".join(items)}</ul>'
        if run.key in (ref.get("runs") or []):
            out += f"<p data-verdict-own-run>{escape(OWN_RUN)}</p>"
    elif ref.get("reference"):
        out += f"<p data-verdict=\"none\">{escape(NOT_KEPT)}</p>"
    out += f"<h3>{escape(REFERENCE_HEAD)}</h3>" + _reference_block(ref, store, up)
    return out + "</section>"


def profile_section(run, store: Store, *, up: str = "../../") -> str:
    """On a benchmark's page, the SDK's variation profile of it and its repeats; "" otherwise."""
    from onetrace_console.benchmarks import mark_of
    if mark_of(store, run.key) is None:
        return ""
    pipeline = pipeline_of(run, store)
    if pipeline is None:
        return ""
    pick = chosen(pipeline, store)
    if pick is None or pick["benchmark"].key != run.key:
        return ""
    try:
        rec = profile_record(pipeline, store, compute=not _public())
    except (StoreError, ValueError):
        return ""
    doc = (rec or {}).get("profile")
    if not isinstance(doc, dict):
        return ""
    from onetrace_console.words import scroll_region
    head = "".join(f"<th>{escape(c)}</th>" for c in PROFILE_COLUMNS)
    rows = []
    for s in doc.get("steps") or []:
        if not isinstance(s, dict):
            continue
        kinds = s.get("kinds") if isinstance(s.get("kinds"), dict) else {}
        cells = [s.get("runs"), s.get("differs"), s.get("distinct_outputs"), kinds.get("output_only"),
                 kinds.get("input_differs"), kinds.get("setting_differs"), s.get("varies_on_its_own"),
                 s.get("may_vary_declared")]
        rows.append(f'<tr data-step="{escape(str(s.get("step", "")))}"><td><code>{escape(str(s.get("step", "")))}</code></td>'
                    + "".join(f'<td class="value">{escape(str(c))}</td>' for c in cells) + "</tr>")
    notes = "".join(f"<li>{escape(str(n))}</li>" for n in doc.get("non_claims") or [])
    return (f'<section data-section="profile" class="variation"><h2>{escape(PROFILE_HEAD)}</h2>'
            f"<p>onetrace's profile of {len(doc.get('runs') or [])} runs: this benchmark and its repeats, "
            f"per step, in its order. Counts only; no threshold.</p>"
            + scroll_region(f'<table class="timeline"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table>',
                            PROFILE_HEAD, "profile")
            + f'<ul class="plain" data-profile-notes>{notes}</ul></section>')


# ---- the monitoring view (a local console only) ------------------------------------------------

MONITOR = "monitor.html"
MONITOR_TITLE = "Verdicts as runs arrive"
MONITOR_WHAT = ("Each pipeline with a reference: its runs as this console received them, newest first, each "
                "with onetrace's verdict against the pipeline's reference, and how many runs read each word. "
                "Counts only; no threshold, no alert. On a local console only.")
MONITOR_NONE = "No pipeline has a benchmark, so no run has a reference to be read against."
MONITOR_SHOWN = 20
NO_VERDICT = "no verdict kept"


def render_monitor(store: Store, *, generated_at: str) -> str:
    """The monitoring view: per pipeline with a reference, the counts of each run word in the SDK's
    order, then its latest runs, newest first, each with its word. Verdicts are made where none is
    kept, as a run's page makes them; a public console draws no such page."""
    from onetrace import reference as sdk_reference
    from onetrace_console.overview import pipelines
    from onetrace_console.render import _document, _tag
    from onetrace_console.words import generated_footer, run_named, scroll_region
    body = ['<p class="crumbs" data-section="crumbs"><a href="home.html">Overview</a> / Monitoring</p>',
            f"<h1>{escape(MONITOR_TITLE)}</h1>", f'<p data-section="what">{escape(MONITOR_WHAT)}</p>']
    shown = 0
    for p in pipelines(store):
        ref = reference_record(p, store, compute=True)
        if ref is None:
            continue
        shown += 1
        words = {}
        for run in p.runs:
            try:
                verdict_record(run, store, compute=True)
            except (StoreError, ValueError):
                pass
            words[run.key] = word_of(run, store)
        #: Each verdict with the seal of the reference it was read against.
        seals = {run.key: seal_of(run, store) for run in p.runs}
        #: A run whose own records could not be checked counts under its own line, never a word.
        for run in p.runs:
            if unchecked(run, store):
                words[run.key] = (UNCHECKED, "")
        order = list(sdk_reference.RUN_WORDS) + [UNCHECKED, NO_VERDICT]
        counts = {w: sum(1 for got in words.values() if (got[0] if got else NO_VERDICT) == w) for w in order}
        short = {UNCHECKED: "no verdict, records could not be checked"}
        tally = " · ".join(f"{escape(short.get(w, w))}: {counts[w]}" for w in order if counts[w])
        rows = "".join(
            f'<tr data-run="{escape(r.key)}"><td><a href="runs/{_tag(r.key)}/case.html">{run_named(store, r.key)}</a></td>'
            f'<td data-verdict-word="{escape(words[r.key][0] if words[r.key] else NO_VERDICT)}">'
            f'{escape(" ".join(x for x in (words[r.key] or (NO_VERDICT, "")) if x))}</td>'
            f'<td>{against_html(seals[r.key]) if seals[r.key] else ""}</td></tr>'
            for r in list(reversed(p.runs))[:MONITOR_SHOWN])
        more = len(p.runs) - min(len(p.runs), MONITOR_SHOWN)
        body.append(f'<section data-section="monitor" data-pipeline="{escape(p.label)}"><h2>{escape(p.label)}</h2>'
                    f'<p data-monitor-counts>{len(p.runs)} runs · {tally}</p>'
                    + scroll_region(f'<table class="timeline"><thead><tr><th>Run</th><th>Verdict</th><th>Reference</th></tr></thead>'
                                    f"<tbody>{rows}</tbody></table>", f"{p.label}'s runs and their verdicts",
                                    f"monitor-{p.label.lower()}")
                    + seals_note(seals[r.key] for r in list(reversed(p.runs))[:MONITOR_SHOWN])
                    + (f"<p>{more} earlier runs are on the pipeline's page.</p>" if more else "")
                    + "</section>")
    if not shown:
        body.append(f'<p data-section="monitor-none">{escape(MONITOR_NONE)}</p>')
    body.append(generated_footer(generated_at))
    return _document(MONITOR_TITLE, "\n".join(['<div class="cp">', *body, "</div>"]))
