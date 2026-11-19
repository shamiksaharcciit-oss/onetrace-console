"""Store data a step touched: format 0.5's `state_reads`, `state_writes`, `state_cut`, `step.effect_basis`, the kept
state values and `state_at_open` (onetrace 0.8's `docs/format.md`, "Store data a step touched"), as a run's record
holds them.

Where they are drawn:
- each step's page gets a section, "Store data this step read and wrote": one item per entry, with the store as the
  team declared it and its kind, the key by its digest (in plain only where the record keeps it in plain), the
  store's version with its kind ("not observed" in those words), and the value's digest with its form, or the
  record's `digest_status`, or `found: false`. `state_cut` is a line above the entries. A kept value opens under
  the entry, labelled as the store's bytes, never as an output;
- the run's head gets a line naming the stores' revisions at open, only where the first receipt holds
  `state_at_open`.

The rules are `step_kinds`' (the record's words alone; a member the verifier fails is not drawn from and its row is
shown; what store state does not show, in `docs/format.md`'s words, on each section). A step in format 0.5 with
neither member reads "No store state recorded", never that it touched no store; an empty list reads "recorded,
nothing read" or "nothing written". A receipt in an earlier format gets nothing.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from onetrace_console.step_kinds import _fail_block, failed, holds_members, prose
from onetrace_console.words import escape

#: onetrace 0.8's `docs/format.md`, "Store data a step touched", "What it does not show".
NON_CLAIMS = (
    "Lineage is equality of recorded digests or versions: it says run B read what run A wrote, not that the data made "
    "B behave as it did. A version is the store's own report, and onetrace does not check that a store's versions are "
    "consistent. At Postgres, a read's version is the LSN at the read, not a snapshot the read is proved to have used. "
    "A store reached without a hook or a declaration is not seen. Source age is the store's own `last modified`, not "
    "when the data was true. A sorted `sql-rows/1` says which rows came back, not in what order. `state_at_open` is a "
    "revision the store reported at open, not a statement of the store's content."
)
HEADING = "Store data this step read and wrote"
READS = "Read"
WRITES = "Written"
NONE_RECORDED = "No store state recorded"
NOT_RECORDED = "not recorded"
READ_NOTHING = "recorded, nothing read"
WROTE_NOTHING = "recorded, nothing written"
LINEAGE_HEADING = "Other runs that wrote what this step read"
BY_KEY_DIGEST = "the key matched by its digest: one side keeps it in plain, the other as a digest"
NOT_INDEXED = "not indexed for lineage: the run index these pages were drawn with holds no store writes"
NO_WRITER = "No other run in the index wrote, for this step's reads' stores and keys, an equal version or digest."
AT_OPEN_LEAD = "This run's first step names the stores' revisions at open"
KEPT_LABEL = "Kept bytes, the value the digest is over: the store's bytes, not an output of the step"
KEPT_MISMATCH = "the kept bytes do not match the entry's digest, not shown"
KEPT_NOT_TEXT = "the kept bytes are not text, not shown"
ENTRY_ROWS = ("state entries",)
BASIS_ROWS = ("step",)
KEPT_ROWS = ("state kept",)
WRITES_ROWS = ("state_writes against effect_label",)
AT_OPEN_ROW = "state at open"
SIDES = (("reads", "state_reads", READS, READ_NOTHING), ("writes", "state_writes", WRITES, WROTE_NOTHING))


def _rec(text: str) -> str:
    return f'<span class="mono" data-words="record">{escape(text)}</span>'


def _version(e: dict) -> str:
    v = e.get("version")
    if not isinstance(v, str):
        return ""
    kind = e.get("version_kind")
    return _rec(v) + (f" ({_rec(kind)})" if isinstance(kind, str) else "")


def _value(e: dict) -> str:
    if e.get("found") == "false":
        return f"{_rec('found: false')}, the read found nothing"
    if isinstance(e.get("digest_status"), str):
        return _rec(e["digest_status"])
    if isinstance(e.get("digest"), str):
        form = e.get("digest_form")
        return (f"{_rec(form)} · " if isinstance(form, str) else "") + _rec(e["digest"])
    return ""


def _kept(e: dict, path: str, read_file) -> str:
    if e.get("kept") != "true" or read_file is None:
        return ""
    blob = read_file(path)
    if blob is None:
        return ""
    if "sha256:" + hashlib.sha256(blob).hexdigest() != e.get("digest"):
        return f"<p>{escape(KEPT_MISMATCH)}</p>"
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return f"<p>{escape(KEPT_NOT_TEXT)}</p>"
    return (
        f"<details data-state-kept><summary>{escape(KEPT_LABEL)}</summary>"
        f'<pre class="mono" data-words="record">{escape(text)}</pre></details>'
    )


def _entry(e: dict, n: int, side: str, stem: str, kept_fails: list[str], read_file) -> str:
    store, kind = e.get("store"), e.get("store_kind")
    said = _rec(str(store)) + (f" ({_rec(kind)})" if isinstance(kind, str) else "")
    if isinstance(e.get("key"), str):
        key = f"key {_rec(e['key'])}, kept in plain"
    else:
        key = f"key {_rec(str(e.get('key_digest', '')))}"
    lines = [said, key, "version " + _version(e), _value(e)]
    if isinstance(e.get("as_of"), dict):
        a = e["as_of"]
        lines.append(f"as of: newest {_rec(str(a.get('newest', '')))}, oldest {_rec(str(a.get('oldest', '')))}")
    kept = _fail_block(kept_fails) if kept_fails else _kept(e, f"state/{stem}/{side}/{n}", read_file)
    return f'<li data-state-entry="{side}-{n}">' + "<br>".join(x for x in lines if x) + kept + "</li>"


def _side(receipt: dict, side: str, member: str, title: str, nothing: str, stem: str, kept_fails, read_file) -> str:
    v = receipt.get(member)
    if v is None:
        body = f"<p>{escape(NOT_RECORDED)}</p>"
    elif isinstance(v, list) and not v:
        body = f"<p>{escape(nothing)}</p>"
    else:
        items = [_entry(e, n, side, stem, kept_fails, read_file) for n, e in enumerate(v, 1) if isinstance(e, dict)]
        body = f'<ul class="plain">{"".join(items)}</ul>'
    return f'<div data-section="state-{side}"><h3>{escape(title)}</h3>{body}</div>'


def _cut(receipt: dict) -> str:
    cut = receipt.get("state_cut")
    if not isinstance(cut, str):
        return ""
    return (
        f'<p data-state-cut="{escape(cut, quote=True)}">{_rec(cut)} more entries were counted and not recorded '
        f"(<code>state_cut</code>): the entries below are not the whole of this step's store state.</p>"
    )


def _basis(receipt: dict, receipt_file: str, rows: list[dict]) -> str:
    if failed(rows, receipt_file, BASIS_ROWS):
        return ""
    step = receipt.get("step")
    basis = step.get("effect_basis") if isinstance(step, dict) else None
    return f"<p>Effect basis: {_rec(basis)}</p>" if isinstance(basis, str) else ""


def _lineage(receipt: dict, run_key: str) -> str:
    """ "Other runs that wrote what this step read": from the run index the pages are drawn with (`run_index.drawing`),
    never the store's records. Each run whose indexed write holds, for a read's store and key, an equal version or an
    equal digest, linked to its step's page. An index without store writes, or none, reads as not indexed."""
    from onetrace_console import run_index
    from onetrace_console.stage_pages import stage_page

    reads = (
        [e for e in receipt.get("state_reads") or [] if isinstance(e, dict) and e.get("found") != "false"]
        if isinstance(receipt.get("state_reads"), list)
        else []
    )
    if not reads:
        return ""
    index = run_index.drawn_with()
    head = f'<div data-section="lineage"><h3>{escape(LINEAGE_HEADING)}</h3>'
    if index is None or index.get(run_index.LINEAGE) != "state_writes":
        return head + f'<p data-lineage="not-indexed">{escape(NOT_INDEXED)}</p></div>'
    items = []
    for read in reads:
        for run, step, w, how, keyed in run_index.wrote(index, run_key, read):
            href = f"../{run['key']}/{stage_page(str(step.get('index', '')))}"
            said = w.get(how, "")
            items.append(
                f'<li data-lineage-run="{escape(str(run["key"]), quote=True)}">'
                f'<a href="{escape(href, quote=True)}">{_rec(str(run.get("run_id", "")))}</a>, step '
                f"{_rec(str(step.get('name', '')))}, wrote {_rec(str(w.get('store', '')))} with an equal {how}: "
                f"{_rec(str(said))}"
                + (f' <span data-lineage-key="digest">({escape(BY_KEY_DIGEST)})</span>' if keyed == "digest" else "")
                + "</li>"
            )
    if not items:
        return head + f'<p data-lineage="none">{escape(NO_WRITER)}</p>{run_index.index_note()}</div>'
    return head + f'<ul class="plain">{"".join(items)}</ul>{run_index.index_note()}</div>'


