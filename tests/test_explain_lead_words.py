"""Console 0.6.1 item 9: "Lead: where to look first" for "Lead (possible culprit)".

The badge on a lead names where to look, never a cause: "culprit" is gone from the console's own words.
"Ruled out" and "Note" are kept. onetrace-explain's own terminal labels wait for its 0.3.
"""
from __future__ import annotations

import re
from pathlib import Path

from tests.test_explain_panel import _diff, _fake, _panel, pair  # noqa: F401  (pair: a fixture)


def test_the_kind_words_are_the_ruled_ones():
    from onetrace_console import explain
    assert explain.KIND_WORDS == {"lead": "Lead: where to look first", "ruled out": "Ruled out", "note": "Note"}


def test_a_drawn_lead_reads_where_to_look_first_and_never_culprit(pair):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store, send=True)
    panel = _panel(_diff(store, comparison))
    badges = re.findall(r'<span class="badge" data-kind="lead">([^<]*)</span>', panel)
    assert badges and set(badges) == {"Lead: where to look first"}
    #: The console's own words: the badge and every line it writes around the model's text.
    words = re.sub(r"<p data-claim-text>.*?</p>", "", panel, flags=re.S)
    assert not re.search(r"culprit", words, re.I)


def test_no_console_source_words_a_lead_as_a_culprit():
    src = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
    said = [p.name for p in src.rglob("*.py") if re.search(r'["\'][^"\']*\bculprit', p.read_text(encoding="utf-8"), re.I)]
    assert said == []
