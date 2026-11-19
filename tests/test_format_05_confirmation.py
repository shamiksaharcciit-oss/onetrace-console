"""A recipient confirmation (onetrace 0.8's section J) in a run the console stores: the CHANGELOG's known gap.

The Authorization page draws a recipient confirmation's rows, in the room an earlier release left for them
(`confirmations`, `tests/test_confirmations_page.py`). What the check says of a confirmation shows where
the console shows a check's rows: onetrace-verify's own `confirmation: …` rows, and its line on what a recipient
confirmation does not show, read as every other (`viewer.report`).

The run is onetrace 0.8.0's own accept vector `A102-real-effected`, a step that presented a permit and kept the
recipient's confirmation that it acted, copied byte for byte from onetrace 0.8.0's sdist
(`tests/format_05_vectors/PROVENANCE.md`).
"""

from __future__ import annotations

import hashlib
import html
import re
import shutil
from pathlib import Path

import pytest

VECTORS = Path(__file__).resolve().parent / "format_05_vectors"
RUN = "A102-real-effected"
CONFIRMATION_ROWS = (
    "confirmation: request",
    "confirmation: permit",
    "confirmation: recipient key",
    "confirmation: single use",
    "confirmation: outcome",
)


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _text(h: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", h)).split())


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import deliver_one
    from onetrace_console.store import Store

    root = tmp_path_factory.mktemp("confirmation")
    shutil.copytree(VECTORS / RUN, root / "runs" / RUN)
    store = Store(root / "store")
    loaded = deliver_one(root / "runs" / RUN, store, Config())
    assert loaded.run is not None, loaded
    return loaded.run, store


def test_the_run_is_onetrace_s_own_vector_byte_for_byte(examined):
    said = {}
    for line in (VECTORS / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `([^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(VECTORS / RUN).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (VECTORS / RUN).rglob("*")
        if p.is_file()
    }
    examined(len(have), "files of the vector")
    assert have and have == said


def test_the_run_is_stored_and_holds(stored, examined):
    from onetrace_console.checks import HOLDS

    run, _store = stored
    examined(1, "the stored run")
    assert run.format == "stage-receipt-chain/0.5" and run.check_verdict == HOLDS, (run.format, run.check_verdict)


def test_its_rows_show_on_the_proof_page_and_on_the_authorization_page(stored, examined):
    from onetrace_console.pages import render_execution

    run, store = stored
    pages = render_execution(run, store, generated_at="2026-10-04T12:00:00+00:00").pages
    proof, authorization = _text(pages["proof.html"]), pages["authorization.html"]
    examined(2, "pages")
    assert all(r in proof for r in CONFIRMATION_ROWS), [r for r in CONFIRMATION_ROWS if r not in proof]
    assert "a recipient confirmation: A confirmation shows the recipient said it acted." in proof
    #: The room an earlier release left for them is filled (`confirmations`, `tests/test_confirmations_page.py`).
    assert 'data-section="confirmations"' in authorization
    assert all(r in _text(authorization) for r in CONFIRMATION_ROWS)
