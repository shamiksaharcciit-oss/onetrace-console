"""The public site's comparison link, named the same on every platform (`site_links`, `folder_load.delivery`).

A run's delivery makes its bundle, whose digest names its comparisons. Its files went in the order this
host sorts paths: on Windows, which folds case, `MANIFEST.json` came after `artifacts/`, so the kept runs
were named otherwise there and the site's comparison link found no page. Delivered in one order on every
platform, the kept runs name it as onetrace 0.5.0 did.

1. A delivery's bytes do not depend on how this host orders paths: planted, this host's paths
   comparing as Windows' do (case-folded), and a folder listing its files in reverse.
2. The kept P1 pair, delivered with this host's paths comparing as Windows' do, names the site's
   comparison link as onetrace 0.5.0 named it.
"""
from __future__ import annotations

from pathlib import Path, PosixPath, PurePosixPath, PureWindowsPath

import pytest

REPO = Path(__file__).resolve().parent.parent
KEPT = REPO / "deploy" / "fly" / "kept" / "runs"
SITE_NAME = "b56e0b73e5e3324556fbdbcfc2a5561a1389322ba405c2184f2fdb620f8284da"


def _windows_paths(monkeypatch):
    """This host's paths compare as Windows' do: case-folded, with its separator (`PureWindowsPath`)."""
    monkeypatch.setattr(PosixPath, "__lt__", lambda a, b: PureWindowsPath(str(a)) < PureWindowsPath(str(b)))
    monkeypatch.setattr(PosixPath, "__gt__", lambda a, b: PureWindowsPath(str(a)) > PureWindowsPath(str(b)))


def _reversed_listing(monkeypatch):
    """Every folder lists its files in reverse."""
    real = Path.rglob
    monkeypatch.setattr(Path, "rglob", lambda self, pattern: iter(list(real(self, pattern))[::-1]))


@pytest.mark.skipif(not issubclass(type(Path(".")), PosixPath), reason="plants Windows' ordering on a POSIX host")
@pytest.mark.parametrize("plant", [_windows_paths, _reversed_listing], ids=["windows ordering", "reversed listing"])
def test_a_delivery_does_not_depend_on_how_this_host_orders_paths(plant, monkeypatch, examined):
    from onetrace_console.folder_load import delivery
    run = KEPT / "p1-02-baseline-set2"
    here = delivery(run)
    examined(1, "run folder")
    names = [p.relative_to(run).as_posix() for p in run.rglob("*") if p.is_file()]
    assert sorted(names, key=PurePosixPath) != sorted(names, key=PureWindowsPath), "the planted order is no different"
    plant(monkeypatch)
    assert delivery(run) == here


@pytest.mark.skipif(not issubclass(type(Path(".")), PosixPath), reason="plants Windows' ordering on a POSIX host")
def test_the_kept_pair_names_the_site_s_comparison_as_onetrace_0_5_0_did_with_windows_ordering(tmp_path, monkeypatch, examined):
    from onetrace_console import site_links
    from onetrace_console.compare import comparison_key
    from onetrace_console.folder_load import delivery
    from onetrace_console.ingest import accept, bundle
    from onetrace_console.store import Store, digest
    _windows_paths(monkeypatch)
    store = Store(tmp_path / "store")
    runs = [accept(delivery(KEPT / name), store).run for name in ("p1-02-baseline-set2", "p1-08-candidate-set2")]
    examined(len(runs), "kept runs")
    version, build = site_links.EARLIER_SDKS[0]
    a, b = (digest(bundle(r, store)) for r in runs)
    assert comparison_key(a, b, version, build) == SITE_NAME
