"""A recorded input that differs is the first thing a comparison says, and its kept text reads.

When the first difference's stage has an own recorded input whose digest differs between the two
runs (kept or not), the summary card names it first -- "input {name} changed: {old} -> {new}",
each digest by its first 12 hex characters -- with a link to the changed lines where the text diff
on the page draws its kept text; and it says nothing of the difference being unexplained (no
"not established" line, no "no recorded cause" sentence). "Other runs that recorded the same value"
matches other runs on that input's digest. A kept text input is drawn as a line diff of its text,
real line breaks, escaped for HTML, beside the outputs; an input not kept stays digest-only.

Held with the demo's P7 pair (one logger reading changed) and three P7 runs recorded here, and the
P6 pair whose frame differs, not kept.
"""
from __future__ import annotations

import hashlib
import re
from html import unescape

from tests.test_compare_page import _page, demo  # noqa: F401
from tests.test_times_and_words import _console

P7 = ("p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed")
P6 = ("p6-36-fill-baseline", "p6-38-fill-below-reject-line")


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _short(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:12]


def card_problems(page: str, name: str, old: str, new: str, linked: bool) -> list[str]:
    """The card names the input first, links its changed lines where `linked`, and says nothing
    of the difference being unexplained."""
    card = re.search(r'<section data-section="first-difference">.*?</section>', page, re.S)
    if card is None:
        return ["no summary card"]
    what = re.search(r'<div data-part="what">(.*?)</div>', card.group(0), re.S).group(1)
    first = re.match(r"<p[^>]*>(.*?)</p>", what, re.S)
    out = []
    if first is None or not _text(first.group(1)).startswith(f"input {name} changed: {old} -> {new}"):
        out.append(f"the card does not open with the input: {_text(first.group(1)) if first else None}")
    link = re.search(r'<a href="#([^"]+)" data-link="changed-lines">', what)
    if linked and (link is None or f'id="{link.group(1)}"' not in page):
        out.append("no link to the changed lines on the page")
    if not linked and link is not None:
        out.append("a link where no kept text is drawn")
    said = _text(card.group(0))
    for words in ("not established", "No recorded cause", "caused", "because"):
        if words in said:
            out.append(f"the card says {words!r}")
    if "no recorded cause" in said.lower():
        out.append("the card says the SDK's no-recorded-cause sentence")
    return out


def test_the_p7_card_names_the_changed_logger_first(demo, examined):  # noqa: F811
    from onetrace_console.demo_store import cold_chain
    page = _page(demo, *P7)
    examined(1, "comparison page")
    assert card_problems(page, "logger", _short(cold_chain.logger_bytes(False)),
                         _short(cold_chain.logger_bytes(True)), linked=True) == []


def test_the_p7_kept_logger_is_a_line_diff_with_real_line_breaks(demo, examined):  # noqa: F811
    page = _page(demo, *P7)
    examined(1, "comparison page")
    block = re.search(r'<div data-kept-diff id="input-fill_gaps-logger">(.*?)</pre>', page, re.S)
    assert block is not None
    rows = [_text(r) for r in block.group(1).split("<pre data-hunk>", 1)[1].split("\n")]
    assert "6 - 30,4.6" in rows and "6 + 30,9.4" in rows, rows
    assert "\\u000a" not in page and "\\n" not in block.group(1)
    assert "1 line removed · 1 added" in _text(block.group(1))


def test_an_input_not_kept_stays_digest_only(demo, examined):  # noqa: F811
    page = _page(demo, *P6)
    examined(1, "comparison page")
    assert "data-kept-diff" not in page
    assert re.search(r"<p data-input>input frame\.json \([^)]*\) changed: [0-9a-f]{12} -&gt; [0-9a-f]{12}", page)


def _three_p7_runs(root):
    """A baseline, a candidate with the changed logger, and a third run recorded with the
    candidate's logger."""
    from onetrace_console.demo_store import cold_chain
    runs = root / "runs"
    for name, changed in (("a", False), ("b", True), ("c", True)):
        cold_chain.main(runs / name, f"cc-{name}", changed)
    return runs


def test_the_lookup_finds_a_third_run_with_the_same_input_digest(tmp_path, examined):
    from onetrace_console.demo_store import cold_chain
    _store, pages, loaded = _console(tmp_path, _three_p7_runs(tmp_path), compare=("a", "b"))
    page = (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")
    examined(1, "comparison page")
    panel = re.search(r'<section data-section="same-change">.*?</section>', page, re.S).group(0)
    said = _text(panel)
    assert "the same input logger digest" in said, said
    assert re.findall(r'<li data-run="[^"]*">', panel) and "cc-c" in said and "cc-a" not in said, said
    assert "2 of 3 stored runs" in said, said
    assert card_problems(page, "logger", _short(cold_chain.logger_bytes(False)),
                         _short(cold_chain.logger_bytes(True)), linked=True) == []


# ------------------------------------------------------------------ sabotages

def test_sabotage_each_card_fault_is_named(demo, examined):  # noqa: F811
    from onetrace_console.demo_store import cold_chain
    page = _page(demo, *P7)
    old, new = _short(cold_chain.logger_bytes(False)), _short(cold_chain.logger_bytes(True))
    line = re.search(r"<p data-input-changed>.*?</p>", page).group(0)
    planted = {
        "not first": page.replace(line, "", 1).replace('</div><div data-part="what">',
                                                        '</div><div data-part="what"><p>x</p>' + line, 1),
        "no link": page.replace('data-link="changed-lines"', "", 1),
        "not established": page.replace("<pre data-section=\"headline-command\">",
                                        "<p>Why it differs is not established by this evidence.</p>"
                                        "<pre data-section=\"headline-command\">", 1),
        "a cause": page.replace(line, line.replace("changed:", "caused it:"), 1),
    }
    examined(len(planted), "planted pages")
    for name, bad in planted.items():
        assert card_problems(bad, "logger", old, new, linked=True), name


def test_an_input_not_kept_is_named_first_with_no_link(demo, examined):  # noqa: F811
    from onetrace_console.demo_store import fill_inspection
    page = _page(demo, *P6)
    examined(1, "comparison page")
    assert card_problems(page, "frame.json", _short(fill_inspection.frame_bytes("full")),
                         _short(fill_inspection.frame_bytes("low")), linked=False) == []
