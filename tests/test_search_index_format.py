"""The search page where the run index is not one this console reads: it says why, and how to get one.

A store root with no index says so. One whose index is in an earlier format says so, and, on a public
console, which reads its build's index and never writes one, to build it again with this release; on a
local console, that the console writes it again itself. A later format is named as one it does not read.
Each rule has its own sabotage below.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from onetrace_console import __version__, run_index, search_page


def _said(page: str) -> str:
    m = re.search(r'<p data-search="no-index">(.*?)</p>', page, re.S)
    return html.unescape(m.group(1)) if m else ""


def _root(tmp_path, fmt):
    if fmt is not None:
        (tmp_path / run_index.FILE_NAME).write_text(json.dumps({"format": fmt, "runs": []}), encoding="utf-8")
    return tmp_path


def _page(root, public: bool) -> str:
    index = run_index.read(root)
    return search_page.body(index, "verdict:PASS", "", None, public=public,
                            found=None if index is not None else run_index.format_of(root))


@pytest.mark.parametrize("public", [True, False], ids=["public", "local"])
def test_no_index_says_none_yet(tmp_path, public, examined):
    examined(1, "store root without an index")
    assert _said(_page(_root(tmp_path, None), public)) == search_page.NO_INDEX


def test_an_earlier_format_on_a_public_console_says_to_build_it_again_with_this_release(tmp_path, examined):
    earlier = "onetrace-console-run-index/0.1"
    examined(1, "public build with an earlier index")
    assert _said(_page(_root(tmp_path, earlier), True)) == (
        f"This build's index of its runs is in an earlier format, {earlier}; build it again with "
        f"onetrace-console {__version__}.")


def test_an_earlier_format_on_a_local_console_says_it_writes_it_again(tmp_path, examined):
    earlier = "onetrace-console-run-index/0.1"
    examined(1, "local store with an earlier index")
    assert _said(_page(_root(tmp_path, earlier), False)) == search_page.EARLIER_LOCAL.format(found=earlier)


@pytest.mark.parametrize("fmt", ["onetrace-console-run-index/9.9", "something-else/0.1"])
def test_a_later_or_unknown_format_is_named_as_one_it_does_not_read(tmp_path, fmt, examined):
    examined(1, "index of another format")
    assert not run_index.earlier(fmt)
    assert _said(_page(_root(tmp_path, fmt), True)) == search_page.OTHER_FORMAT.format(found=fmt)


def test_the_current_format_is_searched_not_refused(tmp_path, examined):
    examined(1, "index of this console's format")
    assert run_index.format_of(_root(tmp_path, run_index.FORMAT)) == run_index.FORMAT
    assert _said(_page(tmp_path, True)) == ""


def test_sabotage_an_earlier_index_said_as_none_yet_is_caught(tmp_path, monkeypatch, examined):
    """The page told nothing of the format: an earlier build then reads as if it held no index, with no
    word of building it again."""
    monkeypatch.setattr(search_page, "no_index", lambda found, *, public: search_page.NO_INDEX)
    examined(1, "planted message")
    said = _said(_page(_root(tmp_path, "onetrace-console-run-index/0.1"), True))
    assert "build it again" not in said
