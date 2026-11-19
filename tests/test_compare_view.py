"""A comparison page leads with the answer: the header, the first difference with what changed there, the steps, the
tabs with Explain beside them, and the runs with near inputs (`compare_view`).

Each state's structure is read off a drawn page:

- the same at every step (the demo's torque firmware pair: every output the same, a recorded setting not);
- the first difference at the first step, in the middle, and at the last step;
- a record that does not verify (the page-text fixtures' forged pair);
- configuration differing;
- no text kept (the same pair, its kept outputs not read);
- L3 kept (the capture store's row-change pair);
- public (the demo as built) and local (the same comparison drawn for a local console), and a static export.

The structure is what the page holds and in what order; the words are the module's own, and every value is read from
the records, so a test says which value it expects from which record.
"""

from __future__ import annotations

import html
import re

import pytest

from onetrace_console import compare_view as cv
from tests.test_deploy_fly_kept import built  # noqa: F401 - the fixture, requested by name


def _text(fragment: str) -> str:
    """The words of a fragment: an inline tag (`code`, `a`, `mark`) joins its words; any other tag is a space."""
    inline = re.sub(r"</?(?:code|a|mark|strong|span)\b[^>]*>", "", fragment)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", inline)).split())


def structure(page: str) -> dict:
    """What a comparison page holds: its top-level parts in order, the header, the first card, What changed here, the
    step cards, the tabs, Explain and the near runs."""
    from onetrace_console import views

    _inner, items = views.parts(page, lambda tag, a: tag == "div" and "cp" in (a.get("class") or "").split())
    head = re.search(r'<div class="compare-head" data-section="(pair|compare-head)">(.*?)</div>', page, re.S)
    first = re.search(r'<div class="compare-first" data-section="compare-first" data-state="(\w+)">', page)
    here = re.search(r'<aside class="changed-here".*?<dl>(.*?)</dl>', page, re.S)
    return {
        "parts": [views.key(p) for p in items],
        "names": head is not None and head.group(1) == "pair",
        "records": tuple(
            map(html.unescape, re.search(r'data-badge="records" data-tone="(\w+)">([^<]*)<', page).groups())
        )
        if head
        else None,
        "config": html.unescape(re.search(r'data-badge="config">([^<]*)<', page).group(1)) if head else None,
        "swap": (re.search(r'data-swap="(\w+)"', page) or [None, None])[1],
        "first": first.group(1) if first else None,
        "step_of": (re.search(r"step (\d+) of (\d+) · checked from the records", page) or [None])[0],
        "headline": _text(m.group(1)) if (m := re.search(r'<h2 data-section="headline">(.*?)</h2>', page)) else None,
        "said": _text(m.group(1)) if (m := re.search(r'data-section="said">(.*?)</p>', page, re.S)) else None,
        "here": dict(
            zip(
                map(_text, re.findall(r"<dt>(.*?)</dt>", here.group(1))),
                map(_text, re.findall(r"<dd>(.*?)</dd>", here.group(1))),
            )
        )
        if here
        else {},
        "cards": re.findall(
            r'<li data-mark="(\w+)"><a href="[^"]*#step-[^"]+"><span class="step-name"><code>([^<]*)</code>', page
        ),
        "tabs": re.findall(r'id="compare-tabbtn-(\w+)" data-tab="\w+"', page),
        "explain": "public"
        if 'data-explain="public"' in page
        else ("panel" if 'data-section="explain-aside"' in page else None),
        "run_here": len(re.findall(r'action="/compare/check" class="run-here"', page)),
        "near": 'data-section="near-runs"' in page,
    }


def _demo_page(shared_demo, a: str, b: str) -> str:
    root = shared_demo["folder"] / "store" / "pages" / "diff"
    for p in sorted(root.glob("*.html")):
        if re.fullmatch(r"[0-9a-f]{64}\.html", p.name):
            page = p.read_text(encoding="utf-8")
            if html.escape(f"Investigate · {a} → {b}", quote=False) in page.split("</title>")[0]:
                return page
    raise AssertionError(f"no comparison {a} → {b} in the demo")


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store

    return shared_demo, Store(shared_demo["folder"] / "store" / "store")


