"""What a public console tells search engines.

A public console's run pages are addressed by their runs' content, so each new build of the hosted demo gives them new
addresses and the old ones answer 404. Search engines are told to index the Overview only:

- every page a public console serves carries `<meta name="robots" content="noindex">`, but the Overview at `/`;
- the Overview, at `/` and at `/home.html` (the same page), carries `<link rel="canonical">` to the console's own
  public address: the setting `ONETRACE_CONSOLE_PUBLIC_URL`, an environment variable the deploy sets, as it sets the
  demo's other links (`app_links`). Absent, empty or not an http(s) address, no canonical is drawn;
- `/robots.txt` allows crawling, so each page's `noindex` can be read; no sitemap is served.

A sealed page carries its `noindex` from when it was drawn (`frame.fill_sealed`), so its seal covers it and it is
served as written; every other page gains it as it is served. A console on this machine is unchanged. A static
export's pages carry `noindex` too (`export_static`).
"""

from __future__ import annotations

from onetrace_console.app_links import address
from onetrace_console.words import escape

PUBLIC_URL_VAR = "ONETRACE_CONSOLE_PUBLIC_URL"
NOINDEX = '<meta name="robots" content="noindex">'
ROBOTS_TXT = "User-agent: *\nAllow: /\n"
#: The Overview, the one page to index, and the same page at its other address.
OVERVIEW, OVERVIEW_PAGE = "/", "/home.html"
_HEAD = b"<head>"


def with_noindex(page: str) -> str:
    """`page` with `noindex` first in its `<head>`; unchanged where it carries it already or has no `<head>`."""
    if NOINDEX in page or "<head>" not in page:
        return page
    return page.replace("<head>", "<head>" + NOINDEX, 1)


def canonical(environ=None) -> str | None:
    """The Overview's canonical address: the console's own public address, ending in `/`; None where it is not set."""
    url = address(PUBLIC_URL_VAR, environ)
    return None if url is None else url.rstrip("/") + "/"


def for_search(page: bytes, path: str, *, environ=None) -> bytes:
    """A public console's HTML page as served at `path`: `noindex` but at the Overview, and the Overview's canonical
    at both its addresses where the setting names one."""
    if _HEAD not in page:
        return page
    if path != OVERVIEW:
        noindex = NOINDEX.encode("utf-8")
        if noindex not in page:
            page = page.replace(_HEAD, _HEAD + noindex, 1)
    url = canonical(environ) if path in (OVERVIEW, OVERVIEW_PAGE) else None
    if url is not None and b'rel="canonical"' not in page:
        link = f'<link rel="canonical" href="{escape(url, quote=True)}">'.encode()
        page = page.replace(_HEAD, _HEAD + link, 1)
    return page
