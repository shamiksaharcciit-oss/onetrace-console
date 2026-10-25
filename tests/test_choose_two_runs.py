"""Choose two runs from a pipeline's runs.

A page per pipeline lists its runs, newest first, each choosing itself as run A. Run A's page lists
the pipeline's other runs as run B: a link to the comparison this console holds of the pair, or
"Not compared yet" with the request that makes it, `POST /compare?a=<run A>&b=<run B>`, both keys
the store's own, escaped, as plain text, and on a local console a Compare button that sends that
request. No page carries a form or an input, its only buttons are those, and no GET makes a
comparison. A public console lists only the pairs it holds, has no button, and says so.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from onetrace_console.choose_pages import choose_href, compare_request, pair_href
from tests.test_home_and_diff import GENERATED_AT, _fake_run, diverging  # noqa: F401

#: A run name a page must never let through as markup.
HOSTILE = '<script>alert("x")</script> & "quoted" \'name\''


def _pages(store, *, public: bool = False) -> dict[str, str]:
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_all
    with rendering(onedoor=False, sign_in=True, public=public):
        return render_all(store, generated_at=GENERATED_AT)


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


@pytest.fixture
def three(diverging):  # noqa: F811
    """The pair compared (A the baseline, B the candidate), and a third run of the same pipeline
    under a hostile name, compared with neither."""
    comparison, store = diverging
    b = store.get_run(comparison.run_b)
    hostile = _fake_run(store, b, run_id=HOSTILE, verdict=b.check_verdict)
    return comparison, store, hostile


def pair_problems(page: str, a_key: str, held: dict, others: set[str]) -> list[str]:
    """What is wrong with run A's page: each other run listed once; a held pair linking its
    comparison; any other pair saying "Not compared yet" with the request, whose keys are the
    store's own for exactly this pair."""
    out = []
    rows = re.findall(r'<tr data-run="([0-9a-f]{64})" data-pair="([a-z-]+)">(.*?)</tr>', page, re.S)
    listed = [k for k, _, _ in rows]
    if sorted(listed) != sorted(others):
        out.append(f"lists {len(listed)} runs as run B, not the {len(others)} others")
    for b_key, state, cells in rows:
        c = held.get((a_key, b_key))
        if c is not None:
            if state != "compared" or f'href="diff/{c.key}.html"' not in cells:
                out.append(f"{b_key[:12]}: a held pair not linked to its comparison")
            continue
        commands = re.findall(r"<code[^>]*data-command>(.*?)</code>", cells, re.S)
        if state != "not-compared" or "Not compared yet." not in _text(cells):
            out.append(f"{b_key[:12]}: not said to be not compared yet")
        if [unescape(c) for c in commands] != [compare_request(a_key, b_key)]:
            out.append(f"{b_key[:12]}: the request is {commands!r}")
    return out


def _held(store) -> dict:
    from onetrace_console.choose_pages import held_comparisons
    return held_comparisons(store)


