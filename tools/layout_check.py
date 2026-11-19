#!/usr/bin/env python3
"""layout_check.py -- every page kind of the demo, at 1280 and at 390 pixels wide: nothing wider
than the window, except inside the console's own named scroll regions.

Starts `onetrace-console demo --public` from this working tree (its own temporary folder, which
it removes on SIGTERM), and beside it the capture store (`demo --public --captures`), whose pages are the two
kinds the demo has none of (CAPTURE_KINDS); picks one page of each kind from the store that holds it, and loads each in
headless Chromium at both widths. A page fails when the document is wider than the window, when
any element outside a scroll region (`.scroll-x`, `.graph-box`, `pre`, and the tables inside
those) reaches past the window's right edge, or when any element hides or scrolls content wider
than its own box (`overflow` hidden, auto, scroll or clip, and `scrollWidth > clientWidth + 1`)
other than the verifier-output and code blocks named in SCROLL_ALLOWED: nothing is cut off, and
nothing but those scrolls sideways. At desktop width it also fails a runs list whose run name
breaks onto a new line anywhere but after a hyphen. On the Overview's tables of planted runs it fails
a row whose three cells are not side by side at 1024 px and above, or do not stack below it,
and a row that reaches past the window's right edge. With --shots DIR it also saves a screenshot of
each page at each width, and a SHA256SUMS over them.

A check of its own, with its own exit code and output kept; an Actions job for it
comes later. Needs a Python with playwright and its Chromium (`--browser-python`), apart from the
console's own (`--console-python`).

Usage:
  python tools/layout_check.py --console-python PY --browser-python PY [--shots DIR] [--widths 1280,768,390]
                               [--every]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: One page of each kind, as a pattern over the built store's pages (the first match, sorted).
KINDS = {
    "overview": r"home\.html",
    "all-counts": r"counts\.html",
    "runs": r"executions-all\.html",
    "runs-filtered": r"executions-contradicts\.html",
    "comparisons": r"comparisons\.html",
    "comparison-line": None,  # chosen by content below: a straight-line pair
    "comparison-graph": None,  # and a graph-shaped one
    "run": r"runs/[0-9a-f]+/case\.html",
    "proof": r"runs/[0-9a-f]+/proof\.html",  # a run page's Proof view, its graph
    "answer": r"runs/[0-9a-f]+/answer\.html",
    "stage": r"runs/[0-9a-f]+/stage-1\.html",
    "receipt": r"runs/[0-9a-f]+/receipt\.html",
    "authorization": r"runs/[0-9a-f]+/authorization\.html",
    "incidents": r"incidents\.html",
    "incident-rule": r"incidents-i-contradicts\.html",
    "incident": r"incidents/i-contradicts-[0-9a-f]+\.html",  # one incident's own page
    "text-diff": r"diff/[0-9a-f]+-text\.html",  # a text diff's own page, two panes
    "pipeline": r"pipeline-p[0-9]+\.html",  # a pipeline's page, its runs as tiles
    "drift": r"drift-p[0-9]+\.html",  # a pipeline's drift page, against the first
    "run-benchmark": None,  # chosen by content below: a benchmark's page, its variation profile
    "authorization-gated": None,  # and a run's Authorization page listing its gated steps
    "comparison-proof": r"diff/[0-9a-f]+-proof\.html",  # Investigate's Proof tab
    "pair-authorization-gated": None,  # Investigate's Authorization tab: both runs' gated steps side by side,
    "pair-authorization-none": None,  # and a pair where neither run has one
    "comparison-token-levels": None,  # the capture store's: the model's rows and choices at the first difference
    "stage-close-calls": None,  # the capture store's: a model step's page with its close-call view
    "search": None,  # served, not built: the index's results (`SEARCH`)
    "runs-page": None,  # served, not built: the Runs page (`RUNS_PAGES`), unfiltered,
    "runs-page-pipeline": None,  # one pipeline chosen,
    "runs-page-2": None,  # and its second page,
    "runs-page-pair": None,  # and one pipeline with a pair chosen in its picker
    "visitor-comparison": None,  # made by Compare's POST before the pages are drawn (`VISITOR_PAIR`)
    "signin-entra": None,  # sign-in through Microsoft Entra ID's pages (`SIGNIN_KINDS`): the sign-in page,
    "signin-refused": None,  # a refused sign-in's page,
    "signin-no-role": None,  # and the page for someone with no role in onetrace
    "settings-sign-out": None,  # a page served to someone signed in, its settings menu open on Sign out
    "signin-local": None,  # the local accounts' sign-in page
    "admin-people": None,  # the admin pages (`SIGNIN_KINDS`), drawn from example facts: people,
    "admin-teams": None,  # teams,
    "admin-audit": None,  # and the audit log
    "forwarding-setup": None,  # trace forwarding's setup page (`SIGNIN_KINDS`), from invented destinations
    "settings-forwarding": None,  # a page with the settings menu open on forwarding's row, broken, with the dot
    "agents-runs": None,  # format 0.5's kinds and agents (`AGENT_KINDS`): the runs list's Kinds column,
    "agents-proof": None,  # a run's table of steps with each step's kind, agent and messages,
    "agents-stage-messages-sent": None,  # a step's page with its kind, agent and the message it sent,
    "agents-stage-messages-taken": None,  # one with the message it took in,
    "agents-stage-tool-call": None,  # and a tool call's page, its request linked
    "state-proof": None,  # format 0.5's store state (`STATE_KINDS`): a run's head naming the stores' revisions at open,
    "state-stage-reads": None,  # a step's page with the store data it read, two values kept,
    "state-stage-writes": None,  # and one with the store data it wrote
    "lineage-stage": None,  # a step's page listing the other run that wrote what it read (`LINK_KINDS`),
    "link-called-by": None,  # a callee's case page, called by a run this console holds,
    "link-calls": None,  # its caller's step page, with its calls to other services,
    "link-twin-calls": None,  # a second run with the caller's run id, its own calls, the id shared (`_desks`),
    "link-origin": None,  # and the page of every run from that request
    "expect-checked": None,  # a run's expectations with what was checked during the run, a batch's count among them,
    "code-case": None,  # a run's case page with its code version, uncommitted changes and lock file,
    "code-rerun-parts": None,  # and a run made from parts of others, its head naming each part,
    "confirmations": None,  # a run's Authorization page with the recipient's confirmation and its rows,
    "recovered-proof": None,  # a run a later process recovered, its head saying so beside the check's row,
    "recovered-case": None,  # and its case page, with the verifier's own lines on the writer and recovery,
    "usage-stage": None,  # a model step's tokens, record by record, a call with none recorded among them,
    "usage-cost": None,  # and a run's tokens per model, its record holding a cost
}
#: Sign-in through Entra ID's three pages, by their address on `tools/signin_pages.py`, which serves them as the
#: console's own renderers draw them, with its stylesheet: a running console draws the no-role page only after a
#: whole sign-in at a real tenant.
SIGNIN_KINDS = {
    "signin-entra": "signin",
    "signin-refused": "signin/refused",
    "signin-no-role": "signin/no-role",
    "settings-sign-out": "settings-sign-out",
    "signin-local": "signin/local",
    "admin-people": "admin/people",
    "admin-teams": "admin/teams",
    "admin-audit": "admin/audit",
    "forwarding-setup": "forwarding/setup",
    "settings-forwarding": "settings-forwarding",
}
#: Format 0.5's step kinds, agents and messages, on `tests/format_05_agents/agents-kept`, loaded by a local console of
#: its own beside the demo: the demo holds no format 0.5 agent run. `{key}` is the run's key, read from its runs list.
AGENT_RUN = REPO / "tests" / "format_05_agents" / "agents-kept"
AGENT_KINDS = {
    "agents-runs": "executions-all.html",
    "agents-proof": "runs/{key}/proof.html",
    "agents-stage-messages-sent": "runs/{key}/stage-2.html",
    "agents-stage-messages-taken": "runs/{key}/stage-3.html",
    "agents-stage-tool-call": "runs/{key}/stage-5.html",
}
#: Format 0.5's store state, on `tests/format_05_state/state-kept`, loaded by the same local console as the agent run.
STATE_RUN = REPO / "tests" / "format_05_state" / "state-kept"
STATE_KINDS = {
    "state-proof": "runs/{key}/proof.html",
    "state-stage-reads": "runs/{key}/stage-2.html",
    "state-stage-writes": "runs/{key}/stage-5.html",
}


#: Format 0.5's lineage and cross-service link, on `tests/format_05_lineage/` and `tests/format_05_link/`, loaded by the
#: same local console beside the store state run, whose note the lineage run read.
LINK_RUNS = (
    REPO / "tests" / "format_05_lineage" / "state-followup",
    REPO / "tests" / "format_05_link" / "link-desk",
    REPO / "tests" / "format_05_link" / "link-billing",
    REPO / "tests" / "format_05_expect" / "expect-record",
    REPO / "tests" / "format_05_code" / "code-dirty",
    REPO / "tests" / "format_05_code" / "accept" / "A77-code-of-lock-differs",
    REPO / "tests" / "format_05_vectors" / "A102-real-effected",
    REPO / "tests" / "onetrace_runs" / "0.8.0" / "refund-killed",
    REPO / "tests" / "format_05_usage" / "usage-a",
    REPO / "tests" / "format_05_usage" / "accept" / "A202-model-usage-cost",
    #: Item 8's candidates, on onetrace 0.8.0's own vectors: a run, a twin of it, a check of it, a step labelled by a
    #: framework hook, and self-hosted model calls in model-call-record/1.1.
    *(
        REPO / "tests" / "format_04_item8" / "accept" / name
        for name in (
            "A02-closed-recorder",
            "A06-twin",
            "A09-check-run",
            "A208-framework-graph",
            "A17-model-call-1-1-self-hosted",
        )
    ),
)
LINK_KINDS = {
    "lineage-stage": ("state-followup", "runs/{key}/stage-2.html"),
    "link-called-by": ("link-billing", "runs/{key}/case.html"),
    "link-calls": ("", "runs/{desk}/stage-2.html"),
    "link-twin-calls": ("", "runs/{twin}/stage-2.html"),
    "link-origin": ("", "origin-link-desk.html"),
    "expect-checked": ("expect-record", "runs/{key}/proof.html"),
    "code-case": ("code-dirty", "runs/{key}/case.html"),
    "code-rerun-parts": ("vector-code-of-lock", "runs/{key}/proof.html"),
    "confirmations": ("vector-real-effected", "runs/{key}/authorization.html"),
    "recovered-proof": ("refund-killed", "runs/{key}/proof.html"),
    "recovered-case": ("refund-killed", "runs/{key}/case.html"),
    "usage-stage": ("usage-a", "runs/{key}/stage-1.html"),
    "usage-cost": ("vector-model-members", "runs/{key}/case.html"),
    "rerun-case": ("vector-twin", "runs/{key}/case.html"),
    "check-run-case": ("vector-check", "runs/{key}/case.html"),
    "checked-case": ("vector-base", "runs/{key}/case.html"),
    "effect-stage": ("vector-framework-graph", "runs/{key}/stage-2.html"),
    "call-ended-stage": ("vector-model-call-1-1-self-hosted", "runs/{key}/stage-3.html"),
    "rerun-runs": ("", "runs"),
}


def _keys_of(listed: str, run_id: str) -> list[str]:
    """The keys of every run whose row in a runs list names `run_id`."""
    return sorted(set(re.findall(rf'<tr data-run="{re.escape(run_id)}" data-key="([0-9a-f]{{64}})"', listed)))


def _key_of(listed: str, run_id: str) -> str:
    """The key of the run whose row in a runs list names `run_id`: exactly one, or the check is refused."""
    (key,) = _keys_of(listed, run_id)
    return key


def _desks(listed: str, called_by: str) -> tuple[str, str]:
    """(the desk, its twin): two runs share the id `link-desk`; the callee's case page links the one its link's head
    picks, the console's own choice, and the other is the twin. Exactly one linked, or the check is refused."""
    keys = _keys_of(listed, "link-desk")
    (desk,) = [k for k in keys if f'data-link-run="{k}"' in called_by]
    (twin,) = [k for k in keys if k != desk]
    return desk, twin


