"""The run receipt, row by row.

Every row is derived from the record or the console's own verifier run -- a test per row, each with
a sabotage that states the row without its evidence. The signature row and the graph's "all in the
approved graph" read "not available until onetrace 0.2.0", never a guessed state, until the third
build; the anchor row is the run page's own rung since step 3 (tests/test_step3_receipt_anchor.py).
"Check it yourself" gives the command the run's record needs (tests/test_receipt_look.py holds it for
unsigned, signed and anchored runs); "What this receipt does not say" is the work order's fixed text.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from html import unescape

from tests.test_stage_pages import DEMO, _pages, demo, tampered  # noqa: F401
from tests.conftest import whole_folds

PLACEHOLDER = "not available until onetrace 0.2.0"


def _receipt(run, store) -> str:
    return _pages(run, store)["receipt.html"]


def _row(page: str, name: str) -> str:
    found = re.search(rf'<tr data-row="{re.escape(name)}">(.*?)</tr>', page, re.S)
    assert found, f"no {name} row"
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(found.group(1))))).strip()


def _manifest() -> dict:
    return json.loads((DEMO / "day-1" / "MANIFEST.json").read_text(encoding="utf-8"))


def test_the_run_row_names_the_run_by_id_and_key(demo):  # noqa: F811
    run, store = demo
    assert f"{run.run_id} · {run.key[:12]}" in _row(_receipt(run, store), "run")


def test_the_format_row_is_the_record_s(demo):  # noqa: F811
    run, store = demo
    assert _manifest()["format"] in _row(_receipt(run, store), "format")


def test_the_stages_row_is_the_overview_s_derived_cell(demo):  # noqa: F811
    run, store = demo
    from onetrace_console.render import _recorded_of_declared
    assert _recorded_of_declared(run) in _row(_receipt(run, store), "stages")


def test_the_graph_row_counts_the_record_s_nodes_and_links(demo):  # noqa: F811
    run, store = demo
    m = _manifest()
    row = _row(_receipt(run, store), "graph")
    assert f"{len(m['chain'])} nodes · {len(m['edges'])} links" in row
    #: Then the verifier's own edge rows from this run's check, verbatim, and
    #: no later version's promise.
    from html import unescape

    from onetrace_console.checks import _EDGE_ROW
    from onetrace_console.pages import _envelope
    rows = [line.strip() for line in _envelope(run, store)["stdout"].splitlines()
            if _EDGE_ROW.match(line.strip())]
    assert rows, "this run's check reported no edge row, so the row's second half is untested"
    #: `_row` reads the row's text with its whitespace collapsed; the rows are compared the same way.
    assert all(" ".join(r.split()) in unescape(row) for r in rows), (rows, row)
    assert PLACEHOLDER not in row and "until onetrace" not in row


def test_the_chain_head_row_is_the_manifest_s(demo):  # noqa: F811
    run, store = demo
    assert _manifest()["chain_head"] in _row(_receipt(run, store), "chain-head")


def test_the_output_files_row_counts_what_matched(demo):  # noqa: F811
    run, store = demo
    assert "6 of 6 present and matching their receipts" in _row(_receipt(run, store), "outputs")


def test_a_tampered_output_is_not_counted_as_matching(tampered):  # noqa: F811
    """Its own store: the tampered delivery has the demo's manifest, so the same run key."""
    bad, store = tampered
    assert "5 of 6 present and matching their receipts" in _row(_receipt(bad, store), "outputs")


def test_the_model_stages_row_names_each_with_the_record_s_note(demo):  # noqa: F811
    run, store = demo
    row = _row(_receipt(run, store), "model-stages")
    assert "model" in row and "declared not re-runnable" in row
    assert "a sampled model call: its output is recorded, not replayed" in row


def test_the_authorization_row(demo):  # noqa: F811
    run, store = demo
    assert "no authorization records" in _row(_receipt(run, store), "authorization")


def test_the_recorded_row_states_the_record_s_time_and_no_invented_version(demo):  # noqa: F811
    """The reference demo's runs have no onetrace intake stage, so the record does not say which
    onetrace version made them, and the row says exactly that."""
    run, store = demo
    page = _receipt(run, store)
    row = _row(page, "recorded")
    assert "2026-09-28 10:00:00 UTC → 10:00:13 UTC" in row
    raw = re.search(r'<tr data-row="recorded">(.*?)</tr>', page, re.S).group(1)
    assert 'datetime="2026-09-28T10:00:00.000+00:00"' in raw, "the whole value is in its <time>"
    assert "the record does not say which onetrace version made it" in row
    assert "recorded with onetrace" not in row


