""""Signed by a known recorder" on the console's other surfaces -- the receipt's
Signature row and "Signed" pill, the stage page's signing badge (§6), and the Overview's row (§5) --
each the run page's own rung, read from this console's own check of a run the SDK really signed
(tests/test_signed_run.py's fixture: the demo pipeline, a test-only key made outside the run).
"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import replace
from html import unescape

import pytest

from onetrace_console.home import SIGNATURE_FORMS, tallies
from tests.test_signed_run import _checked, _signed_rung, _trust, signed  # noqa: F401
from tests.test_receipt_page import _pills, _receipt, _row
from tests.test_stage_pages import _pages

UNTRUSTED = "Signed, key not trusted"


def _cells(row: str) -> list[str]:
    return [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", c))).strip()
            for c in re.findall(r"<td>(.*?)</td>", row, re.S)]


def _badge(run, store) -> str:
    """The signing badge, "question · state · evidence"; the same on every stage page."""
    said = set()
    for name, page in _pages(run, store).items():
        if name.startswith("stage-"):
            row = re.search(r'<tr data-badge="1"[^>]*>(.*?)</tr>', page, re.S).group(1)
            said.add(" · ".join(_cells(row)))
    assert len(said) == 1, said
    return said.pop()


def _surfaces(run, store) -> tuple[str, str, str, str]:
    """(the run page's rung words, the receipt's row, the receipt's pill, the stage badge)."""
    _state, rung = _signed_rung(run, store)
    pill = re.search(r"Signed: (.*?) ·", _pills(run, store)).group(1)
    return rung, _row(_receipt(run, store), "signature"), pill, _badge(run, store)


def test_an_untrusted_signature_on_every_surface(signed, tmp_path):
    run, store = _checked(signed, tmp_path)
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == f"{UNTRUSTED} · {signed[1]}"
    assert row == f"Signature {rung}" and pill == UNTRUSTED
    assert badge == f"Signed by a known recorder · {rung}"


def test_a_trusted_signature_on_every_surface_with_the_label_as_given(signed, tmp_path):
    trust = _trust(tmp_path, signed[1], "test key (demo)")
    run, store = _checked(signed, tmp_path, trust_file=str(trust))
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == f"Yes · test key (demo) · {signed[1]}", "the label as given, no suffix"
    assert row == f"Signature {rung}" and pill == "Yes"
    assert badge == f"Signed by a known recorder · {rung}"


def test_a_signature_that_does_not_verify_is_no(signed, tmp_path):
    folder, key_id, sig = signed
    record = json.loads(sig)
    raw = bytearray(base64.b64decode(record["signature"]))
    raw[0] ^= 1
    record["signature"] = base64.b64encode(bytes(raw)).decode("ascii")
    run, store = _checked((folder, key_id, json.dumps(record).encode("utf-8")), tmp_path)
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == "No · the signature doesn't match this record"
    assert (row, pill, badge) == (f"Signature {rung}", "No", f"Signed by a known recorder · {rung}")


def test_an_unsigned_run_on_every_surface(signed, tmp_path):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_reference_demo import _delivery
    store = Store(tmp_path / "store")
    run = run_and_record(accept(_delivery(signed[0]), store).run, store, ran_at=FIXED_RAN_AT)
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == "Unsigned · no signature beside the chain"
    assert (row, pill, badge) == (f"Signature {rung}", "Unsigned", f"Signed by a known recorder · {rung}")


def _signature_row_as_alg_not_run(run, store):
    """The stored check with its one SIGNED-UNTRUSTED row made NOT-RUN for an alg the verifier
    doesn't implement -- text, --json and the lines after the summary moved together."""
    from tests.test_step3_receipt_anchor import _read_by_the_viewer
    from onetrace_console.viewer.report import BESIDE_NOT_RUN_NOTE, UNTRUSTED_NOTE
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    reason = "alg rsa is not implemented by this verifier"
    out = re.sub(r"^\[SIGNED-UNTRUSTED\] signatures/1\.json: signature -- .*$",
                 f"[NOT-RUN] signatures/1.json: signature -- {reason}", envelope["stdout"], flags=re.M)
    summary = re.search(r"^(\d+) pass, (\d+) fail, (\d+) not-run  ->  (\S+)$", out, re.M)
    p, f, n = (int(summary.group(i)) for i in (1, 2, 3))
    out = out.replace(summary.group(0), f"{p} pass, {f} fail, {n + 1} not-run  ->  {summary.group(4)}")
    out = out.replace(f"records beside the chain: 1 signed by an untrusted key -- {UNTRUSTED_NOTE}\n",
                      "")
    if "not run -- " not in out:
        out = out.replace(f"{p} pass, {f} fail, {n + 1} not-run  ->  {summary.group(4)}\n",
                          f"{p} pass, {f} fail, {n + 1} not-run  ->  {summary.group(4)}\n"
                          f"records beside the chain: 1 not run -- {BESIDE_NOT_RUN_NOTE}\n")
    envelope["stdout"] = out
    doc = json.loads(envelope["rows_json"]["stdout"])
    (row,) = [r for r in doc["rows"] if r["name"] == "signatures/1.json: signature"]
    row["result"], row["detail"] = "NOT-RUN", reason
    doc["summary"]["not_run"] = n + 1
    envelope["rows_json"]["stdout"] = json.dumps(doc, indent=2, sort_keys=True) + "\n"
    _read_by_the_viewer(envelope)
    return replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))


