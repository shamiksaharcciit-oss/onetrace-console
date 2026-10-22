"""Format 0.3's three new members, shown as onetrace-verify reads them and never computed here.

onetrace 0.4.0 writes `stage-receipt-chain/0.3`, which adds three things a run page speaks about:
- **optional stages** (`coverage.optional_stages`): a declared stage the run may skip. The check
  run with `--require-complete` passes a run that skipped only those, and says so in its own row
  (`run complete -- every required stage emitted; optional, not run: ...`). "Nothing declared is
  missing" quotes that row; it never decides from the receipts' lists that a skipped stage was
  optional.
- **a held step's attempted links** (`refused.attempted`): the plan held a step before it ran, and
  the receipt keeps the links it would have read. The check's own row (`step held before running
  -- attempted: ...`) is quoted beside the banner where the run stopped.
- **outputs_kept** (`none`): the run keeps no output files. "Records agree" quotes the check's
  `run: artifacts` row, which says the run declared it, rather than this page's sentence for a
  run delivered without them.

Each run is made here by the installed SDK, and each expected line is the verifier's own text
output for that run, read here: never a line typed into this file.
"""
from __future__ import annotations

import re
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

GENERATED_AT = "2026-10-04T12:00:00+00:00"
RAN_AT = "2026-09-26T12:00:00+02:00"


def _make(root: Path) -> dict[str, Path]:
    """Five runs from the installed SDK: one plain, and one for each new member (two for optional
    stages, one whose required stage is missing too)."""
    from onetrace.emit import EmissionRefused, Instrument, Recorder
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})

    def body(stage, reads=(), rec=None):
        def f(ctx):
            for r in reads:
                ctx.read_receipt(r)
            if rec is not None:
                rec.check_plan_first(ctx)
            return ctx.write_json(f"{stage}.json", {stage: "1"})
        return f

    def recorder(name, stages, **kw):
        return Recorder(str(root / name), run_id=name, declared_stages=stages, manifest=Path(__file__),
                        policy="fail-closed", topology=True, anchor_reason="a test record", **kw)

    r = recorder("plain", ["a", "b"])
    r.run_node("a", "1", tool, body("a")); r.run_node("b", "1", tool, body("b", ["a"])); r.close()
    r = recorder("optional", ["a", "b", "c"], optional_stages=["b"])
    r.run_node("a", "1", tool, body("a")); r.run_node("c", "1", tool, body("c", ["a"])); r.close()
    r = recorder("optional-and-required", ["a", "b", "c"], optional_stages=["b"])
    r.run_node("a", "1", tool, body("a")); r.close()
    r = recorder("held", ["a", "b", "c"], declared_edges=[{"from": "a", "to": "b"}, {"from": "b", "to": "c"}])
    r.run_node("a", "1", tool, body("a")); r.run_node("b", "1", tool, body("b", ["a"]))
    with pytest.raises(EmissionRefused):
        r.run_node("c", "1", tool, body("c", ["a"], r))
    r.close()
    r = recorder("nokeep", ["a", "b"], keep_outputs=False)
    r.run_node("a", "1", tool, body("a")); r.run_node("b", "1", tool, body("b", ["a"])); r.close()
    return {p.name: p for p in root.iterdir()}


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    from tests.test_checks import _require_installed
    _require_installed()
    return _make(tmp_path_factory.mktemp("format-03"))


def _verifier_lines(folder: Path, *flags: str) -> list[str]:
    """The installed verifier's own text output for the run, line by line."""
    proc = subprocess.run([sys.executable, "-m", "onetrace_verify.cli", *flags, "MANIFEST.json"],
                          cwd=folder, capture_output=True)
    return proc.stdout.decode("utf-8").splitlines()


def _one(lines: list[str], marker: str) -> str:
    found = [ln for ln in lines if marker in ln]
    assert len(found) == 1, (marker, found)
    return found[0]


def _model(folder: Path, envelope: dict | None = None):
    from onetrace_console.checks import check
    from onetrace_console.viewer.model import build_model
    from onetrace_console.viewer.record import read_record
    if envelope is None:
        envelope = check(folder, ran_at=RAN_AT).envelope
    return build_model(read_record(folder), envelope, GENERATED_AT, own_check=True, checker="onetrace-verify")


def _case(model) -> str:
    from onetrace_console.viewer.page import render_case
    return render_case(model)


