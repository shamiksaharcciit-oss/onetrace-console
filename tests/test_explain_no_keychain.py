"""No keychain: keyring not importable in the console's Python, or no keychain that works (a server with no
desktop login). The Set up Explain page says so, gives the install line for the Python the console runs
from (as the neighbours page does, with Windows' two lines where either shell quotes that Python), and
keeps today's way: the variable `key_env` names. The form then has no key field, and a Save that carries
a key anyway stores nothing and writes nothing.
"""
from __future__ import annotations

import re
import sys
from html import unescape

import pytest

from tests.keychain import planted_key_searched, KEY, keychain, keyring_lib  # noqa: F401
from tests.test_explain_panel import pair  # noqa: F401
from tests.test_explain_setup import _get, _main, _text, local  # noqa: F401
from tests.test_explain_setup_form import _forms, _post

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

INSTALL = 'pip install "onetrace-explain[keyring]"'


@pytest.fixture
def no_keyring(monkeypatch):
    """keyring not importable, whatever this environment holds."""
    monkeypatch.setitem(sys.modules, "keyring", None)


@pytest.fixture
def no_backend(keychain):
    """keyring importable, and no keychain that works: its own `fail.Keyring`, as on a headless server."""
    import keyring
    from keyring.backends import fail
    keyring.set_keyring(fail.Keyring())
    return keychain


def _section(page: str) -> str:
    found = re.search(r'<div data-setup="no-keychain">(.*?)</div>', page, re.S)
    return found.group(1) if found else ""


@pytest.mark.parametrize("which, why", [
    ("no_keyring", "keyring is not installed in the Python this console runs from"),
    ("no_backend", "keyring finds no keychain that works for this user here"),
])
def test_the_page_says_there_is_no_keychain_and_gives_the_install_line_and_today_s_way(
        local, request, which, why, examined):
    request.getfixturevalue(which)
    base, _, _, _, _ = local
    status, page = _get(f"{base}/explain/setup")
    said = _text(_section(page))
    examined(1, "page")
    assert status == 200 and said, _main(page)[:3000]
    assert f"No keychain here: {why}." in said
    assert f"This console runs from: {sys.executable}" in said
    assert INSTALL in said and f"{sys.executable} -m {INSTALL}" in said
    assert "Until then, set the key in the variable key_env names, as in the example above." in said
    model = [f for f in _forms(_main(page)) if 'data-setup-form="model"' in f]
    assert len(model) == 1 and 'type="password"' not in model[0]


def test_on_windows_the_install_line_is_given_for_each_shell(local, no_keyring, monkeypatch, examined):
    from onetrace_console import explain
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    python = r"C:\Program Files\Python312\python.exe"
    monkeypatch.setattr(sys, "executable", python)
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    section = _section(page)
    lines = {shell: _text(line) for shell, line in re.findall(r'<p class="note" data-shell="(\w+)">(.*?)</p>', section, re.S)}
    examined(len(lines), "shells")
    assert lines == {"cmd": f'In Command Prompt: "{python}" -m {INSTALL}',
                     "powershell": f'In PowerShell: & "{python}" -m {INSTALL}'}, section


def test_with_a_keychain_there_is_no_such_section(local, keychain, examined):
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    examined(1, "page")
    assert 'data-setup="no-keychain"' not in page
    assert 'type="password" name="key"' in page


@pytest.mark.parametrize("which", ["no_keyring", "no_backend"])
def test_a_save_carrying_a_key_with_no_keychain_stores_and_writes_nothing(local, request, which, examined):
    request.getfixturevalue(which)
    base, _, _, _, config = local
    config.write_text('[model]\nprovider = "anthropic"\nname = "kept"\nkey_env = "MY_KEY"\n', encoding="utf-8")
    before = config.read_text(encoding="utf-8")
    status, said = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "x",
                                                   "base_url": "", "key": KEY})
    examined(1, "save")
    assert status == 400 and "Not saved: " in unescape(said) and KEY not in said
    assert config.read_text(encoding="utf-8") == before


def test_a_keyring_that_loads_only_in_part_reads_as_no_keychain(local, keychain, monkeypatch, examined):
    """keyring importable, and a part of it not (a library it needs gone): the page says there is no
    keychain, by the error's type, and is served."""
    import keyring.backends
    monkeypatch.delattr(keyring.backends, "fail", raising=False)
    monkeypatch.setitem(sys.modules, "keyring.backends.fail", None)
    base, _, _, _, _ = local
    status, page = _get(f"{base}/explain/setup")
    examined(1, "page")
    assert status == 200
    assert "No keychain here: keyring could not find a keychain (ModuleNotFoundError)." in _text(_section(page))
