"""The cross-service link and its origin: format 0.5's `parent_link`, the manifest's copies (`parent_run`,
`parent_stage`, `origin_run`) and a step's `calls` (onetrace 0.8's `docs/format.md`, "Across services: the
cross-service link"), as a run's record holds them, and onetrace-verify's own `linked runs match` rows.

Where they are drawn:
- the callee's case page gets a section, "Called by": the caller's run id and step and the origin run id, each linked
  where this store holds that run, and a link to every run from the same request (`origin_href`). A `parent_link`
  with `status` alone says the caller's link could not be read, in its status's words. A manifest copy that differs
  from the first receipt's link is not drawn as a link;
- the caller's step page gets a section, "Calls to other services": one item per `calls` entry, its status in its own
  words, and the child run linked where this store holds it;
- `origin-<run id>.html`, one page per origin a linked run names: every stored run whose origin is that run, read
  from the run index (`run_index`);
- where this store holds both runs of a link, onetrace-verify is run on the pair from each side (`--linked-run`), once,
  and kept (`keep_linked_checks`); its `linked runs match` rows are quoted on both runs' pages, as the verifier wrote
  them, NOT-RUN included.

The rules are `step_kinds`': the record's words and the verifier's rows alone; where the run's own check FAILs
`linked runs match`, no link is drawn from its record and the FAIL is shown; each section carries `docs/format.md`'s
"What a link does not show". What a link to another run may show is decided in one place, `link_to`, so that scoping
runs to teams changes it there alone.
"""

from __future__ import annotations

import hashlib
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from onetrace_console.step_kinds import _fail_block, _line, holds_members, prose
from onetrace_console.words import escape

#: onetrace 0.8's `docs/format.md`, "What a link does not show".
NON_CLAIMS = (
    "A cross-service link shows that two signed records agree on their parent and child. It does not show the "
    "services ran as recorded, or that the network delivered the request unaltered. The parent link is a claim from "
    "the request's sender until the caller's record is held and agrees. A head returned is one receipt of the "
    "callee's chain at the response's start. It is not the callee's final head, and it says nothing about what the "
    "callee did after. A service that does not record, or a proxy that strips a header, is a gap the record shows as "
    "a gap: `called, head not returned`. A link and a recorded trace id are equality of recorded values. They say "
    "nothing of how one service's work affected the other's. The origin is what the chain of callers sent. Where "
    "every folder is held and agrees, the records agree on where the request started. That does not show the origin "
    "run was not itself called by a service that does not record."
)
CALLED_BY = "Called by"
CALLS = "Calls to other services"
UNREADABLE = "A caller's link was sent and could not be read: {status}"
COPIES_DIFFER = "The manifest's copies of the link differ from the first receipt's link, so no link is drawn."
NOT_HELD = "not held in this store"
SHARED = "{n} runs this store holds share this id, and the link names none of them alone"
ORIGIN_HEADING = "Origin"
ORIGIN_NOT_RECORDED = (
    "origin not recorded: this run is nested in another run's process, and takes that run's origin, which its record "
    "does not carry"
)
SAME_REQUEST = "Every run from this request"
CHECK_LEAD = "onetrace-verify, given both runs' folders"
CHECK_AT = "onetrace-verify, given both runs' folders, run at {at}"
ORIGIN_TITLE = "Runs from one request"
ORIGIN_WHAT = (
    "Every run this store holds whose origin is {origin}: the run id each linked run names as where its request "
    "started, or a run's own id where it was called by no one."
)
ROW = "linked runs match"
WITHHELD = "The check of this run FAILs on the link, or on the record's integrity, so no link is drawn from it:"
#: The verifier's rows on a record's integrity: the chain, the manifest's agreement with the receipts, and the
#: signature. A FAIL on one makes every member doubtful, a link among them; a FAIL elsewhere does not withhold a link.
INTEGRITY_ROWS = (
    "chain link",
    "digest matches the manifest",
    "manifest: chain head matches the last receipt",
    "the run's signature",
    "trusted signature required",
)
WITHHELD_PAIR = "the check of both runs together FAILs, so this link is not drawn"
KEPT_KIND = "linked_checks"
COPIES = (("parent_run", "run"), ("parent_stage", "stage"), ("origin_run", "origin"))


