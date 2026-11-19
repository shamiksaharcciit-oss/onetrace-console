"""Serve the pages of sign-in through Microsoft Entra ID, as the console draws them, for the layout check.

    python tools/signin_pages.py --port PORT        (with src on PYTHONPATH)

The admin pages, people, teams and the audit log, drawn from invented facts (`example_facts`). The sign-in page (Sign
in with Microsoft), a refused sign-in's page and the no-role page, and a page as served
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
        **{f"/admin/{which}": (html, _admin_page(which)) for which in ("people", "teams", "audit")},
        "/forwarding/setup": (html, _forwarding_page()),
        "/settings-forwarding": (html, _signed_in_page(_FactsStore(_forwarding_root()))),
        STYLESHEET: ("text/css; charset=utf-8", stylesheet()),
    }


def _signed_in_page(store=None) -> bytes:
    """A console page as it is served to someone signed in: its frame filled, the settings menu ending with Sign
    out. The menu is the browser's popover, closed until pressed; for the layout check it is opened on load, by a
    line of script this tool adds, not the console."""
    from onetrace_console.frame import fill
    from onetrace_console.render import _document

    page = _document("Overview", '<div class="cp"><h1>Overview</h1><p>Signed in.</p></div>').encode("utf-8")
    served = fill(page, "home.html", onedoor=False, user="Ada Lovelace", setup_link=True, store=store, csrf="layout")
    opened = b"<script>document.getElementById('settings-menu').showPopover()</script></body>"
    return served.replace(b"</body>", opened, 1)


def example_facts():
    """The admin pages' facts, invented for the layout check: two people, one inactive, a token expiring soon, a
    value dropped, a group no team names, SCIM's enforcement off and the audit log failing, so every part is drawn."""
    from onetrace_console.admin_pages import Facts

    users = [
        {
            "userName": "ada.lovelace@example.org",
            "displayName": "Ada Lovelace",
            "email": "ada.lovelace@example.org",
            "externalId": "0a21f0f2-8d2a-4f8e-bf98-7363c4aed4ef",
            "active": True,
        },
        {
            "userName": "charles.babbage@example.org",
            "displayName": "Charles Babbage",
            "email": "",
            "externalId": "6f3a1e3b-5b2c-4a5e-9a3e-1b2c3d4e5f60",
            "active": False,
        },
    ]
    group = {
        "displayName": "Payments engineers",
        "externalId": "7a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d",
        "members": ["a" * 32],
    }
    return Facts(
        scim_on=True,
        enforcement=(False, "2026-11-14T22:05:31Z"),
        users=users,
        tokens=[
            {"id": "3f2a" * 8, "expires": "2026-11-24T09:00:00Z", "soon": True},
            {"id": "9c1b" * 8, "expires": "2027-02-12T09:00:00Z", "soon": False},
        ],
        refused_sources=3,
        dropped=[{"at": "2026-11-14T21:40:02.118Z", "id": "b" * 32, "dropped": ["externalId 'mailNickname'"]}],
        refused_writes=[
            {"at": "2026-11-14T21:41:09.004Z", "method": "PATCH", "status": 400, "reason": "the body is not JSON"}
        ],
        teams={
            "payments": {"scim_group": "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e", "role_claim": "Team.Payments"},
            "search-eu": {"role_claim": "Team.Search"},
        },
        groups=[group],
        unmapped=[group],
        unprovisioned=["payments"],
        audit_on=True,
        head={"seq": 1842, "head": "sha256:" + "4e" * 32},
        head_location="/mnt/audit-heads/heads.jsonl",
        unrecorded=[{"at": "2026-11-14T22:01:17.551Z", "event": "signout"}],
    )


class _FactsStore:
    """As much of a store as the settings menu reads: its root."""

    def __init__(self, store_root) -> None:
        self.root = store_root / "store"


_FORWARDING: list = []


def _forwarding_root():
    """Trace forwarding's destinations, invented for the layout check, in a folder of this tool's own: one whose key's
    variable is not set, one in protobuf whose last attempt failed with entries queued and one stopped, and one off
    whose value is kept in the keychain. Nothing is sent."""
    import tempfile
    from pathlib import Path

    if _FORWARDING:
        return _FORWARDING[0]
    from onetrace_console import forwarding as F

    root = Path(tempfile.mkdtemp(prefix="onetrace-layout-forwarding-"))
    a, _ = F.save(
        root,
        None,
        {
            "name": "LangSmith",
            "endpoint": "https://api.smith.langchain.com/otel",
            "headers": [{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_LAYOUT_CHECK_UNSET"}],
        },
    )
    b, _ = F.save(
        root,
        None,
        {
            "name": "Collector on this machine",
            "endpoint": "http://127.0.0.1:4318",
            "encoding": "protobuf",
            "runs": "agree",
        },
    )
    F.save(
        root,
        None,
        {
            "name": "Langfuse",
            "endpoint": "https://cloud.langfuse.com/api/public/otel",
            "enabled": False,
            "headers": [{"name": "Authorization", "key_source": "keyring"}],
        },
    )
    for n, state in ((1, "queued"), (2, "queued"), (3, "stopped")):
        F._write_json(
            F._queue(root, b.id) / f"{n:064x}.json",
            {
                "run": f"{n:064x}",
                "check": "records agree",
                "attempts": 2,
                "next_at": 0.0,
                "state": state,
                "last": "401 Unauthorized" if state == "stopped" else "503 Service Unavailable",
            },
        )
    F._note(
        root,
        b.id,
        last_send="2026-11-15T09:12:30Z",
        last_failure="503 Service Unavailable",
        last_failure_at="2026-11-15T09:40:02Z",
    )
    _FORWARDING.append(root)
    return root


def _forwarding_page() -> bytes:
    from onetrace_console.forward_pages import REL, page
    from onetrace_console.frame import fill

    root = _forwarding_root()
    drawn = page(root, "Added: Collector on this machine.").encode("utf-8")
    return fill(drawn, REL, onedoor=False, user="Ada Lovelace", setup_link=True, store=_FactsStore(root), csrf="layout")


def _admin_page(which: str) -> bytes:
    from onetrace_console.admin_pages import PATHS, page
    from onetrace_console.frame import fill

    drawn = page(which, example_facts()).encode("utf-8")
    return fill(drawn, PATHS[which], onedoor=False, user="Ada Lovelace", setup_link=True, store=None, csrf="layout")


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
