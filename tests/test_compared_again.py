"""A comparison page under an earlier console's name says when its pair has been compared again.

A comparison's name takes in the SDK build that made it, so the same pair compared under a new
build gets a new name, and both pages are kept. The earlier page then says so, and links to the
newer one; it is found by the key the pair has under this console's build, never by time. A page
whose pair has no comparison under this build, and the newer page itself, say nothing of it.
"""
from __future__ import annotations

import html
import re
from dataclasses import replace

from tests.test_compare_unchecked_side import _compared, _diff_page, _load

#: An SDK build this console is not running: an earlier console's.
EARLIER = {"sdk_distribution_version": "0.6.0", "sdk_build_digest": "wheel:" + "0" * 64}


def _earlier(comparison, store):
    """The same pair's comparison as an earlier console stored it: its record, under its own name."""
    from onetrace_console.compare import comparison_key
    key = comparison_key(comparison.bundle_sha_a, comparison.bundle_sha_b, EARLIER["sdk_distribution_version"],
                         EARLIER["sdk_build_digest"])
    old = replace(comparison, key=key, **EARLIER)
    store.put_comparison(old)
    return old


def _line(page: str) -> list[tuple[str, str]]:
    """Each compared-again line: its words, and where it links."""
    return [(" ".join(html.unescape(re.sub(r"<[^>]+>", " ", m.group(1))).split()), m.group(2))
            for m in re.finditer(r'<p data-section="compared-again">(.*?href="([^"]*)".*?)</p>', page, re.S)]


def test_the_earlier_page_says_its_pair_was_compared_again_and_links_the_newer(tmp_path, examined):
    from onetrace_console.render import COMPARED_AGAIN
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-2": "day-2"})
    newer = _compared(store, runs["day-1"], runs["day-2"])
    old = _earlier(newer, store)
    examined(2, "comparison pages of one pair: an earlier console's and this one's")
    assert old.key != newer.key
    assert _line(_diff_page(old, store)) == [(f"{COMPARED_AGAIN}: diff/{newer.key}.html", f"/diff/{newer.key}.html")]
    assert _line(_diff_page(newer, store)) == []


def test_a_page_whose_pair_has_no_new_name_says_nothing(tmp_path, examined):
    """Day 2 against day 1 is held only under the earlier build: no line, though this build compared
    another pair (day 1 against day 2)."""
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-2": "day-2"})
    _compared(store, runs["day-1"], runs["day-2"])
    reverse = _compared(store, runs["day-2"], runs["day-1"])
    old = _earlier(reverse, store)
    (store.root / "comparisons" / f"{reverse.key}.json").unlink()
    examined(1, "an earlier console's page whose pair this build has not compared")
    assert store.get_comparison(reverse.key) is None
    assert _line(_diff_page(old, store)) == []


def test_sabotage_a_line_drawn_for_any_comparison_under_this_build_is_caught(tmp_path, monkeypatch, examined):
    """The line drawn whenever this build holds some comparison, whatever its pair: the page of a pair with
    no new name then gets one, and the test above would fail."""
    from onetrace_console import render
    from onetrace_console.compare import sdk_build_digest
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-2": "day-2"})
    _compared(store, runs["day-1"], runs["day-2"])
    reverse = _compared(store, runs["day-2"], runs["day-1"])
    old = _earlier(reverse, store)
    (store.root / "comparisons" / f"{reverse.key}.json").unlink()

    def any_under_this_build(comparison, store):
        if comparison.sdk_build_digest == sdk_build_digest():
            return None
        return next((c for c in store.comparisons() if c.sdk_build_digest == sdk_build_digest()), None)
    monkeypatch.setattr(render, "compared_again", any_under_this_build)
    examined(1, "planted rule")
    assert _line(_diff_page(old, store)) != []
