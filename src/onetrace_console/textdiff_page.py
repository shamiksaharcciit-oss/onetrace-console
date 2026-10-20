"""The text diff on a page of its own: two panes, as the TextDiff board draws them.

The Diff page's text-diff section shows each stage's diff folded, in the SDK's order. This page is
the same document -- the comparison's own stored run of `onetrace diff A B --text --json`, read
strictly by `textdiff_view` and drawn by it as the SDK wrote it -- laid out for reading one output at
a time:

- the left pane lists what changed, from the first difference on (each stage's outputs, in the
  SDK's order), each linked to its diff on the right, and below it the inputs the SDK says changed,
  in its own words;
- the right pane holds each of those outputs' diffs, as the Diff page draws them, verified only.

It says nothing the document does not: no count, line or verdict of its own. A comparison whose
text diff was not kept, can't be read, was not shown, or has no first difference has no such page,
and its Diff page offers none.
"""
from __future__ import annotations

from html import escape

from onetrace_console.store import Store

#: This page beside the comparison's Diff page: diff/<key>-text.html.
SUFFIX = "-text.html"
TITLE = "Text diff"
#: The board's words, fixed as written.
SHOWN_ONLY = ("Shown only for outputs whose bytes match their receipts in both runs. The diff never "
              "changes a verdict.")
FROM_SDK = ("Line numbers, positions and counts come from the SDK's text-diff document, unchanged.")
NOT_WHICH = "A text diff shows what changed between two verified outputs. It doesn't say which answer is right."
CHANGED = "Changed, from the first difference on"
INPUTS = "Inputs that changed"
OPEN = "Open the text diff on its own page"
#: The verdicts whose outputs the left pane lists: the first difference and what follows it.
LISTED = ("FIRST DIFFERENCE", "downstream")


def page_name(comparison) -> str:
    return f"{comparison.key}{SUFFIX}"


def shown_document(comparison, store: Store) -> dict | None:
    """The comparison's text diff, read strictly, where it was kept, can be read, was shown and
    has a first difference; None otherwise -- and then there is no page (an identical pair's text
    diff has nothing to list)."""
    from onetrace_console.compare import text_diff_raw
    from onetrace_console.kept_inputs import for_this_console
    from onetrace_console.textdiff_view import TextDiffUnreadable, read_textdiff
    from onetrace_console.records import unchecked_sides
    if unchecked_sides(comparison, store):
        return None
    found = text_diff_raw(comparison, store)
    if found is None:
        return None
    try:
        doc = for_this_console(read_textdiff(found[0]), comparison, store)
    except TextDiffUnreadable:
        return None
    return doc if doc["shown"] and any(n["verdict"] == "FIRST DIFFERENCE" for n in doc.get("nodes", [])) else None


def _listed(doc: dict) -> list[tuple[str, str, dict]]:
    """(anchor, stage, output) for each output of a stage from the first difference on."""
    out = []
    for node in doc.get("nodes", []):
        if node["verdict"] not in LISTED:
            continue
        for output in node["outputs"]:
            out.append((f"output-{len(out) + 1}", node["node"], output))
    return out


def render_text_diff_page(comparison, store: Store, *, generated_at: str) -> str | None:
    """The page, or None where the comparison has no shown text diff."""
    from onetrace_console.render import _document, _limit_sentence
    from onetrace_console.textdiff_view import _is_fingerprint, _render_output, _settings_line
    from onetrace_console.words import generated_footer, run_named
    doc = shown_document(comparison, store)
    if doc is None:
        return None
    listed = _listed(doc)
    first = next((n for n in doc.get("nodes", []) if n["verdict"] == "FIRST DIFFERENCE"), None)
    #: The first difference's settings a reader can read, in the Diff page's words; its recorded
    #: fingerprints stay on the Diff page, under its Details.
    settings = [s for s in (first["settings"] if first else []) if s.startswith(" ") and not _is_fingerprint(s)]
    said = " · ".join(_settings_line(s.strip()) for s in settings)
    pair = (f"{run_named(store, comparison.run_a)} → {run_named(store, comparison.run_b)}")
    parts = [
        f'<p class="crumbs" data-section="crumbs"><a href="../comparisons.html">Comparisons</a> / '
        f'<a href="{escape(comparison.key)}.html">{pair}</a> / {escape(TITLE)}</p>',
        f'<div class="title"><h1>{escape(TITLE)}'
        + (f" · {escape(first['node'])}" if first else "") + "</h1></div>",
    ]
    if "first_line" in doc:
        parts.append(f'<p data-first-line>{escape(doc["first_line"])}</p>')
    parts.append(f'<p class="sub" data-section="text-diff-settings">'
                 + (f"Settings: {said} · " if said else "") + f"{escape(SHOWN_ONLY)}</p>")
    items = "".join(f'<li data-listed="{a}"><a href="#{a}">{escape(stage)} · '
                    f'<span class="mono">{escape(o["name"] or "")}</span></a></li>'
                    for a, stage, o in listed)
    inputs = list(dict.fromkeys(s for n in doc.get("nodes", []) if n["verdict"] in LISTED for s in n["inputs"]))
    left = (f'<section class="side" data-section="changed"><h2>{escape(CHANGED)}</h2>'
            + (f'<ul class="plain">{items}</ul>' if items else "<p>No output of these stages is listed.</p>")
            + (f'<h3>{escape(INPUTS)}</h3>' + "".join(f"<p data-input>{escape(s)}</p>" for s in inputs)
               if inputs else "")
            + "</section>")
    #: Each kept text input's line diff, as the comparison page draws it, beside the outputs.
    from onetrace_console.kept_inputs import KEPT_DIFFS
    from onetrace_console.textdiff_view import _render_kept
    kept = "".join(f'<div data-pane-output><h3>{escape(n["node"])}</h3>{_render_kept(n["node"], *k[1:])}</div>'
                   for n in doc.get("nodes", []) if n["verdict"] in LISTED for k in n.get(KEPT_DIFFS) or ())
    right = ('<section data-section="outputs" data-textdiff="shown">' + kept
             + "".join(f'<div id="{a}" data-pane-output><h3>{escape(stage)}</h3>{_render_output(o)}</div>'
                       for a, stage, o in listed)
             + f'<p class="note">{escape(FROM_SDK)}</p><p class="note">{escape(NOT_WHICH)}</p></section>')
    parts.append(f'<div class="io">{left}{right}</div>')
    parts.append(f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>')
    parts.append(generated_footer(generated_at))
    return _document(TITLE, '<div class="cp" data-view="text-diff">' + "".join(parts) + "</div>")
