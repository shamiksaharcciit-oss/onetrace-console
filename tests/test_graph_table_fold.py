"""A graph comparison's table: a node's annotation and its "Each fingerprint in full" fold are two
elements, with visible space between them, in light and dark.

The fold followed the annotation's last word inline, so the two read as one line ("...differsEach
fingerprint in full"). The annotation is now its own element and the fold a block below it, set
apart by a margin and a rule drawn in a theme colour, which both themes define.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

FINGERPRINT = "sha256:" + "ab" * 32
LABEL = "Each fingerprint in full"


def _table(annotations: list[str]) -> str:
    from onetrace_console.render import _dag_table
    row = SimpleNamespace(verdict="FIRST DIFFERENCE", node="retrieve#1", index_baseline="2",
                          index_candidate="2", annotations=annotations)
    return _dag_table(SimpleNamespace(ladder=[row]), "diff")


def _cell(table: str) -> str:
    found = re.findall(r'<td[^>]*data-section="annotations">(.*?)</td>', table, re.S)
    assert len(found) == 1, found
    return found[0]


def test_the_annotation_and_the_fold_are_separate_elements(examined):
    cell = _cell(_table([f"output digest differs: {FINGERPRINT} vs {FINGERPRINT[:-2]}cd"]))
    examined(1, "annotations cell")
    m = re.fullmatch(r'<span data-part="annotation">(.*?)</span>'
                     r'<div data-part="fold"><details class="fingerprint">'
                     r"<summary>(.*?)</summary>.*</details></div>", cell, re.S)
    assert m, cell
    assert m.group(1).rstrip().endswith("cd…</span>") or "…" in m.group(1), m.group(1)
    assert m.group(2) == LABEL


def test_an_annotation_with_no_fingerprint_has_no_fold(examined):
    cell = _cell(_table(["settings: chunk_size"]))
    examined(1, "annotations cell")
    assert cell == '<span data-part="annotation">settings: chunk_size</span>', cell


def test_the_fold_is_set_apart_in_both_themes(examined):
    """The page's rule: the fold a block, with a margin above it and a rule in a colour token
    both the light and the dark palette define."""
    from onetrace_console import frame
    from onetrace_console.viewer import tokens
    css = frame.stylesheet().decode("utf-8")
    rule = re.search(r'td\[data-section=annotations\] \[data-part=fold\]\{([^}]*)\}', css)
    examined(1, "stylesheet rule")
    assert rule, "no rule for the fold"
    body = rule.group(1)
    assert "display:block" in body and re.search(r"margin-top:\s*\d", body), body
    token = re.search(r"border-top:1px solid var\(--([\w-]+)\)", body)
    assert token, body
    assert token.group(1) in tokens.palette_names() and token.group(1) in tokens.dark_palette()


def test_a_text_diff_s_input_line_wraps_however_long_its_kept_text(examined):
    """A kept input's text in the text diff is one token as long as the input (the cold-chain
    demo's logger file, say): the line wraps anywhere, so the page is never wider than the screen."""
    from onetrace_console import frame
    css = frame.stylesheet().decode("utf-8")
    examined(1, "stylesheet rule")
    rule = re.search(r"\.cp p\[data-input\]\{([^}]*)\}", css)
    assert rule and "overflow-wrap:anywhere" in rule.group(1)


def _specificity(selector: str) -> tuple[int, int, int]:
    """A plain selector's specificity: ids, then classes and attributes, then elements."""
    bare = re.sub(r"\[[^\]]*\]", " [a] ", selector)
    return (bare.count("#"), len(re.findall(r"\.[\w-]+|\[a\]|:(?!:)[\w-]+", bare)),
            len(re.findall(r"(?:^|[\s>+~])([a-z][\w-]*)", bare)))


def label_size_problems(css: str) -> list[str]:
    """The fold's label is the size of the annotation's words: the table's cells are small, and a
    rule more specific than the page's `details>summary` keeps the label at that size."""
    rules = re.findall(r"([^{}]+)\{([^{}]*)\}", css)
    page = [s.strip() for s, body in rules if s.strip() == ".cp details>summary" and "font-size" in body]
    fold = [s.strip() for s, body in rules
            if "[data-part=fold]" in s and s.strip().endswith("summary") and "font-size:var(--fs-small)" in body]
    if not page:
        return []
    if not fold:
        return ["no rule sizes the fold's label as its cell"]
    return [f"{f} is less specific than {page[0]}" for f in fold if _specificity(f) <= _specificity(page[0])]


def test_the_fold_label_is_the_annotation_s_size(examined):
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    examined(1, "stylesheet")
    assert ".cp table[data-section=changes] td{font-size:var(--fs-small)" in css
    assert label_size_problems(css) == []


def test_sabotage_the_label_drawn_larger_is_named(examined):
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    examined(1, "planted stylesheet")
    planted = css.replace(" [data-part=fold] details>summary{font-size:var(--fs-small)}", " [data-part=fold] x{}", 1)
    assert label_size_problems(planted) == ["no rule sizes the fold's label as its cell"]
