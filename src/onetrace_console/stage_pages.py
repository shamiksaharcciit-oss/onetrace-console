"""A stage's inputs and outputs.

One page per stage, `runs/<key>/stage-<n>.html`, opened from the graph's nodes in the console's frame
It shows content only as verified:

- **Outputs:** each output this stage's receipt records, read from the stored run at
  `artifacts/<the receipt's own name>/<output name>`. Its text is shown only when the stored bytes'
  sha256 equals the digest the receipt records, with "Verified". Stored bytes that differ: "does not
  match its receipt, not shown", and never the text. Not stored: "fingerprint only". Not text:
  its size and fingerprint, "not shown".
- **Inputs**: an input's content is shown only when its digest equals an output
  recorded in an UPSTREAM stage's receipt (earlier in the chain) and that output's stored bytes
  match it -- labelled "matches the stored output of <stage>": what was checked, never where the
  input came from, which the receipt does not record. Every other input: its name, trust class and
  fingerprint, "fingerprint only". Nothing outside the run's stored outputs is ever shown.
- **Inputs that are an upstream stage's receipt** (`receipt:<stage>`): when
  the input's digest equals the sha256 of that stage's stored receipt bytes, "matches the stored
  receipt of <stage>", linking to that stage's page. Otherwise "fingerprint only", as above.
- **Against a compared run,** before 0.2.0: "Same in <run>" or "Differs from <run>", from the stored
  diff verdict of the run's latest comparison as the candidate. No highlighting (that is 0.2.0's).

The console makes no claim of its own about content. Text past the viewer's verbatim cap is cut with
its own "…and N more" sentence and the run's record offered, as everywhere: the SDK's own
`--text` cap arrives with 0.2.0.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import json

from onetrace_console.store import Store, StoredRun
from onetrace_console.words import (escape, generated_footer, named, record_href, run_named,
                                     scroll_region, verbatim)

STAGE_PAGE = "stage-{n}.html"

#: "The banner states it plainly".
BANNER = ("Outputs are stored and shown after checking; inputs from outside the run are "
          "fingerprinted, not stored.")
VERIFIED = "Verified"
MISMATCH = "does not match its receipt, not shown"
FINGERPRINT_ONLY = "fingerprint only"
NOT_SHOWN = "not shown"
#: What was checked, never the route.
MATCHES = "matches the stored output of {stage}"
MATCHES_RECEIPT = "matches the stored receipt of {stage}"
SAME_IN = "Same in {run}"
DIFFERS_FROM = "Differs from {run}"

#: The compare page's verdicts that say this stage differs, and those that say it is the same.
_DIFFERS = ("FIRST DIFFERENCE", "downstream")
_SAME = ("same", "reconverged")


def stage_page(manifest_index: str) -> str:
    return STAGE_PAGE.format(n=manifest_index)


def _files(run: StoredRun, store: Store) -> dict[str, str]:
    """{path as delivered, normalised: object key} for every file the run's delivery held."""
    from onetrace_console.ingest import same_file
    return {same_file(p): k for p, k in run.listing}


def _read(files: dict[str, str], store: Store, path: str) -> bytes | None:
    from onetrace_console.ingest import same_file
    from onetrace_console.store import StoreError
    key = files.get(same_file(path))
    if key is None:
        return None
    try:
        return store.get(key)
    except StoreError:
        return None


def _steps(run: StoredRun, store: Store) -> list[dict]:
    """The chain's receipts in order: [{index, file, receipt}] -- only receipts the run holds."""
    files = _files(run, store)
    manifest = load_json_bounded((_read(files, store, "MANIFEST.json") or b"{}").decode("utf-8"), "MANIFEST.json", "show")
    out = []
    for entry in manifest.get("chain") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("file"), str):
            continue
        raw = _read(files, store, entry["file"])
        try:
            receipt = load_json_bounded(raw.decode("utf-8"), entry["file"], "show") if raw is not None else None
        except (UnicodeDecodeError, ValueError, RecursionError):
            receipt = None
        if isinstance(receipt, dict):
            out.append({"index": str(entry.get("index", "")), "file": entry["file"],
                        "receipt": receipt})
    return out


def _stage_name(receipt: dict) -> str:
    stage = receipt.get("stage")
    return stage.get("name", "") if isinstance(stage, dict) else ""


