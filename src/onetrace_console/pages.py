"""The two pages, rendered by the viewer.

The Execution page is one run's detail, **reusing the viewer's rendering**. Nothing
in this module renders HTML. It materialises a stored run, reads its record, hands the
stored check report to `viewer.model.build_model`, and calls the viewer's own renderers.
If a sentence appears on a console page, the viewer put it there and some decision worded it.

That is the whole point of depending on the canary package rather than copying it: there is
one renderer for the free file and the hosted console, so a reader who has seen one has
seen the other, and a decision about wording lands in both at once.

WHAT THE PAGES READ
-------------------
The **stored** report, never a fresh check. A page is a view of what was checked when the
run was received; re-checking on render would make the page a different claim every time it
was opened, and would be a check button that the reader did not press (the design note forbids
the one they *could* press, and this would be worse).
"""
from __future__ import annotations

from onetrace_console import __version__

import json
import re
from onetrace_console.bounded_json import load_json_bounded
import shutil
import sys
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path

from onetrace_console.checks import COULD_NOT_CHECK, REPEAT_COMMAND
from onetrace_console.preview import label
from onetrace_console.store import StoredRun, Store

#: The generator string the footer carries. The viewer's own default names the viewer; a
#: page produced here says so, because "which program wrote this file" is exactly the kind
#: of generation-time metadata the footer is for.
#: The one product name and version every footer gives.
GENERATOR = f"onetrace-console {__version__}"

ANSWER = "answer.html"
CASE = "case.html"
EXECUTIONS = "executions.html"
#: A run's authorization page, rendered by this console beside the two
#: viewer pages. See `onetrace_console.authorization`.
from onetrace_console.authorization import AUTHORIZATION  # noqa: E402


class PageError(RuntimeError):
    """A page cannot be rendered honestly. Never a blank page and never a guess."""


@dataclass(frozen=True, slots=True)
class RenderedExecution:
    """One run's pages, and the verdict the page was built from."""
    run: StoredRun
    pages: dict[str, str]
    verdict: str
    repeat_command: str


def _envelope(run: StoredRun, store: Store, *, required: bool = True) -> dict | None:
    """The stored check report, or None for a run the check runner has not reached.

    **Required on a detail page, optional in a list**, and the difference is not a
    convenience. A detail page claims to show one run's check, so rendering one with no
    report would be a page that looks checked; it refuses instead.

    A LIST must be able to hold a run nobody has checked yet, because "runs not checked" is
    one of the counts Home shows, and a list that refused to contain them would make that
    count unopenable. `build_model` takes `envelope=None` and the viewer renders its own
    fixed sentences of absence for it -- so the honest rendering already exists and is the
    viewer's, not a blank invented here.
    """
    if not run.check_report:
        if required:
            raise PageError(
                f"run {run.run_id} has no stored check report, so there is nothing for a "
                f"page to show. The check runner runs at ingest; a run without a report is "
                f"a run this console has not checked, and it says so rather than rendering "
                f"a page that looks checked.")
        return None
    return load_json_bounded(store.get(run.check_report).decode("utf-8"), "the check report")


def _model(run: StoredRun, store: Store, generated_at: str, folder: Path, *,
           require_report: bool = True):
    from onetrace_console.viewer.model import build_model
    from onetrace_console.viewer.record import read_record

    from onetrace_console.checks import materialise
    materialise(run, store, folder)
    #: `own_check=True`: the stored report is this console's own run of the pinned verifier
    #: over the stored bundle, made at ingest by `checks.run_and_record` -- the only writer of
    #: a run's `check_report` (tests/test_own_check.py).
    from dataclasses import replace

    from onetrace_console.words import record_href
    #: The run's own record offered for download where a page shortens its words.
    #: The check that ran, named on the "Ran as approved" rung where it has no
    #: plan row. The console runs only its one pinned verifier, so it is named
    #: from the installed distribution; a report stored under an earlier pin is named by today's.
    from importlib.metadata import version
    checker = f"onetrace-verify {version('onetrace-verify')}"
    model = replace(build_model(read_record(folder), _envelope(run, store, required=require_report),
                                generated_at, own_check=True, checker=checker),
                    record_href=record_href(run))
    #: The authorization rung's evidence in this console's own plain words.
    from onetrace_console.viewer.model import Text

    from onetrace_console.words import NO_AUTHORIZATION
    model = replace(model, ladder=tuple(
        replace(r, evidence=((Text(NO_AUTHORIZATION),),)) if r.key == "authorized" else r
        for r in model.ladder))
    return _with_marks(model, run, store)


