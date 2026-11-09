"""The CHANGELOG's known gaps for a release: what it does not do yet, said where a reader of the
release looks. Console 0.7.0: a run cut short by a kill keeps onetrace's `.lock`, so a folder load skips it,
and it reaches a folder-loaded console only by upload."""
from __future__ import annotations

import re

import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAP = ("A run killed while it records keeps onetrace's `.lock`, and a folder load skips a folder that holds one, "
       "as a run still being recorded. So a run cut short reaches a console that loads a folder only by upload "
       "(`POST /v1/runs`); a console it is uploaded to shows it as cut short.")


def _unreleased() -> str:
    """The 0.7.0 section: `## [Unreleased]` until its version was set."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.7.0]")
    return text[start:text.index("\n## [", start + 1)]


def test_the_release_lists_its_known_gaps_with_the_killed_run_s_lock(examined):
    section = _unreleased()
    examined(1, "unreleased section")
    gaps = section.split("\n### Known gaps\n", 1)
    assert len(gaps) == 2, "no Known gaps under 0.7.0"
    lines = [ln for ln in gaps[1].splitlines() if ln.startswith("- ")]
    assert any(" ".join(ln.split()).endswith(GAP) for ln in lines), lines
    #: A gap is not an entry: its line has no bold lead, so it asks for no README words.
    assert not any(re.match(r"- \*\*", ln) for ln in lines)


#: The two gaps 0.7.0 adds, worded to match the code: a session grants only viewer, and the gate runs no lint.
SIGN_IN_GAP = ("No identity provider. A signed-in person is always a viewer: the admin routes refuse every session. "
               "With sign-in off, as on a local console, no role is checked.")
#: The release date the 0.7.0 heading gives, as 0.6.1's gives its own.
RELEASED = "## [0.7.0] - 2026-11-09\n"
LINT_GAP = "Lint, format and type checks are not part of the release gate yet."


def _gap_lines() -> list[str]:
    return [" ".join(ln.split()) for ln in _unreleased().split("\n### Known gaps\n", 1)[1].splitlines()
            if ln.startswith("- ")]


@pytest.mark.parametrize("gap", [SIGN_IN_GAP, LINT_GAP])
def test_the_release_lists_the_sign_in_and_lint_gaps(gap, examined):
    lines = _gap_lines()
    examined(len(lines), "known gaps")
    assert any(ln == f"- {gap}" for ln in lines), lines


DESIGN_GAPS = REPO / "DESIGN_GAPS.md"


@pytest.mark.skipif(not DESIGN_GAPS.is_file(), reason="the public export leaves DESIGN_GAPS.md out")
def test_design_gaps_says_the_same_of_roles(examined):
    text = " ".join(DESIGN_GAPS.read_text(encoding="utf-8").split())
    examined(1, "DESIGN_GAPS.md")
    assert "there are no roles" not in text and SIGN_IN_GAP in text


def _entry(lead: str) -> str:
    found = [" ".join(ln.split()) for ln in _unreleased().splitlines() if ln.startswith(f"- **{lead}**")]
    assert len(found) == 1, (lead, found)
    return found[0]


def test_the_first_run_to_leave_gap_line_says_what_gap_why_does(examined):
    line = _entry("Each gap on the first-run-to-leave page gives its reason.")
    examined(1, "entry")
    assert ("the first of the kept check's rows, quoted whole, and how many more; a gap with no recorded reason "
            "says so") in line
    assert "Each says what would include the run." not in line


def test_the_install_line_names_the_readmes_that_give_it(examined):
    line = _entry("onetrace-explain 0.3 with its keyring extra, beside the console.")
    examined(1, "entry")
    assert "The READMEs" not in line and "`README.md`" in line and "`PYPI_DESCRIPTION.md`" in line
    for f in ("README.md", "PYPI_DESCRIPTION.md"):
        assert 'onetrace-explain[keyring]>=0.3' in (REPO / f).read_text(encoding="utf-8"), f


def test_the_tokenizer_zip_line_says_a_member_in_a_folder_is_taken_by_its_file_name(examined):
    line = _entry("A tokenizer from this machine.")
    examined(1, "entry")
    assert "a member in a folder is taken by its file name" in line and "a plain file name" not in line


def test_the_0_7_0_heading_is_released_and_dated(examined):
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    examined(1, "CHANGELOG.md")
    assert RELEASED in text and "## [0.7.0] (not released)" not in text
    assert text.index(RELEASED) < text.index("## [0.6.1] - 2026-11-06\n")


def test_the_old_roles_words_are_gone(examined):
    examined(2, "CHANGELOG.md and DESIGN_GAPS.md")
    for path in [REPO / "CHANGELOG.md"] + ([DESIGN_GAPS] if DESIGN_GAPS.is_file() else []):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "The admin role exists only for the command line" not in text, path.name
