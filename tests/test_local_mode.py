"""Local mode -- the console with no configuration file named.

    The console binds to 127.0.0.1 only, unless an explicit flag says otherwise. There's no
    sign-in in local mode.

Loopback alone does not keep a browser out: a web page the local user opens can post to
127.0.0.1, and a hostile name can be pointed at 127.0.0.1 (DNS rebinding). So local mode also
refuses a request whose Host is not this listener's own loopback name, and a state-changing
request from another origin. The independent review of the first version found both open.

Everything here runs `serve.main()` itself, or a real HTTP server with local mode on.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import replace

import pytest

from onetrace_console.config import ENV_VAR, Config


class _Stop(Exception):
    """Raised by the stand-in server's `serve_forever`, after `main()` has bound and said so."""


class _FakeServer:
    """Records the address `main()` binds, then stops `main()` where it would serve. Also
    records what stderr had said by the time it was constructed, so a banner printed before
    the bind is caught."""
    address = None
    said_before_bind = None
    capture = None

    def __init__(self, address, handler):
        type(self).address = address
        if type(self).capture is not None:
            type(self).said_before_bind = type(self).capture.readouterr().err

    def serve_forever(self):
        raise _Stop()

    def server_close(self):
        pass


@pytest.fixture
def local_main(tmp_path, monkeypatch):
    """`serve.main` with the config variable absent, a clean working directory, and a
    stand-in server. Returns a runner that gives (bound address, stderr, stdout)."""
    import onetrace_console.serve as serve_module
    monkeypatch.delenv(ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(serve_module, "ConsoleServer", _FakeServer)
    _FakeServer.address = None
    saved = {n: getattr(serve_module.Handler, n, None) for n in
             ("account_store", "session_store", "token_store", "rate_limit_per_account",
              "rate_limit_per_client", "rate_limit_concurrent_hashes", "local_port")}

    def run(capsys, argv=()):
        _FakeServer.capture, _FakeServer.said_before_bind = capsys, None
        with pytest.raises(_Stop):
            serve_module.main(list(argv))
        said = capsys.readouterr()
        _FakeServer.capture = None
        return _FakeServer.address, (_FakeServer.said_before_bind or "") + said.err, said.out

    yield serve_module, run
    for name, value in saved.items():
        setattr(serve_module.Handler, name, value)


# ------------------------------------------------------------------- the forcing itself

def test_local_config_forces_loopback_and_no_sign_in_whatever_the_base_says():
    """The forcing, tested on its own: whatever `Config()` defaults to now or later."""
    from onetrace_console.serve import LOCAL_HOST, _local_config
    base = Config(host="0.0.0.0", port=9000, sign_in={**Config().sign_in, "enabled": True})
    forced = _local_config(base)
    assert (forced.host, forced.port) == (LOCAL_HOST, 9000)
    assert forced.sign_in["enabled"] is False
    assert LOCAL_HOST == "127.0.0.1"


def test_main_uses_the_forcing(local_main, capsys, monkeypatch):
    """`main()` goes through `_local_config`: a sabotaged one moves the listener."""
    serve_module, run = local_main
    monkeypatch.setattr(serve_module, "_local_config", lambda base: replace(
        base, host="10.9.8.7", sign_in={**base.sign_in, "enabled": False}))
    address, _, _ = run(capsys)
    assert address[0] == "10.9.8.7", "main() does not route local mode through _local_config"


def test_with_no_config_file_the_console_starts_in_local_mode(local_main, capsys):
    serve_module, run = local_main
    #: Placeholders in the six sign-in slots, so "None afterwards" proves main() reset them.
    for name in ("account_store", "session_store", "token_store", "rate_limit_per_account",
                 "rate_limit_per_client", "rate_limit_concurrent_hashes"):
        setattr(serve_module.Handler, name, object())
    address, err, out = run(capsys)
    assert address == ("127.0.0.1", 8080)
    assert not serve_module.Handler.config.sign_in.get("enabled")
    for name in ("account_store", "session_store", "token_store", "rate_limit_per_account",
                 "rate_limit_per_client", "rate_limit_concurrent_hashes"):
        assert getattr(serve_module.Handler, name) is None, name
    assert serve_module.Handler.local_port == 8080


def test_the_banner_says_the_address_and_the_store_after_binding(local_main, capsys, tmp_path):
    """Review finding 3: the port and the store in the one message, printed once the socket
    is bound -- not before, so a failed bind is never preceded by "listens on"."""
    _, run = local_main
    _, err, _ = run(capsys)
    assert "local mode" not in (_FakeServer.said_before_bind or ""), "banner before the bind"
    assert "local mode" in err
    assert "127.0.0.1:8080 only" in err
    assert str((tmp_path / "store").resolve()) in err
    assert "read and write" in err, "the banner says callers can write, not only read"


def test_a_variable_set_but_blank_refuses_rather_than_falling_into_local_mode(
        local_main, capsys, monkeypatch):
    """Review finding 2: a blank value is a mistake by someone who meant to name a file."""
    serve_module, _ = local_main
    for blank in ("", " "):
        monkeypatch.setenv(ENV_VAR, blank)
        assert serve_module.main([]) == 1
        assert "set but blank" in capsys.readouterr().err
    assert _FakeServer.address is None, "it never reached a listener"


def test_unknown_arguments_are_refused_not_ignored(local_main, capsys):
    """Review note 8: `serve --host 0.0.0.0` used to be silently ignored."""
    serve_module, _ = local_main
    assert serve_module.main(["--host", "0.0.0.0"]) == 2
    assert "takes no arguments" in capsys.readouterr().err


def test_local_mode_refuses_a_store_that_was_set_up_with_sign_in(local_main, capsys, tmp_path):
    """Review note 11: accounts in the store mean it was protected; local mode would serve it
    open. Refused, with the way out named."""
    serve_module, _ = local_main
    accounts = tmp_path / "store" / serve_module.ACCOUNTS_DIRNAME
    accounts.mkdir(parents=True)
    (accounts / "admin.json").write_text("{}", encoding="utf-8")
    assert serve_module.main([]) == 1
    assert "set up with sign-in" in capsys.readouterr().err


# --------------------------------------------------------- config-file mode, at main()

def _config_file(tmp_path, monkeypatch, **fields):
    path = tmp_path / "config.json"
    body = {"host": "127.0.0.1", "port": 8080, "store_root": (tmp_path / "s").as_posix()}
    body.update(fields)
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))