# ------------------------------------------------------------------------------------------------ what a link shows


def chain_holds(store, key: str, head: str) -> bool:
    """Whether the stored run `key`'s chain holds `head`, a receipt's chain digest as its manifest lists it."""
    run = store.get_run(key) if store is not None else None
    if run is None:
        return False
    _, manifest, _ = context(run, store)
    chain = listed if isinstance(listed := manifest.get("chain"), list) else []
    return any(isinstance(e, dict) and e.get("digest") == head for e in chain)


def pick(run_id: str, held: dict[str, list[str]], head=None, store=None) -> list[str]:
    """The stored runs a link to `run_id` may mean: every run held with that id, narrowed, where more than one is, to
    those whose chain holds the head the link names. More than one left: the link can't say which, and no guess is
    made."""
    keys = list(held.get(run_id) or [])
    if len(keys) > 1 and isinstance(head, str) and head.startswith("sha256:") and store is not None:
        keys = [k for k in keys if chain_holds(store, k, head)] or keys
    return keys


def link_to(run_id: str, held: dict[str, list[str]], up: str, page: str = "case.html", head=None, store=None) -> str:
    """What a page may show of a link to the run `run_id`: its id, linked to its page where this store holds it once,
    or where the head the link names picks one run of several with that id (`pick`); every run it may mean, where
    several share the id and nothing picks one, never one of them alone; "not held in this store" where none is
    held. The one place a link to another run is decided: scoping runs to teams changes this function alone."""
    keys = pick(run_id, held, head, store)
    said = f'<span class="mono" data-words="record">{escape(run_id)}</span>'
    if not keys:
        return f"{said} ({escape(NOT_HELD)})"
    if len(keys) == 1:
        href = escape(f"{up}runs/{keys[0]}/{page}", quote=True)
        return f'<a href="{href}" data-link-run="{escape(keys[0], quote=True)}">{said}</a>'
    each = ", ".join(
        f'<a href="{escape(f"{up}runs/{k}/{page}", quote=True)}" data-link-shared="{escape(k, quote=True)}">'
        f'<span class="mono">{escape(k[:12])}</span></a>'
        for k in keys
    )
    return f'{said} <span data-link="shared">({escape(SHARED.format(n=len(keys)))}: {each})</span>'


def step_link(run_id: str, stage: str, held: dict[str, list[str]], up: str, head=None, store=None) -> str:
    """A step of another run: its name, linked to its page where the link picks one stored run (`pick`) and the run
    index the pages are drawn with names the step once. Through `link_to`, so scoping decides it with the run."""
    from onetrace_console import run_index
    from onetrace_console.stage_pages import stage_page

    said = f'<span class="mono" data-words="record">{escape(stage)}</span>'
    index = run_index.drawn_with()
    keys = pick(run_id, held, head, store)
    if index is None or len(keys) != 1 or "data-link-run" not in link_to(run_id, held, up, head=head, store=store):
        return said
    run = next((r for r in index.get("runs") or [] if r.get("key") == keys[0]), None)
    found = [s for s in (run or {}).get("steps") or [] if s.get("name") == stage]
    if len(found) != 1:
        return said
    href = f"{up}runs/{keys[0]}/{stage_page(str(found[0].get('index', '')))}"
    return f'<a href="{escape(href, quote=True)}" data-link-step="{escape(stage, quote=True)}">{said}</a>'


def held_runs(store) -> dict[str, list[str]]:
    """Run id to the keys of every run this store holds with it: from the run index the pages are drawn with, else
    the store."""
    from onetrace_console import run_index

    index = run_index.drawn_with()
    pairs = (
        [(r.get("run_id"), r.get("key")) for r in index.get("runs") or []]
        if index is not None
        else [(r.run_id, r.key) for r in store.runs()]
    )
    out: dict[str, list[str]] = {}
    for run_id, key in pairs:
        if isinstance(run_id, str) and isinstance(key, str) and key not in out.get(run_id, []):
            out.setdefault(run_id, []).append(key)
    return out


