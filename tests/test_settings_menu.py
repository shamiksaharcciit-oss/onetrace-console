"""Console 0.6.1 item 13: a settings button at the top right.

The gear opens a small menu, one row per feature, each linking to its setup page and saying its state
from the same checks those pages use; a dot on the gear only where something set up has stopped working;
the menu is the browser's own popover (Esc and a click outside close it, no script); the sidebar's "Set up
Explain" link leaves the sidebar; the setup pages keep their addresses; nothing of a key's value is in the
menu; a public console and a static export show no gear.
"""
from __future__ import annotations

import dataclasses
import os
import re
import subprocess
import urllib.error
import urllib.request
from html import unescape
from pathlib import Path

import pytest

from tests.http_limits import limit

KEY_VALUE = "a-key-value-never-in-the-menu-0042"
VAR = "PLANTED_MENU_KEY_VARIABLE"


@pytest.fixture
def explain_config(tmp_path, monkeypatch):
    config = tmp_path / "explain-config" / "explain.toml"
    config.parent.mkdir()
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    from onetrace_console import explain
    monkeypatch.setattr(explain, "command", lambda: Path("onetrace-explain"))
    return config


def _menu(store=None) -> str:
    from onetrace_console.settings_menu import menu
    return menu(store)


def _row(html: str, feature: str) -> tuple[str, str, str]:
    href, state, words = re.search(rf'<a href="([^"]+)" data-setting="{feature}" data-state="([^"]+)">([^<]*)</a>',
                                   html).groups()
    return href, state, unescape(words)


# ------------------------------------------------------------------ Explain's three states

def test_explain_not_set_up_is_no_fault(explain_config):
    explain_config.write_text("", encoding="utf-8")
    html = _menu()
    assert _row(html, "explain") == ("/explain/setup", "off", "Explain: not set up")
    assert "data-broken" not in html and "settings-dot" not in html


def test_explain_key_not_found_puts_the_dot_on_the_gear(explain_config, monkeypatch):
    explain_config.write_text(f'[model]\nprovider = "anthropic"\nname = "a-model"\nkey_env = "{VAR}"\n', encoding="utf-8")
    monkeypatch.delenv(VAR, raising=False)
    html = _menu()
    assert _row(html, "explain") == ("/explain/setup", "broken", "Explain: key not found")
    assert 'data-frame="gear" data-broken>' in html and 'data-frame="settings-dot"' in html


def test_explain_on_names_the_model_and_never_a_key(explain_config, monkeypatch):
    explain_config.write_text(f'[model]\nprovider = "anthropic"\nname = "a-model"\nkey_env = "{VAR}"\n', encoding="utf-8")
    monkeypatch.setenv(VAR, KEY_VALUE)
    html = _menu()
    assert _row(html, "explain") == ("/explain/setup", "on", "Explain: on, a-model (anthropic)")
    assert KEY_VALUE not in html and "data-broken" not in html


# ------------------------------------------------------------------ neighbours' three states

def _store(tmp_path):
    from onetrace_console.store import Store
    return Store(tmp_path / "store")


def test_neighbours_extra_not_installed_off_and_on(tmp_path, explain_config, monkeypatch):
    from onetrace_console import neighbours
    from onetrace_console.neighbours import settings
    explain_config.write_text("", encoding="utf-8")
    store = _store(tmp_path)
    monkeypatch.setattr(neighbours, "installed", lambda: False)
    assert _row(_menu(store), "neighbours") == ("/neighbours/setup", "off", "Neighbours: extra not installed")
    monkeypatch.setattr(neighbours, "installed", lambda: True)
    assert _row(_menu(store), "neighbours") == ("/neighbours/setup", "off", "Neighbours: off")
    chosen = {"kind": "endpoint", "base_url": "http://127.0.0.1:9/v1", "model": "bag-of-words"}
    settings.turn_on(store, chosen, who="a test", confirmed=settings.confirmation(chosen))
    html = _menu(store)
    assert _row(html, "neighbours") == ("/neighbours/setup", "on", "Neighbours: on, bag-of-words (your endpoint)")
    assert "data-broken" not in html