def test_a_signature_the_check_could_not_settle_is_couldnt_check_with_its_reason(signed, tmp_path):
    run, store = _checked(signed, tmp_path)
    run = _signature_row_as_alg_not_run(run, store)
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == "Couldn't check · alg rsa is not implemented by this verifier"
    assert (row, pill, badge) == (f"Signature {rung}", "Couldn't check",
                                  f"Signed by a known recorder · {rung}")


def test_without_an_own_check_the_page_reads_it_is_not_checked(signed, tmp_path):
    run, store = _checked(signed, tmp_path)
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    envelope["stdout"] += "forged: a line after the summary\n"
    run = replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")))
    rung, row, pill, badge = _surfaces(run, store)
    assert rung == "Not checked · a signature is read only from this page's own check"
    assert (row, pill, badge) == (f"Signature {rung}", "Not checked",
                                  f"Signed by a known recorder · {rung}")


# ---------------------------------------------------------------- §5: the Overview's row

@pytest.fixture
def mixed(store):
    """One stored run per signing reading, and one the check runner has not reached."""
    from onetrace_console.checks import run_and_record
    from tests.test_compare import _require_exam
    from tests.test_home_and_diff import RUN_C, _deliver, _fake_run
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    _require_installed()
    _require_exam()
    real = run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    assert real.signed == "unsigned", "the premise: the exam run has no signature"
    for run_id, reading in (("s-yes", "yes"), ("s-untrusted", "untrusted"), ("s-failed", "failed"),
                            ("s-cc", "couldnt-check"), ("s-unreadable", "unreadable"),
                            ("s-extra", "not-installed")):
        made = _fake_run(store, real, run_id=run_id, verdict=real.check_verdict, note=real.check_note)
        store.put_run(replace(made, signed=reading))
    _fake_run(store, real, run_id="unchecked-1", verdict="")
    assert len(store.runs()) == 8 and not store.unreadable_runs
    return store


def _overview_row(store) -> tuple[str, str]:
    from onetrace_console.render import HOME, render_all
    from tests.test_overview import _section, _text
    from tests.test_pages import GENERATED_AT
    section = _section(render_all(store, generated_at=GENERATED_AT)[HOME], "evidence")
    found = re.search(r'<tr data-rung="signed">(.*?)</tr>', section, re.S)
    return _text(found.group(1)).strip(), found.group(1)


def test_the_overview_counts_each_form_as_each_runs_page_reads_it(mixed, examined):
    store = mixed
    examined(len(store.runs()), "runs counted")
    said, markup = _overview_row(store)
    assert said == ("Signed by a known recorder? 1 yes · 1 key not trusted · 1 the check failed · "
                    "1 unsigned · 2 couldn't check · 2 not checked"), said
    for slug, _r, _w in SIGNATURE_FORMS:
        assert f'href="executions-signed-{slug}.html"' in markup, slug


def test_the_overview_leaves_out_a_form_at_zero_and_counts_over_all_runs(mixed):
    store = mixed
    t = {x.slug: x for x in tallies(store)}
    total = len(store.runs())
    for slug, _r, _w in SIGNATURE_FORMS:
        assert t[f"signed-{slug}"].denominator == total, slug
    assert sum(t[f"signed-{slug}"].count for slug, _r, _w in SIGNATURE_FORMS) == total
    yes = next(r for r in store.runs() if r.signed == "yes")
    store.put_run(replace(yes, signed="unsigned"))
    said, _ = _overview_row(store)
    assert " yes" not in said.split("? ", 1)[1] and "2 unsigned" in said, said
