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

import contextlib
import errno
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from onetrace_console.audit import Audit
from onetrace_console.config import Config
from onetrace_console.store import Store

if TYPE_CHECKING:
    from onetrace_console.access_log import AccessLog
    from onetrace_console.accounts import AccountStore
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.oidc_flow import FlowStore
    from onetrace_console.oidc_issuer import Issuer
    from onetrace_console.oidc_settings import OidcSettings
    from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter
    from onetrace_console.sessions import SessionStore
    from onetrace_console.visitor_compare import Limiter
    from onetrace_console.watch import Watcher

#: Where rendered pages are written, relative to the store's own root -- inside the one
#: data volume, not a second one.
#: The console's own static files: the bundled IBM Plex fonts and their OFL
#: text, served to anyone -- the signed-out sign-in page uses them -- at exactly these paths and no
#: others. Built from the shipped folder, so a file added there is served only by being shipped.
_STATIC_TYPES = {".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8", ".svg": "image/svg+xml"}
STATIC_FILES = {
    f"/static/fonts/{p.name}": p
    for p in sorted((Path(__file__).parent / "static" / "fonts").glob("*"))
    if p.suffix in _STATIC_TYPES
}
#: The console's icon, in the skin's navigation colours; console pages link it (viewer/page.py).
STATIC_FILES["/static/favicon.svg"] = Path(__file__).parent / "static" / "favicon.svg"

PAGES_DIRNAME = "pages"
#: What a client is told when the console fails to answer it: never the cause, which the log has under `ref`.
SERVER_ERROR = "the console could not answer this request; its log names the cause under reference {ref}\n"


def _error_pages():
    from onetrace_console import error_pages

    return error_pages


#: Where local accounts live, relative to the store's own root. A sibling of
#: `pages/` and `store/store`, inside the one mounted volume, the same reasoning as both.
ACCOUNTS_DIRNAME = "accounts"
#: Where ingester bearer tokens live. A sibling of `accounts/`,
#: same reasoning: mutable records (a token is revoked in place), inside the one
#: mounted volume.
TOKENS_DIRNAME = "tokens"


#: The teams' page sets: `pages/t/<team>/`, one per team, beside the all-teams set, `pages/`.
TEAMS_DIRNAME = "t"


@dataclass(frozen=True)
class TeamSet:
    """Where a team's page set is drawn: its pages at `pages`, its run index inside it. Passed where the
    console's root is, so each drawing writes the team's set as it writes the all-teams set; `os.fspath` of it is its
    own folder, which the run index is written beside."""

    pages: Path
    team: str

    def __fspath__(self) -> str:
        return str(self.pages)


def team_set(root: Path, team: str) -> TeamSet:
    return TeamSet(Path(root) / PAGES_DIRNAME / TEAMS_DIRNAME / team, team)


def _pages(root) -> Path:
    """The folder a page set is written to: the console's `pages/`, or a team's set."""
    return root.pages if isinstance(root, TeamSet) else Path(root) / PAGES_DIRNAME


def _team_sets(store, root, config: Config | None, only=None) -> list:
    """(the team's view, its set) for each configured team, or for those of `only`; none for a team's view itself, or
    without teams."""
    if not isinstance(store, Store) or isinstance(root, TeamSet) or config is None or not config.teams:
        return []
    from onetrace_console.team_view import view_of

    return [(view_of(store, t), team_set(root, t)) for t in config.teams if only is None or t in only]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _write(root: Path, rel: str, html: str) -> None:
    target = _pages(root) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        html.encode("utf-8")
    except UnicodeEncodeError as e:
        #: The last guard: a page that cannot be written
        #: as UTF-8 is written as the page saying so, and the traceback goes to the log.
        from onetrace_console.pages import refusal
        from onetrace_console.unreadable import render_failed_page

        html = render_failed_page(refusal(e)[0], generated_at=_now())
    #: The page's own bytes, not text mode: on Windows text mode wrote CRLF after the page was
    #: sealed, and no run page's fingerprint checked.
    target.write_bytes(html.encode("utf-8"))


def _remove_policy_pages_not_in(root: Path, keep: set[str]) -> None:
    """Remove the Policy pages (policy.html, policy-*.html, policy/*.html) that are not in
    `keep`. Only these generated pages, never anything else under the pages folder."""
    pages = _pages(root)
    candidates = (
        list(pages.glob("policy.html")) + list(pages.glob("policy-*.html")) + list((pages / "policy").glob("*.html"))
    )
    for path in candidates:
        if path.relative_to(pages).as_posix() not in keep:
            path.unlink()


def _rendering(config: Config | None, root=None):
    """The configuration a sealed page's frame states, for a render now, and the team whose set `root` is. With
    no configuration -- a caller outside a running console -- sealed pages are drawn unframed."""
    import contextlib

    from onetrace_console.frame import rendering

    if config is None:
        return contextlib.nullcontext()
    return rendering(
        onedoor=bool(config.extensions.get("onedoor")),
        sign_in=bool(config.sign_in.get("enabled")),
        public=config.public,
        tracing_link=(config.tracing or {}).get("link", ""),
        tokenizers=tuple((t["folder"], tuple(t["files"])) for t in config.tokenizers or ()) + _kept_tokenizers(config),
        close_call_margin=config.close_call_margin,
        team=root.team if isinstance(root, TeamSet) else "",
    )


def _kept_tokenizers(config: Config) -> tuple:
    """The tokenizers this console keeps (`token_upload`), named as configured ones are: a local console's."""
    if config.public or not config.store_root:
        return ()
    from onetrace_console import token_upload

    return token_upload.named(Path(config.store_root) / "store")


def _render_run_pages(run, store: Store, root: Path, config: Config | None = None) -> None:
    with store.reading():
        _render_run_pages_read(run, store, root, config)


def _render_run_pages_read(run, store: Store, root: Path, config: Config | None = None) -> None:
    """The run's pages in the all-teams set, then in its team's set, drawn from the team's view."""
    _render_run_pages_one(run, store, root, config)
    for view, where in _team_sets(store, root, config, only=(run.team,)):
        _render_run_pages_one(run, view, where, config)


def _render_run_pages_one(run, store: Store, root: Path, config: Config | None = None) -> None:
    from contextlib import nullcontext

    from onetrace_console import run_index
    from onetrace_console.pages import ANSWER, AUTHORIZATION, CASE, RUN_PROOF, PageError, render_execution

    #: A run's pages drawn alone read the index the console last wrote: lineage from an index written before it held
    #: store writes, or from none, reads as not indexed (`store_state`).
    drawn = run_index.drawn_with()
    index = drawn or run_index.read(root)
    written = "" if drawn is not None else run_index.written_at(root)
    try:
        with (
            _rendering(config, root),
            run_index.drawing(index, written) if index is not None and drawn is None else nullcontext(),
        ):
            pages = render_execution(run, store, generated_at=_now()).pages
    except Exception as e:  # noqa: BLE001 - PageError and anything else: said, and logged
        if not isinstance(e, PageError):
            #: Whatever else escapes one run's pages never stops the rest, or the start.
            from onetrace_console.authorization import render_authorization
            from onetrace_console.pages import refusal
            from onetrace_console.unreadable import render_unreadable_run

            reason, from_viewer = refusal(e)
            page = render_unreadable_run(run, reason, generated_at=_now(), from_viewer=from_viewer)
            pages = {
                ANSWER: page,
                CASE: page,
                RUN_PROOF: page,
                AUTHORIZATION: render_authorization(run, generated_at=_now(), case=CASE),
            }
            for name, html in pages.items():
                _write(root, f"runs/{run.key}/{name}", html)
            return
        #: A stored run with no check report -- its check did not complete when it was
        #: received. The run page is refused, as always; here the console says so, and one
        #: such run never keeps the console from starting.
        from onetrace_console.authorization import render_authorization
        from onetrace_console.unreadable import render_unchecked_run

        page = render_unchecked_run(run, generated_at=_now())
        pages = {
            ANSWER: page,
            CASE: page,
            RUN_PROOF: page,
            AUTHORIZATION: render_authorization(run, generated_at=_now(), case=CASE),
        }
    for name, html in pages.items():
        _write(root, f"runs/{run.key}/{name}", html)


def _render_all_pages(store: Store, root: Path, config: Config | None = None, only=None) -> None:
    """`only`: the teams whose sets a change touched (a delivery's, a mark's); without it, every team's."""
    with store.reading():
        _render_all_pages_read(store, root, config, only)


def _render_all_pages_read(store: Store, root: Path, config: Config | None = None, only=None) -> None:
    """The pages over all runs, in the all-teams set, then in each team's set (or `only`'s), from its view."""
    _render_all_pages_one(store, root, config)
    for view, where in _team_sets(store, root, config, only):
        _render_all_pages_one(view, where, config)


def _render_all_pages_one(store: Store, root: Path, config: Config | None = None) -> None:
    #: The run index, derived from the records beside the store, rebuilt whenever the pages are: built first, so the
    #: pages read lineage from it (`run_index.drawing`), then written as they read it.
    #: Each linked pair this store holds, checked from both sides once (`service_link`), before the pages quote it.
    from onetrace_console import run_index, service_link
    from onetrace_console.render import render_all

    try:
        service_link.keep_linked_checks(store)
    except Exception:  # noqa: BLE001 - logged; the pages say what is kept
        traceback.print_exc(file=sys.stderr)
    #: Built as the pages are drawn (`_rendering`), so each run's verdict in its list entry is made as the runs list
    #: makes it (`run_index.LIST`).
    with _rendering(config, root):
        index = run_index.build(store)
        with run_index.drawing(index, _now()):
            rendered = render_all(store, generated_at=_now())
    for href, html in rendered.items():
        _write(root, href, html)
    run_index.write(store, root, index)
    #: A decision export names no team until its token is bound to one, so a team's set draws no Policy page.
    if config is not None and config.extensions.get("onedoor") and not isinstance(root, TeamSet):
        #: Imported only here, only when the extension is on. `_render_incidents_page`
        #: OVERWRITES incidents.html (already written above by the base render_all) with
        #: the merged rule table -- the base render is never skipped, only superseded,
        #: so a bug in this branch cannot leave incidents.html half-written.
        from onetrace_console.incident_pages import INCIDENTS, render_incidents, render_rule_list, rule_href
        from onetrace_console.onedoor_ext.decision_incidents import RULE, incident_page_args
        from onetrace_console.onedoor_ext.policy_pages import render_policy_pages

        policy = render_policy_pages(store, generated_at=_now())
        #: GET serves whatever is on disk, so a Policy page this render no longer produces
        #: (a verdict filter whose only row can no longer be checked, the couldn't-check
        #: filter once nothing is unchecked) is removed, never left showing an old value.
        _remove_policy_pages_not_in(root, set(policy))
        for href, html in policy.items():
            _write(root, href, html)

        args = incident_page_args(store)
        _write(root, INCIDENTS, render_incidents(store, generated_at=_now(), **args))
        _write(root, rule_href(RULE.id), render_rule_list(store, RULE.id, generated_at=_now(), **args))


def _render_marked_pages(run, same: list, store: Store, root: Path, config: Config | None = None) -> None:
    """The store's pages a mark of `run` changes (`render.render_all(marked=...)`), its pipeline's runs `same`; then the
    run index, which holds each run's mark. In the all-teams set and the run's team's."""
    _render_marked_pages_one(run, same, store, root, config)
    for view, where in _team_sets(store, root, config, only=(run.team,)):
        _render_marked_pages_one(run, [r for r in same if view.get_run(r.key) is not None], view, where, config)


def _render_marked_pages_one(run, same: list, store: Store, root: Path, config: Config | None = None) -> None:
    from onetrace_console.render import render_all
    from onetrace_console.verdicts import pipeline_of

    with store.reading():
        pipeline = pipeline_of(run, store)
        label = pipeline.label if pipeline is not None else ""
        from onetrace_console import run_index

        with _rendering(config, root):
            index = run_index.build(store)
            with run_index.drawing(index, _now()):
                drawn = render_all(store, generated_at=_now(), marked=(label, frozenset(r.key for r in same)))
        for href, html in drawn.items():
            _write(root, href, html)
        run_index.write(store, root, index)


def _render_diff_page(
    comparison, store: Store, root: Path, *, public: bool = False, config: Config | None = None
) -> str:
    """`public`: drawn for a public console, whose explanation panel is its place only. In one
    reading of the store (`Store.reading`), as every drawing is, even drawn alone."""
    with store.reading():
        return _render_diff_page_read(comparison, store, root, public=public, config=config)


def _render_diff_page_read(
    comparison, store: Store, root: Path, *, public: bool = False, config: Config | None = None
) -> str:
    """The comparison's pages in the all-teams set, then in its team's set where both its runs are that team's."""
    rel = _render_diff_page_one(comparison, store, root, public=public)
    for view, where in _team_sets(store, root, config):
        if view.get_comparison(comparison.key) is not None:
            _render_diff_page_one(comparison, view, where, public=public)
    return rel


def _render_diff_page_one(comparison, store: Store, root: Path, *, public: bool = False) -> str:
    from onetrace_console import views
    from onetrace_console.authorization import render_pair_authorization
    from onetrace_console.render import render_diff
    from onetrace_console.textdiff_page import page_name, render_text_diff_page, shown_document

    html = render_diff(comparison, store, generated_at=_now(), public=public)
    rel = f"diff/{comparison.key}.html"
    #: Investigate's tabs: "What changed" at the page's address, "Proof" beside it, the text diff where the
    #: comparison has one shown, and the pair's Authorization.
    text_name = page_name(comparison) if shown_document(comparison, store) is not None else ""
    tabs = views.investigate_tabs(comparison.key, text=text_name)
    said, state = views.pair_said(comparison, store)
    what, proof = views.split(
        html,
        "diff",
        f"{comparison.key}.html",
        views.proof_name(f"{comparison.key}.html"),
        said,
        state,
        views.WITHHELD_PAIR,
        tuple(tabs[2:]),
    )
    from onetrace_console.render import SKIP_TO_FIRST, with_skip

    #: The What changed tab's first focusable item: a skip link to its short answer.
    _write(root, rel, with_skip(what, SKIP_TO_FIRST))
    _write(root, f"diff/{views.proof_name(comparison.key + '.html')}", proof)
    #: Its text diff on a page of its own, where it has one shown; where it has none, no page --
    #: never one left from an earlier drawing.
    text = render_text_diff_page(comparison, store, generated_at=_now(), tabs=views.tabs_row(tabs, views.TEXT_DIFF))
    if text is not None:
        _write(root, f"diff/{page_name(comparison)}", text)
    else:
        (_pages(root) / "diff" / page_name(comparison)).unlink(missing_ok=True)
    _write(
        root,
        f"diff/{comparison.key}{views.AUTHORIZATION_SUFFIX}",
        render_pair_authorization(
            comparison, store, generated_at=_now(), tabs=views.tabs_row(tabs, views.AUTHORIZATION)
        ),
    )
    return rel


def _neighbours_on(store: Store, config: Config | None) -> bool:
    """Neighbours by input are on for this local console's store."""
    if config is None or config.public:
        return False
    from onetrace_console import neighbours

    if not neighbours.installed():
        return False
    from onetrace_console.neighbours import settings

    return settings.read(store) is not None


def _neighbours_refresh(store: Store, config: Config | None) -> None:
    """Where neighbours by input are on (a local console with the extra): embed every kept text not yet
    embedded, as recorded batches, before pages are drawn. A failure is logged and the pages draw what
    the derived file holds."""
    if not _neighbours_on(store, config):
        return
    from onetrace_console.neighbours import batches

    try:
        with store.reading():
            batches.refresh(store)
    except Exception:  # noqa: BLE001 - logged; the pages say what is there
        traceback.print_exc(file=sys.stderr)


def _render_neighbour_pages(store: Store, root: Path, config: Config | None) -> None:
    """Every run's pages and every comparison's, drawn again, and the pages over all of them."""
    with store.reading():
        for run in store.runs():
            _render_run_pages_read(run, store, root, config)
        for comparison in store.comparisons():
            try:
                _render_diff_page_read(comparison, store, root, public=bool(config and config.public), config=config)
            except Exception:  # noqa: BLE001 - that page keeps what it had; logged
                traceback.print_exc(file=sys.stderr)
        _render_all_pages_read(store, root, config)


def _render_startup_pages(store: Store, root: Path, config: Config | None = None) -> None:
    """`_render_startup_pages_read`, in one reading of the store (`Store.reading`)."""
    with store.reading():
        _render_startup_pages_read(store, root, config)


def _render_startup_pages_read(store: Store, root: Path, config: Config | None = None) -> None:
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
    from onetrace_console.checks import (
        check_options,
        run_and_record,
        stored_recipients_record,
        stored_trust_record,
        stored_tsa_record,
        trust_record,
        tsa_record,
    )

    options = check_options(config)
    current = trust_record(options["trust_file"])
    current_tsa = tsa_record(options["tsa_cert"], options["tsa_roots"])
    current_recipients = trust_record(options["recipients_file"])
    rechecked = 0
    for run in store.runs():
        recorded, recorded_tsa = stored_trust_record(run, store), stored_tsa_record(run, store)
        recorded_recipients = stored_recipients_record(run, store)
        if recorded is not None and (
            recorded != current or recorded_tsa != current_tsa or recorded_recipients != current_recipients
        ):
            try:
                run_and_record(run, store, **options)
                rechecked += 1
            except Exception:  # noqa: BLE001 - the run keeps its earlier check; logged
                import traceback

                traceback.print_exc(file=sys.stderr)
    if rechecked:
        print(
            f"onetrace-console: the trust file is now {current} and the time-stamp authority "
            f"{current_tsa}; {rechecked} stored run(s) checked again with them",
            file=sys.stderr,
        )
    _neighbours_refresh(store, config)
    from onetrace_console import startup_progress

    runs, comparisons = list(store.runs()), list(store.comparisons())
    with startup_progress.phase("drawing pages", len(runs) + len(comparisons) + 1) as step:
        _render_startup_drawn(store, root, config, runs, comparisons, step)


