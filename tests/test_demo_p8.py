"""The demo's P8, invoice match, and the names of P8 and P9 on a public demo.

P8 is recorded by the demo's builder over an invented invoice, purchase order and goods receipt; it
pays nothing. Held here, on the public demo, each with a sabotage that the check names:

1. each run reads as its builder made it, in the console's own check: three whose records agree,
   and one declined at approve_payment by its own rule, the reason its own, no declared step left
   after it and no receipt for one;
2. each of its comparisons' first difference: the price tolerance changed, at match; one line's
   quantity changed, at read_invoice; and 42 -> 43's "Settings that changed" naming match's
   `price_tolerance`, 2.00% to 5.00%, as P3's `rules` is named;
3. its kept invoice is shown on the public demo (the demo's example-data exception, as P4's and
   P7's are), and only under the build record: one byte of it changed after the build, the record
   refuses the demo and the exception is off;
4. each pipeline's page on a public demo names it, P8 and P9 among them.

P9's runs and comparisons are held with the other physical-world pipelines in
tests/test_demo_physical.py; their sabotages are here.
"""
from __future__ import annotations

import html
import io
import json
import re
import shutil
import tarfile

import pytest

from tests.test_demo_physical import COMPARED, FIRMWARE, VS_BASELINE, firmware_problems

READINGS = {
    "p8-42-invoice-tolerance-2pct": ("Records agree", None),
    "p8-43-invoice-tolerance-5pct": ("Records agree", None),
    "p8-44-invoice-quantity-changed": ("Records agree", None),
    "p8-45-invoice-over-limit-declined": ("Records agree", ("approve_payment",
                                          "an invoice of 3840.00 is over the approver's limit of 2500.00")),
}
FIRST = {("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"): ("diverged", [
             ("read_invoice", "same"), ("match", "FIRST DIFFERENCE"), ("approve_payment", "downstream")]),
         ("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed"): ("diverged", [
             ("read_invoice", "FIRST DIFFERENCE"), ("match", "downstream"), ("approve_payment", "downstream")])}
P8_VS_BASELINE = {"p8-43-invoice-tolerance-5pct": ("changed", "First difference · stage 2 · match"),
                  "p8-44-invoice-quantity-changed": ("changed", "First difference · stage 1 · read_invoice")}
DECLINED = "p8-45-invoice-over-limit-declined"
KEPT_RUN = "p8-42-invoice-tolerance-2pct"


def _text(page: str) -> str:
    page = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


# ------------------------------------------------------------------ 1. the runs

def reading_problems(store, runs, table: dict) -> list[str]:
    """Each run's "Records agree" and its decline (step, reason), as the console reads them; the
    declined run with no declared step left after it and no receipt past its step."""
    from onetrace_console import records
    from onetrace_console.overview import declined
    out = []
    for name, (said, decline) in table.items():
        run = runs[name]
        d = declined(run)
        got = (records.said(run, store), (d["stage"], d["reason"]) if d else None)
        if got != (said, decline):
            out.append(f"{name} reads {got}")
        if d and d["left"]:
            out.append(f"{name} leaves {d['left']} unreached")
    return out


def test_each_p8_run_reads_as_its_builder_made_it(demo, examined):
    from onetrace_console.demo_store import invoice_match
    _folder, store, runs = demo
    examined(len(READINGS), "P8 runs")
    assert reading_problems(store, runs, READINGS) == []
    #: Declined at its last declared step: a receipt for each of the three, none past it.
    receipts = [p for p, _ in runs[DECLINED].listing if p.startswith("receipts/")]
    assert len(receipts) == len(invoice_match.STAGES) and invoice_match.STAGES[-1] == "approve_payment", receipts


def test_sabotage_the_declined_run_read_as_paid_is_named(demo, examined):
    _folder, store, runs = demo
    planted = {**READINGS, DECLINED: ("Records agree", None)}
    examined(1, "planted table")
    assert reading_problems(store, runs, planted) == [f"{DECLINED} reads ('Records agree', {READINGS[DECLINED][1]!r})"]


