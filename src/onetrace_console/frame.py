"""The console's frame: its navigation, its footer and its one stylesheet.

A console page is written to `pages/` with an empty frame -- `<nav class="frame" data-frame>`
holding only the viewer's marker, `viewer.page.FRAME_NAV` -- and the server fills it as it serves
the page, because only the server knows the session the footer states and whether the onedoor
extension is on. The navigation lists pages that exist and nothing else: Overview, Runs,
Incidents, and Policy when onedoor is on. The footer states facts only: the mode and the
console's version.

The pages the viewer seals -- each run's answer and case, every runs list -- are framed when they
are rendered, not when they are served: the frame is filled before
the seal, so the served bytes are the bytes on disk and the printed fingerprint checks on every
copy. Their footer states the configuration they were rendered under -- "Local mode" or
"Sign-in required" -- and the version, and never a user: a run page is a document
people save and pass on, and a forwarded page does not say who forwarded it.
"""
from __future__ import annotations

import contextlib
import contextvars
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from onetrace_console import __version__
from onetrace_console.words import escape

#: Where the console's one stylesheet is served, to anyone: the sign-in page links it too.
STYLESHEET = "/static/console.css"

_FONTS = Path(__file__).parent / "static" / "fonts"
#: Each bundled face: (family, weight, style) -- read from the files shipped, never a download.
_FACES = {
    "IBMPlexSans-Regular.woff2": ("IBM Plex Sans", 400),
    "IBMPlexSans-Medium.woff2": ("IBM Plex Sans", 500),
    "IBMPlexSans-SemiBold.woff2": ("IBM Plex Sans", 600),
    "IBMPlexMono-Regular.woff2": ("IBM Plex Mono", 400),
    "IBMPlexMono-Medium.woff2": ("IBM Plex Mono", 500),
}

#: The navigation, in order: (label, href, the page it opens under `pages/`).
ITEMS = (("Overview", "/", "home.html"),
         ("Runs", "/executions-all.html", "executions-all.html"),
         #: After Runs, named for what it lists, not the boards' "Diff & compare".
         ("Comparisons", "/comparisons.html", "comparisons.html"),
         ("Incidents", "/incidents.html", "incidents.html"))
POLICY = ("Policy", "/policy.html", "policy.html")


