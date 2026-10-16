"""Before 0.2.0: the places 0.2.0 fills, each reading the placeholder,
"not available until onetrace 0.2.0", and stating nothing else about the runs.

- The text diff: a frame on the Diff page, under the diff report's own blocks, with **no
  field names** -- what `onetrace-textdiff/0.2` writes decides its rows.
- The excerpts: one line below the compare graph, never a guessed excerpt on a node.
- Board 7, where the change started: **absent on every pair before 0.2.0**, the diverged one
  included. Only 0.2.0 can say whether the first difference sits at a node
  whose corpus link changed; a frame on every diverged pair would suggest a source change.
- The signing and anchoring badges: two rows on each stage page, in the run ladder's fixed
  questions.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from onetrace_console.render import render_diff
from tests.test_compare_graph import dag_pages  # noqa: F401
from tests.test_home_and_diff import GENERATED_AT, compared, diverging  # noqa: F401
from tests.test_stage_pages import _pages, _text, demo  # noqa: F401

PLACEHOLDER = "not available until onetrace 0.2.0"
#: The demo's day 1 is signed by the demo key; checked without a trust file.
_DEMO_KEY = json.loads((Path(__file__).resolve().parent.parent / "examples" / "reference-demo" / "runs"
                        / "day-1" / "signatures" / "1.json").read_text(encoding="utf-8"))["key_id"]
LIMIT = "Nothing here says which version is correct, who changed the source, or why."


def _section(page: str, name: str) -> str | None:
    found = re.search(rf'<section data-section="{name}"[^>]*>(.*?)</section>', page, re.S)
    return found.group(1) if found else None


def _words(html: str) -> str:
    from tests.conftest import whole_folds
    return _text(whole_folds(html)).strip()


@pytest.fixture
def linear_page(diverging):  # noqa: F811
    """Runs A and B of the ingest fixture: the diff finds them different (diverged)."""
    comparison, store = diverging
    return render_diff(comparison, store, generated_at=GENERATED_AT)


@pytest.fixture
def same_page(compared):  # noqa: F811
    """The exam's run C against its poppler-24 rerun: the diff finds them identical."""
    comparison, store = compared
    return render_diff(comparison, store, generated_at=GENERATED_AT)


def test_the_text_diff_is_the_sdks_own_stored_run_drawn_as_it_wrote_it(diverging):  # noqa: F811
    """The frame holds the comparison's own stored run of `onetrace diff
    --text --json --no-follow`, read strictly and drawn by `render_textdiff` -- exactly that, and
    never the console's own diff, nor the placeholder."""
    from onetrace_console.compare import text_diff_raw
    from onetrace_console.textdiff_view import read_textdiff, render_textdiff
    comparison, store = diverging
    frame = _section(render_diff(comparison, store, generated_at=GENERATED_AT), "text-diff")
    assert frame is not None, "no text-diff frame on the Diff page"
    raw, verb = text_diff_raw(comparison, store)
    assert verb == "diff --text"
    assert render_textdiff(read_textdiff(raw)) in frame
    assert PLACEHOLDER not in frame


def test_the_text_diff_sits_under_the_diff_report_s_own_blocks(linear_page):
    at = linear_page.index('data-section="text-diff"')
    assert linear_page.index('data-section="changes"') < at
    assert at < linear_page.index('<details data-layer="3">'), "before the SDK's own layer"


def test_board_7_is_absent_on_every_pair_before_0_2_0(linear_page, same_page, dag_pages):  # noqa: F811
    """The diverged pair included. Neither its frame, its title nor its limit line."""
    assert 'data-section="diff-envelope" data-verdict="diverged"' in linear_page
    assert 'data-section="diff-envelope" data-verdict="identical"' in same_page
    for name, page in {"diverged": linear_page, "identical": same_page, **dag_pages}.items():
        assert 'data-section="where-started"' not in page, name
        assert "Where the change started" not in page, name
        assert LIMIT not in page, name


def test_the_text_diff_is_on_a_pair_where_nothing_differs_too(same_page):
    """The frame holds the SDK's own text diff (`diff --text --json
    --no-follow`, stored with the comparison), not the placeholder."""
    words = _words(_section(same_page, "text-diff"))
    assert words.startswith("The text diff Shown with at most 200 lines per output"), words
    assert PLACEHOLDER not in words
    assert re.search(r"Command: onetrace diff runs/\S+ runs/\S+ --text", words), words
    assert "RUN_A" not in words


def test_the_compare_page_promises_no_excerpts_its_text_diff_is_on_the_page(dag_pages):  # noqa: F811
    """The excerpts placeholder is gone: 0.2.0's text diff is the page's own,
    below the changes table, and no line promises a later version."""
    for pair, page in dag_pages.items():
        assert 'data-section="excerpts"' not in page, pair
        assert PLACEHOLDER not in page and "until onetrace" not in page, pair
        assert page.index('data-section="changes"') < page.index('data-section="text-diff"')


def test_a_linear_comparison_has_no_excerpts_line(linear_page, same_page):
    for page in (linear_page, same_page):
        assert 'data-section="excerpts"' not in page


def test_every_stage_page_asks_the_ladder_s_two_questions(demo):  # noqa: F811
    """Each badge states the run's own rung, for signing and for anchoring
    (tests/test_signed_surfaces.py and tests/test_stage_badges.py hold each row)."""
    run, store = demo
    stages = {k: v for k, v in _pages(run, store).items() if k.startswith("stage-")}
    assert stages, "no stage pages"
    for name, page in stages.items():
        rows = re.findall(r'<tr data-badge="(\d)"[^>]*>(.*?)</tr>', _section(page, "badges") or "",
                          re.S)
        assert [(n, _words(r)) for n, r in rows] == [
            ("1", "Signed by a known recorder Signed, key not trusted · " + _DEMO_KEY),
            ("2", "Committed by a known time Not anchored · no anchor beside the chain")], (name, rows)
        assert page.index('data-section="outputs"') < page.index('data-section="badges"')
