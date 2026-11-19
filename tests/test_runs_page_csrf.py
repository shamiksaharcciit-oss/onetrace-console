"""The Runs page, drawn as asked, carries the session's CSRF token in its forms' slots, as every served page does.

On a local console with sign-in, the Runs page's Compare picker (a pipeline chosen) posts to /compare with the
session's token. The page is drawn when it is asked for, then filled with the frame; its own slots were left empty, so
the picker's request was refused for a missing token. Read here with a planted slot, through the suite's fake Entra ID.
"""

from __future__ import annotations

import urllib.request

from tests.http_limits import limit
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - the fixture, used by name


def test_the_runs_page_s_forms_carry_the_session_s_token(entra, monkeypatch, examined):  # noqa: F811
    from onetrace_console import runs_page
    from onetrace_console.frame import CSRF_SLOT

    base, fake, _root = entra
    real = runs_page.page
    monkeypatch.setattr(
        runs_page,
        "page",
        lambda *a, **k: real(*a, **k).replace(
            "</main>", f'<form method="post" action="/compare">{CSRF_SLOT}</form></main>', 1
        ),
    )
    _s, _b, _h, session, csrf = sign_in(base, fake, roles=("onetrace.viewer",))
    req = urllib.request.Request(base + "/runs", headers={"Cookie": f"onetrace_session={session}"})
    with urllib.request.urlopen(req, timeout=limit(30)) as r:
        page = r.read().decode("utf-8")
    examined(1, "Runs page")
    assert CSRF_SLOT not in page, "a slot left empty"
    assert (
        f'<form method="post" action="/compare"><input type="hidden" name="csrf_token" value="{csrf}" data-csrf-slot>'
        in page
    )