def _quoted(page: str) -> list[str]:
    """Every quotation the page marks as the check's own words, unescaped."""
    return [unescape(re.sub(r"<[^>]+>", "", q))
            for q in re.findall(r'<q data-words="check">(.*?)</q>', page, re.S)]


def _rung(model, key: str):
    return next(r for r in model.ladder if r.key == key)


def _evidence_text(rung) -> str:
    return "".join(t.text for ln in rung.evidence for t in ln)


# ------------------------------------------------------------------ optional stages

def optional_problems(model, page: str, row: str) -> list[str]:
    """What is wrong with how a run that skipped only optional stages is shown: `row` is the
    verifier's own `run complete` line under --require-complete."""
    out = []
    rung = _rung(model, "nothing-missing")
    if rung.state != "yes":
        out.append(f"the rung reads {rung.state!r}, not the check's PASS")
    if not any(t.text == row and t.source == "check" for ln in rung.evidence for t in ln):
        out.append("the rung does not quote the check's row")
    if row not in _quoted(page):
        out.append("the page does not show the check's row as its words")
    if "Part of this run wasn't recorded" in unescape(page):
        out.append("the page says part of the run wasn't recorded")
    return out


def test_a_run_that_skipped_only_optional_stages_reads_as_the_check_reads_it(runs, examined):
    folder = runs["optional"]
    row = _one(_verifier_lines(folder, "--require-complete"), "run complete")
    assert row.startswith("[PASS") and "optional, not run: b" in row, row
    model = _model(folder)
    examined(1, "run page of a run that skipped an optional stage")
    assert optional_problems(model, _case(model), row) == []


def test_home_counts_the_optional_run_as_its_page_reads_it(runs, examined):
    """Rung 3 is kept for Home's counts from the same check the page reads."""
    from onetrace_console.checks import check, nothing_missing_state
    folder = runs["optional"]
    examined(1, "kept rung 3")
    assert nothing_missing_state(folder, check(folder, ran_at=RAN_AT).envelope) == "yes"


def test_a_required_stage_missing_beside_an_optional_one_is_still_no(runs, examined):
    folder = runs["optional-and-required"]
    row = _one(_verifier_lines(folder, "--require-complete"), "run complete")
    assert row.startswith("[FAIL"), row
    model = _model(folder)
    examined(1, "run page of a run missing a required stage")
    assert _rung(model, "nothing-missing").state == "no"


def test_only_a_0_3_run_is_checked_again_with_every_required_stage_asked_for(runs, examined):
    """An earlier format's check is the check it was: no third run of the verifier."""
    from onetrace_console.checks import check
    demo = Path(__file__).resolve().parent.parent / "examples" / "reference-demo" / "runs" / "day-1"
    examined(2, "check envelopes")
    assert "completeness_required" in check(runs["optional"], ran_at=RAN_AT).envelope
    assert "completeness_required" not in check(demo, ran_at=RAN_AT).envelope


def test_sabotage_a_check_without_the_completeness_run_is_named(runs, monkeypatch, examined):
    """Without the run with every required stage asked for, the page falls back on the receipts'
    own lists, and the test above names it."""
    from onetrace_console.checks import check
    folder = runs["optional"]
    row = _one(_verifier_lines(folder, "--require-complete"), "run complete")
    envelope = dict(check(folder, ran_at=RAN_AT).envelope)
    envelope.pop("completeness_required")
    model = _model(folder, envelope)
    examined(1, "run page, sabotaged")
    assert optional_problems(model, _case(model), row) != []


def test_sabotage_a_rung_reading_the_receipts_optional_list_is_named(runs, monkeypatch, examined):
    """A page that decided from `coverage.optional_stages` itself, and worded it, would read yes
    without the check's row: named."""
    from onetrace_console.viewer import model as vm
    folder = runs["optional"]
    row = _one(_verifier_lines(folder, "--require-complete"), "run complete")
    monkeypatch.setattr(vm, "_nothing_missing",
                        lambda record, report=None: vm._rung("nothing-missing", vm._YES, vm.line("checks.gaps_none")))
    model = _model(folder)
    examined(1, "run page, sabotaged")
    assert optional_problems(model, _case(model), row) != []



def _exit(folder: Path, *flags: str) -> int:
    return subprocess.run([sys.executable, "-m", "onetrace_verify.cli", *flags, "MANIFEST.json"],
                          cwd=folder, capture_output=True).returncode


