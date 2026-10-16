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
    "IBMPlexMono-Medium-Latin1.woff2": "41201b658a328b9d00368215c2f1102770f80b15952ab82631e4006255e6365d",
    "IBMPlexMono-Medium-Pi.woff2": "92bd18415e8c43a2569f615e4e84a94b1b1c4e0377ba9d8f4d894bbf6ffcc39d",
    "IBMPlexMono-Regular-Latin1.woff2": "e8993d946649b9d01abb1ed06d574b19d8ea3e66b5c3948602db335c44c18e56",
    "IBMPlexMono-Regular-Pi.woff2": "b8002770aa636f544ba43e124da6a227301769754f295eae26e16475b469c767",
    "IBMPlexSans-Medium-Latin1.woff2": "b5610af04d0d4b5a14a621d96d974b993e945a065db1a8861918f69ef9321934",
    "IBMPlexSans-Medium-Pi.woff2": "bf05f10c977353cfb5a5c11e8973adf77c2b93a4798da3aa0dd8ba5088e12515",
    "IBMPlexSans-Regular-Latin1.woff2": "b5ad7bd39f996144915f0ad9849a90183b27d8c28ad97ed98af5b1bebc51f6b1",
    "IBMPlexSans-Regular-Pi.woff2": "1487059829a180f975627e473acc81ff22c2c0faf1da09b314c27eeb41b7f2e4",
    "IBMPlexSans-SemiBold-Latin1.woff2": "fff0ab3a88b0b4aa0b693e4f0201359a15183b08e3fa5696d1918d8f0ade8ad5",
    "IBMPlexSans-SemiBold-Pi.woff2": "768421433d850d3a30118dddf05972625d99ee49bc32c5a8fd26bbe020c4d0f9",
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


# ------------------------------------------------------------------ what the faces cover

def _covered(ranges: str) -> set[int]:
    out = set()
    for part in ranges.split(","):
        a, _, b = part.removeprefix("U+").partition("-")
        out |= set(range(int(a, 16), int(b or a, 16) + 1))
    return out


def console_characters() -> set[int]:
    """Every character the console's own words can draw: its sentence tables and every string in
    its source, printable ASCII and beyond."""
    import ast
    from onetrace_console.viewer import sentences as S
    texts = [v[0] if isinstance(v, tuple) else str(v)
             for name in ("TABLE", "FIXED", "RULED", "PROVISIONAL", "LABELS")
             for v in getattr(S, name).values()]
    for path in (REPO / "src" / "onetrace_console").rglob("*.py"):
        texts += [n.value for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                  if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    #: Less what no page ever draws as itself: a control, bidirectional or surrogate character is
    #: shown as its escape (`viewer.page._UNSHOWN`).
    from onetrace_console.viewer.page import _UNSHOWN
    return {ord(c) for t in texts for c in t if 0x20 <= ord(c) and not _UNSHOWN.match(c)}


def coverage_problems(faces: dict, needed: set[int]) -> list[str]:
    out = []
    for family in sorted({f for f, _, _ in faces.values()}):
        held = set().union(*(_covered(r) for f, _, r in faces.values() if f == family))
        missing = sorted(needed - held)
        if missing:
            out.append(f"{family}: no face holds {', '.join(f'U+{c:04X}' for c in missing[:8])}")
    return out


def test_each_family_holds_every_character_the_console_writes(examined):
    from onetrace_console.frame import _FACES
    needed = console_characters()
    examined(len(needed), "characters the console's words use")
    assert coverage_problems(_FACES, needed) == []


def test_the_stylesheet_names_the_ranges_the_provenance_records(examined):
    from onetrace_console.frame import _FACES, stylesheet
    sheet = stylesheet().decode("utf-8")
    record = (FONTS / "FONTS.md").read_text(encoding="utf-8")
    examined(len(_FACES), "faces")
    for name, (_family, _weight, chars) in _FACES.items():
        assert f"url(/static/fonts/{name}) format('woff2');unicode-range:{chars}}}" in sheet, name
        assert f"| `{name}` |" in record and f"`{chars}`" in record, name


def test_sabotage_a_family_without_its_symbols_face_is_named(examined):
    from onetrace_console.frame import _FACES
    without_pi = {n: v for n, v in _FACES.items() if not n.endswith("-Pi.woff2")}
    examined(1, "faces with the symbols removed")
    found = coverage_problems(without_pi, console_characters())
    assert found and all("U+2192" in p for p in found), found
