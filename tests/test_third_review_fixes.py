"""The third confirmation review's console findings, the 422 set among them.

A third fresh reviewer confirmed the second review's fixes, then found these by running them.
The viewer's halves are canary 220a38b, re-vendored here.

NEW-1  A small upload whose steps named one receipt thousands of times drew pages of hundreds
       of MB; MemoryError answered 500 and the console could not restart.
NEW-2  A lone surrogate escape in the manifest's identity fields answered 500.
NEW-3  Every Executions list printed a fingerprint that was never computed (0000...).
NEW-4  On Windows the pages were written in text mode, so no run page's fingerprint checked.
NEW-5  A staging verifier that did not finish answered 422, outside the 422 set.
NEW-6  One bad item in the store's own files stopped start-up, every ingest and compare, or
       blanked Home and every list.
NEW-8  A start-up print could not be written to a piped stdout; a lone surrogate in host.
NEW-9  An infinite request timeout was accepted.
NEW-12 A staging error named the server's temp path.
NEW-13 A failure that is not the viewer's was tagged as the viewer's words.
NEW-15 "serving on http://::1:port" is not a URL.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import replace

import pytest

from onetrace_console.pages import CASE, render_execution
from tests.conftest import ipv6_loopback_port, make_tar
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_review_fixes import _refused_in_words, _serve_with
from tests.test_unreadable import _renamed, _resummed, _stored, _text


# ------------------------------------------------------------------------------- NEW-1

def _repeating(files, times: int):
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["chain"] = manifest["chain"] + [manifest["chain"][1]] * times
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return _resummed(out)


def test_a_chain_naming_one_receipt_again_and_again_is_stored_and_stated(server, files):
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    from onetrace_console.unreadable import TITLE
    from tests.test_serve import _get, _post
    base, root = server
    status, body = _post(base, "/v1/runs", make_tar(_repeating(files, 50)))
    assert status == 200, body[:300]
    page = _get(base, json.loads(body)["pages"]["case"])[1].decode("utf-8")
    assert TITLE in _text(page) and "more than once" in _text(page)
    _render_startup_pages(Store(root / "store"), root)


def test_a_run_whose_page_fails_to_draw_after_its_model_is_stated(checked, store,  # noqa: F811
                                                                 monkeypatch):
    """The whole drawing is guarded, not only the model: MemoryError came from render_answer."""
    import onetrace_console.viewer.page as page
    from onetrace_console.unreadable import RUN_FAILED

    def exhausted(*a, **k):
        raise MemoryError()
    monkeypatch.setattr(page, "render_answer", exhausted)
    drawn = render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]
    assert RUN_FAILED in _text(drawn) and "MemoryError" in _text(drawn)


def test_a_start_survives_any_run_whose_pages_fail(checked, store, tmp_path, monkeypatch):  # noqa: F811
    import onetrace_console.pages as pages
    from onetrace_console.serve import PAGES_DIRNAME, _render_startup_pages
    from onetrace_console.unreadable import RUN_FAILED
    monkeypatch.setattr(pages, "render_execution", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("an unforeseen failure")))
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    case = (root / PAGES_DIRNAME / "runs" / checked.key / CASE).read_text(encoding="utf-8")
    assert RUN_FAILED in _text(case)


# ------------------------------------------------------------------------------- NEW-2

@pytest.mark.parametrize("field", ["run_id", "chain_head"])
def test_a_manifest_identity_that_is_not_text_is_refused_not_a_500(files, store, field):
    from onetrace_console.ingest import Rejection, accept
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest[field] = "__PLANTED__"
    out["MANIFEST.json"] = json.dumps(manifest).replace('"__PLANTED__"', '"\\ud800"').encode()
    result = accept(make_tar(_resummed(out)), store)
    assert isinstance(result, Rejection), result
    assert any("MANIFEST.json" in r and "UTF-8" in r for r in result.rows), result.rows


# ------------------------------------------------------------------------- NEW-3, NEW-4

def test_every_list_page_carries_its_own_true_fingerprint(checked, store):  # noqa: F811
    from onetrace_console.viewer import fingerprint

    from onetrace_console.render import render_all
    lists = {h: p for h, p in render_all(store, generated_at=GENERATED_AT).items()
             if 'data-view="executions"' in p}
    assert lists
    for href, page in lists.items():
        ok, why = fingerprint.check(page.encode("utf-8"))
        assert ok, (href, why)
        assert href in page, f"the check command names {href}"


def test_a_page_is_written_as_its_bytes_so_its_fingerprint_checks_from_disk(checked, store,  # noqa: F811
                                                                           tmp_path):
    from onetrace_console.viewer import fingerprint

    from onetrace_console.serve import PAGES_DIRNAME, _render_run_pages
    _render_run_pages(checked, store, tmp_path)
    written = (tmp_path / PAGES_DIRNAME / "runs" / checked.key / CASE).read_bytes()
    drawn = render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]
    #: The page's own line endings (a received record quoted in it keeps its CRLF), no more.
    assert written.count(b"\r\n") == drawn.encode("utf-8").count(b"\r\n")
    assert fingerprint.check(written)[0]


# ------------------------------------------------------------------------------- NEW-5

def test_a_staging_verifier_that_does_not_finish_does_not_refuse_the_delivery(files, store,
                                                                            monkeypatch):
    """Not damage and not an unknown format: the delivery is stored, and its check says what
    it says (the 422 set)."""
    import onetrace_console.ingest as ingest
    from onetrace_console.ingest import Accepted
    from onetrace_console.staging import ask_the_verifier
    monkeypatch.setattr(ingest, "ask_the_verifier",
                        lambda folder: ask_the_verifier(folder, timeout=0.001))
    assert isinstance(ingest.accept(make_tar(files), store), Accepted)


# ------------------------------------------------------------------------------- NEW-6

def test_a_run_record_the_store_cannot_read_is_named_and_the_rest_are_drawn(checked, store,  # noqa: F811
                                                                          tmp_path):
    from onetrace_console.render import HOME, render_all
    from onetrace_console.serve import _render_startup_pages
    (store.root / "runs" / ("f" * 64 + ".json")).write_text("{not json", encoding="utf-8")
    assert [r.key for r in store.runs()] == [checked.key]
    pages = render_all(store, generated_at=GENERATED_AT)
    assert "1 stored run record could not be read" in _text(pages[HOME])
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)


def test_a_comparison_record_the_store_cannot_read_is_skipped(checked, store, tmp_path):  # noqa: F811
    from onetrace_console.serve import _render_startup_pages
    d = store.root / "comparisons"
    d.mkdir(exist_ok=True)
    (d / ("e" * 64 + ".json")).write_text(json.dumps({"key": "e" * 64}), encoding="utf-8")
    assert store.comparisons() == ()
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)


def test_a_run_whose_check_report_object_is_gone_does_not_blank_incidents(checked, store):  # noqa: F811
    from onetrace_console.incident_pages import INCIDENTS
    from onetrace_console.render import render_all
    from onetrace_console.unreadable import PAGE_FAILED
    gone = replace(checked, check_verdict="contradicts", check_report="0" * 64)
    store.put_run(gone)
    pages = render_all(store, generated_at=GENERATED_AT)
    assert PAGE_FAILED not in _text(pages[INCIDENTS])


def test_an_access_log_head_it_cannot_read_is_refused_in_words(tmp_path, monkeypatch, capsys):
    root = tmp_path / "data"
    (root / "access_log").mkdir(parents=True)
    (root / "access_log" / "HEAD.json").write_text("{not json", encoding="utf-8")
    assert _serve_with(tmp_path, monkeypatch, {"store_root": root.as_posix(),
                                               "sign_in": {"enabled": False}}) == 1
    _refused_in_words(capsys, "cannot use store_root")


# ------------------------------------------------------------------ NEW-8, NEW-9, NEW-15

def test_a_start_up_line_is_written_to_a_narrow_stdout(tmp_path, monkeypatch):
    """Windows' piped stdout is cp1252: a store root named in CJK broke the 'serving on' line."""
    from onetrace_console import serve

    class Listening(Exception):
        pass

    narrow = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr("sys.stdout", narrow)
    monkeypatch.setattr(serve.ConsoleServer, "serve_forever",
                        lambda self: (_ for _ in ()).throw(Listening()))
    from onetrace_console.config import ENV_VAR
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"port": 18999, "store_root": (tmp_path / "数据").as_posix(),
                                "sign_in": {"enabled": False}}), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    with pytest.raises(Listening):
        serve.main([])