#: The kinds read from the capture store (`demo --public --captures`), built and served beside the demo.
CAPTURE_KINDS = ("comparison-token-levels", "stage-close-calls")
#: The search the "search" kind draws, and the pair Compare makes for "visitor-comparison".
SEARCH = "search?q=setting%3A%2A.chunk_size%3D512"
#: The Runs page's views, each drawn as asked (`runs_page`).
RUNS_PAGES = {
    "runs-page": "runs",
    "runs-page-pipeline": "runs?pipeline=P1",
    "runs-page-2": "runs?page=2",
    #: The busy page's way back: one pipeline, a pair chosen in its picker.
    "runs-page-pair": "runs?pipeline=P1&a=p1-02-baseline-set2&b=p1-09-candidate-set3",
}
#: The first item in tab order on each kind that has a skip link, by its words.
SKIPS = {
    **{k: "Skip to the runs" for k in RUNS_PAGES},
    "comparison-line": "Skip to the first difference",
    "comparison-graph": "Skip to the first difference",
}
#: Investigate's short answer is within the first screen at every width: its bottom, from the page's top. Below 600 px
#: the frame folds to one bar (`frame.FOLD_CSS`), so the page starts under it.
ANSWER_WITHIN = 900
ANSWER_FROM_WIDTH = 0
ANSWER_KINDS = ("comparison-line", "comparison-graph")
VISITOR_PAIR = ("p1-02-baseline-set2", "p1-09-candidate-set3")

