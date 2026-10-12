"""The incidents lists and one incident's own page.

A list's row: the rule's chip (linked to the incident's own page), the run (linked to its page), its
pipeline, and when the incident was raised -- when this console's check of the run ran, as the
stored report records it.

One incident: the run's four answers as its own page's head draws them; the amber caution only where
a signature or an anchor holds over records that contradict themselves; "What the verifier found"
-- the stored report's summary, each fix line and its rows, each its own block, each as the verifier
wrote it, the fix lines' errors-page addresses linked to the published page a reader opens; and
"Which file, and how", built only from the report's failing rows. No re-check: the console has no
such action, and a public console refuses every write.

Every incident of the public demo is held to its run's stored report and its run's own page. Each
check has its sabotage.
"""
from __future__ import annotations

import re
from html import escape

import pytest

from tests.test_runs_list import _text, demo  # noqa: F401

ERRORS_MD = "https://oneproof.dev/onetrace/errors.md#"
ERRORS_HTML = "https://oneproof.dev/onetrace/errors.html#"


def _sdk_codes() -> set[str]:
    """Every section the errors page has: the SDK's own table, from which the page is generated."""
    import onetrace.errors as errors
    table = next(v for v in vars(errors).values()
                 if isinstance(v, (list, tuple)) and v and hasattr(v[0], "code"))
    return {c.code for c in table}


def row_problems(list_page: str, store, pages) -> list[str]:
    from onetrace_console.overview import pipelines
    from onetrace_console.words import short_time
    from onetrace_console.incidents import derive
    from onetrace_console.pages import _envelope
    by_id = {i.id[:12]: i for i in derive(store)}
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    rows = re.findall(r'<tr data-incident="([0-9a-f]+)">(.*?)</tr>', list_page, re.S)
    if not rows:
        return ["no rows"]
    out = []
    for short, row in rows:
        incident = by_id.get(short)
        if incident is None:
            out.append(f"{short}: no such incident")
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
        own = re.search(r'<a href="(incidents/[^"]+\.html)">', cells[0])
        if own is None or not (pages / own.group(1)).exists():
            out.append(f"{short}: its chip opens no page of its own")
        if incident.subject_kind == "run":
            if f'href="runs/{incident.subject}/case.html"' not in cells[1]:
                out.append(f"{short}: no link to its run")
            if _text(cells[2]) != label.get(incident.subject, ""):
                out.append(f"{short}: pipeline {_text(cells[2])!r}")
        #: When this console's check of the run ran, read from the stored report itself.
        raised = (_envelope(store.get_run(incident.subject), store, required=False).get("ran_at")
                  if incident.subject_kind == "run" else None)
        if _text(cells[3]) != (short_time(raised) if raised else "not recorded"):
            out.append(f"{short}: raised {_text(cells[3])!r}")
    return out


def page_problems(page: str, incident, store, pages) -> list[str]:
    """One incident's page against its run's own page and its run's stored report."""
    from onetrace_console.pages import _envelope
    out = []
    if "page-failed" in page:
        return ["the page could not be drawn"]
    run = store.get_run(incident.subject)
    case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    head = dict(re.findall(r'data-head-rung="([^"]+)" data-state="([^"]+)"', case))
    mine = dict(re.findall(r'data-head-rung="([^"]+)" data-state="([^"]+)"', page))
    if len(mine) != 4 or mine != head:
        out.append(f"answers {mine} here, {head} on the run's page")
    signed, anchored = mine.get("signed") == "yes", mine.get("anchored") == "yes"
    cautioned = 'data-section="caution"' in page
    if cautioned != (mine.get("records-agree") == "no" and (signed or anchored)):
        out.append(f"caution {'shown' if cautioned else 'missing'} for {mine}")
    from onetrace_console.viewer.page import _escape_rows
    envelope = _envelope(run, store, required=False)
    stderr = str(envelope.get("stderr", "")).replace("\r\n", "\n").splitlines()
    summary = [line for line in stderr if line and not line.startswith("fix ")]
    fixes = [line for line in stderr if line.startswith("fix ")]
    #: Each block by the run page's rule for the verifier's rows (`_escape_rows`), as written.
    shown_summary = re.findall(r'<pre class="term" data-found="summary">(.*?)</pre>', page, re.S)
    if shown_summary != [_escape_rows(line) for line in summary]:
        out.append(f"summary {shown_summary} for {summary}")
    shown_fixes = re.findall(r'<p class="fix" data-found="fix"><code>(.*?)</code></p>', page, re.S)
    if len(shown_fixes) != len(fixes) or not fixes:
        out.append(f"fix lines {len(shown_fixes)} for {len(fixes)}")
    codes = _sdk_codes()
    for line, shown in zip(fixes, shown_fixes):
        head, _, code = line.rpartition(ERRORS_MD)
        if not head:
            out.append(f"a fix line names no errors page: {line[:80]}")
            continue
        if shown != _escape_rows(head) + f'<a href="{ERRORS_HTML}{code}">{escape(ERRORS_MD + code)}</a>':
            out.append(f"no link to the errors page's {code}, or the line not as written")
        if code not in codes:
            out.append(f"{code}: no such section on the errors page")
    rows = re.search(r'<pre class="term" data-found="rows">(.*?)</pre>', page, re.S)
    if rows is None or not envelope.get("stdout") or \
            rows.group(1) != _escape_rows(str(envelope["stdout"]).replace("\r\n", "\n")):
        out.append("the verifier's rows are not its own")
    import json

    from onetrace_console.viewer.page import _named, _rest

    def word(text):   # a record's word, as every page quotes one
        return _named(text) + _rest(text, whole=False)
    failed = [r for r in json.loads(envelope["rows_json"]["stdout"])["rows"] if r.get("result") == "FAIL"]
    named = re.findall(r"<li data-fail-row>(.*?)</li>", page, re.S)
    wanted = []
    for r in failed:
        path, _, check = str(r["name"]).partition(": ")
        wanted.append(f"<code>{word(path)}</code>" + (f" — {word(check)}" if check else "")
                      + (f": {word(r['detail'])}" if r.get("detail") else ""))
    if not named or named != wanted:
        out.append(f"which file: {named} for {wanted}")
    if re.search(r"<form|<button|re-?check|check again", page, re.I):
        out.append("a re-check")
    return out


