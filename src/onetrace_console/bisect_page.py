"""A pipeline's first run to leave its reference: by step, or after a time, in recorded order.

The runs. The pipeline's runs (`overview.pipelines`), each placed by the recorder's clock: the
earliest `time.started` its receipts state, then by run name and key, as `store.arrival_order`
breaks a tie. The console's own arrival times are not used. A run whose receipts state no readable
start time, with its offset, is not placed, and the page names it.

The reference and the words. The reference is the pipeline's current one, the one `verdicts` would
read a new verdict against now (`verdicts.reference_record`), and each run's words are onetrace's
own verdict against it (`verdicts.verdict_record`): kept where it is kept, made on a local console
where none is, as a run's page makes it, and never made on a public console. A step leaves the
reference where its word is one of `LEAVING`, the words onetrace's verdict diverges on; "same output"
and "slower than its range" (a view of timing, never a divergence) read as the reference. A run
leaves it where its word is "diverged".

Gaps. A run with no verdict kept, a run whose records could not be checked, a run whose verdict is
"refused" or "could not check", and, at one step, a step whose word is "could not check", is a gap:
shown as a gap, never as reading as the reference, and named between the two runs it falls between.

The step form, for each step of the reference: the first run, in recorded order, whose word there
leaves the reference after a run whose word there reads as the reference, with that last run beside
it: their comparison where the console holds one, with the line `first_kind` draws at that step, and
otherwise the pair to compare (`choose_pages`). The window form, asked at `/bisect`: the first run
recorded after a time whose verdict is "diverged". One plain GET form asks it, on the built page and
the page the console answers at `/bisect` alike, and each run's start in the runs table is a link into
it with that time. The page names what it read, and says where no run left the reference. No check,
comparison or command is run by the window form, on either console.

Times. Each run's start is shown in the console's one form, in UTC, to the millisecond where the
receipts give one; the time as written is the `<time>`'s `datetime`.
"""
from __future__ import annotations

import re

from datetime import datetime, timezone

from onetrace_console.store import Store, StoreError
from onetrace_console.words import NO_REFERENCE_YET, escape

PATH = "bisect"
#: The step words that leave the reference: the words onetrace's verdict diverges on.
LEAVING = ("output differs", "setting differs", "input differs")
#: The step word, and the run words, that make a gap.
STEP_GAP = "could not check"
RUN_GAPS = ("refused", "could not check")
TITLE = "First run to leave the reference"
WHAT = ("This pipeline's runs in recorded order, each placed by the recorder's clock: the earliest step "
        "start its receipts state. Each run is read as onetrace's own verdict against the pipeline's "
        "current reference reads it.")
AGAINST = "The reference: {seal}, made from {run}."
LEAVES = ("A step leaves the reference where its word is output differs, setting differs or input differs, "
          "the words onetrace's verdict diverges on; same output, and slower than its range, read as the "
          "reference. A run leaves it where its word is diverged.")
#: The answer, first on the page, from the by-step walk.
ANSWER = ("The first run to leave the reference is {run}, at step {step} ({word}). The run before it, {before}, "
          "reads as the reference.")
ANSWER_MORE = "And {n} more {steps}: below."
ANSWER_NONE = "No run has left the reference."
#: How to read the page, in plain words; the exact rule (WHAT, LEAVES) is kept, word for word, in RULE_HEAD's fold.
HOW = ("Runs are listed in the order they were recorded, by the recorder's clock. Each is compared with the reference "
       "run, {run}. A run leaves the reference at the first step whose output, setting or input differs; the same "
       "output, only slower, reads as the reference.")
HOW_NO_REFERENCE = "Runs are listed in the order they were recorded, by the recorder's clock."
RULE_HEAD = "The exact rule"
NO_REFERENCE = NO_REFERENCE_YET
MAKE = "A reference is made from the run marked as the pipeline's benchmark, by {command}."
MAKE_COMMAND = "python -m onetrace reference make"
NO_REFERENCE_REASON = "No reference: {reason}."
NON_CLAIMS = (
    "The first run that differed is the first recorded run that differed.",
    "Runs not recorded, or recorded without a verdict, are not seen: each one this console holds is "
    "shown as a gap.",
    "Time is the recorder's clock, as each run's receipts state it.",
)
NON_CLAIMS_HEAD = "What this page does not say"
STEP_HEAD = "By step"
STEP_COLUMNS = ("Step", "First run to leave the reference there", "Its word", "The run before it, read as the reference",
                "Side by side")
