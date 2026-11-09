"""What the tests of the Set up Explain form share: keyring and onetrace-explain 0.3.0, each installed from
the local wheel cache by its pinned hash into a folder of its own (never this environment, never a
dependency of the console); a keychain in a folder of the test's own (`keychain_stub`), never the
machine's; and a model server on this machine's loopback that keeps every request it is sent and answers
as the test asks. No model is called.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

STUB = Path(__file__).resolve().parent / "keychain_stub"
BACKEND = "stub_keychain.FolderKeychain"
#: The key the tests store, found nowhere but the keychain's own folder and the request's header.
KEY = "sk-test-planted-0123456789abcdefKEY"
#: Every module keyring brings, so a test after these finds keyring exactly as importable as before.
MODULES = ("keyring", "jaraco", "more_itertools", "stub_keychain")


def _install(target: Path, pins: dict) -> None:
    from tools import fetch_wheel_cache as w
    req = target.parent / f"{target.name}-requirements.txt"
    req.write_text("".join(f"{r} --hash=sha256:{sha}\n" for r, (_, sha) in pins.items()), encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--no-index", "--find-links",
                           str(w.CACHE), "--require-hashes", "--target", str(target), "-r", str(req)],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, done.stdout + done.stderr


@pytest.fixture(scope="session")
def keyring_lib(tmp_path_factory) -> Path:
    """keyring and what it needs, from the wheel cache by hash, in a folder of its own."""
    from tools import fetch_wheel_cache as w
    if not w.check():
        pytest.fail(f"the local wheel cache is not there or does not match: {w.CACHE}\n"
                    f"    python tools/fetch_wheel_cache.py")
    lib = tmp_path_factory.mktemp("keyring") / "lib"
    _install(lib, w.KEYCHAIN)
    return lib


@pytest.fixture(scope="session")
def explain03(tmp_path_factory) -> tuple[Path, Path]:
    """onetrace-explain 0.3.0, from the wheel cache by its pinned hash (`ONE_ENVIRONMENT`, as on PyPI), in a
    folder of its own: (its command, its library folder)."""
    from onetrace_console import explain as e
    from tools import fetch_wheel_cache as w
    if not w.check():
        pytest.fail(f"the local wheel cache is not there or does not match: {w.CACHE}\n"
                    f"    python tools/fetch_wheel_cache.py")
    root = tmp_path_factory.mktemp("onetrace-explain-0.3")
    lib = root / "lib"
    _install(lib, {k: v for k, v in w.ONE_ENVIRONMENT.items() if k.startswith("onetrace-explain==")})
    scripts = next((lib / d for d in ("Scripts", "bin") if (lib / d).is_dir()), None)
    found = e.find(os.name == "nt", str(scripts) if scripts else None, str(root / "no-python"), lambda n: None)
    assert found is not None and found.parent == scripts, (found, scripts)
    return found, lib


def _forget_keyring() -> None:
    for name in list(sys.modules):
        if name.split(".")[0] in MODULES:
            del sys.modules[name]


@pytest.fixture
def keychain(keyring_lib, tmp_path, monkeypatch) -> Path:
    """keyring importable in this test (and in what it runs), its keychain a folder of the test's own.
    Yields the folder; afterwards keyring is as importable as it was before."""
    folder = tmp_path / "keychain"
    folder.mkdir()
    _forget_keyring()
    monkeypatch.syspath_prepend(str(STUB))
    monkeypatch.syspath_prepend(str(keyring_lib))
    monkeypatch.setenv("ONETRACE_TEST_KEYCHAIN", str(folder))
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", BACKEND)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(keyring_lib), str(STUB),
                                                                  os.environ.get("PYTHONPATH")])))
    import keyring
    import stub_keychain
    keyring.set_keyring(stub_keychain.FolderKeychain())
    yield folder
    #: The test's own patches first (one may have set `sys.modules["keyring"]` aside), then keyring forgotten.
    monkeypatch.undo()
    _forget_keyring()


@pytest.fixture
def explain03_installed(explain03, keychain, monkeypatch) -> Path:
    """The console finds onetrace-explain 0.3.0: its library folder first on the command's import path,
    keyring and the test keychain after it."""
    from onetrace_console import explain as e
    found, lib = explain03
    monkeypatch.setattr(e, "command", lambda: found)
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(lib), os.environ["PYTHONPATH"]]))
    return found


class Model:
    """A model server on 127.0.0.1: every request kept (its path, headers and body), each answered as
    `answer` says: "reply" (a 200 with `text` as the message), or "error" (`status`, with `text` as the
    body)."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.answer, self.text, self.status = "reply", "", 500
        model = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                model.requests.append({"path": self.path, "headers": dict(self.headers.items()), "body": body})
                if model.answer == "error":
                    data = model.text.encode("utf-8")
                    self.send_response(model.status)
                else:
                    data = json.dumps({"choices": [{"message": {"content": model.text}}]}).encode("utf-8")
                    self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base_url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


@pytest.fixture
def model():
    m = Model()
    yield m
    m.httpd.shutdown()
    m.httpd.server_close()


def named(path, root) -> str:
    """A found file's name under `root`, with `/` on every system."""
    return path.relative_to(root).as_posix()


def files_holding(root: Path, secret: str, *, but: Path | None = None) -> list[str]:
    """Every file under `root` whose bytes hold `secret`, but those under `but` (the keychain itself)."""
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and not (but is not None and p.is_relative_to(but)):
            try:
                if secret.encode("utf-8") in p.read_bytes():
                    out.append(named(p, root))
            except OSError:
                pass
    return out


def key_problems(root: Path) -> list[str]:
    """The files under `root` holding the planted key, but the keychain's own folder."""
    return [f"{p} holds the planted key" for p in files_holding(root, KEY, but=root / "keychain")]


@pytest.fixture
def planted_key_searched(tmp_path):
    """After the test, every file it wrote (its whole folder) is searched for the planted key, the
    keychain's own folder set aside; a file holding it fails the test."""
    yield
    found = key_problems(tmp_path)
    assert found == [], found
