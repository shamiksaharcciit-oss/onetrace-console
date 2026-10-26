"""No page shows a `\\uXXXX` escape sequence as text in the console's own words: its labels, its
examples, its templates, the setup page. The console's display rule (`viewer.page.display`) shows a
control character in a record's own value escaped, on purpose, and that stays: an escape is allowed only
inside text that is the display of a string the records hold. The demo's records hold no such
character, so on its pages, an export's and the kept build's, no escape is allowed at all. Held here on
the public demo and an export, and on a pair whose record holds a carriage return in a setting's value,
shown escaped, which passes, beside a label of the console's planted with an escape, which is named.
The local console's pages are held in tests/test_explain_setup.py (the setup page, with its planted
example) and tests/test_deploy_fly_kept.py (the kept build, and a local comparison with its
explanation)."""
from __future__ import annotations

import html
import re
import shutil

import pytest

#: An escape sequence as the console's display rule writes one.
ESCAPE = re.compile(r"\\u[0-9a-fA-F]{4}")


def escapes_shown(page: str, allowed=()) -> list[str]:
    """Each `\\uXXXX` in the page's text, as a reader sees it (no script, no style, no markup), but
    those inside text that is one of `allowed`: the display of a record's own value."""
    page = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", page))
    covered = set()
    for value in allowed:
        for m in re.finditer(re.escape(value), text):
            covered.update(range(m.start(), m.end()))
    return [m.group(0) for m in ESCAPE.finditer(text) if m.start() not in covered]


def record_values(*records) -> set[str]:
    """Each string in the records (parsed JSON), as the display rule shows it, where the rule escapes
    something in it: the only text an escape is allowed in."""
    from onetrace_console.viewer.page import _UNSHOWN, display
    out = set()

    def walk(v):
        if isinstance(v, str):
            if _UNSHOWN.search(v):
                out.add(display(v))
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(k)
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
    for r in records:
        walk(r)
    return out


def pages_problems(pages: dict[str, str], allowed=()) -> list[str]:
    return [f"{name}: {found[:3]}" for name, text in sorted(pages.items())
            if (found := escapes_shown(text, allowed))]


def _receipts(store) -> list:
    """Every receipt of every stored run, parsed."""
    import json
    out = []
    for run in store.runs():
        for path, key in run.listing:
            if path.startswith("receipts/") and path.endswith(".json"):
                out.append(json.loads(store.get(key)))
    return out


def test_the_demo_s_records_hold_no_character_the_display_rule_escapes(shared_demo, examined):
    """So on the demo's pages no escape is a record's: each would be the console's own."""
    from onetrace_console.store import Store
    receipts = _receipts(Store(shared_demo["folder"] / "store" / "store"))
    examined(len(receipts), "demo receipts")
    assert receipts and record_values(*receipts) == set()


def _pages(root) -> dict[str, str]:
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.html"))}


def test_no_page_of_the_public_demo_shows_an_escape(shared_demo, examined):
    pages = _pages(shared_demo["folder"] / "store" / "pages")
    examined(len(pages), "public demo pages")
    assert pages and pages_problems(pages) == []


def test_no_page_of_an_export_shows_an_escape(shared_demo, tmp_path, examined):
    from onetrace_console.export_static import export
    from onetrace_console.store import Store
    source = tmp_path / "console"
    shutil.copytree(shared_demo["folder"] / "store", source)
    runs = {r.run_id: r.key for r in Store(source / "store").runs()}
    export(source, [runs["p1-02-baseline-set2"], runs["p1-08-candidate-set2"]], tmp_path / "export")
    pages = _pages(tmp_path / "export")
    examined(len(pages), "exported pages")
    assert pages and pages_problems(pages) == []


def test_sabotage_an_escaped_line_break_planted_is_named(shared_demo, examined):
    pages = _pages(shared_demo["folder"] / "store" / "pages")
    name = next(iter(pages))
    examined(1, "planted page")
    planted = {**pages, name: pages[name].replace("</main>", "<pre><code>[model]\\u000aprovider</code></pre></main>", 1)}
    assert pages_problems(planted) == [f"{name}: ['\\\\u000a']"]


# ------------------------------------------------------------------ a record that holds a control character

def _hostile_pair(root):
    """Two runs whose `score` stage records a setting, `note`, that holds a carriage return in the
    baseline: the record's own value, shown escaped by the display rule."""
    from pathlib import Path

    from onetrace.emit import Instrument, Recorder
    out = []
    for name, note, x in (("a", "a\rb", "1"), ("b", "c", "2")):
        rec = Recorder(str(root / name), run_id=f"hostile-{name}", declared_stages=["load", "score"],
                       manifest=Path(__file__), policy="fail-closed", anchor_reason="a test record")

        def load(ctx):
            return ctx.write_json("load.json", {"load": "1"})

        def score(ctx, note=note, x=x):
            ctx.constant("note", note)
            return ctx.write_json("score.json", {"score": x})
        rec.run_stage("load", Instrument("loader", "tool", "1.0.0", {"source": "docs"}), load)
        rec.run_stage("score", Instrument("scorer", "tool", "1.0.0", {"rule": "max"}), score)
        rec.close()
        out.append(root / name)
    return out


@pytest.fixture
def hostile(tmp_path):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    from tests.test_compare import _deliver
    _require_installed()
    store = Store(tmp_path / "store")
    a, b = (run_and_record(_deliver(f, store), store) for f in _hostile_pair(tmp_path / "made"))
    comparison = compare(a, b, store)
    page = render_diff(comparison, store, generated_at="2026-01-01T00:00:00+00:00", public=True)
    return page, record_values(*_receipts(store))


def test_a_record_s_carriage_return_shown_escaped_is_allowed(hostile, examined):
    page, allowed = hostile
    examined(1, "comparison page of a record holding a carriage return")
    assert allowed == {"a\\u000db"}
    #: Shown, as the display rule shows it, and only inside the record's value.
    assert "a\\u000db" in page and set(escapes_shown(page)) == {"\\u000d"}
    assert pages_problems({"hostile": page}, allowed) == []


def test_sabotage_a_label_of_the_console_s_with_an_escape_beside_it_is_named(hostile, examined):
    page, allowed = hostile
    planted = page.replace("The short answer", "The short\\u000aanswer", 1)
    examined(1, "the same page, a label planted with an escape")
    assert planted != page
    assert pages_problems({"hostile": planted}, allowed) == ["hostile: ['\\\\u000a']"]
