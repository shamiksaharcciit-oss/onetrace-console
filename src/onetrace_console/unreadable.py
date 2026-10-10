"""What the viewer refuses, stated on a page: never a crash, and never a page drawn from a guess.

    Each malformed shape becomes a clean refusal (`VerbReportUnreadable` or its model
    equivalent). None may crash a page.

The viewer refuses a record with a receipt part it cannot read (`RecordUnreadable`) or a file
its manifest names and the run lacks (`RecordError`), and an SDK report it cannot read
(`VerbReportUnreadable`). **Ingest may not refuse such a run**: the 422 set is kept to damaged
sums and unknown formats, and a console that refused to hold a record because
the record is bad news would have the job backwards. So the run is stored and checked like any
other, and what its pages say is here. Before this, the refusal escaped the page code: the
ingest that stored the run answered 500, every later ingest did too (every list is rebuilt with
every run in it), and a restart over that store never reached its listener.

**The words are this console's own and provisional.** No decision words these states; each is a
constant here, so a decision that does lands in one place. They say what the console holds and
what the viewer said, and claim nothing about the record: no verdict is drawn from a record the
viewer could not read.
"""
from __future__ import annotations

from onetrace_console.words import escape, named, record_href, shown_name, verbatim, generated_footer

from onetrace_console.store import StoredRun

TITLE = "This run can't be shown"
HELD = ("This console holds this run exactly as it was delivered. The viewer cannot read its "
        "record, so no page is drawn from it, and nothing here says whether the record holds.")
WHY = "The viewer's reason, word for word:"
#: When drawing the run failed for a reason that is not the viewer's (the second confirmation
#: review, S1: a store integrity failure was shown as the viewer's reason, under "held exactly
#: as delivered"). Nothing is claimed about the bytes.
RUN_FAILED = "This run's pages could not be drawn"
FAILED_SAID = ("Drawing this run's pages failed, so no page is drawn from it, and nothing here "
               "says whether the record holds. What failed:")
#: A stored run with no check report: its check did not complete when it was received (the
#: second review, B2). The run page is refused, as it always was; the console says so.
NOT_CHECKED = "This run has not been checked"
NOT_CHECKED_SAID = ("This console holds this run and has no check report for it: its check did "
                    "not complete when the run was received. No page is drawn from an unchecked "
                    "run, and nothing here says whether the record holds.")
#: Any other page whose drawing failed (the second review, B1): said on that page, and the rest
#: are drawn.
PAGE_FAILED = "This page could not be drawn"
PAGE_FAILED_SAID = "Drawing this page failed, so it shows nothing else. What failed:"
LIST_HEADING = "Runs this console holds and cannot show"
LIST_NOTE = ("These runs are not in the list above: their pages cannot be drawn. Each reason "
             "is given here, and each run's own page says the same.")
REPORT_REFUSED = ("This console cannot read the {verb} report, so nothing is drawn from it. "
                  "The viewer's reason, word for word:")
REPORT_SHOWN = ("The report is shown below as the SDK wrote it, with names from the records "
                "escaped.")
REPORT_FAILED = ("Drawing from the {verb} report failed, so nothing is drawn from it. What "
                 "failed:")

#: Where the list's block goes: the viewer's own closing sentence, which follows its list. An
#: anchor that is missing raises, as `preview.label` does: a run silently left off a list is
#: the failure this module exists to prevent.
_LIST_ANCHOR = '<p class="limit" data-section="limit">'


def _safe(text) -> str:
    """Text a page can carry: a lone surrogate kept visible as its escape, never an error --
    and whatever it is given, as text: the start guard's own except branch raised on a run_id
    that was an int."""
    return str(text).encode("utf-8", "backslashreplace").decode("utf-8")


