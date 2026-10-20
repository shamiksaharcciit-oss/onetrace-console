"""`onetrace-console serve`: the one thing the first order said would arrive later and never did.

`__main__.py` has said, since that first order, *"Nothing is served yet... `serve` arrives with
ingest, the store, the check runner and the two pages."* Those four things all arrived, across
the orders that followed -- as a LIBRARY, called from tests and from `tools/offline_check.py`'s
own manual script. No HTTP surface was ever built to call them from outside a test process. The
container order asks for the console *"listening on 127.0.0.1 inside"* a container, which cannot
be true of a library with no server -- so this module is that server, built now because that
order's own checklist (ingest, every page, the check runner, a comparison, Incidents, all
reachable with `--network none`) has no other way to be true.

NO NEW LOGIC HERE
------------------
Every request handler is a thin wrapper calling functions this repository already had:
`ingest.accept`, `checks.run_and_record`, `compare.compare`, `pages.render_execution`,
`render.render_all`, `render.render_diff`. This module's only job is turning an HTTP request
into a call to one of them and writing what came back to disk under the store's own root, so a
plain GET can serve it afterwards -- no page is rendered on every GET; rendering happens once,
at the point something changed (an ingest, a check, a comparison), the same "render once, serve
the bytes" shape a static site generator uses.

WHY PAGES LIVE UNDER THE STORE ROOT, NOT SOMEWHERE ELSE
----------------------------------------------------------
The container order asks for **one** data volume, for the store. Rendered pages are DERIVED
from the store's own content deterministically (the same content-addressed rendering this whole
console is built on), but they still need to survive a container restart to be useful, and a
second volume is a second thing to mount and back up for no reason -- so they are written under
`<store-root>/pages/`, inside the one volume the order already asks for.

ROUTES
------
    GET  /health                    "ok", for the container's HEALTHCHECK
    GET  /                          the Home page
    GET  /<anything else>           a file under <store-root>/pages/<path>, verbatim
    POST /v1/runs                    body: a delivery (tar bytes, the same shape
                                    `tests/conftest.py`'s `delivery` fixture builds).
                                    Accepts, checks, renders that run's pages and every
                                    page `render_all` covers. Responds with a small JSON
                                    summary; never partial writes on a refusal (accept()
                                    is what refuses, not this handler).
    POST /compare?a=<key>&b=<key>   the two stored runs' keys (StoredRun.key, the same
                                    value `POST /v1/runs`'s response names). Compares,
                                    renders the Diff page and refreshes `render_all`.

Nothing here calls out. The only sockets this process opens are the one it listens on and
whatever `subprocess.run` opens for the verifier and the SDK's own verbs -- both of those are
local processes, not network connections; `checks.py` and `compare.py` already document that
this whole console never re-queries a model.
"""
from __future__ import annotations

import errno
import json
import os
import re
import socket
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from onetrace_console.config import Config
from onetrace_console.store import Store

#: Where rendered pages are written, relative to the store's own root -- inside the one
#: data volume, not a second one.
#: The console's own static files: the bundled IBM Plex fonts and their OFL
#: text, served to anyone -- the signed-out sign-in page uses them -- at exactly these paths and no
#: others. Built from the shipped folder, so a file added there is served only by being shipped.
_STATIC_TYPES = {".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
                 ".svg": "image/svg+xml"}
STATIC_FILES = {f"/static/fonts/{p.name}": p
                for p in sorted((Path(__file__).parent / "static" / "fonts").glob("*"))
                if p.suffix in _STATIC_TYPES}
#: The console's icon, in the skin's navigation colours; console pages link it (viewer/page.py).
STATIC_FILES["/static/favicon.svg"] = Path(__file__).parent / "static" / "favicon.svg"

PAGES_DIRNAME = "pages"
#: Where local accounts live, relative to the store's own root. A sibling of
#: `pages/` and `store/store`, inside the one mounted volume, the same reasoning as both.
ACCOUNTS_DIRNAME = "accounts"
#: Where ingester bearer tokens live. A sibling of `accounts/`,
#: same reasoning: mutable records (a token is revoked in place), inside the one
#: mounted volume.
TOKENS_DIRNAME = "tokens"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _write(root: Path, rel: str, html: str) -> None:
    target = root / PAGES_DIRNAME / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html.encode("utf-8")
    except UnicodeEncodeError as e:
        #: The last guard (the second confirmation review, B1): a page that cannot be written
        #: as UTF-8 is written as the page saying so, and the traceback goes to the log.
        from onetrace_console.pages import refusal
        from onetrace_console.unreadable import render_failed_page
        html = render_failed_page(refusal(e)[0], generated_at=_now())
    #: The page's own bytes, not text mode: on Windows text mode wrote CRLF after the page was
    #: sealed, and no run page's fingerprint checked (the third confirmation review, NEW-4).
    target.write_bytes(html.encode("utf-8"))


def _remove_policy_pages_not_in(root: Path, keep: set[str]) -> None:
    """Remove the Policy pages (policy.html, policy-*.html, policy/*.html) that are not in
    `keep`. Only these generated pages, never anything else under the pages folder."""
    pages = root / PAGES_DIRNAME
    candidates = list(pages.glob("policy.html")) + list(pages.glob("policy-*.html")) \
        + list((pages / "policy").glob("*.html"))
    for path in candidates:
        if path.relative_to(pages).as_posix() not in keep:
            path.unlink()


def _rendering(config: Config | None):
    """The configuration a sealed page's frame states, for a render now. With
    no configuration -- a caller outside a running console -- sealed pages are drawn unframed."""
    import contextlib
    from onetrace_console.frame import rendering
    if config is None:
        return contextlib.nullcontext()
    return rendering(onedoor=bool(config.extensions.get("onedoor")),
                     sign_in=bool(config.sign_in.get("enabled")), public=config.public)


def _render_run_pages(run, store: Store, root: Path, config: Config | None = None) -> None:
    from onetrace_console.pages import (ANSWER, AUTHORIZATION, CASE, RUN_PROOF, PageError,
                                        render_execution)
    try:
        with _rendering(config):
            pages = render_execution(run, store, generated_at=_now()).pages
    except Exception as e:  # noqa: BLE001 - PageError and anything else: said, and logged
        if not isinstance(e, PageError):
            #: Whatever else escapes one run's pages never stops the rest, or the start (the
            #: third confirmation review, NEW-1).
            from onetrace_console.pages import refusal
            from onetrace_console.unreadable import render_unreadable_run
            from onetrace_console.authorization import render_authorization
            reason, from_viewer = refusal(e)
            page = render_unreadable_run(run, reason, generated_at=_now(),
                                         from_viewer=from_viewer)
            pages = {ANSWER: page, CASE: page, RUN_PROOF: page,
                     AUTHORIZATION: render_authorization(run, generated_at=_now(), case=CASE)}
            for name, html in pages.items():
                _write(root, f"runs/{run.key}/{name}", html)
            return
        #: A stored run with no check report -- its check did not complete when it was
        #: received. The run page is refused, as always; here the console says so, and one
        #: such run never keeps the console from starting (the second confirmation review, B2).
        from onetrace_console.authorization import render_authorization
        from onetrace_console.unreadable import render_unchecked_run
        page = render_unchecked_run(run, generated_at=_now())
        pages = {ANSWER: page, CASE: page, RUN_PROOF: page,
                 AUTHORIZATION: render_authorization(run, generated_at=_now(), case=CASE)}
    for name, html in pages.items():
        _write(root, f"runs/{run.key}/{name}", html)


def _render_all_pages(store: Store, root: Path, config: Config | None = None) -> None:
    from onetrace_console.render import render_all
    with _rendering(config):
        rendered = render_all(store, generated_at=_now())
    for href, html in rendered.items():
        _write(root, href, html)
    if config is not None and config.extensions.get("onedoor"):
        #: Imported only here, only when the extension is on. `_render_incidents_page`
        #: OVERWRITES incidents.html (already written above by the base render_all) with
        #: the merged rule table -- the base render is never skipped, only superseded,
        #: so a bug in this branch cannot leave incidents.html half-written.
        from onetrace_console.onedoor_ext.policy_pages import render_policy_pages
        from onetrace_console.onedoor_ext.decision_incidents import RULE, incident_page_args
        from onetrace_console.incident_pages import INCIDENTS, render_incidents, \
            render_rule_list, rule_href

        policy = render_policy_pages(store, generated_at=_now())
        #: GET serves whatever is on disk, so a Policy page this render no longer produces
        #: (a verdict filter whose only row can no longer be checked, the couldn't-check
        #: filter once nothing is unchecked) is removed, never left showing an old value.
        _remove_policy_pages_not_in(root, set(policy))
        for href, html in policy.items():
            _write(root, href, html)

        args = incident_page_args(store)
        _write(root, INCIDENTS, render_incidents(store, generated_at=_now(), **args))
        _write(root, rule_href(RULE.id),
               render_rule_list(store, RULE.id, generated_at=_now(), **args))


