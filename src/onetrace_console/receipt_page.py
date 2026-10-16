"""The run receipt.

One page per run, `runs/<key>/receipt.html`, linked from the case page. Every row is derived from the
record or from the console's own verifier run. The anchor row and the "Anchored" pill are the run
page's own "Committed by a known time" rung, read by the viewer from the console's own check, and the
signature row and the "Signed" pill its "Signed by a known recorder" rung, so the pages cannot
disagree. The graph row gives
the verifier's own edge rows from that run, as the verifier wrote them, and nothing where it wrote
none: never a guessed state and never a later version's promise. "Check it yourself" gives the
command this run needs, read from what its record carries: `[crypto]` and `--trust trust.json` (a
trust file in the onetrace-trust/0.1 format) where it carries a signature, and the time-stamp
authority's files, or the block headers, where it carries an anchor of that method; and below it,
in the black box, what the console's own run of the verifier printed, as it wrote it. "What this
receipt does not say" is fixed text, all four lines.
"""
from __future__ import annotations

import json
from onetrace_console.bounded_json import load_json_bounded

from onetrace_console.store import Store, StoredRun
from onetrace_console.viewer.page import fingerprint_html
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


def _public_record_note() -> str:
    """On a public console: its downloads leave out kept inputs (`ingest.bundle`)."""
    from onetrace_console.frame import rendering_public
    from onetrace_console.kept_inputs import PUBLIC_RECORD
    return f'<p class="note" data-section="public-record">{escape(PUBLIC_RECORD)}</p>' if rendering_public() else ""


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
    """Rung 1, as the run page states it (`records.state`), with the reason where there is one."""
    from onetrace_console import records
    from onetrace_console.checks import PREVIEW_REASON
    state, why = records.state(run, store), records.why(run, store)
    words = {records.YES: "yes", records.NO: "no", records.COULDNT: "couldn't check",
             records.NOT_CHECKED: "not checked", records.NO_VERDICT: "no verdict recorded"}[state]
    if why:
        return f"Records agree: {words} ({why})"
    #: A preview-format run says why, in the fixed words.
    if state == records.COULDNT and run.check_note == PREVIEW_REASON:
        return f"Records agree: {words}. {PREVIEW_REASON}"
    return f"Records agree: {words}"


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


#: The check's own reach, in the ruled words: it makes no network calls ("offline" is not said).
NO_NETWORK = "The check makes no network calls and needs no account."
TRUST_FILE = "trust.json"
TRUST_NOTE = ("trust.json is the signing keys you trust, each with your label for it, in the "
              "onetrace-trust/0.1 format: ")
TRUST_SHAPE = '{"format": "onetrace-trust/0.1", "keys": [{"key_id": "...", "label": "..."}]}'
TSA_NOTE = ("tsa-cert.pem and tsa-root.pem are the time-stamp authority's certificate you trust and "
            "the root it chains to.")
HEADERS_NOTE = "headers.json is the Bitcoin block headers for the run's OpenTimestamps anchor."
OUTPUT_HEAD = "What the check printed"
OUTPUT_LEAD = ("This console's own run of the verifier over the stored record, at {at}: {command}, "
               "exit {exit}. File paths are shortened to their names; the output is as it wrote it, "
               "a row longer than the page shows cut with the count of what is left out.")
NO_OUTPUT = "The check's output could not be read, so none is shown."


def _anchor_methods(run: StoredRun, store: Store) -> set[str]:
    """The method each anchor in the record names (`anchors/*.json`), as recorded."""
    methods = set()
    for path, key in run.listing:
        if path.startswith("anchors/") and path.endswith(".json"):
            try:
                method = load_json_bounded(store.get(key).decode("utf-8"), path).get("method")
            except Exception:  # noqa: BLE001 - an anchor this can't read names no method here
                continue
            if isinstance(method, str):
                methods.add(method)
    return methods


def _command(run: StoredRun, store: Store) -> tuple[str, list[str]]:
    """(the commands, the notes under them) this run's check needs, from what its record carries."""
    signed = any(path.startswith("signatures/") for path, _ in run.listing)
    methods = _anchor_methods(run, store)
    crypto = signed or bool(methods)
    args, notes = ["--require-artifacts"], []
    if signed:
        args += ["--trust", TRUST_FILE]
        notes.append(escape(TRUST_NOTE) + f'<code>{escape(TRUST_SHAPE)}</code>')
    if "rfc3161" in methods:
        args += ["--tsa-cert", "tsa-cert.pem", "--tsa-root", "tsa-root.pem"]
        notes.append(escape(TSA_NOTE))
    if "opentimestamps" in methods:
        args += ["--headers", "headers.json"]
        notes.append(escape(HEADERS_NOTE))
    install = 'pip install "onetrace-verify[crypto]"' if crypto else "pip install onetrace-verify"
    return f"{install}\nonetrace-verify {' '.join(args)} .", notes


