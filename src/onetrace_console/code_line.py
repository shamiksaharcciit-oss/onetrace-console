"""The code version a run ran, and a re-run's parts: format 0.5's `code` and `rerun_from` (onetrace 0.8's
`docs/format.md`, "Re-runs with parts chosen separately"), as a run's record holds them, and onetrace-verify's own
rows on them.

Where they are drawn:
- the run's case page gets a section, "Code": the commit, short, whole in a fold, or the record's `not observed:
  <reason>`; "uncommitted changes" where `dirty` is `true`; the lock file's name and digest; "not recorded" on a
  format 0.5 run that didn't ask. The verifier's rows `code`, `the code matches its commit` and `re-run from` are
  quoted as it wrote them, its detail as it is: onetrace 0.8.0's own words, CRLF line endings among them, never the
  console's;
- a re-run's head gets a line naming each part taken and from which run, each run linked where this store holds it
  (through `service_link.link_to`, picked by the chain head the record names), and "environment: today" in those
  words.

The rules are `step_kinds`': the record's words and the verifier's rows alone; a member the verifier FAILs (`code`,
`re-run from`) is not drawn from, and its row is shown; the section carries `docs/format.md`'s "What it does not
show". A receipt in an earlier format gets nothing.
"""

from __future__ import annotations

from onetrace_console.step_kinds import _fail_block, _line, failed, holds_members, prose
from onetrace_console.words import escape

#: onetrace 0.8's `docs/format.md`, "Re-runs with parts chosen separately", "What it does not show".
NON_CLAIMS = (
    "It shows what that combination does today, with today's services and model. Code from B with today's environment "
    "is not B's run. A recorded commit is what `git` reported when the run opened, and `manifest_digest` covers the "
    "code file the run names, not every file that commit holds. `dirty` `false` says tracked files matched; untracked "
    "files are not read. `lock_differs` compares two files' digests, not which package differs. A part named and "
    "taken is a value handed to the code through a parameter, not shown to be used."
)
HEADING = "Code"
NOT_RECORDED = "not recorded: this run did not ask for its code version"
DIRTY = "uncommitted changes: the tracked files differed from the commit"
CLEAN = "no uncommitted changes to tracked files"
PARTS_LEAD = "This run took parts from other runs"
ENVIRONMENT = "environment: today"
CODE_ROW = "code"
MATCHES_ROW = "the code matches its commit"
RERUN_ROW = "re-run from"
ROWS = (CODE_ROW, MATCHES_ROW, RERUN_ROW)
SHORT = 12


def _rec(text: str) -> str:
    return f'<span class="mono" data-words="record">{escape(text)}</span>'


def _commit(commit: str) -> str:
    if commit.startswith("not observed"):
        return _rec(commit)
    if len(commit) <= SHORT:
        return _rec(commit)
    return f"<details data-code-commit><summary>{_rec(commit[:SHORT])}</summary>{_rec(commit)}</details>"


def _first(receipts: list[dict]) -> dict | None:
    first = receipts[0] if receipts and isinstance(receipts[0], dict) else None
    return first if first is not None and holds_members(first) else None


def section(receipts: list[dict], rows: list[dict]) -> str:
    """The case page's "Code": the code version the first receipt records, and the verifier's rows on it. Nothing for
    an earlier format."""
    first = _first(receipts)
    if first is None:
        return ""
    quoted = [_line(r) for r in rows if r.get("name") in ROWS and r.get("result") != "FAIL"]
    fails = failed(rows, "", (CODE_ROW,))
    code = first.get("code")
    if fails:
        body = _fail_block(fails)
    elif not isinstance(code, dict):
        body = f'<p data-code="not-recorded">{escape(NOT_RECORDED)}</p>'
    else:
        lines = [f"Commit: {_commit(str(code.get('commit', '')))}"]
        if code.get("dirty") == "true":
            lines.append(f'<span data-code="dirty">{escape(DIRTY)}</span>')
        elif code.get("dirty") == "false":
            lines.append(escape(CLEAN))
        if isinstance(code.get("lock_name"), str):
            lines.append(f"Lock file: {_rec(code['lock_name'])} {_rec(str(code.get('lock_digest', '')))}")
        body = "".join(f"<p>{x}</p>" for x in lines)
    rerun_fails = failed(rows, "", (RERUN_ROW,))
    if rerun_fails:
        body += _fail_block(rerun_fails)
    if quoted:
        items = "".join(f'<li><span class="mono" data-check-row="quoted">{escape(ln)}</span></li>' for ln in quoted)
        body += f'<div data-section="code-check"><p>onetrace-verify:</p><ul class="plain">{items}</ul></div>'
    return (
        f'<section data-section="code"><h2>{escape(HEADING)}</h2>{body}'
        f'<p class="note" data-section="code-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


def parts_line(receipts: list[dict], rows: list[dict], held: dict[str, list[str]], store, up: str) -> str:
    """A re-run's head: each part it took and from which run, linked where held; nothing where it took none, or
    where the verifier FAILs `re-run from` (its row is in the case page's "Code")."""
    from onetrace_console.service_link import link_to

    first = _first(receipts)
    taken = first.get("rerun_from") if first is not None else None
    if first is None or not isinstance(taken, dict) or failed(rows, "", (RERUN_ROW,)):
        return ""
    rerun: dict = given if isinstance(given := first.get("rerun"), dict) else {}
    parts = []
    if isinstance(taken.get("code_of_run"), str):
        said = "code from " + link_to(taken["code_of_run"], held, up, head=taken.get("code_of_chain_head"), store=store)
        if isinstance(taken.get("code_commit"), str):
            said += f" at {_rec(taken['code_commit'][:SHORT])}"
        parts.append(said)
    if isinstance(taken.get("config_parts"), list):
        source = taken.get("config_of_run") or rerun.get("config_of_run")
        head = taken.get("config_of_chain_head") or rerun.get("config_of_chain_head")
        names = ", ".join(_rec(str(p)) for p in taken["config_parts"])
        said = f"configuration parts {names}"
        if isinstance(source, str):
            said += " from " + link_to(source, held, up, head=head, store=store)
        parts.append(said)
    if taken.get("lock_differs") == "true":
        parts.append(
            f"the lock file differs: {_rec(str(taken.get('lock_name', '')))} {_rec(str(taken.get('lock_digest', '')))}"
        )
    if isinstance(taken.get("environment"), str):
        parts.append(escape(f"environment: {taken['environment']}"))
    if not parts:
        return ""
    return f'<p class="sub" data-section="rerun-parts">{escape(PARTS_LEAD)}: {" · ".join(parts)}</p>'
