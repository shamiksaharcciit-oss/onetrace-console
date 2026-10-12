"""On a narrow screen a table's rows stack, so each cell must say which column it is: `labelled`
gives every body cell its column's header as `data-label`, and leaves a table with no header row
(a key and its value, row by row) as it is. The stylesheet shows the label above the value, and
lets nothing in a stacked row scroll or be cut off (`tools/layout_check.py` holds the pages).
"""
from __future__ import annotations

import re

from onetrace_console.words import labelled, scroll_region

TABLE = ('<table><thead><tr><th>Run</th><th>When <em>it</em> ran</th><th></th></tr></thead>'
         '<tbody><tr data-x="1"><td>a</td><td class="v">b</td><td>c</td></tr>'
         '<tr><td>d</td><td>e</td><td>f</td></tr></tbody></table>')


def label_problems(html: str, table: str) -> list[str]:
    heads = [" ".join(re.sub(r"<[^>]+>", " ", h).split())
             for h in re.findall(r"<th>(.*?)</th>", table)]
    out = []
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr>", re.search(r"<tbody>(.*?)</tbody>", html).group(1)):
        cells = re.findall(r"<td\b([^>]*)>", row)
        for head, attrs in zip(heads, cells):
            got = re.search(r'data-label="([^"]*)"', attrs)
            if head and (got is None or got.group(1) != head):
                out.append(f"{head!r}: {got.group(1) if got else None!r}")
            if not head and got:
                out.append("a label for a column with no header")
    return out


def test_each_body_cell_carries_its_columns_header(examined):
    examined(2, "rows")
    assert label_problems(labelled(TABLE), TABLE) == []
    assert 'class="v"' in labelled(TABLE) and 'data-x="1"' in labelled(TABLE)


def test_a_table_with_no_header_row_is_left_as_it_is(examined):
    examined(1, "table")
    table = "<table><tbody><tr><td>Records agree</td><td>Yes</td></tr></tbody></table>"
    assert labelled(table) == table


def test_every_scroll_region_labels_its_table(examined):
    examined(1, "region")
    assert label_problems(scroll_region(TABLE, "x", "x"), TABLE) == []


def test_sabotage_a_missing_or_wrong_label_is_named(examined):
    examined(2, "planted tables")
    bare = TABLE
    wrong = labelled(TABLE).replace('data-label="Run"', 'data-label="Pipeline"', 1)
    assert label_problems(bare, TABLE) and label_problems(wrong, TABLE)


def test_the_console_stacks_regions_on_a_narrow_screen(examined):
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    blocks = re.findall(r"@media \(max-width:760px\)\{\n(.*?)\n\}\n", css, re.S)
    examined(1, "stylesheet")
    rules = next((b for b in blocks if ".shell .scroll-x" in b), "")
    assert rules, "the narrow-screen rules"
    assert ".shell .scroll-x{overflow:visible" in rules
    assert ".shell .scroll-x td[data-label]::before{content:attr(data-label)" in rules
