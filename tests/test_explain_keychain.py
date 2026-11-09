"""The key for Explain in this user's keychain: named as onetrace-explain 0.3 names it, said only as stored or
not, replaced and removed from the Set up Explain page, and never read back into a page, a log, a run or
an error.

Held here:
- the console's keychain entry (service and user) is onetrace-explain 0.3's own: its `KEYRING_SERVICE`
  and `keyring_user`, read from the installed 0.3.0 in a process of its own (the console never
  imports onetrace_explain), for a provider with no base_url and with one;
- the page says "A key is stored for this provider." or "No key stored.", with Replace and Remove where
  one is stored; Replace keeps the new key, and Remove takes it out of the keychain;
- a Save with no key where one is stored keeps `key_source = "keyring"`;
- a locked keychain is said, by its type, and nothing is stored or written, a Save with no key refused as one
  with a key is; the press then fails with
  onetrace-explain's own line, which names where it looked and never the key;
- the key planted by the test is searched for in every file the test writes (the console's store, its
  access log, the explanation's run, the configuration's folder), in what the console wrote to its
  output, and in the body of the request the model was sent: it is found only in the keychain's own
  folder and in the request's authorization header.

No model is called: the model is a server on 127.0.0.1 (tests/keychain.py), the keychain a folder of the
test's own.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from html import unescape

import pytest

from tests.keychain import (planted_key_searched, KEY, explain03, explain03_installed, files_holding, keychain,  # noqa: F401
                            keyring_lib, model)
from tests.test_explain_panel import REPLIES, pair, tried  # noqa: F401
from tests.test_explain_setup import _get, _main, local  # noqa: F401
from tests.test_explain_setup_form import _forms, _post

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

NEW_KEY = "sk-test-replaced-9876543210fedcbaNEW"
STORED = "A key is stored for this provider."
NONE_STORED = "No key stored."
#: (provider, base_url): the provider's own address, and one on this machine.
ENTRIES = [("anthropic", ""), ("openai", "http://127.0.0.1:8080/v1"), ("anthropic", "https://example.invalid/api")]


def _save(base, **fields):
    return _post(f"{base}/explain/setup", {"action": "save", "base_url": "", "key": "", **fields})


# ------------------------------------------------------------------ the naming

def _their_naming(lib, entries):
    code = ("import json, sys\nfrom onetrace_explain.providers import KEYRING_SERVICE, keyring_user\n"
            "print(json.dumps([KEYRING_SERVICE, [keyring_user(p, b) for p, b in json.loads(sys.argv[1])]]))")
    done = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(lib)!r})\n" + code,
                           json.dumps(entries)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    service, users = json.loads(done.stdout)
    return service, users


def test_the_entry_is_named_as_onetrace_explain_0_3_names_it(explain03, examined):
    from onetrace_console import explain_keychain as K
    _, lib = explain03
    service, users = _their_naming(lib, ENTRIES)
    examined(len(ENTRIES), "providers")
    assert K.SERVICE == service
    assert [K.user(p, b) for p, b in ENTRIES] == users


def test_sabotage_a_naming_of_its_own_is_named(explain03, monkeypatch, examined):
    from onetrace_console import explain_keychain as K
    _, lib = explain03
    monkeypatch.setattr(K, "user", lambda p, b="": f"{p}@{b or 'default'}")
    _, users = _their_naming(lib, ENTRIES)
    examined(1, "planted naming")
    assert [K.user(p, b) for p, b in ENTRIES] != users


def test_the_console_never_imports_onetrace_explain(examined):
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
    files = list(src.rglob("*.py"))
    examined(len(files), "source files")
    assert [p.name for p in files if "import onetrace_explain" in p.read_text(encoding="utf-8")
            or "from onetrace_explain" in p.read_text(encoding="utf-8")] == []


# ------------------------------------------------------------------ stored, or not; Replace and Remove

def test_the_page_says_a_key_is_stored_with_replace_and_remove_and_never_the_key(local, keychain, examined):
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="a-model", key=KEY)
    status, page = _get(f"{base}/explain/setup")
    forms = {f.split('data-setup-form="')[1].split('"')[0]: f for f in _forms(_main(page)) if "data-setup-form" in f}
    examined(len(forms), "forms")
    assert status == 200 and STORED in unescape(page) and NONE_STORED not in unescape(page)
    assert KEY not in page
    assert sorted(forms) == ["key", "model", "remove"], sorted(forms)
    assert '<input type="password" name="key" autocomplete="new-password"' in forms["key"]
    assert '<button type="submit" name="action" value="replace">Replace</button>' in forms["key"]
    assert '<button type="submit" name="action" value="remove">Remove</button>' in forms["remove"]
    assert "csrf_token" in forms["key"] and "csrf_token" in forms["remove"]


def test_with_none_stored_the_page_says_so_and_offers_no_remove(local, keychain, examined):
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="a-model")
    _, page = _get(f"{base}/explain/setup")
    examined(1, "page")
    assert NONE_STORED in unescape(page) and STORED not in unescape(page)
    assert 'data-setup-form="remove"' not in page


def test_replace_keeps_the_new_key_and_remove_takes_it_out(local, keychain, examined):
    import keyring
    base, _, _, _, config = local
    _save(base, provider="openai", name="m", base_url="http://127.0.0.1:8080/v1", key=KEY)
    status, page = _post(f"{base}/explain/setup", {"action": "replace", "key": NEW_KEY})
    examined(2, "presses: Replace, Remove")
    assert status == 200 and NEW_KEY not in page and KEY not in page, page[-1500:]
    assert keyring.get_password("onetrace-explain", "openai:http://127.0.0.1:8080/v1") == NEW_KEY
    assert tomllib.loads(config.read_text(encoding="utf-8"))["model"]["key_source"] == "keyring"
    status, page = _post(f"{base}/explain/setup", {"action": "remove"})
    assert status == 200 and NONE_STORED in unescape(page)
    assert keyring.get_password("onetrace-explain", "openai:http://127.0.0.1:8080/v1") is None


def test_a_save_with_no_key_where_one_is_stored_keeps_the_keychain(local, keychain, examined):
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="first", key=KEY)
    status, _ = _save(base, provider="anthropic", name="second")
    got = tomllib.loads(config.read_text(encoding="utf-8"))["model"]
    examined(1, "second save")
    assert status == 200 and got["name"] == "second" and got["key_source"] == "keyring" and "key_env" not in got


# ------------------------------------------------------------------ a locked keychain

def test_a_locked_keychain_is_said_and_nothing_is_stored_or_written(local, keychain, examined):
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="a-model")
    before = config.read_text(encoding="utf-8")
    (keychain / "locked").write_text("", encoding="utf-8")
    _, page = _get(f"{base}/explain/setup")
    status, said = _save(base, provider="anthropic", name="other", key=KEY)
    examined(2, "a page and a save, the keychain locked")
    assert "The keychain could not be read (KeyringLocked)" in unescape(page), _main(page)[:3000]
    assert status == 400 and "Not saved: the keychain did not keep the key (KeyringLocked)." in unescape(said)
    assert config.read_text(encoding="utf-8") == before and KEY not in said


@pytest.mark.parametrize("raised", ["unreadable, other words", "unavailable, the unreadable words"])
def test_the_setup_page_s_key_line_is_decided_by_the_error_s_type_not_its_words(local, keychain, monkeypatch,
                                                                               raised, examined):
    """The setup page says the keychain could not be read, by its type, for an Unreadable whatever its
    message says; the words alone, on another Unavailable (no keyring, no keychain), show no key line."""
    from onetrace_console import explain_keychain as K
    base, _, _, _, _ = local
    _save(base, provider="anthropic", name="a-model")

    def stored(provider, base_url):
        if raised.startswith("unreadable"):
            raise K.Unreadable("the keychain said something new", "KeyringLocked")
        raise K.Unavailable("the keychain could not be read (NoKeyringError)", "NoKeyringError")

    monkeypatch.setattr(K, "stored", stored)
    _, page = _get(f"{base}/explain/setup")
    examined(1, f"the setup page, the keychain {raised}")
    if raised.startswith("unreadable"):
        assert 'data-key="unreadable"' in page, _main(page)[:3000]
        assert "The keychain could not be read (KeyringLocked)" in unescape(page)
        assert "something new" not in page
    else:
        assert 'data-setup="key-state"' not in page and "could not be read" not in unescape(page)


def test_a_save_with_no_key_while_locked_is_refused_and_the_file_keeps_its_keychain(local, keychain, examined):
    """A Save with no key, the keychain locked, as a Save with a key, Replace and Remove are: the page says the
    keychain could not be read, by its type, and the file is as it was, `key_source = "keyring"` kept."""
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="a-model", key=KEY)
    before = config.read_text(encoding="utf-8")
    (keychain / "locked").write_text("", encoding="utf-8")
    status, said = _save(base, provider="anthropic", name="other")
    examined(1, "a save with no key, the keychain locked")
    assert status == 400 and "Not saved: the keychain could not be read (KeyringLocked)." in unescape(said), said[-1500:]
    assert "Saved" not in unescape(said).replace("Not saved", "")
    assert config.read_text(encoding="utf-8") == before
    assert tomllib.loads(before)["model"]["key_source"] == "keyring"


@pytest.mark.parametrize("raised, refused", [("unreadable, other words", True),
                                             ("unavailable, the unreadable words", False)])
def test_a_no_key_save_is_decided_by_the_error_s_type_not_its_words(local, keychain, monkeypatch, raised, refused,
                                                                    examined):
    """Whether a Save with no key is refused is decided by what the keychain module knows (an Unreadable,
    there but can't be read), not by the message's words: changing the words changes nothing, and the
    words alone, on another Unavailable (no keyring, no keychain), don't refuse."""
    from onetrace_console import explain_keychain as K
    base, _, _, _, config = local
    _save(base, provider="anthropic", name="a-model", key=KEY)
    before = config.read_text(encoding="utf-8")

    def stored(provider, base_url):
        if raised.startswith("unreadable"):
            raise K.Unreadable("the keychain said something new (KeyringLocked)", "KeyringLocked")
        raise K.Unavailable("the keychain could not be read (NoKeyringError)", "NoKeyringError")

    monkeypatch.setattr(K, "stored", stored)
    status, said = _save(base, provider="anthropic", name="other")
    examined(1, f"a save with no key, the keychain {raised}")
    if refused:
        assert status == 400 and "Not saved: the keychain said something new (KeyringLocked)." in unescape(said)
        assert config.read_text(encoding="utf-8") == before
    else:
        assert status == 200 and "Not saved" not in unescape(said), said[-1500:]
        assert 'name = "other"' in config.read_text(encoding="utf-8")


def test_only_a_keychain_that_is_there_and_can_t_be_read_raises_unreadable(keychain, examined):
    from onetrace_console import explain_keychain as K
    (keychain / "locked").write_text("", encoding="utf-8")
    with pytest.raises(K.Unreadable) as got:
        K.stored("anthropic", "")
    examined(1, "locked keychain")
    assert isinstance(got.value, K.Unavailable) and got.value.kind == "KeyringLocked"
    assert str(got.value) == "the keychain could not be read (KeyringLocked)"


def test_a_press_with_the_keychain_locked_fails_with_where_it_looked_never_the_key(
        local, explain03_installed, model, examined):
    from onetrace_console import explain
    base, _, store, comparison, config = local
    _save(base, provider="openai", name="stub-model", base_url=model.base_url, key=KEY)
    import os
    from pathlib import Path
    (Path(os.environ["ONETRACE_TEST_KEYCHAIN"]) / "locked").write_text("", encoding="utf-8")
    attempt = explain.explain(store.get_comparison(comparison.key), store, send=True)
    examined(1, "press")
    assert model.requests == []
    assert "the keychain could not be read (KeyringLocked)" in attempt["stderr"], tried(store, comparison)
    assert KEY not in json.dumps(attempt)


# ------------------------------------------------------------------ the key, nowhere

@pytest.mark.parametrize("answer", ["reply", "echo in a reply", "echo in an error"])
def test_the_planted_key_is_only_in_the_keychain_and_the_request_s_header(
        local, explain03_installed, model, keychain, capfd, tmp_path, answer, examined):
    from onetrace_console import explain
    base, _, store, comparison, config = local
    if answer == "reply":
        model.text = (REPLIES / "mixed.json").read_text(encoding="utf-8")
    elif answer == "echo in a reply":
        model.text = json.dumps({"claims": [{"text": f"the key is `{KEY}`", "kind": "note", "cites": []}]})
    else:
        model.answer, model.status, model.text = "error", 401, f"invalid key {KEY}"
    _save(base, provider="openai", name="stub-model", base_url=model.base_url, key=KEY)
    pages = [_get(f"{base}/explain/setup")[1]]
    explain.explain(store.get_comparison(comparison.key), store, send=True)
    from onetrace_console.render import render_diff
    pages.append(render_diff(store.get_comparison(comparison.key), store, generated_at="2026-11-07T00:00:00+00:00"))
    pages.append(_post(f"{base}/explain/setup", {"action": "replace", "key": KEY})[1])
    out, err = capfd.readouterr()
    found = files_holding(tmp_path, KEY, but=keychain)
    examined(len(list(tmp_path.rglob("*"))), "files under the test's folder")
    assert len(model.requests) == 1, tried(store, comparison)
    assert model.requests[0]["headers"].get("Authorization") == f"Bearer {KEY}"
    assert KEY.encode() not in model.requests[0]["body"]
    assert found == [], found
    assert KEY not in out and KEY not in err
    assert not any(KEY in p for p in pages)
    #: And no 8 of its characters in a row, as onetrace-explain 0.3 holds its own replies.
    runs = [KEY[i:i + 8] for i in range(len(KEY) - 7)]
    assert not any(r in p for p in pages for r in runs if r not in ("sk-test-",))


def test_sabotage_a_file_holding_the_planted_key_is_named(tmp_path, examined):
    """The search every test here ends with (`planted_key_searched`) finds a file that holds the key, and
    sets aside the keychain's own folder."""
    from tests.keychain import key_problems
    (tmp_path / "keychain").mkdir()
    (tmp_path / "keychain" / "entries.json").write_text(KEY, encoding="utf-8")
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "leak.txt").write_text(f"said: {KEY}\n", encoding="utf-8")
    found = key_problems(tmp_path)
    examined(2, "planted files")
    (tmp_path / "logs" / "leak.txt").unlink()
    assert found == ["logs/leak.txt holds the planted key"]
