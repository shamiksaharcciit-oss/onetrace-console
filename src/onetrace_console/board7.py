"""Board 7, "where the change started", from the SDK's own corpus trace.

Shown on the Diff page only where the text diff's first difference sits at a node whose corpus link
changed, which the SDK says itself: the comparison's stored `--no-follow` text diff then carries a
`corpus_traces` entry, "not followed", for each changed pair of chain heads.
Only then is the trace made: a run of its own,

    python -m onetrace diff RUN_A RUN_B --text --json --runs-root RUNS_ROOT

its stdout kept byte for byte, `--out` to the scratch folder, stored beside the comparison's other
runs, which stay as they are. Anywhere else there is no board 7 and no extra run (`c171976`'s rule).

**The runs root** holds the stored runs the trace can reach, laid out from the store and nothing
else -- never from the network. Each is a run the store holds whole (every object present and
reading back as its own digest), whatever its own check said: the SDK verifies each linked run
itself, and says "did not verify" where it doesn't. A run the store doesn't hold whole is
left out, and the SDK's "not found" is then the truth. The SDK's finder (`run_finder`) takes a run
only by its manifest's chain head, one level down, so only stored runs whose manifest names a chain
head the trace looks for are laid out: no other run could be found there. Each folder is named by
its store key, never by a record's own words.

**Read strictly**, on top of the text diff's own reader (`textdiff_view.read_textdiff`): every trace
entry is held to the SDK's schema for its status, and its nodes to the reader's node rules.

**Drawn as the SDK wrote it**: item 11's points 1-6, every value from the trace run's JSON, the
SDK's sentences word for word, its four "couldn't trace" reasons as given, no count the JSON doesn't
hold, outputs drawn only where the SDK marked them verified, and the limit line always.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from html import escape as _html
from pathlib import Path

from onetrace_console.textdiff_view import (VERIFIED, TextDiffUnreadable, _decimal, _fail, _keys,
                                            _node, _shown, _strings, read_textdiff)
from onetrace_console.child import utf8_env

TRACE = "diff --text --runs-root"
SHOWN_COMMAND = "python -m onetrace diff RUN_A RUN_B --text --json --runs-root RUNS_ROOT"

#: Item 11's words.
HEADING = "Where the change started"
CAUSES_HEADING = "Every recorded cause checked"
CHAIN_HEADING = "The ingest chain"
TEXT_HEADING = "Changed text, from the source document to the answer"
LIMIT = "Nothing here says which version is correct, who changed the source, or why."

_TRACED, _CNC, _NOT_FOLLOWED = "traced", "could not check", "not followed"
_ENTRY = {"node", "status", "baseline", "candidate", "also_at"}
_ENTRY_KEYS = {
    _NOT_FOLLOWED: _ENTRY,
    _CNC: _ENTRY | {"reason"},
    _TRACED: _ENTRY | {"heading", "first_line", "documents", "second_hop", "envelope", "nodes"},
}
_SIDE = {"chain_head", "run_id", "path", "verified"}


# ------------------------------------------------------------------------------------ reading

def _head(value, what: str, *, null: bool) -> None:
    if value is None and null:
        return
    if not (isinstance(value, str) and len(value) == 71 and value.startswith("sha256:")
            and all(c in "0123456789abcdef" for c in value[7:])):
        _fail(f"{what} is not a digest: {value!r:.80}")


def _side(side, status: str, what: str) -> None:
    if status == _NOT_FOLLOWED:
        _keys(side, {"chain_head"}, {"chain_head"}, what)
        _head(side["chain_head"], f"{what}'s chain head", null=True)
        return
    _keys(side, _SIDE, _SIDE, what)
    _head(side["chain_head"], f"{what}'s chain head", null=True)
    for key in ("run_id", "path"):
        if side[key] is not None:
            _shown(side[key], f"{what}'s {key}")
    if side["path"] is not None and ("\\" in side["path"] or ":" in side["path"]):
        _fail(f"{what}'s path is not one the SDK writes")
    if side["verified"] not in (True, False, None):
        _fail(f"{what}'s verified is not true, false or null")
    if side["verified"] is False and side["run_id"] is not None:
        _fail(f"{what} did not verify and still names its run")
    if status == _TRACED and (side["verified"] is not True or side["run_id"] is None
                              or side["path"] is None or side["chain_head"] is None):
        _fail(f"{what} is traced but not found and verified")


def _entry(entry, what: str, *, followed: bool) -> None:
    if not isinstance(entry, dict):
        _fail(f"{what} is not an object")
    status = entry.get("status")
    if status not in _ENTRY_KEYS:
        _fail(f"{what}'s status is {status!r}")
    if followed and status == _NOT_FOLLOWED:
        _fail(f"{what} was not followed in a run made to follow it")
    _keys(entry, _ENTRY_KEYS[status], _ENTRY_KEYS[status], what)
    _shown(entry["node"], f"{what}'s node")
    _strings(entry["also_at"], f"{what}'s also_at")
    for side in ("baseline", "candidate"):
        _side(entry[side], status, f"{what}'s {side}")
    if status == _CNC:
        _shown(entry["reason"], f"{what}'s reason")
    if status != _TRACED:
        return
    for key in ("heading", "first_line"):
        _shown(entry[key], f"{what}'s {key}")
    if entry["envelope"] not in ("identical", "diverged"):
        _fail(f"{what}'s envelope is {entry['envelope']!r}")
    documents = entry["documents"]
    if documents is not None:
        _keys(documents, {"changed", "total", "names"}, {"changed", "total", "names"},
              f"{what}'s documents")
        _decimal(documents["changed"], f"{what}'s documents changed")
        _decimal(documents["total"], f"{what}'s documents total")
        _strings(documents["names"], f"{what}'s document names")
    hop = entry["second_hop"]
    if hop is not None:
        _keys(hop, {"node", "baseline", "candidate"}, {"node", "baseline", "candidate"},
              f"{what}'s second hop")
        _shown(hop["node"], f"{what}'s second hop node")
        for side in ("baseline", "candidate"):
            _head(hop[side], f"{what}'s second hop {side}", null=True)
    if not isinstance(entry["nodes"], list):
        _fail(f"{what}'s nodes are not a list")
    for i, node in enumerate(entry["nodes"]):
        _node(node, f"{what}'s node {i}")


def read_traces(raw: str | bytes, *, followed: bool) -> dict:
    """A text diff read by `read_textdiff`, with each `corpus_traces` entry held to the SDK's schema
    for its status; `followed`: the run was made to follow the trace, so "not followed" is refused.
    Anything else is `TextDiffUnreadable`."""
    doc = read_textdiff(raw)
    traces = doc.get("corpus_traces", [])
    if "corpus_traces" in doc and not traces:
        _fail("the text diff's corpus traces are an empty list")
    for i, entry in enumerate(traces):
        _entry(entry, f"corpus trace {i}", followed=followed)
    return doc


def changed_links(raw: str | bytes) -> list[dict]:
    """The `corpus_traces` of a stored `--no-follow` text diff: one entry per changed pair of chain
    heads at a first difference. Empty where no corpus link changed, or the document is unreadable
    (the text diff's own section says so)."""
    try:
        return read_traces(raw, followed=False).get("corpus_traces", [])
    except TextDiffUnreadable:
        return []


# ---------------------------------------------------------------------- the run that follows it

def _no_follow_raw(comparison, store) -> bytes | None:
    from onetrace_console.compare import TEXT_DIFF
    run = comparison.verb(TEXT_DIFF)
    return None if run is None or run.note else store.get(run.stdout_key)


def needs_trace(comparison, store) -> bool:
    """A comparison whose stored `--no-follow` text diff names a changed corpus link and that has no
    trace run yet: made again, so that board 7 can be drawn."""
    raw = _no_follow_raw(comparison, store)
    return comparison.verb(TRACE) is None and raw is not None and bool(changed_links(raw))


def runs_root(store, heads: set[str], root: Path) -> list[str]:
    """Lay out under `root`, one level down, every stored run the store holds whole whose manifest
    names one of `heads` as its chain head, each in a folder named by its store key. Whatever its
    own check said. Returns the keys laid out."""
    from onetrace_console.checks import materialise
    from onetrace_console.store import SameFileError, StoreError
    root.mkdir(parents=True, exist_ok=True)
    laid = []
    for run in sorted(store.runs(), key=lambda r: r.key):
        if run.chain_head not in heads:
            continue
        dest = root / run.key
        try:
            materialise(run, store, dest)
        except (StoreError, SameFileError, OSError):
            #: Not held whole: left out entirely, never a part of it.
            shutil.rmtree(dest, ignore_errors=True)
            continue
        laid.append(run.key)
    return laid


def trace_run(store, folder_a: Path, folder_b: Path, work: Path, timeout: int, no_follow):
    """The trace's own run over the two laid-out runs, or None where no corpus link changed."""
    from onetrace_console.compare import TIMED_OUT, VerbRun
    if no_follow is None or no_follow.note:
        return None
    links = changed_links(store.get(no_follow.stdout_key))
    if not links:
        return None
    heads = {e[side]["chain_head"] for e in links for side in ("baseline", "candidate")
             if e[side]["chain_head"] is not None}
    root = work / "runs-root"
    runs_root(store, heads, root)
    out = work / "out-trace"
    out.mkdir(parents=True, exist_ok=True)
    command = (sys.executable, "-m", "onetrace", "diff", str(folder_a), str(folder_b),
               "--text", "--json", "--runs-root", str(root), "--out", str(out))
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout, env=utf8_env())
    except subprocess.TimeoutExpired:
        return VerbRun(verb=TRACE, command=command, shown_command=SHOWN_COMMAND, exit_status="",
                       stdout_key=store.put(b""), note=f"{TIMED_OUT} after {timeout}s")
    return VerbRun(verb=TRACE, command=command, shown_command=SHOWN_COMMAND,
                   exit_status=str(proc.returncode), stdout_key=store.put(proc.stdout),
                   refused=proc.returncode not in (0, 1))


