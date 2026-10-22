"""Shared fixtures: a real run folder, and deliveries built from it.

THE RUN IS COMMITTED HERE, DIGEST-CHECKED
-----------------------------------------
It used to come from the pinned canary clone under `.pins/`, read fresh at test time.
That clone is gone -- the SDK now comes from PyPI by hash, and the viewer from a
wheelhouse wheel, neither of which is a place to keep a loose data fixture -- so this run is
now a committed copy under `tests/fixtures/r11/`, with its own `SHA256SUMS` and
`PROVENANCE.md` recording where it came from and why a copy of DATA is not the vendoring
`test_pins.py` forbids for CODE. See `tests/fixtures/r11/PROVENANCE.md`.

`run_folder` checks every file against `SHA256SUMS` before handing the folder to a test, and
**refuses rather than skips** on any mismatch: a skipped test is a test whose examined
population is zero, and this suite's whole subject is whether real received bytes survive a
round trip.
"""
from __future__ import annotations

import hashlib
import io
import tarfile
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

#: A real SDK-emitted run: three receipts, a fan-in, `declared_edges`, and it passes the
#: verifier (76 rows, PASS -- measured on the canary channel).
RUN_FOLDER = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"
SHA256SUMS = REPO / "tests" / "fixtures" / "r11" / "SHA256SUMS"

#: A real onedoor decision export: one permit-shaped request (two rows,
#: exec_intent + exec_result, sharing a request_id -- onedoor's own shape, see
#: tests/fixtures/onedoor/PROVENANCE.md), one deny, one propose. Committed under
#: tests/fixtures/onedoor/, digest-checked the same way as run_folder below.
ONEDOOR_FIXTURE_DIR = REPO / "tests" / "fixtures" / "onedoor"
ONEDOOR_SHA256SUMS = ONEDOOR_FIXTURE_DIR / "SHA256SUMS"

#: What a delivery carries: the manifest and the receipts it names. `localize/` is a verb
#: report that happens to live in the same folder; it is not part of the record.
def _delivery_paths(folder: Path) -> list[Path]:
    manifest = folder / "MANIFEST.json"
    paths = [manifest]
    import json
    for entry in json.loads(manifest.read_bytes().decode("utf-8")).get("chain", []):
        paths.append(folder / entry["file"])
    return paths


@pytest.fixture(scope="session")
def run_folder() -> Path:
    if not RUN_FOLDER.is_dir():
        pytest.fail(
            f"the committed run folder is not there: {RUN_FOLDER}\n"
            f"This refuses rather than skips: these tests exist to show that real "
            f"received bytes survive a round trip, and a skip would report success for "
            f"having examined nothing.")
    sums = {}
    for line in SHA256SUMS.read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        sums[rel] = digest
    mismatched = []
    for rel, want in sums.items():
        got = hashlib.sha256((RUN_FOLDER / rel).read_bytes()).hexdigest()
        if got != want:
            mismatched.append(f"{rel}: SHA256SUMS says {want}, file is {got}")
    assert mismatched == [], (
        "the committed r11 fixture has drifted from its recorded digest:\n  "
        + "\n  ".join(mismatched)
        + "\nThis refuses rather than uses the changed bytes: the fixture is meant to be "
          "the SDK's own frozen output, not something edited in place.")
    return RUN_FOLDER


@pytest.fixture(scope="session")
def onedoor_fixture_dir() -> Path:
    if not ONEDOOR_FIXTURE_DIR.is_dir():
        pytest.fail(
            f"the committed onedoor fixture is not there: {ONEDOOR_FIXTURE_DIR}\n"
            f"This refuses rather than skips, for the same reason run_folder does above.")
    sums = {}
    for line in ONEDOOR_SHA256SUMS.read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        sums[rel] = digest
    mismatched = []
    for rel, want in sums.items():
        got = hashlib.sha256((ONEDOOR_FIXTURE_DIR / rel).read_bytes()).hexdigest()
        if got != want:
            mismatched.append(f"{rel}: SHA256SUMS says {want}, file is {got}")
    assert mismatched == [], (
        "the committed onedoor fixture has drifted from its recorded digest:\n  "
        + "\n  ".join(mismatched))
    return ONEDOOR_FIXTURE_DIR