def _safe(run_id: str) -> str:
    """A run id as a file name on every host: letters, digits, `.`, `_` and `-` as they are; every other byte of its
    UTF-8 as `~` and two lowercase hex digits. Long ids go by their sha256."""
    out = "".join(
        chr(b) if (chr(b).isascii() and (chr(b).isalnum() or chr(b) in "._-")) else f"~{b:02x}"
        for b in run_id.encode("utf-8")
    )
    return out if len(out) <= 150 else "sha256-" + hashlib.sha256(run_id.encode("utf-8")).hexdigest()


def origin_href(origin: str) -> str:
    """The page of every run from the request that started at run `origin`."""
    return f"origin-{_safe(origin)}.html"


# ------------------------------------------------------------------------------------------------ what a run says


def _first(receipts: list[dict]) -> dict | None:
    first = receipts[0] if receipts and isinstance(receipts[0], dict) else None
    return first if first is not None and holds_members(first) else None


def _link(first: dict | None) -> dict | None:
    link = first.get("parent_link") if first is not None else None
    return link if isinstance(link, dict) else None


def copies_differ(link: dict, manifest: dict) -> bool:
    """Whether any of the manifest's copies of the link differs from the first receipt's: such a copy is no link."""
    return any(m in manifest and manifest.get(m) != link.get(f) for m, f in COPIES)


def origin_of(run_id: str, receipts: list[dict], manifest: dict, rows: list[dict]) -> str | None:
    """The run id a run's record names as where its request started: its link's `origin`; its own id where it has no
    link and is not nested in another run; None where it can't be said (a link with `status` alone, a link the
    verifier FAILs, copies that differ, a nested run whose outer run's origin isn't in its record, or an earlier
    format)."""
    first = _first(receipts)
    if first is None or record_fails(rows):
        return None
    link = _link(first)
    if link is None:
        return None if "parent_run" in manifest else run_id
    if record_fails(rows) or copies_differ(link, manifest) or not isinstance(link.get("origin"), str):
        return None
    return link["origin"] or None


def context(run, store) -> tuple[list[dict], dict, list[dict]]:
    """A stored run's receipts, manifest and the verifier's rows of its stored check."""
    from onetrace_console.bounded_json import load_json_bounded
    from onetrace_console.home import _envelope
    from onetrace_console.info_mark import rows_of
    from onetrace_console.stage_pages import _files, _read, _receipts

    receipts = [r["receipt"] for r in _receipts(run, store)]
    try:
        manifest = load_json_bounded(
            (_read(_files(run, store), store, "MANIFEST.json") or b"{}").decode("utf-8"), "MANIFEST.json", "show"
        )
    except (ValueError, UnicodeDecodeError, RecursionError):
        manifest = {}
    return receipts, manifest if isinstance(manifest, dict) else {}, rows_of(_envelope(run, store))


# ------------------------------------------------------------------------------------------------ the kept check


def _pair_key(store, caller: str, callee: str) -> str:
    """A pair's kept check, by both runs' keys and both chain heads: a redraw of the same pair never runs it again."""
    heads = [getattr(store.get_run(k), "chain_head", "") for k in (caller, callee)]
    return hashlib.sha256("\n".join([caller, heads[0], callee, heads[1]]).encode()).hexdigest()


def pairs(store) -> list[tuple]:
    """Each (caller, callee) of stored runs that a stored callee's link, or a stored caller's call, names."""
    runs = list(store.runs())
    held: dict[str, list[str]] = {}
    for r in runs:
        held.setdefault(r.run_id, []).append(r.key)
    by_key = {r.key: r for r in runs}

    def one(run_id, head):
        keys = pick(run_id, held, head, store)
        return by_key[keys[0]] if len(keys) == 1 else None

    found = []
    for r in runs:
        try:
            receipts, manifest, _ = context(r, store)
        except Exception:  # noqa: BLE001 - a run whose record can't be read names no link
            continue
        link = _link(_first(receipts))
        caller = one(link["run"], link.get("head")) if link is not None and isinstance(link.get("run"), str) else None
        if caller is not None:
            found.append((caller, r))
        for receipt in receipts:
            if not holds_members(receipt) or not isinstance(receipt.get("calls"), list):
                continue
            for c in receipt["calls"]:
                child = c.get("child_run") if isinstance(c, dict) else None
                callee = one(child, c.get("child_head")) if isinstance(child, str) else None
                if callee is not None:
                    found.append((r, callee))
    seen, out = set(), []
    for caller, callee in found:
        if (caller.key, callee.key) not in seen and caller.key != callee.key:
            seen.add((caller.key, callee.key))
            out.append((caller, callee))
    return out