def _rung_of(model, key: str):
    """The model's ladder rung `key`: exactly one."""
    (rung,) = [r for r in model.ladder if r.key == key]
    return rung


def latest_as_candidate(run: StoredRun, store: Store):
    """The most recently stored comparison in which `run` is the candidate,
    by its `ran_at` read as a time, a tie going to the lower comparison key -- the Comparisons
    index's own order (`render._newest_first`). A comparison in which the run is the baseline
    never counts. None where there is none."""
    from onetrace_console.render import _newest_first
    mine = [c for c in store.comparisons() if c.run_b == run.key]
    return min(mine, key=_newest_first) if mine else None


def _strict_diff_report(comparison, store: Store):
    """That comparison's `diff` report, through the viewer's strict reader (two_run_dag=True), or
    None where there is none or it does not pass."""
    from onetrace_console.viewer.verbs import TwoRun, TwoRunDag, read_report

    from onetrace_console.compare import DIFF
    from onetrace_console.store import create_exclusively
    run = comparison.verb(DIFF)
    if run is None or run.note or not any(n == "diff.json" for n, _ in run.reports):
        return None
    with tempfile.TemporaryDirectory(prefix="onetrace-marks-") as tmp:
        folder = Path(tmp)
        try:
            for name, key in run.reports:
                (folder / name).parent.mkdir(parents=True, exist_ok=True)
                create_exclusively(folder / name, store.get(key), named=name)
            report = read_report(folder, two_run_dag=True)
        except Exception:  # noqa: BLE001 - said on the page as "could not be read"
            return None
    return report if isinstance(report, (TwoRun, TwoRunDag)) and report.verb == DIFF else None


def _with_marks(model, run: StoredRun, store: Store):
    """The run page's graph marked from `latest_as_candidate`. Each node
    carries the verdict in the compare page's words and the SDK's own annotations, every first
    difference marked; the line above the graph names the comparison. With no comparison the
    model is returned untouched, so the page is the page it always was."""
    from onetrace_console.viewer.verbs import TwoRunDag

    from onetrace_console.render import _RESULT_WORDS
    comparison = latest_as_candidate(run, store)
    if comparison is None:
        return model
    try:
        baseline = store.get_run(comparison.run_a)
    except Exception:  # noqa: BLE001 - named by its key instead
        baseline = None
    name = baseline.run_id if baseline is not None else comparison.run_a[:12]
    href = f"../../diff/{comparison.key}.html"
    report = _strict_diff_report(comparison, store)
    from onetrace_console.viewer.model import _framed
    if report is None:
        return replace(model, graph_source=(name, comparison.ran_at, href, False),
                       changed=(_framed("comparison.could_not_check", "reason",
                                        "the comparison's report could not be read"),))
    #: A graph-shaped report names each node by its id; a linear one by its position, which is
    #: the step's emission index in the candidate.
    by = ({r.node: r for r in report.ladder} if isinstance(report, TwoRunDag)
          else {r.index: r for r in report.ladder})
    nodes = []
    for node in model.graph_nodes:
        row = by.get(node.node_id if isinstance(report, TwoRunDag) else str(node.index))
        if row is None:
            nodes.append(node)
            continue
        notes = tuple(getattr(row, "annotations", ()) or ())
        nodes.append(replace(node, tags=(_RESULT_WORDS.get(row.verdict, row.verdict),), quoted=notes,
                             mark="first" if row.verdict == "FIRST DIFFERENCE" else ""))
    #: "Where it changed" reads the comparison the graph reads, so the two cannot disagree.
    return replace(model, graph_nodes=tuple(nodes), changed=_changed_from(report),
                   graph_source=(name, comparison.ran_at, href, True))


