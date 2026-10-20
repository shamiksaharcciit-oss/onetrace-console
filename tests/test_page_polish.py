"""The pages a first-time visitor reads, polished before the release: text and layout only.

Each page states the same facts as before; what changed is how they are said and laid out:

1. a graph-shaped comparison does not parade what it cannot draw: where the change started and
   other runs with the same change are one closed line at the end of the page, its reasons and the
   SDK's own words inside it; a linear comparison keeps both sections;
2. no developer wording: "What changed between the two runs", "The two runs differ." (the exit code
   only in the SDK's own report), "Repeat this yourself", "with the run's output files present", and
   a repeated stage's nodes as "tests (1st)", "tests (2nd)" in tables;
3. the comparison page says once, at the top, who A and B are;
4. the run page's step table says the reason every step shares once, above it; gives each step's
   times of day to the millisecond, the date once in the case header; and names each receipt for
   its step;
5. every page shows a time one way, `YYYY-MM-DD HH:MM:SS UTC`, inside `<time datetime>`;
6. every footer names one product and version, "onetrace-console 0.1.0";
7. a scroll region's focus ring is drawn in full: the graph panel's on its section, since the fade's
   mask clips what the panel paints outside itself.

Each item's check is a function that names what is wrong; each has a sabotage that plants the old
form and is named. A browser check run beside the suite measures items 5 and 7 at 1280 and 390.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from onetrace_console import __version__
from tests.test_home_and_diff import GENERATED_AT, diverging  # noqa: F401

REPO = Path(__file__).resolve().parent.parent

#: A time as every page shows it, a time of day after a date said once, and a step's clock time.
FULL = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC")
DAY_TIME = re.compile(r"\d\d:\d\d:\d\d UTC")
CLOCK = re.compile(r"(\d{4}-\d\d-\d\d )?\d\d:\d\d:\d\d\.\d{3}")
_RAW = re.compile(r"\d{4}-\d\d-\d\d[T ]\d\d:\d\d")


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict[str, str]:
    """The demo's pages, drawn as the console draws them."""
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("polish") / "demo"
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "demo", "--public",
                          "--build", str(folder)], capture_output=True, text=True, timeout=600,
                         env={**{k: v for k, v in os.environ.items()
                                 if k != "ONETRACE_CONSOLE_CONFIG"},
                              "PYTHONPATH": str(REPO / "src")})
    assert out.returncode == 0, out.stdout + out.stderr
    root = folder / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in root.rglob("*.html")}


def _reference_comparison(pages: dict[str, str]) -> str:
    """The comparison these items were drawn for: the reference demo's two runs. Since 0.1.1 the
    demo stores several comparisons, and a page's name is its content's digest, so "the first diff
    page" would be a different one from build to build: it is picked by its runs, never by order."""
    found = [h for rel, h in pages.items() if re.fullmatch(r"diff/[0-9a-f]{64}\.html", rel)
             and "demo-run-1" in h and "demo-run-2" in h]
    assert len(found) == 1, len(found)
    return found[0]


def _shown(html: str) -> str:
    """The page's own words: no style, script or quoted `<pre>`, tags taken out."""
    import html as _h
    html = re.sub(r"(?s)<(style|script|pre)[^>]*>.*?</\1>", " ", html)
    return _h.unescape(re.sub(r"<[^>]+>", " ", html))


# ------------------------------------------------------------- 1. what a graph pair cannot draw

def item1_problems(page: str, *, graph: bool) -> list[str]:
    out = []
    closed = re.findall(r'<details data-section="not-shown"( open)?><summary>([^<]*)</summary>', page)
    if graph:
        if 'data-section="localize-unreadable"' in page:
            out.append("the localize refusal is drawn as a section")
        if 'data-section="same-change"' in page:
            out.append("the same-change refusal is drawn as a section")
        if len(closed) != 1 or closed[0][0]:
            out.append(f"not one closed line for what is not shown ({len(closed)})")
        elif closed[0][1] != ("Not shown for graph-shaped runs: where the change started, and "
                              "other runs that recorded the same value."):
            out.append(f"the closed line's words: {closed[0][1]!r}")
        body = page[page.find('data-section="not-shown"'):]
        for section in ("not-shown-localize", "not-shown-same-change"):
            if f'data-section="{section}"' not in body:
                out.append(f"no reason for {section}")
        if "The localize report as the SDK wrote it" not in body:
            out.append("the SDK's own localize report is not inside the closed line")
        if page.find('data-section="not-shown"') < page.find('data-section="text-diff"'):
            out.append("the closed line is not at the end of the page")
    else:
        if closed:
            out.append("a linear comparison folds its sections away")
        if 'data-section="same-change"' not in page:
            out.append("a linear comparison lost its same-change section")
    return out