def apart_problems(folder: Path, envelope: dict) -> list[str]:
    """The run with every required stage asked for is a second run of the check, apart from the
    first: the exit, the verdict and the check's counts are the first run's, with or without it,
    and the only words it adds to the page are its own `run complete` row, as printed."""
    from onetrace_console.checks import verdict_for
    from onetrace_console.viewer.report import parse
    out = []
    without = {k: v for k, v in envelope.items() if k != "completeness_required"}

    def shown(report):
        return (report.exit_status, verdict_for(report.exit_status, report.overall),
                report.count("pass"), report.count("fail"), report.count("not_run"))
    if shown(parse(envelope)) != shown(parse(without)):
        out.append("the check's exit, verdict or counts change with the second run")
    if parse(envelope).exit_status != str(_exit(folder)):
        out.append(f"the exit shown is {parse(envelope).exit_status!r}, the first run's is {_exit(folder)}")
    with_it, plain = _model(folder, envelope), _model(folder, without)
    for field in ("strip", "answer", "checked", "not_checked"):
        if getattr(with_it, field) != getattr(plain, field):
            out.append(f"the page's {field} changes with the second run")
    row = _one(_verifier_lines(folder, "--require-complete"), "run complete")
    added = set(_quoted(_case(with_it))) - set(_quoted(_case(plain)))
    if not added <= {row}:
        out.append(f"the second run adds words other than its row: {sorted(added - {row})}")
    return out


def test_the_second_run_never_changes_the_check_s_verdict_exit_or_counts(runs, examined):
    """Most of all where the two differ: a run missing a required stage holds under the check,
    exit 0, while the run with every required stage asked for fails it, exit 1."""
    from onetrace_console.checks import check
    assert (_exit(runs["optional-and-required"]), _exit(runs["optional-and-required"], "--require-complete")) == (0, 1)
    examined(2, "0.3 runs checked twice")
    assert {name: apart_problems(runs[name], check(runs[name], ran_at=RAN_AT).envelope)
            for name in ("optional", "optional-and-required")} == {"optional": [], "optional-and-required": []}


def test_sabotage_the_check_itself_run_with_the_requirement_is_named(runs, monkeypatch, examined):
    """A console that asked for every required stage in the check whose verdict it shows."""
    from onetrace_console.checks import check
    from onetrace_console.viewer import report
    capture, cli_run = report.capture, report._cli_run
    monkeypatch.setattr(report, "capture", lambda *a, args=(), **k: capture(
        *a, args=(*args, "--require-complete"), **k))
    monkeypatch.setattr(report, "_cli_run", lambda run_dir, module, shown_as, args, *rest: cli_run(
        run_dir, module, shown_as, args if "--require-complete" in args else (*args, "--require-complete"), *rest))
    folder = runs["optional-and-required"]
    examined(1, "check envelope, sabotaged")
    assert apart_problems(folder, check(folder, ran_at=RAN_AT).envelope) != []

# ------------------------------------------------------------------ a held step

def held_problems(page: str, row: str) -> list[str]:
    """`row` is the verifier's own `step held before running` line."""
    section = re.search(r'<div data-section="declined">(.*?)</div>', page, re.S)
    if section is None:
        return ["no banner where the run stopped"]
    return [] if row in _quoted(section.group(1)) else ["the banner does not quote the check's row"]


def test_a_held_step_s_attempted_links_are_the_check_s_row(runs, examined):
    folder = runs["held"]
    row = _one(_verifier_lines(folder), "step held before running")
    assert row.startswith("[PASS") and "attempted: a#1 -> c" in row, row
    examined(1, "run page of a run with a held step")
    assert held_problems(_case(_model(folder)), row) == []


def test_sabotage_a_banner_without_the_held_row_is_named(runs, examined):
    from dataclasses import replace
    folder = runs["held"]
    row = _one(_verifier_lines(folder), "step held before running")
    examined(1, "run page, sabotaged")
    assert held_problems(_case(replace(_model(folder), held=())), row) != []


# ------------------------------------------------------------------ outputs_kept none

def kept_none_problems(model, row: str) -> list[str]:
    """`row` is the verifier's own `run: artifacts` line."""
    from onetrace_console.viewer.sentences import template
    rung = _rung(model, "records-agree")
    out = []
    if rung.state != "not-checked":
        out.append(f"the rung reads {rung.state!r}")
    if not any(t.text == row and t.source == "check" for ln in rung.evidence for t in ln):
        out.append("the rung does not quote the check's row")
    if template("rung.records.no_artifacts") in _evidence_text(rung):
        out.append("the rung says the run was delivered without its output files")
    return out


