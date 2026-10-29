#!/usr/bin/env python3
"""container_check.py -- what a running public console must answer, read over HTTP.

Standard library only, so it runs on a machine that has only Python and the address of the
console: container-check.yml runs it against the image built from deploy/fly/Dockerfile, and the
suite runs the same checks against a public console it starts itself (tests/test_public_mode.py).

Every check, and what it expects:
- `/health` answers 200;
- every page named answers 200, carries the banner once, carries every security header, and every
  inline script on it is one the Content-Security-Policy names by its sha256;
- one POST to each route that writes, and to a route that does not exist, declaring a body far
  larger than anything the console accepts and sending none of it: each answers 403 with the
  refusal at once -- a console that waited to read the body would answer late, or otherwise;
- one POST to Compare, the public console's one route that runs something, declaring the same
  body: it answers 413 at once, unread;
- with --log, the console's whole output (its access log): after its two start lines, every line
  is one JSON object with exactly the access log's five fields, or Compare's line with exactly its
  four (the pair, the outcome, the time taken, and when). Any other line -- the standard library's
  own request line, which carries the client's address, or anything else -- is named.

Usage:
  python3 tools/container_check.py BASE_URL --pages FILE
  python3 tools/container_check.py --log FILE
FILE lists one page path per line, relative to the pages folder (as `find -name '*.html'` gives
them), or, with --log, is the console's output. Prints one line per check and a RESULT line;
exits 1 if any check fails.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

#: The routes that write, and one that does not exist: every one is refused the same way.
ROUTES = ("/v1/runs", "/text-diff/more?c=0", "/benchmark?run=0&mark=yes", "/v1/decisions", "/signin",
          "/signout", "/no-such-route")
#: The public console's one route that runs something (Compare on a pipeline's own runs): a body
#: declared past its limit is refused at once, unread.
COMPARE_ROUTE = "/compare"
#: The headers every response carries in public mode.
HEADERS = ("X-Frame-Options", "X-Content-Type-Options", "Cross-Origin-Resource-Policy",
           "Referrer-Policy", "Strict-Transport-Security", "Content-Security-Policy")
#: The banner's opening words, and the refusal's.
BANNER = "A read-only demo of onetrace-console."
REFUSED = "This is a read-only demo of onetrace-console."
#: A refusal must arrive well inside the console's 30-second request timeout.
PROMPT_SECONDS = 5.0
#: What a POST declares and does not send.
DECLARED = 10 ** 9

#: The access log's fields, all of them and no others: no client address among them.
LOG_FIELDS = frozenset({"at", "principal", "method", "path", "status"})
#: Compare's line: the pair, the outcome and the time taken; no client address.
COMPARE_FIELDS = frozenset({"at", "compare", "outcome", "ms"})
#: A public console's two start lines, which come before its access log.
START_LINES = ("onetrace-console serving on ", "onetrace-console public mode: ")

_SCRIPT = re.compile(r"<script>(.*?)</script>", re.S)
_BANNER_TAG = '<p data-frame="banner">'


def fetch(base: str, path: str, timeout: float = 30.0) -> tuple[int, dict[str, str], bytes]:
    try:
        with urllib.request.urlopen(base.rstrip("/") + path, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read()
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, e.read()


def page_problems(status: int, headers: dict[str, str], body: bytes) -> list[str]:
    """What is wrong with one served page, or nothing."""
    out = []
    if status != 200:
        out.append(f"status {status}, not 200")
    out += [f"no {name} header" for name in HEADERS if name.lower() not in headers]
    text = body.decode("utf-8", "replace")
    if text.count(_BANNER_TAG) != 1 or BANNER not in text:
        out.append(f"the banner is there {text.count(_BANNER_TAG)} times, not once")
    csp = headers.get("content-security-policy", "")
    for script in _SCRIPT.findall(text):
        digest = base64.b64encode(hashlib.sha256(script.encode("utf-8")).digest()).decode()
        if f"'sha256-{digest}'" not in csp:
            out.append(f"an inline script the policy does not name (sha256-{digest})")
    return out


def raw_post(base: str, path: str, declared: int = DECLARED,
             timeout: float = 30.0) -> tuple[int, bytes, float]:
    """A POST that declares `declared` bytes and sends none: (status, body, seconds to answer)."""
    url = urlsplit(base)
    host, port = url.hostname, url.port or 80
    request = (f"POST {path} HTTP/1.1\r\nHost: {url.netloc}\r\nContent-Type: application/x-tar\r\n"
               f"Content-Length: {declared}\r\n\r\n").encode("ascii")
    started = time.monotonic()
    data = b""
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(request)
        try:
            while chunk := s.recv(65536):
                data += chunk
        except ConnectionResetError:
            pass
    seconds = time.monotonic() - started
    head, _, body = data.partition(b"\r\n\r\n")
    match = re.match(rb"HTTP/1\.[01] (\d{3})", head)
    return (int(match.group(1)) if match else 0), body, seconds


def compare_problems(status: int, body: bytes, seconds: float) -> list[str]:
    """Compare, sent a body declared past its limit: refused at once with 413, unread."""
    out = [] if status == 413 else [f"status {status}, not 413"]
    if seconds > PROMPT_SECONDS:
        out.append(f"answered after {seconds:.1f} s: it waited for the body")
    return out


def refusal_problems(status: int, body: bytes, seconds: float) -> list[str]:
    out = []
    if status != 403:
        out.append(f"status {status}, not 403")
    if REFUSED.encode("utf-8") not in body:
        out.append("not the refusal's words")
    if seconds > PROMPT_SECONDS:
        out.append(f"answered after {seconds:.1f} s: it waited for the body")
    return out


def log_problems(lines: list[str]) -> list[str]:
    """Every line of a public console's output that is not one of its two start lines or an
    access-log entry of exactly the five fields, named by its number."""
    out, started = [], set()
    for number, line in enumerate(lines, 1):
        line = line.rstrip("\r\n")
        if not line.strip():
            continue
        start = next((s for s in START_LINES if line.startswith(s)), None)
        if start is not None and start not in started:
            started.add(start)
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            entry = None
        if not isinstance(entry, dict) or set(entry) not in (LOG_FIELDS, COMPARE_FIELDS) or (
                set(entry) == COMPARE_FIELDS and (not isinstance(entry["compare"], dict)
                                                  or set(entry["compare"]) != {"a", "b"})):
            out.append(f"line {number} is not an access-log entry: {line[:120]}")
    return out


def run(base: str, pages: list[str], say=print) -> bool:
    ok = True

    def report(what: str, problems: list[str]) -> None:
        nonlocal ok
        ok = ok and not problems
        say(f"{'ok  ' if not problems else 'FAIL'} {what}" + "".join(f"\n       {p}" for p in problems))

    status, headers, _ = fetch(base, "/health")
    report("/health", ([] if status == 200 else [f"status {status}"])
           + [f"no {n} header" for n in HEADERS if n.lower() not in headers])
    for rel in pages:
        report(f"/{rel}", page_problems(*fetch(base, "/" + rel)))
    for route in ROUTES:
        report(f"POST {route}", refusal_problems(*raw_post(base, route)))
    report(f"POST {COMPARE_ROUTE}", compare_problems(*raw_post(base, COMPARE_ROUTE)))
    say(f"RESULT: {'all hold' if ok else 'a check failed'} ({len(pages)} pages, {len(ROUTES)} routes)")
    return ok


def check_log(path: str, say=print) -> bool:
    with open(path, encoding="utf-8", errors="replace") as fh:
        lines = fh.readlines()
    problems = log_problems(lines)
    entries = sum(1 for line in lines if line.startswith("{"))
    for problem in problems:
        say(f"FAIL {problem}")
    say(f"RESULT: {'all hold' if not problems else 'a line is not the access log'} "
        f"({len(lines)} lines, {entries} access-log entries, {len(problems)} other lines)")
    return not problems and entries > 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("base", nargs="?")
    ap.add_argument("--pages", help="a file listing page paths, one per line")
    ap.add_argument("--log", help="the console's output, to read as its access log")
    a = ap.parse_args(argv)
    if a.log is not None:
        if a.base or a.pages:
            ap.error("--log reads the output alone; give no address or pages with it")
        return 0 if check_log(a.log) else 1
    if not a.base or not a.pages:
        ap.error("give the console's address and --pages FILE, or --log FILE")
    with open(a.pages, encoding="utf-8") as fh:
        pages = [line.strip().removeprefix("./") for line in fh if line.strip()]
    if not pages:
        print("no pages listed", file=sys.stderr)
        return 1
    return 0 if run(a.base, pages) else 1


if __name__ == "__main__":
    raise SystemExit(main())
