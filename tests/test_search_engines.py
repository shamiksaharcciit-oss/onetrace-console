"""What a public console tells search engines.

A public console's run pages are addressed by their runs' content, so each new build of the hosted demo gives them new
addresses and the old ones answer 404. Search engines are told to index the Overview only:

- every page a public console serves carries `<meta name="robots" content="noindex">`, but the Overview at `/`;
- the Overview, at `/` and at `/home.html` (the same page), carries `<link rel="canonical">` to the console's own
  public address, the deploy's setting `ONETRACE_CONSOLE_PUBLIC_URL`; unset, no canonical is drawn;
- `/robots.txt` allows crawling, so each page's `noindex` can be read;
- a sealed page carries its `noindex` from when it was drawn, so its printed check still matches as served;
- a console on this machine is unchanged, and a static export's pages carry `noindex` too.
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request

from tests.http_limits import limit
from tests.test_export_static import exported, source  # noqa: F401 - fixtures, requested by name
from tests.test_public_mode import _pages, built, served  # noqa: F401 - fixtures, requested by name

NOINDEX = '<meta name="robots" content="noindex">'
CANONICAL = re.compile(r'<link rel="canonical" href="([^"]*)">')


def _get(base: str, path: str) -> tuple[int, str, str]:
    try:
        with urllib.request.urlopen(base + path, timeout=limit(30)) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read().decode("utf-8", "replace")


def test_every_page_a_public_console_serves_carries_noindex_but_the_overview(served, examined):  # noqa: F811
    base, folder, _c = served
    pages = _pages(folder)
    assert len(pages) >= 50, pages
    for rel in pages:
        status, kind, body = _get(base, "/" + rel)
        assert status == 200 and kind.startswith("text/html"), rel
        assert body.count(NOINDEX) == 1, rel
        assert body.index(NOINDEX) < body.index("</head>"), rel
    status, _kind, overview = _get(base, "/")
    assert status == 200 and NOINDEX not in overview, "the Overview is the one page to index"
    #: A page that is not found says so in HTML where it is HTML, and is not to be indexed either.
    examined(len(pages) + 1, "pages served")


def test_with_no_public_address_set_no_canonical_is_drawn(served, examined):  # noqa: F811
    base, _folder, _c = served
    for path in ("/", "/home.html"):
        assert not CANONICAL.search(_get(base, path)[2]), path
    examined(2, "Overview addresses")


def test_robots_txt_allows_crawling_so_noindex_can_be_read(served, examined):  # noqa: F811
    base, _folder, _c = served
    status, kind, body = _get(base, "/robots.txt")
    assert status == 200 and kind.startswith("text/plain")
    assert body == "User-agent: *\nAllow: /\n"
    assert "Disallow" not in body and "Sitemap" not in body
    examined(1, "robots.txt")


def test_a_sealed_page_served_with_noindex_still_matches_its_seal(served, examined):  # noqa: F811
    from onetrace_console.viewer.fingerprint import check

    base, folder, _c = served
    cases = [rel for rel in _pages(folder) if rel.endswith("/case.html")]
    assert cases
    for rel in cases[:5]:
        body = _get(base, "/" + rel)[2]
        assert NOINDEX in body
        assert check(body.encode("utf-8"))[0], rel
    examined(min(len(cases), 5), "sealed pages checked as served")


def test_the_canonical_follows_the_setting(examined):
    from onetrace_console.search_engines import PUBLIC_URL_VAR, for_search

    page = b'<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n<title>Overview</title>\n</head>'
    at = {PUBLIC_URL_VAR: "https://demo.example.org"}
    root = for_search(page, "/", environ=at).decode("utf-8")
    assert CANONICAL.findall(root) == ["https://demo.example.org/"] and NOINDEX not in root
    home = for_search(page, "/home.html", environ=at).decode("utf-8")
    assert CANONICAL.findall(home) == ["https://demo.example.org/"] and NOINDEX in home
    #: With a path, the Overview is its root.
    deeper = for_search(page, "/", environ={PUBLIC_URL_VAR: "https://example.org/demo/"}).decode("utf-8")
    assert CANONICAL.findall(deeper) == ["https://example.org/demo/"]
    #: Unset, empty, or not an http(s) address: no canonical.
    for environ in ({}, {PUBLIC_URL_VAR: ""}, {PUBLIC_URL_VAR: "javascript:alert(1)"}, {PUBLIC_URL_VAR: "demo"}):
        assert not CANONICAL.search(for_search(page, "/", environ=environ).decode("utf-8")), environ
    #: Any other page: `noindex`, and no canonical.
    other = for_search(page, "/runs/" + "0" * 64 + "/case.html", environ=at).decode("utf-8")
    assert NOINDEX in other and not CANONICAL.search(other)
    #: Twice is once.
    assert for_search(for_search(page, "/x.html"), "/x.html") == for_search(page, "/x.html")
    examined(9, "pages marked")


def test_a_console_on_this_machine_is_unchanged(server, monkeypatch, examined):
    from onetrace_console.search_engines import PUBLIC_URL_VAR

    monkeypatch.setenv(PUBLIC_URL_VAR, "https://demo.example.org")
    base, _root = server
    assert _get(base, "/robots.txt")[0] == 404
    home = _get(base, "/")[2]
    assert NOINDEX not in home and not CANONICAL.search(home)
    examined(2, "a local console's answers")


def test_a_static_export_s_pages_carry_noindex(exported, examined):  # noqa: F811
    out, _files, _source = exported
    pages = sorted(out.rglob("*.html"))
    assert pages
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert text.count(NOINDEX) == 1, page
    examined(len(pages), "exported pages")
