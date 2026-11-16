"""Explain in one press where consent is already given.

Explain prepares the packet, then, in the same press, sends it where nothing in it needs a new consent:
every kind of item in it has been sent to that address before (onetrace-explain's own record), or the
model is on this machine (127.0.0.1, localhost, ::1). It stops before sending, with Show the packet and
"Send to <host>", where a kind is new to that address (a newly ticked "include text" among them), and on
every press where "Always stop before sending" is on. The line says the address as it sends.
"""

from __future__ import annotations

import json
import re
import urllib.request
from html import unescape

import pytest

from tests.http_limits import limit
from tests.test_explain_panel import _diff, _fake, _model, _panel, in_full, pair, toml_string  # noqa: F401  (pair)

REMOTE = "https://api.example.test/v1"


def _remote(config) -> None:
    """A model at an address not on this machine; preparing never reaches it."""
    config.write_text(
        f'[model]\nprovider = "openai"\nname = "a-model"\nbase_url = {toml_string(REMOTE)}\nkey_env = ""\n',
        encoding="utf-8",
    )


def _endpoint(config) -> str:
    return re.search(r'base_url = "([^"]*)"', config.read_text(encoding="utf-8")).group(1)


def _sent_before(config, store, comparison, *, without: tuple[str, ...] = ()) -> None:
    """onetrace-explain's record says every kind of this comparison's packet went to the address before."""
    from onetrace_console import explain

    kinds = json.loads(explain.packet(comparison, store)["stdout"].splitlines()[0])["kinds"]
    kept = [k for k in kinds if k not in without]
    (config.parent / "explain-sent.json").write_text(json.dumps({_endpoint(config): kept}), encoding="utf-8")


def _press(base: str, path: str) -> tuple[int, dict]:
    r = urllib.request.urlopen(urllib.request.Request(base + path, data=b"", method="POST"), timeout=limit(120))
    return r.status, json.loads(r.read())


def _kinds(store, comparison) -> list[str]:
    from onetrace_console import explain

    return [a["kind"] for a in explain.attempts(store, comparison.key) if a["kind"] != "packet"]


@pytest.fixture
def console(server, pair, monkeypatch):
    from onetrace_console.serve import Handler

    store, comparison, config = pair
    base, _root = server
    monkeypatch.setattr(Handler, "store", store)
    return base, store, comparison, config


def _explain(console) -> tuple[int, dict]:
    from onetrace_console import explain

    base, store, comparison, _config = console
    got = _press(base, f"/explain?c={comparison.key}")
    assert explain.wait(comparison.key, timeout=limit(120))
    return got


def test_a_first_send_of_a_kind_stops_after_preparing_and_sends_nothing(console):
    from onetrace_console import explain

    _base, store, comparison, config = console
    _remote(config)
    status, said = _explain(console)
    assert status == 200 and said["exit"] == "0", said
    assert _kinds(store, comparison) == ["prepare"], explain.attempts(store, comparison.key)
    where, info = explain.flow(store, comparison.key)
    assert where == explain.S_FIRST_SEND and info["new"]
    assert not (config.parent / "explain-sent.json").exists()


def test_a_later_send_of_the_same_kinds_is_one_press_and_one_request(console):
    """The fake provider answers from a file: the one press prepares, sends once and reads the reply."""
    from onetrace_console import explain

    _base, store, comparison, config = console
    _fake(config, "mixed.json")
    status, said = _explain(console)
    assert status == 202 and said["started"] is True, said
    assert _kinds(store, comparison) == ["prepare", "send"], [
        in_full(a) for a in explain.attempts(store, comparison.key)
    ]
    assert explain.flow(store, comparison.key)[0] == explain.S_DONE
    assert len(explain.explanations(store, comparison.key)) == 1


def test_with_every_kind_sent_there_before_one_press_sends_and_a_blocked_host_is_one_attempt_said(console, monkeypatch):
    """The address can't be reached (a closed port, read as not on this machine): the one press makes
    exactly one attempt, and the panel says it failed."""
    from onetrace_console import explain

    _base, store, comparison, config = console
    _model(config, "openai:a-model")
    monkeypatch.setattr(explain, "on_this_machine", lambda where: False)
    _sent_before(config, store, comparison)
    status, said = _explain(console)
    assert status == 202 and said["started"] is True, said
    assert _kinds(store, comparison) == ["prepare", "send"]
    sends = [a for a in explain.attempts(store, comparison.key) if a["kind"] == "send"]
    assert len(sends) == 1 and sends[0]["exit"] != "0", in_full(sends[0])
    assert explain.flow(store, comparison.key)[0] == explain.S_FAILED
    assert 'data-flow="failed"' in _panel(_diff(store, comparison))