#: The pages the console draws itself, in v6 board 1's look (its source HTML is
#: the authority: sizes, spacing and weights as drawn there) -- the Overview and All counts,
#: Incidents and each rule's list, and Comparisons. Scoped to `.cp`, the wrapper those pages
#: alone carry, so the pages the viewer draws do not move with it. Every colour is a skin token; the two
#: colours board 1 draws that the skin has no token for are mapped, and the item 12 report lists
#: them: the banner's border #ecd9a8 to --line, and its text #5c3d00 to --cc-ink.
#: The elements keep the tags and attributes the tests read; the look comes from selectors.
#: Board 7 on the Diff page -- its first difference outlined in the amber of a
#: change, and its wide tables scrolling inside their panel with the scrollbar drawn, as the graph's is
#: Nothing past the edge unseen.
PAGE_CSS = """
.cp{padding:26px 36px;display:flex;flex-direction:column;gap:16px}
.cp>*,.cp section{margin:0}
.cp a{color:var(--accent)}
.shell>main:has(>.cp)>[data-preview]{margin:0;padding:14px 36px 0}
.cp h1{margin:0;font-size:var(--fs-h1);font-weight:600}
.cp h2{margin:0;font-size:15px;font-weight:600;color:var(--ink);text-transform:none;
  letter-spacing:0}
.cp>[data-section=what]{font-size:var(--fs-nav);color:var(--ink-muted);margin-top:-12px}
.cp>[data-section=banner]{background:var(--cc-bg);border:1px solid var(--line);
  border-radius:var(--r-card);padding:10px 14px;font-size:var(--fs-body);color:var(--cc-ink)}
.cp [data-section=cards]{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.cp [data-card]{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:16px}
.cp [data-card] h3{margin:0;font-size:var(--fs-body);font-weight:400;color:var(--ink-muted)}
.cp [data-card] p{margin:4px 0 0;font-size:var(--fs-small);color:var(--ink-muted)}
.cp [data-card] p.lead{margin-top:6px;line-height:1.3}
.cp [data-card] p.lead a{color:var(--ink);text-decoration:none}
.cp .kpi{font-size:var(--fs-kpi);font-weight:600}
.cp .of{font-size:15px;color:var(--ink-muted)}
.cp .panels{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.cp :where(section[data-section]:not([data-section=cards])){background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-card);padding:14px 18px}
.cp section>p{margin:4px 0 6px;font-size:var(--fs-small);color:var(--ink-muted)}
.cp .head{display:flex;align-items:center;gap:12px}
.cp .head h2{flex-grow:1}
.cp .head p{margin:0;font-size:var(--fs-body)}
.cp table.rungs{width:100%;border-collapse:collapse;margin-top:8px}
.cp table.rungs td{font-size:var(--fs-body);padding:6px 0;border-bottom:1px solid var(--line-soft)}
.cp table.rungs td+td{text-align:right;padding-left:12px}
.cp table.rungs tr:last-child td{border-bottom:none}
.cp [data-attention]{display:flex;justify-content:space-between;gap:12px;
  font-size:var(--fs-body);padding:6px 0;border-bottom:1px solid var(--line-soft)}
.cp [data-attention]:last-child{border-bottom:none}
.cp .pill{display:inline-block;font-size:var(--fs-small);font-weight:500;padding:3px 8px;
  border-radius:var(--r-pill);margin-right:4px}
.cp .ok{background:var(--ok-bg);color:var(--ok-ink)}
.cp .cc{background:var(--cc-bg);color:var(--cc-ink)}
.cp .cco{background:var(--neu-bg);color:var(--cc-ink);box-shadow:inset 0 0 0 1px var(--cc-ink)}
.cp .bad{background:var(--bad-bg);color:var(--bad-ink)}
.cp .neu{background:var(--neu-bg);color:var(--neu-ink)}
.cp :is([data-section=recent-runs],[data-section=pipelines],[data-section=by-day]){padding:6px 0 0}
.cp :is([data-section=recent-runs],[data-section=pipelines],[data-section=by-day])>.head{padding:8px 18px}
.cp :is([data-section=recent-runs],[data-section=pipelines],[data-section=by-day])>p{padding:0 18px}
.cp table.board{width:100%;border-collapse:collapse}
.cp table.board th{font-size:var(--fs-small);color:var(--ink-muted);font-weight:500;
  padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;text-transform:none;
  letter-spacing:0}
.cp table.board td{font-size:var(--fs-body);padding:11px 12px;border-bottom:1px solid var(--line-soft)}
.cp table.board th:first-child,.cp table.board td:first-child{padding-left:18px}
.cp table.board tr:last-child td{border-bottom:none}
.cp table.board td.value,.cp [data-attention]>.value{white-space:nowrap}
.cp ul[data-section=counts]>li{padding:6px 0;border-bottom:1px solid var(--line-soft)}
.cp>footer{margin-top:12px}
.cp :where(section[data-group]){background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:14px 18px}
.cp [data-group]>p{margin:4px 0 6px;font-size:var(--fs-small);color:var(--ink-muted)}
.cp ul[data-group]{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:4px 18px}
.cp [data-incident]{font-size:var(--fs-body);padding:10px 0;border-bottom:1px solid var(--line-soft)}
.cp [data-incident]:last-child{border-bottom:none}
.cp [data-incident] pre{margin:6px 0;font-size:var(--fs-small);white-space:pre-wrap}
.cp table[data-section=comparisons]{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);border-collapse:separate;border-spacing:0;width:100%}
.cp table[data-section=comparisons] th{font-size:var(--fs-small);color:var(--ink-muted);
  font-weight:500;padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;
  text-transform:none;letter-spacing:0}
.cp table[data-section=comparisons] td{font-size:var(--fs-body);padding:11px 12px;
  border-bottom:1px solid var(--line-soft)}
.cp table[data-section=comparisons] tr:last-child td{border-bottom:none}
.cp table[data-section=comparisons] :is(th,td):first-child{padding-left:18px}
.cp>[data-section=rule-table],.cp>[data-section=not-built]{font-size:var(--fs-small);
  color:var(--ink-muted)}
.cp [data-section=first-difference]{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:16px 20px}
.cp [data-section=first-difference] p{margin:2px 0;font-size:var(--fs-nav)}
.cp [data-section=first-difference]:not([data-shape=dag]) p:first-child{font-size:15px;
  font-weight:600;color:var(--bad-ink)}
.cp [data-section=first-difference][data-shape=dag] p{font-weight:600}
.cp [data-section=first-difference] p:last-child{font-weight:600}
.cp table[data-section=changes]{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);border-collapse:separate;border-spacing:0;width:100%}
.cp table[data-section=changes] th{font-size:var(--fs-small);color:var(--ink-muted);
  font-weight:500;padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;
  text-transform:none;letter-spacing:0}
.cp table[data-section=changes] td{font-size:var(--fs-small);padding:9px 12px;
  border-bottom:1px solid var(--line-soft);vertical-align:top}
.cp table[data-section=changes] :is(td[data-cell=digest],td[data-section=settings],
  td[data-section=annotations]){overflow-wrap:anywhere}
.cp table[data-section=changes] tr:last-child td{border-bottom:none}
.cp table[data-section=changes] td[data-result="FIRST DIFFERENCE"]{color:var(--bad-ink);font-weight:600}
.cp pre{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);
  padding:10px 12px;overflow-x:auto;max-width:100%;font-size:var(--fs-small)}
.cp>p[data-state=no-records]{align-self:flex-start;margin-top:-8px;font-size:var(--fs-small);
  font-weight:500;padding:3px 8px;border-radius:var(--r-pill);background:var(--neu-bg);
  color:var(--neu-ink)}
.cp>[data-section=run]{font-size:var(--fs-body);color:var(--ink-muted)}
.cp [data-section=authorization] h2{font-size:15px}
.cp [data-section=authorization] p{font-size:var(--fs-nav)}
.cp [data-section=authorization] p>a{display:inline-block;padding:9px 16px;
  border:1px solid var(--line-node);border-radius:var(--r-ctl);background:var(--surface);
  color:var(--ink);text-decoration:none}
.cp [data-section=authorization] p[data-section=authorization-note]{font-size:var(--fs-small);
  color:var(--ink-muted)}
@media (max-width:1100px){.cp [data-section=cards]{grid-template-columns:repeat(2,minmax(0,1fr))}
  .cp .panels{grid-template-columns:minmax(0,1fr)}}
.cp details>summary{font-size:var(--fs-body);color:var(--ink-muted);cursor:pointer}
.cp [data-section$=-envelope],.cp [data-section=pair],.cp [data-section=sdk]{font-size:var(--fs-body);
  color:var(--ink-muted)}
.cp [data-section=where-started-chain] li[data-first-difference=true]{outline:2px solid var(--cc-ink);
  outline-offset:2px;border-radius:4px}
.cp [data-section^=where-started] table{display:block;max-width:100%;overflow-x:auto}
.cp [data-section^=where-started] table::-webkit-scrollbar{height:12px}
.cp [data-section^=where-started] table::-webkit-scrollbar-track{background:var(--surface-sunk);
  border-radius:6px}
.cp [data-section^=where-started] table::-webkit-scrollbar-thumb{background:var(--line-strong);
  border-radius:6px}
@supports not selector(::-webkit-scrollbar){.cp [data-section^=where-started] table{
  scrollbar-width:auto;scrollbar-color:var(--line-strong) var(--surface-sunk)}}
"""

