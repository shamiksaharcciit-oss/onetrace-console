"""The Compare page's polish before release, on the demo's headline pair:

- the headline says what differs in one plain paragraph: whether both runs' records agree, the
  stages the same before it, each differing setting by its short name with both values (never
  its whole path, never a digest), that the output differs, and how many stages after it changed;
- every command on the page is one a reader can type: the SDK's own, over the two run folders --
  never the stored placeholder form;
- a setting is named by its short name, its whole path in its tooltip; a recorded fingerprint
  (a digest) that differs is kept whole under Details, not in the table, the sentence or a box;
- each stage's text diff is folded, only the first difference open; the stage table of whole
  digests is folded under Details.

Each check has its sabotage.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_compare_page import HEADLINE, _annotations, demo  # noqa: F401

DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _both_views(demo, base: str, cand: str) -> str:  # noqa: F811
    """The comparison page's two views together: its stage table is on "Proof"."""
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (ids[base], ids[cand]))
    diff = folder / "store" / "pages" / "diff"
    return ((diff / f"{c.key}.html").read_text(encoding="utf-8")
            + (diff / f"{c.key}-proof.html").read_text(encoding="utf-8"))


def polish_problems(page: str, annotations: list[dict]) -> list[str]:
    out = []
    card = re.search(r'<section data-section="first-difference">.*?</section>', page, re.S)
    sentence = _text(re.search(r'<div data-part="what"><p>(.*?)</p>', card.group(0), re.S).group(1))
    first = next(n for n in annotations if n["differs"])
    for field, (old, new) in first["differs"].items():
        digest = DIGEST.fullmatch(str(old)) or DIGEST.fullmatch(str(new))
        short = field.rsplit(".", 1)[-1]
        if digest and (old in sentence or new in sentence):
            out.append(f"a digest in the headline: {field}")
        if not digest and f"{short}: {old} → {new}" not in sentence:
            out.append(f"the headline lacks {short}: {old} → {new}")
        if "." in field and field in sentence:
            out.append(f"the headline names the whole path {field}")
    for cmd in re.findall(r"<code>([^<]*onetrace[^<]*)</code>", page):
        cmd = unescape(cmd)
        if "RUN_A" in cmd or "--out OUT" in cmd or "python -m onetrace" in cmd:
            out.append(f"a placeholder command: {cmd}")
    settings = re.search(r'<section data-section="settings-changed">.*?</section>', page, re.S).group(0)
    main, _, details = settings.partition('<details data-section="settings-details">')
    if DIGEST.search(main):
        out.append("a digest in the settings table, outside Details")
    for note in annotations:
        for field, (old, new) in note["differs"].items():
            where = details if DIGEST.fullmatch(str(old)) or DIGEST.fullmatch(str(new)) else main
            if f'data-setting-path="{field}" title="{field}">{field.rsplit(".", 1)[-1]}<' not in where:
                out.append(f"{field} is not named by its short name in its place")
    graph = re.search(r'<svg class="graph".*?</svg>', page, re.S).group(0)
    if DIGEST.search(graph) or "assertions.constants." in graph:
        out.append("a box quotes a digest or a whole path")
    folds = re.findall(r'<details data-node-fold="([^"]+)"( open)?>', page)
    opened = [n for n, o in folds if o]
    if len(opened) != 1:
        out.append(f"{len(opened)} stage diffs open, not only the first difference")
    if '<details data-section="stage-table" data-verb="diff">' not in page:
        out.append("the stage table is not folded")
    return out


def test_the_compare_page_is_polished(demo, examined):  # noqa: F811
    page = _both_views(demo, *HEADLINE)
    annotations = _annotations(demo, *HEADLINE)
    examined(1, "comparison page")
    assert polish_problems(page, annotations) == []
    folds = re.findall(r'<details data-node-fold="([^"]+)"( open)?>', page)
    assert [n for n, o in folds if o] == ["split"], folds


def test_sabotage_each_unpolished_form_is_named(demo, examined):  # noqa: F811
    page = _both_views(demo, *HEADLINE)
    annotations = _annotations(demo, *HEADLINE)
    first = next(n for n in annotations if n["differs"])
    field = next(f for f, (o, n) in first["differs"].items() if not DIGEST.fullmatch(str(o)))
    short = field.rsplit(".", 1)[-1]
    planted = {
        "whole path": page.replace(f"{short}: ", f"{field}: ", 1),
        "placeholder": page.replace("<code>onetrace diff runs/", "<code>python -m onetrace diff RUN_A RUN_B --out OUT runs/", 1),
        "digest out of Details": page.replace('<details data-section="settings-details">',
                                               '<p>sha256:' + "a" * 64 + '</p><details data-section="settings-details">', 1),
        "all folds open": re.sub(r'(<details data-node-fold="[^"]+")>', r"\1 open>", page),
        "table unfolded": page.replace('<details data-section="stage-table" data-verb="diff">', "<div>", 1),
    }
    examined(len(planted), "planted pages")
    for name, bad in planted.items():
        assert bad != page, name
        assert polish_problems(bad, annotations), name


def test_a_folds_heading_stays_on_its_markers_line(examined):
    """A stage's fold heads its summary: drawn inline, its heading beside the fold's marker rather
    than on a line of its own under it."""
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    examined(1, "stylesheet")
    assert ".cp details[data-node-fold]>summary>h3{display:inline;margin:0}" in css
    assert ".cp details[data-node-fold]>summary>h3{display:inline" not in css.replace(
        ".cp details[data-node-fold]>summary>h3{display:inline;margin:0}", ""), "said once"


def test_every_setting_arrow_is_one_arrow(demo, examined):  # noqa: F811
    """`→` wherever the console says a setting changed: the graph's boxes, the changes table, the
    sentence, the text diff's settings lines. (The SDK's own quoted words stay as it wrote them.)"""
    page = _both_views(demo, *HEADLINE)
    graph = re.search(r'<svg class="graph".*?</svg>', page, re.S).group(0)
    cells = re.findall(r'<td[^>]*data-section="settings"[^>]*>(.*?)</td>', page, re.S)
    lines = re.findall(r"<p data-settings>(.*?)</p>", page, re.S)
    examined(1 + len(cells) + len(lines), "places a setting is said")
    for where in [graph, *cells, *lines]:
        assert " -&gt; " not in where and " -> " not in where, where[:200]
    assert "chunk_size 1024 → 512" in graph
