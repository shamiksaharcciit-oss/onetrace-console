"""Read an emitted page the way the tests need to: whose words, at which layer."""
from __future__ import annotations

import re
from html.parser import HTMLParser

VOID = {"meta", "br", "img", "link", "input", "hr"}
#: Elements that separate words. Inline elements (q, span, code, strong) do not.
BLOCK = {"p", "div", "li", "ul", "h1", "h2", "h3", "section", "article", "tr", "td", "th",
         "header", "footer", "summary", "details", "pre", "main", "br", "table", "title"}


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.own: list[str] = []          # the generator's own words, any layer 1–2
        self.all_text: list[str] = []     # every text node outside style/script

    def _break(self) -> None:
        self.all_text.append(" ")
        self.own.append(" ")

    def handle_starttag(self, tag, attrs):
        if tag in BLOCK:
            self._break()
        if tag not in VOID:
            self.stack.append((tag, dict(attrs)))

    def handle_endtag(self, tag):
        if tag in BLOCK:
            self._break()
        while self.stack:
            t, _ = self.stack.pop()
            if t == tag:
                break

    def handle_data(self, data):
        tags = [t for t, _ in self.stack]
        if "style" in tags or "script" in tags:
            return
        self.all_text.append(data)
        quoted = any("data-words" in a for _, a in self.stack)
        deep = any(a.get("data-layer") in ("3", "4") for _, a in self.stack)
        if not quoted and not deep:
            self.own.append(data)


def own_words(html: str) -> str:
    """Text the generator wrote itself, outside quotations and outside layers 3–4."""
    r = _Reader()
    r.feed(html)
    return re.sub(r"\s+", " ", "".join(r.own))


def visible_text(html: str) -> str:
    r = _Reader()
    r.feed(html)
    return re.sub(r"\s+", " ", "".join(r.all_text))


def section(html: str, name: str) -> str:
    """The HTML of one `data-section` element (first match), for scoped assertions."""
    m = re.search(r'<(section|p) [^>]*data-section="' + re.escape(name) + r'"', html)
    assert m, f"no section {name!r} on the page"
    tag = m.group(1)
    depth, i = 0, m.start()
    for t in re.finditer(r"<(/?)" + tag + r"\b[^>]*>", html[m.start():]):
        depth += -1 if t.group(1) else 1
        if depth == 0:
            return html[m.start():m.start() + t.end()]
    raise AssertionError(f"section {name!r} is not closed")
