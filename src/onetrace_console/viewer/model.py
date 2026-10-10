"""What the two views show, decided from the record and the check's report. No HTML.

Every state on the page is resolved here into a key of the translation table
(`viewer/sentences.py`), and every number is produced by a function in this module and
labelled with the state it came from (019 §5). `page.py` renders what this module carries
and decides nothing.

This module computes no fingerprint. Whether a step's bytes are what the record says is the
check's finding, carried from its report; this module only counts and sorts findings.

A SENTENCE IS A LINE OF PARTS
-----------------------------
A table sentence with a slot — *"It declined to answer, and says why: {reason}."* — becomes
a `Line`: the table's words as page parts, and the slot filled by a **quotation** marked
with whose words it is (the record's, or the check's). The page never splices a quotation
into its own sentence as if it had written it, and never shows an unfilled placeholder:
`line()` raises on a slot with no value.

THE VERDICT STRIP, AND WHAT MAY NEVER STAND ALONE
--------------------------------------------------
Three states from 019 §2.1, chosen in this order:

1. any finding **contradicted** → *the record contradicts itself at step N*;
2. any finding **not run** for a reason other than originality → *one step could not be
   checked from here*;
3. otherwise → *every step checks out*.

A record that is not anchored gets its originality sentence **beside** the strip in every
state. Verifier specification §4.6: "a verifier that lets a green chain imply originality
is lying by omission" — and a page is no better placed than a verifier to omit it. No
report, or an unreadable one, gets a strip that says so and shows no checkmark.
"""
from __future__ import annotations

from onetrace_console import __version__ as _console_version

import json
import re
from dataclasses import dataclass

from onetrace_console.viewer.record import Record, RecordUnreadable, Step, unshowable
from onetrace_console.viewer.report import CLI_COMMAND, SOURCE_TEXT, Finding, Report, ReportUnreadable, parse
from onetrace_console.viewer.sentences import STEP_WORDS, template
from onetrace_console.viewer.verbs import (DagNode, Failure, LadderRow, Reproduce, ReproduceRow, SingleRun, SingleRunDag, TwoRun, boundary_covers)

#: The one product name and version every footer gives.
GENERATOR = f"onetrace-console {_console_version}"

#: At most this many items of any one list are drawn on a page, then
#: "…and N more". Round 4 found a 3.9 KB upload drawing a million gaps, 39 MB of run pages.
LIST_CAP = 100
#: The same finding's other half: a text shown verbatim -- a receipt's bytes, the check's output
#: -- is one item, not a list, and a million gaps made it 44 MB of page. At most this many
#: characters of it are drawn, then "…and N more characters". Its fingerprint, on the same page,
#: is how a reader checks the whole file.
TEXT_CAP = 65_536
#: A run_id or stage name longer than this is shown as its first NAME_CAP
#: characters, then "… (+N more characters)", with the whole value in the run's record. The page
#: applies it to every record word it quotes. Comparisons and keys always use the whole value.
NAME_CAP = 256


def name_shown(name: str) -> str:
    """A name as a page shows it within text: whole, or its first NAME_CAP characters and a count
    of the rest. For a name quoted on its own, the page caps it itself (`page._part`)."""
    name = str(name)
    if len(name) <= NAME_CAP:
        return name
    from onetrace_console.viewer.sentences import template
    return name[:NAME_CAP] + " " + template("name.more").format(n=str(len(name) - NAME_CAP))

_SLOT = re.compile(r"(\{\w+\})")


# ------------------------------------------------------------------ carried structures

@dataclass(frozen=True, slots=True)
class Text:
    """One part of a line, and whose words it is.

    `page`    this generator's words, from the table; vocabulary-checked.
    `value`   a count or a timestamp the page fills in; no words of anyone's.
    `record`  the record's own words, quoted.
    `check`   the check's own words, quoted.
    """

    text: str
    source: str = "page"


Line = tuple[Text, ...]


def line(key: str, **slots: tuple[str, str]) -> Line:
    """A table sentence as parts. Each slot value is `(text, source)`. Missing slots raise."""
    parts: list[Text] = []
    for piece in _SLOT.split(template(key)):
        m = re.fullmatch(r"\{(\w+)\}", piece)
        if m:
            if m.group(1) not in slots:
                raise KeyError(f"sentence {key!r} needs {m.group(1)!r}; nothing was given")
            text, source = slots[m.group(1)]
            parts.append(Text(text, source))
        elif piece:
            parts.append(Text(piece))
    return tuple(parts)


@dataclass(frozen=True, slots=True)
class Item:
    name: str
    size: str
    media_type: str
    fingerprint: str
    trust: str


@dataclass(frozen=True, slots=True)
class StepView:
    index: str
    total: str
    words: str                       # the step's name in plain words (or as recorded)
    stage: str                       # the stage name, as recorded
    ran: Line                        # "Ran as …" / "Read by …"
    started: str
    ended: str
    inputs: tuple[Item, ...]
    outputs: tuple[Item, ...]
    sentences: tuple[Line, ...]      # state sentences, in table order
    check: tuple[Line, ...]          # what the check found for this step
    outcome_words: Line              # the timeline's fixed words
    boundary: bool
    instrument_id: str
    instrument_version: str
    constants: str                   # the record's constants, verbatim JSON
    manifest_fingerprint: str
    raw: str                         # the receipt's bytes, as text
    findings: tuple[str, ...]        # the check's lines for this step, verbatim
    inputs_more: int = 0             # items past LIST_CAP, counted not drawn
    outputs_more: int = 0


@dataclass(frozen=True, slots=True)
class Detail:
    """A value beside a sentence: the label's key (empty for none), and whose words it is.

    An empty label is not an oversight. 030 §3's frames already carry the verb's reason inside
    the sentence, and several 019 rows are a sentence followed by a quotation with nothing to
    call it — the refusal's reason, the instrument's own words. Inventing a label for those
    would add a word core did not rule.
    """

    label: str
    value: Text


@dataclass(frozen=True, slots=True)
class VerbSaid:
    """One thing a verb's report says, as the page will show it.

    `sentence` is always from the translation table; `details` are labelled quotations from the
    report. `step` is the record step index it belongs to, or None for the run as a whole.
    """

    sentence: Line
    details: tuple[Detail, ...] = ()
    step: str | None = None


@dataclass(frozen=True, slots=True)
class Strip:
    state: str                       # "holds" | "not_checked" | "contradicts" | "none"
    sentence: Line
    beside: tuple[Line, ...]
    tone: str                        # "ok" | "bad" | "neutral"


@dataclass(frozen=True, slots=True)
class CheckCount:
    label: str
    state: str                       # the finding state the number counts
    count: int
    sentence: Line
    quotes: tuple[Text, ...] = ()


@dataclass(frozen=True, slots=True)
class Rung:
    """One rung of the run's evidence ladder (v6 board 2): a question, its state, its evidence.

    `state` is the rung's own slug (`yes`, `no`, `couldnt-check`, `not-checked`,
    `not-yet-available`, `no-records`); `state_key` is the table key its words come from.
    `evidence` is one or more lines, each a sentence from the table wherever one already says
    it. A rung is never blank: every state carries its evidence.
    """

    key: str
    state: str
    state_key: str
    evidence: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class PageModel:
    run_id: str
    is_preview: bool
    strip: Strip
    answer: tuple[Line, ...]
    question: tuple[Line, ...]
    steps: tuple[StepView, ...]
    unchecked: tuple[tuple[Line, ...], ...]
    case_ran: str
    case_for: str
    changed: tuple[VerbSaid, ...]
    reproduced: tuple[VerbSaid, ...]
    boundary_steps: tuple[str, ...]
    checked: tuple[CheckCount, ...]
    not_checked: tuple[CheckCount, ...]
    report_output: str | None
    #: Whether the words shown came through the text fallback. A flag and not the
    #: source's name: the renderer is not allowed to know what inputs exist
    #: (`test_structure.py` enforces it), and it does not need to -- it needs to
    #: know whether to say so.
    report_is_fallback: bool
    report_command: tuple[str, ...]
    report_verifier: str          # the verifier's path as a reader would type it
    report_where: str
    report_ran_at: str
    report_problem: str | None
    manifest_raw: str
    generated_at: str
    #: The run's evidence ladder (v6 board 2). Required: a page built without one would
    #: render no rungs, and "no rungs" is not a state any rung is allowed to be in.
    ladder: tuple[Rung, ...]
    generator: str = GENERATOR
    #: Declared stage names past LIST_CAP, counted not drawn.
    case_for_more: int = 0
    #: Where the run's own record can be downloaded, for a page that shortens its words
    #: -- the caller's to give; None where it has none to offer.
    record_href: str | None = None
    #: False when the check's rows cannot be read one by one (30bv §3.3): its output is then
    #: drawn whole, every character escaped, and no row is shown as a row.
    report_rows_readable: bool = True
    #: The execution graph's inputs: one node per step, and the manifest's
    #: `edges` as recorded -- None when the manifest carries no `edges` (a run read as a line).
    #: `graph_unreadable` is True when `edges` is there but is not a list of links each naming
    #: a `from` and a `to`: then no graph is drawn, and the page says why, rather than drawing
    #: the run as a line or as a graph with no links, neither of which the record says.
    graph_nodes: tuple = ()
    graph_edges: tuple | None = None
    graph_unreadable: bool = False
    #: Where the graph's verdict marks come from, when the caller gives them --
    #: (the baseline run, when that comparison was stored, a link to its page, whether its
    #: report passed the strict reader). None: no comparison, and the page is as it always was.
    graph_source: tuple | None = None
    #: The manifest index of the step that wrote the answer, "" where none
    #: did; the answer page's receipt disclosure holds that step's receipt card.
    answer_step: str = ""
    #: The manifest's format, which the preview banner names; and the declared
    #: stages whose last recorded attempt failed, as ((stage, error type), ...) in declared order.
    preview_format: str = ""
    last_failed: tuple = ()
    #: The check ran as the installed `onetrace-verify`: regenerated with
    #: `generate --cli`, which has no verifier path to name.
    report_cli: bool = False
    #: The answer view's anchor sentence, from the page's own check.
    answer_anchor: tuple[Line, ...] = ()
    #: The stage page's anchoring badge, the run's own rung in its words.
    anchor_badge: Rung | None = None

    @property
    def step_count(self) -> int:
        return len(self.steps)


