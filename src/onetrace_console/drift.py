"""A pipeline's drift page: `onetrace drift` over the pipeline's stored runs, read as it reports.

The console runs the SDK's own command, `python -m onetrace drift RUN_1 ... RUN_n --against first`
(or `previous`) `--durations --out OUT`, over the pipeline's runs in the order this console
received them (`overview.pipelines`), and keeps what it wrote: `drift.json`
(`onetrace-drift/0.1`), `drift.txt` and its exit. The page shows one line per run with its verdict
against the run it was compared with, then one row per node with each comparison's verdict, as the
report gives them. The console computes no verdict of its own, and timing never colours one: the
command's own `slower:` lines are listed apart, under their own heading.

The runs are laid out as `run-1`, `run-2`, ... in a scratch folder the command runs in, so the
verifier's words name `run-4`, never a folder of this machine.

A drift report is kept under the store's `drift/`, keyed by the mode, the runs' bundle digests in
order and the SDK's build: the same runs read the same report, and a run added makes a new one.
A public console never runs the command; it reads what its build kept (`ensure_all`).

The page names the command and its exit, not when it ran: the record keeps `ran_at`, and two
consoles drawing the same runs with the same SDK draw the same page.
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

DRIFT_FORMAT = "onetrace-console/drift/0.1"
REPORT_FORMAT = "onetrace-drift/0.1"
AGAINST = ("first", "previous")
#: How each mode is said, as the command's own text report says it.
HOW = {"first": "each compared with the first", "previous": "each compared with the one before it"}
TIMEOUT = 300

#: The page's words.
NO_REPORT = "This console holds no drift report of these runs."
ONE_RUN = "One run: nothing to compare it with."
SLOWER_HEAD = "Slower than the run it was compared with"
TIMING_NOTE = "Timing is shown apart from the verdicts and never changes one."
NULL_CELL = "-"
#: The space each cell of the runs table but a row's last keeps after its text, so the longest run
#: name never meets the next column.
GAP = ' style="padding-right:18px"'


def page_href(label: str, against: str = "first") -> str:
    """A pipeline's drift page, against the first run or each run's previous."""
    return f"drift-{label.lower()}.html" if against == "first" else f"drift-{label.lower()}-previous.html"


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def drift_key(store: Store, runs, against: str) -> str:
    from onetrace_console.compare import sdk_build_digest, sdk_distribution_version
    from onetrace_console.ingest import bundle
    from onetrace_console.store import digest
    parts = [against, *(digest(bundle(r, store)) for r in runs),
             sdk_distribution_version(), sdk_build_digest()]
    return hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest()


def shown_command(n: int, against: str) -> str:
    runs = " ".join(f"RUN_{i}" for i in range(1, n + 1))
    return f"python -m onetrace drift {runs} --against {against} --durations --out OUT"


def run_drift(store: Store, runs, against: str, *, timeout: int = TIMEOUT) -> dict:
    """Run the command over `runs`, in that order, and keep what it wrote. Never a verdict of
    the console's own: a command that timed out is said as that."""
    from onetrace_console.checks import materialise
    from onetrace_console.child import utf8_env
    from onetrace_console.compare import sdk_build_digest, sdk_version
    key = drift_key(store, runs, against)
    record = {"format": DRIFT_FORMAT, "key": key, "against": against, "runs": [r.key for r in runs],
              "sdk_version": sdk_version(), "sdk_build_digest": sdk_build_digest(),
              "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "command": shown_command(len(runs), against), "exit": "", "note": "",
              "report_key": "", "text_key": "", "stderr_key": ""}
    with tempfile.TemporaryDirectory(prefix="onetrace-drift-") as tmp:
        root = Path(tmp)
        names = [f"run-{i}" for i in range(1, len(runs) + 1)]
        for run, name in zip(runs, names):
            materialise(run, store, root / name)
        command = [sys.executable, "-m", "onetrace", "drift", *names, "--against", against,
                   "--durations", "--quiet", "--out", "out"]
        try:
            proc = subprocess.run(command, cwd=root, capture_output=True, timeout=timeout, env=utf8_env())
        except subprocess.TimeoutExpired:
            record["note"] = f"timed out after {timeout}s"
        else:
            record["exit"] = str(proc.returncode)
            record["stderr_key"] = store.put(proc.stderr)
            for name, field in (("drift.json", "report_key"), ("drift.txt", "text_key")):
                path = root / "out" / name
                if path.is_file():
                    record[field] = store.put(path.read_bytes())
    store.put_drift(key, record)
    return record


