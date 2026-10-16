"""The read-only public mode (`onetrace_console/public.py`), as a visitor and an operator meet it.

The demo is built once, as the image builds it (`onetrace-console demo --public --build`), and
served by a real console started with a configuration file that says `"public": true`:

1. the switch: absent, nothing changes; not a boolean, refused; beside sign-in, the onedoor
   extension, another trust file, a store with accounts or tokens, or a store with no pages,
   the console refuses to start, in words with the fix;
2. every write route, and a route that does not exist, answers 403 with the refusal before a byte
   of the body is read, and the store does not change;
3. the access log is standard output, one line per request, and nothing is written under the store;
4. the account and token commands refuse a public configuration;
5. every page answers 200 with the banner and every security header, and its one inline script
   is the one the policy names; the record download is a read and answers; no page shows a word
   no page may show;
6. a folder is never listed;
7. the built store is the demo: the package's runs byte for byte, their comparison, every page,
   and, once its permissions are the image's, the serving user cannot write it.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import pytest

from tests.test_folder_load import REPO, _Console, _free_port
from tools import container_check

PACKAGE_DEMO = REPO / "src" / "onetrace_console" / "demo_store"


def _tree(root: Path) -> dict[str, tuple[str, int]]:
    """Every file under `root`, its sha256 and when it was last written: what "the store did not
    change" compares. The time too, since a page drawn again can be the same bytes."""
    return {p.relative_to(root).as_posix(): (hashlib.sha256(p.read_bytes()).hexdigest(),
                                             p.stat().st_mtime_ns)
            for p in sorted(root.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    """The public demo, built once into a new folder as the image builds it."""
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("public") / "demo"
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "demo", "--public",
                          "--build", str(folder)], capture_output=True, text=True, timeout=600,
                         env={**_clean_env(), "PYTHONPATH": str(REPO / "src")})
    assert out.returncode == 0, out.stdout + out.stderr
    return folder


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"}


def _config(tmp_path: Path, folder: Path, **keys) -> Path:
    data = {"public": True, "host": "127.0.0.1", "port": _free_port(),
            "store_root": str(folder / "store"), "trust_file": str(folder / "trust.json"),
            "sign_in": {"enabled": False}, **keys}
    path = tmp_path / "public.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def served(built, tmp_path_factory):
    """A public console serving the built demo, started as the image starts it. Yields its base
    address, the built folder, and the console (whose output is the access log)."""
    tmp = tmp_path_factory.mktemp("served")
    config = _config(tmp, built)
    port = json.loads(config.read_text(encoding="utf-8"))["port"]
    before = _tree(built)
    c = _Console(tmp, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        yield f"http://127.0.0.1:{port}", built, c
    finally:
        c.stop()
    assert _tree(built) == before, "serving changed the built folder"


def _pages(folder: Path) -> list[str]:
    pages = folder / "store" / "pages"
    return sorted(p.relative_to(pages).as_posix() for p in pages.rglob("*.html"))


# ------------------------------------------------------------------------------- 1. the switch

def test_without_the_key_nothing_changes(server, tmp_path, examined):
    from onetrace_console.config import Config, load
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"store_root": str(tmp_path / "s")}), encoding="utf-8")
    assert Config().public is False and load(plain).public is False
    base, _root = server
    status, body, _ = container_check.raw_post(base, "/no-such-route", declared=0)
    status_home, headers, page = container_check.fetch(base, "/")
    examined(2, "requests to a console without the key")
    assert status == 404, (status, body)
    assert status_home == 200 and b'data-frame="banner"' not in page
    #: Without the key, none of public mode's own headers; the content policy every console sends
    #: (its fonts and scripts its own) is the local one.
    from onetrace_console.public import content_security_policy
    assert "strict-transport-security" not in headers and "x-frame-options" not in headers
    assert headers.get("content-security-policy") == content_security_policy(local=True)


@pytest.mark.parametrize("value", ["true", 1, None, [], {}])
def test_the_key_is_refused_unless_true_or_false(tmp_path, value, examined):
    from onetrace_console.config import ConfigError, load
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"public": value}), encoding="utf-8")
    examined(1, "configuration")
    with pytest.raises(ConfigError, match="public must be true or false"):
        load(path)


