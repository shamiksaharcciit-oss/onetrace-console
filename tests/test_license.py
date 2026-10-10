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
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["license"] == {"text": "Apache-2.0"}


def test_the_image_carries_the_licence():
    """The container is a distribution too, so the licence travels in it."""
    dockerfile = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY LICENSE ./LICENSE" in dockerfile