NONE_LEFT = "No run left the reference."
NEVER_READ = "No run read as the reference here."
ALREADY = "Before the first run to read as the reference, {n} already left it here: {runs}."
GAPS_BETWEEN = "Between them, {n} not seen: {runs}."
GAPS_AFTER = "After {run}, {n} not seen: {runs}."
COMPARE = "Compare the two"
HELD = "Their comparison"
RUNS_HEAD = "The runs, in recorded order"
RUNS_COLUMNS = ("#", "Run", "Recorded start", "Its verdict")
UNPLACED = "Not placed, their receipts stating no readable start time: {runs}."
GAP_WORDS = {"unchecked": "a gap: its records could not be checked",
             "none": "a gap: no verdict against this reference is held",
             "refused": "a gap: onetrace's verdict is refused",
             "could not check": "a gap: onetrace's verdict is could not check"}
STEP_GAP_WORD = "a gap: could not check"
#: Beside each gap in the runs table: what the records hold of its reason, and what would include it.
GAP_ROWS = "The check did not run: {rows}."
GAP_ROWS_MORE = "And {n} more {rows}, on its Proof page."
GAP_ROWS_INCLUDE = "It is included once a check of its records runs these."
GAP_NONE_WHY = "No verdict against this reference is kept for it."
GAP_NONE_INCLUDE = "It is included once one is made: a local console makes it when it draws this page."
GAP_VERDICT_WHY = "onetrace's verdict gives its reason: {reason}."
GAP_VERDICT_INCLUDE = "It is included where onetrace's verdict reads the run against the reference."
GAP_NOT_RECORDED = "The reason is not recorded."
WINDOW_HEAD = "After a time"
WINDOW_LABEL = "Find the first run to leave after:"
WINDOW_BUTTON = "Find"
WINDOW_HINT = "A time in ISO 8601, with its offset; a time with no offset is read as UTC."
WINDOW_AFTER_RUN = "First to leave after it"
WINDOW_FOUND = "The first run recorded after {when} to leave the reference: {run}, diverged at {step}."
WINDOW_NONE = "No run recorded after {when} left the reference."
WINDOW_UNREAD = "Not a time this page reads: {said}. Give it in ISO 8601, with its offset."
WINDOW_UTC = "Read as UTC: no offset was given."
WINDOW_BEFORE = "The run before it to read as identical: {run}."
WINDOW_GAPS = "Between {when} and it, {n} not seen: {runs}."
WINDOW_GAPS_NONE = "After {when}, {n} not seen: {runs}."
#: The most characters of a time read from the address.
MOST_CHARS = 64
#: In a static export the window form is a GET to a console that isn't there: shown disabled, with this.
NEEDS_CONSOLE = "Needs a running console."


def page_href(label: str) -> str:
    return f"bisect-{label.lower()}.html"


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def _instant(value) -> datetime | None:
    """A recorded time with its offset, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        got = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo is not None else None


def recorded_start(run, store: Store) -> tuple[datetime, str] | None:
    """The earliest `time.started` the run's receipts state, read and as written; None where none reads."""
    from onetrace_console.stage_pages import _steps
    try:
        steps = _steps(run, store)
    except Exception:  # noqa: BLE001 - a record that can't be read is not placed
        return None
    said = []
    for s in steps:
        t = s["receipt"].get("time") if isinstance(s["receipt"].get("time"), dict) else {}
        got = _instant(t.get("started"))
        if got is not None:
            said.append((got, str(t["started"])))
    return min(said, key=lambda x: x[0]) if said else None