def test_a_graph_comparison_folds_what_it_cannot_draw_into_one_closed_line(pages, diverging,
                                                                           examined):  # noqa: F811
    from onetrace_console.render import render_diff
    graph = _reference_comparison(pages)
    comparison, store = diverging
    linear = render_diff(comparison, store, generated_at=GENERATED_AT)
    examined(2, "comparison pages")
    assert item1_problems(graph, graph=True) == []
    assert item1_problems(linear, graph=False) == []


def test_item1_sabotage_the_sections_drawn_again_is_named(pages, examined):
    graph = _reference_comparison(pages)
    planted = graph.replace('<details data-section="not-shown">',
                            '<section data-section="same-change"><h2>Other runs with the same change'
                            '</h2></section><details data-section="not-shown" open>', 1)
    examined(1, "planted page")
    assert item1_problems(planted, graph=True)


# ------------------------------------------------------------------ 2. no developer wording

OLD_WORDS = {"the bare heading diff": re.compile(r"<h2>diff</h2>"),
             "the envelope with its exit code": re.compile(r"diff: diverged|\(exit \d+\)"),
             "Repeat it without us": re.compile(r"Repeat it without us"),
             "--require-artifacts": re.compile(r"\(--require-artifacts\)"),
             "a #n node in a table": re.compile(r'<td class="mono">[^<#]+#\d+</td>')}


def item2_problems(overview: str, comparison: str) -> list[str]:
    #: The page's own words only: the SDK's report, quoted as it wrote it, keeps its own.
    words = _shown(overview) + _shown(comparison)
    out = [f"{name} is still shown" for name, rx in OLD_WORDS.items()
           if rx.search(words if name != "a #n node in a table" else comparison)]
    for words in ("What changed between the two runs", "The two runs differ.", "Repeat this yourself",
                  "tests (1st)", "tests (2nd)"):
        if words not in _shown(comparison):
            out.append(f"the comparison page lacks {words!r}")
    if "with the run's output files present" not in _shown(overview):
        out.append("the Overview lacks \"with the run's output files present\"")
    return out


def test_no_developer_wording_on_the_overview_or_the_comparison(pages, examined):
    overview, comparison = pages["home.html"], _reference_comparison(pages)
    examined(2, "pages")
    assert item2_problems(overview, comparison) == []


@pytest.mark.parametrize("old,new", [("What changed between the two runs", "diff"),
                                     ("The two runs differ.", "diff: diverged (exit 1)"),
                                     ("Repeat this yourself", "Repeat it without us"),
                                     ("tests (1st)", "tests#1")])
def test_item2_sabotage_each_old_word_put_back_is_named(pages, old, new, examined):
    comparison = _reference_comparison(pages)
    examined(1, f"{new} planted")
    assert old in comparison
    assert item2_problems(pages["home.html"], comparison.replace(old, new))


# ------------------------------------------------------------------ 3. who A and B are, once

def item3_problems(page: str) -> list[str]:
    out = []
    if page.count('data-section="runs-ab"') != 1:
        out.append(f"who A and B are is said {page.count('data-section=\"runs-ab\"')} times")
    elif page.find('data-section="runs-ab"') > page.find("<h2>"):
        out.append("who A and B are is not said at the top")
    if 'data-section="pair"' in page:
        out.append("the header line repeats who A and B are")
    graph = re.search(r'<section data-section="graph">.*?</section>', page, re.S)
    if graph and 'data-section="runs-ab"' in graph.group(0):
        out.append("the graph card repeats who A and B are")
    return out


