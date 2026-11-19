"""The recipient's confirmation on a run's Authorization page (`confirmations`): onetrace-verify's five rows quoted
as written, and each step's confirmation as the recipient's word, never as proof it acted. Present, absent and
failing, on onetrace 0.8.0's own vectors (`tests/format_05_vectors/`)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from tests.test_step_kinds import _pages, _text

VECTORS = Path(__file__).resolve().parent / "format_05_vectors"
MORE = VECTORS / "confirmations"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _section(folder: Path, tmp_path) -> str:
    page = _pages(folder, tmp_path)["authorization.html"]
    m = re.search(r'<section data-section="confirmations">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def _rows(section: str) -> dict[str, str]:
    return {
        _text(m.group(2)).split(" -- ")[0].split("] ", 1)[1]: m.group(1)
        for m in re.finditer(
            r'<li data-confirmation-row="([^"]+)">.*?<span class="mono" data-words="check">(.*?)</span>', section, re.S
        )
    }


def test_every_file_is_the_one_its_provenance_names(examined):
    said = {}
    for line in (MORE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `([^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(MORE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in MORE.rglob("*")
        if p.is_file() and p.name != "PROVENANCE.md"
    }
    examined(len(have), "files of the vectors")
    assert have and have == said


def test_present_each_confirmation_as_the_recipient_s_word_and_the_rows_as_written(tmp_path, examined):
    from onetrace_console.confirmations import LEAD, NON_CLAIMS
    from onetrace_console.step_kinds import prose

    section = _section(VECTORS / "A102-real-effected", tmp_path)
    examined(1, "the Authorization page of a run whose recipient confirmed it acted")
    assert LEAD in _text(section) and prose(NON_CLAIMS) in section
    step = _text(re.search(r'<li data-confirmation="approve_payment">.*?</li>', section, re.S).group(0))
    assert "the recipient returned sha256:bc293b3a" in step
    assert "kept at authorization/01-approve-payment/confirmation.jwt" in step
    assert "issuer https://issuer.example · id p-0001 · audience https://payments.example" in step
    assert _rows(section) == {
        "confirmation: request": "PASS",
        "confirmation: permit": "PASS",
        "confirmation: recipient key": "NOT-RUN",
        "confirmation: single use": "PASS",
        "confirmation: outcome": "PASS",
    }
    assert "no recipient list given (pass --recipients)" in _text(section)


def test_an_effect_unknown_reads_as_the_recipient_said_it(tmp_path, examined):
    section = _section(MORE / "A103-real-effect-unknown", tmp_path)
    examined(1, "a confirmation whose effect the recipient says is unknown")
    assert 'data-confirmation="approve_payment"' in section and "FAIL" not in set(_rows(section).values())


@pytest.mark.parametrize(
    ("name", "row", "said"),
    [
        ("R118-confirmation-c03", "confirmation: outcome", "reported ok, but the recipient says 'refused'"),
        ("R121-confirmation-c07", "confirmation: request", "the recipient confirmed a different request body"),
    ],
)
def test_failing_a_row_that_fails_withholds_every_confirmation_and_stands(name, row, said, tmp_path, examined):
    from onetrace_console.confirmations import WITHHELD

    section = _section(MORE / name, tmp_path)
    examined(1, f"{name}'s Authorization page")
    assert _rows(section)[row] == "FAIL" and said in _text(section)
    assert WITHHELD in _text(section) and "data-confirmation=" not in section


def test_a_key_failure_the_console_cannot_see_reads_not_run_beside_the_warning(tmp_path, examined):
    """R119 FAILs only with `--recipients`, which the console does not give: the key row reads NOT-RUN, and the page
    carries format.md's words on a PASS beside a Key NOT-RUN."""
    section = _section(MORE / "R119-confirmation-c04", tmp_path)
    examined(1, "a confirmation that does not verify under the recipient's listed key")
    assert _rows(section)["confirmation: recipient key"] == "NOT-RUN"
    assert (
        "a Request or Permit PASS beside a Key FAIL or NOT-RUN is a match with an unauthenticated statement"
        in _text(section)
    )


def test_absent_a_run_with_no_confirmation_gets_no_section(tmp_path, examined):
    examined(1, "a format 0.5 run with no permit presented")
    assert _section(VECTORS.parent / "format_05_state" / "state-kept", tmp_path) == ""


def test_sabotage_a_page_that_draws_a_failed_confirmation_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import confirmations

    real = confirmations.section
    monkeypatch.setattr(
        confirmations, "section", lambda steps, rows: real(steps, [r for r in rows if r.get("result") != "FAIL"])
    )
    section = _section(MORE / "R118-confirmation-c03", tmp_path)
    examined(1, "a page drawn with the FAIL row left out")
    assert 'data-confirmation="approve_payment"' in section
