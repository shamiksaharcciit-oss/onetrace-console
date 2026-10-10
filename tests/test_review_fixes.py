"""A confirmation review's console findings, each with the probe that found it.

The review (a fresh reviewer, at console 6ad9b0c and viewer 2e8a885) confirmed each of these by
running it. The viewer's halves are in canary 5f4f06c, re-vendored here.

1. Blocker: a record the viewer cannot show -- nesting deeper than its encoder reaches, or a
   lone surrogate escape -- made ingest answer 500, every later ingest too, and stopped the
   console starting. The viewer now refuses both as a `RecordError`, and one run's failure of
   any kind no longer takes a page, an ingest or a restart down with it.
2. Blocker (B4): "records agree" read yes from a check not run with `--require-artifacts`.
   The run page's rung now reads the check's own command; the Overview, which
   counts the same claim across runs, counts only runs whose check ran with the flag.
3. Should-fix: the Diff page still crashed on report shapes the reader passed, and on a report
   of another verb or kind. The reader now takes the SDK's exact row shapes; the page takes
   only the kinds of report its verbs write, and states anything else.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from onetrace_console.pages import CASE, render_execution, render_executions
from tests.conftest import make_tar
from tests.test_home_and_diff import diverging  # noqa: F401  (fixture)
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_unreadable import RUN_ID, _renamed, _resummed, _stored, _text


def _planted(files, raw_value: str) -> dict[str, bytes]:
    """The clean fixture, renamed, with `assertions.constants` of one receipt replaced by raw
    JSON text -- `json.dumps` cannot write either input the review used."""
    out = _renamed(files)
    rel = json.loads(out["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    data = json.loads(out[rel].decode("utf-8"))
    data.setdefault("assertions", {})["constants"] = "__PLANTED__"
    text = json.dumps(data, ensure_ascii=False)
    out[rel] = text.replace('"__PLANTED__"', raw_value).encode("utf-8")
    return _resummed(out)


DEEP = '{"a":' * 1500 + "1" + "}" * 1500
SURROGATE = '"\\ud800"'


# ------------------------------------------------------------------------ 1. unshowable

#: The lone surrogate is no longer here: it is shown escaped, never refused
#: (tests/test_followup_names.py). A record nested too deeply to show no longer reaches a page at
#: all: ingest now refuses it first, in the fixed words, with nothing stored
#: (tests/test_bounded_json.py holds the limit at 256 and 257 on every reader).
def test_a_record_the_viewer_cannot_show_is_refused_at_ingest_in_words(files, store):
    """The review's probe: `render_execution` raised RecursionError on this record."""
    from onetrace_console.viewer.depth import MAX_JSON_DEPTH

    from onetrace_console.bounded_json import ingest_refusal
    from onetrace_console.ingest import accept
    planted = _planted(files, DEEP)
    rel = json.loads(planted["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    got = accept(make_tar(planted), store)
    assert getattr(got, "run", None) is None, "a record nested 1500 deep was stored"
    want = f"[FAIL   ] {rel}: nested at most {MAX_JSON_DEPTH} levels deep -- {ingest_refusal(rel)}"
    assert want in got.rows, got.rows


@pytest.mark.parametrize("raw,first", [(DEEP, 422), (SURROGATE, 200)], ids=["deep", "lone-surrogate"])
def test_ingesting_it_and_then_a_clean_run_both_answer_200(server, files, raw, first):
    """The review: POST it -> 500, POST a clean run afterwards -> 500. Neither is a 500 now: the
    lone surrogate is taken, and a record nested past 256 levels
    is refused as a damaged upload (422), in the fixed words; the clean run after it is taken."""
    from onetrace_console.viewer.depth import MAX_JSON_DEPTH

    from tests.test_serve import _post
    base, _ = server
    status, body = _post(base, "/v1/runs", make_tar(_planted(files, raw)))
    assert status == first, body[:300]
    if first == 422:
        said = f"is nested more than {MAX_JSON_DEPTH} levels deep, past what the console reads."
        assert said.encode("utf-8") in body, body[:600]
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, body[:300]


#: The deep case is gone: such a record is now refused at ingest, so no store
#: holds one to restart over (test_a_record_the_viewer_cannot_show_is_refused_at_ingest_in_words).
@pytest.mark.parametrize("raw", [SURROGATE], ids=["lone-surrogate"])
def test_a_restart_over_it_starts(files, store, tmp_path, raw):
    from onetrace_console.serve import _render_startup_pages
    _stored(_planted(files, raw), store)
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    assert (root / "pages" / "home.html").is_file()


def test_one_runs_unforeseen_failure_is_that_runs_page_and_nothing_more(files, store,
                                                                       checked, monkeypatch,
                                                                       capsys):  # noqa: F811
    """Whatever else the viewer might raise on one record, the run's own page says so, the
    traceback goes to the operator's log, and the other runs' pages and lists are drawn."""
    import onetrace_console.viewer.model as model
    from onetrace_console.unreadable import RUN_FAILED
    bad = _stored(_planted(files, '{"k": 1}'), store)
    #: As a run stored before its list row was kept, so the list reads it live.
    store.put_run(replace(bad, list_row=""))
    bad = store.get_run(bad.key)
    real = model.build_model

    def fails_on_one(record, *a, **k):
        if record.run_id == RUN_ID:
            raise RuntimeError("an unforeseen failure")
        return real(record, *a, **k)
    monkeypatch.setattr(model, "build_model", fails_on_one)
    #: And in a list, which draws each run's `list_row`, not its full model.
    real_row = model.list_row

    def row_fails_on_one(record):
        if record.run_id == RUN_ID:
            raise RuntimeError("an unforeseen failure")
        return real_row(record)
    monkeypatch.setattr(model, "list_row", row_fails_on_one)
    page = render_execution(bad, store, generated_at=GENERATED_AT).pages[CASE]
    #: Not the viewer's refusal, so not in its words (the second review, S1).
    assert RUN_FAILED in _text(page) and "RuntimeError: an unforeseen failure" in _text(page)
    assert "Traceback" in capsys.readouterr().err, "the operator's log has the traceback"
    listed = render_executions([checked, bad], store, generated_at=GENERATED_AT)
    assert f'data-run="{checked.run_id}"' in listed and "RuntimeError" in _text(listed)


# ------------------------------------------------------------- 2. records agree, evidence

def _rung_one(case: str) -> str:
    ladder = re.search(r'<section data-section="ladder">(.*?)</section>', case, re.S).group(1)
    return dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', ladder))[
        "records-agree"]


def _with_flag(run, store):
    """The run's stored check report as a check run with `--require-artifacts` would record
    it. The pinned verifier (0.1.0) has no such flag (B4): a test double, and said so."""
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    envelope["command"] = list(envelope["command"]) + ["--require-artifacts"]
    flagged = replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))
    store.put_run(flagged)
    return flagged


