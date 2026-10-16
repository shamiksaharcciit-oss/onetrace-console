"""The one shared style, 0.1.1: its chips, its type scale and its contrast.

Checked here, over the console's whole served stylesheet (`frame.stylesheet()`: the skin's tokens,
the viewer's rules, the frame's, the console pages' and the public banner's), not over two of its
parts:

1. Every text colour the stylesheet sets is read on a background named for it, and each pair
   reads: WCAG AA, 4.5:1. A rule that sets its own background is read on that; a rule whose text
   sits on a coloured block names the block (`ON`); every other rule is read on each of the three
   neutral grounds a page has. A rule that sets a colour and is in none of these fails, so a new
   colour can't arrive unchecked.
2. One chip family: every state chip, wherever it is drawn -- the console's pills, the run
   ladder's rung states, a stage page's badges, the "No records" chip --
   has the one chip shape, and its tone comes from one of four pairs (ok, couldn't check, bad,
   neutral), each the skin's own. A couldn't-check note is a sentence, not a chip: an amber block.
3. The type scale: sizes are the boards' 26, 15, 13 and 12, plus the two the boards also draw
   (the 30px count and the 14px navigation, `--fs-kpi` and `--fs-nav`) and the 20px brand.
"""
from __future__ import annotations

import re

import pytest

#: Text that sits on a coloured block, not on a neutral ground: (selector, the backgrounds).
ON = {
    ".strip.ok .lead": ("ok-bg",),
    ".strip.bad .lead": ("bad-bg",),
    ".strip .beside": ("surface", "ok-bg", "bad-bg"),
    "nav.frame .brand": ("nav-bg",),
    "nav.frame a": ("nav-bg",),
    "nav.frame footer": ("nav-bg",),
    #: A graph's text sits in its boxes; on the Compare page a box is filled by its tone.
    "svg.graph text": ("surface", "ok-bg", "cc-bg", "bad-bg", "neu-bg"),
    #: A text diff's words and line numbers sit on its removed (red) and added (green) lines.
    ".cp mark.del": ("bad-bg",),
    ".cp mark.ins": ("ok-bg",),
    ".cp pre[data-hunk] .ln": ("surface", "bad-bg", "ok-bg"),
}

#: The grounds a page has: the page itself, a card or panel, and a sunk block (`pre`).
NEUTRAL = ("page", "surface", "surface-sunk")


def _rules(css: str) -> list[tuple[str, str]]:
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"@(?:font-face|property)[^{}]*\{[^{}]*\}", "", css)
    out = []
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        selector = " ".join(selector.split())
        if selector.startswith(("@", "from", "to")) or ":root" in selector:
            continue
        out.append((re.sub(r"^@[^{]*\{", "", selector).strip(), body))
    return out


def _var(value: str) -> str | None:
    m = re.fullmatch(r"\s*var\(--([\w-]+)\)\s*", value)
    return m.group(1) if m else None


def _declared(body: str, prop: str) -> str | None:
    m = re.search(rf"(?<![-\w]){prop}\s*:\s*([^;]+)", body)
    return m.group(1).strip() if m else None


def _tokens(theme: str = "light") -> dict[str, str]:
    """{role: #rrggbb} in a theme: the skin's own block for light, the dark theme's mix for dark."""
    from onetrace_console.viewer.tokens import dark_palette, root_css
    if theme == "dark":
        return dict(dark_palette())
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root_css()))


