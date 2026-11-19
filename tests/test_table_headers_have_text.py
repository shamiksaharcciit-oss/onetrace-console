"""Every table header has text: a header named only by `aria-label` reads as empty to some readers and tools (axe's
`empty-table-header`). Where a column's header is not drawn, its words are there, hidden from sight but not from a
screen reader (`visually-hidden`). Read over every page of the public demo.
"""

from __future__ import annotations

import re

_TH = re.compile(r"<th\b[^>]*>(.*?)</th>", re.S)


def test_no_table_header_is_empty(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages").rglob("*.html"))
    seen, empty = 0, {}
    for p in pages:
        for inner in _TH.findall(p.read_text(encoding="utf-8")):
            seen += 1
            if not re.sub(r"<[^>]+>", "", inner).strip():
                empty.setdefault(p.relative_to(shared_demo["folder"]).as_posix(), 0)
                empty[p.relative_to(shared_demo["folder"]).as_posix()] += 1
    examined(seen, "table headers")
    assert empty == {}, f"{len(empty)} pages: {dict(list(empty.items())[:10])}"


def test_a_hidden_header_labels_no_stacked_cell(examined):
    from onetrace_console.words import hidden_header, labelled

    table = (
        "<table><thead><tr><th>Run</th>"
        + hidden_header("Action")
        + "</tr></thead><tbody><tr><td>r1</td><td><a href='#'>Compare</a></td></tr></tbody></table>"
    )
    examined(1, "table")
    got = labelled(table)
    assert '<td data-label="Run">r1</td>' in got and 'data-label="Action"' not in got


def test_a_row_that_begins_with_its_own_header_keeps_each_cell_under_its_column(examined):
    from onetrace_console.words import labelled

    table = (
        "<table><thead><tr><th>rank</th><th>baseline</th><th>candidate</th></tr></thead>"
        '<tbody><tr><th scope="row">1</th><td>15</td><td>40</td></tr></tbody></table>'
    )
    examined(1, "table")
    got = labelled(table)
    assert '<td data-label="baseline">15</td>' in got and '<td data-label="candidate">40</td>' in got
    assert '<th scope="row">1</th>' in got
