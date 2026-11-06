"""Console 0.6.1 item 12: "Include the kept text of outputs that differ".

A checkbox beside Send, off by default and remembered per comparison only, passes onetrace-explain's
`--include-text`. What it adds is onetrace-explain's own: the kept text of each output that differs, text
or JSON, up to 8 KiB each, as items of a kind of their own (`text`), so the first send of text to an
address is asked about as any new kind is. "Show the packet" shows the text before anything goes.
"""
from __future__ import annotations

import json
import re
from html import unescape

from tests.http_limits import limit
from tests.test_explain_panel import _diff, _model, _panel, in_full, pair  # noqa: F401  (pair: a fixture)


def _kinds(attempt: dict) -> list[str]:
    return json.loads(attempt["stdout"].splitlines()[0])["kinds"]


def _items(attempt: dict, kind: str) -> list[dict]:
    return [i for i in json.loads(attempt["stdout"].splitlines()[0])["items"] if i.get("kind") == kind]


def _box(panel: str) -> str:
    got = re.search(r'<p data-explain="text-choice"><label>(.*?)</label></p>', panel, re.S)
    assert got, "no text checkbox"
    return got.group(1)


def test_off_by_default_and_off_sends_no_text(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    got = explain.prepare(comparison, store)
    assert "text" not in _kinds(got) and "--include-text" not in got["command"], in_full(got)
    panel = _panel(_diff(store, comparison))
    box = _box(panel)
    assert " checked" not in box and explain.TEXT_CHOICE in unescape(box)
    sent = explain.explain(comparison, store, send=True)
    assert "--include-text" not in sent["command"]


def test_on_the_first_time_asks_with_the_text_kind_and_the_packet_shows_it(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    explain.set_include_text(store, comparison.key, True)
    got = explain.prepare(comparison, store)
    assert got["command"].endswith("--include-text") and "text" in _kinds(got), in_full(got)
    texts = _items(got, "text")
    assert texts and all(len(i["baseline"].encode()) <= 8192 + 64 for i in texts)
    panel = _panel(_diff(store, comparison))
    assert " checked" in _box(panel)
    question = re.search(r'<div data-explain="first-send">(.*?)</div>', panel, re.S).group(1)
    assert ('<li data-kind="text">the kept text of outputs that differ: text and JSON outputs, up to 8 KiB each '
            "(<code>text</code>)</li>") in question
    #: Show the packet shows the text before anything goes.
    shown = explain.packet(comparison, store)
    assert shown["command"].endswith("--include-text") and _items(shown, "text")
    panel = unescape(_panel(_diff(store, comparison)))
    shown_line = re.search(r'<details data-explain="packet">.*?<pre><code>(.*?)</code></pre>', panel, re.S).group(1)
    assert f'"id":"{texts[0]["id"]}"' in shown_line and '"kind":"text"' in shown_line
    sent = explain.explain(comparison, store, send=True)
    assert sent["command"].endswith("--include-text")


def test_on_after_confirming_it_does_not_ask_again_for_that_address(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    explain.set_include_text(store, comparison.key, True)
    kinds = _kinds(explain.packet(comparison, store))
    endpoint = re.search(r'base_url = "([^"]*)"', config.read_text(encoding="utf-8")).group(1)
    #: What onetrace-explain records once a send with the text has gone to that address.
    (config.parent / "explain-sent.json").write_text(json.dumps({endpoint: kinds}), encoding="utf-8")
    explain.prepare(comparison, store)
    panel = _panel(_diff(store, comparison))
    assert 'data-flow="prepared"' in panel and 'data-explain="first-send"' not in panel


def test_the_choice_is_per_comparison_and_a_change_prepares_again(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    explain.prepare(comparison, store)
    assert explain.flow(store, comparison.key)[0] == "first-send"
    explain.set_include_text(store, comparison.key, True)
    #: The prepared packet was made without the text: Ready, to prepare again before anything is sent.
    assert explain.flow(store, comparison.key)[0] == "ready"
    assert not explain.include_text(store, "b" * 64)
    explain.set_include_text(store, comparison.key, False)
    assert not explain.include_text(store, comparison.key)


def test_over_http_the_checkbox_keeps_the_choice(server, pair, monkeypatch):
    import urllib.request
    from onetrace_console import explain
    from onetrace_console.serve import Handler
    store, comparison, config = pair
    base, _root = server
    monkeypatch.setattr(Handler, "store", store)
    for on, want in (("yes", True), ("no", False)):
        req = urllib.request.Request(f"{base}/explain/text?c={comparison.key}&on={on}", data=b"", method="POST")
        r = urllib.request.urlopen(req, timeout=limit(120))
        assert r.status == 200 and explain.include_text(store, comparison.key) is want
