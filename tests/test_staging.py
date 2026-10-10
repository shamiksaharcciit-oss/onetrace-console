"""The pre-store checks run in a scratch staging area, and a 422 carries the
verifier's own message word for word.

    Run the three pre-store checks (sums, chain_head, format) in a scratch staging area.
    The staging area is outside the store and never reachable by any GET. Delete it after
    every upload, whether accepted or rejected. Return the verifier's own message word for
    word in the 422.

    Check that a rejected upload leaves the store byte-identical and staging empty, and
    that the 422 body equals the verifier's message when run by hand.

    A run whose checks contradict is still stored and recorded as contradicting. A 422 is
    for damaged uploads only, never for a verdict.

Each of those is a test below, named after it. The word-for-word check is made by a
separate process running the verifier by hand, because a body-equals-message claim made by
the code that produced the body is not a check.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from onetrace_console import staging as staging_mod
from onetrace_console.checks import run_and_record, shipped_verifier
from onetrace_console.ingest import (CHAIN_HEAD_ROW, MANIFEST_NAME, SUMS_NAME,
                                     Accepted, Rejection, accept)
from onetrace_console.staging import ask_the_verifier, staging, write_delivery
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed


def _resum(files: dict[str, bytes]) -> None:
    lines = [f"{hashlib.sha256(b).hexdigest()}  {p}"
             for p, b in files.items() if p != SUMS_NAME]
    files[SUMS_NAME] = ("\n".join(lines) + "\n").encode("utf-8")


def _snapshot(store) -> dict[str, str]:
    """Every file under the store root, by path, with its digest. The store's exact state."""
    out = {}
    for path in sorted(store.root.rglob("*")):
        if path.is_file():
            out[path.relative_to(store.root).as_posix()] = \
                hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _staging_dirs() -> list[Path]:
    """Every staging directory anywhere the module would put one."""
    import tempfile
    roots = [Path(tempfile.gettempdir())]
    if staging_mod.DEFAULT_STAGING_ROOT:
        roots.append(Path(staging_mod.DEFAULT_STAGING_ROOT))
    found = []
    for root in roots:
        if root.is_dir():
            found += [p for p in root.glob(staging_mod.PREFIX + "*") if p.is_dir()]
    return found


@pytest.fixture(autouse=True)
def _own_temp_root(tmp_path, monkeypatch):
    """Each test here gets an OS temp root of its own, so `_staging_dirs` sees only its uploads.

    The module stages under `tempfile.gettempdir()`, and these tests look for leftovers there.
    A temp root shared with other processes made "left behind" mean "someone else's upload in
    flight": under `-n 16` another worker's staging directory was counted, and two tests failed
    only in parallel. The module still stages where the OS temp root is,
    and the test still looks exactly there; it is only no longer shared.
    """
    import tempfile
    root = tmp_path / "os-temp"
    root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(root))
    assert Path(tempfile.gettempdir()) == root


# ------------------------------------------------- staging is outside the store, and gone

def test_the_staging_area_is_outside_the_store(store, files):
    _require_installed()
    before = _snapshot(store)
    with staging() as scratch:
        write_delivery(files, scratch / "run")
        assert scratch.is_dir()
        # Not under the store root, by resolved path, not by how it is spelled.
        assert store.root.resolve() not in scratch.resolve().parents
        assert scratch.resolve() != store.root.resolve()
        # And the store did not change while a delivery sat in staging.
        assert _snapshot(store) == before
    assert not scratch.exists(), "the staging area outlived the upload"


def test_nothing_staged_is_reachable_through_the_stores_api(store, files):
    """"never reachable by any GET". Asserted against the store's own read path.

    A staged file's digest is a perfectly good-looking object key. The point is that it was
    never `put`, so the store does not have it -- and `get` says so rather than reading from
    wherever the bytes happen to be.
    """
    _require_installed()
    from onetrace_console.store import StoreError
    with staging() as scratch:
        write_delivery(files, scratch / "run")
        for path, blob in files.items():
            key = hashlib.sha256(blob).hexdigest()
            assert not store.has(key), f"{path} is reachable as object {key}"
            with pytest.raises(StoreError, match="no object"):
                store.get(key)