# ------------------------------------------------------------------------------------ drawing

def _value(value) -> str:
    """A cause's value as the SDK gives it: a string, an input's digest and trust class, or none."""
    if value is None:
        return ""
    if isinstance(value, dict):
        return (f'<code>{_html(str(value.get("digest", "")))}</code> '
                f'{_html(str(value.get("trust_class", "")))}')
    return f"<code>{_html(str(value))}</code>"


def _causes(doc: dict, entry: dict) -> str:
    """Point 2: one row per entry of the SDK's candidate-cause list for the first-difference node,
    in its order, with its own name, values and status. None added, dropped or re-labelled."""
    node = next((n for n in doc.get("nodes", []) if n["node"] == entry["node"]), None)
    if node is None or "causes" not in node:
        return ""
    rows = "".join(
        f'<tr data-cause="{_html(c["name"])}"><td>{_html(c["kind"])}</td>'
        f'<td><code>{_html(c["name"])}</code></td><td>{_value(c["baseline"])}</td>'
        f'<td>{_value(c["candidate"])}</td>'
        f'<td data-status="{_html(c["status"])}">{_html(c["status"])}</td></tr>'
        for c in node["causes"])
    return (f'<section data-section="where-started-causes"><h3>{_html(CAUSES_HEADING)}</h3>'
            f'<p><code>{_html(node["node"])}</code></p>'
            '<table><thead><tr><th>kind</th><th>name</th>'
            "<th>baseline</th><th>candidate</th><th>status</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></section>")


