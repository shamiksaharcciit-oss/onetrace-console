"""The public site's links into the hosted demo (`deploy/fly/site_links.txt`), and a redirect at each
comparison page name the site holds that the build no longer has.

A comparison's page is named by its key, which takes in the SDK build that compared the two runs
(`compare.comparison_key`): a console that pins a new SDK names every comparison anew. For each
listed comparison path the build does not hold, the build looks among its comparisons for the one whose
two runs, compared by an SDK build an earlier console release pinned (`EARLIER_SDKS`), give that
name, and writes a small page at the old name that sends a reader to this build's page between the
same two runs. Only listed paths get one; there is no general table of old names.
"""
from __future__ import annotations

import re
from pathlib import Path

from onetrace_console.words import escape

#: The SDK builds earlier console releases compared with, whose comparison names the site can hold:
#: onetrace 0.5.0's wheel, as console 0.4.0 pinned it (its requirements.lock).
EARLIER_SDKS = (("0.5.0", "wheel:02ac0ce2a6b1581571623535c6219b3fec292c97a31fddd62f9dcc71453f0cc6"),)
MOVED = "This comparison has moved"
_DIFF = re.compile(r"diff/([0-9a-f]{64})\.html")


def read(path: Path) -> list[str]:
    """Each listed link's path on the demo, in the file's order: `/`, `/pipeline-p1.html`, ... The file
    holds paths, not addresses: nothing under deploy/fly names a domain."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if not line.startswith("/"):
                raise ValueError(f"{path}: {line!r} is not a path on the demo")
            out.append(line)
    return out


def page_of(path: str) -> str:
    """The page a path opens, as a console serves it: `/` is `home.html`."""
    return "home.html" if path in ("/", "") else path.lstrip("/")


def page(target: str) -> str:
    """The page at an old comparison name: a page of the console's like every other (its head, and the
    frame a console fills with its navigation and, on a public console, the banner), not indexed, sent
    on to `target`, with a line and its link."""
    from onetrace_console.render import _document
    t = escape(target)
    doc = _document(MOVED, f'<div class="cp"><h1>{escape(MOVED)}</h1>'
                           f'<p data-moved>{escape(MOVED)}: <a href="{t}"><code>{t}</code></a></p></div>')
    head_end = doc.index("</head>")
    return (doc[:head_end] + f'<meta name="robots" content="noindex"><meta http-equiv="refresh" content="0; url={t}">'
            + doc[head_end:])


def earlier_names(store) -> dict[str, str]:
    """{a comparison name an earlier SDK build gave: this build's comparison key between the same runs}."""
    from onetrace_console.compare import comparison_key
    from onetrace_console.ingest import bundle
    from onetrace_console.store import digest
    out = {}
    for c in store.comparisons():
        a, b = digest(bundle(store.get_run(c.run_a), store)), digest(bundle(store.get_run(c.run_b), store))
        for version, build in EARLIER_SDKS:
            out[comparison_key(a, b, version, build)] = c.key
    return out


class Unplaced(ValueError):
    """A listed link this build can open no page at: the build stops, naming it and why."""


def write_redirects(store, pages: Path, links: list[str]) -> dict[str, str]:
    """For each listed comparison path the build's pages do not hold, a page at it sending a reader to
    this build's page between the same two runs: {old page: new page}. A listed path that opens no page
    and that no earlier SDK build's name of a held comparison gives is `Unplaced`: the build stops."""
    names = None
    made = {}
    for path in links:
        rel = page_of(path)
        if (pages / rel).is_file():
            continue
        m = _DIFF.fullmatch(rel)
        if m is None:
            raise Unplaced(f"the public site links to {path}, and this build draws no page there")
        names = earlier_names(store) if names is None else names
        new = names.get(m.group(1))
        if new is None:
            raise Unplaced(f"the public site links to {path}, a comparison page this build does not hold, "
                           f"and no comparison it holds was named so by an earlier onetrace "
                           f"({', '.join(v for v, _ in EARLIER_SDKS)})")
        if not (pages / f"diff/{new}.html").is_file():
            raise Unplaced(f"the public site links to {path}, whose comparison is diff/{new}.html here, "
                           f"and this build draws no page there")
        (pages / rel).write_text(page(f"{new}.html"), encoding="utf-8", newline="\n")
        made[rel] = f"diff/{new}.html"
    return made
