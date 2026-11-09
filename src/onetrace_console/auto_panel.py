"""The zero-configuration panel: what onetrace-auto recorded about a run it made without the app
naming any stage -- the libraries it hooked, the boundaries of what it saw, and each gap where a call
went ahead unrecorded -- and onetrace-verify's own rows about it.

onetrace 0.7 (format 0.4, onetrace's `docs/format.md`) gives such a run's manifest an `auto` block:
its `boundary` and its `hooks`, each a `library`, a `status` and, for a hooked library, its `version`.
The manifest may also hold `boundaries` (each a `kind`, a `name` and a `note`) and `gaps` (each a
`stage`, an `index` and a `reason`); the close receipt's `emission.gaps` holds the same gaps. The panel
shows exactly those, in the record's words, each gap once. A run with no `auto` block, no boundaries
and no gaps shows nothing new.

What is checked is the verifier's: its `auto:` rows, PASS, FAIL or NOT-RUN with the row's own detail,
read from the run's stored check (`--json`). Nothing here infers a call the record does not hold.
"""
from __future__ import annotations

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

HEADING = "Recorded without configuration"
LEAD = ("This run was recorded by onetrace-auto, which hooks libraries rather than steps the app "
        "names. What it hooked, what it could not see and where a call was not recorded, in the "
        "record's own words:")
HOOKS = "Libraries"
BOUNDARY = "Boundary"
BOUNDARIES = "Boundaries"
GAPS = "Gaps"
NO_GAP = "The record names no gap."
ROWS_LEAD = "onetrace-verify's own rows about it:"
ROWS_NONE = "This run's check holds no rows about it."
#: The verifier's own row names (onetrace-verify 0.7.1).
ROW_PREFIX = "auto: "


def _dicts(v) -> list[dict]:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _s(v) -> str:
    return v if isinstance(v, str) else ("" if v is None else str(v))


def gaps(manifest: dict, receipts: list[dict]) -> list[dict]:
    """The run's gaps, each once, in the order the record first holds it: the manifest's, then any
    a receipt's `emission.gaps` holds that the manifest does not."""
    out, seen = [], set()
    sources = [manifest.get("gaps")] + [(r.get("emission") or {}).get("gaps") if isinstance(r.get("emission"), dict)
                                        else None for r in receipts]
    for src in sources:
        for g in _dicts(src):
            key = (_s(g.get("stage")), _s(g.get("index")), _s(g.get("reason")))
            if key not in seen:
                seen.add(key)
                out.append(g)
    return out


def rows(envelope: dict | None) -> list[dict]:
    """The verifier's `auto:` rows from the stored check's `--json`, in its order."""
    part = envelope.get("rows_json") if isinstance(envelope, dict) else None
    try:
        doc = load_json_bounded(part.get("stdout", ""), "the check's rows") if isinstance(part, dict) else None
    except (ValueError, RecursionError):
        return []
    found = doc.get("rows") if isinstance(doc, dict) else None
    return [r for r in found or [] if isinstance(r, dict) and str(r.get("name", "")).startswith(ROW_PREFIX)]


_TONE = {"PASS": "ok", "FAIL": "bad", "NOT-RUN": "cc"}


def _rows_block(found: list[dict]) -> str:
    if not found:
        return f'<p data-auto="rows-none">{escape(ROWS_NONE)}</p>'
    items = "".join(
        f'<li data-auto-row="{escape(_s(r.get("result")))}"><span class="pill {_TONE.get(r.get("result"), "neu")}">'
        f'{escape(_s(r.get("result")))}</span> {escape(_s(r.get("name")))}'
        + (f' <span class="reason">— {escape(_s(r.get("detail")))}</span>' if _s(r.get("detail")) else "")
        + "</li>" for r in found)
    return f'<p>{escape(ROWS_LEAD)}</p><ul class="plain" data-auto="rows">{items}</ul>'


def _words(text: str) -> str:
    return f'<span data-words="record">{escape(text)}</span>'


def run_section(manifest: dict, receipts: list[dict], envelope: dict | None) -> str:
    """The run page's zero-configuration section; empty for a run whose manifest has no `auto` block,
    no boundaries and no gaps. `receipts` is every receipt of the chain, the close receipt included."""
    auto = manifest.get("auto") if isinstance(manifest.get("auto"), dict) else None
    bounds, found = _dicts(manifest.get("boundaries")), gaps(manifest, receipts)
    if auto is None and not bounds and not found:
        return ""
    parts = [f'<h2>{escape(HEADING)}</h2><p class="reported">{escape(LEAD)}</p>']
    if auto is not None:
        if _s(auto.get("boundary")):
            parts.append(f'<p data-auto="boundary">{escape(BOUNDARY)}: {_words(_s(auto["boundary"]))}</p>')
        hooks = "".join(
            f'<li data-auto-hook="{escape(_s(h.get("status")))}"><code>{_words(_s(h.get("library")))}</code>'
            + (f' {_words(_s(h["version"]))}' if _s(h.get("version")) else "")
            + f' — {_words(_s(h.get("status")))}</li>' for h in _dicts(auto.get("hooks")))
        parts.append(f'<h3>{escape(HOOKS)}</h3><ul class="plain" data-auto="hooks">{hooks}</ul>')
    if bounds:
        items = "".join(
            f'<li data-auto-boundary><code>{_words(_s(b.get("name")))}</code> — '
            f'{_words(_s(b.get("kind")))}: {_words(_s(b.get("note")))}</li>' for b in bounds)
        parts.append(f'<h3>{escape(BOUNDARIES)}</h3><ul class="plain" data-auto="boundaries">{items}</ul>')
    items = "".join(
        f'<li data-auto-gap><code>{_words(_s(g.get("stage")))}</code> #{_words(_s(g.get("index")))} — '
        f'{_words(_s(g.get("reason")))}</li>' for g in found)
    parts.append(f'<h3>{escape(GAPS)}</h3>'
                 + (f'<ul class="plain" data-auto="gaps">{items}</ul>' if found
                    else f'<p data-auto="gaps-none">{escape(NO_GAP)}</p>'))
    parts.append(_rows_block(rows(envelope)))
    return f'<section data-section="auto" class="auto">{"".join(parts)}</section>'
