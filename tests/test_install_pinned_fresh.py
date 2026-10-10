"""`tools/install_pinned.py` must work on a machine that has nothing installed.

It imported `onetrace_console.compare` to find where pip's install report goes. Once that module
came to import the vendored `viewer` -- one of the very pins the script installs -- both fresh
Actions runners stopped with "No module named 'viewer'" before installing anything, while the
project's own machine, whose venv already held the viewer, passed. The report path now comes from
`src/onetrace_console/install_report.py`, standard library only, loaded by its path.

The last test runs the script's own lookup in a venv created here with nothing in it -- not even
pip -- exactly as a fresh runner meets it.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "tools" / "install_pinned.py"
MODULE = REPO / "src" / "onetrace_console" / "install_report.py"
STDLIB_ONLY = {"__future__", "os", "sys", "pathlib"}


def _imported(path: Path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names.add((node.module or "").split(".")[0])
    return names


def test_the_report_path_module_imports_only_the_standard_library():
    extra = _imported(MODULE) - STDLIB_ONLY
    assert not extra, f"install_report.py imports {sorted(extra)}: the installer loads it before they exist"


def test_the_installer_never_imports_the_package_it_installs():
    assert "onetrace_console" not in _imported(SCRIPT), (
        "tools/install_pinned.py imports onetrace_console, whose modules import the pins it installs")


def test_the_installers_lookup_works_in_a_venv_with_nothing_installed(tmp_path):
    venv = tmp_path / "fresh"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    probe = ("import runpy, sys; m = runpy.run_path(sys.argv[1]); print(m['report_path']())")
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    env.pop("ONETRACE_CONSOLE_INSTALL_REPORT", None)
    done = subprocess.run([str(python), "-c", probe, str(SCRIPT)], cwd=REPO, env=env,
                          capture_output=True, text=True)
    assert done.returncode == 0, f"the lookup failed with nothing installed:\n{done.stderr[-2000:]}"
    said = Path(done.stdout.strip())
    assert said.name == "onetrace-console-install-report.json"
    assert said.parent.resolve() == Path(subprocess.run(
        [str(python), "-c", "import sys; print(sys.prefix)"], capture_output=True, text=True,
        check=True).stdout.strip()).resolve(), f"the report goes to {said}, not the fresh venv's prefix"