def keep_linked_checks(store) -> int:
    """Run onetrace-verify on each linked pair this store holds, from the caller's side and the callee's, each given
    the other's folder (`--linked-run`), and keep both as the verifier wrote them; once per pair. How many it ran."""
    from onetrace_console.checks import CHECK_TIMEOUT_SECONDS, materialise
    from onetrace_console.viewer.report import _cli_run

    ran = 0
    for caller, callee in pairs(store):
        key = _pair_key(store, caller.key, callee.key)
        if store.get_kept(KEPT_KIND, key) is not None:
            continue
        with tempfile.TemporaryDirectory(prefix="onetrace-linked-") as tmp:
            a = materialise(caller, store, Path(tmp) / "caller")
            b = materialise(callee, store, Path(tmp) / "callee")
            record = {
                "caller": caller.key,
                "callee": callee.key,
                "caller_head": caller.chain_head,
                "callee_head": callee.chain_head,
                "ran_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "from_caller": _cli_run(
                    a,
                    "onetrace_verify.cli",
                    "onetrace-verify",
                    ("--json", "--linked-run", "../callee"),
                    "MANIFEST.json",
                    CHECK_TIMEOUT_SECONDS,
                ),
                "from_callee": _cli_run(
                    b,
                    "onetrace_verify.cli",
                    "onetrace-verify",
                    ("--json", "--linked-run", "../caller"),
                    "MANIFEST.json",
                    CHECK_TIMEOUT_SECONDS,
                ),
            }
        store.put_kept(KEPT_KIND, key, record)
        ran += 1
    return ran


def _rows(run_out: dict) -> list[dict]:
    from onetrace_console.bounded_json import load_json_bounded

    try:
        doc = load_json_bounded(str(run_out.get("stdout", "")), "the linked check's rows")
    except (ValueError, RecursionError):
        return []
    rows = doc.get("rows") if isinstance(doc, dict) else None
    return [r for r in rows if isinstance(r, dict) and r.get("name") == ROW] if isinstance(rows, list) else []


def kept_rows(store, caller_key: str, callee_key: str, side: str) -> list[str] | None:
    """The kept linked check's `linked runs match` rows for a pair, from `side` ("from_caller" or "from_callee"), as
    lines; None where the pair has none kept."""
    try:
        record = store.get_kept(KEPT_KIND, _pair_key(store, caller_key, callee_key))
    except Exception:  # noqa: BLE001 - a kept check that can't be read is said as none
        return None
    if not isinstance(record, dict) or not isinstance(record.get(side), dict):
        return None
    return [_line(r) for r in _rows(record[side])]


def kept_at(store, caller_key: str, callee_key: str) -> str:
    """When the pair's kept check ran, as it recorded it; "" where none is kept."""
    try:
        record = store.get_kept(KEPT_KIND, _pair_key(store, caller_key, callee_key))
    except Exception:  # noqa: BLE001 - a kept check that can't be read is said as none
        return ""
    return str(record.get("ran_at", "")) if isinstance(record, dict) else ""


def _quoted(lines: list[str], lead: str) -> str:
    if not lines:
        return ""
    items = "".join(f'<li><span class="mono" data-check-row="quoted">{escape(ln)}</span></li>' for ln in lines)
    return f'<div data-section="link-check"><p>{escape(lead)}:</p><ul class="plain">{items}</ul></div>'


