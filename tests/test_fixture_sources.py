"""The two fetch tools take the SDK's files from one of two
sources -- PyPI for 0.2.0 as released, or a committed wheelhouse folder for a build on no index, as
the 0.2.0 branch used before the release -- and each source refuses a file whose sha256 is not the pinned one, before anything is
extracted or cached. Neither source is trusted for its name; both go through the same check.

The PyPI source is exercised without the network: `subprocess.run` (the tool's `pip download`) is
replaced by one that writes the bytes a server might have served into the destination folder.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from tools import fetch_sdk_fixtures as fixtures
from tools import fetch_wheel_cache as wheels

WRONG = b"not the pinned bytes\n"


def _pip_download_serving(data_for: dict[str, bytes]):
    """A stand-in for `pip download --dest D <req>` that writes the named file into D."""

    def run(cmd, *args, **kwargs):
        dest = Path(cmd[cmd.index("--dest") + 1])
        for name, data in data_for.items():
            (dest / name).write_bytes(data)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return run


# ------------------------------------------------------------------ the fixture sdist


@pytest.fixture
def fixture_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(fixtures, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(fixtures, "EXAM", tmp_path / "cache" / "exam")
    monkeypatch.setattr(fixtures, "WHEELHOUSE", tmp_path / "wheelhouse")
    (tmp_path / "wheelhouse").mkdir()
    return tmp_path


def test_the_wheelhouse_source_refuses_an_sdist_that_does_not_match(fixture_tool, monkeypatch, examined):
    monkeypatch.setattr(fixtures, "SOURCE", "wheelhouse")
    (fixture_tool / "wheelhouse" / fixtures.SDIST_NAME).write_bytes(WRONG)
    examined(1, "wheelhouse sdist refused")
    with pytest.raises(SystemExit, match="REFUSING: .* from the wheelhouse"):
        fixtures.fetch()
    assert not (fixture_tool / "cache").exists(), "something was extracted from a refused sdist"


def test_the_wheelhouse_source_refuses_when_the_sdist_is_missing(fixture_tool, monkeypatch, examined):
    monkeypatch.setattr(fixtures, "SOURCE", "wheelhouse")
    examined(1, "missing wheelhouse sdist refused")
    with pytest.raises(SystemExit, match="did not provide"):
        fixtures.fetch()


def test_the_pypi_source_refuses_an_sdist_that_does_not_match(fixture_tool, monkeypatch, examined):
    monkeypatch.setattr(fixtures, "SOURCE", "pypi")
    monkeypatch.setattr(fixtures.subprocess, "run", _pip_download_serving({fixtures.SDIST_NAME: WRONG}))
    examined(1, "PyPI sdist refused")
    with pytest.raises(SystemExit, match="REFUSING: .* from PyPI"):
        fixtures.fetch()
    assert not (fixture_tool / "cache").exists(), "something was extracted from a refused sdist"


def test_the_pinned_bytes_pass_their_own_check(tmp_path, monkeypatch, examined):
    """The control: bytes whose sha256 is the pinned one pass, so the refusals above are refusals
    of the wrong file, not of every file. (The release's sdist is on PyPI, not in the tree; the
    pin is pointed at known bytes here, and the pinned value itself is held by test_pin_012.)"""
    import hashlib

    right = b"the pinned bytes\n"
    monkeypatch.setattr(fixtures, "SDIST_SHA256", hashlib.sha256(right).hexdigest())
    path = tmp_path / fixtures.SDIST_NAME
    path.write_bytes(right)
    examined(1, "pinned bytes checked")
    assert fixtures._verified(path, "PyPI") == path


# ------------------------------------------------------------------ the wheel cache


@pytest.fixture
def wheel_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(wheels, "CACHE", tmp_path / "cache")
    monkeypatch.setattr(wheels, "WHEELHOUSE", tmp_path / "wheelhouse")
    (tmp_path / "wheelhouse").mkdir()
    return tmp_path


def test_the_wheelhouse_source_refuses_a_wheel_that_does_not_match(wheel_tool, monkeypatch, examined):
    monkeypatch.setattr(wheels, "SOURCE", "wheelhouse")
    for name, _ in wheels.WHEELS.values():
        (wheel_tool / "wheelhouse" / name).write_bytes(WRONG)
    examined(1, "wheelhouse wheel refused")
    with pytest.raises(SystemExit, match="REFUSING: .* from the wheelhouse"):
        wheels.fetch()
    assert not (wheel_tool / "cache").exists(), "something was cached from a refused wheel"


def test_the_pypi_source_refuses_a_wheel_that_does_not_match(wheel_tool, monkeypatch, examined):
    monkeypatch.setattr(wheels, "SOURCE", "pypi")
    monkeypatch.setattr(
        wheels.subprocess, "run", _pip_download_serving({name: WRONG for name, _ in wheels.WHEELS.values()})
    )
    examined(1, "PyPI wheel refused")
    with pytest.raises(SystemExit, match="REFUSING: .* from PyPI"):
        wheels.fetch()
    assert not (wheel_tool / "cache").exists(), "something was cached from a refused wheel"


# ------------------------------------------------------------------ a fresh fetch leaves a ready cache


def test_a_fresh_fetch_leaves_every_file_the_check_requires(tmp_path, monkeypatch, examined):
    """`fetch_wheel_cache.py` then `--check`, as a reader's first setup runs them: every wheel the tool fetches and
    verifies is in the cache, so the check finds what it requires. Each pinned wheel is served as bytes of its own,
    pinned here by their own sha256; no network."""
    lists = ("WHEELS", "TEST_COMMANDS", "ONE_ENVIRONMENT", "EARLIER_EXPLAIN", "KEYCHAIN")
    served: dict[str, dict[str, bytes]] = {}
    for name in lists:
        pinned = {}
        for requirement, (filename, _sha) in getattr(wheels, name).items():
            data = f"the wheel {filename}\n".encode()
            pinned[requirement] = (filename, hashlib.sha256(data).hexdigest())
            served[requirement] = {filename: data}
        monkeypatch.setattr(wheels, name, pinned)
    monkeypatch.setattr(wheels, "crypto_pins", lambda: {})
    monkeypatch.setattr(wheels, "CACHE", tmp_path / ".wheel-cache")
    monkeypatch.setattr(wheels, "SOURCE", "pypi")

    def run(cmd, *args, **kwargs):
        dest = Path(cmd[cmd.index("--dest") + 1])
        dest.mkdir(parents=True, exist_ok=True)
        for name, data in served.get(cmd[-1], {}).items():
            (dest / name).write_bytes(data)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(wheels.subprocess, "run", run)
    examined(len(served), "wheels fetched, then checked")
    wheels.fetch()
    assert wheels.check(), sorted(p.name for p in (tmp_path / ".wheel-cache").iterdir())