def _luminance(hex_colour: str) -> float:
    def channel(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def ratio(fg: str, bg: str, tokens: dict[str, str]) -> float:
    a, b = sorted((_luminance(tokens[fg]), _luminance(tokens[bg])), reverse=True)
    return (a + 0.05) / (b + 0.05)


def text_pairs(css: str) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Every (selector, text token, background token) the stylesheet reads, and every rule that
    sets a text colour this file can't place."""
    pairs, unplaced = [], []
    for selector, body in _rules(css):
        colour = _declared(body, "color")
        if selector.startswith("svg.graph") and "text" in selector:
            colour = _declared(body, "fill")
        if colour is None:
            continue
        fg = _var(colour)
        if fg is None:
            unplaced.append(f"{selector}: color is not a skin token ({colour})")
            continue
        own = _declared(body, "background") or _declared(body, "background-color")
        if own is not None and _var(own):
            pairs.append((selector, fg, _var(own)))
        elif selector in ON:
            pairs += [(selector, fg, bg) for bg in ON[selector]]
        elif selector.startswith("nav.frame"):
            unplaced.append(f"{selector}: text in the navigation, with no background named")
        else:
            pairs += [(selector, fg, bg) for bg in NEUTRAL]
    return pairs, unplaced


def contrast_problems(css: str, theme: str = "light") -> list[str]:
    tokens = _tokens(theme)
    pairs, unplaced = text_pairs(css)
    return unplaced + [f"{s}: --{fg} on --{bg} reads {ratio(fg, bg, tokens):.2f}:1"
                       for s, fg, bg in pairs if ratio(fg, bg, tokens) < 4.5]


def _sheet() -> str:
    from onetrace_console.frame import stylesheet
    return stylesheet().decode("utf-8")


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_text_colour_in_the_whole_stylesheet_reads_on_its_background(theme, examined):
    pairs, _ = text_pairs(_sheet())
    examined(len(pairs), f"text-on-background pairs in the served stylesheet, {theme}")
    assert len(pairs) >= 100, len(pairs)
    assert contrast_problems(_sheet(), theme) == []


@pytest.mark.parametrize("planted, said", [
    (".last-failed{background:var(--cc-bg);color:var(--ink-faint)}", "--ink-faint on --cc-bg"),
    (".card .step{color:var(--line-strong)}", "--line-strong on --page"),
    ("nav.frame .later{color:var(--nav-ink)}", "with no background named"),
    (".later{color:#777777}", "not a skin token"),
])
def test_the_contrast_check_names_a_pair_that_doesnt_read(planted, said, examined):
    """Sabotage: a pair that falls short, a rule the check can't place, a literal colour."""
    examined(1, "planted rule")
    found = contrast_problems(_sheet() + planted)
    assert any(said in p for p in found), found


# ------------------------------------------------------------------ 2. one chip family

#: Every place a state chip is drawn, by the selector that draws it.
CHIPS = (
    ".cp .pill",
    ".shell .page tr[data-rung]>td:last-child>span:first-child",
    ".cp tr[data-badge]>td:last-child>span:first-child",
    ".cp>p[data-state=no-records]",
)

#: The four tones, as the skin's (ink, fill) pairs.
TONES = {("ok-ink", "ok-bg"), ("cc-ink", "cc-bg"), ("bad-ink", "bad-bg"), ("neu-ink", "neu-bg")}


def chip_problems(css: str) -> list[str]:
    from onetrace_console.frame import CHIP_SHAPE
    rules = _rules(css)
    shaped = [s for s, body in rules if body.strip().rstrip(";") == CHIP_SHAPE.strip().rstrip(";")]
    problems = [f"{c}: not given the one chip shape" for c in CHIPS
                if not any(c in [x.strip() for x in s.split(",")] for s in shaped)]
    for selector, body in rules:
        if not (any(c in selector for c in CHIPS) or "data-state" in selector
                or re.search(r"\.cp \.(?:ok|cc|cco|bad|neu)\b", selector)):
            continue
        fg, bg = _var(_declared(body, "color") or ""), _var(_declared(body, "background") or "")
        if fg and bg and (fg, bg) not in TONES:
            problems.append(f"{selector}: --{fg} on --{bg} is not one of the four tones")
    #: The fifth kind, a run stopped by a step's own rule: the accent's outline on the page's own
    #: ground, and only that, as the declined-runs work order asks.
    dec = [body for s, body in rules if re.search(r"\.cp,\.shell \.page\) \.dec\b", s)]
    want = {"background": "transparent", "color": "var(--accent)", "outline": "1px solid var(--accent)"}
    if len(dec) != 1 or any((_declared(dec[0], k) or "").strip() != v for k, v in want.items()):
        problems.append(f".cp .dec: not the declined outline ({dec})")
    return problems


def test_every_state_chip_has_the_one_shape_and_one_of_four_tones(examined):
    examined(len(CHIPS), "places a state chip is drawn")
    assert chip_problems(_sheet()) == []


@pytest.mark.parametrize("planted, said", [
    (".cp .bad{background:var(--accent);color:var(--accent-ink)}", "is not one of the four tones"),
    #: The declined chip filled red, as a failure would be.
    (":is(.cp,.shell .page) .dec{background:var(--bad-bg);color:var(--bad-ink)}", "not the declined outline"),
])
def test_the_chip_check_names_a_fifth_tone(planted, said, examined):
    examined(1, "planted chip tone")
    found = chip_problems(_sheet() + planted)
    assert any(said in p for p in found), found


def test_the_chip_check_names_a_chip_without_the_shape(examined, monkeypatch):
    from onetrace_console import frame
    examined(1, "chip shape removed")
    sheet = _sheet().replace(frame.CHIP_SHAPE, "display:inline")
    assert any("not given the one chip shape" in p for p in chip_problems(sheet))


# ------------------------------------------------------------------ 3. the type scale

SIZES = {"12px", "13px", "15px", "26px", "30px", "14px", "20px",
         "var(--fs-small)", "var(--fs-body)", "var(--fs-h1)", "var(--fs-kpi)", "var(--fs-nav)",
         "var(--nav-brand-size)"}


def size_problems(css: str) -> list[str]:
    return [f"{s}: font-size {v}" for s, body in _rules(css)
            if (v := _declared(body, "font-size")) is not None and v not in SIZES]


def test_every_font_size_is_on_the_scale(examined):
    sizes = [s for s, body in _rules(_sheet()) if _declared(body, "font-size")]
    examined(len(sizes), "rules that set a font size")
    assert size_problems(_sheet()) == []


def test_the_scale_check_names_a_size_off_the_scale(examined):
    examined(1, "planted size")
    assert size_problems(_sheet() + ".later{font-size:13.5px}") == [".later: font-size 13.5px"]


# ------------------------------------------------------------------ 4. every chip keeps its words

@pytest.fixture(scope="module")
def demo_pages(tmp_path_factory) -> dict[str, str]:
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("f0") / "demo"
    build_public(folder)
    root = folder / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}