def _render_diff_page(comparison, store: Store, root: Path) -> str:
    from onetrace_console.render import render_diff
    from onetrace_console import views
    html = render_diff(comparison, store, generated_at=_now())
    rel = f"diff/{comparison.key}.html"
    #: Its two views: "What changed" at the page's address, "Proof" beside it.
    said, state = views.pair_said(comparison, store)
    what, proof = views.split(html, "diff", f"{comparison.key}.html",
                              views.proof_name(f"{comparison.key}.html"), said, state, views.WITHHELD_PAIR)
    _write(root, rel, what)
    _write(root, f"diff/{views.proof_name(comparison.key + '.html')}", proof)
    #: Its text diff on a page of its own, where it has one shown; where it has none, no page --
    #: never one left from an earlier drawing.
    from onetrace_console.textdiff_page import page_name, render_text_diff_page
    text = render_text_diff_page(comparison, store, generated_at=_now())
    if text is not None:
        _write(root, f"diff/{page_name(comparison)}", text)
    else:
        (root / PAGES_DIRNAME / "diff" / page_name(comparison)).unlink(missing_ok=True)
    return rel


def _render_startup_pages(store: Store, root: Path, config: Config | None = None) -> None:
    """Every page `pages/` should hold, rebuilt from `store/` alone -- so a restart is a
    re-render, never a loss. `_render_all_pages` alone (Home, the tally pages, Incidents,
    the rule lists) is not enough on its own: it does not touch a run's own detail pages
    (`answer.html`/`case.html`) or an existing comparison's Diff page, both of which are
    rendered on demand at ingest/compare time and were otherwise simply absent until the
    NEXT ingest or compare after a restart -- found while writing the operator README's
    claim that `pages/` can always be regenerated from `store/` alone, which was not yet
    true until every already-stored run and comparison was covered here too.
    """
    #: Runs stored before the follow-up batch -- or by any earlier derivation -- are re-derived
    #: first, from their stored bytes and without running their check again: rung 3, the
    #: receipts delivered, the list row and the digests.
    from onetrace_console.checks import DERIVED, rederive
    for run in store.runs():
        if run.derived != DERIVED:
            try:
                rederive(run, store)
            except Exception:  # noqa: BLE001 - the run keeps what it had; logged
                import traceback
                traceback.print_exc(file=sys.stderr)
    #: A run whose stored check ran with another trust file, or another time-stamp authority,
    #: than the ones set now is checked again, so its Signed and Committed rungs are the current
    #: files' -- and said, never silent. The same files: not checked again.
    from onetrace_console.checks import (check_options, run_and_record, stored_trust_record,
                                         stored_tsa_record, trust_record, tsa_record)
    options = check_options(config)
    current = trust_record(options["trust_file"])
    current_tsa = tsa_record(options["tsa_cert"], options["tsa_roots"])
    rechecked = 0
    for run in store.runs():
        recorded, recorded_tsa = stored_trust_record(run, store), stored_tsa_record(run, store)
        if recorded is not None and (recorded != current or recorded_tsa != current_tsa):
            try:
                run_and_record(run, store, **options)
                rechecked += 1
            except Exception:  # noqa: BLE001 - the run keeps its earlier check; logged
                import traceback
                traceback.print_exc(file=sys.stderr)
    if rechecked:
        print(f"onetrace-console: the trust file is now {current} and the time-stamp authority "
              f"{current_tsa}; {rechecked} stored run(s) checked again with them", file=sys.stderr)
    for run in store.runs():
        _render_run_pages(run, store, root, config)
    for key in store.unreadable_run_keys:
        _render_unreadable_record_pages(store, root, key, kind="run")
    for comparison in store.comparisons():
        try:
            _render_diff_page(comparison, store, root)
        except Exception as e:  # noqa: BLE001 - that page says so, and the log has it
            #: One comparison's failure never keeps the console from starting (the second
            #: confirmation review).
            from onetrace_console.pages import refusal
            from onetrace_console.unreadable import render_failed_page
            from onetrace_console.textdiff_page import page_name
            from onetrace_console.views import proof_name
            for name in (f"diff/{comparison.key}.html", f"diff/{proof_name(comparison.key + '.html')}",
                         f"diff/{page_name(comparison)}"):
                _write(root, name, render_failed_page(refusal(e)[0], generated_at=_now()))
    for key in store.unreadable_comparison_keys:
        _render_unreadable_record_pages(store, root, key, kind="comparison")
    _render_all_pages(store, root, config)


def _render_unreadable_record_pages(store: Store, root: Path, key: str, *, kind: str) -> None:
    """The pages of a stored record this version cannot read, replaced by pages saying so.

    An unreadable comparison record was once left out of every count, and its old Diff
    page stayed on disk and was served, saying whatever it said before. The same held for a run
    record's own pages. Only a record named by a content address has pages to replace."""
    from onetrace_console.pages import ANSWER, AUTHORIZATION, CASE, RUN_PROOF
    from onetrace_console.views import proof_name
    from onetrace_console.store import _SHA256
    from onetrace_console.unreadable import render_failed_page
    if not _SHA256.fullmatch(key):
        return
    named = store.unreadable_runs if kind == "run" else store.unreadable_comparisons
    said = next((u for u in named if u.startswith(f"{key}.json")), f"{key}.json")
    reason = (f"the stored {kind} record {said} cannot be read, so nothing is drawn from it; "
              f"the Overview names it")
    page = render_failed_page(reason, generated_at=_now())
    from onetrace_console.textdiff_page import SUFFIX
    names = ([f"runs/{key}/{n}" for n in (ANSWER, CASE, RUN_PROOF, AUTHORIZATION)] if kind == "run"
             else [f"diff/{key}.html", f"diff/{proof_name(key + '.html')}", f"diff/{key}{SUFFIX}"])
    for name in names:
        _write(root, name, page)


#: The answer to `POST /compare?a=K&b=K`.
SAME_RUN = ("the same run: a and b name one run, so there is nothing to compare, and no "
            "comparison was made")


class ConsoleServer(ThreadingHTTPServer):
    """The console's listener: the standard threading server, holding its port alone.

    `http.server.HTTPServer` sets `allow_reuse_address`, so the
    standard server asks for `SO_REUSEADDR`; on Windows that lets a second socket bind the
    port this one listens on, and the two then share its connections. So on Windows this asks
    for `SO_EXCLUSIVEADDRUSE` instead (the two cannot be combined there), and a second
    console fails to bind -- `main()` says so plainly. Elsewhere `SO_REUSEADDR` only lets a
    restart take a port still in TIME_WAIT, and the kernel already refuses a second listener,
    so it is kept.
    """

    allow_reuse_address = os.name != "nt"

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        """A request that raised. The standard server prints "Exception occurred during processing
        of request from" the client's address and port, then the traceback. A public console writes
        one JSON line instead -- when, that it was an error, the exception's type and the traceback
        -- and no address or port. The request's path is not known here, so it is not given. Any
        other console prints as the standard server does."""
        config = getattr(self.RequestHandlerClass, "config", None)
        if config is None or not config.public:
            super().handle_error(request, client_address)
            return
        error = sys.exc_info()[1]
        line = json.dumps({"at": _now(), "event": "error",
                           "exception": type(error).__name__ if error is not None else "unknown",
                           "traceback": traceback.format_exc()}, ensure_ascii=False)
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


class ConsoleServer6(ConsoleServer):
    """The same listener on an IPv6 host such as `::1`, which the local guard already names
    as this machine's own (the second confirmation review, N1: it was refused as unresolvable)."""

    address_family = socket.AF_INET6


