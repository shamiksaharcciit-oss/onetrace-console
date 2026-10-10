"""Two notes from the pin re-check's review, on the onedoor side-car's sums.

1. The onedoor side-car's sums name exactly the delivered file, and nothing else. It used to look up
   only the delivered file's own name, so a second digest under another spelling -- `./x`, another
   case -- was silently ignored: two digests for one file, which is a contradiction. A
   run delivery checks both ways; the side-car now does too.
2. A refusal names the side-car's own file (`onedoor-export.jsonl.sha256`), not `SHA256SUMS`.
"""
from __future__ import annotations

import hashlib

import pytest

from onetrace_console.ingest import DeliveryRefused, parse_sums
from onetrace_console.onedoor_ext.decisions import DecisionsRejection, accept_export
from tests.test_upload_hardening import _member, _tar

NAME = "onedoor-export.jsonl"
SIDECAR = NAME + ".sha256"
ZERO = "0" * 64


def _delivery(onedoor_fixture_dir, sidecar_text: str) -> bytes:
    jsonl = (onedoor_fixture_dir / NAME).read_bytes()
    return _tar(_member(NAME, jsonl), _member(SIDECAR, sidecar_text.encode("utf-8")))


def _good(onedoor_fixture_dir) -> str:
    return hashlib.sha256((onedoor_fixture_dir / NAME).read_bytes()).hexdigest()


@pytest.mark.parametrize("other", [f"./{NAME}", NAME.upper(), "something-else.jsonl"],
                         ids=["dot-slash spelling", "other case", "another file"])
def test_a_side_car_naming_anything_beside_the_delivered_file_is_refused(
        onedoor_fixture_dir, store, other, examined):
    good = _good(onedoor_fixture_dir)
    text = f"{good}  {NAME}\n{ZERO}  {other}\n"
    examined(1, f"side-car naming {other!r} beside the delivered file")
    with pytest.raises(DecisionsRejection) as e:
        accept_export(_delivery(onedoor_fixture_dir, text), store)
    said = str(e.value)
    assert "nothing else" in said and repr(other) in said, said


def test_the_committed_side_car_is_still_accepted(onedoor_fixture_dir, store, examined):
    sidecar = (onedoor_fixture_dir / SIDECAR).read_text(encoding="utf-8")
    examined(1, "the committed side-car")
    assert accept_export(_delivery(onedoor_fixture_dir, sidecar), store).created


def test_a_side_car_s_refusal_names_its_own_file(onedoor_fixture_dir, store, examined):
    good = _good(onedoor_fixture_dir)
    text = f"{good}  {NAME}\n{good}  {NAME}\n"
    examined(1, "side-car listing its file twice")
    with pytest.raises(DecisionsRejection) as e:
        accept_export(_delivery(onedoor_fixture_dir, text), store)
    said = str(e.value)
    assert said.startswith(f"[FAIL   ] {SIDECAR}:"), said
    assert "SHA256SUMS" not in said, said


def test_the_parser_names_the_file_it_was_given_and_defaults_to_sha256sums(examined):
    bad = b"not a sums line\n"
    examined(2, "refusals from the parser")
    with pytest.raises(DeliveryRefused) as named:
        parse_sums(bad, name=SIDECAR)
    assert named.value.rows[0].startswith(f"[FAIL   ] {SIDECAR}:"), named.value.rows
    with pytest.raises(DeliveryRefused) as default:
        parse_sums(bad)
    assert default.value.rows[0].startswith("[FAIL   ] SHA256SUMS:"), default.value.rows
