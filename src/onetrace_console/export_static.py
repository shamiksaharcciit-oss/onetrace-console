"""`onetrace-console export-static`: the pages the local console serves for the listed runs, as
static files.

HOW IT RENDERS: AS THE CONSOLE DOES
-----------------------------------
A scratch data folder is made holding only the listed runs: their records, every stored object
(an object no listed run names is never drawn), and the comparisons whose two runs are both
listed. It is rendered by the console's own start-up render (`serve._render_startup_pages`) in
local mode, and each page is filled by the console's own `frame.fill`, exactly as `do_GET` serves
it: no session, so the footer reads "Local mode". The stylesheet is the one `/static/console.css`
serves, the fonts are the shipped files, and each run's `record.tar` is the delivery byte for
byte (`ingest.bundle`). The scratch folder is removed afterwards.

WHAT CHANGES, AND NOTHING ELSE
------------------------------
- **The link rewrite:** every link, source and stylesheet URL written from the site's root
  (`/`, `/executions-all.html`, `/static/console.css`, `/runs/<key>/record.tar`, the fonts in the
  stylesheet) becomes relative to the file that holds it; `/` is the Overview, `home.html`.
- **The banner,** the work order's words, as the first thing in every page's `<main>`.
- **A comparison's explanation panel** is drawn as its place only, as a public console draws it:
  a file can press nothing, so it carries no button and no script, and no explanation.
- **A sealed page is sealed again** after both, so the check it prints for its reader still says
  "matches" on the exported copy. Its fingerprint is therefore not the served page's, and
  `SEALS.txt` relates the two: for each sealed page, one line -- the page,
  the fingerprint the console serves it with, and the exported copy's.

Routes that write, sign in or ingest are left out by construction: only pages, the stylesheet,
the fonts and the records are written, and no served page carries a form. A comparison's
explanation panel is drawn as its place only, with no button and no script (`explain.no_presses`):
a file can press nothing.

THE CHECKS IT RUNS ON ITS OWN OUTPUT
------------------------------------
Before it returns, the export is scanned for project ids (the pattern below) and for requests to
another host. Either found, and the output folder it made is removed and the export refused. The
fence scan takes its terms from a file named on the command line; the real terms never come to
this machine, so here it runs only on a planted test term, in the tests.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
import shutil
import tempfile
from pathlib import Path

#: "every page carries a banner", in its words, verbatim.
BANNER = ("Demo: two runs of a sample pipeline, signed and anchored with test keys. Install "
          "onetrace to record your own.")
#: Drawn with the skin's tokens, so the stylesheet the console serves is not changed for it.
_BANNER_HTML = ('<p data-export="banner" style="margin:0;padding:10px 36px;'
                'background:var(--cc-bg);color:var(--cc-ink);border-bottom:1px solid var(--line);'
                f'font-size:var(--fs-body)">{BANNER}</p>')

#: Four forms of a project id, and the three other forms the
#: project's own ids take. `tests/test_no_internal_ids.py` holds the rendered pages to it too.
INTERNAL_ID = re.compile(
    r"R-20"                 # a decision id
    r"|\b29[a-z]{2}\b"      # a decision's short form
    r"|WO-"                 # a work-order id
    r"|Addendum"
    r"|\bC0\d\d\b"          # a memo number
    r"|Core → Canary"
    r"|Bench Record")

_ROOTED = re.compile(r'\b(href|src)="(/(?!/)[^"]*)"')
_CSS_ROOTED = re.compile(r"url\((/(?!/)[^)]*)\)")
#: The opening of a page's `<main>`: the console's bare, the viewer's with its class and view.
_MAIN = re.compile(r"<main(?:\s[^>]*)?>")
_SLOT = re.compile(r"(<!--fingerprint-->)[0-9a-f]{64}(<!--/fingerprint-->)")
#: `drift`: the drift reports, each copied where every run it covers is listed; `x`, the
#: explanations (`explain.FOLDER`): never copied, and the panel drawn as its place only
#: (`explain.no_presses`).
_STORE_PARTS = {"objects", "runs", "comparisons", "drift", "x", "beside"}
_FINGERPRINT = re.compile(r"<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->")
SEALS = "SEALS.txt"
_SEALS_HEAD = ("# Each sealed page of this export: its path, the fingerprint the console serves it "
               "with, and the fingerprint of this copy -- its links made relative, the demo banner "
               "added, and sealed again, so the check the page prints matches this copy.\n"
               "# page  served  exported\n")


class ExportError(RuntimeError):
    """The export cannot be made as asked. Nothing is left half-written."""


def shown(html: str) -> str:
    """A page as a reader sees it, text and attributes: less `<style>`, `<script>` and comments."""
    html = re.sub(r"<(style|script)\b.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", html, flags=re.S)


def _relative(target: str, holder: str) -> str:
    """`target`, a path from the site's root, as a link from the file `holder`."""
    path = "home.html" if target == "/" else target.lstrip("/")
    return posixpath.relpath(path, posixpath.dirname(holder) or ".")


