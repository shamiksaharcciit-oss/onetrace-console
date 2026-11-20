"""Marking fields as noise (`noise`, `noise_pages`): a pipeline names fields of a step's JSON output that are noise, and a
comparison's first difference that matters skips a difference found only there. Nothing is hidden: the comparison says
which fields are marked and links the list; where the first difference moves, it shows both, the first difference with
the noise fields set aside and the first difference in the record, each linked; every step's verdict, the record's own
and `onetrace diff`'s stay as they are. An admin marks fields at `/pipelines/<label>/noise`; each change is an audit-log
entry; a public console reads them from its build and refuses changes.

The store is P12's four runs, delivered as the console takes them, with the comparisons the demo stores. Each run's
`read_invoice` says when it read the invoice (`read_at`), so the record's first difference between the good run and
the misread one is there, and with `read_at` marked noise it is `propose_payment`, where the model read 40.00 as
4,000.00.
"""

from __future__ import annotations

import json
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import replace
from html import unescape

import pytest

from onetrace_console import noise
from tests.http_limits import limit

GOOD, MISREAD = "pzz-66-invoice-agent-good", "pzz-67-invoice-agent-misread"
SECTION = re.compile(r'<section class="noise-first" data-section="noise".*?</section>', re.S)
STEPS = re.compile(r'<section class="step-cards" data-section="step-cards".*?</section>', re.S)


# ------------------------------------------------------------------------------------------------- the paths


@pytest.mark.parametrize(
    "path, refused",
    [
        ("read_at", None),
        ("meta.read_at", None),
        ("items.*.request_id", None),
        ("items.0.request_id", None),
        ("items.*.lines.*.id", "at most once"),
        ("$.read_at", "no $, / or brackets"),
        ("items[0].id", "no $, / or brackets"),
        ("meta..read_at", "no empty part"),
        ("meta.read*", "no empty part, space or other *"),
        ("", "names a field"),
    ],
)
def test_a_path_is_keys_and_one_star_for_an_array_index(path, refused, examined):
    got = noise.path_problem(path)
    assert (got is None) if refused is None else (refused in got), got
    examined(1, "path")


def test_a_difference_is_noise_only_where_every_place_lies_under_a_marked_path(examined):
    a = {"number": "INV-1", "read_at": "09:00", "items": [{"id": "r1", "n": 1}, {"id": "r2", "n": 2}]}
    b = {"number": "INV-1", "read_at": "09:05", "items": [{"id": "r9", "n": 1}, {"id": "r8", "n": 2}]}
    assert noise.only_noise(a, b, ["read_at", "items.*.id"])
    assert not noise.only_noise(a, b, ["read_at"]), "the items' ids differ outside the noise"
    assert not noise.only_noise(a, {**b, "number": "INV-2"}, ["read_at", "items.*.id"])
    assert not noise.only_noise(a, a, ["read_at"]), "no difference is no noise"
    assert noise.matches(a, "items.*.id") and noise.matches(a, "items.1.n") and not noise.matches(a, "meta.read_at")
    examined(5, "pairs and paths")


# ------------------------------------------------------------------------------------------------- the store


@pytest.fixture(scope="module")
def p12(tmp_path_factory):
    """P12's runs, recorded and delivered, and the demo's comparisons of them."""
    from onetrace_console import demo_store
    from onetrace_console.compare import compare
    from onetrace_console.config import Config
    from onetrace_console.demo_store import onedoor_demo
    from onetrace_console.folder_load import deliver_one
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed

    _require_installed()
    root = tmp_path_factory.mktemp("noise")
    runs = root / "runs"
    runs.mkdir()
    issuer = onedoor_demo.Issuer()
    specs = [s for s in demo_store.runs() if s.pipeline == "p12"]
    for spec in specs:
        demo_store._record(spec, runs / spec.folder, issuer)
    issuer.write_beside(runs)
    store = Store(root / "store")
    config = Config(sign_in={**Config().sign_in, "enabled": False})
    held = {}
    for spec in specs:
        got = deliver_one(runs / spec.folder, store, config)
        assert got.run is not None, got.refused
        held[spec.folder] = got.run
    compare(held[GOOD], held[MISREAD], store)
    return store, held


@pytest.fixture
def fresh(p12, tmp_path):
    """A copy of the store, its noise fields this test's own."""
    from onetrace_console.store import Store

    store, held = p12
    shutil.copytree(store.root, tmp_path / "store")
    return Store(tmp_path / "store"), held


def _pipeline(store):
    from onetrace_console.overview import pipelines

    [p] = pipelines(store)
    return p


def _page(store, held) -> str:
    from onetrace_console.render import render_diff

    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (held[GOOD].key, held[MISREAD].key))
    with store.reading():
        return render_diff(c, store, generated_at="2026-11-19T00:00:00Z")


