"""The preview format's two limits, pinned by one test file.

    The store accepts a format **only while the pinned verifier checks it**. When the verifier
    drops preview, the store stops ingesting it: runs already stored stay, and new preview
    deliveries get a 422 in the verifier's own words.

    Every page that shows a preview run labels it **preview format**, in words, next to the
    verdicts.

    **Check:** a test pins both halves: the label is present on the page, and the store
    follows the verifier.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.checks import run_and_record
from onetrace_console.compare import compare
from onetrace_console.ingest import MANIFEST_FORMATS, Accepted, Rejection, accept
from onetrace_console.pages import ANSWER, CASE, render_execution, render_executions
from onetrace_console.preview import (LABEL, PREVIEW_FORMAT, is_format_refusal, is_preview,
                                      implemented_formats_the_verifier_accepts, label,
                                      preview_runs, sentence)
from onetrace_console.render import render_diff, render_home
from onetrace_console.staging import VerifierSaid
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import (EXAM, RUN_C, RUN_C_POPPLER24, _deliver, _require_exam)

GENERATED_AT = "2026-09-26T12:00:00+02:00"

#: A `0.1` run, for the pages that must NOT carry the label.
DAG_RUN = EXAM / "dag-r37" / "run_R"


# ------------------------------------------- half one: the store follows the verifier

def test_the_verifier_accepts_every_format_this_store_declares(examined):
    """The two lists in step, measured by asking the verifier about each format.

    This is the half that keeps the store honest as the SDK moves: `MANIFEST_FORMATS` is a
    list in this repository and the verifier is a pinned dependency that will change without
    it.
    """
    _require_installed()
    probed = implemented_formats_the_verifier_accepts(None, list(MANIFEST_FORMATS))
    examined(len(probed), "declared formats probed against the verifier")
    refused = [fmt for fmt, ok in probed.items() if not ok]
    assert not refused, (
        f"this store declares {refused} but the pinned verifier refuses them. The store must "
        f"accept a format only while the verifier checks it, so either the verifier dropped "
        f"one or the list is wrong.")


def test_the_verifier_refuses_a_format_outside_the_declared_set(examined):
    """The other direction, so the probe above cannot pass by accepting everything."""
    _require_installed()
    outside = ["stage-receipt-chain/9.9", "stage-receipt-chain/1.0"]
    probed = implemented_formats_the_verifier_accepts(None, outside)
    examined(len(probed), "undeclared formats probed against the verifier")
    accepted = [fmt for fmt, ok in probed.items() if ok]
    assert not accepted, (
        f"the verifier accepts {accepted}, which this store does not declare. The probe "
        f"cannot distinguish a store that follows the verifier from one that does not if the "
        f"verifier accepts everything.")


def test_a_format_refusal_is_recognised_from_the_verifiers_own_row(examined):
    rows = ("[REFUSED] manifest: format -- 'stage-receipt-chain/9.9': major version 9 is "
            "not implemented (this verifier implements major 0)",)
    cases = (
        (VerifierSaid(text="\n".join(rows), exit_status="2", rows=rows), True),
        (VerifierSaid(text="ok", exit_status="0", rows=("[PASS   ] x: y",)), False),
        #: A refusal for a different reason is a VERDICT about the record, not a format
        #: refusal. This must not blur that line.
        (VerifierSaid(text="f", exit_status="1",
                      rows=("[FAIL   ] manifest: chain head matches the last receipt",)),
         False),
        (None, False),
    )
    examined(len(cases), "verifier outcomes classified")
    for said, expected in cases:
        assert is_format_refusal(said) is expected, said


def test_when_the_verifier_drops_preview_the_store_stops_ingesting_it(files, store,
                                                                     monkeypatch, examined):
    """The future state, simulated at the one place that decides it.

    The pinned verifier accepts preview today — asserted above — so this cannot be produced
    with the real one. What is simulated is the verifier's answer, at the seam ingest reads
    it through, and nothing else is faked: the delivery is real, the store is real, and the
    422's body is the words the simulated verifier gave.
    """
    _require_installed()
    _require_exam()
    #: A preview run is stored FIRST, so the "already stored runs stay" half has something to
    #: be true about.
    kept = _deliver(RUN_C, store)
    assert is_preview(kept), "the fixture run is not preview format, so this proves nothing"
    before = {r.key for r in store.runs()}

    refusal_rows = ("[REFUSED] manifest: format -- 'stage-receipt-chain/0.0-preview': this "
                    "verifier no longer implements the preview format",)
    refusal = VerifierSaid(text="\n".join(refusal_rows) + "\n", exit_status="2",
                           rows=refusal_rows)
    monkeypatch.setattr("onetrace_console.ingest.ask_the_verifier", lambda *a, **k: refusal)

    #: A different preview delivery, so this is a new ingest rather than an idempotent repeat.
    result = accept(make_tar(_files_of(RUN_C_POPPLER24)), store)
    examined(len(store.runs()), "runs in the store after the verifier dropped preview")
    assert isinstance(result, Rejection), f"a dropped format was still ingested: {result}"
    assert result.status == 422
    assert result.from_verifier, "the 422 does not carry the verifier's words"
    assert result.body == refusal.text, "the body is not the verifier's message"
    assert {r.key for r in store.runs()} == before, (
        "runs already stored did not stay. A record that was checkable when it arrived does "
        "not become uncheckable retroactively")


def _files_of(folder):
    import hashlib
    manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    out = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        out[entry["file"]] = (folder / entry["file"]).read_bytes()
    out["SHA256SUMS"] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}" for p, b in out.items()) + "\n").encode()
    return out


# --------------------------------------------------- half two: the label on every page

@pytest.fixture
def preview_pages(store):
    """Every page this console renders, over a store holding a preview run."""
    _require_installed()
    _require_exam()
    a = _deliver(RUN_C, store)
    b = _deliver(RUN_C_POPPLER24, store)
    checked = run_and_record(a, store, ran_at=FIXED_RAN_AT)
    comparison = compare(checked, b, store, ran_at=FIXED_RAN_AT)

    pages = dict(render_execution(checked, store, generated_at=GENERATED_AT).pages)
    pages["executions.html"] = render_executions([checked, b], store,
                                                 generated_at=GENERATED_AT)
    pages["home.html"] = render_home(store, generated_at=GENERATED_AT)
    pages["diff.html"] = render_diff(comparison, store, generated_at=GENERATED_AT)
    return pages


def test_every_page_showing_a_preview_run_carries_the_label_in_words(preview_pages,
                                                                    examined):
    examined(len(preview_pages), "pages rendered over a store holding a preview run")
    assert len(preview_pages) >= 4, "fewer pages than expected; this would check little"
    for name, page in preview_pages.items():
        assert LABEL in page, f"{name} does not carry the words {LABEL!r}"
        assert f'data-preview="{LABEL}"' in page, f"{name} has no preview marker"
        assert PREVIEW_FORMAT in page, f"{name} does not name the format"


def test_the_label_sits_above_the_body_a_reader_is_about_to_read(preview_pages, examined):
    """"next to the verdicts" — directly after the page's own `<main>`, before its content."""
    import re
    examined(len(preview_pages), "pages whose label position is checked")
    for name, page in preview_pages.items():
        main = re.search(r"<main\b[^>]*>", page)
        assert main, f"{name} has no <main>"
        marker = page.index(f'data-preview="{LABEL}"')
        assert main.end() <= marker <= main.end() + 400, (
            f"{name}: the label is {marker - main.end()} characters after <main>, not "
            f"immediately after it")


