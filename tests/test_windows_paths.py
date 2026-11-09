r"""Console 0.6.1, items 2 and 8 on Windows: a path of this machine as Windows gives it.

`windows-check`, `windows-longpaths` and `windows-noutf8` failed on the same three tests, all on how a
Windows path is drawn. Held here on every platform by the route the Windows run takes: the path planted as
Windows gives it (`PureWindowsPath`; `sys.executable` a Windows interpreter) and, where the console asks,
`_on_windows` answering yes.

1. A path is shown as the operating system gives it, escaped once for HTML: never a record's word, whose
   backslashes are each shown doubled (`words.escape`). Item 8's key line on the setup page and the panel,
   and item 2's Python on the neighbours page.
2. The neighbours page's install line names that Python as Windows' own shells take it: as given, one line
   both Command Prompt and PowerShell run, where it needs no quoting; where it does (`subprocess.list2cmdline`
   puts it in double quotes), two lines, each labelled: "In Command Prompt:" the quoted line, and "In
   PowerShell:" the same line led by `& `, as PowerShell runs a quoted program only after `&`. A POSIX
   shell's single quotes (`shlex.quote`) are not quotes there; elsewhere they are, one line. Each line is run
   through a shell's own parser where the platform has one. The PowerShell line quotes the Python by
   PowerShell's own rules for each character it treats specially: in double quotes, as the Command
   Prompt line does, where nothing in it is special inside them (`(`, `)`, `&`, `;`, `@`, `'`, a space);
   in single quotes, each single quote doubled, where it holds `$`, a backtick or a double quote. Any of
   them gives the two labelled lines; the Command Prompt line is as before.
3. The panel's key line shortens the file's path to its last two parts with the platform's own separator,
   from the path itself: a path holding a space, and the long-path form `\\?\`, are shortened too (a
   pattern over the line left them whole, or kept the `\\?\` before the `…`).
"""
from __future__ import annotations

import html
import sys
from pathlib import PureWindowsPath

import pytest

VAR = "PLANTED_KEY_VARIABLE"
VALUE = "a-key-value-never-shown-5551212"

#: As Windows gives them: a drive, a backslash separator; a space, a non-ASCII letter (windows-noutf8 runs
#: on a non-UTF-8 code page); and the long-path form, `\\?\`, that windows-longpaths can be given.
CONFIGS = {
    "plain": r"C:\Users\runneradmin\AppData\Local\Temp\bt\test_0\config\explain.toml",
    "space and accent": r"C:\Users\Zoë Ng\My Settings\config\explain.toml",
    "long-path form": "\\\\?\\C:\\Users\\runneradmin\\" + "deep\\" * 60 + "config\\explain.toml",
}
PYTHONS = {
    "hosted": r"C:\hostedtoolcache\windows\Python\3.12.10\x64\python.exe",
    "space": r"C:\Program Files\Python312\python.exe",
}


@pytest.fixture
def on_windows(monkeypatch):
    """The console reading its configuration where Windows gives it, with no file read: `path` planted."""
    from onetrace_console import explain, explain_setup

    def plant(path: str, *, state: str = "not set") -> PureWindowsPath:
        where = PureWindowsPath(path)
        monkeypatch.setattr(explain, "_on_windows", lambda: True)
        monkeypatch.setattr(explain, "config_path", lambda: where)
        monkeypatch.setattr(explain_setup, "config_path", lambda: where)
        monkeypatch.setattr(explain, "model_config",
                            lambda: {"provider": "anthropic", "name": "a-model", "key_env": VAR})
        if state == "set":
            monkeypatch.setenv(VAR, VALUE)
        else:
            monkeypatch.delenv(VAR, raising=False)
        return where
    return plant


@pytest.mark.parametrize("name", sorted(CONFIGS))
@pytest.mark.parametrize("state", ["not set", "set"])
def test_the_setup_page_shows_the_file_as_windows_gives_it(on_windows, name, state):
    from onetrace_console import explain_setup
    where = on_windows(CONFIGS[name], state=state)
    page = explain_setup.page(None)
    said = f"onetrace-explain read {where}; its key_env names {VAR}, which is {state} in the environment"
    assert html.escape(said) in page
    assert str(where).replace("\\", "\\\\") not in html.unescape(page)
    assert VALUE not in page


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_the_panels_key_line_shows_backslashes_once(on_windows, name):
    from onetrace_console import explain
    on_windows(CONFIGS[name])
    line = html.unescape(explain.key_lines(explain.key_status(), short=True))
    assert "\\\\" not in line.replace("\\\\?\\", "")
    assert f"its key_env names {VAR}, which is not set in the environment this console started from." in line