def test_staging_is_deleted_even_when_the_body_raises():
    """"Delete it after every upload" means every exit, including the unplanned one."""
    class Boom(RuntimeError):
        pass

    captured = {}
    with pytest.raises(Boom):
        with staging() as scratch:
            captured["path"] = scratch
            (scratch / "half-written.json").write_bytes(b"{}")
            raise Boom("something nobody predicted")
    assert not captured["path"].exists(), "staging survived an exception"


@pytest.mark.parametrize("outcome", ["accepted", "rejected"])
def test_no_staging_directory_survives_an_upload(files, store, outcome):
    """Both halves of "whether accepted or rejected", measured by looking for leftovers."""
    _require_installed()
    if outcome == "rejected":
        raw = bytearray(files["receipts/01-zeta.json"])
        raw[30] = (raw[30] + 1) % 256
        files["receipts/01-zeta.json"] = bytes(raw)          # sums NOT recomputed: damaged

    before = set(_staging_dirs())
    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted if outcome == "accepted" else Rejection), result
    assert set(_staging_dirs()) - before == set(), "an upload left a staging directory behind"


# ----------------------------------- a rejected upload leaves the store byte-identical

def test_a_rejected_upload_leaves_the_store_byte_identical_and_staging_empty(files, store):
    """The rule's first check, both clauses, on a store that already holds a run.

    Starting from an EMPTY store would pass for an implementation that wrote the rejected
    delivery and then deleted the whole store. So a good run is stored first, and the
    store's exact state -- every path, every digest -- must be unchanged afterwards.
    """
    _require_installed()
    good = accept(make_tar(dict(files)), store)
    assert isinstance(good, Accepted), getattr(good, "rows", good)
    before = _snapshot(store)
    assert before, "the store is empty, so this test would prove nothing"

    damaged = dict(files)
    raw = bytearray(damaged["receipts/02-alpha.json"])
    raw[25] = (raw[25] + 1) % 256
    damaged["receipts/02-alpha.json"] = bytes(raw)            # sums NOT recomputed

    staging_before = set(_staging_dirs())
    result = accept(make_tar(damaged), store)
    assert isinstance(result, Rejection), f"a damaged upload was accepted: {result}"
    assert result.status == 422

    assert _snapshot(store) == before, "a rejected upload changed the store"
    assert set(_staging_dirs()) - staging_before == set(), "staging is not empty"


# ------------------------------ the 422 body IS the verifier's message, word for word

def _verifier_by_hand(files: dict[str, bytes], tmp_path: Path) -> tuple[str, str]:
    """Run the verifier by hand over the same files. Returns (stdout, exit status)."""
    folder = tmp_path / "byhand"
    for path, blob in files.items():
        (folder / path).parent.mkdir(parents=True, exist_ok=True)
        (folder / path).write_bytes(blob)
    proc = subprocess.run([sys.executable, str(shipped_verifier()), "MANIFEST.json"],
                          cwd=str(folder), capture_output=True)
    return proc.stdout.decode("utf-8"), str(proc.returncode)


def test_the_422_body_equals_the_verifiers_message_when_run_by_hand(files, store, tmp_path):
    """The rule's second check. Compared against a separate process, not against itself.

    The damage is one byte of a receipt, which the verifier reports in its own words --
    `digest matches the manifest` and `chain link -- expected … found …`. The body returned
    to the client must be that output, unedited.
    """
    _require_installed()
    raw = bytearray(files["receipts/01-zeta.json"])
    raw[40] = (raw[40] + 1) % 256
    files["receipts/01-zeta.json"] = bytes(raw)               # sums NOT recomputed

    result = accept(make_tar(files), store)
    assert isinstance(result, Rejection), f"expected a refusal, got {result}"
    assert result.from_verifier, "the body is not attributed to the verifier"

    payload = {p: b for p, b in files.items() if p != SUMS_NAME}
    by_hand, exit_status = _verifier_by_hand(payload, tmp_path)
    assert exit_status != "0", "the verifier did not refuse by hand, so this proves nothing"
    assert result.body == by_hand, (
        "the 422 body is not the verifier's message word for word.\n"
        f"--- body ---\n{result.body[-400:]}\n--- by hand ---\n{by_hand[-400:]}")
    assert "digest matches the manifest" in result.body


