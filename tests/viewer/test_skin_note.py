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
