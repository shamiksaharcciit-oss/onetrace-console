"""One depth rule at every console reader.

Every `json.load`/`json.loads` in `src/onetrace_console/` goes through
`onetrace_console.bounded_json.load_json_bounded`, which applies the vendored viewer's own rule
(`viewer.depth`: `json_depth` against `MAX_JSON_DEPTH`). Until it, "too deep" was wherever the
interpreter ran out -- `json.loads` fails at 2995 levels on Windows 3.12 and 9995 on Linux -- so a
manifest 5000 deep was refused at ingest on Windows and taken on Linux. Each test below builds its
input to a measured total depth, exactly `MAX_JSON_DEPTH` (accepted) or one more (refused), and goes
through the console's own path. The number in every expected message comes from the constant.
"""
from __future__ import annotations

import ast
import json
from dataclasses import replace
from pathlib import Path

import pytest
from onetrace_console.viewer.depth import MAX_JSON_DEPTH, json_depth

from onetrace_console.bounded_json import TooDeep, ingest_refusal, load_json_bounded
from tests.conftest import make_tar
from tests.test_unreadable import _renamed, _resummed

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
#: The fixed limit, as a number here, not read from the constant: these tests pin the boundary
#: itself, so a raised MAX_JSON_DEPTH fails them, rather than moving them with it.
#: Raising it is a remeasuring on all three interpreters first and a change here.
RULED = 256
AT, PAST = RULED, RULED + 1

#: (file relative to src/onetrace_console/, line) -> why a bare json.load(s) is allowed there.
#: One that outlives its line fails below, so an allowance cannot linger as a hole.
#: The viewer's readers go through the helper like every other (tests/viewer/test_bounded_readers.py).
#: One call stays bare for good: the measurement of where json.loads itself fails.
ALLOWED: dict[tuple[str, int], str] = {
    ("viewer/depth.py", 99): "a measurement of where json.loads itself fails; it must call it bare",
    #: The reference demo's pipeline, run by the demo store as P2: byte for byte
    #: examples/reference-demo/demo.py, so it can't be edited. It parses two
    #: files it wrote itself a moment before, at build time; nothing it reads was received.
    ("demo_store/reference_pipeline.py", 120): "P2's own documents.json, written by it at build time",
    ("demo_store/reference_pipeline.py", 131): "P2's own test-results.json, written by it at build time",
}


def _nested(levels: int) -> str:
    """JSON text nesting exactly `levels` objects (0: a bare number)."""
    return '{"a":' * levels + "1" + "}" * levels


def _depth_of(raw: bytes | str) -> int:
    return json_depth(json.loads(raw))


# --------------------------------------------------------------------- the one door, statically

def test_no_json_load_in_the_console_outside_the_helper():
    found = []
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "bounded_json.py":
            continue
        rel = path.relative_to(SRC).as_posix()
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("load", "loads") and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "json"):
                found.append((rel, node.lineno))
            if isinstance(node, ast.ImportFrom) and node.module == "json" and any(
                    a.name in ("load", "loads") for a in node.names):
                found.append((rel, node.lineno))
    bare = [f for f in found if f not in ALLOWED]
    assert not bare, (f"json.load(s) outside onetrace_console.bounded_json, so outside the depth rule"
                      f": {bare}")
    stale = [a for a in ALLOWED if a not in found]
    assert not stale, f"allowances that outlived their line: {stale}"


# --------------------------------------------------------------------- the helper

def test_the_vendored_limit_is_the_ruled_one():
    assert MAX_JSON_DEPTH == RULED, (
        f"viewer.depth.MAX_JSON_DEPTH is {MAX_JSON_DEPTH}, the ruling's is {RULED}: remeasure on all "
        f"three interpreters before either moves")


def test_the_helper_takes_exactly_the_limit_and_refuses_one_past():
    assert json_depth(load_json_bounded(_nested(AT), "x")) == AT
    with pytest.raises(TooDeep) as e:
        load_json_bounded(_nested(PAST), "x.json")
    assert str(e.value) == "x.json is nested too deeply to read"
    with pytest.raises(TooDeep) as e:
        load_json_bounded(_nested(PAST), "MANIFEST.json", "show")
    assert str(e.value) == "MANIFEST.json is nested too deeply to show"
    assert isinstance(e.value, json.JSONDecodeError) and isinstance(e.value, ValueError)


def test_the_ingest_words_are_the_ruled_ones_with_the_number_from_the_constant():
    assert ingest_refusal("receipts/02-rerank.json") == (
        f"Not ingested: receipts/02-rerank.json is nested more than {MAX_JSON_DEPTH} levels deep, "
        f"past what the console reads.")


# --------------------------------------------------------------------- ingest: the manifest and a receipt

def _manifest_at(files, total: int) -> dict[str, bytes]:
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["note"] = "__PLANTED__"
    text = json.dumps(manifest, ensure_ascii=False)
    out["MANIFEST.json"] = text.replace('"__PLANTED__"', _nested(total - 1)).encode("utf-8")
    assert _depth_of(out["MANIFEST.json"]) == total
    return _resummed(out)