#: The public mode's banner, in the navigation (`banner()`): only a public console's pages carry it.
PUBLIC_CSS = """
nav.frame [data-frame=banner]{margin:0 0 14px;padding:10px 14px;border-radius:var(--r-ctl);
  background:var(--cc-bg);color:var(--cc-ink);font-size:var(--fs-small);line-height:1.4}
nav.frame [data-frame=banner] code{font-family:var(--font-mono);overflow-wrap:anywhere}
"""


@lru_cache(maxsize=1)
def stylesheet() -> bytes:
    """The fonts' faces, the skin's tokens, the viewer's stylesheet and the frame's rules."""
    from onetrace_console.viewer.page import CSS, FRAME_CSS
    from onetrace_console.viewer.tokens import root_css
    shipped = sorted(p.name for p in _FONTS.glob("*.woff2"))
    if shipped != sorted(_FACES):
        raise RuntimeError(f"the bundled fonts are not the faces this stylesheet names: {shipped}")
    faces = "".join(
        f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
        f"font-display:swap;src:url(/static/fonts/{name}) format('woff2')}}\n"
        for name, (family, weight) in _FACES.items())
    return (faces + root_css() + "\n" + CSS + FRAME_CSS + PAGE_CSS + PUBLIC_CSS).encode("utf-8")