def _render_startup_drawn(store: Store, root: Path, config: Config | None, runs, comparisons, step) -> None:
    """Each run's pages, each comparison's, and the pages over all of them: one step each, said as the
    console starts (`startup_progress`)."""
    for run in runs:
        _render_run_pages(run, store, root, config)
        step()
    for key in store.unreadable_run_keys:
        _render_unreadable_record_pages(store, root, key, kind="run")
    for comparison in comparisons:
        step()
        try:
            _render_diff_page(comparison, store, root, public=bool(config and config.public), config=config)
        except Exception as e:  # noqa: BLE001 - that page says so, and the log has it
            #: One comparison's failure never keeps the console from starting.
            from onetrace_console.pages import refusal
            from onetrace_console.textdiff_page import page_name
            from onetrace_console.unreadable import render_failed_page
            from onetrace_console.views import AUTHORIZATION_SUFFIX, proof_name

            for name in (
                f"diff/{comparison.key}.html",
                f"diff/{proof_name(comparison.key + '.html')}",
                f"diff/{page_name(comparison)}",
                f"diff/{comparison.key}{AUTHORIZATION_SUFFIX}",
            ):
                _write(root, name, render_failed_page(refusal(e)[0], generated_at=_now()))
    for key in store.unreadable_comparison_keys:
        _render_unreadable_record_pages(store, root, key, kind="comparison")
    _render_all_pages(store, root, config)
    step()


def _render_unreadable_record_pages(store: Store, root: Path, key: str, *, kind: str) -> None:
    """The pages of a stored record this version cannot read, replaced by pages saying so.

    An unreadable comparison record was once left out of every count, and its old Diff
    page stayed on disk and was served, saying whatever it said before. The same held for a run
    record's own pages. Only a record named by a content address has pages to replace."""
    from onetrace_console.pages import ANSWER, AUTHORIZATION, CASE, RUN_PROOF
    from onetrace_console.store import _SHA256
    from onetrace_console.unreadable import render_failed_page
    from onetrace_console.views import AUTHORIZATION_SUFFIX, proof_name

    if not _SHA256.fullmatch(key):
        return
    named = store.unreadable_runs if kind == "run" else store.unreadable_comparisons
    said = next((u for u in named if u.startswith(f"{key}.json")), f"{key}.json")
    reason = f"the stored {kind} record {said} cannot be read, so nothing is drawn from it; the Overview names it"
    page = render_failed_page(reason, generated_at=_now())
    from onetrace_console.textdiff_page import SUFFIX

    names = (
        [f"runs/{key}/{n}" for n in (ANSWER, CASE, RUN_PROOF, AUTHORIZATION)]
        if kind == "run"
        else [
            f"diff/{key}.html",
            f"diff/{proof_name(key + '.html')}",
            f"diff/{key}{SUFFIX}",
            f"diff/{key}{AUTHORIZATION_SUFFIX}",
        ]
    )
    for name in names:
        _write(root, name, page)