#: The only blocks allowed to scroll their content sideways: the verifier's output and code, each
#: kind named. Every other element that hides or scrolls content wider than its box fails, so
#: nothing on a page is cut off; a new kind of block fails until it is named here on purpose.
SCROLL_ALLOWED = (
    "pre.term",  # the receipt's black box: the verifier's output
    "pre[data-layer]",  # the run page's verifier rows and command
    "pre[data-quoted=report]",  # a verb's report, quoted
    "pre[data-section=headline-command]",
    "pre[data-section=manifest]",
    "pre[data-content]",  # a stage's verified output, as written
    "pre[data-hunk]",
    "pre[data-notes]",
    "pre[data-words]",
    "pre:has(> code)",  # a command to type
    "nav[data-section=views]",  # a page's tabs, one row scrolling sideways in its own labelled region at 760 and below
    ".visually-hidden",  # words said to a screen reader and clipped to one pixel on purpose: the gear's dot, a
    #: table's header for a column of links or marks (`words.hidden_header`)
    ".scroll-x:has(> pre.term)",  # the verifier's output in its labelled region, which scrolls in its place
    "[data-page=forwarding] input",  # a field on forwarding's page holding an address longer than itself, as a field does
)

#: Run in the page: every element past the window's right edge that isn't inside a region the
#: console draws to scroll sideways on purpose; and every element that hides or scrolls content
#: wider than its own box (overflow hidden, auto, scroll or clip), outside SCROLL_ALLOWED.
PROBE = """(allowed) => {
  const w = window.innerWidth;
  const inRegion = el => el.closest('.scroll-x, .graph-box, pre, details[data-cell=digest], nav[data-section=views]');
  const over = [];
  for (const el of document.querySelectorAll('body *')) {
    if (inRegion(el)) continue;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > w + 1) {
      over.push(el.tagName.toLowerCase() + (el.getAttribute('data-section') ? '[' + el.getAttribute('data-section') + ']' : '') + ' right=' + Math.round(r.right));
      if (over.length >= 5) break;
    }
  }
  const clipped = [];
  const ok = el => allowed.some(sel => el.matches(sel) || el.closest(sel));
  for (const el of document.querySelectorAll('body *')) {
    const ox = getComputedStyle(el).overflowX;
    if (!['hidden', 'auto', 'scroll', 'clip'].includes(ox)) continue;
    if (el.scrollWidth <= el.clientWidth + 1 || el.clientWidth === 0 || ok(el)) continue;
    const name = el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '')
      + (el.getAttribute('data-section') ? '[' + el.getAttribute('data-section') + ']' : '')
      + (el.getAttribute('data-scroll') ? '[scroll=' + el.getAttribute('data-scroll') + ']' : '');
    clipped.push(name + ' ' + ox + ' ' + el.scrollWidth + '>' + el.clientWidth);
    if (clipped.length >= 5) break;
  }
  // The runs list's run names, at desktop width: a name that breaks onto a new line anywhere but
  // after a hyphen is named, with where. Each character's line, read from its own box.
  const names = [];
  if (w >= 1024) for (const el of document.querySelectorAll('table[data-section=runs-table] td:first-child .mono')) {
    const t = el.firstChild;
    if (!t || t.nodeType !== 3) continue;
    const s = t.textContent;
    let top = null;
    for (let i = 0; i < s.length; i++) {
      const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 1);
      const box = r.getClientRects()[0];
      if (!box) continue;
      if (top !== null && box.top > top + 1 && s[i - 1] !== '-') { names.push(s + ' broken before ' + JSON.stringify(s.slice(i))); break; }
      top = box.top;
    }
    if (names.length >= 5) break;
  }
  // A graph box's text: every line drawn inside its own box, none past the box's right edge.
  const graphs = [];
  for (const node of document.querySelectorAll('svg.graph rect.node')) {
    const box = node.getBBox(), right = box.x + box.width;
    for (const t of node.parentElement.querySelectorAll(':scope > text')) {
      const b = t.getBBox();
      if (b.width > 0 && b.x + b.width > right) {
        graphs.push(JSON.stringify(t.textContent) + ' ends at ' + Math.round(b.x + b.width) + ', its box at ' + Math.round(right));
        if (graphs.length >= 5) break;
      }
    }
    if (graphs.length >= 5) break;
  }
  // A planted run on the public demo's Overview, a row of three cells: side by side at desktop
  // width (1024 and above); below it stacked, each below the one before; never past the window's right edge.
  const planted = [];
  for (const tr of document.querySelectorAll('tr[data-planted]')) {
    const name = tr.getAttribute('data-planted').slice(0, 12);
    const cells = [...tr.querySelectorAll(':scope > td')].map(c => c.getBoundingClientRect());
    if (cells.length !== 3) { planted.push(name + ' has ' + cells.length + ' cells'); }
    else if (w >= 1024 && !(cells[1].left >= cells[0].right - 1 && cells[2].left >= cells[1].right - 1)) {
      planted.push(name + ' cells not side by side at ' + w);
    } else if (w < 1024 && !(cells[1].top >= cells[0].bottom - 1 && cells[2].top >= cells[1].bottom - 1)) {
      planted.push(name + ' cells not stacked at ' + w);
    } else if (tr.getBoundingClientRect().right > w + 1) {
      planted.push(name + ' right=' + Math.round(tr.getBoundingClientRect().right) + ' past ' + w);
    }
    if (planted.length >= 5) break;
  }
  // The first item in tab order, by its words; and the short answer's bottom, from the page's top.
  const tabbable = [...document.querySelectorAll('a[href], button, input, select, textarea, summary, [tabindex]')]
    .filter(e => e.tabIndex >= 0 && !e.disabled && !e.closest('[hidden]') && e.type !== 'hidden');
  const first = tabbable.length ? tabbable[0].textContent.trim().replace(/\\s+/g, ' ').slice(0, 60) : '';
  const ans = document.querySelector('[data-short=headline]');
  const answer = ans ? Math.round(ans.getBoundingClientRect().bottom + window.scrollY) : null;
  return {doc: document.documentElement.scrollWidth, win: w, over: over, clipped: clipped, names: names, graphs: graphs, planted: planted, first: first, answer: answer};
}"""