def test_the_comparison_says_once_at_the_top_who_a_and_b_are(pages, examined):
    examined(1, "comparison page")
    assert item3_problems(_reference_comparison(pages)) == []


def test_item3_sabotage_the_graph_card_says_it_again(pages, examined):
    page = _reference_comparison(pages)
    ab = re.search(r'<p data-section="runs-ab">.*?</p>', page, re.S).group(0)
    planted = page.replace('<section data-section="graph">', '<section data-section="graph">' + ab, 1)
    examined(1, "planted page")
    assert item3_problems(planted)


# ------------------------------------------------------------------ 4. the run page's step table

SHARED = ("Held under the checks that ran; not anchored, so none of these steps can be shown to be "
          "the record that was made.")
PER_STEP = "Held under the checks that ran; not anchored, so it can't be shown to be the record"


def _unlabelled(html: str) -> str:
    """The page without the narrow screen's column labels (`words.labelled`), so a table reads as
    its cells were drawn before them; nothing else changes."""
    import re as _re
    return _re.sub(r' data-label="[^"]*"', "", html)


def item4_problems(case: str) -> list[str]:
    case = _unlabelled(case)
    out = []
    table = re.search(r'<section data-section="timeline">(.*?)</section>', case, re.S)
    if table is None:
        return ["no step table"]
    body = table.group(1)
    rows = re.findall(r'<tr data-step="(\d+)">(.*?)</tr>', body, re.S)
    if not rows:
        return ["no steps"]
    import html as _h
    shared = [_h.unescape(t) for t in re.findall(r'<p data-section="timeline-shared">([^<]*)</p>', body)]
    per_step = [n for n, row in rows if PER_STEP in _h.unescape(row)]
    if shared != [SHARED]:
        out.append("the reason every step shares is not said once above the table")
    if per_step:
        out.append(f"steps {per_step} still repeat the shared reason")
    for n, row in rows:
        cell = re.findall(r'<td class="value" data-words="record">(.*?)</td>', row, re.S)
        times = re.findall(r'<time datetime="([^"]+)"[^>]*>([^<]*)</time>', cell[0] if cell else "")
        if len(times) != 2 or not all(CLOCK.fullmatch(shown) for _, shown in times):
            out.append(f"step {n}'s times are not two clock times in <time>: {times}")
    total = len(rows)
    for n, row in rows:
        name = re.search(r'</span>([^<]+)<div class="step">', row)
        want = f"Receipt · step {n} of {total} · {name.group(1) if name else '?'}"
        if f"<summary>{want}</summary>" not in case:
            out.append(f"no receipt named {want!r}")
    if "The receipt for this step" in case:
        out.append("a receipt is not named for its step")
    return out


def _with_proof(pages: dict, rel: str) -> str:
    """A page with its "Proof" view after it: what a reader can reach of it, wherever a part is."""
    sibling = (rel[:-len("case.html")] + "proof.html" if rel.endswith("/case.html")
               else rel[:-len(".html")] + "-proof.html")
    return pages[rel] + pages.get(sibling, "")


def test_the_step_table_says_the_shared_reason_once_and_names_each_receipt(pages, examined):
    cases = [rel for rel in pages if rel.endswith("/case.html")]
    examined(len(cases), "run pages")
    assert cases
    for rel in cases:
        case = pages[rel]
        assert item4_problems(_with_proof(pages, rel)) == []
        #: The case is on "What changed", or on "Proof" for a run whose records don't hold up.
        header = re.search(r'<section data-section="case">.*?</section>', _with_proof(pages, rel), re.S).group(0)
        assert re.search(r"<time [^>]*>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC</time> → "
                         r"<time [^>]*>\d\d:\d\d:\d\d UTC</time>", header), "the date is not said once"


@pytest.mark.parametrize("planted", ["the shared reason per step", "a full timestamp in a step",
                                     "an unnamed receipt"])
