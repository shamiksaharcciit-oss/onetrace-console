"""The hosted demo and the capture store's app, each linking to the other (deploy/fly/captures/).

Two settings, each an environment variable the deploy sets on one app, never an address in the code: on the
demo's app, `ONETRACE_CONSOLE_CAPTURES_URL`, the capture store's address, drawn as one line under the
comparisons page's heading ("Token-level examples (L2 and L3): <address>"); on the capture store's app,
`ONETRACE_CONSOLE_DEMO_URL`, the demo's address, drawn as one line under the Overview's heading ("The
onetrace-console demo: <address>"). Added as a public console serves the page (`with_link`), never into the stored
page, so a deploy changes it without a new build. A setting that is absent, empty or not an http(s) address draws
no line. A local console draws neither.
"""

from __future__ import annotations

import os
import re

CAPTURES_VAR = "ONETRACE_CONSOLE_CAPTURES_URL"
DEMO_VAR = "ONETRACE_CONSOLE_DEMO_URL"
EXAMPLES = "Token-level examples (L2 and L3):"
BACK = "The onetrace-console demo:"
#: Each page that gains a line: its heading, the line's words, and the setting that names the address.
LINES = {
    "comparisons.html": (b"<h1>Comparisons</h1>", EXAMPLES, CAPTURES_VAR),
    "home.html": (b"<h1>Overview</h1>", BACK, DEMO_VAR),
}
#: An http(s) address: a host, a port where given, and a path of plain characters.
_ADDRESS = re.compile(r"https?://[A-Za-z0-9.-]+(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~/%-]*)?")


def address(var: str, environ=None) -> str | None:
    """The address the setting `var` names, where it is an http(s) address; None otherwise."""
    value = ((os.environ if environ is None else environ).get(var) or "").strip()
    return value if _ADDRESS.fullmatch(value) else None


def with_link(page: bytes, rel: str, *, public: bool, environ=None) -> bytes:
    """`page`, as served at `rel`, with its line where it is a public console's page that gains one and the
    setting names an address; otherwise unchanged."""
    if not public or rel not in LINES:
        return page
    head, words, var = LINES[rel]
    url = address(var, environ)
    if url is None or page.count(head) != 1:
        return page
    from onetrace_console.words import escape

    line = f'<p data-section="app-link">{escape(words)} <a href="{escape(url, quote=True)}">{escape(url)}</a></p>'
    return page.replace(head, head + line.encode("utf-8"), 1)
