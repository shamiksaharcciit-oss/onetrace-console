"""Round 4's findings in the console, and NEW-11.

The fourth confirmation review re-ran the third's probes and found these. The viewer's halves
(resolved names in its duplicate check, a lookup set for declared stages, capped lists, a
record's words escaped) are canary 9515a20, re-vendored here.

B1   Names were compared as written: one file spelled another way got past each comparison.
     Here: the tar's own members, and the chain's names when ingest reads a receipt's format.
B2   Home said an early-stopped SDK run was missing nothing, while its own page said "No":
     ingest took the declared stages from the chain, and the pinned SDK's manifest declares
     none. Home now counts rung 3 as the run's page decides it, stored at check time.
B4   On Windows an upload naming `notes/a:b.txt` answered 500 (the safe-extraction filter's
     ValueError), and
S2   names Windows cannot hold answered 422 outside the set. Both are now refusals in (b).
S1   A 3.9 KB upload drew 39 MB of pages; every list rebuilt every run's full model.
S3   One wrong-typed run record stopped the start or blanked other runs' pages.
S4   A deeply nested or wrong-typed access_log/HEAD.json stopped the start with a traceback or
     left every request unanswered.
S5   An unreadable comparison record was dropped without a word, and its old Diff page served.
Notes: a lone surrogate in the configuration was called a control character; infinity was
     refused without the word "finite"; `notes/NUL` was accepted on Windows and went to the
     null device; a staging area that could not be deleted raised past ingest with its path.
NEW-11 (§2): wherever a page shows a record's own words, C0 and C1 controls, the bidirectional
     controls and lone surrogates are shown escaped as \\uXXXX.
"""
from __future__ import annotations

import errno
import io
import json
import os
import re
import tarfile
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.checks import run_and_record
from onetrace_console.ingest import Accepted, Rejection, accept
from onetrace_console.pages import (ANSWER, AUTHORIZATION, CASE, render_execution,
                                    render_executions)
from onetrace_console.render import COUNTS, HOME, render_all
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_review_fixes import _refused_in_words, _serve_with
from tests.test_unreadable import _renamed, _resummed, _stored, _text, missing_a_receipt

WINDOWS = os.name == "nt"
HOLDABLE = "a name this host can hold"


def _with_note(files, name: str, blob: bytes = b"a note\n"):
    out = dict(files)
    out[name] = blob
    return _resummed(out)


def _section(page: str, name: str) -> str:
    found = re.search(rf'<(\w+) data-section="{name}"[^>]*>(.*?)</\1>', page, re.S)
    assert found, f"no {name} section"
    return found.group(2)


def _rung(page: str, key: str) -> str:
    return re.search(rf'<tr data-rung="{key}" data-state="([^"]+)"', page).group(1)


# ---------------------------------------------------------------------------------- B1

@pytest.mark.parametrize("names", [("notes/a.txt", "notes/./a.txt")]
                         + ([("notes/Note.txt", "notes/note.txt")] if WINDOWS else []),
                         ids=lambda n: "|".join(n))
def test_one_file_named_twice_by_the_tar_is_refused_inside_the_set(files, store, names):
    out = dict(files)
    for i, name in enumerate(names):
        out[name] = f"note {i}\n".encode()
    result = accept(make_tar(_resummed(out)), store)
    assert isinstance(result, Rejection), result
    assert any("each path appears once" in r for r in result.rows), result.rows
    assert store.runs() == ()


def test_a_receipt_the_chain_names_another_way_is_still_format_checked(files, store):
    """The format check looked the chain's name up as written: `receipts/./02-alpha.json` was
    not found, so its unknown format was never read, and the run was stored."""
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    rel = manifest["chain"][1]["file"]
    receipt = json.loads(out[rel].decode("utf-8"))
    receipt["format"] = "stage-receipt/9.9"
    out[rel] = json.dumps(receipt).encode("utf-8")
    head, name = rel.rsplit("/", 1)
    manifest["chain"][1] = dict(manifest["chain"][1], file=f"{head}/./{name}")
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    result = accept(make_tar(_resummed(out)), store)
    assert isinstance(result, Rejection), "a receipt in an unknown format was stored"
    assert any("stage-receipt/9.9" in r for r in result.rows), result.rows