def _start(tmp_path: Path, config: Path) -> tuple[int, str]:
    """A start that must refuse. Stopped whatever happens: a console that starts serving instead
    is the failure, and must not outlive the test."""
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        return c.exited(timeout=60)
    finally:
        c.stop()


def _refused(code: int, out: str, *said: str) -> None:
    assert code == 1, out
    assert "refusing to start:" in out and "fix:" in out, out
    for words in said:
        assert words in out, (words, out)


def test_public_beside_sign_in_is_refused(built, tmp_path, examined):
    code, out = _start(tmp_path, _config(tmp_path, built, sign_in={"enabled": True}))
    examined(1, "start")
    _refused(code, out, "sign_in.enabled is true", "no accounts and no sign-in")


def test_public_beside_the_onedoor_extension_is_refused(built, tmp_path, examined):
    code, out = _start(tmp_path, _config(tmp_path, built, extensions={"onedoor": True}))
    examined(1, "start")
    _refused(code, out, "extensions.onedoor")


@pytest.mark.parametrize("trust", ["another", "none", "missing"])
def test_public_with_a_trust_file_not_the_demos_is_refused(built, tmp_path, trust, examined):
    other = tmp_path / "trust.json"
    other.write_text(json.dumps({"format": "onetrace-trust/0.1", "keys": []}), encoding="utf-8")
    named = {"another": str(other), "none": None, "missing": str(tmp_path / "absent.json")}[trust]
    code, out = _start(tmp_path, _config(tmp_path, built, trust_file=named))
    examined(1, "start")
    _refused(code, out, "not the packaged demo's trust file")


@pytest.mark.parametrize("held", ["accounts", "tokens"])
def test_public_over_a_store_with_accounts_or_tokens_is_refused(built, tmp_path, held, examined):
    root = tmp_path / "root"
    shutil.copytree(built / "store", root)
    (root / held).mkdir()
    (root / held / "someone.json").write_text("{}", encoding="utf-8")
    config = _config(tmp_path, built)
    data = json.loads(config.read_text(encoding="utf-8"))
    config.write_text(json.dumps({**data, "store_root": str(root)}), encoding="utf-8")
    code, out = _start(tmp_path, config)
    examined(1, "start")
    _refused(code, out, f"holds {held}")


def test_public_over_a_store_with_no_pages_is_refused_and_draws_none(built, tmp_path, examined):
    empty = tmp_path / "empty"
    empty.mkdir()
    config = _config(tmp_path, built)
    data = json.loads(config.read_text(encoding="utf-8"))
    config.write_text(json.dumps({**data, "store_root": str(empty)}), encoding="utf-8")
    code, out = _start(tmp_path, config)
    examined(1, "start")
    _refused(code, out, "has no pages drawn", "--build")
    assert list(empty.iterdir()) == [], "a refused start wrote into the store"


# ---------------------------------------------------------------- 2. every write, refused unread

@pytest.mark.parametrize("route", container_check.ROUTES)
def test_each_write_route_is_refused_before_its_body_is_read(served, route, examined):
    base, folder, _c = served
    before = _tree(folder)
    status, body, seconds = container_check.raw_post(base, route)
    examined(1, f"POST {route}")
    assert container_check.refusal_problems(status, body, seconds) == [], (status, body, seconds)
    from onetrace_console.public import REFUSAL
    assert body.decode("utf-8").strip() == REFUSAL
    assert _tree(folder) == before


def test_a_refusal_is_the_same_with_a_body_sent_in_full(served, examined):
    """A small, well-formed delivery is refused the same way: the refusal does not depend on the
    body being too large."""
    base, folder, _c = served
    req = urllib.request.Request(base + "/v1/runs", data=b"x" * 100, method="POST")
    examined(1, "POST with a body")
    with pytest.raises(urllib.error.HTTPError) as e:
        urllib.request.urlopen(req, timeout=30)
    assert e.value.code == 403


# --------------------------------------------------------------------- 3. the access log, on stdout

