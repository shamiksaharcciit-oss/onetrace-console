"""Console 0.6.1 item 6: the Explain panel reads as a flow.

Seven states, each with its one line and only its buttons, and a step line "Prepare → Check → Send →
Read" marking where it is. "Explain" prepares the packet and never sends; "Send", always named with the
address, is the only press that sends; "Cancel" sends nothing and returns to Ready.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from html import unescape

import pytest

from tests.http_limits import limit
from tests.test_explain_panel import _diff, _fake, _model, _panel, in_full, pair  # noqa: F401  (pair: a fixture)


def _buttons(panel: str) -> list[str]:
    row = re.search(r'<p data-explain="buttons">(.*?)</p>', panel, re.S)
    if row is None:
        return []
    return [unescape(t) for t in re.findall(r"<(?:button|a)\b[^>]*>([^<]*)</(?:button|a)>", row.group(1))]


def _flow(panel: str) -> str:
    return re.search(r'data-flow="([^"]+)"', panel).group(1)


def _step(panel: str) -> str | None:
    got = re.search(r'<li data-step="[a-z]+" aria-current="step">([A-Za-z]+)</li>', panel)
    return got.group(1) if got else None


def _port(config) -> str:
    return re.search(r"127\.0\.0\.1:(\d+)", config.read_text(encoding="utf-8")).group(1)


def _sent(config) -> bool:
    return (config.parent / "explain-sent.json").exists()


def _send_problems(panel: str) -> list[str]:
    """Every press that sends names the address it sends to."""
    out = []
    for attrs, words in re.findall(r"<button\b([^>]*)>([^<]*)</button>", panel):
        if "send=yes" in attrs and not re.fullmatch(r"Send to \S.*", unescape(words)):
            out.append(f"a Send button that names no address: {words!r}")
    return out


def test_the_step_line_is_at_the_top_and_says_the_four_steps(pair):
    store, comparison, config = pair
    _model(config, "openai:a-model")
    panel = _panel(_diff(store, comparison))
    line = re.search(r'<ol class="flow" data-explain="flow"[^>]*>(.*?)</ol>', panel, re.S)
    assert line and re.findall(r">([A-Za-z]+)</li>", line.group(1)) == ["Prepare", "Check", "Send", "Read"]
    assert panel.index('data-explain="flow"') < panel.index('data-explain="what"')


def test_not_set_up_says_so_and_offers_only_the_setup(pair):
    from onetrace_console import explain
    store, comparison, _config = pair
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "not-set-up" and _step(panel) is None
    assert explain.NO_MODEL in unescape(panel)
    assert _buttons(panel) == ["Set up Explain"] and "data-explain-post" not in panel


def test_ready_offers_explain_only(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "ready" and _step(panel) == "Prepare"
    assert explain.READY_LINE in unescape(panel)
    assert _buttons(panel) == ["Explain"]


def test_explain_prepares_and_never_sends_then_asks_before_a_first_send(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    got = explain.prepare(comparison, store)
    assert got["exit"] == "0" and got["stdout"].splitlines()[1].endswith("dry run: nothing sent"), in_full(got)
    assert not _sent(config) and explain.explanations(store, comparison.key) == []
    panel = _panel(_diff(store, comparison))
    host = f"127.0.0.1:{_port(config)}"
    assert _flow(panel) == "first-send" and _step(panel) == "Check"
    assert "Before anything is sent" in panel
    assert f"Show the packet sees exactly what goes; Send sends it to {host}." in unescape(panel)
    assert _buttons(panel) == ["Show the packet", f"Send to {host}", "Cancel"]
    assert re.search(r'<button class="primary" [^>]*send=yes[^>]*>Send to ', panel), "Send is the primary button"
    assert _send_problems(panel) == []


def test_prepared_with_nothing_new_is_ready_to_send(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    kinds = json.loads(explain.packet(comparison, store)["stdout"].splitlines()[0])["kinds"]
    endpoint = re.search(r'base_url = "([^"]*)"', config.read_text(encoding="utf-8")).group(1)
    (config.parent / "explain-sent.json").write_text(json.dumps({endpoint: kinds}), encoding="utf-8")
    explain.prepare(comparison, store)
    panel = _panel(_diff(store, comparison))
    host = f"127.0.0.1:{_port(config)}"
    assert _flow(panel) == "prepared" and f"Ready to send to {host}." in unescape(panel)
    assert _buttons(panel) == ["Show the packet", f"Send to {host}", "Cancel"]
    assert _send_problems(panel) == []


def test_cancel_returns_to_ready_and_sends_nothing(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    explain.prepare(comparison, store)
    got = explain.cancel(comparison, store)
    assert got["kind"] == "cancel" and got["command"] == ""
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "ready" and _buttons(panel) == ["Explain"]
    assert not _sent(config) and explain.explanations(store, comparison.key) == []


def test_running_says_where_it_was_sent_and_when_and_offers_nothing(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    folder = explain.folder_of(store, comparison.key)
    folder.mkdir(parents=True, exist_ok=True)
    started = datetime(2026, 11, 5, 14, 2, 5, tzinfo=timezone.utc)
    explain._set_state(folder, {"kind": "send", "started_at": started.isoformat(), "model": "openai:a-model",
                                "host": "api.example.test", "step": "waiting"})
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "running" and _step(panel) == "Send"
    assert re.search(r'<p data-explain="running">Sent to api\.example\.test at 14:02 UTC; waiting for the reply '
                     r"<span data-elapsed>\(\d+ s so far\)</span>\.</p>", panel)
    assert _buttons(panel) == []


def test_done_reads_with_its_time_and_model(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.prepare(comparison, store)
    explain.explain(comparison, store, send=True)
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "done" and _step(panel) == "Read"
    assert re.search(r'<p data-explain="done">Read at \d{4}-\d\d-\d\d \d\d:\d\d UTC, from fake:', panel)
    assert _buttons(panel) == ["Explain again", "Show the packet"]
    assert "<article data-explanation=" in panel


def test_failed_says_what_failed_and_the_fix(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    explain.prepare(comparison, store)
    got = explain.explain(comparison, store, send=True)
    assert got["exit"] == "3", in_full(got)          # nothing listens at the address
    panel = _panel(_diff(store, comparison))
    assert _flow(panel) == "failed" and _step(panel) == "Send"
    assert "The command failed, exit 3:" in unescape(panel) and explain.FAILED_FIX in unescape(panel)
    assert _buttons(panel) == ["Set up Explain", "Try again"]
    #: Try again prepares again: it never sends.
    assert re.search(r'data-explain-post="/explain\?c=[0-9a-f]{64}" hidden>Try again</button>', panel)


def test_no_state_shows_send_without_naming_the_address(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    seen = []
    _model(config, "openai:a-model")
    seen.append(_panel(_diff(store, comparison)))
    explain.prepare(comparison, store)
    seen.append(_panel(_diff(store, comparison)))
    explain.explain(comparison, store, send=True)
    seen.append(_panel(_diff(store, comparison)))
    _fake(config, "mixed.json")
    explain.prepare(comparison, store)
    seen.append(_panel(_diff(store, comparison)))
    explain.explain(comparison, store, send=True)
    seen.append(_panel(_diff(store, comparison)))
    assert [_flow(p) for p in seen] == ["ready", "first-send", "failed", "prepared", "done"]
    for p in seen:
        assert _send_problems(p) == []
        #: Only a Send press sends: the Explain press never carries send=yes.
        assert not re.search(r"send=yes[^>]*>(?!Send to )", p)


def test_sabotage_a_send_button_without_its_address_is_named():
    planted = '<button class="primary" type="button" data-explain-post="/explain?c=k&amp;send=yes" hidden>Send</button>'
    assert _send_problems(planted) == ["a Send button that names no address: 'Send'"]


@pytest.mark.usefixtures("pair")
def test_over_http_explain_prepares_and_cancel_returns_to_ready(server, pair, monkeypatch):
    import urllib.request
    from onetrace_console.serve import Handler
    store, comparison, config = pair
    _model(config, "openai:a-model")
    base, _root = server
    monkeypatch.setattr(Handler, "store", store)

    def post(path):
        r = urllib.request.urlopen(urllib.request.Request(base + path, data=b"", method="POST"), timeout=limit(120))
        return r.status, json.loads(r.read())
    status, said = post(f"/explain?c={comparison.key}")
    assert status == 200 and said["exit"] == "0" and not _sent(config)
    from onetrace_console import explain
    assert explain.flow(store, comparison.key)[0] == "first-send"
    status, said = post(f"/explain/cancel?c={comparison.key}")
    assert status == 200 and explain.flow(store, comparison.key)[0] == "ready"
