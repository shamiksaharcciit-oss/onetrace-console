"""The settings menu's Explain row, where the configuration keeps its key in the keychain (console 0.7.0), in
three states, as onetrace-explain 0.3 tells them apart: "Explain: key stored" where a key is stored for the
provider the file names; "Explain: no key stored" where none is; "Explain: the keychain can't be read
(<its type>)" where it is locked, or keyring is missing or finds no keychain. The dot on the gear marks
the last two. The key's presence is read, never its value, which is not in the menu. A configuration that
names `key_env` keeps its rows ("on, <model> (<provider>)", "key not found"); one that names both is read by
`key_source`, as onetrace-explain 0.3 reads it.
"""
from __future__ import annotations

import sys

import pytest

from tests.keychain import planted_key_searched, KEY, keychain, keyring_lib  # noqa: F401
from tests.test_settings_menu import _menu, _row, explain_config  # noqa: F401

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

KEYRING_TABLE = '[model]\nprovider = "openai"\nname = "local-model"\nbase_url = "http://127.0.0.1:8080/v1"\nkey_source = "keyring"\n'


def test_a_stored_key_reads_on_with_the_model_and_no_dot(explain_config, keychain, examined):
    import keyring
    explain_config.write_text(KEYRING_TABLE, encoding="utf-8")
    keyring.set_password("onetrace-explain", "openai:http://127.0.0.1:8080/v1", KEY)
    html = _menu()
    examined(1, "menu")
    assert _row(html, "explain") == ("/explain/setup", "on", "Explain: key stored")
    assert "settings-dot" not in html and KEY not in html


def test_no_key_stored_reads_key_not_found_with_the_dot(explain_config, keychain, examined):
    explain_config.write_text(KEYRING_TABLE, encoding="utf-8")
    html = _menu()
    examined(1, "menu")
    assert _row(html, "explain") == ("/explain/setup", "broken", "Explain: no key stored")
    assert "settings-dot" in html


def test_a_key_stored_for_another_address_is_not_this_one_s(explain_config, keychain, examined):
    import keyring
    explain_config.write_text(KEYRING_TABLE, encoding="utf-8")
    keyring.set_password("onetrace-explain", "openai:default", KEY)
    examined(1, "menu")
    assert _row(_menu(), "explain")[1:] == ("broken", "Explain: no key stored")


@pytest.mark.parametrize("how, said", [("locked", "KeyringLocked"), ("no keyring", "ModuleNotFoundError"),
                                       ("no keychain", "NoKeyringError")])
def test_a_keychain_that_can_t_be_read_says_so_by_its_type_never_key_not_found(
        explain_config, keychain, monkeypatch, how, said, examined):
    explain_config.write_text(KEYRING_TABLE, encoding="utf-8")
    if how == "locked":
        (keychain / "locked").write_text("", encoding="utf-8")
    elif how == "no keyring":
        monkeypatch.setitem(sys.modules, "keyring", None)
    else:
        import keyring
        from keyring.backends import fail
        keyring.set_keyring(fail.Keyring())
    html = _menu()
    examined(1, "menu")
    assert _row(html, "explain")[1:] == ("broken", f"Explain: the keychain can't be read ({said})")
    assert "settings-dot" in html and "key not found" not in html


#: A table that names both: `key_source` is read first, as onetrace-explain 0.3 reads it.
BOTH_TABLE = KEYRING_TABLE + 'key_env = "ONETRACE_TEST_KEY_NOT_SET"\n'


@pytest.mark.parametrize("state", ["locked", "stored"])
def test_key_source_is_read_before_key_env(explain_config, keychain, monkeypatch, state, examined):
    import keyring
    monkeypatch.delenv("ONETRACE_TEST_KEY_NOT_SET", raising=False)
    explain_config.write_text(BOTH_TABLE, encoding="utf-8")
    if state == "locked":
        (keychain / "locked").write_text("", encoding="utf-8")
        want = ("broken", "Explain: the keychain can't be read (KeyringLocked)")
    else:
        keyring.set_password("onetrace-explain", "openai:http://127.0.0.1:8080/v1", KEY)
        want = ("on", "Explain: key stored")
    html = _menu()
    examined(1, "menu")
    assert _row(html, "explain")[1:] == want
    assert "key not found" not in html and KEY not in html