def test_a_turned_on_local_model_with_a_file_missing_puts_the_dot(tmp_path, explain_config, monkeypatch):
    import hashlib
    import json
    from onetrace_console import neighbours
    from onetrace_console.neighbours import embedder, settings
    explain_config.write_text("", encoding="utf-8")
    monkeypatch.setattr(neighbours, "installed", lambda: True)
    data = {"onnx/model.onnx": b"weights", "tokenizer.json": b"{}"}
    tiny = embedder.Model("tiny", "example/tiny", "0" * 40, "mean", "none",
                          {p: hashlib.sha256(d).hexdigest() for p, d in data.items()})
    monkeypatch.setattr(embedder, "MODELS", {**embedder.MODELS, "tiny": tiny})
    store = _store(tmp_path)
    local = {"kind": "local", "model": "tiny"}
    settings.turn_on(store, local, who="a test", confirmed=settings.confirmation(local),
                     get=lambda url: data[url.rsplit(f"{tiny.revision}/", 1)[1]])
    assert _row(_menu(store), "neighbours") == ("/neighbours/setup", "on", "Neighbours: on, tiny")
    (embedder.folder(embedder.models_root(store), tiny) / "tokenizer.json").unlink()
    html = _menu(store)
    assert _row(html, "neighbours")[1:] == ("broken", "Neighbours: on, tiny: a model file is missing")
    assert 'data-frame="gear" data-broken>' in html


# ------------------------------------------------------------------ the button and the menu

def test_the_gear_is_a_real_button_named_settings_opening_a_popover(explain_config):
    explain_config.write_text("", encoding="utf-8")
    html = _menu()
    assert re.search(r'<button type="button" class="gear" popovertarget="settings-menu" aria-label="Settings" '
                     r'data-frame="gear">', html)
    assert '<div id="settings-menu" popover data-frame="settings-menu">' in html
    assert "<script" not in html


# ------------------------------------------------------------------ over HTTP

def _get(url):
    try:
        r = urllib.request.urlopen(url, timeout=limit(30))
        return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_a_local_console_serves_the_gear_and_the_setup_pages_keep_their_addresses(server, explain_config, monkeypatch):
    explain_config.write_text(f'[model]\nprovider = "anthropic"\nname = "a-model"\nkey_env = "{VAR}"\n', encoding="utf-8")
    monkeypatch.setenv(VAR, KEY_VALUE)
    base, _root = server
    status, home = _get(base + "/")
    assert status == 200 and 'data-frame="settings"' in home
    assert 'data-frame="setup"' not in home, "the sidebar's setup link has left the sidebar"
    assert KEY_VALUE not in home
    nav = re.search(r'<nav class="frame" data-frame>(.*?)</nav>', home, re.S).group(1)
    assert nav.index('data-frame="settings"') < nav.index("</div>", nav.index('class="brand"')) + 200
    for path in ("/explain/setup", "/neighbours/setup"):
        status, page = _get(base + path)
        assert status == 200 and 'data-frame="settings"' in page


def test_a_public_console_and_a_static_export_show_no_gear(server, monkeypatch):
    from onetrace_console.frame import fill
    from onetrace_console.serve import Handler
    base, _root = server
    page = b'<nav class="frame" data-frame></nav>'
    from onetrace_console.viewer.page import FRAME_NAV
    page = FRAME_NAV.encode()
    assert b'data-frame="settings"' not in fill(page, "home.html", onedoor=False, user=None, public=True, setup_link=True)
    #: A static export's pages are filled with no setup link: no gear.
    assert b'data-frame="settings"' not in fill(page, "home.html", onedoor=False, user=None)
    monkeypatch.setattr(Handler, "config", dataclasses.replace(Handler.config, public=True))
    status, home = _get(base + "/")
    assert 'data-frame="settings"' not in home


BROWSER_PYTHON = os.environ.get("ONETRACE_BROWSER_PYTHON", "")
ESC_SCRIPT = r"""
import sys
from playwright.sync_api import sync_playwright
url = sys.argv[1]
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1280, "height": 800})
    page.goto(url)
    menu = page.locator("#settings-menu")
    gear = page.get_by_role("button", name="Settings")
    out = []
    gear.click(); out.append(menu.is_visible())
    page.keyboard.press("Escape"); out.append(menu.is_visible())
    gear.click(); out.append(menu.is_visible())
    page.mouse.click(400, 600); out.append(menu.is_visible())
    page.set_viewport_size({"width": 390, "height": 800})
    box = gear.bounding_box(); out.append(box is not None and box["y"] < 60 and box["x"] > 300)
    gear.focus(); page.keyboard.press("Enter"); out.append(menu.is_visible())
    print(out)
    b.close()
"""


@pytest.mark.skipif(not BROWSER_PYTHON, reason="ONETRACE_BROWSER_PYTHON names no Python with Playwright's Chromium "
                                                "(the gate sets it)")
def test_in_a_browser_esc_and_a_click_outside_close_it_and_it_stays_at_the_top_on_a_phone(server, tmp_path):
    base, _root = server
    script = tmp_path / "esc.py"
    script.write_text(ESC_SCRIPT, encoding="utf-8")
    done = subprocess.run([BROWSER_PYTHON, str(script), base + "/"], capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "[True, False, True, False, True, True]"
