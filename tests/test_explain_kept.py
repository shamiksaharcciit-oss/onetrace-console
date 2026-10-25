"""Explanations a public console's build kept, shown read-only.

A public console presses nothing: it shows the explanations its build kept, the way it shows the
drift reports its build kept. The build takes them only as onetrace-explain's own records, from a
folder the builder names (the folder the command wrote `explain/` under), and keeps one only where
its record reads as the command wrote it and belongs to a comparison the build holds. Anything else
is refused with its reason, and never shown.

Test fixtures only: every explanation here is made by the command itself with a model of
`fake:PATH`, whose replies are kept under tests/fixtures/explain/, so no model is called and nothing
leaves this machine (tests/test_explain_panel.py). None goes into the demo.

Two stores hold the same two runs, byte for byte: the builder's, where the explanation is made,
and the build's, which keeps it. A third holds another pair, which the build does not hold.
"""
from __future__ import annotations

import json
import re
import shutil
from html import unescape
from pathlib import Path

import pytest

from tests.test_explain_panel import (LABEL, RAN_AT, _diff, _fake, _make, _panel, _text,
                                      explained_problems, tried)


def _store_of(made: list[Path], root: Path):
    """A store holding the runs in `made`, checked, and their comparison."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.store import Store
    from tests.test_compare import _deliver
    store = Store(root)
    a, b = (run_and_record(_deliver(f, store, outputs=True), store, ran_at=RAN_AT) for f in made)
    return store, compare(a, b, store)


@pytest.fixture
def kept(tmp_path, monkeypatch, explain_installed):
    """The builder's store, with one explanation made by the command; the build's store, holding
    the same runs; and the folder the command wrote `explain/` under, which the builder names."""
    from onetrace_console import explain
    from tests.test_checks import _require_installed
    _require_installed()
    made = _make(tmp_path / "made")
    builder, b_cmp = _store_of(made, tmp_path / "builder")
    build, cmp = _store_of(made, tmp_path / "build")
    config = tmp_path / "config" / "explain.toml"
    config.parent.mkdir()
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    _fake(config, "mixed.json")
    explain.explain(b_cmp, builder)
    source = explain.folder_of(builder, b_cmp.key) / explain.REPORT
    assert len(list((source / "explain").glob("*.explanation.json"))) == 1, tried(builder, b_cmp)
    return build, cmp, source


def _public_page(store, comparison) -> str:
    from onetrace_console.frame import rendering
    with rendering(onedoor=False, sign_in=False, public=True):
        return _diff(store, comparison)


def _local_page(store, comparison) -> str:
    from onetrace_console.frame import rendering
    with rendering(onedoor=False, sign_in=False, public=False):
        return _diff(store, comparison)


def read_only_problems(panel: str) -> list[str]:
    """What a public console's panel offers that computes or sends: any button, any press's
    address, the packet's offer."""
    out = []
    for b in re.findall(r"<button\b[^>]*>(.*?)</button>", panel, re.S):
        out.append(f"a button: {_text(b)!r}")
    for path in ("/explain?", "/explain/packet", "/explain/check"):
        if path in panel:
            out.append(f"a press's address: {path}")
    if "Show the packet" in panel:
        out.append("the packet is offered")
    return out


def refusals(record: dict) -> dict[str, str]:
    return {r["file"]: r["reason"] for r in record["refused"]}


# ------------------------------------------------------------------ kept and shown

def test_a_kept_explanation_is_shown_on_a_public_page_as_the_command_wrote_it(kept, examined):
    from onetrace_console import explain
    build, cmp, source = kept
    record = explain.keep(source, build)
    examined(1, "kept explanation")
    assert [k["comparison"] for k in record["kept"]] == [cmp.key] and record["refused"] == []
    panel = _panel(_public_page(build, cmp))
    assert explained_problems(panel) == [], panel
    assert read_only_problems(panel) == []
    assert f"<h3>{LABEL}</h3>" in unescape(panel)


def test_the_kept_record_is_in_the_build_s_store_and_reads_as_written(kept, examined):
    from onetrace_console import explain
    build, cmp, source = kept
    explain.keep(source, build)
    kept_at = explain.folder_of(build, cmp.key) / explain.REPORT / "explain"
    examined(1, "kept record")
    names = sorted(p.name for p in kept_at.iterdir())
    assert names == sorted(p.name for p in (source / "explain").iterdir())
    for p in (source / "explain").rglob("*"):
        if p.is_file():
            assert (kept_at / p.relative_to(source / "explain")).read_bytes() == p.read_bytes(), p
    rec = names[0]
    assert explain.verified(build, cmp.key, rec).endswith("(exit 0)")


def test_without_kept_explanations_the_public_page_reads_as_in_0_3_0(kept, examined):
    from onetrace_console import explain
    build, cmp, _ = kept
    examined(1, "public comparison page, nothing kept")
    panel = _panel(_public_page(build, cmp))
    assert _text(panel) == f"{explain.TITLE} {explain.NOT_SET_UP_DEMO}"


def test_a_comparison_with_none_kept_says_so_on_a_build_that_kept_some(kept, tmp_path, examined):
    """The build kept explanations, none of them of this comparison."""
    from onetrace_console import explain
    from onetrace_console.compare import compare
    build, cmp, source = kept
    explain.keep(source, build)
    other = compare(build.get_run(cmp.run_b), build.get_run(cmp.run_a), build)
    examined(1, "public comparison page, none of its own kept")
    panel = _panel(_public_page(build, other))
    assert _text(panel) == f"{explain.TITLE} {explain.KEPT_NONE}"


