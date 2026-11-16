"""Neighbours' Turn off and the Tokenizers page's Remove and "Use this tokenizer" answer in place.

As the console's other small actions do: Turn off posts in place to the setup page's section for the setting as it is
(`#neighbours-now`), whose status line then says neighbours are off; without script its action ends at that anchor,
and the console's answer names the outcome (`?said=off`). The tokenizer buttons, which exist only with script,
replace their own section from the page drawn again (the Tokenizers page's steps and kept tokenizers, or the step's
section), its status line announced; each button bound once.
"""

from __future__ import annotations

import json
import re

from tests.test_in_place import in_place_problems, section


def _on(store) -> None:
    """Neighbours on, with an endpoint embedder, as the setting file keeps it."""
    from onetrace_console.neighbours import settings

    path = settings._path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "format": settings.FORMAT,
                "embedder": {"kind": "endpoint", "base_url": "http://127.0.0.1:9/v1", "model": "m"},
                "confirmed": "confirmed words",
                "who": "a person",
                "when": "2026-11-10T12:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )


def test_turn_off_posts_in_place_to_the_setting_s_section(tmp_path, examined):
    from onetrace_console.neighbours.pages import NOW, setup_page
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    _on(store)
    page = setup_page(store, csrf="t")
    examined(1, "the setup page, neighbours on")
    assert f'action="/neighbours/off#{NOW}" data-in-place="{NOW}"' in page
    assert in_place_problems(page) == []


def test_turned_off_the_section_says_so_announced(tmp_path, examined):
    from onetrace_console.neighbours.pages import NOW, TURNED_OFF, setup_page
    from onetrace_console.store import Store

    page = setup_page(Store(tmp_path / "store"), said=TURNED_OFF, csrf="t")
    here = section(page, NOW)
    examined(1, "the setup page, turned off")
    from onetrace_console.words import escape

    assert f'<p data-neighbours="said" data-status role="status" aria-live="polite">{escape(TURNED_OFF)}</p>' in here
    assert 'data-section="choose"' in here


def test_the_tokenizer_buttons_replace_their_own_section_and_announce_it(examined):
    from onetrace_console.token_script import KEPT, REMOVED, TOKEN_SCRIPT

    examined(1, "the tokenizers' script")
    assert "sec.replaceWith(n);bind(n)" in TOKEN_SCRIPT and "[data-tokenizer-section]" in TOKEN_SCRIPT
    assert f"'{KEPT}'" in TOKEN_SCRIPT and f"'{REMOVED}'" in TOKEN_SCRIPT
    assert "data-tokenizer-bound" in TOKEN_SCRIPT and TOKEN_SCRIPT.count("location.reload()") == 2


def test_the_tokenizers_page_is_one_section_with_its_status_line(tmp_path, examined):
    from onetrace_console import token_upload as T
    from onetrace_console.store import Store

    body = T.page_body(Store(tmp_path / "store"), tmp_path / "kept", named=())
    examined(1, "the Tokenizers page")
    assert body.startswith("<div data-tokenizer-section>") and body.endswith("</div>")
    assert '<span data-tokenizer-said role="status" aria-live="polite">' in T.picker("sha256:" + "0" * 64)
    assert re.search(r'data-section="tokenizers-wanted".*data-section="tokenizers"', body, re.S)