def test_the_recorded_row_reads_the_version_from_the_run_s_intake_stage(store, examined):
    """A run made by onetrace 0.2.0 carries the intake stage's receipt, whose instrument is
    `onetrace-intake` with its version: the row says that version and where it was read from."""
    from tests.test_checks import _require_installed
    from tests.test_stage_pages import _stored
    _require_installed()
    rc2 = Path(__file__).resolve().parent / "fixtures" / "demo-runs-rc2"
    names = ("ingest-day1", "query-day1")
    examined(len(names), "RC2 runs")
    for name in names:
        run = _stored(rc2 / name, store)
        row = _row(_receipt(run, store), "recorded")
        assert "recorded with onetrace 0.2.0 (from the run's intake stage)" in row, row
        assert "does not say which onetrace version" not in row, row


def test_signature_is_the_run_pages_signing_rung(demo):  # noqa: F811
    """The run's own "Signed by a known recorder" rung. The demo's day 1 is signed
    by the demo key; checked here without a trust file, it reads "Signed, key not trusted"
    (tests/test_signed_surfaces.py holds each state)."""
    run, store = demo
    key_id = json.loads((DEMO / "day-1" / "signatures" / "1.json").read_text(encoding="utf-8"))["key_id"]
    assert _row(_receipt(run, store), "signature") == f"Signature Signed, key not trusted · {key_id}"


def test_the_header_pills_are_the_verifier_s_counts(demo):  # noqa: F811
    run, store = demo
    from onetrace_console.viewer.report import parse
    from onetrace_console.pages import _envelope
    report = parse(_envelope(run, store))
    total = report.count("pass") + report.count("fail") + report.count("not_run")
    pills = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(re.search(
        r'<p data-section="pills">(.*?)</p>', _receipt(run, store), re.S).group(1)))))
    assert f"{report.count('pass')} of {total} checks" in pills
    assert "Signed: Signed, key not trusted" in pills and pills.rstrip().endswith("Anchored: Not anchored")


def _pills(run, store) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(re.search(
        r'<p data-section="pills">(.*?)</p>', _receipt(run, store), re.S).group(1))))).strip()


def test_a_check_that_held_without_output_files_required_is_not_said_to_agree(demo):  # noqa: F811
    """Only a check run with the output files required is evidence. Since
    step 2 that run is made only where the run holds `artifacts/`; the demo run
    does, so here its stored report is taken without it -- as a run without `artifacts/` is."""
    import json
    from dataclasses import replace
    run, store = demo
    assert run.check_verdict == "holds"
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    envelope.pop("outputs_required")
    from tests.test_one_reading import reread
    without = reread(replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8"))), store)
    assert _pills(without, store).startswith(
        "Records agree: not checked (held without its output files required)")


def test_a_run_holding_its_outputs_and_passing_with_them_required_agrees(demo):  # noqa: F811
    """The demo run holds `artifacts/`; its outputs-required run passed."""
    import json
    run, store = demo
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    assert envelope["outputs_required"]["exit_status"] == "0"
    assert _pills(run, store).startswith("Records agree: yes ·")


def test_records_agree_only_for_a_check_that_required_the_output_files(demo, monkeypatch):  # noqa: F811
    run, store = demo
    import onetrace_console.home as home
    monkeypatch.setattr(home, "artifacts_required", lambda r, s: True)
    pills = _pills(run, store)
    assert pills.startswith("Records agree: yes · "), pills


def test_view_json_is_the_manifest_as_delivered(demo):  # noqa: F811
    run, store = demo
    found = re.search(r'<pre data-section="manifest">(.*?)</pre>', _receipt(run, store), re.S)
    assert found and unescape(found.group(1)) == (DEMO / "day-1" / "MANIFEST.json").read_text(
        encoding="utf-8")


def test_check_it_yourself_is_the_command_this_run_needs(demo):  # noqa: F811
    """The demo's day 1 carries a signature, so its check needs the crypto extra and a trust file,
    named in the onetrace-trust/0.1 format; and the page says the check makes no network calls --
    never "offline", the ruled wording."""
    run, store = demo
    assert any(p.startswith("signatures/") for p, _ in run.listing)
    found = re.search(r'<section data-section="check-yourself">(.*?)</section>',
                      _receipt(run, store), re.S).group(1)
    text = unescape(found)
    assert 'pip install "onetrace-verify[crypto]"' in text
    assert "onetrace-verify --require-artifacts --trust trust.json ." in text
    assert "onetrace-trust/0.1" in text
    assert "makes no network calls" in text and "no account" in text and "offline" not in text
    assert f'href="/runs/{run.key}/record.tar"' in found


def test_what_this_receipt_does_not_say_is_the_fixed_text(demo):  # noqa: F811
    run, store = demo
    found = re.search(r'<section data-section="does-not-say">(.*?)</section>',
                      _receipt(run, store), re.S).group(1)
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", whole_folds(found))))
    for line in ("that the output or the action was correct",
                 "why the model wrote what it wrote",
                 "that the signing key wasn't misused (your trust list is what ties a key to a name)",
                 "that the run was correct at the anchored time (the anchor shows only that the "
                 "record existed by then)"):
        assert line in text, line


def test_the_case_page_links_the_receipt(demo):  # noqa: F811
    run, store = demo
    pages = _pages(run, store)
    assert 'href="receipt.html"' in pages["case.html"] and "receipt.html" in pages
