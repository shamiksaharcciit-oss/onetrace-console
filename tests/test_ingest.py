"""A delivery is accepted whole or rejected whole, and the bundle comes back
byte-for-byte.

Four checks on delivery, each with a test named after it:

  - a valid run is stored;
  - tampering with one byte is rejected, and nothing is stored;
  - sending the same run twice stores one copy;
  - a reused `run_id` is flagged.

And one on the way back: the bundle comes back with every file byte-for-byte identical,
verified by its sums.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from onetrace_console.ingest import (MANIFEST_NAME, RUN_ID_REUSED, SUMS_NAME, Accepted,
                                     Rejection, accept, bundle, check_sums, read_tar)
from onetrace_console.store import StoreError, digest, run_key
from tests.conftest import make_tar


def _rejected(result) -> Rejection:
    assert isinstance(result, Rejection), f"expected a refusal, got {result}"
    assert result.status == 422
    assert result.rows, "a refusal with no rows says nothing"
    for r in result.rows:
        assert r.startswith("[FAIL   ] "), f"not the verifier's row grammar: {r!r}"
    return result


# ------------------------------------------------------------- a valid run is stored

def test_a_valid_run_is_stored(delivery, store):
    result = accept(delivery, store)
    assert isinstance(result, Accepted), getattr(result, "rows", result)
    assert result.created and result.status == 201
    run = result.run
    assert run.run_id == "dag-r37-r"
    assert run.format == "stage-receipt-chain/0.1"
    assert run.flags == ()
    assert run.key == run_key(run.run_id, run.chain_head)
    assert store.get_run(run.key) == run
    assert len(store.runs()) == 1


def test_what_was_stored_is_what_arrived(delivery, files, store):
    """Every delivered file is in the listing, under a key that is its own digest."""
    run = accept(delivery, store).run
    assert dict(run.listing).keys() == files.keys()
    for path, key in run.listing:
        assert key == digest(files[path]), f"{path} stored under the wrong key"
        assert store.get(key) == files[path], f"{path} did not come back as delivered"


def test_the_index_fields_are_recorded_even_though_nothing_reads_them_yet(delivery, files,
                                                                         store):
    """DESIGN_GAPS.md §4: cheap now, expensive to backfill.

    The stages are asserted exactly, in order. The first version of this test read
    `== () or set(...) == {...}`, which passes when the field is EMPTY -- a guard that
    cannot fail is not a guard (F15 on the canary channel), and this one would have
    reported success for recording nothing at all.
    """
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    assert "declared_stages" not in manifest, (
        "the fixture now declares its stages, so this test is no longer exercising the "
        "fallback that derives them from the chain")
    run = accept(delivery, store).run
    assert run.declared_stages == ("zeta", "alpha", "join"), run.declared_stages
    assert run.stage_count == 3
    assert run.recorded_count == 3
    assert run.pipeline == digest(files[MANIFEST_NAME])


# ------------------------------------- tampering is rejected, and nothing is stored

@pytest.mark.parametrize("target", ["MANIFEST.json", "receipts/01-zeta.json"])
def test_tampering_with_one_byte_is_rejected_and_nothing_is_stored(files, store, target):
    """One byte, not one field: the check is over bytes, so the smallest change must fail.

    Both halves asserted. "Rejected" alone would pass for an implementation that rejected
    the delivery after writing half of it to disk, which is the failure the design note's
    "nothing partial is ever stored" is about.
    """
    raw = bytearray(files[target])
    offset = len(raw) // 2
    raw[offset] = (raw[offset] + 1) % 256
    files[target] = bytes(raw)

    result = _rejected(accept(make_tar(files), store))
    assert any(target in r and "bytes match the sums file" in r for r in result.rows), \
        result.rows
    assert store.runs() == (), "a rejected delivery left a run behind"
    assert not any(store.root.joinpath("objects").rglob("*")), \
        "a rejected delivery left objects behind"


def test_a_file_present_but_unlisted_is_rejected(files, store):
    """The other direction. A one-directional coverage check is how a hole gets in."""
    files["receipts/99-smuggled.json"] = b'{"format":"stage-receipt/0.1"}'
    result = _rejected(accept(make_tar(files), store))
    assert any("present but unlisted" in r for r in result.rows), result.rows
    assert store.runs() == ()


def test_a_listed_file_that_is_missing_is_rejected(files, store):
    del files["receipts/02-alpha.json"]
    result = _rejected(accept(make_tar(files), store))
    assert any("02-alpha" in r and "is not in the archive" in r for r in result.rows), \
        result.rows
    assert store.runs() == ()


def test_a_delivery_with_no_sums_file_is_rejected(files, store):
    del files[SUMS_NAME]
    result = _rejected(accept(make_tar(files), store))
    assert any(SUMS_NAME in r for r in result.rows), result.rows


# --------------------------------------------------- chain_head, and formats (R16)

def test_a_chain_head_that_is_not_the_chains_head_is_stored_not_refused(files, store):
    """This is not in the 422 set, and rightly so.

    The check itself was correct about the fact -- this manifest's `chain_head` is not its
    last link's digest -- and wrong about the consequence. The delivery arrived exactly as
    its sender made it; what it says contradicts *itself*. That is a verdict, so the run is
    stored and the verifier reports it. `tests/test_staging.py` carries the verdict half.
    """
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    manifest["chain_head"] = "sha256:" + "0" * 64
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    _resum(files)                                     # honest sums: not damage
    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), getattr(result, "body", result)
    assert len(store.runs()) == 1


def test_a_header_that_disagrees_with_the_manifest_is_flagged_not_refused(delivery, store):
    """Not one of the two things a 422 is for, so it is recorded rather than refused.

    Kept as a flag rather than dropped: a delivery whose envelope contradicts its contents
    is worth knowing about, and ignoring the header entirely would make it a decoration.
    This placement is a reading of the rule rather than a sentence in it, and the addendum
    says so.
    """
    result = accept(delivery, store, headers={"chain_head": "sha256:deadbeef"})
    assert isinstance(result, Accepted), getattr(result, "body", result)
    assert any("disagrees with the manifest" in f for f in result.run.flags), result.run.flags


def test_headers_that_agree_are_accepted(delivery, files, store):
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    result = accept(delivery, store, headers={
        "run_id": manifest["run_id"], "chain_head": manifest["chain_head"],
        "format": manifest["format"]})
    assert isinstance(result, Accepted), getattr(result, "rows", result)


def test_an_unknown_manifest_format_is_rejected(files, store):
    """R16: a format the store does not implement is refused, not read hopefully."""
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    manifest["format"] = "stage-receipt-chain/9.9"
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    _resum(files)
    result = _rejected(accept(make_tar(files), store))
    assert any("format is one this store implements" in r for r in result.rows), result.rows


def test_an_unknown_receipt_format_is_rejected(files, store):
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["format"] = "stage-receipt/9.9"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    _resum(files)
    result = _rejected(accept(make_tar(files), store))
    assert any("01-zeta" in r and "format is one this store implements" in r
               for r in result.rows), result.rows


def test_a_verb_report_beside_the_receipts_is_not_treated_as_a_receipt(files, store,
                                                                      run_folder):
    """A real run folder carries `localize/localize.json`, which is `onetrace-report/0.1`.

    The first version of the format check looked at every `*.json` in the delivery and
    refused this. It is not a receipt, the manifest's chain does not name it, and a store
    that rejected it would reject real run folders.
    """
    report = run_folder / "localize" / "localize.json"
    assert report.is_file(), "the fixture no longer carries a verb report"
    assert json.loads(report.read_bytes().decode("utf-8"))["format"] != "stage-receipt/0.1"
    files["localize/localize.json"] = report.read_bytes()
    _resum(files)
    result = accept(make_tar(files), store)
    assert isinstance(result, Accepted), getattr(result, "rows", result)


# -------------------------------------------------------------------- idempotency

def test_sending_the_same_run_twice_stores_one_copy(delivery, store):
    first = accept(delivery, store)
    assert isinstance(first, Accepted) and first.created and first.status == 201
    second = accept(delivery, store)
    assert isinstance(second, Accepted), getattr(second, "rows", second)
    assert not second.created, "the second delivery was stored again"
    assert second.status == 200
    assert second.run.key == first.run.key
    assert len(store.runs()) == 1
    assert second.run == first.run, "the second delivery changed the stored record"


def test_a_reused_run_id_with_a_different_chain_head_is_stored_and_flagged(files, store):
    """"two chains under one name is itself a finding" -- the design note, §1."""
    first = accept(make_tar(files), store)
    assert isinstance(first, Accepted) and first.run.flags == ()

    # A genuinely different chain under the same name: drop the last receipt and make the
    # manifest honest about it, so the delivery is valid and only its identity collides.
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    dropped = manifest["chain"].pop()
    del files[dropped["file"]]
    manifest["chain_head"] = manifest["chain"][-1]["digest"]
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode("utf-8")
    _resum(files)

    second = accept(make_tar(files), store)
    assert isinstance(second, Accepted), getattr(second, "rows", second)
    assert second.created, "the second chain was not stored"
    assert second.run.key != first.run.key
    assert RUN_ID_REUSED in second.run.flags, second.run.flags
    assert first.run.flags == (), "the flag was written onto the earlier run"
    assert len(store.runs()) == 2
    assert store.get_run(first.run.key) == first.run, "the first run changed"


# ------------------------------------------------- step 2: the bundle is identical

def test_the_bundle_comes_back_byte_for_byte(delivery, files, store):
    """Step 2's check, verified by the delivery's own sums rather than by our own record."""
    run = accept(delivery, store).run
    out = read_tar(bundle(run, store))
    assert out.keys() == files.keys(), "the bundle holds different paths"
    for path in files:
        assert out[path] == files[path], f"{path} came back changed"
    assert check_sums(out) == [], "the exported bundle does not satisfy its own sums file"


def test_the_bundle_is_the_same_bytes_every_time(delivery, store):
    """An export that differed run to run would make a reader ask which copy is evidence."""
    run = accept(delivery, store).run
    assert bundle(run, store) == bundle(run, store)


def test_the_bundle_keeps_the_order_the_delivery_arrived_in(delivery, files, store):
    run = accept(delivery, store).run
    assert list(read_tar(bundle(run, store))) == list(files)


# ---------------------------------------------------------- the store's own rules

def test_an_object_is_never_overwritten_with_different_bytes(store):
    key = store.put(b"the received bytes")
    assert store.put(b"the received bytes") == key, "put is not idempotent"
    path = store._object_path(key)
    path.write_bytes(b"something else entirely")
    with pytest.raises(StoreError, match="different bytes"):
        store.put(b"the received bytes")


def test_reading_an_object_whose_bytes_moved_raises(store):
    """Verified on the way out too. A store that only checks on the way in tells you
    about corruption at the worst possible moment."""
    key = store.put(b"frozen")
    store._object_path(key).write_bytes(b"thawed")
    with pytest.raises(StoreError, match="the bytes on disk moved"):
        store.get(key)


def test_an_archive_escaping_the_run_folder_is_refused(store):
    for name in ("../escape.json", "/etc/passwd"):
        data = make_tar({name: b"{}"})
        result = accept(data, store)
        assert isinstance(result, Rejection), f"{name} was not refused"
    assert store.runs() == ()


def test_an_unreadable_archive_is_refused_not_crashed(store):
    result = _rejected(accept(b"this is not a tar file at all", store))
    assert any("the archive can be read" in r for r in result.rows), result.rows


def _resum(files: dict[str, bytes]) -> None:
    """Recompute SHA256SUMS over the payload, keeping the delivery internally valid.

    Used by the tests that change a run legitimately. Without it every such test would
    fail on the sums check and prove nothing about the check it was written for.
    """
    lines = [f"{hashlib.sha256(b).hexdigest()}  {p}"
             for p, b in files.items() if p != SUMS_NAME]
    files[SUMS_NAME] = ("\n".join(lines) + "\n").encode("utf-8")
