"""The Set up Explain page's form, on a local console: provider, model name, base_url and the key; Save.

Held here:
- the page has one form posting to `/explain/setup`, with the CSRF slot the console's other forms carry
  (filled from the session, checked as the sign-out form's is): a provider (`anthropic`, or `openai` for
  any OpenAI-compatible address), the model's name, `base_url` (required for `openai`) and the key in a
  password field (optional, as for a local server);
- Save writes `[model]` to the file the page names, atomically (a write that fails leaves the file as it
  was, and no stray file), keeping every other line of the file byte for byte: other tables, the
  table's own other keys, comments;
- with a key given, the file says `key_source = "keyring"` and no `key_env`, and the key is in the
  keychain, never in the file; the answer to Save shows the `[model]` lines as written, never the key;
- the next Send uses what was saved, with no restart: the model server on this machine's loopback is
  sent the model's name, and the key only in the request's authorization header;
- a public console has no such route, and a static export has no such form.

No model is called: the model is a server on 127.0.0.1 that keeps what it is sent (tests/keychain.py), the
keychain a folder of the test's own.
"""
from __future__ import annotations

import dataclasses
import json
import re
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

import pytest
from tests.http_limits import limit

from tests.keychain import planted_key_searched, KEY, explain03, explain03_installed, keychain, keyring_lib, model  # noqa: F401
from tests.test_explain_panel import REPLIES, pair, tried  # noqa: F401
from tests.test_explain_setup import _get, _main, local  # noqa: F401

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

#: A file a person keeps by hand: a comment, a key before any table, the [model] table with a key of its
#: own and a subtable, and a table of another program's.
KEPT = ('# my settings, by hand\n'
        'top = "level"\n\n'
        '[model]\n'
        'provider = "anthropic"  # was this\n'
        'name = "old-model"\n'
        'key_env = "MY_KEY_VARIABLE"\n'
        'timeout_note = "kept as it is"\n\n'
        '[model.params]\n'
        'temperature = "0.2"\n\n'
        '[elsewhere]\n'
        'value = "another program\'s"\n')
#: The [model] keys the form writes; every other line of the file is kept.
WRITTEN = ("provider", "name", "base_url", "key_env", "key_source")


def _post(url: str, fields: dict) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=limit(60)) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _kept_lines(text: str) -> list[str]:
    """The file's lines but the [model] table's own lines for the keys the form writes."""
    out, table = [], None
    for line in text.splitlines(keepends=True):
        head = re.match(r"\s*\[([^\]]+)\]", line)
        if head:
            table = head.group(1).strip()
        key = re.match(r"\s*([A-Za-z0-9_-]+)\s*=", line)
        if table == "model" and key and key.group(1) in WRITTEN:
            continue
        out.append(line)
    return out


def _forms(main: str) -> list[str]:
    return re.findall(r"<form\b.*?</form>", main, re.S)


# ------------------------------------------------------------------ the form

def test_the_local_page_has_one_form_with_the_four_fields_and_the_csrf_slot(local, keychain, examined):
    """Where there is a keychain; where there is none, the form has no key field (test_explain_no_keychain)."""
    base, _, _, _, _ = local
    status, page = _get(f"{base}/explain/setup")
    forms = [f for f in _forms(_main(page)) if 'data-setup-form="model"' in f]
    examined(len(forms), "model forms")
    assert status == 200 and len(forms) == 1, _main(page)[:3000]
    form = forms[0]
    assert re.match(r'<form method="post" action="/explain/setup" data-setup-form="model">', form), form[:200]
    assert '<input type="hidden" name="csrf_token" value="" data-csrf-slot>' in form
    assert re.findall(r'<option value="([^"]*)"', form) == ["anthropic", "openai"]
    assert re.search(r'<input type="text" name="name"[^>]* required', form)
    assert re.search(r'<input type="url" name="base_url"', form)
    key = re.search(r'<input type="password" name="key"[^>]*>', form)
    assert key and 'autocomplete="new-password"' in key.group(0) and "required" not in key.group(0)
    assert 'value=' not in key.group(0)
    assert re.search(r'<button type="submit" name="action" value="save">Save</button>', form)


def test_the_form_s_csrf_slot_is_filled_with_the_session_s_token(examined):
    from onetrace_console.frame import fill_csrf
    from onetrace_console import explain_setup
    page = fill_csrf(explain_setup.page(None).encode("utf-8"), "the-session-token").decode("utf-8")
    examined(1, "page")
    assert '<input type="hidden" name="csrf_token" value="the-session-token" data-csrf-slot>' in page


# ------------------------------------------------------------------ Save

def test_save_writes_the_model_table_and_keeps_every_other_line_byte_for_byte(local, examined):
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")
    status, page = _post(f"{base}/explain/setup", {"action": "save", "provider": "openai", "name": "local-model",
                                                   "base_url": "http://127.0.0.1:8080/v1", "key": ""})
    written = config.read_text(encoding="utf-8")
    examined(len(KEPT.splitlines()), "lines of the file")
    assert status == 200, page[-2000:]
    assert _kept_lines(written) == _kept_lines(KEPT), written
    got = tomllib.loads(written)
    assert {k: got["model"].get(k) for k in ("provider", "name", "base_url")} == {
        "provider": "openai", "name": "local-model", "base_url": "http://127.0.0.1:8080/v1"}
    #: No key given and none stored: the variable the file names stays, as it was.
    assert got["model"]["key_env"] == "MY_KEY_VARIABLE" and "key_source" not in got["model"]
    assert got["model"]["params"] == {"temperature": "0.2"}
    assert got["elsewhere"] == {"value": "another program's"} and got["top"] == "level"