def _changed_from(report) -> tuple:
    """What "Where it changed" says from the comparison the graph reads, in the viewer's own table
    sentences. The viewer words a linear report itself; a graph-shaped one (`TwoRunDag`) it does
    not, so it is said here the same way: "It changed — here is the step where.", with each
    first-difference node quoted from the report."""
    from onetrace_console.viewer.model import Detail, Text, VerbSaid, _framed, changed_said, line
    from onetrace_console.viewer.verbs import TwoRunDag
    if not isinstance(report, TwoRunDag):
        return changed_said(report)
    if report.envelope == "identical":
        return (VerbSaid(line("diff.pass")),)
    if report.envelope == "diverged" and report.first_difference_frontier:
        return (VerbSaid(line("localize.located"), tuple(
            Detail("field.where", Text(node, "check")) for node in report.first_difference_frontier)),)
    frames = {"not comparable": "comparison.not_comparable", "refused": "comparison.refused",
              "could not check": "comparison.could_not_check"}
    return (_framed(frames.get(report.envelope, "comparison.could_not_check"), "reason",
                    report.reason),)


def topology_note_block(case_html: str, run: StoredRun) -> str:
    """The run's one-line topology note, inside the viewer's "What was checked and what was not"
    section, where a check that did not happen belongs. Nothing where there is no note."""
    if not run.topology_note:
        return case_html
    from onetrace_console.words import escape
    section = re.search(r'<section data-section="checked"><h2>[^<]*</h2>', case_html)
    if section is None:
        raise ValueError("cannot show the run's topology note: the case page has no "
                         "\"What was checked\" section to place it in")
    note = f'<p data-section="topology-note">{escape(run.topology_note)}</p>'
    return case_html[:section.end()] + note + case_html[section.end():]


def refusal(e: Exception, *, log: bool = True) -> tuple[str, bool]:
    """(what a page says, whether it is the viewer's own refusal). A refusal the viewer made is
    its own words; anything else is named by its type, never as the viewer's (the second
    review, S1), with the traceback in the operator's log where `log` -- once, on the run's own
    page, not again on every list that holds it."""
    from onetrace_console.viewer.record import RecordError
    if isinstance(e, RecordError):
        return str(e), True
    if log:
        import traceback
        traceback.print_exception(e, file=sys.stderr)
    return f"{type(e).__name__}: {e}", False


def render_execution(run: StoredRun, store: Store, *, generated_at: str) -> RenderedExecution:
    """One run's detail pages: the answer and the case, sealed as the viewer seals them."""
    from onetrace_console.viewer import fingerprint
    from onetrace_console.viewer.page import render_answer, render_case

    from onetrace_console.authorization import authorization_link, render_authorization

    def drawn(folder: Path) -> dict[str, str]:
        model = _model(run, store, generated_at, folder)
        #: In the console's frame a graph node opens its stage page,
        #: a sibling file; the free file keeps the viewer's in-page `#step-N`.
        from onetrace_console.frame import _RENDERING
        from onetrace_console.stage_pages import render_stage_pages, stage_page
        from onetrace_console.receipt_page import RECEIPT, receipt_link, render_receipt
        if _RENDERING.get() is not None:
            model = replace(model, graph_nodes=tuple(
                replace(n, href=stage_page(n.href[len("#step-"):]))
                if n.href.startswith("#step-") else n for n in model.graph_nodes))
        #: Labelled BEFORE sealing, so the fingerprint covers the label. Sealing first and
        #: splicing after would leave a page whose own seal did not describe it.
        from onetrace_console.incident_pages import incidents_block
        from onetrace_console.incidents import derive
        every = derive(store)
        raised = tuple(i for i in every if i.subject == run.key)

        #: Labelled and given its incidents BEFORE sealing, so the fingerprint covers both --
        #: and the case page its link to the authorization page, for the same reason. The
        #: console's frame is filled last before the seal, for the same reason again.
        from onetrace_console.frame import fill_sealed, sealed_framing
        with sealed_framing():
            answer = render_answer(model, ANSWER, sibling=CASE)
            case = render_case(model, CASE, sibling=ANSWER)
        return {
            ANSWER: fingerprint.seal(fill_sealed(incidents_block(
                label(answer, [run]), raised, len(every), store, up="../../"),
                f"runs/{run.key}/{ANSWER}")),
            CASE: fingerprint.seal(fill_sealed(receipt_link(authorization_link(incidents_block(
                topology_note_block(label(case, [run]), run), raised, len(every), store,
                up="../../"))),
                f"runs/{run.key}/{CASE}")),
            AUTHORIZATION: render_authorization(run, generated_at=generated_at, case=CASE),
            #: The run receipt, labelled like the run's other pages.
            RECEIPT: label(render_receipt(run, store, generated_at=generated_at,
                                         anchored=_rung_of(model, "anchored"),
                                         signed=_rung_of(model, "signed")), [run]),
            #: Labelled like the run's other pages: every page that shows a preview run says so.
            **{name: label(page, [run]) for name, page
               in render_stage_pages(run, store, generated_at=generated_at,
                                     anchored=model.anchor_badge,
                                     signed=_rung_of(model, "signed")).items()},
        }

    gone = store.missing(run)
    if gone:
        #: A run the store is missing an object of is not drawn from what is
        #: left: its pages say what is missing, as could not check.
        from onetrace_console.store import MISSING_OBJECT
        from onetrace_console.unreadable import render_incomplete_run
        page = render_incomplete_run(run, MISSING_OBJECT.format(objects=", ".join(gone)),
                                     generated_at=generated_at)
        return RenderedExecution(run=run, pages={
            ANSWER: page, CASE: page,
            AUTHORIZATION: render_authorization(run, generated_at=generated_at, case=CASE)},
            #: Could not check, whatever verdict the passed run carries -- a
            #: caller holding a raw StoredRun, not the store's reading, gets the same.
            verdict=COULD_NOT_CHECK, repeat_command=REPEAT_COMMAND)
    with tempfile.TemporaryDirectory(prefix="onetrace-page-") as tmp:
        try:
            pages = drawn(Path(tmp) / "run")
        except PageError:
            raise
        except Exception as e:  # noqa: BLE001 - stated on the run's page, and logged
            #: The viewer refused the record, or drawing it failed in
            #: a way nobody foresaw -- anywhere from the model to the seal: the third
            #: confirmation review found MemoryError in `render_answer`. Both pages say so, and
            #: one run never takes the others down with it. The authorization page is the same
            #: as any run's.
            from onetrace_console.unreadable import render_unreadable_run
            reason, from_viewer = refusal(e)
            page = render_unreadable_run(run, reason, generated_at=generated_at,
                                         from_viewer=from_viewer)
            pages = {ANSWER: page, CASE: page,
                     AUTHORIZATION: render_authorization(run, generated_at=generated_at,
                                                         case=CASE)}
    return RenderedExecution(run=run, pages=pages, verdict=run.check_verdict,
                             repeat_command=REPEAT_COMMAND)