def _spelled(files, n: int) -> dict[str, bytes]:
    """The chain names one receipt `n` more times, each spelled differently (round 4's probe)."""
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    rel = manifest["chain"][1]["file"]
    head, name = rel.rsplit("/", 1)
    spellings = [f"{head}/" + "./" * (k + 1) + name if k % 2 == 0
                 else f"{head}/" + "x/../" * k + name for k in range(n)]
    manifest["chain"] = manifest["chain"] + [dict(manifest["chain"][1], file=s)
                                             for s in spellings]
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return _resummed(out)


def test_the_113_kb_upload_that_drew_254_mb_of_pages_is_stored_and_stated(server, files):
    """Round 4's probe_new1_e2e.py: 400 spellings of one receipt. Stored (it is no damage), its
    pages say the viewer's refusal, and every page written together stays small."""
    from tests.test_serve import _get, _post
    from onetrace_console.serve import PAGES_DIRNAME
    base, root = server
    body = make_tar(_spelled(files, 400))
    status, answer = _post(base, "/v1/runs", body)
    assert status == 200, answer[:300]
    case = _get(base, json.loads(answer)["pages"]["case"])[1].decode("utf-8")
    assert "more than once" in _text(case)
    written = sum(p.stat().st_size for p in (root / PAGES_DIRNAME).rglob("*") if p.is_file())
    assert written < 5_000_000, f"{written} bytes of pages from a {len(body)}-byte upload"


# ---------------------------------------------------------------------------------- B2

def _early_stopped(tmp_path: Path) -> dict[str, bytes]:
    """A run from the pinned SDK that stopped early: three stages declared, two run. Made with
    the SDK's own Recorder, delivered as the SDK leaves it (round 4's probe_sdk_early_stop)."""
    from onetrace.emit import Instrument, Recorder
    code = tmp_path / "pipeline.py"
    code.write_text("# the pipeline this run stands for\n", encoding="utf-8")
    out = tmp_path / "early-stop"
    rec = Recorder(out, run_id="early-stop", declared_stages=["load", "clean", "publish"],
                   manifest=code, policy="fail-closed", anchor_reason="a test")

    @rec.stage("load", Instrument("loader", "reader", "1.0.0", {"rows": "3"}))
    def load(ctx):
        return ctx.write_json("rows.json", {"rows": ["1", "2", "3"]})

    @rec.stage("clean", Instrument("cleaner", "transform", "1.0.0", {"drop": "none"}))
    def clean(ctx, rows):
        return ctx.write_json("clean.json", ctx.read_json(rows))

    clean(load())
    rec.close()                                      # "publish" never ran
    return _resummed({p.relative_to(out).as_posix(): p.read_bytes()
                      for p in sorted(out.rglob("*")) if p.is_file()})


def test_a_run_that_stopped_early_is_missing_a_stage_on_home_as_on_its_own_page(tmp_path,
                                                                               store):
    run = _stored(_early_stopped(tmp_path), store)
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    assert _rung(case, "nothing-missing") == "no"
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[HOME]
    rung = _text(re.search(r'<tr data-rung="nothing-missing">(.*?)</tr>', home, re.S).group(1))
    assert "0 of 1" in rung and "1 missing a declared stage" in rung, rung
    tally = _text(re.search(r'data-tally="missing-a-declared-stage"[^>]*>(.*?)</li>',
                            pages[COUNTS], re.S).group(1))
    assert tally.startswith("1 run of 1"), tally
    attention = _text(_section(home, "needs-attention"))
    assert "Needs attention first · 1 of 1" in attention and "A declared stage missing" in attention
    recent = _text(re.search(r'<tr data-recent="[^"]*">(.*?)</tr>', home, re.S).group(1))
    assert "2 of 3" in recent, recent
    pipeline = _text(re.search(r'<tr data-pipeline="[^"]*">(.*?)</tr>', home, re.S).group(1))
    assert "load → clean → publish" in pipeline, pipeline


