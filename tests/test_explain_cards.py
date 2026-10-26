"""An explanation as 0.3.2 draws it on a local console: its checks, each command once, "Run" only
for those the console runs today and "Copy the command" for every other; its footer, every claim
the post-check read and those it left out, with their reasons a fold away; its record and step
times dimmed under the footer; "Hide the details" folding the chips and the footer, the cards open.

`repeated.json` asks for one check twice and another twice; `mixed.json` keeps three claims and
leaves two out, one reason each.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_explain_panel import _diff, _fake, _panel, pair, tried  # noqa: F401  (pair: a fixture)


def _article(store, comparison) -> str:
    found = re.search(r"<article data-explanation=.*?</article>", _panel(_diff(store, comparison)), re.S)
    return found.group(0) if found else ""


def checks_problems(article: str) -> list[str]:
    """repeated.json's checks: three commands, each once, in the order first asked; Run for the
    two the console runs (by the first index each was asked at), Copy for reproduce, which needs a
    runner one names."""
    rows = re.findall(r'<li data-check="(\d+)"><code>([^<]*)</code> (.*?)</li>', article, re.S)
    out = []
    want = [("0", "onetrace diff a b --text --stage score#1", "run"),
            ("2", "onetrace localize a b --for decide#1", "run"),
            ("3", "onetrace reproduce b score#1 --runner <your runner>", "copy")]
    got = []
    for i, cmd, rest in rows:
        run = re.search(rf'data-explain-post="/explain/check\?c=[0-9a-f]{{64}}&amp;e=[^&]+&amp;i={i}"', rest)
        copy = re.search(r'<button type="button" data-copy="([^"]*)" hidden>Copy the command</button>', rest)
        kind = "run" if run and not copy else "copy" if copy and not run else "?"
        if copy and unescape(copy.group(1)) != unescape(cmd):
            out.append(f"check {i}: Copy copies {copy.group(1)!r}")
        got.append((i, unescape(cmd), kind))
    if [(i, k) for i, _, k in got] != [(i, k) for i, _, k in want] or len({c for _, c, _ in got}) != len(got):
        out.append(f"checks {got}")
    return out


def test_repeated_commands_are_merged_and_only_the_runnable_offer_run(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "repeated.json")
    got = explain.explain(comparison, store)
    article = _article(store, comparison)
    examined(1, "explanation with repeated checks")
    assert got["exit"] == "0" and article, tried(store, comparison)
    assert len(explain.check_lines(explain.explanations(store, comparison.key)[0])) == 5
    assert checks_problems(article) == []


def test_sabotage_the_commands_unmerged_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "repeated.json")
    explain.explain(comparison, store)
    monkeypatch.setattr(explain, "merged_checks", lambda e: list(enumerate(explain.check_lines(e))))
    examined(1, "explanation drawn unmerged")
    assert [p.split(" ")[0] for p in checks_problems(_article(store, comparison))] == ["checks"]


def footer_problems(article: str) -> list[str]:
    """mixed.json's footer: 5 claims checked, 2 left out, each reason a fold away, with the check it
    left out; then the record and its verify line, and the step times, under it."""
    out = []
    foot = re.search(r'<div class="ex-foot" data-explain="footer">(.*?)<div class="meta">(.*?)</div></div>', article, re.S)
    if foot is None:
        return ["no footer"]
    fold = re.search(r'<details data-explain="left-out"><summary>(.*?)</summary><ul class="plain">(.*?)</ul></details>',
                     foot.group(1), re.S)
    if fold is None or unescape(fold.group(1)) != "5 claims checked against the record · 2 left out":
        out.append(f"the footer line {fold and fold.group(1)!r}")
    elif sorted(unescape(r) for r in re.findall(r"<li>(.*?)</li>", fold.group(2))) != [
            "1 cites an item the packet doesn't hold", "1 says what caused a difference",
            "checks: 1 names a setting the packet doesn't hold"]:
        out.append("the reasons left out are not under it")
    meta = foot.group(2)
    if 'data-explain="record"' not in meta or "data-verified" not in meta or 'data-explain="steps"' not in meta:
        out.append("the record, its verify line or the step times are not under the footer")
    return out


def test_the_footer_counts_what_was_checked_and_left_out_and_the_record_is_under_it(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    examined(1, "explanation's footer")
    assert footer_problems(_article(store, comparison)) == [], tried(store, comparison)


def test_sabotage_the_footer_counting_kept_claims_only_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    monkeypatch.setattr(explain, "_dropped", lambda e: 0)
    examined(1, "footer, left-out claims not counted")
    assert [p.split(" ")[0:3] for p in footer_problems(_article(store, comparison))] == [["the", "footer", "line"]]


def toggle_problems(article: str, css: str) -> list[str]:
    """"Hide the details": a disclosure, open, before the cards; closed, the stylesheet hides the
    chips and the footer, and the cards stay. Its words follow its state."""
    out = []
    toggle = re.search(r'<details class="ex-more" open data-explain="toggle"><summary><span class="when-open">'
                       r'Hide the details</span><span class="when-closed">Show the details</span></summary></details>',
                       article)
    if toggle is None or article.index(toggle.group(0)) > article.find('data-explain="claims"'):
        out.append("no open toggle before the cards")
    for rule in (".cp .explain details.ex-more:not([open])~.cards [data-cites]",
                 ".cp .explain details.ex-more:not([open])~.ex-foot{display:none}",
                 ".cp .explain details.ex-more[open] .when-closed,.cp .explain details.ex-more:not([open]) .when-open"
                 "{display:none}"):
        if rule not in css:
            out.append(f"the stylesheet lacks {rule[:50]!r}")
    if re.search(r"ex-more:not\(\[open\]\)~\.cards\s*\{", css):
        out.append("the cards themselves are hidden")
    return out


def test_hide_the_details_folds_the_chips_and_the_footer_and_leaves_the_cards(pair, examined):
    from onetrace_console import explain
    from onetrace_console.frame import stylesheet
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    examined(1, "explanation's toggle")
    assert toggle_problems(_article(store, comparison), stylesheet().decode("utf-8")) == []


def test_sabotage_the_toggle_closed_by_default_is_named(pair, examined):
    from onetrace_console import explain
    from onetrace_console.frame import stylesheet
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    examined(1, "planted toggle")
    planted = _article(store, comparison).replace('class="ex-more" open', 'class="ex-more"')
    assert toggle_problems(planted, stylesheet().decode("utf-8")) == ["no open toggle before the cards"]
