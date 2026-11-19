"""The recipient's confirmation (format 0.5's section J; onetrace 0.8's `docs/format.md`, "The recipient's
confirmation") on a run's Authorization page, in the room an earlier release left for it (`data-section=
"confirmations"`).

What is drawn: onetrace-verify's five rows (`confirmation: request`, `permit`, `recipient key`, `single use`,
`outcome`), quoted as it wrote them, NOT-RUN included; and, for each step that presented a permit and kept what the
recipient returned, the confirmation as the recipient's word: its digest, the permit it answers (issuer, id,
audience) and where the token is kept beside the record. Never as proof the recipient acted: the section says so in
`docs/format.md`'s words. Where any of the five rows FAILs, no step's confirmation is drawn: the rows stand alone. A run
whose check gives no such row, and whose record holds no confirmation, gets no section.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from onetrace_console.step_kinds import _line, prose
from onetrace_console.words import escape

HEADING = "The recipient's confirmation"
LEAD = (
    "Each step that presented a permit and kept what the recipient returned: the recipient's word, signed, as the "
    "record keeps it. It is not proof the recipient acted."
)
ROWS_LEAD = "onetrace-verify's rows on them"
WITHHELD = "A row below FAILs, so no step's confirmation is drawn."
ROW_PREFIX = "confirmation: "
#: onetrace 0.8's `docs/format.md`, "The recipient's confirmation", "What it does not show", in its words.
NON_CLAIMS = (
    "A confirmation shows the recipient said it acted, not that the effect happened in the world: that is the "
    "recipient's word, signed. A `refused` confirmation is likewise the recipient's word that it did not act. A trusted "
    "key means the key is on the list you gave: onetrace does not decide whom to trust. The rows other than the Key row "
    "compare what a confirmation says whether or not its signature verified: a Request or Permit PASS beside a Key "
    "FAIL or NOT-RUN is a match with an unauthenticated statement. The request digests are the ones the step wrote when "
    "it sent the request: a match shows the recipient confirmed what the step says it sent, not what went on the wire, "
    "and the presenter's own request signature is not checked (no body or key is kept). In a refusal at step 2, the "
    "permit's issuer and id are what the recipient read, not what it authenticated. Single use is checked across the "
    "records you give one verifier run, not across every record that exists; a byte-identical repeat is counted once, "
    "so a second effect behind a reused token cannot be seen. A confirmation's `iat` is the recipient's own clock; "
    "`mandate_verdict` is recorded, not checked; unknown members are named, not checked. The rows make no network "
    "calls and ask no recipient anything."
)
_TONE = {"PASS": "ok", "FAIL": "bad", "NOT-RUN": "cc"}


def _rec(text: str) -> str:
    return f'<span class="mono" data-words="record">{escape(text)}</span>'


def confirmed(steps: list[dict]) -> list[dict]:
    """Each step whose receipt keeps a confirmation: its name, file and `authorization` member."""
    out = []
    for s in steps:
        receipt = s.get("receipt") if isinstance(s, dict) else None
        if not isinstance(receipt, dict):
            continue
        auth = receipt.get("authorization")
        if isinstance(auth, dict) and isinstance(auth.get("confirmation_digest"), str):
            stage: dict = given if isinstance(given := receipt.get("stage"), dict) else {}
            out.append({"name": str(stage.get("name", "")), "file": str(s.get("file", "")), "authorization": auth})
    return out


def _step(c: dict) -> str:
    auth = c["authorization"]
    stem = PurePosixPath(c["file"]).stem
    permit = " · ".join(
        f"{label} {_rec(str(auth[k]))}"
        for label, k in (("issuer", "permit_iss"), ("id", "permit_jti"), ("audience", "permit_aud"))
        if isinstance(auth.get(k), str)
    )
    status = auth.get("permit_status")
    return (
        f'<li data-confirmation="{escape(c["name"], quote=True)}">Step {_rec(c["name"])}: the recipient returned '
        f"{_rec(auth['confirmation_digest'])}, kept at {_rec(f'authorization/{stem}/confirmation.jwt')}"
        + (f"<br>Permit presented: {permit}" if permit else "")
        + (f"<br>Permit: {_rec(status)}" if isinstance(status, str) else "")
        + "</li>"
    )


def section(steps: list[dict], rows: list[dict]) -> str:
    """The Authorization page's confirmations; "" where the check has no confirmation row and the record keeps no
    confirmation."""
    own = [r for r in rows if str(r.get("name", "")).startswith(ROW_PREFIX)]
    kept = confirmed(steps)
    if not own and not kept:
        return ""
    fails = any(r.get("result") == "FAIL" for r in own)
    if fails:
        body = f'<p data-confirmations="withheld">{escape(WITHHELD)}</p>'
    elif kept:
        body = f'<p>{escape(LEAD)}</p><ul class="plain">{"".join(_step(c) for c in kept)}</ul>'
    else:
        body = ""
    items = "".join(
        f'<li data-confirmation-row="{escape(str(r.get("result", "")), quote=True)}">'
        f'<span class="pill {_TONE.get(str(r.get("result", "")), "neu")}">{escape(str(r.get("result", "")))}</span> '
        f'<span class="mono" data-words="check">{escape(_line(r))}</span></li>'
        for r in own
    )
    if items:
        body += f'<h3>{escape(ROWS_LEAD)}</h3><ul class="plain" data-confirmation-rows>{items}</ul>'
    return (
        f'<section data-section="confirmations"><h2>{escape(HEADING)}</h2>{body}'
        f'<p class="note" data-section="confirmations-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )
