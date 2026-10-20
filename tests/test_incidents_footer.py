"""The Incidents page's last lines: the rule table's digest, then the rules not built, each one
sentence on one line.

1. "Rule table digest: <the digest, shown short>", ending at the shortened digest's "…": no full
   stop inside the digest's fold or after it, so no line of the page starts with a full stop.
2. "Rules not built: I-DIFF-REGRESSION." on a line of its own; where every rule is built, the line
   is absent.

Each check returns the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import html
import re

GENERATED_AT = "2026-09-26T12:00:00+02:00"


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def footer_problems(page: str, not_built: tuple[str, ...]) -> list[str]:
    out = []
    digest = re.search(r'<div data-section="rule-table">(.*?)</div>', page, re.S)
    if not digest:
        return ["no rule table digest"]
    if not re.fullmatch(r'Rule table digest: <details class="fingerprint"><summary class="mono">'
                        r'[^<.]*…</summary><span class="mono" data-fingerprint="whole">[^<]*</span>'
                        r"</details>", digest.group(1)):
        out.append(f"the digest's line is not one sentence: {_text(digest.group(1))!r}")
    if re.search(r"</details>\s*\.", page) or re.search(r">\s*\.\s*Rules not built", page):
        out.append("a line starts with a full stop")
    lines = re.findall(r'<p data-section="not-built">(.*?)</p>', page, re.S)
    if not_built:
        want = f"Rules not built: {', '.join(not_built)}."
        if [_text(x) for x in lines] != [want]:
            out.append(f"the rules not built read {[_text(x) for x in lines]}, not {want!r}")
    elif lines or "Rules not built" in _text(page):
        out.append("every rule is built, and the page says rules not built")
    if 'data-section="not-built"' in page and not lines:
        out.append("the rules not built are not one line")
    return out


def _page(store, monkeypatch=None, not_built=None) -> str:
    from onetrace_console import incident_pages
    if monkeypatch is not None:
        monkeypatch.setattr(incident_pages, "NOT_BUILT", not_built)
    return incident_pages.render_incidents(store, generated_at=GENERATED_AT)


def test_a_rule_not_built_is_one_sentence_on_its_own_line(store, examined):
    from onetrace_console.incidents import NOT_BUILT
    assert NOT_BUILT == ("I-DIFF-REGRESSION",)
    page = _page(store)
    assert footer_problems(page, NOT_BUILT) == []
    assert "Rules not built: I-DIFF-REGRESSION." in _text(page)
    examined(1, "Incidents page with a rule not built")


def test_every_rule_built_and_the_line_is_absent(store, monkeypatch, examined):
    page = _page(store, monkeypatch, ())
    assert footer_problems(page, ()) == []
    assert "Rules not built" not in page
    examined(1, "Incidents page with every rule built")


# ------------------------------------------------------------------------------- sabotages

#: The footer as 0.2.1's first candidate drew it: the full stop after the digest's fold, and the
#: rules not built as a list after the sentence.
OLD_FOOTER = ('<div data-section="rule-table">Rule table digest: {fp}. Rules not built: '
              '</div><ul class="plain" data-section="not-built"><li>I-DIFF-REGRESSION</li></ul>')


def _old(page: str) -> str:
    from onetrace_console.incidents import RULE_TABLE_DIGEST
    from onetrace_console.viewer.page import fingerprint_html
    old = OLD_FOOTER.format(fp=fingerprint_html(RULE_TABLE_DIGEST))
    bad = re.sub(r'<div data-section="rule-table">.*?</div>(\s*<p data-section="not-built">.*?</p>)?',
                 lambda m: old, page, count=1, flags=re.S)
    assert bad != page
    return bad


def test_sabotage_a_full_stop_inside_the_digest_s_fold_is_named(store):
    page = _page(store)
    bad = page.replace("…</summary>", "….</summary>", 1)
    assert bad != page
    assert any("not one sentence" in p for p in footer_problems(bad, ("I-DIFF-REGRESSION",)))


def test_sabotage_the_old_footer_is_named(store):
    problems = footer_problems(_old(_page(store)), ("I-DIFF-REGRESSION",))
    assert any("full stop" in p for p in problems), problems
    assert any("not one line" in p or "read" in p for p in problems), problems


def test_sabotage_rules_not_built_said_when_every_rule_is_built_is_named(store, monkeypatch):
    page = _page(store, monkeypatch, ())
    bad = page.replace('<p class="limit"', '<p data-section="not-built">Rules not built: .</p><p class="limit"', 1)
    assert bad != page
    assert any("every rule is built" in p for p in footer_problems(bad, ()))
