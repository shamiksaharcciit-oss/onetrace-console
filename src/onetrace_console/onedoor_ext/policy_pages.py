"""The Policy page. Decisions standing alone -- what onedoor recorded,
never what the console thinks about it.

ONE ENTRY PER request_id, NOT PER ROW
---------------------------------------
See `tests/fixtures/onedoor/PROVENANCE.md`: a single auto-executed request is recorded
as two rows (`exec_intent` then `exec_result`) sharing one `request_id`. The list view
groups by `request_id` and shows the ROW onedoor's own code would call "the" result
for it -- `result_for_request_id()` in `onedoor/guardrail/audit.py` at the pinned
commit: `exec_result` if present, else `exec_intent`, else a plain `decision`, else the
last row written. Reused as a documented reading, not invented here; every row is
still stored and shown in the detail view, `exec_intent`/`exec_result` included.
"""
from __future__ import annotations

from onetrace_console.words import escape, generated_footer

from onetrace_console.onedoor_ext.decisions import (CheckedRow, DecisionRow,
                                                    StoredDecisionExport, check_store)
from onetrace_console.store import Store

POLICY = "policy.html"


def _document(title: str, body: str) -> str:
    from onetrace_console.render import _document as core_document
    #: In `.cp`, as every page the console draws itself, so the one style reaches it.
    return core_document(title, f'<div class="cp">\n{body}\n</div>')


def _limit_sentence() -> str:
    from onetrace_console.render import _limit_sentence as core_limit
    return core_limit()


class Decision:
    """One request_id's rows, from however many exports hold them, read from the delivery.

    Rows are the delivery's own (`CheckedRow.delivered`), grouped by the
    delivery's request id, so an edit to a stored copy can neither move a row nor change
    what it says. Each row keeps every (export, position) that holds it, and is shown only
    when every stored copy matches its delivery. A row any copy of which cannot be checked
    is not shown -- its value, the verdict included, is replaced by "couldn't check" and
    the name of the copy that changed. Byte-identical copies are one row.
    """

    def __init__(self, held: tuple[CheckedRow, ...]):
        self.held = held
        distinct: dict[str, DecisionRow] = {}
        for h in held:
            distinct.setdefault(h.delivered.raw_line, h.delivered)
        self.rows = tuple(distinct.values())

    def holders(self, row: DecisionRow) -> tuple[CheckedRow, ...]:
        return tuple(h for h in self.held if h.delivered.raw_line == row.raw_line)

    def changed_copies(self, row: DecisionRow) -> tuple[str, ...]:
        """The "couldn't check" sentence of every stored copy of `row` that does not
        match its delivery, each naming its export and position."""
        return tuple(h.couldnt_check for h in self.holders(row) if h.problem)

    def couldnt_check(self, row: DecisionRow) -> str | None:
        """None when every stored copy of `row` matches its delivery; otherwise the
        "couldn't check" sentence naming the first copy that does not.

        One edited copy withholds the row, even when another export holds it intact.
        The alternative -- show a row any one copy of which checks, naming the changed
        copies -- was raised for review as a choice."""
        changed = self.changed_copies(row)
        return changed[0] if changed else None

    @property
    def export(self) -> StoredDecisionExport:
        """The export holding the representative row (its first holder): the one an
        incident quoting that row can name."""
        return self.holders(self.representative)[0].export

    @property
    def request_id(self) -> str | None:
        return self.rows[0].request_id

    @property
    def representative(self) -> DecisionRow:
        by_kind = {r.kind: r for r in self.rows}
        return (by_kind.get("exec_result") or by_kind.get("exec_intent")
                or by_kind.get("decision") or self.rows[-1])

    @property
    def shown(self) -> bool:
        """Whether the representative row's values may be shown at all."""
        return self.couldnt_check(self.representative) is None

    @property
    def verdict(self) -> str | None:
        return self.representative.decision if self.shown else None

    @property
    def issuer(self) -> str | None:
        v = self.representative.fields.get("source") if self.shown else None
        return v if isinstance(v, str) else None

    @property
    def rule_or_policy(self) -> str | None:
        v = self.representative.fields.get("policy_version") if self.shown else None
        return v if isinstance(v, str) else None


def checked_rows(store: Store) -> tuple[CheckedRow, ...]:
    """Every stored row position of every export, checked against its delivery."""
    return check_store(store)