#: The export's own copy of the verifier's errors page, which an incident page's fix lines link to:
#: the published page is on another host, so the export carries the page the pinned SDK generates.
ERRORS_FILE = "errors.html"


def errors_page() -> bytes:
    """The errors page as the installed onetrace generates it (`onetrace.errors.render_page`, the
    page `python -m onetrace._errors_page` prints), each section under its code's id, its words
    escaped and kept as written."""
    from html import escape

    import onetrace
    from onetrace.errors import render_page
    from onetrace_console.frame import STYLESHEET
    head, *sections = re.split(r"(?m)^## ", render_page())
    parts = [f"<pre>{escape(head.strip())}</pre>"]
    for section in sections:
        code, _, body = section.partition("\n")
        parts.append(f'<section id="{escape(code.strip(), quote=True)}"><h2>{escape(code.strip())}</h2>'
                     f"<pre>{escape(body.strip())}</pre></section>")
    version = escape(getattr(onetrace, "__version__", ""))
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
            f'<title>onetrace errors</title>\n<link rel="stylesheet" href="{STYLESHEET}">\n</head>\n'
            f'<body><main><p class="note">The errors page as onetrace {version} generates it, kept with '
            "this export so its links stay in it.</p>" + "".join(parts) + "</main></body>\n</html>\n"
            ).encode("utf-8")


def _page(served: bytes, rel: str) -> bytes:
    """A served page as exported: links relative, the banner, and sealed again if it was sealed.
    A link to the published errors page goes to the export's own copy of it, at the same section."""
    from onetrace_console.incident_pages import ERRORS_PAGE
    page = served.decode("utf-8")
    page = page.replace(f'href="{ERRORS_PAGE}#', f'href="/{ERRORS_FILE}#')
    page = _ROOTED.sub(lambda m: f'{m.group(1)}="{_relative(m.group(2), rel)}"', page)
    opened = _MAIN.findall(page)
    if len(opened) != 1:
        raise ExportError(f"{rel}: a page must open exactly one <main> to carry the banner")
    page = _MAIN.sub(lambda m: m.group(0) + _BANNER_HTML, page, count=1)
    if _SLOT.search(page):
        from onetrace_console.viewer.fingerprint import seal
        from onetrace_console.viewer.slot import ZEROS
        page = seal(_SLOT.sub(lambda m: m.group(1) + ZEROS + m.group(2), page))
    return page.encode("utf-8")


def _scratch(source: Path, keys: list[str], into: Path):
    """A data folder holding only the listed runs, and the comparisons between them."""
    from onetrace_console.store import Store
    store_dir = source / "store"
    if not store_dir.is_dir():
        raise ExportError(f"no store at {store_dir}")
    other = sorted(p.name for p in store_dir.iterdir() if p.name not in _STORE_PARTS)
    if other:
        raise ExportError(f"the store holds what this export does not know how to filter: {other}")
    source_store = Store(store_dir)
    for key in keys:
        if source_store.get_run(key) is None:
            raise ExportError(f"no stored run {key}")
    shutil.copytree(store_dir / "objects", into / "store" / "objects")
    (into / "store" / "runs").mkdir(parents=True)
    for key in keys:
        shutil.copy2(store_dir / "runs" / f"{key}.json", into / "store" / "runs" / f"{key}.json")
        #: What was kept beside a listed run (`beside`): its objects are in `objects/` already.
        kept = store_dir / "beside" / f"{key}.json"
        if kept.is_file():
            (into / "store" / "beside").mkdir(exist_ok=True)
            shutil.copy2(kept, into / "store" / "beside" / kept.name)
    listed = set(keys)
    for comparison in source_store.comparisons():
        if comparison.run_a in listed and comparison.run_b in listed:
            target = into / "store" / "comparisons"
            target.mkdir(exist_ok=True)
            shutil.copy2(store_dir / "comparisons" / f"{comparison.key}.json",
                         target / f"{comparison.key}.json")
    #: The drift reports this console holds over listed runs only: a page reads the report this
    #: console made, rather than one the export would make again.
    for p in sorted((store_dir / "drift").glob("*.json")) if (store_dir / "drift").is_dir() else ():
        record = source_store.get_drift(p.stem)
        if record is not None and set(record.get("runs") or ()) <= listed and record.get("runs"):
            target = into / "store" / "drift"
            target.mkdir(exist_ok=True)
            shutil.copy2(p, target / p.name)
    return Store(into / "store")


