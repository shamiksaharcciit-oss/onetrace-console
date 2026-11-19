"""The frame under teams: a sealed page of a team's set states its team in its sealed footer, never
the person; an unsealed page, as it is served, names the team read and, where the person has more than one team, a
switcher to each of the others; an admin's switches between every team and the all-teams set. A console without teams
draws no team line. And `explain/state`, the one GET that takes a comparison's key in its query, answers another team's
key as an unknown one.
"""

from __future__ import annotations

import re

from tests.test_team_pages import A, B
from tests.test_team_serving import UNKNOWN, console, get, session  # noqa: F401 - the served split demo

TEAM_LINE = re.compile(r'<div data-frame="team">(.*?)</div>', re.S)


def test_a_sealed_page_of_a_team_s_set_states_its_team_and_never_the_person(console, examined):  # noqa: F811
    from onetrace_console.serve import Handler

    _base, _store, views, _config = console
    root = Handler.store_root / "pages"
    key = views[B].runs()[0].key
    sealed = (root / "t" / B / "runs" / key / "case.html").read_text(encoding="utf-8")
    assert TEAM_LINE.findall(sealed) == ["Team: beta"]
    assert "Signed in as" not in sealed
    whole = (root / "runs" / key / "case.html").read_text(encoding="utf-8")
    assert TEAM_LINE.findall(whole) == []
    examined(2, "a run's case page, sealed in its team's set and in the all-teams set")


def test_an_unsealed_page_names_the_team_and_switches_between_the_person_s_teams(console, examined):  # noqa: F811
    base, _store, _views, _config = console
    lines = {}
    for who, headers in (
        ("one", session("viewer", (B,))),
        ("two", session("viewer", (A, B))),
        ("admin", session("admin", ())),
    ):
        status, body, _ = get(base, "/", headers)
        assert status == 200, who
        lines[who] = TEAM_LINE.findall(body.decode())
    assert lines["one"] == ["Team: beta"]
    (two,) = lines["two"]
    assert two.startswith("Team: alpha") and 'href="/t/beta/"' in two and 'href="/t/alpha/"' not in two
    (admin,) = lines["admin"]
    assert admin.startswith("All teams") and 'href="/t/alpha/"' in admin and 'href="/t/beta/"' in admin
    status, body, _ = get(base, "/t/beta/", session("admin", ()))
    (in_beta,) = TEAM_LINE.findall(body.decode())
    assert in_beta.startswith("Team: beta") and 'href="/"' in in_beta and 'href="/t/alpha/"' in in_beta
    examined(4, "Overviews served to a person in one team, in two, and to an admin in two sets")


def test_a_console_without_teams_draws_no_team_line(shared_demo, examined):
    pages = shared_demo["folder"] / "store" / "pages"
    read = 0
    for path in list(pages.glob("*.html"))[:40] + list((pages / "runs").glob("*/case.html"))[:10]:
        assert 'data-frame="team"' not in path.read_text(encoding="utf-8"), path.name
        read += 1
    examined(read, "the demo's pages, drawn without teams")


def test_explain_state_of_another_team_s_comparison_answers_as_an_unknown_one(console, examined):  # noqa: F811
    base, _store, views, _config = console
    beta = session("investigator", (B,))
    key = views[A].comparisons()[0].key
    outside = get(base, f"/explain/state?c={key}", beta)
    unknown = get(base, f"/explain/state?c={UNKNOWN}", beta)
    assert outside[0] == unknown[0] and outside[1].replace(key.encode(), b"K") == unknown[1].replace(
        UNKNOWN.encode(), b"K"
    )
    own = views[B].comparisons()[0].key
    assert get(base, f"/explain/state?c={own}", beta)[0] == 200
    examined(3, "explain states asked for")
