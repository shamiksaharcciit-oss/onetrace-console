"""The app's spans at a comparison's differing step: one table per span, one row per attribute.

attribute | baseline | candidate | a column of its own saying "differs": the values line up. The rows that
differ come first, marked; the rows that are the same are folded under "N attributes the same", a
`<details>` that opens from the keyboard (its `<summary>` is a control; the round's rendered check presses
it). The heading in plain words: "At step `<step>`: spans from your app's traces (the files under
traces/)", or the run's own export where that is the source. Facts from the traces only, never a cause.
"""
from __future__ import annotations

import html
import re

import pytest

from onetrace_console import trace_panel


def _span(name, sid, parent, start, end, attrs):
    return {"spanId": sid, "parentSpanId": parent, "name": name, "startTimeUnixNano": str(start),
            "endTimeUnixNano": str(end),
            "attributes": [{"key": k, "value": {"stringValue": v} if isinstance(v, str) else {"intValue": v}}
                           for k, v in attrs.items()]}


def _doc(model: str, tokens: int):
    return {"resourceSpans": [{"scopeSpans": [{"spans": [
        _span("onetrace.stage call", "a" * 16, "", 1_000_000, 9_000_000,
              {"onetrace.stage": "call", "gen_ai.request.model": model, "gen_ai.usage.output_tokens": tokens,
               "gen_ai.system": "example"}),
        _span("http.request", "b" * 16, "a" * 16, 2_000_000, 3_000_000, {"gen_ai.system": "example"}),
    ]}]}]}


def _text(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


@pytest.fixture
def drawn():
    return trace_panel.panel("call", (_doc("model-a", 10), _doc("model-b", 10)), ("given", "given"), ("", ""))


def test_the_heading_is_in_plain_words_and_names_where_the_spans_come_from(drawn, examined):
    examined(1, "panel")
    def heading(page):
        return html.unescape(re.search(r"<h2>.*?</h2>", page, re.S).group(0))
    assert heading(drawn) == "<h2>At step <code>call</code>: spans from your app's traces (the files under traces/)</h2>"
    exported = trace_panel.panel("call", (_doc("m", 1), _doc("m", 1)), ("export", "export"), ("", ""))
    assert heading(exported) == ("<h2>At step <code>call</code>: spans from your app's traces "
                                 "(onetrace export otel of each run)</h2>")


def test_one_row_per_attribute_the_differing_ones_first_and_marked(drawn, examined):
    tables = re.findall(r'<table [^>]*data-trace="spans"[^>]*>.*?</table>', drawn, re.S)
    examined(len(tables), "span tables")
    first = tables[0]
    head = _text(re.search(r"<thead>.*?</thead>", first, re.S).group(0))
    assert head == "attribute baseline candidate"
    rows = re.findall(r"<tr[^>]*>.*?</tr>", re.search(r"<tbody>.*?</tbody>", first, re.S).group(0), re.S)
    assert 'data-differs="yes"' in rows[0] and _text(rows[0]) == "gen_ai.request.model model-a model-b differs"
    assert all('data-differs="yes"' in r for r in rows if "differs" in _text(r))


def test_the_same_rows_are_folded_under_a_count_that_opens_from_the_keyboard(drawn, examined):
    fold = re.search(r"<details data-trace-same><summary>(\d+) attributes the same</summary>(.*?)</details>", drawn, re.S)
    examined(1, "fold")
    assert fold, drawn
    same = re.findall(r"<tr[^>]*>", re.search(r"<tbody>.*?</tbody>", fold.group(2), re.S).group(0))
    assert int(fold.group(1)) == len(same) and same and not any("data-differs" in t for t in same)
    assert "gen_ai.usage.output_tokens" in fold.group(2) and "gen_ai.request.model" not in fold.group(2)


@pytest.mark.parametrize("word", ["caused", "because", "why"])
def test_no_line_says_what_produced_the_difference(word, examined):
    said = [v for k, v in vars(trace_panel).items() if k.isupper() and isinstance(v, str)]
    examined(len(said), "lines")
    assert not any(re.search(rf"\b{word}\b", s, re.I) for s in said)


def test_the_differing_rows_are_tinted_by_the_page_s_stylesheet(examined):
    from onetrace_console.frame import PAGE_CSS
    rules = {k.strip(): v for k, v in re.findall(r"([^{}]+)\{([^{}]*)\}", PAGE_CSS)}
    examined(1, "rule")
    assert "background:var(--hl)" in rules[".cp .trace-panel tr[data-differs]>*"]


def test_each_value_is_labelled_by_its_own_column_where_the_rows_stack(drawn, examined):
    """At a narrow width the console stacks a table's cells, each under its column's label: every cell is a
    `td`, each table in its own region, so the baseline's value is labelled baseline, in the fold too."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", "".join(re.findall(r"<tbody>.*?</tbody>", drawn, re.S)), re.S)
    examined(len(rows), "rows")
    for row in rows:
        assert re.findall(r'<td data-label="([^"]*)"', row)[:3] == ["attribute", "baseline", "candidate"], row
