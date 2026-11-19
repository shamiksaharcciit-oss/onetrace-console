"""`deploy/fly/captures/postdeploy_080_captures.ps1`: the capture store's app checked after its deploy (round fb, part 4).

Read here, not run: no PowerShell on this machine; the operator runs it after `fly deploy`. Its checks are the ones
the app needs: /health; its two comparisons answer and show the token-level section; a capture step shows close
calls; the public scan's words hold, with the verifier's own row for a model call's engine setting allowed and nothing
else; a write is refused; the read-only banner, with its sentence on what the store holds; and, where the demo's
address is given, the Overview's line back to it. Each request goes over a connection of its own, and every page is
asked for once before any check. The scan's words are
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


def _field_allowance() -> str:
    """The script's allowance for the model-call record's engine-setting field name: its pattern, as written."""
    words_seen = _text()[_text().index("function Words-Seen") :]
    found = re.findall(r"\$t = \[regex\]::Replace\(\$t, '([^']*engine_core[^']*)', ' '\)", words_seen)
    assert len(found) == 1, found
    return found[0]


def test_it_allows_the_record_s_field_name_for_the_engine_setting_as_the_scan_does(examined):
    from tests.test_ux_screens import ENGINE_CORE_FIELD, FIELD_PAGE, REVIEW_WORD, split_words

    text = _text()
    words_seen = text[text.index("function Words-Seen") : text.index("\n}\n", text.index("function Words-Seen"))]
    examined(1, "the script's word check")
    #: The same pattern as the scan's, after the tags are out and before the words are split.
    assert _field_allowance() == ENGINE_CORE_FIELD.pattern
    assert words_seen.index("'<[^>]+>', ' ')") < words_seen.index(_field_allowance()) < words_seen.index("-split")
    #: The script's own steps, tags out, then its allowance, then its split: the field name passes; the word in any
    #: other text still fails.
    steps = lambda html: split_words(re.sub(_field_allowance(), " ", re.sub(r"<[^>]+>", " ", html)))  # noqa: E731
    assert REVIEW_WORD not in steps(FIELD_PAGE)
    assert REVIEW_WORD in steps(
        FIELD_PAGE.replace("</main>", f"<p>The engine {REVIEW_WORD} of this console.</p></main>")
    )
    assert REVIEW_WORD in steps(FIELD_PAGE.replace(f"engine.settings.engine_{REVIEW_WORD}", f"engine_{REVIEW_WORD}"))


#: The banner's sentence on the runs, as 0.8.0's capture store served it: the demo's words, whatever the store held.
LINE_080 = (
    "Its runs come from 11 small example pipelines, recorded when this demo was built, with no network calls and no "
    "hosted model."
)


def _c6():
    """Check C6 as the script makes it: (the sentence it requires, a function reading a front page as C6 does)."""
    text = _text()
    holds = re.findall(r'^\$Holds = "([^"]+)"$', text, re.M)
    assert len(holds) == 1, "C6 names the sentence the capture store's banner holds"
    (line,) = [ln for ln in text.splitlines() if ln.startswith('Check "C6 ')]
    assert "$front.Status -eq 200" in line and "Contains('data-frame=\"banner\"')" in line
    assert "$front.Body.Contains($Holds)" in line
    return holds[0], lambda body: 'data-frame="banner"' in body and holds[0] in body


def _front(sentence: str) -> str:
    return f'<header data-frame="banner"><p>A read-only demo of onetrace-console.</p><p>{sentence}</p></header>'


def test_c6_reads_the_banner_s_sentence_on_what_the_capture_store_holds(examined):
    from onetrace_console import public

    holds, c6 = _c6()
    public.speaks_for("captures")
    try:
        now = public.banner_runs()
    finally:
        public.speaks_for("demo")
    examined(2, "front pages")
    assert now.startswith(holds), (holds, now)
    assert not c6(_front(LINE_080)), "0.8.0's line, the demo's, fails C6"
    assert c6(_front(now)), "this build's capture store line passes C6"
