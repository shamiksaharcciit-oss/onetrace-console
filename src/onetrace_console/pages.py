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
#: The run page's "Proof" view (`views`).
RUN_PROOF = "proof.html"
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


#: The verifier's options that name a file of the reader's: shown by the file's name alone.
EVIDENCE_OPTIONS = ("--trust", "--tsa-cert", "--tsa-root", "--decisions", "--permit-issuers", "--nested-run")


def shown_command(command: tuple[str, ...]) -> tuple[str, ...]:
    """`command` as a page shows it: each evidence option's file by its name alone, whichever
    system's separators the path was written with. Everything else as it ran."""
    import re
    out = list(command)
    for i, arg in enumerate(out[:-1]):
        if arg in EVIDENCE_OPTIONS:
            out[i + 1] = re.split(r"[\\/]", out[i + 1])[-1] or out[i + 1]
    return tuple(out)


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
    #: "Repeat the check" names each evidence file by its name alone, as the receipt page's
    #: command does: the stored report keeps the command as it ran, with the path on this
    #: console's machine, which says nothing a reader can use and shows how the machine is laid out.
    model = replace(model, report_command=shown_command(model.report_command))
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
    from onetrace_console.records import unchecked_sides
    run = comparison.verb(DIFF)
    if run is None or run.note or not any(n == "diff.json" for n, _ in run.reports):
        return None
    #: A side that couldn't be checked: nothing the SDK's diff says of the pair is read.
    if unchecked_sides(comparison, store):
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


#: A node's fact lines, from the record: its output files, or, for a stage retried after a failed
#: attempt, its attempts (the store's retry rule, `ingest.delivered_and_retries`).
NODE_OUTPUTS = ("{n} output file", "{n} output files")
NODE_ATTEMPTS = "{n} attempts"
#: A step with steps inside it (onetrace 0.5's `children`), on its box.
NODE_INSIDE = ("{n} step inside", "{n} steps inside")


