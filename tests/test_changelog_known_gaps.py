"""The CHANGELOG's known gaps for a release: what it does not do yet, said where a reader of the
release looks. Console 0.7.0: a run cut short by a kill keeps onetrace's `.lock`, so a folder load skips it,
and it reaches a folder-loaded console only by upload."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GAP = (
    "A run killed while it records keeps onetrace's `.lock`, and a folder load skips a folder that holds one, "
    "as a run still being recorded. So a run cut short reaches a console that loads a folder only by upload "
    "(`POST /v1/runs`); a console it is uploaded to shows it as cut short."
)


def _unreleased() -> str:
    """The 0.7.0 section: `## [Unreleased]` until its version was set."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.7.0]")
    return text[start : text.index("\n## [", start + 1)]


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
SIGN_IN_GAP = (
    "No identity provider. A signed-in person is always a viewer: the admin routes refuse every session. "
    "With sign-in off, as on a local console, no role is checked."
)
#: The release date the 0.7.0 heading gives, as 0.6.1's gives its own.
RELEASED = "## [0.7.0] - 2026-11-09\n"
LINT_GAP = "Lint, format and type checks are not part of the release gate yet."


def _gap_lines() -> list[str]:
    return [
        " ".join(ln.split())
        for ln in _unreleased().split("\n### Known gaps\n", 1)[1].splitlines()
        if ln.startswith("- ")
    ]


@pytest.mark.parametrize("gap", [SIGN_IN_GAP, LINT_GAP])
def test_the_release_lists_the_sign_in_and_lint_gaps(gap, examined):
    lines = _gap_lines()
    examined(len(lines), "known gaps")
    assert any(ln == f"- {gap}" for ln in lines), lines


#: The repository's own list of its design gaps, which the public export leaves out.
GAPS_LIST = REPO / "DESIGN_GAPS.md"


@pytest.mark.skipif(not GAPS_LIST.is_file(), reason="the public export leaves the list of design gaps out")
def test_design_gaps_says_the_same_of_roles(examined):
    """0.7.0's gap, said of local accounts; with Entra ID, the app roles (console 0.8.0)."""
    text = " ".join(GAPS_LIST.read_text(encoding="utf-8").split())
    examined(1, "the list of design gaps")
    assert "there are no roles" not in text and "No identity provider" not in text
    assert ROLES_GAP in text


#: The gaps list's words since sign-in through Microsoft Entra ID (console 0.8.0); 0.7.0's CHANGELOG keeps its own.
ROLES_GAP = (
    "With the console's own accounts, a signed-in person is always a viewer: the admin routes refuse every "
    "session. With sign-in through Microsoft Entra ID (`sign_in.method` `oidc`), Entra's app roles give each "
    "person viewer, investigator or admin, read at each sign-in. With sign-in off, as on a local console, no "
    "role is checked. Runs are not scoped to teams: every role reads every run."
)


def _entry(lead: str) -> str:
    found = [" ".join(ln.split()) for ln in _unreleased().splitlines() if ln.startswith(f"- **{lead}**")]
    assert len(found) == 1, (lead, found)
    return found[0]


def test_the_first_run_to_leave_gap_line_says_what_gap_why_does(examined):
    line = _entry("Each gap on the first-run-to-leave page gives its reason.")
    examined(1, "entry")
    assert (
        "the first of the kept check's rows, quoted whole, and how many more; a gap with no recorded reason says so"
    ) in line
    assert "Each says what would include the run." not in line


def test_the_install_line_names_the_readmes_that_give_it(examined):
    line = _entry("onetrace-explain 0.3 with its keyring extra, beside the console.")
    examined(1, "entry")
    assert "The READMEs" not in line and "`README.md`" in line and "`PYPI_DESCRIPTION.md`" in line
    for f in ("README.md", "PYPI_DESCRIPTION.md"):
        assert "onetrace-explain[keyring]>=0.3.2" in (REPO / f).read_text(encoding="utf-8"), f


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
    examined(2, "CHANGELOG.md and the list of design gaps")
    for path in [REPO / "CHANGELOG.md"] + ([GAPS_LIST] if GAPS_LIST.is_file() else []):
        text = " ".join(path.read_text(encoding="utf-8").split())
        assert "The admin role exists only for the command line" not in text, path.name


#: The gap the next release lists: section J's rows, which go to 0.9.0.
RECIPIENT_GAP = (
    "The recipient confirmation's rows (onetrace 0.8's section J) are not on a run's Authorization page yet: the "
    "page keeps room for them, and onetrace-verify's own rows about a recipient confirmation show where the console "
    "shows a check's rows."
)


def _next_release_gaps() -> list[str]:
    """The 0.8.0 section's known gaps (`## [Unreleased]` until its version was set), each line's words joined."""
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.8.0]")
    section = text[start : text.index("\n## [", start + 1)]
    parts = section.split("\n### Known gaps\n", 1)
    assert len(parts) == 2, "no Known gaps under the next release"
    return [" ".join(ln.split()) for ln in parts[1].splitlines() if ln.startswith("- ")]


def test_the_next_release_lists_the_recipient_confirmation_s_rows_as_a_known_gap(examined):
    lines = _next_release_gaps()
    examined(len(lines), "the next release's known gaps")
    assert f"- {RECIPIENT_GAP}" in lines, lines
    assert not any(re.match(r"- \*\*", ln) for ln in lines)


#: The access log's gap (read in console 0.7.0's public code): its head is kept on the same volume as its entries.
ACCESS_LOG_GAP = (
    "The access log shows an edit to its entries, not a cut tail: entries cut from its end, with `HEAD.json` "
    "rewritten to match, read as a whole chain, its head being kept on the same volume. Console 0.9's audit log "
    "keeps its head outside the volume."
)


def test_the_next_release_lists_the_access_log_s_cut_tail_as_a_known_gap(examined):
    lines = _next_release_gaps()
    examined(len(lines), "the next release's known gaps")
    assert f"- {ACCESS_LOG_GAP}" in lines, lines


def test_the_access_log_still_reads_a_cut_tail_with_its_head_rewritten_as_whole(tmp_path, examined):
    """What the gap says, held: an edit inside the chain is found, a cut tail with HEAD.json rewritten is not. When
    the access log finds that too, this fails, and the gap's line goes."""
    import json

    from onetrace_console.access_log import AccessLog, entry_digest

    log = AccessLog(tmp_path, 10_000)
    for i in range(5):
        log.append(principal="p", method="GET", path=f"/r{i}", status=200, now=f"2026-11-11T00:00:0{i}Z")
    segment = sorted(tmp_path.glob("*.jsonl"))[0]
    lines = segment.read_bytes().splitlines(True)
    edited = lines[:1] + [lines[1].replace(b"/r1", b"/rX")] + lines[2:]
    segment.write_bytes(b"".join(edited))
    examined(2, "a log edited, and a log cut with its head rewritten")
    assert AccessLog(tmp_path, 10_000).verify_chain()[0] is False, "an edit inside the chain is found"
    segment.write_bytes(b"".join(lines[:3]))
    head = json.loads((tmp_path / "HEAD.json").read_text(encoding="utf-8"))
    head.update(chain_head=entry_digest(json.loads(lines[2])), segment_size=len(b"".join(lines[:3])))
    (tmp_path / "HEAD.json").write_text(json.dumps(head), encoding="utf-8")
    assert AccessLog(tmp_path, 10_000).verify_chain() == (True, ""), "a cut tail with its head rewritten reads whole"