def test_a_run_that_keeps_no_output_files_reads_as_the_check_reads_it(runs, examined):
    folder = runs["nokeep"]
    row = _one(_verifier_lines(folder), "run: artifacts")
    assert row.startswith("[NOT-RUN]") and "outputs_kept: none" in row, row
    examined(1, "run page of a run that keeps no output files")
    model = _model(folder)
    assert kept_none_problems(model, row) == []
    assert row in _quoted(_case(model))


def test_the_kept_none_run_counts_as_held_without_its_outputs(runs, examined):
    """Lists and counts read rung 1 as the page does: not checked, held without output files."""
    from onetrace_console.checks import agree_state, check
    folder = runs["nokeep"]
    examined(1, "kept rung 1")
    assert agree_state(folder, check(folder, ran_at=RAN_AT).envelope) == {"agree": "not-checked",
                                                                          "agree_why": "no-outputs"}


def test_sabotage_the_generic_sentence_for_a_kept_none_run_is_named(runs, monkeypatch, examined):
    from onetrace_console.viewer import model as vm
    folder = runs["nokeep"]
    row = _one(_verifier_lines(folder), "run: artifacts")
    monkeypatch.setattr(vm, "_kept_none_row", lambda report: None)
    examined(1, "run page, sabotaged")
    assert kept_none_problems(_model(folder), row) != []


def test_a_plain_0_3_run_is_drawn_as_before(runs, examined):
    """None of the three is said of a run that has none of them."""
    model = _model(runs["plain"])
    page = unescape(_case(model))
    examined(1, "run page of a plain 0.3 run")
    assert _rung(model, "nothing-missing").state == "yes"
    assert "optional, not run" not in page and "step held before running" not in page
    assert "outputs_kept" not in page


# ------------------------------------------------------------------ the ruled words

#: The ruled words of the three sentences the page puts before the check's own row.
RULED_WORDS = {
    "declined.held": "The check says:",
    "rung.missing.optional": "The check, asked whether every required step ran, says:",
    "rung.records.outputs_not_kept": ("The check did not look at the run's output files. This page does "
                                      "not say the records agree. The check says:"),
}


def ruled_words_problems(runs) -> list[str]:
    """Each of the three is the ruled sentence, then the check's own row, on the run's page; and
    the table holds them as ruled, none of them still provisional."""
    from onetrace_console.viewer import sentences as S
    out = []
    for key, words in RULED_WORDS.items():
        if key not in S.RULED or S.RULED[key][0] != words:
            out.append(f"{key}: not ruled as {words!r}")
        if key in S.PROVISIONAL:
            out.append(f"{key}: still provisional")
    cases = (("optional", "--require-complete", "run complete",
              lambda m: _evidence_text(_rung(m, "nothing-missing")), "rung.missing.optional"),
             ("held", None, "step held before running",
              lambda m: "".join(t.text for t in m.held[0]) if m.held else "", "declined.held"),
             ("nokeep", None, "run: artifacts",
              lambda m: _evidence_text(_rung(m, "records-agree")), "rung.records.outputs_not_kept"))
    for name, flag, marker, said, key in cases:
        row = _one(_verifier_lines(runs[name], *([flag] if flag else [])), marker)
        model = _model(runs[name])
        if said(model) != RULED_WORDS[key] + " " + row:
            out.append(f"{name}: says {said(model)!r}")
        if RULED_WORDS[key] not in unescape(re.sub(r"<[^>]+>", "", _case(model))):
            out.append(f"{name}: the page does not carry the ruled words")
    return out


def test_the_three_sentences_are_the_ruled_words(runs, examined):
    examined(len(RULED_WORDS), "ruled sentences, each on its run's page")
    assert ruled_words_problems(runs) == []


def test_sabotage_a_sentence_in_other_words_is_named(runs, monkeypatch, examined):
    from onetrace_console.viewer import sentences as S
    examined(len(RULED_WORDS), "sentences put back in other words, one at a time")
    for key in RULED_WORDS:
        with monkeypatch.context() as m:
            table = S.RULED if key in S.RULED else S.PROVISIONAL
            m.setitem(table, key, ("The check, in other words, says:", "sabotage"))
            assert any(key in p or "says" in p for p in ruled_words_problems(runs)), key