# ---------------------------------------------------------------------- engine functions

def count_findings(report: Report, outcome: str, subject: str | None = None,
                   exclude_property: str | None = None) -> int:
    """How many findings of one outcome, optionally about one subject. The only counter."""
    return sum(1 for f in report.findings
               if f.outcome == outcome
               and (subject is None or f.subject == subject)
               and (exclude_property is None or f.property != exclude_property))


#: The subject of a run-level row: a finding about the run as a whole, not about one of its
#: receipts or its manifest. `onetrace-verify` 0.1.2 prints one, `run: artifacts`. It is shown
#: on its own line beside the strip, never as a step.
RUN_SUBJECT = "run"
#: Rows about the run as a whole: `run:` rows, and rows that name no subject at all -- 0.2.0's two
#: graph rows, read from `--json`. Neither is a step's; the second kind is
#: drawn in the "Ran as approved" rung, not beside the strip.
WHOLE_RUN = frozenset({RUN_SUBJECT, ""})
#: A record beside the chain, at run level like `run:` -- exactly
#: `anchors/<name>.json` or `signatures/<name>.json` (one segment after the folder, no backslash,
#: nothing after `.json`), whose file is in the run, compared by code point. Anything else under
#: those folders stays "not in this run".
_BESIDE = re.compile(r"(?:anchors|signatures)/[^/\\]+\.json")


def beside_subject(subject: str, record: Record) -> bool:
    if not _BESIDE.fullmatch(subject) or subject.split("/", 1)[1] in (".json", "..json"):
        return False
    path = record.run_dir / subject
    return path.is_file() and path.parent.name == subject.split("/", 1)[0]


def _whole_run(record: Record, report: Report) -> frozenset:
    """The subjects about the run as a whole in this report: `run:`, the subject-less rows, and the
    records beside the chain."""
    return WHOLE_RUN | {f.subject for f in report.findings if beside_subject(f.subject, record)}


def _run_rows(report: Report) -> list[Finding]:
    return [f for f in report.findings if f.subject == RUN_SUBJECT]


def _run_line(f: Finding) -> Line:
    """One run-level row as its own line: the check's name and reason in the check's words."""
    said = line(f"run_row.{f.outcome}", check=(f.property, "check"))
    return said + ((Text(" "), Text(f.detail, "check")) if f.detail else ())


def count_steps(report: Report, outcome: str, steps: dict,
                exclude_property: str | None = None) -> int:
    """How many distinct steps have at least one finding of an outcome (023 §3 Q2)."""
    return len({f.subject for f in report.findings
                if f.outcome == outcome and f.subject in steps
                and (exclude_property is None or f.property != exclude_property)})


def count_gaps(step: Step) -> int:
    """How many items a step records as not processed."""
    gaps = step.data.get("emission", {}).get("gaps", [])
    return len(gaps) if isinstance(gaps, list) else 0


def missing_stages(record: Record) -> tuple[str, ...]:
    """Declared stages that no receipt in the run reports emitting.

    `coverage.completeness` is **per receipt and cumulative**: in the SDK's own runs, steps
    1-3 read `incomplete` because not every declared stage had emitted *yet*, and the last
    step reads `complete`. Read per step it says nothing about the run, so 019 §4's sentence
    — *"Part of this run wasn't recorded"* — is a claim about the run and is decided here,
    from the whole record: a declared stage that appears in no receipt's emitting list.
    Taking any one step's `incomplete` for the run's state said that three times over a run
    that was completely recorded.
    """
    declared: list[str] = []
    #: A lookup set beside the ordered list: `not in` a list made this quadratic, and 20,000
    #: declared names (a 48 KB upload) took 38 s per page (round 4, B3).
    seen: set[str] = set()
    emitting: set[str] = set()
    for s in record.steps:
        cov = s.data.get("coverage", {})
        for name in cov.get("declared_stages", []) or []:
            if str(name) not in seen:
                seen.add(str(name))
                declared.append(str(name))
        emitting.update(str(n) for n in (cov.get("emitting_stages", []) or []))
    return tuple(name for name in declared if name not in emitting)


# ------------------------------------------------------------------------ the decisions

#: What the page shows for a stage whose recorded name is empty. The
#: page's words, never quoted as the record's -- the record named nothing, and an empty
#: quotation said it had.
UNNAMED_STAGE = "(unnamed stage)"


def _stage(step: Step) -> str:
    """The stage name exactly as recorded. What rows are matched against; see `_stage_shown`."""
    return str(step.data.get("stage", {}).get("name", step.manifest_stage))


def _stage_shown(step: Step) -> tuple[str, str]:
    """The stage name for a sentence's slot: the record's own words, or the page's for none."""
    name = _stage(step)
    return (name, "record") if name.strip() else (UNNAMED_STAGE, "page")


def _named_stage(name: str) -> str:
    """A stage as a page names it: the name it was recorded under, then the console's friendlier
    words for it in brackets where there are any. The friendlier words never stand in its place."""
    friendly = STEP_WORDS.get(name)
    return name_shown(name) + (f" ({friendly})" if friendly else "")


def _words(step: Step) -> str:
    return _named_stage(_stage(step)) if _stage(step).strip() else UNNAMED_STAGE


def _more(n: int) -> Line:
    """The line after a capped list: "…and N more"."""
    return line("list.more", n=(str(n), "value"))


def _case_for(declared) -> tuple[str, int]:
    """The declared stages as the list and case pages name them: the first LIST_CAP, and how
    many more there are."""
    names = list(declared) if isinstance(declared, list) else []
    shown = " → ".join(_named_stage(str(n)) for n in names[:LIST_CAP])
    return shown, max(0, len(names) - LIST_CAP)


def _items(entries) -> tuple[Item, ...]:
    return tuple(Item(name=str(e.get("name", "")), size=str(e.get("bytes", "")),
                      media_type=str(e.get("media_type", "")),
                      fingerprint=str(e.get("digest", "")), trust=str(e.get("trust_class", "")))
                 for e in (entries if isinstance(entries, list) else []) if isinstance(e, dict))


def _recorded_reason(oc: dict) -> tuple[str, str]:
    """The reason a refusal states, or C030 §3's words when it states none (C034 §2 R1).

    019 §2.2's sentence promises the record "says why". Where the record says nothing, the
    page said `says why: .` — it asserted a reason existed and rendered an empty placeholder
    with a dangling stop. C030 §3 had already fixed that shape for the verbs' frames; C034 §2
    R1 puts a recorded refusal under the same rule. The words are the page's, not the
    record's, and are marked as the page's so no quotation claims the record wrote them.
    """
    words = str(oc.get("reason", "") or "")
    given = bool(words.strip())
    return (words if given else NO_REASON, "record" if given else "page")


def _error_is_whole(oc: dict) -> bool:
    """Whether a recorded error carries the two fields its ruled sentence names.

    019 §4's sentence is *"Failed — {status}: {body}."* and §3.2's is *"failed — {status}:
    {body}"*. Both placeholders are the record's; neither is optional, and the delivered format
    agrees — `rejection/R06-error-without-body.json` is a vector a conforming verifier **must
    refuse**, for the stated reason: *"an HTTP error without its body is a status code wearing
    an explanation."*

    Where the record cannot fill them, the page does not fill them for it and does not quietly
    drop the step either (the three-outcome rule: malformed is surfaced, never skipped). It
    falls through to `outcome.unknown` — ruled wording — which shows the outcome exactly as
    recorded, so the reader sees the status code and sees that nothing explains it.
    """
    return bool(str(oc.get("status", "") or "").strip()
                and str(oc.get("body", "") or "").strip())


def _outcome_lines(step: Step) -> tuple[Line, Line]:
    """(the card's state sentence, the timeline's fixed outcome words)."""
    oc = step.data.get("outcome", {})
    cls = oc.get("class")
    if cls == "ok":
        return line("outcome.ok"), line("outcome.ok")
    if cls == "refused":
        reason = _recorded_reason(oc)
        return line("outcome.refused", reason=reason), line("timeline.refused", reason=reason)
    if cls == "error" and _error_is_whole(oc):
        status, body = (str(oc["status"]), "record"), (str(oc["body"]), "record")
        origin = str(oc.get("origin", "") or "").strip()
        # Bench Record 047 ruled a third field into the card's sentence, for the state where
        # the record names an origin. Where it does not, 019 §4's two-field sentence keeps its
        # state: the format requires a body (rejection/R06) and requires no origin, so an
        # error without one is conforming and must not lose its sentence — nor be given a
        # field the page composed. 047 ruled on `outcome.error` alone; §3.2's timeline form
        # is untouched, and carries status and body in both states.
        card = (line("outcome.error_origin", status=status, body=body,
                     origin=(origin, "record"))
                if origin else line("outcome.error", status=status, body=body))
        return card, line("timeline.error", status=status, body=body)
    # An error missing the status or the body its ruled sentence names falls through here:
    # the record is shown exactly as recorded, rather than rendered into a sentence whose
    # placeholders the record cannot fill. See `_error_is_whole` (C034 §2 R12, F14).
    shown = Text(json.dumps(oc, ensure_ascii=False, sort_keys=True), "record")
    unknown = line("outcome.unknown") + (Text(" "), shown)
    return unknown, unknown


def _state_sentences(step: Step) -> tuple[Line, ...]:
    d = step.data
    out = [_outcome_lines(step)[0]]
    if str(d.get("instrument", {}).get("rederivable", "")) == "false":
        out.append(line("rederivable.false"))
    n = count_gaps(step)
    if n:
        out.append(line("emission.gaps", n=(str(n), "value")))
    # `coverage.completeness` is not shown per step: it is cumulative, and the sentence for
    # it is a claim about the run. See `missing_stages`.
    anchor = d.get("anchor", {})
    if anchor.get("state") == "anchored":
        date = anchor.get("date") or anchor.get("time")
        out.append(line("anchor.anchored", date=(str(date), "record")) if date
                   else line("anchor.anchored_no_date"))
    return tuple(out)