def test_a_check_that_held_without_the_flag_is_not_counted_as_agreeing(checked, store):  # noqa: F811
    from onetrace_console.render import HOME, render_all
    assert checked.check_verdict == "holds"
    assert _rung_one(render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]) \
        == "not-checked"
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    card = re.search(r'<div data-card="records-agree">(.*?)</div>', home, re.S).group(1)
    assert re.search(r"\b0 of 1 run verified\b", _text(card)), _text(card)
    evidence = re.search(r'<tr data-rung="records-agree">(.*?)</tr>', home, re.S).group(1)
    assert "0 of 1" in _text(evidence) and "1 held without its output files required" in \
        _text(evidence), _text(evidence)


def test_a_check_that_held_with_the_flag_is_counted(checked, store):  # noqa: F811
    from onetrace_console.render import HOME, render_all
    flagged = _with_flag(checked, store)
    assert _rung_one(render_execution(flagged, store, generated_at=GENERATED_AT).pages[CASE]) \
        == "yes"
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    card = re.search(r'<div data-card="records-agree">(.*?)</div>', home, re.S).group(1)
    assert re.search(r"\b1 of 1 run verified\b", _text(card)), _text(card)


# ------------------------------------------------------------------------ 3. the Diff page

def _edited(comparison, store, verb_file: str, change):
    from onetrace_console.compare import DIFF, LOCALIZE
    report = json.loads(store.get(dict(comparison.verb(DIFF).reports)["diff.json"]))
    change(report)
    edited = store.put(json.dumps(report).encode("utf-8"))
    verbs = tuple(
        replace(v, reports=tuple((n, edited if n == verb_file else k) for n, k in v.reports))
        if v.verb == DIFF else v for v in comparison.verbs if v.verb != LOCALIZE)
    return replace(comparison, verbs=verbs)


