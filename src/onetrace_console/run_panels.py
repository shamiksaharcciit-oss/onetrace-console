"""What onetrace 0.5 records about a run, on its page and its steps' pages: the gated steps and their
decisions (`onedoor_panel`), the span context (`trace_panel`), and steps and runs inside steps
(`nesting_view`). Each section is spliced into the viewer's run page before it is sealed, as the
console's other blocks are; a run that records none of these gets no new section.

The decisions, the span context and the nesting are read from the record's contents, so on a run
whose records contradict themselves they go to "Proof" with the steps (`views.RUN_READ_FROM`). The
verifier's own decision rows are a check, not the record's contents: they stay on "What changed".
"""
from __future__ import annotations

from onetrace_console import model_call, nesting_view, onedoor_panel, trace_panel
from onetrace_console.bounded_json import load_json_bounded

#: The viewer's section the new ones are placed before, on every run page.
BEFORE = '<section data-section="reproduce"'


def manifest_of(run, store) -> dict:
    from onetrace_console.stage_pages import _files, _read
    raw = _read(_files(run, store), store, "MANIFEST.json")
    try:
        m = load_json_bounded(raw.decode("utf-8"), "MANIFEST.json") if raw else {}
    except (ValueError, UnicodeDecodeError, RecursionError):
        return {}
    return m if isinstance(m, dict) else {}


def held_runs(store, up: str = "../") -> dict[str, str]:
    """{run id: the href of its page from a run's page} for each run the console holds."""
    return {r.run_id: f"{up}{r.key}/case.html" for r in store.runs() if r.run_id}


def sections(run, store) -> str:
    """The run page's new sections, in order: gated steps and the verifier's decision rows; the span
    context; steps inside steps. Empty for a run with none of them."""
    from onetrace_console.frame import rendering_public, tracing_link
    from onetrace_console.home import _envelope
    from onetrace_console.stage_pages import _steps
    manifest, steps = manifest_of(run, store), _steps(run, store)
    gated = onedoor_panel.run_section(manifest, steps)
    rows = ""
    if gated:
        #: The decisions themselves, then the verifier's rows about them in a section of their own.
        rows = (f'<section data-section="onedoor-rows" class="onedoor"><h2>{onedoor_panel.ROWS_HEADING}</h2>'
                f'{onedoor_panel.rows_block(onedoor_panel.decision_rows(_envelope(run, store)))}</section>')
    held = held_runs(store)
    return (nesting_view.parent_section(manifest, held) + gated + rows
            + trace_panel.run_section(manifest, steps, tracing_link(), public=rendering_public())
            + nesting_view.run_section(steps, held))


def with_sections(case_html: str, run, store) -> str:
    """The case page with the new sections before the viewer's "What could be re-checked". Refused,
    as the console's other blocks are, when that section is not there."""
    added = sections(run, store)
    if not added:
        return case_html
    at = case_html.find(BEFORE)
    if at < 0:
        raise ValueError("cannot place the run's decisions, span context or nesting: the case page "
                         "has no \"What could be re-checked\" section")
    return case_html[:at] + added + case_html[at:]


def step_blocks(manifest: dict, receipt: dict, run_has_spans: bool, held: dict[str, str],
                receipt_file: str = "", read_file=None, same_files=None) -> str:
    """One step's page: its decisions, its span ids (or "ran outside any span", where the run has a
    span context), its children and nested runs, and its model-call records (`read_file(path)`: the
    run's stored bytes at a path, or None; `same_files(value)`: the other runs whose records name the
    same model files)."""
    from onetrace_console.frame import tracing_link
    from onetrace_console.words import escape
    name = nesting_view._name(receipt)
    out = onedoor_panel.step_block(name, receipt, name in onedoor_panel.gated_stages(manifest))
    if out:
        out = f'<section data-section="onedoor" class="onedoor">{out}</section>'
    t = trace_panel.trace_of(receipt)
    if t is not None:
        link = trace_panel.link(tracing_link(), t["trace_id"], t["span_id"])
        out += (f'<section data-section="span-context" class="span-context"><p class="reported">'
                f'{escape(trace_panel.SPAN_LEAD)}</p><ul class="plain">'
                + trace_panel._id("trace id", t["trace_id"], link) + trace_panel._id("span id", t["span_id"], "")
                + "</ul></section>")
    elif run_has_spans:
        out += (f'<section data-section="span-context" class="span-context"><p>This step '
                f'{escape(trace_panel.OUTSIDE)}.</p></section>')
    nest = nesting_view.run_section([{"receipt": receipt}], held)
    calls = model_call.step_section(receipt, receipt_file, read_file, same_files) if read_file is not None else ""
    return out + nest + calls
