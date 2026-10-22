"""The preview-format limits against the pinned verifier. The store accepts a format only while
the pinned verifier checks it; it no longer checks preview receipts (NOT-RUN, NOT VERIFIED), so a
NEW preview delivery gets a 422: one console sentence, then the verifier's own row, verbatim, and
nothing is stored. Runs already stored stay. A 0.1 or 0.2 delivery is taken.
"""
from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

from onetrace_console.ingest import SUMS_NAME, Rejection, accept
from onetrace_console.preview import PREVIEW_NOT_INGESTED, PREVIEW_NOT_RUN_ROW
from tests.test_checks import _require_installed
from tests.test_compare import EXAM, RUN_C, _deliver, _require_exam

RULED = ("Not ingested: this run is in the preview record format (stage-receipt/0.0-preview), and "
         "onetrace-verify does not check that format, so its receipts couldn't be checked.")


def _delivery(folder: Path) -> bytes:
    """The folder as a sidecar would deliver it: its chain and a SHA256SUMS, as a tar."""
    manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    files = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        files[entry["file"]] = (folder / entry["file"]).read_bytes()
    files[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                  for p, b in files.items()) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def test_the_sentence_is_the_ruled_one():
    assert PREVIEW_NOT_INGESTED == RULED


def test_a_new_preview_delivery_is_refused_in_the_ruled_words_and_nothing_is_stored(store, examined):
    _require_installed()
    _require_exam()
    got = accept(_delivery(RUN_C), store)
    examined(1, "preview delivery refused")
    assert isinstance(got, Rejection), got
    assert got.status == 422 and got.from_verifier is False, got
    first, row, *rest = got.body.split("\n")
    assert first == RULED, got.body
    assert row.startswith(PREVIEW_NOT_RUN_ROW) and "does not implement" in row, row
    assert rest == [""], got.body
    assert row in got.rows, got.rows
    assert store.runs() == (), store.runs()


def test_a_0_1_delivery_is_taken(store, examined):
    _require_installed()
    _require_exam()
    got = accept(_delivery(EXAM / "dag-r37" / "run_R"), store)
    examined(1, "0.1 delivery taken")
    assert got.run is not None, getattr(got, "body", got)
    assert got.run.format == "stage-receipt-chain/0.1"


def test_a_delivery_in_the_installed_sdk_s_format_is_taken(store, tmp_path, examined):
    """What the pinned SDK writes now (format 0.3, onetrace 0.4.0) is taken."""
    _require_installed()
    from tests.test_last_attempt_failed import _emit
    _emit(tmp_path / "r", "a-0-3-run", [("a", "1", "ok"), ("b", "1", "ok")])
    got = accept(_delivery(tmp_path / "r"), store)
    examined(1, "0.3 delivery taken")
    assert got.run is not None, getattr(got, "body", got)
    assert got.run.format == "stage-receipt-chain/0.3", got.run.format


def test_a_0_2_delivery_is_taken(store, examined):
    """A 0.2 run, the reference demo's committed day 1, is still taken."""
    _require_installed()
    folder = Path(__file__).resolve().parent.parent / "examples" / "reference-demo" / "runs" / "day-1"
    got = accept(_delivery(folder), store)
    examined(1, "0.2 delivery taken")
    assert got.run is not None, getattr(got, "body", got)
    assert got.run.format == "stage-receipt-chain/0.2", got.run.format


def test_a_preview_run_already_stored_stays_readable(store, examined):
    """Stored directly (as before the pin moved; see `_deliver`), it reads back, and a second
    delivery of the same run is still refused rather than overwriting anything."""
    _require_installed()
    _require_exam()
    held = _deliver(RUN_C, store)
    examined(2, "stored preview run read back, and redelivered")
    assert store.get_run(held.key).run_id == held.run_id
    again = accept(_delivery(RUN_C), store)
    assert isinstance(again, Rejection) and again.status == 422, again
    assert store.get_run(held.key) == held