def _ran(step: Step) -> Line:
    inst = step.data.get("instrument", {})
    ident, version = (str(inst.get("id", "")), "record"), (str(inst.get("version", "")), "record")
    if inst.get("kind") == "generator" and version[0] == "pinned":
        return line("card.read_by", id=ident)
    return line("card.ran_as", id=ident, version=version)


def _check_lines(report: Report | None, subject: str) -> tuple[Line, ...]:
    if report is None:
        return ()
    mine = [f for f in report.findings if f.subject == subject]
    out: list[Line] = []
    fails = [f for f in mine if f.outcome == "fail"]
    for f in fails:
        out.append(line("check.fail",
                        reason=(f.property + (f" — {f.detail}" if f.detail else ""), "check")))
    if not fails and any(f.outcome == "pass" for f in mine):
        out.append(line("check.pass"))
    for f in mine:
        if f.outcome == "not_run":
            out.append(line("check.not_run.originality") if f.property == "originality"
                       else line("not_run.other") + (Text(" "), Text(f.detail, "check")))
    return tuple(out)


def _unanchored(record: Record) -> bool:
    return any(s.data.get("anchor", {}).get("state") == "unanchored" for s in record.steps)


def _strip(record: Record, report: Report | None, problem: str | None) -> Strip:
    beside = (line("check.not_run.originality"),) if _unanchored(record) else ()
    if problem is not None:
        return Strip("none", line("strip.unreadable"), beside, "neutral")
    if report is None:
        return Strip("none", line("strip.not_performed"), beside, "neutral")
    #: Run-level rows are read here, beside the strip, and nowhere below as a step: the strip's
    #: own state is decided from the steps and the manifest, except that a run-level FAIL is a
    #: FAIL the verifier reported, so the strip says the check failed (30bv §3.2).
    beside += tuple(_run_line(f) for f in _run_rows(report))
    #: A time in a headline: drawn short, the full value kept (page.py, source "time").
    date = (report.ran_at, "time")
    #: 30bz §3: the check's NOT VERIFIED (exit 2): a receipt names a format it does not implement,
    #: so its content was not read. Never "holds", never "contradicts".
    if report.overall == "not_verified":
        return Strip("not_checked", line("strip.not_verified", date=date), beside, "neutral")
    #: 30bv §3.3: rows a record broke apart. The verdict is the exit status and the summary's;
    #: no row is trusted, so no step is named and none is shown as checked.
    if not report.rows_readable:
        beside += (line("rows.unreadable"),)
        if report.overall == "fail":
            return Strip("contradicts", line("strip.rows_unread_fail", date=date), beside, "bad")
        return Strip("holds", line("strip.rows_unread_pass", date=date), beside, "ok")
    by_file = {s.file: s for s in record.steps}
    whole = _whole_run(record, report)
    fails = [f for f in report.findings if f.outcome == "fail" and f.subject not in whole]
    if not fails and any(f.outcome == "fail" and f.subject in whole for f in report.findings):
        return Strip("contradicts", line("strip.contradicts_run", date=date), beside, "bad")
    if fails:
        steps = count_steps(report, "fail", by_file)
        if steps == 1:
            only = next(by_file[f.subject] for f in fails if f.subject in by_file)
            return Strip("contradicts",
                         line("strip.contradicts", date=date, n=(only.manifest_index, "record")),
                         beside, "bad")
        if steps > 1:
            return Strip("contradicts",
                         line("strip.contradicts_n", date=date, n=(str(steps), "value")),
                         beside, "bad")
        return Strip("contradicts", line("strip.contradicts_list", date=date), beside, "bad")
    if any(f.outcome == "not_run" and f.property != "originality" and f.subject not in whole
           for f in report.findings):
        steps = count_steps(report, "not_run", by_file, exclude_property="originality")
        if steps == 1:
            return Strip("not_checked", line("strip.not_checked_one", date=date), beside, "neutral")
        if steps > 1:
            return Strip("not_checked",
                         line("strip.not_checked_n", date=date, n=(str(steps), "value")),
                         beside, "neutral")
        return Strip("not_checked", line("strip.not_checked_list", date=date), beside, "neutral")
    return Strip("holds", line("strip.holds", date=date), beside, "ok")


def last_attempt_failed(record: Record) -> tuple[tuple[str, str], ...]:
    """For the free file as for the console: each declared stage
    whose LAST recorded attempt has outcome class `error`, with its `status` (the SDK writes the
    exception's type) as the error type, in the declared order. Retried until it succeeded: not
    counted; "declined" (`refused`): not an error; a declared stage with no attempt is missing,
    which the ladder already states. The console derives the same from the same receipts."""
    declared: list[str] = []
    last: dict[str, tuple[str, str]] = {}
    for s in record.steps:
        coverage = s.data.get("coverage")
        names = coverage.get("declared_stages") if isinstance(coverage, dict) else None
        for name in names if isinstance(names, list) else ():
            if isinstance(name, str) and name not in declared:
                declared.append(name)
        stage, outcome = s.data.get("stage"), s.data.get("outcome")
        name = stage.get("name") if isinstance(stage, dict) else None
        if isinstance(name, str) and isinstance(outcome, dict):
            status = outcome.get("status")
            last[name] = (outcome.get("class"), status if isinstance(status, str) else "")
    return tuple((name, last[name][1]) for name in declared
                 if name in last and last[name][0] == "error")


def _answer_step(record: Record) -> str:
    """The manifest index of the step that wrote the answer -- the last generator, as `_answer`
    reads it -- or "" where no step did."""
    gen = [s for s in record.steps if s.data.get("instrument", {}).get("kind") == "generator"]
    return gen[-1].manifest_index if gen else ""


def _answer(record: Record) -> tuple[tuple[Line, ...], tuple[Line, ...]]:
    # Only a record that HAS a question says anything about one. The SDK's ingestion runs
    # carry no question input at all, and "the question's text is not part of this record
    # package" told a reader there was a question whose text had been withheld.
    asked = [i for i in _items(record.steps[0].data.get("inputs")) if i.name == "question"]
    question = ((line("question.not_in_package"),)
                + tuple((Text(i.fingerprint, "record"),) for i in asked[:LIST_CAP])
                + ((_more(len(asked) - LIST_CAP),) if len(asked) > LIST_CAP else ())
                ) if asked else ()
    gen = [s for s in record.steps if s.data.get("instrument", {}).get("kind") == "generator"]
    if not gen:
        return (line("answer.no_step"),), question
    step = gen[-1]
    oc = step.data.get("outcome", {})
    if oc.get("class") == "refused":
        words, kind = _recorded_reason(oc)
        return (line("answer.refused") + (Text(" "), Text(words, kind)),), question
    if oc.get("class") == "error":
        return (_outcome_lines(step)[0],), question
    outputs = _items(step.data.get("outputs"))
    return ((line("answer.not_in_package"),)
            + tuple((Text(i.fingerprint, "record"),) for i in outputs[:LIST_CAP])
            + ((_more(len(outputs) - LIST_CAP),) if len(outputs) > LIST_CAP else ())), question


def _unchecked(record: Record, report: Report | None) -> tuple[tuple[Line, ...], ...]:
    rows: list[tuple[Line, ...]] = []
    for s in record.steps:
        n = count_gaps(s)
        if n:
            gaps = s.data["emission"]["gaps"]
            named = tuple((Text(json.dumps(g, ensure_ascii=False, sort_keys=True), "record"),)
                          for g in gaps[:LIST_CAP])
            if len(gaps) > LIST_CAP:
                named += (_more(len(gaps) - LIST_CAP),)
            rows.append((line("unchecked.gaps_at_step", n=(str(n), "value"),
                              step=_stage_shown(s)),) + named)
    incomplete = bool(missing_stages(record))
    # 023 §4: "Every step that was declared left a receipt; nothing is missing from the trail."
    # True only when no step records a gap AND no step says the run was partly unrecorded:
    # shown beside "Part of this run wasn't recorded", it would contradict it.
    if not any(count_gaps(s) for s in record.steps) and not incomplete:
        rows.append((line("checks.gaps_none"),))
    if incomplete:
        rows.append((line("coverage.incomplete"),))
    if _unanchored(record):
        rows.append((line("unchecked.unanchored"), line("anchoring.would_add")))
    if report is not None:
        for f in report.findings:
            #: A run-level row is on its own line beside the strip, not in this list (30bv §3.2).
            if (f.outcome == "not_run" and f.property != "originality"
                    and f.subject not in _whole_run(record, report)):
                rows.append((line("not_run.other") + (Text(" "), Text(f.detail, "check")),))
    return tuple(rows)


def reproduce_said(row: ReproduceRow) -> VerbSaid:
    """029 §6: one re-check row onto its sentence, with the report's own words beside it.

    The five outcomes are kept apart exactly as the report keeps them. `declared` is the record
    telling the truth about itself and gets 019 §4's model-step sentence; `unavailable` is this
    reader's reach and gets the access-problem sentence, whose "what would resolve it" is the
    report's `reason`; `mismatch` has no ruled row and carries core's proposed wording.
    """
    if row.outcome == "REPRODUCED":
        return VerbSaid(line("reproduce.pass"), step=row.index)
    if row.outcome == "DIVERGED":
        details = []
        for key, side in (("field.recorded_result", row.recorded), ("field.new_result", row.produced)):
            if side:
                details.append(Detail(key, Text(json.dumps(side, ensure_ascii=False,
                                                           sort_keys=True), "record")))
        return VerbSaid(line("reproduce.fail"), tuple(details), row.index)
    if row.category == "declared":
        # 019's sentence, then the instrument's own words. No label, by design.
        words = (Detail("", Text(row.declared, "record")),) if row.declared else ()
        return VerbSaid(line("rederivable.false"), words, row.index)
    if row.category == "unavailable":
        # 019's row ends "here is what would resolve it", and 029 §6 says the reason is it.
        why = (Detail("", Text(row.reason, "check")),) if row.reason else ()
        return VerbSaid(line("reproduce.not_run.unavailable"), why, row.index)
    return VerbSaid(line("reproduce.not_run.mismatch"), mismatch_digests(row), row.index)


