"""The console's frame -- its navigation, its footer and its one stylesheet.

What the specification fixes, and what each test below holds:
- the navigation lists pages that exist, and only those: Overview, Runs, Comparisons (after Runs),
  Incidents, and Policy when the onedoor extension is on. Nothing is drawn as "not available";
- every link in it answers 200 to a signed-in user, and every item is a page that exists;
- the footer states facts only -- the mode (local, or signed in as the session's user) and the
  console's version -- and matches the session it is served to;
- one stylesheet, `/static/console.css`, served to anyone (the sign-in page uses it), with no
  request to any other host from it or from any page;
- the frame is `data-frame`, so the visible-text comparison leaves it out (tests/test_visible_text.py).

For the pages the viewer seals (a run's answer and case, every runs list), the
frame is filled when the page is rendered, before its seal, so the served bytes are the bytes on
disk and the printed fingerprint checks on what the reader gets -- in local mode and signed in.
A sealed page's footer states the configuration ("Local mode" or "Sign-in required") and the
version, and never a user; an unsealed page's states the session.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from onetrace_console import __version__
from onetrace_console.config import Config
from onetrace_console.serve import PAGES_DIRNAME, Handler, _render_all_pages
from tests.test_pages import checked  # noqa: F401 - a fixture
from tests.test_roles_enforcement import _sign_in
from tests.test_signin_flow import _get

NAV = re.compile(r'<nav class="frame" data-frame>(.*?)</nav>', re.S)
LINK = re.compile(r'<a href="([^"]+)"( aria-current="page")?>([^<]*)</a>')
FOOTER = re.compile(r"<footer>(.*?)</footer>", re.S)
UNFRAMED = ("home.html", "incidents.html")


def _nav(page: bytes) -> str:
    found = NAV.findall(page.decode("utf-8"))
    assert len(found) == 1, f"expected one frame nav, found {len(found)}"
    return found[0]


def _items(page: bytes) -> list[tuple[str, str, bool]]:
    return [(label, href, bool(cur)) for href, cur, label in LINK.findall(_nav(page))]


def _footer_text(page: bytes) -> str:
    """What the footer states: its mode and version. The theme switch beside them, and its script,
    are each there once and left out of what it states (tests/test_theme_switch.py holds them)."""
    from onetrace_console.frame import THEME_SCRIPT, THEME_SWITCH
    footer = FOOTER.findall(_nav(page))
    assert len(footer) == 1
    assert footer[0].count(THEME_SWITCH) == 1 and footer[0].count(THEME_SCRIPT) == 1
    stated = footer[0].replace(THEME_SWITCH, "").replace(THEME_SCRIPT, "")
    return " ".join(re.sub(r"<[^>]+>", " ", stated).split())


@pytest.fixture
def onedoor(server):
    """The same console with the onedoor extension on, its Policy pages rendered."""
    base, store_root = server
    old = Handler.config
    Handler.config = Config(sign_in={**old.sign_in}, extensions={"onedoor": True})
    _render_all_pages(Handler.store, store_root, Handler.config)
    try:
        yield base, store_root
    finally:
        Handler.config = old


# ----------------------------------------------------------------------- the navigation

def test_the_navigation_lists_overview_runs_comparisons_and_incidents_without_onedoor(server, examined):
    base, _ = server
    status, page, _, _ = _get(base, "/")
    examined(1, "Overview served")
    assert status == 200
    assert [(label, href) for label, href, _ in _items(page)] == [
        ("Overview", "/"), ("Runs", "/executions-all.html"), ("Comparisons", "/comparisons.html"),
        ("Incidents", "/incidents.html")]


def test_the_navigation_adds_policy_with_onedoor(onedoor, examined):
    base, _ = onedoor
    status, page, _, _ = _get(base, "/")
    examined(1, "Overview served")
    assert status == 200
    assert [label for label, _, _ in _items(page)] == ["Overview", "Runs", "Comparisons",
                                                       "Incidents", "Policy"]


def test_nothing_is_drawn_as_not_available(onedoor, examined):
    base, _ = onedoor
    pages = [_get(base, f"/{rel}")[1] for rel in UNFRAMED]
    examined(len(pages), "pages")
    for page in pages:
        nav = _nav(page).lower()
        for word in ("not available", "unavailable", "coming soon", "disabled"):
            assert word not in nav, word
        assert nav.count("<a ") == len(_items(page)), "an item that is not a link"


def test_every_item_is_a_page_that_exists(onedoor, examined):
    base, store_root = onedoor
    items = _items(_get(base, "/")[1])
    examined(len(items), "navigation items")
    pages = store_root / PAGES_DIRNAME
    for label, href, _ in items:
        rel = "home.html" if href == "/" else href.lstrip("/")
        assert (pages / rel).is_file(), (label, rel)


def test_every_link_answers_200_to_a_signed_in_user(onedoor, examined):
    base, store_root = onedoor
    saved = {n: getattr(Handler, n) for n in ("config", "account_store", "session_store",
                                              "token_store", "rate_limit_per_account",
                                              "rate_limit_per_client",
                                              "rate_limit_concurrent_hashes")}
    _sign_in_on(store_root)
    try:
        cookie, _ = _sign_in(base)
        headers = {"Cookie": f"onetrace_session={cookie}"}
        seen = 0
        for rel in UNFRAMED + ("policy.html",):
            status, page, _, _ = _get(base, f"/{rel}", headers=headers)
            assert status == 200, rel
            for label, href, _ in _items(page):
                assert _get(base, href, headers=headers)[0] == 200, (rel, label, href)
                seen += 1
        examined(seen, "links followed, signed in")
    finally:
        for name, value in saved.items():
            setattr(Handler, name, value)


def test_the_current_page_is_marked_and_only_it(onedoor, examined):
    base, _ = onedoor
    #: The All counts page is the Overview's own list, so it sits under Overview.
    expected = {"home.html": "Overview", "counts.html": "Overview", "incidents.html": "Incidents",
                "policy.html": "Policy"}
    examined(len(expected), "pages")
    for rel, label in expected.items():
        current = [item for item, _, cur in _items(_get(base, f"/{rel}")[1]) if cur]
        assert current == [label], (rel, current)


# --------------------------------------------------------------------------- the footer

def test_the_footer_states_local_mode_and_the_version(server, examined):
    base, _ = server
    examined(len(UNFRAMED), "pages")
    for rel in UNFRAMED:
        assert _footer_text(_get(base, f"/{rel}")[1]) == f"Local mode onetrace-console {__version__}"


def _package_version() -> str:
    import tomllib
    text = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8")
    return tomllib.loads(text)["project"]["version"]


def test_every_footer_shows_the_package_s_own_version(server, examined):
    """The version a footer shows is the one pyproject.toml gives the package, not only the
    module's constant: a served page's, a drawn page's, and the generator line's."""
    from datetime import datetime, timezone

    from onetrace_console.pages import GENERATOR
    from onetrace_console.words import generated_footer
    version = _package_version()
    base, _ = server
    for rel in UNFRAMED:
        assert _footer_text(_get(base, f"/{rel}")[1]).endswith(f" onetrace-console {version}"), rel
    drawn = generated_footer(datetime(2026, 10, 15, tzinfo=timezone.utc))
    assert re.search(rf"by onetrace-console {re.escape(version)}\.</p></footer>$", drawn), drawn
    assert GENERATOR == f"onetrace-console {version}"
    examined(len(UNFRAMED) + 2, "footers read")


def test_the_footer_names_the_signed_in_user(server, examined):
    base, store_root = server
    saved = {n: getattr(Handler, n) for n in ("config", "account_store", "session_store",
                                              "token_store", "rate_limit_per_account",
                                              "rate_limit_per_client",
                                              "rate_limit_concurrent_hashes")}
    _sign_in_on(store_root)
    try:
        cookie, _ = _sign_in(base)
        examined(len(UNFRAMED), "pages, signed in")
        for rel in UNFRAMED:
            page = _get(base, f"/{rel}", headers={"Cookie": f"onetrace_session={cookie}"})[1]
            assert _footer_text(page) == f"Signed in as alice onetrace-console {__version__}"
    finally:
        for name, value in saved.items():
            setattr(Handler, name, value)


def test_the_footer_is_escaped(examined):
    from onetrace_console.frame import footer
    examined(1, "footer drawn")
    assert "<b>" not in footer('<b>x</b>') and "&lt;b&gt;" in footer('<b>x</b>')


# ----------------------------------------------------------------------- the stylesheet

def test_the_stylesheet_is_served_to_anyone(server, examined):
    """With sign-in on and no session -- the sign-in page links it."""
    base, _ = server
    from onetrace_console.viewer.page import CSS, FRAME_CSS
    from onetrace_console.viewer.tokens import root_css
    old = Handler.config
    Handler.config = Config(sign_in={"enabled": True})
    try:
        status, body, headers, _ = _get(base, "/static/console.css")
    finally:
        Handler.config = old
    examined(1, "stylesheet served signed out")
    assert status == 200 and headers.get("Content-Type") == "text/css; charset=utf-8"
    text = body.decode("utf-8")
    for part in (root_css(), CSS, FRAME_CSS):
        assert part.strip() in text
    fonts = sorted(p.name for p in (Path(__file__).resolve().parent.parent / "src"
                                    / "onetrace_console" / "static" / "fonts").glob("*.woff2"))
    assert sorted(re.findall(r"url\(/static/fonts/([\w-]+\.woff2)\)", text)) == fonts


def test_a_framed_page_links_the_stylesheet_and_embeds_none(server, examined):
    base, _ = server
    examined(len(UNFRAMED), "pages")
    for rel in UNFRAMED:
        page = _get(base, f"/{rel}")[1].decode("utf-8")
        assert '<link rel="stylesheet" href="/static/console.css">' in page
        assert "<style>" not in page, rel


def test_the_sign_in_page_links_the_stylesheet_and_has_no_navigation(server, examined):
    base, _ = server
    old = Handler.config
    Handler.config = Config(sign_in={"enabled": True})
    try:
        status, page, _, _ = _get(base, "/signin")
    finally:
        Handler.config = old
    examined(1, "sign-in page")
    text = page.decode("utf-8")
    assert status == 200
    assert '<link rel="stylesheet" href="/static/console.css">' in text
    assert "<nav" not in text and "<a " not in text


# ------------------------------------------------------------------ no external requests

#: Anything a browser fetches by itself: an attribute naming another host (or scheme-relative),
#: a CSS url() or @import doing the same.
EXTERNAL = re.compile(r'(?:\b(?:src|href|action)\s*=\s*["\']?\s*(?:[a-z][a-z0-9+.-]*:)?//)'
                      r'|(?:url\(\s*["\']?\s*(?:[a-z][a-z0-9+.-]*:)?//)|@import', re.I)


def test_no_page_or_stylesheet_asks_another_host_for_anything(onedoor, examined):
    base, store_root = onedoor
    served = [_get(base, "/static/console.css")[1]]
    for path in sorted((store_root / PAGES_DIRNAME).rglob("*.html")):
        rel = path.relative_to(store_root / PAGES_DIRNAME).as_posix()
        served.append(_get(base, f"/{rel}")[1])
    examined(len(served), "served files")
    for body in served:
        assert not EXTERNAL.search(body.decode("utf-8")), EXTERNAL.search(body.decode("utf-8"))


def test_the_external_request_scan_catches_what_it_looks_for(examined):
    examined(5, "probes")
    for probe in ('<link href="https://fonts.example/x.css">', "src='//cdn.example/x.js'",
                  "url(https://x.example/f.woff2)", '@import "a.css";',
                  '<img src = "http://x.example/a.png">'):
        assert EXTERNAL.search(probe), probe
    assert not EXTERNAL.search('<a href="/executions-all.html">Runs</a>')


# ------------------------------------------------------------------------ sealed pages

def _sealed(store_root: Path, run_key: str) -> list[str]:
    """Every page on disk that carries a fingerprint -- found by its slot, not listed by hand, so
    a sealed page added later is held too. Asserted to include a run's two pages and a list."""
    from onetrace_console.viewer.slot import OPEN
    pages = store_root / PAGES_DIRNAME
    rels = sorted(p.relative_to(pages).as_posix() for p in pages.rglob("*.html")
                  if OPEN.encode() in p.read_bytes())
    for rel in (f"runs/{run_key}/answer.html", f"runs/{run_key}/case.html", "executions-all.html"):
        assert rel in rels, rel
    return rels