class Walk:
    """A pipeline's runs against its current reference: placed in recorded order, each with its words."""

    def __init__(self, pipeline, store: Store, *, compute: bool):
        from onetrace_console import verdicts
        self.pipeline, self.store = pipeline, store
        self.ref = verdicts.reference_record(pipeline, store, compute=compute)
        self.doc = (self.ref or {}).get("reference") if isinstance((self.ref or {}).get("reference"), dict) else None
        self.placed, self.unplaced, self.docs, self.gaps = [], [], {}, {}
        if self.doc is None:
            return
        rows = []
        for run in pipeline.runs:
            when = recorded_start(run, store)
            if when is None:
                self.unplaced.append(run)
            else:
                rows.append((when, run))
            self.gaps[run.key], self.docs[run.key] = self._read(run, compute)
        rows.sort(key=lambda wr: (wr[1].run_id, wr[1].key))
        rows.sort(key=lambda wr: wr[0][0])
        self.placed = [(run, when) for when, run in rows]

    def _read(self, run, compute: bool) -> tuple[str | None, dict | None]:
        """(a gap's reason, or None; the verdict as onetrace gives it, or None)."""
        from onetrace_console import verdicts
        if verdicts.unchecked(run, self.store):
            return "unchecked", None
        try:
            _ref, rec = verdicts.verdict_record(run, self.store, compute=compute)
        except (StoreError, ValueError):
            return "none", None
        doc = (rec or {}).get("verdict")
        if not isinstance(doc, dict) or not isinstance(doc.get("verdict"), str):
            return "none", None
        if doc["verdict"] in RUN_GAPS:
            return doc["verdict"], doc
        return None, doc

    def steps(self) -> list[str]:
        order = self.doc.get("step_order") if self.doc else None
        return [str(s) for s in order] if isinstance(order, list) else []

    def word(self, run, step: str) -> str | None:
        """The run's word at `step`, or None where it is a gap there."""
        if self.gaps.get(run.key):
            return None
        rows = self.docs[run.key].get("steps") or []
        got = next((r.get("word") for r in rows if isinstance(r, dict) and r.get("step") == step), None)
        return None if not isinstance(got, str) or got == STEP_GAP else got

    def at_step(self, step: str) -> dict:
        """{"left": run or None, "before": the last run before it to read as the reference, or None,
        "word": its word, "gaps": the gaps between them (or after the last such run where none left),
        "already": the runs that left it before any run read as the reference}."""
        before, gaps, already = None, [], []
        for run, _when in self.placed:
            word = self.word(run, step)
            if word is None:
                gaps.append(run)
            elif word in LEAVING:
                if before is not None:
                    return {"left": run, "before": before, "word": word, "gaps": gaps, "already": already}
                already.append(run)
                gaps = []
            else:
                before, gaps = run, []
        return {"left": None, "before": before, "word": "", "gaps": gaps, "already": already}

    def after(self, when: datetime) -> dict:
        """{"left": the first run recorded after `when` whose verdict is diverged, or None, "at": its
        step, "before": the last run before it to read as identical, "gaps": the gaps after `when`
        before it}."""
        identical, gaps = None, []
        for run, (start, _said) in self.placed:
            doc = self.docs.get(run.key)
            word = None if self.gaps.get(run.key) else (doc or {}).get("verdict")
            if start <= when:
                if word == "identical":
                    identical = run
                continue
            if word is None:
                gaps.append(run)
            elif word == "diverged":
                return {"left": run, "at": str(doc.get("diverged_at", "")), "before": identical, "gaps": gaps}
            elif word == "identical":
                identical = run
        return {"left": None, "at": "", "before": identical, "gaps": gaps}


def read_time(said: str) -> tuple[datetime | None, bool]:
    """(the time asked, whether it was read as UTC for want of an offset); (None, False) where unread."""
    text = said.strip().replace(" ", "T", 1).replace("Z", "+00:00")
    try:
        got = datetime.fromisoformat(text)
    except ValueError:
        return None, False
    if got.tzinfo is None:
        return got.replace(tzinfo=timezone.utc), True
    return got, False


def _run_link(run, store: Store) -> str:
    from onetrace_console.render import _tag
    from onetrace_console.words import run_named
    return f'<a href="runs/{_tag(run.key)}/case.html">{run_named(store, run.key)}</a>'


def _runs(runs, store: Store) -> str:
    return ", ".join(_run_link(r, store) for r in runs)


class Drawn:
    """A part of a sentence already drawn as markup (a `<time>`)."""

    def __init__(self, html: str):
        self.html = html