def couldnt_check_sentence(store: Store) -> str:
    """"K of T stored rows couldn't be checked: <each, named>", or nothing when K is 0."""
    every = checked_rows(store)
    bad = [c for c in every if c.problem]
    if not bad:
        return ""
    names = "; ".join(escape(c.couldnt_check) for c in bad)
    return (f'<p data-section="couldnt-check">{len(bad)} of {len(every)} stored rows '
            f"couldn't be checked: {names}.</p>")


def all_decisions(store: Store) -> tuple[Decision, ...]:
    """Every request_id, across every ingested export, its rows grouped together -- in
    first-seen order: the store's order of exports (by export key, not delivery time),
    then file order within one. Grouped by the DELIVERY's request id; a position whose
    delivery cannot be read has no trustworthy request id and is reported by
    `couldnt_check_sentence` instead.
    """
    by_request: dict[str, list[CheckedRow]] = {}
    for c in checked_rows(store):
        rid = c.delivered.request_id if c.delivered is not None else None
        if rid is None:
            continue
        by_request.setdefault(rid, []).append(c)
    return tuple(Decision(tuple(held)) for held in by_request.values())


def _decision_href(request_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in request_id)
    return f"policy/{safe}.html"


def _decision_row_html(d: Decision) -> str:
    rep = d.representative
    if not d.shown:
        return (
            f'<tr data-request-id="{escape(d.request_id or "", quote=True)}">'
            f'<td><a href="{escape(_decision_href(d.request_id), quote=True)}">'
            f'{escape(d.request_id or "")}</a></td>'
            f'<td colspan="4" data-state="couldnt-check">'
            f"{escape(d.couldnt_check(rep))}</td></tr>")
    rule = d.rule_or_policy or ""
    issuer = d.issuer or ""
    return (
        f'<tr data-request-id="{escape(d.request_id or "", quote=True)}">'
        f'<td><a href="{escape(_decision_href(d.request_id), quote=True)}">'
        f'{escape(d.request_id or "")}</a></td>'
        f"<td>{escape(rep.fields.get('created_at') or '')}</td>"
        f'<td data-verdict="{escape(d.verdict or "", quote=True)}">{escape(d.verdict or "")}</td>'
        f"<td>{escape(rule)}</td>"
        f"<td>{escape(issuer)}</td>"
        f"</tr>")


def render_policy(store: Store, *, generated_at: str) -> str:
    decisions = all_decisions(store)
    rows = "".join(_decision_row_html(d) for d in decisions)

    verdicts = sorted({d.verdict for d in decisions if d.verdict})
    issuers = sorted({d.issuer for d in decisions if d.issuer})
    filters = []
    if verdicts:
        filters.append("<p>By verdict: " + ", ".join(
            f'<a href="{escape(_verdict_href(v), quote=True)}">{escape(v)}</a>'
            for v in verdicts) + "</p>")
    if issuers:
        filters.append("<p>By issuer: " + ", ".join(
            f'<a href="{escape(_issuer_href(i), quote=True)}">{escape(i)}</a>'
            for i in issuers) + "</p>")
    unshown = sum(1 for d in decisions if not d.shown)
    if unshown:
        filters.append(f'<p>Couldn\'t check: <a href="{COULDNT_CHECK}">{unshown} of '
                       f"{len(decisions)} decisions</a></p>")

    body = [
        "<h1>Policy</h1>",
        '<p data-section="what">Every decision onedoor recorded, one row per request. '
        "The verdict is onedoor's own word, exactly as it recorded it -- this console "
        "computes no verdict of its own.</p>",
        couldnt_check_sentence(store),
        "".join(filters),
        '<table><thead><tr><th>request id</th><th>time</th><th>verdict</th>'
        "<th>rule / policy</th><th>issuer</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>" if decisions else
        '<p data-section="none">No decisions have been ingested.</p>',
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>',
        generated_footer(generated_at),
    ]
    return _document("Policy", "\n".join(body))


def _verdict_href(verdict: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in verdict)
    return f"policy-verdict-{safe}.html"


def _issuer_href(issuer: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in issuer)
    return f"policy-issuer-{safe}.html"


#: The filter for decisions whose value cannot be shown. A verdict or
#: issuer filter would place such a row by the very value that is not shown, so it is on
#: none of those, and here instead.
COULDNT_CHECK = "policy-couldnt-check.html"


