"""The console names the pair's folders in the SDK's words in the forms the SDK
writes them -- as given, and with backslashes doubled (the SDK's text escapes them one-to-one since
0.2.0) -- stated, not through the viewer's display(); case-insensitively on Windows. On every OS: a
folder whose path holds a backslash, as every Windows path does."""
from __future__ import annotations

import pytest


@pytest.fixture
def folder(tmp_path):
    made = tmp_path / "bs\\dir" / "candidate"
    made.mkdir(parents=True)
    return str(made)


def test_a_backslashed_folder_is_named_in_the_sdks_escaped_form(folder, monkeypatch):
    import onetrace_console.viewer.page as page

    from onetrace_console.render import _named_folder
    sdk_text = f"refused — does not verify: ({folder.replace(chr(92), chr(92) * 2)})"
    #: Whatever the viewer's display() does, as test_one_to_one's "as it was" rendering checks.
    monkeypatch.setattr(page, "display", lambda text, **_: text)
    assert _named_folder(sdk_text, folder, "(the candidate run's folder)") == (
        "refused — does not verify: ((the candidate run's folder))")


def test_as_given_too(folder):
    from onetrace_console.render import _named_folder
    assert _named_folder(f"in {folder} now", folder, "X") == "in X now"


def test_case_insensitively_on_windows(folder, monkeypatch):
    import onetrace_console.render as render
    monkeypatch.setattr(render, "_FOLDERS_CASE_INSENSITIVE", True)
    sdk_text = folder.upper().replace("\\", "\\\\")
    assert render._named_folder(sdk_text, folder, "X") == "X"
    monkeypatch.setattr(render, "_FOLDERS_CASE_INSENSITIVE", False)
    assert render._named_folder(sdk_text, folder, "X") == sdk_text, "case kept off Windows"
