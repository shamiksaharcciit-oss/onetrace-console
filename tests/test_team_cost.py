"""The cost of drawing per team, measured on the demo split into three teams.

With team sets, a start draws every set, and a delivery redraws its own team's lists and the all-teams lists. This
measures, on a copy of the public demo whose runs are dealt among three teams in turn, the start with teams and
without, and the lists a delivery redraws with teams and without. The seconds are stated in the run's report of what
each check examined; the check holds that each set was drawn and that each team's set holds a third of the runs.
Each is measured twice, in turn, and the faster kept. Timing is never asserted: a slow machine is not a failure.
A team's view keeps a reading of its own (`TeamView._read`), so what the pages compute once per reading is computed
once per team, not once per page.
"""

from __future__ import annotations

import time
from dataclasses import replace

import pytest

TEAMS3 = {t: {"role_claim": f"Team.{t.title()}"} for t in ("alpha", "beta", "gamma")}


def test_the_cost_of_a_redraw_on_the_demo_split_into_three_teams(shared_demo, tmp_path, examined):
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_all_pages, _render_startup_pages
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path / "demo")
    store = Store(folder / "store" / "store")
    runs = sorted(store.runs(), key=lambda r: r.key)
    names = list(TEAMS3)
    for i, run in enumerate(runs):
        store.put_run(replace(run, team=names[i % 3]))
    store, root = Store(folder / "store" / "store"), folder / "store"
    without = Config(sign_in={**Config().sign_in, "enabled": False})
    with_teams = replace(without, teams=TEAMS3)

    def timed(draw) -> float:
        started = time.perf_counter()
        draw()
        return time.perf_counter() - started

    #: Each measured twice, in turn, and the faster kept: the first start reads the store cold.
    starts = {"without": [], "with": []}
    lists = {"without": [], "with": []}
    for _ in range(2):
        starts["without"].append(timed(lambda: _render_startup_pages(store, root, without)))
        starts["with"].append(timed(lambda: _render_startup_pages(store, root, with_teams)))
        lists["without"].append(timed(lambda: _render_all_pages(store, root, without)))
        lists["with"].append(timed(lambda: _render_all_pages(store, root, with_teams, only=("beta",))))
    start_without, start_with = min(starts["without"]), min(starts["with"])
    lists_without, lists_with = min(lists["without"]), min(lists["with"])

    for t in names:
        drawn = {p.name for p in (root / "pages" / "t" / t / "runs").iterdir()}
        assert drawn == {r.key for i, r in enumerate(runs) if names[i % 3] == t}
        assert len(runs) // 3 <= len(drawn) <= len(runs) // 3 + 1
    examined(
        len(runs),
        f"runs dealt among three teams; a start {start_without:.1f} s without teams, "
        f"{start_with:.1f} s with ({start_with / start_without:.2f}x)",
    )
    examined(
        3,
        f"team sets; a delivery's lists {lists_without:.2f} s without teams, {lists_with:.2f} s with its "
        f"team's ({lists_with / lists_without:.2f}x)",
    )


def test_a_team_s_view_keeps_a_reading_of_its_own(drawn_store, examined):
    """In a reading, a view's cache (`_read`) is a dict of its own: not the store's, which holds every team's, nor
    another team's; outside a reading, none; a write through the store forgets it with the rest."""
    from onetrace_console.team_view import TeamView

    store = drawn_store
    a, b = TeamView(store, "alpha"), TeamView(store, "beta")
    assert a._read() is None
    with store.reading():
        mine = a._read()
        assert isinstance(mine, dict) and mine is a._read()
        assert mine is not store._read() and mine is not b._read()
        mine["planted"] = 1
        store._forget()
        assert "planted" not in a._read()
    examined(3, "views' readings: in, out of, and after a write in a reading")


@pytest.fixture
def drawn_store(shared_demo, tmp_path):
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path / "demo")
    store = Store(folder / "store" / "store")
    for i, run in enumerate(sorted(store.runs(), key=lambda r: r.key)):
        store.put_run(replace(run, team=("alpha", "beta")[i % 2]))
    return Store(folder / "store" / "store")