def test_the_declared_stages_are_the_receipts_own_not_the_chains(tmp_path, store):
    run = _stored(_early_stopped(tmp_path), store)
    assert run.declared_stages == ("load", "clean", "publish")
    assert (run.stage_count, run.recorded_count) == (3, 2)
    assert run.nothing_missing == "no"


def test_a_run_with_gaps_is_counted_on_home_as_its_own_page_says(files, store):
    """Every declared stage recorded, and items left unprocessed: the page's rung 3 is No, and
    Home counted it "missing nothing" from the chain against the declared stages."""
    run = _stored(_with_receipt(files, lambda d: d["emission"].update(gaps=[0, 0, 0]), "gaps"),
                  store)
    assert (run.recorded_count, run.stage_count) == (3, 3)
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    assert _rung(case, "nothing-missing") == "no"
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    rung = _text(re.search(r'<tr data-rung="nothing-missing">(.*?)</tr>', home, re.S).group(1))
    assert "0 of 1" in rung and "1 missing a declared stage" in rung, rung


def test_a_run_whose_record_the_viewer_refuses_is_not_counted_as_missing_nothing(files, store):
    """Round 4's probe_missing_claim.py: its run page cannot be drawn, and Home counted it
    "missing nothing". Neither is established, and Home says so."""
    run = _stored(missing_a_receipt(files), store)
    assert run.nothing_missing == ""
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    rung = _text(re.search(r'<tr data-rung="nothing-missing">(.*?)</tr>', home, re.S).group(1))
    assert "0 of 1" in rung and "1 not established" in rung, rung


# --------------------------------------------------------------------------- B4 and S2

#: Names no host holds: one part longer than a file name may be.
EVERY_HOST = ["notes/" + "x" * 300 + ".txt"]
#: Names Windows cannot hold (round 4's probe_member_names.py and probe_winnames.py, and
#: `notes/NUL`, which staging wrote to the null device).
WINDOWS_ONLY = ["notes/a:b.txt", "notes/what?.txt", "notes/a<b>.txt", 'notes/a"b.txt',
                "notes/a|b.txt", "notes/a*b.txt", "notes/a\x01b.txt", "notes/NUL",
                "notes/nul.txt", "notes/CON", "notes/com1.json", "notes/LPT9",
                "notes/trailing.", "notes/trailing ", "notes/" + "y" * 240 + ".txt"]


@pytest.mark.parametrize("name", EVERY_HOST + (WINDOWS_ONLY if WINDOWS else []),
                         ids=lambda n: n[:24])
def test_a_name_this_host_cannot_hold_is_refused_inside_the_set(files, store, name):
    result = accept(make_tar(_with_note(files, name)), store)
    assert isinstance(result, Rejection), result
    assert result.status == 422
    assert any(HOLDABLE in r for r in result.rows), result.rows
    assert not any("can be examined" in r for r in result.rows), result.rows
    assert store.runs() == ()


def test_the_safe_extraction_filter_raising_valueerror_is_a_refusal_not_a_500(files, store,
                                                                            monkeypatch):
    """B4: `tarfile.data_filter` raises ValueError from `ntpath.commonpath` on Windows."""
    def filtered(member, dest):
        if member.name.startswith("notes/"):
            raise ValueError("Can't mix absolute and relative paths")
        return member
    monkeypatch.setattr(tarfile, "data_filter", filtered)
    result = accept(make_tar(_with_note(files, "notes/a.txt")), store)
    assert isinstance(result, Rejection), result
    assert any("safe-extraction filter" in r and "ValueError" in r for r in result.rows)