def _printed(run: StoredRun, store: Store) -> str:
    """The black box: the console's own run of the verifier, its output verbatim."""
    from pathlib import PurePath

    from onetrace_console.pages import _envelope
    from onetrace_console.words import time_html
    try:
        envelope = _envelope(run, store, required=False)
    except Exception:  # noqa: BLE001 - said, never guessed
        envelope = None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("stdout"), str):
        return (f'<section data-section="printed"><h3>{escape(OUTPUT_HEAD)}</h3>'
                f"<p>{escape(NO_OUTPUT)}</p></section>")
    command = " ".join(PurePath(a).name if ("/" in a or "\\" in a) else a
                       for a in envelope.get("command") or [] if isinstance(a, str))
    lead = escape(OUTPUT_LEAD).replace("{at}", time_html(str(envelope.get("ran_at", ""))))
    lead = lead.replace("{command}", f"<code>{escape(command)}</code>")
    lead = lead.replace("{exit}", escape(str(envelope.get("exit_status", ""))))
    #: Drawn as the run page draws the verifier's rows: each row whole up to the viewer's cap, a
    #: longer one cut with the viewer's own marker; the whole row stays in the stored report.
    from onetrace_console.viewer.page import _escape_rows
    out = envelope["stdout"].replace("\r\n", "\n")
    return (f'<section data-section="printed"><h3>{escape(OUTPUT_HEAD)}</h3><p>{lead}</p>'
            + scroll_region(f'<pre class="term" data-section="verifier-output">{_escape_rows(out)}</pre>',
                            "What the check printed, scrolls", "printed")
            + "</section>")


def _crumbs(run: StoredRun, store: Store) -> str:
    from onetrace_console.stage_pages import _crumbs as stage_crumbs
    return stage_crumbs(run, store).replace("/ Inputs &amp; outputs</p>", "/ Receipt</p>")


def _row(name: str, label: str, value: str) -> str:
    return f'<tr data-row="{name}"><th>{escape(label)}</th><td>{value}</td></tr>'


def render_receipt(run: StoredRun, store: Store, *, generated_at: str, anchored, signed,
                   agree=None) -> str:
    """`anchored`, `signed` and `agree`: the run page's "Committed by a known time", "Signed by a
    known recorder" and "Records agree" rungs, from the same model; each pill takes its rung's
    tone by the one colour rule (neutral where no rung is given)."""
    from onetrace_console import tones
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
    agreed = escape(_agree(run, store)) + (
        f" · {counts[0]} of {counts[1]} checks" if counts else " · the check report could not be read")
    anchor_state, anchor_said = _rung_said(anchored)
    signed_state, signed_said = _rung_said(signed)

    def pill(rung, words: str) -> str:
        tone = tones.tone(tones.RUNG, rung.state) if rung is not None else tones.TONE[tones.NOT_MADE]
        return f'<span class="pill {tone}">{words}</span>'
    #: The chips keep the " · " between them: the line reads as one line, copied or read aloud.
    pills = " · ".join((pill(agree, agreed), pill(signed, f"Signed: {signed_state}"),
                      pill(anchored, f"Anchored: {anchor_state}")))
    command, notes = _command(run, store)
    href = record_href(run)
    rows = "".join((
        _row("run", "Run", run_named(store, run.key)),
        _row("format", "Format", f'<span class="mono">{escape(run.format)}</span>'),
        _row("stages", "Stages", escape(_recorded_of_declared(run))),
        _row("graph", "The graph", " · ".join([escape(f"{len(steps)} nodes · {links}"),
                                               *(f'<q data-words="check">{escape(row)}</q>'
                                                 for row in _edge_rows(run, store))])),
        _row("chain-head", "Chain head", fingerprint_html(run.chain_head)),
        _row("outputs", "Output files",
             escape(f"{matched} of {total} present and matching their receipts")),
        _row("model-stages", "Model stages", "<br>".join(model) or "none declared"),
        _row("authorization", "Authorization", "no authorization records"),
        _row("recorded", "Recorded", f"{recorded} · {escape(_recorded_with(steps))}"),
        _row("signature", "Signature", signed_said),
        _row("anchor", "Anchor", anchor_said),
    ))
    body = (
        '<div class="cp" data-view="receipt">'
        + _crumbs(run, store)
        + f'<div class="title"><h1>{escape(TITLE)}</h1>'
        f'<p data-section="pills">{pills}</p></div>'
        '<div class="io">'
        '<section data-section="facts">'
        + scroll_region(f'<table class="timeline" data-section="receipt">{rows}</table>',
                        "The receipt, scrolls sideways", "receipt")
        + '<details data-section="view-json"><summary>View JSON</summary>'
        f'<pre data-section="manifest">{verbatim(manifest_text)}</pre></details></section>'
        '<div class="side">'
        '<section data-section="check-yourself"><h2>Check it yourself</h2>'
        f'<p>Download <a href="{escape(href, quote=True)}" download>this run\'s record</a>, '
        "unpack it, and in its folder run:</p>"
        #: Each line escaped on its own: the page's escape draws a line break as a visible
        #: character, and the command is two lines to type.
        + "<pre><code>" + "\n".join(escape(line) for line in command.split("\n")) + "</code></pre>"
        + "".join(f'<p class="note">{n}</p>' for n in notes)
        + _public_record_note()
        + f"<p>{escape(NO_NETWORK)}</p>"
        + _printed(run, store)
        + "</section>"
        '<section data-section="does-not-say"><h2>What this receipt does not say</h2>'
        '<ul class="plain">' + "".join(f"<li>{escape(line)}</li>" for line in DOES_NOT_SAY)
        + "</ul></section></div></div>"
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
