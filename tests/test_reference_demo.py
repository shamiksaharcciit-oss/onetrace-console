"""The reference demo pipeline (examples/reference-demo): release 1's screenshots come from it.

    The reference demo pipeline. A small sample agent run built with onetrace, with
    no onedoor in it. It has two runs, a day apart, where the model stage writes a different
    value from the same inputs.

Checked here: the committed runs are exactly what the script produces; both verify; the model
stage reads the same inputs in both and writes a different value, and that is where the two
first differ; they are a day apart and say in the record that the demo set their clock; and
no authorization records are anywhere in them.

Verified and compared with onetrace's own commands -- the same ones this console runs (see
`checks.py` and `compare.py`) -- and, now that format 0.2 is accepted, loaded
through the console's own path: ingest, check, compare, the run pages, the Overview and the
Diff page.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest
from tests.conftest import whole_folds

REPO = Path(__file__).resolve().parent.parent
DEMO = REPO / "examples" / "reference-demo"
RUNS = DEMO / "runs"
DAYS = {1: "2026-09-28T10:00:00Z", 2: "2026-09-29T10:00:00Z"}


def _files(run: Path) -> list[str]:
    """Every file of a run, less the recorder's own lock file, which is not part of it."""
    return sorted(p.relative_to(run).as_posix() for p in run.rglob("*")
                  if p.is_file() and p.name != ".lock")


def _receipts(run: Path) -> list[dict]:
    manifest = json.loads((run / "MANIFEST.json").read_bytes().decode("utf-8"))
    return [json.loads((run / e["file"]).read_bytes().decode("utf-8")) for e in manifest["chain"]]


def _stage(run: Path, name: str) -> dict:
    return next(r for r in _receipts(run) if r["stage"]["name"] == name)


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("demo")
    for day, at in DAYS.items():
        subprocess.run([sys.executable, "-B", str(DEMO / "demo.py"), str(out / f"day-{day}"),
                        f"demo-run-{day}", str(day), "--at", at], check=True,
                       capture_output=True)
    return out


def test_the_committed_runs_are_exactly_what_the_script_produces(regenerated, examined):
    """Every file the script writes, byte for byte. The signatures beside the chain are not the
    script's: they were added after, with a demo key that no longer exists (the README says so), so
    they are held by the signing tests below, and are the only files the script does not make."""
    checked = 0
    for day in DAYS:
        committed, made = _files(RUNS / f"day-{day}"), _files(regenerated / f"day-{day}")
        signed = {rel for rel in committed if str(rel).replace("\\", "/").startswith("signatures/")}
        assert [str(rel).replace("\\", "/") for rel in sorted(signed)] == ["signatures/1.json"], day
        committed = [rel for rel in committed if rel not in signed]
        assert committed == made, day
        for rel in committed:
            assert (RUNS / f"day-{day}" / rel).read_bytes() == \
                (regenerated / f"day-{day}" / rel).read_bytes(), rel
            checked += 1
    examined(checked, "files of the two committed runs compared with a fresh generation")


def _data(receipt: dict) -> list[str]:
    """The digests of what a stage read, less the upstream receipts it read (each of which records
    its own times, so differs from day to day without the data differing)."""
    return [i["digest"] for i in receipt["inputs"] if not i["name"].startswith("receipt:")]


def test_the_model_reads_the_same_inputs_and_writes_a_different_value():
    one, two = (_stage(RUNS / f"day-{d}", "model") for d in DAYS)
    assert _data(one) == _data(two) and len(_data(one)) == 3
    assert [i["name"] for i in one["inputs"]] == [i["name"] for i in two["inputs"]]
    assert [o["digest"] for o in one["outputs"]] != [o["digest"] for o in two["outputs"]]
    values = [json.loads((RUNS / f"day-{d}" / "artifacts" / "05-model" / "model-output.json")
                         .read_bytes())["action"]["changes"]["auth_env"] for d in DAYS]
    assert values == ["production", "staging"]
    assert one["instrument"]["rederivable"] == "false", "declared not re-runnable"