@pytest.mark.parametrize("code", [errno.EINVAL, errno.ENAMETOOLONG])
def test_a_name_staging_cannot_write_is_a_refusal_inside_the_set(files, store, monkeypatch,
                                                                 code):
    """Belt and braces for a name the checks above did not foresee: a staging write refused
    for the name is (b), not "the delivery can be examined"."""
    import onetrace_console.ingest as ingest

    def refused(files, dest):
        raise OSError(code, os.strerror(code), str(dest / "notes" / "odd"))
    monkeypatch.setattr(ingest, "write_delivery", refused)
    result = accept(make_tar(files), store)
    assert isinstance(result, Rejection), result
    assert any(HOLDABLE in r for r in result.rows), result.rows
    assert not any("staging" in r.lower() or "onetrace-" in r for r in result.rows), result.rows


# ---------------------------------------------------------------------------------- S1

def _with_receipt(files, change, run_id: str) -> dict[str, bytes]:
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = run_id
    rel = manifest["chain"][0]["file"]
    receipt = json.loads(out[rel].decode("utf-8"))
    change(receipt)
    out[rel] = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    return _resummed(out)


def _gz(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, blob in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def _written(pages: dict[str, str]) -> int:
    return sum(len(p.encode("utf-8")) for p in pages.values())


def test_the_39_mb_upload_of_a_million_gaps_is_stored_and_draws_small_pages(files, store):
    """Round 4's probe_shapes_amp.py gaps 1000000: a 3.9 KB upload drew 39 MB of run pages.
    Ingest does not refuse it; its pages draw the first hundred gaps and a count."""
    from onetrace_console.viewer.model import LIST_CAP
    body = _gz(_with_receipt(files, lambda d: d["emission"].update(gaps=[0] * 1_000_000),
                             "a-million-gaps"))
    assert len(body) < 20_000
    _require_installed()
    accepted = accept(body, store)
    assert isinstance(accepted, Accepted), getattr(accepted, "rows", accepted)
    run = run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)
    pages = render_execution(run, store, generated_at=GENERATED_AT).pages
    assert f"{1_000_000 - LIST_CAP} more" in _text(pages[ANSWER])
    assert _written(pages) < 3_000_000, _written(pages)
    every = render_all(store, generated_at=GENERATED_AT)
    assert max(len(p) for p in every.values()) < 1_000_000


def test_twenty_thousand_declared_stages_draw_a_hundred_and_a_count(files, store):
    """Round 4's 47.8 KB upload (B3). The Overview's pipelines table names the first hundred."""
    from onetrace_console.viewer.model import LIST_CAP
    from onetrace_console.viewer.sentences import template
    names = [f"s{i}" for i in range(20_000)]
    run = _stored(_with_receipt(files, lambda d: d["coverage"].update(
        declared_stages=d["coverage"]["declared_stages"] + names), "declared"), store)
    assert run.stage_count == 20_003 and len(run.declared_stages) == LIST_CAP
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    cell = _text(re.search(r'<tr data-pipeline="[^"]*">(.*?)</tr>', home, re.S).group(1))
    assert template("list.more").format(n=str(20_003 - LIST_CAP)) in cell, cell[:300]
    assert "s19999" not in cell and len(home) < 200_000


def test_a_list_is_drawn_from_light_rows_each_run_read_once_per_render(checked, store,  # noqa: F811
                                                                       files, monkeypatch):
    import onetrace_console.viewer.model as model
    import onetrace_console.viewer.record as record
    _stored(_resummed(_renamed(files)), store)
    monkeypatch.setattr(model, "build_model", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("a list built a run's full model")))
    reads = []
    real = record.read_record
    monkeypatch.setattr(record, "read_record", lambda folder: reads.append(1) or real(folder))
    pages = render_all(store, generated_at=GENERATED_AT)
    lists = [p for h, p in pages.items() if 'data-view="executions"' in p]
    assert len(lists) > 5
    assert all("a list built" not in p for p in lists)
    assert f'data-run="{checked.run_id}"' in pages["executions-all.html"]
    #: Once per run per render at most; since the follow-up batch,
    #: not at all for a run whose check kept its row.
    assert len(reads) == 0, f"{len(reads)} reads for 2 checked runs over {len(lists)} lists"


