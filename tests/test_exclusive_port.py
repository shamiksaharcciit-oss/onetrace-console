"""The listener's port is this console's alone.

    Windows port sharing: set `SO_EXCLUSIVEADDRUSE` on Windows, so a second instance fails
    with a clear message. Tier A, because it's the listener.

`http.server.HTTPServer` sets `allow_reuse_address`, so the standard server asks for
`SO_REUSEADDR`. On Windows that option lets a second socket bind a port another socket is
already listening on, and the two then share its connections: a second console, or anything
else, could take requests meant for this one. `ConsoleServer` asks for `SO_EXCLUSIVEADDRUSE`
there instead, and `main()` turns a port it cannot take into a clear refusal. Elsewhere the
kernel already refuses a second listener on the same address, so the same tests hold on every
platform and fail on Windows alone without the fix.
"""
from __future__ import annotations

import json
import os
import socket

import pytest

from onetrace_console.config import ENV_VAR
from onetrace_console.serve import ConsoleServer, Handler


@pytest.fixture
def first():
    """A real console listener on an ephemeral loopback port, never served."""
    server = ConsoleServer(("127.0.0.1", 0), Handler)
    try:
        yield server
    finally:
        server.server_close()


def test_another_socket_cannot_bind_the_consoles_port(first):
    """The hijack: a socket asking for `SO_REUSEADDR` binds the address the console holds."""
    port = first.server_address[1]
    other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        with pytest.raises(OSError):
            other.bind(("127.0.0.1", port))
    finally:
        other.close()


def test_the_listener_asks_for_the_port_as_the_platform_needs(first):
    """Windows: exclusively, and without `SO_REUSEADDR` (the two cannot be combined there).
    Elsewhere `SO_REUSEADDR` only lets a restart take a port still in TIME_WAIT, and is kept."""
    if os.name == "nt":
        assert first.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
        assert first.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
    else:
        assert ConsoleServer.allow_reuse_address


def test_a_second_console_on_the_same_port_refuses_with_a_clear_message(first, tmp_path,
                                                                       monkeypatch, capsys):
    from onetrace_console import serve
    port = first.server_address[1]
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"host": "127.0.0.1", "port": port,
                                  "store_root": (tmp_path / "data").as_posix(),
                                  "sign_in": {"enabled": False}}), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config))

    def listened(self):
        raise RuntimeError("the second console took the port and listened")
    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", listened)
    assert serve.main([]) == 1
    err = capsys.readouterr().err
    assert f"refusing to start: cannot listen on 127.0.0.1:{port}" in err
    assert "another process" in err
    assert "Traceback" not in err