@pytest.mark.parametrize("name", sorted(PYTHONS))
def test_the_neighbours_page_shows_the_python_as_given(monkeypatch, name):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", PYTHONS[name])
    page = pages.missing_page()
    assert f'<code data-neighbours="python">{html.escape(PYTHONS[name])}</code>' in page
    assert PYTHONS[name].replace("\\", "\\\\") not in html.unescape(page)


INSTALL = ' -m pip install "onetrace-console[neighbours]"'
CMD, POWERSHELL = "In Command Prompt:", "In PowerShell:"


def _install_paragraphs(page: str) -> list[str]:
    """The page's lines after "With that Python named", as text."""
    import re
    tail = page.split("With that Python named", 1)[1].split("</section>", 1)[0]
    return [html.unescape(re.sub(r"<[^>]+>", "", p)).strip() for p in re.findall(r"<p[^>]*>(.*?)</p>", tail)]


def test_on_windows_a_python_needing_no_quotes_is_one_line_with_no_labels(monkeypatch):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", PYTHONS["hosted"])
    assert pages.install_lines() == [("", PYTHONS["hosted"] + INSTALL)]
    page = pages.missing_page()
    assert f'With that Python named: <code>{html.escape(PYTHONS["hosted"] + INSTALL)}</code>' in page
    assert CMD not in page and POWERSHELL not in page


def test_on_windows_a_quoted_python_is_a_line_for_each_shell_each_labelled(monkeypatch):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", PYTHONS["space"])
    quoted = f'"{PYTHONS["space"]}"' + INSTALL
    assert pages.install_lines() == [(CMD, quoted), (POWERSHELL, "& " + quoted)]
    assert _install_paragraphs(pages.missing_page()) == [f"{CMD} {quoted}", f"{POWERSHELL} & {quoted}"]


def test_elsewhere_the_install_line_is_quoted_for_a_posix_shell(monkeypatch):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: False)
    monkeypatch.setattr(sys, "executable", "/opt/a python/bin/python3")
    assert pages.install_lines() == [("", "'/opt/a python/bin/python3'" + INSTALL)]
    assert CMD not in pages.missing_page()


#: A Python in a folder named with each character PowerShell treats specially, and its PowerShell line.
SPECIAL = {c: rf"C:\Users\a{c}b\python.exe" for c in "()&;$@`'"}


def _powershell_quoted(path: str) -> str:
    """The quoting the PowerShell line is held to, by PowerShell's own rules (as the docstring says)."""
    if any(c in path for c in "$`\"\u201c\u201d\u201e"):
        return "'" + "".join(c * 2 if c in "'\u2018\u2019\u201a\u201b" else c for c in path) + "'"
    return f'"{path}"'


@pytest.mark.parametrize("char", sorted(SPECIAL))
def test_on_windows_a_python_powershell_takes_specially_gets_its_own_powershell_line(monkeypatch, char):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", SPECIAL[char])
    cmd_line = pages.install_line()
    assert pages.install_lines() == [(CMD, cmd_line), (POWERSHELL, f"& {_powershell_quoted(SPECIAL[char])}" + INSTALL)]
    assert _install_paragraphs(pages.missing_page()) == [f"{CMD} {cmd_line}",
                                                          f"{POWERSHELL} & {_powershell_quoted(SPECIAL[char])}{INSTALL}"]


def test_the_single_quotes_double_a_single_quote_inside_them(monkeypatch):
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", r"C:\Users\o'n $x\python.exe")
    assert dict(pages.install_lines())[POWERSHELL] == r"& 'C:\Users\o''n $x\python.exe'" + INSTALL


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell's own parser is Windows'")
@pytest.mark.parametrize("char", sorted(SPECIAL))
def test_powershells_parser_reads_each_line_as_that_python(monkeypatch, char):
    """PowerShell's parser finds no error in the line, and its command is the Python, as given."""
    import os
    import subprocess
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", SPECIAL[char])
    line = dict(pages.install_lines())[POWERSHELL]
    parse = ("$e = $null; $a = [System.Management.Automation.Language.Parser]::ParseInput($env:INSTALL_LINE, [ref]$null, "
             "[ref]$e); $c = $a.FindAll({$args[0] -is [System.Management.Automation.Language.CommandAst]}, $true) | "
             "Select-Object -First 1; [Console]::Out.Write(\"$($e.Count)`n\"); "
             "[Console]::Out.Write([Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($c.CommandElements[0].Value)))")
    got = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", parse], capture_output=True, text=True,
                         timeout=120, env={**os.environ, "INSTALL_LINE": line})
    assert got.returncode == 0, got
    errors, named = got.stdout.split("\n", 1)
    import base64
    assert (int(errors), base64.b64decode(named.strip()).decode("utf-8")) == (0, SPECIAL[char]), (line, got.stdout)


