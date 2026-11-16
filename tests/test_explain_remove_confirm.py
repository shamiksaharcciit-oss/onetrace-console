"""Remove asks first. The Set up Explain page's Remove leads to a confirmation page: "Remove the key stored for
<provider> at <address>? Explain will need a key again before it can send.", with Remove (destructive) and Cancel
(secondary, back to the page). The keychain changes only on the confirmation page's own POST, which carries the
page's single-use confirmation token (and, with sign-in on, the session's CSRF token, as every press does). No
script and no browser dialog.

On a local console with the stub keychain (tests/keychain.py): the first press changes nothing; the confirming press
removes the key; Cancel changes nothing; a confirming press without its token, or with one not given, is refused.
"""

from __future__ import annotations

import re
from html import unescape

import pytest

from tests.keychain import (
    KEY,
    keychain,  # noqa: F401 - a fixture, requested by name
    keyring_lib,  # noqa: F401 - a fixture, requested by name
    planted_key_searched,  # noqa: F401 - a fixture, requested by name
)
from tests.test_explain_panel import pair  # noqa: F401 - a fixture, requested by `local`
from tests.test_explain_setup import _get, local  # noqa: F401 - `local`, a fixture
from tests.test_explain_setup_form import _post

pytestmark = pytest.mark.usefixtures("planted_key_searched")

USER = "openai:http://127.0.0.1:8080/v1"
ASKED = "Remove the key stored for openai at 127.0.0.1:8080? Explain will need a key again before it can send."


def _stored():
    import keyring

    return keyring.get_password("onetrace-explain", USER)


def _saved(base) -> None:
    status, _ = _post(
        f"{base}/explain/setup",
        {"action": "save", "provider": "openai", "name": "m", "base_url": "http://127.0.0.1:8080/v1", "key": KEY},
    )
    assert status == 200 and _stored() == KEY


def _asked(base) -> tuple[str, str]:
    """The first press: (the confirmation page, its token)."""
    status, page = _post(f"{base}/explain/setup", {"action": "remove"})
    assert status == 200, page[-800:]
    token = re.search(r'<input type="hidden" name="confirm" value="([0-9a-f]{32,})">', page)
    assert token, page[-1500:]
    return page, token.group(1)


def test_the_first_press_asks_and_changes_nothing(local, keychain, examined):
    base, _, _, _, _ = local
    _saved(base)
    page, _token = _asked(base)
    confirm = re.search(
        #: It lands at the setup page's form section.
        r'<form method="post" action="/explain/setup#setup-form" data-setup-form="remove-confirm">.*?</form>',
        page,
        re.S,
    )
    cancel = re.search(r'<form method="get" action="/explain/setup" data-setup-form="cancel">.*?</form>', page, re.S)
    examined(4, "the confirmation page and the keychain")
    assert ASKED in unescape(page)
    assert (
        confirm
        and '<button class="btn-destructive" data-busy="Removing…" type="submit" name="action" value="remove-confirmed">Remove</button>'
        in confirm.group(0)
    )
    assert (
        cancel
        and '<button class="btn-secondary" data-busy="Going back…" type="submit">Cancel</button>' in cancel.group(0)
    )
    assert "<script" not in page.split("<main", 1)[-1].split("</main>", 1)[0] and "confirm(" not in page
    assert _stored() == KEY


def test_the_confirming_press_removes_the_key(local, keychain, examined):
    base, _, _, _, _ = local
    _saved(base)
    _page, token = _asked(base)
    status, page = _post(f"{base}/explain/setup", {"action": "remove-confirmed", "confirm": token})
    examined(1, "the confirming press")
    assert status == 200 and "No key stored." in unescape(page), page[-800:]
    assert _stored() is None


def test_cancel_changes_nothing(local, keychain, examined):
    base, _, _, _, _ = local
    _saved(base)
    _asked(base)
    status, page = _get(f"{base}/explain/setup")
    examined(1, "Cancel, back to the page")
    assert status == 200 and "A key is stored for this provider." in unescape(page)
    assert _stored() == KEY


def test_a_confirming_press_without_its_token_is_refused(local, keychain, examined):
    base, _, _, _, _ = local
    _saved(base)
    _asked(base)
    without, _ = _post(f"{base}/explain/setup", {"action": "remove-confirmed"})
    planted, _ = _post(f"{base}/explain/setup", {"action": "remove-confirmed", "confirm": "0" * 32})
    examined(2, "presses without a token given")
    assert without == 403 and planted == 403
    assert _stored() == KEY