def test_the_access_log_is_standard_output_and_nothing_is_written(served, examined):
    base, folder, c = served
    container_check.fetch(base, "/log-check-read.html")
    container_check.raw_post(base, "/log-check-write")
    wanted = {("GET", "/log-check-read.html", 404), ("POST", "/log-check-write", 403)}
    seen = set()
    while not wanted <= seen:
        entry = json.loads(c.until("{", timeout=30))
        assert set(entry) == {"at", "principal", "method", "path", "status"}, entry
        assert entry["principal"] == "anonymous", entry
        seen.add((entry["method"], entry["path"], entry["status"]))
    examined(len(wanted), "access-log lines")
    assert not (folder / "store" / "access_log").exists(), "the access log was written to disk"


def _raw(base: str, request: bytes) -> int:
    """Send `request` as it is and return the status the console answers."""
    import re
    import socket
    from urllib.parse import urlsplit
    url = urlsplit(base)
    with socket.create_connection((url.hostname, url.port), timeout=30) as s:
        s.sendall(request)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return int(re.match(rb"HTTP/1\.[01] (\d{3})", data).group(1))


def test_a_public_consoles_output_is_its_access_log_and_nothing_else(built, monkeypatch, examined):
    """In-process, with the console's output caught: a page, a page not there, a refused write, a
    method the standard server answers itself, and a request it refuses to read (too many
    headers). Every line is
    an access-log entry of exactly five fields -- no line in the standard library's own form, which
    carries the client's address -- and each answer is one entry."""
    import io
    import threading
    from http.server import ThreadingHTTPServer

    from onetrace_console.config import Config
    from onetrace_console.public import StdoutAccessLog
    from onetrace_console.serve import Handler
    from onetrace_console.store import Store

    out = io.StringIO()
    monkeypatch.setattr(sys, "stderr", out)
    names = ("store_root", "store", "config", "access_log", "local_port", "timeout")
    saved = {n: Handler.__dict__[n] for n in names if n in Handler.__dict__}
    root = built / "store"
    Handler.store_root, Handler.store = root, Store(root / "store")
    Handler.config = Config(public=True, store_root=str(root), trust_file=str(built / "trust.json"),
                            sign_in={**Config().sign_in, "enabled": False})
    Handler.access_log, Handler.local_port, Handler.timeout = StdoutAccessLog(stream=out), None, 30
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        statuses = [
            container_check.fetch(base, "/")[0],
            container_check.fetch(base, "/not-there.html")[0],
            container_check.raw_post(base, "/v1/runs")[0],
            _raw(base, b"PUT / HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n"),
            _raw(base, b"GET / HTTP/1.1\r\n" + b"X: y\r\n" * 120 + b"\r\n"),
        ]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        for n in names:
            if n in saved:
                setattr(Handler, n, saved[n])
            elif n in Handler.__dict__:
                delattr(Handler, n)
    lines = out.getvalue().splitlines()
    examined(len(lines), "output lines")
    assert statuses == [200, 404, 403, 501, 431], statuses
    assert container_check.log_problems(lines) == [], lines
    entries = [json.loads(line) for line in lines]
    assert sorted(e["status"] for e in entries) == sorted(statuses), entries
    assert all(e["principal"] == "anonymous" for e in entries)
    assert not any("127.0.0.1" in line for line in lines), lines