def drift_record(store: Store, pipeline, against: str, *, compute: bool) -> dict | None:
    """The kept report of these runs in this mode, made now if `compute` and none is kept."""
    if len(pipeline.runs) < 2:
        return None
    key = drift_key(store, pipeline.runs, against)
    held = store.get_drift(key)
    if held is not None or not compute:
        return held
    return run_drift(store, pipeline.runs, against)


def report_of(record: dict, store: Store) -> dict | None:
    """drift.json as the command wrote it, read strictly; None where it wrote none."""
    from onetrace_console.bounded_json import load_json_bounded
    if not record.get("report_key"):
        return None
    rep = load_json_bounded(store.get(record["report_key"]).decode("utf-8"), "drift.json")
    if not isinstance(rep, dict) or rep.get("format") != REPORT_FORMAT:
        raise StoreError(f"drift.json is not {REPORT_FORMAT}")
    return rep


def ensure_all(store: Store) -> None:
    """Every pipeline's two reports, made where none is kept: what a public demo's build keeps."""
    from onetrace_console.overview import pipelines
    for p in pipelines(store):
        for against in AGAINST:
            drift_record(store, p, against, compute=True)


def _line(c: dict | None) -> str:
    """A run's line, from the report's comparison of it: never a word of the console's own."""
    if c is None:
        return "the baseline"
    what = f"against {c['baseline']}: {c['envelope']}"
    if c.get("first_difference"):
        what += f", first difference {', '.join(c['first_difference'])}"
    elif c.get("reason"):
        what += f" — {c['reason']}"
    return what


