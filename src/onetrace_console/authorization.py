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
third is the illustration's. None is made. The viewer's independent review found the same
over-claim in the case page's Policy sentence (its finding 8). What the page can say is what
release 1 has: no authorization records for this run, and that this is not a fault.

Board 3's AADP sentence ("When a policy engine that speaks AADP is added, this page shows the
whole chain for each action...") is left out too, after this page's own review: it presupposes
that no engine has been added -- the same claim about an unseen pipeline -- and promises a page
nothing here backs yet.

Board 3's "How to add authorization records" button is not rendered either: there is no page
or document for it to open yet, and a link to nothing is worse than none.

The words are v6 board 3's.
"""
from __future__ import annotations

import re
from onetrace_console.words import escape, named, record_href, shown_name, generated_footer

from onetrace_console.store import StoredRun

AUTHORIZATION = "authorization.html"

TITLE = "Authorization"
STATE = "No records"
HEADING = "No authorization records for this run"
NOT_A_FAULT = "That is not a failure of the record."
NOTE = ('Nothing here is counted as a pass. "No records" is shown wherever authorization '
        "would appear.")
BACK = "Back to the run"

#: The link's own marker. NOT a name the viewer's page carries, because a guard keyed on
#: someone else's section silently decides the work is already done.
LINK_MARKER = "authorization-link"


def render_authorization(run: StoredRun, *, generated_at: str, case: str) -> str:
    """The page for one run. `case` is the relative link back to that run's case page."""
    from onetrace_console.preview import label
    from onetrace_console.render import _document, _limit_sentence

    body = (
        f"<h1>{escape(TITLE)}</h1>"
        f'<p data-state="no-records">{escape(STATE)}</p>'
        f'<p data-section="run">Run <span class="mono" data-words="record">'
        f"{named(run.run_id, record_href(run))}</span></p>"
        f'<section data-section="authorization" data-state="no-records">'
        f"<h2>{escape(HEADING)}</h2>"
        f"<p>{escape(NOT_A_FAULT)}</p>"
        f'<p><a href="{escape(case, quote=True)}">{escape(BACK)}</a></p>'
        f'<p data-section="authorization-note">{escape(NOTE)}</p></section>'
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>'
        + generated_footer(generated_at))
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
        raise ValueError("cannot link the authorization page: the case page has no Policy "
                         "section to place the link in")
    #: Already there only if it is IN the Policy section: a marker elsewhere on the page is not
    #: the link, and must neither stand in for it nor hide a missing section (the review of
    #: the first version).
    if f'data-section="{LINK_MARKER}"' in policy.group(0):
        return case_html
    link = (f'<p data-section="{LINK_MARKER}"><a href="{escape(href, quote=True)}">'
            f"{escape(TITLE)}</a></p>")
    at = policy.start(1)
    return case_html[:at] + link + case_html[at:]