#: One intake at a time: a run delivered by `POST /v1/runs` and one the folder watcher takes in
#: (`watch.py`) each write the store and draw pages, and never at once.
INTAKE_LOCK = threading.RLock()


class Handler(BaseHTTPRequestHandler):
    store_root: Path       # set by `main()` before the server starts
    store: Store           # ditto
    config: Config         # ditto -- the upload-hardening limits
    access_log: "AccessLog"  # ditto
    #: Sign-in step 2. `None` when `sign_in.enabled` is false -- the disabled
    #: console never constructs any of these (see `main()`), so a disabled server's
    #: Handler never even has real values here to begin with.
    account_store: object = None
    session_store: object = None
    rate_limit_per_account: object = None
    rate_limit_per_client: object = None
    #: `token_store` is `None` under the same "disabled means unconstructed" rule as
    #: the four above; `rate_limit_concurrent_hashes` guards `verify_password` itself,
    #: independent of which account or client is asking.
    token_store: object = None
    rate_limit_concurrent_hashes: object = None
    #: Local mode's port, or `None` in config-file mode. When set, every
    #: request passes `_local_guard` first.
    local_port: int | None = None
    #: The folder watcher (`watch.py`), in `onetrace-console <runs folder>` mode only.
    watcher: object = None

    server_version = "onetrace-console/0.1"

    def setup(self) -> None:
        """Each request keeps the store it started with. The class holds
        the console's store; a request reads it once, here, so a request that outlives its client
        -- or a store swapped while it runs -- never writes a run's objects to one store and its
        record to another."""
        cls = type(self)
        self.store = getattr(cls, "store", None)
        self.store_root = getattr(cls, "store_root", None)
        super().setup()

    def _local_guard(self, method: str) -> bool:
        """Local mode's browser guard. `True` if the request may proceed; `False` means a
        refusal has already been sent.

        Loopback keeps other machines out, not the browser on this one: a web page the local
        user opens can send a "simple" POST to 127.0.0.1, and a hostile name can be pointed at
        127.0.0.1 so that the browser reads pages from it (DNS rebinding). With no sign-in to
        stand in the way, local mode answers only requests that name this listener's own
        loopback address as their Host, and refuses any write that says it comes from another
        origin -- by its Origin header, or by the browser's own Sec-Fetch-Site.
        """
        port = self.local_port
        if port is None:
            return True
        own = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        #: One of each, or none of the optional two: two Hosts is a 400 (RFC 9112 §3.2), and
        #: two Origins or two Sec-Fetch-Sites cannot be read as one.
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or any(len(self.headers.get_all(h) or []) > 1
                                  for h in ("Origin", "Sec-Fetch-Site")):
            self._respond(400, b"a request must carry exactly one Host, and at most one "
                               b"Origin and one Sec-Fetch-Site\n", "text/plain")
            return False
        host = hosts[0].strip().lower()
        #: An absolute-form request-target names its own authority; it must be ours too.
        target = urlsplit(self.path)
        if host not in own or (target.scheme and target.netloc.lower() not in own):
            self._respond(421, f"local mode answers only its own loopback address: "
                               f"http://127.0.0.1:{port}\n".encode("utf-8"), "text/plain")
            return False
        if method != "GET":
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in own}:
                self._respond(403, b"local mode refuses a write from another origin\n",
                              "text/plain")
                return False
            site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if site not in ("", "same-origin", "none"):
                self._respond(403, b"local mode refuses a write from another site\n",
                              "text/plain")
                return False
        return True

    def _read_body_bounded(self, length: int) -> bytes | None:
        """Read exactly `length` bytes, refusing before the read starts if `length`
        already exceeds the configured limit, and abandoning the read -- returning
        `None` -- if the whole read has not finished within the configured wall-clock
        deadline.

        `rfile.read1()`, not `rfile.read()`: `.read(n)` on a buffered stream loops
        internally, issuing as many underlying socket reads as it takes to fill `n`
        bytes; `.read1(n)` returns after at most ONE underlying read (whatever arrived,
        or nothing within the timeout), which is what lets a **slowly trickling** client
        keep the read alive across several calls -- each one re-armed with whatever of
        the overall deadline is left -- while a client that stops sending entirely still
        hits that shrinking budget and gives up.

        **Exactly one timeout is tolerated, not retried.** `socket.SocketIO` sticks a
        `_timeout_occurred` flag the first time a read times out, and every read after
        that raises `OSError("cannot read from timed out object")` **even against a
        connection that has since sent more data** -- found the hard way, writing the
        first version of this method, which called `settimeout()` with a short, fixed
        slice and looped expecting a fresh `TimeoutError` each pass; the second pass hit
        that OSError instead and it went unhandled, a 500 for what should have been a
        clean 408. The fix is not to catch that OSError and retry -- the socket cannot
        be un-poisoned -- it is to never attempt a second read after a timeout at all:
        one `settimeout()` per iteration, sized to whatever of the deadline remains, and
        the FIRST timeout ends the read outright. That is also the correct meaning of
        "stalled": a client still trickling bytes keeps re-arming a fresh, shrinking
        budget and never times out; only one that truly stops does.
        """
        if length > self.config.max_request_body:
            return None
        deadline = time.monotonic() + self.config.request_timeout_seconds
        chunks: list[bytes] = []
        remaining = length
        while remaining > 0:
            budget = deadline - time.monotonic()
            if budget <= 0:
                return None
            self.connection.settimeout(budget)
            try:
                chunk = self.rfile.read1(min(remaining, 65536))
            except OSError:                       # covers both TimeoutError and the
                return None                        # poisoned-socket OSError alike
            finally:
                self.connection.settimeout(None)
            if not chunk:
                return None        # the connection closed before the body arrived in full
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    # -------------------------------------------------------------- logging
    def log_message(self, fmt: str, *args) -> None:                 # noqa: A003
        if self.config.public:
            #: A public console's log is its access log alone: five fields, no client address.
            #: The standard server's own line (each request, and each error it answers itself)
            #: would carry the address, so it is not written; `send_error` records those answers
            #: in the access log instead.
            return
        sys.stderr.write(f"{self.address_string()} - {fmt % args}\n")

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        """The standard server's own error answers -- a method it does not serve, a request line it
        cannot read, a header too long -- recorded in a public console's access log like every
        other answer, since their standard log line is not written."""
        if self.config.public:
            path = urlsplit(getattr(self, "path", "") or "").path or "-"
            self.access_log.append(principal="anonymous", method=self.command or "-", path=path,
                                   status=code)
        super().send_error(code, message, explain)

    # -------------------------------------------------------------- sign-in helpers
    def _current_session(self):
        """The caller's session, or `None` -- absent, expired, or sign-in disabled
        entirely. Never raises; a malformed or missing cookie reads exactly like no
        session at all.
        """
        if self.session_store is None:
            return None
        from onetrace_console.signin import SESSION_COOKIE, parse_cookies

        cookies = parse_cookies(self.headers.get("Cookie"))
        session_id = cookies.get(SESSION_COOKIE)
        if not session_id:
            return None
        return self.session_store.get(session_id)

    def _bearer_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer "):].strip()
        return None

    def _granted(self) -> tuple[str | None, str]:
        """`(role, principal)` the CALLER actually presented, resolved once. A
        bearer token grants exactly `ingester`; a session grants exactly `viewer`
        -- never mixed (design note §1 item 11). A
        token takes precedence when both happen to be present, since only a
        machine credential would ever carry one at all. `role` is `None` for no
        valid credential; `principal` is always a string, `"anonymous"` when
        `role` is `None`.
        """
        token = self._bearer_token()
        if token is not None:
            principal = self.token_store.principal_for(token) if self.token_store else None
            if principal is not None:
                from onetrace_console import roles
                return roles.INGESTER, principal
            return None, "anonymous"
        session = self._current_session()
        if session is not None:
            from onetrace_console import roles
            return roles.VIEWER, session.username
        return None, "anonymous"

    def _resolve_request_identity(self) -> None:
        """Resolved ONCE, at the very top of every request, before any handler
        runs -- so an action that destroys its own credential
        (sign-out invalidating the session it was just called with) is still
        logged and role-checked under the principal that made the request, not
        whatever is left of it afterward.
        """
        self._request_role, self._request_principal = self._granted()

    def _principal(self) -> str:
        """The name the access log records for this request -- the identity
        `_resolve_request_identity` already captured at request start.
        """
        return getattr(self, "_request_principal", "anonymous")

    def _enforce_role(self, method: str, path: str, *, rel_for_get: str | None = None) -> bool:
        """`True` if the request may proceed. `False` means a refusal has ALREADY
        been sent and the caller must return immediately without running its own
        handler. A no-op (`True`) entirely when `sign_in.enabled` is false -- an
        unmodified, ungated console, exactly today's behaviour.
        """
        if not self.config.sign_in.get("enabled"):
            return True
        from onetrace_console import roles

        try:
            required = roles.required_role(method, path, rel_for_get=rel_for_get)
        except roles.NoRouteTableEntry:
            #: A route (or a page shape) this table has never heard of -- refused
            #: outright, never silently served open. Reads to the client exactly
            #: like an unknown route, which it is, from the role table's own
            #: point of view.
            self._respond(404, b"no such route\n", "text/plain")
            return False
        if required is None:
            return True
        granted_role = self._request_role
        if granted_role is not None and roles.role_includes(granted_role, required):
            return True
        if granted_role is None:
            #: No credential at all: redirect a browser, 401 a script (design
            #: note §1 item 3's own distinction between the two audiences).
            if method == "GET":
                self._respond(303, b"", "text/plain", [("Location", "/signin")])
            else:
                self._respond(401, b"sign-in or a bearer token is required\n", "text/plain")
            return False
        #: A real credential, just not one that grants this route's role (the
        #: three cases item 8's own tests name: a token on a viewer page, a
        #: session on an ingester route, and -- structurally impossible here
        #: since `required_role` would have raised above -- anything else).
        self._respond(403, b"this credential does not grant the required role\n",
                     "text/plain")
        return False

    def _submitted_csrf_token(self, *, body: bytes | None = None,
                              query: dict | None = None) -> str:
        """Where a CSRF value may travel for an already-authenticated action
        A custom header first (works for `POST /compare`, which
        has no body), then a query parameter (also fine for `/compare`), then a
        urlencoded body field (for `/signout`, which a form could submit either
        way). The FIRST one present wins; there is no "try all and OR them".
        """
        header = self.headers.get("X-CSRF-Token")
        if header:
            return header
        if query and query.get("csrf_token"):
            return query["csrf_token"][0]
        if body:
            from onetrace_console.signin import parse_signin_form
            form = parse_signin_form(body)
            if form.get("csrf_token"):
                return form["csrf_token"]
        return ""

    def _check_action_csrf(self, *, body: bytes | None = None, query: dict | None = None) -> bool:
        """CSRF for an already-authenticated, state-changing action (`POST
        /compare`, `POST /signout`) -- the double-submit pattern, but bound to
        the session's OWN token (`sessions.py` already mints one per session)
        rather than a separately re-issued cookie: the submitted value, the
        `onetrace_csrf` cookie, and the session's own `csrf_token` must all
        agree. `True` (nothing to check) when there is no live session at all --
        the sign-in-page CSRF check is the pre-auth case, this is the post-auth
        one, and a request with no session has already failed, or will fail, the
        role/no-op check on its own merits.
        """
        session = self._current_session()
        if session is None:
            return True
        from onetrace_console.signin import CSRF_COOKIE, parse_cookies

        submitted = self._submitted_csrf_token(body=body, query=query)
        cookie = parse_cookies(self.headers.get("Cookie")).get(CSRF_COOKIE, "")
        return bool(submitted) and submitted == cookie == session.csrf_token

    # -------------------------------------------------------------- GET
    def do_GET(self) -> None:                                       # noqa: N802
        self._resolve_request_identity()
        if not self._local_guard("GET"):
            return
        path = urlsplit(self.path).path
        if path == "/health":
            self._respond(200, b"ok\n", "text/plain")
            return
        if path == "/v1/folder" and self.watcher is not None:
            #: What the watcher knows: read by the Overview's and the runs list's notice.
            self._respond_json(200, self.watcher.state.as_json())
            return
        if path == "/signin" and self.config.sign_in.get("enabled"):
            self._handle_signin_get()
            return
        if path.startswith("/static/"):
            #: Exact paths only: anything else under /static/ -- another name, an encoded
            #: traversal -- is not found, and never reaches the pages lookup below.
            from onetrace_console.frame import STYLESHEET, stylesheet
            if path == STYLESHEET:
                self._respond(200, stylesheet(), "text/css; charset=utf-8")
                return
            target = STATIC_FILES.get(path)
            if target is None:
                self._respond(404, b"not found\n", "text/plain")
                return
            self._respond(200, target.read_bytes(), _STATIC_TYPES[target.suffix])
            return

        rel = "home.html" if path in ("/", "") else path.lstrip("/")
        #: A path that could step around the role table is refused
        #: before the role check and before any file is touched -- `..`, a backslash, an
        #: encoded dot or backslash, or an empty or `.` segment.
        segments = rel.split("/")
        if (".." in rel or "\\" in rel or _ENCODED_DOT_OR_BACKSLASH.search(rel)
                or any(s in ("", ".") for s in segments)):
            self._respond(400, b"bad path\n", "text/plain")
            return
        if not self._enforce_role("GET", path, rel_for_get=rel):
            return
        record = _RECORD_PATH.fullmatch(rel)
        if record:
            self._handle_record(record.group(1))
            return
        pages = (self.store_root / PAGES_DIRNAME).resolve()
        target = self.store_root / PAGES_DIRNAME / rel
        try:
            #: The page served is exactly the one the role row matched: under `pages/`, and
            #: resolving to the same relative path, spelled the same way.
            resolved = target.resolve().relative_to(pages).as_posix()
        except ValueError:
            resolved = None
        if resolved != rel:
            self._respond(400, b"bad path\n", "text/plain")
            return
        if not target.is_file():
            self._respond(404, f"not rendered: {rel}\n".encode(), "text/plain")
            return
        #: The frame is filled here, as the page is served, because only the
        #: server knows the session the footer states. A page with no empty frame -- a sealed
        #: page -- is served exactly as written.
        from onetrace_console import roles
        from onetrace_console.frame import fill
        user = self._principal() if getattr(self, "_request_role", None) == roles.VIEWER else None
        page = fill(target.read_bytes(), rel, onedoor=bool(self.config.extensions.get("onedoor")),
                    user=user, public=self.config.public)
        self._respond(200, page, "text/html; charset=utf-8")

    # -------------------------------------------------------------- POST
    def do_POST(self) -> None:                                      # noqa: N802
        if self.config.public:
            #: The public mode's one check, ahead of everything else -- the routing, the
            #: Content-Length, the body: every POST is refused, a route added later included, and
            #: not a byte of the body is read. The connection is closed rather than drained.
            from onetrace_console.public import REFUSAL
            self.close_connection = True
            self._respond(403, (REFUSAL + "\n").encode("utf-8"), "text/plain; charset=utf-8")
            return
        self._resolve_request_identity()
        if not self._local_guard("POST"):
            return
        split = urlsplit(self.path)

        raw_length = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            self._respond(400, f"Content-Length is not an integer: {raw_length!r}\n".encode(),
                         "text/plain")
            self.close_connection = True
            return
        if length < 0:
            self._respond(400, f"Content-Length is negative: {length}\n".encode(), "text/plain")
            self.close_connection = True
            return

        #: Refused BEFORE the read starts, and the connection is closed rather than
        #: drained: reading and discarding a body that was refused for being too large
        #: is the same cost the limit exists to avoid.
        if length > self.config.max_request_body:
            self._respond(413, f"body of {length} bytes exceeds the configured "
                              f"{self.config.max_request_body}-byte limit\n".encode(),
                         "text/plain")
            self.close_connection = True
            return

        body = self._read_body_bounded(length) if length else b""
        if body is None:
            #: Either the wall-clock deadline passed (a stalled or trickling client,
            #: item 4) or the connection closed before the declared length arrived (a
            #: truncated request, item 5) -- both are the client's fault and neither is
            #: a servable body, so neither reaches a route handler.
            self._respond(408, b"request body did not arrive in full within the "
                              b"configured timeout\n", "text/plain")
            self.close_connection = True
            return

        try:
            if split.path == "/v1/runs":
                if not self._enforce_role("POST", "/v1/runs"):
                    return
                self._handle_ingest(body)
            elif split.path == "/compare":
                if not self._enforce_role("POST", "/compare"):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_compare(query)
            elif split.path == "/text-diff/more":
                if not self._enforce_role("POST", "/text-diff/more"):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_text_diff_more(query)
            elif split.path == "/v1/decisions" and self.config.extensions.get("onedoor"):
                #: Imported only here, only once the config key is checked -- a disabled
                #: console never reaches this line, so it never imports the extension.
                #: See tests/test_onedoor_ext_isolation.py.
                if not self._enforce_role("POST", "/v1/decisions"):
                    return
                self._handle_decisions(body)
            elif split.path == "/signin" and self.config.sign_in.get("enabled"):
                self._handle_signin_post(body)
            elif split.path == "/signout" and self.config.sign_in.get("enabled"):
                if not self._check_action_csrf(body=body):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_signout()
            else:
                self._respond(404, b"no such route\n", "text/plain")
        except Exception as exc:                          # noqa: BLE001 - reported, not swallowed
            #: The traceback goes to stderr (the operator's own logs), never into the
            #: response. Only the exception's type and message reach the client.
            traceback.print_exc()
            self._respond(500, f"{type(exc).__name__}: {exc}\n".encode(), "text/plain")

    # ---------------------------------------------------------------- sign-in
    def _cookie_secure(self) -> bool:
        """`Secure` on every cookie whenever sign-in is on, not
        only when this process itself terminates TLS -- see `signin.cookies_secure`.
        """
        from onetrace_console.signin import cookies_secure
        return cookies_secure(self.config)

    def _handle_signin_get(self) -> None:
        from onetrace_console.signin import (CSRF_COOKIE, new_csrf_form_token,
                                             render_signin_page, set_cookie_header)

        token = new_csrf_form_token()
        body = render_signin_page(csrf_token=token).encode("utf-8")
        cookie = set_cookie_header(CSRF_COOKIE, token, http_only=False,
                                   secure=self._cookie_secure())
        self._respond(200, body, "text/html; charset=utf-8", [("Set-Cookie", cookie)])

    def _handle_signin_post(self, body: bytes) -> None:
        from onetrace_console.signin import (CSRF_COOKIE, CSRF_FIELD, SESSION_COOKIE,
                                             clear_cookie_header, new_csrf_form_token,
                                             parse_cookies, parse_signin_form,
                                             render_signin_page, set_cookie_header)

        form = parse_signin_form(body)
        cookies = parse_cookies(self.headers.get("Cookie"))

        #: CSRF: the cookie set when the form was rendered must equal
        #: the hidden field the form submitted. Neither present, or the two disagree,
        #: is refused the same way -- never distinguished for an attacker's benefit.
        submitted_csrf = form.get(CSRF_FIELD, "")
        cookie_csrf = cookies.get(CSRF_COOKIE, "")
        if not submitted_csrf or not cookie_csrf or submitted_csrf != cookie_csrf:
            self._respond(403, b"sign-in refused: missing or mismatched CSRF token\n",
                         "text/plain")
            return

        username = form.get("username", "")
        password = form.get("password", "").encode("utf-8")
        client_key = self.client_address[0] if self.client_address else "unknown"

        #: Rate limits, item 3: per account AND per client, checked before the
        #: password is ever touched -- a limited-out request never reaches scrypt.
        if not self.rate_limit_per_client.check_and_record(client_key):
            self._respond(429, b"too many sign-in attempts from this client\n", "text/plain")
            return
        if username and not self.rate_limit_per_account.check_and_record(username):
            self._respond(429, b"too many sign-in attempts for this account\n", "text/plain")
            return

        #: A global cap on concurrent scrypt computations, checked
        #: before `verify_password` -- which itself always hashes, real account or
        #: not (item 3) -- ever runs. Refused with 503, never silently queued: a
        #: caller that cannot get a slot right now gets an honest "too busy", not
        #: a wrong-password page that would misreport why it failed.
        if not self.rate_limit_concurrent_hashes.try_acquire():
            self._respond(503, b"too many concurrent sign-in attempts; try again shortly\n",
                         "text/plain")
            return
        try:
            #: No `username and` short-circuit -- an EMPTY username
            #: takes the same path as an unknown one, so "no username submitted"
            #: is not a distinguishable-by-timing third case. `AccountStore.get("")`
            #: simply finds no file and `verify_password` runs its dummy hash.
            authenticated = self.account_store.verify_password(username, password)
        finally:
            self.rate_limit_concurrent_hashes.release()

        if authenticated:
            self.rate_limit_per_account.reset(username)
            session = self.session_store.create(username)
            cookie = set_cookie_header(SESSION_COOKIE, session.session_id, http_only=True,
                                       secure=self._cookie_secure())
            #: The CSRF cookie is no longer just cleared on
            #: success -- it is set to the SESSION's own token (`sessions.py`
            #: already mints one per session), the value `POST /compare` and
            #: `POST /signout` must echo back. Not `HttpOnly`, the same reasoning
            #: as the pre-auth token: a form must be able to carry it.
            action_csrf = set_cookie_header(CSRF_COOKIE, session.csrf_token, http_only=False,
                                            secure=self._cookie_secure())
            self._respond(303, b"", "text/plain",
                         [("Set-Cookie", cookie), ("Set-Cookie", action_csrf),
                          ("Location", "/")])
            return

        #: A fresh CSRF token for the re-shown form -- the one just submitted is spent
        #: either way, matching the "one token per render" shape the GET side sets up.
        token = new_csrf_form_token()
        retry_cookie = set_cookie_header(CSRF_COOKIE, token, http_only=False,
                                         secure=self._cookie_secure())
        page = render_signin_page(csrf_token=token,
                                  error="wrong username or password").encode("utf-8")
        self._respond(401, page, "text/html; charset=utf-8", [("Set-Cookie", retry_cookie)])

    def _handle_record(self, key: str) -> None:
        """The run's own record for download: the delivery as it arrived, byte for byte
        (`ingest.bundle`). A page that shortens a run's words offers it."""
        from onetrace_console.ingest import bundle
        from onetrace_console.store import MISSING_OBJECT, StoreError
        try:
            run = self.store.get_run(key)
            gone = self.store.missing(run) if run is not None else ()
            if gone:
                #: Said in the fixed words, not as an object's hash.
                self._respond(409, (MISSING_OBJECT.format(objects=", ".join(gone)) + "\n")
                              .encode("utf-8"), "text/plain; charset=utf-8")
                return
            body = bundle(run, self.store, public=self.config.public) if run is not None else None
        except StoreError as e:
            self._respond(409, f"{e}\n".encode("utf-8"), "text/plain; charset=utf-8")
            return
        if body is None:
            self._respond(404, b"no such run\n", "text/plain")
            return
        self._respond(200, body, "application/x-tar",
                      [("Content-Disposition", f'attachment; filename="{key}.tar"')])

    def _handle_signout(self) -> None:
        from onetrace_console.signin import (CSRF_COOKIE, SESSION_COOKIE,
                                             clear_cookie_header, parse_cookies)

        cookies = parse_cookies(self.headers.get("Cookie"))
        session_id = cookies.get(SESSION_COOKIE)
        if session_id:
            self.session_store.invalidate(session_id)
        cookie = clear_cookie_header(SESSION_COOKIE, secure=self._cookie_secure())
        csrf_cookie = clear_cookie_header(CSRF_COOKIE, secure=self._cookie_secure())
        self._respond(303, b"", "text/plain",
                     [("Set-Cookie", cookie), ("Set-Cookie", csrf_cookie),
                      ("Location", "/signin")])

    def _handle_ingest(self, body: bytes) -> None:
        from onetrace_console.checks import run_and_record
        from onetrace_console.ingest import Rejection, accept

        with INTAKE_LOCK:
            self._ingest_locked(body, accept, Rejection)

    def _ingest_locked(self, body: bytes, accept, Rejection) -> None:
        from onetrace_console.checks import run_and_record
        accepted = accept(body, self.store, limits=self.config)
        if isinstance(accepted, Rejection):
            self._respond_json(accepted.status, {
                "accepted": False,
                "rows": list(accepted.rows),
                "body": accepted.body,
                "from_verifier": accepted.from_verifier,
            })
            return
        from onetrace_console.checks import check_options
        run = run_and_record(accepted.run, self.store, **check_options(self.config))
        _render_run_pages(run, self.store, self.store_root, self.config)
        _render_all_pages(self.store, self.store_root, self.config)
        self._respond_json(200, {
            "accepted": True,
            "run_key": run.key,
            "run_id": run.run_id,
            "check_verdict": run.check_verdict,
            "pages": {
                "executions": "/home.html",
                "answer": f"/runs/{run.key}/answer.html",
                "case": f"/runs/{run.key}/case.html",
                "authorization": f"/runs/{run.key}/authorization.html",
            },
        })

    def _handle_decisions(self, body: bytes) -> None:
        from onetrace_console.onedoor_ext.decisions import (DecisionsRejection,
                                                             accept_export)

        try:
            accepted = accept_export(body, self.store, limits=self.config)
        except DecisionsRejection as e:
            self._respond(422, e.body.encode("utf-8"), "text/plain")
            return
        _render_all_pages(self.store, self.store_root, self.config)
        self._respond_json(accepted.status, {
            "accepted": True,
            "export_key": accepted.export.key,
            "row_count": len(accepted.export.rows),
            "pages": {"policy": "/policy.html"},
        })

    def _handle_compare(self, query: dict[str, list[str]]) -> None:
        from onetrace_console.compare import ComparisonError, compare
        from onetrace_console.store import StoreError

        unreadable: list[str] = []

        def lookup(key: str):
            if not key:
                return None
            try:
                return self.store.get_run(key)
            except StoreError as e:
                if "cannot be read" in str(e):
                    #: A record the store holds and cannot read is said as that, not as an
                    #: unknown key.
                    unreadable.append(str(e))
                return None                                   # malformed key: same as "unknown"

        a_key = (query.get("a") or [""])[0]
        b_key = (query.get("b") or [""])[0]
        a_run = lookup(a_key)
        b_run = lookup(b_key)
        if a_run is None or b_run is None:
            missing = [k for k, r in (("a", a_run), ("b", b_run)) if r is None]
            self._respond_json(400, {"error": "; ".join(unreadable) if unreadable else
                                     f"unknown or malformed run key(s): {missing}"})
            return
        if a_run.key == b_run.key:
            #: Said plainly, never 500. Nothing is compared and nothing
            #: is stored: a run compared with itself is the same run.
            self._respond_json(200, {"same_run": True, "run_key": a_run.key,
                                     "answer": SAME_RUN})
            return
        from onetrace_console.store import MISSING_OBJECT, SameFileError
        gone = [(r, self.store.missing(r)) for r in (a_run, b_run)]
        if any(objects for _, objects in gone):
            #: The pair is refused in the fixed words, never a 500; nothing
            #: is compared and nothing stored.
            self._respond_json(409, {"error": "; ".join(
                f"run {r.key[:12]}: " + MISSING_OBJECT.format(objects=", ".join(objects))
                for r, objects in gone if objects)})
            return
        try:
            comparison = compare(a_run, b_run, self.store)
        except ComparisonError as e:
            #: Said, never 500: nothing compared and nothing stored.
            self._respond_json(400, {"error": str(e)})
            return
        except SameFileError as e:
            #: A run the store holds that cannot be laid out here as stored: said, nothing
            #: compared and nothing stored.
            self._respond_json(400, {"error": f"this console cannot lay out a run of this pair "
                                              f"on this host: {e}"})
            return
        rel = _render_diff_page(comparison, self.store, self.store_root)
        #: Storing a comparison re-renders its candidate's pages, whose
        #: graph is marked from it; nothing else re-renders them but start-up.
        _render_run_pages(b_run, self.store, self.store_root, self.config)
        _render_all_pages(self.store, self.store_root, self.config)
        self._respond_json(200, {"comparison_key": comparison.key, "pages": {"diff": f"/{rel}"}})

    def _handle_text_diff_more(self, query: dict[str, list[str]]) -> None:
        """The comparison's text diff again at the console's one larger
        limit, stored as a run of its own; the original runs and every verdict unchanged. The
        limit is never taken from the request: a `max_lines` other than it is refused."""
        from onetrace_console.compare import TEXT_DIFF_MORE_LINES, ComparisonError, show_more
        asked = (query.get("max_lines") or [""])[0]
        if asked and asked != str(TEXT_DIFF_MORE_LINES):
            self._respond_json(400, {"error": f"the larger limit is fixed at "
                                              f"{TEXT_DIFF_MORE_LINES} lines per output"})
            return
        key = (query.get("c") or [""])[0]
        from onetrace_console.store import StoreError
        try:
            comparison = self.store.get_comparison(key) if key else None
        except (StoreError, OSError, ValueError):
            comparison = None
        if comparison is None:
            self._respond_json(400, {"error": "unknown or malformed comparison key"})
            return
        try:
            comparison = show_more(comparison, self.store)
        except ComparisonError as e:
            self._respond_json(400, {"error": str(e)})
            return
        rel = _render_diff_page(comparison, self.store, self.store_root)
        self._respond_json(200, {"comparison_key": comparison.key, "max_lines": TEXT_DIFF_MORE_LINES,
                                 "pages": {"diff": f"/{rel}"}})

    # -------------------------------------------------------------- helpers
    def _respond(self, status: int, body: bytes, content_type: str,
                extra_headers: list[tuple[str, str]] | None = None) -> None:
        """The one place every response leaves through -- so it is also the one place
        the access log is written from. The
        append is attempted BEFORE anything is sent to the client: a failure there
        (`AccessLogExhausted`) replaces the response with a 500 instead of serving the
        original one silently unrecorded. See `access_log.py`'s own docstring for why
        that failure itself goes unlogged -- the one honest gap.

        The principal recorded is `self._principal()`: the real,
        signed-in username when a valid session says so, `"anonymous"` otherwise --
        never a password, a session id, or a CSRF token, none of which ever reach
        this method as anything but part of an opaque request the log does not
        inspect further than `method`/`path`/`status`.
        """
        from onetrace_console.access_log import AccessLogExhausted

        try:
            self.access_log.append(principal=self._principal(), method=self.command,
                                   path=urlsplit(self.path).path, status=status)
        except AccessLogExhausted as e:
            status = 500
            from onetrace_console.oserror import shown
            body = (shown(f"the access log could not be written: {e}") + "\n").encode("utf-8")
            content_type = "text/plain"
            extra_headers = None
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (extra_headers or ()):
            self.send_header(name, value)
        if self.local_port is not None and not self.config.public:
            #: Local mode has no sign-in, so a page from another site must not be able to
            #: frame a local page or have one sniffed into another type. (A public console sends
            #: these and more on every response, from `end_headers`.)
            for name, value in (("X-Frame-Options", "DENY"),
                                ("Cross-Origin-Resource-Policy", "same-origin"),
                                ("X-Content-Type-Options", "nosniff")):
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        """A public console's security headers, on every response it sends -- `_respond`'s and
        the standard server's own error answers alike, since both end here."""
        config = getattr(type(self), "config", None)
        if config is not None and config.public:
            from onetrace_console.public import security_headers
            for name, value in security_headers():
                self.send_header(name, value)
        else:
            #: A console on this machine sends the same content policy, its fonts and scripts
            #: its own, plus the watched folder's notice reading the console itself.
            from onetrace_console.public import content_security_policy
            self.send_header("Content-Security-Policy", content_security_policy(local=True))
        super().end_headers()

    def _respond_json(self, status: int, obj: dict,
                      extra_headers: list[tuple[str, str]] | None = None) -> None:
        self._respond(status, json.dumps(obj, indent=1).encode("utf-8"), "application/json",
                     extra_headers)


