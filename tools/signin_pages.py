"""Serve the pages of sign-in through Microsoft Entra ID, as the console draws them, for the layout check.

    python tools/signin_pages.py --port PORT        (with src on PYTHONPATH)

The sign-in page (Sign in with Microsoft), a refused sign-in's page and the no-role page, and a page as served
to someone signed in with the settings menu open on its Sign out, each from the console's own renderers (`onetrace_console.signin`) with the words the console uses, and the console's
stylesheet at its own address. A running console draws the no-role page only after a whole sign-in at
Entra, whose issuer is derived from a real tenant's id, so the layout check reads the three pages here.
"""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def pages() -> dict[str, tuple[str, bytes]]:
    from onetrace_console.frame import STYLESHEET, stylesheet
    from onetrace_console.oidc_flow import NOT_THIS_BROWSER
    from onetrace_console.oidc_identity import NO_ROLE_WORDS
    from onetrace_console.signin import render_oidc_refused_page, render_oidc_signin_page, render_signin_page

    html = "text/html; charset=utf-8"
    return {
        "/settings-sign-out": (html, _signed_in_page()),
        "/signin/local": (html, render_signin_page(csrf_token="layout-check").encode("utf-8")),
        "/signin": (html, render_oidc_signin_page("/comparisons.html").encode("utf-8")),
        "/signin/refused": (html, render_oidc_refused_page(NOT_THIS_BROWSER).encode("utf-8")),
        "/signin/no-role": (html, render_oidc_refused_page(NO_ROLE_WORDS, no_role=True).encode("utf-8")),
        STYLESHEET: ("text/css; charset=utf-8", stylesheet()),
    }


def _signed_in_page() -> bytes:
    """A console page as it is served to someone signed in: its frame filled, the settings menu ending with Sign
    out. The menu is the browser's popover, closed until pressed; for the layout check it is opened on load, by a
    line of script this tool adds, not the console."""
    from onetrace_console.frame import fill
    from onetrace_console.render import _document

    page = _document("Overview", '<div class="cp"><h1>Overview</h1><p>Signed in.</p></div>').encode("utf-8")
    served = fill(page, "home.html", onedoor=False, user="Ada Lovelace", setup_link=True, store=None, csrf="layout")
    opened = b"<script>document.getElementById('settings-menu').showPopover()</script></body>"
    return served.replace(b"</body>", opened, 1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    port = ap.parse_args(argv).port
    served = pages()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:
            pass

        def do_GET(self) -> None:  # noqa: N802
            found = served.get(self.path) or (served["/signin"] if self.path == "/health" else None)
            ctype, body = found if found else ("text/plain", b"not found\n")
            self.send_response(200 if found else 404)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