def _first_card_stage(page: str) -> str:
    return re.search(r'<h2 data-section="headline">[^<]*<code>([^<]+)</code>', page).group(1)


def test_with_no_noise_set_the_comparison_is_as_before_and_names_no_noise(fresh, examined):
    store, held = fresh
    page = _page(store, held)
    assert 'data-section="noise"' not in page
    assert _first_card_stage(page) == "read_invoice", "the record's first difference: the invoice's read time"
    examined(1, "comparison page")


def test_noise_that_moves_the_first_difference_shows_both_each_linked(fresh, examined):
    store, held = fresh
    before = _page(store, held)
    noise.add(store, _pipeline(store), "read_invoice", "read_at")
    page = _page(store, held)
    [section] = SECTION.findall(page)
    said = unescape(re.sub(r"<[^>]+>", " ", section))
    said = " ".join(said.split())
    aside = re.search(r'data-noise="set-aside".*?<a href="#step-(\d+)"><code>([^<]+)</code>', section, re.S)
    record = re.search(r'data-noise="in-record".*?<a href="#step-(\d+)"><code>([^<]+)</code>', section, re.S)
    assert aside.group(2) == "propose_payment" and record.group(2) == "read_invoice"
    assert aside.group(1) != record.group(1)
    assert "The first difference, noise fields set aside" in said and "The first difference in the record" in said
    assert "read_invoice" in said and "read_at" in said, "which fields are marked"
    assert 'href="../pipelines/p1/noise"' in section, "the list, linked"
    assert noise.NOT_THE_RECORD in said
    #: Nothing is hidden: the record's first card and every step's verdict stay as they are.
    assert _first_card_stage(page) == "read_invoice"
    assert STEPS.findall(page) == STEPS.findall(before)
    examined(2, "first differences")


def test_noise_that_matches_nothing_is_said_and_moves_nothing(fresh, examined):
    from onetrace_console import noise_pages

    store, held = fresh
    p = _pipeline(store)
    noise.add(store, p, "read_invoice", "meta.request_id")
    page = _page(store, held)
    [section] = SECTION.findall(page)
    assert 'data-noise="set-aside"' not in section and "meta.request_id" in section
    assert _first_card_stage(page) == "read_invoice"
    listed = unescape(noise_pages.page(store, p, public=False))
    row = re.search(r'<tr data-noise-field="read_invoice meta\.request_id">.*?</tr>', listed, re.S).group(0)
    assert noise_pages.MATCHES_NOTHING in row
    examined(1, "field")


def test_a_difference_outside_the_noise_is_still_the_first(fresh, examined):
    store, held = fresh
    noise.add(store, _pipeline(store), "read_invoice", "vendor")
    page = _page(store, held)
    [section] = SECTION.findall(page)
    assert 'data-noise="set-aside"' not in section, "read_at differs, and it is not marked"
    assert _first_card_stage(page) == "read_invoice"
    examined(1, "comparison page")


def test_a_marked_field_is_kept_beside_the_pipeline_and_listed_with_what_it_matches(fresh, examined):
    from onetrace_console import noise_pages

    store, held = fresh
    p = _pipeline(store)
    noise.add(store, p, "read_invoice", "read_at")
    kept = json.loads((store.root / noise.FOLDER / f"{p.runs[0].declared_digest}.json").read_text(encoding="utf-8"))
    assert kept["fields"] == [{"step": "read_invoice", "path": "read_at"}] and kept["format"] == noise.FORMAT
    listed = unescape(noise_pages.page(store, p, public=False))
    row = re.search(r'<tr data-noise-field="read_invoice read_at">.*?</tr>', listed, re.S).group(0)
    assert noise_pages.MATCHES.format(n=4, m=4) in row
    with pytest.raises(noise.Refused, match="marked already"):
        noise.add(store, p, "read_invoice", "read_at")
    with pytest.raises(noise.Refused, match="not one of the pipeline's"):
        noise.add(store, p, "no_such_step", "read_at")
    examined(1, "field")


# ------------------------------------------------------------------------------------------------- the page, served


def _post(url: str, fields: dict) -> tuple[int, str]:
    req = urllib.request.Request(url, data=urllib.parse.urlencode(fields).encode(), method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=limit(30)) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


