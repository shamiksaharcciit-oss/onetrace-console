"""In the console, the check is the installed CLI, three ways.

1. `onetrace-verify MANIFEST.json`: the verdict and the check's own words, stored as text;
2. `onetrace-verify --json MANIFEST.json`: its rows, stored too; the two summaries must agree;
3. only where the stored run holds `artifacts/`: `--json --require-artifacts`, the evidence for
   "Records agree". A run without `artifacts/` is never checked with the
   flag, which would FAIL it for files it was never sent with.
"""
from __future__ import annotations

import hashlib
import json

from onetrace_console.checks import COULD_NOT_CHECK, HOLDS, run_and_record
from onetrace_console.ingest import accept
from onetrace_console.receipt_page import _agree
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, _deliver, _require_exam

EDGES_ROWS = ("[PASS   ] edges conform to declared_edges",
              "[PASS   ] edges equal the edges derived from the receipts")


def _envelope(run, store) -> dict:
    return json.loads(store.get(run.check_report).decode("utf-8"))


def _emitted(tmp_path, *, change_an_output: bool = False) -> dict[str, bytes]:
    """A real 0.2 run, recorded here by the pinned SDK, with its `artifacts/` (its output files)."""
    from tests.test_last_attempt_failed import _emit
    out = tmp_path / "run"
    _emit(out, "with-outputs", [("a", "1", "ok"), ("b", "1", "ok")])
    files = {p.relative_to(out).as_posix(): p.read_bytes() for p in sorted(out.rglob("*"))
             if p.is_file() and p.name != ".lock"}
    assert any(n.startswith("artifacts/") for n in files), "the SDK wrote no artifacts/"
    if change_an_output:
        name = next(n for n in files if n.startswith("artifacts/"))
        files[name] = files[name] + b" "
    files["SHA256SUMS"] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {n}"
                                     for n, b in files.items()) + "\n").encode()
    return files


def test_a_run_without_artifacts_holds_and_its_rung_says_so_as_ruled(store, examined):
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    env = _envelope(run, store)
    examined(1, "artifact-less run checked")
    assert run.check_verdict == HOLDS, (run.check_verdict, run.check_note)
    assert env["command"] == ["onetrace-verify", "MANIFEST.json"]
    assert env["rows_json"]["command"] == ["onetrace-verify", "--json", "MANIFEST.json"]
    assert "outputs_required" not in env, "the flag is never run on a run without artifacts/"
    assert _agree(run, store) == "Records agree: not checked (held without its output files required)"


def test_the_graph_edge_rows_are_in_the_stored_words(store, examined):
    """The bench verify.py has neither row; the CLI has both (group A)."""
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    examined(2, "graph rows looked for")
    for row in EDGES_ROWS:
        assert row in _envelope(run, store)["stdout"], row


def test_a_run_with_artifacts_gets_the_third_check_and_the_rung_reads_from_it(store, tmp_path,
                                                                            examined):
    _require_installed()
    run = run_and_record(accept(make_tar(_emitted(tmp_path)), store).run, store,
                         ran_at=FIXED_RAN_AT)
    env = _envelope(run, store)
    examined(1, "run with outputs checked")
    assert run.check_verdict == HOLDS, (run.check_verdict, run.check_note)
    assert env["outputs_required"]["command"] == [
        "onetrace-verify", "--json", "--require-artifacts", "MANIFEST.json"]
    assert env["outputs_required"]["exit_status"] == "0"
    assert _agree(run, store) == "Records agree: yes"


def test_an_output_that_no_longer_matches_is_a_no(store, tmp_path, examined):
    _require_installed()
    got = accept(make_tar(_emitted(tmp_path, change_an_output=True)), store)
    examined(1, "run with a changed output checked")
    run = run_and_record(got.run, store, ran_at=FIXED_RAN_AT)
    env = _envelope(run, store)
    assert env["outputs_required"]["exit_status"] == "1", env["outputs_required"]
    assert _agree(run, store) == "Records agree: no"


def test_a_run_carrying_anchors_gets_its_anchor_rows(store, tmp_path, examined):
    """The anchor rows (`records beside the chain`) come from the CLI, never the bench. Reading
    them into the "Committed by time" row is step 3; here: they are in the check's words."""
    _require_installed()
    files = _emitted(tmp_path)
    files["anchors/1.json"] = b'{"not": "an anchor record"}'
    files["SHA256SUMS"] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {n}"
                                     for n, b in files.items() if n != "SHA256SUMS") + "\n").encode()
    got = accept(make_tar(files), store)
    examined(1, "run with anchors/ checked")
    if got.run is None:
        #: Not stored: then the anchors/ folder does not reach the check, and this proves nothing.
        raise AssertionError(f"the delivery with anchors/ was refused: {getattr(got, 'body', got)}")
    run = run_and_record(got.run, store, ran_at=FIXED_RAN_AT)
    assert "anchors/1.json" in _envelope(run, store)["stdout"], _envelope(run, store)["stdout"][-600:]


def test_a_text_and_json_run_that_disagree_is_a_could_not_check(store, monkeypatch, examined):
    """The summaries must agree; if they don't, could not check, with that reason."""
    import onetrace_console.viewer.report as vr
    _require_installed()
    _require_exam()
    real = vr.capture_cli

    def disagreeing(run_dir, **kw):
        env = real(run_dir, **kw)
        doc = json.loads(env["rows_json"]["stdout"])
        doc["rows"] = doc["rows"][:-1]
        doc["summary"]["pass"] -= 1
        env["rows_json"]["stdout"] = json.dumps(doc)
        return env

    monkeypatch.setattr(vr, "capture_cli", disagreeing)
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store, ran_at=FIXED_RAN_AT)
    examined(1, "disagreeing check recorded")
    assert run.check_verdict == COULD_NOT_CHECK
    assert "the check's text and its --json disagree" in run.check_note, run.check_note