def items(onedoor: bool) -> tuple[tuple[str, str, str], ...]:
    return ITEMS + ((POLICY,) if onedoor else ())


def _current(rel: str) -> str | None:
    """Which item a page belongs under, for `aria-current`."""
    if rel in ("home.html", "counts.html"):
        return "Overview"
    if rel.startswith(("executions-", "runs/")):
        return "Runs"
    if rel == "comparisons.html" or rel.startswith("diff/"):
        return "Comparisons"
    if rel.startswith("incidents"):
        return "Incidents"
    if rel.startswith("policy"):
        return "Policy"
    return None


def _footer(mode: str) -> str:
    return f"<footer><div>{mode}</div><div>onetrace-console {escape(__version__)}</div></footer>"


def footer(user: str | None, *, public: bool = False) -> str:
    """An unsealed page's footer, filled as it is served: the session and the version."""
    from onetrace_console.public import FOOTER_MODE
    if public:
        return _footer(FOOTER_MODE)
    return _footer("Local mode" if user is None else f"Signed in as {escape(user)}")


def sealed_footer(sign_in: bool, *, public: bool = False) -> str:
    """A sealed page's footer, filled as it is rendered: the configuration and the version, never
    a user."""
    from onetrace_console.public import FOOTER_MODE
    if public:
        return _footer(FOOTER_MODE)
    return _footer("Sign-in required" if sign_in else "Local mode")


def banner() -> str:
    """The public mode's banner, the first thing under the brand on every page."""
    from onetrace_console.public import BANNER, BANNER_COMMAND
    return f'<p data-frame="banner">{escape(BANNER)} <code>{escape(BANNER_COMMAND)}</code></p>'


def nav(rel: str, *, onedoor: bool, foot: str, public: bool = False) -> str:
    here = _current(rel)
    links = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if label == here else ""}>{label}</a>'
        for label, href, _ in items(onedoor))
    return f'<div class="brand">onetrace</div>{banner() if public else ""}{links}{foot}'


def fill(page: bytes, rel: str, *, onedoor: bool, user: str | None, public: bool = False) -> bytes:
    """An unsealed page with its frame filled as it is served, or the page unchanged when it has
    no empty frame -- a sealed page, whose frame was filled before its seal."""
    from onetrace_console.viewer.page import FRAME_NAV
    marker = FRAME_NAV.encode("utf-8")
    if page.count(marker) != 1:
        return page
    return page.replace(marker, nav(rel, onedoor=onedoor, foot=footer(user, public=public),
                                    public=public).encode("utf-8"))


# ------------------------------------------------------------------- sealed pages

@dataclass(frozen=True)
class Rendering:
    """The configuration a render runs under: what a sealed page's frame states."""
    onedoor: bool
    sign_in: bool
    public: bool = False


_RENDERING: contextvars.ContextVar[Rendering | None] = contextvars.ContextVar("rendering",
                                                                             default=None)


@contextlib.contextmanager
def rendering(*, onedoor: bool, sign_in: bool, public: bool = False):
    """`with rendering(...)`: sealed pages drawn inside are framed, under this configuration.
    The server renders every page inside one; outside it -- a caller with no console around it --
    a sealed page is drawn as the viewer draws it, with no frame."""
    token = _RENDERING.set(Rendering(onedoor=onedoor, sign_in=sign_in, public=public))
    try:
        yield
    finally:
        _RENDERING.reset(token)


def sealed_framing():
    """The viewer's frame for a sealed page drawn now, or nothing outside `rendering`."""
    from onetrace_console.viewer.page import framed
    return framed(STYLESHEET) if _RENDERING.get() is not None else contextlib.nullcontext()


def fill_sealed(page: str, rel: str) -> str:
    """Fill a sealed page's frame BEFORE it is sealed, so its fingerprint covers the
    frame and the page is served as written. A page drawn outside `rendering` has no frame."""
    from onetrace_console.viewer.page import FRAME_NAV
    r = _RENDERING.get()
    if r is None:
        return page
    if page.count(FRAME_NAV) != 1:
        raise ValueError(f"a sealed page to frame must carry exactly one empty frame: {rel}")
    return page.replace(FRAME_NAV, nav(rel, onedoor=r.onedoor,
                                       foot=sealed_footer(r.sign_in, public=r.public),
                                       public=r.public))
