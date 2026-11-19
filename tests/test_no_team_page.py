"""A person in no team: signed in through Entra ID with a role and no team, they get a
page saying so, "You are in no team. Ask your administrator to add you.", the same for every path asked, naming no
team. A person in a team gets their team's pages, and an admin every team's."""

from __future__ import annotations

import urllib.error
import urllib.request

from tests.http_limits import limit
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - the fake Entra ID's console, requested by name
from tests.test_team_pages import TEAMS


def _get(base: str, path: str, session: str) -> tuple[int, str]:
    req = urllib.request.Request(base + path, headers={"Cookie": f"onetrace_session={session}"})
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def test_a_person_in_no_team_gets_a_page_saying_so_naming_no_team(entra, examined):  # noqa: F811
    from dataclasses import replace

    from onetrace_console.serve import Handler
    from onetrace_console.team_assign import NO_TEAM

    base, fake, _root = entra
    Handler.config = replace(Handler.config, teams=TEAMS)
    assert NO_TEAM == "You are in no team. Ask your administrator to add you."
    session = sign_in(base, fake, roles=("onetrace.viewer",))[3]
    answers = [
        _get(base, path, session)
        for path in ("/", "/home.html", "/runs", "/t/alpha/home.html", "/runs/" + "0" * 64 + "/case.html")
    ]
    assert {status for status, _ in answers} == {403}
    bodies = {body for _, body in answers}
    assert len(bodies) == 1, "the same page for every path: it tells nothing of what is there"
    page = bodies.pop()
    assert NO_TEAM in page
    assert not any(team in page for team in TEAMS), "it names no team"
    #: A person in a team is answered with their team's pages, not this one.
    in_alpha = sign_in(base, fake, roles=("onetrace.viewer", "Team.Alpha"))[3]
    status, page = _get(base, "/home.html", in_alpha)
    assert status != 403 and NO_TEAM not in page, (
        "their team's set is read (here not drawn: answered as a page not drawn)"
    )
    examined(len(answers) + 1, "pages asked for")