def test_a_request_that_raises_is_one_json_error_line_and_the_console_serves_on(built, monkeypatch,
                                                                              examined):
    """In-process, on the console's own server class, with its output caught: a page whose drawing
    raises inside the handler. The output holds exactly one line that is not an access-log entry:
    one JSON error line -- when, "error", the exception's type, the traceback -- naming no client
    address or port. The console then answers the next request."""
    import io
    import threading

    import onetrace_console.frame as frame
    from onetrace_console.config import Config
    from onetrace_console.public import StdoutAccessLog
    from onetrace_console.serve import ConsoleServer, Handler
    from onetrace_console.store import Store

    out = io.StringIO()
    monkeypatch.setattr(sys, "stderr", out)

    def broken(*args, **kwargs):
        raise RuntimeError("the page could not be filled")
    monkeypatch.setattr(frame, "fill", broken)
    names = ("store_root", "store", "config", "access_log", "local_port", "timeout")
    saved = {n: Handler.__dict__[n] for n in names if n in Handler.__dict__}
    root = built / "store"
    Handler.store_root, Handler.store = root, Store(root / "store")
    Handler.config = Config(public=True, store_root=str(root), trust_file=str(built / "trust.json"),
                            sign_in={**Config().sign_in, "enabled": False})
    Handler.access_log, Handler.local_port, Handler.timeout = StdoutAccessLog(stream=out), None, 30
    httpd = ConsoleServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with pytest.raises((urllib.error.URLError, ConnectionError, OSError)):
            urllib.request.urlopen(base + "/home.html", timeout=30).read()
        after = container_check.fetch(base, "/health")[0]
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        for n in names:
            if n in saved:
                setattr(Handler, n, saved[n])
            elif n in Handler.__dict__:
                delattr(Handler, n)
    lines = out.getvalue().splitlines()
    others = container_check.log_problems(lines)
    examined(len(lines), "output lines")
    assert after == 200, "the console stopped serving after the error"
    assert len(others) == 1, (others, lines)
    error = json.loads(next(l for l in lines if '"event": "error"' in l))
    assert set(error) == {"at", "event", "exception", "traceback"}, error
    assert error["event"] == "error" and error["exception"] == "RuntimeError", error
    assert "the page could not be filled" in error["traceback"]
    assert not any("127.0.0.1" in l or str(port) in l for l in lines), lines
    assert "Exception occurred" not in out.getvalue()


def test_the_log_check_names_a_line_in_the_standard_librarys_form(examined):
    """The check's own sabotage: the standard library's request line, an error line, and an entry
    with a sixth field are each named; the two start lines and five-field entries pass."""
    entry = json.dumps({"at": "t", "principal": "anonymous", "method": "GET", "path": "/",
                        "status": 200})
    clean = ["onetrace-console serving on http://0.0.0.0:8080 (store root: /srv)",
             "onetrace-console public mode: read-only.", entry, entry]
    planted = [*clean,
               '172.17.0.1 - "GET /home.html HTTP/1.1" 200 -',
               "172.17.0.1 - code 501, message Unsupported method ('PUT')",
               json.dumps({**json.loads(entry), "client": "172.17.0.1"}),
               "onetrace-console public mode: read-only."]
    examined(len(planted), "lines")
    assert container_check.log_problems(clean) == []
    found = container_check.log_problems(planted)
    assert [f.split(" is not")[0] for f in found] == ["line 5", "line 6", "line 7", "line 8"], found


# ------------------------------------------------------------------------- 4. the CLI's writes

@pytest.mark.parametrize("command", [["admin", "create", "someone"], ["token", "create", "someone"],
                                     ["token", "revoke", "0"]])
def test_the_account_and_token_commands_refuse_a_public_configuration(built, tmp_path, command,
                                                                      examined):
    root = tmp_path / "root"
    config = _config(tmp_path, built)
    data = json.loads(config.read_text(encoding="utf-8"))
    config.write_text(json.dumps({**data, "store_root": str(root)}), encoding="utf-8")
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", *command],
                         input="a password long enough to be accepted\n", capture_output=True, text=True, timeout=60,
                         env={**_clean_env(), "PYTHONPATH": str(REPO / "src"),
                              "ONETRACE_CONSOLE_CONFIG": str(config)})
    examined(1, " ".join(command))
    assert out.returncode == 1, out.stdout + out.stderr
    assert "the configuration is public" in out.stderr, out.stderr
    assert not root.exists(), "the refused command made the store"


# ------------------------------------------------------------------ 5. every page, as served

def test_every_page_answers_with_the_banner_and_every_header(served, examined):
    from onetrace_console.public import security_headers
    base, folder, _c = served
    pages = _pages(folder)
    examined(len(pages), "pages served")
    assert len(pages) >= 50, pages
    want = {name.lower(): value for name, value in security_headers()}
    for rel in pages:
        status, headers, body = container_check.fetch(base, "/" + rel)
        assert container_check.page_problems(status, headers, body) == [], rel
        assert {k: headers.get(k) for k in want} == want, rel