# ------------------------------------------------------------------ 2. the comparisons

def _comparison(store, runs, a, b):
    (found,) = [c for c in store.comparisons() if (c.run_a, c.run_b) == (runs[a].key, runs[b].key)]
    return found


def comparison_problems(store, runs, table: dict, vs: dict) -> list[str]:
    from onetrace_console.overview import vs_baseline
    out = []
    for pair, want in table.items():
        rep = json.loads(store.get(dict(_comparison(store, runs, *pair).verb("diff").reports)["diff.json"]))
        got = (rep["envelope"], [(r["stage"], r["verdict"]) for r in rep["ladder"]])
        if got != want:
            out.append(f"{pair[0]} -> {pair[1]}: {got}")
        if pair[1] in vs and vs_baseline(runs[pair[1]], store) != vs[pair[1]]:
            out.append(f"{pair[1]}'s vs baseline: {vs_baseline(runs[pair[1]], store)}")
    return out


def test_each_p8_comparison_finds_what_its_builder_changed(demo, examined):
    from onetrace_console.demo_store import COMPARISONS
    _folder, store, runs = demo
    examined(len(FIRST), "P8 comparisons")
    assert set(COMPARISONS) >= set(FIRST)
    assert comparison_problems(store, runs, FIRST, P8_VS_BASELINE) == []


def test_sabotage_a_first_difference_moved_is_named(demo, examined):
    """Each new pair with another first difference expected: P8's two, and P9's low-bolt run."""
    _folder, store, runs = demo
    planted = {**FIRST, ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"): ("diverged", [
        ("read_invoice", "FIRST DIFFERENCE"), ("match", "downstream"), ("approve_payment", "downstream")])}
    p9 = {k: v for k, v in COMPARED.items() if k[1].startswith("p9-")}
    assert len(p9) == 2
    p9[("p9-46-torque-baseline", "p9-48-torque-one-bolt-low")] = ("diverged", [
        ("read_tool_log", "same"), ("torque_check", "FIRST DIFFERENCE"), ("station_decision", "downstream")])
    examined(2, "planted tables")
    assert len(comparison_problems(store, runs, planted, P8_VS_BASELINE)) == 1
    assert len(comparison_problems(store, runs, p9, VS_BASELINE)) == 1


def test_sabotage_the_p9_firmware_setting_left_off_the_page_is_named(demo, examined):
    folder, store, runs = demo
    pair = ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed")
    page = _text((folder / "store" / "pages" / "diff" / f"{_comparison(store, runs, *pair).key}.html")
                 .read_text(encoding="utf-8"))
    examined(1, "planted page")
    assert firmware_problems(page, FIRMWARE[pair]) == []
    assert firmware_problems(page.replace("tool_firmware", "tool firmware"), FIRMWARE[pair]) != []


TOLERANCE = ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct")


def tolerance_problems(page: str) -> list[str]:
    """The tolerance pair's page: match's `price_tolerance` under "Settings that changed", both values."""
    section = page[page.index("Settings that changed"):] if "Settings that changed" in page else ""
    section = section.split("The text diff", 1)[0]
    return [] if "match price_tolerance 2.00% 5.00%" in section else ["no 'match price_tolerance 2.00% 5.00%' "
                                                                       "in Settings that changed"]


def _tolerance_page(folder, store, runs) -> str:
    return _text((folder / "store" / "pages" / "diff" / f"{_comparison(store, runs, *TOLERANCE).key}.html")
                 .read_text(encoding="utf-8"))


def test_the_tolerance_comparison_names_price_tolerance_with_both_values(demo, examined):
    folder, store, runs = demo
    examined(1, "comparison page")
    assert tolerance_problems(_tolerance_page(folder, store, runs)) == []


