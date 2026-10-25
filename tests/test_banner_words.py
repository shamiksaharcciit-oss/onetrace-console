"""The public banner reads as sentences: the install command ends its own, before "Its runs come from".

The banner's parts are drawn inline, the command in code type: with nothing between the command and
the next sentence it read "pip install onetrace-console Its runs come from…". Every public page
carries the one banner (`frame.banner`), so it is held here once.
"""
from __future__ import annotations

import re
from html import unescape


def banner_problems(html: str) -> list[str]:
    from onetrace_console.public import BANNER, BANNER_COMMAND
    text = " ".join(unescape(re.sub(r"<[^>]+>", "", html)).split())
    if not text.startswith(f"{BANNER} {BANNER_COMMAND}"):
        return [f"the banner does not open with its words and the command: {text[:80]!r}"]
    after = text[len(f"{BANNER} {BANNER_COMMAND}"):]
    if not after.startswith(". Its runs come from "):
        return [f"the command's sentence does not end before the next: {BANNER_COMMAND}{after[:30]!r}"]
    return []


def test_the_install_command_ends_its_sentence(examined):
    from onetrace_console.frame import banner
    examined(1, "banner")
    assert banner_problems(banner()) == []


def test_sabotage_the_command_run_into_the_next_sentence_is_named(examined):
    from onetrace_console.frame import banner
    examined(1, "planted banner")
    assert banner_problems(banner().replace("</code>. ", "</code> ")) != []