def _chain(entry: dict) -> str:
    """Point 3: the traced runs' stages, in the SDK's order, each with its verdict, the first
    difference outlined; and the one count the SDK gives, documents changed."""
    items = []
    for n in entry["nodes"]:
        first = n["verdict"] == "FIRST DIFFERENCE"
        label = f'<code>{_html(n["node"])}</code> · {_html(n["verdict"])}'
        items.append(f'<li data-node="{_html(n["node"])}" data-verdict="{_html(n["verdict"])}"'
                     + (f' data-first-difference="true"><strong>{label}</strong></li>' if first
                        else f">{label}</li>"))
    count = ""
    documents = entry["documents"]
    if documents is not None:
        count = (f'<p data-documents>{_html(documents["changed"])} of '
                 f'{_html(documents["total"])} documents changed</p>')
    return (f'<section data-section="where-started-chain"><h3>{_html(CHAIN_HEADING)}</h3>'
            f'<ol>{"".join(items)}</ol>{count}</section>')


def _cells(out: dict) -> tuple[str, str]:
    """An output's baseline and current text, from the SDK's own hunks and spans: each side's
    lines as the SDK numbered them, its marked words highlighted. Never the console's own diff."""
    from onetrace_console.textdiff_view import _marked
    sides = {"baseline": [], "candidate": []}
    for hunk in out["hunks"]:
        for line in hunk["lines"]:
            mark = {"-": "del", "+": "ins"}.get(line["op"], "")
            text = _marked(line["text"], line["spans"], mark)
            if line["op"] in (" ", "-"):
                sides["baseline"].append(text)
            if line["op"] in (" ", "+"):
                sides["candidate"].append(text)
    if out["notes"]:
        notes = "\n".join(_html(n) for n in out["notes"])
        sides["baseline"].insert(0, notes)
        sides["candidate"].insert(0, notes)
    return tuple(f'<pre>{chr(10).join(sides[s])}</pre>' for s in ("baseline", "candidate"))


