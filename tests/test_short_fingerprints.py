"""Fingerprints in text and tables, short: the first 12 hex characters, the whole value as plain,
selectable text in a closed Details beside it -- no script, nothing to press but the fold.

1. No page of the public demo shows a whole fingerprint as running text or in a table, outside what
   stays whole: a fold's own value, the verifier's output as it printed it (its rows and summary),
   the record as written (the verbatim layers), and the page's own fingerprint in its footer, which
   a saved copy is checked against.
2. Each short form is the start of the whole value its fold holds.
3. No fold sits inside a paragraph (a parser would close the paragraph at it).
4. Every short form on a page -- in a fold's summary, in running text, in the graph, in a settings
   cell -- has its whole value on the same page: a run of hex characters cut with "…", and, where
   the form keeps the end too, its last six, is the start (and end) of a whole value the page holds.

Each check has its sabotage.
"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser

import pytest

from tests.test_public_mode import built  # noqa: F401

_WHOLE = re.compile(r"(?:sha256:)?[0-9a-f]{64}")
_VOID = {"meta", "br", "img", "link", "input", "hr", "rect", "path", "area", "base", "col", "embed",
         "source", "track", "wbr"}


class _Reader(HTMLParser):
    """Each whole fingerprint a reader sees as text, by where it is; and each fold inside a <p>."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.shown, self.in_p = [], [], 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "details" and a.get("class") == "fingerprint" and any(t == "p" for t, _ in self.stack):
            self.in_p += 1
        if tag not in _VOID:
            self.stack.append((tag, a))

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()[0] == tag:
                break

    def handle_data(self, data):
        if any(t in ("details", "pre", "script", "style", "title") or a.get("data-layer") in ("3", "4")
               or (t == "code" and a.get("class") == "fp") for t, a in self.stack):
            return
        self.shown += [">".join(t for t, _ in self.stack[-3:])] * len(_WHOLE.findall(data))


def page_problems(html: str) -> list[str]:
    r = _Reader()
    r.feed(html)
    out = [f"a whole fingerprint shown in {where}" for where in dict.fromkeys(r.shown)]
    if r.in_p:
        out.append(f"{r.in_p} folds inside a paragraph")
    for short, whole in re.findall(r'<details class="fingerprint"[^>]*><summary class="mono">([^<]*)…</summary>'
                                   r'<span class="mono" data-fingerprint="whole">([^<]*)</span>', html):
        if not whole.startswith(short) or len(short.removeprefix("sha256:")) != 12:
            out.append(f"{short}… is not the start of {whole}")
    return out


#: A short form as any part of a page draws one: hex characters cut with "…", the end kept or not.
_SHORT = re.compile(r"(?<![0-9a-f])((?:sha256:)?[0-9a-f]{8,63})…(?:([0-9a-f]{6})(?![0-9a-f]))?")


def short_forms_without_whole(html: str) -> tuple[int, list[str]]:
    """How many short forms the page shows, and each one whose whole value is not on the page."""
    text = unescape(html)
    wholes = set(_WHOLE.findall(text))
    found = list(_SHORT.finditer(text))
    return len(found), [m.group(0) for m in found
                        if not any(w.startswith(m.group(1)) and w.endswith(m.group(2) or "") for w in wholes)]


@pytest.fixture(scope="module")
def pages(built):  # noqa: F811
    root = built / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}


def test_no_page_shows_a_whole_fingerprint_in_its_text_or_tables(pages, examined):
    folds = sum(p.count('<details class="fingerprint"') for p in pages.values())
    examined(folds, "fingerprints shown short, each with its fold")
    assert {n: page_problems(p) for n, p in pages.items() if page_problems(p)} == {}


@pytest.mark.parametrize("what", ["a whole value in a table cell", "a short form of another value",
                                  "a fold inside a paragraph"])
def test_sabotage_each_fault_is_named(pages, what, examined):
    one = re.compile(r'<details class="fingerprint"[^>]*><summary class="mono">')
    name, page = next((n, p) for n, p in sorted(pages.items()) if one.search(p))
    whole = re.search(r'data-fingerprint="whole">([^<]*)<', page).group(1)
    planted = {
        "a whole value in a table cell": page.replace("</body>", f"<table><tr><td>{whole}</td></tr></table></body>", 1),
        "a short form of another value": re.sub(r'(<details class="fingerprint"[^>]*><summary class="mono">)',
                                                r"\g<1>0", page, count=1),
        "a fold inside a paragraph": page.replace("</body>", '<p>See <details class="fingerprint"><summary class="mono">'
                                                             f'{whole[:19]}…</summary></details></p></body>', 1),
    }[what]
    examined(1, f"planted page: {what}")
    assert planted != page and page_problems(planted) != [], what


def test_every_short_form_has_its_whole_value_on_the_same_page(pages, examined):
    counted = {n: short_forms_without_whole(p) for n, p in pages.items()}
    examined(sum(c for c, _ in counted.values()), "short forms, each read back to a whole value on its page")
    assert sum(c for c, _ in counted.values()) > 0, "no short form on any page"
    assert {n: missing for n, (_c, missing) in counted.items() if missing} == {}


def test_sabotage_a_short_form_whose_whole_value_is_gone_is_named(pages, examined):
    """Every copy of one fold's whole value taken off the page; its short form stays."""
    name, page = next((n, p) for n, p in sorted(pages.items()) if 'data-fingerprint="whole"' in p)
    whole = re.search(r'data-fingerprint="whole">([^<]*)<', page).group(1)
    hexes = whole.removeprefix("sha256:")
    planted = page.replace(hexes, "f" * 64)
    examined(1, f"planted page: {name}")
    assert planted != page
    assert any(m.startswith(whole[:len(whole) - 52]) for m in short_forms_without_whole(planted)[1]), name