def test_the_local_console_is_unchanged_by_a_kept_explanation(kept, examined):
    """A local console's page is its own: Explain and the packet offered, as before."""
    from onetrace_console import explain
    build, cmp, source = kept
    before = _panel(_local_page(build, cmp))
    explain.keep(source, build)
    examined(1, "local comparison page")
    after = _panel(_local_page(build, cmp))
    assert "Show the packet" in before and "Show the packet" in after
    assert re.findall(r"<button\b[^>]*>([^<]*)</button>", after)[:2] == ["Explain", "Show the packet"]


# ------------------------------------------------------------------ refused, with the reason

def test_a_record_for_a_comparison_the_build_does_not_hold_is_refused(kept, tmp_path, examined):
    from onetrace_console import explain
    _, _, source = kept
    other, o_cmp = _store_of(_make(tmp_path / "other-made"), tmp_path / "other")
    record = explain.keep(source, other)
    examined(1, "foreign record")
    assert record["kept"] == []
    assert list(refusals(record).values()) == [explain.NOT_HELD]
    assert _text(_panel(_public_page(other, o_cmp))) == f"{explain.TITLE} {explain.KEPT_NONE}"


def _one_record(source: Path) -> Path:
    return next(p for p in (source / "explain").iterdir() if p.is_dir())


@pytest.mark.parametrize("edited", ["the model's reply", "a receipt", "the explanation's claims", "its model"])
def test_an_edited_record_is_refused(kept, edited, examined):
    from onetrace_console import explain
    build, cmp, source = kept
    rec = _one_record(source)
    side = rec.with_name(rec.name + ".explanation.json")
    if edited == "the model's reply":
        p = rec / "artifacts" / "02-model" / "reply.txt"
        p.write_bytes(p.read_bytes() + b" ")
    elif edited == "a receipt":
        p = rec / "receipts" / "03-post-check.json"
        p.write_bytes(p.read_bytes().replace(b'"post_check"', b'"post-check"', 1))
    else:
        e = json.loads(side.read_text(encoding="utf-8"))
        if edited == "the explanation's claims":
            e["claims"][0]["text"] = "The scorer is the culprit."
        else:
            e["model"] = "a model it was not"
        side.write_text(json.dumps(e, indent=1, sort_keys=True), encoding="utf-8")
    record = explain.keep(source, build)
    examined(1, f"record with {edited} edited")
    assert record["kept"] == []
    reason = refusals(record)[f"explain/{side.name}"]
    want = {"the model's reply": explain.NOT_VERIFIED, "a receipt": explain.NOT_VERIFIED,
            "the explanation's claims": explain.NOT_ITS_RECORD, "its model": explain.NOT_ITS_MODEL}[edited]
    assert reason.startswith(want), reason
    assert _text(_panel(_public_page(build, cmp))) == f"{explain.TITLE} {explain.KEPT_NONE}"


def test_a_file_that_is_not_the_command_s_is_refused_and_nothing_else_is_taken(kept, examined):
    from onetrace_console import explain
    build, cmp, source = kept
    (source / "explain" / "notes.txt").write_text("not the command's", encoding="utf-8")
    shutil.copytree(_one_record(source), source / "explain" / "2026-01-01T00-00-00.000000Z")
    record = explain.keep(source, build)
    examined(3, "files in the folder")
    assert len(record["kept"]) == 1
    assert refusals(record) == {"explain/notes.txt": explain.NOT_ITS_FILE,
                                "explain/2026-01-01T00-00-00.000000Z": explain.NO_EXPLANATION}


def test_a_folder_without_explain_is_refused_in_words(tmp_path, kept):
    from onetrace_console import explain
    build, _, _ = kept
    with pytest.raises(ValueError, match="holds no explain/ folder"):
        explain.keep(tmp_path, build)


# ------------------------------------------------------------------ sabotages

def test_sabotage_the_held_check_skipped_is_named(kept, tmp_path, monkeypatch, examined):
    """With the comparison check skipped, the foreign record is kept and shown: named."""
    from onetrace_console import explain
    _, _, source = kept
    other, o_cmp = _store_of(_make(tmp_path / "other-made"), tmp_path / "other")
    monkeypatch.setattr(explain, "_held_comparison", lambda held, rec: next(iter(held.values())))
    record = explain.keep(source, other)
    examined(1, "foreign record, the check skipped")
    assert record["kept"] != [] and refusals(record) == {}
    assert explained_problems(_panel(_public_page(other, o_cmp))) == []


def test_sabotage_the_verifier_skipped_is_named(kept, monkeypatch, examined):
    """With the verifier's reading skipped, an edited reply is kept: named."""
    from onetrace_console import explain
    build, _, source = kept
    p = _one_record(source) / "artifacts" / "02-model" / "reply.txt"
    p.write_bytes(p.read_bytes() + b" ")
    monkeypatch.setattr(explain, "_record_verifies", lambda folder: (True, "skipped"))
    record = explain.keep(source, build)
    examined(1, "edited record, the verifier skipped")
    assert record["kept"] != []


def test_sabotage_a_kept_explanation_with_a_button_is_named(kept, monkeypatch, examined):
    """A kept explanation drawn as the local console draws it offers Run: named."""
    from onetrace_console import explain
    build, cmp, source = kept
    explain.keep(source, build)
    real = explain._one
    monkeypatch.setattr(explain, "_one", lambda e, c, s, steps, read_only=False: real(e, c, s, steps))
    examined(1, "kept explanation with a button")
    assert read_only_problems(_panel(_public_page(build, cmp))) != []
