"""onetrace-verify's own lines on what format 0.5's members do not show (`verifier_notes`), drawn as a list inside the
section of the page each concerns, in the verifier's words, from the run's stored check; never composed, and not drawn
where the check printed none."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_step_kinds import OLDER, _pages, _text

TESTS = Path(__file__).resolve().parent


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _list(page: str, key: str) -> str:
    m = re.search(rf'<div class="note" data-verifier-non-claims="{key}">.*?</ul></div>', page, re.S)
    return _text(m.group(0)) if m else ""


def _in_section(page: str, section: str, key: str) -> bool:
    m = re.search(rf'<section data-section="{section}">.*?</section>', page, re.S)
    return bool(m) and f'data-verifier-non-claims="{key}"' in m.group(0)


def test_the_verifier_s_lines_are_read_as_it_printed_them(examined):
    from onetrace_console.verifier_notes import TOPICS, of_text

    run = TESTS / "format_05_state" / "state-kept"
    out = subprocess.run(
        [sys.executable, "-m", "onetrace_verify.cli", "MANIFEST.json"], cwd=run, capture_output=True, text=True
    ).stdout
    notes = of_text(out)
    line = next(ln for ln in out.splitlines() if ln.startswith(TOPICS["store"] + ": "))
    examined(len(notes), "topics the check printed")
    assert sorted(notes) == ["kinds", "store"]
    assert "; ".join(notes["store"]) == line[len(TOPICS["store"]) + 2 :]


def test_each_section_carries_its_topic_s_list_in_the_verifier_s_words(tmp_path, examined):
    state = _pages(TESTS / "format_05_state" / "state-kept", tmp_path / "s")
    agents = _pages(TESTS / "format_05_agents" / "agents-kept", tmp_path / "a")
    code = _pages(TESTS / "format_05_code" / "code-dirty", tmp_path / "c")
    stopped = _pages(TESTS / "format_05_expect" / "expect-stop", tmp_path / "e")
    recovered = _pages(TESTS / "onetrace_runs" / "0.8.0" / "refund-killed", tmp_path / "r")
    examined(6, "sections that carry the verifier's lines")
    assert _in_section(state["stage-2.html"], "store-state", "store")
    assert "a store reached without a hook or a declaration" in _list(state["stage-2.html"], "store")
    assert _in_section(agents["stage-2.html"], "step-kind", "kinds")
    assert _in_section(agents["stage-2.html"], "messages", "messages")
    assert _in_section(code["case.html"] + code["proof.html"], "code", "code")
    assert 'data-verifier-non-claims="expect"' in stopped["case.html"] + stopped["proof.html"]
    assert _in_section(recovered["case.html"] + recovered["proof.html"], "recovery", "recovery")


def test_the_link_sections_carry_the_link_s_list(tmp_path, examined):
    from tests.test_service_link import HERE, _drawn, _store

    store, keys = _store(tmp_path, {n: HERE / n for n in ("link-desk", "link-billing")})
    examined(2, "the callee's case page and the caller's step page")
    assert _in_section(_drawn(store, keys["link-billing"])["case.html"], "called-by", "link")
    assert _in_section(_drawn(store, keys["link-desk"])["stage-2.html"], "calls", "link")


def test_absent_a_run_whose_check_printed_none_gets_no_list(tmp_path, examined):
    older = _pages(OLDER, tmp_path / "o")
    closed = _pages(TESTS / "onetrace_runs" / "0.8.0" / "refund-closed", tmp_path / "c")
    examined(2, "a format 0.4 run, and a 0.5 run that closed itself")
    assert not any("data-verifier-non-claims" in p for p in older.values())
    assert not any('data-section="recovery"' in p for p in closed.values())


def test_sabotage_a_page_that_composes_its_own_lines_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import verifier_notes

    monkeypatch.setattr(verifier_notes, "of_envelope", lambda envelope: {})
    state = _pages(TESTS / "format_05_state" / "state-kept", tmp_path)
    examined(1, "a step page drawn with no lines read from the check")
    assert "data-verifier-non-claims" not in state["stage-2.html"]
