"""In the console, what the viewer refuses is stated on a page, never a crash.

    Each malformed shape becomes a clean refusal (`VerbReportUnreadable` or its model
    equivalent). None may crash a page.

The viewer refuses a record with a receipt part it cannot read (`RecordUnreadable`) or a file
its manifest names and the run lacks (`RecordError`), and an SDK report it cannot read
(`VerbReportUnreadable`). The console may not refuse such a run at ingest -- the 422 set is
kept to damaged sums and unknown formats -- so the run is stored and checked like
any other, and its pages must say what happened. Before this change the refusal escaped the
page code, and each test below names what it did then.
"""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from onetrace_console.checks import run_and_record
from onetrace_console.ingest import SUMS_NAME, accept
from onetrace_console.pages import (ANSWER, AUTHORIZATION, CASE, render_execution,
                                    render_executions)
from onetrace_console.unreadable import LIST_HEADING, TITLE
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_pages import GENERATED_AT, assert_the_prohibitions, checked  # noqa: F401

RUN_ID = "a-run-the-viewer-refuses"


def _resummed(files: dict[str, bytes]) -> dict[str, bytes]:
    body = {p: b for p, b in files.items() if p != SUMS_NAME}
    body[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                 for p, b in body.items()) + "\n").encode("utf-8")
    return body


def _renamed(files: dict[str, bytes]) -> dict[str, bytes]:
    """Its own identity, so a store holding the clean fixture stores this one too."""
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = RUN_ID
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return out


def malformed(files: dict[str, bytes], part: str = "anchor", value="x") -> dict[str, bytes]:
    """The clean fixture with one receipt part in a shape the viewer cannot read, its sums
    recomputed: undamaged by its own sums, so ingest stores it (the check then finds it)."""
    out = _renamed(files)
    rel = json.loads(out["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    data = json.loads(out[rel].decode("utf-8"))
    data[part] = value
    out[rel] = json.dumps(data).encode("utf-8")
    return _resummed(out)


def missing_a_receipt(files: dict[str, bytes]) -> dict[str, bytes]:
    """The manifest names a receipt the delivery does not carry, and the sums list only what
    is there: stored, and "a missing chain file is the verifier's finding, after storing"."""
    out = _renamed(files)
    rel = json.loads(out["MANIFEST.json"].decode("utf-8"))["chain"][1]["file"]
    del out[rel]
    return _resummed(out)


def _stored(files, store):
    _require_installed()
    accepted = accept(make_tar(files), store)
    assert accepted.run is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)


def _text(html: str) -> str:
    from html import unescape
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


# ---------------------------------------------------------------- one run's own pages

@pytest.mark.parametrize("build,reason", [
    (malformed, "`anchor` is 'x', not an object"),
    (missing_a_receipt, "which is not in the run directory"),
], ids=["a-part-it-cannot-read", "a-receipt-the-manifest-names-is-missing"])
def test_a_run_the_viewer_refuses_gets_a_page_that_says_so(files, store, build, reason):
    """Before: `render_execution` raised (RecordUnreadable, or RecordError for the missing
    receipt), so the run had no pages at all."""
    run = _stored(build(files), store)
    pages = render_execution(run, store, generated_at=GENERATED_AT).pages
    for name in (ANSWER, CASE):
        page = pages[name]
        text = _text(page)
        assert TITLE in text and RUN_ID in text and reason in text, name
        assert 'data-section="ladder"' not in page, "no page is drawn from the record"
        assert_the_prohibitions(name, page)
    assert "No authorization records" in _text(pages[AUTHORIZATION]), "its board 3 page too"


def test_the_stated_page_claims_nothing_about_the_record(files, store):
    run = _stored(malformed(files), store)
    text = _text(render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]).lower()
    for claim in ("checks out", "records agree", "contradicts itself", "nothing is missing",
                  "re-run and matched"):
        assert claim not in text, claim


# ---------------------------------------------------------------- the lists

def test_a_list_names_the_runs_it_cannot_show_and_counts_them(files, store, checked):  # noqa: F811
    """Before: `render_executions` raised for the whole list, so every list holding the run
    failed -- and every list is rebuilt on each ingest."""
    bad = _stored(malformed(files), store)
    page = render_executions([checked, bad], store, generated_at=GENERATED_AT)
    shown = re.search(r'<section data-section="executions">.*?</section>', page, re.S).group(0)
    refused = re.search(r'<section data-section="unshowable-runs">.*?</section>', page, re.S)
    assert refused, "the run is named, not dropped"
    assert f'data-run="{checked.run_id}"' in shown and RUN_ID not in shown
    assert LIST_HEADING in _text(refused.group(0))
    assert RUN_ID in refused.group(0) and "`anchor` is 'x', not an object" in _text(refused.group(0))
    assert "1 of 2" in _text(shown), "the viewer's count carries the runs it was handed"


def test_a_list_of_only_such_runs_still_renders(files, store):
    bad = _stored(malformed(files), store)
    page = render_executions([bad], store, generated_at=GENERATED_AT)
    assert "0 of 1" in _text(page) and RUN_ID in page


def test_a_list_of_clean_runs_is_unchanged(files, store, checked):  # noqa: F811
    page = render_executions([checked], store, generated_at=GENERATED_AT)
    assert 'data-section="unshowable-runs"' not in page


# ---------------------------------------------------------------- over HTTP, and on restart

def test_ingesting_it_answers_200_and_serves_the_page(server, files):
    """Before: the POST stored the run and answered 500, and each later ingest answered 500
    as well, since every list is rebuilt with every run in it."""
    from tests.test_serve import _get, _post
    base, _ = server
    status, body = _post(base, "/v1/runs", make_tar(malformed(files)))
    assert status == 200, body[:300]
    result = json.loads(body)
    s, page = _get(base, result["pages"]["case"])
    assert s == 200 and TITLE in _text(page.decode("utf-8"))
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, ("a clean run ingested after it", body[:300])


def test_a_restart_over_a_store_holding_it_starts(files, store, tmp_path):
    """Before: `_render_startup_pages` raised, and `main()` never reached the listener."""
    from onetrace_console.serve import _render_startup_pages
    _stored(malformed(files), store)
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    assert any(root.rglob("case.html")) and (root / "pages" / "home.html").is_file()

