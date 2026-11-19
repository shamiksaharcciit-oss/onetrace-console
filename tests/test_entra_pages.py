"""The layout check reads sign-in through Entra ID's three pages (`tools/signin_pages.py`): the sign-in page,
a refused sign-in's page and the no-role page, each as the console's renderers draw it, with its stylesheet."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from tests.http_limits import limit

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "signin_pages.py"


def test_the_layout_check_names_the_three_kinds(examined):
    sys.path.insert(0, str(REPO))
    from tools import layout_check

    examined(2, "SIGNIN_KINDS, and each in KINDS")
    assert layout_check.SIGNIN_KINDS == {
        "signin-entra": "signin",
        "signin-refused": "signin/refused",
        "signin-no-role": "signin/no-role",
        "settings-sign-out": "settings-sign-out",
        "signin-local": "signin/local",
        "admin-people": "admin/people",
        "admin-teams": "admin/teams",
        "admin-audit": "admin/audit",
        "forwarding-setup": "forwarding/setup",
        "settings-forwarding": "settings-forwarding",
    }
    assert set(layout_check.SIGNIN_KINDS) <= set(layout_check.KINDS)


def test_each_page_is_served_with_the_console_s_words_and_stylesheet(examined):
    from onetrace_console.oidc_identity import NO_ROLE_WORDS

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-B", str(TOOL), "--port", str(port)],
        env={**os.environ, "PYTHONPATH": str(REPO / "src")},
    )
    try:
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/health", timeout=limit(5)).read()
                break
            except OSError:
                time.sleep(0.1)

        def get(path: str) -> str:
            with urllib.request.urlopen(base + path, timeout=limit(5)) as r:
                return r.read().decode("utf-8")

        examined(5, "the three pages, the stylesheet, the signed-in page's menu")
        assert "Sign in with Microsoft" in get("/signin")
        assert "Start again" in get("/signin/refused")
        import html

        assert NO_ROLE_WORDS in html.unescape(get("/signin/no-role"))
        assert get("/static/console.css").strip()
        menu = get("/settings-sign-out")
        assert 'action="/signout"' in menu and ">Sign out</button>" in menu and "showPopover()" in menu
    finally:
        proc.terminate()
        proc.wait(timeout=limit(10))