def test_a_list_names_a_run_the_viewer_refuses_as_before(checked, store, files):  # noqa: F811
    from onetrace_console.unreadable import LIST_HEADING
    refused = _stored(missing_a_receipt(files), store)
    page = render_executions([checked, refused], store, generated_at=GENERATED_AT)
    assert LIST_HEADING in _text(page) and "a-run-the-viewer-refuses" in _text(page)


# ---------------------------------------------------------------------------------- S3

def _edit_record(store, run, change) -> Path:
    path = store.root / "runs" / f"{run.key}.json"
    if callable(change):
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data), encoding="utf-8")
    else:
        path.write_text(change, encoding="utf-8")
    return path


WRONG = {
    "received_at an int": lambda d: d.update(received_at=5),
    "run_id an int": lambda d: d.update(run_id=5),
    "could_not_check with no reason": lambda d: d.update(check_verdict="could_not_check",
                                                         check_note="", topology_note=""),
    "a flag an int": lambda d: d.update(flags=[5]),
    "an unknown verdict": lambda d: d.update(check_verdict="maybe"),
    "a declared stage an int": lambda d: d.update(declared_stages=[5]),
    "a count a string": lambda d: d.update(stage_count="3"),
    "a count true": lambda d: d.update(recorded_count=True),
    "a listing entry not a pair": lambda d: d.update(listing=[["MANIFEST.json"]]),
    "a rung state unknown": lambda d: d.update(nothing_missing="perhaps"),
    "nested too deep": "[" * 100_000 + "]" * 100_000,
}


@pytest.mark.parametrize("change", WRONG.values(), ids=WRONG.keys())
def test_a_wrong_typed_run_record_is_named_and_stops_nothing(checked, store, files,  # noqa: F811
                                                             tmp_path, change):
    from onetrace_console.incident_pages import INCIDENTS
    from onetrace_console.serve import PAGES_DIRNAME, _render_startup_pages
    from onetrace_console.unreadable import PAGE_FAILED, RUN_FAILED
    other = _stored(_resummed(_renamed(files)), store)
    path = _edit_record(store, checked, change)
    assert [r.key for r in store.runs()] == [other.key]
    assert any(path.name in u for u in store.unreadable_runs), store.unreadable_runs
    root = tmp_path / "root"
    root.mkdir()
    _render_startup_pages(store, root)
    pages = root / PAGES_DIRNAME
    home = (pages / HOME).read_text(encoding="utf-8")
    assert PAGE_FAILED not in home and path.name in _text(_section(home, "unreadable-records"))
    assert PAGE_FAILED not in (pages / INCIDENTS).read_text(encoding="utf-8")
    case = (pages / "runs" / other.key / CASE).read_text(encoding="utf-8")
    assert RUN_FAILED not in case and "ValueError" not in case


def test_a_rule_that_fails_on_one_run_is_named_and_the_rest_are_derived(checked, store,  # noqa: F811
                                                                        files):
    """A run recorded `contradicts` whose report has no FAIL row: `_contradicts` raises, as it
    should, and that blanked Home, the Incidents page and every other run's pages."""
    from onetrace_console.incident_pages import INCIDENTS
    from onetrace_console.incidents import derive
    from onetrace_console.unreadable import PAGE_FAILED
    other = _stored(_resummed(_renamed(files)), store)
    store.put_run(replace(checked, check_verdict="contradicts"))
    derive(store)
    assert any(checked.key[:12] in u and "I-CONTRADICTS" in u for u in store.underived), \
        store.underived
    pages = render_all(store, generated_at=GENERATED_AT)
    assert PAGE_FAILED not in pages[HOME] and PAGE_FAILED not in pages[INCIDENTS]
    for page in (pages[HOME], pages[INCIDENTS]):
        assert "I-CONTRADICTS" in _text(_section(page, "underived"))
    case = render_execution(other, store, generated_at=GENERATED_AT).pages[CASE]
    assert "ValueError" not in case


