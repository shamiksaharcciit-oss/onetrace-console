"""Step expectations (onetrace 0.7; onetrace's manual, 16.22): a rule a step declares about its own
output, read by onetrace-verify on every run with no other run to compare against.

A run's page shows each step's declared expectations, one row each, as the verifier wrote it: PASS;
FAIL, its detail naming the value and the rule; NOT-RUN, its detail the reason. An expectation a
receipt declares that the check gives no row for reads NOT-RUN, and says so. Beside the rows, the
manual's own words for what a held expectation shows; and how many held, on a line of its own, apart
from the comparison's verdicts. Nothing here reads an output or decides a row: the rows are the
verifier's, read from the run's stored check (`--json`).
"""

from __future__ import annotations

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.step_kinds import _line as _text_line
from onetrace_console.words import escape

HEADING = "Expectations"
#: The manual's own words (16.22, "What it shows").
NON_CLAIM = "An expectation that holds shows the declared rule held, not that the output was right."
LEAD = (
    "Each step's declared expectations, as onetrace-verify read them on this run: PASS, FAIL naming "
    "the value and the rule, or NOT-RUN with its reason."
)
COUNT = "{held} of {n} expectations held."
COUNT_ONE = "{held} of 1 expectation held."
NO_ROW = "the check holds no row for it"
STEP = "Step {step}"
#: The verifier's own row names (onetrace-verify 0.7.1): `expect <step>.<name>`; an expectation
#: declared after the run carries `(declared after the run, <seal>)` after its name.
ROW_PREFIX = "expect "
AFTER = "(declared after the run"
WITH_THE_RUN = "with the run"
#: The results a count takes as held.
HELD = ("PASS",)
#: Format 0.5's expectations checked during the run (onetrace 0.8's `docs/format.md`, "Expectations checked during the
#: run"): each `checked` beside the verifier's row, and a batch's count. The verifier's row is the one that counts.
CHECKED = "Checked during the run"
DIFFERS = "differs from onetrace-verify's row, which is the one that counts"
BATCH = "failed {failed} of {of}"
BATCH_SUFFIX = " batch"
STOP_ROW = "the run's stop"
#: `docs/format.md`'s "What it does not show", for expectations checked during the run.
CHECKED_NON_CLAIMS = (
    "A run that was not stopped shows that no `stop` expectation failed at a step's return, not that the outputs "
    "were right. A stop guards the steps after it, never the step that failed. It is not a policy check before an "
    "action. `checked` says what the reading gave over the bytes recorded at that moment, under `reader`'s version. "
    "Code the app runs after catching `ExpectationStopped`, or outside any stage, is not stopped. On a run that keeps "
    "no outputs, the result written during the run cannot be re-read: it is the SDK's word, under the run's "
    "signature. A batch's count is written, not which documents failed."
)


def declared(receipts: list[dict]) -> list[dict]:
    """Each expectation the receipts declare with the run, in the chain's order: its step, name, kind."""
    out = []
    for r in receipts:
        stage = _stage if isinstance(_stage := r.get("stage"), dict) else {}
        step = _name if isinstance(_name := stage.get("name"), str) else ""
        if stage.get("instance") not in (None, "", "1"):
            step = f"{step}#{stage['instance']}"
        for member, batch in (("expectations", False), ("expectations_batch", True)):
            for e in r.get(member) or [] if isinstance(r.get(member), list) else []:
                if isinstance(e, dict) and e.get("declared") == WITH_THE_RUN:
                    name = (
                        e.get("name")
                        if isinstance(e.get("name"), str) and e.get("name")
                        else f"{e.get('target', '')} {e.get('kind', '')}"
                    )
                    checked = e.get("checked") if isinstance(e.get("checked"), dict) else None
                    out.append(
                        {"step": step, "name": name, "kind": str(e.get("kind", "")), "batch": batch, "checked": checked}
                    )
    return out


def row_name(d: dict) -> str:
    """The verifier's row name for a declared expectation: `expect <step>.<name>`, or `<step>.<name> batch`."""
    return f"{d['step']}.{d['name']}{BATCH_SUFFIX}" if d.get("batch") else f"{ROW_PREFIX}{d['step']}.{d['name']}"


