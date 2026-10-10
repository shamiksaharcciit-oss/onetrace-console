"""IBM Plex Sans and Mono, bundled with the console, from a named upstream release.

The `woff2` files and the OFL text live in `src/onetrace_console/static/fonts/`, taken from the
npm releases `@ibm/plex-sans` 1.1.0 and `@ibm/plex-mono` 2.5.0, each tarball checked against the
registry's own sha512 integrity before anything was taken from it. These tests hold:
- each file's sha256, pinned here (written by tooling from the files, never typed);
- the provenance record naming both releases and their integrity;
- the OFL text shipped, and named in the operator README's storage section;
- the files declared as package data, so a wheel install carries them too;
- the route that serves them: to anyone, signed in or not (the sign-in page uses them), only
  these files, with the right content type -- and nothing else under `/static/`.
"""
from __future__ import annotations

import hashlib
import http.client
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).resolve().parent.parent
FONTS = REPO / "src" / "onetrace_console" / "static" / "fonts"

#: sha256 of each shipped file, written by tooling from the files taken from the releases below.
PINNED = {
    "IBMPlexMono-Medium.woff2": "33faf307fa6031fb4062276d7320a6d632de890cbb347576fd80cfa01077bc25",
    "IBMPlexMono-Regular.woff2": "ba204497f16b6d334cee9d1e963a831b73e3a56e1d6300a8489d18df7214b350",
    "IBMPlexSans-Medium.woff2": "5660f8a658f8bb50dbc005232f885eadffd2bc1c235c4f6fbb63469d1f9cde6d",
    "IBMPlexSans-Regular.woff2": "ba711a3085ff9f27440b6b9c4550cfc47c97bf36591d5da958b975bb3add8c1a",
    "IBMPlexSans-SemiBold.woff2": "f78048030eab62e860efa39a0df79e2e5581bf122eb95b9bc42c0b8a4988d205",
    "OFL.txt": "7e6b2818edbd8f6a01ae80641cc8f16a51080d08fb4e532be3a0b6f74adb07da",
}
RELEASES = {
    "@ibm/plex-sans": ("1.1.0", "sha512-WPgvO6Yfj2w5YbhyAr1tv95RUz4LRJlqN+CmYvBglabXteufP1D1E9BABMde+ZIKdRbFJDoKF5eQzfhpnbgZcQ=="),
    "@ibm/plex-mono": ("2.5.0", "sha512-STBJIPxPomOYPmBMO7z5TKPJUotAF9u3gAUumTqVgwgrAO+K4FRNh0MlhsoJjKhJKsMbBJR10/bk4inkj/wc1w=="),
}


def test_each_shipped_font_file_is_the_pinned_one(examined):
    shipped = sorted(p.name for p in FONTS.iterdir() if p.suffix in (".woff2", ".txt"))
    examined(len(shipped), "font files")
    assert shipped == sorted(PINNED), shipped
    for name, sha in PINNED.items():
        assert hashlib.sha256((FONTS / name).read_bytes()).hexdigest() == sha, name


def test_the_provenance_names_both_releases_their_integrity_and_every_file(examined):
    record = (FONTS / "FONTS.md").read_text(encoding="utf-8")
    examined(len(RELEASES) + len(PINNED), "provenance entries")
    for package, (version, integrity) in RELEASES.items():
        assert f"`{package}` {version}" in record and integrity in record, package
    for name, sha in PINNED.items():
        assert f"`{name}`" in record and sha in record, name


def test_the_ofl_text_ships_and_the_readme_names_it(examined):
    ofl = (FONTS / "OFL.txt").read_text(encoding="utf-8")
    examined(1, "licence text")
    assert "SIL Open Font License, Version 1.1" in ofl and 'Reserved Font Name "Plex"' in ofl
    readme = " ".join((REPO / "OPERATOR_README.md").read_text(encoding="utf-8").split())
    section = readme[readme.index("## Where the data lives"):]
    section = section[:section.index("### Backing up")]
    assert "static/fonts/OFL.txt" in section and "IBM Plex" in section


def test_the_fonts_are_package_data(examined):
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    examined(1, "pyproject read")
    assert "[tool.setuptools.package-data]" in text
    assert '"static/fonts/*.woff2"' in text and '"static/fonts/OFL.txt"' in text


def _get(base: str, path: str) -> tuple[int, str, bytes]:
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=20)
    conn.request("GET", path)
    r = conn.getresponse()
    return r.status, r.getheader("Content-Type") or "", r.read()


def test_the_fonts_are_served_to_anyone_and_nothing_else_is(server, examined):
    """With sign-in on and no session: the sign-in page itself uses these files."""
    base, _ = server
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    old = Handler.config
    Handler.config = Config(sign_in={"enabled": True})
    try:
        examined(len(PINNED) + 4, "static requests")
        for name in PINNED:
            status, ctype, body = _get(base, f"/static/fonts/{name}")
            assert status == 200, (name, status)
            assert body == (FONTS / name).read_bytes(), name
            assert ctype == ("font/woff2" if name.endswith(".woff2") else "text/plain; charset=utf-8"), ctype
        for path in ("/static/fonts/IBMPlexSans-Bold.woff2", "/static/fonts/FONTS.md",
                     "/static/fonts/../../serve.py", "/static/fonts/%2e%2e/%2e%2e/serve.py"):
            status, _, _ = _get(base, path)
            assert status in (400, 404), (path, status)
    finally:
        Handler.config = old