def test_a_record_that_cannot_be_read_is_a_store_error_where_it_is_asked_for(checked,  # noqa: F811
                                                                            store):
    """Asked for by key -- a Diff page's pair, a compare -- it is said as the store's own
    damage, never raised as the record's TypeError or ValueError."""
    from onetrace_console.render import _held
    from onetrace_console.store import StoreError
    _edit_record(store, checked, WRONG["received_at an int"])
    with pytest.raises(StoreError, match=f"{checked.key}.json cannot be read"):
        store.get_run(checked.key)
    assert _held(store, checked.key) is None


def test_compare_says_a_run_record_cannot_be_read(server, files):
    from onetrace_console.serve import Handler
    from tests.test_serve import _post
    base, _root = server
    a = _stored(_resummed(_renamed(files)), Handler.store)
    b = _stored(files, Handler.store)
    _edit_record(Handler.store, a, WRONG["run_id an int"])
    status, body = _post(base, f"/compare?a={a.key}&b={b.key}")
    assert status == 400 and "cannot be read" in json.loads(body)["error"], body


def test_home_is_drawn_when_a_held_runs_check_report_is_gone(checked, store):  # noqa: F811
    """`records agree` reads each held run's stored report; one whose object had gone blanked
    Home (a StoreError the count did not catch)."""
    from onetrace_console.unreadable import PAGE_FAILED
    key = checked.check_report
    (store.root / "objects" / key[:2] / key).unlink()
    assert PAGE_FAILED not in render_all(store, generated_at=GENERATED_AT)[HOME]


def test_the_start_guard_names_a_run_whose_words_are_not_text():
    from onetrace_console.unreadable import _safe
    assert _safe(5) == "5"
    assert _safe("a\ud800b") == "a\\ud800b"


def test_the_store_knows_the_verdicts_and_rung_states_the_console_writes():
    """The store checks a record's verdict and rung 3 against lists spelled beside it, because
    `checks` imports the store; held in step with their sources here."""
    from onetrace_console.checks import VERDICTS
    from onetrace_console.store import _RUNG_STATES, _VERDICTS
    from onetrace_console.viewer.model import _COULDNT, _NO, _NOT_CHECKED, _YES
    assert set(_VERDICTS) == {""} | set(VERDICTS)
    assert set(_RUNG_STATES) == {""} | {s[0] for s in (_YES, _NO, _COULDNT, _NOT_CHECKED)}


# ---------------------------------------------------------------------------------- S4

HEADS = {
    "nested too deep": "[" * 100_000 + "]" * 100_000,
    "segment a string": json.dumps({"segment": "1", "segment_size": 0, "chain_head": None}),
    "segment true": json.dumps({"segment": True, "segment_size": 0, "chain_head": None}),
    "segment_size null": json.dumps({"segment": 1, "segment_size": None, "chain_head": None}),
    "segment_size negative": json.dumps({"segment": 1, "segment_size": -1, "chain_head": None}),
    "chain_head a number": json.dumps({"segment": 1, "segment_size": 0, "chain_head": 5}),
    "chain_head not a digest": json.dumps({"segment": 1, "segment_size": 0,
                                           "chain_head": "sha256:xyz"}),
}


@pytest.mark.parametrize("head", HEADS.values(), ids=HEADS.keys())
def test_an_access_log_head_that_is_not_its_own_is_refused_in_words(tmp_path, monkeypatch,
                                                                    capsys, head):
    root = tmp_path / "data"
    (root / "access_log").mkdir(parents=True)
    (root / "access_log" / "HEAD.json").write_text(head, encoding="utf-8")
    assert _serve_with(tmp_path, monkeypatch, {
        "store_root": root.as_posix(), "sign_in": {"enabled": False}}) == 1
    err = _refused_in_words(capsys, "cannot use store_root")
    assert "HEAD.json" in err


def test_an_access_log_head_of_its_own_still_opens(tmp_path):
    from onetrace_console.access_log import AccessLog
    log = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    log.append(principal="p", method="GET", path="/", status=200)
    again = AccessLog(tmp_path / "access_log", max_segment_bytes=1_000_000)
    assert again.verify_chain() == (True, "")


