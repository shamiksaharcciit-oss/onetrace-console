"""`explain.command()` says what it does (console 0.8.0): the `onetrace-explain` of this interpreter's own
environment, in its scripts folder or beside it, and never one found only on `PATH`; None where neither
place holds it. The panel then says so with the install line for this environment."""

from __future__ import annotations

import inspect
import sys
from html import unescape

import pytest


def test_the_docstring_says_only_this_environment_s_command_is_used(examined):
    from onetrace_console import explain

    doc = " ".join(inspect.getdoc(explain.command).split())
    examined(1, "docstring")
    assert "never one found only on `PATH`" in doc and "falls back" not in doc, doc


def test_one_only_on_path_is_not_taken(tmp_path, examined):
    from onetrace_console import explain

    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "onetrace-explain").write_bytes(b"")
    found = explain.find(False, str(tmp_path / "scripts"), str(tmp_path / "bin" / "python"))
    examined(1, "lookup")
    assert found is None


def test_the_panel_gives_this_environment_s_install_lines_where_it_is_absent(monkeypatch, examined):
    from onetrace_console import explain
    from onetrace_console.neighbours.pages import install_lines

    monkeypatch.setattr(explain, "command", lambda: None)
    got = explain.not_installed_lines()
    lines = install_lines(explain.EXPLAIN_PACKAGE)
    examined(len(lines), "install lines")
    text = unescape(got)
    assert 'data-explain="install"' in got and explain.INSTALL_HERE in text
    assert all(line in text for _, line in lines) and sys.executable in text


@pytest.mark.parametrize(
    "python",
    [r"C:\Users\ana\env\Scripts\python.exe", r"C:\Program Files\Python312\python.exe"],
    ids=["a bare path", "a path with a space"],
)
def test_on_windows_the_panel_s_install_line_names_the_python_as_it_is(monkeypatch, python, examined):
    """A Windows-shaped path, on every platform: each line the panel gives holds the interpreter's path with its
    backslashes as they are, escaped for HTML only, never doubled."""
    from onetrace_console import explain
    from onetrace_console.neighbours.pages import install_lines

    monkeypatch.setattr(explain, "command", lambda: None)
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", python)
    got = unescape(explain.not_installed_lines())
    lines = install_lines(explain.EXPLAIN_PACKAGE)
    examined(len(lines), "install lines for a Windows path")
    assert lines and all(line in got for _, line in lines), (got, lines)
    assert "\\\\" not in got
