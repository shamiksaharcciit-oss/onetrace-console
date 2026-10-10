"""The console's pages are a public surface, so they carry no internal ids --
no ruling, work order, memo or addendum named on a page. The reason a page says what it says may
stay in a code comment, citing its ruling.

Read: every page kind `tools/visible_text.py` renders from the committed fixtures, and the graph
pages the exam's dag-r37 runs draw (the compare page, and a run page marked from it). Read as the
browser shows them, text and attributes both (a `title` is read on hover), less `<style>`,
`<script>` and comments, which are not shown.
"""
from __future__ import annotations

import pytest

#: Four forms of an internal id, and the three other forms this channel's own ids take: one
#: pattern, held in the console so that `export-static` scans its own output with it too.
from onetrace_console.export_static import INTERNAL_ID
from onetrace_console.export_static import shown as _shown


def _found(pages: dict[str, str]) -> list[str]:
    return [f"{name}: …{_shown(html)[max(0, m.start() - 50):m.end() + 30]}…"
            for name, html in sorted(pages.items()) for m in INTERNAL_ID.finditer(_shown(html))]


@pytest.mark.parametrize("text", ["R-2026-09-28h", "(29di §2)", "WO-C18 item 12", "Addendum 3",
                                  "C036 §5", "Core → Canary 031", "Bench Record 047"])
def test_the_pattern_finds_each_form_of_internal_id(text):
    assert _found({"page": f"<p>a sentence {text}.</p>"}), text


@pytest.mark.parametrize("text", ["sha256:29abcdef0123", "2026-09-28T10:00:00+00:00",
                                  "stage 4 · model", "<!-- R-2026-09-28h -->",
                                  "<style>.wo-x{}</style>"])
def test_the_pattern_leaves_values_and_hidden_text_alone(text):
    assert not _found({"page": f"<p>{text}</p>"}), text


def test_no_page_the_console_renders_names_an_internal_id(tmp_path, examined):
    from tools.visible_text import rendered
    pages = rendered(tmp_path)
    examined(len(pages), "pages rendered from the fixtures, scanned")
    found = _found(pages)
    assert not found, f"{len(found)} internal ids on rendered pages:\n" + "\n".join(found[:20])


def test_no_graph_page_names_an_internal_id(runs, examined):
    from onetrace_console.compare import compare
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_all, render_diff
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_home_and_diff import GENERATED_AT
    found, store = runs
    c = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    pages = {"diff[P,R]": render_diff(c, store, generated_at=GENERATED_AT)}
    for name, html in render_execution(found["R"], store, generated_at=GENERATED_AT).pages.items():
        pages[f"run[R]/{name}"] = html
    pages.update({f"all/{k}": v for k, v in render_all(store, generated_at=GENERATED_AT).items()})
    examined(len(pages), "graph and overview pages, scanned")
    hits = _found(pages)
    assert not hits, f"{len(hits)} internal ids:\n" + "\n".join(hits[:20])


from tests.test_run_page_marks import runs  # noqa: E402,F401  P, Q and R, delivered and checked