#: A chip as each page draws it: a pill, a rung's or a badge's state word, the "No records" chip.
_CHIP_MARKUP = (re.compile(r'<span class="pill[^"]*">(.*?)</span>', re.S),
                re.compile(r'<tr data-(?:rung|badge)="[^"]*" data-state="[^"]*"><td>.*?</td><td><span>(.*?)</span>',
                           re.S),
                re.compile(r'<p data-state="no-records">(.*?)</p>', re.S))


def test_every_chip_on_every_demo_page_carries_its_words(demo_pages, examined):
    chips = [(rel, m) for rel, page in demo_pages.items() for rx in _CHIP_MARKUP
             for m in rx.findall(page)]
    kinds = {rx.pattern for rx in _CHIP_MARKUP for page in demo_pages.values() if rx.search(page)}
    examined(len(chips), "chips on the demo's pages")
    assert len(kinds) == len(_CHIP_MARKUP), "each kind of chip is drawn somewhere in the demo"
    empty = [(rel, m) for rel, m in chips if not re.sub(r"<[^>]+>", "", m).strip()]
    assert not empty, empty[:5]


def placement_problems(css: str) -> list[str]:
    """Each chip tone added since the four: styled wherever a chip can sit -- the console's own pages
    (.cp), the viewer-framed pages (.shell .page: the runs lists, a run's pages), and a run's head."""
    out = []
    for tone in ("dec", "fd", "ca"):
        if not re.search(rf":is\(\.cp,\.shell \.page\) \.{tone}\{{", css):
            out.append(f".{tone}: not styled on the console's and the viewer-framed pages")
        if not re.search(rf"\[data-section=run-head\] \.{tone}\{{", css):
            out.append(f".{tone}: not styled in a run's head")
    return out


def test_each_new_chip_tone_is_styled_wherever_a_chip_sits(examined):
    examined(3, "chip tones")
    assert placement_problems(_sheet()) == []


def test_sabotage_a_tone_missing_from_the_run_head_is_named(examined):
    examined(1, "planted sheet")
    sheet = re.sub(r"\[data-section=run-head\] \.fd\{", "[data-section=run-head] .x-fd{", _sheet())
    assert ".fd: not styled in a run's head" in placement_problems(sheet)
