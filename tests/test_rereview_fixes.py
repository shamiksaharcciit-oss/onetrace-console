"""The second confirmation review's console findings.

    None may crash a page.  /  Config errors: print a clean message with a `fix:` line, never
    a traceback.

A second fresh reviewer confirmed the first review's ten findings closed, then found these, each
by running it. The viewer's halves are canary 2491b86 and b7c7f52, re-vendored here.

B1. A lone surrogate reached pages through the Overview's day-change marker, which reads stored
    receipts itself: ingest 500, every later ingest 500, and no restart.
B2. A check that outran its timeout left a stored run with no check report, and the next start
    re-raised `PageError`: one upload, and the console never started again.
S1. A store integrity failure was shown as "the viewer's reason", under "held exactly as
    delivered".
S2. Start-up still ended in a traceback for an unusable store folder, an unreadable or deeply
    nested configuration, and control characters in a path or host.
S4. Every diverging Diff page printed a Python dict for the first difference.
N1. A host that is not this machine's was called a busy port; `::1` was called unresolvable.
N6. A delivery nested past what JSON can read answered 500 instead of being refused.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

import pytest

from onetrace_console.pages import CASE, render_execution
from tests.conftest import ipv6_loopback_port, make_tar
from tests.test_home_and_diff import diverging  # noqa: F401  (fixture)
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_review_fixes import _serve_with, _refused_in_words
from tests.test_unreadable import RUN_ID, _renamed, _resummed, _stored, _text


def _with_raw(files, part, raw):
    """The clean fixture renamed, one receipt's `instrument[part]` set to raw JSON text."""
    out = _renamed(files)
    rel = json.loads(out["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    data = json.loads(out[rel].decode("utf-8"))
    data["instrument"][part] = "__PLANTED__"
    out[rel] = json.dumps(data, ensure_ascii=False).replace('"__PLANTED__"', raw).encode("utf-8")
    return _resummed(out)


# ------------------------------------------------------------ B1: the day-change marker

@pytest.fixture
def two_days(files, store, checked):  # noqa: F811
    """The clean run, received yesterday; the same pipeline today, with a lone surrogate in a
    recorded digest -- the review's probe_marker_surrogate.py."""
    store.put_run(replace(checked, received_at="2026-09-28T09:00:00+00:00"))
    bad = _stored(_with_raw(files, "manifest_digest", '"\\ud800"'), store)
    store.put_run(replace(bad, received_at="2026-09-29T09:00:00+00:00"))
    return store


def test_a_lone_surrogate_in_a_recorded_digest_marks_nothing_and_says_so(two_days):
    from onetrace_console.render import HOME, render_all
    home = render_all(two_days, generated_at=GENERATED_AT)[HOME]
    home.encode("utf-8")
    by_day = re.search(r'<section data-section="by-day">.*?</section>', home, re.S).group(0)
    assert "The receipts of 1 of 2 runs could not be read" in _text(by_day)
    assert "data-change-marker" not in by_day


def test_ingest_and_restart_survive_it(server, files, tmp_path):
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    from tests.test_serve import _post
    base, root = server
    assert _post(base, "/v1/runs", make_tar(files))[0] == 200
    status, body = _post(base, "/v1/runs", make_tar(_with_raw(files, "manifest_digest",
                                                                    '"\\ud800"')))
    assert status == 200, body[:300]
    assert _post(base, "/v1/runs", make_tar(files))[0] == 200
    _render_startup_pages(Store(root / "store"), root)


def test_a_page_that_cannot_be_drawn_is_stated_and_the_others_are_drawn(checked, store,  # noqa: F811
                                                                      monkeypatch, capsys):
    import onetrace_console.render as render
    from onetrace_console.unreadable import PAGE_FAILED
    monkeypatch.setattr(render, "render_home", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("an unforeseen failure")))
    pages = render.render_all(store, generated_at=GENERATED_AT)
    assert PAGE_FAILED in _text(pages[render.HOME])
    assert "RuntimeError: an unforeseen failure" in _text(pages[render.HOME])
    assert any('data-run="' in html for href, html in pages.items() if href != render.HOME)
    assert "Traceback" in capsys.readouterr().err


def test_a_page_that_cannot_be_written_as_utf8_is_stated_not_raised(tmp_path, capsys):
    from onetrace_console.serve import PAGES_DIRNAME, _write
    from onetrace_console.unreadable import PAGE_FAILED
    _write(tmp_path, "home.html", "<p>\ud800</p>")
    written = (tmp_path / PAGES_DIRNAME / "home.html").read_bytes().decode("utf-8")
    assert PAGE_FAILED in _text(written) and "UnicodeEncodeError" in _text(written)


# ------------------------------------------------------------------ B2: an unfinished check

def test_a_check_that_does_not_finish_reads_could_not_check(files, store, monkeypatch):
    """The check runner records it; the run is stored, checked, and says why."""
    import onetrace_console.checks as checks
    from onetrace_console.checks import COULD_NOT_CHECK, run_and_record
    from onetrace_console.ingest import accept
    monkeypatch.setattr(checks, "CHECK_TIMEOUT_SECONDS", 0.001)
    run = run_and_record(accept(make_tar(files), store).run, store)
    assert run.check_verdict == COULD_NOT_CHECK and run.check_report
    assert "did not finish" in run.check_note


def test_the_check_waits_as_long_as_staging_does():
    """Staging's verifier call passed and the check timed out after it: never again."""
    import inspect

    from onetrace_console import checks, staging
    allowed = inspect.signature(staging.ask_the_verifier).parameters["timeout"].default
    assert checks.CHECK_TIMEOUT_SECONDS >= allowed


def test_a_stored_run_with_no_check_report_does_not_stop_a_restart(files, store, tmp_path):
    """The review's probe_unchecked_run_restart.py: a process stopped during the check leaves
    exactly this. Its pages say so; the others are drawn; the console starts."""
    from onetrace_console.ingest import accept
    from onetrace_console.serve import PAGES_DIRNAME, _render_startup_pages
    from onetrace_console.unreadable import NOT_CHECKED
    run = accept(make_tar(files), store).run
    assert not run.check_report
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    case = (root / PAGES_DIRNAME / "runs" / run.key / CASE).read_text(encoding="utf-8")
    assert NOT_CHECKED in _text(case)


# ------------------------------------------------------------ S1: not the viewer's reason

def test_a_store_integrity_failure_is_not_called_the_viewers_reason(checked, store):  # noqa: F811
    from onetrace_console.render import render_all
    from onetrace_console.unreadable import HELD, RUN_FAILED
    key = dict(checked.listing)["MANIFEST.json"]
    path = store.root / "objects" / key[:2] / key
    assert path.is_file(), "the store keeps an object where store.py says it does"
    path.write_bytes(path.read_bytes() + b" ")
    page = render_execution(checked, store, generated_at=GENERATED_AT).pages[CASE]
    assert RUN_FAILED in _text(page) and "StoreError" in _text(page)
    assert HELD not in _text(page), "it does not claim the bytes are as delivered"
    render_all(store, generated_at=GENERATED_AT)


# ------------------------------------------------------------------------ S2: start-up

@pytest.mark.parametrize("part", ["store", "pages", "access_log"])
def test_a_store_folder_that_is_a_file_is_refused_in_words(tmp_path, monkeypatch, capsys, part):
    root = tmp_path / "data"
    root.mkdir()
    (root / part).write_text("a file where a folder belongs", encoding="utf-8")
    assert _serve_with(tmp_path, monkeypatch, {"store_root": root.as_posix(),
                                               "sign_in": {"enabled": False}}) == 1
    _refused_in_words(capsys, "cannot use store_root")


def test_a_configuration_it_cannot_read_is_refused_in_words(tmp_path, monkeypatch, capsys):
    from pathlib import Path

    def denied(self, *a, **k):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(Path, "read_text", denied)
    assert _serve_with(tmp_path, monkeypatch, {"store_root": (tmp_path / "d").as_posix()}) == 1
    _refused_in_words(capsys, "")


def test_a_configuration_nested_too_deeply_is_refused_in_words(tmp_path, monkeypatch, capsys):
    from onetrace_console import serve
    from onetrace_console.config import ENV_VAR
    path = tmp_path / "config.json"
    path.write_text("[" * 5000 + "]" * 5000, encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    assert serve.main([]) == 1
    _refused_in_words(capsys, "")


@pytest.mark.parametrize("body", [{"host": "127.0.0.1\x00"}, {"store_root": "data\x00x"},
                                  {"sign_in": {"enabled": True, "tls_cert_path": "a\x00.pem",
                                               "tls_key_path": "k.pem"}}],
                         ids=["host", "store-root", "tls-path"])
def test_a_control_character_in_a_name_is_refused_in_words(tmp_path, monkeypatch, capsys, body):
    body = {"store_root": (tmp_path / "d").as_posix(), **body}
    assert _serve_with(tmp_path, monkeypatch, body) == 1
    err = _refused_in_words(capsys, "")
    assert "control character" in err


# ----------------------------------------------------------------- S4: the first difference

def test_the_first_difference_is_named_not_printed_as_a_dict(diverging):  # noqa: F811
    from onetrace_console.render import render_diff
    comparison, store = diverging
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    localized = " ".join(re.findall(r'data-section="localized">(.*?)</', page, re.S))
    assert "{'index'" not in page
    assert "stage 4 · split" in _text(localized) or "The set it localized" in page


# ------------------------------------------------------------------------ N1 and N6

def test_a_host_that_is_not_this_machines_is_said_to_be_so(tmp_path, monkeypatch, capsys):
    assert _serve_with(tmp_path, monkeypatch, {"host": "192.0.2.1",
                                               "store_root": (tmp_path / "d").as_posix(),
                                               "sign_in": {"enabled": False}}) == 1
    err = _refused_in_words(capsys, "cannot listen on 192.0.2.1")
    assert "not an address of this machine" in err and "another process" not in err


def test_ipv6_loopback_is_listened_on(tmp_path, monkeypatch, capsys):
    from onetrace_console import serve

    class Listening(Exception):
        pass

    def reached(self):
        raise Listening(self.server_address)
    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", reached)
    from onetrace_console.config import ENV_VAR
    free = ipv6_loopback_port()
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"host": "::1", "port": free, "store_root": (tmp_path / "d").as_posix(),
                                "sign_in": {"enabled": False}}), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    with pytest.raises(Listening):
        serve.main([])


def test_a_delivery_nested_past_json_is_refused_not_a_500(files, store):
    from onetrace_console.ingest import Rejection, accept
    out = dict(files)
    out["MANIFEST.json"] = ("[" * 5000 + "]" * 5000).encode("utf-8")
    result = accept(make_tar(_resummed(out)), store)
    assert isinstance(result, Rejection), result
    assert any("MANIFEST.json" in r for r in result.rows)
