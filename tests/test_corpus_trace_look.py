"""Where the change started: its look in the console's stylesheet -- the first difference
outlined, and its wide tables scrolling inside their panel, the scrollbar drawn -- on the markup the section
draws. The visible text is unchanged: these are selectors only."""

from __future__ import annotations

import inspect


def test_the_stylesheet_outlines_the_first_difference_and_scrolls_the_wide_tables():
    from onetrace_console import corpus_trace
    from onetrace_console.frame import stylesheet

    css = stylesheet().decode("utf-8")
    assert ".cp [data-section=where-started-chain] li[data-first-difference=true]{outline:" in css
    assert ".cp [data-section^=where-started] table{display:block;max-width:100%;overflow-x:auto}" in css
    assert ".cp [data-section^=where-started] table::-webkit-scrollbar{height:12px}" in css
    #: The selectors are the section's own markup, not names this test assumes.
    source = inspect.getsource(corpus_trace)
    assert 'data-section="where-started-chain"' in source and 'data-first-difference="true"' in source
    assert 'data-section="where-started-causes"' in source and 'data-section="where-started-text"' in source
    assert source.count("<table>") >= 2
