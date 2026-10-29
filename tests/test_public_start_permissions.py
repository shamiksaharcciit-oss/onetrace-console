"""A public console started as the image starts it: as a user other than the one that built the demo.

The SDK writes a run's manifest and receipts readable by their owner only. The image builds the demo
as root and serves it as an unprivileged user, so the image's permission step must make the demo
readable (and still not writable) by everyone, or the console can't check the demo against its
build record at start. That check, and every other check at start, must refuse in one line -- never
raise -- when a file can't be read: the early check run found the console crashing with a
PermissionError traceback, and the host's log then held no access-log line at all.

Both run here as the image runs: the demo copied, owned by root, given the Dockerfile's own
permission step, and the check run by `nobody` in a child process. Root only (the serving user is
another user), and not on Windows, where the image does not run.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_public_mode import _clean_env, built  # noqa: F401

REPO = Path(__file__).resolve().parent.parent
NOBODY = 65534

pytestmark = pytest.mark.skipif(os.name == "nt" or getattr(os, "geteuid", lambda: 1)() != 0,
                                reason="the image's serving user is another user: needs root, not Windows")

def _image_permissions(folder: Path) -> None:
    """As the image: owned by root, then the Dockerfile's own chmod over the demo folder."""
    dockerfile = (REPO / "deploy" / "fly" / "Dockerfile").read_text(encoding="utf-8")
    modes = re.search(r"chmod -R (\S+) /srv/onetrace-demo", dockerfile).group(1)
    subprocess.run(["chown", "-R", "root:root", str(folder)], check=True)
    subprocess.run(["chmod", "-R", modes, str(folder)], check=True)


def _check_as_nobody(folder: str, packaged: bytes, conn) -> None:
    """The child: a fresh interpreter, started as root, imports everything the check imports as it
    runs (once it is `nobody` it can't read the interpreter's library under root's home), drops to
    `nobody`, runs `start_refusal`, and sends back its result as JSON -- or, had it raised, the
    traceback."""
    import json
    import traceback
    code, out, err = 0, "", ""
    try:
        import importlib.readers  # noqa: F401  (the packaged trust file is read through it)
        import onetrace_console.demo_store  # noqa: F401
        import onetrace_console.neighbours  # noqa: F401  (the check refuses a store holding its folder)
        import onetrace_console.serve  # noqa: F401
        import onetrace_console.public as public
        from onetrace_console.config import Config
        from onetrace_console.public import start_refusal
        public.demo_trust_bytes = lambda: packaged
        config = Config(public=True, store_root=str(Path(folder) / "store"),
                        trust_file=str(Path(folder) / "trust.json"), sign_in={"enabled": False})
        os.setgid(NOBODY)
        os.setuid(NOBODY)
        refused = start_refusal(config, Path(folder) / "store")
        out = json.dumps(None if refused is None else [refused.message, refused.fix])
    except BaseException:  # noqa: BLE001 - reported to the parent, which fails the test
        code, err = 1, traceback.format_exc()
    conn.send(json.dumps([code, out, err]))
    conn.close()


def _as_nobody(folder: Path) -> tuple[int, str, str]:
    """The console's start check over `folder`, run by `nobody`, in a child started with `spawn`, not
    `fork()`: in the full suite the test process has other threads by the time this runs, and forking
    such a process is what Python warns of. The child drops to `nobody` itself (`_check_as_nobody`)."""
    import json
    import multiprocessing
    import onetrace_console.public as public
    #: The packaged trust file, read now: the check compares the demo's with it, and this checkout
    #: may sit where `nobody` can't read (under root's home); the image's code is under /app,
    #: readable by every user. Read once here, handed to the child.
    packaged = public.demo_trust_bytes()
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_check_as_nobody, args=(str(folder), packaged, child))
    proc.start()
    child.close()
    try:
        said = parent.recv()
    finally:
        proc.join(timeout=300)
    code, out, err = json.loads(said)
    return code, out, err


@pytest.fixture
def imaged(built, tmp_path_factory):  # noqa: F811
    """A copy of the built demo under /tmp (which `nobody` can reach), with the image's permissions."""
    import tempfile
    work = Path(tempfile.mkdtemp(prefix="onetrace-image-perm-", dir="/tmp"))
    os.chmod(work, 0o755)
    folder = work / "demo"
    shutil.copytree(built, folder, symlinks=True)
    _image_permissions(folder)
    yield folder
    subprocess.run(["chmod", "-R", "u+w", str(work)], check=False)
    shutil.rmtree(work, ignore_errors=True)


def test_the_serving_user_can_check_the_demo_as_the_image_leaves_it(imaged, examined):
    """The SDK's owner-only files, after the image's permission step, read by the serving user."""
    manifest = next(imaged.glob("runs/*/MANIFEST.json"))
    examined(1, "start check as nobody")
    assert manifest.stat().st_mode & 0o004, "the image leaves the manifest readable by others"
    assert not manifest.stat().st_mode & 0o222, "and writable by no one"
    code, out, err = _as_nobody(imaged)
    assert code == 0 and out.strip() == "null", (out, err)


def test_a_file_it_cannot_read_is_a_one_line_refusal_never_a_traceback(imaged, examined):
    from onetrace_console.public import UNREADABLE_FIX
    manifest = next(imaged.glob("runs/*/MANIFEST.json"))
    os.chmod(manifest, 0o400)   # the owner's (root's) alone, as the SDK wrote it
    examined(1, "start check as nobody, one file unreadable")
    code, out, err = _as_nobody(imaged)
    assert code == 0 and "Traceback" not in err, err
    import json
    message, fix = json.loads(out)
    assert "cannot be read" in message and str(manifest) in message and "\n" not in message
    assert fix == UNREADABLE_FIX


def test_the_check_as_nobody_never_forks_a_multi_threaded_process(imaged, examined):
    """With another thread running, as the full suite's process has by the time this runs, starting
    the child raises no warning of a fork in a multi-threaded process: it is spawned, never forked."""
    import threading
    import warnings
    stop = threading.Event()
    other = threading.Thread(target=stop.wait, daemon=True)
    other.start()
    try:
        with warnings.catch_warnings(record=True) as got:
            warnings.simplefilter("always")
            code, out, err = _as_nobody(imaged)
    finally:
        stop.set()
        other.join(timeout=10)
    examined(1, "start check as nobody, beside another thread")
    assert code == 0 and out.strip() == "null", (out, err)
    assert not [w for w in got if "use of fork()" in str(w.message)], [str(w.message) for w in got]
