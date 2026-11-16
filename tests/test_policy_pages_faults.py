"""Two reads on the onedoor Policy pages that raised on a value their own types allow:

- a held row whose delivery couldn't be read (`CheckedRow.delivered` None) is drawn with "delivery not readable",
  and the rest of the decision's page as before;
- a decision with no request id gets no link: its cell says "no request id", as the cell beside it already writes an
  empty value.

Each case constructed: the rows built as an export holds them.
"""

from __future__ import annotations

import json

from onetrace_console.onedoor_ext.decisions import CheckedRow, DecisionRow, StoredDecisionExport
from onetrace_console.onedoor_ext.policy_pages import Decision, _decision_row_html, render_decision_detail
from onetrace_console.store import Store


def _row(**fields) -> DecisionRow:
    return DecisionRow(raw_line=json.dumps(fields, sort_keys=True, separators=(",", ":")))


def _export(*rows: DecisionRow) -> StoredDecisionExport:
    return StoredDecisionExport(key="k" * 64, export_object="k" * 64, received_at="", rows=rows)


def test_a_held_row_whose_delivery_couldn_t_be_read_is_drawn_as_that(tmp_path, examined):
    row = _row(request_id="req-1", kind="decision", decision="allow", created_at="2026-11-09T12:00:00Z")
    export = _export(row)
    d = Decision((CheckedRow(export, 0, row, None), CheckedRow(export, 1, None, "the delivery cannot be read")))
    page = render_decision_detail(d, Store(tmp_path / "store"), generated_at="2026-11-09T12:00:00+00:00")
    examined(2, "the decision's page: its readable row, and the one that isn't")
    assert "delivery not readable" in page
    assert 'data-kind="decision"' in page and "Decision req-1" in page


def test_a_decision_with_no_request_id_gets_no_link_and_says_so(examined):
    row = _row(kind="decision", decision="allow", created_at="2026-11-09T12:00:00Z")
    d = Decision((CheckedRow(_export(row), 0, row, None),))
    drawn = _decision_row_html(d)
    examined(1, "the decision's row")
    assert d.request_id is None
    assert "<a " not in drawn and "no request id" in drawn
