"""One page set per team: `pages/t/<team>/`, each drawn from the team's view, beside the all-teams
set.

On a copy of the public demo, P1's runs are split between two teams, which share its stage list, and every other run
is the first team's; the console is configured with both teams and draws its pages as it does at start:

- for each page kind the drawing writes, the second team's set names no run key and no run id of the first's, and the
  first's none of the second's;
- each set holds its own team's run pages and comparisons, and its run index lists its own runs only; the all-teams
  set holds every run, as before;
- a run page's cross-run facts are the team's: every run a team's page links to is in that team's set;
- a record no one can read is said in the all-teams set only;
- a console without teams draws no team set.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

A, B = "alpha", "beta"
TEAMS = {A: {"role_claim": "Team.Alpha"}, B: {"role_claim": "Team.Beta"}}
_HEX64 = re.compile(r"(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])")


def split_demo(shared_demo, dest):
    """A copy of the demo with P1's runs split between the two teams; every other run the first's."""
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, dest)
    store = Store(folder / "store" / "store")
    p1 = next(p for p in pipelines(store) if p.label == "P1")
    team_of = {r.key: (A if i % 2 == 0 else B) for i, r in enumerate(p1.runs)}
    for run in store.runs():
        store.put_run(replace(run, team=team_of.get(run.key, A)))
    return folder / "store", Store(folder / "store" / "store")


@pytest.fixture(scope="module")
def drawn(shared_demo, tmp_path_factory):
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages

    root, store = split_demo(shared_demo, tmp_path_factory.mktemp("team-pages") / "demo")
    config = Config(sign_in={**Config().sign_in, "enabled": False}, teams=TEAMS)
    _render_startup_pages(store, root, config)
    keys = {t: {r.key for r in store.runs() if r.team == t} for t in (A, B)}
    ids = {t: {r.run_id for r in store.runs() if r.team == t} for t in (A, B)}
    return root, store, keys, ids


def _files(folder):
    return sorted(p for p in folder.rglob("*") if p.is_file())


def _kind(rel: str) -> str:
    """A page's kind: its path with each key and number taken out."""
    return re.sub(r"[0-9]+", "N", _HEX64.sub("K", rel))


@pytest.mark.parametrize("team, other", [(B, A), (A, B)])
def test_a_team_s_set_names_no_run_key_or_run_id_of_another_team(drawn, team, other, examined):
    root, _store, keys, ids = drawn
    folder = root / "pages" / "t" / team
    only_other_ids = ids[other] - ids[team]
    assert only_other_ids, "the split leaves each team run ids of its own"
    kinds, files = set(), 0
    for path in _files(folder):
        text = path.read_text(encoding="utf-8", errors="replace")
        named = set(_HEX64.findall(text)) | set(_HEX64.findall(path.relative_to(folder).as_posix()))
        assert not named & keys[other], (path.relative_to(folder).as_posix(), sorted(named & keys[other])[:2])
        held = [i for i in only_other_ids if i in text]
        assert not held, (path.relative_to(folder).as_posix(), held[:2])
        kinds.add(_kind(path.relative_to(folder).as_posix()))
        files += 1
    examined(files, f"files in {team}'s set, of {len(kinds)} kinds, read for {other}'s keys and run ids")


def test_each_set_holds_its_team_s_runs_and_comparisons_and_the_all_teams_set_holds_every_run(drawn, examined):
    from onetrace_console.team_view import TeamView

    root, store, keys, _ids = drawn
    pages = root / "pages"
    for team in (A, B):
        folder = pages / "t" / team
        drawn_runs = {p.name for p in (folder / "runs").iterdir()}
        assert drawn_runs == keys[team]
        view = TeamView(store, team)
        drawn_diffs = {p.name[:64] for p in (folder / "diff").glob("*.html")}
        assert drawn_diffs == {c.key[:64] for c in view.comparisons()}
        index = json.loads((folder / "run_index.json").read_text(encoding="utf-8"))
        assert {r["key"] for r in index["runs"]} == keys[team]
        for kind in ("home.html", "comparisons.html", "incidents.html", "pipeline-p1.html", "choose-p1.html"):
            assert (folder / kind).is_file(), (team, kind)
    assert {p.name for p in (pages / "runs").iterdir()} == keys[A] | keys[B]
    whole = json.loads((root / "run_index.json").read_text(encoding="utf-8"))
    assert {r["key"] for r in whole["runs"]} == keys[A] | keys[B]
    examined(len(keys[A]) + len(keys[B]), "runs drawn in their team's set and in the all-teams set")