def test_a_newly_ticked_include_text_stops_before_sending(console, monkeypatch):
    from onetrace_console import explain

    _base, store, comparison, config = console
    _model(config, "openai:a-model")
    monkeypatch.setattr(explain, "on_this_machine", lambda where: False)
    _sent_before(config, store, comparison)
    explain.set_include_text(store, comparison.key, True)
    status, _said = _explain(console)
    where, info = explain.flow(store, comparison.key)
    assert status == 200 and _kinds(store, comparison) == ["prepare"]
    assert where == explain.S_FIRST_SEND and "text" in info["new"]


def test_a_model_on_this_machine_is_one_press_from_the_start(console):
    """Nothing of the comparison was sent to it before; the model's port is closed, so the send fails,
    once."""
    from onetrace_console import explain

    _base, store, comparison, config = console
    _model(config, "openai:a-model")
    assert explain.on_this_machine(_endpoint(config))
    status, said = _explain(console)
    assert status == 202 and said["started"] is True, said
    assert _kinds(store, comparison) == ["prepare", "send"]


@pytest.mark.parametrize("model", ["fake", "this machine"])
def test_always_stop_before_sending_brings_back_the_two_presses(console, model):
    from onetrace_console import explain

    _base, store, comparison, config = console
    _fake(config, "mixed.json") if model == "fake" else _model(config, "openai:a-model")
    explain.set_always_stop(store, True)
    for _ in range(2):
        status, _said = _explain(console)
        assert status == 200 and explain.flow(store, comparison.key)[0] in (explain.S_PREPARED, explain.S_FIRST_SEND)
    assert _kinds(store, comparison) == ["prepare", "prepare"]
    explain.set_always_stop(store, False)
    assert not explain.always_stop(store)


@pytest.mark.parametrize(
    ("base_url", "host"),
    [(REMOTE, "api.example.test"), ("http://127.0.0.1:8080/v1", "127.0.0.1:8080"), ("http://[::1]:9/v1", "::1:9")],
)
def test_the_line_names_the_address_as_it_sends(pair, base_url, host):
    from onetrace_console import explain

    store, comparison, config = pair
    config.write_text(
        f'[model]\nprovider = "openai"\nname = "m"\nbase_url = {toml_string(base_url)}\nkey_env = ""\n',
        encoding="utf-8",
    )
    folder = explain.folder_of(store, comparison.key)
    folder.mkdir(parents=True, exist_ok=True)
    explain._set_state(
        folder,
        {
            "kind": "send",
            "started_at": "2026-11-10T08:00:00+00:00",
            "model": "m",
            "host": explain.host(explain.endpoint(explain.model_config())),
            "step": "preparing",
        },
    )
    assert explain.state(store, comparison.key)["words"] == f"Sending to {host}…"
    assert explain.on_this_machine(base_url) is (host != "api.example.test")


def test_the_panel_says_one_press_where_it_may_send_and_two_where_it_will_stop(pair):
    from onetrace_console import explain

    store, comparison, config = pair
    _remote(config)
    ready = unescape(_panel(_diff(store, comparison)))
    assert explain.READY_LINE in ready and "Nothing is sent until you confirm." in ready
    _model(config, "openai:a-model")
    host = explain.host(_endpoint(config))
    local = unescape(_panel(_diff(store, comparison)))
    assert explain.READY_LOCAL.format(host=host) in local and explain.INTRO_ONE_PRESS_END in local
    explain.set_always_stop(store, True)
    assert explain.READY_LINE in unescape(_panel(_diff(store, comparison)))


def test_the_setup_page_keeps_the_setting_and_the_menu_says_it(console):
    from onetrace_console import explain, settings_menu

    base, store, _comparison, config = console
    _fake(config, "mixed.json")
    page = urllib.request.urlopen(base + "/explain/setup", timeout=limit(30)).read().decode()
    assert 'data-setup-form="always-stop"' in page and explain.ALWAYS_STOP in unescape(page)
    data = b"action=always-stop&always_stop=yes"
    req = urllib.request.Request(base + "/explain/setup", data=data, method="POST")
    said = urllib.request.urlopen(req, timeout=limit(30)).read().decode()
    assert explain.always_stop(store) and explain.ALWAYS_STOP_ON in unescape(said)
    assert settings_menu.explain_row(store).words.endswith(settings_menu.ALWAYS_STOPS)
    req = urllib.request.Request(base + "/explain/setup", data=b"action=always-stop", method="POST")
    said = urllib.request.urlopen(req, timeout=limit(30)).read().decode()
    assert not explain.always_stop(store) and explain.ALWAYS_STOP_OFF in unescape(said)
    assert not settings_menu.explain_row(store).words.endswith(settings_menu.ALWAYS_STOPS)
