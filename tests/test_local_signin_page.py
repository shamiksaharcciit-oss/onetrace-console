"""The local sign-in page in the console's frame, as the Entra ID pages are: the saved theme applied before the
first paint, the main column's padding, its form unchanged; measured by the layout check at 1280 and 390, both
themes."""

from __future__ import annotations

import sys
from pathlib import Path

from onetrace_console.frame import THEME_HEAD_SCRIPT
from onetrace_console.signin import CSRF_FIELD, render_signin_page

REPO = Path(__file__).resolve().parent.parent


def test_the_page_takes_the_theme_and_the_column(examined):
    page = render_signin_page(csrf_token="t0ken")
    examined(4, "the theme script, the column, the viewport, the form")
    assert THEME_HEAD_SCRIPT in page
    assert '<div class="shell"><main><div class="cp">' in page
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in page
    assert f'name="{CSRF_FIELD}" value="t0ken"' in page and 'action="/signin"' in page and 'type="password"' in page


def test_an_error_is_still_said(examined):
    examined(1, "the wrong-password line")
    assert '<p data-section="error">wrong username or password</p>' in render_signin_page(
        csrf_token="t", error="wrong username or password"
    )


def test_the_layout_check_reads_it(examined):
    sys.path.insert(0, str(REPO))
    from tools import layout_check, signin_pages

    examined(2, "the kind, and the tool serving it")
    assert layout_check.SIGNIN_KINDS["signin-local"] == "signin/local"
    assert "/signin/local" in signin_pages.pages()