def test_config_file_mode_still_refuses_plain_http_beyond_loopback_with_sign_in(
        local_main, capsys, tmp_path, monkeypatch):
    """Review finding 4: `refuse_if_insecure` inside `main()` was tested only on its own. Now
    the refusal is printed with its fix and exits 1, never a traceback."""
    serve_module, _ = local_main
    _config_file(tmp_path, monkeypatch, host="0.0.0.0", sign_in={"enabled": True})
    assert serve_module.main([]) == 1
    err = capsys.readouterr().err
    assert "refusing to start: sign_in.enabled is true" in err and "\nfix: configure both" in err
    assert _FakeServer.address is None, "it never listened"


def test_config_file_mode_with_sign_in_off_warns_and_is_not_local_mode(
        local_main, capsys, tmp_path, monkeypatch):
    serve_module, run = local_main
    _config_file(tmp_path, monkeypatch, sign_in={"enabled": False})
    _, err, _ = run(capsys)
    assert "WARNING: sign_in.enabled is false" in err
    assert "local mode" not in err
    assert serve_module.Handler.local_port is None, "no local-mode guard in config-file mode"


# ------------------------------------------------ over real HTTP: the browser guard

@pytest.fixture
def local_server(server):
    """The suite's real server, with local mode's guard switched on for its own port."""
    from urllib.parse import urlsplit

    from onetrace_console.serve import Handler
    base, store_root = server
    saved = Handler.local_port
    Handler.local_port = urlsplit(base).port
    try:
        yield base, store_root
    finally:
        Handler.local_port = saved