def test_a_run_page_s_cross_run_facts_are_the_team_s(drawn, examined):
    """Every run a page of a team's set links to (`runs/<key>/`) has its pages in that set: "This step in the other
    runs", "Other runs with the same inputs", the pipeline's lists, the Choose pages."""
    root, _store, keys, _ids = drawn
    linked = 0
    for team in (A, B):
        folder = root / "pages" / "t" / team
        for path in _files(folder):
            if path.suffix != ".html":
                continue
            for key in re.findall(r"runs/([0-9a-f]{64})/", path.read_text(encoding="utf-8")):
                assert key in keys[team], (team, path.relative_to(folder).as_posix(), key)
                linked += 1
    examined(linked, "links to a run from a team's set, each to a run of that team")


def test_a_team_s_view_has_no_unreadable_record_the_all_teams_set_says_it(drawn, examined):
    from onetrace_console.team_view import TeamView

    _root, store, _keys, _ids = drawn
    view = TeamView(store, B)
    assert view.unreadable_runs == () and view.unreadable_comparisons == ()
    assert view.unreadable_run_keys == () and view.unreadable_comparison_keys == ()
    examined(4, "a team's view's counts of unreadable records")


def test_a_console_without_teams_draws_no_team_set(shared_demo, examined):
    pages = shared_demo["folder"] / "store" / "pages"
    assert (pages / "home.html").is_file()
    assert not (pages / "t").exists()
    examined(1, "the demo's pages, drawn without teams")


def test_teams_is_a_key_of_its_own_and_a_public_console_refuses_it(tmp_path, examined):
    from onetrace_console.config import ConfigError, load

    good = tmp_path / "good.json"
    good.write_text(json.dumps({"teams": TEAMS}), encoding="utf-8")
    assert load(good).teams == TEAMS
    for name, data, said in (
        ("public", {"public": True, "teams": TEAMS}, "public is true and teams is set"),
        ("shape", {"teams": ["alpha"]}, "teams must be an object"),
        ("entry", {"teams": {"alpha": "Team.Alpha"}}, "teams.alpha must be an object"),
        ("inner", {"teams": {"alpha": {"label": "x"}}}, "unknown key(s) ['label'] in teams.alpha"),
        ("text", {"teams": {"alpha": {"role_claim": 3}}}, "teams.alpha.role_claim must be text"),
    ):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ConfigError, match=re.escape(said)):
            load(path)
    examined(6, "configuration files with teams")


def test_no_page_fails_in_a_team_s_set_that_draws_in_the_all_teams_set(drawn, examined):
    """`render_all` draws a page that failed as a page saying so; a team's view must draw each page the store does."""
    root, _store, _keys, _ids = drawn
    pages, failed = root / "pages", 'data-section="page-failed"'
    read = 0
    for team in (A, B):
        folder = pages / "t" / team
        for path in _files(folder):
            if path.suffix != ".html":
                continue
            rel = path.relative_to(folder).as_posix()
            if failed in path.read_text(encoding="utf-8"):
                whole = pages / rel
                assert whole.is_file() and failed in whole.read_text(encoding="utf-8"), (team, rel)
            read += 1
    examined(read, "pages of the teams' sets, read for a page that failed")


def test_an_origin_in_another_team_reads_to_a_team_byte_for_byte_as_one_not_held(tmp_path, examined):
    """The origin page, the case page's "Called by" and the origin's list, read by team B where the origin names team
    A's run, are the bytes drawn where no run of that id is held: another team's run reads as no run."""
    from onetrace_console import run_index, service_link
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from onetrace_console.team_view import TeamView
    from tests.test_service_link import HERE, RAN_AT, _section, _store

    def teamed(where, folders, team_of):
        store, keys = _store(where, folders)
        for run in store.runs():
            store.put_run(replace(run, team=team_of[run.run_id]))
        return Store(where / "store"), keys

    both, keys = teamed(
        tmp_path / "both",
        {n: HERE / n for n in ("link-desk", "link-billing")},
        {
            "link-desk": A,
            "link-billing": B,
        },
    )
    alone, alone_keys = teamed(tmp_path / "alone", {"link-billing": HERE / "link-billing"}, {"link-billing": B})
    assert keys["link-billing"] == alone_keys["link-billing"]

    def read_by_b(store):
        view = TeamView(store, B)
        service_link.keep_linked_checks(view)
        index = run_index.build(view)
        with run_index.drawing(index):
            case = render_execution(view.get_run(keys["link-billing"]), view, generated_at=RAN_AT).pages["case.html"]
        return _section(case, "called-by"), service_link.origin_pages(index, RAN_AT)

    called_by, origin = read_by_b(both)
    assert called_by and list(origin) == ["origin-link-desk.html"]
    assert keys["link-desk"] not in called_by + "".join(origin.values())
    assert (called_by, origin) == read_by_b(alone)
    #: The all-teams set draws the origin across teams: the caller is linked there.
    with run_index.drawing(run_index.build(both)):
        whole = render_execution(both.get_run(keys["link-billing"]), both, generated_at=RAN_AT).pages["case.html"]
    assert keys["link-desk"] in _section(whole, "called-by")
    examined(3, "the Called by section, the origin page and its list, read by the callee's team")