def rows_of(envelope: dict | None) -> list[dict]:
    """The verifier's rows from the stored check's `--json`, in its order."""
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
    except (ValueError, RecursionError):
        return []
    rows = doc.get("rows") if isinstance(doc, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def with_the_run(rows: list[dict]) -> list[dict]:
    """The rows about expectations declared with the run: `expect ...` and `... batch`, not declared after it."""
    return [
        r
        for r in rows
        if (str(r.get("name", "")).startswith(ROW_PREFIX) or str(r.get("name", "")).endswith(BATCH_SUFFIX))
        and AFTER not in str(r.get("name", ""))
    ]


def with_rows(declared_: list[dict], rows: list[dict]) -> list[dict]:
    """A row for each declared expectation: the verifier's, by its name, or NOT-RUN where it gives none;
    and any row of the verifier's about an expectation not matched, as it wrote it."""
    by_name = {str(r.get("name", "")): r for r in rows}
    out, used = [], set()
    for d in declared_:
        name = row_name(d)
        row = dict(by_name[name]) if name in by_name else {"name": name, "result": "NOT-RUN", "detail": NO_ROW}
        used.add(name)
        if d.get("checked") is not None:
            row["checked"] = d["checked"]
        out.append(row)
    out += [r for r in rows if str(r.get("name", "")) not in used]
    return out


_TONE = {"PASS": "ok", "FAIL": "bad", "NOT-RUN": "cc"}


def _checked(r: dict) -> str:
    """What the record says was checked during the run, beside the verifier's row; where the two differ, both stand,
    and the page says the verifier's counts."""
    c = r.get("checked")
    if not isinstance(c, dict):
        return ""
    outcome = str(c.get("outcome", ""))
    said = " · ".join(
        x
        for x in (
            outcome,
            str(c.get("mode", "")),
            f"read by {c['reader']}" if isinstance(c.get("reader"), str) else "",
            BATCH.format(failed=c["failed"], of=c["of"])
            if isinstance(c.get("failed"), str) and isinstance(c.get("of"), str)
            else "",
        )
        if x
    )
    differs = outcome != str(r.get("result", ""))
    return (
        f'<div data-checked="{escape(outcome, quote=True)}"><span>{escape(CHECKED)}:</span> '
        f'<span data-words="record">{escape(said)}</span>'
        f' <span class="reason">— <span data-words="record">{escape(str(c.get("detail", "")))}</span></span>'
        + (f" <strong data-checked-differs>({escape(DIFFERS)})</strong>" if differs else "")
        + "</div>"
    )


def _row(r: dict) -> str:
    result = str(r.get("result", ""))
    return (
        f'<li data-expectation="{escape(result)}"><span class="pill {_TONE.get(result, "neu")}">{escape(result)}</span>'
        f' <span data-words="check">{escape(str(r.get("name", "")))}</span>'
        f' <span class="reason">— <span data-words="check">{escape(str(r.get("detail", "")))}</span></span>'
        f"{_checked(r)}</li>"
    )


def count_line(rows: list[dict]) -> str:
    n, held = len(rows), sum(1 for r in rows if r.get("result") in HELD)
    return (COUNT_ONE if n == 1 else COUNT).format(held=held, n=n)


def run_section(receipts: list[dict], envelope: dict | None) -> str:
    """The run page's section of its steps' expectations; empty for a run that declares none and whose
    check holds no row about one."""
    every = rows_of(envelope)
    rows = with_rows(declared(receipts), with_the_run(every))
    if not rows:
        return ""
    steps: dict[str, list[dict]] = {}
    for r in rows:
        name = str(r.get("name", ""))
        step = (name[len(ROW_PREFIX) :] if name.startswith(ROW_PREFIX) else name).split(".", 1)[0]
        steps.setdefault(step, []).append(r)
    from onetrace_console.step_kinds import prose

    checked = any("checked" in r for r in rows)
    stop = "".join(
        f'<p data-expectations="stop"><span data-words="check">{escape(_text_line(r))}</span></p>'
        for r in every
        if r.get("name") == STOP_ROW
    )
    from onetrace_console.verifier_notes import block, of_envelope

    extra = (
        stop
        + block(of_envelope(envelope), "expect")
        + (f'<p class="note" data-expectations="checked-non-claims">{prose(CHECKED_NON_CLAIMS)}</p>' if checked else "")
    )
    groups = "".join(
        f'<h3>{escape(STEP.format(step=step))}</h3><ul class="plain" data-expectations-step="{escape(step)}">'
        f"{''.join(_row(r) for r in group)}</ul>"
        for step, group in steps.items()
    )
    return (
        f'<section data-section="expectations" class="expectations"><h2>{escape(HEADING)}</h2>'
        f'<p data-expectations="count">{escape(count_line(rows))}</p>'
        f'<p class="reported">{escape(LEAD)}</p><p data-expectations="non-claim">{escape(NON_CLAIM)}</p>'
        f"{groups}{extra}</section>"
    )
