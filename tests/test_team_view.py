"""A team's view of the store: its runs, comparisons and kept records, and nothing else.

On a copy of the public demo, P1's runs are split between two teams, which share its stage list, and every other run
is the first team's:

- a team's view answers `runs()`, `comparisons()`, `get_run()` and `get_comparison()` with its own records only, and
  `None` for the other team's keys and for unknown keys alike;
- pipelines are grouped and labelled within a team, so each team has its own P1;
- a benchmark marked in one team does not change the other's reference;
- kept records (references, verdicts, profiles, linked checks), drift, benchmarks' marks, what was kept beside a run
  and expectations declared after it are read per team;
- no module reads a folder under the store's root except through the view: a test over the source.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
A, B = "alpha", "beta"


@pytest.fixture(scope="module")
def teamed(shared_demo, tmp_path_factory):
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path_factory.mktemp("teams") / "demo")
    store = Store(folder / "store" / "store")
    p1 = next(p for p in pipelines(store) if p.label == "P1")
    p1_keys = [r.key for r in p1.runs]
    team_of = {k: (A if i % 2 == 0 else B) for i, k in enumerate(p1_keys)}
    for run in store.runs():
        store.put_run(replace(run, team=team_of.get(run.key, A)))
    store = Store(folder / "store" / "store")
    return store, {k for k, t in team_of.items() if t == B}, p1.stages


def _views(store):
    from onetrace_console.team_view import TeamView

    return TeamView(store, A), TeamView(store, B)


def test_a_team_s_view_answers_its_own_and_none_for_another_s_key_or_an_unknown_one(teamed, examined):
    store, beta_keys, _stages = teamed
    a, b = _views(store)
    alpha_keys = {r.key for r in store.runs()} - beta_keys
    examined(len(alpha_keys) + len(beta_keys), "runs, split between two teams")
    assert {r.key for r in a.runs()} == alpha_keys and {r.key for r in b.runs()} == beta_keys
    unknown = "0" * 64
    for key in beta_keys:
        assert a.get_run(key) is None and b.get_run(key) is not None
    assert a.get_run(unknown) is None and b.get_run(unknown) is None
    for c in store.comparisons():
        inside_a = c.run_a in alpha_keys and c.run_b in alpha_keys
        assert (a.get_comparison(c.key) is not None) == inside_a, c.key
    assert all(c.run_a in alpha_keys and c.run_b in alpha_keys for c in a.comparisons())
    assert a.get_comparison(unknown) is None
    run_id = store.get_run(next(iter(beta_keys))).run_id
    assert all(r.team == A for r in a.runs_with_id(run_id))


def test_pipelines_are_grouped_and_labelled_within_a_team(teamed, examined):
    from onetrace_console.overview import pipelines

    store, beta_keys, stages = teamed
    a, b = _views(store)
    p_a = {p.label: p for p in pipelines(a)}
    p_b = {p.label: p for p in pipelines(b)}
    examined(2, "teams with one stage list between them")
    assert p_b["P1"].stages == stages and {r.key for r in p_b["P1"].runs} == beta_keys
    assert p_a["P1"].stages == stages and not ({r.key for r in p_a["P1"].runs} & beta_keys)
    assert list(p_b) == ["P1"], "the second team's own pipelines only"


def test_a_benchmark_marked_in_one_team_does_not_change_another_s_reference(teamed, examined):
    from onetrace_console import benchmarks
    from onetrace_console.overview import pipelines
    from onetrace_console.team_view import TeamView
    from onetrace_console.verdicts import chosen

    store, beta_keys, _stages = teamed
    a, b = _views(store)
    b_p1 = next(p for p in pipelines(b) if p.label == "P1")
    before = chosen(b_p1, b)
    a_p1 = next(p for p in pipelines(a) if p.label == "P1")
    marked = a_p1.runs[-1]
    benchmarks.mark(a, marked, who="a test", when="2099-01-01T00:00:00+00:00")
    try:
        b_again = TeamView(store, B)
        after = chosen(next(p for p in pipelines(b_again) if p.label == "P1"), b_again)
        examined(1, "mark in one team")
        assert (before or {}).get("benchmark") == (after or {}).get("benchmark")
        assert marked.key not in benchmarks.marks(b_again)
        assert marked.key in benchmarks.marks(TeamView(store, A))
        with pytest.raises(benchmarks.MarkError):
            benchmarks.mark(b_again, marked, who="a test")
    finally:
        benchmarks.unmark(store, marked.key)


def test_kept_records_drift_and_kept_files_are_read_per_team(teamed, examined):
    from onetrace_console import beside, expectations_after

    store, beta_keys, _stages = teamed
    a, b = _views(store)
    beta = sorted(beta_keys)
    alpha = sorted({r.key for r in store.runs()} - beta_keys)
    kept = {
        "references": {"key": "1" * 64, "runs": beta[:2]},
        "verdicts": {"key": "2" * 64, "run": beta[0]},
        "profiles": {"key": "3" * 64, "runs": beta[:2]},
        "linked_checks": {"key": "4" * 64, "caller": beta[0], "callee": beta[1]},
    }
    for kind, record in kept.items():
        store.put_kept(kind, record["key"], record)
    store.put_drift("5" * 64, {"runs": beta[:2]})
    store.put_drift("6" * 64, {"runs": [alpha[0], beta[0]]})
    beside.keep(store, beta[0], trace_source="given")
    examined(len(kept) + 3, "kept records, drift and a kept file")
    for kind, record in kept.items():
        assert a.get_kept(kind, record["key"]) is None, kind
        assert b.get_kept(kind, record["key"]) == record, kind
        with pytest.raises(ValueError):
            a.put_kept(kind, record["key"], record)
    assert a.get_drift("5" * 64) is None and b.get_drift("5" * 64) is not None
    assert a.get_drift("6" * 64) is None and b.get_drift("6" * 64) is None, "a drift over both teams is neither's"
    assert beside.read(a, beta[0]) == {} and beside.read(b, beta[0]).get("trace_source") == "given"
    assert a.kept_path("beside", beta[0]) is None and b.kept_path("beside", beta[0]) is not None
    with pytest.raises(expectations_after.ExpectationsError):
        expectations_after._path(a, beta[0])
    assert a.neighbours_root() != b.neighbours_root() != store.neighbours_root()


def test_a_run_record_s_team_is_kept_and_a_record_without_one_is_written_as_before(teamed, examined):
    from onetrace_console.store import StoredRun

    store, beta_keys, _stages = teamed
    run = store.get_run(next(iter(beta_keys)))
    examined(1, "run record")
    assert run.team == B and '"team": "beta"' in run.to_json()
    assert StoredRun.from_json(run.to_json()) == run
    plain = replace(run, team="")
    assert '"team"' not in plain.to_json() and StoredRun.from_json(plain.to_json()).team == ""
    with pytest.raises(ValueError, match="not a team's name"):
        StoredRun.from_json(plain.to_json().replace('"key":', '"team": "../x",\n "key":', 1))


# ------------------------------------------------------- no module reads under the store's root by path

#: (file, function) -> why it may read under the store's root by path: each reads what belongs to the whole
#: console, never a run's or a team's.
CONSOLE_WIDE = {
    ("explain.py", "too_long"): "the store's own path's length, for Windows' path limit; it reads no file",
    ("explain.py", "always_stop"): "Explain's 'always stop before sending', a setting of the whole console",
    ("explain.py", "set_always_stop"): "Explain's 'always stop before sending', a setting of the whole console",
    (
        "explain.py",
        "kept_record",
    ): "a public console's build record of the explanations it kept; a public console has no teams",
    (
        "explain.py",
        "keep",
    ): "a public console's build record of the explanations it kept; a public console has no teams",
    ("neighbours/settings.py", "_path"): "whether neighbours are on, a setting of the whole console",
    ("neighbours/embedder.py", "models_root"): "the embedder's model files, fetched once for the whole console",
    ("neighbours/fetching.py", "_key"): "the name a fetch's lock goes by, the store's own path; it reads no file",
    ("settings_menu.py", "tokenizers_row"): "the tokenizers kept by this console, a setting of the whole console",
    ("forward_pages.py", "root_of"): "trace forwarding's destinations and queue, a setting of the whole console",
    ("serve.py", "_tokenizers_page"): "the tokenizers kept by this console, a setting of the whole console",
    ("serve.py", "_handle_model_tokenizers"): "the tokenizers kept by this console, a setting of the whole console",
}


def _store_root_reads() -> list[tuple[str, str, int]]:
    """Every `<a store>.root` in the package, outside the store and the view: (file, innermost function, line)."""
    found = []
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC).as_posix()
        if rel in ("store.py", "team_view.py"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Attribute) and node.attr == "root"):
                continue
            v = node.value
            subject = v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else ""
            if subject not in ("store", "source_store"):
                continue
            around = [f for f in funcs if f.lineno <= node.lineno <= (f.end_lineno or f.lineno)]
            inner = min(around, key=lambda f: (f.end_lineno or f.lineno) - f.lineno) if around else None
            found.append((rel, inner.name if inner else "<module>", node.lineno))
    return sorted(found)


def test_no_module_reads_a_folder_under_the_store_s_root_except_through_the_view(examined):
    reads = _store_root_reads()
    examined(len(reads), "reads of a store's root by path")
    outside = [r for r in reads if (r[0], r[1]) not in CONSOLE_WIDE]
    assert outside == [], outside


def test_each_console_wide_read_is_still_there():
    used = {(r[0], r[1]) for r in _store_root_reads()}
    assert set(CONSOLE_WIDE) <= used, sorted(set(CONSOLE_WIDE) - used)
