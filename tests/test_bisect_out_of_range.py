"""A time the bisect page cannot place in UTC is a refused input, never a 500.

An instant before year 1 once its offset is taken away (`0001-01-01T00:00:00+23:59`) was read, then raised
`OverflowError` where it was turned to UTC: the page answered 500. It is now read as a time that can't be read, as a
malformed one is. Read on the suite's two-team console, with the same date's other sign and the
far end of the range beside it. Asked as the admin, the one role that reads the whole console.
"""

from __future__ import annotations

from tests.test_team_pages import A, B
from tests.test_team_serving import console, get, session  # noqa: F401 - the fixture, requested by name

HTML = {"Accept": "text/html"}


def test_a_time_out_of_range_is_refused_and_the_page_answers(console, examined):  # noqa: F811
    from onetrace_console.bisect_page import read_time

    base, _store, _views, _config = console
    #: As the admin, who reads the whole console: a team's own set does not reach the time's use here.
    headers = {**HTML, **session("admin", (A, B))}
    asked = {
        "before year 1 in UTC": "/bisect?p=P1&after=0001-01-01T00:00:00%2B23:59",
        "the other sign": "/bisect?p=P1&after=0001-01-01T00:00:00-23:59",
        "the far end": "/bisect?p=P1&before=9999-12-31T23:59:59-23:59",
    }
    got = {k: get(base, q, headers)[0] for k, q in asked.items()}
    examined(len(got), "times asked")
    assert got == dict.fromkeys(asked, 200), got
    assert read_time("0001-01-01T00:00:00+23:59") == (None, False)
