"""Each run "Other runs that recorded the same value" lists is a link, with its pair beside it.

Each listed run's name links to its page ("What changed"); beside it, "compare" names the pair of
this page's baseline and that run, as the runs list names a chosen pair: the comparison where this
console holds it, otherwise the baseline's "Choose run B" page at that run's row -- nothing is
compared when the panel is drawn. The candidate is listed first, marked "this comparison", with no
"compare". The matching rule, the count and "Nothing here says what the change did in those runs"
are as before. Held with the demo's P1 pair (settings matched), three P7 runs recorded here (an
input matched), one of them named with characters that need escaping, and a static export.
"""
from __future__ import annotations

import re
from html import escape, unescape

from tests.test_compare_page import _page, demo  # noqa: F401
from tests.test_recorded_input_first import _three_p7_runs
from tests.test_times_and_words import _console

P1 = ("p1-02-baseline-set2", "p1-08-candidate-set2")
ODD = 'cc-<b>&"x'


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _panel(page: str) -> str:
    return re.search(r'<section data-section="same-change">.*?</section>', page, re.S).group(0)


def link_problems(page: str, store, base_key: str, cand_key: str) -> list[str]:
    """Every listed run linked to its page; each but the candidate with a compare link naming the
    pair (baseline, that run); the candidate marked and with none."""
    from onetrace_console.choose_pages import b_anchor
    held = {c.key: (c.run_a, c.run_b) for c in store.comparisons()}
    out = []
    items = re.findall(r'<li data-run="([0-9a-f]{64})"([^>]*)>(.*?)</li>', _panel(page), re.S)
    if not items:
        return ["no run listed"]
    for key, attrs, body in items:
        if f'href="/runs/{key}/case.html"' not in body:
            out.append(f"{key[:12]}: no link to its page")
        compare = re.findall(r'<a href="([^"]+)" data-link="compare">compare</a>', body)
        if key == cand_key:
            if "data-this-comparison" not in attrs or "this comparison" not in _text(body) or compare:
                out.append("the candidate is not marked, or has a compare link")
            continue
        if len(compare) != 1:
            out.append(f"{key[:12]}: {len(compare)} compare links")
            continue
        href = unescape(compare[0])
        m = re.fullmatch(r"/diff/([0-9a-f]{64})\.html", href)
        if m:
            if held.get(m.group(1)) != (base_key, key):
                out.append(f"{key[:12]}: compare opens another pair")
        elif not (href.endswith(f"-{base_key}.html#{b_anchor(key)}") and href.startswith("/choose-")):
            out.append(f"{key[:12]}: compare names {href}")
    if items[0][0] != cand_key:
        out.append("the candidate is not listed first")
    for words in ("Matching rule:", "Nothing here says what the change did in those runs."):
        if words not in _text(_panel(page)):
            out.append(f"lost: {words}")
    return out


def test_the_p1_pair_links_each_run_and_its_pair(demo, examined):  # noqa: F811
    _folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    page = _page(demo, *P1)
    examined(1, "comparison page")
    assert len(re.findall(r"<li data-run=", _panel(page))) >= 2
    assert link_problems(page, store, ids[P1[0]], ids[P1[1]]) == []


def test_an_input_match_links_each_run_and_a_name_is_escaped(tmp_path, examined):
    from onetrace_console.demo_store import cold_chain
    runs = _three_p7_runs(tmp_path)
    cold_chain.main(runs / "d", ODD, True)
    store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    page = (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")
    ids = {r.run_id: r.key for r in store.runs()}
    examined(1, "comparison page")
    assert link_problems(page, store, ids["cc-a"], ids["cc-b"]) == []
    panel = _panel(page)
    assert escape(ODD) in panel and ODD not in panel
    assert all(ODD not in unescape(h) for h in re.findall(r'href="([^"]*)"', panel))
    assert f'/runs/{ids[ODD]}/case.html' in panel


def test_the_links_resolve_in_a_static_export(demo, tmp_path, examined):  # noqa: F811
    from onetrace_console.export_static import export, external_requests
    from onetrace_console.overview import pipelines
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    p1 = next(p for p in pipelines(store) if ids[P1[0]] in {r.key for r in p.runs})
    out = tmp_path / "export"
    export(folder / "store", [r.key for r in p1.runs], out)
    pair = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (ids[P1[0]], ids[P1[1]]))
    page_path = out / "diff" / f"{pair.key}.html"
    hrefs = re.findall(r'href="([^"]+)"', _panel(page_path.read_text(encoding="utf-8")))
    examined(len(hrefs), "links")
    assert hrefs
    for href in hrefs:
        path, _, anchor = unescape(href).partition("#")
        target = (page_path.parent / path).resolve() if path else page_path
        assert target.is_file(), href
        if anchor:
            assert f'id="{anchor}"' in target.read_text(encoding="utf-8"), href
    assert external_requests(out) == []


def test_sabotage_each_fault_is_named(demo, examined):  # noqa: F811
    _folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    page = _page(demo, *P1)
    base, cand = ids[P1[0]], ids[P1[1]]
    planted = {
        "a plain name": re.sub(r'<a href="/runs/[0-9a-f]{64}/case.html">', "<a>", page, count=2),
        "no compare": page.replace('data-link="compare">compare</a>', "></a>", 1),
        "the candidate unmarked": page.replace(" data-this-comparison", "", 1),
        "another pair": re.sub(r'(data-link="compare")', r'\1', page.replace(f"-{base}.html#", "-x.html#", 1))
        if f"-{base}.html#" in page else page.replace('<a href="/diff/', '<a href="/diff/0', 1),
    }
    examined(len(planted), "planted pages")
    for name, bad in planted.items():
        assert link_problems(bad, store, base, cand), name


# ------------------------------------------------------------------ the rule line reads as one sentence

def rule_period_problems(page: str) -> list[str]:
    """The matching rule's line, where its value is a digest: the closing period in the same text
    node as the value shown (the fold's summary), and nothing drawn after the fold. A closed fold
    is a box of its own in the browser, so a period after it starts a line of its own."""
    rule = re.search(r'<div>Matching rule:(.*?)</div>', _panel(page), re.S)
    if rule is None:
        return ["no rule line"]
    fold = re.search(r'<details class="fingerprint"[^>]*><summary class="mono">([^<]*)</summary>.*?</details>(.*)$',
                     rule.group(1), re.S)
    if fold is None:
        return ["the value is not a digest"]
    out = []
    if not re.fullmatch(r"sha256:[0-9a-f]+….", fold.group(1)):
        out.append(f"the period is not with the value: {fold.group(1)!r}")
    if fold.group(2).strip():
        out.append(f"drawn after the value: {fold.group(2)!r}")
    return out


def test_an_input_match_s_rule_line_keeps_its_period_with_the_value(tmp_path, examined):
    runs = _three_p7_runs(tmp_path)
    _store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    page = (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")
    examined(1, "comparison page")
    assert rule_period_problems(page) == []
    assert re.search(r"Matching rule: the same input \S+ digest at .+, by exact equality: sha256:[0-9a-f]+…\.",
                     _text(_panel(page))), "the rule's words changed"


def test_sabotage_the_period_after_the_fold_is_named(tmp_path, examined):
    runs = _three_p7_runs(tmp_path)
    _store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    page = (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")
    old = re.sub(r"(<summary class=\"mono\">sha256:[0-9a-f]+…)\.(</summary>.*?</details>)", r"\1\2.", page, count=1, flags=re.S)
    examined(1, "planted page")
    assert old != page
    assert rule_period_problems(old)