def _said(template: str, store: Store, **parts) -> str:
    """`template` with each part: a run or runs as links, a `Drawn` part as drawn, anything else
    escaped as text."""
    import re
    out, at = [], 0
    for m in re.finditer(r"\{(\w+)\}", template):
        out.append(escape(template[at:m.start()]))
        v = parts[m.group(1)]
        if isinstance(v, (list, tuple)):
            out.append(_runs(v, store))
        elif hasattr(v, "key"):
            out.append(_run_link(v, store))
        elif isinstance(v, Drawn):
            out.append(v.html)
        else:
            out.append(escape(str(v)))
        at = m.end()
    return "".join(out) + escape(template[at:])


def _pair(a, b, step: str | None, store: Store, held: dict, label: str) -> str:
    """The two runs side by side: their comparison and its kind line at `step` where held, else the pair."""
    from onetrace_console import first_kind
    from onetrace_console.choose_pages import b_anchor, pair_href
    from onetrace_console.render import _tag
    found = held.get((a.key, b.key))
    if found is None:
        return (f'<a href="{_tag(pair_href(label, a.key))}#{_tag(b_anchor(b.key))}" data-pair="compare">'
                f"{escape(COMPARE)}</a>")
    line = ""
    if step is not None:
        try:
            line = first_kind.drawn(first_kind.at_stage(step, found, store))
        except Exception:  # noqa: BLE001 - the comparison's page says what could not be read
            line = ""
    return f'<a href="diff/{_tag(found.key)}.html" data-pair="held">{escape(HELD)}</a>{line}'


def _pipelines(store: Store):
    from onetrace_console.overview import pipelines
    return pipelines(store)


def answer_html(walk: Walk, held: dict) -> str:
    """The page's answer, from the by-step walk: the earliest run, in recorded order, to leave the
    reference at any step (the first such step in the reference's order where one run leaves first at
    several), the run before it there, and their comparison; the other steps a run leaves at, counted."""
    store, order = walk.store, {run.key: i for i, (run, _when) in enumerate(walk.placed)}
    left = [(step, got) for step in walk.steps() if (got := walk.at_step(step))["left"] is not None]
    if not left:
        return f'<p data-section="bisect-answer">{escape(ANSWER_NONE)}</p>'
    step, got = min(left, key=lambda sg: order[sg[1]["left"].key])
    said = _said(ANSWER, store, run=got["left"], step=Drawn(f"<code>{escape(step)}</code>"), word=got["word"],
                 before=got["before"])
    more = len(left) - 1
    if more:
        said += " " + escape(ANSWER_MORE.format(n=more, steps="step" if more == 1 else "steps"))
    pair = _pair(got["before"], got["left"], None, store, held, walk.pipeline.label)
    return f'<p data-section="bisect-answer" data-left="{escape(got["left"].key)}" data-step="{escape(step)}">{said} {pair}</p>'


def _step_rows(walk: Walk, held: dict) -> str:
    from onetrace_console.render import _tag
    store, rows = walk.store, []
    for step in walk.steps():
        got = walk.at_step(step)
        notes = []
        if got["already"]:
            notes.append(_said(ALREADY, store, n=len(got["already"]), runs=got["already"]))
        if got["left"] is not None:
            first, word = _run_link(got["left"], store), escape(got["word"])
            before = _run_link(got["before"], store)
            pair = _pair(got["before"], got["left"], step, store, held, walk.pipeline.label)
            if got["gaps"]:
                notes.append(_said(GAPS_BETWEEN, store, n=len(got["gaps"]), runs=got["gaps"]))
        else:
            first = escape(NONE_LEFT if got["before"] is not None else NEVER_READ)
            word, pair = "", ""
            before = _run_link(got["before"], store) if got["before"] is not None else ""
            if got["gaps"] and got["before"] is not None:
                notes.append(_said(GAPS_AFTER, store, run=got["before"], n=len(got["gaps"]), runs=got["gaps"]))
        said = "".join(f"<p data-bisect-note>{n}</p>" for n in notes)
        rows.append(f'<tr data-step="{_tag(step)}" data-left="{_tag(got["left"].key if got["left"] else "")}">'
                    f'<td><code>{escape(step)}</code></td><td data-first>{first}{said}</td><td data-word>{word}</td>'
                    f"<td data-before>{before}</td><td data-side>{pair}</td></tr>")
    return "".join(rows)


