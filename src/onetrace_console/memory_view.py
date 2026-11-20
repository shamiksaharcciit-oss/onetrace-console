"""A run's memory: what each step read from a store and wrote to one, in the run's order, and which other runs wrote
what it read.

`runs/<key>/memory.html`, for a run whose record holds format 0.5's `state_reads` or `state_writes` on any step (an
agent's memory is a store like any other, `ot.state.read` and `ot.state.write` as onetrace 0.9 records them):

- **The timeline**: one row an entry, the run's steps in order, each read before its step's writes: the step (linked to
  its page), read or written, the store as the team named it and its kind, the key by its digest (in plain only where
  the record keeps it so), the value's digest with its form (or `found: false`, or the record's `digest_status`), and
  the store's version ("not observed" in those words).
- **Across runs**, under each step that read: "read what <run> wrote", each run whose indexed write holds, for the
  read's store and key, an equal digest or version (`store_state`'s lineage, from the run index the pages are drawn
  with).
- **What it does not show**, in the store hooks' own words (`store_state.NON_CLAIMS`).

The page links the run's other pages: its steps, its model calls' own pages and its Authorization page, where it has
them. Nothing here is the console's own reading: every value is the record's.
"""

from __future__ import annotations

from onetrace_console.words import escape

PAGE = "memory.html"
TAB = "Memory"
TITLE = "Memory"
LEAD = (
    "What each step read from a store and wrote to one, in the run's order, as its record holds it, and the other runs "
    "that wrote what it read, by an equal digest or version."
)
NOT_OBSERVED = "not observed"


def holds_state(receipts: list[dict]) -> bool:
    """Whether any step's receipt holds a state member: the run has a memory page."""
    return any(
        isinstance(r.get("state_reads"), list) or isinstance(r.get("state_writes"), list)
        for r in receipts
        if isinstance(r, dict)
    )


def _value(e: dict) -> str:
    if str(e.get("found")) == "false":
        return "found nothing"
    if e.get("digest"):
        from onetrace_console.viewer.page import fingerprint_html

        form = f" ({escape(str(e['digest_form']))})" if e.get("digest_form") else ""
        return f'<span class="mono">{fingerprint_html(str(e["digest"]))}</span>{form}'
    if e.get("digest_status"):
        return escape(str(e["digest_status"]))
    return NOT_OBSERVED


def _key(e: dict) -> str:
    from onetrace_console.viewer.page import fingerprint_html

    if isinstance(e.get("key"), str):
        return f'<span class="mono">{escape(e["key"])}</span>'
    return f'<span class="mono">{fingerprint_html(str(e.get("key_digest", "")))}</span>'


def _row(step: dict, side: str, e: dict, href: str) -> str:
    version = str(e.get("version", NOT_OBSERVED))
    kind = f" ({escape(str(e['version_kind']))})" if e.get("version_kind") else ""
    return (
        f'<tr data-memory="{side}"><td><a href="{escape(href, quote=True)}">{escape(str(step["index"]))} · '
        f'<span class="mono">{escape(step["name"])}</span></a></td><td>{"read" if side == "read" else "written"}</td>'
        f'<td><span class="mono">{escape(str(e.get("store", "")))}</span> ({escape(str(e.get("store_kind", "")))})</td>'
        f"<td>{_key(e)}</td><td>{_value(e)}</td><td>{escape(version)}{kind}</td></tr>"
    )


def render_memory(run, store, *, generated_at: str, links: str = "") -> str | None:
    """The run's memory page, or None where no step's receipt holds a state member. `links`: the run's other pages,
    as the run's tab row gives them."""
    from onetrace_console.render import _document
    from onetrace_console.stage_pages import _receipts, _stage_name, stage_page
    from onetrace_console.store_state import NON_CLAIMS, _lineage
    from onetrace_console.words import generated_footer, scroll_region

    steps = _receipts(run, store)
    if not holds_state([s["receipt"] for s in steps]):
        return None
    rows, across = [], []
    for s in steps:
        receipt = s["receipt"]
        step = {"index": s["index"], "name": _stage_name(receipt)}
        href = stage_page(str(s["index"]))
        for side, member in (("read", "state_reads"), ("written", "state_writes")):
            for e in receipt.get(member) or []:
                if isinstance(e, dict):
                    rows.append(_row(step, side, e, href))
        lineage = _lineage(receipt, run.key)
        if lineage:
            across.append(
                f'<div data-memory-step="{escape(str(s["index"]), quote=True)}"><h3>Step {escape(str(s["index"]))} · '
                f'<span class="mono">{escape(step["name"])}</span></h3>{lineage}</div>'
            )
    table = scroll_region(
        '<table class="board" data-section="memory-timeline"><thead><tr><th>Step</th><th>Read or written</th>'
        "<th>Store</th><th>Key</th><th>Value</th><th>Version</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>",
        "The run's memory, step by step",
        "memory-timeline",
    )
    body = (
        '<div class="cp" data-view="memory">'
        f'<p class="crumbs" data-section="crumbs"><a href="../../executions-all.html">Runs</a> / '
        f'<a href="case.html"><span class="mono">{escape(run.run_id)}</span></a> / {escape(TITLE)}</p>'
        f'<h1>{escape(TITLE)} · <span class="mono">{escape(run.run_id)}</span></h1>'
        f"<p>{escape(LEAD)}</p>{links}"
        f'<section data-section="memory"><h2>The timeline</h2>{table}</section>'
        + (
            f'<section data-section="memory-across"><h2>Across runs: who wrote what it read</h2>{"".join(across)}'
            "</section>"
            if across
            else ""
        )
        + f'<p class="nonclaim" data-memory-nonclaim>{escape(NON_CLAIMS)}</p>'
        + generated_footer(generated_at)
        + "</div>"
    )
    return _document(f"{TITLE} · {run.run_id}", body)


def links(run, store) -> str:
    """The run's other pages a memory page points at: its steps' model-call pages and its Authorization page."""
    from onetrace_console import model_call as mc
    from onetrace_console import model_call_pages
    from onetrace_console.stage_pages import _receipts

    out = []
    for s in _receipts(run, store):
        for o in mc.outputs(s["receipt"]):
            out.append(
                f'<a href="{model_call_pages.base_name(str(s["index"]), str(o["name"]))}.html">'
                f"The model call at step {escape(str(s['index']))}</a>"
            )
    #: Every run has its Authorization page, which says where none of its steps is gated.
    out.append('<a href="authorization.html">Authorization</a>')
    return f'<p data-section="memory-links">{" · ".join(out)}</p>' if out else ""