def _render_sealed(checked, store, store_root) -> None:
    """Render as the console does at start-up, under the configuration it now has."""
    from onetrace_console.serve import _render_startup_pages
    Handler.store = store
    _render_startup_pages(store, store_root, Handler.config)


def _check_sealed(base, store_root, rels, headers, footer_text) -> None:
    from onetrace_console.viewer import fingerprint
    for rel in rels:
        status, body, _, _ = _get(base, f"/{rel}", headers=headers)
        assert status == 200, rel
        assert body == (store_root / PAGES_DIRNAME / rel).read_bytes(), f"served != disk: {rel}"
        ok, why = fingerprint.check(body)
        assert ok, (rel, why)
        assert [label for label, _, cur in _items(body) if cur] == ["Runs"], rel
        assert _footer_text(body) == footer_text, rel
        assert "alice" not in _nav(body), f"a user named in a sealed page's frame: {rel}"


def test_a_sealed_page_is_served_as_written_and_checks_in_local_mode(checked, store, server,
                                                                       examined):
    base, store_root = server
    old = Handler.store
    try:
        _render_sealed(checked, store, store_root)
        rels = _sealed(store_root, checked.key)
        examined(len(rels), "sealed pages served, local mode")
        _check_sealed(base, store_root, rels, {}, f"Local mode onetrace-console {__version__}")
    finally:
        Handler.store = old


