"""A team's view says what the last derivation over it could not derive (`incidents.derive`), as a store does, and
none before any: a team's Home, drawn by a view made afresh, read the store's attribute and failed to draw."""

from __future__ import annotations


def test_a_fresh_team_view_holds_no_underived_and_its_home_draws(shared_demo, tmp_path, examined):
    from dataclasses import replace

    from onetrace_console.render import render_home
    from onetrace_console.store import Store
    from onetrace_console.team_view import TeamView
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path / "demo")
    store = Store(folder / "store" / "store")
    for run in store.runs():
        store.put_run(replace(run, team="alpha"))
    view = TeamView(store, "alpha")
    assert view.underived == ()
    page = render_home(view, generated_at="2026-01-01T00:00:00+00:00")
    assert 'data-section="underived"' not in page and "<html" in page
    examined(2, "a fresh view's underived, and its Home drawn")
