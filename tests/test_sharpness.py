"""Sharp at any pixel density: no page and no stylesheet draws UI text or a diagram as a raster
image. Every drawing is SVG or CSS -- no `<img>` of a PNG, JPEG, GIF or WebP, no raster `data:`
image, no `url(...)` to one, no `<canvas>`. Held to every page of the public demo and the console's
stylesheet, with a sabotage.
"""
from __future__ import annotations

import re

import pytest

from tests.test_public_mode import built  # noqa: F401

_RASTER = re.compile(r"\.(?:png|jpe?g|gif|webp|bmp)\b|data:image/(?:png|jpe?g|gif|webp|bmp)", re.I)


def raster_problems(text: str) -> list[str]:
    out = []
    for src in re.findall(r'<img\b[^>]*\bsrc="([^"]*)"', text, re.I) + re.findall(r"url\(\s*['\"]?([^'\")]+)", text):
        if _RASTER.search(src):
            out.append(f"a raster image: {src[:60]}")
    if re.search(r"<canvas\b", text, re.I):
        out.append("a canvas")
    return out


def test_no_page_or_stylesheet_draws_with_a_raster_image(built, examined):  # noqa: F811
    from onetrace_console.frame import stylesheet
    root = built / "store" / "pages"
    pages = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}
    pages["static/console.css"] = stylesheet().decode("utf-8")
    examined(len(pages), "pages and the stylesheet")
    assert {n: raster_problems(t) for n, t in pages.items() if raster_problems(t)} == {}
    assert sum(p.count('<svg class="graph"') for p in pages.values()) > 0, "no graph drawn as SVG"


@pytest.mark.parametrize("planted", ['<img src="graph.png">', "background:url(/static/x.webp)",
                                     '<img src="data:image/png;base64,AAAA">', "<canvas width=2></canvas>"])
def test_sabotage_a_raster_drawing_is_named(planted, examined):
    examined(1, "planted page")
    assert raster_problems("<p>a page</p>" + planted), planted