def _receipt_at(files, total: int) -> tuple[dict[str, bytes], str]:
    out = _renamed(files)
    rel = json.loads(out["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    data = json.loads(out[rel].decode("utf-8"))
    data.setdefault("assertions", {})["constants"] = "__PLANTED__"
    text = json.dumps(data, ensure_ascii=False)
    out[rel] = text.replace('"__PLANTED__"', _nested(total - 2)).encode("utf-8")
    assert _depth_of(out[rel]) == total
    return _resummed(out), rel


def _refusal_row(name: str) -> str:
    return f"[FAIL   ] {name}: nested at most {MAX_JSON_DEPTH} levels deep -- {ingest_refusal(name)}"


def test_ingest_takes_a_manifest_exactly_at_the_limit(files, store):
    from onetrace_console.ingest import accept
    got = accept(make_tar(_manifest_at(files, AT)), store)
    assert getattr(got, "run", None) is not None, getattr(got, "rows", got)


def test_ingest_refuses_a_manifest_one_past_the_limit_in_the_ruled_words(files, store):
    from onetrace_console.ingest import accept
    got = accept(make_tar(_manifest_at(files, PAST)), store)
    assert getattr(got, "run", None) is None
    assert _refusal_row("MANIFEST.json") in got.rows, got.rows


def test_ingest_takes_a_receipt_exactly_at_the_limit(files, store):
    from onetrace_console.ingest import accept
    planted, _ = _receipt_at(files, AT)
    got = accept(make_tar(planted), store)
    assert getattr(got, "run", None) is not None, getattr(got, "rows", got)


def test_ingest_refuses_a_receipt_one_past_the_limit_in_the_ruled_words(files, store):
    from onetrace_console.ingest import accept
    planted, rel = _receipt_at(files, PAST)
    got = accept(make_tar(planted), store)
    assert getattr(got, "run", None) is None
    assert _refusal_row(rel) in got.rows, got.rows


# --------------------------------------------------------------------- the configuration file

def _config_at(tmp_path, total: int) -> Path:
    path = tmp_path / "console.json"
    path.write_text('{"x":' + _nested(total - 1) + "}", encoding="utf-8")
    assert _depth_of(path.read_text(encoding="utf-8")) == total
    return path


def test_config_at_the_limit_is_not_refused_for_depth(tmp_path):
    from onetrace_console.config import ConfigError, load
    try:
        load(_config_at(tmp_path, AT))
        said = ""
    except ConfigError as e:
        said = str(e)
    assert "nested too deeply" not in said, said


def test_config_one_past_the_limit_is_refused_in_its_existing_words(tmp_path):
    from onetrace_console.config import ConfigError, load
    path = _config_at(tmp_path, PAST)
    with pytest.raises(ConfigError, match="nested too deeply to read"):
        load(path)


# --------------------------------------------------------------------- the access log's own HEAD

def _access_log_at(tmp_path, total: int) -> Path:
    root = tmp_path / "access_log"
    root.mkdir()
    (root / "HEAD.json").write_text('{"x":' + _nested(total - 1) + "}", encoding="utf-8")
    assert _depth_of((root / "HEAD.json").read_text(encoding="utf-8")) == total
    return root


@pytest.mark.parametrize("total,refused", [(AT, False), (PAST, True)], ids=["at", "past"])
def test_the_access_logs_head_is_judged_by_the_limit(tmp_path, total, refused):
    from onetrace_console.access_log import AccessLog
    try:
        AccessLog(_access_log_at(tmp_path, total), max_segment_bytes=1 << 20)
        said = ""
    except ValueError as e:
        said = str(e)
    assert ("HEAD.json is nested too deeply to read" in said) is refused, said


# --------------------------------------------------------------------- stored reports: check, diff, verb

@pytest.fixture
def held(files, store):
    """A clean run, ingested and checked: a stored check report and a stored diff report to swap."""
    from tests.test_unreadable import _stored
    return _stored(_resummed(_renamed(files)), store), store


def _report_at(total: int, **fields) -> bytes:
    """A JSON object holding `fields`, nested to exactly `total` by one more key."""
    doc = dict(fields, deep="__PLANTED__")
    raw = json.dumps(doc).replace('"__PLANTED__"', _nested(total - 1)).encode("utf-8")
    assert _depth_of(raw) == total
    return raw


@pytest.mark.parametrize("total,refused", [(AT, False), (PAST, True)], ids=["at", "past"])
def test_a_stored_check_report_is_judged_by_the_limit_on_the_run_page_path(held, total, refused):
    from onetrace_console.pages import _envelope
    run, store = held
    run = replace(run, check_report=store.put(_report_at(total, command=["onetrace-verify"])))
    if refused:
        with pytest.raises(TooDeep, match="the check report is nested too deeply to read"):
            _envelope(run, store)
    else:
        assert _envelope(run, store)["command"] == ["onetrace-verify"]


@pytest.mark.parametrize("total,counted", [(AT, True), (PAST, False)], ids=["at", "past"])
def test_a_stored_check_report_is_judged_by_the_limit_on_the_overview_count(held, total, counted):
    """Home's count of checks run with --require-artifacts reads the stored report itself."""
    import onetrace_console.home as home
    run, store = held
    run = replace(run, check_report=store.put(_report_at(
        total, command=["onetrace-verify", "--require-artifacts"])))
    fn = next(getattr(home, n) for n in dir(home)
              if callable(getattr(home, n)) and getattr(getattr(home, n), "__code__", None)
              and "--require-artifacts" in getattr(home, n).__code__.co_consts)
    assert fn(run, store) is counted


@pytest.mark.parametrize("total,read", [(AT, True), (PAST, False)], ids=["at", "past"])
def test_a_stored_diff_report_is_judged_by_the_limit_on_the_overview(store, total, read):
    """The Overview reads a comparison's stored diff report (`overview._diff_of`)."""
    from types import SimpleNamespace

    from onetrace_console.compare import DIFF
    from onetrace_console.overview import _diff_of
    key = store.put(_report_at(total, verdict="same"))
    verb_run = SimpleNamespace(note="", reports=(("diff.json", key),))
    comparison = SimpleNamespace(verb=lambda verb: verb_run if verb == DIFF else None)
    got = _diff_of(comparison, store)
    assert (got is not None) is read, got
