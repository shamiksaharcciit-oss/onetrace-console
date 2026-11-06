"""Console 0.6.1 item 10: backticks as code in the reading.

A backtick pair in the model's words renders as inline code, after the panel's escaping, with no other
markup and no links. An unpaired backtick stays a backtick, and a backtick pair around `<script>` shows
the text `<script>` inside code, never markup.
"""
from __future__ import annotations

import json
import re

import pytest

from tests.test_explain_panel import _diff, _fake, _panel, pair  # noqa: F401  (pair: a fixture)


@pytest.mark.parametrize("said, shown", [
    ("the `retrieve` step", "the <code>retrieve</code> step"),
    ("`a` then `b`", "<code>a</code> then <code>b</code>"),
    ("one ` alone", "one ` alone"),
    ("`a` and ` b", "<code>a</code> and ` b"),
    ("an empty `` pair", "an empty `` pair"),
    ("`<script>alert(1)</script>`", "<code>&lt;script&gt;alert(1)&lt;/script&gt;</code>"),
    ("*bold* and [a link](https://example.test) and <b>", "*bold* and [a link](https://example.test) and &lt;b&gt;"),
])
def test_a_pair_is_code_after_the_escaping_and_nothing_else_is_markup(said, shown):
    from onetrace_console import explain
    from onetrace_console.words import escape
    assert explain.inline_code(escape(said)) == shown


def test_the_drawn_reading_shows_its_backticks_as_code(pair, tmp_path):
    """A model's reply with backticks, through onetrace-explain's post-check, drawn by the panel."""
    from onetrace_console import explain
    from tests.test_explain_panel import _model
    store, comparison, config = pair
    reply = tmp_path / "backticks.json"
    reply.write_text(json.dumps({"claims": [
        {"text": "The `load#1` step reads the same on both sides.", "kind": "ruled out", "cites": ["node/load#1"]},
        {"text": "The scorer's recorded settings differ at this step.", "kind": "lead",
         "cites": ["node/score#1/instrument"]}], "checks": []}), encoding="utf-8")
    _model(config, f"fake:{reply}")
    explain.explain(comparison, store, send=True)
    (e,) = explain.explanations(store, comparison.key)
    texts = [c.get("text", "") for c in e.get("claims") or []]
    assert any("`" in t for t in texts), texts
    panel = _panel(_diff(store, comparison))
    drawn = re.findall(r"<p data-claim-text>(.*?)</p>", panel, re.S)
    assert len(drawn) == len(texts)
    assert "The <code>load#1</code> step reads the same on both sides." in drawn
    #: Never a link or other markup inside a claim.
    for d in drawn:
        assert not re.search(r"<(?!/?code>)[a-z/]", d), d