@pytest.fixture
def onedoor_export_bytes(onedoor_fixture_dir: Path) -> bytes:
    return (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()


@pytest.fixture
def onedoor_export_sha256(onedoor_fixture_dir: Path) -> bytes:
    return (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()


#: hand-made receipts standing in for the SDK's own, which does not
#: emit decision_refs yet. See tests/fixtures/synthetic_receipts/README.md.
SYNTHETIC_RECEIPTS_DIR = REPO / "tests" / "fixtures" / "synthetic_receipts"
SYNTHETIC_RECEIPTS_SUMS = SYNTHETIC_RECEIPTS_DIR / "SHA256SUMS"


@pytest.fixture(scope="session")
def synthetic_receipts_dir() -> Path:
    if not SYNTHETIC_RECEIPTS_DIR.is_dir():
        pytest.fail(f"the committed synthetic receipts fixture is not there: "
                   f"{SYNTHETIC_RECEIPTS_DIR}")
    sums = {}
    for line in SYNTHETIC_RECEIPTS_SUMS.read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        sums[rel] = digest
    mismatched = [
        f"{rel}: SHA256SUMS says {want}, file is {hashlib.sha256((SYNTHETIC_RECEIPTS_DIR / rel).read_bytes()).hexdigest()}"
        for rel, want in sums.items()
        if hashlib.sha256((SYNTHETIC_RECEIPTS_DIR / rel).read_bytes()).hexdigest() != want]
    assert mismatched == [], "\n".join(mismatched)
    return SYNTHETIC_RECEIPTS_DIR


@pytest.fixture
def files(run_folder: Path) -> dict[str, bytes]:
    """`path -> bytes` for one delivery, plus the SHA256SUMS a sidecar would compute."""
    out: dict[str, bytes] = {}
    for path in _delivery_paths(run_folder):
        out[path.relative_to(run_folder).as_posix()] = path.read_bytes()
    lines = [f"{hashlib.sha256(b).hexdigest()}  {p}" for p, b in out.items()]
    out["SHA256SUMS"] = ("\n".join(lines) + "\n").encode("utf-8")
    return out


@contextmanager
def preview_veto_off():
    """Ingest without the preview veto: storing one of the exam's preview-format
    fixtures DIRECTLY, as a run stored before the 0.2.0 pin moved was. A new preview
    delivery is otherwise refused (422); these fixtures are about what a console does with a run
    it already holds. Every use says why."""
    import onetrace_console.ingest as ingest
    original = ingest.preview_not_run_row
    ingest.preview_not_run_row = lambda said: None
    try:
        yield
    finally:
        ingest.preview_not_run_row = original


@pytest.fixture
def preview_stored_directly():
    """`preview_veto_off` for a whole test: for HTTP tests whose uploads are preview fixtures
    (the console under test runs in-process, in a thread)."""
    with preview_veto_off():
        yield


def make_tar(files: dict[str, bytes]) -> bytes:
    """A deterministic tar of the given files, in the given order."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size = len(blob)
            info.mtime = 0
            info.mode = 0o644
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def ipv6_loopback_port(*, windows: bool | None = None) -> int:
    """A free port on the IPv6 loopback, MEASURED by binding ('::1', 0).

    The IPv6 tests check a real property -- the console listens on, and states, an IPv6 address
    when there is one -- so they are not Windows-only. Where the bind fails (a Linux host with
    IPv6 turned off in its kernel: Errno 99), the test is skipped, naming the failure. On
    Windows a failed probe FAILS the test instead: that host has IPv6, and its run is what
    covers these tests, so a skip there would hide the very thing they check.
    """
    import os
    import socket
    if windows is None:
        windows = os.name == "nt"
    try:
        probe = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        try:
            probe.bind(("::1", 0))
            return probe.getsockname()[1]
        finally:
            probe.close()
    except OSError as e:
        said = f"Errno {e.errno}: {e.strerror}"
        if windows:
            pytest.fail(f"no IPv6 loopback on this Windows host ({said}); a skip here would hide "
                        f"what this test checks")
        pytest.skip(f"this host has no IPv6 loopback ({said})")


@pytest.fixture(scope="session")
def explain_command(tmp_path_factory) -> tuple[Path, Path]:
    """The published onetrace-explain, installed from the wheel cache by its pinned hash into a folder
    of its own: never into this environment, never a dependency of the console. (command, its
    library folder), found by the console's own lookup with the folder's scripts first. Refuses
    rather than skips where the cache is not ready, as the pin tests do."""
    import os
    import subprocess
    import sys
    from onetrace_console import explain as e
    from tools import fetch_wheel_cache as w
    if not w.check():
        pytest.fail(f"the local wheel cache is not there or does not match: {w.CACHE}\n"
                    f"    python tools/fetch_wheel_cache.py")
    (requirement, (_, sha)), = w.TEST_COMMANDS.items()
    root = tmp_path_factory.mktemp("onetrace-explain")
    req = root / "requirement.txt"
    req.write_text(f"{requirement} --hash=sha256:{sha}\n", encoding="utf-8")
    lib = root / "lib"
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--find-links",
                           str(w.CACHE), "--require-hashes", "--target", str(lib), "-r", str(req)],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr
    scripts = next((lib / d for d in ("Scripts", "bin") if (lib / d).is_dir()), None)
    found = e.find(os.name == "nt", str(scripts) if scripts else None, str(root / "no-python"), lambda n: None)
    assert found is not None and found.parent == scripts, (found, scripts)
    return found, lib


@pytest.fixture
def explain_installed(explain_command, monkeypatch) -> Path:
    """The console finds the published onetrace-explain: its lookup answers the installed command,
    whose library folder is put first on the command's import path."""
    import os
    from onetrace_console import explain as e
    found, lib = explain_command
    monkeypatch.setattr(e, "command", lambda: found)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(lib), os.environ.get("PYTHONPATH")])))
    return found