def _list_row(run: StoredRun, store: Store, folder: Path):
    """What a list shows of one run: the viewer's `list_row`, never its full model, or
    (why not, whether the viewer said so) where it refused the record. Read from the
    run's record where its check kept the row: a list then reads no receipt."""
    from onetrace_console.viewer.model import ListRow, list_row
    from onetrace_console.viewer.record import read_record

    from onetrace_console.checks import materialise
    from onetrace_console.words import record_href
    kept = _kept_row(run.list_row)
    if kept is not None:
        if "refused" in kept:
            return kept["refused"], kept["from_viewer"]
        return ListRow(run_id=run.run_id, record_href=record_href(run), **kept)
    materialise(run, store, folder)
    return replace(list_row(read_record(folder)), record_href=record_href(run))


def _kept_row(text: str) -> dict | None:
    """A list row the run's check kept, or None where there is none or it is not one."""
    if not text:
        return None
    try:
        kept = load_json_bounded(text, "the kept report row")
    except ValueError:
        return None
    if not isinstance(kept, dict):
        return None
    if set(kept) == {"refused", "from_viewer"}:
        ok = isinstance(kept["refused"], str) and isinstance(kept["from_viewer"], bool)
    else:
        ok = (set(kept) == {"case_ran", "case_for", "step_count", "case_for_more"}
              and isinstance(kept["case_ran"], str) and isinstance(kept["case_for"], str)
              and all(isinstance(kept[k], int) and not isinstance(kept[k], bool)
                      and kept[k] >= 0 for k in ("step_count", "case_for_more")))
    return kept if ok else None


#: Fixed wording for the console's Runs page only: it is exactly the list of
#: the stored runs, so the free file's "It is not a view of a store, and nothing is summarised
#: across runs" is untrue in the console. The free viewer file keeps its own sentence.
RUNS_STORED = ("Runs stored: {n} of {n}, and this page lists every one of them. Nothing is "
               "summarised across runs on this page.")
