"""The Tokenizers page lists only the runs the viewer's teams hold, as the Runs and Search pages do.

The page lists each model step that asks for a tokenizer, with a link to its run. With teams it read the whole store,
so a viewer of one team saw another team's runs named there. Read here through the suite's two-team console (P1's
runs split between teams A and B, sign-in through Entra ID).
"""

from __future__ import annotations

import re

from tests.test_team_pages import A, B
from tests.test_team_serving import console, get, session  # noqa: F401 - the fixture, requested by name

HTML = {"Accept": "text/html"}


def _linked(base, team) -> tuple[int, set[str]]:
    status, body, _ = get(base, "/model-tokenizers", {**HTML, **session("viewer", (team,))})
    return status, {k.decode() for k in re.findall(rb"/runs/([0-9a-f]{64})/", body)}


def test_a_viewer_sees_on_the_tokenizers_page_only_runs_of_their_teams(console, examined):  # noqa: F811
    base, _store, views, _config = console
    a, b = {r.key for r in views[A].runs()}, {r.key for r in views[B].runs()}
    status_a, seen_a = _linked(base, A)
    status_b, seen_b = _linked(base, B)
    examined(len(seen_a) + len(seen_b), "runs linked on the two teams' Tokenizers pages")
    assert status_a == status_b == 200
    #: Team A's viewer sees its runs that ask for a tokenizer; team B's sees none of them.
    assert seen_a and seen_a <= a
    assert seen_b <= b and not seen_b & (a - b), "a run of team A alone, listed to a team-B viewer"