@pytest.mark.parametrize("body,says", [
    #: Named as a lone surrogate, not as a control character.
    ({"host": "\ud800"}, "host holds a lone surrogate escape"),
    ({"request_timeout_seconds": 1e309}, "request_timeout_seconds must be"),
], ids=["host-a-lone-surrogate", "timeout-infinite"])
def test_values_that_cannot_work_are_refused_in_words(tmp_path, monkeypatch, capsys, body, says):
    assert _serve_with(tmp_path, monkeypatch, {"store_root": (tmp_path / "d").as_posix(),
                                               "sign_in": {"enabled": False}, **body}) == 1
    assert says in _refused_in_words(capsys, "")


def test_an_ipv6_host_is_said_as_a_url(tmp_path, monkeypatch, capsys):
    from onetrace_console import serve

    class Listening(Exception):
        pass

    monkeypatch.setattr(serve.ConsoleServer, "serve_forever",
                        lambda self: (_ for _ in ()).throw(Listening()))
    free = ipv6_loopback_port()
    from onetrace_console.config import ENV_VAR
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"host": "::1", "port": free, "store_root": (tmp_path / "d").as_posix(),
                                "sign_in": {"enabled": False}}), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    with pytest.raises(Listening):
        serve.main([])
    assert f"serving on http://[::1]:{free}" in capsys.readouterr().out


# ------------------------------------------------------------------------- NEW-12, NEW-13

def test_a_staging_error_does_not_name_the_servers_temp_path(files, store, monkeypatch):
    import onetrace_console.ingest as ingest

    def fails(files, where):
        raise OSError(22, "Invalid argument", str(where / "a?b"))
    monkeypatch.setattr(ingest, "write_delivery", fails)
    result = ingest.accept(make_tar(files), store)
    assert not any("onetrace-staging" in r for r in result.rows), result.rows


def test_a_failure_that_is_not_the_viewers_is_not_tagged_as_its_words(checked, store,  # noqa: F811
                                                                    monkeypatch):
    import onetrace_console.viewer.model as model

    from onetrace_console.pages import render_executions
    #: A list draws each run's `list_row`, not its full model.
    monkeypatch.setattr(model, "list_row", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("not the viewer's")))
    #: As a run stored before its list row was kept, so the list reads it live.
    store.put_run(replace(checked, list_row=""))
    listed = render_executions([store.get_run(checked.key)], store, generated_at=GENERATED_AT)
    block = re.search(r'<section data-section="unshowable-runs">.*?</section>', listed, re.S)
    assert block and 'data-words="error"' in block.group(0)
    assert 'data-words="viewer"' not in block.group(0)
