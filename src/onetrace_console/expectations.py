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
from onetrace_console.words import escape

HEADING = "Expectations"
#: The manual's own words (16.22, "What it shows").
NON_CLAIM = "An expectation that holds shows the declared rule held, not that the output was right."
LEAD = ("Each step's declared expectations, as onetrace-verify read them on this run: PASS, FAIL naming "
        "the value and the rule, or NOT-RUN with its reason.")
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


def declared(receipts: list[dict]) -> list[dict]:
    """Each expectation the receipts declare with the run, in the chain's order: its step, name, kind."""
    out = []
    for r in receipts:
        stage = r.get("stage") if isinstance(r.get("stage"), dict) else {}
        step = stage.get("name") if isinstance(stage.get("name"), str) else ""
        if stage.get("instance") not in (None, "", "1"):
            step = f"{step}#{stage['instance']}"
        for e in r.get("expectations") or [] if isinstance(r.get("expectations"), list) else []:
            if isinstance(e, dict) and e.get("declared") == WITH_THE_RUN:
                name = e.get("name") if isinstance(e.get("name"), str) and e.get("name") else \
                    f'{e.get("target", "")} {e.get("kind", "")}'
                out.append({"step": step, "name": name, "kind": str(e.get("kind", ""))})
    return out


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
    """The rows about expectations declared with the run: `expect ...`, not declared after it."""
    return [r for r in rows if str(r.get("name", "")).startswith(ROW_PREFIX) and AFTER not in str(r.get("name", ""))]


def with_rows(declared_: list[dict], rows: list[dict]) -> list[dict]:
    """A row for each declared expectation: the verifier's, by its name, or NOT-RUN where it gives none;
    and any row of the verifier's about an expectation not matched, as it wrote it."""
    by_name = {str(r.get("name", "")): r for r in rows}
    out, used = [], set()
    for d in declared_:
        name = f'{ROW_PREFIX}{d["step"]}.{d["name"]}'
        if name in by_name:
            out.append(by_name[name])
            used.add(name)
        else:
            out.append({"name": name, "result": "NOT-RUN", "detail": NO_ROW})
    out += [r for r in rows if str(r.get("name", "")) not in used]
    return out


_TONE = {"PASS": "ok", "FAIL": "bad", "NOT-RUN": "cc"}


def _row(r: dict) -> str:
    result = str(r.get("result", ""))
    return (f'<li data-expectation="{escape(result)}"><span class="pill {_TONE.get(result, "neu")}">{escape(result)}</span>'
            f' <span data-words="check">{escape(str(r.get("name", "")))}</span>'
            f' <span class="reason">— <span data-words="check">{escape(str(r.get("detail", "")))}</span></span></li>')


def count_line(rows: list[dict]) -> str:
    n, held = len(rows), sum(1 for r in rows if r.get("result") in HELD)
    return (COUNT_ONE if n == 1 else COUNT).format(held=held, n=n)


def run_section(receipts: list[dict], envelope: dict | None) -> str:
    """The run page's section of its steps' expectations; empty for a run that declares none and whose
    check holds no row about one."""
    rows = with_rows(declared(receipts), with_the_run(rows_of(envelope)))
    if not rows:
        return ""
    steps: dict[str, list[dict]] = {}
    for r in rows:
        step = str(r.get("name", ""))[len(ROW_PREFIX):].split(".", 1)[0]
        steps.setdefault(step, []).append(r)
    groups = "".join(f'<h3>{escape(STEP.format(step=step))}</h3><ul class="plain" data-expectations-step="{escape(step)}">'
                     f'{"".join(_row(r) for r in group)}</ul>' for step, group in steps.items())
    return (f'<section data-section="expectations" class="expectations"><h2>{escape(HEADING)}</h2>'
            f'<p data-expectations="count">{escape(count_line(rows))}</p>'
            f'<p class="reported">{escape(LEAD)}</p><p data-expectations="non-claim">{escape(NON_CLAIM)}</p>'
            f"{groups}</section>")
