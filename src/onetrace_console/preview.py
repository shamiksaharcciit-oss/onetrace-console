"""The `0.0-preview` limits: the store follows the verifier, and the page says so in words.

    The store accepts a format **only while the pinned verifier checks it**. When the
    verifier drops preview, the store stops ingesting it: runs already stored stay, and new
    preview deliveries get a 422 in the verifier's own words.

    Every page that shows a preview run labels it **preview format**, in words, next to the
    verdicts.                           -- the preview-format decision

WHY THE VERIFIER DECIDES AND NOT A LIST
---------------------------------------
`ingest.MANIFEST_FORMATS` is this store's own declaration of what it implements, and it is
kept -- but it cannot be the last word, because it is a list in this repository and the
verifier is a pinned dependency that will move without it. The moment the verifier drops
preview, a store still holding `0.0-preview` in its list would go on ingesting records
nothing can check.

So the gate is the verifier's own refusal: **a refusal that names the format check is a
format refusal**, whatever this store's list says, and the delivery gets a 422 carrying the
verifier's words. The list narrows; the verifier vetoes.

Runs already stored stay. A record that was checkable when it arrived does not become
uncheckable retroactively, and deleting it would destroy evidence over a dependency bump.

THE LABEL
---------
The words **preview format** are fixed. The sentence around them is the console's own
wording. It says what the format is, how many of the runs
shown declare it, and what the verifier does about it -- because "preview" alone tells a
reader to be uneasy without telling them what about.

It is inserted into pages this console renders **and** into pages the viewer renders, which
is done by splicing rather than by the viewer because `answer.html` is frozen until the
reader session. Recorded in DESIGN_GAPS.md: the viewer is the right home for it.
"""
from __future__ import annotations

import json
import re

from onetrace_console.store import StoredRun, Store

#: The format the decision is about, and the words it requires.
PREVIEW_FORMAT = "stage-receipt-chain/0.0-preview"
PREVIEW_RECEIPT_FORMAT = "stage-receipt/0.0-preview"
LABEL = "preview format"

#: What the verifier's format refusal looks like. Measured at pin `4c11f0e`:
#:
#:     exit 2
#:     [REFUSED] manifest: format -- 'stage-receipt-chain/9.9': major version 9 is not
#:               implemented (this verifier implements major 0)
#:
#: Matched on the check's name rather than on the whole sentence, so a reworded reason still
#: reads as a format refusal. `[REFUSED]` is not required: what matters is that the verifier
#: refused AND named the format check.
VERIFIER_FORMAT_CHECK = "manifest: format"


#: The 0.2.0 verifier no longer checks preview receipts. It does not refuse
#: them -- it reports this NOT-RUN row and exits 2 (NOT VERIFIED) -- and the console reads that as
#: the verifier dropping the format: a new preview delivery gets a 422, the row quoted, after
#: this one sentence. Runs already stored stay.
PREVIEW_NOT_RUN_ROW = "[NOT-RUN] manifest: chain format -- 'stage-receipt-chain/0.0-preview'"
PREVIEW_NOT_INGESTED = ("Not ingested: this run uses the preview record format, which the 0.2.0 "
                        "verifier doesn't check.")


def preview_not_run_row(said) -> str | None:
    """The verifier's own row saying it does not implement the preview chain format, or None.

    Matched on the row's start (status, check and the quoted format) and on its "does not
    implement", so a reworded reason still reads as the verifier not checking the format; only
    when the check as a whole did not pass (exit status not 0)."""
    if said is None or not said.refused:
        return None
    return next((r for r in said.rows
                 if r.startswith(PREVIEW_NOT_RUN_ROW) and "does not implement" in r), None)


def is_format_refusal(said) -> bool:
    """Did the verifier refuse this delivery over its FORMAT?

    Takes a `staging.VerifierSaid`. A refusal for any other reason is a verdict about the
    record and is not this function's business -- that line is drawn deliberately, and
    this must not blur it.
    """
    if said is None or not said.refused:
        return False
    return any(VERIFIER_FORMAT_CHECK in row for row in said.rows)


def is_preview(run: StoredRun) -> bool:
    """Does this stored run declare the preview format?"""
    return run.format == PREVIEW_FORMAT


def preview_runs(runs) -> tuple[StoredRun, ...]:
    return tuple(r for r in runs if is_preview(r))


def sentence(n: int) -> str:
    """The label, with what a reader needs to do anything with it.

    The console's own wording, apart from the two fixed words.
    """
    runs = "run" if n == 1 else "runs"
    return (f"{LABEL}: {n} {runs} shown here declare {PREVIEW_FORMAT}. The pinned verifier "
            f"reads that format but does not perform the draft-00 checks on it, and says so "
            f"in its own report.")


#: The opening `<main …>` of a page, whoever rendered it. The viewer writes
#: `<main class="page" data-view="answer">` and this console writes a bare `<main>`, so the
#: anchor is matched as a pattern rather than as one literal string — a literal found only
#: this console's own pages and left every viewer-rendered page unlabelled.
_MAIN = re.compile(r"<main\b[^>]*>")


def label(html_text: str, runs) -> str:
    """Put the label on a page that shows at least one preview run. Idempotent.

    Spliced in directly after the page's `<main …>` so it sits above the verdicts a reader is
    about to read. The anchor is **asserted**: a page this cannot label is a page that would
    go silently unlabelled, which is the failure the decision is about, so it raises rather
    than returning the page unchanged.
    """
    shown = preview_runs(runs)
    if not shown:
        return html_text
    if f'data-preview="{LABEL}"' in html_text:
        return html_text
    found = _MAIN.search(html_text)
    if found is None:
        raise ValueError(
            f"cannot label this page: it has no <main> to place the {LABEL!r} sentence "
            f"after, so the label would be silently absent. Every page showing a preview run "
            f"must carry it.")
    from onetrace_console.words import escape
    note = f'<p data-preview="{LABEL}" class="limit">{escape(sentence(len(shown)))}</p>'
    at = found.end()
    return html_text[:at] + "\n" + note + html_text[at:]


def implemented_formats_the_verifier_accepts(store: Store, formats) -> dict[str, bool]:
    """For each format, does the pinned verifier refuse a manifest declaring it?

    Used by the test that keeps this store's declared list and the verifier in step. Builds a
    one-receipt manifest per format in a scratch directory and asks; nothing is stored.
    """
    import shutil
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    from onetrace_console.checks import shipped_verifier

    verifier = shipped_verifier()
    out: dict[str, bool] = {}
    for fmt in formats:
        folder = Path(tempfile.mkdtemp(prefix="fmt-probe-"))
        try:
            (folder / "MANIFEST.json").write_bytes(json.dumps(
                {"format": fmt, "run_id": "probe", "chain_head": "sha256:" + "0" * 64,
                 "chain": []}, separators=(",", ":")).encode("utf-8"))
            proc = subprocess.run([sys.executable, str(verifier), "MANIFEST.json"],
                                  cwd=str(folder), capture_output=True, text=True)
            refused_for_format = proc.returncode != 0 and re.search(
                re.escape(VERIFIER_FORMAT_CHECK), proc.stdout) is not None
            out[fmt] = not refused_for_format
        finally:
            shutil.rmtree(folder, ignore_errors=True)
    return out
