"""`deploy/fly/captures/postdeploy_080_captures.ps1`: the capture store's app checked after its deploy (round fb, part 4).

Read here, not run: no PowerShell on this machine; the operator runs it after `fly deploy`. Its checks are the ones
the app needs: /health; its two comparisons answer and show the token-level section; a capture step shows close
calls; the public scan's words hold, with the verifier's own row for a model call's engine setting allowed and nothing else; a write is
refused; the read-only banner; and, where the demo's address is given, the Overview's line back to it. Each
request goes over a connection of its own, and every page is asked for once before any check. The scan's words are
carried as their sha256 alone, the same words `tests/test_ux_screens.py` refuses.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "fly" / "captures" / "postdeploy_080_captures.ps1"


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def _scan_words() -> tuple[set[str], set[str]]:
    """The scan's refused words, by sha256: (case kept, case blind), from its own patterns."""
    from tests.test_ux_screens import NOT_ON_A_PAGE

    kept, blind = set(), set()
    for pattern in NOT_ON_A_PAGE.values():
        m = re.fullmatch(r"\\b([A-Za-z]+)\\b", pattern.pattern) or re.fullmatch(r"([a-z]+)\(\?!.*\)", pattern.pattern)
        if not m:
            continue
        word = m.group(1)
        if pattern.flags & re.I:
            blind.add(hashlib.sha256(word.lower().encode()).hexdigest())
        else:
            kept.add(hashlib.sha256(word.encode()).hexdigest())
    return kept, blind


def test_it_carries_the_scan_s_words_by_their_hashes_and_no_word_itself(examined):
    from tests.test_ux_screens import NOT_ON_A_PAGE

    text = _text()
    kept, blind = _scan_words()
    block = lambda name: set(re.findall(r'"([0-9a-f]{64})"', text[text.index(f"${name} = @(") :].split(")", 1)[0]))  # noqa: E731
    examined(len(kept) + len(blind), "refused words")
    assert len(kept) == 3 and len(blind) == 2
    assert block("CaseKept") == kept and block("CaseBlind") == blind
    #: The verifier's own row label is the one word allowed, as the scan allows it.
    plain = text.replace("engine core", "")
    assert [n for n, p in NOT_ON_A_PAGE.items() if p.search(plain)] == []


def test_every_request_has_its_own_connection_and_a_warm_up_comes_first(examined):
    text = _text()
    get_page = text[text.index("function Get-Page") : text.index("function Check")]
    examined(1, "the script")
    assert text.count("HttpClient]::new()") == 1 and "HttpClient]::new()" in get_page
    assert "$req.Headers.ConnectionClose = $true" in get_page and "$client.Dispose()" in get_page
    first_check = text.index('\nCheck "C1')
    assert text.rindex("$null = Get-Page", 0, first_check) > text.index("# The warm-up pass")


def test_it_runs_the_checks_the_app_needs(examined):
    names = re.findall(r'(?:Check|Skip) "(C\d) ([^"]*)"', _text())
    examined(len(names), "checks")
    said = dict(names)
    assert sorted(said) == ["C1", "C2", "C3", "C4", "C5", "C6", "C7"], names
    assert "/health" in said["C1"] and "token-level section" in said["C2"] and "close calls" in said["C3"]
    assert "scan" in said["C4"] and "write is refused" in said["C5"] and "back to the demo" in said["C7"]
    assert 'data-section="token-levels"' in _text() and "data-close-calls" in _text()
