"""The short answer at the top of every comparison page: its headline, the line under it and the
stage strip, from the comparison's own report and the two runs' receipts, with no model.

Held on the demo's comparisons as the public build draws them, one for each case the headline has:
a setting named with both values (P1, P8 42->43), only a configuration fingerprint (P5 32->33), an
input (P8 43->44, P9 46->48), only the output with a setting recorded at a later stage (P4 29->30),
graph-shaped pairs whose report names the first difference (P2, P3), runs that agree while a
setting differs (P5 32->34, P9 46->47), and runs that agree with nothing recorded differing (P1
01->13). Where differences begin on a graph whose report names none is held on a planted graph.
"""
from __future__ import annotations

import html
import re

import pytest

#: (baseline, candidate): (headline, the line under it), each name from the record in backticks.
WANT = {
    ("p1-02-baseline-set2", "p1-08-candidate-set2"): (
        "The runs first differ at `split`, where `chunk_size` went from 1024 to 512.",
        "Every stage before it is the same. All 3 stages after it differ."),
    ("p5-32-pump-baseline", "p5-33-pump-offset-changed"): (
        "The runs first differ at `calibrate`, where its configuration changed.",
        "Every stage before it is the same. All 4 stages after it differ."),
    ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"): (
        "The runs first differ at `match`, where `price_tolerance` went from 2.00% to 5.00%.",
        "Every stage before it is the same. The stage after it differs."),
    ("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed"): (
        "The runs first differ at `read_invoice`, where input `invoice` changed.",
        "No stage comes before it. Both stages after it differ."),
    ("p9-46-torque-baseline", "p9-48-torque-one-bolt-low"): (
        "The runs first differ at `read_tool_log`, where input `tool_log.csv` changed.",
        "No stage comes before it. Both stages after it differ."),
    ("p1-01-baseline-set1", "p1-13-baseline-set1-again"): ("The two runs agree.", None),
    ("p4-29-reply-30-days", "p4-30-reply-14-days"): (
        "The runs first differ at `draft`, where its output changed.",
        "Every stage before it is the same. Both stages after it differ. "
        "A recorded setting also changed later: `refund_days` at `policy_check`, `30` → `14`."),
    ("demo-run-1", "demo-run-2"): (
        "The runs first differ at `model`, where `seed` went from 42 to 17.",
        "Same: 4 · differ: 3."),
    ("p3-23-t-1-rules1", "p3-27-t-1-rules2"): (
        "The runs first differ at `classify`, where `rules` went from 1 to 2.",
        "Same: 2 · differ: 3."),
    ("p5-32-pump-baseline", "p5-34-pump-firmware-changed"): (
        "Every recorded output is the same. A setting differs: `sensor_firmware` at `readings`, `3.1` → `3.2`.",
        None),
    ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"): (
        "Every recorded output is the same. A setting differs: `tool_firmware` at `read_tool_log`, `4.2` → `4.3`.",
        None),
}
CHECKED = "Checked from the records. The same answer every time."
#: The stage strip's words, the console's own (`render._RESULT_WORDS`).
WORDS = {"same": "Same", "FIRST DIFFERENCE": "First difference", "downstream": "Changed after it",
         "reconverged": "Same again", "COULD NOT CHECK": "Couldn't check"}


def said(fragment: str) -> str:
    """Words as a reader reads them, each `<code>` name between backticks."""
    fragment = re.sub(r"<code>(.*?)</code>", r"`\1`", fragment, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split()).replace(" .", ".").replace(" ,", ",")


def short(page: str) -> str | None:
    found = re.search(r'<section data-section="short-answer".*?</section>', page, re.S)
    return found.group(0) if found else None


def parts(section: str) -> dict:
    head = re.search(r'<p class="headline" data-short="headline">(.*?)</p>', section, re.S)
    second = re.search(r'<p data-short="second">(.*?)</p>', section, re.S)
    strip = re.findall(r'<li data-verdict="([^"]*)"( data-mark="first")? class="[^"]*">'
                       r'<span class="name">(.*?)</span><span class="word">(.*?)</span></li>', section, re.S)
    return {"headline": said(head.group(1)) if head else None, "second": said(second.group(1)) if second else None,
            "strip": [(html.unescape(n), v, bool(m), html.unescape(w)) for v, m, n, w in strip],
            "checked": CHECKED in html.unescape(section)}


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    store = Store(shared_demo["folder"] / "store" / "store")
    runs = {r.run_id: r for r in store.runs()}
    pages = shared_demo["folder"] / "store" / "pages" / "diff"
    out = {}
    for c in store.comparisons():
        a, b = (next((r.run_id for r in runs.values() if r.key == k), None) for k in (c.run_a, c.run_b))
        out[(a, b)] = (c, (pages / f"{c.key}.html").read_text(encoding="utf-8"))
    return store, out


def report_ladder(store, comparison) -> list[tuple[str, str]]:
    """The diff report's rows, (stage or node, verdict), in the report's order."""
    import json
    rep = json.loads(store.get(dict(comparison.verb("diff").reports)["diff.json"]))
    rows = rep.get("ladder") or (rep.get("dag") or {}).get("ladder") or []
    return [(r.get("node") or r.get("stage"), r["verdict"]) for r in rows]


