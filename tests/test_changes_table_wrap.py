"""The changes table breaks only its annotation and digest cells.

    The changes table breaks node names mid-word: "reques t", "contex t", "propos al",
    "config applie d". The rule that breaks digest cells (`841f004`) is applied to every cell.
    Break only the annotation and digest cells. Node names wrap only at spaces.

The break-anywhere rule had named `td.mono`, and a graph comparison's node column is `td.mono`
too. Digest cells now say what they are (`data-cell="digest"`), and the rule names them, the
settings cell and the annotations cell, and nothing else.
"""
from __future__ import annotations

import re

from onetrace_console.render import render_diff
from tests.test_compare_graph import dag_pages  # noqa: F401
from tests.test_home_and_diff import GENERATED_AT, compared  # noqa: F401

#: The cells the decision lets break anywhere: digests, and the annotation cells of either table.
BREAKABLE = {"td[data-cell=digest]", "td[data-section=settings]", "td[data-section=annotations]"}


def _break_rules() -> list[str]:
    """The selector of every rule, in the console's page skin, that breaks a word anywhere."""
    from onetrace_console.frame import PAGE_CSS
    return [sel.strip() for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", PAGE_CSS)
            if re.search(r"overflow-wrap:\s*anywhere|word-break:\s*break-(all|word)", body)]


def _parts(selector: str) -> set[str]:
    inner = re.search(r":is\(([^()]*)\)", selector)
    return {p.strip() for p in (inner.group(1) if inner else selector.split()[-1]).split(",")}


def test_break_anywhere_reaches_only_the_digest_and_annotation_cells(examined):
    rules = [s for s in _break_rules() if "data-section=changes" in s]
    examined(len(rules), "break-anywhere rules on the changes table")
    for selector in rules:
        assert _parts(selector) <= BREAKABLE, (
            f"a changes-table cell that is not a digest or an annotation breaks anywhere: "
            f"{selector}")
    assert set().union(*map(_parts, rules)) == BREAKABLE


def _rows(page: str) -> list[list[str]]:
    table = re.search(r'<table data-section="changes".*?</table>', page, re.S)
    assert table, "no changes table"
    body = table.group(0).split("<tbody>", 1)[1]
    return [re.findall(r"<td[^>]*>", row) for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S)]


def _breaks(cell: str) -> bool:
    """Whether the cell's opening tag carries an attribute one of the BREAKABLE selectors names."""
    return any(f'{attr}="{value}"' in cell
               for attr, value in (re.match(r"td\[([\w-]+)=([\w-]+)\]", s).groups()
                                   for s in BREAKABLE))


def test_a_graph_comparisons_node_names_are_not_cells_the_rule_breaks(dag_pages, examined):
    rows = _rows(dag_pages["PR"])
    examined(len(rows), "node rows")
    for cells in rows:
        node, annotations = cells[1], cells[4]
        assert not _breaks(node), f"a node name's cell breaks anywhere: {node}"
        assert _breaks(annotations), f"the annotations cell does not break: {annotations}"


def test_a_linear_comparisons_digests_are_the_cells_that_break(compared, examined):
    comparison, store = compared
    rows = _rows(render_diff(comparison, store, generated_at=GENERATED_AT))
    examined(len(rows), "stage rows")
    for cells in rows:
        stage, baseline, candidate = cells[1], cells[2], cells[3]
        assert not _breaks(stage), f"a stage name's cell breaks anywhere: {stage}"
        assert _breaks(baseline) and _breaks(candidate), "a digest cell does not break"