def _call(base, path, *, method="GET", body=None, headers=None):
    request = urllib.request.Request(base + path, data=body, method=method,
                                     headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


def test_a_foreign_host_name_is_refused(local_server, examined):
    """DNS rebinding: a hostile name pointed at 127.0.0.1 arrives with its own Host."""
    base, _ = local_server
    port = base.rsplit(":", 1)[1]
    examined(2, "requests with a foreign and an own Host")
    status, _, _ = _call(base, "/", headers={"Host": f"attacker.example:{port}"})
    assert status == 421
    status, _, _ = _call(base, "/health", headers={"Host": f"localhost:{port}"})
    assert status == 200


def test_a_cross_site_write_is_refused_and_stores_nothing(local_server, files, examined):
    """A web page the local user opens posting a run: refused by Origin, and by the
    browser's own Sec-Fetch-Site where Origin is absent."""
    from tests.conftest import make_tar
    base, store_root = local_server
    examined(2, "cross-site POSTs to /v1/runs")
    for headers in ({"Origin": "https://evil.example", "Content-Type": "text/plain"},
                    {"Sec-Fetch-Site": "cross-site", "Content-Type": "text/plain"}):
        status, _, _ = _call(base, "/v1/runs", method="POST", body=make_tar(files),
                             headers=headers)
        assert status == 403, headers
    assert not list((store_root / "store" / "runs").glob("*")), "nothing was stored"


def test_a_same_origin_write_is_accepted(local_server, files):
    from tests.conftest import make_tar
    base, _ = local_server
    status, body, _ = _call(base, "/v1/runs", method="POST", body=make_tar(files),
                            headers={"Origin": base})
    assert status == 200, body[:200]


def test_local_mode_serves_no_sign_in_and_sets_no_cookie(local_server):
    base, _ = local_server
    status, _, headers = _call(base, "/signin")
    assert status == 404
    assert "Set-Cookie" not in headers



def test_a_file_in_accounts_that_is_not_an_account_does_not_refuse(local_main, capsys, tmp_path):
    """Closing review A: `.gitkeep`, `desktop.ini`, `.DS_Store` are not accounts."""
    serve_module, run = local_main
    accounts = tmp_path / "store" / serve_module.ACCOUNTS_DIRNAME
    accounts.mkdir(parents=True)
    for name in (".gitkeep", "desktop.ini", ".DS_Store"):
        (accounts / name).write_text("", encoding="utf-8")
    address, _, _ = run(capsys)
    assert address == ("127.0.0.1", 8080)


# ------------------------------------------------- the guard's header hygiene, and more

def _raw(base, lines: list[str], body: bytes = b"") -> tuple[int, bytes]:
    """A request written by hand, for header shapes urllib will not send."""
    import socket
    from urllib.parse import urlsplit
    u = urlsplit(base)
    with socket.create_connection((u.hostname, u.port), timeout=10) as s:
        s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
    return int(data.split(b" ", 2)[1]), data


def test_duplicate_guard_headers_are_refused(local_server, examined):
    """Closing review C: RFC 9112 says two Hosts is a 400; two Origins or two
    Sec-Fetch-Sites cannot be read as one."""
    base, _ = local_server
    port = base.rsplit(":", 1)[1]
    own = f"127.0.0.1:{port}"
    cases = [
        ["GET / HTTP/1.1", f"Host: {own}", "Host: evil.example"],
        ["POST /v1/runs HTTP/1.1", f"Host: {own}", f"Origin: http://{own}",
         "Origin: https://evil.example", "Content-Length: 0"],
        ["POST /v1/runs HTTP/1.1", f"Host: {own}", "Sec-Fetch-Site: same-origin",
         "Sec-Fetch-Site: cross-site", "Content-Length: 0"],
    ]
    examined(len(cases), "requests with a guard header twice")
    for lines in cases:
        status, _ = _raw(base, lines)
        assert status == 400, lines


def test_an_absolute_form_target_must_name_this_listener_too(local_server):
    base, _ = local_server
    port = base.rsplit(":", 1)[1]
    status, _ = _raw(base, [f"GET http://evil.example:{port}/home.html HTTP/1.1",
                            f"Host: 127.0.0.1:{port}"])
    assert status == 421
    status, _ = _raw(base, [f"GET http://127.0.0.1:{port}/health HTTP/1.1",
                            f"Host: 127.0.0.1:{port}"])
    assert status == 200


def test_local_mode_pages_cannot_be_framed_or_sniffed(local_server):
    """Closing review E: a cross-site page can embed a local page even if it cannot read it."""
    base, _ = local_server
    _, _, headers = _call(base, "/health")
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Cross-Origin-Resource-Policy") == "same-origin"
    assert headers.get("X-Content-Type-Options") == "nosniff"


def test_a_refused_host_is_told_the_address_that_works(local_server):
    """Closing review F: an ssh tunnel on another port gets 421 -- and the address to use."""
    base, _ = local_server
    port = base.rsplit(":", 1)[1]
    status, body, _ = _call(base, "/", headers={"Host": "127.0.0.1:9000"})
    assert status == 421 and f"127.0.0.1:{port}" in body.decode("utf-8")


def test_config_file_mode_carries_no_local_guard_headers(server):
    """The guard and its headers are local mode's alone."""
    from onetrace_console.serve import Handler
    assert Handler.local_port is None
    base, _ = server
    _, _, headers = _call(base, "/health")
    assert "X-Frame-Options" not in headers