def _rows(run: str, nodes: list) -> list[str]:
    rows = []
    for n in nodes:
        for out in n["outputs"]:
            name = _html(out["name"]) if out["name"] is not None else ""
            head = (f'<td>{run}</td><td><code>{_html(n["node"])}</code></td>'
                    f'<td><code>{name}</code></td><td>{_html(n["verdict"])}</td>')
            if out["verified"] is not True:
                #: Never an unverified output's text: the SDK's reason, word for word.
                rows.append(f'<tr data-output data-verified="false">{head}'
                            f'<td colspan="3" data-not-shown>{_html(out.get("reason", ""))}</td></tr>')
                continue
            base, cand = _cells(out)
            rows.append(f'<tr data-output data-verified="true">{head}<td>{base}</td><td>{cand}</td>'
                        f'<td><span class="pill ok" data-badge="verified">{VERIFIED}</span></td></tr>')
    return rows


def _text_table(doc: dict, entry: dict, query_run: str) -> str:
    """Point 4: one table, the traced ingest rows first, then the query rows."""
    ingest = (f'{_html(entry["baseline"]["run_id"])} → {_html(entry["candidate"]["run_id"])}')
    rows = _rows(ingest, entry["nodes"]) + _rows(query_run, doc.get("nodes", []))
    return (f'<section data-section="where-started-text"><h3>{_html(TEXT_HEADING)}</h3>'
            '<table><thead><tr><th>run</th><th>stage</th>'
            "<th>output</th><th>verdict</th><th>baseline</th><th>current</th><th></th></tr></thead>"
            f'<tbody>{"".join(rows)}</tbody></table></section>')


def _second_hop(entry: dict) -> str:
    """The SDK's own sentence for a second changed link, as its plain form words it."""
    from onetrace.textdiff import short
    hop = entry["second_hop"]
    if hop is None:
        return ""
    return (f"<p data-second-hop>the linked ingest runs' own corpus link changed at "
            f"{_html(hop['node'])}: {_html(short(hop['baseline']))} -> "
            f"{_html(short(hop['candidate']))}; not followed (one hop only)</p>")


def render_board7(doc: dict, query_run: str) -> str:
    """The board's body from a strict reading of the trace run, one part per trace entry."""
    parts = []
    if "first_line" in doc:
        parts.append(f'<p data-first-line>{_html(doc["first_line"])}</p>')
    for entry in doc.get("corpus_traces", []):
        parts.append(f'<article data-trace="{_html(entry["node"])}" '
                     f'data-status="{_html(entry["status"])}">')
        if entry["status"] == _TRACED:
            parts.append(f'<p data-trace-heading>{_html(entry["heading"])}</p>'
                         f'<p data-trace-first-line>{_html(entry["first_line"])}</p>'
                         + _second_hop(entry))
            parts.append(_causes(doc, entry))
            parts.append(_chain(entry))
            parts.append(_text_table(doc, entry, query_run))
        else:
            #: Point 5: the SDK's reason, word for word; the rest of the page as it was.
            parts.append(f'<p data-trace-reason>{_html(entry["reason"])}</p>')
            parts.append(_causes(doc, entry))
        parts.append("</article>")
    return "".join(parts)


def board7_section(comparison, store) -> str:
    """Board 7 on the Diff page, or nothing: only where the comparison holds a trace run, which it
    makes only where a corpus link changed at a first difference."""
    from onetrace_console.render import TEXT_DIFF_UNREADABLE
    from onetrace_console.words import run_named
    run = comparison.verb(TRACE)
    if run is None:
        return ""
    head = f'<section data-section="where-started"><h2>{_html(HEADING)}</h2>'
    from onetrace_console.render import typed_command
    #: The linked ingest runs are found where the SDK looks by default: the folder holding the
    #: baseline, `runs/`, so no --runs-root is needed.
    command = (f'<p data-section="where-started-command">Command: '
               f"<code>{_html(typed_command(comparison, store, 'diff', text=True))}</code></p>")
    limit = f'<p class="limit" data-section="where-started-limit">{_html(LIMIT)}</p>'
    if run.note:
        body = (f"<p>This console did not obtain an answer: {_html(run.note)}. Nothing is shown "
                "below because there is nothing the SDK said.</p>")
    else:
        try:
            doc = read_traces(store.get(run.stdout_key), followed=True)
        except TextDiffUnreadable as e:
            body = f"<p>{_html(TEXT_DIFF_UNREADABLE.format(why=e))}</p>"
        else:
            query = (f"{run_named(store, comparison.run_a)} → "
                     f"{run_named(store, comparison.run_b)}")
            body = render_board7(doc, query)
    return f"{head}{body}{limit}{command}</section>"
