"""A step's effect label: whether its receipt records it as reading or writing, or that its effect is unknown, and on
what basis (format 0.4's `effect_label`, onetrace 0.8's `docs/format.md`: `value` `read`, `write` or `unknown`, and
`basis`, one of six).

Where it is drawn:
- each step's page gets a section, "Effect": the value and its basis, in the record's words;
- the Runs page's Steps column names each step by its label, where any step of the run has one (`step_marks.cell`).

The rules are `step_kinds`': the record's words alone; a label the verifier FAILs is not drawn from and its row is
shown. A step with no label gets nothing, never "read": a label absent means the step was not marked, not that it
read. A re-run stopped before a step labelled `write` or `unknown` already says so in its own close: its ending,
`re-run stopped before <step>: effect <value> (<basis>)`, on its head and in the Runs page's Closed column.
"""

from __future__ import annotations

from onetrace_console.step_kinds import _fail_block, failed
from onetrace_console.words import escape

VALUES = ("read", "write", "unknown")
BASES = (
    "declared on the stage",
    "model call",
    "model call stored by the provider",
    "http method",
    "not classified",
    "substituted, not executed",
)
#: The verifier's rows on a receipt's label.
ROWS = ("effect_label", "effect_label against effects", "effect_label as the producer documents it")
HEADING = "Effect"
#: What a label is, and what it is not.
NON_CLAIM = (
    "The label is what the record says of this step's effect, and on what basis: a stage's own declaration, or the "
    "kind of call a hook saw. It is not an observation of what the step did. A re-run reads it before running the step."
)


def kept(receipt: dict, receipt_file: str, rows: list[dict]) -> dict | None:
    """The receipt's label, {"value", "basis"}, where it holds one of the format's and the verifier does not FAIL it;
    else None."""
    label = receipt.get("effect_label")
    if not isinstance(label, dict) or label.get("value") not in VALUES or label.get("basis") not in BASES:
        return None
    if failed(rows, receipt_file, ROWS):
        return None
    return {"value": label["value"], "basis": label["basis"]}


def step_section(receipt: dict, receipt_file: str, rows: list[dict]) -> str:
    """A step's page: its label and basis; the verifier's FAIL rows where it fails one; "" where it has none."""
    fails = failed(rows, receipt_file, ROWS)
    if fails and "effect_label" in receipt:
        return f'<section data-section="effect" class="effect"><h2>{HEADING}</h2>{_fail_block(fails)}</section>'
    label = kept(receipt, receipt_file, rows)
    if label is None:
        return ""
    return (
        f'<section data-section="effect" class="effect" data-effect="{escape(label["value"])}"><h2>{HEADING}</h2>'
        f'<p><span data-words="record">{escape(label["value"])}</span>: '
        f'<span data-words="record">{escape(label["basis"])}</span></p>'
        f'<p class="note">{escape(NON_CLAIM)}</p></section>'
    )


def words(steps: list[dict]) -> str:
    """The Steps column's words for the labels: each value with its steps, in recorded order ("read: a, c; write: b");
    "" where no step has one."""
    by: dict[str, list[str]] = {}
    for s in steps:
        e = s.get("effect")
        if isinstance(e, dict) and e.get("value") in VALUES:
            by.setdefault(e["value"], []).append(str(s.get("step")))
    return "; ".join(f"{v}: {', '.join(by[v])}" for v in VALUES if v in by)
