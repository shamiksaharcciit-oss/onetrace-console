#!/usr/bin/env python3
"""explain_look_check.py -- the short answer, the explanation and the setup page, and since console
0.4.0 the run and comparison pages' new parts, at 1280 and 390 pixels wide, in the light and the dark
theme: nothing wider than the window, and every line of text in them at a contrast of 4.5:1 or more
against what it is drawn on.

Builds the public demo with the kept explanations (`deploy/fly/kept/`, as the image builds it) and
serves it; then a local console over the same kept runs, comparing P1's pair, with the P1
explanation kept beside it (`explain.keep`), served by a Python that has onetrace-explain
installed (`--local-python`), so its panel is the local one. The pages: the four kept comparisons
and P8 43->44 on the public console; the P1 comparison and the setup page on the local one, the
setup page once at each of its three steps. And a public demo built fresh (`demo --public`), whose
runs record onetrace 0.5.0's blocks: a gated run's page (records agree, and paid on a deny, its case
and its Proof), an agent's run page and its step with model-call records, a run's "What changed?",
and P1's and P10's comparisons (the trace panel; the descent). And the capture store built fresh
(`demo --public --captures`): its two comparisons (the model's rows and choices at the first difference) and a
capture run's step (its close-call view). Each is judged by
`layout_check.PROBE` (past the edge, cut off or scrolled) and by a contrast probe over PARTS. With
--shots DIR it saves a screenshot of each, and a SHA256SUMS over them.

A gate step, as tools/layout_check.py is. No model is called: the explanations are kept records.

Usage:
  python tools/explain_look_check.py --console-python PY --local-python PY --browser-python PY
                                     [--shots DIR] [--widths 1280,390] [--theme light|dark] [--self-test]
                                     [--timeout S] [--view-timeout S]
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
KEPT = REPO / "deploy" / "fly" / "kept"
_spec = importlib.util.spec_from_file_location("layout_check", REPO / "tools" / "layout_check.py")
layout_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(layout_check)

#: The public console's pages, by the two runs each compares: the four kept, and P8 43->44.
PUBLIC = {
    "kept-p1": ("p1-02-baseline-set2", "p1-08-candidate-set2"),
    "kept-p5": ("p5-32-pump-baseline", "p5-33-pump-offset-changed"),
    "kept-p8": ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"),
    "kept-p9": ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"),
    "p8-43-44": ("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed"),
}
LOCAL_PAIR = PUBLIC["kept-p1"]
#: The fresh public demo's pages: comparisons by their two runs, run pages by run and page.
FRESH_PAIRS = {
    "trace-p1": ("p1-02-baseline-set2", "p1-08-candidate-set2"),
    "descent-p10": ("pz-51-agent-baseline", "pz-53-agent-amount-changed"),
}
#: The capture store's pages (`demo --public --captures`), built and served beside the fresh demo.
CAPTURE_PAIRS = {
    "token-levels-p10": ("pz-59-agent-capture-baseline", "pz-61-agent-capture-row-changed"),
    "token-levels-batch-off": ("pz-59-agent-capture-baseline", "pz-63-agent-capture-batch-off"),
}
#: The committed token-level runs (a second small local store), and what each Tokenizers state's page holds and
#: does not hold.
TOKEN_RUNS = REPO / "tests" / "token_level_runs_071"
TOKENIZER_STATES = {
    "tokenizers-no-step": (("data-tokenizers-none",), ("data-tokenizer-wanted=",)),
    "tokenizers-steps": (("data-tokenizer-wanted=",), ("data-tokenizers-missing", "data-tokenizers-none")),
    "tokenizers-missing": (("data-tokenizer-wanted=", "data-tokenizers-missing"), ("data-tokenizers-none",)),
}
CAPTURE_RUNS = {"capture-step": ("pz-59-agent-capture-baseline", "stage-1.html")}
FRESH_RUNS = {
    "gated-agree": ("p8-42-invoice-tolerance-2pct", "case.html"),
    "gated-deny": ("p8-49-invoice-paid-on-deny", "case.html"),
    "gated-deny-proof": ("p8-49-invoice-paid-on-deny", "proof.html"),
    "agent": ("pz-51-agent-baseline", "case.html"),
    "agent-step": ("pz-51-agent-baseline", "stage-1.html"),
    "what-changed": ("p1-08-candidate-set2", "case.html"),
}
#: One page view's limit in the browser, in seconds, as the layout check's.
VIEW_TIMEOUT = layout_check.VIEW_TIMEOUT
#: The parts whose text the contrast probe reads.
PARTS = (
    ".short-answer",
    ".explain",
    ".setup",
    ".onedoor",
    ".span-context",
    ".trace-panel",
    ".nesting",
    '[data-section="descent"]',
    ".what-changed",
    ".model-call",
    ".token-levels",
    #: The status line a small action's press leaves in its own section.
    "[data-status]",
    #: The Tokenizers page: the steps that ask and the tokenizers kept.
    "[data-tokenizer-section]",
)

#: Run in the page: each element in the new parts with text of its own, drawn, whose text is
#: below 4.5:1 against the colour it sits on (its own background, or the nearest ancestor's that
#: is not transparent; a translucent one is laid over what is under it).
CONTRAST = """() => {
  const parse = c => { const m = c.match(/rgba?\\(([^)]+)\\)/); if (!m) return null;
    const p = m[1].split(/[ ,\\/]+/).filter(Boolean).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const over = (top, under) => [0, 1, 2].map(i => top[i] * top[3] + under[i] * (1 - top[3])).concat([1]);
  const ground = el => { const layers = [];
    for (let e = el; e; e = e.parentElement) { const b = parse(getComputedStyle(e).backgroundColor);
      if (b && b[3] > 0) { layers.push(b); if (b[3] >= 1) break; } }
    let c = [255, 255, 255, 1];
    for (let i = layers.length - 1; i >= 0; i--) c = over(layers[i], c);
    return c; };
  const bad = []; let seen = 0;
  for (const el of document.querySelectorAll(PARTS_SELECTOR)) {
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own) continue;
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    if (r.width === 0 || r.height === 0 || s.visibility === 'hidden' || s.display === 'none') continue;
    seen++;
    const fg = parse(s.color), bg = ground(el);
    const ink = over(fg, bg);
    const a = lum(ink), b = lum(bg), ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (ratio < 4.5) { bad.push(el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : '')
      + ' ' + JSON.stringify(el.textContent.trim().slice(0, 30)) + ' ' + ratio.toFixed(2)); if (bad.length >= 8) break; }
  }
  return {seen: seen, bad: bad};
}"""

BROWSER = (
    layout_check.WATCH
    + r"""
