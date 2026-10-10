"""The last way the console names the SDK's build: a git commit, taken only from onetrace's own
checkout.

When onetrace has no install report, no direct_url.json and no RECORD, the console may read the
commit of the checkout onetrace is loaded from. It must never read the commit of some other
project that merely contains the installed package (a `.venv` inside a repository is common):
that would put another project's commit on screen as onetrace's build.
"""
from __future__ import annotations

import importlib.metadata
import subprocess
from pathlib import Path

import pytest

from onetrace_console.compare import ComparisonError, sdk_build_digest


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                           "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(root: Path, project: str, package: str) -> tuple[Path, str]:
    """A git repository at `root` whose pyproject.toml names `project`, holding an `onetrace`
    package at `package` (relative to `root`). Returns the package folder and the commit."""
    root.mkdir(parents=True)
    (root / "pyproject.toml").write_text(f'[project]\nname = "{project}"\nversion = "1.0"\n',
                                         encoding="utf-8")
    pkg = root / package
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "initial")
    return pkg, _git(root, "rev-parse", "HEAD")


@pytest.fixture
def loaded_from(tmp_path, monkeypatch):
    """Make the console see onetrace as loaded from a given folder, with no install report, no
    installed distribution (so no direct_url.json and no RECORD): only the git source is left."""
    import onetrace

    monkeypatch.setenv("ONETRACE_CONSOLE_INSTALL_REPORT", str(tmp_path / "no-install-report.json"))
    real = importlib.metadata.distribution

    def distribution(name):
        if name == "onetrace":
            raise importlib.metadata.PackageNotFoundError(name)
        return real(name)

    monkeypatch.setattr(importlib.metadata, "distribution", distribution)

    def load(package_dir: Path) -> None:
        monkeypatch.setattr(onetrace, "__file__", str(package_dir / "__init__.py"))
    return load


def test_onetrace_in_a_venv_inside_another_repository_is_refused(tmp_path, loaded_from, examined):
    pkg, stranger = _repo(tmp_path / "someone-elses-project", "someone-elses-project",
                          ".venv/lib/python3.12/site-packages/onetrace")
    loaded_from(pkg)
    examined(1, "installation inside another project's repository")
    with pytest.raises(ComparisonError) as refused:
        sdk_build_digest()
    message = str(refused.value)
    assert stranger not in message, "the other project's commit was named"
    for source in ("install report", "direct_url.json", "RECORD", "git"):
        assert source in message, (source, message)


@pytest.mark.parametrize("layout", ["src/onetrace", "onetrace"])
def test_onetrace_loaded_from_its_own_checkout_is_named_by_its_commit(tmp_path, loaded_from, examined,
                                                                      layout):
    pkg, head = _repo(tmp_path / "onetrace", "onetrace", layout)
    loaded_from(pkg)
    examined(1, "onetrace's own checkout")
    assert sdk_build_digest() == f"commit:{head}"


def test_a_checkout_of_another_project_with_the_same_layout_is_refused(tmp_path, loaded_from, examined):
    """The layout alone is not enough: the checkout's own pyproject.toml must name onetrace."""
    pkg, other = _repo(tmp_path / "fork", "not-onetrace", "src/onetrace")
    loaded_from(pkg)
    examined(1, "checkout that names another project")
    with pytest.raises(ComparisonError) as refused:
        sdk_build_digest()
    assert other not in str(refused.value)