def record_fails(rows: list[dict]) -> list[str]:
    """The FAIL rows of a run's own check that withhold a link drawn from its record, as lines: the link's own row
    (`linked runs match`), and the rows on the record's integrity (`INTEGRITY_ROWS`, a receipt's or the run's). A FAIL
    on any other row leaves the link drawn: the record's FAIL rows show on its pages as they do."""

    def withholds(name: str) -> bool:
        bare = name.split(": ", 1)[1] if name.startswith("receipts/") and ": " in name else name
        return name == ROW or bare in INTEGRITY_ROWS

    return [_line(r) for r in rows if r.get("result") == "FAIL" and withholds(str(r.get("name", "")))]


def _own_rows(rows: list[dict]) -> list[str]:
    return [_line(r) for r in rows if r.get("name") == ROW]


def _section(kind: str, title: str, body: str) -> str:
    from onetrace_console import run_index

    return (
        f'<section data-section="{kind}"><h2>{escape(title)}</h2>{body}{run_index.index_note()}'
        f'<p class="note" data-section="{kind}-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


# ------------------------------------------------------------------------------------------------ the pages


def called_by(run, store, up: str = "../../") -> str:
    """The callee's case page: who called it, as its first receipt's link says. Nothing where it records no link."""
    receipts, manifest, rows = context(run, store)
    link = _link(_first(receipts))
    if link is None:
        #: A run nested in-process in another holds no origin of its own: it is its outer run's (format.md, "The
        #: origin a run sends"), which its record does not carry. Said, never left silent.
        if _first(receipts) is not None and "parent_run" in manifest:
            return (
                f'<section data-section="origin"><h2>{escape(ORIGIN_HEADING)}</h2>'
                f'<p data-link="origin-not-recorded">{escape(ORIGIN_NOT_RECORDED)}</p></section>'
            )
        return ""
    fails = record_fails(rows)
    own = _quoted([ln for ln in _own_rows(rows) if not ln.startswith("[FAIL")], "The check of this run alone")
    if fails:
        return _section("called-by", CALLED_BY, f"<p>{escape(WITHHELD)}</p>" + _fail_block(fails) + own)
    if "status" in link and "run" not in link:
        said = UNREADABLE.format(status=str(link.get("status", "")))
        return _section("called-by", CALLED_BY, f'<p data-link="unreadable">{escape(said)}</p>{own}')
    if copies_differ(link, manifest):
        return _section("called-by", CALLED_BY, f'<p data-link="copies-differ">{escape(COPIES_DIFFER)}</p>{own}')
    held = held_runs(store)
    caller, stage = str(link.get("run", "")), str(link.get("stage", ""))
    origin = link.get("origin")
    head = link.get("head")
    picked = pick(caller, held, head, store)
    pair = kept_rows(store, picked[0], run.key, "from_callee") if len(picked) == 1 else None
    lead = CHECK_AT.format(at=kept_at(store, picked[0], run.key)) if pair is not None else CHECK_LEAD
    if any(ln.startswith("[FAIL") for ln in pair or []):
        body = (
            f'<p data-link="withheld">{escape(WITHHELD_PAIR)}</p>'
            f'<p><span class="mono" data-words="record">{escape(caller)}</span>, at step '
            f'<span class="mono" data-words="record">{escape(stage)}</span></p>'
        )
        return _section("called-by", CALLED_BY, body + own + _quoted(pair or [], lead))
    body = (
        f'<p data-link="caller">{link_to(caller, held, up, head=head, store=store)}, at step '
        f"{step_link(caller, stage, held, up, head=head, store=store)}</p>"
        f'<p>Given head: <span class="mono" data-words="record">{escape(str(link.get("head", "")))}</span></p>'
    )
    if isinstance(origin, str):
        body += (
            f'<p data-link="origin">Origin: {link_to(origin, held, up)} · '
            f'<a href="{escape(up + origin_href(origin), quote=True)}">{escape(SAME_REQUEST)}</a></p>'
        )
    body += own + _quoted(pair or [], lead)
    return _section("called-by", CALLED_BY, body)


def calls_section(
    receipt: dict, rows: list[dict], held: dict[str, list[str]], run_key: str, store, up: str = "../../"
) -> str:
    """The caller's step page: each call it records to another service. Nothing where it records none."""
    if not holds_members(receipt) or not isinstance(receipt.get("calls"), list):
        return ""
    fails = record_fails(rows)
    if fails:
        return _section("calls", CALLS, f"<p>{escape(WITHHELD)}</p>" + _fail_block(fails))
    items, quoted = [], ""
    for c in receipt["calls"]:
        if not isinstance(c, dict):
            continue
        status = str(c.get("status", ""))
        item = f'<span class="mono" data-words="record">{escape(status)}</span>'
        child = c.get("child_run")
        if isinstance(child, str):
            picked = pick(child, held, c.get("child_head"), store)
            pair = kept_rows(store, run_key, picked[0], "from_caller") or [] if len(picked) == 1 and store else []
            if pair:
                quoted += _quoted(pair, CHECK_AT.format(at=kept_at(store, run_key, picked[0])))
            withheld = any(ln.startswith("[FAIL") for ln in pair)
            shown = (
                f'<span class="mono" data-words="record">{escape(child)}</span>'
                if withheld
                else link_to(child, held, up, head=c.get("child_head"), store=store)
            )
            item += f": {shown}, head "
            item += f'<span class="mono" data-words="record">{escape(str(c.get("child_head", "")))}</span>'
            if withheld:
                item += f' <span data-link="withheld">({escape(WITHHELD_PAIR)})</span>'
        items.append(f'<li data-call="{escape(status, quote=True)}">{item}</li>')
    stage = receipt.get("stage")
    name = str(stage.get("name", "")) if isinstance(stage, dict) else ""
    own = [ln for ln in _own_rows(rows) if f" -- {name}: " in ln]
    body = f'<ul class="plain">{"".join(items)}</ul>' + _quoted(own, "The check of this run alone")
    body += quoted
    return _section("calls", CALLS, body)


def origin_pages(index: dict, generated_at: str, written: str = "") -> dict[str, str]:
    """`origin-<run id>.html` for each origin a linked run names: every run in the index with that origin."""
    from onetrace_console.render import _document
    from onetrace_console.run_index import from_index_html
    from onetrace_console.words import generated_footer

    by_origin: dict[str, list[dict]] = {}
    linked: set[str] = set()
    for r in index.get("runs") or []:
        o = r.get("origin")
        if isinstance(o, str):
            by_origin.setdefault(o, []).append(r)
            if o != r.get("run_id"):
                linked.add(o)
    pages = {}
    for origin in sorted(linked):
        items = "".join(
            f"<li>{link_to(str(r['run_id']), {str(r['run_id']): [str(r['key'])]}, '')}</li>"
            for r in sorted(by_origin[origin], key=lambda r: r["order"])
        )
        body = (
            '<div class="cp"><p class="crumbs" data-section="crumbs"><a href="home.html">Overview</a> / '
            f"{escape(ORIGIN_TITLE)}</p><h1>{escape(ORIGIN_TITLE)}</h1>"
            f'<p data-section="what">{escape(ORIGIN_WHAT.format(origin=origin))}</p>'
            f'<ul class="plain" data-section="origin-runs">{items}</ul>'
            f'<p class="note" data-section="origin-non-claims">{prose(NON_CLAIMS)}</p>'
            f'<p class="note" data-section="from-index">{from_index_html(index, written)}</p>'
            f"{generated_footer(generated_at)}</div>"
        )
        pages[origin_href(origin)] = _document(ORIGIN_TITLE, body)
    return pages


def index_origin(run, store) -> str | None:
    """The run's origin for the run index (`origin_of`), from its stored record."""
    receipts, manifest, rows = context(run, store)
    origin = origin_of(run.run_id, receipts, manifest, rows)
    link = _link(_first(receipts))
    caller = link.get("run") if link is not None else None
    held: dict[str, list[str]] = {}
    for r in store.runs() if isinstance(caller, str) else []:
        held.setdefault(r.run_id, []).append(r.key)
    picked = pick(caller, held, link.get("head") if link else None, store) if isinstance(caller, str) else []
    #: A link the check of both runs together FAILs names no origin either.
    if len(picked) == 1:
        if any(ln.startswith("[FAIL") for ln in kept_rows(store, picked[0], run.key, "from_callee") or []):
            return None
    return origin
