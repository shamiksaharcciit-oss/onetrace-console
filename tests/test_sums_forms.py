"""`SHA256SUMS` in both of the forms `sha256sum` itself writes, and no other.

`sha256sum` writes `<64 hex><space><mode><path>`, where the mode is a space (text) or `*` (binary).
Git for Windows writes `*` by default, and the end-to-end check of 30 September was refused on
it: the parser took only the text form, though its own comment credited `sha256sum`. Both forms
are read; the `*` is the mode, never part of the path. Anything else is still refused, naming
the line.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from onetrace_console.ingest import DeliveryRefused, accept, check_sums, parse_sums
from tests.conftest import make_tar

REPO = Path(__file__).resolve().parent.parent
RUN = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"
SUMS = REPO / "tests" / "fixtures" / "sums"

#: The run folder's five files, and their sha256 as the committed r11 sums file records them.
EXPECTED = {
    line.split("  ", 1)[1]: line.split("  ", 1)[0]
    for line in (REPO / "tests" / "fixtures" / "r11" / "SHA256SUMS").read_text(
        encoding="utf-8").splitlines() if line.strip()
}


def _run_files() -> dict[str, bytes]:
    return {p.relative_to(RUN).as_posix(): p.read_bytes()
            for p in sorted(RUN.rglob("*")) if p.is_file()}


def test_the_two_files_are_the_two_forms_the_tool_wrote(examined):
    """Guards the fixtures themselves: one line per file, each in the form its name says."""
    default = SUMS.joinpath("default.SHA256SUMS").read_text(encoding="utf-8").splitlines()
    text = SUMS.joinpath("text.SHA256SUMS").read_text(encoding="utf-8").splitlines()
    examined(len(default) + len(text), "sums lines read")
    assert len(default) == len(text) == len(EXPECTED) == 5
    assert all(line[64:66] == " *" for line in default), default
    assert all(line[64:66] == "  " for line in text), text


@pytest.mark.parametrize("name", ["default.SHA256SUMS", "text.SHA256SUMS"])
def test_each_form_reads_as_the_same_paths_and_digests(name, examined):
    got = parse_sums(SUMS.joinpath(name).read_bytes())
    examined(len(got), f"entries read from {name}")
    assert got == EXPECTED, got
    assert not any(p.startswith("*") for p in got), "the mode was read as part of a path"


def test_a_file_mixing_both_forms_reads_as_one(examined):
    default = SUMS.joinpath("default.SHA256SUMS").read_text(encoding="utf-8").splitlines()
    text = SUMS.joinpath("text.SHA256SUMS").read_text(encoding="utf-8").splitlines()
    mixed = [d if i % 2 else t for i, (d, t) in enumerate(zip(default, text))]
    assert {line[64:66] for line in mixed} == {" *", "  "}
    got = parse_sums(("\n".join(mixed) + "\n").encode("utf-8"))
    examined(len(got), "entries read from a mixed file")
    assert got == EXPECTED, got


@pytest.mark.parametrize("name", ["default.SHA256SUMS", "text.SHA256SUMS"])
def test_a_delivery_carrying_either_form_is_stored(name, store, examined):
    """The whole route, not the parser alone: the run folder plus the tool's own sums file."""
    files = {**_run_files(), "SHA256SUMS": SUMS.joinpath(name).read_bytes()}
    assert check_sums(files) == [], check_sums(files)
    result = accept(make_tar(files), store)
    examined(1, f"delivery with {name}")
    assert result.__class__.__name__ == "Accepted", getattr(result, "rows", result)


GOOD = "c8eeb4970a8f18fcfa16483164a5a5c7f31f084066c18434a8fe66eb8ffeb350"

REFUSED = {
    "a doubled binary mode": f"{GOOD} **MANIFEST.json",
    "no mode after the digest": f"{GOOD} MANIFEST.json",
    "no separator at all": f"{GOOD}MANIFEST.json",
    "upper-case hex": f"{GOOD.upper()}  MANIFEST.json",
    "a tab for the separator": f"{GOOD}\t MANIFEST.json",
    "a digest one character short": f"{GOOD[:-1]}  MANIFEST.json",
    "a mode and no path": f"{GOOD} *",
}


@pytest.mark.parametrize("case", sorted(REFUSED))
def test_every_other_form_is_still_refused_naming_the_line(case, examined):
    line = REFUSED[case]
    examined(1, f"refused form: {case}")
    with pytest.raises(DeliveryRefused) as e:
        parse_sums((line + "\n").encode("utf-8"))
    said = "\n".join(e.value.rows)
    assert "SHA256SUMS" in said and repr(line) in said, said


# ---------------------------------------------- a path listed twice

_SECOND = "c8eeb4970a8f18fcfa16483164a5a5c7f31f084066c18434a8fe66eb8ffeb351"


@pytest.mark.parametrize("second", [GOOD, _SECOND], ids=["identical repeat", "conflicting repeat"])
@pytest.mark.parametrize("form", ["  ", " *"], ids=["text", "binary"])
def test_a_path_listed_twice_is_refused_naming_both_lines(second, form, examined):
    """Two lines for one path are a contradiction in the delivery, or at best a repeat no one can
    tell from one: the old parser let the last line win and ignored the digest the sender wrote."""
    first_line = f"{GOOD}{form}MANIFEST.json"
    second_line = f"{second}  MANIFEST.json"
    text = f"{first_line}\nfedcba98{'0' * 56}  other.json\n{second_line}\n"
    examined(1, "a SHA256SUMS listing one path twice")
    with pytest.raises(DeliveryRefused) as e:
        parse_sums(text.encode("utf-8"))
    said = "\n".join(e.value.rows)
    assert "SHA256SUMS" in said and "listed twice" in said, said
    assert repr(first_line) in said and repr(second_line) in said, said


def test_a_delivery_listing_a_path_twice_is_refused_whole(store, examined):
    files = _run_files()
    lines = SUMS.joinpath("text.SHA256SUMS").read_text(encoding="utf-8").splitlines()
    files["SHA256SUMS"] = ("\n".join(lines + [lines[0]]) + "\n").encode("utf-8")
    result = accept(make_tar(files), store)
    examined(1, "delivery with a repeated sums line")
    assert result.__class__.__name__ == "Rejection", result
    assert any("listed twice" in r for r in result.rows), result.rows


def test_the_onedoor_side_car_fixture_still_parses(examined):
    """The onedoor side-car shares the parser and so the rule (10-01cc §1); its committed files
    still read: both its SHA256SUMS and the export's own `.sha256`."""
    from onetrace_console.onedoor_ext import decisions
    assert decisions.parse_sums is parse_sums, "the side-car no longer shares the parser"
    onedoor = REPO / "tests" / "fixtures" / "onedoor"
    sums = parse_sums((onedoor / "SHA256SUMS").read_bytes())
    sidecar = parse_sums((onedoor / "onedoor-export.jsonl.sha256").read_bytes())
    examined(len(sums) + len(sidecar), "onedoor sums entries read")
    assert set(sums) == {p.name for p in onedoor.iterdir() if p.is_file() and p.name != "SHA256SUMS"}
    assert set(sidecar) == {"onedoor-export.jsonl"}
    assert sidecar["onedoor-export.jsonl"] == sums["onedoor-export.jsonl"]