def start_html(said: str) -> str:
    """A recorded start as the page shows it: the one form, to the millisecond where it has them."""
    from onetrace_console.words import clock, short_time, time_html
    has_ms = "." in said.split("T", 1)[-1]
    return time_html(said, text=f"{short_time(said)[:10]} {clock(said)}" if has_ms else None)


def ask_href(label: str, after: str) -> str:
    from urllib.parse import quote
    return f"{PATH}?p={quote(label)}&amp;after={quote(after, safe='')}"


def unsettled_rows(run, store: Store) -> list[str]:
    """The kept check's rows that left the run's records unsettled, quoted whole, by the rule its own
    page reads them with (`viewer.model`'s strip): a row not run, not about originality, and about a
    step rather than the run as a whole. Empty where none is read."""
    import tempfile
    from pathlib import Path
    from onetrace_console.bounded_json import load_json_bounded
    from onetrace_console.checks import materialise
    from onetrace_console.viewer.model import _whole_run
    from onetrace_console.viewer.record import read_record
    from onetrace_console.viewer.report import parse
    if not run.check_report:
        return []
    try:
        report = parse(load_json_bounded(store.get(run.check_report).decode("utf-8"), "the check report"))
        with tempfile.TemporaryDirectory(prefix="onetrace-gap-") as tmp:
            record = read_record(materialise(run, store, Path(tmp) / "run"))
        whole = _whole_run(record, report)
    except Exception:  # noqa: BLE001 - a report or record not read gives no rows, and says so
        return []
    return [f.line for f in report.findings
            if f.outcome == "not_run" and f.property != "originality" and f.subject not in whole]


def gap_why(walk: Walk, run, gap: str) -> str:
    """What the records hold of a gap's reason, and what would include it; never a guess."""
    from onetrace_console.render import _tag
    if gap == "unchecked":
        rows = unsettled_rows(run, walk.store)
        if not rows:
            return escape(GAP_NOT_RECORDED)
        said = escape(GAP_ROWS.format(rows=rows[0]))
        if len(rows) > 1:
            more = GAP_ROWS_MORE.format(n=len(rows) - 1, rows="row" if len(rows) == 2 else "rows")
            head, tail = more.split("on its Proof page")
            said += (f' {escape(head)}<a href="runs/{_tag(run.key)}/proof.html">on its Proof page</a>'
                     f"{escape(tail)}")
        return f"{said} {escape(GAP_ROWS_INCLUDE)}"
    if gap == "none":
        return f"{escape(GAP_NONE_WHY)} {escape(GAP_NONE_INCLUDE)}"
    reason = (walk.docs.get(run.key) or {}).get("reason")
    if isinstance(reason, str) and reason.strip():
        return f"{escape(GAP_VERDICT_WHY.format(reason=reason.strip()))} {escape(GAP_VERDICT_INCLUDE)}"
    return f"{escape(GAP_NOT_RECORDED)} {escape(GAP_VERDICT_INCLUDE)}"


def _runs_table(walk: Walk) -> str:
    from onetrace_console.render import _tag
    rows = []
    for i, (run, (_start, said)) in enumerate(walk.placed, start=1):
        gap = walk.gaps.get(run.key)
        doc = walk.docs.get(run.key) or {}
        if gap:
            verdict = (f'<span data-gap="{_tag(gap)}">{escape(GAP_WORDS[gap])}</span>'
                       f'<p data-gap-why>{gap_why(walk, run, gap)}</p>')
        else:
            verdict = escape(doc["verdict"] + (f" at {doc['diverged_at']}" if doc.get("diverged_at") else ""))
        #: The row's time is a link into the one form: the first run to leave after it.
        rows.append(f'<tr data-run="{_tag(run.key)}"><td>{i}</td><td>{_run_link(run, walk.store)}</td>'
                    f'<td class="mono"><a href="{ask_href(walk.pipeline.label, said)}" data-bisect-ask '
                    f'title="{escape(WINDOW_AFTER_RUN)}">{start_html(said)}</a></td><td data-verdict>{verdict}</td></tr>')
    return "".join(rows)