def test_item4_sabotage_each_old_form_is_named(pages, planted, examined):
    #: The run's step table is on whichever view holds it; the demo's runs come in no fixed order.
    case = _unlabelled(next(_with_proof(pages, rel) for rel in sorted(pages) if rel.endswith("/case.html")))
    if planted == "the shared reason per step":
        bad = case.replace('<td><p>Checked — it holds.</p></td>',
                           "<td><p>Checked — it holds.</p><p>" + PER_STEP + ".</p></td>", 1)
    elif planted == "a full timestamp in a step":
        bad = re.sub(r'(<tr data-step="1">.*?<time datetime="[^"]+"[^>]*>)[^<]*', r"\g<1>2026-09-29T10:00:00.000+00:00",
                     case, count=1, flags=re.S)
    else:
        bad = re.sub(r"<summary>Receipt · step 1 of \d+ · [^<]*</summary>", "<summary>The receipt for this step</summary>",
                     case, count=1)
    examined(1, planted)
    assert bad != case, "the sabotage changed nothing"
    assert item4_problems(bad), planted


# ------------------------------------------------------------------ 5. one way to show a time

def item5_problems(rel: str, page: str) -> list[str]:
    out = []
    shown = re.sub(r"(?s)<time[^>]*>.*?</time>", " ", page)
    for m in _RAW.finditer(_shown(shown)):
        out.append(f"{rel}: a time outside <time>: {m.group(0)}")
    for attrs, text in re.findall(r"<time([^>]*)>([^<]*)</time>", page):
        if "datetime=" not in attrs:
            out.append(f"{rel}: a <time> with no datetime")
        if not (FULL.fullmatch(text) or DAY_TIME.fullmatch(text) or CLOCK.fullmatch(text)):
            out.append(f"{rel}: a time shown as {text!r}")
    from tests.test_ux_screens import MONTHS
    if MONTHS.search(_shown(page)):
        out.append(f"{rel}: a month by name")
    return out


def test_every_page_shows_a_time_one_way(pages, examined):
    examined(len(pages), "pages")
    found = [p for rel, page in pages.items() for p in item5_problems(rel, page)]
    assert not found, found[:10]


def test_item5_sabotage_a_raw_time_is_named(pages, examined):
    rel = "comparisons.html"
    bad = re.sub(r"<time datetime=\"([^\"]+)\"[^>]*>[^<]*</time>", r"\1", pages[rel], count=1)
    examined(1, "planted page")
    assert bad != pages[rel] and item5_problems(rel, bad)


# ------------------------------------------------------------------ 6. one name in every footer

def item6_problems(rel: str, page: str) -> list[str]:
    footers = re.findall(r"(?s)<footer>(.*?)</footer>", page)
    out = [] if footers else [f"{rel}: no footer"]
    named = f"onetrace-console {__version__}"
    for footer in footers:
        words = _shown(footer)
        if "onetrace viewer" in words or "(preview)" in words:
            out.append(f"{rel}: a footer names the viewer or a preview")
        if "Generated" in words and named not in words:
            out.append(f"{rel}: a footer's generator is not {named!r}")
    return out


def test_every_footer_names_one_product_and_version(pages, examined):
    examined(len(pages), "pages")
    found = [p for rel, page in pages.items() for p in item6_problems(rel, page)]
    assert not found, found[:10]


def test_item6_sabotage_the_old_viewer_name_is_named(pages, examined):
    rel = next(r for r in pages if r.endswith("/case.html"))
    bad = pages[rel].replace(f"by onetrace-console {__version__}.", "by onetrace viewer 0.1 (preview).", 1)
    examined(1, "planted page")
    assert bad != pages[rel] and item6_problems(rel, bad)


# ------------------------------------------------------------------ 7. the focus ring, in full

def item7_problems(css: str) -> list[str]:
    out = []
    own = re.search(r"\.graph-box:focus-visible\{([^}]*)\}", css)
    if own is None or "outline:none" not in own.group(1):
        out.append("the masked graph panel draws its own ring, which the mask clips")
    if not re.search(r"\[data-section=graph\]:has\(>\.graph-box:focus-visible\)\{outline:2px solid "
                     r"var\(--accent\);\s*outline-offset:2px\}", css):
        out.append("the graph's section draws no ring when its panel has focus")
    return out


