"""The console's licence: an Apache-2.0 LICENSE.

The file is onetrace-ci's LICENSE, byte for byte -- the Apache License 2.0 text used for the
public repositories -- and the README carries the one copyright line that goes beside it
there.
"""
from __future__ import annotations

import hashlib
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: sha256 of onetrace-ci's LICENSE, written here by script (X-11), never typed.
LICENSE_SHA256 = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"


def test_the_licence_is_apache_2_0_byte_for_byte():
    data = (REPO / "LICENSE").read_bytes()
    assert hashlib.sha256(data).hexdigest() == LICENSE_SHA256
    text = data.decode("utf-8")
    assert text.lstrip().startswith("Apache License")
    assert "Version 2.0, January 2004" in text
    assert "TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION" in text


def test_the_readme_carries_the_ruled_line():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "Copyright 2026 Shamik Saha. Licensed under Apache-2.0; see LICENSE." in readme


def test_the_package_declares_the_same_licence():
    """As an SPDX expression with its file named (PEP 639), since 0.1.1: the table form
    (`{text = ...}`) made setuptools warn that it is deprecated."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == "Apache-2.0" and project["license-files"] == ["LICENSE"]


def test_the_built_metadata_says_apache_2_0_and_the_build_does_not_warn(tmp_path):
    """Built from the tracked tree, the wheel's metadata names Apache-2.0 and carries the
    licence file, and the build prints no licence deprecation warning."""
    import os
    import subprocess
    import sys
    import zipfile
    tree = tmp_path / "tree"
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True,
                             check=True).stdout.decode("utf-8").split("\0")
    for rel in filter(None, tracked):
        if (REPO / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((REPO / rel).read_bytes())
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    built = subprocess.run([sys.executable, "-c", "import sys; from setuptools import build_meta as b; "
                            "print(b.build_wheel(sys.argv[1]))", str(tmp_path / "dist")],
                           cwd=tree, capture_output=True, text=True, env=clean)
    assert built.returncode == 0, built.stderr[-2000:]
    assert "License classifiers are deprecated" not in built.stderr
    assert "project.license` as a TOML table is deprecated" not in built.stderr
    wheel = next((tmp_path / "dist").glob("onetrace_console-*.whl"))
    with zipfile.ZipFile(wheel) as whl:
        meta = next(n for n in whl.namelist() if n.endswith(".dist-info/METADATA"))
        text = whl.read(meta).decode("utf-8")
        assert "License-Expression: Apache-2.0" in text, text[:800]
        assert any(n.endswith(".dist-info/licenses/LICENSE") for n in whl.namelist())


def test_the_image_carries_the_licence():
    """The container is a distribution too, so the licence travels in it."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY LICENSE ./LICENSE" in dockerfile
