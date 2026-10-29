"""The onedoor panel: a gated step's recorded decisions, its permit and its action's digest, and
onetrace-verify's own rows about them.

onetrace 0.5 lets a step record which onedoor decision allowed it: the run's manifest names its
`gated_stages`, and a step's receipt may hold an `authorization` block, a list of `decisions` in call
order, each its `ref` (an `onedoor-decision-ref/1` object), and where one was used, the bound
`permit` (a compact JWS) and the `action_digest`. The panel shows exactly that, in the record's words:
the permit by what its payload states (its issuer, subject, what it allows, its validity window),
never its signature's bytes, and a field the payload does not hold as "not stated in the permit".
A gated step with no `authorization` block says "no decision recorded". A run with no gated step and
no decision shows nothing new.

What is checked is the verifier's: its five `decisions:` rows, PASS, FAIL or NOT-RUN with the row's
own reason, read from the run's stored check (`--json`). Nothing here checks a signature or a
digest, and nothing is inferred from a missing block.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timezone

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

HEADING = "Gated steps"
GATED = "Gated step"
CITES = "Cites a decision"
NONE_RECORDED = "no decision recorded"
NOT_STATED = "not stated in the permit"
NOT_RECORDED = "not recorded"
ROWS_HEADING = "The decisions, as checked"
ROWS_LEAD = "onetrace-verify's own rows about the decisions this run records:"
ROWS_NONE = "This run's check holds no decision rows."
SHOWN = "Shown as the record holds them. What is checked is onetrace-verify's, in its rows below."
#: The verifier's own row names, in its order (onetrace-verify 0.5.0).
ROW_PREFIX = "decisions: "


def gated_stages(manifest: dict) -> list[str]:
    stages = manifest.get("gated_stages") if isinstance(manifest, dict) else None
    return [s for s in stages if isinstance(s, str)] if isinstance(stages, list) else []


def decisions(receipt: dict) -> list[dict] | None:
    """The receipt's recorded decisions, in call order; None where it has no `authorization` block."""
    block = receipt.get("authorization") if isinstance(receipt, dict) else None
    if not isinstance(block, dict):
        return None
    got = block.get("decisions")
    return [d for d in got if isinstance(d, dict)] if isinstance(got, list) else []