#: Fixed wording for every other list a count opens: in the console each is drawn from the
#: store, so "not a view of a store" is untrue there too. The free file keeps its own. One form
#: each for none, one and several runs; the last sentence follows every one.
RUNS_IN_LIST = {0: "Runs in this list: none of the {T} stored.",
                1: "Runs in this list: 1 of {T} stored, and this page lists it.",
                2: "Runs in this list: {n} of {T} stored, and this page lists all {n}."}
SUMMARISED = " Nothing is summarised across runs on this page."


def runs_in_list(n: int, total: int) -> str:
    """The sentence a filtered list of `n` of the `total` stored runs carries."""
    return RUNS_IN_LIST[min(n, 2)].format(n=n, T=total) + SUMMARISED


def _runs_stored(page: str, given: int, of: int, sentence: str, section: str) -> str:
    """A list page with the viewer's corpus sentence replaced by the console's fixed one."""
    from onetrace_console.viewer.page import escape as viewer_escape
    from onetrace_console.viewer.sentences import template
    said = (template("executions.one").format(total=of) if given == 1
            else template("executions.corpus").format(n=given, total=of))
    old = f"<p>{viewer_escape(said)}</p>"
    if page.count(old) != 1:
        raise RuntimeError("the viewer's corpus sentence is not on the list exactly once, so "
                           "the console's cannot replace it")
    return page.replace(old, f'<p data-section="{section}">{viewer_escape(sentence)}</p>')


def render_executions(runs: list[StoredRun], store: Store, *, generated_at: str,
                      of: int | None = None, file_name: str = EXECUTIONS,
                      rows: dict | None = None, every_stored: bool = False,
                      filtered: bool = False) -> str:
    """The list of stored runs. Rows are addressed by the directory they came from.

    `of` is the size of the set these runs were chosen from (a count carries its
    denominator): the runs stored, for a list a Home tally opens. None means the list
    is every run it was given.

    Unlinked: the runs are inside the store, addressed by content, and there is no
    directory on the reader's disk to point at. `hrefs=None` is the viewer's own answer for
    a caller with nowhere honest to link to, and taking it is better than inventing a URL
    for a page that does not exist yet.

    A row is the run's record only -- its id, when it ran, what it was for, its steps -- so no
    check report is read for it: a run nobody has checked is listed like any other. `rows`,
    where given, holds each run's row by key across the lists of one render, so each run is
    read once however many lists hold it. `every_stored` says the list is every
    stored run, the Runs page, which says so in the fixed words; `filtered` says it
    is a list of some of them, which says so in its own fixed words.
    """
    from onetrace_console.viewer.page import render_executions as viewer_render_executions

    from onetrace_console.unreadable import unshowable_runs_block

    rows = {} if rows is None else rows
    shown, refused = [], []
    with tempfile.TemporaryDirectory(prefix="onetrace-list-") as tmp:
        for i, run in enumerate(runs):
            if run.key not in rows:
                try:
                    rows[run.key] = _list_row(run, store, Path(tmp) / f"run-{i}")
                except Exception as e:  # noqa: BLE001 - named below the list, and logged
                    rows[run.key] = refusal(e, log=False)
            row = rows[run.key]
            if isinstance(row, tuple):
                #: Named below the list with the viewer's reason, never dropped from it
                #: The count keeps it in its denominator.
                refused.append((run, *row))
            else:
                shown.append(row)
        from onetrace_console.frame import fill_sealed, sealed_framing
        with sealed_framing():
            page = viewer_render_executions(shown, generated_at, GENERATOR, file_name,
                                            hrefs=None, of=len(runs) if of is None else of)
        total = len(runs) if of is None else of
        if every_stored:
            page = _runs_stored(page, len(shown), total, RUNS_STORED.format(n=len(runs)),
                                "runs-stored")
        elif filtered:
            page = _runs_stored(page, len(shown), total,
                                runs_in_list(len(runs), total), "runs-in-list")
    #: Sealed as the viewer seals its own list, AFTER the console's splices so the fingerprint
    #: covers them, under the page's own file name: the console never sealed these, and every
    #: list printed 0000... as its fingerprint (the third confirmation review, NEW-3).
    from onetrace_console.viewer import fingerprint
    return fingerprint.seal(fill_sealed(label(unshowable_runs_block(page, refused), runs),
                                        file_name))
