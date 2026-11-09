"""One line at the top of a comparison page: what kind of thing differs at the first difference.

Chosen from what the records hold at the step diff's report names as the first difference, in this
order, the first that holds:

1. **Inputs differ:** a recorded input of the step's own (`render.own_inputs`, as the short answer
   reads them) differs between the runs. A link to a run the step started (`run:<its id>`, an
   agent's sub-agent) is not one of them: the step diff descends into that run.
2. **A decision step:** the two runs' recorded decision refs at the step differ
   (`onedoor_panel.differs` says "decision"). The line names each side's verdicts from the refs, and
   the policy version only where both runs' decisions are found in a held decision export (by
   `request_id`, the row chosen by `decision_digest`, as the decisions-cited join chooses it).
3. **A model call, inputs equal:** a model-call record both runs hold at the step, compared by the
   installed onetrace's comparator (`model_call_compare.compared`). A `diverged` result is named by
   its first differing field, in the comparator's own groups (`IDENTITY`, `engine.settings.*`,
   `sampling.*`, then the output alone); a `could not compare` whose reason is the batch context is
   said in the comparator's words, as a could-not-compare. Any other result gives no line.
4. **A kept output absent:** the SDK's text diff names an output of the step as
   `not shown: <name> is missing`.

A step none of these covers gets no line. A tool call is not among them: the records name no step
kind and no tool call, so it waits for a source onetrace defines (console 0.7.0).

The line names what differs as the records give it; it never says what produced the difference.
"""
from __future__ import annotations

from onetrace_console.words import escape

INPUTS = "The first difference is upstream: this step's inputs already differed."
MODEL = "The model's output differed on equal inputs; the comparator's kind of change: {kind} (first differing field {field})."
BATCH = "At this step's model call, the comparator's result is: {result}."
DECISION = "The policy decision differed: {a} in the baseline, {b} in the candidate."
POLICY_SAME = "The policy version is the same in both: {v}."
POLICY_DIFFERS = "The policy version differed: {a} in the baseline, {b} in the candidate."
POLICY_NOT_RECORDED = "The policy version is not recorded."
NOT_KEPT = "This step's output was not kept, so only its digest is compared."
#: The comparator's groups, in its order.
IDENTITY, ENGINE, SAMPLING, OUTPUT = "model identity", "engine settings", "sampling settings", "the output alone"
#: The comparator's own words for a batch context that differs.
BATCH_WORDS = "could not compare: batch context differs"


def _code(s: str) -> str:
    return f"<code>{escape(s)}</code>"


def model_kind(first: str) -> str:
    """The comparator's group of its first differing field, from its own lists."""
    from onetrace.model_call.comparator import IDENTITY as FIELDS
    if first in FIELDS:
        return IDENTITY
    if first.startswith("engine.settings."):
        return ENGINE
    if first.startswith("sampling."):
        return SAMPLING
    return OUTPUT


def _first_stage(report) -> str | None:
    """The step diff's report names as its one first difference, or None."""
    rows = [r for r in getattr(report, "ladder", ()) if r.verdict == "FIRST DIFFERENCE"]
    if len(rows) != 1:
        return None
    return str(getattr(rows[0], "node", None) or rows[0].stage).split("#", 1)[0]


#: A step's link to a run it started (an agent's sub-agent), as the receipt names it: `run:<its run id>`.
SUB_RUN = "run:"


def _inputs_differ(stage: str, a: list[dict], b: list[dict]) -> bool:
    """Whether an input of the step's own differs: not a link to a run the step started, whose name and
    digest differ between any two runs (a difference inside that run is the step diff's, as it descends)."""
    from onetrace_console.render import own_inputs
    x, y = own_inputs(a).get(stage, {}), own_inputs(b).get(stage, {})
    return any(x.get(n) != y.get(n) for n in x.keys() | y.keys() if not n.startswith(SUB_RUN))


def _export_row(ref: dict, store):
    """The held export row a decision ref names (by `request_id`, then `decision_digest`), where every
    copy of it checks against its delivery; None otherwise."""
    from onetrace_console.onedoor_ext.decision_refs import _decisions_by_request_id
    d = _decisions_by_request_id(store).get(ref.get("request_id"))
    if d is None:
        return None
    row = next((r for r in d.rows if r.decision_digest == ref.get("decision_digest")), None)
    return row if row is not None and d.couldnt_check(row) is None else None


