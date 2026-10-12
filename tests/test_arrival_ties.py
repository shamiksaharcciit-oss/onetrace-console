"""Two real runs can arrive in the same second: arrival is recorded to the second. Every ordering
the console makes by arrival breaks that tie by a field of the run itself, never by the order the
store happened to list or deliver them (a review question, 2 October, after the visible-text race).

- `store.runs()`: newest arrival first, then `run_id` (descending, with arrival), then the run's
  key, ascending -- records are named by their key and read in sorted order.
- `overview.pipelines()`: P1, P2 ... by first arrival, then by key.
- `overview.needs_attention()`: by kind, then newest arrival, then by key.

Each test gives the ordering the same tied runs in two different orders and requires one answer,
so a missing tiebreak shows as a difference every time, not by chance.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from onetrace_console.checks import HOLDS
from tests.test_home_and_diff import _fake_run, ten_runs  # noqa: F401  (fixture)

SAME = "2026-10-02T09:00:00+00:00"


def _all_at_one_second(store) -> list:
    for run in store.runs():
        store.put_run(replace(run, received_at=SAME))
    return list(store.runs())


def _given_in_order(monkeypatch, store, runs) -> None:
    monkeypatch.setattr(store, "runs", lambda: tuple(runs))


def test_pipelines_tied_on_arrival_are_labelled_by_key_whatever_order_they_are_given(
        ten_runs, monkeypatch, examined):  # noqa: F811
    from onetrace_console.overview import pipelines
    store, made = ten_runs
    #: A second pipeline whose run_id sorts after every other run's, so the store's own order
    #: (run_id descending) and its reverse would put different pipelines first.
    other = _fake_run(store, made[0], run_id="zz-other-pipeline", verdict=HOLDS)
    store.put_run(replace(other, declared_stages=("fetch", "answer"), stage_count=2,
                          recorded_count=2))
    runs = _all_at_one_second(store)
    examined(len(runs), "runs stored in one second, across two pipelines")
    first_by_key = min(runs, key=lambda r: r.key)

    labelled = []
    for given in (runs, list(reversed(runs))):
        _given_in_order(monkeypatch, store, given)
        labelled.append([(p.label, sorted(r.key for r in p.runs)) for p in pipelines(store)])
    assert labelled[0] == labelled[1], "the pipeline labels depend on the order the runs came in"
    p1 = pipelines(store)[0]
    assert first_by_key.key in {r.key for r in p1.runs}, "P1 is not the pipeline of the first key"


def test_needs_attention_tied_on_arrival_lists_each_kind_by_key_whatever_order_given(
        ten_runs, monkeypatch, examined):  # noqa: F811
    from onetrace_console.overview import needs_attention
    store, _ = ten_runs
    runs = _all_at_one_second(store)
    listed = []
    for given in (runs, list(reversed(runs))):
        _given_in_order(monkeypatch, store, given)
        listed.append([(kind, r.key) for kind, r in needs_attention(store)])
    examined(len(listed[0]), "runs needing attention, all arrived in one second")
    assert listed[0] == listed[1], "needs attention depends on the order the runs came in"
    for kind in {k for k, _ in listed[0]}:
        keys = [key for k, key in listed[0] if k == kind]
        assert keys == sorted(keys), (kind, "not by key within one arrival second")


class _ListedBackwards(type(Path())):
    """The runs folder, listing its records in reverse: the order a store happens to list in is
    not something the runs' order may depend on."""

    def glob(self, pattern):
        return reversed(list(super().glob(pattern)))


