"""The store read interface (`onetrace_console.store_read`), over planted stores.

Each answer is checked against the records by another route: the receipts' own `config_digest`, the
model-call records as the run page reads them (`model_call.files_value`), and the run page's own
neighbour suggestions. A store whose run index is a format the interface does not read, or that has
none, is refused with the reason; neighbours are refused where the extra is not installed or not on.
Asking writes nothing. Each rule has its own sabotage.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from tests.test_neighbours import _absent, held, needs_extra, on, recorded  # noqa: F401 - fixtures

REPO = Path(__file__).resolve().parent.parent


def _indexed(store) -> Path:
    """The store root of `store` (the folder holding its `store/`), with the run index written there."""
    from onetrace_console import run_index
    root = Path(store.root).parent
    run_index.write(store, root)
    return root


def _tree(root: Path) -> dict:
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def _receipt_digests(store) -> list[tuple[str, str, str]]:
    """(run key, step, its instrument's config_digest) for every step, read from the receipts."""
    from onetrace_console.stage_pages import _steps
    out = []
    with store.reading():
        for run in store.runs():
            for s in _steps(run, store):
                stage, inst = s["receipt"].get("stage") or {}, s["receipt"].get("instrument") or {}
                if inst.get("config_digest"):
                    out.append((run.key, str(stage.get("name", "")), str(inst["config_digest"])))
    return out


def test_runs_by_a_stage_s_configuration_are_the_receipts_own(held, examined):
    from onetrace_console import store_read
    store, _runs = held
    reader = store_read.open_store(_indexed(store))
    every = _receipt_digests(store)
    examined(len(every), "steps with a configuration digest, from their receipts")
    assert every
    for key, step, digest in every:
        want = sorted((k, s) for k, s, d in every if d == digest and s == step)
        assert sorted((f.run_key, f.step) for f in reader.runs_by_config(step, digest)) == want
        assert {f.run_key for f in reader.runs_by_config("*", digest)} == {k for k, _s, d in every if d == digest}
    #: The two cold-chain runs: one configuration, inputs apart.
    p7 = [(k, s, d) for k, s, d in every if k == _runs["p7-39-cold-chain-baseline"].key]
    assert all({f.run_key for f in reader.runs_by_config(s, d)} >= {_runs["p7-40-cold-chain-one-reading-changed"].key}
               for _k, s, d in p7)
    assert reader.runs_by_config("*", "sha256:" + "0" * 64) == []


@pytest.fixture(scope="module")
def model_files(tmp_path_factory):
    """A planted store: two runs whose model-call records name the same model files, one naming others,
    and one with no record, written with the installed onetrace's own helpers (no model is called)."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("store-read-model-files")
    made = {"a": record_run(folder / "a", "sr-a"), "b": record_run(folder / "b", "sr-b"),
            "f": record_run(folder / "f", "sr-f", files_digest="sha256:" + "f" * 64),
            "n": record_run(folder / "n", "sr-n", with_record=False)}
    store = Store(folder / "root" / "store")
    runs = {k: run_and_record(_deliver(p, store, outputs=True), store, ran_at=FIXED_RAN_AT) for k, p in made.items()}
    return store, runs


def test_runs_by_model_files_are_the_records_own(model_files, examined):
    from onetrace_console import model_call, store_read
    from onetrace_console.stage_pages import _files, _read, _steps
    store, runs = model_files
    want: dict[str, set] = {}
    with store.reading():
        for run in store.runs():
            files = _files(run, store)
            for s in _steps(run, store):
                for o in model_call.outputs(s["receipt"]):
                    record = model_call.read_output(s["file"], o, lambda p: _read(files, store, p))
                    got = model_call.files_value(record)
                    if got:
                        step = str((s["receipt"].get("stage") or {}).get("name"))
                        want.setdefault(got[0], set()).add((run.key, step, got[1]))
    reader = store_read.open_store(_indexed(store))
    examined(sum(len(v) for v in want.values()), "model-call records naming their model files")
    assert sorted(len(v) for v in want.values()) == [1, 2], want
    for value, found in want.items():
        assert {(f.run_key, f.step, f.state) for f in reader.runs_by_model_files(value)} == found
    assert {f.run_key for f in reader.runs_by_model_files("sha256:" + "c" * 64)} == {runs["a"].key, runs["b"].key}
    assert reader.runs_by_model_files("sha256:" + "0" * 64) == []


def test_neighbours_are_refused_where_the_extra_is_absent_or_off(held, monkeypatch, examined):
    from onetrace_console import neighbours, store_read
    store, runs = held
    reader = store_read.open_store(_indexed(store))
    key = runs["p7-39-cold-chain-baseline"].key
    examined(2, "refusals: off, and absent")
    with pytest.raises(store_read.Refused, match="not turned on" if neighbours.installed() else "not installed"):
        reader.neighbours(key)
    _absent(monkeypatch)
    with pytest.raises(store_read.Refused, match="not installed"):
        reader.neighbours(key)


@needs_extra
def test_neighbours_are_the_run_page_s_own_where_on(on, examined):
    from onetrace_console import store_read
    from onetrace_console.neighbours import nearness
    store, runs = on
    reader = store_read.open_store(_indexed(store))
    examined(len(runs), "runs asked")
    for run in runs.values():
        with store.reading():
            rows = nearness.suggestions(run, store).rows
        got = reader.neighbours(run.key)
        assert [(f.run_key, f.step, f.name, f.nearness, f.state) for f in got] == \
            [(r.other.key, r.step, r.name, r.near.value, r.near.how) for r in rows]


def test_asking_writes_nothing(held, examined):
    from onetrace_console import store_read
    store, runs = held
    root = _indexed(store)
    before = _tree(root)
    reader = store_read.open_store(root)
    for _k, s, d in _receipt_digests(store)[:3]:
        reader.runs_by_config(s, d)
    reader.runs_by_model_files("sha256:" + "0" * 64)
    with pytest.raises(store_read.Refused):
        reader.neighbours(runs["p4-29-reply-30-days"].key)
    examined(len(before), "files under the store root")
    assert _tree(root) == before


EARLIER = "onetrace-console-run-index/0.1"


def _refused(root: Path, body) -> str:
    from onetrace_console import store_read
    (root / "run_index.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(store_read.Refused) as got:
        store_read.open_store(root)
    return str(got.value)


def _earlier_reason_held(said: str) -> bool:
    """The earlier format's own reason: the format found, then the search page's two sentences for it."""
    from onetrace_console import __version__, search_page
    return (f'is "{EARLIER}", an earlier format' in said
            and f"On a local console: {search_page.EARLIER_LOCAL.format(found=EARLIER)}" in said
            and f"On a public console: {search_page.EARLIER_PUBLIC.format(found=EARLIER, version=__version__)}"
            in said)


def test_an_index_in_an_earlier_format_is_refused_with_who_writes_it_again(tmp_path, examined):
    examined(1, "planted index in an earlier format")
    said = _refused(tmp_path, {"format": EARLIER, "runs": []})
    assert _earlier_reason_held(said), said
    assert "reads onetrace-console-run-index/0.2 only" not in said


@pytest.mark.parametrize("planted, found", [
    ("a later format", '"onetrace-console-run-index/9.9"'),
    ("another name", '"another-index/0.2"'),
    ("no format", "null"),
    ("not an index", "null"),
])
def test_a_store_whose_index_is_not_one_this_version_reads_is_refused(tmp_path, planted, found, examined):
    body = {"a later format": {"format": "onetrace-console-run-index/9.9", "runs": []},
            "another name": {"format": "another-index/0.2", "runs": []},
            "no format": {"runs": []}, "not an index": ["runs"]}[planted]
    examined(1, "planted index")
    said = _refused(tmp_path, body)
    assert said.endswith(f"run_index.json is {found}, and this interface (onetrace-console-store-read/1) reads "
                         f"onetrace-console-run-index/0.2 only"), said
    assert "earlier format" not in said


def test_sabotage_an_earlier_format_given_the_generic_message_is_caught(tmp_path, monkeypatch, examined):
    """`run_index.earlier` told no format is earlier: the earlier format gets the one message every unread
    format gets, and the reason the first test holds is gone."""
    from onetrace_console import run_index
    monkeypatch.setattr(run_index, "earlier", lambda said: False)
    examined(1, "planted interface")
    said = _refused(tmp_path, {"format": EARLIER, "runs": []})
    assert not _earlier_reason_held(said)
    assert said.endswith("reads onetrace-console-run-index/0.2 only")


def test_an_index_that_cannot_be_read_is_refused_with_the_error_s_reason_and_path_as_written(tmp_path, monkeypatch,
                                                                                            examined):
    """An OSError is said as `oserror.said` says it: the reason, then the path as written, never Python's
    repr of it with every backslash doubled."""
    import errno
    from onetrace_console import store_read
    (tmp_path / "run_index.json").write_text("{}", encoding="utf-8")
    where = "C:\\data\\store\\run_index.json"

    def refused(self, *a, **k):
        raise PermissionError(errno.EACCES, "Permission denied", where)
    monkeypatch.setattr(Path, "read_text", refused)
    examined(1, "index that cannot be read")
    with pytest.raises(store_read.Refused) as got:
        store_read.open_store(tmp_path)
    assert str(got.value).endswith(f"cannot be read as a run index: Permission denied: {where}")
    assert "\\\\" not in str(got.value) and "[Errno" not in str(got.value)


def test_a_store_with_no_index_is_refused_with_how_to_get_one(tmp_path, examined):
    from onetrace_console import store_read
    examined(1, "store root without an index")
    with pytest.raises(store_read.Refused, match="start the console on this store once"):
        store_read.open_store(tmp_path)


def test_sabotage_an_unknown_format_read_as_known_is_caught(tmp_path, monkeypatch, examined):
    """The interface told it reads 0.1 too: the refusals above no longer hold, so their tests would fail."""
    from onetrace_console import store_read
    (tmp_path / "run_index.json").write_text(json.dumps({"format": "onetrace-console-run-index/0.1", "runs": []}),
                                             encoding="utf-8")
    monkeypatch.setattr(store_read, "INDEX_FORMATS", store_read.INDEX_FORMATS + ("onetrace-console-run-index/0.1",))
    examined(1, "planted interface")
    assert store_read.open_store(tmp_path).runs_by_config("*", "x") == []


def test_sabotage_a_config_question_that_ignores_the_digest_is_caught(held, monkeypatch, examined):
    """Every run with the step answered, whatever its configuration: a digest no run records then gets
    runs, where the first test holds it gets none."""
    from onetrace_console import store_read
    store, _runs = held
    reader = store_read.open_store(_indexed(store))

    def any_digest(self, step, digest):
        return [store_read.Found(r["key"], r["run_id"], "", s["name"], digest)
                for r in self._runs() for s in r["steps"] if step in ("*", s["name"])]
    monkeypatch.setattr(store_read.Reader, "runs_by_config", any_digest)
    examined(1, "planted question")
    assert reader.runs_by_config("*", "sha256:" + "0" * 64) != []


def test_the_docs_page_names_the_version_the_formats_and_each_question(examined):
    from onetrace_console import store_read
    page = (REPO / "docs" / "store_read.md").read_text(encoding="utf-8")
    names = [store_read.VERSION, *store_read.INDEX_FORMATS, "open_store", "runs_by_config", "runs_by_model_files",
             "neighbours", "Refused"]
    examined(len(names), "names the docs page must hold")
    assert [n for n in names if n not in page] == []


def test_the_docs_page_names_the_model_files_states_and_the_store_folder_refusal(examined):
    """The states the model-files question matches, as the interface's own FILES_STATES gives them, and the
    neighbours refusal for a store root with no store folder, by the folders the code looks for."""
    from onetrace_console import store_read
    page = (REPO / "docs" / "store_read.md").read_text(encoding="utf-8")
    names = [*(f"`{s}`" for s in store_read.FILES_STATES), "`store/objects`", "`store/runs`"]
    examined(len(names), "names the docs page must hold")
    assert [n for n in names if n not in page] == []
    assert store_read.FILES_STATES == ("observed", "declared")
