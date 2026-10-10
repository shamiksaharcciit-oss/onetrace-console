"""The run receipt.

One page per run, `runs/<key>/receipt.html`, linked from the case page. Every row is derived from the
record or from the console's own verifier run. The anchor row and the "Anchored" pill are the run
page's own "Committed by a known time" rung, read by the viewer from the console's own check, and the
signature row and the "Signed" pill its "Signed by a known recorder" rung, so the pages cannot
disagree. The graph row gives
the verifier's own edge rows from that run, as the verifier wrote them, and nothing where it wrote
none: never a guessed state and never a later version's promise. "Check it yourself" gives the command: no `[crypto]`
and no `--trust`, which belong to signed runs. "What this receipt does not say" is
fixed text, all four lines.
"""
from __future__ import annotations

import json
from onetrace_console.bounded_json import load_json_bounded

from onetrace_console.store import Store, StoredRun
from onetrace_console.words import (escape, generated_footer, named, record_href, run_named,
                                     scroll_region, span_html, verbatim)

RECEIPT = "receipt.html"
TITLE = "The run receipt"
#: What the Recorded row says of the onetrace version, read from the record and never assumed: the
#: version the run's intake stage records (its instrument is `onetrace-intake`), or plainly that the
#: record does not say.
INTAKE_INSTRUMENT = "onetrace-intake"
RECORDED_WITH = "recorded with onetrace {version} (from the run's intake stage)"
NO_SDK_VERSION = "the record does not say which onetrace version made it"
DOES_NOT_SAY = (
    "that the output or the action was correct",
    "why the model wrote what it wrote",
    "that the signing key wasn't misused (your trust list is what ties a key to a name)",
    "that the run was correct at the anchored time (the anchor shows only that the record "
    "existed by then)",
)


def _edge_rows(run: StoredRun, store: Store) -> list[str]:
    """The verifier's own edge rows from the console's run of it, verbatim, in its order."""
    from onetrace_console.checks import _EDGE_ROW
    from onetrace_console.pages import _envelope
    try:
        envelope = _envelope(run, store, required=False)
    except Exception:  # noqa: BLE001 - an unreadable report has no rows to show
        return []
    if envelope is None:
        return []
    return [line.strip() for line in str(envelope.get("stdout", "")).splitlines()
            if _EDGE_ROW.match(line.strip())]


def _counts(run: StoredRun, store: Store) -> tuple[int, int] | None:
    """(checks that passed, checks reported) from the console's own verifier run, or None."""
    from onetrace_console.viewer.report import parse

    from onetrace_console.pages import _envelope
    try:
        envelope = _envelope(run, store, required=False)
        if envelope is None:
            return None
        report = parse(envelope)
    except Exception:  # noqa: BLE001 - an unreadable report gives no count, and says so
        return None
    passed = report.count("pass")
    return passed, passed + report.count("fail") + report.count("not_run")


def _agree(run: StoredRun, store: Store) -> str:
    """Rung 1, as the run page states it: "Records agree" only for a check that held with the
    run's output files required."""
    from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
    from onetrace_console.home import artifacts_required, outputs_required_exit
    if run.check_verdict == HOLDS:
        if artifacts_required(run, store):
            return "Records agree"
        #: The check held, but with the run's output files required it did not.
        if outputs_required_exit(run, store) not in (None, "0"):
            return "Records agree: no"
        #: Not counted as agreeing, and said in the Overview's words (board 1).
        return "Records agree: held without its output files required"
    if run.check_verdict == CONTRADICTS:
        return "Records agree: no"
    if run.check_verdict == COULD_NOT_CHECK:
        from onetrace_console.checks import PREVIEW_REASON
        #: A preview-format run says why, in the fixed words.
        if run.check_note == PREVIEW_REASON:
            return f"Records agree: couldn't check. {PREVIEW_REASON}"
        return "Records agree: couldn't check"
    return "Records agree: not checked"


def _outputs(run: StoredRun, store: Store) -> tuple[int, int]:
    """(outputs present and matching their receipts, outputs the receipts record): item 7's check."""
    from onetrace_console.stage_pages import _artifact_path, _files, _read, _steps, _verified
    files = _files(run, store)
    matched = total = 0
    for step in _steps(run, store):
        for out in step["receipt"].get("outputs") or []:
            if not isinstance(out, dict):
                continue
            total += 1
            blob = _read(files, store, _artifact_path(step["file"], str(out.get("name", ""))))
            matched += _verified(blob, str(out.get("digest", "")))
    return matched, total


def _rung_said(rung) -> tuple[str, str]:
    """(the state word, "state · evidence") of a viewer rung, in the run page's own words."""
    from onetrace_console.viewer.page import _line, _t
    state = _t(rung.state_key)
    return state, f"{state} · " + " ".join(_line(e) for e in rung.evidence)


def _recorded_with(steps: list[dict]) -> str:
    """The onetrace version the run's intake stage records, in the Recorded row's words."""
    for step in steps:
        instrument = step["receipt"].get("instrument")
        if isinstance(instrument, dict) and instrument.get("id") == INTAKE_INSTRUMENT:
            version = instrument.get("version")
            if isinstance(version, str) and version.strip():
                return RECORDED_WITH.format(version=version.strip())
    return NO_SDK_VERSION