#: The two digests a mismatch reason carries, in the order the reason states them: the one the
#: record names, then the one on this machine.
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def mismatch_digests(row: ReproduceRow) -> tuple[Detail, ...]:
    """030 §1: beneath the sentence, the two digests labelled *ran* and *available here*,
    "nothing else".

    If the reason does not carry exactly two, the reason is shown unchanged instead — the page
    will not guess which digest is which — and that report is a finding to send to core rather
    than a shape to accommodate quietly.
    """
    found = _DIGEST.findall(row.reason or "")
    if len(found) != 2:
        return (Detail("", Text(row.reason, "check")),) if row.reason else ()
    return (Detail("field.ran", Text(found[0], "record")),
            Detail("field.available_here", Text(found[1], "check")))


#: 030 §3: when an envelope requires a reason and the report carries none, the frame renders
#: with these words. The page does not write the reason the verb should have written — and the
#: report goes to core as a finding.
NO_REASON = "(no reason given)"


def _framed(key: str, slot: str, words: str | None) -> VerbSaid:
    """One of 030 §3's fixed frames, filled with the verb's own words, set as the verb's."""
    given = bool(words and words.strip())
    return VerbSaid(line(key, **{slot: (words if given else NO_REASON,
                                        "check" if given else "page")}))


def _envelope_reason(report: TwoRun) -> str | None:
    """The reason a no-result frame is filled with (030 §3, corrected by 031 §2).

    C029 §2 said the envelope's `reason` is set whenever the envelope is not identical or
    diverged. 031 §2 corrects that for the boundary case: at `c325c94` a `could not check`
    caused by a declared boundary carries `reason: null`, and the verb's words live in the
    ladder rows, whose reason begins `declared boundary '<name>'`. So the frame fills from the
    first COULD NOT CHECK row rather than saying no reason was given — the words exist in the
    report, and *(no reason given)* is for a null reason with **no** boundary.
    """
    if report.reason:
        return report.reason
    if report.envelope == "could not check" and report.boundary:
        for row in report.ladder:
            if row.verdict == "COULD NOT CHECK" and row.reason:
                return row.reason
    return None


def _dag_said(report: SingleRunDag) -> tuple[VerbSaid, ...]:
    """R11 as ruled: the set of minimal unclean nodes, sorted by node id, never a first node.

    `Core_Ruling_C034_R11_Corrected_Wording_2026-09-25.md` — the page renders *every node the
    report names, as one set*, labelled as a set and not as a list with an implied order, and no
    sentence chooses one node as "the" answer.

    **Sorted here, not upstream.** The report's order is the emission order, which the exam's
    `dag-r37/run_R` deliberately makes the reverse of the id order. Sorting is the page's act.

    **One sentence, not one per node.** A set is one answer. Where the set has a single member,
    019 §4's `localize.located` already fits it exactly — a set of one *is* a located step — so
    nothing new is worded for that case. The plural takes `localize.located_set`, which is this
    channel's wording and provisional (024 §4), and whose second clause denies the ordering a
    reader would otherwise supply.

    **Each node carries the report's own words, quoted.** The node id and the kind are the
    report's vocabulary, not the page's, so they are marked as the check's words rather than
    written as prose — and no label is invented for them, for the reason `Detail` already gives.
    A boundary never appears here: `walk_dag` does not put one in `nodes`.
    """
    nodes = sorted(report.nodes, key=lambda n: n.node)
    if not nodes:
        return (VerbSaid(line("localize.clean")),)
    head = (line("localize.located") if len(nodes) == 1
            else line("localize.located_set", n=(str(len(nodes)), "check")))
    details = tuple(Detail("", Text(_dag_node_words(n), "check")) for n in nodes)
    return (VerbSaid(head, details),)


def _dag_node_words(node: DagNode) -> str:
    """`<node id> — <kind>: <reason>`, every part the report's own."""
    parts = [node.node, " — ", node.kind]
    if node.words:
        parts += [": ", node.words]
    return "".join(parts)


def changed_said(report) -> tuple[VerbSaid, ...]:
    """What a `diff` or `localize` report lets the page say (029 §6, 030 §§1-3)."""
    if isinstance(report, Failure):
        return (_framed("verb.did_not_start", "reason", report.reason),)
    if isinstance(report, SingleRunDag):
        return _dag_said(report)
    if isinstance(report, SingleRun):
        if report.result == "clean":
            return (VerbSaid(line("localize.clean")),)
        if report.result == "located":
            # The step it located, then the verb's own sentence unlabelled. `check` names which
            # check found it ("outcome", "coverage"); calling that "what changed" would have
            # been a label saying something the field does not, and `words` says it already.
            details = [Detail("field.where", Text(report.stage, "check"))] if report.stage else []
            if report.words:
                details.append(Detail("", Text(report.words, "check")))
            return (VerbSaid(line("localize.located"), tuple(details)),)
        return (_framed("localize.could_not_check", "words", report.words or report.stage),)
    assert isinstance(report, TwoRun)
    if report.envelope == "identical":
        # 029 §6: "and only that" — a ladder with reconverged rows is diverged, and this
        # sentence must not appear for it.
        return (VerbSaid(line("diff.pass")),)
    if report.envelope == "diverged" and report.first_difference:
        details = [Detail("field.where", Text(
            f"{report.first_difference.get('index')} {report.first_difference.get('stage')}", "check"))]
        cause = report.cause or {}
        change, constants = cause.get("instrument_change"), cause.get("constants")
        # An object, or the SDK's own words (`viewer.verbs.CAUSE_WORDS`). "instrument unchanged"
        # lists no change; COULD NOT CHECK is quoted once, unlabelled, with the SDK's reason --
        # surfaced, never dropped, and never set under "what changed" as though it were one.
        if isinstance(change, dict) and change:
            # The SDK writes no id when the instrument itself changed, and its text prints none.
            named = f"{change.get('id')}: " if change.get("id") else ""
            details.append(Detail("field.what_changed", Text(
                f"{named}{change.get('from')} → {change.get('to')}", "check")))
        for key, value in (constants if isinstance(constants, dict) else {}).items():
            # Each constant is [before, after], as the SDK's text prints it.
            shown = (f"{value[0]} → {value[1]}" if isinstance(value, list) and len(value) == 2
                     else f"{value}")
            details.append(Detail("field.what_changed", Text(f"{key}: {shown}", "check")))
        if "COULD NOT CHECK" in (change, constants):
            reason = cause.get("instrument_reason")
            details.append(Detail("", Text(
                "COULD NOT CHECK" + (f": {reason}" if reason else ""), "check")))
        blast = cause.get("blast_radius") or {}
        if blast.get("status") == "counted":
            details.append(Detail("field.reach", Text(
                f"{blast.get('documents_whose_chunk_set_moved')} of {blast.get('documents')} "
                f"documents moved; {blast.get('documents_unmoved')} unmoved", "check")))
        return (VerbSaid(line("localize.located"), tuple(details)),)
    # 030 §3: the envelope's own frame first; 019's per-row boundary sentence still governs
    # the ladder rows beneath it.
    frames = {"not comparable": "comparison.not_comparable", "refused": "comparison.refused",
              "could not check": "comparison.could_not_check"}
    said = ([_framed(frames[report.envelope], "reason", _envelope_reason(report))]
            if report.envelope in frames else [])
    if report.boundary:
        for row in [r for r in report.ladder if boundary_covers(report, r)]:
            said.append(VerbSaid(line("verb.not_run.boundary"),
                                 (Detail("", Text(row.reason or "", "check")),) if row.reason else (),
                                 row.index))
    if not said:
        said.append(_framed("comparison.could_not_check", "reason", report.reason))
    return tuple(said)


def _verb_states(verbs: dict | None) -> tuple[tuple[VerbSaid, ...], tuple[VerbSaid, ...], tuple[str, ...]]:
    """(where it changed, what was re-checked, the step indices a boundary covers).

    031 §3: both sections are on the page, so a section that received no report renders its one
    fixed sentence of absence. Blank would now mean the section is not there at all.
    """
    if not verbs:
        return (line_said("verbs.not_run"),), (line_said("absence.no_recheck"),), ()
    changed: list[VerbSaid] = []
    reproduced: list[VerbSaid] = []
    boundary: list[str] = []
    for name in ("localize", "diff"):
        report = verbs.get(name)
        if report is not None:
            changed.extend(changed_said(report))
            if isinstance(report, TwoRun) and report.boundary:
                boundary.extend(r.index for r in report.ladder if boundary_covers(report, r))
    report = verbs.get("reproduce")
    if isinstance(report, Reproduce) and report.result == "refused":
        # The SDK refused the record before re-running anything: said as a verb that did not
        # start, in the verifier's own words, never as the absence of a re-check.
        reproduced.append(_framed("verb.did_not_start", "reason", report.refused_because))
    elif isinstance(report, Reproduce):
        reproduced.extend(reproduce_said(row) for row in report.stages)
    elif isinstance(report, Failure):
        reproduced.append(changed_said(report)[0])
    if not changed:
        changed.append(line_said("verbs.not_run"))
    if not reproduced:
        reproduced.append(line_said("absence.no_recheck"))
    return tuple(changed), tuple(reproduced), tuple(dict.fromkeys(boundary))


def line_said(key: str) -> VerbSaid:
    return VerbSaid(line(key))


