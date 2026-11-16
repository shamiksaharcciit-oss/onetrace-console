"""onetrace, onetrace-console, onetrace-explain and onetrace-auto install into one environment, and
`pip check` finds nothing to report.

The console's wheel is built from a copy of the tracked files and installed into a fresh venv with
onetrace-explain and onetrace-auto (`tools/fetch_wheel_cache.py`, `ONE_ENVIRONMENT`), pip resolving every
dependency from the wheel cache alone, as `pip install onetrace onetrace-console onetrace-explain
onetrace-auto` resolves them from PyPI: no other index, no network.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import only

REPO = Path(__file__).resolve().parent.parent
FOUR = ("onetrace", "onetrace-console", "onetrace-explain", "onetrace-auto")


def _cache() -> Path:
    from tools.fetch_wheel_cache import CACHE, check

    if not check():
        pytest.fail(f"the local wheel cache is not ready: {CACHE}\n    python tools/fetch_wheel_cache.py")
    return CACHE


@pytest.fixture(scope="module")
def console_wheel(tmp_path_factory) -> Path:
    """The console's wheel, built from a copy of the tracked files, so the build writes nothing here."""
    root = tmp_path_factory.mktemp("one-environment")
    tree = root / "tree"
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\0")
    for rel in filter(None, tracked):
        if (REPO / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((REPO / rel).read_bytes())
    dist = root / "dist"
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from setuptools import build_meta as b; print(b.build_wheel(sys.argv[1]))",
            str(dist),
        ],
        cwd=tree,
        check=True,
        capture_output=True,
        env=_clean(),
    )
    return only(dist.glob("onetrace_console-*.whl"))


def _clean() -> dict:
    return {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}


def installed_together(venv: Path, console_wheel: Path, beside: list[str]) -> tuple[int, str, dict[str, str]]:
    """Install the console's wheel and `beside` into a fresh venv from the cache alone: pip check's
    exit and words, and the four distributions' versions as installed."""
    cache = _cache()
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    done = subprocess.run(
        [str(py), "-m", "pip", "install", "-q", "--no-index", "--find-links", str(cache), str(console_wheel), *beside],
        capture_output=True,
        text=True,
        env=_clean(),
        timeout=900,
    )
    if done.returncode != 0:
        return done.returncode, (done.stdout + done.stderr)[-2000:], {}
    check = subprocess.run([str(py), "-m", "pip", "check"], capture_output=True, text=True, env=_clean())
    code = "import importlib.metadata as m, json, sys\nprint(json.dumps({n: m.version(n) for n in sys.argv[1:]}))"
    import json

    versions = json.loads(
        subprocess.run([str(py), "-c", code, *FOUR], capture_output=True, text=True, env=_clean(), check=True).stdout
    )
    return check.returncode, check.stdout + check.stderr, versions


def test_the_four_install_into_one_environment_and_pip_check_finds_nothing(console_wheel, tmp_path, examined):
    from tests.test_pins import PINNED_SDK_VERSION
    from tools.fetch_wheel_cache import ONE_ENVIRONMENT

    exit_code, said, versions = installed_together(tmp_path / "venv", console_wheel, list(ONE_ENVIRONMENT))
    examined(len(FOUR), "distributions installed into one environment")
    assert exit_code == 0, said
    assert "No broken requirements found." in said, said
    assert versions["onetrace"] == PINNED_SDK_VERSION == "0.8.0", versions
    assert (versions["onetrace-explain"], versions["onetrace-auto"]) == ("0.3.1", "0.8.0"), versions


def test_onetrace_explain_0_3_1_is_pinned_by_its_hash_and_no_candidate_remains(examined):
    """onetrace-explain 0.3.1 as released: its wheel's sha256 as its release build gave it, the one the tests of
    the Set up Explain form run against; the cache keeps no candidate taken from a folder."""
    from tools import fetch_wheel_cache as w

    examined(1, "pin")
    assert w.ONE_ENVIRONMENT["onetrace-explain==0.3.1"] == (
        "onetrace_explain-0.3.1-py3-none-any.whl",
        "20a506dce8e5c1f19fb70c9054f6f7c1bfab313f71fd59aae3b745eebf81e7b5",
    )
    assert not hasattr(w, "CANDIDATE") and not hasattr(w, "take_candidate")


def test_sabotage_an_onetrace_explain_that_takes_no_0_8_is_named(console_wheel, tmp_path, examined):
    """onetrace-explain 0.3.0 takes onetrace below 0.8: beside the console's pin, pip refuses or pip
    check names it."""
    from tools.fetch_wheel_cache import EARLIER_EXPLAIN

    (older,) = EARLIER_EXPLAIN
    assert older == "onetrace-explain==0.3.0", older
    exit_code, said, _ = installed_together(tmp_path / "venv", console_wheel, [older])
    examined(1, "an environment with an onetrace-explain that takes no 0.8")
    assert exit_code != 0 and "onetrace" in said, said
