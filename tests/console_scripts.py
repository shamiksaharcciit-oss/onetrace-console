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