def _step_view(record: Record, report: Report | None, step: Step) -> StepView:
    d = step.data
    inst = d.get("instrument", {})
    return StepView(
        index=step.manifest_index, total=str(len(record.steps)), words=_words(step),
        stage=_stage(step), ran=_ran(step),
        started=str(d.get("time", {}).get("started", "")),
        ended=str(d.get("time", {}).get("ended", "")),
        inputs=_items(d.get("inputs"))[:LIST_CAP], outputs=_items(d.get("outputs"))[:LIST_CAP],
        inputs_more=max(0, len(_items(d.get("inputs"))) - LIST_CAP),
        outputs_more=max(0, len(_items(d.get("outputs"))) - LIST_CAP),
        sentences=_state_sentences(step), check=_check_lines(report, step.file),
        outcome_words=_outcome_lines(step)[1],
        boundary=bool(d.get("coverage", {}).get("boundaries")),
        instrument_id=str(inst.get("id", "")), instrument_version=str(inst.get("version", "")),
        constants=json.dumps(d.get("assertions", {}).get("constants", {}),
                             ensure_ascii=False, sort_keys=True, indent=1),
        manifest_fingerprint=step.manifest_fingerprint,
        raw=step.raw.decode("utf-8"),
        findings=tuple(f.line for f in report.findings if f.subject == step.file) if report else ())


def _checked_lists(record: Record, report: Report) -> tuple[tuple[CheckCount, ...], tuple[CheckCount, ...]]:
    subjects = [s.file for s in record.steps] + ["manifest"]
    #: The run itself is a subject too, and its rows are drawn beside the strip, not listed here.
    #: A row naming no subject is about the run as a whole too: 0.2.0's two graph rows, read from
    #: `--json`, drawn in the "Ran as approved" rung, not listed here.
    stray = sorted({f.subject for f in report.findings} - set(subjects) - _whole_run(record, report))
    if stray:
        raise ReportUnreadable(f"the report has findings about something not in this run: {stray}")
    total = str(len(record.steps))
    labels = {s.file: template("step.of").format(n=s.manifest_index, total=total) + " · " + _words(s)
              for s in record.steps}
    labels["manifest"] = template("label.manifest")
    checked: list[CheckCount] = []
    not_checked: list[CheckCount] = []
    for subj in subjects:
        n_pass = count_findings(report, "pass", subj)
        if n_pass:
            checked.append(CheckCount(labels[subj], "pass", n_pass,
                                      line("checks.held_one") if n_pass == 1
                                      else line("checks.held", n=(str(n_pass), "value"))))
        for f in report.findings:
            if f.subject != subj:
                continue
            if f.outcome == "fail":
                checked.append(CheckCount(labels[subj], "fail", 1, line(
                    "check.fail", reason=(f.property + (f" — {f.detail}" if f.detail else ""), "check"))))
            elif f.outcome == "not_run":
                not_checked.append(CheckCount(
                    labels[subj], "not_run", 1,
                    line("check.not_run.originality") if f.property == "originality"
                    else line("not_run.other") + (Text(" "), Text(f.detail, "check"))))
    return tuple(checked), tuple(not_checked)


# ---------------------------------------------------------------------- the run's ladder
#
# A rung reads yes only when its evidence establishes it. Absent evidence ("not checked"),
# evidence this page cannot read or cannot tie to this run ("couldn't check") and evidence
# against ("no") are kept apart, and none of them is a yes -- the three-outcome rule, which
# the independent review of the first version held this to, finding by finding.

_YES, _NO = ("yes", "rung.state.yes"), ("no", "rung.state.no")
_COULDNT = ("couldnt-check", "rung.state.couldnt_check")
_NOT_CHECKED = ("not-checked", "rung.state.not_checked")
#: Two state words of the signing rung's own. Unsigned is No's finding in its own word (the record
#: holds no signature, as "not anchored" is No); "Signed, key not trusted" is never Yes.
_UNSIGNED = ("no", "rung.state.unsigned")
_SIGNED_UNTRUSTED = ("signed-untrusted", "rung.state.signed_untrusted")

#: A key the record does not carry, told apart from one it carries with a null value.
_ABSENT = object()


def _rung(key: str, state: tuple[str, str], *evidence: Line) -> Rung:
    return Rung(key, state[0], state[1], tuple(evidence))


def _records_agree(record: Record, report: Report | None, strip: Strip,
                   problem: str | None, own_check: bool) -> Rung:
    """Rung 1: the strip's own finding, in the strip's ruled sentence -- and a yes only when
    the report says something that held about every step AND the list of steps.

    A report that says nothing about part of the run still reads "holds" on the strip (that is
    the strip's ruled behaviour, and not this rung's to change); here it is couldn't-check. A
    report that could not be read is couldn't-check too, never the same as no report.

    **Only the page's own run of the check sets this rung**. A report
    that was kept or supplied is shown as a report -- the strip and the lists still read it --
    and never sets the rung, in either direction: the rung says it was handed a report.
    """
    if not own_check and (report is not None or problem is not None):
        return _rung("records-agree", _NOT_CHECKED, line("rung.records.supplied"))
    if problem is not None:
        return _rung("records-agree", _COULDNT, strip.sentence)
    if report is None:
        return _rung("records-agree", _NOT_CHECKED, strip.sentence)
    if not report.rows_readable:
        # 30bv §3.3: a FAIL is a no; a PASS whose rows cannot be read cannot be tied to every step.
        return _rung("records-agree", _NO if report.overall == "fail" else _COULDNT, strip.sentence)
    if strip.state == "holds":
        subjects = [s.file for s in record.steps] + ["manifest"]
        if not all(count_findings(report, "pass", subject) for subject in subjects):
            return _rung("records-agree", _COULDNT, line("rung.records.partial"))
        # The evidence for a yes is the verifier run with
        # `--require-artifacts` returning PASS. Read from the command the check recorded, so it
        # holds for any caller and needs no one's word for it. A check that held without the
        # flag did not look at the run's output files: not checked, never a yes. A FAIL is
        # still a no, with or without it.
        #: Since 0.2.0 the verdict comes from the plain check, and the
        #: evidence for a yes from the same check run again with the outputs required -- only
        #: where the run holds `artifacts/`. Its PASS is a yes, its FAIL a no (the outputs do not
        #: match), anything else couldn't check.
        if report.outputs_required is not None:
            exit_req, result_req = report.outputs_required
            if result_req == "fail":
                return _rung("records-agree", _NO, line("rung.records.outputs_differ"))
            if (exit_req, result_req) != ("0", "pass"):
                return _rung("records-agree", _COULDNT, strip.sentence)
        elif "--require-artifacts" not in report.command:
            return _rung("records-agree", _NOT_CHECKED, line("rung.records.no_artifacts"))
        n = count_findings(report, "pass")
        return _rung("records-agree", _YES, line("checks.held_one") if n == 1
                     else line("checks.held", n=(str(n), "value")))
    state = _NO if strip.state == "contradicts" else _COULDNT
    return _rung("records-agree", state, strip.sentence)


#: What rung 3 reads from each receipt's coverage, and the shape the format gives it.
_COVERAGE_FIELDS = (("declared_stages", list), ("emitting_stages", list),
                    ("completeness", str))
_COMPLETENESS = ("complete", "incomplete")


def _names(value) -> bool:
    """A list of stage names: every item a non-empty string."""
    return all(isinstance(x, str) and x for x in value)


def _nothing_missing(record: Record) -> Rung:
    """Rung 3. Yes only when every receipt says what was declared, what emitted, whether the run
    is complete and what it left out -- and none of it is missing, from the trail itself.

    A field a receipt does not carry is "not checked" (there is nothing to say "nothing is
    missing" from); a field with a shape the format does not give it is "couldn't check", and
    whatever a receipt does carry is shape-checked even beside a field it lacks. Only then are
    the record's own statements read, with the sentences already ruled for them: a declared
    stage no receipt emitted, a declared stage with no receipt in the list of steps, a last
    receipt that is incomplete or whose own lists leave a declared stage unemitted, a gap.
    """
    unstated = False
    for s in record.steps:
        coverage = s.data.get("coverage", _ABSENT)
        emission = s.data.get("emission", _ABSENT)
        present = [part for part in (coverage, emission) if part is not _ABSENT]
        if any(not isinstance(part, dict) for part in present):
            return _rung("nothing-missing", _COULDNT, line("rung.missing.unreadable"))
        if len(present) < 2:
            unstated = True
        fields = []
        if coverage is not _ABSENT:
            fields += [(coverage.get(k, _ABSENT), kind) for k, kind in _COVERAGE_FIELDS]
        if emission is not _ABSENT:
            fields.append((emission.get("gaps", _ABSENT), list))
        for value, kind in fields:
            if value is _ABSENT:
                unstated = True
            elif not isinstance(value, kind):
                return _rung("nothing-missing", _COULDNT, line("rung.missing.unreadable"))
        if coverage is _ABSENT:
            continue
        if not all(_names(coverage.get(k, [])) for k in ("declared_stages", "emitting_stages")):
            return _rung("nothing-missing", _COULDNT, line("rung.missing.unreadable"))
        if coverage.get("completeness", "complete") not in _COMPLETENESS:
            return _rung("nothing-missing", _COULDNT, line("rung.missing.unreadable"))
        if coverage.get("declared_stages") == []:
            unstated = True
    if unstated:
        return _rung("nothing-missing", _NOT_CHECKED, line("rung.missing.unstated"))
    coverages = [s.data["coverage"] for s in record.steps]
    declared = {n for c in coverages for n in c["declared_stages"]}
    in_trail = {_stage(s) for s in record.steps}
    says_complete_and_is_not = any(
        set(c["declared_stages"]) - set(c["emitting_stages"])
        for c in coverages if c["completeness"] == "complete")
    if (missing_stages(record) or coverages[-1]["completeness"] != "complete"
            or declared - in_trail or says_complete_and_is_not):
        return _rung("nothing-missing", _NO, line("coverage.incomplete"))
    gapped = [s for s in record.steps if count_gaps(s)]
    if gapped:
        return _rung("nothing-missing", _NO, *(
            line("unchecked.gaps_at_step", n=(str(count_gaps(s)), "value"),
                 step=_stage_shown(s)) for s in gapped))
    return _rung("nothing-missing", _YES, line("checks.gaps_none"))


def _unreplayable(record: Record) -> list[str]:
    """The steps the record itself declares not replayable, by index."""
    out = []
    for s in record.steps:
        instrument = s.data.get("instrument")
        if isinstance(instrument, dict) and str(instrument.get("rederivable", "")) == "false":
            out.append(s.manifest_index)
    return out


