"""The information mark: a small "i" beside a count the console states, whose note says what was
counted, with the arithmetic that reaches the number shown.

The note is plain text, in the page: shown on hover or keyboard focus by the stylesheet alone (no
script), named for a screen reader by its `aria-label`, in both themes at the page's contrast. Every
number in it is read from the record that gave the count (the verifier's own `--json` rows, the
explanation's record, the comparison's report), never typed.
"""
from __future__ import annotations

import re
from collections import Counter

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

#: The mark's look, in the console's stylesheet (`frame.stylesheet`).
INFO_CSS = """
.info{position:relative;display:inline-block;margin-left:4px;vertical-align:baseline}
.info>.i{display:inline-block;min-width:1.3em;height:1.3em;line-height:1.3em;text-align:center;
  border-radius:50%;border:1px solid var(--line-strong);font-size:var(--fs-small);font-style:normal;
  font-weight:600;color:var(--ink);background:var(--surface);cursor:help}
.info:focus{outline:none}
.info:focus>.i{outline:2px solid var(--accent);outline-offset:2px}
.info>.tip{display:none;position:absolute;left:0;top:1.6em;z-index:5;width:min(32em,80vw);
  padding:8px 10px;border:1px solid var(--line-strong);border-radius:var(--r-ctl);background:var(--surface);
  color:var(--ink);font-size:var(--fs-small);font-weight:400;line-height:1.4;white-space:normal;text-align:left}
.info:hover>.tip,.info:focus>.tip,.info:focus-within>.tip{display:block}
"""


def mark(note: str) -> str:
    """The "i" and its note: reachable by keyboard, its note its accessible name."""
    return (f'<span class="info" tabindex="0" role="note" aria-label="{escape(note)}" data-info>'
            f'<span class="i" aria-hidden="true">i</span><span class="tip" aria-hidden="true">{escape(note)}</span></span>')


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def checks_note(rows: list[dict], shown: int) -> str:
    """For "N checks made — all hold": the verifier's rows that held, by what each is about (the
    receipt, the manifest, a run-wide check), adding up to N; the rows NOT-RUN and FAIL named apart.
    `rows`: the verifier's own `--json` rows."""
    held = [r for r in rows if r.get("result") == "PASS"]
    by = Counter(str(r.get("name", "")).split(": ", 1)[0] if ": " in str(r.get("name", "")) else str(r.get("name", ""))
                 for r in held)
    receipts = sorted((k, n) for k, n in by.items() if k.startswith("receipts/"))
    others = sorted((k, n) for k, n in by.items() if not k.startswith("receipts/"))
    parts = [f"{n} on {k}" for k, n in receipts] + [f"{n} on {k}" for k, n in others]
    total = sum(by.values())
    rest = Counter(r.get("result") for r in rows if r.get("result") != "PASS")
    not_counted = "; ".join(f"{n} {k}" for k, n in sorted(rest.items()))
    return (f"onetrace-verify's rows that held, by what each checks: {' + '.join(parts)} = {total}"
            + (f". Not counted: {not_counted}." if not_counted else ".")
            + ("" if total == shown else f" (The line shows {shown}.)"))


def rows_of(envelope: dict | None) -> list[dict]:
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
    except (ValueError, RecursionError):
        return []
    rows = doc.get("rows") if isinstance(doc, dict) else None
    return [r for r in rows or [] if isinstance(r, dict)]


def claims_note(kept: int, left: dict) -> str:
    """For "N claims checked against the record · M left out": the kept claims and each reason's count."""
    parts = [f"{kept} kept"] + [f"{n} {why}" for why, n in sorted(left.items())]
    total = kept + sum(int(n) for n in left.values())
    return f"Every claim the post-check read: {' + '.join(parts)} = {total}."


def stages_note(counts: Counter, total: int) -> str:
    """For a count of stages: each verdict's count, in the SDK's words, adding up to `total`."""
    parts = [f"{n} {v}" for v, n in counts.items() if n]
    return f"The comparison's rows, by the SDK's verdict: {' + '.join(parts)} = {total}."


def step_note(rows: list[dict], receipt_file: str, shown: int) -> str:
    """For a step's "N checks made": the verifier's rows about that step's receipt that held."""
    mine = [r for r in rows if str(r.get("name", "")).startswith(receipt_file + ": ")]
    held = sum(1 for r in mine if r.get("result") == "PASS")
    rest = Counter(r.get("result") for r in mine if r.get("result") != "PASS")
    not_counted = "; ".join(f"{n} {k}" for k, n in sorted(rest.items()))
    return (f"onetrace-verify's rows about {receipt_file} that held: {held}"
            + (f". Not counted: {not_counted}." if not_counted else ".")
            + ("" if held == shown else f" (The line shows {shown}.)"))


_RUNG = re.compile(r'(<tr data-rung="records-agree"[^>]*>.*?<span class="value" data-words="value">(\d+)</span>'
                   r' checks? made — (?:all hold|it holds)\.)', re.S)
_STEP = re.compile(r'(<li data-state="pass" data-count="(\d+)"><strong>step (\d+) of \d+ · [^<]*</strong>'
                   r' — <span class="value" data-words="value">\d+</span> checks? made — (?:all hold|it holds)\.)')


def splice(page: str, rows: list[dict], chain_files: list[str]) -> str:
    """The run page with a mark beside the run's "N checks made" and each step's: `rows`, the
    verifier's own `--json` rows; `chain_files`, the receipts in the chain's order (step n is the
    n-th)."""
    if not rows:
        return page
    page = _RUNG.sub(lambda m: m.group(1) + mark(checks_note(rows, int(m.group(2)))), page)

    def step(m):
        n = int(m.group(3))
        if not 1 <= n <= len(chain_files):
            return m.group(1)
        return m.group(1) + mark(step_note(rows, chain_files[n - 1], int(m.group(2))))
    return _STEP.sub(step, page)
