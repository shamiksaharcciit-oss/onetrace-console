"""The container serves TLS itself, by default, and never without sign-in.

    Option 1, TLS inside the container, as the container's default:
    - the container config binds 0.0.0.0;
    - it names sign_in.tls_cert_path and sign_in.tls_key_path under a mounted path;
    - it refuses to start until a certificate is mounted, with a fix: line and no traceback.
    Option 2, a reverse proxy, is documented as the alternative ... Option 3 is refused.

These tests hold the image's own configuration and the refusal. The real `docker run` checks
the specification asks for -- a mounted test certificate reaches /health over TLS from the host, and
without one the container refuses -- are `tools/container_tls_check.py`, whose output is in the
report: this suite runs offline and without Docker.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from onetrace_console.config import load
from onetrace_console.signin import refuse_if_insecure
from tests.test_review_fixes import _refused_in_words, _serve_with

ROOT = Path(__file__).resolve().parent.parent
CONTAINER = ROOT / "config" / "container.json"
TLS_DIR = "/etc/onetrace-console/tls"


def test_the_container_config_serves_tls_on_every_interface_with_sign_in():
    config = load(CONTAINER)
    assert config.host == "0.0.0.0", "reachable through a published port"
    assert config.sign_in["enabled"] is True, "option 3, a container without sign-in, is refused"
    assert config.sign_in["tls_cert_path"] == f"{TLS_DIR}/cert.pem"
    assert config.sign_in["tls_key_path"] == f"{TLS_DIR}/key.pem"
    refuse_if_insecure(config)  # TLS is configured, so the non-loopback listener is allowed


def test_the_image_installs_the_container_config_and_checks_its_health_over_tls():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY config/container.json /etc/onetrace-console/config.json" in dockerfile
    assert "config/default.json /etc/onetrace-console/config.json" not in dockerfile
    probes = [line for line in dockerfile.splitlines() if "urlopen" in line]
    assert probes and all("https://127.0.0.1:8080/health" in line for line in probes)


def _container_config_here(tmp_path, *, cert: bool, key: bool) -> dict:
    """The image's own config, with its /data and certificate folder moved under `tmp_path`."""
    body = json.loads(CONTAINER.read_text(encoding="utf-8"))
    tls = tmp_path / "tls"
    tls.mkdir()
    if cert:
        (tls / "cert.pem").write_text("a certificate", encoding="utf-8")
    if key:
        (tls / "key.pem").write_text("a key", encoding="utf-8")
    body["store_root"] = (tmp_path / "data").as_posix()
    body["sign_in"]["tls_cert_path"] = (tls / "cert.pem").as_posix()
    body["sign_in"]["tls_key_path"] = (tls / "key.pem").as_posix()
    return body


@pytest.mark.parametrize("cert,key,says", [
    (False, False, "no TLS certificate at"),
    (True, False, "no TLS key at"),
], ids=["nothing-mounted", "no-key"])
def test_without_a_mounted_certificate_it_refuses_with_a_fix_line(tmp_path, monkeypatch, capsys,
                                                                  cert, key, says):
    body = _container_config_here(tmp_path, cert=cert, key=key)
    assert _serve_with(tmp_path, monkeypatch, body) == 1
    err = _refused_in_words(capsys, says)
    assert "/etc/onetrace-console/tls" in err.split("\nfix: ", 1)[1], "the fix names the mount"
    assert not list((tmp_path / "data").rglob("*.html")), "nothing was drawn before the refusal"