# ---------------------------------------------------------------------------------- S5

GARBAGE_KEY = "ab" * 32


def test_an_unreadable_comparison_record_is_named_on_home(checked, store):  # noqa: F811
    folder = store.root / "comparisons"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{GARBAGE_KEY}.json").write_text("{not json", encoding="utf-8")
    assert store.comparisons() == ()
    assert any(GARBAGE_KEY in u for u in store.unreadable_comparisons)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    said = _text(_section(home, "unreadable-comparisons"))
    assert f"{GARBAGE_KEY}.json" in said and "changed vs baseline" in said


def test_an_unreadable_records_old_pages_are_replaced_at_start_up(checked, store,  # noqa: F811
                                                                  tmp_path):
    """Round 4, PLAUSIBLE from reading the code: the old Diff page stayed on disk and was
    served. Measured here, and the same for a run record's own pages."""
    from onetrace_console.serve import PAGES_DIRNAME, _render_startup_pages
    from onetrace_console.unreadable import PAGE_FAILED
    (store.root / "comparisons").mkdir(parents=True, exist_ok=True)
    (store.root / "comparisons" / f"{GARBAGE_KEY}.json").write_text("[", encoding="utf-8")
    (store.root / "runs" / f"{'cd' * 32}.json").write_text("[", encoding="utf-8")
    root = tmp_path / "root"
    stale = {root / PAGES_DIRNAME / "diff" / f"{GARBAGE_KEY}.html",
             root / PAGES_DIRNAME / "runs" / ("cd" * 32) / CASE,
             root / PAGES_DIRNAME / "runs" / ("cd" * 32) / ANSWER}
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("<p>verdict: holds</p>", encoding="utf-8")
    _render_startup_pages(store, root)
    for path in stale:
        page = path.read_text(encoding="utf-8")
        assert "verdict: holds" not in page and PAGE_FAILED in _text(page), path
        assert "cannot be read" in _text(page)


# ------------------------------------------------------------------------------- notes

@pytest.mark.parametrize("where", ["host", "store_root", "tls"])
def test_a_lone_surrogate_in_the_configuration_is_named_as_one(tmp_path, monkeypatch, capsys,
                                                               where):
    body = {"sign_in": {"enabled": False}, "store_root": (tmp_path / "data").as_posix()}
    if where == "tls":
        body["sign_in"] = {"enabled": False, "tls_cert_path": "a\ud800.pem",
                           "tls_key_path": "k.pem"}
    else:
        body[where] = "a\ud800b"
    assert _serve_with(tmp_path, monkeypatch, body) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err and "lone surrogate" in err and "\nfix: " in err, err
    assert "control character" not in err, err


def test_infinity_is_refused_as_not_finite(tmp_path, monkeypatch, capsys):
    assert _serve_with(tmp_path, monkeypatch, {
        "sign_in": {"enabled": False}, "request_timeout_seconds": float("inf")}) == 1
    err = capsys.readouterr().err
    assert "a finite number above zero" in err and "\nfix: " in err, err


def test_a_staging_area_that_cannot_be_deleted_is_logged_without_its_path(files, store,
                                                                         tmp_path,
                                                                         monkeypatch, capsys):
    import onetrace_console.staging as staging
    root = tmp_path / "staging-root"
    monkeypatch.setattr(staging, "DEFAULT_STAGING_ROOT", root)
    monkeypatch.setattr(staging.shutil, "rmtree", lambda *a, **k: None)
    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), result
    err = capsys.readouterr().err
    assert "could not be deleted" in err, err
    assert str(root) not in err and "onetrace-staging-" not in err, err


# ------------------------------------------------------------------------------- NEW-11

UNSAFE_ID = "run‮\x00\x1b\r\n⁦\x85id"
SHOWN_ID = "run\\u202e\\u0000\\u001b\\u000d\\u000a\\u2066\\u0085id"