def test_save_writes_a_new_file_where_there_is_none(local, examined):
    base, _, _, _, config = local
    config.unlink()
    status, _ = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "a-model",
                                                "base_url": "", "key": ""})
    examined(1, "file")
    assert status == 200
    assert tomllib.loads(config.read_text(encoding="utf-8")) == {"model": {"provider": "anthropic", "name": "a-model"}}


@pytest.mark.parametrize("fields, said", [
    ({"provider": "openai", "name": "m", "base_url": ""}, "An openai provider needs its address, base_url."),
    ({"provider": "other", "name": "m", "base_url": ""}, "Choose anthropic or openai."),
    ({"provider": "anthropic", "name": "", "base_url": ""}, "Give the model's name."),
    ({"provider": "openai", "name": "m", "base_url": "127.0.0.1:8080"},
     "base_url is an address starting http:// or https://."),
])
def test_a_save_the_file_can_t_take_is_refused_and_writes_nothing(local, fields, said, examined):
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")
    status, page = _post(f"{base}/explain/setup", {"action": "save", "key": "", **fields})
    examined(1, "refused save")
    assert status == 400 and said in unescape(page), page[-1500:]
    assert config.read_text(encoding="utf-8") == KEPT


def test_a_write_that_fails_leaves_the_file_as_it_was_and_no_stray_file(local, monkeypatch, examined):
    import os
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")

    real = os.replace

    def refused(src, dst, *a, **k):
        #: Only the configuration's own replace fails; the console's access log is written as ever.
        if Path(dst) == config:
            raise PermissionError(13, "Permission denied")
        return real(src, dst, *a, **k)
    monkeypatch.setattr(os, "replace", refused)
    status, page = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "new",
                                                   "base_url": "", "key": ""})
    examined(1, "failed write")
    assert status == 400 and "Not saved" in unescape(page), page[-1500:]
    assert config.read_text(encoding="utf-8") == KEPT
    assert sorted(p.name for p in config.parent.iterdir()) == [config.name]


def test_with_a_key_the_file_says_keyring_and_no_key_env_and_the_answer_shows_the_lines_never_the_key(
        local, keychain, examined):
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")
    status, page = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "a-model",
                                                   "base_url": "", "key": KEY})
    written = config.read_text(encoding="utf-8")
    examined(1, "save with a key")
    assert status == 200, page[-1500:]
    got = tomllib.loads(written)["model"]
    assert got["key_source"] == "keyring" and "key_env" not in got
    assert KEY not in written and KEY not in page
    import keyring
    assert keyring.get_password("onetrace-explain", "anthropic:default") == KEY
    shown = re.search(r'<pre data-setup="written"><code>(.*?)</code></pre>', page, re.S)
    assert shown, page[-2000:]
    assert unescape(shown.group(1)) == ('[model]\nprovider = "anthropic"\nname = "a-model"\nkey_source = "keyring"\n')


def test_the_next_send_uses_what_was_saved_with_no_restart(local, explain03_installed, model, examined):
    from onetrace_console import explain
    base, _, store, comparison, config = local
    model.text = (REPLIES / "mixed.json").read_text(encoding="utf-8")
    status, page = _post(f"{base}/explain/setup", {"action": "save", "provider": "openai", "name": "stub-model",
                                                   "base_url": model.base_url, "key": KEY})
    assert status == 200, page[-1500:]
    explain.explain(store.get_comparison(comparison.key), store, send=True)
    examined(len(model.requests), "requests the model server was sent")
    assert len(model.requests) == 1, tried(store, comparison)
    sent = model.requests[0]
    assert json.loads(sent["body"])["model"] == "stub-model"
    assert sent["headers"].get("Authorization") == f"Bearer {KEY}"
    assert KEY.encode() not in sent["body"]


# ------------------------------------------------------------------ nowhere else

def test_a_public_console_refuses_the_form_and_writes_nothing(local, monkeypatch, examined):
    """A public console refuses every POST before it reads a byte of the body (`public.REFUSAL`)."""
    from onetrace_console.public import REFUSAL
    from onetrace_console.serve import Handler
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")
    monkeypatch.setattr(Handler, "config", dataclasses.replace(Handler.config, public=True))
    status, said = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "x",
                                                   "base_url": "", "key": ""})
    examined(1, "post to a public console")
    assert status == 403 and REFUSAL in said and config.read_text(encoding="utf-8") == KEPT
    #: Nor does it serve the page that holds the form.
    assert _get(f"{base}/explain/setup")[0] == 404


def test_a_save_without_its_csrf_token_is_refused_and_writes_nothing(local, monkeypatch, examined):
    from onetrace_console.serve import Handler
    base, _, _, _, config = local
    config.write_text(KEPT, encoding="utf-8")
    monkeypatch.setattr(Handler, "_check_action_csrf", lambda self, **k: False)
    status, _ = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "x",
                                                "base_url": "", "key": ""})
    examined(1, "post without its token")
    assert status == 403 and config.read_text(encoding="utf-8") == KEPT


def test_a_static_export_has_no_setup_form(local, tmp_path, examined):
    from onetrace_console.export_static import export
    _, _, store, comparison, _ = local
    dest = tmp_path / "export"
    export(Path(store.root).parent, [comparison.run_a, comparison.run_b], dest)
    pages = list(dest.rglob("*.html"))
    examined(len(pages), "exported pages")
    assert pages and [p.name for p in pages if 'action="/explain/setup"' in p.read_text(encoding="utf-8")
                      or "data-setup-form" in p.read_text(encoding="utf-8")] == []