def test_the_checker_names_each_header_dropped(served, examined):
    """The sabotage of the page check: each header taken out in turn is named as missing."""
    base, folder, _c = served
    status, headers, body = container_check.fetch(base, "/")
    examined(len(container_check.HEADERS), "headers dropped")
    assert container_check.page_problems(status, headers, body) == []
    for name in container_check.HEADERS:
        dropped = {k: v for k, v in headers.items() if k != name.lower()}
        problems = container_check.page_problems(status, dropped, body)
        assert problems[0] == f"no {name} header", name
        #: The Overview carries the relative-times script (0.1.1) and the theme switch's two: with
        #: no policy, each is also one the policy doesn't name, and the checker says so for each.
        extra = ["an inline script the policy does not name"] * 3 if name == "Content-Security-Policy" else []
        assert [p.split(" (")[0] for p in problems[1:]] == extra, (name, problems)


def test_the_policy_names_the_one_inline_script_and_the_checker_catches_another(served, examined):
    base, _folder, _c = served
    status, headers, body = container_check.fetch(base, "/executions-all.html")
    examined(1, "page")
    from onetrace_console.frame import THEME_HEAD_SCRIPT, THEME_SCRIPT
    from onetrace_console.viewer.page import PRINT_SCRIPT
    from onetrace_console.words import RELATIVE_TIME_SCRIPT
    #: The runs list carries the print helper, the relative times and the theme switch's two
    #: scripts, each once, each named.
    assert body.count(b"<script>") == 4
    assert all(body.count(s.encode()) == 1 for s in (PRINT_SCRIPT, RELATIVE_TIME_SCRIPT,
                                                     THEME_HEAD_SCRIPT, THEME_SCRIPT))
    assert container_check.page_problems(status, headers, body) == []
    planted = body.replace(b"</body>", b"<script>alert(1)</script></body>", 1)
    problems = container_check.page_problems(status, headers, planted)
    assert len(problems) == 1 and "inline script the policy does not name" in problems[0], problems


def test_the_checkers_words_are_the_consoles(examined):
    from onetrace_console.public import BANNER, REFUSAL, security_headers
    examined(3, "fixed words")
    assert BANNER.startswith(container_check.BANNER) or container_check.BANNER.startswith(BANNER)
    assert REFUSAL.startswith(container_check.REFUSED)
    assert tuple(name for name, _ in security_headers()) == container_check.HEADERS


def test_a_runs_record_download_is_a_read_and_answers(served, examined):
    base, folder, _c = served
    keys = sorted(p.name for p in (folder / "store" / "pages" / "runs").iterdir() if p.is_dir())
    examined(len(keys), "record downloads")
    from onetrace_console.demo_store import runs
    assert len(keys) == len(runs()), keys
    for key in keys:
        status, headers, body = container_check.fetch(base, f"/runs/{key}/record.tar")
        assert status == 200 and headers["content-type"] == "application/x-tar" and body, key
        assert "content-security-policy" in headers


def test_no_public_page_shows_a_word_no_page_may_show(served, examined):
    from tests.test_ux_screens import MONTHS, NOT_ON_A_PAGE, _text
    base, folder, _c = served
    pages = _pages(folder)
    examined(len(pages), "public pages read")
    found = []
    for rel in pages:
        text = _text(container_check.fetch(base, "/" + rel)[2].decode("utf-8"))
        found += [f"{rel}: {name}" for name, rx in NOT_ON_A_PAGE.items() if rx.search(text)]
        found += [f"{rel}: a month by name" for _ in MONTHS.finditer(text)]
    assert not found, found


# --------------------------------------------------------------------------- 6. no listing

@pytest.mark.parametrize("path", ["/runs", "/runs/", "/diff", "/diff/", "/static/", "/static/fonts/",
                                  "/store/", "/pages/", "/access_log/"])
def test_a_folder_is_never_listed(served, path, examined):
    base, _folder, _c = served
    status, headers, body = container_check.fetch(base, path)
    examined(1, path)
    assert status in (400, 404), (path, status)
    assert b"<a " not in body and "content-security-policy" in headers


