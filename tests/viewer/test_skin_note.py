"""The vendored skin note, with its header removed, still gives exactly the original's tokens.

The note was vendored with a header naming where it came from. That header was removed, and nothing
the viewer reads from the note changed: its `css` block. ORIGINAL_TOKENS below is every declaration in
the original note's block, generated from that file when the header came off, and kept here as data,
so this test needs nothing outside the console.
"""
from __future__ import annotations

import re

from onetrace_console.viewer import tokens

ORIGINAL_TOKENS = {
    '--page': '#f5f6f8',
    '--surface': '#ffffff',
    '--surface-sunk': '#fbfcfd',
    '--surface-alt': '#f9fafb',
    '--ink': '#16202e',
    '--ink-soft': '#3a4556',
    '--ink-muted': '#4a5566',
    '--ink-faint': '#667185',
    '--line': '#dde2ea',
    '--line-soft': '#eef1f5',
    '--line-node': '#c9d0db',
    '--line-strong': '#8a96a8',
    '--accent': '#1f3a5f',
    '--accent-ink': '#ffffff',
    '--nav-bg': '#0f1b2d',
    '--nav-ink': '#c9d3e0',
    '--nav-ink-faint': '#8fa0b8',
    '--nav-on-bg': '#1f3a5f',
    '--nav-on-ink': '#ffffff',
    '--ok-bg': '#e6f4ea',
    '--ok-ink': '#17663a',
    '--cc-bg': '#fdf3dc',
    '--cc-ink': '#7a4f00',
    '--hl': '#fdf3dc',
    '--bad-bg': '#fdeaea',
    '--bad-ink': '#a4161a',
    '--neu-bg': '#eef1f5',
    '--neu-ink': '#3a4556',
    '--font-sans': "'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif",
    '--font-mono': "'IBM Plex Mono',ui-monospace,'Cascadia Mono',Consolas,monospace",
    '--fs-small': '12px',
    '--fs-body': '13px',
    '--fs-nav': '14px',
    '--fs-h1': '26px',
    '--fs-kpi': '30px',
    '--r-card': '8px',
    '--r-ctl': '6px',
    '--r-pill': '4px',
    '--r-num': '13px',
    '--nav-width': '232px',
}


def _declarations(block: str) -> dict[str, str]:
    return {k: v.strip() for k, v in re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", block)}


def test_the_note_gives_the_original_tokens(examined):
    tokens.css_block.cache_clear()
    got = _declarations(tokens.css_block())
    examined(len(got), "token declarations read from the note")
    assert got == ORIGINAL_TOKENS


def test_the_palette_is_the_original_colours(examined):
    tokens.css_block.cache_clear()
    tokens.palette.cache_clear()
    want = {k: v.lower() for k, v in ORIGINAL_TOKENS.items() if re.fullmatch(r"#[0-9a-fA-F]{6}", v)}
    examined(len(want), "colours")
    assert tokens.palette() == want


# ------------------------------------------------------------------ the note reworded (console 0.7.0)
#: sha256 of css_block() and of root_css(), as they were before the note's words were changed: the
#: rewording leaves every byte the viewer reads as it was.
CSS_BLOCK_SHA256 = "734a1ebf8466c9e107784fcd526ead604b5294f07a39c9026d03f46508733422"
ROOT_CSS_SHA256 = "207107543f6a10bc34880c8b8a24a0a0fe837bc221d621495438962f19a2a080"
#: sha256 of the reworded note, the value tokens.SPEC_DIGEST and _vendor/skin.SHA256 pin.
NOTE_SHA256 = "39ba38b9f4d5a8ae3fd94e42e8e6935addbade8956443df3a5337ee2fd1a8cb8"


def test_css_block_and_root_css_are_byte_for_byte_as_before(examined):
    import hashlib
    tokens.css_block.cache_clear()
    examined(2, "token blocks")
    assert hashlib.sha256(tokens.css_block().encode("utf-8")).hexdigest() == CSS_BLOCK_SHA256
    assert hashlib.sha256(tokens.root_css().encode("utf-8")).hexdigest() == ROOT_CSS_SHA256


def test_the_note_s_digest_is_pinned_where_the_viewer_checks_it(examined):
    import hashlib
    raw = tokens.SPEC_PATH.read_bytes()
    pinned = (tokens.SPEC_PATH.parent / "skin.SHA256").read_text(encoding="utf-8").split()
    examined(1, "note")
    assert hashlib.sha256(raw).hexdigest() == NOTE_SHA256 == tokens.SPEC_DIGEST
    assert pinned == [NOTE_SHA256, tokens.SPEC_PATH.name]


def test_sabotage_a_changed_word_in_the_note_is_refused(tmp_path, monkeypatch, examined):
    import pytest
    changed = tmp_path / tokens.SPEC_PATH.name
    raw = tokens.SPEC_PATH.read_bytes()
    changed.write_bytes(raw.replace(b"Colour signals verdicts only.", b"Colour signals verdicts mostly.", 1))
    assert changed.read_bytes() != raw
    monkeypatch.setattr(tokens, "SPEC_PATH", changed)
    tokens.css_block.cache_clear()
    examined(1, "changed note")
    try:
        with pytest.raises(tokens.TokenError, match="bytes have changed"):
            tokens.css_block()
    finally:
        tokens.css_block.cache_clear()


#: The canvas's own ids, which the note named outside its token block: a board set's ("65Qi…") and a live
#: version's (ten digits, a dash, four characters). Neither is read by css_block().
CANVAS_IDS = re.compile(r"65Qi|\b\d{10}-[0-9a-z]{4}\b")


def test_the_note_names_no_canvas_id_and_its_block_never_did(examined):
    text = tokens.SPEC_PATH.read_text(encoding="utf-8")
    tokens.css_block.cache_clear()
    examined(1, "note")
    assert CANVAS_IDS.search(text) is None, CANVAS_IDS.findall(text)
    assert CANVAS_IDS.search(tokens.css_block()) is None