#: `%2e` (a dot) or `%5c` (a backslash), in either case: the encoded forms of what a path
#: may not contain.
_ENCODED_DOT_OR_BACKSLASH = re.compile(r"%(2e|5c)", re.IGNORECASE)

#: The run's own record: `runs/<key>/record.tar`, the key a sha256 run key.
_RECORD_PATH = re.compile(r"runs/([0-9a-f]{64})/record\.tar")

#: Local mode's one address.
LOCAL_HOST = "127.0.0.1"


def _local_config(base: Config) -> Config:
    """Local mode's configuration: `base` with the host FORCED to loopback and sign-in forced
    off, whatever `base` says."""
    from dataclasses import replace
    return replace(base, host=LOCAL_HOST, sign_in={**base.sign_in, "enabled": False})


def _writable_store(store_root: Path, config: Config):
    """The store and the access log of a console that writes: the root made and write-tested."""
    from onetrace_console.access_log import AccessLog
    store_root.mkdir(parents=True, exist_ok=True)
    #: The write test first: an unwritable store root whose access_log/ already existed
    #: spun inside the access log's own temp-file loop (the third review, NEW-10).
    written = store_root / f".write-test-{os.getpid()}"
    written.write_bytes(b"")
    written.unlink()
    #: `Store(root)` makes `root/objects` and `root/runs` itself, so this names the STORE's
    #: own root as a sibling of `pages/` under the one mounted volume -- not nested in it.
    store = Store(store_root / "store")
    (store_root / PAGES_DIRNAME).mkdir(exist_ok=True)
    return store, AccessLog(store_root / "access_log",
                            max_segment_bytes=config.access_log_max_segment_bytes)


