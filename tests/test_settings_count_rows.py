"""A text diff's "settings: N changed" sits over N rows.

The SDK counts every setting line of a stage, its recorded fingerprints among them; the text diff
showed the readable settings and put each fingerprint under Details, so "settings: 2 changed" sat
over one row. Each fingerprint now has a row of its own where the count is, saying what it
fingerprints and that it differs; its two values stay under Details, as before. Held on every
text diff the demo draws, on the comparison pages and on the text diff's own pages.
"""
from __future__ import annotations

import re

from tests.test_compare_page import demo  # noqa: F401
from tests.test_textdiff_view import settings_problems


def count_problems(page: str) -> list[str]:
    """For each stage in a text diff: its "settings: N changed" against the rows shown outside
    Details, the count line itself not counted."""
    out = []
    for node, body in re.findall(r'<article data-node="([^"]*)">(.*?)</article>', page, re.S):
        m = re.search(r"<p data-settings>settings: (\d+) changed</p>", body)
        if not m:
            continue
        shown = body.split("<details data-settings-details>", 1)[0]
        rows = len(re.findall(r"<p data-settings[ >]", shown)) - 1
        if rows != int(m.group(1)):
            out.append(f"{node}: settings: {m.group(1)} changed over {rows} rows")
    return out


def _pages(demo) -> dict[str, str]:  # noqa: F811
    folder, _store = demo
    return {p.name: p.read_text(encoding="utf-8") for p in (folder / "store" / "pages" / "diff").glob("*.html")}


def test_every_count_sits_over_as_many_rows(demo, examined):  # noqa: F811
    pages = _pages(demo)
    counted = sum(len(re.findall(r"settings: \d+ changed", p)) for p in pages.values())
    examined(counted, "settings counts")
    assert counted > 0
    assert {name: count_problems(p) for name, p in pages.items() if count_problems(p)} == {}


def test_a_fingerprint_row_names_it_and_keeps_its_values_under_details(examined):
    from onetrace_console.textdiff_view import _settings
    lines = ["settings: 2 changed", "  instrument.config_digest: aaa2d6fad586 -> a034738a4cba",
             "  constants.chunk_size: 1024 -> 512"]
    html = _settings(lines)
    examined(len(lines), "settings lines")
    page = f'<article data-node="split">{html}</article>'
    assert count_problems(page) == []
    assert settings_problems(html) == []
    shown = html.split("<details data-settings-details>", 1)[0]
    assert "configuration fingerprint</span>: differs, both values under Details" in shown
    assert "aaa2d6fad586" not in shown and "aaa2d6fad586" in html


def test_sabotage_a_missing_row_is_named(examined):
    from onetrace_console.textdiff_view import _settings
    lines = ["settings: 2 changed", "  instrument.config_digest: aaa2d6fad586 -> a034738a4cba",
             "  constants.chunk_size: 1024 -> 512"]
    html = re.sub(r"<p data-settings data-fingerprint>.*?</p>", "", _settings(lines), count=1)
    examined(1, "planted stage")
    assert count_problems(f'<article data-node="split">{html}</article>') == ["split: settings: 2 changed over 1 rows"]
