"""An installed console script, found as the console finds onetrace-explain (`explain.find`): in this
interpreter's scripts folder (`sysconfig`), then beside the interpreter, then on PATH, by its name on
the platform (`<name>.exe` on Windows). A venv's scripts sit beside its Python; a base Python on Windows
keeps them in `Scripts\\`, not beside `python.exe`, so a path built as the interpreter's folder and the
bare name finds nothing there.
"""
from __future__ import annotations

import os
import shutil
import sys
import sysconfig
from pathlib import Path


def console_script(name: str) -> Path | None:
    """The installed command `name`, or None where it is not installed."""
    file = f"{name}.exe" if os.name == "nt" else name
    for folder in (sysconfig.get_path("scripts"), str(Path(sys.executable).parent)):
        if folder and (Path(folder) / file).is_file():
            return Path(folder) / file
    found = shutil.which(name)
    return Path(found) if found else None


def required_script(name: str, *, python: str | Path | None = None, scripts: str | Path | None = None,
                    windows: bool | None = None) -> Path:
    """The installed command `name` a test runs: in the interpreter's scripts folder
    (`sysconfig.get_path("scripts")`) first, then in the interpreter's own folder, by its name on the
    platform (`<name>.exe` on Windows). Never PATH, and never a skip: where neither folder holds it, the
    test fails, naming both folders. `python`, `scripts` and `windows` stand in for this interpreter's own,
    for the helper's tests."""
    import pytest
    windows = os.name == "nt" if windows is None else windows
    python = Path(sys.executable if python is None else python)
    if scripts is None and python == Path(sys.executable):
        scripts = sysconfig.get_path("scripts")
    file = f"{name}.exe" if windows else name
    folders = [Path(f) for f in (scripts, python.parent) if f]
    for folder in folders:
        if (folder / file).is_file():
            return folder / file
    pytest.fail(f"{file} is in neither this interpreter's scripts folder nor its own folder: "
                f"{', '.join(str(f) for f in folders)}. Install it into this environment (see PINS.md).")