def answer_problems(store, pages: dict, want: dict) -> list[str]:
    out = []
    for pair, (headline, second) in want.items():
        if pair not in pages:
            out.append(f"{pair}: no such comparison in the demo")
            continue
        comparison, page = pages[pair]
        section = short(page)
        if section is None:
            out.append(f"{pair}: no short answer")
            continue
        got = parts(section)
        if got["headline"] != headline:
            out.append(f"{pair}: headline {got['headline']!r}")
        if got["second"] != second:
            out.append(f"{pair}: second line {got['second']!r}")
        if not got["checked"]:
            out.append(f"{pair}: no line saying it is checked from the records")
    return out


def test_each_case_s_headline_and_second_line_are_the_ruled_words(demo, examined):
    store, pages = demo
    examined(len(WANT), "comparisons, one per case")
    assert answer_problems(store, pages, WANT) == []


def test_sabotage_a_headline_from_the_old_page_is_named(demo, examined):
    """The headline as the page wrote it before the short answer: named, case by case."""
    store, pages = demo
    planted = {**WANT, ("p4-29-reply-30-days", "p4-30-reply-14-days"): (
        "The runs first differ at `draft`, where `refund_days` went from 30 to 14.", WANT[(
            "p4-29-reply-30-days", "p4-30-reply-14-days")][1])}
    examined(1, "planted headline")
    assert answer_problems(store, pages, planted) == [
        "('p4-29-reply-30-days', 'p4-30-reply-14-days'): headline "
        "'The runs first differ at `draft`, where its output changed.'"]


def strip_problems(store, pages: dict) -> list[str]:
    """Every comparison page's strip: one mark per stage, in the report's order (the graph view's
    order on a graph), each in the console's words for its verdict, the first difference marked."""
    out = []
    for pair, (comparison, page) in pages.items():
        section = short(page)
        if section is None:
            out.append(f"{pair}: no short answer")
            continue
        got = parts(section)["strip"]
        rows = report_ladder(store, comparison)
        from onetrace_console.words import shown_name
        if [(n, v) for n, v, _, _ in got] != [(shown_name(n), v) for n, v in rows]:
            out.append(f"{pair}: strip {[(n, v) for n, v, _, _ in got]}")
        if any(w != WORDS[v] for _, v, _, w in got):
            out.append(f"{pair}: a mark's words are not the console's")
        if [m for _, v, m, _ in got] != [v == "FIRST DIFFERENCE" for _, v, _, _ in got]:
            out.append(f"{pair}: the first difference is not the one marked")
    return out


def test_every_comparison_page_opens_with_its_strip_in_order_and_in_words(demo, examined):
    store, pages = demo
    examined(len(pages), "comparison pages")
    assert strip_problems(store, pages) == []


def test_the_short_answer_is_first_and_the_sections_below_keep_their_order(demo, examined):
    """At the top: after the page's heading and the line naming its runs, nothing else before it;
    the sections the page had stay after it in their order."""
    _, pages = demo
    examined(len(pages), "comparison pages")
    for pair, (_, page) in pages.items():
        main = page[page.index('<div class="cp">'):]
        first = re.search(r'<(section|details|table|div) data-section="([^"]+)"', main)
        assert first and first.group(2) == "short-answer", (pair, first and first.group(2))


def test_the_short_answer_is_the_same_every_time(demo, examined):
    """Each comparison drawn again, at another time: its short answer, the same bytes."""
    from onetrace_console.render import render_diff
    store, pages = demo
    examined(len(pages), "comparisons drawn again")
    for pair, (comparison, page) in pages.items():
        again = render_diff(comparison, store, generated_at="2026-01-01T00:00:00+00:00", public=True)
        assert short(page) is not None and short(again) == short(page), pair


# ------------------------------------------------------------------ where differences begin, on a graph

class _Row:
    def __init__(self, node, verdict):
        self.node, self.verdict = node, verdict


def test_differences_begin_at_each_stage_that_differs_while_all_it_reads_from_is_the_same(examined):
    """A planted graph whose report names no first difference: `x` and `y` read only from `in`,
    which is the same; `z` reads from `x`. Differences begin at `x` and `y`."""
    from onetrace_console import short_answer
    ladder = [_Row("in", "same"), _Row("x", "downstream"), _Row("y", "downstream"), _Row("z", "downstream"),
              _Row("w", "same")]
    edges = [{"from": "in", "to": "x"}, {"from": "in", "to": "y"}, {"from": "x", "to": "z"}, {"from": "in", "to": "w"}]
    examined(1, "planted graph")
    assert short_answer.begins(ladder, edges) == ["x", "y"]

    class Report:
        pass
    report = Report()
    report.ladder = ladder
    got = short_answer.for_graph(report, [], edges, lambda s: [], {})
    assert short_answer.text(got.headline) == "Differences begin at 2 stages: `x` and `y`."
    assert short_answer.text(got.second) == "Same: 2 · differ: 3."
    assert [s for s, _, first in got.strip if first] == ["x", "y"]


def test_sabotage_begins_read_without_the_edges_is_named(examined):
    """Every stage that differs counted as a beginning: `z` comes in, and the planted answer is named."""
    from onetrace_console import short_answer
    ladder = [_Row("in", "same"), _Row("x", "downstream"), _Row("z", "downstream")]
    edges = [{"from": "in", "to": "x"}, {"from": "x", "to": "z"}]
    examined(1, "planted graph, read without its edges")
    assert short_answer.begins(ladder, edges) == ["x"]
    assert short_answer.begins(ladder, []) == ["x", "z"]