def test_a_pipelines_page_lists_its_runs_newest_first_each_choosing_itself(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order
    (p,) = pipelines(store)
    page = _pages(store)[choose_href(p.label)]
    examined(len(p.runs), "runs on the pipeline's page")
    keys = re.findall(r'<tr data-run="([0-9a-f]{64})">', page)
    assert keys == [r.key for r in arrival_order(p.runs, newest_first=True)]
    for k in keys:
        assert f'href="{pair_href(p.label, k)}"' in page


def test_run_a_lists_every_other_run_once_with_its_comparison_or_the_request(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    pages, held = _pages(store), _held(store)
    examined(len(p.runs), "run A pages")
    for a in p.runs:
        page = pages[pair_href(p.label, a.key)]
        assert pair_problems(page, a.key, held, {r.key for r in p.runs} - {a.key}) == [], a.run_id
    #: The one pair held links to it, in its direction only; its reverse is not compared yet.
    page_a = pages[pair_href(p.label, comparison.run_a)]
    assert f'href="diff/{comparison.key}.html"' in page_a
    page_b = pages[pair_href(p.label, comparison.run_b)]
    assert compare_request(comparison.run_b, comparison.run_a) in unescape(page_b)


def test_the_request_carries_the_stores_keys_and_a_hostile_name_stays_text(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    pages = _pages(store)
    page = pages[pair_href(p.label, comparison.run_a)]
    examined(1, "run A page with a hostile run name as run B")
    assert f"POST /compare?a={comparison.run_a}&amp;b={hostile.key}" in page, "escaped, keys whole"
    #: The console's own scripts, each named in the policy by its hash, are the page's only ones.
    from onetrace_console.compare_script import COMPARE_SCRIPT
    from onetrace_console.public import inline_scripts
    rest = page
    for script in inline_scripts() + (COMPARE_SCRIPT,):
        rest = rest.replace(script, "")
    assert "<script>" not in rest and HOSTILE not in page
    for name, html in pages.items():
        if name.startswith("choose-"):
            assert "<script>alert" not in html, name


def test_sabotage_a_request_with_a_wrong_key_is_named(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    page = _pages(store)[pair_href(p.label, comparison.run_a)]
    others = {r.key for r in p.runs} - {comparison.run_a}
    examined(2, "sabotaged pages")
    swapped = page.replace(f"a={comparison.run_a}&amp;b={hostile.key}",
                           f"a={hostile.key}&amp;b={comparison.run_a}")
    assert swapped != page
    assert any("the request is" in x for x in pair_problems(swapped, comparison.run_a, _held(store), others))
    unlinked = page.replace(f'href="diff/{comparison.key}.html"', 'href="comparisons.html"')
    assert any("not linked" in x for x in pair_problems(unlinked, comparison.run_a, _held(store), others))


COMPARE_BUTTON = re.compile(r'<button type="button" hidden data-compare-post="/compare\?a=([0-9a-f]{64})&amp;b=([0-9a-f]{64})">Compare</button>')


def test_no_page_carries_a_form_or_an_input_and_its_only_button_is_compare(three, examined):
    comparison, store, hostile = three
    pages = {k: v for k, v in _pages(store).items() if k.startswith("choose-")}
    examined(len(pages), "choose pages")
    for name, html in pages.items():
        for tag in ("<form", "<input", "<select", "<textarea", "onclick", "clipboard"):
            assert tag not in html.lower(), (name, tag)
        #: Every button is a Compare button for one pair not compared yet, the pair its row shows.
        assert html.count("<button") == len(COMPARE_BUTTON.findall(html)), name
        for a, b in COMPARE_BUTTON.findall(html):
            assert f"POST /compare?a={a}&amp;b={b}</code>" in html, name


def test_a_compare_button_is_offered_only_for_a_pair_not_compared_and_carries_its_script(three, examined):
    comparison, store, hostile = three
    from onetrace_console.compare_script import COMPARE_SCRIPT
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    page = _pages(store)[pair_href(p.label, comparison.run_a)]
    examined(2, "rows")
    rows = {state: cells for _, state, cells in
            re.findall(r'<tr data-run="([0-9a-f]{64})" data-pair="([a-z-]+)">(.*?)</tr>', page, re.S)}
    assert "<button" not in rows["compared"] and "<button" in rows["not-compared"]
    assert page.count(COMPARE_SCRIPT) == 1


def test_sabotage_a_button_without_its_request_is_named(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    page = _pages(store)[pair_href(p.label, comparison.run_a)]
    examined(1, "sabotaged page")
    broken = re.sub(r"<code class=\"mono\" data-command>[^<]*</code>", "", page)
    (a, b), *_ = COMPARE_BUTTON.findall(broken)
    assert f"POST /compare?a={a}&amp;b={b}</code>" not in broken


def test_a_public_console_carries_no_compare_button_or_script(three, examined):
    comparison, store, hostile = three
    from onetrace_console.compare_script import COMPARE_SCRIPT
    pages = {k: v for k, v in _pages(store, public=True).items() if k.startswith("choose-")}
    examined(len(pages), "public choose pages")
    for name, html in pages.items():
        assert "<button" not in html and COMPARE_SCRIPT not in html, name


def test_a_public_console_lists_only_the_pairs_it_holds_and_says_so(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    pages = _pages(store, public=True)
    examined(len(p.runs), "public run A pages")
    a_page = pages[pair_href(p.label, comparison.run_a)]
    assert re.findall(r'data-pair="([a-z-]+)"', a_page) == ["compared"]
    assert "This public console makes no comparison, so it lists only the pairs it holds: 1 of the 2" in _text(a_page)
    for r in p.runs:
        page = pages[pair_href(p.label, r.key)]
        assert "data-command" not in page and "POST /compare" not in page, r.run_id


def test_the_role_table_serves_them_to_a_viewer_and_nothing_else_like_them(examined):
    from onetrace_console import roles
    examined(4, "paths")
    assert roles.required_role("GET", "/choose-p1.html") == roles.VIEWER
    assert roles.required_role("GET", "/" + pair_href("P12", "ab" * 32)) == roles.VIEWER
    for bad in ("/choose-p1-../home.html", "/choose-px.html"):
        with pytest.raises(roles.NoRouteTableEntry):
            roles.required_role("GET", bad)


def test_the_comparisons_page_opens_each_pipelines_page(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    from onetrace_console.render import COMPARISONS
    pages = _pages(store)
    examined(len(pipelines(store)), "pipelines")
    for p in pipelines(store):
        assert f'href="{choose_href(p.label)}"' in pages[COMPARISONS]
        assert choose_href(p.label) in pages


# ------------------------------------------------------------------ the cap on run B's list

def cap_problems(page: str, a_key: str, held: dict, others_newest_first: list[str], cap: int) -> list[str]:
    """Run B's list under the console's list cap: every pair this console holds a comparison of,
    always, first; then the newest of the rest up to the cap; then "…and N more." for those left."""
    out = []
    rows = re.findall(r'<tr data-run="([0-9a-f]{64})" data-pair="([a-z-]+)">', page)
    compared = [k for k in others_newest_first if (a_key, k) in held]
    rest = [k for k in others_newest_first if (a_key, k) not in held]
    want = compared + rest[:cap]
    if [k for k, _ in rows] != want:
        out.append(f"lists {len(rows)} runs as run B, not the {len(compared)} compared then the "
                   f"newest {min(cap, len(rest))} of the rest")
    more = len(rest) - cap
    said = re.findall(r'data-section="more">([^<]*)<', page)
    if more > 0 and said != [f"…and {more} more."]:
        out.append(f"the {more} left are said as {said!r}")
    if more <= 0 and said:
        out.append(f"says {said!r} with nothing left")
    return out


@pytest.fixture
def many(three, monkeypatch):
    """The three runs and a dozen more of the same pipeline, under a cap of 5."""
    import onetrace_console.choose_pages as choose
    comparison, store, hostile = three
    b = store.get_run(comparison.run_b)
    for i in range(12):
        _fake_run(store, b, run_id=f"more-{i:02d}", verdict=b.check_verdict)
    monkeypatch.setattr(choose, "LIST_CAP", 5)
    return comparison, store


def _others(store, a_key) -> list[str]:
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order
    (p,) = pipelines(store)
    return [r.key for r in arrival_order(p.runs, newest_first=True) if r.key != a_key]


def test_run_bs_list_keeps_every_compared_pair_and_caps_the_rest(many, examined):
    comparison, store = many
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    pages, held = _pages(store), _held(store)
    examined(len(p.runs), "run A pages under the cap")
    for a in p.runs:
        page = pages[pair_href(p.label, a.key)]
        assert cap_problems(page, a.key, held, _others(store, a.key), 5) == [], a.run_id
    #: The compared pair is listed even though, by arrival, it is not among the newest five.
    a_page = pages[pair_href(p.label, comparison.run_a)]
    assert f'data-run="{comparison.run_b}" data-pair="compared"' in a_page


def test_sabotage_a_cap_that_drops_a_compared_pair_or_the_count_is_named(many, examined):
    comparison, store = many
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    page = _pages(store)[pair_href(p.label, comparison.run_a)]
    others, held = _others(store, comparison.run_a), _held(store)
    examined(2, "sabotaged pages")
    dropped = re.sub(rf'<tr data-run="{comparison.run_b}" data-pair="compared">.*?</tr>', "", page, flags=re.S)
    assert dropped != page and cap_problems(dropped, comparison.run_a, held, others, 5)
    uncounted = re.sub(r'<p data-section="more">[^<]*</p>', "", page)
    assert uncounted != page and cap_problems(uncounted, comparison.run_a, held, others, 5)


# ------------------------------------------------------------------ the cap on run A's list

#: The pipeline page's line, so a run past the cap is still reachable: from its own page.
OWN_PAGE = "Any run of {label} can be chosen as run A from its own page."


def pipeline_cap_problems(page: str, label: str, newest_first: list[str], cap: int) -> list[str]:
    """The pipeline page under the cap: the newest runs, at most the cap; "…and N more." for the
    rest; and the line saying any run can be chosen as run A from its own page."""
    out = []
    rows = re.findall(r'<tr data-run="([0-9a-f]{64})">', page)
    if rows != newest_first[:cap]:
        out.append(f"lists {len(rows)} runs, not the newest {min(cap, len(newest_first))}")
    more = len(newest_first) - cap
    said = re.findall(r'data-section="more">([^<]*)<', page)
    if (more > 0 and said != [f"…and {more} more."]) or (more <= 0 and said):
        out.append(f"the runs left are said as {said!r}")
    if OWN_PAGE.format(label=label) not in _text(page):
        out.append("no line saying a run can be chosen as run A from its own page")
    return out


def own_page_problems(case_page: str, label: str, key: str) -> list[str]:
    """A run's own page offers it as run A: a link to its run A page."""
    link = re.search(rf'<a href="(?:\.\./)*{re.escape(pair_href(label, key))}">([^<]*)</a>', case_page)
    return [] if link and link.group(1) == "Choose as run A" else ["the run's page does not offer it as run A"]


def test_the_pipeline_page_lists_the_newest_runs_under_the_cap(many, examined):
    comparison, store = many
    from onetrace_console.overview import pipelines
    from onetrace_console.store import arrival_order
    (p,) = pipelines(store)
    page = _pages(store)[choose_href(p.label)]
    newest = [r.key for r in arrival_order(p.runs, newest_first=True)]
    examined(len(newest), "runs of the pipeline")
    assert pipeline_cap_problems(page, p.label, newest, 5) == []


def test_every_runs_own_page_offers_it_as_run_a(three, examined):
    comparison, store, hostile = three
    from onetrace_console.overview import pipelines
    from onetrace_console.pages import CASE, render_execution
    from onetrace_console.checks import run_and_record
    from tests.test_checks import FIXED_RAN_AT
    #: A page is drawn for a run that was checked: the fixture's two real runs, checked here (its
    #: third run is a stored copy with no record of its own to check).
    checked = [run_and_record(store.get_run(k), store, ran_at=FIXED_RAN_AT)
               for k in (comparison.run_a, comparison.run_b)]
    (p,) = pipelines(store)
    examined(len(checked), "run pages")
    assert len(checked) == 2
    for r in checked:
        case = render_execution(r, store, generated_at=GENERATED_AT).pages[CASE]
        assert own_page_problems(case, p.label, r.key) == [], r.run_id


def test_sabotage_the_run_a_cap_and_the_own_page_link_are_each_named(many, examined):
    comparison, store = many
    from onetrace_console.overview import pipelines
    from onetrace_console.pages import CASE, render_execution
    from onetrace_console.store import arrival_order
    (p,) = pipelines(store)
    page = _pages(store)[choose_href(p.label)]
    newest = [r.key for r in arrival_order(p.runs, newest_first=True)]
    examined(3, "sabotaged pages")
    no_line = page.replace("can be chosen as run A from its own page", "can be chosen")
    assert no_line != page and pipeline_cap_problems(no_line, p.label, newest, 5)
    uncounted = re.sub(r'<p data-section="more">[^<]*</p>', "", page)
    assert uncounted != page and pipeline_cap_problems(uncounted, p.label, newest, 5)
    from onetrace_console.checks import run_and_record
    from tests.test_checks import FIXED_RAN_AT
    run = run_and_record(store.get_run(comparison.run_a), store, ran_at=FIXED_RAN_AT)
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    unlinked = case.replace(pair_href(p.label, run.key), "comparisons.html")
    assert unlinked != case and own_page_problems(unlinked, p.label, run.key)