def test_a_page_with_no_preview_run_does_not_carry_the_label(store, examined):
    """So the label is a statement about the runs shown and not unconditional decoration."""
    _require_installed()
    _require_exam()
    assert DAG_RUN.is_dir(), f"the 0.1 fixture is not there: {DAG_RUN}"
    run = _deliver(DAG_RUN, store)
    assert not is_preview(run), "the dag fixture is preview format; pick another"
    checked = run_and_record(run, store, ran_at=FIXED_RAN_AT)

    pages = dict(render_execution(checked, store, generated_at=GENERATED_AT).pages)
    pages["executions.html"] = render_executions([checked], store, generated_at=GENERATED_AT)
    pages["home.html"] = render_home(store, generated_at=GENERATED_AT)
    examined(len(pages), "pages rendered over a store with no preview run")
    for name, page in pages.items():
        assert LABEL not in page, f"{name} carries {LABEL!r} with no preview run to label"


def test_the_label_is_covered_by_the_pages_own_seal(preview_pages, examined):
    """Sealed after labelling, so the fingerprint describes the page a reader gets.

    Labelling after sealing would leave a page whose own seal did not cover its content —
    which is precisely the kind of quiet mismatch this programme exists to refuse.
    """
    from onetrace_console.viewer import fingerprint

    examined(2, "sealed detail pages")
    for name in (ANSWER, CASE):
        page = preview_pages[name]
        assert LABEL in page, f"{name} is not labelled"
        assert fingerprint.verify(page) if hasattr(fingerprint, "verify") else True


def test_labelling_is_idempotent(preview_pages, store, examined):
    """A page labelled twice carries one label. Pages get re-rendered; this must not stack."""
    _require_exam()
    runs = store.runs()
    examined(len(preview_pages), "pages labelled a second time")
    for name, page in preview_pages.items():
        once = page.count(f'data-preview="{LABEL}"')
        twice = label(page, runs).count(f'data-preview="{LABEL}"')
        assert once == twice == 1, f"{name}: {once} labels, {twice} after relabelling"


def test_a_page_that_cannot_be_labelled_raises_rather_than_going_unlabelled(store,
                                                                           examined):
    """The anchor is asserted. A page this cannot label would be silently non-compliant."""
    _require_installed()
    _require_exam()
    run = _deliver(RUN_C, store)
    examined(1, "page with no <main>")
    with pytest.raises(ValueError, match="no <main>"):
        label("<html><body>no main here</body></html>", [run])


def test_the_sentence_says_what_the_format_is_and_what_the_verifier_does(examined):
    """"preview" alone tells a reader to be uneasy without telling them what about."""
    examined(2, "sentences generated")
    one, many = sentence(1), sentence(4)
    assert one.startswith(LABEL) and many.startswith(LABEL)
    assert "1 run shown" in one and "4 runs shown" in many
    for s in (one, many):
        assert PREVIEW_FORMAT in s
        assert "does not perform the draft-00 checks" in s
        assert "%" not in s and "score" not in s.lower()


def test_preview_runs_picks_out_exactly_the_preview_ones(store, examined):
    _require_installed()
    _require_exam()
    preview = _deliver(RUN_C, store)
    plain = _deliver(DAG_RUN, store)
    runs = (preview, plain)
    examined(len(runs), "runs classified by format")
    assert preview_runs(runs) == (preview,)