import json, sys
from playwright.sync_api import sync_playwright
jobs = json.loads(sys.argv[1]); probe = sys.argv[2]; contrast = sys.argv[3]; shots = sys.argv[4]
allowed = json.loads(sys.argv[5]); theme = sys.argv[6]; view_limit = float(sys.argv[7])
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for i, (url, name, width, anchor) in enumerate(jobs, 1):
        watch = watch_view(f"view {i} of {len(jobs)}: {name} at {width} ({url})", view_limit)
        step("a new page")
        page = b.new_page(viewport={"width": width, "height": 900}, color_scheme=theme)
        page.add_init_script("try{localStorage.setItem('onetrace-console-theme'," + json.dumps(theme) + ")}catch(e){}")
        step("loading")
        page.goto(url, wait_until="networkidle")
        if anchor.startswith("press:"):
            #: A small action pressed, its section updated in place: judged with its status line.
            step("pressing")
            sid = anchor[len("press:"):]
            if sid == "benchmark":
                page.click("section[data-section=benchmark] button[data-benchmark-post]")
                page.wait_for_function("() => (document.querySelector('[data-benchmark-said]') || {}).textContent",
                                       timeout=120000)
            else:
                page.click("#" + sid + " button[type=submit]")
                page.wait_for_function("(s) => (document.querySelector('#' + s + ' [data-status]') || {}).textContent",
                                       arg=sid, timeout=120000)
        step("measuring")
        got = page.evaluate(probe, allowed)
        seen = page.evaluate(contrast)
        if shots:
            step("the screenshot")
            if anchor.startswith("press:"):
                at = "[data-status]"
                page.evaluate("document.querySelector(" + json.dumps(at) + ").scrollIntoView({block:'center'})")
                page.screenshot(path=f"{shots}/{name}-{width}.png")
            elif anchor:
                page.locator("#" + anchor).scroll_into_view_if_needed()
                page.evaluate("document.getElementById(" + json.dumps(anchor) + ").scrollIntoView({block:'start'})")
                page.screenshot(path=f"{shots}/{name}-{width}.png")
            else:
                page.screenshot(path=f"{shots}/{name}-{width}.png", full_page=True)
        out.append({"page": name, "width": width, **got, "contrast": seen})
        view_done(out[-1])
        step("closing")
        page.close()
        watch.cancel()
    b.close()