def _versions(refs: list[dict], store) -> list[str] | None:
    """Each ref's row's `policy_version`, or None where any ref's row is not held or holds none."""
    out = []
    for ref in refs:
        row = _export_row(ref, store)
        v = row.fields.get("policy_version") if row is not None else None
        if v is None or isinstance(v, (dict, list)):
            return None
        out.append(str(v))
    return out


def _decision_line(ra: dict | None, rb: dict | None, store) -> str:
    from onetrace_console.onedoor_panel import decisions, differs
    if differs(ra, rb) != "decision":
        return ""
    refs = [[d.get("ref") if isinstance(d.get("ref"), dict) else {} for d in decisions(r or {}) or []]
            for r in (ra, rb)]
    verdicts = [", ".join(_code(str(ref.get("verdict", ""))) for ref in side) or "no decision" for side in refs]
    line = DECISION.format(a=verdicts[0], b=verdicts[1])
    try:
        va, vb = (_versions(side, store) if side else None for side in refs)
    except Exception:  # noqa: BLE001 - exports that can't be read hold no version to name
        va = vb = None
    if va is None or vb is None:
        return line + " " + POLICY_NOT_RECORDED
    if va == vb:
        return line + " " + POLICY_SAME.format(v=", ".join(_code(v) for v in va))
    return line + " " + POLICY_DIFFERS.format(a=", ".join(_code(v) for v in va), b=", ".join(_code(v) for v in vb))


def _model_line(comparison, store, stage: str) -> str:
    from onetrace_console import model_call_compare
    for result in model_call_compare.compared(comparison, store, stage):
        if result.result == "diverged":
            return MODEL.format(kind=escape(model_kind(result.first)), field=_code(result.first))
        if result.result == "could not compare" and result.first.startswith("batch context differs"):
            return BATCH.format(result=escape(result.result_line()))
        if result.result != "same":
            return ""
    return ""


def _not_kept(comparison, store, stage: str) -> bool:
    from onetrace_console.compare import text_diff_raw
    from onetrace_console.textdiff_view import TextDiffUnreadable, read_textdiff
    found = text_diff_raw(comparison, store)
    if found is None:
        return False
    try:
        doc = read_textdiff(found[0])
    except TextDiffUnreadable:
        return False
    for node in doc.get("nodes", []):
        if str(node.get("node", "")).split("#", 1)[0] != stage or node.get("verdict") != "FIRST DIFFERENCE":
            continue
        return any(o["kind"] == "not shown" and str(o.get("reason", "")).startswith("not shown: ")
                   and str(o.get("reason", "")).endswith(" is missing") for o in node["outputs"])
    return False


def chosen(report, comparison, store) -> tuple[str, str] | None:
    """(the kind, the line as HTML), or None where no kind holds."""
    stage = _first_stage(report)
    if stage is None:
        return None
    return at_stage(stage, comparison, store)


def at_stage(stage: str, comparison, store) -> tuple[str, str] | None:
    """(the kind, the line as HTML) at `stage` of the comparison's two runs, in the same order, or None
    where no kind holds there: the first-run-to-leave page asks it at the step it names."""
    from onetrace_console.render import _receipts_in_order, _stage_of
    a, b = _receipts_in_order(comparison.run_a, store), _receipts_in_order(comparison.run_b, store)
    if not (a and b):
        return None
    if _inputs_differ(stage, a, b):
        return "inputs", escape(INPUTS)
    ra = next((r for r in a if _stage_of(r) == stage), None)
    rb = next((r for r in b if _stage_of(r) == stage), None)
    line = _decision_line(ra, rb, store)
    if line:
        return "decision", line
    line = _model_line(comparison, store, stage)
    if line:
        return ("model-call-batch" if line.startswith("At this step") else "model-call"), line
    if _not_kept(comparison, store, stage):
        return "output-not-kept", escape(NOT_KEPT)
    return None


def drawn(got: tuple[str, str] | None) -> str:
    """A chosen kind as its line, or "" with none."""
    if got is None:
        return ""
    kind, said = got
    return f'<p class="first-kind" data-section="first-kind" data-kind="{kind}">{said}</p>'


def line(report, comparison, store) -> str:
    """The line, first on the page, or "" where no kind holds."""
    return drawn(chosen(report, comparison, store))