def export(source: Path, keys: list[str], out: Path) -> dict[str, str]:
    """Export the listed runs' pages from the console data folder `source` into the new folder
    `out`. Returns {path in `out`: sha256} for every file written."""
    from onetrace_console.config import Config
    from onetrace_console.frame import STYLESHEET, fill, stylesheet
    from onetrace_console.ingest import bundle
    from onetrace_console.serve import (PAGES_DIRNAME, STATIC_FILES, _local_config,
                                        _render_startup_pages)
    source, out = Path(source), Path(out)
    if not keys:
        raise ExportError("no runs named")
    for key in keys:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ExportError(f"not a run key: {key!r}")
    if len(set(keys)) != len(keys):
        raise ExportError("a run is named twice")
    if out.exists():
        raise ExportError(f"{out} already exists; the export writes only into a new folder")
    work = Path(tempfile.mkdtemp(prefix="export-static-"))
    made = False
    try:
        store = _scratch(source, keys, work)
        from onetrace_console.explain import no_presses
        with no_presses():
            _render_startup_pages(store, work, _local_config(Config()))
        files: dict[str, bytes] = {}
        seals: list[str] = []
        pages = work / PAGES_DIRNAME
        for path in sorted(pages.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(pages).as_posix()
            #: Local mode serves every rendered page (`do_GET`, with no role enforced), so each
            #: is exported as served.
            served = fill(path.read_bytes(), rel, onedoor=False, user=None)
            files[rel] = _page(served, rel)
            was = _FINGERPRINT.search(served.decode("utf-8"))
            if was:
                now = _FINGERPRINT.search(files[rel].decode("utf-8")).group(1)
                seals.append(f"{rel}  {was.group(1)}  {now}\n")
        if any(f'{ERRORS_FILE}#'.encode() in data for data in files.values()):
            files[ERRORS_FILE] = _page(errors_page(), ERRORS_FILE)
        css = STYLESHEET.lstrip("/")
        files[css] = _CSS_ROOTED.sub(lambda m: f"url({_relative(m.group(1), css)})",
                                     stylesheet().decode("utf-8")).encode("utf-8")
        for path, shipped in STATIC_FILES.items():
            files[path.lstrip("/")] = shipped.read_bytes()
        for key in keys:
            files[f"runs/{key}/record.tar"] = bundle(store.get_run(key), store)
        files[SEALS] = (_SEALS_HEAD + "".join(seals)).encode("utf-8")
        out.mkdir(parents=True)
        made = True
        for rel, data in files.items():
            (out / rel).parent.mkdir(parents=True, exist_ok=True)
            (out / rel).write_bytes(data)
        found = internal_ids(out) + external_requests(out)
        if found:
            raise ExportError(f"{len(found)} findings in the export:\n" + "\n".join(found[:20]))
        return {rel: hashlib.sha256(data).hexdigest() for rel, data in sorted(files.items())}
    except BaseException:
        if made:
            shutil.rmtree(out)
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _texts(folder: Path, suffixes: tuple[str, ...]):
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file() and path.suffix in suffixes:
            yield path.relative_to(folder).as_posix(), path.read_text(encoding="utf-8")


def internal_ids(folder: Path) -> list[str]:
    """The project-id scan over every exported page and stylesheet, as a reader sees them."""
    return [f"{rel}: …{shown(text)[max(0, m.start() - 50):m.end() + 30]}…"
            for rel, text in _texts(folder, (".html", ".css"))
            for m in INTERNAL_ID.finditer(shown(text))]


_REQUEST = re.compile(r'\b(?:href|src|action|poster|data)\s*=\s*"([^"]*)"'
                      r"|\bsrcset\s*=\s*\"([^\"]*)\""
                      r"|url\(\s*['\"]?([^)'\"]*)"
                      r"|@import\s+['\"]([^'\"]*)")
#: A URL that names a host or a scheme: a request away from the exported folder.
_AWAY = re.compile(r"^\s*(?://|[a-zA-Z][a-zA-Z0-9+.-]*:)")


def external_requests(folder: Path) -> list[str]:
    """Every link, source, stylesheet URL or import in an exported page or stylesheet that names
    another host or a scheme -- none may (item 10: no fonts or scripts from other hosts)."""
    hits = []
    for rel, text in _texts(folder, (".html", ".css")):
        for m in _REQUEST.finditer(text):
            values = ([u.strip().split(" ")[0] for u in m.group(2).split(",")] if m.group(2)
                      else [m.group(1) or m.group(3) or m.group(4) or ""])
            hits += [f"{rel}: {v}" for v in values if _AWAY.match(v)]
    return hits


def fence_hits(folder: Path, terms_file: Path) -> list[str]:
    """The fence scan's mechanism: each term in `terms_file` (one a line; `#` lines and blank lines
    are not terms), case-insensitive, in every exported file's bytes -- a record's tar included.
    Returns `<file>: term <n>`, never the term itself, so a report can carry the count."""
    terms = [t.strip().lower() for t in Path(terms_file).read_text(encoding="utf-8").splitlines()
             if t.strip() and not t.lstrip().startswith("#")]
    if not terms:
        raise ExportError(f"{terms_file} holds no terms")
    hits = []
    for path in sorted(Path(folder).rglob("*")):
        if path.is_file():
            text = path.read_bytes().decode("utf-8", errors="replace").lower()
            rel = path.relative_to(folder).as_posix()
            hits += [f"{rel}: term {n}" for n, term in enumerate(terms, 1) if term in text]
    return hits
