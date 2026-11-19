"""Format 0.5's code version and a re-run's parts on a run's pages (`code_line`): "Code" on the case page (the commit,
short and whole, "uncommitted changes" where `dirty`, the lock file, "not recorded" where the run didn't ask, the
verifier's rows as it wrote them) and a re-run's head naming each part taken. Each present, absent, not observed and
failed by the verifier, on `tests/format_05_code/`."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

from tests.test_format_05_agents_runs import _verify
from tests.test_step_kinds import OLDER, _pages, _text

HERE = Path(__file__).resolve().parent / "format_05_code"
RECORDED = ("code-clean", "code-dirty")


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _code(pages: dict[str, str]) -> str:
    m = re.search(r'<section data-section="code">.*?</section>', pages["case.html"] + pages["proof.html"], re.S)
    return _text(m.group(0)) if m else ""


def _parts(pages: dict[str, str]) -> str:
    m = re.search(r'<p class="sub" data-section="rerun-parts".*?</p>', pages["proof.html"], re.S)
    return _text(m.group(0)) if m else ""


def test_every_file_is_the_one_its_provenance_names_and_each_run_verifies(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `((?:accept|reject)/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ("accept", "reject")
        for p in (HERE / d).rglob("*")
        if p.is_file()
    }
    made = json.loads((HERE / "MADE.json").read_text(encoding="utf-8"))
    examined(len(have) + 2, "vector files and recorded runs")
    assert have and have == said
    assert made["versions"]["onetrace"] == "0.8.0" and sorted(made["runs"]) == sorted(RECORDED)
    assert all(_verify(HERE / n) == (0, "PASS", []) for n in RECORDED)


def test_present_the_commit_the_lock_and_uncommitted_changes(tmp_path, examined):
    from onetrace_console.code_line import CLEAN, DIRTY, NON_CLAIMS
    from onetrace_console.step_kinds import prose

    commit = json.loads((HERE / "MADE.json").read_text(encoding="utf-8"))["commit"]
    clean = _pages(HERE / "code-clean", tmp_path / "c")
    dirty = _pages(HERE / "code-dirty", tmp_path / "d")
    examined(2, "a run with every tracked file committed, and one with a change")
    assert f"Commit: {commit[:12]} {commit}" in _code(clean) and CLEAN in _code(clean) and DIRTY not in _code(clean)
    assert DIRTY in _code(dirty) and "Lock file: requirements.txt sha256:" in _code(dirty)
    #: The verifier's rows as it wrote them, its NOT-RUN included, whatever its detail says.
    assert f"[PASS ] code -- commit {commit}" in _code(clean)
    assert "[NOT-RUN] the code matches its commit -- the repository was not given" in _code(clean)
    assert _text(prose(NON_CLAIMS)) in _code(clean)


def test_absent_not_recorded_not_observed_and_an_earlier_format(tmp_path, examined):
    from onetrace_console.code_line import NOT_RECORDED

    asked_not = _pages(HERE.parent / "format_05_state" / "state-kept", tmp_path / "n")
    unobserved = _pages(HERE / "accept" / "A80-code-not-observed", tmp_path / "u")
    older = _pages(OLDER, tmp_path / "o")
    examined(3, "a 0.5 run that didn't ask, one whose code is in no repository, and a 0.4 run")
    assert NOT_RECORDED in _code(asked_not)
    assert "Commit: not observed: the code file is not in a git repository" in _code(unobserved)
    assert not any('data-section="code"' in p or 'data-section="rerun-parts"' in p for p in older.values())


def test_a_re_run_s_head_names_each_part_taken_and_from_which_run(tmp_path, examined):
    from onetrace_console.code_line import PARTS_LEAD
    from onetrace_console.service_link import NOT_HELD

    pages = _pages(HERE / "accept" / "A77-code-of-lock-differs", tmp_path)
    examined(1, "a reproduce that took its code from another run")
    assert _parts(pages).startswith(f"{PARTS_LEAD}: code from vector-code-b ({NOT_HELD}) at 4e1f00000000")
    assert "the lock file differs: uv.lock sha256:7b593592" in _parts(pages)
    assert _parts(pages).endswith("environment: today")
    assert "[PASS ] re-run from -- code from vector-code-b at 4e1f00000000000000000000000000000000009b" in _code(pages)


def test_malformed_a_member_the_verifier_fails_is_not_drawn_its_row_is(tmp_path, examined):
    commit = _pages(HERE / "reject" / "R115-code-commit-out-of-form", tmp_path / "c")
    copy = _pages(HERE / "reject" / "R117-code-manifest-copy-differs", tmp_path / "m")
    parts = _pages(HERE / "reject" / "R110-rerun-from-disagrees", tmp_path / "p")
    examined(3, "a commit out of form, a manifest copy that differs, and receipts that disagree on their parts")
    assert "[FAIL ] code -- commit 'HEAD' is out of form" in _code(commit) and "Commit:" not in _code(commit)
    assert "[FAIL ] code -- the manifest's copy differs" in _code(copy) and "uncommitted" not in _code(copy)
    assert "[FAIL ] re-run from -- the receipts disagree on rerun_from" in _code(parts) and _parts(parts) == ""


def test_sabotage_a_page_that_draws_a_failed_commit_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import code_line

    monkeypatch.setattr(code_line, "failed", lambda rows, subject, names: [])
    commit = _pages(HERE / "reject" / "R115-code-commit-out-of-form", tmp_path)
    examined(1, "a run whose commit the verifier fails, drawn from anyway")
    assert "Commit: HEAD" in _code(commit)
