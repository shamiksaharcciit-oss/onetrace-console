"""A run's authorization page, in release 1's "no records" state (v6 board 3).

    Release 1 is onetrace, the console and onetrace-ci. The authorization board ships in its
    "no records" state.
    It is never counted as a pass. It is never blank.

Rendered here, in the viewer's shell like the Diff page, because the viewer has no
authorization page. It sits beside the run's two viewer pages, and the case page's Policy
section links to it (`authorization_link`).

WHAT IT DOES NOT SAY
--------------------
Board 3 also says "Nothing in the record shows a policy decision, a permit or a confirmation
from the receiving system", "this pipeline does not yet send its actions through a policy
engine", and names its drawing's own stages ("proposed an action (stage 5)"). The first is a
claim about a run's receipts, which this console does not search for such things; the
second is about a system it cannot see (the records may simply not have reached it); the
third is the illustration's. None is made. The case page's Policy sentence made the same
over-claim, and no longer does. What the page can say is what
release 1 has: no authorization records for this run, and that this is not a fault.

Board 3's AADP sentence ("When a policy engine that speaks AADP is added, this page shows the
whole chain for each action...") is left out too: it presupposes
that no engine has been added -- the same claim about an unseen pipeline -- and promises a page
nothing here backs yet.

Board 3's "How to add authorization records" button is not rendered either: there is no page
or document for it to open yet, and a link to nothing is worse than none.

The words are v6 board 3's.
"""

from __future__ import annotations

import re

from onetrace_console.store import StoredRun
from onetrace_console.words import escape, generated_footer, named, record_href, scroll_region, shown_name

AUTHORIZATION = "authorization.html"

TITLE = "Authorization"
STATE = "No records"
HEADING = "No authorization records for this run"
NOT_A_FAULT = "That is not a failure of the record."
NOTE = 'Nothing here is counted as a pass. "No records" is shown wherever authorization would appear.'
BACK = "Back to the run"

#: Where the run declares a gated step or cites a decision (console 0.8.0): one row a step.
GATED_STATE = "From the record"
GATED_HEADING = "Gated steps"
COLUMNS = ("Step", "Decision reference", "Decision, as recorded", "Permit", "The step's outcome, as recorded")
THEN = ", then "
NO_PERMIT = "no permit recorded"
PERMIT_FROM = "recorded, issued by"
PERMIT_UNREAD = "recorded; its payload cannot be read"
NO_OUTCOME = "not recorded"
VERIFIER_ON_STEP = "onetrace-verify on this step:"
NON_CLAIMS = (
    "This page shows what the record holds and what onetrace-verify reads in it. It does not say "
    "whether a decision was right, or whether the action should have been taken."
)
#: The verifier's row that reads whether a step that acted cited a permitting decision.
PERMITTING_ROW = "decisions: a step that acted cites a permitting decision"

#: The link's own marker. NOT a name the viewer's page carries, because a guard keyed on
#: someone else's section silently decides the work is already done.
LINK_MARKER = "authorization-link"


def gated_rows(manifest: dict, steps: list[dict]) -> list[dict]:
    """One entry per step the run gates or that cites a decision, in the record's order: its name,
    whether it is gated, its decisions as recorded (None: no `authorization` block), and its outcome's
    class as recorded."""
    from onetrace_console import onedoor_panel

    gated = onedoor_panel.gated_stages(manifest)
    out = []
    for s in steps:
        r = s.get("receipt") or {}
        name = (r.get("stage") or {}).get("name", "") if isinstance(r.get("stage"), dict) else ""
        got = onedoor_panel.decisions(r)
        if name in gated or got:
            oc = _outcome if isinstance(_outcome := r.get("outcome"), dict) else {}
            out.append(
                {
                    "step": name,
                    "gated": name in gated,
                    "decisions": got,
                    "outcome": _class if isinstance(_class := oc.get("class"), str) else None,
                }
            )
    return out


def _permit_cell(decisions: list[dict]) -> str:
    from onetrace_console import onedoor_panel

    permits = [d["permit"] for d in decisions if "permit" in d]
    if not permits:
        return f'<span class="absent">{escape(NO_PERMIT)}</span>'
    said = []
    for jws in permits:
        read, _why = onedoor_panel.permit_payload(jws)
        issuer = (read or {}).get("payload", {}).get("iss") if read else None
        said.append(
            f'{escape(PERMIT_FROM)} <span class="mono" data-words="record">{escape(str(issuer))}</span>'
            if issuer is not None
            else escape(PERMIT_UNREAD)
        )
    return "; ".join(said)


