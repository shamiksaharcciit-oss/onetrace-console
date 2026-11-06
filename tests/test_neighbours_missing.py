"""Console 0.6.1 item 2: the extra missing, said plainly.

On a local console whose Python lacks the `[neighbours]` extra, `/neighbours/setup` says so, names the
Python the console runs from (`sys.executable`) and gives `pip install "onetrace-console[neighbours]"`,
in place of "not rendered". A public console still has no such page, and the routes that turn the
feature on or off still do not exist without the extra.
"""
from __future__ import annotations

import html
import os
import shlex
import subprocess
import sys
import urllib.error
import urllib.request

from tests.http_limits import limit
from tests.test_neighbours import _absent


def _ask(url):
    try:
        r = urllib.request.urlopen(url, timeout=limit(30))
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_the_page_names_the_python_and_the_install_line(server, monkeypatch):
    base, _root = server
    _absent(monkeypatch)
    status, page = _ask(base + "/neighbours/setup")
    assert status == 200
    assert "not rendered" not in page
    assert "The neighbours extra is not installed in the Python this console runs from." in page
    assert f'<code data-neighbours="python">{html.escape(sys.executable)}</code>' in page
    assert 'pip install "onetrace-console[neighbours]"' in html.unescape(page)
    #: The Python named as this platform's shell takes it, as the page names it (unquoted, it failed wherever
    #: `sys.executable` holds a space): `shlex.quote`, or on Windows `subprocess.list2cmdline`.
    quoted = subprocess.list2cmdline([sys.executable]) if os.name == "nt" else shlex.quote(sys.executable)
    assert f'{quoted} -m pip install "onetrace-console[neighbours]"' in html.unescape(page)
    #: Nothing to turn on: no form posts to the routes the extra would add.
    assert "/neighbours/on" not in page and "<form" not in page.split("<main", 1)[1]


def test_a_public_console_still_has_no_such_page(server, monkeypatch):
    from onetrace_console.serve import Handler
    base, _root = server
    _absent(monkeypatch)
    import dataclasses
    monkeypatch.setattr(Handler, "config", dataclasses.replace(Handler.config, public=True))
    status, page = _ask(base + "/neighbours/setup")
    assert status == 404 and "neighbours" not in page.replace("not rendered: neighbours/setup", "")


def test_the_page_never_shows_the_choice_or_a_setting():
    from onetrace_console.neighbours.pages import missing_page
    page = missing_page()
    assert 'data-section="choose"' not in page and 'data-section="setting"' not in page
    assert "huggingface" not in page