def _comparison(store, a: str, b: str):
    return next(
        c for c in store.comparisons() if (store.get_run(c.run_a).run_id, store.get_run(c.run_b).run_id) == (a, b)
    )


def _local(store, a: str, b: str) -> str:
    """The comparison drawn for a local console."""
    from onetrace_console.render import render_diff

    return render_diff(_comparison(store, a, b), store, generated_at="2026-11-17T00:00:00+00:00", public=False)


# ------------------------------------------------------------------------------------------------- the states


def test_the_same_at_every_step_says_so_and_names_the_settings_that_differ(demo, examined):
    shared, _store = demo
    s = structure(_demo_page(shared, "p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"))
    examined(1, "page")
    assert s["first"] == "same" and s["step_of"] is None and s["headline"] is None
    #: The firmware is a recorded setting that differs: the header and the card say so; no output differs.
    assert s["config"] == "configuration or settings differ at 1 step"
    assert "tool_firmware" in s["said"] and "read_tool_log" in s["said"]
    assert {m for m, _s in s["cards"]} == {"same"} and len(s["cards"]) == 3
    assert "spans" not in s["tabs"] and s["tabs"][0] == "text"


def test_the_first_difference_at_the_first_step(demo, examined):
    shared, _store = demo
    s = structure(_demo_page(shared, "p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed"))
    examined(1, "page")
    assert s["first"] == "first" and s["step_of"] == "step 1 of 3 · checked from the records"
    assert [m for m, _s in s["cards"]][0] == "first"
    #: At the first step the pair's inputs are the step's own: nothing is said of "the same input" before it.
    assert not s["said"].startswith("Both runs took the same input")
    assert s["here"]["Fields changed"] == "quantity"


def test_the_first_difference_in_the_middle(demo, examined):
    shared, _store = demo
    s = structure(_demo_page(shared, "p4-29-reply-30-days", "p4-30-reply-14-days"))
    examined(1, "page")
    assert s["step_of"] == "step 2 of 4 · checked from the records" and s["headline"] == "The runs first part at draft"
    assert s["cards"] == [
        ("same", "question"),
        ("first", "draft"),
        ("downstream", "policy_check"),
        ("downstream", "send"),
    ]
    assert s["said"] == (
        "Both runs took the same input. At draft the outputs differ in reply. Every step after it differs. "
        "The settings recorded at this step are identical."
    )
    assert s["here"] == {
        "Kind of difference": "output",
        "Fields changed": "reply",
        "Settings": "identical",
        "Model identity": "no model call recorded at this step",
        "Size": "190 B → 213 B",
    }
    assert s["config"] == "configuration or settings differ at 1 step", "policy_check's refund_days differs"


def test_the_first_difference_at_the_last_step(demo, examined):
    shared, _store = demo
    s = structure(_demo_page(shared, "pz-51-agent-baseline", "pz-53-agent-amount-changed"))
    examined(1, "page")
    assert s["step_of"] == "step 1 of 1 · checked from the records"
    #: Nothing after it: no sentence about the steps after.
    assert "after it" not in s["said"]


def test_configuration_differing(demo, examined):
    shared, _store = demo
    s = structure(_demo_page(shared, "p1-02-baseline-set2", "p1-08-candidate-set2"))
    examined(1, "page")
    assert s["config"] == "configuration or settings differ at 1 step"
    assert s["records"] == ("ok", "Both records verify")


def test_a_record_that_does_not_verify_keeps_the_steps_off_what_changed(tmp_path_factory, examined):
    from onetrace_console import views
    from tools.visible_text import rendered

    page = rendered(tmp_path_factory.mktemp("compare-view"))["diff[held-a,held-b]"]
    examined(1, "page")
    s = structure(page)
    assert s["records"][0] == "bad" and s["records"][1] == "Run A's record verifies · run B's contradicts itself"
    #: The view split: the step-by-step parts go to Proof, as the comparison page's verdicts always have.
    what, proof = views.split(page, "diff", "k.html", "k-proof.html", "said", "no")
    assert 'data-section="compare-first"' not in what and 'data-section="step-cards"' not in what
    assert 'data-section="pair"' in what and 'data-section="pair"' in proof


