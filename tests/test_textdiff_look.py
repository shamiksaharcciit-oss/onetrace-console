"""The text diff in 0.1.1's look, styled in place on the Diff page, on the golden warranty pair.

Checked: every line drawn carries the document's own line numbers, side by side, and its `-`/`+`
mark; each output's counts are its lines' own `op` tally; removed words are struck through and
added ones marked, by the stylesheet; a settings line's `old -> new` reads with an arrow, the
words otherwise the SDK's; each side is said verified. Each check has its sabotage. What is never
shown -- an output whose bytes don't match a receipt -- is held by tests/test_textdiff_view.py.
"""
from __future__ import annotations

import html
import re

from tests.test_textdiff_view import golden  # noqa: F401


def _lines(page: str) -> list[tuple[str, str, str]]:
    """(baseline number, candidate number, op) for every line drawn."""
    return re.findall(r'<span data-op="([ +-])"><span class="ln" data-side="baseline">([^<]*)</span>'
                      r'<span class="ln" data-side="candidate">([^<]*)</span>\1 ', page)


def line_problems(page: str, doc: dict) -> list[str]:
    want = [(line["op"], line["baseline"] or "", line["candidate"] or "")
            for node in doc["nodes"] for out in node["outputs"] if out["verified"] is True
            for hunk in out["hunks"] for line in hunk["lines"]]
    got = _lines(page)
    return [] if got == want else [f"lines drawn {got[:3]}…, the document's {want[:3]}…"]


def count_problems(page: str, doc: dict) -> list[str]:
    said = re.findall(r"<p data-counts>(\d+) lines? removed · (\d+) added", page)
    want = [(str(sum(l["op"] == "-" for h in o["hunks"] for l in h["lines"])),
             str(sum(l["op"] == "+" for h in o["hunks"] for l in h["lines"])))
            for n in doc["nodes"] for o in n["outputs"] if o["verified"] is True]
    return [] if said == want else [f"counts said {said}, the document's {want}"]


def test_every_line_has_its_numbers_and_its_mark(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    page = render_textdiff(golden)
    examined(len(_lines(page)), "lines drawn")
    assert _lines(page) and line_problems(page, golden) == []


def test_each_outputs_counts_are_its_own_op_tally(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    page = render_textdiff(golden)
    examined(page.count("<p data-counts>"), "outputs counted")
    assert count_problems(page, golden) == []


def test_removed_words_are_struck_and_added_ones_marked_by_the_stylesheet(examined):
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    examined(2, "rules")
    assert re.search(r"\.cp mark\.del\{[^}]*text-decoration:line-through", css)
    assert re.search(r"\.cp mark\.ins\{[^}]*color:var\(--ok-ink\)", css)
    assert re.search(r'\.cp pre\[data-hunk\]>span\[data-op="-"\]\{background:var\(--bad-bg\)\}', css)


def test_a_settings_line_reads_with_an_arrow_and_otherwise_as_written(examined):
    from onetrace_console.textdiff_view import _settings_line
    examined(2, "settings lines")
    #: A setting by its short name, its whole path in its tooltip, with the arrow (H4's rule).
    assert _settings_line("  constants.chunk_size: 1024 -> 512") == (
        '<span class="mono" data-setting-path="constants.chunk_size" title="constants.chunk_size">'
        "chunk_size</span>: 1024 → 512")
    #: A line of another shape, as written.
    assert _settings_line("settings: none changed") == "settings: none changed"


def test_each_side_is_said_verified(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    page = render_textdiff(golden)
    shown = sum(o["verified"] is True for n in golden["nodes"] for o in n["outputs"])
    examined(shown, "outputs shown")
    for side in ("Baseline", "Candidate"):
        assert page.count(f">{side}: verified</span>") == shown


# ------------------------------------------------------------------ the sabotages

def test_sabotage_a_mark_dropped_is_named(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    examined(1, "planted page")
    page = re.sub(r'(<span data-op="-">(?:<span class="ln"[^>]*>[^<]*</span>){2})- ', r"\1", render_textdiff(golden), count=1)
    assert line_problems(page, golden)


def test_sabotage_a_line_number_off_by_one_is_named(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    examined(1, "planted page")
    page = re.sub(r'(<span class="ln" data-side="baseline">)(\d+)',
                  lambda m: m.group(1) + str(int(m.group(2)) + 1), render_textdiff(golden), count=1)
    assert line_problems(page, golden)


def test_sabotage_counts_not_from_the_lines_are_named(golden, examined):  # noqa: F811
    from onetrace_console.textdiff_view import render_textdiff
    examined(1, "planted page")
    page = re.sub(r"<p data-counts>(\d+)", lambda m: f"<p data-counts>{int(m.group(1)) + 1}",
                  render_textdiff(golden), count=1)
    assert count_problems(page, golden)