def _row(entry: dict, rows: list[dict]) -> str:
    from onetrace_console.onedoor_panel import NONE_RECORDED
    from onetrace_console.trace_panel import code_or_fold

    got = entry["decisions"] or []
    verdicts = [str((d.get("ref") or {}).get("verdict", "")) if isinstance(d.get("ref"), dict) else "" for d in got]
    refs = "".join(
        f'<li><span class="mono" data-words="record">{escape(str((d.get("ref") or {}).get("request_id", "")))}'
        f"</span> {code_or_fold(str((d.get('ref') or {}).get('decision_digest', '')))}</li>"
        for d in got
        if isinstance(d.get("ref"), dict)
    )
    refs = f'<ul class="plain">{refs}</ul>' if refs else f'<span class="absent">{escape(NONE_RECORDED)}</span>'
    decision = (
        escape(THEN).join(f'<code data-words="record">{escape(v)}</code>' for v in verdicts)
        if verdicts
        else f'<span class="absent">{escape(NONE_RECORDED)}</span>'
    )
    outcome = (
        f'<code data-words="record">{escape(entry["outcome"])}</code>'
        if entry["outcome"]
        else f'<span class="absent">{escape(NO_OUTCOME)}</span>'
    )
    #: The verifier's own words where its row names this step as one that acted on a decision that
    #: did not permit it: "proposal to effect", as the verifier reads it, never this page's inference.
    said = [
        str(r.get("detail", ""))
        for r in rows
        if r.get("name") == PERMITTING_ROW
        and r.get("result") == "FAIL"
        and str(r.get("detail", "")).startswith(f"{entry['step']}:")
    ]
    if said:
        outcome += (
            f'<p data-authorization="verifier">{escape(VERIFIER_ON_STEP)} '
            f'<span data-words="check">{escape(said[0])}</span></p>'
        )
    return (
        f'<tr data-step="{escape(entry["step"], quote=True)}" data-verdicts="{escape(" ".join(verdicts), quote=True)}"'
        f' data-outcome="{escape(entry["outcome"] or "", quote=True)}">'
        + "".join(
            f"<td>{v}</td>"
            for v in (
                f'<code data-words="record">{escape(entry["step"])}</code>',
                refs,
                decision,
                _permit_cell(got),
                outcome,
            )
        )
        + "</tr>"
    )


def gated_section(entries: list[dict], rows: list[dict], case: str) -> str:
    """The page's own section where the run gates a step or cites a decision: the table, what the page
    does not claim, and the verifier's `decisions:` rows."""
    from onetrace_console import onedoor_panel

    head = "".join(f'<th scope="col">{escape(c)}</th>' for c in COLUMNS)
    body = "".join(_row(e, rows) for e in entries)
    return (
        f'<section data-section="authorization" data-state="gated"><h2>{escape(GATED_HEADING)}</h2>'
        + scroll_region(
            f'<table class="authorization"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>',
            GATED_HEADING,
            "gated-steps",
        )
        + f'<p data-section="authorization-non-claims">{escape(NON_CLAIMS)}</p>'
        f"<h3>{escape(onedoor_panel.ROWS_HEADING)}</h3>{onedoor_panel.rows_block(rows)}"
        f'<p><a href="{escape(case, quote=True)}">{escape(BACK)}</a></p></section>'
    )


def render_authorization(
    run: StoredRun,
    *,
    generated_at: str,
    case: str,
    head: str = "",
    manifest: dict | None = None,
    steps: list[dict] | None = None,
    rows: list[dict] | None = None,
) -> str:
    """The page for one run. `case` is the relative link back to that run's case page; `head`,
    where the run's pages are drawn, the run's head (as on its run page), above the page's own.
    Where the run's `manifest` and `steps` show a gated step or a cited decision, the page lists them,
    with the verifier's `rows`; elsewhere it reads "No records"."""
    from onetrace_console.preview import label
    from onetrace_console.render import _document, _limit_sentence

    entries = gated_rows(manifest or {}, steps or [])
    if entries:
        body = (
            head + f"<h1>{escape(TITLE)}</h1>"
            f'<p data-state="gated">{escape(GATED_STATE)}</p>'
            f'<p data-section="run">Run <span class="mono" data-words="record">'
            f"{named(run.run_id, record_href(run))}</span></p>"
            + gated_section(entries, rows or [], case)
            + f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>'
            + generated_footer(generated_at)
        )
        return label(_document(f"{TITLE} · {shown_name(run.run_id)}", f'<div class="cp">{body}</div>'), [run])

    body = (
        head + f"<h1>{escape(TITLE)}</h1>"
        f'<p data-state="no-records">{escape(STATE)}</p>'
        f'<p data-section="run">Run <span class="mono" data-words="record">'
        f"{named(run.run_id, record_href(run))}</span></p>"
        f'<section data-section="authorization" data-state="no-records">'
        f"<h2>{escape(HEADING)}</h2>"
        f"<p>{escape(NOT_A_FAULT)}</p>"
        f'<p><a href="{escape(case, quote=True)}">{escape(BACK)}</a></p>'
        f'<p data-section="authorization-note">{escape(NOTE)}</p></section>'
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>' + generated_footer(generated_at)
    )
    #: Titled with its run, as the viewer titles the two pages beside it. In the console's page
    #: skin, board 3's look (item 12).
    body = f'<div class="cp">{body}</div>'
    return label(_document(f"{TITLE} · {shown_name(run.run_id)}", body), [run])


def authorization_link(case_html: str, href: str = AUTHORIZATION) -> str:
    """Splice the link to the run's authorization page into the case page's Policy section.

    Spliced, as the preview label and the incidents block are, because the case page is the
    viewer's. Placed inside the viewer's own `data-section="policy"`, which is where
    authorization appears on a run page, and **refused** when that section is not there: a
    run page that silently lost its way to the authorization page would still look whole.
    """
    policy = re.search(r'<section data-section="policy">.*?(</section>)', case_html, re.S)
    if policy is None:
        raise ValueError("cannot link the authorization page: the case page has no Policy section to place the link in")
    #: Already there only if it is IN the Policy section: a marker elsewhere on the page is not
    #: the link, and must neither stand in for it nor hide a missing section.
    if f'data-section="{LINK_MARKER}"' in policy.group(0):
        return case_html
    link = f'<p data-section="{LINK_MARKER}"><a href="{escape(href, quote=True)}">{escape(TITLE)}</a></p>'
    at = policy.start(1)
    return case_html[:at] + link + case_html[at:]