def _raw(page: str) -> list[str]:
    return [c for c in ("‮", "\x00", "\x1b", "⁦", "\x85") if c in page]


def test_a_run_id_with_control_and_bidi_characters_is_shown_escaped_on_every_page(files,
                                                                                store):
    from onetrace_console.unreadable import (render_unreadable_run, unshowable_runs_block,
                                             render_unchecked_run)
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = UNSAFE_ID
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    run = _stored(_resummed(out), store)
    assert run.run_id == UNSAFE_ID, "ingest keeps a record's words as they are"
    pages = dict(render_all(store, generated_at=GENERATED_AT))
    pages.update({f"run/{k}": v for k, v in
                  render_execution(run, store, generated_at=GENERATED_AT).pages.items()})
    pages["unreadable"] = render_unreadable_run(run, "a reason‮", generated_at=GENERATED_AT)
    pages["failed"] = render_unreadable_run(run, "x", generated_at=GENERATED_AT,
                                            from_viewer=False)
    pages["unchecked"] = render_unchecked_run(run, generated_at=GENERATED_AT)
    listed = render_executions([], store, generated_at=GENERATED_AT, of=1)
    pages["unshowable"] = unshowable_runs_block(listed, [(run, "why‮", True)])
    for name, page in pages.items():
        assert _raw(page) == [], name
    showing = {n for n, p in pages.items() if SHOWN_ID in p}
    assert {HOME, "executions-all.html", f"run/{ANSWER}", f"run/{CASE}",
            f"run/{AUTHORIZATION}", "unreadable", "failed", "unchecked",
            "unshowable"} <= showing, set(pages) - showing


def test_stage_names_with_bidi_characters_are_shown_escaped_on_home(files, store):
    def declare(d):
        d["coverage"]["declared_stages"] = d["coverage"]["declared_stages"] + ["re‮load"]
    _stored(_with_receipt(files, declare, "bidi-stages"), store)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    assert _raw(home) == []
    assert "re\\u202eload" in _section(home, "pipelines")


def test_the_diff_pages_record_words_are_shown_escaped():
    from types import SimpleNamespace

    from onetrace_console.render import _first_difference_summary, _ladder_table, _localized
    row = SimpleNamespace(index="1", stage="sp‮lit\x1b", verdict="FIRST DIFFERENCE",
                          baseline={"outputs": ["sha256:a\x00"]}, candidate={"outputs": []},
                          reason="why⁦")
    report = SimpleNamespace(ladder=[row], minimal_unclean_nodes=("no‮de",),
                             first_difference={"index": "1", "stage": "sp‮lit\x1b"})
    drawn = (_ladder_table(report, "diff", annotations=[])
             + _first_difference_summary(report, [], 0) + _localized(report))
    assert _raw(drawn) == [] and "sp\\u202elit\\u001b" in drawn and "no\\u202ede" in drawn


def test_the_same_change_list_shows_run_ids_escaped(checked, store, monkeypatch):  # noqa: F811
    import onetrace_console.overview as overview
    from onetrace_console.render import _same_change
    odd = replace(checked, run_id=UNSAFE_ID)
    monkeypatch.setattr(overview, "same_change", lambda c, s: overview.SameChange(
        "found", "1", "split‮", "settings", "sha256:0", "P1", 2, (odd,)))
    drawn = _same_change(None, store)
    assert _raw(drawn) == [] and SHOWN_ID in drawn and "split\\u202e" in drawn


def test_a_verbatim_layer_keeps_its_line_breaks(checked, store):  # noqa: F811
    from onetrace_console.incident_pages import _incident_item
    from onetrace_console.incidents import Incident
    item = _incident_item(Incident(id="i" * 64, rule="I-CONTRADICTS", subject=checked.key,
                                   subject_kind="run", source_sha="s", field_path="stdout",
                                   quoted="[FAIL   ] a\n[FAIL   ] b‮", evidence="x.html"))
    assert "[FAIL   ] a\n[FAIL   ] b\\u202e" in item