def test_the_runs_are_a_day_apart_and_the_record_says_the_demo_set_the_clock():
    firsts = [_stage(RUNS / f"day-{d}", "request") for d in DAYS]
    assert [r["time"]["started"][:10] for r in firsts] == ["2026-09-28", "2026-09-29"]
    for r in firsts:
        assert r["assertions"]["constants"]["clock"] == (
            "set by the demo; the times in this record were not read from a clock")


def test_there_are_no_authorization_records_anywhere_in_the_demo():
    """No policy engine is in it, so nothing in it could carry one."""
    for path in DEMO.rglob("*"):
        if path.is_file():
            text = path.read_bytes().decode("utf-8", errors="replace").lower()
            assert "onedoor" not in text and "decision_ref" not in text, path


def _verifier() -> str:
    """The pinned `onetrace-verify` beside this interpreter, as `checks.REPEAT_COMMAND` names it."""
    import shutil
    here = Path(sys.executable).parent
    found = shutil.which("onetrace-verify", path=str(here)) or shutil.which("onetrace-verify")
    if not found:
        pytest.fail("onetrace-verify is not installed; see PINS.md")
    return found


def test_both_runs_verify(examined):
    for day in DAYS:
        run = RUNS / f"day-{day}"
        done = subprocess.run([_verifier(), "."], cwd=run, capture_output=True, text=True)
        examined(1, f"day {day}'s run, by the pinned verifier")
        assert done.returncode == 0, done.stdout[-600:]
        assert re.search(r"\d+ pass, 0 fail, \d+ not-run\s+->\s+PASS", done.stdout), done.stdout[-300:]


def test_the_first_difference_is_the_model_stage_and_only_its_seed_differs(tmp_path):
    """`python -m onetrace diff`, as `compare.py` runs it."""
    done = subprocess.run([sys.executable, "-m", "onetrace", "diff", str(RUNS / "day-1"),
                           str(RUNS / "day-2"), "--out", str(tmp_path)], capture_output=True)
    report = json.loads((tmp_path / "diff.json").read_bytes().decode("utf-8"))
    assert report["envelope"] == "diverged", done.stdout[-400:]
    #: A graph comparison: the SDK names a frontier, every node where the runs first differ.
    assert (report["shape"], report["mode"]) == ("dag", "two-run")
    assert report["first_difference_frontier"] == ["model"]
    assert [(r["node"], r["verdict"]) for r in report["ladder"]] == [
        ("request", "same"), ("context", "same"), ("tests#1", "same"), ("tests#2", "same"),
        ("model", "FIRST DIFFERENCE"), ("proposal", "downstream"),
        ("config applied", "downstream")]
    model = next(r for r in report["ladder"] if r["node"] == "model")
    #: Of the model's recorded settings, only the seed differs (and so the digest over them).
    settings = [a for a in model["annotations"] if not a.startswith("output ")]
    assert len(settings) == 2 and "constant seed differs" in settings
    assert settings[0].startswith("instrument config_digest differs")


def test_the_store_takes_exactly_the_listed_formats():
    """Format 0.2 added, and the store's lists are exactly these -- a format
    joins or leaves them only by changing this test."""
    from onetrace_console.ingest import MANIFEST_FORMATS, RECEIPT_FORMATS
    assert MANIFEST_FORMATS == ("stage-receipt-chain/0.2", "stage-receipt-chain/0.1",
                                "stage-receipt-chain/0.0-preview")
    assert RECEIPT_FORMATS == ("stage-receipt/0.2", "stage-receipt/0.1",
                               "stage-receipt/0.0-preview")
    fmt = json.loads((RUNS / "day-1" / "MANIFEST.json").read_bytes())["format"]
    assert fmt in MANIFEST_FORMATS, "the demo's own format is one the store implements"


# ------------------------------------------------ through the console's own path