@pytest.fixture
def served(server, p12, monkeypatch, tmp_path):
    """The console, serving a copy of P12's store, with the audit log on."""
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler
    from onetrace_console.store import Store

    base, root = server
    store, held = p12
    shutil.copytree(store.root, root / "copy")
    monkeypatch.setattr(Handler, "store", Store(root / "copy"))
    log = AuditLog(tmp_path / "audit_log", head_location=tmp_path / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", Audit(log))
    return base, Handler.store, log


def test_an_admin_marks_and_removes_a_field_and_each_change_is_an_audit_entry(served, examined):
    base, store, log = served
    status, html = _get(base + "/pipelines/p1/noise")
    assert status == 200 and 'action="/noise"' in html
    status, html = _post(
        base + "/noise", {"pipeline": "p1", "action": "add", "step": "read_invoice", "path": "read_at"}
    )
    assert status == 200, html[:300]
    assert noise.read(store, _pipeline(store).runs[0].declared_digest) == [noise.Field("read_invoice", "read_at")]
    status, _ = _post(
        base + "/noise", {"pipeline": "p1", "action": "remove", "step": "read_invoice", "path": "read_at"}
    )
    assert status == 200
    assert noise.read(store, _pipeline(store).runs[0].declared_digest) == []
    entries = [e for e in log.entries() if e["event"] == "noise.changed"]
    assert [(e["object"], e["detail"]) for e in entries] == [
        ("p1", {"action": "add", "step": "read_invoice", "path": "read_at"}),
        ("p1", {"action": "remove", "step": "read_invoice", "path": "read_at"}),
    ]
    examined(len(entries), "audit entries")


def test_a_path_that_is_not_one_is_refused_and_nothing_is_written_or_recorded(served, examined):
    base, store, log = served
    status, html = _post(base + "/noise", {"pipeline": "p1", "action": "add", "step": "read_invoice", "path": "$.x"})
    assert status == 400 and "no $, / or brackets" in unescape(html)
    assert noise.read(store, _pipeline(store).runs[0].declared_digest) == []
    assert not [e for e in log.entries() if e["event"] == "noise.changed"]
    examined(1, "refused press")


def test_a_public_console_reads_the_fields_and_refuses_changes(served, monkeypatch, examined):
    from onetrace_console.serve import Handler

    base, store, _log = served
    noise.add(store, _pipeline(store), "read_invoice", "read_at")
    monkeypatch.setattr(Handler, "config", replace(Handler.config, public=True))
    status, html = _get(base + "/pipelines/p1/noise")
    assert status == 200 and "read_at" in html and "<form" not in html
    assert noise_said_public() in unescape(html)
    status, _ = _post(
        base + "/noise", {"pipeline": "p1", "action": "remove", "step": "read_invoice", "path": "read_at"}
    )
    assert status == 403
    assert noise.read(store, _pipeline(store).runs[0].declared_digest) == [noise.Field("read_invoice", "read_at")]
    examined(1, "public console")


def noise_said_public() -> str:
    from onetrace_console import noise_pages

    return noise_pages.PUBLIC


def test_the_demo_marks_p12_s_read_time_as_noise(examined):
    from onetrace_console import demo_store

    assert demo_store.NOISE == {"p12": (("read_invoice", "read_at"),)}
    examined(1, "pipeline")


def test_the_noise_page_s_fields_are_laid_out_as_the_forwarding_page_s(examined):
    """Each field of the add form on a line of its own, its label above it, as on the forwarding page: inline, the step's
    select and the path's label ran together."""
    from onetrace_console.frame import PAGE_CSS

    for rule in ("label.field{display:block", "label.field select{display:block"):
        found = [line for line in PAGE_CSS.splitlines() if "data-page=noise" in line and rule.split("{")[0] in line]
        assert found, rule
    examined(2, "rules")


def test_a_step_whose_settings_differ_is_not_set_aside_by_noise(fresh, examined):
    """A step is set aside only where everything the comparison reads at it is the same but a noise path. With
    `read_at` marked, `read_invoice`'s outputs differ only there; once its recorded settings differ too, it is still the
    first difference, and the noise section says the first difference doesn't move."""
    from onetrace_console import compare_view
    from onetrace_console.render import read_diff

    store, held = fresh
    noise.add(store, _pipeline(store), "read_invoice", "read_at")
    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (held[GOOD].key, held[MISREAD].key))
    with store.reading():
        report, annotations = read_diff(c, store)
        f = compare_view.facts(report, annotations, c, store)
        _pipeline_, fields = noise.fields_for(c, store)
        assert f.steps[f.first].stage == "read_invoice" and not f.annotations.get("read_invoice")
        moved = noise.first_that_matters(f, c, store, fields)
        f.annotations["read_invoice"] = {"assertions.constants.currency": ["EUR", "USD"]}
        kept = noise.first_that_matters(f, c, store, fields)
        section = compare_view.noise_section(f, c, store)
    examined(2, "first differences: settings the same, settings differing")
    assert f.steps[moved].stage == "propose_payment", "outputs differ only in read_at, settings the same: set aside"
    assert kept == f.first, "its settings differ, so it is not set aside"
    assert 'data-noise="not-moved"' in section and 'data-noise="set-aside"' not in section
