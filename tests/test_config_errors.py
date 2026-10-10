"""A configuration file the console cannot use is refused in words.

    Config errors: print a clean message with a `fix:` line, never a traceback.

Every refusal `config.load` can make carries the one line an operator acts on, and each entry
point that reads the file -- `serve`, `admin create`, `token create` -- prints the message and
that line and exits 1. The top-level keys are checked for their types here too: before this, a
`port` written as a string passed loading and failed at bind with a traceback, and a port past
65535 did the same.
"""
from __future__ import annotations

import io
import json

import pytest

from onetrace_console.config import ENV_VAR

#: (case, the file's bytes -- or None for a path that is not there, what the message says).
BAD = [
    ("not-a-file", None, "which is not a file"),
    ("not-utf8", b"\xff\xfe{}", "not valid UTF-8"),
    ("not-json", b"{nope", "not valid JSON"),
    ("not-an-object", b"[]", "must be a JSON object"),
    ("unknown-key", {"prot": 8080}, "unknown configuration key"),
    ("port-a-string", {"port": "8080"}, "port must be"),
    ("port-a-boolean", {"port": True}, "port must be"),
    ("port-past-65535", {"port": 70000}, "port must be"),
    ("port-zero", {"port": 0}, "port must be"),
    ("host-a-number", {"host": 7}, "host must be"),
    ("host-empty", {"host": ""}, "host must be"),
    ("store-root-null", {"store_root": None}, "store_root must be"),
    ("limit-zero", {"max_members": 0}, "max_members must be"),
    ("timeout-a-string", {"request_timeout_seconds": "30"}, "request_timeout_seconds must be"),
    ("extensions-a-list", {"extensions": []}, "'extensions' must be a JSON object"),
    ("extension-unknown", {"extensions": {"graph": True}}, "unknown extension"),
    ("sign-in-a-string", {"sign_in": {"enabled": "yes"}}, "sign_in.enabled must be"),
    ("tls-half-set", {"sign_in": {"tls_cert_path": "a.pem"}}, "set together"),
]


def _named(tmp_path, monkeypatch, content) -> None:
    path = tmp_path / "config.json"
    if content is not None:
        if isinstance(content, dict):
            content = json.dumps({"store_root": (tmp_path / "s").as_posix(), **content}).encode()
        path.write_bytes(content)
    monkeypatch.setenv(ENV_VAR, str(path))


def _refused(err: str, says: str, start: str) -> None:
    assert err.startswith(start), err
    assert says in err, err
    lines = err.strip().splitlines()
    assert len(lines) == 2 and lines[1].startswith("fix: ") and len(lines[1]) > len("fix: "), err
    assert "Traceback" not in err


@pytest.mark.parametrize("case,content,says", BAD, ids=[c for c, _, _ in BAD])
def test_serve_refuses_a_file_it_cannot_use_with_a_fix_line(case, content, says, tmp_path,
                                                           monkeypatch, capsys):
    from onetrace_console import serve

    def never(*a, **k):
        raise AssertionError("it reached the listener with a configuration it cannot use")
    monkeypatch.setattr(serve, "ConsoleServer", never)
    _named(tmp_path, monkeypatch, content)
    assert serve.main([]) == 1
    _refused(capsys.readouterr().err, says, "refusing to start: ")


@pytest.mark.parametrize("argv", [["admin", "create", "alice"], ["token", "create", "ingester"]],
                         ids=["admin-create", "token-create"])
@pytest.mark.parametrize("case,content,says", [BAD[2], BAD[5]], ids=["not-json", "port-a-string"])
def test_the_admin_commands_refuse_it_the_same_way(argv, case, content, says, tmp_path,
                                                   monkeypatch, capsys):
    from onetrace_console.__main__ import main
    _named(tmp_path, monkeypatch, content)
    monkeypatch.setattr("sys.stdin", io.StringIO("a long enough password\n"))
    assert main(argv) == 1
    _refused(capsys.readouterr().err, says, "refusing: ")


def test_a_file_it_can_use_still_loads(tmp_path, monkeypatch):
    from onetrace_console.config import load_from_env
    _named(tmp_path, monkeypatch, {"host": "127.0.0.1", "port": 8081, "max_members": 64,
                                   "request_timeout_seconds": 12})
    config = load_from_env()
    assert (config.port, config.max_members, config.request_timeout_seconds) == (8081, 64, 12)
