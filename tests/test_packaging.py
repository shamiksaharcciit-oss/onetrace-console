"""What `pip install onetrace-console` gives a user: the right version, the SDK it was tested with,
its pins readable from the installed package, and comparisons that work on a plain install.

The last test builds the wheel, installs it into a fresh venv with the SDK's own wheels (the
same bytes PyPI serves, from the local wheel cache, so no network is needed), and checks that a
comparison there answers 200 with the same report as the pinned install.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
META = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_version_is_0_1_0_everywhere(examined):
    import onetrace_console
    examined(3, "places the version is stated")
    assert META["version"] == "0.1.0"
    assert onetrace_console.__version__ == "0.1.0"
    out = subprocess.run([sys.executable, "-m", "onetrace_console", "--version"], capture_output=True,
                         text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert out.stdout.strip() == "0.1.0", out


def test_the_metadata_names_the_sdk_it_was_tested_with(examined):
    deps = META["dependencies"]
    examined(len(deps), "declared dependencies")
    assert "onetrace==0.2.0" in deps
    assert "onetrace-verify[crypto]==0.2.0" in deps
    assert META["requires-python"] == ">=3.12"
    assert len(META["authors"]) == 1 and META["authors"][0].get("name", "").strip(), META["authors"]


def test_no_private_username_in_the_shipped_project_files(examined):
    """No machine's own user folder is named: a `pytest-of-<user>` path may appear only with the
    placeholder, never a real account name."""
    import re
    files = [REPO / "pyproject.toml", REPO / "requirements.lock"]
    examined(len(files), "project files read")
    for f in files:
        named = re.findall(r"pytest-of-(?!<user>)[A-Za-z0-9_]+", f.read_text(encoding="utf-8"))
        assert not named, (f.name, named)


def test_the_pins_command_reads_the_lock_shipped_in_the_package(examined):
    """`onetrace-console pins` prints the lock from the installed package, which is the
    repository's own lock, byte for byte."""
    shipped = REPO / "src" / "onetrace_console" / "requirements.lock"
    examined(1, "shipped lock compared with the repository's")
    assert shipped.read_bytes() == (REPO / "requirements.lock").read_bytes()
    out = subprocess.run([sys.executable, "-m", "onetrace_console", "pins"], capture_output=True,
                         env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert out.returncode == 0, out.stderr
    assert out.stdout.replace(b"\r\n", b"\n") == shipped.read_bytes().replace(b"\r\n", b"\n")


def test_a_plain_install_is_identified_by_its_record(tmp_path, examined):
    """With no install report and no direct_url.json, the build is named by the installed
    distribution's version and the hashed lines of its RECORD: the files the wheel itself lists,
    so the same wheel gives the same identity on any Python and any machine."""
    from onetrace_console.compare import record_digest
    lines = ["onetrace/__init__.py,sha256=AAAA,10", "onetrace/emit.py,sha256=BBBB,20",
             "onetrace-0.2.0.dist-info/METADATA,sha256=CCCC,30"]
    unhashed = ["onetrace/__pycache__/emit.cpython-312.pyc,,", "onetrace-0.2.0.dist-info/INSTALLER,,",
                "onetrace-0.2.0.dist-info/RECORD,,"]
    a = record_digest("0.2.0", lines + unhashed)
    b = record_digest("0.2.0", list(reversed(lines)) + ["onetrace/__pycache__/emit.cpython-313.pyc,,"])
    examined(2, "RECORDs of one wheel, installed two ways")
    assert a == b and a.startswith("record:0.2.0:")
    assert record_digest("0.2.0", lines[:2]) != a, "a different set of files is a different build"
    assert record_digest("0.2.1", lines) != a, "a different version is a different build"


def _wheels() -> dict[str, Path]:
    from tools.fetch_wheel_cache import check
    cache = REPO / ".wheel-cache"
    found = {p.name.split("-")[0]: p for p in cache.glob("*.whl")}
    if not check():
        pytest.fail(f"the local wheel cache is not ready: {cache}\n    python tools/fetch_wheel_cache.py")
    return found


def test_a_plain_pip_install_compares_with_the_same_report_as_the_pinned_install(tmp_path, examined):
    """Build the wheel; install it into a fresh venv with pip resolving every dependency from the
    SDK's wheels alone, no other index and no install report; deliver two runs and compare them there. The comparison answers, and its
    report is the pinned install's, byte for byte."""
    wheels = _wheels()
    #: Built from a copy of the tracked files, so the build writes nothing into the repository.
    tree = tmp_path / "tree"
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    for rel in filter(None, tracked):
        if (REPO / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((REPO / rel).read_bytes())
    dist = tmp_path / "dist"
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    #: One process for each: run in the same process after build_wheel, setuptools writes the
    #: sdist into a folder left from the wheel's build, not into `dist`.
    for build in ("build_wheel", "build_sdist"):
        subprocess.run([sys.executable, "-c", f"import sys; from setuptools import build_meta as b; "
                        f"print(b.{build}(sys.argv[1]))", str(dist)], cwd=tree, check=True,
                       capture_output=True, env=clean)
    console_whl = next(dist.glob("onetrace_console-0.1.0-*.whl"))
    _check_the_viewer_ships_without_its_tests(console_whl, next(dist.glob("onetrace_console-0.1.0.tar.gz")))
    #: The wheel carries the demo's runs and trust file, so `onetrace-console demo` works installed.
    import zipfile
    demo = REPO / "src" / "onetrace_console" / "reference_demo"
    want = {f"onetrace_console/reference_demo/{p.relative_to(demo).as_posix()}"
            for p in demo.rglob("*") if p.is_file()}
    with zipfile.ZipFile(console_whl) as whl:
        assert want and want <= set(whl.namelist()), sorted(want - set(whl.namelist()))[:5]
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    #: The console's wheel, with pip resolving its dependencies itself from the wheel cache as a
    #: local index (the bytes PyPI serves for them) and nothing else: no wheelhouse, no other
    #: index. The SDK so arrives as from an index, so pip leaves no direct_url.json for it.
    installed = subprocess.run([str(py), "-m", "pip", "install", "-q", "--no-index", "--find-links",
                                str(REPO / ".wheel-cache"), str(console_whl)],
                               capture_output=True, text=True, env=clean)
    assert installed.returncode == 0, installed.stderr[-2000:]
    subprocess.run([str(py), "-m", "pip", "check"], check=True, capture_output=True, env=clean)
    #: The premise: the SDK arrived as from an index, so neither earlier identity source applies.
    found = subprocess.run([str(py), "-c", "import importlib.metadata as m; d = m.distribution('onetrace'); "
                            "print(d.read_text('direct_url.json') is None)"],
                           capture_output=True, text=True, env=clean).stdout.strip()
    assert found == "True", "the SDK was installed as a direct reference, so the RECORD path is not tested"
    #: And the plain install names its build by RECORD. Asserted, not left to the comparison: the
    #: temporary folder may sit inside a git checkout, where a later source would answer instead.
    named = subprocess.run([str(py), "-c", "from onetrace_console.compare import sdk_build_digest; "
                            "print(sdk_build_digest())"], capture_output=True, text=True, env=clean)
    assert named.stdout.startswith("record:0.2.0:"), (named.stdout, named.stderr[-1500:])
    listed = subprocess.run([str(py), "-m", "pip", "list"], capture_output=True, text=True, env=clean).stdout
    assert "onetrace-console" in listed and "0.1.0" in listed, listed
    here = _compare_report(sys.executable, {"PYTHONPATH": str(REPO / "src")}, tmp_path / "pinned")
    there = _compare_report(str(py), {}, tmp_path / "plain")
    examined(2, "comparisons of the same two runs: the pinned install and a plain one")
    assert there["status"] == 200, there
    assert here["status"] == 200, here
    #: Every comparison lays the two runs out in a fresh temporary folder, and the report names it
    #: (two comparisons on the same install differ there and nowhere else). That one field is
    #: masked, in both reports exactly twice (the baseline's and the candidate's); the rest must be
    #: the same bytes.
    masked_there, n_there = _mask_compare_folders(there["diff"])
    masked_here, n_here = _mask_compare_folders(here["diff"])
    assert (n_there, n_here) == (2, 2), f"the mask matched {n_there} and {n_here} fields, not 2 and 2"
    assert masked_there == masked_here, "the plain install's comparison report differs"


#: A comparison folder's path in a report, as JSON writes it: on Windows each backslash is escaped,
#: so the separator before `a` or `b` is two characters there and one (`/`) elsewhere.
_COMPARE_FOLDER = re.compile(r'"path": ?"[^"]*onetrace-compare-[^"/\\]+(?:/|\\\\)([ab])"')


def _mask_compare_folders(report: str) -> tuple[str, int]:
    return _COMPARE_FOLDER.subn(r'"path":"<compare folder>/\1"', report)


def test_the_compare_folder_mask_matches_the_path_on_every_platform(examined):
    """The same report, written on Linux and on Windows: masked, they are the same bytes, and each
    path field is masked once. Nothing else in the report is touched."""
    linux = '{"baseline":{"path":"/tmp/onetrace-compare-k2j8x_1q/a","run_id":"q1"},' \
            '"candidate":{"path":"/tmp/onetrace-compare-k2j8x_1q/b","run_id":"q2"}}'
    windows = ('{"baseline":{"path":"C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\'
               'onetrace-compare-r7b_bv2h\\\\a","run_id":"q1"},'
               '"candidate":{"path":"C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\'
               'onetrace-compare-r7b_bv2h\\\\b","run_id":"q2"}}')
    import json
    assert json.loads(windows)["baseline"]["path"].endswith("onetrace-compare-r7b_bv2h\\a"), "a real Windows path"
    examined(2, "reports, one per platform")
    (ml, nl), (mw, nw) = _mask_compare_folders(linux), _mask_compare_folders(windows)
    assert (nl, nw) == (2, 2), (nl, nw)
    assert ml == mw
    assert '"run_id":"q1"' in mw and '"run_id":"q2"' in mw


def _check_the_viewer_ships_without_its_tests(wheel: Path, sdist: Path) -> None:
    """The viewer's code ships in both; its tests, and anything named for where they came from,
    in neither."""
    import tarfile
    import zipfile
    with zipfile.ZipFile(wheel) as z:
        in_wheel = z.namelist()
    with tarfile.open(sdist) as t:
        in_sdist = [m.name.split("/", 1)[1] for m in t.getmembers() if "/" in m.name]
    for kind, names in (("wheel", in_wheel), ("sdist", in_sdist)):
        viewer = [n for n in names if "onetrace_console/viewer/" in n]
        assert any(n.endswith("onetrace_console/viewer/page.py") for n in viewer), (kind, viewer[:5])
        assert any(n.endswith("viewer/_vendor/ONETRACE_CONSOLE_SKIN_v1.md") for n in viewer), kind
        assert any(n.endswith("viewer/PROVENANCE.md") for n in viewer), kind
        assert not [n for n in viewer if "/tests/" in n], (kind, "the viewer's tests ship")
        named = [n for n in names if any(w in n for w in ("from_core", "Core_Ruling", ".tar.gz"))]
        assert not named, (kind, named)


_COMPARE = r'''
import json, sys, threading, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from onetrace_console.config import Config
from onetrace_console.serve import Handler, _render_all_pages
from onetrace_console.store import Store
from onetrace_console.access_log import AccessLog
root = Path(sys.argv[1]); root.mkdir(parents=True)
Handler.store_root = root; Handler.store = Store(root / "store")
Handler.config = Config(sign_in={**Config().sign_in, "enabled": False})
Handler.access_log = AccessLog(root / "access_log", max_segment_bytes=Handler.config.access_log_max_segment_bytes)
_render_all_pages(Handler.store, root, Handler.config)
httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{httpd.server_address[1]}"
keys = []
for tar in sys.argv[2:]:
    req = urllib.request.Request(base + "/v1/runs", data=Path(tar).read_bytes(), method="POST")
    keys.append(json.load(urllib.request.urlopen(req))["run_key"])
req = urllib.request.Request(f"{base}/compare?a={keys[0]}&b={keys[1]}", method="POST")
try:
    got = json.load(urllib.request.urlopen(req)); status = 200
except urllib.error.HTTPError as e:
    print(json.dumps({"status": e.code, "body": e.read().decode()[:2000]})); raise SystemExit(0)
from onetrace_console.compare import DIFF
cmp = Handler.store.get_comparison(got["comparison_key"])
run = cmp.verb(DIFF)
report = {name: Handler.store.get(key).decode() for name, key in run.reports}
print(json.dumps({"status": status, "diff": report.get("diff.json")}))
httpd.shutdown()
'''


def _compare_report(python: str, env: dict, root: Path) -> dict:
    from tests.test_ux_screens import RUNS, _checked_fixture
    from tests.conftest import make_tar
    _checked_fixture()
    tars = []
    for name in ("query-day1", "query-day2", "ingest-day1", "ingest-day2"):
        folder = RUNS / name
        files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}
        files["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(files.items())).encode()
        tar = root.parent / f"{root.name}-{name}.tar"
        tar.write_bytes(make_tar(files))
        tars.append(str(tar))
    script = root.parent / f"{root.name}-compare.py"
    script.write_text(_COMPARE, encoding="utf-8")
    out = subprocess.run([python, str(script), str(root), *tars], capture_output=True, text=True,
                         env={**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, **env}, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])
