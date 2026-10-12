"""An incident page's summary and fix lines are capped, as the run page caps the verifier's rows.

A planted report -- a real incident's stored report with its summary and fix lines replaced by
lines far longer than the cap -- is drawn by the incident page itself. Each block shows the line's
first NAME_CAP characters and says how many were left out; a fix line's errors-page address is
kept whole and linked after its cut. The expectation is built here from NAME_CAP and the marker's
own template, not through the function that draws it. Taking the cap off fails it.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_incident_page import ERRORS_HTML, ERRORS_MD, _sdk_codes
from tests.test_runs_list import demo  # noqa: F401

LONG = 20_000


def _planted(envelope: dict, code: str) -> tuple[dict, list[str], list[str]]:
    summary = ["onetrace-verify: " + "s" * LONG, "  " + "é" * (LONG // 2)]
    fixes = ["fix receipts/01.json: " + "f" * LONG + f"; see {ERRORS_MD}{code}"]
    return {**envelope, "stderr": "\n".join(summary + fixes) + "\n"}, summary, fixes


def _cut(text: str) -> str:
    from onetrace_console.viewer.model import NAME_CAP
    from onetrace_console.viewer.sentences import template
    return text[:NAME_CAP] + " " + template("name.more").format(n=str(len(text) - NAME_CAP))


def cap_problems(page: str, summary: list[str], fixes: list[str], code: str) -> list[str]:
    out = []
    shown = [unescape(s) for s in re.findall(r'<pre class="term" data-found="summary">(.*?)</pre>', page, re.S)]
    if shown != [_cut(line) for line in summary]:
        out.append(f"summary lines drawn {[len(s) for s in shown]} long, not cut at the cap")
    drawn = re.findall(r'<p class="fix" data-found="fix"><code>(.*?)</code></p>', page, re.S)
    for line, html in zip(fixes, drawn):
        head = line[:line.rindex(ERRORS_MD)]
        link = f'<a href="{ERRORS_HTML}{code}">'
        before, _, after = html.partition(link)
        if not after or unescape(before) != _cut(head) or unescape(re.sub(r"<[^>]+>", "", after)) != ERRORS_MD + code:
            out.append(f"fix line drawn {len(unescape(before))} long before its link, not cut at the cap")
    if len(drawn) != len(fixes):
        out.append(f"fix lines {len(drawn)} for {len(fixes)}")
    return out


def _page(demo, monkeypatch):  # noqa: F811
    from onetrace_console import pages
    from onetrace_console.incident_pages import render_incident_page
    from onetrace_console.incidents import WHOLE_OUTPUT, derive
    store, _ = demo
    incident = next(i for i in derive(store) if i.subject_kind == "run" and i.field_path != WHOLE_OUTPUT)
    code = sorted(_sdk_codes())[0]
    real = pages._envelope
    planted = {}

    def envelope(run, st, **kw):
        found = real(run, st, **kw)
        planted["it"] = _planted(found, code)
        return planted["it"][0]
    monkeypatch.setattr(pages, "_envelope", envelope)
    page = render_incident_page(incident, store, generated_at="now")
    _, summary, fixes = planted["it"]
    return page, summary, fixes, code


def test_a_planted_report_s_long_summary_and_fix_lines_are_cut_at_the_cap(demo, monkeypatch, examined):  # noqa: F811
    page, summary, fixes, code = _page(demo, monkeypatch)
    examined(len(summary) + len(fixes), "planted lines past the cap")
    assert cap_problems(page, summary, fixes, code) == []
    from onetrace_console.viewer.model import NAME_CAP
    assert all(c * (NAME_CAP + 1) not in page for c in "sf"), "a planted line drawn past the cap"


def test_sabotage_the_cap_taken_off_is_caught(demo, monkeypatch, examined):  # noqa: F811
    """The incident page's lines drawn by the uncapped rule (every line whole): the check names it."""
    from onetrace_console.viewer import page as viewer_page
    monkeypatch.setattr(viewer_page, "_escape_rows", viewer_page._escape_lines)
    page, summary, fixes, code = _page(demo, monkeypatch)
    problems = cap_problems(page, summary, fixes, code)
    examined(1, "fault caught")
    assert any("summary" in p for p in problems) and any("fix line" in p for p in problems), problems