def _window(walk: Walk, said: str | None, label: str, held: dict, *, form: bool) -> str:
    """The window form, one for any time, on the built page and the page the console answers; its
    answer beside it on the page the console answers (each row's time is a link into it). `form` is
    whether the page is the console's answer, kept for its callers."""
    store = walk.store
    shown = escape(said or "")
    #: One plain GET form, on the built page and the page the console answers alike: it reads what is
    #: kept, and runs nothing.
    form = (f'<form method="get" action="{PATH}" data-bisect-window><input type="hidden" name="p" '
            f'value="{escape(label)}"><label>{escape(WINDOW_LABEL)} <input type="text" name="after" '
            f'value="{shown}" maxlength="{MOST_CHARS}"></label> <button type="submit">{escape(WINDOW_BUTTON)}'
            f"</button></form><p>{escape(WINDOW_HINT)}</p>")
    if not form_result(said):
        return form
    when, utc = read_time(said)
    if when is None:
        return form + f'<p data-bisect-window-result="unread">{escape(WINDOW_UNREAD.format(said=said))}</p>'
    got = walk.after(when)
    from onetrace_console.words import time_html
    asked = Drawn(time_html(when.isoformat()))
    out = [f"<p data-bisect-utc>{escape(WINDOW_UTC)}</p>"] if utc else []
    if got["left"] is not None:
        out.append(f'<p data-bisect-window-result="left">'
                   + _said(WINDOW_FOUND, store, when=asked, run=got["left"], step=got["at"]) + "</p>")
        if got["before"] is not None:
            out.append("<div>" + _said(WINDOW_BEFORE, store, run=got["before"]) + " "
                       + _pair(got["before"], got["left"], got["at"] or None, store, held, label) + "</div>")
        if got["gaps"]:
            out.append("<p data-bisect-note>" + _said(WINDOW_GAPS, store, when=asked, n=len(got["gaps"]),
                                                      runs=got["gaps"]) + "</p>")
    else:
        out.append(f'<p data-bisect-window-result="none">{_said(WINDOW_NONE, store, when=asked)}</p>')
        if got["gaps"]:
            out.append("<p data-bisect-note>" + _said(WINDOW_GAPS_NONE, store, when=asked, n=len(got["gaps"]),
                                                      runs=got["gaps"]) + "</p>")
    return form + "".join(out)


def form_result(said: str | None) -> bool:
    """Whether a time was asked, so the form's answer is drawn beside it."""
    return said is not None and bool(said.strip())


