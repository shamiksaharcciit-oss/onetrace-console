"""Three small things 0.1.1 fixes, each as a user meets it.

1. `--help` and `-h` print the usage on standard output and exit 0; anything not understood still
   prints it on standard error and exits 2.
2. `demo --public`, stopped with SIGTERM (as a container or a test stops it), removes the temporary
   folder it built the demo in.
3. The console has an icon: served at /static/favicon.svg, in the skin's own navigation colours,
   and linked from every page the console frames.

tools/sabotage_small_fixes.py breaks each one and expects these tests to fail.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _cli(*args: str) -> subprocess.CompletedProcess:
    env = {**{k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"},
           "PYTHONPATH": str(REPO / "src")}
    return subprocess.run([sys.executable, "-B", "-m", "onetrace_console", *args],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=120)


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_prints_the_usage_on_standard_output_and_succeeds(flag, examined):
    done = _cli(flag)
    examined(1, "help asked for")
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith("onetrace-console") and "onetrace-console demo" in done.stdout
    assert done.stderr == ""


@pytest.mark.parametrize("args", [[], ["--no-such-flag"]], ids=["nothing", "unknown flag"])
def test_anything_not_understood_still_goes_to_standard_error_with_2(args, examined):
    done = _cli(*args)
    examined(1, "command")
    assert done.returncode == 2 and done.stdout == "" and "onetrace-console demo" in done.stderr


@pytest.mark.skipif(os.name == "nt", reason="Windows stops a process with TerminateProcess, "
                                            "which no program can catch; there is no SIGTERM to test")
def test_a_public_demo_stopped_with_sigterm_leaves_no_temporary_folder(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port
    _require_installed()
    temp = tmp_path / "tmp"
    temp.mkdir()
    c = _Console(tmp_path, "demo", "--public", "--port", str(_free_port()),
                 env={"TMPDIR": str(temp), "TEMP": str(temp), "TMP": str(temp)})
    try:
        c.until("overview:")
        assert [p.name for p in temp.iterdir() if p.name.startswith("onetrace-console-public-demo-")], \
            "the demo was built in the temporary folder"
        c.proc.terminate()
        c.proc.wait(timeout=60)
    finally:
        c.stop()
    examined(1, "demo stopped")
    left = [p.name for p in temp.iterdir() if p.name.startswith("onetrace-console-public-demo-")]
    assert left == [], left


def test_the_icon_is_served_in_the_skins_colours_and_every_framed_page_links_it(examined):
    from onetrace_console.serve import STATIC_FILES, _STATIC_TYPES
    from onetrace_console.viewer.page import framed, _head
    from onetrace_console.viewer.tokens import root_css
    icon = STATIC_FILES["/static/favicon.svg"]
    examined(1, "icon")
    assert _STATIC_TYPES[icon.suffix] == "image/svg+xml"
    colours = set(re.findall(r'"(#[0-9a-f]{6})"', icon.read_text(encoding="utf-8")))
    tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-fA-F]{6})", root_css()))
    assert colours == {tokens["nav-bg"], tokens["nav-on-ink"]}, colours
    with framed("/static/console.css"):
        head = _head("x")
    assert '<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">' in head
    assert "favicon" not in _head("x"), "the free file, framed by nothing, links no icon"


def test_the_icon_ships_in_the_package(examined):
    import tomllib
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    examined(1, "package-data list")
    assert "static/favicon.svg" in data["tool"]["setuptools"]["package-data"]["onetrace_console"]
