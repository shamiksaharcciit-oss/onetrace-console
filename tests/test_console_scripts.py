"""An installed console script, as the tests find it (`tests/console_scripts.required_script`): in this
interpreter's scripts folder (`sysconfig.get_path("scripts")`) first, then in the interpreter's own folder,
by its name on the platform (`<name>.exe` on Windows). A venv keeps its scripts beside its Python; a base
Python on Windows keeps them in `Scripts\\` beneath `python.exe`, and a POSIX prefix in `bin/`, where the
interpreter's own folder may be another. Where neither folder holds the tool, the test fails, named; it is
never skipped.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TOOL = "onetrace-verify"


def _layout(root: Path, *, windows: bool, beneath: bool) -> tuple[Path, Path, Path]:
    """A fake interpreter and its scripts folder: the scripts beside it, or in `Scripts\\` (Windows) or
    `bin/` beneath it. Returns (interpreter, scripts folder, the tool's file)."""
    home = root / ("x64" if windows else "prefix")
    python = home / ("python.exe" if windows else "python3")
    scripts = home / ("Scripts" if windows else "bin") if beneath else home
    scripts.mkdir(parents=True, exist_ok=True)
    python.parent.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"")
    tool = scripts / (f"{TOOL}.exe" if windows else TOOL)
    tool.write_bytes(b"")
    return python, scripts, tool


@pytest.mark.parametrize("windows", [False, True], ids=["posix", "windows"])
@pytest.mark.parametrize("beneath", [False, True], ids=["beside", "beneath"])
def test_the_tool_is_found_in_either_layout(tmp_path, windows, beneath, examined):
    from tests.console_scripts import required_script
    python, scripts, tool = _layout(tmp_path, windows=windows, beneath=beneath)
    examined(1, f"a {'Windows' if windows else 'POSIX'} layout, scripts {'beneath' if beneath else 'beside'}")
    assert required_script(TOOL, python=python, scripts=scripts, windows=windows) == tool


@pytest.mark.parametrize("windows", [False, True], ids=["posix", "windows"])
def test_the_scripts_folder_is_read_before_the_interpreter_s(tmp_path, windows, examined):
    from tests.console_scripts import required_script
    python, scripts, tool = _layout(tmp_path, windows=windows, beneath=True)
    (python.parent / tool.name).write_bytes(b"")
    examined(1, "a tool in both folders")
    assert required_script(TOOL, python=python, scripts=scripts, windows=windows) == tool


@pytest.mark.parametrize("windows", [False, True], ids=["posix", "windows"])
def test_the_scripts_folder_unset_the_interpreter_s_own_is_read(tmp_path, windows, examined):
    from tests.console_scripts import required_script
    python, _scripts, tool = _layout(tmp_path, windows=windows, beneath=False)
    examined(1, "no scripts folder named")
    assert required_script(TOOL, python=python, scripts=None, windows=windows) == tool


def test_where_neither_folder_holds_it_the_test_fails_named(tmp_path, examined):
    from tests.console_scripts import required_script
    python, scripts, tool = _layout(tmp_path, windows=True, beneath=True)
    tool.unlink()
    examined(1, "a layout without the tool")
    with pytest.raises(pytest.fail.Exception) as failed:
        required_script(TOOL, python=python, scripts=scripts, windows=True)
    said = str(failed.value)
    assert f"{TOOL}.exe" in said and str(scripts) in said and str(python.parent) in said


def test_sabotage_today_s_with_name_form_misses_the_scripts_folder_beneath(tmp_path, examined):
    """The form the release's test used, `Path(sys.executable).with_name(...)`, finds the tool beside the
    interpreter and not in `Scripts\\` beneath it: the hosted Windows Python's layout."""
    python, _scripts, tool = _layout(tmp_path, windows=True, beneath=True)
    examined(1, "the old form, on the layout beneath")
    assert not python.with_name(tool.name).is_file() and not python.with_name(TOOL).is_file()
    python2, _s2, tool2 = _layout(tmp_path / "venv", windows=True, beneath=False)
    assert python2.with_name(tool2.name).is_file()


#: A script's path built from the interpreter's own: `Path(sys.executable).with_name(...)`, or its
#: `.parent` joined to a name (`/ "..."`), or `os.path.dirname(sys.executable)` the same.
PATTERN = re.compile(r"Path\(sys\.executable\)(?:\.resolve\(\))?\.(?:with_name\(|parent\s*/)"
                     r"|os\.path\.join\(os\.path\.dirname\(sys\.executable\)")
#: The helper itself reads the interpreter's folder, as its second place.
HELPER = "tests/console_scripts.py"


def finds_by_the_interpreter(files) -> list[str]:
    return [f"{rel}:{n}" for rel, text in files for n, line in enumerate(text.splitlines(), 1)
            if PATTERN.search(line) and rel != HELPER]


def _sources() -> list[tuple[str, str]]:
    return [(p.relative_to(REPO).as_posix(), p.read_text(encoding="utf-8", errors="replace"))
            for folder in ("tests", "tools") for p in sorted((REPO / folder).rglob("*.py"))
            if p.name != Path(__file__).name]


def test_no_test_or_tool_finds_a_script_beside_the_interpreter(examined):
    files = _sources()
    examined(len(files), "test and tool modules")
    assert finds_by_the_interpreter(files) == []


@pytest.mark.parametrize("line", ['verify = Path(sys.executable).with_name("onetrace-verify")',
                                  'tool = Path(sys.executable).parent / "onetrace-verify"',
                                  'tool = os.path.join(os.path.dirname(sys.executable), "onetrace")'])
def test_sabotage_each_form_of_the_pattern_is_named(line, examined):
    examined(1, "a planted line")
    assert finds_by_the_interpreter([("tests/test_planted.py", f"import sys\n{line}\n")]) == [
        "tests/test_planted.py:2"]
