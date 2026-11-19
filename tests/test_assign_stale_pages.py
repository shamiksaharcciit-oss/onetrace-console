"""After `run assign`, no page of the run's old team still names it.

The assign took away the run's own pages under its old key, but not the other pages of the old team's set that name
it (its pipeline's choose page, an incidents page), which the next start does not draw again for that team. So the
old team's viewer was still served a page naming a run moved to another team. Read here on the demo split between two
teams, a team-A run moved to team B, the pages drawn again as a start draws them.
"""

from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

from tests.test_team_pages import TEAMS, A, B, split_demo
from tests.test_team_serving import CLIENT, TENANT, get


def _files(folder: Path) -> dict[str, bytes]:
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*.html") if p.is_file()}


def test_after_assign_the_old_team_s_set_names_the_run_nowhere_and_its_old_pages_answer_404(
    shared_demo, tmp_path, examined
):
    from onetrace_console.config import Config
    from onetrace_console.serve import PAGES_DIRNAME, Handler, _render_startup_pages
    from onetrace_console.sessions import SessionStore
    from onetrace_console.store import Store
    from onetrace_console.team_assign import assign
    from onetrace_console.team_view import TeamView
    from tests.conftest import serving

    root, store = split_demo(shared_demo, tmp_path / "demo")
    config = Config(
        sign_in={
            "enabled": True,
            "method": "oidc",
            "public_url": "http://127.0.0.1",
            "insecure_cookie_for_local_dev": True,
            "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "X", "session_max_hours": 8},
        },
        teams=TEAMS,
    )
    _render_startup_pages(store, root, config)
    a_set = root / PAGES_DIRNAME / "t" / A
    a_only = {r.key for r in TeamView(store, A).runs()} - {r.key for r in TeamView(store, B).runs()}
    before = _files(a_set)
    #: The team-A run the most of team A's pages name.
    key = max(sorted(a_only), key=lambda k: sum(k.encode() in b for b in before.values()))
    named_before = sorted(rel for rel, b in before.items() if key.encode() in b and not rel.startswith(f"runs/{key}/"))
    moved = assign(store, root, store.get_run(key), B)
    again = Store(root / "store")
    _render_startup_pages(again, root, config)
    after = _files(a_set)
    stale = sorted(rel for rel, b in after.items() if moved.old_key.encode() in b or moved.new_key.encode() in b)
    examined(len(named_before), "pages of team A's set that named the run besides its own")
    assert named_before, "the run is named on other pages of its team's set: the case this test reads"
    assert stale == [], stale
    #: Served to team A's viewer: each page that named it answers 404 now.
    (tmp_path / "srv").mkdir()
    with serving(tmp_path / "srv") as (base, _empty):
        names = ("store", "store_root", "config", "session_store")
        saved = {n: getattr(Handler, n, None) for n in names}
        try:
            Handler.store, Handler.store_root = again, root
            Handler.config = replace(config, sign_in={**config.sign_in, "public_url": base})
            Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
            s = Handler.session_store.create(
                f"{TENANT}/aaaaaaaa-0000-0000-0000-000000000000",
                role="viewer",
                display_name="v",
                expires_at=time.time() + 600,
                teams=(A,),
            )
            headers = {
                "Accept": "text/html",
                "Cookie": f"onetrace_session={s.session_id}; onetrace_csrf={s.csrf_token}",
            }
            for rel in named_before:
                if rel in after:
                    continue
                status, body, _ = get(base, "/" + rel, headers)
                #: The answer of a page not drawn, which echoes the address asked for (the old key is in it); it names
                #: the run where it is now nowhere.
                assert status == 404 and moved.new_key.encode() not in body, (rel, status)
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)
