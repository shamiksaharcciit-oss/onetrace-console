"""A press counts once, on the server too. Disabling a busy button stops most second presses, not all of them:

- Explain's Send: a second Send of a comparison while its send runs is answered with the run in progress (202, its
  state's address), and starts no second send.
- Compare's start: a second press of the same pair while its comparison is made waits for it and is answered with
  the same comparison; the pair is compared once.
- Remove's confirmation: a second confirm with the page's token, once the key is removed, finds nothing to remove
  and says so, without an error.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from html import unescape

import pytest

from tests.http_limits import limit
from tests.keychain import (
    KEY,
    keychain,  # noqa: F401 - a fixture, requested by name
    keyring_lib,  # noqa: F401 - a fixture, requested by name
    planted_key_searched,  # noqa: F401 - a fixture, requested by name
)
from tests.test_explain_panel import pair  # noqa: F401 - a fixture, requested by `local`
from tests.test_explain_remove_confirm import USER, _asked, _saved
from tests.test_explain_setup import local  # noqa: F401 - a fixture
from tests.test_explain_setup_form import _post

pytestmark = pytest.mark.usefixtures("planted_key_searched")


def _post_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(req, timeout=limit(60)) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def test_a_send_while_its_send_runs_is_answered_with_the_run_in_progress(local, monkeypatch, examined):
    from onetrace_console import explain

    base, _root, _store, comparison, _config = local
    started = []
    monkeypatch.setattr(explain, "command", lambda: "onetrace-explain")
    monkeypatch.setattr(explain, "start", lambda *a, **k: started.append(a))
    lock = explain._lock(comparison.key)
    assert lock.acquire(blocking=False)
    try:
        status, said = _post_json(f"{base}/explain?c={comparison.key}&send=yes")
    finally:
        lock.release()
    examined(1, "a second Send")
    assert status == 202, said
    assert said == {
        "comparison_key": comparison.key,
        "started": False,
        "running": True,
        "state": f"/explain/state?c={comparison.key}",
    }
    assert started == []


def test_a_second_compare_of_a_pair_while_it_is_made_shares_its_answer(local, monkeypatch, examined):
    from onetrace_console import compare as cmp

    base, _root, _store, comparison, _config = local
    real, calls, held = cmp.compare, [], threading.Event()

    def slow(a, b, store, **kw):
        calls.append((a.key, b.key))
        held.wait(30)
        return real(a, b, store, **kw)

    monkeypatch.setattr(cmp, "compare", slow)
    url = f"{base}/compare?a={comparison.run_a}&b={comparison.run_b}"
    answers = []
    first = threading.Thread(target=lambda: answers.append(_post_json(url)))
    first.start()
    while not calls:
        threading.Event().wait(0.05)
    second = threading.Thread(target=lambda: answers.append(_post_json(url)))
    second.start()
    threading.Event().wait(0.5)
    held.set()
    first.join(60)
    second.join(60)
    examined(2, "two presses of one pair")
    assert len(calls) == 1, calls
    assert [s for s, _ in answers] == [200, 200], answers
    assert answers[0][1]["comparison_key"] == answers[1][1]["comparison_key"]


def test_a_second_confirm_finds_nothing_to_remove_and_says_so(local, keychain, examined):
    import keyring

    base, _, _, _, _ = local
    _saved(base)
    _page, token = _asked(base)
    first, _ = _post(f"{base}/explain/setup", {"action": "remove-confirmed", "confirm": token})
    again, page = _post(f"{base}/explain/setup", {"action": "remove-confirmed", "confirm": token})
    examined(2, "two confirms")
    assert first == 200 and keyring.get_password("onetrace-explain", USER) is None
    assert again == 200, page[-600:]
    assert "Nothing to remove: the key was removed already." in unescape(page)
    assert KEY not in page
