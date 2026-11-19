"""An error page drawn for a caller with no session carries no settings menu, as the sign-in page carries none.

With sign-in on, a browser with no session asking for a page that does not exist met the framed 404 with the settings
menu in its frame, and in it what the console has configured (Explain's model, the tokenizers, forwarding). The menu
is now drawn for a signed-in person only, on a console with sign-in. Read on the suite's two-team console, through its
fake Entra ID.
"""

from __future__ import annotations

from tests.test_team_pages import A
from tests.test_team_serving import console, get, session  # noqa: F401 - the fixture, requested by name

HTML = {"Accept": "text/html"}


def test_an_anonymous_error_page_has_no_settings_menu_and_a_signed_in_one_does(console, examined):  # noqa: F811
    base, _store, _views, _config = console
    anonymous = get(base, "/no-such-page", HTML)
    signed_in = get(base, "/no-such-page", {**HTML, **session("admin", (A,))})
    examined(2, "error pages")
    status, body, _ = anonymous
    assert status == 404 and b"Page not found" in body
    assert b'data-frame="settings-menu"' not in body
    for word in (b"Explain", b"Forwarding", b"Tokenizer"):
        assert word not in body, word
    #: A signed-in person's error page keeps the menu, as every page of theirs does.
    assert signed_in[0] == 404 and b'data-frame="settings-menu"' in signed_in[1]