def test_sabotage_the_tolerance_left_as_a_fingerprint_only_is_named(demo, examined):
    folder, store, runs = demo
    page = _tolerance_page(folder, store, runs)
    examined(1, "planted page")
    assert tolerance_problems(page.replace("price_tolerance 2.00% 5.00%", "config_digest")) != []


# ------------------------------------------------------------------ 3. the kept invoice

def kept_problems(page: str) -> list[str]:
    from onetrace_console.demo_store import invoice_match
    out = [] if 'data-kept="shown"' in page else ["the invoice is not shown kept"]
    if json.loads(invoice_match.invoice_bytes("base")).splitlines()[3] not in html.unescape(page):
        out.append("the invoice's line is not on the page")
    return out + ([] if "invented example data" in _text(page) else ["the page does not say it is invented"])


def test_the_kept_invoice_is_shown_on_the_public_demo_under_its_build_record(demo, tmp_path, examined):
    from onetrace_console.demo_store import allowing_examples, check_build_record
    from onetrace_console.ingest import bundle
    folder, store, runs = demo
    page = (folder / "store" / "pages" / "runs" / runs[KEPT_RUN].key / "stage-1.html").read_text(encoding="utf-8")
    examined(2, "the kept invoice, the demo with one byte changed")
    assert kept_problems(page) == []
    copy = tmp_path / "demo"
    shutil.copytree(folder, copy)
    (kept,) = (copy / "runs" / KEPT_RUN / "inputs").rglob("*.json")
    kept.write_bytes(kept.read_bytes().replace(b"bracket", b"Bracket", 1))
    assert check_build_record(copy) == [f"{kept.relative_to(copy).as_posix()} was changed"]
    from onetrace_console.store import Store
    (run,) = [r for r in Store(copy / "store" / "store").runs() if r.run_id == KEPT_RUN]
    with allowing_examples(copy) as allowing:
        assert not allowing.allowed
        with tarfile.open(fileobj=io.BytesIO(bundle(run, Store(copy / "store" / "store"), public=True))) as tar:
            assert not any(m.startswith("inputs/") for m in tar.getnames())


def test_sabotage_the_invoice_not_shown_is_named(demo, examined):
    folder, _store, runs = demo
    page = (folder / "store" / "pages" / "runs" / runs[KEPT_RUN].key / "stage-1.html").read_text(encoding="utf-8")
    examined(1, "planted page")
    assert kept_problems(page.replace('data-kept="shown"', 'data-kept="withheld"')) != []


# ------------------------------------------------------------------ 4. the names

def name_problems(folder, store) -> list[str]:
    from onetrace_console.demo_store import name_of
    from onetrace_console.overview import pipelines
    out = []
    for p in pipelines(store):
        name = name_of([r.run_id for r in p.runs])
        page = _text((folder / "store" / "pages" / f"pipeline-{p.label.lower()}.html").read_text(encoding="utf-8"))
        if name is None or f"{p.label} · {name}" not in page:
            out.append(f"{p.label}'s page does not name {name}")
    return out


def test_each_pipeline_page_on_the_public_demo_names_its_pipeline(demo, examined):
    from onetrace_console.demo_store import PIPELINE_NAMES
    folder, store, _runs = demo
    examined(len(PIPELINE_NAMES), "pipeline pages")
    assert len(PIPELINE_NAMES) == 9 and PIPELINE_NAMES["p8"] == "invoice match"
    assert PIPELINE_NAMES["p9"] == "wheel-bolt torque check"
    assert name_problems(folder, store) == []


def test_sabotage_a_pipeline_named_wrong_is_named(demo, monkeypatch, examined):
    from onetrace_console import demo_store
    folder, store, _runs = demo
    monkeypatch.setitem(demo_store.PIPELINE_NAMES, "p8", "invoice matching")
    examined(1, "planted name")
    assert name_problems(folder, store) != []