print(json.dumps(out))
"""
)

#: The contrast probe's own sabotage: each planted page, and whether it must be flagged.
SELF_TEST = (
    ("grey on white", '<div class="explain" style="background:#fff"><p style="color:#aaa">faint</p></div>', True),
    ("dark ink on white", '<div class="explain" style="background:#fff"><p style="color:#333">plain</p></div>', False),
    (
        "amber word on its amber ground",
        '<div class="short-answer" style="background:#fdf3dc">'
        '<span style="color:#f5c873">First difference</span></div>',
        True,
    ),
    (
        "light ink on the dark surface",
        '<div class="setup" style="background:#122137"><p style="color:#a9b7cb">muted</p></div>',
        False,
    ),
)
SELF_TEST_BROWSER = r"""
import json, sys
from playwright.sync_api import sync_playwright
cases = json.loads(sys.argv[1]); contrast = sys.argv[2]
out = []
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 900})
    for name, html, _ in cases:
        page.set_content("<!doctype html><body>" + html + "</body>")
        out.append(bool(page.evaluate(contrast)["bad"]))
    b.close()
print(json.dumps(out))
"""


def self_test(browser_python: str) -> int:
    ran = subprocess.run(
        [browser_python, "-c", SELF_TEST_BROWSER, json.dumps([list(c) for c in SELF_TEST]), CONTRAST],
        capture_output=True,
        text=True,
    )
    if ran.returncode != 0:
        print(ran.stderr[-3000:], file=sys.stderr)
        return 2
    wrong = 0
    for (name, _, want), got in zip(SELF_TEST, json.loads(ran.stdout)):
        wrong += got != want
        print(f"{'ok  ' if got == want else 'WRONG'} {name}: {'flagged' if got else 'passed'}")
    print(f"self-test: {len(SELF_TEST)} planted pages, {wrong} judged wrongly")
    return 1 if wrong else 0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


#: What is left of this run's limit (`--timeout`), for every step it waits on.
LIMIT = layout_check.Limit(layout_check.TIMEOUT)


def _wait(base: str, proc, what: str) -> None:
    deadline = time.monotonic() + 300
    while True:
        try:
            urllib.request.urlopen(base + "/health", timeout=min(5, LIMIT.left())).read()
            return
        except OSError:
            LIMIT.left()
            if time.monotonic() > deadline or proc.poll() is not None:
                raise layout_check.Stopped(f"the {what} console did not start") from None
            time.sleep(1)


def _stop(proc) -> None:
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


CONTRAST = CONTRAST.replace("PARTS_SELECTOR", json.dumps(", ".join(f"{s} *, {s}" for s in PARTS)))


def _run_keys(python: str, env: dict, store: Path) -> dict[str, str]:
    code = (
        "import json,sys\nfrom onetrace_console.store import Store\n"
        "print(json.dumps({r.run_id: r.key for r in Store(sys.argv[1]).runs()}))"
    )
    return json.loads(
        subprocess.run(
            [python, "-B", "-c", code, str(store)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            timeout=LIMIT.left(),
        ).stdout
    )


def _keys(python: str, env: dict, store: Path, pairs: dict, wait: float = 0) -> dict[str, str]:
    """{name: the comparison's key} for each named pair of run ids, read from the store; waiting up
    to `wait` seconds for a comparison the console is still making."""
    deadline = time.monotonic() + wait
    while True:
        try:
            return _keys_now(python, env, store, pairs)
        except KeyError:
            if time.monotonic() > deadline:
                raise
            LIMIT.left()
            time.sleep(1)


def _keys_now(python: str, env: dict, store: Path, pairs: dict) -> dict[str, str]:
    code = (
        "import json,sys\nfrom onetrace_console.store import Store\ns=Store(sys.argv[1])\n"
        "ids={r.key:r.run_id for r in s.runs()}\n"
        "print(json.dumps({f'{ids.get(c.run_a)} {ids.get(c.run_b)}':c.key for c in s.comparisons()}))"
    )
    got = json.loads(
        subprocess.run(
            [python, "-B", "-c", code, str(store)],
            capture_output=True,
            text=True,
            env=env,
            check=True,
            timeout=LIMIT.left(),
        ).stdout
    )
    return {name: got[f"{a} {b}"] for name, (a, b) in pairs.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--console-python", required=True)
    ap.add_argument("--local-python", required=False, help="a Python with onetrace-explain installed")
    ap.add_argument("--browser-python", required=True)
    ap.add_argument(
        "--tokenizers-python",
        required=False,
        help="a Python with the console's packages and `tokenizers`, for the Tokenizers page with steps listed",
    )
    ap.add_argument("--shots", type=Path, default=None)
    ap.add_argument("--widths", default="1280,390")
    ap.add_argument("--theme", choices=("light", "dark"), default="light")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument(
        "--timeout",
        type=float,
        default=layout_check.TIMEOUT,
        help="the whole check's limit, in seconds; past it the check stops and says so",
    )
    ap.add_argument(
        "--view-timeout",
        type=float,
        default=VIEW_TIMEOUT,
        help="one page view's limit in the browser, in seconds; past it the check stops and names the view",
    )
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test(args.browser_python)
    if not args.local_python:
        ap.error("--local-python is required")
    global LIMIT
    LIMIT = layout_check.Limit(args.timeout)
    return layout_check.guarded("explain look check", args.theme, LIMIT, lambda: _check(args))


def _check(args) -> int:
    widths = [int(w) for w in args.widths.split(",")]
    temp = Path(tempfile.mkdtemp(prefix="explain-look-"))
    env = {
        **{k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"},
        "PYTHONPATH": str(REPO / "src"),
        "TMPDIR": str(temp),
        #: No model is named for the local console: its Explain is offered, and never pressed.
        "ONETRACE_EXPLAIN_CONFIG": str(temp / "explain.toml"),
    }
    procs, jobs = [], []
    #: A Tokenizers state the check could not reach: a failure, named.
    not_reached: list[str] = []
    try:
        build = temp / "public"
        subprocess.run(
            [
                args.console_python,
                "-B",
                "-m",
                "onetrace_console",
                "demo",
                "--public",
                "--build",
                str(build),
                "--runs-from",
                str(KEPT),
                "--explanations",
                str(KEPT),
            ],
            env=env,
            cwd=temp,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=LIMIT.left(),
        )
        port = _free_port()
        (temp / "public.json").write_text(
            json.dumps(
                {
                    "public": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "store_root": str(build / "store"),
                    "trust_file": str(build / "trust.json"),
                    "sign_in": {"enabled": False},
                }
            ),
            encoding="utf-8",
        )
        log = open(temp / "public.log", "w", encoding="utf-8")
        procs.append(
            subprocess.Popen(
                [args.console_python, "-B", "-m", "onetrace_console", "serve"],
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**env, "ONETRACE_CONSOLE_CONFIG": str(temp / "public.json")},
                cwd=temp,
            )
        )
        base = f"http://127.0.0.1:{port}"
        _wait(base, procs[-1], "public")
        keys = _keys(args.console_python, env, build / "store" / "store", PUBLIC)
        jobs += [(f"{base}/diff/{keys[n]}.html", n, w, "") for n in PUBLIC for w in widths]

        fresh = temp / "fresh"
        subprocess.run(
            [args.console_python, "-B", "-m", "onetrace_console", "demo", "--public", "--build", str(fresh)],
            env=env,
            cwd=temp,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=LIMIT.left(),
        )
        port = _free_port()
        (temp / "fresh.json").write_text(
            json.dumps(
                {
                    "public": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "store_root": str(fresh / "store"),
                    "trust_file": str(fresh / "trust.json"),
                    "sign_in": {"enabled": False},
                }
            ),
            encoding="utf-8",
        )
        log = open(temp / "fresh.log", "w", encoding="utf-8")
        procs.append(
            subprocess.Popen(
                [args.console_python, "-B", "-m", "onetrace_console", "serve"],
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**env, "ONETRACE_CONSOLE_CONFIG": str(temp / "fresh.json")},
                cwd=temp,
            )
        )
        base = f"http://127.0.0.1:{port}"
        _wait(base, procs[-1], "fresh public")
        keys = _keys(args.console_python, env, fresh / "store" / "store", FRESH_PAIRS)
        jobs += [(f"{base}/diff/{keys[n]}.html", n, w, "") for n in FRESH_PAIRS for w in widths]
        runs = _run_keys(args.console_python, env, fresh / "store" / "store")
        jobs += [(f"{base}/runs/{runs[rid]}/{page}", n, w, "") for n, (rid, page) in FRESH_RUNS.items() for w in widths]

        captured = temp / "captures"
        subprocess.run(
            [args.console_python, "-B", "-m", "onetrace_console", "demo", "--public", "--build", str(captured)]
            + ["--captures"],
            env=env,
            cwd=temp,
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=LIMIT.left(),
        )
        port = _free_port()
        (temp / "captures.json").write_text(
            json.dumps(
                {
                    "public": True,
                    "host": "127.0.0.1",
                    "port": port,
                    "store_root": str(captured / "store"),
                    "trust_file": str(captured / "trust.json"),
                    "sign_in": {"enabled": False},
                }
            ),
            encoding="utf-8",
        )
        log = open(temp / "captures.log", "w", encoding="utf-8")
        procs.append(
            subprocess.Popen(
                [args.console_python, "-B", "-m", "onetrace_console", "serve"],
                stdout=log,
                stderr=subprocess.STDOUT,
                env={**env, "ONETRACE_CONSOLE_CONFIG": str(temp / "captures.json")},
                cwd=temp,
            )
        )
        base = f"http://127.0.0.1:{port}"
        _wait(base, procs[-1], "capture store's public")
        keys = _keys(args.console_python, env, captured / "store" / "store", CAPTURE_PAIRS)
        jobs += [(f"{base}/diff/{keys[n]}.html", n, w, "") for n in CAPTURE_PAIRS for w in widths]
        runs = _run_keys(args.console_python, env, captured / "store" / "store")
        jobs += [
            (f"{base}/runs/{runs[rid]}/{page}", n, w, "") for n, (rid, page) in CAPTURE_RUNS.items() for w in widths
        ]

        local = temp / "local"
        local.mkdir()
        runs = local / "runs"
        runs.mkdir()
        for name in LOCAL_PAIR:
            shutil.copytree(KEPT / "runs" / name, runs / name)
        argv_local = [
            args.local_python,
            "-B",
            "-m",
            "onetrace_console",
            str(runs),
            "--trust",
            str(KEPT / "trust.json"),
            "--compare",
            *LOCAL_PAIR,
        ]
        for attempt in ("load", "serve"):
            port = _free_port()
            log = open(temp / f"local-{attempt}.log", "w", encoding="utf-8")
            procs.append(
                subprocess.Popen(
                    [*argv_local, "--port", str(port)], stdout=log, stderr=subprocess.STDOUT, env=env, cwd=local
                )
            )
            base = f"http://127.0.0.1:{port}"
            _wait(base, procs[-1], "local")
            if attempt == "load":
                #: Once the console has compared the pair, the P1 explanation kept beside its
                #: comparison, as a press keeps one; then the console started again, so its pages
                #: are drawn with it.
                _keys(args.local_python, env, local / "store" / "store", {"local-p1": LOCAL_PAIR}, wait=300)
                _stop(procs.pop())
                code = (
                    "import sys\nfrom pathlib import Path\nfrom onetrace_console import explain\n"
                    "from onetrace_console.store import Store\n"
                    "r=explain.keep(Path(sys.argv[1]), Store(sys.argv[2]))\nprint([k['record'] for k in r['kept']])"
                )
                kept = subprocess.run(
                    [args.local_python, "-B", "-c", code, str(KEPT), str(local / "store" / "store")],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=True,
                    timeout=LIMIT.left(),
                ).stdout
                #: The local store holds the P1 pair alone: exactly one explanation kept, one of the
                #: kept set's own records (read from deploy/fly/kept/explain, never typed here).
                records = sorted(p.name for p in (KEPT / "explain").iterdir() if p.is_dir())
                got = json.loads(kept.replace("'", '"'))
                if len(got) != 1 or got[0] not in records:
                    raise SystemExit(f"the local store did not keep the P1 explanation: {kept}")
        key = _keys(args.local_python, env, local / "store" / "store", {"local-p1": LOCAL_PAIR})["local-p1"]
        jobs += [(f"{base}/diff/{key}.html", "local-p1", w, "") for w in widths]
        jobs += [(f"{base}/explain/setup", "setup", w, "") for w in widths]
        jobs += [
            (f"{base}/explain/setup#step-{n}", f"setup-step-{n}", w, f"step-{n}") for n in (1, 2, 3) for w in widths
        ]
        #: The small actions' status lines, each pressed in place: "Always stop before sending"
        #: on Set up Explain, and Mark as benchmark (then its undo, at the second width) on the P1 baseline.
        jobs += [(f"{base}/explain/setup", "setup-in-place", w, "press:always-stop") for w in widths]
        local_runs = _run_keys(args.local_python, env, local / "store" / "store")
        jobs += [
            (f"{base}/runs/{local_runs[LOCAL_PAIR[0]]}/case.html", "benchmark-in-place", w, "press:benchmark")
            for w in widths
        ]
        #: The Tokenizers page in each of its states: no step asking (the local P1 store); steps listed
        #: (the committed token-level runs, a second small local store, served from a Python with `tokenizers`); and
        #: `tokenizers` missing (the same runs, served from one without). Each is read first for its state.
        jobs += [(f"{base}/model-tokenizers", "tokenizers-no-step", w, "") for w in widths]
        states = {"tokenizers-no-step": base}
        for name, python in (("tokenizers-steps", args.tokenizers_python), ("tokenizers-missing", args.console_python)):
            if not python:
                not_reached.append(f"{name}: no --tokenizers-python named")
                continue
            folder = temp / name
            (folder / "runs").mkdir(parents=True)
            for pair in sorted(p.name for p in TOKEN_RUNS.iterdir() if p.is_dir()):
                for side in ("a", "b"):
                    shutil.copytree(TOKEN_RUNS / pair / side, folder / "runs" / f"{pair}-{side}")
            port = _free_port()
            log = open(temp / f"{name}.log", "w", encoding="utf-8")
            procs.append(
                subprocess.Popen(
                    [python, "-B", "-m", "onetrace_console", str(folder / "runs"), "--port", str(port), "--quiet"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=folder,
                )
            )
            states[name] = f"http://127.0.0.1:{port}"
            _wait(states[name], procs[-1], name)
            jobs += [(f"{states[name]}/model-tokenizers", name, w, "") for w in widths]
        for name, at in states.items():
            page = urllib.request.urlopen(f"{at}/model-tokenizers", timeout=60).read().decode("utf-8")
            if not all(m in page for m in TOKENIZER_STATES[name][0]) or any(
                m in page for m in TOKENIZER_STATES[name][1]
            ):
                not_reached.append(f"{name}: the page is not in that state")
        if args.shots:
            args.shots.mkdir(parents=True, exist_ok=True)
        results = _browser(args.browser_python, jobs, args.shots, args.theme, args.view_timeout)
    finally:
        for p in procs:
            _stop(p)
    failed = len(not_reached)
    for line in not_reached:
        print(f"FAIL {line}")
    for r in results:
        c = r["contrast"]
        ok = r["doc"] <= r["win"] and not r["over"] and not r["clipped"] and c["seen"] > 0 and not c["bad"]
        failed += not ok
        print(
            f"{'ok  ' if ok else 'FAIL'} {r['page']:<14} {r['width']:>4}  document {r['doc']} in {r['win']}, "
            f"{c['seen']} text elements read for contrast"
            + (f"  past the edge: {'; '.join(r['over'])}" if r["over"] else "")
            + (f"  cut off or scrolled: {'; '.join(r['clipped'])}" if r["clipped"] else "")
            + (f"  below 4.5:1: {'; '.join(c['bad'])}" if c["bad"] else "")
        )
    if args.shots:
        sums = "".join(
            f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in sorted(args.shots.glob("*.png"))
        )
        (args.shots / "SHA256SUMS").write_text(sums, encoding="utf-8")
    retried = getattr(results, "retries", 0)
    print(f"explain look check ({args.theme}): {len(results)} page views, {failed} failed, {retried} retries")
    shutil.rmtree(temp, ignore_errors=True)
    return 1 if failed else 0


def _browser(browser_python: str, jobs: list, shots, theme: str, view_limit: float) -> list:
    """The browser script's results; a view it stalled on named on the summary line (`layout_check.run_browser`)."""
    return layout_check.run_browser(
        [
            browser_python,
            "-c",
            BROWSER,
            json.dumps(jobs),
            layout_check.PROBE,
            CONTRAST,
            str(shots or ""),
            json.dumps(list(layout_check.SCROLL_ALLOWED)),
            theme,
            str(view_limit),
        ],
        LIMIT,
    )


if __name__ == "__main__":
    sys.exit(main())
