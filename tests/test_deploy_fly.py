"""`deploy/fly/`: the hosted demo's files, as they must stay.

1. `public.json` is a configuration this console loads, public, listening on every interface inside
   the machine on the port `fly.toml` sends to, with the demo's store and trust file as the
   Dockerfile builds them;
2. `fly.toml` checks `/health`, forces HTTPS, and stops idle machines, keeping none on;
3. nothing in the folder names an app, a region, an organisation, a token, an address or a domain:
   those are set by whoever deploys. The scan's own sabotage plants one of each kind.
"""
from __future__ import annotations

import json
import re
import shutil
import tomllib
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parent.parent / "deploy" / "fly"

#: What may never be committed here, by kind. A domain is any dotted name ending in a
#: top-level domain, except the two the host's own documentation and machines use.
NAMES = {
    "an app name": re.compile(r"^\s*app\s*=", re.M),
    "a region": re.compile(r"^\s*primary_region\s*=", re.M),
    "an organisation": re.compile(r"(?:--org|\borg(?:anization)?\s*=)\s*[\"']?\w", re.I),
    "a token": re.compile(r"FlyV1 |\bf[mo]\d_[A-Za-z0-9_-]{8,}|FLY_API_TOKEN\s*=\s*\S"),
    "an email address": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "a domain": re.compile(r"\b(?:[a-z0-9-]+\.)+(?:com|dev|io|app|net|org|ai|co|sh|me|xyz)\b",
                           re.I),
}
ALLOWED_DOMAINS = {"fly.io", "fly.dev"}


def scan(folder: Path) -> list[str]:
    """Every name found in the folder's files, as `file: kind: text`."""
    found = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for kind, pattern in NAMES.items():
            for m in pattern.finditer(text):
                if kind == "a domain" and m.group(0).lower() in ALLOWED_DOMAINS:
                    continue
                found.append(f"{path.relative_to(folder).as_posix()}: {kind}: {m.group(0)}")
    return found


def test_the_folder_holds_the_four_files_and_the_kept_inputs(examined):
    """The four files, and `kept/`, the inputs the Dockerfile builds from where they are there
    (tests/test_deploy_fly_kept.py holds what is in it), and `site_links.txt`, the public site's links
    into the demo the kept build answers (the same file holds its rule)."""
    names = sorted(p.name for p in DEPLOY.iterdir())
    examined(len(names), "files in deploy/fly")
    assert names == ["Dockerfile", "README.md", "fly.toml", "kept", "public.json", "site_links.txt"], names


def test_public_json_is_a_public_configuration_on_the_port_fly_toml_names(examined):
    from onetrace_console.config import load
    config = load(DEPLOY / "public.json")
    fly = tomllib.loads((DEPLOY / "fly.toml").read_text(encoding="utf-8"))
    examined(2, "files read")
    assert config.public is True and config.sign_in["enabled"] is False
    assert config.host == "0.0.0.0" and config.port == fly["http_service"]["internal_port"] == 8080
    dockerfile = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    built = re.search(r"demo --public --build (\S+)", dockerfile).group(1)
    assert config.store_root == f"{built}/store" and config.trust_file == f"{built}/trust.json"
    #: Readable by every user (the serving user checks the build record at start), writable by none.
    assert f"chmod -R a+rX,a-w {built}" in dockerfile and "USER demo" in dockerfile
    assert "COPY deploy/fly/public.json /etc/onetrace-console/public.json" in dockerfile
    assert "ONETRACE_CONSOLE_CONFIG=/etc/onetrace-console/public.json" in dockerfile


def test_fly_toml_checks_health_forces_https_and_stops_idle_machines(examined):
    fly = tomllib.loads((DEPLOY / "fly.toml").read_text(encoding="utf-8"))
    service = fly["http_service"]
    examined(1, "fly.toml")
    assert service["force_https"] is True
    assert service["auto_stop_machines"] == "stop" and service["min_machines_running"] == 0
    assert [c["path"] for c in service["checks"]] == ["/health"]
    assert "min_machines_running = 1" in (DEPLOY / "fly.toml").read_text(encoding="utf-8"), \
        "the comment on keeping one machine on"


def test_nothing_in_the_folder_names_an_app_region_account_token_or_domain(examined):
    files = [p for p in DEPLOY.rglob("*") if p.is_file()]
    examined(len(files), "files scanned")
    assert scan(DEPLOY) == []


@pytest.mark.parametrize("kind,planted", [
    ("an app name", ("fly.toml", '\napp = "onetrace-demo"\n')),
    ("a region", ("fly.toml", '\nprimary_region = "lhr"\n')),
    ("an organisation", ("README.md", "\nfly apps create demo --org personal\n")),
    ("a token", ("README.md", "\nexport FLY_API_TOKEN=abc123\n")),
    ("an email address", ("README.md", "\nmail someone@example.com\n")),
    ("a domain", ("README.md", "\nopen demo.example.dev\n")),
])
def test_the_scan_finds_each_kind_planted(tmp_path, kind, planted, examined):
    copy = tmp_path / "fly"
    shutil.copytree(DEPLOY, copy)
    name, text = planted
    with (copy / name).open("a", encoding="utf-8") as fh:
        fh.write(text)
    found = scan(copy)
    examined(1, f"{kind} planted")
    assert any(f": {kind}: " in f for f in found), found
