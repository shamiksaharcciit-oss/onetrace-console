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
#: The P1 pair as the hosted demo kept it until console 0.8.0 recorded its runs again: the two runs the public
#: site's comparison links were named from, kept here, byte for byte, so the earlier SDKs' names are still
#: held against real runs.
KEPT = REPO / "tests" / "site_links_runs"
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
def test_the_kept_pair_names_the_site_s_comparison_as_onetrace_0_5_0_did_with_windows_ordering(
    tmp_path, monkeypatch, examined
):
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


#: The site's name for the pair under each earlier release's SDK build, in `EARLIER_SDKS`' order.
SITE_NAMES = (
    "b56e0b73e5e3324556fbdbcfc2a5561a1389322ba405c2184f2fdb620f8284da",
    "85dc0852a57737a69d71b9e12c697b77e69ab92d30b5c358ca9f8fb7cfc7dd1b",
)


def test_each_earlier_sdk_is_the_wheel_its_release_pinned(examined):
    """Each earlier SDK build is named by its release's wheel, as PyPI serves it (tests/test_pin_012.py)."""
    from onetrace_console import site_links
    from tests.test_pin_012 import RELEASE_0_5_0, RELEASE_0_6_0

    examined(len(site_links.EARLIER_SDKS), "earlier SDK builds")
    assert site_links.EARLIER_SDKS == (
        ("0.5.0", "wheel:" + RELEASE_0_5_0["onetrace-0.5.0-py3-none-any.whl"]),
        ("0.6.0", "wheel:" + RELEASE_0_6_0["onetrace-0.6.0-py3-none-any.whl"]),
    )


def test_each_earlier_sdk_names_the_kept_pair_as_the_site_links_it(tmp_path, examined):
    """The kept P1 pair, named by each earlier SDK build: console 0.4.0's name and console 0.5.0's, the
    two the site links; and this console's own name is neither."""
    from onetrace_console import site_links
    from onetrace_console.compare import comparison_key, sdk_build_digest, sdk_distribution_version
    from onetrace_console.folder_load import delivery
    from onetrace_console.ingest import accept, bundle
    from onetrace_console.store import Store, digest

    store = Store(tmp_path / "store")
    runs = [accept(delivery(KEPT / name), store).run for name in ("p1-02-baseline-set2", "p1-08-candidate-set2")]
    a, b = (digest(bundle(r, store)) for r in runs)
    examined(len(site_links.EARLIER_SDKS), "earlier SDK builds")
    assert tuple(comparison_key(a, b, v, build) for v, build in site_links.EARLIER_SDKS) == SITE_NAMES
    assert comparison_key(a, b, sdk_distribution_version(), sdk_build_digest()) not in SITE_NAMES


# ------------------------------------------------------------------ a link to runs since recorded again


def test_a_line_may_name_the_two_runs_its_link_showed(tmp_path, examined):
    """`/diff/<old>.html <run A> <run B>`: the link is still read as its path, and its pair kept apart."""
    from onetrace_console import site_links

    f = tmp_path / "links.txt"
    old = "diff/" + "ab" * 32 + ".html"
    f.write_text(f"# c\n/\n/{old} p1-02-baseline-set2 p1-08-candidate-set2\n", encoding="utf-8")
    examined(2, "the paths, and the pair")
    assert site_links.read(f) == ["/", f"/{old}"]
    assert site_links.read_pairs(f) == {f"/{old}": ("p1-02-baseline-set2", "p1-08-candidate-set2")}


@pytest.mark.parametrize("line", ["/x.html a", "/x.html a b c", "/x.html a B", "/ a b"])
def test_a_line_whose_pair_is_not_two_run_ids_on_a_comparison_link_is_refused(tmp_path, line, examined):
    from onetrace_console import site_links

    examined(1, repr(line))
    f = tmp_path / "links.txt"
    f.write_text(line + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        site_links.read_pairs(f)


class _Run:
    def __init__(self, key, run_id):
        self.key, self.run_id = key, run_id


class _Comparison:
    def __init__(self, key, a, b):
        self.key, self.run_a, self.run_b = key, a, b


class _Store:
    def __init__(self):
        self._runs = {"ka": _Run("ka", "p1-02-baseline-set2"), "kb": _Run("kb", "p1-08-candidate-set2")}
        self._comparisons = [_Comparison("cd" * 32, "ka", "kb")]

    def comparisons(self):
        return list(self._comparisons)

    def runs(self):
        return list(self._runs.values())


def test_a_named_pair_s_old_link_moves_to_its_comparison_now(tmp_path, monkeypatch, examined):
    """The runs were recorded again, so no earlier onetrace names the old link; the pair the line names does."""
    from onetrace_console import site_links

    monkeypatch.setattr(site_links, "earlier_names", lambda store: {})
    pages = tmp_path / "pages"
    (pages / "diff").mkdir(parents=True)
    (pages / "diff" / f"{'cd' * 32}.html").write_text("the comparison now", encoding="utf-8")
    old = "/diff/" + "ab" * 32 + ".html"
    examined(2, "the moved page made, and where it sends")
    made = site_links.write_redirects(
        _Store(), pages, [old], pairs={old: ("p1-02-baseline-set2", "p1-08-candidate-set2")}
    )
    assert made == {old.lstrip("/"): f"diff/{'cd' * 32}.html"}
    assert f"url={'cd' * 32}.html" in (pages / old.lstrip("/")).read_text(encoding="utf-8")


def test_a_named_pair_the_build_does_not_hold_stops_it_naming_the_pair(tmp_path, monkeypatch, examined):
    from onetrace_console import site_links

    monkeypatch.setattr(site_links, "earlier_names", lambda store: {})
    pages = tmp_path / "pages"
    pages.mkdir()
    old = "/diff/" + "ab" * 32 + ".html"
    examined(1, "a pair with no comparison")
    with pytest.raises(site_links.Unplaced, match="p1-02-baseline-set2 and p9-99-nothing"):
        site_links.write_redirects(_Store(), pages, [old], pairs={old: ("p1-02-baseline-set2", "p9-99-nothing")})


SITE_LINKS_WORDS = (
    "A comparison link whose runs were recorded again names, after its path, the two runs it showed, and the "
    "build sends its old name to their comparison now."
)


@pytest.mark.parametrize("readme", ["README.md", "PYPI_DESCRIPTION.md"])
def test_the_readmes_say_a_link_may_name_its_two_runs(readme, examined):
    examined(1, readme)
    assert SITE_LINKS_WORDS in " ".join((REPO / readme).read_text(encoding="utf-8").split())