def _b64url(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def permit_payload(jws: str) -> tuple[dict | None, str]:
    """(the permit's header and payload as JSON objects, or None; the reason it could not be read)."""
    if not isinstance(jws, str):
        return None, "the permit is not a string"
    parts = jws.split(".")
    if len(parts) != 3:
        return None, "the permit is not a compact JWS (three parts)"
    try:
        header = load_json_bounded(_b64url(parts[0]).decode("utf-8"), "the permit's header", "show")
        payload = load_json_bounded(_b64url(parts[1]).decode("utf-8"), "the permit's payload", "show")
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        return None, f"the permit's header or payload cannot be read ({type(e).__name__})"
    if not (isinstance(header, dict) and isinstance(payload, dict)):
        return None, "the permit's header or payload is not an object"
    return {"header": header, "payload": payload}, ""


def _when(value) -> str:
    """A permit's time (seconds since the epoch, as JWT writes it), as HTML: the time every page
    shows, then the number as the payload states it. Anything else is shown as written."""
    from onetrace_console.words import time_html
    if isinstance(value, bool) or not isinstance(value, int):
        return escape(str(value))
    try:
        iso = datetime.fromtimestamp(value, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return escape(str(value))
    return f"{time_html(iso)} ({value})"


def _field(label: str, value, absent: str = NOT_STATED) -> str:
    from onetrace_console.trace_panel import code_or_fold
    if value is None:
        return f'<li><span class="k">{escape(label)}</span> <span class="mono absent">{escape(absent)}</span></li>'
    return f'<li><span class="k">{escape(label)}</span> {code_or_fold(str(value))}</li>'


def _permit(jws) -> str:
    read, why = permit_payload(jws)
    if read is None:
        return f'<p data-onedoor="permit-unreadable">Permit: {escape(why)}.</p>'
    p, h = read["payload"], read["header"]
    window = (f"from {_when(p['nbf'])}" if "nbf" in p else "from: " + escape(NOT_STATED)) + "; " + (
        f"until {_when(p['exp'])}" if "exp" in p else "until: " + escape(NOT_STATED))
    allows = p.get("action_digest", p.get("act"))
    return ('<div data-onedoor="permit"><p>Permit, as its payload states it'
            f' (signed with {escape(str(h.get("alg", "an algorithm not stated")))}; its signature is not shown here):</p>'
            '<ul class="plain">'
            + _field("issuer", p.get("iss")) + _field("subject", p.get("sub"))
            + _field("allows the action with digest", allows)
            + f'<li><span class="k">validity</span> <span class="mono">{window}</span></li>'
            + "</ul></div>")


def _decision(n: int, d: dict) -> str:
    ref = d.get("ref") if isinstance(d.get("ref"), dict) else {}
    parts = [f'<li data-onedoor="decision"><p>Decision {n}: verdict <code>{escape(str(ref.get("verdict", "")))}</code>,'
             f' request <code>{escape(str(ref.get("request_id", "")))}</code></p><ul class="plain">'
             + _field("format", ref.get("format"), NOT_RECORDED)
             + _field("issuer", ref.get("issuer"), NOT_RECORDED)
             + _field("decision digest", ref.get("decision_digest"), NOT_RECORDED)
             + "</ul>"]
    if "permit" in d:
        parts.append(_permit(d["permit"]))
    else:
        parts.append('<p data-onedoor="no-permit">No permit recorded with this decision.</p>')
    if "action_digest" in d:
        from onetrace_console.trace_panel import code_or_fold
        parts.append(f'<div data-onedoor="action">The action, by its digest: {code_or_fold(str(d["action_digest"]))}</div>')
    else:
        parts.append('<p data-onedoor="no-action">No action digest recorded with this decision.</p>')
    return "".join(parts) + "</li>"


def step_block(stage: str, receipt: dict, gated: bool) -> str:
    """One step's panel: "Gated step" (or "Cites a decision"), then each decision; "no decision
    recorded" for a gated step with no block; empty for a step neither gated nor citing one."""
    got = decisions(receipt)
    if not gated and not got:
        return ""
    title = GATED if gated else CITES
    head = f'<h3>{escape(title)} <code>{escape(stage)}</code></h3>'
    if got is None or not got:
        return (f'<div class="onedoor-step" data-onedoor-step="{escape(stage)}">{head}'
                f'<p data-onedoor="none">{escape(NONE_RECORDED)}</p></div>')
    items = "".join(_decision(n, d) for n, d in enumerate(got, start=1))
    return (f'<div class="onedoor-step" data-onedoor-step="{escape(stage)}">{head}'
            f'<ol class="plain">{items}</ol></div>')


def decision_rows(envelope: dict | None) -> list[dict]:
    """The verifier's `decisions:` rows from the stored check's `--json`, in its order."""
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
    except (ValueError, RecursionError):
        return []
    rows = doc.get("rows") if isinstance(doc, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and str(r.get("name", "")).startswith(ROW_PREFIX)]


_TONE = {"PASS": "ok", "FAIL": "bad", "NOT-RUN": "cc"}


def rows_block(rows: list[dict]) -> str:
    if not rows:
        return f'<p data-onedoor="rows-none">{escape(ROWS_NONE)}</p>'
    items = "".join(
        f'<li data-onedoor-row="{escape(str(r.get("result", "")))}"><span class="pill {_TONE.get(r.get("result"), "neu")}">'
        f'{escape(str(r.get("result", "")))}</span> {escape(str(r.get("name", "")))}'
        f' <span class="reason">— {escape(str(r.get("detail", "")))}</span></li>' for r in rows)
    return f'<p>{escape(ROWS_LEAD)}</p><ul class="plain" data-onedoor="rows">{items}</ul>'


def run_section(manifest: dict, steps: list[dict]) -> str:
    """The run page's section of the decisions as recorded; empty for a run with no gated step and
    no decision. The verifier's rows go in a section of their own (`run_panels`)."""
    gated = gated_stages(manifest)
    blocks = []
    for s in steps:
        r = s.get("receipt") or {}
        name = (r.get("stage") or {}).get("name", "") if isinstance(r.get("stage"), dict) else ""
        blocks.append(step_block(name, r, name in gated))
    blocks = [b for b in blocks if b]
    if not blocks:
        return ""
    return (f'<section id="gated-steps" data-section="onedoor" class="onedoor"><h2>{escape(HEADING)}</h2>'
            f'<p class="shown">{escape(SHOWN)}</p>{"".join(blocks)}</section>')


def differs(receipt_a: dict | None, receipt_b: dict | None) -> str:
    """For a comparison: "decision" or "permit" where the two runs' recorded decisions or permits at
    a step differ, by their recorded bytes; "" where they are the same or neither run recorded any."""
    da, db = (decisions(r or {}) or [] for r in (receipt_a, receipt_b))
    if [d.get("ref") for d in da] != [d.get("ref") for d in db]:
        return "decision"
    if [(d.get("permit"), d.get("action_digest")) for d in da] != [(d.get("permit"), d.get("action_digest")) for d in db]:
        return "permit"
    return ""