def _run_page(run: StoredRun, title: str, said: str, reason: str | None, *, words: str,
              generated_at: str, state: str = "unreadable") -> str:
    from onetrace_console.preview import label
    from onetrace_console.render import _document, _limit_sentence

    why = (f'<pre data-words="{words}">{verbatim(reason)}</pre>' if reason else "")
    body = (
        f"<h1>{escape(title)}</h1>"
        f'<p data-section="run">Run <span class="mono" data-words="record">'
        f"{named(_safe(run.run_id), record_href(run))}</span></p>"
        f'<section data-section="unreadable" data-state="{escape(state)}">'
        f"<p>{escape(said)}</p>{why}</section>"
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>'
        + generated_footer(generated_at))
    body = f'<div class="cp">{body}</div>'  # the console's page skin (item 12)
    return label(_document(f"{title} · {shown_name(_safe(run.run_id))}", body), [run])


def render_unreadable_run(run: StoredRun, reason: str, *, generated_at: str,
                          from_viewer: bool = True) -> str:
    """The page a run's answer and case pages become when the viewer refuses its record -- or,
    `from_viewer=False`, when drawing it failed for another reason, which claims nothing about
    the bytes."""
    if from_viewer:
        return _run_page(run, TITLE, f"{HELD} {WHY}", reason, words="viewer",
                         generated_at=generated_at)
    return _run_page(run, RUN_FAILED, FAILED_SAID, reason, words="error",
                     generated_at=generated_at)


def render_incomplete_run(run: StoredRun, said: str, *, generated_at: str) -> str:
    """The page a run's answer and case pages become when the store is missing an object its
    record names: the fixed line, as could not check -- never drawn from
    what is left, never holds or contradicts."""
    return _run_page(run, RUN_FAILED, said, None, words="console", generated_at=generated_at,
                     state="couldnt-check")


def render_unchecked_run(run: StoredRun, *, generated_at: str) -> str:
    """The page a run's answer and case pages become when it has no stored check report."""
    return _run_page(run, NOT_CHECKED, NOT_CHECKED_SAID, None, words="console",
                     generated_at=generated_at)


def render_failed_page(reason: str, *, generated_at: str) -> str:
    """Any other page, when drawing it failed. What failed is named; nothing else is shown."""
    from onetrace_console.render import _document

    body = (f"<h1>{escape(PAGE_FAILED)}</h1>"
            f'<section data-section="page-failed" data-state="unreadable">'
            f"<p>{escape(PAGE_FAILED_SAID)}</p>"
            f'<pre data-words="error">{verbatim(reason)}</pre></section>'
            + generated_footer(generated_at))
    return _document(PAGE_FAILED, f'<div class="cp">{body}</div>')  # the page skin (item 12)


def unshowable_runs_block(page: str, refused: list[tuple[StoredRun, str, bool]]) -> str:
    """Name, below the viewer's list, each run it could not be given, with the viewer's reason."""
    if not refused:
        return page
    if page.count(_LIST_ANCHOR) != 1:
        raise ValueError("cannot name the runs this list cannot show: the list page has no "
                         "single closing sentence to place them before")
    #: Whose words each reason is: the viewer's refusal, or a failure that is not its (the third
    #: confirmation review, NEW-13).
    items = "".join(
        f'<li><span class="mono" data-words="record">{named(_safe(run.run_id), record_href(run))}</span> '
        f'<span class="mono">{escape(run.key[:12])}</span>: '
        f'<span data-words="{"viewer" if from_viewer else "error"}">{escape(_safe(reason))}'
        f"</span></li>" for run, reason, from_viewer in refused)
    block = (f'<section data-section="unshowable-runs"><h2>{escape(LIST_HEADING)}</h2>'
             f"<p>{escape(LIST_NOTE)}</p><ul>{items}</ul></section>")
    at = page.index(_LIST_ANCHOR)
    return page[:at] + block + page[at:]


def report_refused(verb: str, reason: str, *, from_viewer: bool = True) -> str:
    """The Diff page's words for a report the viewer refused -- or, `from_viewer=False`, one
    whose drawing failed otherwise, not in the viewer's name -- in place of what it would draw."""
    said, words = ((REPORT_REFUSED, "viewer") if from_viewer else (REPORT_FAILED, "error"))
    return (f'<section data-section="{escape(verb)}-unreadable" data-state="unreadable">'
            f"<p>{escape(said.format(verb=verb))}</p>"
            f'<pre data-words="{words}">{verbatim(reason)}</pre>'
            f"<p>{escape(REPORT_SHOWN)}</p></section>")