def _delivery(folder: Path, extra: dict[str, bytes] | None = None) -> bytes:
    """A delivery as a sender makes it: the manifest, its chain, any files beside the chain,
    and a SHA256SUMS covering every one of them."""
    import hashlib
    import io
    import tarfile

    from onetrace_console.ingest import SUMS_NAME
    manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    files = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        files[entry["file"]] = (folder / entry["file"]).read_bytes()
    files.update(extra or {})
    files[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                   for p, b in files.items()) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    """Both runs delivered to a store, checked and compared, as the console does it."""
    from dataclasses import replace

    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    _require_installed()
    store = Store(tmp_path_factory.mktemp("demo-store") / "store")
    runs = []
    for day, at in DAYS.items():
        accepted = accept(_delivery(RUNS / f"day-{day}"), store,
                          received_at=at.replace("Z", "+00:00"))
        assert getattr(accepted, "run", None) is not None, getattr(accepted, "rows", accepted)
        runs.append(run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT))
    comparison = compare(runs[0], runs[1], store, ran_at=FIXED_RAN_AT)
    return store, runs, comparison


def test_the_console_ingests_and_checks_both_runs(loaded):
    _, runs, _ = loaded
    assert [r.check_verdict for r in runs] == ["holds", "holds"]
    #: Six declared stages, seven receipts: the tests stage's failed attempt is one of them.
    assert [r.stage_count for r in runs] == [6, 6]
    assert [r.recorded_count for r in runs] == [7, 7]


def test_the_console_compares_them_to_the_model_stage(loaded):
    from onetrace_console.compare import DIFF
    store, _, comparison = loaded
    report = json.loads(store.get(dict(comparison.verb(DIFF).reports)["diff.json"]))
    assert report["first_difference_frontier"] == ["model"]


def test_each_run_page_renders_with_its_ladder_and_no_records(loaded):
    from onetrace_console.pages import AUTHORIZATION, CASE, render_execution
    store, runs, _ = loaded
    for run in runs:
        pages = render_execution(run, store, generated_at="2026-09-29T12:00:00+00:00").pages
        case = unescape(re.sub(r"<[^>]+>", " ", whole_folds(pages[CASE])))
        assert "No records · This console does not record authorization." in re.sub(r"\s+", " ", case)
        #: The check holds, and was run without `--require-artifacts` (the pinned verifier
        #: has no such flag), so rung 1 is "not checked", never yes, as the confirmation review
        #: held it.
        assert 'data-rung="records-agree" data-state="not-checked"' in pages[CASE]
        assert "did not require the run's output files" in case
        assert "No authorization records for this run" in pages[AUTHORIZATION]


def test_the_overview_and_the_diff_page_show_it(loaded):
    from onetrace_console.render import HOME, render_all, render_diff
    store, _, comparison = loaded
    home = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(render_all(store, generated_at="x")[HOME]))))
    assert "1 of 2 runs changed vs baseline" in home
    assert "P1 · stage model · settings changed" in home
    assert "First difference · model" in home, "the recent runs name the frontier"
    diff = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(render_diff(comparison, store, generated_at="x")))))
    assert "Why model's output differs is not established by this evidence." in diff