def render_policy_filtered(decisions: tuple[Decision, ...], title: str,
                          *, generated_at: str, note: str = "") -> str:
    """`note` is the couldn't-check sentence: every filter page names the rows it cannot
    show, since any of them might have belonged on it."""
    rows = "".join(_decision_row_html(d) for d in decisions)
    body = [
        f"<h1>{escape(title)}</h1>",
        note,
        '<table><thead><tr><th>request id</th><th>time</th><th>verdict</th>'
        "<th>rule / policy</th><th>issuer</th></tr></thead>"
        f"<tbody>{rows}</tbody></table>" if decisions else
        '<p data-section="none">No decisions match this filter.</p>',
        '<p><a href="policy.html">all decisions</a></p>',
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>',
        generated_footer(generated_at),
    ]
    return _document(title, "\n".join(body))


def render_decision_detail(d: Decision, store: Store, *, generated_at: str) -> str:
    """Detail view: every recorded field of every row for this request_id, and each
    row's own `decision_digest` (the sha256 of the canonical JSON of the
    row exactly as the export wrote it -- computed from the delivered line's own
    bytes, see `DecisionRow.decision_digest`).

    Each row is checked against its delivery before it is shown -- every copy against the
    export that holds it. A row any stored copy of which differs from
    its delivery shows nothing of itself -- no kind, no fields, no digest, no verdict --
    only "couldn't check: stored record changed since delivery" and the changed copy's name.
    """
    def couldnt_check_line(sentence: str) -> str:
        return f'<p data-state="couldnt-check">{escape(sentence)}</p>'

    rep_problem = d.couldnt_check(d.representative)
    top_line = (
        couldnt_check_line(rep_problem) if rep_problem is not None else
        f'<p data-verdict="{escape(d.verdict or "", quote=True)}">verdict (onedoor\'s own '
        f"word): {escape(d.verdict or '')}</p>")

    sections = []
    for row in d.rows:
        problem = d.couldnt_check(row)
        if problem is not None:
            sections.append(f'<section data-state="couldnt-check">'
                            f"{couldnt_check_line(problem)}</section>")
            continue
        fields_html = "".join(
            f"<tr><td>{escape(str(k))}</td><td><code>{escape(str(v))}</code></td></tr>"
            for k, v in sorted(row.fields.items()))
        sections.append(
            f'<section data-kind="{escape(row.kind or "", quote=True)}">'
            f"<h2>{escape(row.kind or '(no kind)')}</h2>"
            f'<p data-section="digest">decision_digest: '
            f'<span class="mono">{escape(row.decision_digest)}</span></p>'
            f"<table><tbody>{fields_html}</tbody></table>"
            "</section>")
    body = [
        f"<h1>Decision {escape(d.request_id or '')}</h1>",
        top_line,
        "".join(sections),
        '<p><a href="../policy.html">back to Policy</a></p>',
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>',
        generated_footer(generated_at),
    ]
    return _document(f"Decision {d.request_id}", "\n".join(body))


def render_policy_pages(store: Store, *, generated_at: str) -> dict[str, str]:
    """Everything step 3 needs, keyed by the path each page is written at."""
    decisions = all_decisions(store)
    pages = {POLICY: render_policy(store, generated_at=generated_at)}
    for d in decisions:
        if d.request_id is None:
            continue
        pages[_decision_href(d.request_id)] = render_decision_detail(
            d, store, generated_at=generated_at)
    note = couldnt_check_sentence(store)
    for v in sorted({d.verdict for d in decisions if d.verdict}):
        mine = tuple(d for d in decisions if d.verdict == v)
        pages[_verdict_href(v)] = render_policy_filtered(
            mine, f"Policy — verdict: {v}", generated_at=generated_at, note=note)
    for i in sorted({d.issuer for d in decisions if d.issuer}):
        mine = tuple(d for d in decisions if d.issuer == i)
        pages[_issuer_href(i)] = render_policy_filtered(
            mine, f"Policy — issuer: {i}", generated_at=generated_at, note=note)
    unshown = tuple(d for d in decisions if not d.shown)
    if unshown:
        pages[COULDNT_CHECK] = render_policy_filtered(
            unshown, "Policy — couldn't check", generated_at=generated_at, note=note)
    return pages