def test_store_runs_tied_on_arrival_are_by_run_id_then_key_whatever_the_listing(
        ten_runs, examined):  # noqa: F811
    store, made = ten_runs
    #: Two runs sharing a run_id (a reused one) and an arrival second: only the key separates them.
    from onetrace_console.store import run_key
    twin_a = _fake_run(store, made[0], run_id="twin", verdict=HOLDS)
    other_head = "sha256:" + "f" * 64
    store.put_run(replace(twin_a, chain_head=other_head, key=run_key("twin", other_head)))
    _all_at_one_second(store)
    store._runs = _ListedBackwards(store._runs)
    runs = store.runs()
    examined(len(runs), "runs stored in one second, two of them sharing a run_id")
    order = [(r.run_id, r.key) for r in runs]
    expected = sorted(order, key=lambda ik: ik[1])
    expected = sorted(expected, key=lambda ik: ik[0], reverse=True)
    assert order == expected, "not run_id descending, then key ascending, within one second"
    twins = [key for run_id, key in order if run_id == "twin"]
    assert len(twins) == 2 and twins == sorted(twins)


# ---------------------------------------------------------------------------------------------
# The product's own tiebreak, on two real runs ingested in one second.

README_LINE = "Runs that arrive in the same second are ordered by run key."


def _unlabelled(html: str) -> str:
    """The page without the narrow screen's column labels (`words.labelled`), so a table reads as
    its cells were drawn before them; nothing else changes."""
    import re as _re
    return _re.sub(r' data-label="[^"]*"', "", html)


def _pipeline_rows(home: str) -> list[tuple[str, str]]:
    """(label, declared stages) for each row of the Overview's pipelines table, as rendered."""
    import re
    from html import unescape
    return [(label, unescape(stages)) for label, stages in re.findall(
        r'<tr data-pipeline="[^"]*"><td>([^<]*)</td><td data-words="record">([^<]*)</td>',
        _unlabelled(home))]


def test_two_runs_ingested_in_one_second_p1_is_the_lower_key_across_renders_and_a_restart(
        tmp_path, examined):
    """Two real runs from different pipelines -- the committed r11 run and an SDK-made one --
    ingested with the same arrival second. P1 goes to the pipeline of the lower run key, and the
    labels are the same on every render and after a restart (a fresh store over the same folder,
    every page rebuilt from it as the console's start-up does)."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.overview import pipelines
    from onetrace_console.render import HOME, render_all, shown_name
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    from tests.conftest import REPO, _delivery_paths, make_tar
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_home_and_diff import GENERATED_AT
    from tests.test_diff_sdk_text_layer import _forged_pair
    from tests.test_unreadable import _resummed
    _require_installed()

    root = tmp_path / "console"
    store = Store(root / "store")
    r11 = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"
    r11_files = _resummed({p.relative_to(r11).as_posix(): p.read_bytes()
                           for p in _delivery_paths(r11)})
    (tmp_path / "held").mkdir()
    sdk_run, _ = _forged_pair(tmp_path / "held")
    stored = {}
    for name, files in (("r11", r11_files), ("sdk", sdk_run)):
        accepted = accept(make_tar(files), store, received_at=SAME)
        assert accepted.run is not None, getattr(accepted, "rows", accepted)
        stored[name] = run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)
    assert stored["r11"].received_at == stored["sdk"].received_at == SAME
    assert stored["r11"].declared_stages != stored["sdk"].declared_stages, "one pipeline, not two"
    lower = min(stored.values(), key=lambda r: r.key)
    p1_stages = " → ".join(shown_name(s) for s in lower.declared_stages)
    examined(2, "real runs from two pipelines, ingested in one arrival second")

    found = pipelines(store)
    assert [p.label for p in found] == ["P1", "P2"]
    assert [r.key for r in found[0].runs] == [lower.key], "P1 is not the lower run key's"

    renders = [_pipeline_rows(render_all(store, generated_at=GENERATED_AT)[HOME]) for _ in range(3)]
    assert renders[0][0] == ("P1", p1_stages), renders[0]
    assert renders[1] == renders[0] and renders[2] == renders[0], "the labels moved between renders"

    restarted = Store(root / "store")
    _render_startup_pages(restarted, root)
    after = _pipeline_rows((root / "pages" / HOME).read_text(encoding="utf-8"))
    assert after == renders[0], "the labels moved across a restart"


def test_the_operator_readme_says_how_same_second_runs_are_ordered():
    from tests.conftest import REPO
    text = " ".join((REPO / "OPERATOR_README.md").read_text(encoding="utf-8").split())
    assert README_LINE in text