#: The answer to `POST /compare?a=K&b=K`.
SAME_RUN = "the same run: a and b name one run, so there is nothing to compare, and no comparison was made"


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
    #: Connections the kernel holds before the console accepts them: at the standard library's 5, a
    #: burst of requests was reset before any was read.
    request_queue_size = 64

    def server_bind(self) -> None:
        if os.name == "nt":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)  # type: ignore[attr-defined]  # Windows's name, read only where os.name is nt
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
        line = json.dumps(
            {
                "at": _now(),
                "event": "error",
                "exception": type(error).__name__ if error is not None else "unknown",
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
        sys.stderr.write(line + "\n")
        sys.stderr.flush()


class ConsoleServer6(ConsoleServer):
    """The same listener on an IPv6 host such as `::1`, which the local guard already names
    as this machine's own (it was once refused as unresolvable)."""

    address_family = socket.AF_INET6


#: One intake at a time: a run delivered by `POST /v1/runs` and one the folder watcher takes in
#: (`watch.py`) each write the store and draw pages, and never at once.
INTAKE_LOCK = threading.RLock()
#: The pairs being compared now, each with its answer once made (`Handler._handle_compare`): a second press of a
#: pair waits for the first, up to COMPARE_WAIT_SECONDS.
_COMPARING: dict[tuple[str, str], dict] = {}
_COMPARING_LOCK = threading.Lock()
COMPARE_WAIT_SECONDS = 1800
COMPARING_STILL = "This pair is still being compared; its page appears when it is done."


class OnlyHeaders:
    """A request's headers with only `allowed` (lower-case names) readable: any other name asked for
    raises, so a handler that should read nothing else cannot."""

    def __init__(self, headers, allowed: set[str]):
        self._headers, self._allowed = headers, allowed

    def _check(self, name: str) -> None:
        if str(name).lower() not in self._allowed:
            raise PermissionError(f"this route reads no {name!r} header")

    def get(self, name: str, default=None):
        self._check(name)
        return self._headers.get(name, default)

    def __getitem__(self, name: str):
        self._check(name)
        return self._headers[name]

    def __contains__(self, name) -> bool:
        self._check(name)
        return name in self._headers

    def get_all(self, name: str, failobj=None):
        self._check(name)
        return self._headers.get_all(name, failobj)

    def __getattr__(self, name):
        raise PermissionError(f"this route reads no headers but {sorted(self._allowed)}")


class Handler(BaseHTTPRequestHandler):
    store_root: Path  # set by `main()` before the server starts
    store: Store  # ditto
    config: Config  # ditto -- the upload-hardening limits
    access_log: AccessLog  # ditto
    #: Sign-in step 2. `None` when `sign_in.enabled` is false -- the disabled
    #: console never constructs any of these (see `main()`), so a disabled server's
    #: Handler never even has real values here to begin with.
    account_store: AccountStore = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    session_store: SessionStore = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    rate_limit_per_account: RateLimiter = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    rate_limit_per_client: RateLimiter = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    #: `token_store` is `None` under the same "disabled means unconstructed" rule as
    #: the four above; `rate_limit_concurrent_hashes` guards `verify_password` itself,
    #: independent of which account or client is asking.
    token_store: TokenStore | None = None
    #: The audit log (`audit.Audit`): off, and recording nothing, until main() reads `audit.enabled`.
    audit: Audit = Audit()
    rate_limit_concurrent_hashes: ConcurrencyLimiter = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    #: The account's other two windows (`rate_limit.account_refusal`): per known browser, and per
    #: (account, client address) pair; `rate_limit_per_account` is the account's ceiling.
    rate_limit_per_pair: RateLimiter = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    rate_limit_per_device: RateLimiter = None  # type: ignore[assignment]  # None until main() sets it, and read only where sign-in is on
    #: Local mode's port, or `None` in config-file mode. When set, every
    #: request passes `_local_guard` first.
    local_port: int | None = None
    #: The folder watcher (`watch.py`), in `onetrace-console <runs folder>` mode only.
    watcher: Watcher = None  # type: ignore[assignment]  # None outside folder mode, where nothing lists a folder to read
    #: A public console's Compare limiter (`visitor_compare.Limiter`); None on any other console.
    visitor_limiter: Limiter = None  # type: ignore[assignment]  # None but on a public console, the only one with a Compare route
    #: Entra ID sign-in's settings and credential (`oidc_settings.load`), where `sign_in.method` is
    #: `oidc`; None on any other console.
    oidc_settings: OidcSettings | None = None
    #: The issuer those settings name (`oidc_issuer.Issuer`): its discovery document, keys and token
    #: endpoint, and its end-session endpoint for sign-out. None where `sign_in.method` is not `oidc`.
    oidc_issuer: Issuer | None = None
    #: The sign-ins begun and not yet finished (`oidc_flow.FlowStore`), in memory; None without `oidc`.
    oidc_flows: FlowStore | None = None

    server_version = "onetrace-console/0.1"

    def setup(self) -> None:
        """Each request keeps the store it started with. The class holds
        the console's store; a request reads it once, here, so a request that outlives its client
        -- or a store swapped while it runs -- never writes a run's objects to one store and its
        record to another."""
        cls = type(self)
        self.store = getattr(cls, "store", None)  # type: ignore[assignment]  # None only on a Handler no main() set up
        self.store_root = getattr(cls, "store_root", None)  # type: ignore[assignment]  # as `store`
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
        if len(hosts) != 1 or any(len(self.headers.get_all(h) or []) > 1 for h in ("Origin", "Sec-Fetch-Site")):
            self._respond(
                400,
                b"a request must carry exactly one Host, and at most one Origin and one Sec-Fetch-Site\n",
                "text/plain",
            )
            return False
        host = hosts[0].strip().lower()
        #: An absolute-form request-target names its own authority; it must be ours too.
        target = urlsplit(self.path)
        if host not in own or (target.scheme and target.netloc.lower() not in own):
            self._respond(
                421,
                f"local mode answers only its own loopback address: http://127.0.0.1:{port}\n".encode(),
                "text/plain",
            )
            return False
        if method != "GET":
            origin = self.headers.get("Origin")
            if origin is not None and origin.strip().lower() not in {f"http://{h}" for h in own}:
                self._respond(403, b"local mode refuses a write from another origin\n", "text/plain")
                return False
            site = (self.headers.get("Sec-Fetch-Site") or "").strip().lower()
            if site not in ("", "same-origin", "none"):
                self._respond(403, b"local mode refuses a write from another site\n", "text/plain")
                return False
        return True

    def _own_origin(self) -> str | None:
        """This console's origin: `sign_in.public_url`'s where it is set, else the request's own
        scheme (https on a TLS listener) and its Host."""
        from onetrace_console.config import origin_of

        configured = self.config.sign_in.get("public_url") or ""
        if configured:
            return origin_of(configured)
        import ssl

        scheme = "https" if isinstance(self.connection, ssl.SSLSocket) else "http"
        hosts = self.headers.get_all("Host") or []
        return origin_of(f"{scheme}://{hosts[0].strip()}") if len(hosts) == 1 else None

    def _same_origin_guard(self) -> bool:
        """With sign-in on, a state-changing request carried by a session cookie (no bearer token)
        whose Origin, else Referer, names another origin than this console's is refused with 403,
        before its body is read. `True` if the request may proceed. With neither header, the CSRF
        check that follows decides, as before; a bearer-token request is not checked here."""
        if not self.config.sign_in.get("enabled") or self._bearer_token() is not None:
            return True
        if self._current_session() is None:
            return True
        from onetrace_console.config import origin_of

        origins, referers = self.headers.get_all("Origin") or [], self.headers.get_all("Referer") or []
        if not origins and not referers:
            return True
        if len(origins) > 1 or (not origins and len(referers) > 1):
            said = None
        elif origins:
            said = origin_of(origins[0])
        else:
            said = origin_of(referers[0], path_allowed=True)
        own = self._own_origin()
        if said is not None and own is not None and said == own:
            return True
        self.close_connection = True
        self._respond(403, b"refused: this request comes from another origin than this console's\n", "text/plain")
        return False

    def _body_limit(self) -> int:
        """The most a request's body may hold: the configured limit, and on a local console's tokenizer
        upload, the upload's own (`token_upload.MOST_UPLOAD`)."""
        if not self.config.public and urlsplit(self.path).path == "/model-tokenizers":
            from onetrace_console.token_upload import MOST_UPLOAD

            return MOST_UPLOAD
        return self.config.max_request_body

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
        if length > self._body_limit():
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
            except OSError:  # covers both TimeoutError and the
                return None  # poisoned-socket OSError alike
            finally:
                self.connection.settimeout(None)
            if not chunk:
                return None  # the connection closed before the body arrived in full
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    # -------------------------------------------------------------- logging
    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
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
            self.access_log.append(principal="anonymous", method=self.command or "-", path=path, status=code)
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
        session = self.session_store.get(session_id)
        if session is not None and session.role is not None and self._scim_enforcing():
            #: The per-request active check: a session from Entra ID whose person the join
            #: no longer admits ends here, with every other session of that person, before the role check.
            refused = self._directory().refusal(
                session.username, tenant=self._scim_tenant(), required=self.config.scim["required_for_sign_in"]
            )
            if refused is not None:
                from onetrace_console.audit import CONSOLE

                count = self.session_store.end_principal(session.username)
                self._audit_removal(
                    "sessions.ended",
                    session.username,
                    {"count": count, "by": f"the active check: {refused}"},
                    actor=CONSOLE,
                )
                return None
        return session

    def _bearer_token(self) -> str | None:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[len("Bearer ") :].strip()
        return None

    def _granted(self) -> tuple[str | None, str]:
        """`(role, principal)` the CALLER actually presented, resolved once. A
        bearer token grants exactly `ingester`; a session grants exactly `viewer`
        -- never mixed: a machine's and a person's credentials stay apart. A
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

            #: A session from sign-in through Entra ID carries the role its `roles` claim gave; a local
            #: account's carries none, and is a viewer, as before.
            return session.role or roles.VIEWER, session.username
        return None, "anonymous"

    def _resolve_request_identity(self) -> None:
        """Resolved ONCE, at the very top of every request, before any handler
        runs -- so an action that destroys its own credential
        (sign-out invalidating the session it was just called with) is still
        logged and role-checked under the principal that made the request, not
        whatever is left of it afterward.
        """
        self._request_role, self._request_principal = self._granted()

    def _signed_in_as(self) -> str | None:
        """Who a page's footer says is signed in: a browser session's, whatever its role (viewer, or with
        sign-in through Entra ID investigator or admin), by the name Entra gives where it gave one, never the
        account's key (its tenant and object ids); None for no session, or a bearer token."""
        from onetrace_console import roles

        if getattr(self, "_request_role", None) not in (roles.VIEWER, roles.INVESTIGATOR, roles.ADMIN):
            return None
        session = self._current_session()
        if session is not None and session.display_name:
            return session.display_name
        if session is not None and session.role is not None:
            return "someone signed in through Microsoft Entra ID"
        return self._principal()

    def _audited(
        self, event: str, obj: str, detail: dict | None = None, *, actor: str | None = None, undo=None
    ) -> bool:
        """Record an action in the audit log before it is reported done: True, or False once the
        refusal is answered (`503`, nothing done; `undo`, where given, run first, so what was done is taken back before
        anyone is told). Off, it records nothing and answers True."""
        from onetrace_console.audit import AuditRefused

        try:
            self.audit.record(actor or self._principal(), event, obj, detail)
        except AuditRefused as e:
            if undo is not None:
                undo()
            self._respond(503, f"Not done: {e}.\n".encode(), "text/plain; charset=utf-8")
            return False
        return True

    def _signin_detail(self, principal: str, method: str, roles: tuple, teams: tuple) -> dict:
        """`signin.ok`'s detail: the method, the roles and teams granted, and whether they differ from the
        principal's last sign-in."""
        return {
            "method": method,
            "roles": list(roles),
            "teams": list(teams),
            "differs": self.audit.signin_differs(principal, (tuple(roles), tuple(teams))) if self.audit.on else False,
        }

    def _audit_removal(self, event: str, obj: str, detail: dict | None = None, *, actor: str | None = None) -> None:
        """Record an action that removes access: it applies whether or not the entry could be appended."""
        self.audit.record(actor or self._principal(), event, obj, detail, removes_access=True)

    def _principal(self) -> str:
        """The name the access log records for this request -- the identity
        `_resolve_request_identity` already captured at request start.
        """
        return getattr(self, "_request_principal", "anonymous")

    # -------------------------------------------------------------- teams
    def _every_team(self) -> bool:
        """Whether this request reads every team: without teams; on a console with no sign-in, the machine's own
        user's; an `admin`'s."""
        from onetrace_console import roles

        return (
            not self.config.teams
            or not self.config.sign_in.get("enabled")
            or getattr(self, "_request_role", None) == roles.ADMIN
        )

    def _my_teams(self) -> tuple[str, ...]:
        """The configured teams this request may read, in the configuration's order: every one where it reads every
        team; else the teams its session was given at sign-in; none for a bearer token or no session."""
        if self._every_team():
            return tuple(self.config.teams)
        session = self._current_session()
        if session is not None and self._scim_on():
            #: With SCIM on, teams come from its Groups, read on each request, and a role claim grants none
            #:; while its enforcement is off, SCIM grants none either.
            held = self._directory().teams_of(session.username, self.config.teams) if self._scim_enforcing() else ()
        else:
            held = session.teams if session is not None else ()
        return tuple(t for t in self.config.teams if t in held)

    def _scim_on(self) -> bool:
        return bool(self.config.scim.get("enabled")) and self.config.sign_in.get("method") == "oidc"

    def _scim_tenant(self) -> str:
        return str(self.config.scim.get("tenant_id") or (self.config.sign_in.get("oidc") or {}).get("tenant_id", ""))

    def _directory(self):
        """SCIM's records as this console reads them on each request (`scim.Directory`), made once per store root."""
        from onetrace_console import scim

        got = type(self).__dict__.get("scim_directory")
        if got is None or got.store_root != Path(self.store_root):
            got = scim.Directory(self.store_root)
            type(self).scim_directory = got
        return got

    def _scim_enforcing(self) -> bool:
        """SCIM on, and its enforcement of sign-in not turned off on the machine."""
        return self._scim_on() and self._directory().enforcement()[0]

    def _scope(self, asked: str | None):
        """(the store this request reads, the root its pages are served from), or None where it may read no set:
        another team's prefix, a prefix naming no team, or a person in no team. `asked`: the team a `/t/<team>/`
        prefix names. Without one, an `admin` reads the all-teams set and anyone else their first team's."""
        if asked is None and self._every_team():
            return self.store, self.store_root
        mine = self._my_teams()
        team = asked if asked is not None else (mine[0] if mine else None)
        if team is None or team not in mine:
            return None
        from onetrace_console.team_view import view_of

        return view_of(self.store, team), team_set(self.store_root, team)

    def _team_frame(self) -> str:
        """The served page's team line (`frame.team_line`): the team read, and the person's others to switch to; an
        admin's lists every team and the all-teams set. "" without teams."""
        if not self.config.teams:
            return ""
        from onetrace_console.frame import team_line

        seen = getattr(self, "_seen_root", None)
        current = seen.team if isinstance(seen, TeamSet) else None
        return team_line(current, self._my_teams(), every=self._every_team())

    def _views(self) -> list:
        """The stores a request that names a key may read it in: the store, where it reads every team; else each
        of its teams' views."""
        if self._every_team():
            return [self.store]
        from onetrace_console.team_view import view_of

        return [view_of(self.store, t) for t in self._my_teams()]

    def _seen_run(self, key: str):
        """The run `key` names where this request may read it, else None: another team's key reads as unknown."""
        return next((r for v in self._views() if (r := v.get_run(key)) is not None), None)

    def _seen_comparison(self, key: str):
        return next((c for v in self._views() if (c := v.get_comparison(key)) is not None), None)

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
            required = roles.required_role(
                method, path, rel_for_get=rel_for_get, oidc=self.config.sign_in.get("method") == "oidc"
            )
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
            #: No credential at all: redirect a browser, 401 a script (the two audiences
            #: are told apart, a person to sign in and a script to authenticate).
            if method == "GET":
                self._respond(303, b"", "text/plain", [("Location", self._signin_location())])
            else:
                self._respond(401, b"sign-in or a bearer token is required\n", "text/plain")
            return False
        #: A real credential, just not one that grants this route's role (the
        #: three cases item 8's own tests name: a token on a viewer page, a
        #: session on an ingester route, and -- structurally impossible here
        #: since `required_role` would have raised above -- anything else).
        self._respond(403, b"this credential does not grant the required role\n", "text/plain")
        return False

    def _submitted_csrf_token(self, *, body: bytes | None = None, query: dict | None = None) -> str:
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
        import hmac

        return (
            bool(submitted)
            and hmac.compare_digest(submitted.encode("utf-8"), cookie.encode("utf-8"))
            and hmac.compare_digest(submitted.encode("utf-8"), session.csrf_token.encode("utf-8"))
        )

    # -------------------------------------------------------------- GET
    def _reading(self):
        """One request's reading of the store (`Store.reading`): every page it draws shares one
        read of the runs and comparisons; none where no store is set."""
        from contextlib import nullcontext

        store = getattr(self, "store", None)
        return store.reading() if store is not None else nullcontext()

    def do_GET(self) -> None:  # noqa: N802
        with self._reading(), self._answering():
            if not self._scim("GET"):
                self._do_get()

    def do_PUT(self) -> None:  # noqa: N802
        with self._reading(), self._answering():
            if not self._scim("PUT"):
                self._unsupported()

    def do_PATCH(self) -> None:  # noqa: N802
        with self._reading(), self._answering():
            if not self._scim("PATCH"):
                self._unsupported()

    def do_DELETE(self) -> None:  # noqa: N802
        with self._reading(), self._answering():
            if not self._scim("DELETE"):
                self._unsupported()

    def _unsupported(self) -> None:
        """A PUT, PATCH or DELETE outside `/scim/v2`: the console serves none, so it is answered as the standard server
        answers a method with no handler, as it was before SCIM's routes."""
        self.send_error(501, f"Unsupported method ({self.command!r})")

    #: Requests from outside `scim.allowed_sources`, refused since start: the admin page and the start-up line say how
    #: many.
    scim_refused_sources: int = 0
    #: SCIM's records as read on each request (`_directory`).
    scim_directory = None
    #: The SCIM writes refused since start, newest last, at most 100: the People page lists those that would have
    #: removed access.
    scim_refused_writes: list = []

    def _scim(self, method: str) -> bool:
        """`/scim/v2/*`: answered here, ahead of the role table and the pages, by SCIM's own
        token check; False for any other path. With `scim.enabled` false, or from outside `scim.allowed_sources`, it
        answers as a route the console does not have. The token comes before every other answer, so a caller without
        it learns nothing from a `404` or a `501`."""
        from onetrace_console import scim

        path = urlsplit(self.path).path
        if path != scim.PREFIX and not path.startswith(scim.PREFIX + "/"):
            return False
        settings = self.config.scim
        self._request_role, self._request_principal = None, "anonymous"
        if not settings.get("enabled") or self.config.public:
            self._respond(404, b"no such route\n", "text/plain")
            return True
        if not scim.allowed_from(settings, self.client_address[0] if self.client_address else ""):
            type(self).scim_refused_sources += 1
            self._respond(404, b"no such route\n", "text/plain")
            return True
        query = urlsplit(self.path).query
        raw = scim.bearer(self.headers.get("Authorization"))
        in_query = "access_token" in parse_qs(query, keep_blank_values=True)
        form = (self.headers.get("Content-Type") or "").split(";")[
            0
        ].strip().lower() == "application/x-www-form-urlencoded"
        token = scim.TokenStore(self.store_root).find(raw) if raw is not None and not in_query and not form else None
        if token is None:
            #: A token in the query or a form body is refused and never looked up (RFC 6750 §2.3).
            self._scim_answer(scim.unauthorized(given=raw is not None))
            return True
        self._request_role, self._request_principal = "scim", f"scim:{token.token_id}"
        from onetrace_console import roles

        rest = path[len(scim.PREFIX) :]
        if not roles.scim_row(method, path) and not (rest in ("/Me", "/.search", "/Bulk") or rest.endswith("/.search")):
            #: No row: answered in SCIM's form, after the token, so nothing is learnt without it.
            known = any(roles.scim_row(m, path) for m in ("GET", "POST", "PUT", "PATCH", "DELETE"))
            status, said = (405, "the method is not served here") if known else (404, "no such resource")
            self._scim_answer(scim.Answer(status, scim.ScimError(status, said).body()))
            return True
        body = b""
        if method in ("POST", "PUT", "PATCH"):
            raw_length = self.headers.get("Content-Length", "0") or "0"
            try:
                length = int(raw_length)
            except ValueError:
                length = -1
            if length < 0 or length > settings["max_body_bytes"]:
                self.close_connection = True
                said = "the body is over the console's limit" if length >= 0 else "Content-Length is not a length"
                self._scim_answer(
                    scim.Answer(413 if length >= 0 else 400, scim.ScimError(413, said, "invalidSyntax").body())
                )
                return True
            got = self._read_body_bounded(length) if length else b""
            if got is None:
                self.close_connection = True
                self._scim_answer(scim.Answer(408, scim.ScimError(408, "the body did not arrive in time").body()))
                return True
            body = got
        kind = "groups" if path.startswith(scim.PREFIX + "/Groups") else "users"
        folder = Path(self.store_root) / scim.DIRNAME / kind
        named = path.rsplit("/", 1)[-1] if path.count("/") > 3 else ""
        before = (folder / f"{named}.json").read_bytes() if named and (folder / f"{named}.json").is_file() else None
        base = (self.config.sign_in.get("public_url") or "").rstrip("/")
        answer, written = scim.answer(
            method, path, query, body, store_root=self.store_root, settings=settings, base=base, token_id=token.token_id
        )
        if written is not None:
            from onetrace_console.audit import CONSOLE, AuditRefused

            detail = {
                "method": written.method,
                "changed": list(written.changed),
                "active": written.active,
                **({"dropped": list(written.dropped)} if written.dropped else {}),
            }
            if written.kind == "Group":
                detail = {"resource": "Group", **detail, "members": list(written.members or ())}
                del detail["active"]
            try:
                self.audit.record(
                    f"scim:{token.token_id}",
                    "scim.write",
                    written.user_id,
                    detail,
                    removes_access=written.removes_access,
                )
            except AuditRefused as e:
                #: Not a removal: taken back, and the directory told, so it tries again.
                kept = folder / f"{written.user_id}.json"
                if before is None:
                    kept.unlink(missing_ok=True)
                else:
                    from onetrace_console.store import _atomic_write

                    _atomic_write(kept, before)
                answer = scim.Answer(503, scim.ScimError(503, str(e)).body())
            if written.removes_access and written.kind == "User" and written.external_id and self.session_store:
                #: Deprovisioning: every live session of that person ends through the
                #: index before the answer, whatever SCIM's enforcement says, and the count is recorded.
                principal = f"{self._scim_tenant().lower()}/{written.external_id}"
                count = self.session_store.end_principal(principal)
                self._audit_removal(
                    "sessions.ended", principal, {"count": count, "by": "deprovisioning"}, actor=CONSOLE
                )
        if answer.status >= 400 and method in ("PUT", "PATCH", "DELETE"):
            text = body.decode("utf-8", "replace").lower().replace(" ", "")
            removal = "active" in text and ("false" in text)
            if method == "DELETE" or removal or '"members' in text:
                from onetrace_console.audit import now_iso

                reason = (answer.body or {}).get("detail") or (answer.body or {}).get("scimType") or ""
                type(self).scim_refused_writes = [
                    *type(self).scim_refused_writes[-99:],
                    {"at": now_iso(), "method": method, "status": answer.status, "reason": str(reason)[:200]},
                ]
        self._scim_answer(answer)
        return True

    def _scim_answer(self, answer) -> None:
        import json as _json

        from onetrace_console import scim

        body = b"" if answer.body is None else _json.dumps(answer.body, sort_keys=True).encode("utf-8")
        self._respond(answer.status, body, scim.MEDIA_TYPE, list(answer.headers))

    def _do_get(self) -> None:
        self._resolve_request_identity()
        if not self._local_guard("GET"):
            return
        path = urlsplit(self.path).path
        if path == "/health":
            self._respond(200, b"ok\n", "text/plain")
            return
        if path == "/v1/folder" and self.watcher is not None and self.local_port is not None:
            #: What the watcher knows: read by the Overview's and the runs list's notice. Answered before
            #: roles in local mode only: no configuration file, loopback, behind the local guard above. With a
            #: configuration file it is a viewer's route, answered below the role check.
            self._respond_json(200, self.watcher.state.as_json())
            return
        if path == "/signin" and self.config.sign_in.get("enabled"):
            self._handle_signin_get()
            return
        if path in ("/signin/oidc/start", "/signin/oidc/callback") and self._oidc():
            self._handle_oidc(path)
            return
        if path == "/robots.txt" and self.config.public:
            #: A public console lets search engines crawl, so each page's `noindex` can be read (`search_engines`).
            from onetrace_console.search_engines import ROBOTS_TXT

            self._respond(200, ROBOTS_TXT.encode("utf-8"), "text/plain; charset=utf-8")
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
        #: With teams, `/t/<team>/` names the team whose set is read; the rest of the path is the page.
        asked, team = rel, None
        prefixed = _TEAM_PREFIX.fullmatch(rel) if self.config.teams else None
        if prefixed:
            team, rel = prefixed.group(1), prefixed.group(2) or "home.html"
        #: A path that could step around the role table is refused
        #: before the role check and before any file is touched -- `..`, a backslash, an
        #: encoded dot or backslash, or an empty or `.` segment.
        segments = rel.split("/")
        if ".." in rel or "\\" in rel or _ENCODED_DOT_OR_BACKSLASH.search(rel) or any(s in ("", ".") for s in segments):
            self._respond(400, b"bad path\n", "text/plain")
            return
        if not self._enforce_role("GET", path, rel_for_get=rel):
            return
        scope = self._scope(team)
        if scope is None and not self._every_team() and not self._my_teams():
            #: A person in no team: one page, the same whatever was asked for, naming no team.
            from onetrace_console.team_assign import no_team_page

            self._setup_page(403, no_team_page(), "no-team", self._signed_in_as())
            return
        if scope is None:
            #: Another team's set, a team that does not exist: the answer of a page not drawn, echoing the path asked
            #: for, byte for byte.
            self._respond(404, f"not rendered: {asked}\n".encode(), "text/plain")
            return
        self._seen, self._seen_root = scope
        moved = _MOVED_RUN_PATH.fullmatch(rel) if self.config.teams else None
        if moved and self._seen.get_run(moved.group(1)) is None:
            #: A run `run assign` keyed anew: its old address leads to the new one for a person who can see the
            #: run where it is asked for; anyone else gets what a run that does not exist gets, below.
            new = self.store.moved_to(moved.group(1))
            if new is not None and self._seen.get_run(new) is not None:
                where = asked[: len(asked) - len(rel)] + f"runs/{new}/{moved.group(2)}"
                self._respond(302, b"", "text/plain", [("Location", "/" + where)])
                return
        if rel == "v1/folder":
            #: The watched folder's state, for a viewer: the folder's path, the runs it took in and changed, its
            #: errors. A console with no watcher has none.
            if self.watcher is None:
                self._respond(404, b"not found\n", "text/plain")
                return
            if self.config.teams and not self._every_team() and self.config.folder_team not in self._my_teams():
                #: With teams, the folder's runs are its team's: anyone else is answered as for a
                #: route the console does not have, as the role check answers one.
                self._respond(404, b"no such route\n", "text/plain")
                return
            self._respond_json(200, self.watcher.state.as_json())
            return
        record = _RECORD_PATH.fullmatch(rel)
        if record:
            self._handle_record(record.group(1))
            return
        if rel in ("admin/people", "admin/teams", "admin/audit"):
            #: The admin pages (`admin_pages`): drawn as they are asked for, from SCIM's records, the configuration
            #: and the audit log's head, never from runs. A public console has none.
            if self.config.public:
                self._respond(404, f"not rendered: {asked}\n".encode(), "text/plain")
                return
            from onetrace_console import admin_pages
            from onetrace_console.frame import fill

            facts = admin_pages.gather(
                self.store_root,
                self.config,
                audit_log=self.audit.log,
                refused_sources=type(self).scim_refused_sources,
                refused_writes=list(type(self).scim_refused_writes),
            )
            drawn = admin_pages.page(rel.split("/", 1)[1], facts).encode("utf-8")
            framed = fill(
                drawn,
                rel,
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=self._signed_in_as(),
                csrf=self._session_csrf(),
                setup_link=True,
                store=None,
            )
            self._respond(200, framed, "text/html; charset=utf-8")
            return
        if rel == "explain/setup":
            #: The setup page, a local console's only: drawn as it is asked for, read-only, and
            #: framed as every page is. A public console has none.
            if self.config.public:
                self._respond(404, b"not found\n", "text/plain")
                return
            from onetrace_console.explain_setup import page as setup_page
            from onetrace_console.frame import fill

            user = self._signed_in_as()
            self._setup_page(200, setup_page(self.store), rel, user)
            return
        if rel == "forwarding/setup":
            #: Trace forwarding's setup page (`forward_pages`), a local console's only, an admin's (the role table).
            if self.config.public:
                self._respond(404, b"not found\n", "text/plain")
                return
            from onetrace_console.forward_pages import page as forwarding_page

            self._setup_page(200, forwarding_page(self.store_root), rel, self._signed_in_as())
            return
        if rel == "neighbours/setup" and self._neighbours():
            self._handle_neighbours_setup()
            return
        if rel == "neighbours/setup" and not self.config.public:
            #: A local console without the extra: the page says so, with the Python the console runs
            #: from and the install line. A public console has no such page, the extra or not.
            from onetrace_console.frame import fill
            from onetrace_console.neighbours.pages import PATH, missing_page

            user = self._signed_in_as()
            self._respond(
                200,
                fill(
                    missing_page().encode("utf-8"),
                    PATH,
                    onedoor=bool(self.config.extensions.get("onedoor")),
                    user=user,
                    csrf=self._session_csrf(),
                    setup_link=True,
                    store=self.store,
                ),
                "text/html; charset=utf-8",
            )
            return
        if rel == "model-tokenizers":
            #: The tokenizers this console keeps, with Remove: a local console's only.
            if self.config.public:
                self._respond(404, b"not found\n", "text/plain")
                return
            from onetrace_console import token_upload
            from onetrace_console.frame import fill

            user = self._signed_in_as()
            from onetrace_console.render import _document

            page = _document(
                token_upload.SETTINGS_HEADING,
                f'<div class="cp">{self._tokenizers_page(token_upload)}</div>',
            )
            self._respond(
                200,
                fill(
                    page.encode("utf-8"),
                    rel,
                    onedoor=bool(self.config.extensions.get("onedoor")),
                    user=user,
                    csrf=self._session_csrf(),
                    setup_link=True,
                    store=self.store,
                ),
                "text/html; charset=utf-8",
            )
            return
        if rel == "search":
            self._handle_search()
            return
        if rel == "runs":
            self._handle_runs()
            return
        if rel == "bisect":
            self._handle_bisect()
            return
        if rel == "explain/state":
            #: A comparison's press now running, read by its panel's script while it waits.
            from onetrace_console import explain

            key = (parse_qs(urlsplit(self.path).query).get("c") or [""])[0]
            try:
                said = explain.state(self._seen, key)
            except ValueError:
                self._respond_json(400, {"error": "unknown or malformed comparison key"})
                return
            self._respond_json(200, said)
            return
        pages = _pages(self._seen_root).resolve()
        target = _pages(self._seen_root) / rel
        try:
            #: The page served is exactly the one the role row matched: under `pages/`, and
            #: resolving to the same relative path, spelled the same way.
            resolved = target.resolve().relative_to(pages).as_posix()
        except ValueError:
            resolved = None
        if resolved != rel:
            self._respond(400, b"bad path\n", "text/plain")
            return
        if not target.is_file() and self.config.public:
            #: A comparison a visitor made (`visitor_compare`), from the cache beside the store.
            from onetrace_console.visitor_compare import cache_root, cached_page

            cached = cached_page(cache_root(self.config, self.store_root), rel)
            if cached is not None:
                from onetrace_console.frame import fill

                self._respond(200, fill(cached, rel, onedoor=False, user=None, public=True), "text/html; charset=utf-8")
                return
        if not target.is_file():
            self._respond(404, f"not rendered: {asked}\n".encode(), "text/plain")
            return
        #: The frame is filled here, as the page is served, because only the
        #: server knows the session the footer states. A page with no empty frame -- a sealed
        #: page -- is served exactly as written.
        from onetrace_console.frame import fill

        user = self._signed_in_as()
        served = fill(
            target.read_bytes(),
            rel,
            onedoor=bool(self.config.extensions.get("onedoor")),
            user=user,
            csrf=self._session_csrf(),
            public=self.config.public,
            setup_link=not self.config.public,
            store=self.store,
            team=self._team_frame(),
        )
        #: The hosted demo and the capture store's app link to each other, as their deploy names them.
        from onetrace_console.app_links import with_link

        served = with_link(served, rel, public=self.config.public)
        if not self.config.public:
            from onetrace_console.frame import fill_csrf

            served = fill_csrf(served, self._session_csrf())
            #: A comparison's checks run on its page: their kept results where the checks are listed.
            ran = re.fullmatch(r"(?:t/[^/]+/)?diff/([0-9a-f]{64})\.html", rel)
            if ran:
                from onetrace_console.compare_view import with_results

                served = with_results(served, self.store, ran.group(1))
        self._respond(200, served, "text/html; charset=utf-8")

    # -------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        with self._reading(), self._answering():
            self._do_post()

    def _do_post(self) -> None:
        if self.config.public:
            #: The public mode's one exception, Compare on a pipeline's own runs
            #: (`visitor_compare`), reading nothing but its two ids and what its limiter needs.
            if urlsplit(self.path).path == "/compare":
                self._handle_visitor_compare()
                return
            #: The public mode's one check, ahead of everything else -- the routing, the
            #: Content-Length, the body: every other POST is refused, a route added later included,
            #: and not a byte of the body is read. The connection is closed rather than drained.
            from onetrace_console.public import REFUSAL

            self.close_connection = True
            self._respond(403, (REFUSAL + "\n").encode("utf-8"), "text/plain; charset=utf-8")
            return
        if self._scim("POST"):
            return
        self._resolve_request_identity()
        if not self._local_guard("POST"):
            return
        if not self._same_origin_guard():
            return
        split = urlsplit(self.path)

        raw_length = self.headers.get("Content-Length", "0") or "0"
        try:
            length = int(raw_length)
        except ValueError:
            self._respond(400, f"Content-Length is not an integer: {raw_length!r}\n".encode(), "text/plain")
            self.close_connection = True
            return
        if length < 0:
            self._respond(400, f"Content-Length is negative: {length}\n".encode(), "text/plain")
            self.close_connection = True
            return

        #: Refused BEFORE the read starts, and the connection is closed rather than
        #: drained: reading and discarding a body that was refused for being too large
        #: is the same cost the limit exists to avoid.
        if length > self._body_limit():
            self._respond(
                413,
                f"body of {length} bytes exceeds the configured {self._body_limit()}-byte limit\n".encode(),
                "text/plain",
            )
            self.close_connection = True
            return

        body = self._read_body_bounded(length) if length else b""
        if body is None:
            #: Either the wall-clock deadline passed (a stalled or trickling client,
            #: item 4) or the connection closed before the declared length arrived (a
            #: truncated request, item 5) -- both are the client's fault and neither is
            #: a servable body, so neither reaches a route handler.
            self._respond(408, b"request body did not arrive in full within the configured timeout\n", "text/plain")
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
                #: The pipeline page's picker posts a form: a and b, and the CSRF token, in the body.
                form = bool(body) and not query.get("a")
                if form:
                    query = parse_qs(body.decode("utf-8", "replace"))
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_compare(query, form=form)
            elif split.path == "/compare/check":
                if not self._enforce_role("POST", "/compare/check"):
                    return
                #: The page's form sends its fields in the body; a client may name them in the query, as for /compare.
                form_q = {**parse_qs(split.query), **parse_qs(body.decode("utf-8", "replace"))}
                if not self._check_action_csrf(query=form_q):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_compare_check(form_q)
            elif split.path in ("/explain", "/explain/packet", "/explain/check", "/explain/cancel", "/explain/text"):
                if not self._enforce_role("POST", split.path):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_explain(split.path, query)
            elif split.path == "/benchmark":
                if not self._enforce_role("POST", "/benchmark"):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_benchmark(query, body)
            elif split.path == "/expectations":
                if not self._enforce_role("POST", "/expectations"):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_expectations(query, body)
            elif split.path in ("/model-tokenizers", "/model-tokenizers/remove"):
                if not self._enforce_role("POST", split.path):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_model_tokenizers(split.path, query, body)
            elif split.path == "/runs/load-not-closed" and self.watcher is not None and not self.config.public:
                if not self._enforce_role("POST", split.path):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_load_not_closed(query)
            elif split.path == "/text-diff/more":
                if not self._enforce_role("POST", "/text-diff/more"):
                    return
                query = parse_qs(split.query)
                if not self._check_action_csrf(query=query):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_text_diff_more(query)
            elif split.path == "/explain/setup" and not self.config.public:
                #: The Set up Explain form's Save (`explain_setup.save`): a local console's only; a public
                #: console has no such route.
                if not self._enforce_role("POST", split.path):
                    return
                if not self._check_action_csrf(body=body):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_explain_setup(body)
            elif split.path == "/forwarding/setup" and not self.config.public:
                #: Trace forwarding's changes and its test trace (`forward_pages`): a local console's only.
                if not self._enforce_role("POST", split.path):
                    return
                if not self._check_action_csrf(body=body):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_forwarding(body)
            elif split.path in ("/neighbours/on", "/neighbours/off") and self._neighbours():
                #: Neighbours by input (`neighbours`): a route only where the extra is installed on a
                #: local console; anywhere else this is the unknown route below.
                if not self._enforce_role("POST", split.path):
                    return
                if not self._check_action_csrf(body=body):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_neighbours(split.path, body)
            elif split.path == "/v1/decisions" and self.config.extensions.get("onedoor"):
                #: Imported only here, only once the config key is checked -- a disabled
                #: console never reaches this line, so it never imports the extension.
                #: See tests/test_onedoor_ext_isolation.py.
                if not self._enforce_role("POST", "/v1/decisions"):
                    return
                self._handle_decisions(body)
            elif split.path == "/signin" and self.config.sign_in.get("enabled") and not self._oidc():
                #: With sign-in through Entra ID, local sign-in is off: no such route.
                self._handle_signin_post(body)
            elif split.path == "/signout" and self.config.sign_in.get("enabled"):
                if not self._check_action_csrf(body=body):
                    self._respond(403, b"missing or mismatched CSRF token\n", "text/plain")
                    return
                self._handle_signout()
            else:
                self._respond(404, b"no such route\n", "text/plain")
        except Exception:  # noqa: BLE001 - reported, not swallowed
            #: An error reading the accounts during `POST /signin`, which needs no session, can name a path on this
            #: machine: answered as any request's unhandled error is.
            self._unhandled()

    # ---------------------------------------------------------------- sign-in
    def _cookie_secure(self) -> bool:
        """`Secure` on every cookie whenever sign-in is on, not
        only when this process itself terminates TLS -- see `signin.cookies_secure`.
        """
        from onetrace_console.signin import cookies_secure

        return cookies_secure(self.config)

    def _handle_signin_get(self) -> None:
        from onetrace_console.signin import CSRF_COOKIE, new_csrf_form_token, render_signin_page, set_cookie_header

        if self._oidc():
            from onetrace_console.oidc_flow import safe_next
            from onetrace_console.signin import render_oidc_signin_page

            asked = parse_qs(urlsplit(self.path).query).get("next", ["/"])[0]
            page = render_oidc_signin_page(safe_next(asked)).encode("utf-8")
            self._respond(200, page, "text/html; charset=utf-8")
            return
        token = new_csrf_form_token()
        body = render_signin_page(csrf_token=token).encode("utf-8")
        cookie = set_cookie_header(CSRF_COOKIE, token, http_only=False, secure=self._cookie_secure())
        self._respond(200, body, "text/html; charset=utf-8", [("Set-Cookie", cookie)])

    def _handle_signin_post(self, body: bytes) -> None:
        from onetrace_console.signin import (
            CSRF_COOKIE,
            CSRF_FIELD,
            SESSION_COOKIE,
            new_csrf_form_token,
            parse_cookies,
            parse_signin_form,
            render_signin_page,
            set_cookie_header,
        )

        form = parse_signin_form(body)
        cookies = parse_cookies(self.headers.get("Cookie"))

        #: CSRF: the cookie set when the form was rendered must equal
        #: the hidden field the form submitted. Neither present, or the two disagree,
        #: is refused the same way -- never distinguished for an attacker's benefit.
        submitted_csrf = form.get(CSRF_FIELD, "")
        cookie_csrf = cookies.get(CSRF_COOKIE, "")
        import hmac

        if (
            not submitted_csrf
            or not cookie_csrf
            or not hmac.compare_digest(submitted_csrf.encode("utf-8"), cookie_csrf.encode("utf-8"))
        ):
            self._respond(403, b"sign-in refused: missing or mismatched CSRF token\n", "text/plain")
            return

        username = form.get("username", "")
        password = form.get("password", "").encode("utf-8")
        from onetrace_console.rate_limit import client_address

        peer = self.client_address[0] if self.client_address else "unknown"
        client_key = client_address(
            peer, self.headers.get_all("X-Forwarded-For") or [], self.config.sign_in.get("trusted_proxies") or []
        )

        #: Rate limits, item 3: per account AND per client, checked before the
        #: password is ever touched -- a limited-out request never reaches scrypt.
        if not self.rate_limit_per_client.check_and_record(client_key):
            self._respond(429, b"too many sign-in attempts from this client\n", "text/plain")
            return
        device = None
        if username:
            from onetrace_console.rate_limit import account_refusal

            device = self._valid_device(username, cookies)
            if self.rate_limit_per_account is not None:
                self.rate_limit_per_account.clear_once(username, self.account_store.unlocked_at(username))
            refused = account_refusal(username, client_key, device, self._signin_limiters())
            if refused is not None:
                named = username if self.account_store.exists(username) else "unknown"
                self._audit_removal("signin.refused", named, {"method": "local", "reason": "locked out"}, actor=named)
                #: The same words and status whether or not the name has an account.
                token = new_csrf_form_token()
                page = render_signin_page(csrf_token=token, error=SIGNIN_LIMIT_WORDS[refused]).encode("utf-8")
                self._respond(
                    429,
                    page,
                    "text/html; charset=utf-8",
                    [
                        (
                            "Set-Cookie",
                            set_cookie_header(CSRF_COOKIE, token, http_only=False, secure=self._cookie_secure()),
                        )
                    ],
                )
                return

        #: A global cap on concurrent scrypt computations, checked
        #: before `verify_password` -- which itself always hashes, real account or
        #: not (item 3) -- ever runs. Refused with 503, never silently queued: a
        #: caller that cannot get a slot right now gets an honest "too busy", not
        #: a wrong-password page that would misreport why it failed.
        if not self.rate_limit_concurrent_hashes.try_acquire():
            self._respond(503, b"too many concurrent sign-in attempts; try again shortly\n", "text/plain")
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
            from onetrace_console.rate_limit import after_right_password

            after_right_password(username, client_key, device, self._signin_limiters())
            if not self._audited("signin.ok", username, self._signin_detail(username, "local", (), ()), actor=username):
                return
            session = self.session_store.create(username)
            cookie = set_cookie_header(SESSION_COOKIE, session.session_id, http_only=True, secure=self._cookie_secure())
            #: The CSRF cookie is no longer just cleared on
            #: success -- it is set to the SESSION's own token (`sessions.py`
            #: already mints one per session), the value `POST /compare` and
            #: `POST /signout` must echo back. Not `HttpOnly`, the same reasoning
            #: as the pre-auth token: a form must be able to carry it.
            action_csrf = set_cookie_header(
                CSRF_COOKIE, session.csrf_token, http_only=False, secure=self._cookie_secure()
            )
            known = self._device_cookie_header(username)
            self._respond(
                303,
                b"",
                "text/plain",
                [
                    ("Set-Cookie", cookie),
                    ("Set-Cookie", action_csrf),
                    *([("Set-Cookie", known)] if known else []),
                    ("Location", "/"),
                ],
            )
            return

        #: A name that matches no account is not kept: it may be a password typed into the wrong field.
        named = username if username and self.account_store.exists(username) else "unknown"
        self._audit_removal("signin.refused", named, {"method": "local", "reason": "wrong password"}, actor=named)
        #: A fresh CSRF token for the re-shown form -- the one just submitted is spent
        #: either way, matching the "one token per render" shape the GET side sets up.
        token = new_csrf_form_token()
        retry_cookie = set_cookie_header(CSRF_COOKIE, token, http_only=False, secure=self._cookie_secure())
        page = render_signin_page(csrf_token=token, error="wrong username or password").encode("utf-8")
        self._respond(401, page, "text/html; charset=utf-8", [("Set-Cookie", retry_cookie)])

    def _signin_limiters(self) -> dict:
        return {
            n: getattr(self, n, None)
            for n in ("rate_limit_per_account", "rate_limit_per_pair", "rate_limit_per_device")
        }

    def _valid_device(self, username: str, cookies: dict) -> str | None:
        """The id of the request's device cookie where it is valid for `username`, else None. The
        key is read at each attempt, so `admin device-key rotate` reaches a running console."""
        from onetrace_console import device_cookie

        value = cookies.get(device_cookie.COOKIE)
        if not value or self.account_store is None:
            return None
        return device_cookie.valid_for(device_cookie.read_key(self.account_store.root), value, username)

    def _device_cookie_header(self, username: str) -> str | None:
        """A right password's new device cookie, where the console has a device key."""
        from onetrace_console import device_cookie
        from onetrace_console.signin import set_cookie_header

        key = device_cookie.read_key(self.account_store.root)
        if key is None:
            return None
        return set_cookie_header(
            device_cookie.COOKIE,
            device_cookie.make(key, username),
            http_only=True,
            secure=self._cookie_secure(),
            max_age=device_cookie.LIFETIME_SECONDS,
        )

    def _handle_record(self, key: str) -> None:
        """The run's own record for download: the delivery as it arrived, byte for byte
        (`ingest.bundle`). A page that shortens a run's words offers it."""
        from onetrace_console.ingest import bundle
        from onetrace_console.store import MISSING_OBJECT, StoreError

        try:
            #: Another team's key reads as an unknown one, before the run is looked up.
            run = self._seen_run(key)
            gone = self.store.missing(run) if run is not None else ()
            if gone:
                #: Said in the fixed words, not as an object's hash.
                self._respond(
                    409,
                    (MISSING_OBJECT.format(objects=", ".join(gone)) + "\n").encode("utf-8"),
                    "text/plain; charset=utf-8",
                )
                return
            body = bundle(run, self.store, public=self.config.public) if run is not None else None
        except StoreError as e:
            self._respond(409, f"{e}\n".encode(), "text/plain; charset=utf-8")
            return
        if body is None:
            self._respond(404, b"no such run\n", "text/plain")
            return
        self._respond(200, body, "application/x-tar", [("Content-Disposition", f'attachment; filename="{key}.tar"')])

    # -------------------------------------------------------------- sign-in through Entra ID
    def _oidc(self) -> bool:
        """Sign-in through Entra ID is on: `sign_in.method` `oidc`, its settings read at start."""
        return (
            bool(self.config.sign_in.get("enabled"))
            and self.config.sign_in.get("method") == "oidc"
            and self.oidc_settings is not None
        )

    def _signin_location(self) -> str:
        """Where a browser with no session is sent: the sign-in page, carrying, with Entra ID, the path
        and query it asked for, which the flow records and returns to (`oidc_flow.safe_next`)."""
        if not self._oidc():
            return "/signin"
        from urllib.parse import quote

        split = urlsplit(self.path)
        asked = split.path + (f"?{split.query}" if split.query else "")
        return "/signin?next=" + quote(asked, safe="")

    def log_request(self, code="-", size="-") -> None:  # noqa: ANN001
        """The standard request line, with the flow's query left out: the callback's carries the code
        and the state, which no log line may hold."""
        line = self.requestline
        parts = line.split(" ")
        if (
            len(parts) >= 2
            and "?" in parts[1]
            and urlsplit(parts[1]).path in ("/signin/oidc/start", "/signin/oidc/callback")
        ):
            parts[1] = parts[1].split("?", 1)[0] + "?(not logged)"
            line = " ".join(parts)
        self.log_message('"%s" %s %s', line, str(code), str(size))

    def _handle_oidc(self, path: str) -> None:
        """The flow's start (a flow kept, its cookie set, the browser sent to Entra) and its callback (the
        flow taken once, the code redeemed, the ID token checked, a session made)."""
        from onetrace_console import oidc_flow
        from onetrace_console.oidc_identity import NoRole
        from onetrace_console.oidc_issuer import IssuerError
        from onetrace_console.signin import (
            CSRF_COOKIE,
            SESSION_COOKIE,
            flow_cookie_header,
            parse_cookies,
            render_oidc_refused_page,
            render_signed_in_page,
            set_cookie_header,
        )

        assert self.oidc_settings is not None and self.oidc_issuer is not None and self.oidc_flows is not None
        query = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query, keep_blank_values=True).items()}
        secure = self._cookie_secure()
        html = "text/html; charset=utf-8"
        if path == "/signin/oidc/start":
            try:
                endpoint = self.oidc_issuer.endpoints().authorization
            except IssuerError as e:
                page = render_oidc_refused_page(f"Microsoft's sign-in could not be reached: {e}.")
                self._respond(503, page.encode("utf-8"), html)
                return
            flow_id, flow = self.oidc_flows.start(query.get("next", "/"))
            self._respond(
                303,
                b"",
                "text/plain",
                [
                    ("Set-Cookie", flow_cookie_header(flow_id, secure=secure, max_age=oidc_flow.FLOW_SECONDS)),
                    ("Location", oidc_flow.authorize_url(endpoint, self.oidc_settings, flow)),
                ],
            )
            return
        taken = self.oidc_flows.take(parse_cookies(self.headers.get("Cookie")).get(oidc_flow.FLOW_COOKIE))
        cleared = ("Set-Cookie", flow_cookie_header("", secure=secure, max_age=0))
        try:
            code = oidc_flow.check_callback(query, taken)
            assert taken is not None
            who = oidc_flow.finish(code, taken, self.oidc_settings, self.oidc_issuer)
        except NoRole as e:
            who_refused = getattr(e, "key", "") or "unknown"
            self._audit_removal(
                "signin.refused", who_refused, {"method": "oidc", "reason": "no role"}, actor=who_refused
            )
            self._respond(403, render_oidc_refused_page(str(e), no_role=True).encode("utf-8"), html, [cleared])
            return
        except oidc_flow.SignInRefused as e:
            self._audit_removal(
                "signin.refused", "unknown", {"method": "oidc", "reason": "the sign-in was refused"}, actor="unknown"
            )
            self._respond(400, render_oidc_refused_page(str(e)).encode("utf-8"), html, [cleared])
            return
        #: Without SCIM, a person is in each team whose `role_claim` the token's app roles hold, read here, at sign-in
        #: only.
        teams = tuple(t for t, entry in self.config.teams.items() if entry.get("role_claim") in who.app_roles)
        if self._scim_on():
            #: With SCIM on, a role claim grants no team; SCIM's Groups do, read on each request.
            teams = ()
            if self._scim_enforcing():
                refused = self._directory().refusal(
                    who.key, tenant=self._scim_tenant(), required=self.config.scim["required_for_sign_in"]
                )
                if refused is not None:
                    #: The join: refused, and the refusal recorded.
                    self._audit_removal("signin.refused", who.key, {"method": "oidc", "reason": refused}, actor=who.key)
                    page = render_oidc_refused_page("not provisioned for this console")
                    self._respond(403, page.encode("utf-8"), html, [cleared])
                    return
        roles_granted = (who.role,) if who.role else ()
        if not self._audited(
            "signin.ok", who.key, self._signin_detail(who.key, "oidc", roles_granted, teams), actor=who.key
        ):
            return
        session = self.session_store.create(
            who.key, role=who.role, display_name=who.display_name, expires_at=who.expires_at, teams=teams
        )
        self._respond(
            200,
            render_signed_in_page(taken.next_path).encode("utf-8"),
            html,
            [
                ("Set-Cookie", set_cookie_header(SESSION_COOKIE, session.session_id, http_only=True, secure=secure)),
                ("Set-Cookie", set_cookie_header(CSRF_COOKIE, session.csrf_token, http_only=False, secure=secure)),
                cleared,
            ],
        )

    def _handle_signout(self) -> None:
        from onetrace_console.signin import CSRF_COOKIE, SESSION_COOKIE, clear_cookie_header, parse_cookies

        cookies = parse_cookies(self.headers.get("Cookie"))
        session_id = cookies.get(SESSION_COOKIE)
        if session_id:
            ending = self.session_store.get(session_id)
            if ending is not None:
                self._audit_removal("signout", ending.username, {"how": "pressed"}, actor=ending.username)
            self.session_store.invalidate(session_id)
        cookie = clear_cookie_header(SESSION_COOKIE, secure=self._cookie_secure())
        csrf_cookie = clear_cookie_header(CSRF_COOKIE, secure=self._cookie_secure())
        if self.config.sign_in.get("method") == "oidc":
            #: Sign-in through Entra ID: the console's session is ended above; Entra's own is offered,
            #: by its end-session endpoint where the issuer names one.
            from onetrace_console.oidc_issuer import IssuerError
            from onetrace_console.signin import render_signed_out_page

            try:
                entra = self.oidc_issuer.endpoints().end_session if self.oidc_issuer is not None else None
            except IssuerError:
                entra = None
            page = render_signed_out_page(entra).encode("utf-8")
            self._respond(200, page, "text/html; charset=utf-8", [("Set-Cookie", cookie), ("Set-Cookie", csrf_cookie)])
            return
        self._respond(
            303, b"", "text/plain", [("Set-Cookie", cookie), ("Set-Cookie", csrf_cookie), ("Location", "/signin")]
        )

    def _handle_ingest(self, body: bytes) -> None:
        from onetrace_console.ingest import Rejection, accept

        with INTAKE_LOCK:
            self._ingest_locked(body, accept, Rejection)

    def _ingest_locked(self, body: bytes, accept, Rejection) -> None:
        from onetrace_console.checks import run_and_record

        team = ""
        if self.config.teams:
            #: The delivering token's team, and nothing the uploader writes. The console
            #: refused to start with a live token bound to none, so a delivery with none came with no token.
            token = self._bearer_token()
            record = self.token_store.record_for(token) if token is not None and self.token_store else None
            team = record.team if record is not None else ""
            if not team:
                self._respond_json(
                    403,
                    {
                        "accepted": False,
                        "rows": [],
                        "body": "Not stored: this console has teams, and a run is delivered by an ingester token "
                        "bound to its team. Deliver it with one (onetrace-console token create <principal> "
                        "--team <team>).\n",
                        "from_verifier": False,
                    },
                )
                return
        accepted = accept(body, self.store, limits=self.config, team=team)
        if isinstance(accepted, Rejection):
            self._respond_json(
                accepted.status,
                {
                    "accepted": False,
                    "rows": list(accepted.rows),
                    "body": accepted.body,
                    "from_verifier": accepted.from_verifier,
                },
            )
            return
        from onetrace_console.checks import check_options

        run = run_and_record(accepted.run, self.store, **check_options(self.config))
        if accepted.created:
            #: Recorded once its check has said its verdict, before a page is drawn or the uploader told; where it
            #: cannot be, the run is taken back and the delivery refused.
            token = self._bearer_token()
            held = self.token_store.record_for(token) if token is not None and self.token_store else None
            detail = {
                "run_id": run.run_id,
                "team": run.team,
                "token": held.token_id if held is not None else None,
                "build": _build_identity(),
                "verdict": run.check_verdict,
            }
            actor = f"ingester:{held.token_id}" if held is not None else None
            if not self._audited(
                "run.uploaded", run.key, detail, actor=actor, undo=lambda: type(self).store.withdraw_run(run.key)
            ):
                return
        #: A new run's kept texts embedded first, where neighbours are on: its page and its group's
        #: are drawn with them.
        if _neighbours_on(self.store, self.config):
            _neighbours_refresh(self.store, self.config)
            _render_neighbour_pages(self.store, self.store_root, self.config)
        else:
            _render_run_pages(run, self.store, self.store_root, self.config)
            #: The all-teams set and the delivered run's team's set.
            _render_all_pages(self.store, self.store_root, self.config, only=(run.team,))
        self._respond_json(
            200,
            {
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
            },
        )

    def _handle_decisions(self, body: bytes) -> None:
        from onetrace_console.onedoor_ext.decisions import DecisionsRejection, accept_export

        try:
            accepted = accept_export(body, self.store, limits=self.config)
        except DecisionsRejection as e:
            self._respond(422, e.body.encode("utf-8"), "text/plain")
            return
        #: A decision export changes the Policy pages, which only the all-teams set draws.
        _render_all_pages(self.store, self.store_root, self.config, only=())
        self._respond_json(
            accepted.status,
            {
                "accepted": True,
                "export_key": accepted.export.key,
                "row_count": len(accepted.export.rows),
                "pages": {"policy": "/policy.html"},
            },
        )

    def _compare_answer(self, status: int, said: dict, form: bool) -> None:
        """`POST /compare`'s answer: JSON to the Compare buttons; to the picker's form, a redirect to
        the comparison, or a page with the refusal in the same words."""
        if not form:
            self._respond_json(status, said)
            return
        if status == 200 and said.get("pages", {}).get("diff"):
            self._respond(303, b"", "text/plain", [("Location", said["pages"]["diff"])])
            return
        from onetrace_console.frame import fill
        from onetrace_console.visitor_compare import answer_page

        words = str(said.get("error") or said.get("answer") or "Not compared")
        words = words if words.rstrip().endswith((".", "!", "?", "…")) else words + "."
        html = answer_page("Not compared", words, back="/home.html")
        self._respond(
            status if status != 200 else 400,
            fill(
                html.encode("utf-8"),
                "compare",
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=None,
                setup_link=True,
                store=self.store,
            ),
            "text/html; charset=utf-8",
        )

    def _handle_compare(self, query: dict[str, list[str]], form: bool = False) -> None:
        from onetrace_console.compare import ComparisonError, compare
        from onetrace_console.store import StoreError

        unreadable: list[str] = []

        def lookup(key: str):
            if not key:
                return None
            try:
                return self._seen_run(key)
            except StoreError as e:
                if "cannot be read" in str(e):
                    #: A record the store holds and cannot read is said as that, not as an
                    #: unknown key.
                    unreadable.append(str(e))
                return None  # malformed key: same as "unknown"

        a_key = (query.get("a") or [""])[0]
        b_key = (query.get("b") or [""])[0]
        a_run = lookup(a_key)
        b_run = lookup(b_key)
        if a_run is None or b_run is None:
            missing = [k for k, r in (("a", a_run), ("b", b_run)) if r is None]
            self._compare_answer(
                400,
                {"error": "; ".join(unreadable) if unreadable else f"unknown or malformed run key(s): {missing}"},
                form,
            )
            return
        if not self._every_team() and not any(
            v.get_run(a_run.key) is not None and v.get_run(b_run.key) is not None for v in self._views()
        ):
            #: Both runs in one of the person's teams, or the second answers as an unknown key.
            self._compare_answer(400, {"error": "unknown or malformed run key(s): ['b']"}, form)
            return
        if a_run.key == b_run.key:
            #: Said plainly, never 500. Nothing is compared and nothing
            #: is stored: a run compared with itself is the same run.
            self._compare_answer(200, {"same_run": True, "run_key": a_run.key, "answer": SAME_RUN}, form)
            return
        from onetrace_console.store import MISSING_OBJECT, SameFileError

        gone = [(r, self.store.missing(r)) for r in (a_run, b_run)]
        if any(objects for _, objects in gone):
            #: The pair is refused in the fixed words, never a 500; nothing
            #: is compared and nothing stored.
            self._compare_answer(
                409,
                {
                    "error": "; ".join(
                        f"run {r.key[:12]}: " + MISSING_OBJECT.format(objects=", ".join(objects))
                        for r, objects in gone
                        if objects
                    )
                },
                form,
            )
            return
        #: A press counts once: a second press of a pair while it is compared waits for that comparison and is
        #: answered with it; the pair is compared once.
        pair = (a_run.key, b_run.key)
        with _COMPARING_LOCK:
            flight = _COMPARING.get(pair)
            mine = flight is None
            if flight is None:
                flight = _COMPARING[pair] = {"done": threading.Event(), "answer": None}
        if not mine:
            flight["done"].wait(COMPARE_WAIT_SECONDS)
            status, payload = flight["answer"] or (409, {"error": COMPARING_STILL})
            self._compare_answer(status, payload, form)
            return
        try:
            flight["answer"] = self._compare_pair(a_run, b_run, compare, ComparisonError, SameFileError)
        finally:
            with _COMPARING_LOCK:
                _COMPARING.pop(pair, None)
            flight["done"].set()
        status, payload = flight["answer"]
        self._compare_answer(status, payload, form)

    def _handle_compare_check(self, form: dict[str, list[str]]) -> None:
        """`POST /compare/check` (a local console's "Run on this page"): the text diff or localize at the comparison's
        first difference, run over its laid-out runs and kept (`compare_view.run_check`), then back to the page the
        person pressed it on, at the result. The command is the console's own, never one from the request."""
        import subprocess

        from onetrace_console import compare_view
        from onetrace_console.store import StoreError

        key, check = (form.get("key") or [""])[0], (form.get("check") or [""])[0]
        try:
            comparison = self._seen_comparison(key) if re.fullmatch(r"[0-9a-f]{64}", key) else None
        except (StoreError, OSError, ValueError):
            comparison = None
        if comparison is None:
            self._respond(400, b"unknown or malformed comparison key\n", "text/plain")
            return
        try:
            compare_view.run_check(comparison, self.store, check)
        except ValueError as e:
            self._respond(400, f"{e}\n".encode(), "text/plain")
            return
        except subprocess.TimeoutExpired:
            self._respond(503, b"the check did not finish in time; nothing was kept\n", "text/plain")
            return
        #: Back to the page it was pressed on: the comparison's own page, in the person's team's set or the whole
        #: console's, as the request's Referer names it; any other address is not followed.
        referer = urlsplit(self.headers.get("Referer") or "").path
        back = referer if re.fullmatch(rf"(?:/t/[A-Za-z0-9_.-]+)?/diff/{key}\.html", referer) else f"/diff/{key}.html"
        self._respond(303, b"", "text/plain", [("Location", back + "#pair-checks-result")])

    def _compare_pair(self, a_run, b_run, compare, ComparisonError, SameFileError) -> tuple[int, dict]:  # noqa: N803
        """Compare the pair and draw its pages: (the status, the answer)."""
        held = type(self).store.comparison_names()
        try:
            comparison = compare(a_run, b_run, self.store)
        except ComparisonError as e:
            #: Said, never 500: nothing compared and nothing stored.
            return 400, {"error": str(e)}
        except SameFileError as e:
            #: A run the store holds that cannot be laid out here as stored: said, nothing
            #: compared and nothing stored.
            return 400, {"error": f"this console cannot lay out a run of this pair on this host: {e}"}
        if comparison.key not in held:
            #: A comparison made, not one held already, is recorded before its page is drawn; where it cannot be,
            #: it is taken back and nothing drawn.
            from onetrace_console.audit import AuditRefused

            detail = {"a": a_run.key, "b": b_run.key, "team": a_run.team, "build": comparison.sdk_build_digest}
            try:
                self.audit.record(self._principal(), "compare.made", comparison.key, detail)
            except AuditRefused as e:
                type(self).store.withdraw_comparison(comparison.key)
                return 503, {"error": f"Not done: {e}."}
        rel = _render_diff_page(comparison, self.store, self.store_root, public=self.config.public, config=self.config)
        #: Storing a comparison re-renders its candidate's pages, whose
        #: graph is marked from it; nothing else re-renders them but start-up.
        _render_run_pages(b_run, self.store, self.store_root, self.config)
        _render_all_pages(self.store, self.store_root, self.config, only=(a_run.team, b_run.team))
        return 200, {"comparison_key": comparison.key, "pages": {"diff": f"/{rel}"}}

    def _handle_visitor_compare(self) -> None:
        """`POST /compare` on a public console (`visitor_compare`): the two ids read from the body,
        the pair served as built or as cached, or compared under the limiter, and a redirect to its
        page; a refusal or "busy" said on a page of its own. Every header but Content-Length and the
        configured client-address header is out of reach while it runs (`OnlyHeaders`)."""
        from onetrace_console import visitor_compare as vc
        from onetrace_console.frame import fill

        started = time.monotonic()
        allowed = {"content-length"} | (
            {self.config.compare_client_header.lower()} if self.config.compare_client_header else set()
        )
        headers, self.headers = self.headers, OnlyHeaders(self.headers, allowed)  # type: ignore[assignment]  # a stand-in reading only `allowed`, put back after
        pair, outcome = ("", ""), "refused"
        try:
            split = urlsplit(self.path)
            raw = self.headers.get("Content-Length")
            try:
                length = int(raw) if raw is not None else -1
            except ValueError:
                length = -1
            if length < 0 or length > vc.MOST_BODY:
                self.close_connection = True
                raise vc.Refused(
                    f"the body is two run ids, at most {vc.MOST_BODY} bytes, with its Content-Length",
                    413 if length > vc.MOST_BODY else 411,
                )
            body = self._read_body_bounded(length) if length else b""
            if body is None:
                self.close_connection = True
                raise vc.Refused("the body did not arrive in full in time", 408)
            pair = vc.read_pair(split.query, body)
            with self.store.reading():
                a, b = vc.resolve(self.store, *pair)
            root = vc.cache_root(self.config, self.store_root)
            rel = vc.held_page(self.store, root, a, b)
            if rel is not None:
                outcome = "held"
            else:
                address = vc.client_address(self.config, self.headers, self.client_address[0])
                with self.visitor_limiter.slot(address) as got:
                    if not got:
                        outcome = "busy"
                        page = vc.answer_page(vc.BUSY, vc.BUSY_WORDS, back="/")
                        with self.store.reading():
                            from onetrace_console.verdicts import pipeline_of

                            pipeline = pipeline_of(a, self.store)
                        if pipeline is not None:
                            page = vc.answer_page(
                                vc.BUSY,
                                vc.BUSY_WORDS,
                                back=vc.back_to_pair(pipeline.label, a.run_id, b.run_id),
                                back_words=vc.BACK_TO_PAIR,
                            )
                        self._respond(
                            503,
                            fill(page.encode("utf-8"), "busy", onedoor=False, user=None, public=True),
                            "text/html; charset=utf-8",
                            [("Retry-After", "60")],
                        )
                        return
                    rel = vc.held_page(self.store, root, a, b) or vc.make(
                        self.store, root, a, b, timeout=self.config.compare_verb_seconds
                    )
                outcome = "made"
            self._respond(303, b"", "text/plain", [("Location", f"/{rel}")])
        except vc.Refused as e:
            outcome = "refused" if e.status < 500 else "not-kept" if e.status == 504 else "no-cache"
            page = vc.answer_page("Not compared", f"Not compared: {e}.")
            self._respond(
                e.status,
                fill(page.encode("utf-8"), "refused", onedoor=False, user=None, public=True),
                "text/html; charset=utf-8",
            )
        finally:
            self.headers = headers
            log = getattr(self.access_log, "compare", None)
            if log is not None:
                log(a=pair[0], b=pair[1], outcome=outcome, ms=int((time.monotonic() - started) * 1000))

    def _handle_search(self) -> None:
        """The index's search results (`search_page`): the index the store root holds, read and
        never written, and the page drawn as asked. Nothing is run, on either console."""
        from onetrace_console import run_index, search_page
        from onetrace_console.frame import fill

        query = parse_qs(urlsplit(self.path).query)
        q = (query.get("q") or [""])[0][: search_page.MOST_CHARS]
        run_key = (query.get("run") or [""])[0]
        run_key = run_key if re.fullmatch(r"[0-9a-f]{64}", run_key) else ""
        with self.store.reading():
            #: The current team's index, or the all-teams index.
            index = run_index.read(self._seen_root)
            html = search_page.page(
                index,
                q,
                run_key,
                self._seen,
                public=self.config.public,
                found=None if index is not None else run_index.format_of(self._seen_root),
            )
        user = self._signed_in_as()
        self._respond(
            200,
            fill(
                html.encode("utf-8"),
                "search",
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=user,
                csrf=self._session_csrf(),
                public=self.config.public,
                setup_link=not self.config.public,
                store=self.store,
                team=self._team_frame(),
            ),
            "text/html; charset=utf-8",
        )

    def _handle_runs(self) -> None:
        """The Runs page (`runs_page`): the index the store root holds, read and never written, and the page drawn as
        asked, its filters and page from the query. Nothing is run, on either console."""
        from onetrace_console import run_index, runs_page
        from onetrace_console.frame import fill

        query = parse_qs(urlsplit(self.path).query)
        params = {
            name: (query.get(name) or [""])[0][: runs_page.MOST_CHARS]
            for name in ("q", "page", *(p for p, _f, _l in runs_page.FILTERS), *runs_page.PAIR_PARAMS)
        }
        with self.store.reading():
            index = run_index.read(self._seen_root)
            html = runs_page.page(
                index,
                params,
                public=self.config.public,
                found=None if index is not None else run_index.format_of(self._seen_root),
            )
        user = self._signed_in_as()
        served = fill(
            html.encode("utf-8"),
            "runs",
            onedoor=bool(self.config.extensions.get("onedoor")),
            user=user,
            csrf=self._session_csrf(),
            public=self.config.public,
            setup_link=not self.config.public,
            store=self.store,
            team=self._team_frame(),
        )
        if not self.config.public:
            #: The page's own forms (its Compare picker) carry the session's token, as every served page's do.
            from onetrace_console.frame import fill_csrf

            served = fill_csrf(served, self._session_csrf())
        self._respond(200, served, "text/html; charset=utf-8")

    def _handle_bisect(self) -> None:
        """A pipeline's first run to leave the reference after a time (`bisect_page`): what the store
        keeps, read and never written, and the page drawn as asked. Nothing is run, on either console."""
        from onetrace_console import bisect_page
        from onetrace_console.frame import fill

        query = parse_qs(urlsplit(self.path).query)
        label = (query.get("p") or [""])[0]
        after = (query.get("after") or [""])[0][: bisect_page.MOST_CHARS]
        if not re.fullmatch(r"P[0-9]{1,6}", label):
            self._respond(404, b"no such pipeline\n", "text/plain")
            return
        with self.store.reading(), _rendering(self.config):
            #: `P<n>` within the current team: its P1 is the team's P1.
            html = bisect_page.page_for(
                self._seen, label, after, generated_at=datetime.now(UTC).isoformat(timespec="seconds")
            )
        if html is None:
            self._respond(404, b"no such pipeline\n", "text/plain")
            return
        user = self._signed_in_as()
        self._respond(
            200,
            fill(
                html.encode("utf-8"),
                "bisect",
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=user,
                csrf=self._session_csrf(),
                public=self.config.public,
                setup_link=not self.config.public,
                store=self.store,
                team=self._team_frame(),
            ),
            "text/html; charset=utf-8",
        )

    def _neighbours(self) -> bool:
        """Neighbours by input exist on this console: the extra installed, the console not public."""
        from onetrace_console import neighbours

        return neighbours.exists(public=self.config.public)

    def _session_csrf(self) -> str | None:
        session = self._current_session()
        return session.csrf_token if session is not None else None

    def _handle_neighbours_setup(self, said: str = "", status: int = 200) -> None:
        """The setup page, drawn as it is asked for: the setting, and the forms that turn it on or off."""
        from onetrace_console.frame import fill
        from onetrace_console.neighbours.pages import PATH, document

        query = parse_qs(urlsplit(self.path).query) if status == 200 else {}
        if not said and (query.get("said") or [""])[0] == "off":
            from onetrace_console.neighbours.pages import TURNED_OFF

            said = TURNED_OFF
        html = document(self.store, query=query, said=said, csrf=self._session_csrf())
        user = self._signed_in_as()
        self._respond(
            status,
            fill(
                html.encode("utf-8"),
                PATH,
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=user,
                csrf=self._session_csrf(),
                setup_link=True,
                store=self.store,
            ),
            "text/html; charset=utf-8",
        )

    def _tokenizers_page(self, token_upload) -> str:
        """The Tokenizers page's body: the steps that ask for one (with this console's tokenizers), the kept ones."""
        named = tuple((t["folder"], tuple(t["files"])) for t in self.config.tokenizers or ()) + _kept_tokenizers(
            self.config
        )
        #: The runs listed are those of the store this request reads (`_scope`): with teams, the viewer's team's view,
        #: as the Runs and Search pages read. The tokenizers kept are the whole console's.
        seen = self._seen
        with self.store.reading():
            return token_upload.page_body(seen, Path(self.store.root), named=named)

    def _setup_page(self, status: int, page: str, rel: str = "explain/setup", user: str | None = None) -> None:
        """The Set up Explain page, framed as every page is, its form's CSRF slot holding the session's
        token."""
        from onetrace_console.frame import fill, fill_csrf

        self._respond(
            status,
            fill_csrf(
                fill(
                    page.encode("utf-8"),
                    rel,
                    onedoor=bool(self.config.extensions.get("onedoor")),
                    user=user,
                    csrf=self._session_csrf(),
                    setup_link=True,
                    store=self.store,
                ),
                self._session_csrf(),
            ),
            "text/html; charset=utf-8",
        )

    def _handle_explain_setup(self, body: bytes) -> None:
        """Save, from the setup page's form: the page again, saying what was written or why nothing was."""
        from onetrace_console import explain_setup
        from onetrace_console.signin import parse_signin_form

        form = parse_signin_form(body) if body else {}
        user = self._signed_in_as()
        if form.get("action") == "always-stop":
            #: "Always stop before sending": kept for this store; the checkbox unticked, off.
            from onetrace_console import explain

            on = form.get("always_stop") == "yes"
            if not self._audited("setting.changed", "explain", {"setting": "always stop before sending", "on": on}):
                return
            explain.set_always_stop(self.store, on)
            said = explain.ALWAYS_STOP_ON if on else explain.ALWAYS_STOP_OFF
            self._setup_page(200, explain_setup.page(self.store, said=said, at=explain_setup.STOP_SECTION), user=user)
            return
        if form.get("action") == "remove":
            #: Remove asks first: its confirmation page, and nothing changed.
            self._setup_page(200, explain_setup.confirm_page(self.store), user=user)
            return
        if form.get("action") == "remove-confirmed":
            taken = explain_setup.take_confirm(form.get("confirm", ""))
            if taken == "used":
                #: A press counts once: a second confirm finds the key removed by the first, and says so.
                self._setup_page(
                    200,
                    explain_setup.page(self.store, said=explain_setup.REMOVED_ALREADY, at=explain_setup.FORM_SECTION),
                    user=user,
                )
                return
            if taken != "fresh":
                self._respond(403, b"missing or mismatched confirmation token\n", "text/plain")
                return
        changed = explain_setup.change_of(form)
        if changed is not None and not self._audited("setting.changed", "explain", changed):
            return
        status, said, written = explain_setup.save(form)
        #: Said in the section the press came from, where the page then opens.
        self._setup_page(
            status,
            explain_setup.page(self.store, said=said, written=written, at=explain_setup.FORM_SECTION),
            user=user,
        )

    def _send_done(self, comparison, store, root, *, public: bool, config):
        """What a Send does when it ends: the comparison's page drawn again, and `explain.completed`, the
        explanation records the send made and their chain heads, which do not exist when it starts; none where it made
        none. The send has happened by then, so an entry that cannot be appended is noted, never a refusal."""
        from onetrace_console import explain
        from onetrace_console.audit import AuditRefused

        before = explain.record_heads(store, comparison.key)
        audit, actor = self.audit, self._principal()

        def done() -> None:
            _render_diff_page(comparison, store, root, public=public, config=config)
            made = [
                {"record": name, "chain_head": head}
                for name, head in explain.record_heads(store, comparison.key).items()
                if name not in before
            ]
            try:
                audit.record(actor, "explain.completed", comparison.key, {"records": made})
            except AuditRefused:
                pass  # noted by the log, and said on the error stream (`Audit.record`)

        return done

    def _handle_forwarding(self, body: bytes) -> None:
        """One press on the forwarding page: recorded in the audit log first (the destination and the fields, never a
        value), then made; the page again, saying what was done or why nothing was. The test trace changes nothing
        and is not recorded."""
        from onetrace_console import forward_pages
        from onetrace_console.signin import parse_signin_form

        form = parse_signin_form(body) if body else {}
        planned = forward_pages.plan(self.store_root, form)
        if planned.status:
            self._setup_page(
                planned.status,
                forward_pages.page(self.store_root, planned.said, planned),
                forward_pages.REL,
                self._signed_in_as(),
            )
            return
        if form.get("action") != "test" and not self._audited(
            "forwarding.changed", planned.destination, {"action": form.get("action", ""), "fields": planned.fields}
        ):
            return
        done = forward_pages.apply(self.store_root, form)
        self._setup_page(
            done.status,
            forward_pages.page(self.store_root, done.said, done if done.status >= 400 else None),
            forward_pages.REL,
            self._signed_in_as(),
        )

    def _handle_neighbours(self, path: str, body: bytes) -> None:
        """Turn neighbours on (after the confirmation names the embedder; the local model's files fetched
        and checked) or off; then embed what is kept, and draw the pages again."""
        from onetrace_console.neighbours import embedder, settings
        from onetrace_console.signin import parse_signin_form

        form = parse_signin_form(body) if body else {}
        if path == "/neighbours/on":
            from onetrace_console.neighbours import fetching
            from onetrace_console.neighbours.pages import ALREADY

            if fetching.running(self.store):
                #: One fetch at a time: a second press is answered, and starts nothing.
                self._handle_neighbours_setup(said=ALREADY.format(model=fetching.now(self.store).model), status=409)  # type: ignore[union-attr]  # running(): a fetch is under way
                return
            try:
                chosen = settings.choose(form)
                if chosen["kind"] == "local":
                    #: The local model's files are fetched in the background; the setup page shows
                    #: the count of files checked and refreshes itself until the setting is written.
                    store, root, config = self.store, self.store_root, self.config

                    def after() -> None:
                        _neighbours_refresh(store, config)
                        _render_neighbour_pages(store, root, config)

                    if not self._audited(
                        "setting.changed",
                        "neighbours",
                        {"setting": "neighbours", "on": True, "embedder": chosen.get("model", "")},
                    ):
                        return
                    fetching.forget(self.store)
                    fetching.start(
                        self.store, chosen, who=self._principal(), confirmed=form.get("confirmed", ""), after=after
                    )
                    self._respond(303, b"", "text/plain", [("Location", "/neighbours/setup")])
                    return
                if not self._audited(
                    "setting.changed",
                    "neighbours",
                    {"setting": "neighbours", "on": True, "embedder": chosen.get("model", "")},
                ):
                    return
                settings.turn_on(self.store, chosen, who=self._principal(), confirmed=form.get("confirmed", ""))
            except fetching.AlreadyFetching as e:
                self._handle_neighbours_setup(said=ALREADY.format(model=e.args[0]), status=409)
                return
            except embedder.Refused as e:
                self._handle_neighbours_setup(said=f"Not turned on: {e}", status=400)
                return
            except OSError as e:
                from onetrace_console.oserror import said

                self._handle_neighbours_setup(said=f"Not turned on: {said(e)}", status=400)
                return
        else:
            if settings.read(self.store) is not None and not self._audited(
                "setting.changed", "neighbours", {"setting": "neighbours", "on": False}
            ):
                return
            settings.turn_off(self.store)
        _neighbours_refresh(self.store, self.config)
        _render_neighbour_pages(self.store, self.store_root, self.config)
        #: Turned off: the page says so, in its section; turned on, it shows the fetch or the setting.
        where = "/neighbours/setup?said=off" if path == "/neighbours/off" else "/neighbours/setup"
        self._respond(303, b"", "text/plain", [("Location", where)])

    def _handle_benchmark(self, query: dict[str, list[str]], body: bytes) -> None:
        """ "Mark as benchmark" (`mark=yes`, with an optional note in the JSON body) or its undo
        (`mark=no`) on a local console: the mark in the store, then the pages drawn again."""
        from onetrace_console import benchmarks
        from onetrace_console.store import StoreError

        key = (query.get("run") or [""])[0]
        which = (query.get("mark") or [""])[0]
        try:
            run = self._seen_run(key) if re.fullmatch(r"[0-9a-f]{64}", key) else None
        except StoreError:
            run = None
        if run is None:
            self._respond_json(400, {"error": "unknown or malformed run key"})
            return
        if which not in ("yes", "no"):
            self._respond_json(400, {"error": "mark takes yes or no"})
            return
        note = ""
        if which == "yes" and body:
            from onetrace_console.bounded_json import load_json_bounded

            try:
                got = load_json_bounded(body.decode("utf-8"), "the benchmark's note")
                said = got.get("note", "") if isinstance(got, dict) else None
            except (UnicodeDecodeError, ValueError, RecursionError):
                said = None
            if not isinstance(said, str):
                self._respond_json(400, {"error": 'the body is {"note": "<text>"} or empty'})
                return
            note = said
        undo = _undo_of(benchmarks._path(self.store, run.key), self.store)
        try:
            if which == "yes":
                benchmarks.mark(self.store, run, who=self._principal(), note=note)
            else:
                benchmarks.unmark(self.store, run.key)
        except benchmarks.MarkError as e:
            self._respond_json(400, {"error": str(e)})
            return
        event = "benchmark.marked" if which == "yes" else "benchmark.unmarked"
        detail = {"team": run.team, "note": bool(note)} if which == "yes" else {}
        if not self._audited(event, run.key, detail, undo=undo):
            return
        #: The mark changes which run "What changed?" takes for the pipeline's later runs, and the
        #: badge wherever the run is listed: every page of the pipeline's runs is drawn again, and only
        #: the store's pages a mark changes (`render_all(marked=...)`), then the run index.
        from onetrace_console.overview import declared_list

        same = [other for other in self.store.runs() if declared_list(other) == declared_list(run)]
        for other in same:
            _render_run_pages(other, self.store, self.store_root, self.config)
        #: A comparison page shows each run against its pipeline's reference run, which a mark can make: each
        #: comparison of the pipeline's runs is drawn again.
        keys = {r.key for r in same}
        for c in self.store.comparisons():
            if c.run_a in keys or c.run_b in keys:
                _render_diff_page(c, self.store, self.store_root, public=self.config.public, config=self.config)
        _render_marked_pages(run, same, self.store, self.store_root, self.config)
        self._respond_json(200, {"run_key": run.key, "benchmark": which == "yes"})

    def _handle_expectations(self, query: dict[str, list[str]], body: bytes) -> None:
        """ "Check against an expectations file" on a local console (`expectations_after`): the run
        checked against the file named in the JSON body `{"path": ...}`, what the check said kept in
        the store, then the run's pages drawn again."""
        from onetrace_console import expectations_after
        from onetrace_console.bounded_json import load_json_bounded
        from onetrace_console.store import StoreError

        key = (query.get("run") or [""])[0]
        try:
            run = self._seen_run(key) if re.fullmatch(r"[0-9a-f]{64}", key) else None
        except StoreError:
            run = None
        if run is None:
            self._respond_json(400, {"error": "unknown or malformed run key"})
            return
        try:
            got = load_json_bounded(body.decode("utf-8"), "the named file") if body else None
        except (UnicodeDecodeError, ValueError, RecursionError):
            got = None
        named = got.get("path") if isinstance(got, dict) else None
        if not isinstance(named, str):
            self._respond_json(400, {"error": 'the body is {"path": "<the file\'s path on this machine>"}'})
            return
        kept = self.store.kept_path(expectations_after.FOLDER, run.key, f"{run.key}.json")
        undo = _undo_of(kept, self.store) if kept is not None else (lambda: None)
        try:
            entry = expectations_after.check(self.store, run, named.strip())
        except expectations_after.ExpectationsError as e:
            self._respond_json(400, {"error": str(e)})
            return
        #: The seal of what the check said, never the file's path or its rows.
        detail = {"seal": entry["seal"], "rows": len(entry["rows"])}
        if not self._audited("expectations.checked", run.key, detail, undo=undo):
            return
        _render_run_pages(run, self.store, self.store_root, self.config)
        self._respond_json(
            200, {"run_key": run.key, "file": entry["file"], "seal": entry["seal"], "rows": len(entry["rows"])}
        )

    def _handle_load_not_closed(self, query: dict[str, list[str]]) -> None:
        """The Runs page's "Load as not closed": the watched folder's run folder named, listed with an
        empty `.lock` (`run_lock`), taken in without it; its pages drawn. Anything else is refused."""
        from onetrace_console import closing, run_lock

        name = (query.get("folder") or [""])[0]
        if not name or run_lock.LISTED.get(name, ("", ""))[1] != "empty":
            self._respond_json(400, {"error": "no run folder of that name is listed as locked"})
            return
        if not self.watcher.take_in_not_closed(name):
            self._respond_json(409, {"error": f"{name} was not loaded; the console's log says why"})
            return
        import json as _json

        try:
            closed = closing.said(_json.dumps(closing.ending_of(self.watcher.folder / name)))
        except Exception:  # noqa: BLE001 - the run is stored; only these words could not be read
            closed = closing.NOT_CLOSED_UNREAD
        self._respond_json(200, {"folder": name, "closed": closed})

    def _handle_model_tokenizers(self, path: str, query: dict[str, list[str]], body: bytes) -> None:
        """A tokenizer picked on a model step's page, kept only where its files hash to the digest named
        (`token_upload.keep`), or one kept removed; then every page drawn again, so each model step reads
        with what is kept now."""
        from onetrace_console import token_upload

        digest = (query.get("digest") or [""])[0]
        try:
            if path == "/model-tokenizers/remove":
                held = {k.get("digest") for k in token_upload.kept(Path(self.store.root))}
                if digest in held and not self._audited("tokenizer.removed", digest):
                    return
                if not token_upload.remove(Path(self.store.root), digest):
                    self._respond_json(400, {"error": f"this console keeps no tokenizer {digest}"})
                    return
                entry = {"digest": digest, "removed": True}
            else:
                name = (query.get("name") or [""])[0]
                held = {k.get("digest") for k in token_upload.kept(Path(self.store.root))}
                entry = token_upload.keep(Path(self.store.root), digest, body, name)
                if digest not in held and not self._audited(
                    "setting.changed",
                    "tokenizer",
                    {"setting": "tokenizer kept", "digest": digest},
                    undo=lambda: token_upload.remove(Path(self.store.root), digest),
                ):
                    return
        except token_upload.UploadError as e:
            self._respond_json(400, {"error": str(e)})
            return
        for run in self.store.runs():
            _render_run_pages(run, self.store, self.store_root, self.config)
        self._respond_json(
            200, {"digest": entry["digest"], "files": entry.get("files", []), "removed": bool(entry.get("removed"))}
        )

    def _handle_explain(self, path: str, query: dict[str, list[str]]) -> None:
        """One press on a comparison's explanation panel (`explain`): Explain, Send (`send=yes`,
        the only press that passes `--yes`), Show the packet, or Run a check the explanation names
        (`e`, `i`), rebuilt from the explanation and never from the request. The page is drawn
        again after each; the command's own exit and lines are kept, never read as a verdict."""
        from onetrace_console import explain
        from onetrace_console.store import StoreError

        key = (query.get("c") or [""])[0]
        try:
            comparison = self._seen_comparison(key) if key else None
        except (StoreError, OSError, ValueError):
            comparison = None
        if comparison is None:
            self._respond_json(400, {"error": "unknown or malformed comparison key"})
            return
        if explain.command() is None:
            self._respond_json(400, {"error": "onetrace-explain is not installed with this console"})
            return
        store, root, public, config = self.store, self.store_root, self.config.public, self.config
        sending = path == "/explain" and (query.get("send") or [""])[0] == "yes"
        if sending and explain._lock(comparison.key).locked():
            #: A press counts once: a second Send while this comparison's send runs is answered with that run,
            #: and sends nothing.
            self._respond_json(
                202,
                {
                    "comparison_key": comparison.key,
                    "started": False,
                    "running": True,
                    "state": f"/explain/state?c={comparison.key}",
                },
            )
            return
        try:
            if explain._lock(comparison.key).locked():
                raise explain.Busy(explain.BUSY)
            if path == "/explain" and (query.get("send") or [""])[0] == "yes":
                #: Send, the only press that sends: it starts the work and answers at once; the page is
                #: drawn again when it ends. Recorded before anything leaves.
                if not self._audited("explain.sent", comparison.key, _sent_detail(store, comparison.key)):
                    return
                explain.start(
                    comparison,
                    store,
                    send=True,
                    done=self._send_done(comparison, store, root, public=public, config=config),
                )
                self._respond_json(
                    202,
                    {"comparison_key": comparison.key, "started": True, "state": f"/explain/state?c={comparison.key}"},
                )
                return
            elif path == "/explain":
                #: Explain prepares the packet; then, in the same press, sends it where nothing in it needs a
                #: new consent (`explain.sends_at_once`), answering as Send does.
                got = explain.prepare(comparison, self.store)
                if got.get("exit") == "0" and explain.sends_at_once(store, comparison.key):
                    if not self._audited("explain.sent", comparison.key, _sent_detail(store, comparison.key)):
                        return
                    explain.start(
                        comparison,
                        store,
                        send=True,
                        done=self._send_done(comparison, store, root, public=public, config=config),
                    )
                    self._respond_json(
                        202,
                        {
                            "comparison_key": comparison.key,
                            "started": True,
                            "state": f"/explain/state?c={comparison.key}",
                        },
                    )
                    return
            elif path == "/explain/cancel":
                got = explain.cancel(comparison, self.store)
            elif path == "/explain/text":
                #: The text checkbox: the choice kept for this comparison only; nothing run or sent.
                explain.set_include_text(self.store, comparison.key, (query.get("on") or [""])[0] == "yes")
                got = {"exit": ""}
            elif path == "/explain/packet":
                got = explain.packet(comparison, self.store)
            else:
                index = (query.get("i") or [""])[0]
                if not index.isdigit():
                    raise ValueError("no such check")
                got = explain.run_check(self.store, comparison.key, (query.get("e") or [""])[0], int(index))
        except explain.Busy as e:
            self._respond_json(409, {"error": str(e)})
            return
        except ValueError as e:
            self._respond_json(400, {"error": str(e)})
            return
        except (OSError, subprocess.SubprocessError) as e:
            #: Its reason, never its whole text: an OSError's carries a path of this machine.
            self._respond_json(
                500, {"error": f"the command could not be run: {getattr(e, 'strerror', None) or type(e).__name__}"}
            )
            return
        rel = _render_diff_page(comparison, self.store, self.store_root, public=self.config.public, config=self.config)
        self._respond_json(
            200, {"comparison_key": comparison.key, "exit": got.get("exit", ""), "pages": {"diff": f"/{rel}"}}
        )

    def _handle_text_diff_more(self, query: dict[str, list[str]]) -> None:
        """The comparison's text diff again at the console's one larger
        limit, stored as a run of its own; the original runs and every verdict unchanged. The
        limit is never taken from the request: a `max_lines` other than it is refused."""
        from onetrace_console.compare import TEXT_DIFF_MORE_LINES, ComparisonError, show_more

        asked = (query.get("max_lines") or [""])[0]
        if asked and asked != str(TEXT_DIFF_MORE_LINES):
            self._respond_json(400, {"error": f"the larger limit is fixed at {TEXT_DIFF_MORE_LINES} lines per output"})
            return
        key = (query.get("c") or [""])[0]
        from onetrace_console.store import StoreError

        try:
            comparison = self._seen_comparison(key) if key else None
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
        rel = _render_diff_page(comparison, self.store, self.store_root, public=self.config.public, config=self.config)
        self._respond_json(
            200, {"comparison_key": comparison.key, "max_lines": TEXT_DIFF_MORE_LINES, "pages": {"diff": f"/{rel}"}}
        )

    # -------------------------------------------------------------- helpers
    def _respond(
        self, status: int, body: bytes, content_type: str, extra_headers: list[tuple[str, str]] | None = None
    ) -> None:
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
            self.access_log.append(
                principal=self._principal(), method=self.command, path=urlsplit(self.path).path, status=status
            )
        except AccessLogExhausted as e:
            status = 500
            from onetrace_console.oserror import shown

            body = (shown(f"the access log could not be written: {e}") + "\n").encode("utf-8")
            content_type = "text/plain"
            extra_headers = None
        config = getattr(type(self), "config", None)
        if status in _error_pages().PAGES and content_type.startswith("text/plain"):
            #: A browser's request for a page meets an error as a page in the frame (`error_pages`); every other
            #: client gets the line as it was.
            framed = self._framed_error(status, body)
            if framed is not None:
                body, content_type = framed, "text/html; charset=utf-8"
        if config is not None and config.public and content_type.startswith("text/html"):
            #: Search engines index a public console's Overview only (`search_engines`).
            from onetrace_console.search_engines import for_search

            body = for_search(body, urlsplit(self.path).path)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra_headers or ():
            self.send_header(name, value)
        if self.local_port is not None and not self.config.public:
            #: Local mode has no sign-in, so a page from another site must not be able to
            #: frame a local page or have one sniffed into another type. (A public console sends
            #: these and more on every response, from `end_headers`.)
            for name, value in (
                ("X-Frame-Options", "DENY"),
                ("Cross-Origin-Resource-Policy", "same-origin"),
                ("X-Content-Type-Options", "nosniff"),
            ):
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

    def send_response(self, code: int, message: str | None = None) -> None:
        #: Once a status line is on its way, an error is only logged (`_unhandled`).
        self._answer_started = True
        super().send_response(code, message)

    @contextlib.contextmanager
    def _answering(self):
        """Around a request's handling: an error nothing caught is answered (`_unhandled`). A broken pipe or a reset
        connection is the client gone, not the console's error: it reaches the server's own handling, as before."""
        self._answer_started = False
        try:
            yield
        except (BrokenPipeError, ConnectionResetError):
            raise
        except Exception:  # noqa: BLE001 - answered and logged, never dropped
            self._unhandled()

    def _unhandled(self) -> None:
        """The error being handled, which nothing caught: its type, message and traceback go to the console's own log
        under a short reference, with the request's method and path (never its query); the client gets the 500 line
        with that reference, which a browser meets as the framed page (`error_pages`), and never the exception's
        words, which can name a path on this machine. A public console logs one JSON line, as `handle_error` does.
        If the answer had already started, nothing more is sent and the connection is closed."""
        import secrets

        ref = secrets.token_hex(4)
        path = urlsplit(self.path).path
        config = getattr(type(self), "config", None)
        if config is not None and config.public:
            error = sys.exc_info()[1]
            line = json.dumps(
                {
                    "at": _now(),
                    "event": "error",
                    "reference": ref,
                    "method": self.command,
                    "path": path,
                    "exception": type(error).__name__ if error is not None else "unknown",
                    "traceback": traceback.format_exc(),
                },
                ensure_ascii=False,
            )
            sys.stderr.write(line + "\n")
            sys.stderr.flush()
        else:
            print(f"error {ref}: answering {self.command} {path}", file=sys.stderr)
            traceback.print_exc()
            sys.stderr.flush()
        if getattr(self, "_answer_started", False):
            self.close_connection = True
            return
        self._respond(500, SERVER_ERROR.format(ref=ref).encode(), "text/plain")

    def _framed_error(self, status: int, said: bytes) -> bytes | None:
        """`said`, an error's plain line, as a page in the frame where a browser asked for a page; None where it
        did not, or where the page could not be drawn (the line is then sent as it is)."""
        from onetrace_console import error_pages
        from onetrace_console.frame import fill, fill_csrf

        headers = getattr(self, "headers", None)
        if headers is None or not error_pages.wants_page(urlsplit(self.path).path, headers.get("Accept")):
            return None
        try:
            public = bool(self.config.public)
            csrf = None if public else self._session_csrf()
            user = None if public else self._signed_in_as()
            page = error_pages.document(status, said.decode("utf-8", errors="replace")).encode("utf-8")
            filled = fill(
                page,
                "error.html",
                onedoor=bool(self.config.extensions.get("onedoor")),
                user=user,
                public=public,
                #: The settings menu says what the console has configured: with sign-in on, for a signed-in person
                #: only, as the sign-in page draws none for a caller with no session.
                setup_link=not public and (user is not None or not self.config.sign_in.get("enabled")),
                store=self.store,
                csrf=csrf,
            )
            return fill_csrf(filled, csrf)
        except Exception:  # noqa: BLE001 - the plain line is sent instead, as before
            return None

    def _respond_json(self, status: int, obj: dict, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self._respond(status, json.dumps(obj, indent=1).encode("utf-8"), "application/json", extra_headers)


#: `%2e` (a dot) or `%5c` (a backslash), in either case: the encoded forms of what a path
#: may not contain.
_ENCODED_DOT_OR_BACKSLASH = re.compile(r"%(2e|5c)", re.IGNORECASE)

#: A page of a run, by its key: what a run's old address, after `run assign`, is read by.
_MOVED_RUN_PATH = re.compile(r"runs/([0-9a-f]{64})/(.*)")
#: The run's own record: `runs/<key>/record.tar`, the key a sha256 run key.
_RECORD_PATH = re.compile(r"runs/([0-9a-f]{64})/record\.tar")
#: `t/<team>/<page>`: a team's name (`store.TEAM_NAME`), then the page; `t/<team>/` alone is the team's Overview.
_TEAM_PREFIX = re.compile(r"t/([a-z][a-z0-9-]{0,62})/(.*)", re.S)

#: Local mode's one address.
LOCAL_HOST = "127.0.0.1"


#: A sign-in refused by one of the account's windows: the page's words. None of them says whether
#: the name has an account, and each is said the same for a name with none.
SIGNIN_LIMIT_WORDS = {
    "ceiling": (
        "too many sign-in attempts for this account from new browsers; sign in from a browser "
        "you have used before, or ask an admin"
    ),
    "pair": "too many sign-in attempts for this account from this address; try again later",
    "device": "too many wrong passwords for this account from this browser; try again later",
}


def signin_limiters(config: Config) -> dict:
    """The sign-in limiters the configuration's `sign_in` settings make, by Handler attribute."""
    from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter

    s = config.sign_in
    return {
        "rate_limit_per_client": RateLimiter(
            max_attempts=s["rate_limit_max_attempts_per_client"], window_seconds=s["rate_limit_window_seconds"]
        ),
        "rate_limit_per_device": RateLimiter(
            max_attempts=s["rate_limit_max_attempts_per_device"], window_seconds=s["rate_limit_pair_window_seconds"]
        ),
        "rate_limit_per_pair": RateLimiter(
            max_attempts=s["rate_limit_max_attempts_per_pair"], window_seconds=s["rate_limit_pair_window_seconds"]
        ),
        "rate_limit_per_account": RateLimiter(
            max_attempts=s["rate_limit_max_attempts_per_account"], window_seconds=s["rate_limit_account_window_seconds"]
        ),
        "rate_limit_concurrent_hashes": ConcurrencyLimiter(max_concurrent=s["rate_limit_max_concurrent_hashes"]),
    }


def _build_identity() -> str:
    """The SDK build the console checks and compares with (`compare.sdk_build_digest`), for the audit log's entries:
    said as unidentified where it cannot be told, never guessed."""
    from onetrace_console.compare import sdk_build_digest

    try:
        return sdk_build_digest()
    except Exception:  # noqa: BLE001 - an identity it cannot tell is said as that
        return "unidentified"


def _undo_of(path: Path, store=None):
    """What puts `path` back as it is now, file or none, and has `store` read it again: an action's undo where its
    entry cannot be appended."""
    from onetrace_console.store import _atomic_write

    before = path.read_bytes() if path.is_file() else None

    def undo() -> None:
        if before is None:
            path.unlink(missing_ok=True)
        else:
            _atomic_write(path, before)
        if store is not None:
            store._forget()

    return undo


def _sent_detail(store, key: str) -> dict:
    """`explain.sent`'s detail: the address it goes to, the kinds of item that address is sent, and whether
    the texts go. The packet is never kept. Recorded before the send, so the explanation's chain head is the
    explanation record's own, not the entry's."""
    from onetrace_console import explain

    where = explain.endpoint(explain.model_config())
    return {
        "endpoint": where,
        "kinds": sorted(explain.sent_kinds(where)),
        "include_text": explain.include_text(store, key),
    }


def session_store_for(config: Config, accounts, *, store_root: Path | None = None, on_ended=None, on_end=None):
    """The console's sessions, as its configuration bounds them: the idle and absolute timeouts,
    `max_sessions_per_account`, and the end time `admin sessions end` writes (`session_ends`, under `store_root`;
    0.8.0's, beside the accounts, is read too). `on_ended` is told how many sessions an end time ended."""
    from onetrace_console.session_ends import DIRNAME, EndTimes
    from onetrace_console.sessions import SessionStore

    #: The accounts folder is `<store_root>/accounts/`, so its parent where no root is given.
    times = EndTimes((store_root if store_root is not None else Path(accounts.root).parent) / DIRNAME)

    def ended(principal: str) -> int | None:
        found = [accounts.sessions_ended_at(principal), times.read(principal)]
        return max((t for t in found if t is not None), default=None)

    return SessionStore(
        idle_timeout_seconds=config.sign_in["session_idle_timeout_seconds"],
        absolute_timeout_seconds=config.sign_in["session_absolute_timeout_seconds"],
        max_per_account=config.sign_in.get("max_sessions_per_account", 3),
        ended=ended,
        on_ended=on_ended,
        on_end=on_end,
    )


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
    #: spun inside the access log's own temp-file loop.
    written = store_root / f".write-test-{os.getpid()}"
    written.write_bytes(b"")
    written.unlink()
    #: `Store(root)` makes `root/objects` and `root/runs` itself, so this names the STORE's
    #: own root as a sibling of `pages/` under the one mounted volume -- not nested in it.
    store = Store(store_root / "store")
    (store_root / PAGES_DIRNAME).mkdir(exist_ok=True)
    return store, AccessLog(store_root / "access_log", max_segment_bytes=config.access_log_max_segment_bytes)


def _public_store(store_root: Path):
    """A public console's store, read as it was built -- it may be read-only on disk -- and its
    access log, on standard output. Nothing is made or written."""
    from onetrace_console.public import StdoutAccessLog

    return Store(store_root / "store"), StdoutAccessLog()


def start_forwarding(store_root: Path, store: Store, config: Config):
    """Trace forwarding's sender, started; None on a public console, which forwards nothing."""
    if config.public:
        return None
    from onetrace_console import forwarding

    sender = forwarding.Forwarder(store_root, store)
    sender.start()
    return sender


def main(
    argv: list[str] | None = None,
    *,
    overrides: dict | None = None,
    prepare=None,
    open_browser: bool = False,
    announce=None,
    watch=None,
) -> int:
    """`ONETRACE_CONSOLE_CONFIG` names the console's configuration file. Host, port, the store's root, and every
    upload-hardening limit all come from that one file; the other variables the console reads, each for one thing,
    are the operator guide's ("Configuration"). `onetrace_console.config.load_from_env()` reads the file.

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
        print(
            f"onetrace-console serve takes no arguments (given: {' '.join(argv)}). Host, "
            f"port and everything else come from the configuration file named in "
            f"{ENV_VAR}; with none named, it runs in local mode.",
            file=sys.stderr,
        )
        return 2
    #: Anything this console prints may carry a path or a name the console's own stream cannot
    #: encode -- Windows' piped stdout is cp1252.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    named = os.environ.get(ENV_VAR)
    if named is not None and not named.strip():
        print(
            f"refusing to start: {ENV_VAR} is set but blank. Name a configuration file, "
            f"or leave the variable out entirely for local mode.",
            file=sys.stderr,
        )
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
        print(
            "refusing to start: extensions.onedoor is true, and the authorization extension "
            "is not part of this release. Remove it, or set it to false.\nfix: remove "
            "extensions.onedoor from the configuration file, or set it to false.",
            file=sys.stderr,
        )
        return 1

    store_root = Path(config.store_root).resolve()
    if config.public:
        from onetrace_console.public import start_refusal

        refused = start_refusal(config, store_root)
        if refused is None and prepare is not None:
            from onetrace_console.public import Refusal

            refused = Refusal(
                "public is true, and a public console loads nothing at start.",
                "build the store first with onetrace-console demo --public --build <folder>.",
            )
        if refused is not None:
            print(f"refusing to start: {refused.message}\nfix: {refused.fix}", file=sys.stderr)
            return 1
        #: The banner speaks for the store its build record names: the demo's, or the capture store's.
        from onetrace_console.public import recorded_builder, speaks_for

        speaks_for(recorded_builder(Path(config.trust_file).parent))  # type: ignore[arg-type]  # start_refusal above refuses a public console with no trust_file
        #: The demo's own example inputs, which its build record (checked above) vouches for, are
        #: the one kind of input from outside a pipeline this console may hand out.
        from onetrace_console.demo_store import serve_examples

        #: `start_refusal` has just checked that record, clean: it is not read a second time.
        serve_examples(Path(config.trust_file).parent, vouched=True)  # type: ignore[arg-type]  # start_refusal above refuses a public console with no trust_file

    #: Checked before anything else touches the network: a plain-HTTP, non-loopback
    #: listener with sign-in enabled refuses to start outright -- in words, with its fix,
    #: never a traceback (it was found raising one in the container).
    from onetrace_console.signin import InsecureListenerError

    try:
        refuse_if_insecure(config)
    except InsecureListenerError as e:
        fix = (
            "set sign_in.insecure_cookie_for_local_dev to false, or bind host to loopback."
            if config.sign_in.get("insecure_cookie_for_local_dev")
            else "configure both sign_in.tls_cert_path and sign_in.tls_key_path, or bind host to "
            "loopback behind your own TLS-terminating proxy."
        )
        print(f"{e}\nfix: {fix}", file=sys.stderr)
        return 1

    if local and any((store_root / ACCOUNTS_DIRNAME).glob("*.json")):
        #: A store with accounts was set up with sign-in; local mode would serve it open.
        #: Accounts are `*.json`, as `AccountStore` writes them -- a `.gitkeep` is not one.
        print(
            f"refusing to start in local mode: the store at {store_root} was set up with "
            f"sign-in (it holds accounts). Name its configuration file in {ENV_VAR}.",
            file=sys.stderr,
        )
        return 1
    try:
        store, access_log = _public_store(store_root) if config.public else _writable_store(store_root, config)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as e:
        #: ValueError, KeyError, TypeError: an access_log/HEAD.json that is not the access
        #: log's own ended in a traceback; RecursionError, one nested
        #: past what JSON reads -- `AccessLog` now says so as a ValueError itself.
        #: Each once ended the start in a traceback: a store_root that is
        #: a file, under one, on no such drive or not writable, or whose store, pages or
        #: access_log is a file, ended in a traceback.
        from onetrace_console.oserror import shown

        print(
            shown(
                f"refusing to start: cannot use store_root {store_root}: "
                f"{getattr(e, 'strerror', None) or f'{type(e).__name__}: {e}'}"
                f"{f' ({getattr(e, "filename", None)})' if getattr(e, 'filename', None) else ''}"
            )
            + "\nfix: point store_root at a folder this console can create and write, "
            "holding nothing but what this console put there.",
            file=sys.stderr,
        )
        return 1

    Handler.store_root = store_root
    Handler.store = store
    Handler.config = config
    Handler.access_log = access_log
    if config.public:
        from onetrace_console.visitor_compare import Limiter

        Handler.visitor_limiter = Limiter(
            per_minute=config.compare_per_minute,
            running=config.compare_running,
            queue=config.compare_queue,
            wait_seconds=config.compare_wait_seconds,
        )

    #: SCIM: only beside sign-in through Entra ID, on a console that is neither local nor
    #: public.
    from onetrace_console import scim

    scim_refused = scim.start_refusal(config, local=local)
    if scim_refused is not None:
        print(f"refusing to start: {scim_refused[0]}\nfix: {scim_refused[1]}", file=sys.stderr)
        return 1
    if config.scim.get("enabled"):
        on, since = scim.enforcement(store_root)
        if not on:
            #: Said at every start, on the error stream, until it is on again.
            print(
                f"WARNING: SCIM's enforcement of sign-in is off, since {since}: an Entra ID sign-in is admitted on "
                "its app roles alone, with no team from SCIM. Turn it on with onetrace-console scim enforcement on.",
                file=sys.stderr,
            )

    #: The audit log: on, it needs its head's second location, off the store's volume.
    from onetrace_console import audit as audit_log

    audit_refused = audit_log.required_refusal(config) or audit_log.start_refusal(config, store_root)
    if audit_refused is not None:
        print(f"refusing to start: {audit_refused[0]}\nfix: {audit_refused[1]}", file=sys.stderr)
        return 1
    Handler.audit = audit_log.audit_for(config, store_root)
    try:
        said_audit = audit_log.start_line(Handler.audit)
    except (OSError, ValueError, audit_log.AuditUnavailable) as e:
        from onetrace_console.oserror import said

        why = said(e) if isinstance(e, OSError) else str(e)
        print(
            f"refusing to start: the audit log's head could not be read: {why}\nfix: restore audit_log/HEAD.json "
            "from a backup, or check the log with onetrace-console audit verify.",
            file=sys.stderr,
        )
        return 1
    if said_audit:
        print(said_audit, file=sys.stderr)
    try:
        audit_log.at_start(Handler.audit, config, os.environ.get(ENV_VAR) or None, store_root)
    except audit_log.AuditRefused as e:
        print(
            f"refusing to start: {e}\nfix: free the audit log's volume or its head location, then start again.",
            file=sys.stderr,
        )
        return 1

    #: With teams, every run has one team, and nothing the uploader writes picks it: a live token
    #: bound to none, a held run with none, a folder console with no `folder_team`, each refuses start, before
    #: anything is drawn.
    from onetrace_console import team_assign

    team_refused = (
        team_assign.sign_in_refusal(config)
        or team_assign.open_ingest_refusal(config, store_root, folder=prepare is not None)
        or team_assign.token_refusal(config, store_root)
        or (team_assign.folder_refusal(config) if prepare is not None else None)
        or team_assign.run_refusal(config, store)
    )
    if team_refused is not None:
        print(f"refusing to start: {team_refused.message}\nfix: {team_refused.fix}", file=sys.stderr)
        return 1
    if team_assign.sign_in_off(config):
        print(team_assign.SIGN_IN_OFF, file=sys.stderr, flush=True)

    #: A warning at every start-up when a configuration file leaves sign-in off: the
    #: console is unauthenticated and every page is open, and an operator who did not mean
    #: that should see it the moment the process starts. Local mode says the same, and more,
    #: in its own message once it is listening.
    Handler.local_port = config.port if local else None
    #: A public console gives each connection the request timeout, so a client that trickles its
    #: request line or headers cannot hold a thread; other consoles bound the body's read alone.
    Handler.timeout = config.request_timeout_seconds if config.public else None
    if local or config.public:
        for name in (
            "account_store",
            "session_store",
            "token_store",
            "rate_limit_per_account",
            "rate_limit_per_client",
            "rate_limit_concurrent_hashes",
            "rate_limit_per_pair",
            "rate_limit_per_device",
        ):
            setattr(Handler, name, None)
    if not config.sign_in.get("enabled") and not local and not config.public:
        print(
            "WARNING: sign_in.enabled is false -- every page and route is "
            "unauthenticated. Set it to true (the shipped default) once an "
            "admin account exists (`onetrace-console admin create`).",
            file=sys.stderr,
        )

    if config.sign_in.get("enabled"):
        from onetrace_console.accounts import AccountStore
        from onetrace_console.ingester_tokens import TokenStore

        #: Logged at start-up -- the one way to get a non-`Secure`
        #: cookie is loud, never a silent config value nobody notices.
        if config.sign_in.get("insecure_cookie_for_local_dev"):
            print(
                "WARNING: sign_in.insecure_cookie_for_local_dev is true -- session "
                "and CSRF cookies will NOT carry Secure. Refused outright unless "
                "this listener is loopback (see refuse_if_insecure).",
                file=sys.stderr,
            )

        Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
        Handler.token_store = TokenStore(store_root / TOKENS_DIRNAME)
        from onetrace_console.audit import CONSOLE

        #: A session's end is recorded, however it comes, and applies whatever the log says.
        Handler.session_store = session_store_for(
            config,
            Handler.account_store,
            store_root=store_root,
            on_ended=lambda who, n: Handler.audit.record(
                CONSOLE, "sessions.ended", who, {"count": n, "by": "admin sessions end"}, removes_access=True
            ),
            on_end=lambda session, how: Handler.audit.record(
                CONSOLE, "signout", session.username, {"how": how}, removes_access=True
            ),
        )
        for name, limiter in signin_limiters(config).items():
            setattr(Handler, name, limiter)
        #: The device key, made at first start beside the accounts.
        from onetrace_console.device_cookie import ensure_key

        ensure_key(store_root / ACCOUNTS_DIRNAME)

    #: The order: everything that
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
                print(
                    f"refusing to start: no TLS {what} at {named} (sign_in.{key})\nfix: "
                    f"mount a PEM certificate and its private key at sign_in.tls_cert_path "
                    f"and sign_in.tls_key_path -- in the container, with docker run "
                    f"-v <a folder holding cert.pem and key.pem>:/etc/onetrace-console/tls:ro"
                    f" -- or run the console behind your own TLS-terminating proxy "
                    f"(OPERATOR_README.md).",
                    file=sys.stderr,
                )
                return 1
    try:
        ssl_context = build_ssl_context(config)
    except (OSError, ssl.SSLError) as e:
        from onetrace_console.oserror import shown

        print(
            shown(
                f"refusing to start: cannot load the TLS certificate and key named in "
                f"sign_in.tls_cert_path and sign_in.tls_key_path: {e}"
            )
            + "\nfix: point both at a PEM certificate and its PEM private key this console "
            "can read.",
            file=sys.stderr,
        )
        return 1
    #: Entra ID sign-in: the client credential is read here, with the TLS files, before anything is
    #: bound or drawn. A refusal names the file or the variable, never what it holds.
    Handler.oidc_settings = None
    Handler.oidc_issuer = None
    Handler.oidc_flows = None
    if config.sign_in.get("enabled") and config.sign_in.get("method") == "oidc":
        from onetrace_console import oidc_settings
        from onetrace_console.oidc_issuer import Issuer

        try:
            Handler.oidc_settings = oidc_settings.load(config)
        except oidc_settings.CredentialError as e:
            print(f"refusing to start: {e}\nfix: {e.fix}", file=sys.stderr)
            return 1
        #: Nothing is asked of the issuer at start: its discovery document is read at the first sign-in.
        Handler.oidc_issuer = Issuer(Handler.oidc_settings.issuer)
        from onetrace_console.oidc_flow import FlowStore

        Handler.oidc_flows = FlowStore()
    try:
        server_class = ConsoleServer6 if ":" in config.host else ConsoleServer
        server = server_class((config.host, config.port), Handler)
    except socket.gaierror as e:
        print(
            f"refusing to start: cannot resolve host {config.host!r}: {e.strerror or e}"
            f"\nfix: give host a name or address this machine can resolve, such as "
            f"127.0.0.1.",
            file=sys.stderr,
        )
        return 1
    except OSError as e:
        if e.errno == errno.EADDRNOTAVAIL or getattr(e, "winerror", None) == 10049:
            #: A host that resolves and is not an address of this machine is not a busy port.
            print(
                f"refusing to start: cannot listen on {config.host}:{config.port}: "
                f"{config.host} is not an address of this machine.\nfix: give host an "
                f"address of this machine, such as 127.0.0.1.",
                file=sys.stderr,
            )
            return 1
        #: A port another process holds is refused in words, not
        #: with a traceback -- including a second console, which Windows would otherwise let
        #: share the port.
        print(
            f"refusing to start: cannot listen on {config.host}:{config.port}: "
            f"{e.strerror or e}. Is another process (perhaps another console) already "
            f"listening there?\nfix: stop that process, or give this console another "
            f"port: --port N on the command line, or port in its configuration file.",
            file=sys.stderr,
        )
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
        from onetrace_console.visitor_compare import cache_root

        print(
            f"onetrace-console public mode: read-only. Every write is refused before its body "
            f"is read, and the pages are served as they were built under {store_root}; nothing "
            f"is checked or drawn while serving, and nothing is compared but a pair a visitor "
            f"asks Compare for, two runs of one pipeline, kept in {cache_root(config, store_root)}. "
            f"The access log is this output.",
            file=sys.stderr,
            flush=True,
        )
    elif local:
        print(
            f"onetrace-console local mode: no configuration file named ({ENV_VAR} is not "
            f"set), so this console listens on {config.host}:{config.port} only, with no "
            f"sign-in, and keeps its store under {store_root}. Anyone who can use this "
            f"machine's loopback can read and write every page and route; requests naming "
            f"another host, and writes from another web origin, are refused. To serve beyond "
            f"this machine, name a configuration file in {ENV_VAR}.",
            file=sys.stderr,
            flush=True,
        )
    #: An IPv6 address is bracketed, or the line is not a URL.
    shown_host = f"[{config.host}]" if ":" in config.host else config.host
    base = f"{scheme}://{shown_host}:{config.port}"
    print(startup_line(base, store_root), flush=True)
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
    #: Trace forwarding's sender (`forwarding`), on a thread of its own; never on a public console.
    forwarder = start_forwarding(store_root, store, config)
    try:
        with _sigterm_as_interrupt():
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if forwarder is not None:
            forwarder.stop()
        if watcher is not None:
            watcher.stop()
            Handler.watcher = None  # type: ignore[assignment]  # back to unset, as before main()
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


def startup_line(base: str, store_root) -> str:
    """The line a console prints when it listens: its address, and the folder its store is in --
    the store root's `store`, where `x/` and every record are, as an explanation's paths name it."""
    return f"onetrace-console serving on {base} (store: {os.path.join(str(store_root), 'store')})"