def _row(name: str, label: str, value: str) -> str:
    return f'<tr data-row="{name}"><th>{escape(label)}</th><td>{value}</td></tr>'


def render_receipt(run: StoredRun, store: Store, *, generated_at: str, anchored, signed) -> str:
    """`anchored` and `signed`: the run page's "Committed by a known time" and "Signed by a known
    recorder" rungs, from the same model."""
    from onetrace_console.render import _document, _recorded_of_declared
    from onetrace_console.stage_pages import _files, _read, _stage_name, _steps
    files = _files(run, store)
    raw = _read(files, store, "MANIFEST.json") or b""
    manifest_text = raw.decode("utf-8", errors="backslashreplace")
    try:
        manifest = load_json_bounded(manifest_text, "MANIFEST.json", "show")
    except ValueError:
        manifest = {}
    steps = _steps(run, store)
    edges = manifest.get("edges") if isinstance(manifest, dict) else None
    links = (f"{len(edges)} links" if isinstance(edges, list)
             else "recorded as a straight line (no graph recorded)")
    matched, total = _outputs(run, store)
    model = []
    for step in steps:
        instrument = step["receipt"].get("instrument")
        if isinstance(instrument, dict) and instrument.get("rederivable") == "false":
            note = instrument.get("rederivable_note")
            model.append(f"{named(_stage_name(step['receipt']))}: declared not re-runnable"
                         + (f" — <q data-words=\"record\">{escape(note)}</q>"
                            if isinstance(note, str) and note else ""))
    times = [t for s in steps for t in (s["receipt"].get("time") or {}).values()
             if isinstance(t, str)]
    recorded = span_html(min(times), max(times)) if times else "no time recorded"
    counts = _counts(run, store)
    pills = escape(_agree(run, store)) + (
        f" · {counts[0]} of {counts[1]} checks" if counts else " · the check report could not be read")
    anchor_state, anchor_said = _rung_said(anchored)
    signed_state, signed_said = _rung_said(signed)
    href = record_href(run)
    rows = "".join((
        _row("run", "Run", run_named(store, run.key)),
        _row("format", "Format", f'<span class="mono">{escape(run.format)}</span>'),
        _row("stages", "Stages", escape(_recorded_of_declared(run))),
        _row("graph", "The graph", " · ".join([escape(f"{len(steps)} nodes · {links}"),
                                               *(f'<q data-words="check">{escape(row)}</q>'
                                                 for row in _edge_rows(run, store))])),
        _row("chain-head", "Chain head", f'<span class="mono">{escape(run.chain_head)}</span>'),
        _row("outputs", "Output files",
             escape(f"{matched} of {total} present and matching their receipts")),
        _row("model-stages", "Model stages", "<br>".join(model) or "none declared"),
        _row("authorization", "Authorization", "no authorization records"),
        _row("recorded", "Recorded", f"{recorded} · {escape(_recorded_with(steps))}"),
        _row("signature", "Signature", signed_said),
        _row("anchor", "Anchor", anchor_said),
    ))
    body = (
        '<div class="cp">'
        f"<h1>{escape(TITLE)}</h1>"
        f'<p data-section="pills">{pills} · Signed: {signed_state} · '
        f"Anchored: {anchor_state}</p>"
        + scroll_region(f'<table class="timeline" data-section="receipt">{rows}</table>',
                        "The receipt, scrolls sideways", "receipt")
        + '<details data-section="view-json"><summary>View JSON</summary>'
        f'<pre data-section="manifest">{verbatim(manifest_text)}</pre></details>'
        '<section data-section="check-yourself"><h2>Check it yourself</h2>'
        f'<p>Download <a href="{escape(href, quote=True)}" download>this run\'s record</a>, '
        "unpack it, and in its folder run:</p>"
        "<pre><code>pip install onetrace-verify\n"
        "onetrace-verify --require-artifacts .</code></pre>"
        "<p>It runs offline, with no account.</p></section>"
        '<section data-section="does-not-say"><h2>What this receipt does not say</h2>'
        '<ul class="plain">' + "".join(f"<li>{escape(line)}</li>" for line in DOES_NOT_SAY)
        + "</ul></section>"
        '<p data-section="back"><a href="case.html">The run, step by step</a></p>'
        + generated_footer(generated_at)
        + "</div>")
    return _document(TITLE, body)


def receipt_link(case_html: str) -> str:
    """The case page with a link to the run's receipt, beside the link to its authorization page
    in the Policy section -- where the run's own summary links already are. Refused, as that one
    is, when the section is not there."""
    import re
    policy = re.search(r'<section data-section="policy">.*?(</section>)', case_html, re.S)
    if policy is None:
        raise ValueError("cannot link the run receipt: the case page has no Policy section")
    if 'data-section="receipt-link"' in policy.group(0):
        return case_html
    link = (f'<p data-section="receipt-link"><a href="{RECEIPT}">{escape(TITLE)}</a></p>')
    at = policy.start(1)
    return case_html[:at] + link + case_html[at:]