def test_no_text_kept_says_not_recorded(demo, monkeypatch, examined):
    _shared, store = demo
    monkeypatch.setattr(cv, "_kept", lambda *a, **k: None)
    s = structure(_local(store, "p4-29-reply-30-days", "p4-30-reply-14-days"))
    examined(1, "page")
    assert s["here"]["Fields changed"] == cv.FIELDS_NOT_KEPT
    assert "At draft the outputs differ by fingerprint; their text was not kept." in s["said"]


def test_l3_kept_has_the_model_rows_tab(tmp_path_factory, examined):
    from onetrace_console.demo_store import captures
    from onetrace_console.folder_load import build_public

    folder = tmp_path_factory.mktemp("captures") / "built"
    build_public(folder, builder=captures)
    page = next(
        p.read_text(encoding="utf-8")
        for p in sorted((folder / "store" / "pages" / "diff").glob("*.html"))
        if re.fullmatch(r"[0-9a-f]{64}\.html", p.name)
        and "pz-61-agent-capture-row-changed" in p.read_text(encoding="utf-8").split("</title>")[0]
    )
    examined(1, "page")
    s = structure(page)
    assert s["tabs"][-1] == "model"
    #: The comparator's own result for this pair's model-call records: their batch context differs, so it could not
    #: compare them, and the page says that rather than "identical".
    assert s["here"]["Model identity"] == "could not compare"


def test_public_and_local(demo, examined):
    shared, store = demo
    public = structure(_demo_page(shared, "p4-29-reply-30-days", "p4-30-reply-14-days"))
    local = structure(_local(store, "p4-29-reply-30-days", "p4-30-reply-14-days"))
    examined(2, "pages")
    #: Public: Explain only says where it runs; nothing runs on the page; Swap asks as Compare does there.
    assert public["explain"] == "public" and public["run_here"] == 0 and public["swap"] == "ask"
    #: Local: Explain's panel, the two checks it runs, Swap with its CSRF slot.
    assert local["explain"] == "panel" and local["run_here"] == 2 and local["swap"] == "ask"
    page = _local(store, "p4-29-reply-30-days", "p4-30-reply-14-days")
    swap = re.search(r'<form method="post" action="/compare" data-swap="ask".*?</form>', page, re.S).group(0)
    assert "data-csrf-slot" in swap
    #: The same new parts, in the same order, on both (the public page is the What changed view, split).
    new = ("pair", "compare-first", "step-cards", "compare-main")
    assert [p for p in public["parts"] if p in new] == [p for p in local["parts"] if p in new] == list(new)
    #: Each step card opens its row: on the split page, on Proof, where the step table is.
    assert re.search(
        r'<li data-mark="first"><a href="[0-9a-f]{64}-proof\.html#step-2">',
        _demo_page(shared, "p4-29-reply-30-days", "p4-30-reply-14-days"),
    )


def test_a_static_export_keeps_no_request(demo, examined):
    from onetrace_console.export_static import without_run_tools

    _shared, store = demo
    page = without_run_tools(_local(store, "p4-29-reply-30-days", "p4-30-reply-14-days"))
    examined(1, "page")
    assert 'data-swap="ask"' not in page and "/compare/check" not in page and 'data-section="near-runs"' not in page


# ------------------------------------------------------------------------------------------------- the parts


def test_swap_opens_the_reverse_comparison_where_it_is_held(demo, monkeypatch, examined):
    _shared, store = demo
    comparison = _comparison(store, "p4-29-reply-30-days", "p4-30-reply-14-days")
    other = _comparison(store, "p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed")
    import onetrace_console.what_changed as wc

    monkeypatch.setattr(wc, "held", lambda s, a, b: other if (a, b) == (comparison.run_b, comparison.run_a) else None)
    examined(1, "swap")
    got = cv.swap(comparison, store, public=True, export=False)
    assert got == f'<a class="btn-secondary" data-swap="held" href="{other.key}.html">Swap runs</a>'


def test_changed_fields_reads_into_objects_by_path(examined):
    examined(3, "pairs")
    assert cv.changed_fields({"a": 1, "t": "x", "s": 0.81}, {"a": 2, "t": "x", "s": 0.81}) == ["a"]
    assert cv.changed_fields({"o": {"p": 1, "q": 2}}, {"o": {"p": 1, "q": 3}}) == ["o.q"]
    assert cv.changed_fields({"a": 1}, {"b": 1}) == ["a", "b"]


