"""Nothing is lost when Runs moves to `/runs`: every address the console served before keeps its answer, and each is
listed here with that answer, served by a public console over the demo as the image builds it.

- Every kind of page drawn ahead, every page drawn as asked with its query parameters, the run's record, the
  stylesheet and the health check: unchanged, as each answered before.
- The list of every run stored (`executions-all.html`): unchanged, with one line linking the Runs page.
- Every page's sidebar names Runs at `/runs`, which answers with the Runs page.
- Each comparison's new Authorization tab, `/diff/<key>-authorization.html`, answers, titled with its pair.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.test_public_mode import built, served  # noqa: F401 - the module's fixtures
from tools import container_check

#: Each address a console served before, as a pattern over the built pages, with the answer it keeps.
UNCHANGED = "unchanged, as before"
ROUTES: tuple[tuple[str, int, str], ...] = (
    ("/", 200, UNCHANGED),
    ("/home.html", 200, UNCHANGED),
    ("/counts.html", 200, UNCHANGED),
    ("/executions-all.html", 200, "unchanged, with one line linking /runs"),
    ("/executions-<tally>.html", 200, UNCHANGED),
    ("/comparisons.html", 200, UNCHANGED),
    ("/incidents.html", 200, UNCHANGED),
    ("/incidents-<rule>.html", 200, UNCHANGED),
    ("/incidents/<id>.html", 200, UNCHANGED),
    ("/pipeline-p<N>.html", 200, UNCHANGED),
    ("/pipeline-p<N>-agree.html", 200, UNCHANGED),
    ("/pipeline-p<N>-attention.html", 200, UNCHANGED),
    ("/choose-p<N>.html", 200, UNCHANGED),
    ("/choose-p<N>-<key>.html", 200, UNCHANGED),
    ("/drift-p<N>.html", 200, UNCHANGED),
    ("/drift-p<N>-previous.html", 200, UNCHANGED),
    ("/bisect-p<N>.html", 200, UNCHANGED),
    ("/bisect?p=P1&after=", 200, UNCHANGED),
    ("/search?q=verdict%3AFAIL", 200, UNCHANGED),
    ("/search?q=benchmark%3Ayes&run=<key>", 200, UNCHANGED),
    ("/runs/<key>/case.html", 200, UNCHANGED),
    ("/runs/<key>/answer.html", 200, UNCHANGED),
    ("/runs/<key>/proof.html", 200, UNCHANGED),
    ("/runs/<key>/authorization.html", 200, UNCHANGED),
    ("/runs/<key>/stage-1.html", 200, UNCHANGED),
    ("/runs/<key>/receipt.html", 200, UNCHANGED),
    ("/runs/<key>/record.tar", 200, UNCHANGED),
    ("/diff/<key>.html", 200, UNCHANGED),
    ("/diff/<key>-proof.html", 200, UNCHANGED),
    ("/diff/<key>-text.html", 200, UNCHANGED),
    ("/health", 200, UNCHANGED),
    ("/static/console.css", 200, UNCHANGED),
    ("/static/favicon.svg", 200, UNCHANGED),
)
#: The address this release adds.
NEW = (("/runs", 200, "the Runs page"), ("/runs?pipeline=P1&page=1", 200, "the Runs page, one pipeline"))


def _instance(pattern: str, pages: Path) -> str:
    """A real address of the pattern's kind, from the pages the build drew."""
    if "<" not in pattern:
        return pattern
    if "?" in pattern:
        key = sorted(p.name for p in (pages / "runs").iterdir() if p.is_dir())[0]  # any run serves: the first by name
        return pattern.replace("<key>", key)
    shape = re.escape(pattern.lstrip("/"))
    for part, rx in (
        (r"<tally>", r"[a-z0-9-]+"),
        (r"<rule>", r"[a-z0-9.-]+"),
        (r"<id>", r"[^/]+"),
        (r"<N>", r"[0-9]+"),
        (r"<key>", r"[0-9a-f]{64}"),
    ):
        shape = shape.replace(re.escape(part), rx)
    found = sorted(
        p.relative_to(pages).as_posix()
        for p in pages.rglob("*")
        if re.fullmatch(shape, p.relative_to(pages).as_posix())
    )
    if not found and pattern.endswith("/record.tar"):
        key = sorted(p.name for p in (pages / "runs").iterdir() if p.is_dir())[0]  # any run serves: the first by name
        return f"/runs/{key}/record.tar"
    assert found, f"the build drew no page of the kind {pattern}"
    return "/" + found[0]


def test_every_address_served_before_keeps_its_answer(served, examined):  # noqa: F811 - the fixture
    base, folder, _c = served
    pages = folder / "store" / "pages"
    examined(len(ROUTES), "kinds of address served before")
    for pattern, status, answer in ROUTES:
        path = _instance(pattern, pages)
        got, _headers, body = container_check.fetch(base, path)
        assert got == status, (pattern, path, got, answer)
        if path.endswith(".html") or path == "/":
            text = body.decode("utf-8")
            assert 'href="/runs"' in text, (pattern, "the sidebar's Runs")
            if answer != UNCHANGED:
                assert 'data-section="runs-page-link"' in text and 'href="/runs">Runs</a>' in text, pattern


def test_the_new_address_answers_with_the_runs_page(served, examined):  # noqa: F811 - the fixture
    base, _folder, _c = served
    examined(len(NEW), "new addresses")
    for path, status, _answer in NEW:
        got, _headers, body = container_check.fetch(base, path)
        assert got == status and b"<h1>Runs</h1>" in body, (path, got)
        assert b'aria-current="page">Runs</a>' in body, "the sidebar marks Runs as the page shown"


def test_each_comparison_s_authorization_tab_answers_titled_with_its_pair(served, examined):  # noqa: F811 - the fixture
    base, folder, _c = served
    keys = sorted(p.name[: -len(".html")] for p in (folder / "store" / "pages" / "diff").glob("*-proof.html"))
    keys = [k[: -len("-proof")] for k in keys]
    examined(len(keys), "comparisons' Authorization tabs")
    assert keys
    for key in keys:
        got, _headers, body = container_check.fetch(base, f"/diff/{key}-authorization.html")
        assert got == 200 and b"<title>Investigate \xc2\xb7 " in body, (key, got)
        assert b'aria-current="page">Authorization</a>' in body, key