#: Said by a browser script on its error output, for each page view: the view and each step as it
#: starts it; and a view that takes longer than its limit stops the script with a line the check reads.
WATCH = r"""
import json, os, sys, threading
_where = ["", ""]
def watch_view(text, limit):
    _where[:] = [text, ""]
    t = threading.Timer(limit, _stalled, (limit,))
    t.daemon = True
    t.start()
    return t
def view_done(result):
    # Each view's result as soon as it is judged, so a run that stalls later keeps it (`run_browser`'s retry).
    print("result: " + json.dumps(result), file=sys.stderr, flush=True)
def step(what):
    _where[1] = what
    print(f"{_where[0]}: {what}", file=sys.stderr, flush=True)
def _stalled(limit):
    print(f"stalled: {_where[0]}, waiting on {_where[1]}, for {limit:g} s", file=sys.stderr, flush=True)
    os._exit(3)
"""

BROWSER = (
    WATCH
    + r"""
import json, sys
from playwright.sync_api import sync_playwright
jobs = json.loads(sys.argv[1]); probe = sys.argv[2]; shots = sys.argv[3]; allowed = json.loads(sys.argv[4])
theme = sys.argv[5]; view_limit = float(sys.argv[6])
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for i, (url, name, width) in enumerate(jobs, 1):
        watch = watch_view(f"view {i} of {len(jobs)}: {name} at {width} ({url})", view_limit)
        step("a new page")
        page = b.new_page(viewport={"width": width, "height": 900}, color_scheme=theme)
        # the theme chosen as the console's own switch keeps it: dark is the default whatever the
        # system says, so a light page is one a reader chose light on
        page.add_init_script("try{localStorage.setItem('onetrace-console-theme'," + json.dumps(theme) + ")}catch(e){}")
        step("loading")
        page.goto(url, wait_until="networkidle")
        step("measuring")
        got = page.evaluate(probe, allowed)
        if shots:
            step("the screenshot")
            page.screenshot(path=f"{shots}/{name}-{width}.png", full_page=True)
        out.append({"page": name, "width": width, **got})
        view_done(out[-1])
        step("closing")
        page.close()
        watch.cancel()
    b.close()
print(json.dumps(out))
"""
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


#: The whole check's own limit, in seconds (`--timeout`): each step it waits on gets what is left of it.
TIMEOUT = 1800
#: One page view's limit in the browser, in seconds (`--view-timeout`): in the gates' runs each view took
#: a few seconds.
VIEW_TIMEOUT = 300


class Stopped(Exception):
    """The check stopped short; its reason, as its summary line says it."""


class Limit:
    """What is left of a check's limit."""

    def __init__(self, seconds: float):
        self.seconds = seconds
        self.deadline = time.monotonic() + seconds

    def left(self) -> float:
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise Stopped(f"stopped at its limit of {self.seconds:g} s")
        return left


def _what(cmd) -> str:
    """A command as the summary line names it: its program and what it was asked to run."""
    parts = [str(c) for c in (cmd if isinstance(cmd, (list, tuple)) else [cmd])]
    named = Path(parts[0]).name
    if "-m" in parts:
        named += " -m " + " ".join(parts[parts.index("-m") + 1 : parts.index("-m") + 3])
    elif "-c" in parts:
        named += " (the browser's script)" if "playwright" in parts[parts.index("-c") + 1] else " -c"
    return named


#: How many times a view whose page did not open is opened again: the open only, never the judgment.
RETRIES = 2
#: The steps that open a view: a stall at either is an open that did not happen.
OPENING = ("a new page", "loading")
_STALL = re.compile(r"stalled: view (\d+) of (\d+): (.*), waiting on (.*), for ([\d.]+) s$")


class Results(list):
    """The views' results, and how many times a view was opened again (`retries`)."""

    retries = 0


def run_browser(cmd: list, limit: Limit) -> list:
    """A browser script's results (it prints them as JSON). A view it stalled on, at its own limit or
    the whole check's, is named on the check's summary line: which view, its page and width, and the
    step it waited on (`WATCH`).

    Where the browser stalled opening a view (a new page, or loading its address), the script is run
    again from that view, keeping the views it judged before it: at most RETRIES times a view, each
    said on the check's output with its view and time; a view still not open after that fails by name.
    A stall while a view is judged (measured, its screenshot taken) is never retried. `cmd[3]` is the
    script's views, as both checks give them."""
    try:
        jobs = json.loads(cmd[3]) if len(cmd) > 3 else None
    except (TypeError, ValueError):
        jobs = None
    done, start, tries = Results(), 0, {}
    while True:
        run = cmd if jobs is None else [*cmd[:3], json.dumps(jobs[start:]), *cmd[4:]]
        got, stalled = _run_once(run, limit)
        if stalled is None:
            done.extend(got)
            return done
        m = _STALL.match(stalled)
        #: Only a stall line that names a view of this run's own list is read for a retry.
        if jobs is None or m is None or m.group(4) not in OPENING or int(m.group(2)) != len(jobs) - start:
            raise Stopped("the browser stalled at " + stalled[len("stalled: ") :])
        done.extend(got)
        at = start + int(m.group(1)) - 1
        tries[at] = tries.get(at, 0) + 1
        what = f"view {at + 1} of {len(jobs)}: {m.group(3)}"
        if tries[at] > RETRIES:
            raise Stopped(
                f"the browser could not open {what}: it did not open within {m.group(5)} s, "
                f"opened again {RETRIES} times"
            )
        done.retries += 1
        print(
            f"retry {tries[at]} of {RETRIES}: {what}, opened again at {time.strftime('%H:%M:%S', time.gmtime())} "
            f"UTC: it did not open within {m.group(5)} s ({m.group(4)})",
            flush=True,
        )
        start = at


def _run_once(cmd: list, limit: Limit) -> tuple[list, str | None]:
    """One run of the browser script: (its views' results, None), or, where it stalled, (the results of the
    views it judged before, its stall line)."""
    try:
        ran = subprocess.run(cmd, capture_output=True, text=True, timeout=limit.left())
    except subprocess.TimeoutExpired as e:
        err = e.stderr.decode("utf-8", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        last = [line for line in err.splitlines() if line.startswith("view ")]
        if not last:
            raise
        view, _, what = last[-1].rpartition(": ")
        raise Stopped(
            f"stopped at its limit of {limit.seconds:g} s, waiting on the browser at {view}, {what}"
        ) from None
    stall = [line for line in ran.stderr.splitlines() if line.startswith("stalled: ")]
    if stall:
        judged = [
            json.loads(line[len("result: ") :]) for line in ran.stderr.splitlines() if line.startswith("result: ")
        ]
        return judged, stall[-1]
    if ran.returncode != 0:
        print(ran.stderr[-3000:], file=sys.stderr)
        raise Stopped(f"the browser's run ended with exit {ran.returncode} (its error output is above)")
    return json.loads(ran.stdout), None


def guarded(name: str, theme: str, limit: Limit, check) -> int:
    """`check()`'s exit; any way it stops short -- its limit, a console that did not start, a step that
    failed -- said on the check's summary line, on its output, and exit 2."""
    try:
        return check()
    except Stopped as e:
        reason = str(e)
    except subprocess.TimeoutExpired as e:
        reason = f"stopped at its limit of {limit.seconds:g} s, waiting on {_what(e.cmd)}"
    except subprocess.CalledProcessError as e:
        reason = f"a step ended with exit {e.returncode}: {_what(e.cmd)}"
    except SystemExit as e:
        if not isinstance(e.code, str):
            raise
        reason = e.code
    except Exception as e:  # noqa: BLE001 -- any other way it stops short is said, never a bare traceback
        reason = f"{type(e).__name__}: {e}"
    print(f"{name} ({theme}): no page views judged, FAILED: {reason}", flush=True)
    return 2


def _pick(pages: Path) -> dict[str, str]:
    rels = sorted(p.relative_to(pages).as_posix() for p in pages.rglob("*.html"))
    chosen = {}
    for kind, pattern in KINDS.items():
        if pattern:
            hit = next((r for r in rels if re.fullmatch(pattern, r)), None)
            if hit:
                chosen[kind] = hit
    #: The comparisons' first tabs; a text diff's own page and the pair's Authorization tab are kinds of their own.
    diffs = [r for r in rels if r.startswith("diff/") and not r.endswith(("-text.html", "-authorization.html"))]
    pair_auth = [r for r in rels if re.fullmatch(r"diff/[0-9a-f]+-authorization\.html", r)]
    for rel in pair_auth:
        state = "gated" if 'data-state="gated"' in (pages / rel).read_text(encoding="utf-8") else "none"
        chosen.setdefault(f"pair-authorization-{state}", rel)
    #: A comparison that found a first difference first: the page with the most on it.
    diffs.sort(key=lambda r: 'data-section="first-difference"' not in (pages / r).read_text(encoding="utf-8"))
    for rel in diffs:
        shaped = 'data-shape="dag"' in (pages / rel).read_text(encoding="utf-8")
        chosen.setdefault("comparison-graph" if shaped else "comparison-line", rel)
    hit = next(
        (
            r
            for r in rels
            if re.fullmatch(KINDS["run"], r) and 'data-section="profile"' in (pages / r).read_text(encoding="utf-8")
        ),
        None,
    )
    if hit:
        chosen["run-benchmark"] = hit
    #: The Authorization page in both of its states: a run with no gated step ("No records"), and one
    #: whose gated steps it lists.
    auth = [r for r in rels if re.fullmatch(KINDS["authorization"], r)]
    gated = [r for r in auth if 'data-state="gated"' in (pages / r).read_text(encoding="utf-8")]
    if gated:
        chosen["authorization-gated"] = gated[0]
    plain = [r for r in auth if r not in gated]
    if plain:
        chosen["authorization"] = plain[0]
    #: The model's rows and choices at a first difference (L3 and L2), and a step's close-call view.
    levels = next((r for r in diffs if 'data-section="token-levels"' in (pages / r).read_text(encoding="utf-8")), None)
    if levels:
        chosen["comparison-token-levels"] = levels
    close = next(
        (
            r
            for r in rels
            if re.fullmatch(r"runs/[0-9a-f]+/stage-[0-9]+\.html", r)
            and "data-close-calls" in (pages / r).read_text(encoding="utf-8")
        ),
        None,
    )
    if close:
        chosen["stage-close-calls"] = close
    return chosen


def _served(base: str) -> dict[str, str]:
    """The kinds a public console draws as asked: the index's results, and a comparison Compare
    makes (its POST answered with the page's address)."""
    from urllib.parse import urlencode

    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    out = {"search": SEARCH, **RUNS_PAGES}
    body = urlencode({"a": VISITOR_PAIR[0], "b": VISITOR_PAIR[1]}).encode("ascii")
    req = urllib.request.Request(base + "/compare", data=body, method="POST")
    try:
        urllib.request.build_opener(Stay).open(req, timeout=300)
    except urllib.error.HTTPError as e:
        if e.code == 303:
            out["visitor-comparison"] = e.headers["Location"].lstrip("/")
    return out


def _every(pages: Path) -> dict[str, str]:
    """Every page, each named by its kind and its place among that kind's pages."""
    one = _pick(pages)
    rels = sorted(p.relative_to(pages).as_posix() for p in pages.rglob("*.html"))
    chosen, counts = {}, {}
    for rel in rels:
        kind = next(
            (k for k, pat in KINDS.items() if pat and re.fullmatch(pat.replace("stage-1", "stage-[0-9]+"), rel)),
            next((k for k, r in one.items() if r == rel), None)
            or ("comparison" if rel.startswith("diff/") else "other"),
        )
        counts[kind] = counts.get(kind, 0) + 1
        chosen[f"{kind}-{counts[kind]:03d}"] = rel
    for kind, rel in one.items():
        if kind not in _kinds_of(chosen):
            chosen[kind] = rel
    return chosen


def _kinds_of(chosen: dict[str, str]) -> set[str]:
    """The kinds `chosen` covers: its names, less any place number `_every` added."""
    out = set(chosen)
    for name in chosen:
        base, _, n = name.rpartition("-")
        if n.isdigit():
            out.add(base)
    return out


#: The check's own sabotage: planted pages the probe must judge, each with what it must find.
SELF_TEST = (
    ("a clipped box", '<div style="width:100px;overflow:hidden;white-space:nowrap">' + "x" * 400 + "</div>", True),
    (
        "a table scrolled inside its region",
        '<div class="scroll-x" style="width:120px;overflow-x:auto">'
        '<table><tr><td style="white-space:nowrap">' + "y" * 400 + "</td></tr></table></div>",
        True,
    ),
    (
        "the verifier's output, allowed",
        '<pre class="term" style="width:120px;overflow:auto">' + "[PASS   ] " + "z" * 400 + "</pre>",
        False,
    ),
    ("a block that fits", '<div style="width:300px;overflow:hidden">short</div>', False),
    (
        "a run name broken mid-word",
        '<table class="timeline" data-section="runs-table"><tr><td>'
        '<span class="mono" style="overflow-wrap:anywhere;display:block;width:4ch">p1-17-baseline-set2</span>'
        "</td><td>" + "w " * 50 + "</td></tr></table>",
        True,
    ),
    (
        "a run name broken at its hyphens",
        '<table class="timeline" data-section="runs-table"><tr><td style="width:1px">'
        '<span class="mono" style="overflow-wrap:break-word">p1-17-baseline-set2</span></td>'
        "<td>" + "w " * 50 + "</td></tr></table>",
        False,
    ),
    (
        "a graph box's line past its edge",
        '<svg class="graph" width="400" height="60"><g>'
        '<rect class="node" x="10" y="10" width="184" height="40"/><text x="20" y="35" '
        'style="font:12px monospace">' + "v" * 40 + "</text></g></svg>",
        True,
    ),
    (
        "a graph box's line inside it",
        '<svg class="graph" width="400" height="60"><g>'
        '<rect class="node" x="10" y="10" width="184" height="40"/><text x="20" y="35" '
        'style="font:12px monospace">' + "v" * 10 + "</text></g></svg>",
        False,
    ),
    (
        "a planted row's cells stacked at desktop width",
        '<table><tr data-planted="x">'
        '<td style="display:block">p1-15</td><td style="display:block">Its answer changed.</td>'
        '<td style="display:block">Contradicts its record</td></tr></table>',
        True,
    ),
    (
        "a planted row's cells side by side",
        '<table><tr data-planted="x"><td>p1-15</td>'
        "<td>Its answer changed.</td><td>Contradicts its record</td></tr></table>",
        False,
    ),
    (
        "a planted row past the window inside its region",
        '<div class="scroll-x"><table><tr data-planted="x">'
        '<td>p1-15</td><td style="white-space:nowrap">' + "u" * 400 + "</td><td>Contradicts its record</td>"
        "</tr></table></div>",
        True,
    ),
)

SELF_TEST_BROWSER = r"""
import json, sys
from playwright.sync_api import sync_playwright
cases = json.loads(sys.argv[1]); probe = sys.argv[2]; allowed = json.loads(sys.argv[3])
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 900})
    for name, html, _ in cases:
        page.set_content("<!doctype html><body>" + html + "</body>")
        got = page.evaluate(probe, allowed)
        out.append(bool(got["clipped"] or got["over"] or got["names"] or got["graphs"] or got["planted"]))
    b.close()
print(json.dumps(out))
"""


def self_test(browser_python: str) -> int:
    """The probe on planted pages: each must be judged as SELF_TEST says. Exit 1 if any is not."""
    ran = subprocess.run(
        [
            browser_python,
            "-c",
            SELF_TEST_BROWSER,
            json.dumps([list(c) for c in SELF_TEST]),
            PROBE,
            json.dumps(list(SCROLL_ALLOWED)),
        ],
        capture_output=True,
        text=True,
    )
    if ran.returncode != 0:
        print(ran.stderr[-3000:], file=sys.stderr)
        return 2
    judged = json.loads(ran.stdout)
    wrong = 0
    for (name, _html, want), got in zip(SELF_TEST, judged):
        wrong += got != want
        print(f"{'ok  ' if got == want else 'WRONG'} {name}: {'flagged' if got else 'passed'}")
    print(f"self-test: {len(SELF_TEST)} planted pages, {wrong} judged wrongly")
    return 1 if wrong else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--console-python", required=True)
    ap.add_argument("--browser-python", required=True)
    ap.add_argument("--shots", type=Path, default=None)
    ap.add_argument("--widths", default="1280,768,390")
    ap.add_argument(
        "--theme",
        choices=("light", "dark"),
        default="light",
        help="the theme each page is drawn in: chosen as the console's own switch keeps "
        "it, and asked of the browser as its colour scheme",
    )
    ap.add_argument(
        "--self-test", action="store_true", help="judge planted pages only (the check's own sabotage), then stop"
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=TIMEOUT,
        help="the whole check's limit, in seconds; past it the check stops and says so",
    )
    ap.add_argument(
        "--view-timeout",
        type=float,
        default=VIEW_TIMEOUT,
        help="one page view's limit in the browser, in seconds; past it the check stops and names the view",
    )
    ap.add_argument(
        "--every",
        action="store_true",
        help="every page the demo built, not one of each kind: a fault on one run's "
        "page (a long stage name, say) is found wherever it is",
    )
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test(args.browser_python)
    limit = Limit(args.timeout)
    return guarded("layout check", args.theme, limit, lambda: _check(args, limit))


def _wait(base: str, proc, what: str, limit: Limit) -> None:
    """Until `base` answers /health; Stopped where `proc` ends first or 300 s pass."""
    deadline = time.monotonic() + 300
    while True:
        try:
            urllib.request.urlopen(base + "/health", timeout=min(5, limit.left())).read()
            return
        except OSError:
            limit.left()
            if time.monotonic() > deadline or proc.poll() is not None:
                raise Stopped(f"{what} did not start") from None
            time.sleep(1)


def _check(args, limit: Limit) -> int:
    widths = [int(w) for w in args.widths.split(",")]
    port = _free_port()
    temp = Path(tempfile.mkdtemp(prefix="layout-check-"))
    env = {
        **{k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"},
        "PYTHONPATH": str(REPO / "src"),
        "TMPDIR": str(temp),
    }
    #: The console's output goes to a file, never an unread pipe: it writes a line per request,
    #: and a full pipe would stop it mid-run -- a page that never loads, after enough of them.
    log = open(temp / "console.log", "w", encoding="utf-8")
    proc = subprocess.Popen(
        [args.console_python, "-B", "-m", "onetrace_console", "demo", "--public", "--port", str(port)],
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=temp,
    )
    #: The capture store, built and served beside it, in a temporary folder of its own.
    ctemp = temp / "captures"
    ctemp.mkdir()
    cport = _free_port()
    clog = open(temp / "captures-console.log", "w", encoding="utf-8")
    cproc = subprocess.Popen(
        [args.console_python, "-B", "-m", "onetrace_console", "demo", "--public", "--captures", "--port", str(cport)],
        stdout=clog,
        stderr=subprocess.STDOUT,
        text=True,
        env={**env, "TMPDIR": str(ctemp)},
        cwd=ctemp,
    )
    #: Sign-in through Entra ID's pages, served beside them (`SIGNIN_KINDS`).
    sport = _free_port()
    sproc = subprocess.Popen(
        [args.console_python, "-B", str(REPO / "tools" / "signin_pages.py"), "--port", str(sport)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        cwd=temp,
    )
    #: Format 0.5's agent run, loaded by a local console of its own (`AGENT_KINDS`), from a copy in a folder of its own.
    atemp = temp / "agents"
    shutil.copytree(AGENT_RUN, atemp / "runs" / AGENT_RUN.name)
    shutil.copytree(STATE_RUN, atemp / "runs" / STATE_RUN.name)
    for run in LINK_RUNS:
        shutil.copytree(run, atemp / "runs" / run.name)
    #: The desk recorded again under the same run id: the callee's origin then names a run id two runs share.
    shutil.copytree(REPO / "tests" / "format_05_link_twin" / "link-desk", atemp / "runs" / "link-desk-twin")
    aport = _free_port()
    alog = open(temp / "agents-console.log", "w", encoding="utf-8")
    aproc = subprocess.Popen(
        [args.console_python, "-B", "-m", "onetrace_console", str(atemp / "runs"), "--port", str(aport), "--quiet"],
        stdout=alog,
        stderr=subprocess.STDOUT,
        text=True,
        env={**env, "TMPDIR": str(atemp)},
        cwd=atemp,
    )
    try:
        base, cbase, sbase = f"http://127.0.0.1:{port}", f"http://127.0.0.1:{cport}", f"http://127.0.0.1:{sport}"
        abase = f"http://127.0.0.1:{aport}"
        _wait(base, proc, "the demo console", limit)
        _wait(cbase, cproc, "the capture store's console", limit)
        _wait(sbase, sproc, "the sign-in pages", limit)
        _wait(abase, aproc, "the agent run's console", limit)
        listed = urllib.request.urlopen(f"{abase}/executions-all.html", timeout=min(30, limit.left())).read()
        akey = _key_of(listed.decode("utf-8"), AGENT_RUN.name)
        skey = _key_of(listed.decode("utf-8"), STATE_RUN.name)
        agents = {k: v.format(key=akey) for k, v in AGENT_KINDS.items()}
        agents |= {k: v.format(key=skey) for k, v in STATE_KINDS.items()}
        billing = _key_of(listed.decode("utf-8"), "link-billing")
        called_by = urllib.request.urlopen(f"{abase}/runs/{billing}/case.html", timeout=min(30, limit.left())).read()
        desk, twin = _desks(listed.decode("utf-8"), called_by.decode("utf-8"))
        agents |= {
            k: rel.format(key=_key_of(listed.decode("utf-8"), run_id) if run_id else "", desk=desk, twin=twin)
            for k, (run_id, rel) in LINK_KINDS.items()
        }
        (built,) = [p for p in temp.glob("onetrace-console-public-demo-*/demo")]
        (cbuilt,) = [p for p in ctemp.glob("onetrace-console-public-demo-*/demo")]
        chosen = {**(_every if args.every else _pick)(built / "store" / "pages"), **_served(base)}
        captured = {k: v for k, v in _pick(cbuilt / "store" / "pages").items() if k in CAPTURE_KINDS}
        chosen = {k: v for k, v in chosen.items() if k not in CAPTURE_KINDS}
        missing = sorted(
            set(KINDS)
            - set(_kinds_of(chosen))
            - set(captured)
            - set(SIGNIN_KINDS)
            - set(AGENT_KINDS)
            - set(STATE_KINDS)
            - set(LINK_KINDS)
        )
        jobs = [(f"{base}/{rel}", kind, w) for kind, rel in sorted(chosen.items()) for w in widths]
        jobs += [(f"{cbase}/{rel}", kind, w) for kind, rel in sorted(captured.items()) for w in widths]
        jobs += [(f"{sbase}/{rel}", kind, w) for kind, rel in sorted(SIGNIN_KINDS.items()) for w in widths]
        jobs += [(f"{abase}/{rel}", kind, w) for kind, rel in sorted(agents.items()) for w in widths]
        if args.shots:
            args.shots.mkdir(parents=True, exist_ok=True)
        results = run_browser(
            [
                args.browser_python,
                "-c",
                BROWSER,
                json.dumps(jobs),
                PROBE,
                str(args.shots or ""),
                json.dumps(list(SCROLL_ALLOWED)),
                args.theme,
                str(args.view_timeout),
            ],
            limit,
        )
    finally:
        for p in (proc, cproc, sproc, aproc):
            p.send_signal(signal.SIGTERM)
            try:
                p.wait(timeout=60)
            except subprocess.TimeoutExpired:
                p.kill()
        log.close()
        clog.close()
        alog.close()
    failed = 0
    for r in results:
        kind = r["page"]
        skip = SKIPS.get(kind) or SKIPS.get(kind.rpartition("-")[0] if kind.rpartition("-")[2].isdigit() else "")
        r["skip"] = f"first in tab order is {r.get('first')!r}, not {skip!r}" if skip and r.get("first") != skip else ""
        #: Every page with a short answer is held to it, and each answer kind must have one.
        r["late"] = (
            f"the short answer ends at {r.get('answer')} px, past {ANSWER_WITHIN}"
            if r["width"] >= ANSWER_FROM_WIDTH
            and (
                (r.get("answer") is not None and r["answer"] > ANSWER_WITHIN)
                or (kind in ANSWER_KINDS and r.get("answer") is None)
            )
            else ""
        )
        ok = (
            r["doc"] <= r["win"]
            and not r["over"]
            and not r["clipped"]
            and not r["names"]
            and not r["graphs"]
            and not r["planted"]
            and not r["skip"]
            and not r["late"]
        )
        failed += not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {r['page']:<17} {r['width']:>4}  document {r['doc']} "
            f"in {r['win']}"
            + (f"  past the edge: {'; '.join(r['over'])}" if r["over"] else "")
            + (f"  cut off or scrolled: {'; '.join(r['clipped'])}" if r["clipped"] else "")
            + (f"  run name broken off its hyphens: {'; '.join(r['names'])}" if r["names"] else "")
            + (f"  graph text past its box: {'; '.join(r['graphs'])}" if r["graphs"] else "")
            + (f"  planted runs: {'; '.join(r['planted'])}" if r["planted"] else "")
            + (f"  skip link: {r['skip']}" if r["skip"] else "")
            + (f"  {r['late']}" if r["late"] else "")
            + (f"  short answer ends at {r.get('answer')} px" if r.get("answer") is not None else "")
        )
    for kind in missing:
        print(f"MISSING {kind}: no page of this kind in the demo")
    if args.shots:
        sums = "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(args.shots.glob("*.png"))
        )
        (args.shots / "SHA256SUMS").write_text(sums, encoding="utf-8")
        (args.shots / "PAGES.json").write_text(
            json.dumps(
                {
                    **chosen,
                    **{k: f"captures/{v}" for k, v in captured.items()},
                    **{k: f"signin-pages/{v}" for k, v in SIGNIN_KINDS.items()},
                    **{k: f"agents/{v}" for k, v in AGENT_KINDS.items()},
                    **{k: f"agents/{v}" for k, v in STATE_KINDS.items()},
                    **{k: f"agents/{v[1]}" for k, v in LINK_KINDS.items()},
                },
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    retried = getattr(results, "retries", 0)
    print(
        f"layout check ({args.theme}): {len(results)} page views, {failed} failed, {len(missing)} kinds missing, "
        f"{retried} retries"
    )
    return 1 if failed or missing else 0


if __name__ == "__main__":
    sys.exit(main())