def _with_node_facts(model):
    """Each graph node's lines on the run page: one fact taken from the record -- the step's
    output files, or "N attempts" for a stage retried after a failed attempt -- and its chip: the
    comparison's verdict where the page is marked from one, otherwise what the check found for
    the step, in the step table's own words. The boxes draw three lines, so a comparison's quoted
    setting keeps its place."""
    import re as _re
    from collections import Counter
    from html import unescape

    from onetrace_console.viewer.page import _line
    steps = {s.index: s for s in model.steps}
    order = sorted(model.graph_nodes, key=lambda n: n.index)
    failed: set[str] = set()
    retried: set[str] = set()
    for n in order:
        if n.name in failed:
            retried.add(n.name)
        if n.failed:
            failed.add(n.name)
    attempts = Counter(n.name for n in order)
    nodes = []
    for n in model.graph_nodes:
        step = steps.get(str(n.index))
        if step is None:
            nodes.append(n)
            continue
        if n.name in retried:
            fact = NODE_ATTEMPTS.format(n=attempts[n.name])
        else:
            count = len(step.outputs) + step.outputs_more
            fact = NODE_OUTPUTS[count != 1].format(n=count)
        check = (" ".join(unescape(_re.sub(r"<[^>]+>", " ", _line(step.check[0]))).split())
                 if step.check else "")
        tags = (n.tags + (fact,)) if n.tags else ((fact, check) if check else (fact,))
        #: A step with steps inside it says how many, after the record's fact (a box's first line
        #: after its chip); its box opens its step's page, which lists them (onetrace 0.5's `children`).
        try:
            kids = load_json_bounded(step.raw, "a receipt", "show").get("children")
        except (ValueError, AttributeError, RecursionError):
            kids = None
        if isinstance(kids, list) and kids:
            at = tags.index(fact) + 1
            tags = (tags[:at] + (NODE_INSIDE[len(kids) != 1].format(n=len(kids)),) + tags[at:])[:3]
        nodes.append(replace(n, tags=tags))
    return replace(model, graph_nodes=tuple(nodes), graph_tag_lines=3)


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
        from onetrace_console.records import UNCHECKED_MARKS, unchecked_sides
        from onetrace_console.viewer.model import VerbSaid, line
        unchecked = unchecked_sides(comparison, store)
        #: The console's own words where a side couldn't be checked, never set as the verb's.
        changed = (_framed("comparison.could_not_check", "reason",
                           "the comparison's report could not be read") if not unchecked else
                   VerbSaid(line("comparison.could_not_check", reason=(UNCHECKED_MARKS.format(
                       name=unchecked[0][1].run_id, role=unchecked[0][0]), "page"))))
        return replace(model, graph_source=(name, comparison.ran_at, href, False),
                       changed=(changed,))
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
                if n.href.startswith("#step-") else n for n in model.graph_nodes),
                #: A line wraps at four boxes a row, as the comparison's does, read row by row.
                graph_wrap=4)
            model = _with_node_facts(model)
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
        #: The run's head, in place of the viewer's header, before the seal so the fingerprint
        #: covers it.
        from onetrace_console.run_head import run_head, with_head
        first = next((s.index for s in model.steps if s.index.isdigit()), "")
        case = with_head(case, run_head(run, store, model, receipt=RECEIPT,
                                        stage_page=stage_page(first) if first else ""))
        #: F5: the answer page and the authorization page carry the same head, their tabs to the
        #: run page's views; the authorization page keeps its own heading, so its run is the
        #: head's title line, not a second h1.
        answer = with_head(answer, run_head(run, store, model, receipt=RECEIPT, page=CASE,
                                            stage_page=stage_page(first) if first else ""),
                           anchors=False)
        authorization_head = run_head(run, store, model, receipt=RECEIPT, page=CASE,
                                      stage_page=stage_page(first) if first else "", title_tag="p",
                                      rungs=False)
        #: The run page as its two views, split before the seal so each view's fingerprint covers
        #: that view: "What changed" at the page's address, "Proof" its sibling.
        from onetrace_console import views
        #: onetrace 0.5's records, where the run holds them: gated steps and their decisions, the
        #: span context, steps inside steps (`run_panels`), before the seal like every block here.
        from onetrace_console.run_panels import with_sections
        whole = receipt_link(authorization_link(incidents_block(
            topology_note_block(with_sections(label(case, [run]), run, store), run), raised, len(every),
            store, up="../../")))
        #: A mark beside each count of checks, its note read from the verifier's own rows.
        from onetrace_console import info_mark
        from onetrace_console.home import _envelope as _stored
        from onetrace_console.run_panels import manifest_of
        chain = [e.get("file", "") for e in manifest_of(run, store).get("chain") or [] if isinstance(e, dict)]
        whole = info_mark.splice(whole, info_mark.rows_of(_stored(run, store)), chain)
        #: Steps inside steps in the table of steps: each child under its calling step, each nested
        #: run a row of its own (`nesting_ladder`); a run with neither is left as it is.
        from onetrace_console.nesting_ladder import run_ladder
        from onetrace_console.run_panels import held_runs
        from onetrace_console.stage_pages import _steps
        whole = run_ladder(whole, _steps(run, store), held_runs(store))
        #: "What changed?": the comparison a stated rule picks for this run (`what_changed`).
        from onetrace_console import what_changed
        from onetrace_console.frame import rendering_public
        from onetrace_console.run_panels import BEFORE
        at = whole.find(BEFORE)
        if at >= 0:
            whole = whole[:at] + what_changed.section(run, store, public=rendering_public()) + whole[at:]
        said, state = views.run_said(run, store)
        what, proof = views.split(whole, "run", CASE, views.RUN_PROOF, said, state)
        #: The answer and authorization pages' tabs into the run page, at the view that holds them.
        answer = views.retarget(answer, what, proof, CASE, views.RUN_PROOF)
        authorization_head = views.retarget(authorization_head, what, proof, CASE, views.RUN_PROOF)
        return {
            ANSWER: fingerprint.seal(fill_sealed(incidents_block(
                label(answer, [run]), raised, len(every), store, up="../../"),
                f"runs/{run.key}/{ANSWER}")),
            CASE: fingerprint.seal(fill_sealed(what, f"runs/{run.key}/{CASE}")),
            views.RUN_PROOF: fingerprint.seal(fill_sealed(_check_names(proof, views.RUN_PROOF),
                                                          f"runs/{run.key}/{views.RUN_PROOF}")),
            AUTHORIZATION: render_authorization(run, generated_at=generated_at, case=CASE,
                                                head=authorization_head),
            #: The run receipt, labelled like the run's other pages.
            RECEIPT: label(render_receipt(run, store, generated_at=generated_at,
                                         anchored=_rung_of(model, "anchored"),
                                         signed=_rung_of(model, "signed"),
                                         agree=_rung_of(model, "records-agree")), [run]),
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
            ANSWER: page, CASE: page, RUN_PROOF: page,
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
            pages = {ANSWER: page, CASE: page, RUN_PROOF: page,
                     AUTHORIZATION: render_authorization(run, generated_at=generated_at,
                                                         case=CASE)}
    return RenderedExecution(run=run, pages=pages, verdict=run.check_verdict,
                             repeat_command=REPEAT_COMMAND)


def _check_names(page: str, name: str) -> str:
    """A view's "Check it yourself" command, naming that view's own file."""
    from onetrace_console.viewer.page import _code
    from onetrace_console.viewer.slot import STANDALONE_CHECK
    return page.replace(_code(STANDALONE_CHECK.format(file=CASE)), _code(STANDALONE_CHECK.format(file=name)))


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


#: The console's own words for its runs lists: the free file's "The runs this page was given"
#: suits a file someone hands over, not a console's list of what it stores; and the column says
#: "When it ran", not the bare "ran".
LIST_TITLE_ALL = "Every run stored here"
LIST_TITLE_FILTERED = "The runs in this list"
LIST_RAN = "When it ran"


def _plain_list_words(page: str, every_stored: bool) -> str:
    from onetrace_console.viewer.page import escape as viewer_escape
    from onetrace_console.viewer.sentences import template
    title = LIST_TITLE_ALL if every_stored else LIST_TITLE_FILTERED
    given = viewer_escape(template("title.executions"))
    for old, new in ((f"<title>{given}</title>", f"<title>{title}</title>"),
                     (f"<h1>{given}</h1>", f"<h1>{title}</h1>"),
                     (f"<th>{viewer_escape(template('field.ran'))}</th>", f"<th>{LIST_RAN}</th>")):
        if page.count(old) != 1:
            raise RuntimeError(f"the runs list does not carry {old!r} exactly once")
        page = page.replace(old, new)
    return page


#: The runs list's columns (F1): the run, its pipeline, its two times, how far it got, and the three
#: answers the store holds per run, each as the run's own page says it.
RUN_COLUMNS = ("Run", "Pipeline", "When it ran", "Received by this console", "How far it got",
               "Records agree", "Signed by a known recorder", "Committed by a known time",
               "Ran as approved")
#: Each reading the store keeps, as the run page's rung state (`data-state`).
_SIGNED_STATE = {"yes": "yes", "untrusted": "signed-untrusted", "failed": "no", "unsigned": "unsigned",
                 "couldnt-check": "couldnt-check", "unreadable": "couldnt-check",
                 "not-installed": "not-checked", "": "not-checked"}
_ANCHORED_STATE = {"yes": "yes", "couldnt-check": "couldnt-check", "failed": "no",
                   "not-anchored": "not-anchored", "": "not-checked"}
#: "Ran as approved": the run page's states, and "Couldn't check" wherever the plan can't be
#: decided -- the verifier has no plan row, or the run doesn't verify, so its rows aren't read.
_APPROVED_STATE = {"approved": "yes", "departed": "no", "edges-mismatch": "no", "no-plan": "not-declared",
                   "not-a-graph-run": "not-a-graph-run", "cant-check": "couldnt-check", "no-paths": "couldnt-check",
                   "does-not-verify": "couldnt-check", "couldnt-check": "couldnt-check",
                   "not-checked": "not-checked", "": "not-checked"}


def run_answers(run: StoredRun, store: Store) -> dict[str, str]:
    """{rung: state} for the three answers the store holds per run, each by the rule the Overview
    counts it by, so a row, the Overview and the run's own page cannot disagree; and "Ran as
    approved", as the run's own page reads it, recorded when the run is checked."""
    from onetrace_console import records
    return {"records-agree": records.state(run, store), "signed": _SIGNED_STATE.get(run.signed, "not-checked"),
            "anchored": _ANCHORED_STATE.get(run.anchored, "not-checked"),
            "approved": _APPROVED_STATE.get(run.approved, "couldnt-check")}


def _short_line(run: StoredRun, store: Store) -> str:
    """The run's "What changed" line for the runs list: a row of its own under the run's, across the
    table, holding the short answer against the run the stated rule picks; "" where that comparison
    is not held (the run's page says why). A row, not a column: the table fills its frame at desktop
    width already."""
    from onetrace_console.what_changed import NOT_COMPARED, runs_line
    from onetrace_console.words import escape
    import re as _re
    said = runs_line(run, store)
    if said == NOT_COMPARED:
        return ""
    line = _re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(said))
    return (f'<tr class="what-changed-row" data-what-changed-of="{run.key}"><td colspan="{len(RUN_COLUMNS)}" '
            f'data-answer="what-changed">What changed: {line}</td></tr>')