def _artifact_path(receipt_file: str, name: str) -> str:
    """Where the SDK stores a stage's output: `artifacts/<the receipt's own name>/<output>`."""
    stem = receipt_file.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    return f"artifacts/{stem}/{name}"


def _verified(blob: bytes | None, digest: str) -> bool:
    return blob is not None and digest == "sha256:" + hashlib.sha256(blob).hexdigest()


def _content(blob: bytes, media_type: str, href: str) -> str:
    """Text as the page shows it: JSON pretty-printed, invalid UTF-8 escaped, cut at the viewer's
    verbatim cap with its own sentence. Binary content: never here."""
    from onetrace_console.viewer.model import TEXT_CAP
    from onetrace_console.viewer.page import _t
    text = blob.decode("utf-8", errors="backslashreplace")
    if media_type == "application/json":
        try:
            text = json.dumps(load_json_bounded(text, "the output", "show"), indent=2, ensure_ascii=False)
        except ValueError:
            pass
    shown = verbatim(text[:TEXT_CAP])
    if len(text) > TEXT_CAP:
        shown += ("\n" + _t("text.more", n=str(len(text) - TEXT_CAP))
                  + f' <a href="{escape(href)}" download>{escape("the run\'s record")}</a>')
    return f'<pre data-content="verified">{shown}</pre>'


