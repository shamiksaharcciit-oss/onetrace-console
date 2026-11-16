"""The 0.8.0 notes say what was exposed before 0.8.0 and that 0.8.0 fixes it.

A folder console started with a configuration file answered the watched folder's state to anyone, before any sign-in
was asked for, from 0.1.1 to 0.7.0; and a request that raised was answered with the exception's words. The release's
notes name both under Security: what was exposed, in which versions, under which setup, and that 0.8.0 fixes it.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _section() -> str:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.8.0]")
    return text[start : text.index("\n## [", start + 1)]


def test_the_release_notes_have_a_security_part_naming_the_watched_folder_s_state(examined):
    section = _section()
    examined(1, "0.8.0's notes")
    assert "\n### Security\n" in section
    security = section[section.index("\n### Security\n") :].split("\n### ", 2)[1]
    for words in (
        "`GET /v1/folder`",
        "0.1.1 to 0.7.0",
        "configuration file",
        "the watched folder's path on the server",
        "the names of runs",
        "how many runs it had taken in",
        "its last 20 error lines",
        "0.8.0 answers it after the role check",
    ):
        assert words in security, words


def test_the_security_part_names_the_server_error_s_words_too(examined):
    security = _section().split("\n### Security\n", 1)[1].split("\n### ", 1)[0]
    examined(1, "Security part")
    for words in ("`POST /signin`", "a path on the server", "0.7.0 and earlier", "a short reference"):
        assert words in security, words
