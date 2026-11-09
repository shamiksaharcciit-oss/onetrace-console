"""What the Set up Explain page says of the keychain, in so many words, where the key can be kept there
(console 0.7.0): who can read it, and that the console stores none."""
from __future__ import annotations

import pytest

from tests.keychain import planted_key_searched, keychain, keyring_lib  # noqa: F401
from tests.test_explain_no_keychain import no_keyring  # noqa: F401
from tests.test_explain_panel import pair  # noqa: F401
from tests.test_explain_setup import _get, _main, _text, local  # noqa: F401

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

NON_CLAIMS = ("The key is kept by your operating system's keychain, under this user's login. Anyone who can run "
              "code as this user can read it, as with an environment variable. The console stores no key.")


def test_the_page_says_who_can_read_the_key_and_that_the_console_stores_none(local, keychain, examined):
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    examined(1, "page")
    assert NON_CLAIMS in _text(_main(page))
    assert '<p data-setup="keychain-words">' in page


def test_where_no_key_can_be_kept_there_it_is_not_said(local, no_keyring, examined):
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    examined(1, "page")
    assert NON_CLAIMS not in _text(_main(page))


WHERE_THE_KEY_IS = ("The key stays with you: in this user's keychain, kept with the form below, or in the variable "
                    "your configuration names. onetrace-explain reads it there when it sends. The console keeps and "
                    "shows no key, and reads the keychain only to say whether one is stored.")
STEP_3_KEY = ("Keep your key in this user's keychain with the form in step 1, or set it in your own environment, in "
              "the variable key_env names.")


def test_the_page_says_where_the_key_is_as_it_is_now(local, keychain, examined):
    """The provider's paragraph and step 3 name both places a key can be, and the page no longer says the
    console never reads it: it reads the keychain to say whether a key is stored."""
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    said = _text(_main(page))
    examined(1, "page")
    assert WHERE_THE_KEY_IS in said and STEP_3_KEY in said
    assert "never reads" not in said