#: How `onetrace.reproduce` derives its exit from the rows, and its result from its exit.
_SDK_RESULT = {"0": "all REPRODUCED", "1": "DIVERGED", "4": "COULD NOT CHECK"}


def _step_outputs(step) -> list | None:
    """The receipt's output digests in its order, or None where any output names no digest --
    nothing is matched against an output the record gives no digest for."""
    outputs = step.data.get("outputs")
    if not isinstance(outputs, list):
        return None
    digests = [o.get("digest") if isinstance(o, dict) else None for o in outputs]
    return digests if all(isinstance(d, str) and d for d in digests) else None


def _bound_to(row, step) -> bool:
    """Whether a row that ran recorded exactly this step's result: its outputs, and its outcome
    class where the row names one."""
    recorded, outputs = row.recorded, _step_outputs(step)
    if not isinstance(recorded, dict) or outputs is None or recorded.get("outputs") != outputs:
        return False
    if "outcome_class" in recorded:
        outcome = step.data.get("outcome")
        return isinstance(outcome, dict) and recorded["outcome_class"] == outcome.get("class")
    return True


def _reproduced(record: Record, verbs: dict | None, agree: str) -> Rung:
    """Rung 4, from a re-check report -- counted only if it is about exactly this run.

    The report must be a whole-run re-check naming this run's id and chain head, with one row
    per step of this record, in order, under the record's own stage names; and the steps it
    calls declared must be the steps the record declares not replayable. Each row that ran
    must carry THIS record's outputs as its recorded result. And the report must agree with
    itself: a REPRODUCED row's two results the same, a DIVERGED row's different, and its exit
    and result the ones `onetrace.reproduce` derives from its rows -- which is also why a yes
    is read from the rows and not from `result`: the SDK writes COULD NOT CHECK whenever any
    row is, a declared row included. Otherwise nothing in it is counted.

    The denominator is the record's replayable steps. A yes needs every one of them re-run and
    matched, and the records to agree (`agree`, rung 1's state): a re-check tied to records the
    check found wanting is never counted as a yes. A different result is still a no -- the
    conservative direction. Anything else is couldn't-check.
    """
    report = (verbs or {}).get("reproduce")
    if report is None:
        return _rung("reproduced", _NOT_CHECKED, line("absence.no_recheck"))
    if getattr(report, "verb", None) != "reproduce":
        return _rung("reproduced", _COULDNT, line("rung.reproduced.other"))
    if isinstance(report, Failure):
        return _rung("reproduced", _COULDNT, changed_said(report)[0].sentence)
    if isinstance(report, Reproduce) and report.result == "refused":
        return _rung("reproduced", _COULDNT,
                     _framed("verb.did_not_start", "reason", report.refused_because).sentence)
    steps = [(s.manifest_index, _stage(s)) for s in record.steps]
    if (not isinstance(report, Reproduce) or report.mode != "whole-run"
            or report.run_id != record.run_id or report.chain_head is None
            or report.chain_head != record.manifest.get("chain_head")
            or [(r.index, r.stage) for r in report.stages] != steps):
        return _rung("reproduced", _COULDNT, line("rung.reproduced.other"))
    for r, step in zip(report.stages, record.steps):
        if r.outcome == "COULD NOT CHECK":
            continue
        if not _bound_to(r, step):
            return _rung("reproduced", _COULDNT, line("rung.reproduced.other"))
        if (r.outcome == "REPRODUCED") != (r.produced == r.recorded):
            return _rung("reproduced", _COULDNT, line("rung.reproduced.inconsistent"))
    outcomes = {r.outcome for r in report.stages}
    exit_code = "1" if "DIVERGED" in outcomes else "4" if "COULD NOT CHECK" in outcomes else "0"
    if report.exit_code != exit_code or report.result != _SDK_RESULT[exit_code]:
        return _rung("reproduced", _COULDNT, line("rung.reproduced.inconsistent"))
    unreplayable = _unreplayable(record)
    if [r.index for r in report.stages if r.category == "declared"] != unreplayable:
        return _rung("reproduced", _COULDNT, line("rung.reproduced.disagrees"))
    covered = [r for r in report.stages if r.category != "declared"]
    matched = sum(1 for r in covered if r.outcome == "REPRODUCED")
    if len(unreplayable) == 1:
        named: tuple[Line, ...] = (line("rederivable.false"),)
    elif unreplayable:
        named = (line("rung.reproduced.declared_n", n=(str(len(unreplayable)), "value")),)
    else:
        named = ()
    if not covered:
        return _rung("reproduced", _NOT_CHECKED, *named)
    count = line("rung.reproduced.count", n=(str(matched), "value"),
                 total=(str(len(covered)), "value"))
    if any(r.outcome == "DIVERGED" for r in covered):
        return _rung("reproduced", _NO, count, *named)
    if matched < len(covered):
        return _rung("reproduced", _COULDNT, count, *named)
    if agree != "yes":
        return _rung("reproduced", _COULDNT, count, *named, line("rung.reproduced.unbound"))
    return _rung("reproduced", _YES, count, *named)


def _anchor_state(value) -> str:
    if value is _ABSENT:
        return "absent"
    if isinstance(value, dict) and value.get("state") in ("anchored", "unanchored"):
        return value["state"]
    return "unreadable"


def _anchored(record: Record) -> Rung:
    """Rung 6, from every receipt's anchor and the list of steps' own.

    **Never a yes in this release.** Nothing here verifies an anchor, and an anchor the record
    declares is not one anybody checked (X-8: anchor only what you have re-verified), so the
    most a declared anchor gets is "not checked". Any step or the list saying unanchored is a
    no; a value this page has no words for is couldn't-check; silence is said as silence.
    """
    states = [_anchor_state(s.data.get("anchor", _ABSENT)) for s in record.steps]
    if "anchor" in record.manifest:
        states.append(_anchor_state(record.manifest["anchor"]))
    if "unanchored" in states:
        return _rung("anchored", _NO, line("rung.anchored.not"))
    if "unreadable" in states:
        return _rung("anchored", _COULDNT, line("rung.anchored.unreadable"))
    if all(st == "absent" for st in states):
        return _rung("anchored", _NOT_CHECKED, line("rung.anchored.unstated"))
    if "absent" in states:
        return _rung("anchored", _NOT_CHECKED, line("rung.anchored.partial"))
    return _rung("anchored", _NOT_CHECKED, line("rung.anchored.unchecked"))


_ATTESTED = re.compile(r", attested (?:block )?time (\S+?)(?:;|$)")


@dataclass(frozen=True, slots=True)
class AnchorReading:
    """What the page's own check says of the anchors beside the chain, as one of
    "yes" (with `time` and `source`), "couldnt-check" or "failed" (with the verifier's `detail`),
    or "not-anchored" (no anchor row)."""

    kind: str
    detail: str = ""
    time: str = ""
    source: str = ""


def anchor_reading(record: Record, report: Report | None, own_check: bool) -> AnchorReading | None:
    """The verifier's anchor rows read once, for the rung, the answer view and the console's
    counts alike: any FAIL is "failed", with the verifier's reason; else a PASS is "yes", at its
    attested time, with the verifier's own words for the source (the earliest time where several
    pass); a PASS whose words give no attested time is "couldnt-check", never a guess; rows not run
    are "couldnt-check", with the verifier's reason; no anchor row is "not-anchored". None without
    the page's own check, whose rows are read: then nothing here read an anchor."""
    if not own_check or report is None or not report.rows_readable:
        return None
    rows = [f for f in report.findings if f.subject.startswith("anchors/")
            and beside_subject(f.subject, record) and f.property == "originality"]
    if not rows:
        return AnchorReading("not-anchored")
    failed = [f for f in rows if f.outcome == "fail"]
    if failed:
        return AnchorReading("failed", detail=failed[0].detail)
    passed = []
    for f in rows:
        if f.outcome == "pass":
            found = _ATTESTED.search(f.detail)
            if found is None:
                return AnchorReading("couldnt-check", detail=f.detail)
            passed.append((found.group(1), f.detail[:found.start()]))
    if passed:
        time, source = min(passed)
        return AnchorReading("yes", time=time, source=source)
    return AnchorReading("couldnt-check", detail=rows[0].detail)


def committed_by_time(record: Record, report: Report | None, own_check: bool) -> Rung:
    """The rung "Committed by a known time", from the verifier's own anchor rows in the
    page's own check (`anchor_reading`) -- never from what a record declares. Without the page's
    own check, the rung says what the record declares and that nothing here checked it
    (`_anchored`)."""
    read = anchor_reading(record, report, own_check)
    if read is None:
        return _anchored(record)
    if read.kind == "not-anchored":
        #: "Not anchored", in the canvas's fixed words for the rung.
        return _rung("anchored", _NO, line("rung.anchored.not"))
    if read.kind == "yes":
        return _rung("anchored", _YES, line("rung.anchored.yes", time=(read.time, "value"),
                                            source=(read.source, "report")))
    state = _NO if read.kind == "failed" else _COULDNT
    return _rung("anchored", state, line("rung.anchored.reason", detail=(read.detail, "report")))


def anchor_badge(record: Record, report: Report | None, own_check: bool) -> Rung:
    """The stage page's anchoring badge: the run's own rung, in the run page's
    words, its Yes naming the whole run's record and its Couldn't check giving the verifier's reason
    alone. Without the page's own check, the record-declared rung, as on the run page."""
    read = anchor_reading(record, report, own_check)
    if read is None:
        return _anchored(record)
    if read.kind == "yes":
        return _rung("anchored", _YES, line("badge.anchored.yes", time=(read.time, "value"),
                                            source=(read.source, "report")))
    if read.kind == "couldnt-check":
        return _rung("anchored", _COULDNT, (Text(read.detail, "report"),))
    return committed_by_time(record, report, own_check)