def _is_text(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in ("application/json",)


def _fingerprint(item: dict) -> str:
    return (f'<span class="mono">{escape(str(item.get("digest", "")))}</span>'
            f' · {escape(str(item.get("bytes", "")))} bytes')


def _output(step: dict, out: dict, files, store, href: str) -> str:
    name, digest = str(out.get("name", "")), str(out.get("digest", ""))
    media = str(out.get("media_type", ""))
    blob = _read(files, store, _artifact_path(step["file"], name))
    head = f'<span class="mono">{named(name)}</span> · {_fingerprint(out)}'
    if blob is None:
        said = f"<p>{escape(FINGERPRINT_ONLY)}</p>"
    elif not _verified(blob, digest):
        said = f"<p>{escape(MISMATCH)}</p>"
    elif not _is_text(media):
        said = f"<p>{escape(NOT_SHOWN)}</p>"
    else:
        said = f'<p><span class="pill ok">{VERIFIED}</span></p>' + _content(blob, media, href)
    return f'<li data-output="{escape(name, quote=True)}">{head}{said}</li>'


def _input(item: dict, upstream: dict[str, tuple[str, str, bytes | None]], href: str,
           receipts: dict[str, tuple[str, str, bytes]] | None = None) -> str:
    """`upstream`: {recorded output digest: (stage, media type, stored bytes or None)} over the
    stages earlier in the chain. `receipts`: {sha256 of a stored receipt: (stage, its chain index,
    the stored bytes)} over the same stages."""
    name, digest = str(item.get("name", "")), str(item.get("digest", ""))
    head = (f'<span class="mono">{named(name)}</span> · {escape(str(item.get("trust_class", "")))}'
            f" · {_fingerprint(item)}")
    match = upstream.get(digest)
    receipt = (receipts or {}).get(digest)
    if receipt is not None and _verified(receipt[2], digest) and receipt[1].isdigit():
        stage, index, _ = receipt
        said = (f'<p><span class="pill ok">{VERIFIED}</span> '
                f'<a href="{stage_page(index)}">{escape(MATCHES_RECEIPT.format(stage=stage))}</a></p>')
    elif match is not None and _verified(match[2], digest) and _is_text(match[1]):
        stage, media, blob = match
        said = (f'<p><span class="pill ok">{VERIFIED}</span> '
                f"{escape(MATCHES.format(stage=stage))}</p>" + _content(blob, media, href))
    else:
        said = f"<p>{escape(FINGERPRINT_ONLY)}</p>"
    return f'<li data-input="{escape(name, quote=True)}">{head}{said}</li>'


def _verdicts(run: StoredRun, store: Store) -> tuple[str, dict[str, str]] | None:
    """(the baseline as a page names it, {stage name: verdict}) from the run's latest comparison
    as the candidate, or None where there is none that reads."""
    from onetrace_console.viewer.verbs import TwoRunDag

    from onetrace_console.pages import _strict_diff_report, latest_as_candidate
    comparison = latest_as_candidate(run, store)
    if comparison is None:
        return None
    report = _strict_diff_report(comparison, store)
    if report is None:
        return None
    if isinstance(report, TwoRunDag):
        by = {r.node.split("#", 1)[0]: r.verdict for r in report.ladder}
    else:
        by = {r.stage: r.verdict for r in report.ladder}
    return run_named(store, comparison.run_a), by


#: The badges, asked in the run ladder's own fixed questions, each stating the run's
#: own rung in the run page's words, from the same model the run's pages are drawn from: signing, the
#: "Signed by a known recorder" rung; anchoring, the viewer's `anchor_badge`
#: 
_BADGES = ("Signed by a known recorder", "Committed by a known time")


def _badges(anchored, signed) -> str:
    from onetrace_console.receipt_page import _rung_said
    signing, question = _BADGES
    table = ('<table class="rungs"><tbody>'
             f'<tr data-badge="1" data-state="{escape(signed.state)}"><td>{escape(signing)}</td>'
             f"<td>{_rung_said(signed)[1]}</td></tr>"
             f'<tr data-badge="2" data-state="{escape(anchored.state)}"><td>{escape(question)}</td>'
             f"<td>{_rung_said(anchored)[1]}</td></tr>"
             "</tbody></table>")
    return ('<section data-section="badges">'
            + scroll_region(table, "Signed and anchored, scrolls sideways", "badges") + "</section>")


def render_stage_pages(run: StoredRun, store: Store, *, generated_at: str,
                       anchored, signed) -> dict[str, str]:
    """Every stage page of the run: {stage-<n>.html: page}. Unsealed console pages, framed when
    served, like the Diff page. `anchored`: the anchoring badge, the viewer's `anchor_badge` from
    the model the run's pages are drawn from; `signed`, the signing badge, that
    model's "Signed by a known recorder" rung."""
    from onetrace_console.render import _document
    files = _files(run, store)
    steps = _steps(run, store)
    href = record_href(run)
    compared = _verdicts(run, store)
    pages: dict[str, str] = {}
    upstream: dict[str, tuple[str, str, bytes | None]] = {}
    receipts: dict[str, tuple[str, str, bytes]] = {}
    for step in steps:
        receipt, stage = step["receipt"], _stage_name(step["receipt"])
        inputs = [i for i in receipt.get("inputs") or [] if isinstance(i, dict)]
        outputs = [o for o in receipt.get("outputs") or [] if isinstance(o, dict)]
        verdict = ""
        if compared is not None and stage in compared[1]:
            v = compared[1][stage]
            words = (DIFFERS_FROM if v in _DIFFERS else SAME_IN if v in _SAME else "")
            if words:
                verdict = f'<p data-section="compared">{words.format(run=compared[0])}</p>'
        body = (
            '<div class="cp">'
            f'<h1>{named(stage)}</h1>'
            f'<p data-section="run">step {escape(step["index"])} of {len(steps)} · '
            f"{run_named(store, run.key)}</p>"
            f'<p data-section="banner">{escape(BANNER)}</p>'
            f"{verdict}"
            '<section data-section="inputs"><h2>Inputs</h2><ul class="plain">'
            + ("".join(_input(i, upstream, href, receipts) for i in inputs) or "<li>none recorded</li>")
            + '</ul></section><section data-section="outputs"><h2>Outputs</h2><ul class="plain">'
            + ("".join(_output(step, o, files, store, href) for o in outputs)
               or "<li>none recorded</li>")
            + "</ul></section>"
            + _badges(anchored, signed)
            + f'<p data-section="back"><a href="case.html">The run, step by step</a></p>'
            + generated_footer(generated_at)
            + "</div>")
        if step["index"].isdigit():
            pages[stage_page(step["index"])] = _document(stage or "stage", body)
        stored = _read(files, store, step["file"])
        if stored is not None:
            receipts.setdefault("sha256:" + hashlib.sha256(stored).hexdigest(),
                                (stage, step["index"], stored))
        for o in outputs:
            path = _artifact_path(step["file"], str(o.get("name", "")))
            upstream.setdefault(str(o.get("digest", "")),
                                (stage, str(o.get("media_type", "")), _read(files, store, path)))
    return pages
