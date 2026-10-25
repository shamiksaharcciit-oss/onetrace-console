"""The content policy every page is served with, and the hosts a page may load from.

1. Both modes' policies: a script runs only by its exact sha256 hash -- exactly the hashes of the
   scripts the console ships, never `'unsafe-inline'`, `'unsafe-eval'`, `'strict-dynamic'` or a
   wildcard. No directive names another host or scheme (`data:` for images only). `style-src`
   stays `'self' 'unsafe-inline'`, as it was before this test: pinned here so it cannot spread.
   Only the local console has `connect-src 'self'`, for the watched folder's notice.
2. Each script a page carries is one of those, by its hash.
3. The served headers: a local console sends the local policy, a public one the public policy.
4. No page and no stylesheet loads anything from another host: every `src`, every `<link href>`
   and every `url(...)` names this console's own path.

Each check has its sabotage.
"""
from __future__ import annotations

import hashlib
import base64
import http.client
import re
from urllib.parse import urlparse

import pytest

from tests.test_public_mode import _pages, built, served  # noqa: F401

#: Every source a directive may name, by directive; anything else is a problem.
ALLOWED = {
    "default-src": {"'none'"}, "style-src": {"'self'", "'unsafe-inline'"}, "font-src": {"'self'"},
    "img-src": {"'self'", "data:"}, "connect-src": {"'self'"}, "base-uri": {"'none'"},
    "form-action": {"'none'"}, "frame-ancestors": {"'none'"},
}


def _hash(script: str) -> str:
    body = script.removeprefix("<script>").removesuffix("</script>")
    return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'"


def policy_problems(policy: str, *, local: bool) -> list[str]:
    from onetrace_console.public import inline_scripts
    directives = {}
    for part in filter(None, (p.strip() for p in policy.split(";"))):
        name, *sources = part.split()
        directives[name] = sources
    out = []
    from onetrace_console.compare_script import COMPARE_SCRIPT
    from onetrace_console.explain_script import EXPLAIN_SCRIPT
    #: The explanation panel's and the Compare buttons are the local console's only.
    shipped = {_hash(s) for s in inline_scripts() + ((EXPLAIN_SCRIPT, COMPARE_SCRIPT) if local else ())}
    if set(directives.get("script-src", [])) != shipped:
        out.append(f"script-src is not exactly the shipped scripts' hashes: {directives.get('script-src')}")
    for name, sources in directives.items():
        if name == "script-src":
            continue
        bad = [s for s in sources if s not in ALLOWED.get(name, set())]
        if bad:
            out.append(f"{name} names {bad}")
    if directives.get("style-src") != ["'self'", "'unsafe-inline'"]:
        out.append(f"style-src moved: {directives.get('style-src')}")
    if ("connect-src" in directives) != local:
        out.append(f"connect-src {'missing from' if local else 'in'} the {'local' if local else 'public'} policy")
    return out


@pytest.mark.parametrize("local", [False, True])
def test_each_mode_s_policy_runs_only_the_shipped_scripts_by_hash(local, examined):
    from onetrace_console.public import content_security_policy, inline_scripts
    examined(len(inline_scripts()), "shipped scripts")
    assert policy_problems(content_security_policy(local=local), local=local) == []


#: Each way a policy could widen, as an edit to the public policy, and the problem it must raise.
WIDENED = {
    "script-src gains 'unsafe-inline'": (("script-src ", "script-src 'unsafe-inline' "), "script-src is not exactly"),
    "script-src gains an unknown hash": (("script-src ", "script-src 'sha256-AAAA' "), "script-src is not exactly"),
    "fonts from another host": (("font-src 'self'", "font-src 'self' https://fonts.example.org"), "font-src names"),
    "styles from another host": (("style-src 'self' 'unsafe-inline'",
                                  "style-src 'self' 'unsafe-inline' https://cdn.example.org"), "style-src names"),
    "images from blob:": (("img-src 'self' data:", "img-src 'self' data: blob:"), "img-src names"),
}


@pytest.mark.parametrize("what", sorted(WIDENED))
def test_sabotage_a_policy_that_widens_is_named(what, examined):
    from onetrace_console.public import content_security_policy
    (old, new), said = WIDENED[what]
    policy = content_security_policy()
    assert policy.count(old) == 1, old
    widened = policy.replace(old, new)
    examined(1, "planted policy")
    assert any(said in p for p in policy_problems(widened, local=False)), widened


def _get(base: str, path: str) -> tuple[int, dict, bytes]:
    u = urlparse(base)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=20)
    conn.request("GET", path)
    r = conn.getresponse()
    return r.status, dict(r.getheaders()), r.read()


def test_a_local_console_sends_the_local_policy(server, examined):
    from onetrace_console.public import content_security_policy
    base, _ = server
    examined(2, "responses")
    for path in ("/", "/static/console.css"):
        _status, headers, _ = _get(base, path)
        assert headers.get("Content-Security-Policy") == content_security_policy(local=True), path


def test_a_public_console_sends_the_public_policy_and_each_page_s_scripts_are_in_it(served, examined):  # noqa: F811
    from onetrace_console.public import content_security_policy
    base, folder, _c = served
    pages = _pages(folder)
    examined(len(pages), "public pages served")
    policy = content_security_policy()
    for rel in pages:
        _status, headers, body = _get(base, "/" + rel)
        assert headers.get("Content-Security-Policy") == policy, rel
        for script in re.findall(r"<script>.*?</script>", body.decode("utf-8"), re.S):
            assert _hash(script) in policy, (rel, script[:80])


#: A resource a page or the stylesheet loads, as the browser reads it.
_LOADS = (re.compile(r'<(?:script|img|iframe|source|audio|video|embed)\b[^>]*\bsrc="([^"]*)"', re.I),
          re.compile(r'<link\b[^>]*\bhref="([^"]*)"', re.I),
          re.compile(r"url\(\s*['\"]?([^'\")]+)"),
          re.compile(r"@import\s+['\"]([^'\"]+)"))


def external_loads(text: str) -> list[str]:
    """Every resource `text` loads from anywhere but this console: a scheme, or `//`."""
    found = [m for rx in _LOADS for m in rx.findall(text)]
    return [u for u in found if re.match(r"(?:[a-z][a-z0-9+.-]*:|//)", u, re.I) and not u.startswith("data:")]


def test_no_page_and_no_stylesheet_loads_from_another_host(built, examined):  # noqa: F811
    from onetrace_console.frame import stylesheet
    root = built / "store" / "pages"
    pages = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}
    pages["static/console.css"] = stylesheet().decode("utf-8")
    examined(len(pages), "pages and the stylesheet")
    assert {n: external_loads(t) for n, t in pages.items() if external_loads(t)} == {}
    assert "url(/static/fonts/" in pages["static/console.css"], "the fonts are not the console's own"


@pytest.mark.parametrize("planted", [
    '<link rel="stylesheet" href="https://fonts.example.org/plex.css">',
    "@font-face{src:url(https://fonts.example.org/plex.woff2)}",
    '<script src="//cdn.example.org/x.js"></script>',
    '<img src="http://example.org/logo.png">',
])
def test_sabotage_an_external_load_is_named(planted, examined):
    examined(1, "planted load")
    assert external_loads("<p>a page</p>" + planted), planted
