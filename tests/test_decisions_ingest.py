"""`onedoor_ext.decisions.accept_export`. One named test per upload-hardening check
this route inherits from `ingest.read_tar` (proving the reuse actually wires through,
not re-sabotaging `read_tar` itself -- that already happened in
`test_upload_hardening.py` against the identical function), plus the JSONL-specific
checks this route adds on top.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from onetrace_console.config import Config
from onetrace_console.onedoor_ext.decisions import DecisionsRejection, accept_export
from tests.test_upload_hardening import _member, _tar


def _sidecar(payload_name: str, data: bytes) -> tuple:
    return _member(f"{payload_name}.sha256",
                   f"{hashlib.sha256(data).hexdigest()}  {payload_name}\n".encode("utf-8"))


def _wrap(payload_name: str, data: bytes, *, sidecar_data: bytes | None = None) -> bytes:
    payload = _member(payload_name, data)
    sidecar = _member(f"{payload_name}.sha256", sidecar_data) if sidecar_data is not None \
        else _sidecar(payload_name, data)
    return _tar(payload, sidecar)


ROW1 = json.dumps({"request_id": "a", "kind": "decision", "decision": "denied"},
                  sort_keys=True, separators=(",", ":"))
ROW2 = json.dumps({"request_id": "b", "kind": "decision", "decision": "proposed"},
                  sort_keys=True, separators=(",", ":"))
TWO_ROWS = (ROW1 + "\n" + ROW2 + "\n").encode("utf-8")


# ------------------------------------------------------------- the real fixture

def test_the_real_fixture_export_is_accepted(onedoor_fixture_dir, store, examined):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    examined(1, "real onedoor exports posted")
    accepted = accept_export(archive, store)
    assert accepted.created
    assert len(accepted.export.rows) == 7


def test_a_repeated_identical_export_is_acknowledged_not_stored_again(
        onedoor_fixture_dir, store, examined):
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    examined(2, "deliveries of the identical export")
    first = accept_export(archive, store)
    second = accept_export(archive, store)
    assert first.created and not second.created
    assert first.export.key == second.export.key


def test_the_fixtures_own_shared_request_id_pair_is_allowed(onedoor_fixture_dir, store, examined):
    """The finding in PROVENANCE.md, proven positively: rows 1 and 2 of the real
    fixture share a request_id (exec_intent then exec_result) and this is not refused.
    """
    jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
    sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
    archive = _tar(_member("onedoor-export.jsonl", jsonl),
                   _member("onedoor-export.jsonl.sha256", sidecar))
    rows = [json.loads(l) for l in jsonl.decode("utf-8").splitlines() if l]
    request_ids = [r["request_id"] for r in rows]
    examined(1, "request_ids appearing more than once across kinds in the real fixture")
    assert len(set(request_ids)) < len(request_ids), \
        "the fixture no longer demonstrates the shared-request_id shape this test checks"
    accepted = accept_export(archive, store)
    assert accepted.created


# ---------------------------------------------------------------- item 1: traversal

def test_item1_a_traversal_member_name_is_refused(store, examined):
    archive = _tar(_member("../escape.jsonl", TWO_ROWS), _sidecar("../escape.jsonl", TWO_ROWS))
    examined(1, "traversal member names posted to /v1/decisions")
    with pytest.raises(DecisionsRejection, match="delivery"):
        accept_export(archive, store)


# --------------------------------------------------------- item 2: links/special

def test_item2_a_symlink_member_is_refused(store, examined):
    import tarfile
    archive = _tar(_member("onedoor-export.jsonl", type_=tarfile.SYMTYPE, linkname="/etc/passwd"),
                   _sidecar("onedoor-export.jsonl", TWO_ROWS))
    examined(1, "symlink members posted to /v1/decisions")
    with pytest.raises(DecisionsRejection, match="delivery"):
        accept_export(archive, store)


# ------------------------------------------------------- item 3b/3c: size limits

def test_item3b_the_member_count_limit_is_enforced(store, examined):
    archive = _wrap("onedoor-export.jsonl", TWO_ROWS)
    examined(1, "deliveries posted against a member limit of 1")
    with pytest.raises(DecisionsRejection):
        accept_export(archive, store, limits=Config(max_members=1))


def test_item3c_the_total_size_limit_is_enforced(store, examined):
    archive = _wrap("onedoor-export.jsonl", TWO_ROWS)
    examined(1, "deliveries posted against a total-size limit smaller than the export")
    with pytest.raises(DecisionsRejection):
        accept_export(archive, store, limits=Config(max_total_extracted_size=4))


# --------------------------------------------------- item 5: malformed input, 422

def test_item5_a_malformed_archive_is_refused_and_nothing_is_stored(store, examined):
    examined(1, "garbage bytes posted to /v1/decisions")
    with pytest.raises(DecisionsRejection):
        accept_export(b"not a tar file at all", store)
    assert store.decision_exports() == ()


def test_a_checksum_mismatch_is_refused_and_nothing_is_stored(store, examined):
    archive = _wrap("onedoor-export.jsonl", TWO_ROWS,
                    sidecar_data=(hashlib.sha256(b"different bytes").hexdigest()
                                 + "  onedoor-export.jsonl\n").encode("utf-8"))
    examined(1, "exports whose sidecar does not match the delivered bytes")
    with pytest.raises(DecisionsRejection, match="does not match"):
        accept_export(archive, store)
    assert store.decision_exports() == ()


def test_the_wrong_number_of_members_is_refused(store, examined):
    examined(2, "archives with zero or three members instead of exactly two")
    with pytest.raises(DecisionsRejection):
        accept_export(_tar(), store)
    archive = _tar(_member("onedoor-export.jsonl", TWO_ROWS),
                  _sidecar("onedoor-export.jsonl", TWO_ROWS),
                  _member("extra.txt", b"x"))
    with pytest.raises(DecisionsRejection):
        accept_export(archive, store)


# ---------------------------------------------------------- JSONL-specific checks

def test_a_row_count_over_the_limit_is_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", TWO_ROWS)
    examined(1, "exports posted against a row limit of 1")
    with pytest.raises(DecisionsRejection, match="row"):
        accept_export(archive, store, limits=Config(max_decision_rows=1))


def test_a_line_over_the_length_limit_is_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", TWO_ROWS)
    examined(1, "exports posted against a line-length limit shorter than a real row")
    with pytest.raises(DecisionsRejection, match="line limit"):
        accept_export(archive, store, limits=Config(max_decision_line_length=8))


def test_non_utf8_bytes_are_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", b"\xff\xfe not utf-8\n")
    examined(1, "non-UTF-8 exports")
    with pytest.raises(DecisionsRejection, match="UTF-8"):
        accept_export(archive, store)


def test_an_invalid_json_row_is_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", b"{not json}\n")
    examined(1, "rows that are not valid JSON")
    with pytest.raises(DecisionsRejection, match="not valid JSON"):
        accept_export(archive, store)


def test_a_non_object_row_is_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", b'["a", "list", "not", "an", "object"]\n')
    examined(1, "rows that are JSON but not an object")
    with pytest.raises(DecisionsRejection, match="not a JSON object"):
        accept_export(archive, store)


def test_a_float_anywhere_in_a_row_is_refused(store, examined):
    bad = json.dumps({"request_id": "a", "kind": "decision", "cost": 1.5},
                     sort_keys=True, separators=(",", ":")) + "\n"
    archive = _wrap("onedoor-export.jsonl", bad.encode("utf-8"))
    examined(1, "rows carrying a float")
    with pytest.raises(DecisionsRejection, match="float"):
        accept_export(archive, store)


def test_a_float_nested_inside_a_row_is_also_refused(store, examined):
    bad = json.dumps({"request_id": "a", "kind": "decision", "nested": {"x": [1, 2.0]}},
                     sort_keys=True, separators=(",", ":")) + "\n"
    archive = _wrap("onedoor-export.jsonl", bad.encode("utf-8"))
    examined(1, "rows carrying a float nested inside a list inside an object")
    with pytest.raises(DecisionsRejection, match="float"):
        accept_export(archive, store)


def test_duplicate_request_id_and_kind_pair_is_refused(store, examined):
    dup = json.dumps({"request_id": "a", "kind": "decision", "decision": "denied"},
                     sort_keys=True, separators=(",", ":"))
    data = (dup + "\n" + dup + "\n").encode("utf-8")
    archive = _wrap("onedoor-export.jsonl", data)
    examined(1, "exports with the same (request_id, kind) pair twice")
    with pytest.raises(DecisionsRejection, match="duplicate"):
        accept_export(archive, store)


def test_the_same_request_id_with_a_different_kind_is_not_a_duplicate(store, examined):
    a = json.dumps({"request_id": "shared", "kind": "exec_intent", "decision": "executed"},
                   sort_keys=True, separators=(",", ":"))
    b = json.dumps({"request_id": "shared", "kind": "exec_result", "decision": "executed"},
                   sort_keys=True, separators=(",", ":"))
    data = (a + "\n" + b + "\n").encode("utf-8")
    archive = _wrap("onedoor-export.jsonl", data)
    examined(1, "exports where one request_id has two different kinds")
    accepted = accept_export(archive, store)
    assert accepted.created
    assert len(accepted.export.rows) == 2


def test_an_empty_export_is_refused(store, examined):
    archive = _wrap("onedoor-export.jsonl", b"")
    examined(1, "empty exports")
    with pytest.raises(DecisionsRejection, match="no rows"):
        accept_export(archive, store)