def step_section(receipt: dict, receipt_file: str, rows: list[dict], read_file, run_key: str = "") -> str:
    """A step's page: the store data it read and wrote, then the other runs that wrote what it read. Nothing for a
    receipt in an earlier format."""
    if not holds_members(receipt):
        return ""
    stem = PurePosixPath(receipt_file).stem
    entry_fails = failed(rows, receipt_file, ENTRY_ROWS)
    writes_fails = failed(rows, receipt_file, WRITES_ROWS)
    has = any(receipt.get(m) is not None for _, m, _, _ in SIDES)
    if entry_fails:
        body = _fail_block(entry_fails)
    elif not has:
        body = f'<p data-state="none">{escape(NONE_RECORDED)}</p>'
    else:
        kept_fails = failed(rows, receipt_file, KEPT_ROWS)
        body = _cut(receipt) + _basis(receipt, receipt_file, rows)
        for side, member, title, nothing in SIDES:
            if side == "writes" and writes_fails:
                body += f'<div data-section="state-writes"><h3>{escape(title)}</h3>{_fail_block(writes_fails)}</div>'
            else:
                body += _side(receipt, side, member, title, nothing, stem, kept_fails, read_file)
        body += _lineage(receipt, run_key)
    if writes_fails and (entry_fails or not has):
        body += _fail_block(writes_fails)
    return (
        f'<section data-section="store-state"><h2>{escape(HEADING)}</h2>{body}'
        f'<p class="note" data-section="store-state-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


def head_line(receipts: list[dict], rows: list[dict]) -> str:
    """The run's head's line: the stores' revisions at open, from the first receipt; the verifier's FAIL where its
    row fails; nothing where the first receipt holds none, or is in an earlier format."""
    fails = failed(rows, "", (AT_OPEN_ROW,))
    first = receipts[0] if receipts and isinstance(receipts[0], dict) else None
    if fails:
        return f'<div data-section="state-at-open"><p class="sub">{escape(AT_OPEN_LEAD)}:</p>{_fail_block(fails)}</div>'
    if first is None or not holds_members(first) or not isinstance(first.get("state_at_open"), list):
        return ""
    said = []
    for s in first["state_at_open"]:
        if isinstance(s, dict) and isinstance(s.get("store"), str) and isinstance(s.get("version"), str):
            kind = s.get("version_kind")
            said.append(f"{s['store']} at {s['version']}" + (f" ({kind})" if isinstance(kind, str) else ""))
    return (
        f'<p class="sub" data-section="state-at-open">{escape(AT_OPEN_LEAD)}: '
        f'<span class="mono" data-words="record">{escape("; ".join(said))}</span></p>'
    )