def runs_table(runs: list[StoredRun], store: Store) -> str:
    """The runs list's table: one row per run, in the order given, each linked to its page."""
    from onetrace_console import tones
    from onetrace_console.overview import pipelines, ran_at
    from onetrace_console.run_head import declined_chip
    from onetrace_console.viewer.page import _named
    from onetrace_console.viewer.page import escape as viewer_escape
    from onetrace_console.viewer.sentences import template
    from onetrace_console.words import record_href, rest, scroll_region, time_html
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}

    def chip(state: str) -> str:
        return (f'<span class="pill {tones.tone(tones.RUNG, state)}" data-state="{state}">'
                f'{viewer_escape(template("rung.state." + state.replace("-", "_")))}</span>')

    rows, lines = [], {}
    for run in runs:
        lines[run.key] = _short_line(run, store)
        answers = run_answers(run, store)
        ran = ran_at(run)
        got = (f"{run.delivered_stages} of {run.stage_count} declared stages"
               + (f"; {run.retries} retr{'y' if run.retries == 1 else 'ies'} recorded" if run.retries else ""))
        rows.append(
            #: The run id capped as every page caps a record word: its whole is in its record.
            f'<tr data-run="{_named(run.run_id)}" data-key="{run.key}">'
            #: The id capped inside its link; after it, what was left out and the record offered.
            f'<td><a href="runs/{run.key}/case.html"><span class="mono" data-words="record">'
            f"{_named(run.run_id)}</span></a>{rest(run.run_id, record_href(run))}</td>"
            f'<td>{viewer_escape(label.get(run.key, ""))}</td>'
            f'<td class="value">{time_html(ran) if ran else "not recorded"}</td>'
            f'<td class="value">{time_html(run.received_at)}</td>'
            f"<td>{viewer_escape(got)}{(' ' + stopped) if (stopped := declined_chip(run)) else ''}</td>"
            + "".join(f'<td data-answer="{k}">{chip(answers[k])}</td>'
                      for k in ("records-agree", "signed", "anchored", "approved"))
            + "</tr>"
            #: "What changed?": a row of its own where the rule's comparison is held, put in after
            #: the cells are labelled by column (it is under none), at its empty placeholder.
            + (f'<tr data-what-changed-slot="{run.key}"></tr>' if lines[run.key] else ""))
    head = "".join(f"<th>{c}</th>" for c in RUN_COLUMNS)
    table = scroll_region(f'<table class="timeline" data-section="runs-table"><thead><tr>{head}</tr>'
                          f"</thead><tbody>{''.join(rows)}</tbody></table>", "The runs", "runs")
    for key, line in lines.items():
        if line:
            table = table.replace(f'<tr data-what-changed-slot="{key}"></tr>', line)
    return table