def _last_row_index(r):
    r["ladder"][-1]["index"] = "x"


def _first_difference_index(r):
    row = next(x for x in r["ladder"] if x["verdict"] == "FIRST DIFFERENCE")
    row["index"] = "x"


def _outputs(value):
    def change(r):
        r["ladder"][0]["baseline"]["outputs"] = value
    return change


def _as(verb, mode, **more):
    def change(r):
        r.update(verb=verb, mode=mode, **more)
    return change


@pytest.mark.parametrize("change,why", [
    (_last_row_index, "not a decimal string"),
    (_first_difference_index, "not a decimal string"),
    (_outputs(5), "not a list of digests"),
    (_outputs("sha256:abc"), "not a list of digests"),
    (_as("localize", "single-run", result="clean", stage=None, check=None, words=None),
     "not a comparison"),
    (_as("reproduce", "whole-run", result="all REPRODUCED", stages=[]), "not a comparison"),
], ids=["row-index", "first-difference-index", "outputs-a-number", "outputs-a-string",
        "a-single-run-localize", "a-reproduce"])
def test_the_diff_page_states_what_it_cannot_draw(diverging, change, why):
    """The review's probe_diff_page.py: each of these crashed `render_diff` (ValueError,
    TypeError, AttributeError), or drew a string's characters as digests."""
    from onetrace_console.render import render_diff
    comparison, store = diverging
    page = render_diff(_edited(comparison, store, "diff.json", change), store,
                       generated_at=GENERATED_AT)
    block = re.search(r'<section data-section="diff-unreadable".*?</section>', page, re.S)
    assert block and why in _text(block.group(0)), _text(page)[:600]
    assert 'data-verb="diff"' not in page


# ------------------------------------------------ 4. the start-up refuses in words, in order

def _serve_with(tmp_path, monkeypatch, body: dict):
    """`serve.main` over a named configuration file; returns (exit code, stderr)."""
    from onetrace_console import serve
    from onetrace_console.config import ENV_VAR
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))

    def listened(self):
        raise AssertionError("it served with a configuration it cannot use")
    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", listened)
    return serve.main([])


def _refused_in_words(capsys, says: str) -> str:
    err = capsys.readouterr().err
    assert "Traceback" not in err, err
    assert f"refusing to start: {says}" in err and "\nfix: " in err, err
    return err


def test_a_store_root_that_cannot_be_made_is_refused_in_words(tmp_path, monkeypatch, capsys):
    """The review's probe_config.py: a store_root that is a file ended in FileExistsError."""
    blocker = tmp_path / "a-file"
    blocker.write_text("not a folder", encoding="utf-8")
    for root in (blocker, blocker / "under-a-file"):
        assert _serve_with(tmp_path, monkeypatch, {
            "store_root": root.as_posix(), "sign_in": {"enabled": False}}) == 1
        _refused_in_words(capsys, "cannot use store_root")