# ------------------------------------------------------------------ 7. the built store is the demo

def test_a_public_start_writes_nothing_and_draws_nothing(built, tmp_path, examined):
    """Started and serving, a public console has written no file under the store: not a page
    drawn again, not an access log, not a record re-derived."""
    root = tmp_path / "copy"
    shutil.copytree(built, root, copy_function=shutil.copy2)
    before = _tree(root)
    config = _config(tmp_path, root)
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        port = json.loads(config.read_text(encoding="utf-8"))["port"]
        container_check.fetch(f"http://127.0.0.1:{port}", "/")
        after = _tree(root)
    finally:
        c.stop()
    examined(len(before), "files under the store")
    assert after == before, sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def test_the_built_store_is_the_builders_demo_compared_and_drawn(built, examined):
    """0.1.1: the image's store is the demo store's builder's -- its runs,
    its trust file (the packaged one), its comparisons -- under a build record that holds
    every byte of it."""
    from onetrace_console.demo_store import COMPARISONS, check_build_record, runs
    from onetrace_console.store import Store
    assert sorted(p.name for p in (built / "runs").iterdir()) == sorted(r.folder for r in runs())
    assert (built / "trust.json").read_bytes() == (PACKAGE_DEMO / "trust.json").read_bytes()
    assert check_build_record(built) == []
    record = json.loads((built / "BUILD_RECORD.json").read_text(encoding="utf-8"))
    assert record["covers"] == ["runs", "store", "trust.json"]
    store = Store(built / "store" / "store")
    stored, comparisons = list(store.runs()), list(store.comparisons())
    examined(len(stored) + len(comparisons), "stored runs and comparisons")
    assert sorted(r.run_id for r in stored) == sorted(r.run_id or r.folder for r in runs())
    assert len(comparisons) == len(COMPARISONS)
    pages = set(_pages(built))
    assert {"home.html"} | {f"diff/{c.key}.html" for c in comparisons} <= pages
    for run in stored:
        assert {f"runs/{run.key}/{n}" for n in ("answer.html", "case.html")} <= pages


@pytest.mark.parametrize("where", ["store/pages/home.html", "runs/p1-01-baseline-set1/MANIFEST.json",
                                   "trust.json"])
def test_public_over_a_demo_edited_after_its_build_is_refused(built, tmp_path, where, examined):
    """One byte changed anywhere the build record covers, and a public console doesn't start."""
    copy = tmp_path / "demo"
    shutil.copytree(built, copy)
    target = copy / where
    data = bytearray(target.read_bytes())
    data[len(data) // 2] ^= 0x01
    target.write_bytes(bytes(data))
    config = _config(tmp_path, copy)
    code, out = _start(tmp_path, config)
    examined(1, "start")
    if where == "trust.json":
        _refused(code, out, "not the packaged demo's trust file")
    else:
        _refused(code, out, f"{where} was changed", "--build")


def test_building_into_a_folder_that_is_not_new_and_empty_is_refused(tmp_path, examined):
    (tmp_path / "taken").mkdir()
    (tmp_path / "taken" / "x").write_text("x", encoding="utf-8")
    out = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "demo", "--public",
                          "--build", str(tmp_path / "taken")], capture_output=True, text=True,
                         timeout=120, env={**_clean_env(), "PYTHONPATH": str(REPO / "src")})
    no_public = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", "demo", "--build",
                                str(tmp_path / "new")], capture_output=True, text=True,
                               timeout=120, env={**_clean_env(), "PYTHONPATH": str(REPO / "src")})
    examined(2, "builds")
    assert out.returncode == 1 and "not a new, empty folder" in out.stderr, out.stderr
    assert no_public.returncode == 2 and "give --public" in no_public.stderr, no_public.stderr
    assert not (tmp_path / "new").exists()


