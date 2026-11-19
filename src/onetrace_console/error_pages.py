"""An error a browser meets is a page: the console's own words, in its frame, in both themes.

The console answers 401, 403, 404, 405 and 500 with one plain line of its own ("not rendered: <path>", "this
credential does not grant the required role", the server error with its reference). A browser asking for a page
(`Accept` naming `text/html`, a page's path, not the API's) gets that line inside a page instead: a title, the
document's language, a heading, what happened in words, the console's line as it said it, and a link to the Overview
(and, for 401, to sign-in). Every other client, the API's, the ingest and SCIM clients, scripts and tests, gets the
plain line byte for byte, as before.

What the page does not do: it does not say what is at the address, or whether anything is (a team's runs, another
team's set and an address that never existed answer alike), and it names no path on this machine. A 500's page keeps
the reference its line gives, which the operator's log names.
"""

from __future__ import annotations

from onetrace_console.words import escape

#: Status: (the title and heading, what happened in words).
PAGES: dict[int, tuple[str, str]] = {
    401: ("Sign-in needed", "This page is shown to people who are signed in."),
    403: ("Not available to you", "Your sign-in does not open this page. Ask your administrator if you need it."),
    404: (
        "Page not found",
        "There is no page at this address. A run's pages are addressed by the run itself, so an address from an "
        "earlier build of a console can stop answering.",
    ),
    405: ("Not answered here", "This address does not answer that kind of request."),
    500: (
        "The console could not answer",
        "Something went wrong while the console answered this request. Its log names the cause under the reference "
        "below.",
    ),
}
#: Paths whose answers are for programs, never pages: the API, SCIM, the stylesheet and fonts, the health check, the
#: sign-in flow's own steps.
NOT_PAGES = ("/v1/", "/scim/", "/static/", "/health", "/signin/oidc/")


def wants_page(path: str, accept: str | None) -> bool:
    """A browser's request for a page: `Accept` names `text/html`, and the path is not a program's."""
    return "text/html" in (accept or "") and not any(path == p.rstrip("/") or path.startswith(p) for p in NOT_PAGES)


def document(status: int, said: str) -> str:
    """The page for `status`, holding `said`, the console's own line, in the frame the server fills."""
    from onetrace_console.render import _document

    title, words = PAGES[status]
    sign_in = '<a href="/signin">Sign in</a> · ' if status == 401 else ""
    body = (
        f'<div class="cp" data-page="error" data-status="{status}" id="error">'
        f"<h1>{escape(title)}</h1>"
        f'<p data-section="error-words">{escape(words)}</p>'
        f'<p data-section="error-said" class="sub">The console said: <code>{escape(said.strip())}</code></p>'
        f'<p data-section="error-next">{sign_in}<a href="/">Go to the Overview</a></p>'
        "</div>"
    )
    return _document(f"{title} · onetrace", body, skip=("Skip to the message", "error"))
