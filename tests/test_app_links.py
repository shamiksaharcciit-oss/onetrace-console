"""The demo and the capture store's app link to each other (round fb, part 4).

On a public console, as a page is served: the comparisons page gains one line, "Token-level examples (L2 and L3):
<the captures app's address>", where `ONETRACE_CONSOLE_CAPTURES_URL` names it; the Overview gains one line back,
"The onetrace-console demo: <its address>", where `ONETRACE_CONSOLE_DEMO_URL` does. Each address is the deploy's
setting, never in the code: with the variable absent, or not an http(s) address, no line is drawn. A local console
draws neither.
"""

from __future__ import annotations

import urllib.request

import pytest

from tests.http_limits import limit

CAPTURES = "https://captures.example.test"
DEMO = "https://demo.example.test/"
COMPARISONS = b"<main><h1>Comparisons</h1><p>16 comparisons.</p></main>"
OVERVIEW = b"<main><h1>Overview</h1><p>The store.</p></main>"


def test_each_line_is_drawn_with_its_setting(examined):
    from onetrace_console import app_links

    env = {app_links.CAPTURES_VAR: CAPTURES, app_links.DEMO_VAR: DEMO}
    comparisons = app_links.with_link(COMPARISONS, "comparisons.html", public=True, environ=env).decode()
    overview = app_links.with_link(OVERVIEW, "home.html", public=True, environ=env).decode()
    examined(2, "pages")
    assert (
        '<h1>Comparisons</h1><p data-section="app-link">Token-level examples (L2 and L3): '
        f'<a href="{CAPTURES}">{CAPTURES}</a></p>'
    ) in comparisons
    assert (
        f'<h1>Overview</h1><p data-section="app-link">The onetrace-console demo: <a href="{DEMO}">{DEMO}</a></p>'
    ) in overview


@pytest.mark.parametrize("value", [None, "", "  ", "javascript:alert(1)", "ftp://x.test", 'https://x.test/"><b>'])
def test_with_the_setting_absent_or_not_an_address_no_line_is_drawn(value, examined):
    from onetrace_console import app_links

    env = {} if value is None else {app_links.CAPTURES_VAR: value, app_links.DEMO_VAR: value}
    examined(1, f"the setting {value!r}")
    assert app_links.with_link(COMPARISONS, "comparisons.html", public=True, environ=env) == COMPARISONS
    assert app_links.with_link(OVERVIEW, "home.html", public=True, environ=env) == OVERVIEW


def test_a_local_console_and_any_other_page_draw_no_line(examined):
    from onetrace_console import app_links

    env = {app_links.CAPTURES_VAR: CAPTURES, app_links.DEMO_VAR: DEMO}
    examined(2, "pages")
    assert app_links.with_link(COMPARISONS, "comparisons.html", public=False, environ=env) == COMPARISONS
    assert app_links.with_link(COMPARISONS, "executions-all.html", public=True, environ=env) == COMPARISONS


def test_a_public_console_serves_the_line_its_setting_names(server, monkeypatch, examined):
    """Through the console's own GET: the line is added as the page is served, not drawn into the stored page."""
    from onetrace_console import app_links
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler

    base, root = server
    monkeypatch.setattr(Handler, "config", Config(public=True, sign_in={**Config().sign_in, "enabled": False}))
    stored = (root / "pages" / "comparisons.html").read_bytes()
    monkeypatch.delenv(app_links.CAPTURES_VAR, raising=False)
    without = urllib.request.urlopen(base + "/comparisons.html", timeout=limit(30)).read().decode()
    monkeypatch.setenv(app_links.CAPTURES_VAR, CAPTURES)
    with_it = urllib.request.urlopen(base + "/comparisons.html", timeout=limit(30)).read().decode()
    examined(2, "the comparisons page, served without the setting and with it")
    assert 'data-section="app-link"' not in without
    assert f'Token-level examples (L2 and L3): <a href="{CAPTURES}">' in with_it
    assert (root / "pages" / "comparisons.html").read_bytes() == stored