def test_sizes_name_up_to_three_outputs_then_sum_them(examined):
    def step(n: int) -> cv.Step:
        outs = [{"name": f"o{i}.json", "bytes": str(100 + i)} for i in range(n)]
        return cv.Step("1", "s", "FIRST DIFFERENCE", "", {"receipt": {"outputs": outs}}, {"receipt": {"outputs": outs}})

    examined(3, "steps")
    assert cv.sizes(step(1))[0] == "100 B → 100 B"
    assert cv.sizes(step(3))[0] == "o0.json 100 B → 100 B · o1.json 101 B → 101 B · o2.json 102 B → 102 B"
    line, rows = cv.sizes(step(5))
    assert line == "5 outputs, 510 B → 510 B" and len(rows) == 5


def test_side_by_side_puts_each_run_s_lines_in_its_column_with_the_sdk_s_spans(examined):
    doc = {
        "shown": True,
        "nodes": [
            {
                "node": "draft",
                "outputs": [
                    {
                        "kind": "text",
                        "name": "draft.json",
                        "hunks": [
                            {
                                "lines": [
                                    {"op": " ", "text": "{", "spans": []},
                                    {"op": "-", "text": '"r": "a"', "spans": [["6", "7"]]},
                                    {"op": "+", "text": '"r": "b"', "spans": [["6", "7"]]},
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }
    got = cv.side_by_side(doc, "draft")
    examined(1, "output")
    a = re.search(r'<div class="diff-col" data-side="baseline">.*?</div>', got, re.S).group(0)
    b = re.search(r'<div class="diff-col" data-side="candidate">.*?</div>', got, re.S).group(0)
    assert '<mark data-side="baseline">a</mark>' in a and '"b"' not in _text(a)
    assert '<mark data-side="candidate">b</mark>' in b and '"a"' not in _text(b)
    assert cv.side_by_side(doc, "other") == ""


def test_the_checks_name_the_first_difference_and_run_only_two_commands(demo, examined):
    _shared, store = demo
    comparison = _comparison(store, "p4-29-reply-30-days", "p4-30-reply-14-days")
    examined(3, "checks")
    assert cv.first_step(comparison, store) == "draft"
    assert cv.check_argv("text", "draft")[3:] == ["diff", "a", "b", "--text", "--stage", "draft"]
    assert cv.check_argv("for", "draft")[3:] == ["localize", "a", "b", "--for", "draft"]
    assert cv.check_argv("reproduce", "draft") is None
    with pytest.raises(ValueError):
        cv.run_check(comparison, store, "rm -rf")


def test_a_kept_check_result_is_drawn_where_the_checks_are(tmp_path, monkeypatch, examined):
    monkeypatch.setattr(
        cv,
        "kept_results",
        lambda store, key: [
            {
                "check": "text",
                "command": "onetrace diff a b",
                "at": "2026-11-17T01:02:03+00:00",
                "exit": "1",
                "output": "line\n",
            }
        ],
    )
    examined(1, "page")
    got = cv.with_results(b"<p>x</p><div data-check-result></div>", None, "k").decode()
    assert "Ran onetrace diff a b at 2026-11-17 01:02:03+00:00: exit 1." in got and '<pre class="term">line' in got
    assert cv.with_results(b"<p>no marker</p>", None, "k") == b"<p>no marker</p>"


# ------------------------------------------------------------------------------------------------- in a browser

BROWSER_PYTHON = __import__("os").environ.get("ONETRACE_BROWSER_PYTHON", "")

KEYS_SCRIPT = r"""
import json, sys
from playwright.sync_api import sync_playwright
html = open(sys.argv[1], encoding="utf-8").read()
out = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.set_content(html)
    state = lambda: page.evaluate('''() => ({
        role: document.querySelector('[data-compare-tabs]').getAttribute('role'),
        selected: [...document.querySelectorAll('[data-compare-tabs] a')].filter(a => a.getAttribute('aria-selected') === 'true').map(a => a.dataset.tab),
        shown: [...document.querySelectorAll('.tab-panel')].filter(p => !p.hidden).map(p => p.dataset.tabPanel),
        focus: document.activeElement.dataset.tab || document.activeElement.dataset.tabPanel || document.activeElement.tagName,
        outline: getComputedStyle(document.activeElement).outlineStyle})''')
    page.focus('#compare-tabbtn-text')
    out["start"] = state()
    for key in ("ArrowRight", "ArrowRight", "End", "Home", "ArrowLeft"):
        page.keyboard.press(key)
        out[key + str(len(out))] = state()
    page.keyboard.press("Home")
    page.keyboard.press("Tab")
    out["tab"] = state()
    b.close()
print(json.dumps(out))
"""


@pytest.mark.browser
@pytest.mark.skipif(
    not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium (the gate sets it)"
)
def test_in_a_browser_the_tabs_are_a_tablist_by_keyboard_with_focus_seen_and_no_trap(demo, tmp_path, examined):
    import json
    import subprocess

    from onetrace_console import frame

    shared, _store = demo
    page = _demo_page(shared, "p4-29-reply-30-days", "p4-30-reply-14-days").replace(
        '<link rel="stylesheet" href="/static/console.css">', f"<style>{frame.stylesheet().decode()}</style>"
    )
    f, script = tmp_path / "page.html", tmp_path / "keys.py"
    f.write_text(page, encoding="utf-8")
    script.write_text(KEYS_SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), str(f)], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr[-3000:]
    got = json.loads(done.stdout)
    examined(len(got), "keyboard states")
    tabs = structure(page)["tabs"]
    assert got["start"]["role"] == "tablist" and got["start"]["selected"] == got["start"]["shown"] == ["text"]
    assert got["start"]["outline"] not in ("none", ""), "the focused tab is seen"
    walk = [got[k] for k in got if k not in ("start", "tab")]
    #: Right, right, End, Home, Left (which wraps to the last).
    expected = [tabs[1], tabs[2], tabs[-1], tabs[0], tabs[-1]]
    assert [s["selected"] for s in walk] == [[t] for t in expected]
    assert [s["shown"] for s in walk] == [[t] for t in expected] and [s["focus"] for s in walk] == expected
    #: Tab leaves the tab list for the open panel: no trap.
    assert got["tab"]["focus"] == "text"


def test_the_public_explain_panel_shows_kept_readings_and_no_form_or_control(demo, examined):
    """On a public console Explain shows what was kept, read-only, each reading labelled AI-generated with its time, and
    says it runs on a local console: no step, no button, no form, nothing sent."""
    shared, _store = demo
    pages = [
        _demo_page(shared, "p1-02-baseline-set2", "p1-08-candidate-set2"),
        _demo_page(shared, "p4-29-reply-30-days", "p4-30-reply-14-days"),
    ]
    examined(len(pages), "public pages")
    for page in pages:
        aside = re.search(r'<aside class="compare-explain" data-section="explain-aside">.*?</aside>', page, re.S).group(
            0
        )
        assert '<p class="note" data-explain="public">Explain runs on a local console.</p>' in aside
        for control in ("<form", "<button", "<input", "<select", "<textarea", "data-explain-post", "onclick="):
            assert control not in aside, control
        assert "Prepare" not in _text(aside) and "Send" not in _text(aside)


def test_the_public_panel_shows_a_kept_reading_read_only_with_its_label_and_time(built, explain_installed, examined):  # noqa: F811
    """The hosted demo's build, with its kept readings: P1's, in the panel, labelled AI-generated with its model and
    the time it was made; no control beside it."""
    from tests.test_deploy_fly_kept import _page

    folder, _, pairs = built
    page = _page(folder, pairs[("p1-02-baseline-set2", "p1-08-candidate-set2")])
    examined(1, "public page with a kept reading")
    aside = re.search(r'<aside class="compare-explain" data-section="explain-aside">.*?</aside>', page, re.S).group(0)
    assert '<article data-explanation="' in aside and '<span class="ai">AI-generated, may be wrong</span>' in aside
    #: Its time: the record each reading is kept under is named by when it was made, shown as the panel shows it.
    assert re.search(
        r'<p data-explain="record">Its record: <span class="mono">explain/2026-11-10T[0-9-]+\.\d+Z/</span>', aside
    )
    assert '<p class="note" data-explain="public">Explain runs on a local console.</p>' in aside
    for control in ("<form", "<button", "<input", "data-explain-post"):
        assert control not in aside, control