# ------------------------------------------------------------------ the store

def _tar(folder: Path, *, manifest: dict | None = None, receipt_format: str | None = None) -> bytes:
    """A delivery of a run folder as a sender makes it, with every file under it and a SHA256SUMS
    covering each. `manifest` replaces the manifest; `receipt_format` rewrites each receipt's
    `format` (the sums are made after, so the delivery is undamaged)."""
    import hashlib
    import io
    import json
    import tarfile

    from onetrace_console.ingest import SUMS_NAME
    files = {p.relative_to(folder).as_posix(): p.read_bytes()
             for p in sorted(folder.rglob("*")) if p.is_file() and p.name != ".lock"}
    if manifest is not None:
        files["MANIFEST.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if receipt_format is not None:
        for name in [n for n in files if n.startswith("receipts/")]:
            r = json.loads(files[name])
            r["format"] = receipt_format
            files[name] = json.dumps(r, sort_keys=True, separators=(",", ":")).encode("utf-8")
    files[SUMS_NAME] = "".join(f"{hashlib.sha256(b).hexdigest()}  {p}\n" for p, b in files.items()).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def stored_problems(folder: Path, store) -> list[str]:
    """What is wrong with a 0.3 run's way through the store: stored, read back, checked."""
    from onetrace_console.checks import HOLDS, run_and_record
    from onetrace_console.ingest import accept
    got = accept(_tar(folder), store)
    if getattr(got, "run", None) is None:
        return [f"refused: {getattr(got, 'body', got)!r}"[:300]]
    out = []
    if got.run.format != "stage-receipt-chain/0.3":
        out.append(f"stored as {got.run.format!r}")
    if store.get_run(got.run.key) != got.run:
        out.append("not read back as stored")
    checked = run_and_record(got.run, store, ran_at=RAN_AT)
    if checked.check_verdict != HOLDS:
        out.append(f"checked: {checked.check_verdict!r}")
    return out


def test_a_0_3_run_stores_reads_back_and_verifies(runs, store, examined):
    examined(len(runs), "0.3 runs through the store")
    assert {name: stored_problems(folder, store) for name, folder in runs.items()} == {
        name: [] for name in runs}


def test_a_stored_0_3_run_s_pages_quote_the_check(runs, store, examined):
    """The three rows, on the pages the console draws from what it stored."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.pages import CASE, render_execution
    examined(3, "stored runs' case pages")
    for name, marker, flags in (("optional", "run complete", ("--require-complete",)),
                                ("held", "step held before running", ()),
                                ("nokeep", "run: artifacts", ())):
        row = _one(_verifier_lines(runs[name], *flags), marker)
        run = run_and_record(accept(_tar(runs[name]), store).run, store, ran_at=RAN_AT)
        page = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
        assert row in _quoted(page), name
        if name == "optional":
            assert store.get_run(run.key).nothing_missing == "yes", "Home counts it as its page reads it"


def test_sabotage_a_store_without_0_3_is_named(runs, store, monkeypatch, examined):
    from onetrace_console import ingest
    monkeypatch.setattr(ingest, "MANIFEST_FORMATS", tuple(f for f in ingest.MANIFEST_FORMATS if not f.endswith("/0.3")))
    examined(1, "0.3 run, sabotaged store")
    assert stored_problems(runs["plain"], store) != []


def refused_problems(data: bytes, store, named: str) -> list[str]:
    """An unknown format is refused, 422, naming it, and nothing is stored. Where the verifier
    spoke, the body is its own words, unedited, and this store's row naming the format rides in
    `rows` (`ingest.Rejection`)."""
    from onetrace_console.ingest import Rejection, accept
    before = list(store.runs())
    got = accept(data, store)
    out = []
    if not isinstance(got, Rejection) or got.status != 422:
        out.append(f"not refused: {got!r}"[:200])
    elif named not in got.body and not any(named in r for r in got.rows):
        out.append("the refusal does not name the format")
    if list(store.runs()) != before:
        out.append("something was stored")
    return out


UNKNOWN = (("chain", "stage-receipt-chain/0.4"), ("chain", "stage-receipt-chain/1.0"),
           ("receipt", "stage-receipt/0.4"), ("receipt", "stage-receipt/1.0"))


def _unknown(folder: Path, part: str, fmt: str) -> bytes:
    import json
    if part == "chain":
        manifest = json.loads((folder / "MANIFEST.json").read_bytes())
        return _tar(folder, manifest=dict(manifest, format=fmt))
    return _tar(folder, receipt_format=fmt)


def test_a_format_the_console_does_not_know_is_still_refused(runs, store, examined):
    examined(len(UNKNOWN), "deliveries in an unknown format")
    assert {fmt: refused_problems(_unknown(runs["plain"], part, fmt), store, fmt) for part, fmt in UNKNOWN} == {
        fmt: [] for _, fmt in UNKNOWN}


def test_sabotage_a_store_that_takes_any_format_is_named(runs, store, monkeypatch, examined):
    from onetrace_console import ingest

    class Any(tuple):
        def __contains__(self, item):
            return True
    monkeypatch.setattr(ingest, "MANIFEST_FORMATS", Any(ingest.MANIFEST_FORMATS))
    monkeypatch.setattr(ingest, "RECEIPT_FORMATS", Any(ingest.RECEIPT_FORMATS))
    examined(len(UNKNOWN), "deliveries in an unknown format, sabotaged store")
    #: A minor the verifier reads (0.4) is held off by this store's lists alone: named.
    for part, fmt in UNKNOWN:
        if fmt.endswith("/0.4"):
            assert refused_problems(_unknown(runs["plain"], part, fmt), store, fmt) != [], fmt
    #: A new major is refused by the verifier's own veto even then (`ingest`: "the verifier vetoes
    #: a format, whatever this store's list says").
    assert refused_problems(_unknown(runs["plain"], "chain", "stage-receipt-chain/1.0"), store,
                            "stage-receipt-chain/1.0") == []


# ------------------------------------------------------------------ earlier formats

EARLIER = Path(__file__).resolve().parent / "fixtures" / "earlier-formats-read.json"


def earlier_reading(root: Path, store) -> dict:
    """Each committed earlier-format run (the reference demo, the test fixtures, the SDK's exam),
    stored and checked as the console does, and what it keeps about it: the table
    `earlier-formats-read.json` holds, made by this function under the pinned 0.3.0 SDK before
    the store took format 0.3."""
    import json
    from onetrace_console.checks import run_and_record
    from tests.test_compare import _deliver
    folders = sorted({p.parent for g in ("examples/**/MANIFEST.json", "tests/fixtures/**/MANIFEST.json",
                                         ".sdk-fixtures/**/MANIFEST.json") for p in root.glob(g)})
    out = {}
    for f in folders:
        run = run_and_record(_deliver(f, store, outputs=(f / "artifacts").is_dir()), store, ran_at=RAN_AT)
        report = json.loads(store.get(run.check_report)) if run.check_report else {}
        lines = [ln for ln in (report.get("stdout") or "").splitlines() if ln.strip()]
        out[f.relative_to(root).as_posix()] = {
            "format": run.format, "check_verdict": run.check_verdict, "check_exit": run.check_exit,
            "summary": lines[-1] if lines else "", "nothing_missing": run.nothing_missing,
            "agree": run.agree, "agree_why": run.agree_why, "approved": run.approved,
            "signed": run.signed, "anchored": run.anchored, "declined": run.declined,
            "recorded_count": run.recorded_count, "completeness_run": "completeness_required" in report}
    return out


def test_earlier_formats_read_as_before(store, examined):
    """0.2, 0.1 and the preview read as they did before format 0.3 was taken: the same verdict,
    the same summary from the check, the same rungs kept, and no run with every required stage
    asked for."""
    import json
    from tests.test_checks import _require_installed
    _require_installed()
    before = json.loads(EARLIER.read_text(encoding="utf-8"))
    now = earlier_reading(Path(__file__).resolve().parent.parent, store)
    examined(len(now), "earlier-format runs read again")
    assert {r["format"] for r in now.values()} == {"stage-receipt-chain/0.2", "stage-receipt-chain/0.1",
                                                  "stage-receipt-chain/0.0-preview"}
    assert now == before


def test_sabotage_an_earlier_format_dropped_is_named(store, monkeypatch, examined):
    from onetrace_console import ingest
    monkeypatch.setattr(ingest, "MANIFEST_FORMATS", tuple(f for f in ingest.MANIFEST_FORMATS if not f.endswith("/0.2")))
    examined(1, "earlier-format runs, sabotaged store")
    with pytest.raises((AssertionError, AttributeError)):   # `_deliver`'s refusal, either way
        earlier_reading(Path(__file__).resolve().parent.parent, store)