#: In place of installing: the interpreter printing its own name, so a shell's run of a line is seen.
PRINT_ITSELF = ' -c "import sys; print(sys.executable)"'


def _python_in_a_folder_with_a_space(tmp_path):
    """A Python whose path holds a space: a venv (no pip) in a folder named with one."""
    import subprocess
    folder = tmp_path / "win venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(folder)], check=True, capture_output=True,
                   timeout=300)
    return folder / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


@pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell's run; Windows' shells are run below")
def test_a_posix_shell_runs_the_line(monkeypatch, tmp_path):
    import subprocess
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    python = _python_in_a_folder_with_a_space(tmp_path)
    monkeypatch.setattr(explain, "_on_windows", lambda: False)
    monkeypatch.setattr(sys, "executable", str(python))
    [(label, line)] = pages.install_lines()
    run = subprocess.run(["/bin/sh", "-c", line.replace(INSTALL, PRINT_ITSELF)], capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 0 and run.stdout.strip() == str(python), run


@pytest.mark.skipif(sys.platform != "win32", reason="Command Prompt and PowerShell are Windows' own")
def test_windows_shells_take_their_own_lines(monkeypatch, tmp_path):
    """cmd runs its line (installing swapped for the interpreter printing itself); PowerShell's own parser
    finds no error in its line, and does find one in the line without `& ` (the check bites)."""
    import os
    import subprocess
    from onetrace_console import explain
    from onetrace_console.neighbours import pages
    python = _python_in_a_folder_with_a_space(tmp_path)
    monkeypatch.setattr(explain, "_on_windows", lambda: True)
    monkeypatch.setattr(sys, "executable", str(python))
    lines = dict(pages.install_lines())
    run = subprocess.run(f'cmd /d /c "{lines[CMD].replace(INSTALL, PRINT_ITSELF)}"', capture_output=True, text=True,
                         timeout=120)
    assert run.returncode == 0 and os.path.normcase(run.stdout.strip()) == os.path.normcase(str(python)), run
    parse = ("$e = $null; [System.Management.Automation.Language.Parser]::ParseInput($env:INSTALL_LINE, [ref]$null, "
             "[ref]$e) | Out-Null; $e.Count")

    def errors(line: str) -> int:
        got = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", parse], capture_output=True,
                             text=True, timeout=120, env={**os.environ, "INSTALL_LINE": line})
        assert got.returncode == 0, got
        return int(got.stdout.strip())
    assert errors(lines[POWERSHELL]) == 0
    assert errors(lines[CMD]) > 0


@pytest.mark.parametrize("name", sorted(CONFIGS))
def test_the_panel_shortens_a_windows_path_to_its_last_two_parts(on_windows, name):
    from onetrace_console import explain
    on_windows(CONFIGS[name])
    line = html.unescape(explain.key_lines(explain.key_status(), short=True))
    assert line.startswith('<p data-explain="key" data-key="not-set">onetrace-explain read …\\config\\explain.toml; '), line


@pytest.mark.parametrize("path", ["/home/runner/work/a b/config/explain.toml", "/tmp/x/config/explain.toml"])
def test_the_panel_shortens_a_posix_path_to_its_last_two_parts(monkeypatch, path):
    from pathlib import PurePosixPath
    from onetrace_console import explain
    monkeypatch.setattr(explain, "config_path", lambda: PurePosixPath(path))
    monkeypatch.setattr(explain, "model_config", lambda: {"provider": "anthropic", "name": "m", "key_env": VAR})
    line = html.unescape(explain.key_lines(explain.key_status(), short=True))
    assert "onetrace-explain read …/config/explain.toml; " in line, line