def _public_store(store_root: Path):
    """A public console's store, read as it was built -- it may be read-only on disk -- and its
    access log, on standard output. Nothing is made or written."""
    from onetrace_console.public import StdoutAccessLog
    return Store(store_root / "store"), StdoutAccessLog()


def main(argv: list[str] | None = None, *, overrides: dict | None = None, prepare=None,
         open_browser: bool = False, announce=None, watch=None) -> int:
    """`ONETRACE_CONSOLE_CONFIG` is the only environment variable this console reads
    Host, port, the store's root, and every upload-hardening
    limit all come from the one file it names -- `onetrace_console.config.load_from_env()`.

    With the variable **absent**, this starts in local mode: 127.0.0.1
    only and no sign-in, whatever the defaults say, with a browser guard in place of
    sign-in (`Handler._local_guard`), and it says so once it is listening. It replaced
    an earlier refusal to start with the variable absent, and keeps that refusal's purpose --
    never open to the network by accident.
    With the variable **set but blank** it refuses: that is someone who meant to name a
    file. With it naming a file, the file decides, exactly as before. The shipped
    container always names one (`/etc/onetrace-console/config.json`).

    The folder load and the demo (`onetrace_console.folder_load`) start through here too:
    `overrides` replaces configuration values before local mode forces its host and sign-in;
    `prepare(store, config)` loads runs once the port is bound and before pages are drawn, and
    returns the lines to print once listening and the page `open_browser` opens.

    A public console (`"public": true`, `public.py`) draws nothing at start and writes nothing:
    it serves the store it was built with, read-only. It takes no `prepare`; `announce` is the
    lines and page, worked out when the store was built.
    """
    import os
    from dataclasses import replace

    from onetrace_console.config import ENV_VAR, load_from_env

    from onetrace_console.signin import refuse_if_insecure

    argv = list(sys.argv[1:] if argv is None else argv)
    if argv:
        print(f"onetrace-console serve takes no arguments (given: {' '.join(argv)}). Host, "
              f"port and everything else come from the configuration file named in "
              f"{ENV_VAR}; with none named, it runs in local mode.", file=sys.stderr)
        return 2
    #: Anything this console prints may carry a path or a name the console's own stream cannot
    #: encode -- Windows' piped stdout is cp1252 (the third confirmation review, NEW-8).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    named = os.environ.get(ENV_VAR)
    if named is not None and not named.strip():
        print(f"refusing to start: {ENV_VAR} is set but blank. Name a configuration file, "
              f"or leave the variable out entirely for local mode.", file=sys.stderr)
        return 1
    local = named is None
    if local:
        #: Local mode: "The console is open source and runs locally ...
        #: binds to 127.0.0.1 only, unless an explicit flag says otherwise ... There's no
        #: sign-in in local mode." The explicit flag is a named configuration file, the one
        #: source of host and port.
        import onetrace_console.config as config_module
        config = _local_config(replace(config_module.Config(), **(overrides or {})))
    else:
        from onetrace_console.config import ConfigError
        try:
            config = load_from_env()
        except ConfigError as e:
            #: The message and its fix, never a traceback.
            print(f"refusing to start: {e}\nfix: {e.fix}", file=sys.stderr)
            return 1
        config = replace(config, **(overrides or {}))

    #: In release 1 the authorization extension cannot be switched
    #: on. Its code stays for release 2, which wires its join to the run pages; until then a
    #: console showing decisions while every run page says "no authorization records" would
    #: contradict itself, so the setting is refused at start.
    if config.extensions.get("onedoor"):
        print("refusing to start: extensions.onedoor is true, and the authorization extension "
              "is not part of this release. Remove it, or set it to false.\nfix: remove "
              "extensions.onedoor from the configuration file, or set it to false.",
              file=sys.stderr)
        return 1

    store_root = Path(config.store_root).resolve()
    if config.public:
        from onetrace_console.public import start_refusal
        refused = start_refusal(config, store_root)
        if refused is None and prepare is not None:
            from onetrace_console.public import Refusal
            refused = Refusal("public is true, and a public console loads nothing at start.",
                              "build the store first with onetrace-console demo --public --build "
                              "<folder>.")
        if refused is not None:
            print(f"refusing to start: {refused.message}\nfix: {refused.fix}", file=sys.stderr)
            return 1
        #: The demo's own example inputs, which its build record (checked above) vouches for, are
        #: the one kind of input from outside a pipeline this console may hand out.
        from onetrace_console.demo_store import serve_examples
        serve_examples(Path(config.trust_file).parent)

    #: Checked before anything else touches the network: a plain-HTTP, non-loopback
    #: listener with sign-in enabled refuses to start outright -- in words, with its fix,
    #: never a traceback (it was found raising one in the container).
    from onetrace_console.signin import InsecureListenerError
    try:
        refuse_if_insecure(config)
    except InsecureListenerError as e:
        fix = ("set sign_in.insecure_cookie_for_local_dev to false, or bind host to loopback."
               if config.sign_in.get("insecure_cookie_for_local_dev") else
               "configure both sign_in.tls_cert_path and sign_in.tls_key_path, or bind host to "
               "loopback behind your own TLS-terminating proxy.")
        print(f"{e}\nfix: {fix}", file=sys.stderr)
        return 1

    if local and any((store_root / ACCOUNTS_DIRNAME).glob("*.json")):
        #: A store with accounts was set up with sign-in; local mode would serve it open.
        #: Accounts are `*.json`, as `AccountStore` writes them -- a `.gitkeep` is not one.
        print(f"refusing to start in local mode: the store at {store_root} was set up with "
              f"sign-in (it holds accounts). Name its configuration file in {ENV_VAR}.",
              file=sys.stderr)
        return 1
    try:
        store, access_log = (_public_store(store_root) if config.public
                             else _writable_store(store_root, config))
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as e:
        #: ValueError, KeyError, TypeError: an access_log/HEAD.json that is not the access
        #: log's own ended in a traceback (the third review, NEW-6); RecursionError, one nested
        #: past what JSON reads -- `AccessLog` now says so as a ValueError itself.
        #: Found by the two confirmation reviews: a store_root that is
        #: a file, under one, on no such drive or not writable, or whose store, pages or
        #: access_log is a file, ended in a traceback.
        from onetrace_console.oserror import shown
        print(shown(f"refusing to start: cannot use store_root {store_root}: "
                    f"{getattr(e, 'strerror', None) or f'{type(e).__name__}: {e}'}"
                    f"{f' ({e.filename})' if getattr(e, 'filename', None) else ''}")
              + "\nfix: point store_root at a folder this console can create and write, "
                "holding nothing but what this console put there.", file=sys.stderr)
        return 1

    Handler.store_root = store_root
    Handler.store = store
    Handler.config = config
    Handler.access_log = access_log

    #: A warning at every start-up when a configuration file leaves sign-in off: the
    #: console is unauthenticated and every page is open, and an operator who did not mean
    #: that should see it the moment the process starts. Local mode says the same, and more,
    #: in its own message once it is listening.
    Handler.local_port = config.port if local else None
    #: A public console gives each connection the request timeout, so a client that trickles its
    #: request line or headers cannot hold a thread; other consoles bound the body's read alone.
    Handler.timeout = config.request_timeout_seconds if config.public else None
    if local or config.public:
        for name in ("account_store", "session_store", "token_store", "rate_limit_per_account",
                     "rate_limit_per_client", "rate_limit_concurrent_hashes"):
            setattr(Handler, name, None)
    if not config.sign_in.get("enabled") and not local and not config.public:
        print("WARNING: sign_in.enabled is false -- every page and route is "
             "unauthenticated. Set it to true (the shipped default) once an "
             "admin account exists (`onetrace-console admin create`).", file=sys.stderr)

    if config.sign_in.get("enabled"):
        from onetrace_console.accounts import AccountStore
        from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter
        from onetrace_console.sessions import SessionStore
        from onetrace_console.ingester_tokens import TokenStore

        #: Logged at start-up -- the one way to get a non-`Secure`
        #: cookie is loud, never a silent config value nobody notices.
        if config.sign_in.get("insecure_cookie_for_local_dev"):
            print("WARNING: sign_in.insecure_cookie_for_local_dev is true -- session "
                 "and CSRF cookies will NOT carry Secure. Refused outright unless "
                 "this listener is loopback (see refuse_if_insecure).", file=sys.stderr)

        Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
        Handler.token_store = TokenStore(store_root / TOKENS_DIRNAME)
        Handler.session_store = SessionStore(
            idle_timeout_seconds=config.sign_in["session_idle_timeout_seconds"],
            absolute_timeout_seconds=config.sign_in["session_absolute_timeout_seconds"])
        Handler.rate_limit_per_account = RateLimiter(
            max_attempts=config.sign_in["rate_limit_max_attempts_per_account"],
            window_seconds=config.sign_in["rate_limit_window_seconds"])
        Handler.rate_limit_per_client = RateLimiter(
            max_attempts=config.sign_in["rate_limit_max_attempts_per_client"],
            window_seconds=config.sign_in["rate_limit_window_seconds"])
        Handler.rate_limit_concurrent_hashes = ConcurrencyLimiter(
            max_concurrent=config.sign_in["rate_limit_max_concurrent_hashes"])

    #: The order is the confirmation review's (notes 8 and 9, should-fix 4): everything that
    #: can refuse -- the TLS files, the host, the port -- refuses BEFORE any page is drawn, so
    #: a console that cannot start never rewrites a running console's pages on the way out.
    import ssl

    from onetrace_console.signin import build_ssl_context
    #: The container names a certificate it does not ship. Until one is
    #: mounted, it refuses -- saying which file is missing and where to mount it.
    if config.sign_in.get("tls_cert_path") and config.sign_in.get("tls_key_path"):
        for what, key in (("certificate", "tls_cert_path"), ("key", "tls_key_path")):
            named = config.sign_in[key]
            if not Path(named).is_file():
                print(f"refusing to start: no TLS {what} at {named} (sign_in.{key})\nfix: "
                      f"mount a PEM certificate and its private key at sign_in.tls_cert_path "
                      f"and sign_in.tls_key_path -- in the container, with docker run "
                      f"-v <a folder holding cert.pem and key.pem>:/etc/onetrace-console/tls:ro"
                      f" -- or run the console behind your own TLS-terminating proxy "
                      f"(OPERATOR_README.md).", file=sys.stderr)
                return 1
    try:
        ssl_context = build_ssl_context(config)
    except (OSError, ssl.SSLError) as e:
        from onetrace_console.oserror import shown
        print(shown(f"refusing to start: cannot load the TLS certificate and key named in "
                    f"sign_in.tls_cert_path and sign_in.tls_key_path: {e}")
              + "\nfix: point both at a PEM certificate and its PEM private key this console "
                "can read.", file=sys.stderr)
        return 1
    try:
        server_class = ConsoleServer6 if ":" in config.host else ConsoleServer
        server = server_class((config.host, config.port), Handler)
    except socket.gaierror as e:
        print(f"refusing to start: cannot resolve host {config.host!r}: {e.strerror or e}"
              f"\nfix: give host a name or address this machine can resolve, such as "
              f"127.0.0.1.", file=sys.stderr)
        return 1
    except OSError as e:
        if e.errno == errno.EADDRNOTAVAIL or getattr(e, "winerror", None) == 10049:
            #: A host that resolves and is not an address of this machine is not a busy port
            #: (the second confirmation review, N1).
            print(f"refusing to start: cannot listen on {config.host}:{config.port}: "
                  f"{config.host} is not an address of this machine.\nfix: give host an "
                  f"address of this machine, such as 127.0.0.1.", file=sys.stderr)
            return 1
        #: A port another process holds is refused in words, not
        #: with a traceback -- including a second console, which Windows would otherwise let
        #: share the port.
        print(f"refusing to start: cannot listen on {config.host}:{config.port}: "
              f"{e.strerror or e}. Is another process (perhaps another console) already "
              f"listening there?\nfix: stop that process, or give this console another "
              f"port: --port N on the command line, or port in its configuration file.",
              file=sys.stderr)
        return 1
    scheme = "http"
    if ssl_context is not None:
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    ready: tuple[list, str] = ([], "")
    try:
        if prepare is not None:
            from onetrace_console.folder_load import LoadRefused
            try:
                ready = prepare(store, config)
            except LoadRefused as e:
                print(f"refusing to start: {e}", file=sys.stderr)
                server.server_close()
                return 1
        if not config.public:
            _render_startup_pages(store, store_root, config)
        elif announce is not None:
            ready = announce
    except BaseException:
        server.server_close()
        raise
    if config.public:
        print(f"onetrace-console public mode: read-only. Every write is refused before its body "
              f"is read, and the pages are served as they were built under {store_root}; nothing "
              f"is checked, compared or drawn while serving. The access log is this output.",
              file=sys.stderr, flush=True)
    elif local:
        print(f"onetrace-console local mode: no configuration file named ({ENV_VAR} is not "
              f"set), so this console listens on {config.host}:{config.port} only, with no "
              f"sign-in, and keeps its store under {store_root}. Anyone who can use this "
              f"machine's loopback can read and write every page and route; requests naming "
              f"another host, and writes from another web origin, are refused. To serve beyond "
              f"this machine, name a configuration file in {ENV_VAR}.", file=sys.stderr,
              flush=True)
    #: An IPv6 address is bracketed, or the line is not a URL (the third review, NEW-15).
    shown_host = f"[{config.host}]" if ":" in config.host else config.host
    base = f"{scheme}://{shown_host}:{config.port}"
    print(f"onetrace-console serving on {base} (store root: {store_root})", flush=True)
    lines, opened = ready
    for text, path in lines[:-1]:
        print(text if path is None else f"{text} {base}/{path}", flush=True)
    if open_browser:
        #: Before the last line, so a reader of this output knows, once it has that line,
        #: whether a browser was asked to open.
        import webbrowser
        print(f"opening {base}/{opened} in your browser", flush=True)
        webbrowser.open(f"{base}/{opened}")
    for text, path in lines[-1:]:
        print(text if path is None else f"{text} {base}/{path}", flush=True)
    #: `watch(store, store_root, config)`: the folder watcher, started once the first pages are
    #: drawn, stopped before the server closes.
    watcher = watch(store, store_root, config) if watch is not None else None
    if watcher is not None:
        Handler.watcher = watcher
        watcher.start()
    try:
        with _sigterm_as_interrupt():
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if watcher is not None:
            watcher.stop()
            Handler.watcher = None
        server.server_close()
    return 0


class _sigterm_as_interrupt:
    """While serving, SIGTERM (a container stopping, a test's terminate) ends the console as
    Ctrl+C does: serving stops and every `with` around it unwinds -- `demo --public`'s temporary
    folder is removed. Only from the main thread, where Python delivers signals; elsewhere, and
    where the platform has no catchable SIGTERM (Windows' TerminateProcess), nothing changes."""

    def __enter__(self):
        import signal
        import threading
        self._old = None
        if threading.current_thread() is threading.main_thread() and hasattr(signal, "SIGTERM"):
            def interrupt(signum, frame):
                raise KeyboardInterrupt
            self._old = signal.signal(signal.SIGTERM, interrupt)
        return self

    def __exit__(self, *exc):
        if self._old is not None:
            import signal
            signal.signal(signal.SIGTERM, self._old)
        return False


if __name__ == "__main__":
    raise SystemExit(main())
