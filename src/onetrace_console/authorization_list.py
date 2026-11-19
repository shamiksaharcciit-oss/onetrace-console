"""Authorization across the console: every run whose record names a gated step, and the way to each run's own
Authorization page.

- **The console's page** (`/authorization.html`, after Incidents in the sidebar, always there): every run with a gated
  step, its gated steps, the decisions they cite, and onetrace-verify's decision rows in one word, with a link to the
  run's Authorization page. With none, it says "No authorization records in this console". It is drawn with the
  console's other pages, so a team's set holds its team's runs, the public demo and a static export hold theirs, and
  it is read by whoever may read the Runs list.
- **A run's tab:** every run with a gated step has an Authorization tab beside its other pages, with the count of its
  gated steps, whether its record holds up or not.
- **A run whose record does not hold up:** its Authorization page shows what the record says, under the same
  "does not hold up" line as its other views.
- **"The decisions, as checked"** links to the run's Authorization page; and the Policy line on Proof says how many
  gated steps the record names, where it said "No authorization records for this run." beside them.

Every number and word here is read from the record and onetrace-verify's own rows; nothing is inferred. The result in
one word is FAIL where any decision row fails, PASS only where every one passes, and "couldn't check" where
onetrace-verify did not run on the decisions or its rows can't be read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from onetrace_console.words import escape, generated_footer, hidden_header, scroll_region

PAGE = "authorization.html"
TITLE = "Authorization"
LEAD = (
    "Every run whose record names a gated step: the decisions those steps cite, and what onetrace-verify's decision "
    "rows say of them. A decision row says what the record holds, not whether the action should have happened."
)
NONE = "No authorization records in this console"
COLUMNS = ("Run", "Pipeline", "Gated steps", "Decisions cited", "onetrace-verify's decision rows")
OPEN = "Open its Authorization page"
PASS, FAIL, COULDNT = "PASS", "FAIL", "couldn't check"
#: On a run's pages.
TAB = "Authorization"
SEE = "Open the run's Authorization page"
POLICY_GATED = "The record names {n} gated {word}: the run's Authorization page shows each, with its decision."


def plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


@dataclass(frozen=True)
class Facts:
    """What a run's record says of authorization: its gated steps, the decisions they cite, and onetrace-verify's
    decision rows in one word (None where the run has no gated step)."""

    gated: int
    decisions: int
    result: str | None


def facts(run, store) -> Facts:
    """`Facts` for `run`, read from its record and its stored check."""
    from onetrace_console.authorization import gated_rows
    from onetrace_console.onedoor_panel import decision_rows
    from onetrace_console.pages import _envelope
    from onetrace_console.run_panels import manifest_of
    from onetrace_console.stage_pages import _steps

    entries = gated_rows(manifest_of(run, store), _steps(run, store))
    gated = sum(1 for e in entries if e["gated"])
    if not gated:
        return Facts(0, 0, None)
    decisions = sum(len(e["decisions"] or []) for e in entries)
    return Facts(gated, decisions, result_of(decision_rows(_envelope(run, store, required=False))))


def result_of(rows: list[dict]) -> str:
    """onetrace-verify's decision rows in one word: FAIL where any fails, PASS only where every one passes, "couldn't
    check" otherwise (none run, none readable, or some not run)."""
    results = [str(r.get("result", "")) for r in rows]
    if FAIL in results:
        return FAIL
    if results and all(r == PASS for r in results):
        return PASS
    return COULDNT


def gated_count(run, store) -> int:
    """How many gated steps `run`'s record names, for the runs list's mark; 0 where it can't be read."""
    try:
        return facts(run, store).gated
    except Exception:  # noqa: BLE001 - a record that can't be read marks nothing; its page says why
        return 0


def gated_words(n: int) -> str:
    return f"{n} gated {plural(n, 'step', 'steps')}"


# ------------------------------------------------------------------------------------------- the console's page