def test_a_wrong_chain_head_with_honest_sums_is_stored_as_contradicting(files, store):
    """`chain_head` is out of the 422 set.

    The earlier version of this test asserted the opposite. It changed because a `chain_head`
    mismatch under honest sums is not damage: the delivery arrived exactly as its sender made
    it, and what it says contradicts itself. So the run is stored, and the verifier's own row
    for it is in the stored report.
    """
    _require_installed()
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    manifest["chain_head"] = "sha256:" + "0" * 64
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    _resum(files)                                # honest sums: the delivery is not damaged

    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), (
        f"a chain_head mismatch was refused with a 422: "
        f"{getattr(result, 'body', '')[-300:]}")

    run = run_and_record(result.run, store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == "contradicts", run.check_verdict
    report = json.loads(store.get(run.check_report).decode("utf-8"))["stdout"]
    #: The verifier's own row, taken from the constant rather than retyped here, so the two
    #: cannot drift and the constant is not left as decoration now that it gates nothing.
    assert f"[FAIL   ] {CHAIN_HEAD_ROW}" in report, report[-300:]


def test_an_unknown_format_is_refused_in_the_verifiers_own_words(files, store, tmp_path):
    """The unknown-format residual is **closed**, and this is the switch planned for it.

        Keep the test that fails if the verifier gains the check, and when it does, switch
        to the verifier's words.

    The verifier gained the check at `90584f4`. The self-cancelling test
    that stood here fired the moment the pin moved, which is what it was for. The residual
    is gone: an R16 refusal now returns the verifier's own message, word for word, compared
    against a separate process running it by hand.
    """
    _require_installed()
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    manifest["format"] = "stage-receipt-chain/9.9"
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    _resum(files)

    payload = {p: b for p, b in files.items() if p != SUMS_NAME}
    by_hand, exit_status = _verifier_by_hand(payload, tmp_path)
    assert exit_status != "0", (
        "the verifier no longer refuses an unknown manifest format, so this test is not "
        "exercising the switch it was written for")
    assert "is not implemented" in by_hand, by_hand[-300:]

    result = accept(make_tar(files), store)
    assert isinstance(result, Rejection), f"expected a refusal, got {result}"
    assert result.from_verifier, "the body is not attributed to the verifier"
    assert result.body == by_hand, (
        "the 422 body is not the verifier's message word for word.\n"
        f"--- body ---\n{result.body[-300:]}\n--- by hand ---\n{by_hand[-300:]}")
    assert store.runs() == (), "an unknown format was stored"


def test_a_refusal_the_verifier_has_no_words_for_stays_in_the_stores_own_words(files, store,
                                                                              tmp_path):
    """The other branch, still reachable, and still honestly attributed.

    An unlisted extra file is damage the verifier cannot see: the manifest does not name it,
    so the verifier passes and only `SHA256SUMS` catches it. The body is then this store's
    words with `from_verifier` **false** — never attributed to the verifier, because a 422
    claiming the verifier's sentence when it was ours would be undetectable from outside.
    Both branches are covered so the attribution cannot quietly become a habit.
    """
    _require_installed()
    files["receipts/99-smuggled.json"] = b'{"format":"stage-receipt/0.1"}'
    # sums deliberately NOT recomputed: the extra file is present but unlisted

    payload = {p: b for p, b in files.items() if p != SUMS_NAME}
    by_hand, exit_status = _verifier_by_hand(payload, tmp_path)
    assert exit_status == "0", (
        f"the verifier now objects to an unlisted extra file, so this branch is no longer "
        f"the one with no verifier words: {by_hand[-300:]}")

    result = accept(make_tar(files), store)
    assert isinstance(result, Rejection), f"expected a refusal, got {result}"
    assert not result.from_verifier, (
        "the body claims to be the verifier's, but the verifier said nothing about it")
    assert "present but unlisted" in result.body, result.body
    assert store.runs() == ()


# ------------------------------- a 422 is for damage only, never for a verdict

def test_a_contradicting_run_is_stored_and_never_a_422(files, store):
    """The rule's sharpest line, asserted directly.

    The delivery is internally valid -- its sums are recomputed -- and the RECORD
    contradicts itself: a receipt whose field changed so its digest no longer matches what
    the manifest recorded. That is a verdict, so it is STORED and recorded as
    contradicting. A 422 here would be the console refusing to hold evidence because the
    evidence is bad news, which is the opposite of the job.
    """
    _require_installed()
    #: A NON-LAST receipt, deliberately. Changing the last one also moves the chain's head,
    #: which trips the `chain_head` pre-store check and so returns 422 by the rule's own
    #: list — a real edge, raised in the addendum rather than smoothed over here.
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-changed"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    _resum(files)

    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), (
        f"a contradicting run was refused with a 422: "
        f"{getattr(result, 'body', '')[-300:]}")

    run = run_and_record(result.run, store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == "contradicts", run.check_verdict
    assert store.get_run(run.key) is not None, "the contradicting run was not kept"


#: The first receipt in the chain and the last one. Which receipt moved used to decide
#: which side of the damage/verdict line the upload landed on, because changing the last
#: one also moves the chain's head. It no longer does: the line is the sums and nothing
#: else.
FIRST_RECEIPT = "receipts/01-zeta.json"
LAST_RECEIPT = "receipts/03-join.json"


@pytest.mark.parametrize("target", [FIRST_RECEIPT, LAST_RECEIPT])
def test_an_honest_delivery_of_a_contradicting_record_is_stored(files, store, target):
    """The rule's check, first half:

        the test pair now shows that changing the last receipt and changing an earlier
        receipt, both with honest sums, **both** give a stored contradiction.

    `LAST_RECEIPT` is the case that used to return 422, because moving it moves the chain's
    head. It is parametrised beside the earlier receipt so the two can never drift apart
    again.
    """
    _require_installed()
    raw = bytearray(files[target])
    raw[40] = (raw[40] + 1) % 256
    files[target] = bytes(raw)
    _resum(files)                                # honest sums: not damage, whichever moved

    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), (
        f"changing {target} with honest sums was refused with a 422: "
        f"{getattr(result, 'body', '')[-300:]}")
    run = run_and_record(result.run, store, ran_at=FIXED_RAN_AT)
    assert run.check_verdict == "contradicts", run.check_verdict
    assert store.get_run(run.key) is not None, "the contradicting run was not kept"