def render_bisect(pipeline, store: Store, *, generated_at: str, after: str | None = None,
                  held: dict | None = None, compute: bool | None = None, form: bool = False) -> str:
    """The pipeline's page; `after`, the window form's time as asked. `compute`: make the reference
    and verdicts where none is kept; by default a local console does and a public one never does."""
    from onetrace_console.choose_pages import held_comparisons
    from onetrace_console.pipeline_pages import named, page_href as pipeline_href
    from onetrace_console.render import _document, _tag
    from onetrace_console.viewer.page import shortened_in_text
    from onetrace_console.words import generated_footer, scroll_region
    compute = (not _public()) if compute is None else (compute and not _public())
    label = pipeline.label
    body = ['<p class="crumbs" data-section="crumbs"><a href="home.html">Overview</a> / '
            f'<a href="{_tag(pipeline_href(label))}">{escape(label)}</a> / {escape(TITLE)}</p>',
            f"<h1>{escape(TITLE)} · {named(pipeline)}</h1>"]
    try:
        walk = Walk(pipeline, store, compute=compute)
    except (StoreError, ValueError) as e:
        walk, unreadable = None, str(e)
    if walk is not None and walk.doc is not None:
        held = held_comparisons(store) if held is None else held
        body.append(answer_html(walk, held))
    bench = None
    if walk is not None and walk.doc is not None:
        made = walk.ref.get("runs") or []
        bench = store.get_run(made[0]) if made else None
    how = _said(HOW, store, run=bench) if bench is not None else escape(HOW_NO_REFERENCE)
    body.append(f'<div data-section="bisect-how"><p>{how}</p></div>'
                f'<details data-section="bisect-rule"><summary>{escape(RULE_HEAD)}</summary>'
                f'<p data-section="what">{escape(WHAT)}</p><p data-section="bisect-leaves">{escape(LEAVES)}</p></details>')
    if walk is None:
        body.append(f'<p data-section="bisect-unreadable">{escape(unreadable)}</p>')
    if walk is not None and walk.doc is None:
        body.append(f'<p data-section="bisect-no-reference">{escape(NO_REFERENCE)}</p>')
        reason = (walk.ref or {}).get("refused") or (walk.ref or {}).get("note")
        if reason:
            body.append(f"<p data-bisect-reason>{escape(NO_REFERENCE_REASON.format(reason=reason))}</p>")
        h, t = MAKE.split("{command}")
        body.append(f"<p data-bisect-make>{escape(h)}<code>{escape(MAKE_COMMAND)}</code>{escape(t)}</p>")
    elif walk is not None:
        head, tail = AGAINST.split("{run}")
        h1, h2 = head.split("{seal}")
        #: One line of text: the seal shown short in it, and the whole value in a fold after it (a closed
        #: Details is a box of its own, so text after one starts a line).
        short, whole = shortened_in_text(str(walk.doc.get("seal", "")))
        body.append(f'<div data-section="bisect-reference"><p data-reference-line>{escape(h1)}{short}'
                    f'{escape(h2)}{_run_link(bench, store) if bench is not None else ""}{escape(tail)}</p>'
                    f"{whole}</div>")
        head = "".join(f"<th>{escape(c)}</th>" for c in STEP_COLUMNS)
        body.append(f"<h2>{escape(STEP_HEAD)}</h2>" + scroll_region(
            f'<table data-section="bisect-steps"><thead><tr>{head}</tr></thead><tbody>{_step_rows(walk, held)}'
            "</tbody></table>", STEP_HEAD, "bisect-steps"))
        body.append(f'<h2>{escape(WINDOW_HEAD)}</h2><div data-section="bisect-window">'
                    f"{_window(walk, after, label, held, form=form)}</div>")
        head = "".join(f"<th>{escape(c)}</th>" for c in RUNS_COLUMNS)
        body.append(f"<h2>{escape(RUNS_HEAD)}</h2>" + scroll_region(
            f'<table data-section="bisect-runs"><thead><tr>{head}</tr></thead><tbody>{_runs_table(walk)}'
            "</tbody></table>", RUNS_HEAD, "bisect-runs"))
        if walk.unplaced:
            body.append(f'<p data-section="bisect-unplaced">{_said(UNPLACED, store, runs=walk.unplaced)}</p>')
    body.append(f'<section data-section="bisect-non-claims"><h2>{escape(NON_CLAIMS_HEAD)}</h2><ul class="plain">'
                + "".join(f"<li>{escape(n)}</li>" for n in NON_CLAIMS) + "</ul></section>")
    body.append(generated_footer(generated_at))
    return _document(f"{TITLE} · {label}", "\n".join(['<div class="cp">', *body, "</div>"]))


def page_for(store: Store, label: str, after: str, *, generated_at: str) -> str | None:
    """The `/bisect` answer: the pipeline's page with the window form's result, read from what is kept
    and nothing run; None where no pipeline has that label."""
    p = next((p for p in _pipelines(store) if p.label == label), None)
    if p is None:
        return None
    return render_bisect(p, store, generated_at=generated_at, after=after[:MOST_CHARS], compute=False,
                         form=True)


_WINDOW_FORM = re.compile(r'<form method="get" action="[^"]*" data-bisect-window>.*?</form><p>[^<]*</p>', re.S)


def exported(page: str) -> str:
    """A first-run-to-leave page as a static export carries it: the window form, a GET to a console that
    isn't there, shown disabled (no form, nothing to submit), with one line, NEEDS_CONSOLE, in place of
    the form's hint."""
    disabled = (f'<p data-bisect-window data-needs-console><label>{escape(WINDOW_LABEL)} <input type="text" '
                f'name="after" value="" maxlength="{MOST_CHARS}" disabled></label> <button type="button" '
                f'disabled>{escape(WINDOW_BUTTON)}</button></p><p data-needs-console>{escape(NEEDS_CONSOLE)}</p>')
    return _WINDOW_FORM.sub(lambda m: disabled, page, count=1)