@pytest.fixture
def delivery(files: dict[str, bytes]) -> bytes:
    return make_tar(files)


@pytest.fixture
def store(tmp_path):
    from onetrace_console.store import Store
    return Store(tmp_path / "store")


@pytest.fixture
def server(tmp_path):
    """A real running console, in a thread, on an ephemeral port -- for any test that
    needs to exercise `onetrace_console.serve` over real HTTP rather than by calling its
    functions directly. Torn down after the test. Shared here (not defined per test
    module) because `tests/test_upload_hardening.py` needs the identical fixture
    `tests/test_serve.py` already had.
    """
    with serving(tmp_path) as served:
        yield served


@contextmanager
def serving(tmp_path: Path):
    """`server`'s console, for a fixture of another scope: the same console, the same teardown."""
    import threading

    from http.server import ThreadingHTTPServer

    from onetrace_console.access_log import AccessLog
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler, _render_all_pages
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed

    _require_installed()
    store_root = tmp_path / "data"
    store_root.mkdir()
    Handler.store_root = store_root
    Handler.store = Store(store_root / "store")
    #: Sign-in named OFF: the schema default is on, and the tests that
    #: exercise sign-in switch it on themselves (`roles_enabled`, `test_signin_flow`).
    Handler.config = Config(sign_in={**Config().sign_in, "enabled": False})
    Handler.access_log = AccessLog(store_root / "access_log",
                                   max_segment_bytes=Handler.config.access_log_max_segment_bytes)
    _render_all_pages(Handler.store, store_root, Handler.config)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}", store_root
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------- the standing rule