_VIEWER_RUNS = re.compile(r'(<section data-section="executions"><h2>[^<]*</h2>.*?)<table class="timeline">.*?</table>',
                          re.S)


def _with_runs_table(page: str, runs: list[StoredRun], store: Store) -> str:
    """`page` with the viewer's table of runs replaced by the console's, its section and sentences
    kept; refused if the viewer's table isn't there exactly once."""
    if len(_VIEWER_RUNS.findall(page)) != 1:
        raise RuntimeError("the runs list does not carry the viewer's table exactly once")
    from onetrace_console.words import RELATIVE_TIME_SCRIPT
    page = _VIEWER_RUNS.sub(lambda m: m.group(1) + runs_table(runs, store), page, count=1)
    return page.replace("</main>", RELATIVE_TIME_SCRIPT + "</main>", 1) if runs else page


NO_RUNS = "No run is listed here."


def _without_runs_table(page: str) -> str:
    if len(_VIEWER_RUNS.findall(page)) != 1:
        raise RuntimeError("the runs list does not carry the viewer's table exactly once")
    return _VIEWER_RUNS.sub(lambda m: m.group(1) + f'<p class="zero" data-section="no-runs">{NO_RUNS}</p>',
                            page, count=1)


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
            #: The watched folder, as on the Overview: on the list of every run only.
            from onetrace_console.render import watched_section
            watched = watched_section()
            if watched and "</header>" in page:
                page = page.replace("</header>", "</header>" + watched, 1)
        elif filtered:
            page = _runs_stored(page, len(shown), total,
                                runs_in_list(len(runs), total), "runs-in-list")
    page = _plain_list_words(page, every_stored)
    #: F1: the console's own table of the runs it listed, those the viewer refused said below as
    #: before.
    if shown:
        listed = [r for r in runs if not isinstance(rows.get(r.key), tuple)]
        page = _with_runs_table(page, listed, store)
    else:
        #: A list with no run in it (a count at zero): no empty table, one grey line, its sentence
        #: kept -- the Overview's zeros, folded the same way.
        page = _without_runs_table(page)
    #: Sealed as the viewer seals its own list, AFTER the console's splices so the fingerprint
    #: covers them, under the page's own file name: the console never sealed these, and every
    #: list printed 0000... as its fingerprint (the third confirmation review, NEW-3).
    from onetrace_console.viewer import fingerprint
    return fingerprint.seal(fill_sealed(label(unshowable_runs_block(page, refused), runs),
                                        file_name))