def answer_anchor(record: Record, report: Report | None, own_check: bool) -> tuple[Line, ...]:
    """The answer view's anchor sentence: an anchor is stated only
    when the verifier's anchor row passes; otherwise the case is stated; with no anchor row, or
    without the page's own check, nothing about anchoring."""
    read = anchor_reading(record, report, own_check)
    if read is None or read.kind == "not-anchored":
        return ()
    if read.kind == "yes":
        return (line("answer.anchor.yes", time=(read.time, "value"), source=(read.source, "report")),)
    key = "answer.anchor.failed" if read.kind == "failed" else "answer.anchor.couldnt_check"
    return (line(key, detail=(read.detail, "report")),)


#: The verifier's own words for a signature row (onetrace_verify/signatures.py at 246ca51, lines
#: 169-199): a trusted signer's label (the reader's trust file's) and key id; an untrusted key id. A
#: record's `signer` is only ever a claim, after the key id, as a JSON string: the label shown is the
#: shortest after which the rest is exactly the key id and that claim, so no claim can move it.
_CLAIM = r'(?: \(claimed signer "(?:[^"\\]|\\.)*"\))?'
_SIGNED_BY = re.compile(r"^signed by (.+?) \((sha256:[0-9a-f]{64})\)" + _CLAIM + "$")
_UNTRUSTED_BY = re.compile(r"^signed by an untrusted key (sha256:[0-9a-f]{64}) -- signer not on the "
                           r"reader's trust list" + _CLAIM + "$")
SIGNATURE_NOT_INSTALLED = "install onetrace-verify[crypto] to check signatures"


@dataclass(frozen=True, slots=True)
class SignatureReading:
    """What the page's own check says of the signatures beside the chain: "yes" (with `label` and
    `key_id`), "untrusted" (with `key_id`), "failed", "unsigned", "not-installed", "couldnt-check"
    (with the verifier's `detail`), or "unreadable" (words this page can't read)."""

    kind: str
    label: str = ""
    key_id: str = ""
    detail: str = ""


def signature_reading(record: Record, report: Report | None, own_check: bool) -> SignatureReading | None:
    """The verifier's signature rows read once, for the rung, the stage badge and the console's
    counts alike, in this order: any FAIL is "failed"; else a trusted signature is
    "yes" (the first, in the rows' order); else an untrusted one; else rows all not run for want of
    the extra are "not-installed"; else "couldnt-check", with the first other row's reason. A pass
    or an untrusted row in words this page can't read is "unreadable", never a guess. No signature
    row is "unsigned". None without the page's own check, whose rows are read."""
    if not own_check or report is None or not report.rows_readable:
        return None
    rows = [f for f in report.findings if f.subject.startswith("signatures/")
            and beside_subject(f.subject, record) and f.property == "signature"]
    if not rows:
        return SignatureReading("unsigned")
    if any(f.outcome == "fail" for f in rows):
        return SignatureReading("failed")
    for f in rows:
        if f.outcome == "pass":
            found = _SIGNED_BY.match(f.detail)
            if found is None:
                return SignatureReading("unreadable", detail=f.detail)
            return SignatureReading("yes", label=found.group(1), key_id=found.group(2))
    for f in rows:
        if f.outcome == "signed_untrusted":
            found = _UNTRUSTED_BY.match(f.detail)
            if found is None:
                return SignatureReading("unreadable", detail=f.detail)
            return SignatureReading("untrusted", key_id=found.group(1))
    if all(f.detail == SIGNATURE_NOT_INSTALLED for f in rows):
        return SignatureReading("not-installed")
    other = next(f for f in rows if f.detail != SIGNATURE_NOT_INSTALLED)
    return SignatureReading("couldnt-check", detail=other.detail)


def signed_by_known_recorder(record: Record, report: Report | None, own_check: bool) -> Rung:
    """The rung "Signed by a known recorder", in its fixed words, from
    `signature_reading` -- never from a record's claim. The label is the trust file's, exactly."""
    read = signature_reading(record, report, own_check)
    if read is None:
        return _rung("signed", _NOT_CHECKED, line("rung.signed.no_own_check"))
    if read.kind == "unsigned":
        return _rung("signed", _UNSIGNED, line("rung.signed.none"))
    if read.kind == "failed":
        return _rung("signed", _NO, line("rung.signed.no"))
    if read.kind == "yes":
        return _rung("signed", _YES, line("rung.signed.yes", label=(read.label, "report"),
                                          key_id=(read.key_id, "value")))
    if read.kind == "untrusted":
        return _rung("signed", _SIGNED_UNTRUSTED, (Text(read.key_id, "value"),))
    if read.kind == "not-installed":
        return _rung("signed", _NOT_CHECKED, line("rung.signed.not_installed"))
    if read.kind == "unreadable":
        return _rung("signed", _COULDNT, line("rung.signed.unreadable"))
    #: The verifier's reason itself; "the check says" is kept for a failed check.
    return _rung("signed", _COULDNT, (Text(read.detail, "report"),))


def nothing_missing(record: Record) -> Rung:
    """Rung 3, "nothing missing", exactly as the run's page decides it -- for a caller that counts
    it across runs (the console's Home: counted by the same test the page uses)."""
    return _nothing_missing(record)


#: The rung "Ran as approved": the verifier's two rows,
#: read by name from its own report. Nothing about the plan is computed here.
PLAN_ROW = "edges conform to declared_edges"
EDGES_ROW = "edges equal the edges derived from the receipts"


@dataclass(frozen=True, slots=True)
class Approval:
    """What the run's own check says of its plan. `state` is one of: `approved`, `departed`,
    `edges-mismatch`, `no-plan`, `not-a-graph-run`, `cant-check`, `does-not-verify`,
    `not-checked`, `couldnt-check`. `detail` is the row's own detail where a state shows one
    (unescaped here; the page escapes it), or the verifier named for `cant-check`."""
    state: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CheckRows:
    """The parts of one run of the check the plan rung reads: its rows as (property, outcome,
    detail) -- outcome `pass`, `fail` or `not_run` -- its exit status and its summary's result
    (`pass`, `fail`, `not_verified`). `readable` is False when the rows can't be read one by one.
    Built by `rows_from_report` (the stored text report) or `rows_from_json` (`--json`)."""
    rows: tuple[tuple[str, str, str], ...]
    exit_status: str
    overall: str
    readable: bool = True


def rows_from_report(report: Report) -> CheckRows:
    return CheckRows(tuple((f.property, f.outcome, f.detail) for f in report.findings),
                     report.exit_status, report.overall, report.rows_readable)


_JSON_OUTCOME = {"PASS": "pass", "FAIL": "fail", "NOT-RUN": "not_run"}
_JSON_RESULT = {"PASS": "pass", "FAIL": "fail", "NOT VERIFIED": "not_verified"}


def rows_from_json(doc: dict, exit_status: str) -> CheckRows:
    """`onetrace-verify --json`'s output, read strictly: a row's name is `<subject>: <property>`,
    or the property alone (0.2.0's two graph rows have no subject). Anything else unexpected --
    a result this reader doesn't know, a summary that disagrees with the exit status -- reads
    as rows that can't be read, never as a guess."""
    try:
        summary = doc["summary"]
        overall = _JSON_RESULT[summary["result"]]
        rows = []
        for row in doc["rows"]:
            name = row["name"]
            subject, sep, prop = name.partition(": ")
            rows.append((prop if sep else name, _JSON_OUTCOME[row["result"]], row["detail"]))
        readable = str(summary["exit"]) == exit_status
    except (KeyError, TypeError, AttributeError):
        return CheckRows((), exit_status, "", False)
    return CheckRows(tuple(rows), exit_status, overall, readable)


def ran_as_approved(manifest: dict, check: CheckRows | None, *, own_check: bool,
                    verifier: str | None) -> Approval:
    """The plan rung's state, from the page's own check only (as "Records agree", 29x §3 item 2).

    In order:
    - no check, or one handed to the page: not checked;
    - its rows can't be read one by one, or a row is there twice: couldn't check;
    - no `edges` in the manifest, and neither row: not a graph run;
    - `edges`, but either row missing: this verifier can't check the plan (0.1.2 has neither);
    - the plan row FAILs: departed from the plan, with its detail;
    - the edges row FAILs: the executed edges don't match the receipts, with its detail;
    - the plan row NOT-RUN: no approved plan recorded;
    - exit 0, the summary PASS and both rows PASS: ran as approved -- never the two
      rows alone;
    - anything else: the run doesn't verify, and its own verdict stands.
    """
    if check is None or not own_check:
        return Approval("not-checked")
    if not check.readable:
        return Approval("couldnt-check")
    found: dict[str, list] = {PLAN_ROW: [], EDGES_ROW: []}
    for prop, outcome, detail in check.rows:
        if prop in found:
            found[prop].append((outcome, detail))
    if any(len(rows) > 1 for rows in found.values()):
        return Approval("couldnt-check")
    plan, edges = (rows[0] if rows else None for rows in found.values())
    graph = isinstance(manifest, dict) and "edges" in manifest
    if plan is None and edges is None and not graph:
        return Approval("not-a-graph-run")
    if plan is None or edges is None:
        return Approval("cant-check", verifier or "")
    if plan[0] == "fail":
        return Approval("departed", plan[1])
    if edges[0] == "fail":
        return Approval("edges-mismatch", edges[1])
    if plan[0] == "not_run":
        return Approval("no-plan")
    if (check.exit_status == "0" and check.overall == "pass"
            and plan[0] == "pass" and edges[0] == "pass"):
        return Approval("approved")
    return Approval("does-not-verify")


#: The plan rung's state, its state word, and its evidence. A straight-line
#: run draws no state word: no badge, one line.
_APPROVAL_RUNG = {
    "approved": (_YES, "rung.approved.yes"),
    "departed": (_NO, "rung.approved.departed"),
    "edges-mismatch": (_NO, "rung.approved.edges"),
    "no-plan": (("not-declared", "rung.state.not_declared"), "rung.approved.no_plan"),
    "not-a-graph-run": (("not-a-graph-run", ""), "rung.approved.linear"),
    "cant-check": (_COULDNT, "rung.approved.cant_check"),
    #: Not "No": that would say the run departed from its plan, which wasn't established.
    "does-not-verify": (("does-not-verify", "rung.state.couldnt_check"), "rung.approved.not_verified"),
    "not-checked": (_NOT_CHECKED, "rung.approved.not_checked"),
    "couldnt-check": (_COULDNT, "rung.approved.unreadable"),
}