_PROBE = r"""
import os, sys
store, files_only = sys.argv[1], sys.argv[2] == "1"
if len(sys.argv) > 3:
    os.setgid(int(sys.argv[3])); os.setuid(int(sys.argv[3]))
targets = [(os.path.join(store, "pages", "home.html"), "ab")]
if not files_only:
    targets.append((os.path.join(store, "pages", "new.html"), "xb"))
results = []
for target, mode in targets:
    try:
        with open(target, mode) as fh:
            fh.write(b"x")
        results.append("wrote")
    except PermissionError:
        results.append("refused")
print(" ".join(results))
"""


def _probe(store: Path, uid: int | None) -> list[str]:
    """Append to a page and create one, as `uid` (or as this process); what happened to each.
    On Windows a folder's read-only flag does not stop a file being made in it, so there only the
    file's own flag is tried."""
    files_only = "1" if os.name == "nt" else "0"
    args = [sys.executable, "-B", "-c", _PROBE, str(store), files_only]
    out = subprocess.run(args + ([str(uid)] if uid is not None else []), capture_output=True,
                         text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    made = store / "pages" / "new.html"
    if made.exists():
        made.unlink()
    return out.stdout.split()


def _lock(root: Path) -> None:
    """The image's permissions on the built store: no write bit anywhere (`chmod -R a-w`)."""
    for p in [root, *root.rglob("*")]:
        mode = stat.S_IMODE(p.stat().st_mode)
        p.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _unlock(root: Path) -> None:
    for p in [root, *root.rglob("*")]:
        p.chmod(stat.S_IMODE(p.stat().st_mode) | stat.S_IWUSR)


def _own(root: Path, uid: int) -> None:
    for p in [root, *root.rglob("*")]:
        os.chown(p, uid, uid)


def test_once_locked_the_serving_user_cannot_write_the_store(built, examined):
    """As the image: the store owned by root with no write bit, served by another user. Each layer
    is tried alone, after a control that writes a store the serving user owns, so a refusal is the
    layer's and not the probe's. Run as root, the serving user is `nobody`; otherwise it is this
    process's user, and the ownership layer is not tried."""
    as_root = getattr(os, "geteuid", lambda: None)() == 0
    serving = 65534 if as_root else None
    want = ["wrote"] if os.name == "nt" else ["wrote", "wrote"]
    refused = ["refused"] * len(want)
    #: Under /tmp when the serving user is another one: it must be able to reach the store, so
    #: that only the lock stands in its way (a temporary folder under root's home does not let it).
    work = Path(tempfile.mkdtemp(prefix="onetrace-public-lock-", dir="/tmp" if as_root else None))
    seen = {}
    try:
        work.chmod(0o755)
        store = work / "store"
        shutil.copytree(built / "store", store)
        if as_root:
            _own(store, serving)
        seen["control: the serving user's, writable"] = _probe(store, serving)
        _lock(store)
        seen["the mode alone: no write bit"] = _probe(store, serving)
        _unlock(store)
        if as_root:
            _own(store, 0)
            seen["the ownership alone: root's"] = _probe(store, serving)
            _lock(store)
            seen["as the image: root's, no write bit"] = _probe(store, serving)
            _unlock(store)
        examined(sum(len(v) for v in seen.values()), "writes tried")
        assert seen.pop("control: the serving user's, writable") == want, \
            "the probe cannot write even an unlocked store"
        assert seen == {k: refused for k in seen}, seen
    finally:
        _unlock(work)
        shutil.rmtree(work)


# --------------------------------------------------------------- the demo command, as a user runs it

def test_demo_public_serves_the_read_only_demo_on_this_machine(tmp_path, console, examined):
    port = _free_port()
    c = console(tmp_path, "demo", "--public", "--port", str(port))
    c.until("overview:")
    base = f"http://127.0.0.1:{port}"
    status, headers, page = container_check.fetch(base, "/")
    refused = container_check.raw_post(base, "/v1/runs")
    examined(2, "requests")
    assert container_check.page_problems(status, headers, page) == []
    assert container_check.refusal_problems(*refused) == []
    assert not any(tmp_path.iterdir()), "demo --public wrote into the folder it was started from"


@pytest.fixture
def console():
    started: list[_Console] = []

    def start(*args, **kw) -> _Console:
        c = _Console(*args, **kw)
        started.append(c)
        return c
    yield start
    for c in started:
        c.stop()