def test_a_sealed_page_is_served_as_written_and_checks_signed_in(checked, store, server,
                                                                   examined):
    base, store_root = server
    saved = {n: getattr(Handler, n) for n in ("config", "store", "account_store", "session_store",
                                              "token_store", "rate_limit_per_account",
                                              "rate_limit_per_client",
                                              "rate_limit_concurrent_hashes")}
    try:
        _sign_in_on(store_root)
        _render_sealed(checked, store, store_root)
        rels = _sealed(store_root, checked.key)
        cookie, _ = _sign_in(base)
        examined(len(rels), "sealed pages served, signed in as alice")
        _check_sealed(base, store_root, rels, {"Cookie": f"onetrace_session={cookie}"},
                      f"Sign-in required onetrace-console {__version__}")
        #: The same session's unsealed page does name its user.
        home = _get(base, "/", headers={"Cookie": f"onetrace_session={cookie}"})[1]
        assert _footer_text(home) == f"Signed in as alice onetrace-console {__version__}"
    finally:
        for name, value in saved.items():
            setattr(Handler, name, value)


def test_a_sealed_page_drawn_outside_a_console_has_no_frame(checked, store, examined):
    """`render_execution` called with no console around it -- the viewer's own drawing."""
    from onetrace_console.pages import ANSWER, CASE, render_execution
    pages = render_execution(checked, store, generated_at="2026-10-01T12:00:00+00:00").pages
    examined(2, "pages")
    for name in (ANSWER, CASE):
        assert "data-frame" not in pages[name] and "<style>" in pages[name], name


def _sign_in_on(store_root: Path) -> None:
    """Sign-in on with one account, `alice` -- as `roles_enabled` sets it up, keeping the
    extensions the test already chose."""
    from onetrace_console.accounts import AccountError, AccountStore
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.rate_limit import ConcurrencyLimiter, RateLimiter
    from onetrace_console.serve import ACCOUNTS_DIRNAME, TOKENS_DIRNAME
    from onetrace_console.sessions import SessionStore
    Handler.config = Config(sign_in={"enabled": True}, extensions=dict(Handler.config.extensions))
    Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
    try:
        Handler.account_store.create("alice", b"correct horse battery staple")
    except AccountError:
        pass                                  # made by an earlier call in the same test
    Handler.token_store = TokenStore(store_root / TOKENS_DIRNAME)
    Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    Handler.rate_limit_per_account = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_per_client = RateLimiter(max_attempts=100, window_seconds=60)
    Handler.rate_limit_concurrent_hashes = ConcurrencyLimiter(max_concurrent=100)