def approved_rung(manifest: dict, check: CheckRows | None, own_check: bool,
                  checker: str | None) -> Rung:
    """The rung "Ran as approved": `ran_as_approved` over the page's own check, as a
    rung. A row's detail is the check's own words, quoted (escaped by the page like every
    quotation)."""
    said = ran_as_approved(manifest, check, own_check=own_check, verifier=checker)
    state, key = _APPROVAL_RUNG[said.state]
    if said.state in ("departed", "edges-mismatch"):
        return _rung("approved", state, line(key, detail=(said.detail, "report")))
    if said.state == "cant-check":
        return _rung("approved", state,
                     line(key, checker=(said.detail, "report")) if said.detail
                     else line("rung.approved.cant_check_unnamed"))
    return _rung("approved", state, line(key))


def ladder(record: Record, report: Report | None, strip: Strip, verbs: dict | None,
           problem: str | None, *, own_check: bool,
           checker: str | None = None) -> tuple[Rung, ...]:
    """The run's seven rungs, in board 2's order, with "Ran as approved" after "Nothing declared
    is missing". Signing is not yet available
    in this format, and release 1 has no authorization records: neither is
    ever a yes. `checker` names the check that ran, where the caller knows it."""
    agree = _records_agree(record, report, strip, problem, own_check)
    return (
        agree,
        signed_by_known_recorder(record, report, own_check),
        _nothing_missing(record),
        approved_rung(record.manifest, rows_from_report(report) if report else None,
                      own_check, checker),
        _reproduced(record, verbs, agree.state),
        _rung("authorized", ("no-records", "rung.state.no_records"),
              line("rung.authorized.no_records")),
        committed_by_time(record, report, own_check),
    )


#: Every part of a receipt this module reads, and the one shape it reads it in. A parent comes
#: before its children, so a child is looked for only in an object. Absent is not refused: the
#: pages word every absence already. Measured before this: the first eight crashed a page when
#: not objects, the two stage lists did when a number,
#: and `emission.gaps` not a list was read as no gaps -- "nothing is missing from the trail".
_SHAPES = (("anchor", "an object"), ("assertions", "an object"), ("coverage", "an object"),
           ("emission", "an object"), ("instrument", "an object"), ("outcome", "an object"),
           ("stage", "an object"), ("time", "an object"),
           ("inputs", "a list of objects"), ("outputs", "a list of objects"),
           ("coverage.declared_stages", "a list of strings"),
           ("coverage.emitting_stages", "a list of strings"),
           ("emission.gaps", "a list"),
           ("stage.name", "a string"))


def _fits(value, shape: str) -> bool:
    if shape == "an object":
        return isinstance(value, dict)
    if shape == "a string":
        return isinstance(value, str)
    if not isinstance(value, list):
        return False
    if shape == "a list of objects":
        return all(isinstance(x, dict) for x in value)
    if shape == "a list of strings":
        return all(isinstance(x, str) for x in value)
    return True


def _shown(value) -> str:
    text = repr(value)
    return text if len(text) <= 80 else text[:77] + "..."


def _case_ran(record: Record) -> str:
    first, last = record.steps[0].data, record.steps[-1].data
    return f"{first.get('time', {}).get('started', '')} → {last.get('time', {}).get('ended', '')}"


@dataclass(frozen=True, slots=True)
class ListRow:
    """What a list page shows of one run, and nothing more (full models are not
    rebuilt for lists). `viewer.page.render_executions` takes these or whole page models."""

    run_id: str
    case_ran: str
    case_for: str
    step_count: int
    case_for_more: int = 0
    record_href: str | None = None


def list_row(record: Record) -> ListRow:
    """A list's row for one run: refused, as the run's own pages are, for a part it cannot read."""
    refuse_unreadable_parts(record)
    case_for, more = _case_for(record.steps[0].data.get("coverage", {}).get("declared_stages", []))
    return ListRow(run_id=record.run_id, case_ran=_case_ran(record), case_for=case_for,
                   step_count=len(record.steps), case_for_more=more)


def refuse_unreadable_parts(record: Record) -> None:
    """Raise `RecordUnreadable` for the first receipt part not in the shape it is read in."""
    for step in record.steps:
        for where, shape in _SHAPES:
            head, _, tail = where.partition(".")
            if head not in step.data:
                continue
            value = step.data[head]
            if tail:
                if tail not in value:
                    continue
                value = value[tail]
            if not _fits(value, shape):
                raise RecordUnreadable(f"{step.file}: `{where}` is {_shown(value)}, not {shape}")


def build_model(record: Record, envelope: dict | None, generated_at: str,
                verbs: dict | None = None, *, own_check: bool,
                checker: str | None = None) -> PageModel:
    """Both views, decided. `envelope` is the check's report as captured, or None if absent.

    `own_check` is True only when `envelope` is the caller's own run of the check over this
    record. It has no default: a caller that has not said whose check
    it holds cannot get a yes from it.

    A record with a part in a shape this module cannot read is refused first, with
    `RecordUnreadable` (see `refuse_unreadable_parts`); nothing is read around it.
    """
    refuse_unreadable_parts(record)
    report: Report | None = None
    problem: str | None = None
    checked: tuple[CheckCount, ...] = ()
    not_checked: tuple[CheckCount, ...] = ()
    if envelope is not None:
        try:
            report = parse(envelope)
            if report.rows_readable:
                checked, not_checked = _checked_lists(record, report)
        except ReportUnreadable as e:
            report, problem = None, str(e)
    answer, question = _answer(record)
    first, last = record.steps[0].data, record.steps[-1].data
    case_for, case_for_more = _case_for(first.get("coverage", {}).get("declared_stages", []))
    env = envelope or {}
    changed, reproduced, boundary = _verb_states(verbs)
    strip = _strip(record, report, problem)
    return PageModel(
        run_id=record.run_id, is_preview=record.is_preview,
        strip=strip, answer=answer, question=question, answer_step=_answer_step(record),
        preview_format=str(record.manifest.get("format", "")),
        last_failed=last_attempt_failed(record),
        steps=tuple(_step_view(record, report, s) for s in record.steps),
        unchecked=_unchecked(record, report),
        case_ran=_case_ran(record), case_for=case_for, case_for_more=case_for_more,
        changed=changed, reproduced=reproduced, boundary_steps=boundary,
        checked=checked, not_checked=not_checked,
        # The command to repeat the check is carried only from a report that was read. An
        # unreadable report's fields are not trusted enough to tell a reader what to type.
        # An unreadable report's own words are still shown, unless they are what could not be
        # shown (a lone surrogate the page's UTF-8 cannot carry).
        report_output=report.output if report else (
            env.get("stdout") if isinstance(env.get("stdout"), str)
            and unshowable(env.get("stdout")) is None else None),
        report_is_fallback=report.source == SOURCE_TEXT if report else False,
        report_command=report.command if report else (),
        report_verifier=(report.command[1] if report and len(report.command) > 1
                         and report.command[0] != CLI_COMMAND else ""),
        report_cli=bool(report) and report.command[:1] == (CLI_COMMAND,),
        answer_anchor=answer_anchor(record, report, own_check),
        anchor_badge=anchor_badge(record, report, own_check),
        report_where=report.cwd_note if report else "",
        report_ran_at=report.ran_at if report else "",
        report_problem=problem,
        report_rows_readable=report.rows_readable if report else True,
        manifest_raw=record.manifest_raw.decode("utf-8"),
        generated_at=generated_at,
        ladder=ladder(record, report, strip, verbs, problem, own_check=own_check,
                      checker=checker),
        graph_nodes=_graph_nodes(record, boundary),
        **_graph_edges(record))


def _graph_nodes(record: Record, boundary_steps: tuple[str, ...]) -> tuple:
    """One graph node per step: its node id as the SDK forms it (the stage name, or
    `name#instance`), its emission index, a link to its row, dashed when it is a boundary, and
    marked failed when its outcome class is `error` (a retry's failed attempt stays visible)."""
    from onetrace_console.viewer.graph import GraphNode
    nodes = []
    for position, s in enumerate(record.steps):
        stage = s.data.get("stage") if isinstance(s.data.get("stage"), dict) else {}
        name = stage.get("name") if isinstance(stage.get("name"), str) else s.manifest_stage
        instance = stage.get("instance")
        node_id = f"{name}#{instance}" if isinstance(instance, str) and instance else name
        index = int(s.manifest_index) if s.manifest_index.isdigit() else position
        outcome = s.data.get("outcome") if isinstance(s.data.get("outcome"), dict) else {}
        coverage = s.data.get("coverage") if isinstance(s.data.get("coverage"), dict) else {}
        nodes.append(GraphNode(
            node_id=node_id, name=name, index=index,
            #: In-page links are `#step-N` only (core, 2 October): a step whose manifest index
            #: is not a number gets no link rather than a link of another shape.
            href=f"#step-{s.manifest_index}" if s.manifest_index.isdigit() else "",
            label=name_shown(node_id), shown=name_shown(name),
            #: The timeline's own rule for a boundary row (`_step_view` and the case page).
            dashed=bool(coverage.get("boundaries")) or s.manifest_index in boundary_steps,
            failed=outcome.get("class") == "error"))
    return tuple(nodes)


def _graph_edges(record: Record) -> dict:
    """The manifest's `edges`, as recorded: absent is None (a line), a list of links is that
    list, and anything else is unreadable -- never quietly read as either of the other two."""
    if "edges" not in record.manifest:
        return {"graph_edges": None}
    raw = record.manifest["edges"]
    if isinstance(raw, list) and all(
            isinstance(e, dict) and isinstance(e.get("from"), str)
            and isinstance(e.get("to"), str) for e in raw):
        return {"graph_edges": tuple({"from": e["from"], "to": e["to"]} for e in raw)}
    return {"graph_edges": None, "graph_unreadable": True}