def test_the_graph_panels_focus_ring_is_drawn_on_its_section(examined):
    from onetrace_console.viewer.page import CSS
    examined(1, "stylesheet")
    assert item7_problems(CSS) == []
    #: A table's scroll region has the fade too, so its ring is its frame's, never its own.
    assert re.search(r"\.scroll-x:focus-visible\{outline:none\}", CSS)
    assert re.search(r"\.scroll-frame:has\(>\.scroll-x:focus-visible\)\{outline:2px solid "
                     r"var\(--accent\);outline-offset:2px\}", CSS)


def test_item7_sabotage_the_ring_back_on_the_masked_panel_is_named(examined):
    from onetrace_console.viewer.page import CSS
    bad = (CSS.replace(".graph-box:focus-visible{outline:none}",
                       ".graph-box:focus-visible{outline:2px solid var(--accent);outline-offset:2px}")
           .replace("[data-section=graph]:has(>.graph-box:focus-visible)", "[data-section=graph]:has(>.never)"))
    examined(1, "planted stylesheet")
    assert bad != CSS and len(item7_problems(bad)) == 2


# ------------------------------------------------------------- 8. phone width: wide tables scroll

#: Every table wider than the page at 390 (measured), by the page it is on and its region's name.
WIDE_TABLES = {r"home\.html": ("recent-runs", "pipelines", "by-day"),
               r"comparisons\.html": ("comparisons",),
               r"runs/[0-9a-f]{64}/case\.html": ("ladder", "steps"),
               r"runs/[0-9a-f]{64}/receipt\.html": ("receipt",),
               r"runs/[0-9a-f]{64}/stage-\d+\.html": ("badges",),
               r"diff/[0-9a-f]{64}\.html": ("changes",)}
_REGION = re.compile(r'<div class="scroll-frame"><div class="scroll-x" data-scroll="([\w-]+)" '
                     r'tabindex="0" role="region" aria-label="([^"]+), scrolls sideways"><table[ >]')


def item8_problems(rel: str, page: str, names: tuple[str, ...]) -> list[str]:
    found = {name: label for name, label in _REGION.findall(page)}
    return [f"{rel}: the {name} table is not in a named scroll region" for name in names
            if name not in found]


def test_every_wide_table_scrolls_in_a_named_region(pages, examined):
    checked = 0
    for pattern, names in WIDE_TABLES.items():
        matched = [rel for rel in pages if re.fullmatch(pattern, rel)]
        assert matched, pattern
        for rel in matched:
            assert item8_problems(rel, _with_proof(pages, rel), names) == []
            checked += 1
    examined(checked, "pages with wide tables")


def test_item8_sabotage_a_table_out_of_its_region_is_named(pages, examined):
    page = pages["comparisons.html"]
    bad = re.sub(r'<div class="scroll-frame"><div class="scroll-x" data-scroll="comparisons"[^>]*>(.*?)</div></div>',
                 r"\1", page, count=1, flags=re.S)
    examined(1, "planted page")
    assert bad != page and item8_problems("comparisons.html", bad, ("comparisons",))


def digest_wrap_problems(css: str) -> list[str]:
    return ([] if re.search(r"(^|\n)\.mono,q\[data-words\]\{overflow-wrap:break-word\}", css)
            else ["a long unbroken value does not wrap at a narrow width"])


def test_a_long_digest_wraps_rather_than_widening_the_page(examined):
    """`break-word` breaks a value only where it would overflow: at 1280 no width or height moves,
    and a copied digest is the same characters (both measured in the browser check)."""
    from onetrace_console.viewer.page import CSS
    examined(1, "stylesheet")
    assert digest_wrap_problems(CSS) == []


def test_digest_wrap_sabotage_the_rule_removed_is_named(examined):
    from onetrace_console.viewer.page import CSS
    bad = CSS.replace(".mono,q[data-words]{overflow-wrap:break-word}", "")
    examined(1, "planted stylesheet")
    assert bad != CSS and digest_wrap_problems(bad)