def render_drift(pipeline, store: Store, *, generated_at: str, against: str = "first",
                 held: dict | None = None, compute: bool | None = None) -> str:
    """The drift page of `pipeline` in mode `against`. `compute`: run the command where no report
    is kept; by default a local console does and a public one never does."""
    from onetrace_console.choose_pages import b_anchor, held_comparisons, pair_href
    from onetrace_console.pipeline_pages import named, page_href as pipeline_href
    from onetrace_console.render import _document, _tag
    from onetrace_console.words import escape, generated_footer, scroll_region, verbatim
    compute = (not _public()) if compute is None else (compute and not _public())
    label = pipeline.label
    toggle = ('<p data-section="toggle">Each run against: '
              + " · ".join((f'<a href="{_tag(page_href(label, a))}" aria-current="page">{w}</a>'
                            if a == against else f'<a href="{_tag(page_href(label, a))}">{w}</a>')
                           for a, w in (("first", "the first run"), ("previous", "the run before it")))
              + "</p>")
    body = ['<p class="crumbs" data-section="crumbs"><a href="home.html">Overview</a> / '
            f'<a href="{_tag(pipeline_href(label))}">{escape(label)}</a> / Drift</p>',
            f"<h1>Drift · {named(pipeline)}</h1>",
            f'<p data-section="what">{len(pipeline.runs)} runs, oldest first as this console received '
            f"them, {escape(HOW[against])}, as <code>onetrace drift</code> reports it. This console "
            "computes no verdict of its own.</p>",
            toggle]
    record = rep = None
    try:
        record = drift_record(store, pipeline, against, compute=compute)
        rep = report_of(record, store) if record is not None else None
    except (StoreError, ValueError, UnicodeDecodeError) as e:
        record, rep = None, None
        body.append(f'<p data-section="drift-unreadable">{escape(str(e))}</p>')
    if len(pipeline.runs) < 2:
        body.append(f'<p data-section="drift-none">{escape(ONE_RUN)}</p>')
    elif record is None:
        body.append(f'<p data-section="drift-none">{escape(NO_REPORT)}</p>')
    else:
        body.append(f'<p data-section="drift-command">Command: <code>{verbatim(record["command"])}</code>'
                    + (f', exit <span data-exit>{escape(record["exit"])}</span>' if record["exit"] else "")
                    + (f" ({escape(record['note'])})" if record["note"] else "") + ".</p>")
    if rep is not None:
        held = held_comparisons(store) if held is None else held
        runs = list(pipeline.runs)
        by_index = {str(i): r for i, r in enumerate(runs, start=1)}
        by_cand = {c["candidate"]: c for c in rep["comparisons"]}

        def pair_link(c: dict, text: str) -> str:
            a, b = by_index.get(c["baseline"]), by_index.get(c["candidate"])
            if a is None or b is None:
                return escape(text)
            found = held.get((a.key, b.key))
            href = (f"diff/{found.key}.html" if found is not None
                    else f"{pair_href(label, a.key)}#{b_anchor(b.key)}")
            return f'<a href="{_tag(href)}">{escape(text)}</a>'

        rows = []
        for r in rep["runs"]:
            run = by_index.get(r["index"])
            c = by_cand.get(r["index"])
            name = (f'<a href="runs/{_tag(run.key)}/case.html" class="mono">{escape(run.run_id)}</a>'
                    if run is not None else escape(str(r.get("run_id") or "")))
            rows.append(f'<tr data-run="{_tag(r["index"])}"><td{GAP}>{escape(r["index"])}</td><td{GAP}>{name}</td>'
                        f'<td data-line>{pair_link(c, _line(c)) if c else escape(_line(c))}</td></tr>')
        body.append(scroll_region(f'<table data-section="drift-runs"><thead><tr><th{GAP}>#</th><th{GAP}>Run</th>'
                                  "<th>Against the run it was compared with</th></tr></thead>"
                                  f"<tbody>{''.join(rows)}</tbody></table>",
                                  "Each run's verdict", "drift-runs"))
        comps = rep["comparisons"]
        #: One row per node, its verdicts a list that wraps: each item names its pair and gives the
        #: report's verdict for it, so a pipeline of many runs is never wider than the page.
        nrows = []
        for n in rep["nodes"]:
            cells = "".join(f'<li data-cell="{_tag(c["candidate"])}"><span data-pair>{escape(c["candidate"])} vs '
                            f'{escape(c["baseline"])}</span> <span data-verdict>'
                            f'{pair_link(c, v if v is not None else NULL_CELL)}</span></li>'
                            for c, v in zip(comps, n["verdicts"]))
            nrows.append(f'<tr data-node="{_tag(n["node"])}"><td class="mono">{escape(n["node"])}</td>'
                         f'<td><ul class="plain" data-section="drift-cells" style="display:flex;flex-wrap:wrap;'
                         f'gap:4px 18px;margin:0;padding:0">{cells}</ul></td></tr>')
        body.append("<h2>Each node, in each comparison</h2>")
        body.append(scroll_region('<table data-section="drift-nodes"><thead><tr><th>Node</th>'
                                  "<th>Its verdict in each comparison</th></tr>"
                                  f"</thead><tbody>{''.join(nrows)}</tbody></table>",
                                  "Each node's verdicts", "drift-nodes"))
        text = store.get(record["text_key"]).decode("utf-8", "replace") if record.get("text_key") else ""
        #: The command's own lines for a slower time, each beginning `slower: `; its legend after
        #: them ("slower means ...") is its own line, shown as written.
        slower = [ln for ln in text.splitlines() if ln.startswith("slower: ")]
        legend = [ln for ln in text.splitlines() if ln.startswith("slower means ")]
        if slower:
            body.append(f'<section data-section="drift-slower"><h2>{escape(SLOWER_HEAD)}</h2>'
                        f'<p>{escape(TIMING_NOTE)}</p>'
                        + "".join(f'<p data-slower class="mono">{escape(ln)}</p>' for ln in slower)
                        + "".join(f'<p class="mono">{escape(ln)}</p>' for ln in legend)
                        + "</section>")
    body.append(generated_footer(generated_at))
    title = f"Drift · {label}" + (" · against the run before" if against == "previous" else "")
    return _document(title, "\n".join(['<div class="cp">', *body, "</div>"]))