def render(store, *, generated_at: str) -> str:
    """The console's Authorization page: every run of `store` (a team's view in a team's set) with a gated step."""
    from onetrace_console.pages import label
    from onetrace_console.render import _document
    from onetrace_console.verdicts import pipeline_of

    listed = []
    for run in sorted(store.runs(), key=lambda r: (r.run_id, r.key)):
        try:
            got = facts(run, store)
        except Exception:  # noqa: BLE001 - a record that can't be read lists nothing here; its page says why
            continue
        if got.gated:
            listed.append((run, got))
    if listed:
        rows = "".join(
            f'<tr data-run="{escape(run.key)}"><td><a href="runs/{escape(run.key)}/{PAGE}">'
            f'<span class="mono" data-words="record">{escape(run.run_id)}</span></a></td>'
            f"<td>{escape(_pipeline(run, store, pipeline_of))}</td>"
            f"<td>{got.gated}</td><td>{got.decisions}</td>"
            f'<td data-result="{escape(str(got.result))}">{escape(str(got.result))}</td>'
            f'<td><a href="runs/{escape(run.key)}/{PAGE}">{escape(OPEN)}</a></td></tr>'
            for run, got in listed
        )
        head = "".join(f'<th scope="col">{escape(c)}</th>' for c in COLUMNS) + hidden_header("Action")
        table = scroll_region(
            f'<table class="timeline" data-section="authorization-list"><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table>",
            "Runs with gated steps",
            "authorization-list",
        )
    else:
        table = f'<p data-section="none">{escape(NONE)}</p>'
    body = (
        f'<div class="cp" data-page="authorization-list"><h1>{escape(TITLE)}</h1>'
        f'<p data-section="what">{escape(LEAD)}</p>{table}{generated_footer(generated_at)}</div>'
    )
    return label(_document(TITLE, body), [run for run, _ in listed])


def _pipeline(run, store, pipeline_of) -> str:
    try:
        got = pipeline_of(run, store)
    except Exception:  # noqa: BLE001 - a run whose pipeline can't be read shows none
        return ""
    return str(getattr(got, "label", got) or "")


# ------------------------------------------------------------------------------------------- a run's own pages

_TABS = re.compile(r'(<nav class="tabs" aria-label="This run\'s pages">)(.*?)(</nav>)', re.S)


def with_tab(page: str, got: Facts, *, href: str, here: bool = False) -> str:
    """`page`, one of a run's pages, with the Authorization tab and its count among the run's tabs: where the run has a
    gated step; unchanged otherwise, or where the page has no tabs or has the tab already."""
    if not got.gated or f'data-tab="{PAGE}"' in page:
        return page
    current = ' aria-current="page"' if here else ""
    tab = (
        f' <a href="{escape(href)}" data-tab="{PAGE}"{current}>{escape(TAB)} '
        f'<span class="count">· {escape(gated_words(got.gated))}</span></a>'
    )
    return _TABS.sub(lambda m: m.group(1) + m.group(2) + tab + m.group(3), page, count=1)


#: The run's own tabs' Authorization tab: matched inside that one row, never past its end.
_HEAD_TAB = re.compile(
    r'(<nav class="tabs" aria-label="This run\'s pages">(?:(?!</nav>).)*?) ?<a href="authorization\.html">[^<]*</a>',
    re.S,
)


def without_head_tab(page: str) -> str:
    """`page`, a run's page that carries the views' tabs, without the run's own Authorization tab: the views' tab is
    the page's one; unchanged where the run's tabs have none."""
    return _HEAD_TAB.sub(lambda m: m.group(1), page, count=1)


def with_decisions_link(page: str, *, href: str) -> str:
    """`page` with "The decisions, as checked" leading to the run's Authorization page; unchanged where it is not there
    or links already."""
    marker = '<section data-section="onedoor-rows" class="onedoor"><h2>The decisions, as checked</h2>'
    if marker not in page or f'data-see="{PAGE}"' in page:
        return page
    link = f'<p data-see="{PAGE}"><a href="{escape(href)}">{escape(SEE)}</a></p>'
    return page.replace(marker, marker + link, 1)


_NO_RECORDS = re.compile(
    r'(<section data-section="policy">.*?)(<p[^>]*>(?:<[^>]+>)*No authorization records for this run\.?(?:</[^>]+>)*</p>)',
    re.S,
)


def with_policy_line(page: str, got: Facts, *, href: str) -> str:
    """`page` with its Policy section saying how many gated steps the record names, in place of "No authorization
    records for this run.", where the record names one; unchanged otherwise."""
    if not got.gated:
        return page
    line = (
        f'<p data-section="policy-gated">{escape(POLICY_GATED.format(n=got.gated, word=plural(got.gated, "step", "steps")))}'
        f' <a href="{escape(href)}">{escape(TAB)}</a></p>'
    )
    return _NO_RECORDS.sub(lambda m: m.group(1) + line, page, count=1)


def does_not_hold_up(said: str, state: str, rows_from: str) -> str:
    """The lines a run's Authorization page carries under its head where its record does not hold up (or could not be
    checked), the same as its other views carry: that what follows comes from that record, and what the records
    establish."""
    tone = "bad" if state == "no" else "cc"
    return (
        f'<h2 data-section="withheld" data-tone="{tone}">{escape(rows_from)}</h2>'
        f'<p data-section="integrity" data-tone="{tone}">{escape(said)}</p>'
    )
