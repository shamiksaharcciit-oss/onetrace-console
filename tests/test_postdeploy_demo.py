"""`deploy/fly/postdeploy_080.ps1`: the demo's checks after its deploy, with the line to the capture store's app (round
fb, part 4).

0.7.0's checks (its release kit's `postdeploy_070.ps1`), the version they name now a parameter, and one more: where
-Captures names the capture store's address, the comparisons page's line to it, "Token-level examples (L2 and L3):
<address>"; without it, that check is skipped, not failed. Read here, not run: no PowerShell on this machine.
"""

from __future__ import annotations

import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "fly" / "postdeploy_080.ps1"


def test_the_link_line_is_checked_only_where_its_address_is_given(examined):
    text = SCRIPT.read_text(encoding="utf-8")
    examined(1, "the script")
    assert re.search(r'\[string\]\$Captures = ""', text)
    check = text[text.index("if ($Captures) {") :]
    assert 'Check "C1 /comparisons.html has its line to the token-level examples"' in check
    assert '[regex]::Escape("Token-level examples (L2 and L3): <a href=`"$($Captures.TrimEnd(\'/\'))")' in check
    assert 'Skip "C1 /comparisons.html has its line to the token-level examples" "no -Captures given"' in check


def test_the_version_it_checks_is_its_parameter_and_0_7_0_s_checks_stay(examined):
    text = SCRIPT.read_text(encoding="utf-8")
    names = re.findall(r'Check "([AB]\d+) ', text)
    examined(len(names), "carried checks")
    assert '[string]$Version = "0.8.0"' in text and 'Check "A3 / names onetrace-console $Version"' in text
    #: B12, console 0.8.0's check of the kept runs recorded again: P1's run shows its kept input's text.
    assert names == [f"A{i}" for i in range(1, 11)] + [f"B{i}" for i in range(1, 13)]


def _statements(text: str) -> dict[str, str]:
    """{check name: its whole statement}, a statement running on while its next line is indented."""
    out = {}
    for m in re.finditer(r'^Check "([AB]\d+) .*?(?=^\S)', text + "\n#", re.M | re.S):
        out[m.group(1)] = m.group(0)
    return out


def test_its_counts_are_read_from_the_deployed_build_s_record_never_typed_in(examined):
    """The comparisons (A8), the kept explanations (A9, B1, B2) and the closed and not closed runs (B7) are
    counted from the build record of the build deployed (`-BuildRecord`); none of those checks compares with
    a count written in the script."""
    text = SCRIPT.read_text(encoding="utf-8")
    checks = _statements(text)
    examined(len(checks) + 5, "checks, the parameter and the four counts")
    assert re.search(r"\[Parameter\(Mandatory = \$true\)\]\[string\]\$BuildRecord", text)
    #: Each count from the record: directly, or from its runs and their close receipts, read from it.
    for name in ("$runIds", "$closedIds", "$expectComparisons", "$expectKept"):
        assert re.search(rf"^\{name} = .*\$recorded", text, re.M), name
    for name in ("$expectClosed", "$expectNotClosed"):
        assert re.search(rf"^\{name} = .*\$runIds .*\$closedIds", text, re.M), name
    #: The five that compare with a count: none compares with one written here (zero, an HTTP status aside).
    counted = ("A8", "A9", "B1", "B2", "B7")
    typed = {n: checks[n] for n in counted if re.search(r"-(?:eq|ge|gt|lt) (?!0\b|200\b|403\b|404\b)\d+", checks[n])}
    assert typed == {}, typed
    for n in ("A8", "A9", "B1", "B2", "B7"):
        assert "$expect" in checks[n], n


def test_b12_reads_p1_s_kept_input_text_and_its_example_data_label(examined):
    import html

    from onetrace_console.kept_inputs import EXAMPLE_RECORD

    text = SCRIPT.read_text(encoding="utf-8")
    examined(5, "the run found, its step page, the text shown, the label, the check")
    assert 'data-run="p1-02-baseline-set2" data-key="([0-9a-f]{64})"' in text
    assert "stage-1.html" in text and 'data-kept="shown"' in text and "<pre data-kept-text>" in text
    #: As the receipt page writes it: escaped, its apostrophes as &#x27;.
    assert html.escape(EXAMPLE_RECORD, quote=True) in text
    assert "B12" in _statements(text)