def test_files_beside_the_chain_are_accepted_kept_and_not_the_chain(tmp_path):
    """0.2.0 adds anchors/<n>.json and signatures/<n>.json outside the chain. The store
    must not refuse a run for having them, must keep them, and must not treat them as part of
    the chain. Placeholders here -- and since 0.2.0 checks anchors/, a placeholder anchor FAILs
    (the test is written to the 0.2.0 verdict)."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept, bundle
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    _require_installed()
    beside = {"anchors/1.json": b'{"placeholder":"anchor"}',
              "signatures/1.json": b'{"placeholder":"signature"}'}
    store = Store(tmp_path / "store")
    accepted = accept(_delivery(RUNS / "day-1", beside), store)
    assert getattr(accepted, "run", None) is not None, getattr(accepted, "rows", accepted)
    run = accepted.run
    listed = dict(run.listing)
    for path, data in beside.items():
        assert path in listed and store.get(listed[path]) == data, f"{path} is kept, byte for byte"
    manifest = json.loads(store.get(listed["MANIFEST.json"]))
    chain = [e["file"] for e in manifest["chain"]]
    assert not set(beside) & set(chain), "they are not in the chain"
    #: Six declared stages, seven receipts: one is the tests stage's failed attempt.
    assert (run.stage_count, run.recorded_count) == (6, 7)
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(bundle(run, store))) as tar:
        names = tar.getnames()
    assert all(p in names for p in beside), "the bundle hands them back"
    #: The 0.2.0 verdict: the 0.2.0 verifier checks anchors/, and a placeholder
    #: is not an anchor record, so its row FAILs and the run contradicts. The row is read as a
    #: record beside the chain, and the anchors' caveat after the summary as the
    #: verifier's own line. Since the third development build (246ca51) signatures/ has rows
    #: too: the placeholder signature is not a signature record, so it FAILs as well, and what a
    #: signature does not show is the last line.
    checked = run_and_record(run, store, ran_at=FIXED_RAN_AT)
    assert checked.check_verdict == "contradicts", (checked.check_verdict, checked.check_note)
    stored = json.loads(store.get(checked.check_report).decode("utf-8"))["stdout"]
    assert "[FAIL   ] anchors/1.json: originality -- malformed anchor record" in stored
    assert "[FAIL   ] signatures/1.json: signature -- malformed signature record" in stored
    tail = stored.rstrip("\n").split("\n")[-2:]
    assert tail[0].startswith("anchors show this record existed"), tail
    assert tail[1].startswith("a signature does not show: "), tail
    from onetrace_console.pages import CASE, render_execution
    case = render_execution(checked, store, generated_at="2026-10-06T12:00:00+00:00").pages[CASE]
    assert 'data-state="contradicts"' in case, "the page reads the anchor row and contradicts"


# ------------------------------------------------------- item 5: the demo as a graph (board 2)

#: Board 2's approved graph, over stage names.
APPROVED = {("request", "context"), ("request", "tests"), ("request", "model"),
            ("context", "model"), ("tests", "model"), ("model", "proposal"),
            ("proposal", "config applied")}


def _manifest(run: Path) -> dict:
    return json.loads((run / "MANIFEST.json").read_bytes().decode("utf-8"))


def _both(regenerated) -> list[Path]:
    """The committed runs and the script's own fresh output: the shape is the script's, not only
    the committed files'."""
    return [base / f"day-{day}" for base in (RUNS, regenerated) for day in DAYS]


def test_each_run_records_board_2_s_graph_and_its_approved_plan(regenerated, examined):
    for run in _both(regenerated):
        day = run.name
        m = _manifest(run)
        assert {(e["from"], e["to"]) for e in m["declared_edges"]} == APPROVED
        assert len(m["declared_edges"]) == len(APPROVED)
        observed = [(e["from"], e["to"]) for e in m["edges"]]
        #: The request feeds both attempts of the tests stage; the model reads the one that ran.
        assert observed == [("request", "context"), ("request", "tests#1"), ("request", "tests#2"),
                            ("request", "model"), ("context", "model"), ("tests#2", "model"),
                            ("model", "proposal"), ("proposal", "config applied")], day
        assert {(a.split("#")[0], b.split("#")[0]) for a, b in observed} == APPROVED, (
            "every link is in the approved graph, and every approved link was used")
        examined(len(observed), f"{run.parent.name}/{day}'s recorded links")


def test_the_tests_stage_s_failed_attempt_is_kept_and_says_the_demo_set_it(regenerated):
    for run in _both(regenerated):
        receipts = {(r["stage"]["name"], r["stage"].get("instance")): r
                    for r in _receipts(run)}
        first, second = receipts[("tests", "1")], receipts[("tests", "2")]
        assert first["outcome"]["class"] == "error" and first["outcome"]["status"] == "TimeoutError"
        assert first["outcome"]["body"] == ("set by the demo to show a retry: the first attempt "
                                            "raises this instead of running; nothing timed out")
        assert not first["outputs"], "the failed attempt wrote nothing"
        assert second["outcome"] == {"class": "ok"} and second["outputs"]
        model_reads = [i["name"] for i in receipts[("model", None)]["inputs"]]
        assert "receipt:tests#2" in model_reads and "receipt:tests#1" not in model_reads


