"""Whether a run closed, and how it ended, in the record's own words.

onetrace 0.7 (format 0.4, onetrace's `docs/format.md`, "The close receipt") ends every run it closes
with a close receipt, whose constant `onetrace.ended_by` says how it ended: `exit`, `unhandled
exception: <class>`, `SIGTERM`, or one of the two `re-run stopped` forms. A run with no close receipt
was killed, ended without closing, or was written before format 0.4, and its record cannot tell which:
it reads "not closed", never "finished". The words are onetrace-verify's own row's, `the close
receipt`: `closed: by <onetrace.ended_by>`, or `not closed: the record ends at <last step> and holds
no close`.

What is read is kept with the run when it is checked (`checks.derived_from`, the run's `ending`), so
its page, its row in the runs list and its head say the same.
"""
from __future__ import annotations

from pathlib import Path

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

#: onetrace-verify 0.7's own words for its row `the close receipt`.
CLOSED = "closed: by {ended_by}"
NOT_CLOSED = "not closed: the record ends at {last} and holds no close"
#: Where the record could not be read for its steps: no close receipt was read, and nothing more.
NOT_CLOSED_UNREAD = "not closed: no close receipt was read"
#: A close receipt that states no `onetrace.ended_by`, which onetrace-verify 0.7 reads as a FAIL.
CLOSED_UNSTATED = "closed: its close receipt states no onetrace.ended_by"
#: The runs list's column.
COLUMN = "Closed"
ENDED_BY = "onetrace.ended_by"


def ending_of(folder: Path) -> dict:
    """{"closed": bool, "ended_by": str, "last": str} for the run in `folder`, read as its pages read
    it (`viewer.record.read_record`): the close receipt's own `onetrace.ended_by`, or the last
    step's name where there is no close receipt."""
    from onetrace_console.viewer.record import read_record
    record = read_record(folder)
    if record.close is not None:
        constants = (record.close.data.get("assertions") or {}).get("constants") or {}
        ended_by = constants.get(ENDED_BY) if isinstance(constants, dict) else None
        return {"closed": True, "ended_by": ended_by if isinstance(ended_by, str) else "", "last": ""}
    last = ""
    if record.steps:
        stage = record.steps[-1].data.get("stage")
        last = stage.get("name", "") if isinstance(stage, dict) and isinstance(stage.get("name"), str) else ""
    return {"closed": False, "ended_by": "", "last": last}


def read(kept: str) -> dict | None:
    """A run's kept `ending`, or None where none was kept."""
    try:
        got = load_json_bounded(kept, "the run's kept ending") if kept else None
    except (ValueError, RecursionError):
        return None
    return got if isinstance(got, dict) and isinstance(got.get("closed"), bool) else None


def state(kept: str) -> str:
    """`closed` or `not-closed`: never anything that reads as finished."""
    got = read(kept)
    return "closed" if got is not None and got["closed"] else "not-closed"


def said(kept: str) -> str:
    """The words, plain."""
    got = read(kept)
    if got is None:
        return NOT_CLOSED_UNREAD
    if got["closed"]:
        return CLOSED.format(ended_by=got["ended_by"]) if got.get("ended_by") else CLOSED_UNSTATED
    return NOT_CLOSED.format(last=got["last"]) if got.get("last") else NOT_CLOSED_UNREAD


def html(kept: str) -> str:
    """The words, with what the record says marked as the record's."""
    got = read(kept)
    if got is not None and got["closed"] and got.get("ended_by"):
        return _marked(CLOSED, "{ended_by}", got["ended_by"])
    if got is not None and not got["closed"] and got.get("last"):
        return _marked(NOT_CLOSED, "{last}", got["last"])
    return escape(said(kept))


def _marked(words: str, slot: str, value: str) -> str:
    before, after = words.split(slot, 1)
    return f'{escape(before)}<span class="mono" data-words="record">{escape(value)}</span>{escape(after)}'

