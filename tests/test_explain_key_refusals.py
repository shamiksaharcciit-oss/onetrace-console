"""Two things onetrace-explain 0.3.0 refuses or withholds, held for the console's Set up Explain form.

- The form refuses to keep a key that no request can carry, as onetrace-explain 0.3 refuses to send one:
  a line end, another control character, or a character outside ASCII (a zero-width space, a no-break
  space, a curly quote, as a paste can carry). Save and Replace both say so without echoing the key,
  keep nothing in the keychain, and write nothing.
- A stored key never appears in the console's Explain panel, its log, or an attempt record, including
  where the model server echoes it back, in an error and in a 200 reply.

No model is called: the model is a server on 127.0.0.1 (tests/keychain.py), the keychain a folder of the
test's own.
"""
from __future__ import annotations

import json
import re
import tomllib
from html import unescape

import pytest

from tests.keychain import planted_key_searched, KEY, explain03, explain03_installed, keychain, keyring_lib, model  # noqa: F401
from tests.test_explain_panel import REPLIES, pair, tried  # noqa: F401
from tests.test_explain_setup import _get, local  # noqa: F401
from tests.test_explain_setup_form import _post

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

REFUSED = ("the key holds a line end, another control character or a character outside ASCII, which no "
           "request can carry: paste it again without it")
BAD = {"a line end": KEY + "\n", "a carriage return": KEY + "\r\n", "a tab": KEY[:10] + "\t" + KEY[10:],
       "NUL": KEY + "\x00", "DEL": KEY + "\x7f", "a zero-width space": KEY + "​",
       "a no-break space": KEY[:10] + " " + KEY[10:], "a curly quote": "“" + KEY + "”"}


def _entries(folder) -> dict:
    p = folder / "entries.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


@pytest.mark.parametrize("what", sorted(BAD))
def test_save_refuses_a_key_no_request_can_carry_without_echoing_it(local, keychain, what, examined):
    base, _, _, _, config = local
    config.write_text('[model]\nprovider = "anthropic"\nname = "kept"\n', encoding="utf-8")
    before = config.read_text(encoding="utf-8")
    status, page = _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "x",
                                                   "base_url": "", "key": BAD[what]})
    examined(1, f"a key holding {what}")
    assert status == 400 and f"Not saved: {REFUSED}." in unescape(page), page[-1500:]
    assert KEY[:8] not in page.replace("sk-test-", "") and KEY[8:16] not in page
    assert _entries(keychain) == {} and config.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("what", ["a line end", "a zero-width space"])
def test_replace_refuses_it_too_and_keeps_the_key_stored(local, keychain, what, examined):
    import keyring
    base, _, _, _, config = local
    _post(f"{base}/explain/setup", {"action": "save", "provider": "anthropic", "name": "x", "base_url": "",
                                    "key": KEY})
    status, page = _post(f"{base}/explain/setup", {"action": "replace", "key": BAD[what]})
    examined(1, f"a replace holding {what}")
    assert status == 400 and f"Nothing changed: {REFUSED}." in unescape(page), page[-1500:]
    assert KEY[8:16] not in page
    assert keyring.get_password("onetrace-explain", "anthropic:default") == KEY


def _panel(page: str) -> str:
    found = re.search(r'<section data-section="explain"[^>]*>.*?</section>', page, re.S)
    return found.group(0) if found else ""


@pytest.mark.parametrize("answer", ["an error echoing it", "a 200 reply echoing it"])
def test_a_stored_key_is_never_in_the_panel_the_log_or_an_attempt_record(
        local, explain03_installed, model, capfd, answer, examined):
    from onetrace_console import explain
    from onetrace_console.render import render_diff
    base, _, store, comparison, config = local
    if answer == "an error echoing it":
        model.answer, model.status, model.text = "error", 401, json.dumps({"error": f"bad key {KEY}"})
    else:
        model.text = json.dumps({"claims": [{"text": f"your key is `{KEY}`", "kind": "lead", "cites": []}],
                                 "checks": []})
    _post(f"{base}/explain/setup", {"action": "save", "provider": "openai", "name": "stub-model",
                                    "base_url": model.base_url, "key": KEY})
    explain.explain(store.get_comparison(comparison.key), store, send=True)
    panel = _panel(render_diff(store.get_comparison(comparison.key), store, generated_at="2026-11-07T00:00:00+00:00"))
    attempts = explain.attempts(store, comparison.key)
    out, err = capfd.readouterr()
    logs = [p for p in store.root.parent.rglob("*") if p.is_file() and "access_log" in p.name]
    examined(len(attempts) + 1 + len(logs), "attempts, the panel and the console's logs")
    assert len(model.requests) == 1 and attempts, tried(store, comparison)
    assert panel, "no Explain panel drawn"
    runs = {KEY[i:i + 8] for i in range(len(KEY) - 7)} - {"sk-test-"}
    for where, text in [("the panel", panel), ("the console's output", out + err),
                        *[(f"attempt {a['n']}", json.dumps(a)) for a in attempts],
                        *[(str(p.name), p.read_text(encoding="utf-8", errors="replace")) for p in logs]]:
        assert not any(r in text for r in runs), where
    #: onetrace-explain 0.3 says it: an error by its status alone, a reply holding the key not kept.
    said = attempts[-1]["stderr"]
    assert ("HTTPError: 401" in said) if answer == "an error echoing it" else ("the reply was not kept" in said or
                                                                             "was not kept" in said), said