def test_the_run_page_draws_the_graph_with_the_retry_folded_and_its_failure_shown(loaded):
    from onetrace_console.pages import CASE, render_execution
    store, runs, _ = loaded
    case = render_execution(runs[1], store, generated_at="2026-09-29T12:00:00+00:00").pages[CASE]
    graph = re.search(r'<section data-section="graph">.*?</section>', case, re.S).group(0)
    labels = re.findall(r"<text[^>]*>([^<]*)</text>", graph)
    assert "tests ×2" in labels, labels
    for name in ("request", "context", "model", "proposal", "config applied"):
        assert name in labels, (name, labels)
    assert 'data-failed="yes"' in graph, "the failed attempt stays visible"
    assert "recorded as a straight line" not in graph


# ------------------------------------------- item 5's signing: a demo key, "test key (demo)"

def test_both_runs_are_signed_by_the_demo_key_the_trust_file_names():
    """Each run's signature covers its own chain head, beside the chain,
    by the one key the demo's trust file names, labelled "test key (demo)"."""
    trust = json.loads((DEMO / "trust.json").read_text(encoding="utf-8"))
    assert trust["format"] == "onetrace-trust/0.1"
    ((entry),) = trust["keys"]
    assert entry["label"] == "test key (demo)"
    for day in ("day-1", "day-2"):
        manifest = json.loads((RUNS / day / "MANIFEST.json").read_text(encoding="utf-8"))
        record = json.loads((RUNS / day / "signatures" / "1.json").read_text(encoding="utf-8"))
        assert record["chain_head"] == manifest["chain_head"], day
        assert record["key_id"] == entry["key_id"], day
        assert "signatures/1.json" not in [e["file"] for e in manifest["chain"]], "beside the chain"


def test_the_demo_trust_file_is_the_demos_only():
    """Two trust files, each a demo's own, and nowhere else: the console's own default names none.
    This example's names its deleted test key. The package's is the demo store's (0.1.1,
    the trust question): its builder's, byte for byte, naming the public-seed key with a label that
    says what such a key proves."""
    import subprocess
    from onetrace_console.demo_store import keys
    tracked = subprocess.run(["git", "ls-files"], cwd=DEMO.parent.parent, capture_output=True,
                             text=True, check=True).stdout.split()
    shipped = "src/onetrace_console/demo_store/trust.json"
    assert [p for p in tracked if p.endswith("trust.json")] == ["examples/reference-demo/trust.json",
                                                                shipped]
    assert (REPO / shipped).read_bytes() == keys.trust_file_bytes()
    ((entry),) = json.loads((REPO / shipped).read_text(encoding="utf-8"))["keys"]
    assert entry["label"] == keys.TRUSTED_LABEL and "not who signed it" in entry["label"]
    default = json.loads((DEMO.parent.parent / "config" / "default.json").read_text(encoding="utf-8"))
    assert default["trust_file"] is None


@pytest.mark.parametrize("with_trust", [True, False], ids=["demo-trust-file", "no-trust-file"])
def test_the_console_reads_the_demo_signature_as_its_trust_file_says(tmp_path, with_trust):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_signed_run import _signed_rung
    _require_installed()
    store = Store(tmp_path / "store")
    sig = (RUNS / "day-1" / "signatures" / "1.json").read_bytes()
    run = accept(_delivery(RUNS / "day-1", {"signatures/1.json": sig}), store).run
    run = run_and_record(run, store, ran_at=FIXED_RAN_AT,
                         trust_file=str(DEMO / "trust.json") if with_trust else None)
    key_id = json.loads(sig)["key_id"]
    expected = (("yes", f"Yes · test key (demo) · {key_id}") if with_trust
                else ("signed-untrusted", f"Signed, key not trusted · {key_id}"))
    assert _signed_rung(run, store) == expected