@pytest.fixture
def examined(request):
    """Report how many items this check looked at. Zero is a failure of the check.

    A standing rule. See `tests/examined.py` for why it is a
    recorded count rather than a habit.
    """
    from tests.examined import record

    def report(count, what):
        return record(request.node.nodeid, count, what)

    return report


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Print what every check examined, so the run states its own coverage.

    This is where the work-order report's per-check numbers come from. Generated by the run,
    never transcribed (X-11).
    """
    from tests.examined import summary_lines

    terminalreporter.write_line("")
    for line in summary_lines():
        terminalreporter.write_line(line)


# Under pytest-xdist (`-n`), each test runs in a worker process, and its `examined` records
# land in that worker's `RECORDS`. The summary above is printed by the controller, which
# recorded nothing itself, so a parallel run said "NOTHING WAS RECORDED ... the recording is
# broken" while every check had in fact recorded (found by the parallel trial). Each worker
# hands its records back at the end of its session, and the controller adds them before
# printing. Both hooks do nothing in a serial run; `optionalhook` because
# `pytest_testnodedown` exists only where xdist is installed.

def pytest_sessionfinish(session, exitstatus):
    workeroutput = getattr(session.config, "workeroutput", None)
    if workeroutput is not None:                      # this process is an xdist worker
        from tests.examined import RECORDS
        workeroutput["examined"] = [(r.nodeid, r.what, r.count) for r in RECORDS]


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    from tests.examined import RECORDS, Report
    RECORDS.extend(Report(nodeid, what, count)
                   for nodeid, what, count in node.workeroutput.get("examined", ()))


def whole_folds(html: str) -> str:
    """`html` with each fingerprint's fold read whole: its short summary dropped, the whole value
    it holds kept -- so a check that a page carries a fingerprint reads the whole one, which is
    on the page, one fold away."""
    import re
    return re.sub(r'(<details class="fingerprint"[^>]*>)<summary class="mono">[^<]*</summary>', r"\1", html)


# ---------------------------------------------------------- the public demo, built once a session

#: The shared builds, by name: each one's folder, what its build returned, and its contents digest.
SHARED: dict[str, dict] = {}


def tree_digest(root: Path) -> str:
    """The contents digest in its standing form: the sha256 of the `sha256sum -b` lines of every
    file under `root`, named `./<path>` and sorted by bytes (`find . -type f | LC_ALL=C sort`)."""
    names = sorted(("./" + p.relative_to(root).as_posix()).encode("utf-8")
                   for p in root.rglob("*") if p.is_file())
    lines = b"".join(hashlib.sha256((root / n[2:].decode("utf-8")).read_bytes()).hexdigest().encode()
                     + b" *" + n + b"\n" for n in names)
    return hashlib.sha256(lines).hexdigest()


def _shared(name: str, folder: Path, said=None) -> dict:
    SHARED[name] = {"folder": folder, "said": said, "digest": tree_digest(folder)}
    return SHARED[name]


@pytest.fixture(scope="session")
def shared_demo(tmp_path_factory) -> dict:
    """The public demo, built once a session with `build_public` and read by every module that
    reads the demo as built. Read-only: a module that changes it fails `_shared_demo_unchanged`.
    A module that writes takes its own copy (`demo_copy`)."""
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("shared-demo") / "demo"
    said, _ = build_public(folder)
    return _shared("shared_demo", folder, said)


@pytest.fixture(scope="session")
def shared_cli_demo(tmp_path_factory) -> dict:
    """The public demo, built once a session as the image builds it (`demo --public --build`), and
    read by every module that reads that build. Read-only, as `shared_demo` is."""
    import os
    import subprocess
    import sys
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("shared-cli-demo") / "demo"
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "demo", "--public",
                          "--build", str(folder)], capture_output=True, text=True, timeout=600,
                         env={**{k: v for k, v in os.environ.items()
                                 if k != "ONETRACE_CONSOLE_CONFIG"},
                              "PYTHONPATH": str(REPO / "src")})
    assert out.returncode == 0, out.stdout + out.stderr
    return _shared("shared_cli_demo", folder)


def demo_copy(shared: dict, dest: Path) -> Path:
    """A module's own copy of a shared build, for a module that changes what it reads."""
    import shutil
    shutil.copytree(shared["folder"], dest, symlinks=True, copy_function=shutil.copy2)
    return dest


@pytest.fixture(scope="module", autouse=True)
def _shared_demo_unchanged(request):
    """After each module: every shared build still has the contents digest it was built with. A
    changed one fails here, naming the module; the next module is held to the changed digest, so
    each change is named once, by the module that made it."""
    yield
    changed = []
    for name, shared in SHARED.items():
        now = tree_digest(shared["folder"])
        if now != shared["digest"]:
            changed.append(f"{name} ({shared['folder']}): {shared['digest']} before, {now} after")
            shared["digest"] = now
    if changed:
        pytest.fail(f"{request.module.__name__} changed a shared demo build, which every module "
                    f"reads as built: " + "; ".join(changed) + ". Give the module its own copy "
                    f"(demo_copy).", pytrace=False)
