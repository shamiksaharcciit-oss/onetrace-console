"""End to end, over real HTTP: POST /v1/decisions, then GET the rendered Policy and
Incidents pages -- the same "no mocking of the handler" discipline test_serve.py uses.
"""
from __future__ import annotations

import urllib.error
import urllib.request

from onetrace_console.config import Config
from onetrace_console.serve import Handler
from tests.test_upload_hardening import _member, _tar


def _get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post(base: str, path: str, body: bytes) -> tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_a_request_split_across_two_posted_exports_is_accepted_both_times(
        server, onedoor_fixture_dir, examined):
    """#23 over real HTTP: the second delivery used to be stored, then fail rendering
    with a 500, and every later POST failed the same way."""
    import hashlib

    base, _ = server
    old_config = Handler.config
    Handler.config = Config(extensions={"onedoor": True}, sign_in={**Config().sign_in, "enabled": False})
    try:
        lines = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes().decode("utf-8") \
            .split("\n")[:-1]
        statuses = []
        for name, part in (("export-1.jsonl", lines[:1]), ("export-2.jsonl", lines[1:])):
            data = ("\n".join(part) + "\n").encode("utf-8")
            sidecar = f"{hashlib.sha256(data).hexdigest()}  {name}\n".encode("utf-8")
            status, body = _post(base, "/v1/decisions",
                                 _tar(_member(name, data), _member(f"{name}.sha256", sidecar)))
            statuses.append((status, body))
        examined(len(statuses), "split decision exports posted over real HTTP")
        assert [s for s, _ in statuses] == [201, 201], statuses
        status, policy_html = _get(base, "/policy.html")
        assert status == 200 and policy_html.count(b"<tr data-request-id=") == 5
    finally:
        Handler.config = old_config


def test_ingesting_a_decision_export_over_http_renders_the_policy_page(
        server, onedoor_fixture_dir, examined):
    base, _ = server
    old_config = Handler.config
    Handler.config = Config(extensions={"onedoor": True}, sign_in={**Config().sign_in, "enabled": False})
    try:
        jsonl = (onedoor_fixture_dir / "onedoor-export.jsonl").read_bytes()
        sidecar = (onedoor_fixture_dir / "onedoor-export.jsonl.sha256").read_bytes()
        archive = _tar(_member("onedoor-export.jsonl", jsonl),
                       _member("onedoor-export.jsonl.sha256", sidecar))

        examined(1, "decision exports posted over real HTTP")
        status, body = _post(base, "/v1/decisions", archive)
        assert status == 201, body

        status, policy_html = _get(base, "/policy.html")
        assert status == 200
        assert b"Policy" in policy_html
        assert b"executed" in policy_html

        status, incidents_html = _get(base, "/incidents.html")
        assert status == 200
        assert b"I-ONEDOOR-DECISION" in incidents_html
    finally:
        Handler.config = old_config