@pytest.mark.parametrize("content,says", [
    (None, "no TLS certificate at"),                     # B5: said by name
    (b"not a certificate", "cannot load the TLS certificate and key"),
], ids=["missing", "not-pem"])
def test_tls_files_it_cannot_load_are_refused_before_anything_is_drawn(tmp_path, monkeypatch,
                                                                     capsys, content, says):
    """The review: missing or non-PEM TLS files ended in a traceback, after every page had been
    rendered and the port bound."""
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    if content is not None:
        cert.write_bytes(content)
        key.write_bytes(content)
    root = tmp_path / "data"
    assert _serve_with(tmp_path, monkeypatch, {
        "store_root": root.as_posix(),
        "sign_in": {"enabled": True, "tls_cert_path": str(cert), "tls_key_path": str(key)}}) == 1
    _refused_in_words(capsys, says)
    assert not list((root / "pages").rglob("*.html")), "nothing was drawn before the refusal"


def test_a_second_console_refuses_before_it_draws_over_the_firsts_pages(tmp_path, monkeypatch,
                                                                       capsys):
    """Review note 9: the pages were rendered before the bind, so a second console on the same
    store rewrote the first's pages and only then found its port taken."""
    from onetrace_console.serve import ConsoleServer, Handler
    first = ConsoleServer(("127.0.0.1", 0), Handler)
    try:
        root = tmp_path / "data"
        assert _serve_with(tmp_path, monkeypatch, {
            "port": first.server_address[1], "store_root": root.as_posix(),
            "sign_in": {"enabled": False}}) == 1
        _refused_in_words(capsys, "cannot listen on")
        assert not list((root / "pages").rglob("*.html")), "nothing was drawn before the refusal"
    finally:
        first.server_close()


def test_a_host_that_does_not_resolve_is_not_called_a_busy_port(tmp_path, monkeypatch, capsys):
    """Review note 8: an unresolvable host was reported as another process on the port."""
    assert _serve_with(tmp_path, monkeypatch, {
        "host": "no-such-host.invalid", "store_root": (tmp_path / "d").as_posix(),
        "sign_in": {"enabled": False}}) == 1
    err = _refused_in_words(capsys, "cannot resolve host 'no-such-host.invalid'")
    assert "another process" not in err


def test_a_configuration_saved_with_a_byte_order_mark_is_read(tmp_path, monkeypatch):
    """Review note 8: Notepad's UTF-8 saves a BOM, and the file was refused as bad JSON."""
    from onetrace_console.config import ENV_VAR, load_from_env
    path = tmp_path / "config.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"port": 8099}).encode("utf-8"))
    monkeypatch.setenv(ENV_VAR, str(path))
    assert load_from_env().port == 8099


def test_the_release1_extension_refusal_has_its_fix_line(tmp_path, monkeypatch, capsys):
    """Review note 8: the fixed wording, and a `fix:` line after it."""
    assert _serve_with(tmp_path, monkeypatch, {
        "store_root": (tmp_path / "d").as_posix(), "extensions": {"onedoor": True},
        "sign_in": {"enabled": False}}) == 1
    err = _refused_in_words(capsys, "extensions.onedoor is true")
    assert "the authorization extension is not part of this release" in err


# ------------------------------------------------------------- 5. the pipeline field, unread

def test_nothing_in_the_source_reads_the_stored_pipeline_field():
    """Leave it unread. Review note 10: partners.py still named it."""
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
    #: The stored field is set in ingest.py and declared in store.py; the Overview's own
    #: pipelines (`found.pipeline`, `m.pipeline`) are its declared-stage-list pipelines, which
    #: batch 4 defines, and are not this field.
    readers = [p.name for p in src.rglob("*.py")
               if re.search(r"""["']pipeline["']\s*:|\b(?:run|r|other|a|b|a_run|b_run)\.pipeline\b""",
                            p.read_text(encoding="utf-8"))
               and p.name not in ("ingest.py", "store.py")]
    assert readers == [], readers