def test_every_incident_row_opens_its_page_and_its_run(demo, examined):
    from onetrace_console.incident_pages import INCIDENTS, rule_href
    from onetrace_console.incidents import RULES
    store, pages = demo
    rows = 0
    for name in [INCIDENTS] + [rule_href(r.id) for r in RULES]:
        html = (pages / name).read_text(encoding="utf-8")
        found = len(re.findall(r'<tr data-incident="', html))
        if found:
            assert row_problems(html, store, pages) == [], name
        rows += found
    examined(rows, "incident rows across the lists")
    assert rows >= 2


def test_every_incident_page_is_its_run_s_report_and_its_run_s_answers(demo, examined):
    from onetrace_console.incident_pages import incident_href
    from onetrace_console.incidents import derive
    store, pages = demo
    every = [i for i in derive(store) if i.subject_kind == "run"]
    examined(len(every), "incident pages")
    assert every
    for incident in every:
        page = (pages / incident_href(incident)).read_text(encoding="utf-8")
        assert page_problems(page, incident, store, pages) == [], incident_href(incident)


def test_sabotage_each_check_catches_its_fault(demo, examined):
    """Each fault, made in a copy of a real page: the check names it."""
    from onetrace_console.incident_pages import INCIDENTS, incident_href
    from onetrace_console.incidents import derive
    store, pages = demo
    incident = next(i for i in derive(store) if i.subject_kind == "run")
    page = (pages / incident_href(incident)).read_text(encoding="utf-8")
    listed = (pages / INCIDENTS).read_text(encoding="utf-8")
    faults = {
        "an answer the run's page doesn't say": (page, lambda p: re.sub(
            r'(data-head-rung="signed" data-state=")[^"]+', r"\1no", p, count=1), "answers"),
        "the caution dropped": (page, lambda p: re.sub(
            r'<p data-section="caution".*?</p>', "", p, count=1, flags=re.S), "caution"),
        "a fix line linked to the source page": (page, lambda p: p.replace(ERRORS_HTML, ERRORS_MD), "errors page"),
        "the rows cut short": (page, lambda p: re.sub(r'(data-found="rows">)(.{40}).*?(</pre>)', r"\1\2\3",
                                                      p, count=1, flags=re.S), "rows"),
        "a summary line rewritten": (page, lambda p: re.sub(
            r'(data-found="summary">)([^<]*)', r"\1\2 (tidied)", p, count=1), "summary"),
        "a file named that no row fails": (page, lambda p: p.replace(
            "<li data-fail-row>", "<li data-fail-row><code>receipts/00-made-up.json</code></li><li data-fail-row>", 1),
            "which file"),
        "a re-check button": (page, lambda p: p.replace("</h1>", "</h1><button>Check again</button>", 1), "re-check"),
    }
    caught = 0
    for name, (original, fault, said) in faults.items():
        broken = fault(original)
        assert broken != original, f"{name}: the fault changed nothing"
        problems = page_problems(broken, incident, store, pages)
        assert any(said in p for p in problems), f"{name}: not caught ({problems})"
        caught += 1
    row = re.search(r'<tr data-incident="[0-9a-f]+">.*?</tr>', listed, re.S).group(0)
    for name, fault, said in [
            ("a chip to nowhere", lambda r: r.replace('href="incidents/', 'href="incidents/gone-', 1), "no page"),
            ("the raised time shown as now", lambda r: re.sub(
                r'(<td[^>]*class="value">).*?(</td></tr>)', r"\1just now\2", r, flags=re.S), "raised")]:
        assert fault(row) != row, f"{name}: the fault changed nothing"
        problems = row_problems(fault(row), store, pages)
        assert any(said in p for p in problems), f"{name}: not caught ({problems})"
        caught += 1
    examined(caught, "faults caught")


def test_the_answers_are_a_strip_and_the_rows_a_block_of_their_own_height(examined):
    """The Check board's shape: the four answers in one row of cells, the run head's own strip; the
    verifier's rows a block of fixed height that scrolls, not the page's whole length; the summary
    line wrapped, never cut at the side."""
    import re as _re

    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    strip = _re.search(r":is\(\[data-section=run-head\] \.seals,\.seals\[data-section=answers\]\)\{display:grid;", css)
    rows = _re.search(r"\.cp\[data-view=incident\] \[data-scroll=found-rows\]\{max-height:\d+px;overflow:auto\}", css)
    summary = _re.search(r"\.cp\[data-view=incident\] pre\[data-found=summary\]\{white-space:pre-wrap;", css)
    examined(3, "rules")
    assert strip and rows and summary, (bool(strip), bool(rows), bool(summary))