@pytest.mark.parametrize("target", [FIRST_RECEIPT, LAST_RECEIPT])
def test_a_damaged_delivery_is_refused_whichever_receipt_moved(files, store, target):
    """The rule's check, second half: *"Changing either one with stale sums gives a 422."*

    Same byte, same receipts, and the only difference from the test above is whether
    `SHA256SUMS` was recomputed. That is the whole of the line the rule drew.
    """
    _require_installed()
    raw = bytearray(files[target])
    raw[40] = (raw[40] + 1) % 256
    files[target] = bytes(raw)
    # sums deliberately NOT recomputed: the delivery no longer matches its own sums

    result = accept(make_tar(files), store)
    assert isinstance(result, Rejection), f"a damaged delivery of {target} was stored"
    assert result.status == 422
    assert store.runs() == (), "a damaged upload was stored"


# ------------------------------------------------------ the verifier is asked in staging

def test_the_verifier_is_actually_run_in_the_staging_area(files, monkeypatch, tmp_path):
    """The premise of everything above: the pre-store checks really do consult it.

    Without this, every test in this file would still pass against an implementation that
    never staged anything and happened to produce matching words some other way.
    """
    _require_installed()
    seen = {}
    real = staging_mod.ask_the_verifier

    def watched(folder, **kw):
        seen["folder"] = Path(folder)
        seen["manifest_there"] = (Path(folder) / "MANIFEST.json").is_file()
        return real(folder, **kw)

    monkeypatch.setattr("onetrace_console.ingest.ask_the_verifier", watched)
    from onetrace_console.store import Store
    #: The test's own folder, never `tempfile.mkdtemp()`, which left it in $TMPDIR.
    store = Store(tmp_path / "store")
    accept(make_tar(files), store)

    assert "folder" in seen, "the verifier was never asked"
    assert seen["manifest_there"], "the delivery was not written into staging before asking"
    assert staging_mod.PREFIX in str(seen["folder"]), (
        f"the verifier was run somewhere other than a staging area: {seen['folder']}")
    assert not seen["folder"].exists(), "the staging area was not deleted afterwards"
