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
#: Each bundled face: (family, weight, the characters it holds) -- read from the files shipped, never
#: a download. Each weight is two files, IBM Plex's own split: Latin1, and Pi (arrows and other
#: symbols); `unicode-range` names each file's characters, so a page loads Pi only where it draws
#: one. The ranges were read from the files' own character maps (static/fonts/FONTS.md).
_FACES = {
    "IBMPlexSans-Regular-Latin1.woff2": ("IBM Plex Sans", 400,
             "U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02"),
    "IBMPlexSans-Regular-Pi.woff2": ("IBM Plex Sans", 400,
             "U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD"),
    "IBMPlexSans-Medium-Latin1.woff2": ("IBM Plex Sans", 500,
             "U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02"),
    "IBMPlexSans-Medium-Pi.woff2": ("IBM Plex Sans", 500,
             "U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD"),
    "IBMPlexSans-SemiBold-Latin1.woff2": ("IBM Plex Sans", 600,
             "U+0000,U+000D,U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02"),
    "IBMPlexSans-SemiBold-Pi.woff2": ("IBM Plex Sans", 600,
             "U+0E3F,U+2000-200D,U+2015,U+2028-2029,U+202F,U+2032-2033,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+221A,U+221E,U+222B,U+2248,U+2260,U+2264-2265,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+ECE0,U+EFCC,U+FEFF,U+FFFD"),
    "IBMPlexMono-Regular-Latin1.woff2": ("IBM Plex Mono", 400,
             "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02"),
    "IBMPlexMono-Regular-Pi.woff2": ("IBM Plex Mono", 400,
             "U+03C0,U+0E3F,U+2000-200D,U+2010-2012,U+2015,U+2028-2029,U+202F,U+2032-2033,U+203E,U+205F,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+2219-221A,U+221E,U+222B,U+2236,U+2248,U+2260,U+2264-2265,U+2400-2421,U+2500-259F,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+3000,U+FEFF,U+FFFD"),
    "IBMPlexMono-Medium-Latin1.woff2": ("IBM Plex Mono", 500,
             "U+0020-007E,U+00A0-00FF,U+0131,U+0152-0153,U+02C6,U+02DA,U+02DC,U+2013-2014,U+2018-201A,U+201C-201E,U+2020-2022,U+2026,U+2030,U+2039-203A,U+2044,U+20AC,U+2122,U+2212,U+FB01-FB02"),
    "IBMPlexMono-Medium-Pi.woff2": ("IBM Plex Mono", 500,
             "U+03C0,U+0E3F,U+2000-200D,U+2010-2012,U+2015,U+2028-2029,U+202F,U+2032-2033,U+203E,U+205F,U+2070,U+2074-2079,U+2080-2089,U+2113,U+2116,U+2126,U+212E,U+2150-2151,U+2153-215E,U+2190-2199,U+21A9-21AA,U+21B0-21B3,U+21B6-21B7,U+21BA-21BB,U+21C4,U+21C6,U+2202,U+2206,U+220F,U+2211,U+2215,U+2219-221A,U+221E,U+222B,U+2236,U+2248,U+2260,U+2264-2265,U+2400-2421,U+2500-259F,U+25CA,U+2713,U+274C,U+2B0E-2B11,U+3000,U+FEFF,U+FFFD"),
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
.cp>[data-section=subtitle]{font-size:var(--fs-nav);color:var(--ink-muted);margin-top:-12px}
.cp>[data-section=how]{margin-top:-10px}
.cp>[data-section=how]>summary{font-size:var(--fs-small)}
.cp>[data-section=how] [data-section=what]{margin:6px 0 0;font-size:var(--fs-small);
  color:var(--ink-muted)}
.cp [data-card]{position:relative}
.cp [data-card] details.def{margin:6px 0 0}
.cp [data-card] details.def>summary{position:absolute;top:12px;right:12px;width:20px;height:20px;
  border:1px solid var(--line-node);border-radius:var(--r-num);text-align:center;line-height:18px;
  font-size:var(--fs-small);color:var(--ink-muted);list-style:none}
.cp [data-card] details.def>summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cp .zero,.cp .zero a{color:var(--ink-faint)}
.cp .rel{color:var(--ink-muted)}
.cp>[data-section=banner]{background:var(--cc-bg);border:1px solid var(--line);
  border-radius:var(--r-card);padding:10px 14px;font-size:var(--fs-body);color:var(--cc-ink)}
.cp [data-section=cards]{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.cp>[data-section=banner].notice{background:var(--neu-bg);color:var(--neu-ink)}
.cp>.crumbs{margin:0;font-size:var(--fs-small);color:var(--ink-muted)}
.cp>[data-section=instrument]{margin:-8px 0 0;color:var(--ink-muted);overflow-wrap:anywhere}
.cp .io{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:14px;align-items:start}
.cp .io>section{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:14px 16px;min-width:0}
.cp .io table.board td{vertical-align:top}
.cp .io table.board td p{margin:0 0 4px}
.cp .io .note{font-size:var(--fs-small);color:var(--ink-muted)}
.cp .io nav.tabs{display:flex;flex-wrap:wrap;gap:6px 20px;border-bottom:1px solid var(--line);
  margin:0 0 10px}
.cp .io nav.tabs a{padding:6px 2px;text-decoration:none}
.cp .io .fp{color:var(--ink-muted)}
.cp>.title{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px}
.cp>.title>p{margin:0;display:flex;flex-wrap:wrap;gap:6px}
.cp .io>.side{display:flex;flex-direction:column;gap:14px;min-width:0}
.cp .io>.side>section{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:14px 16px;min-width:0}
.cp pre.term{background:var(--nav-bg);color:var(--nav-ink);border-radius:var(--r-ctl);
  padding:12px 14px;margin:0;font-size:var(--fs-small);white-space:pre}
.cp [data-section=printed] h3{margin:14px 0 4px;font-size:var(--fs-body)}
.cp[data-view=receipt] .io{grid-template-columns:minmax(0,1.4fr) minmax(0,1fr)}
.cp[data-view=text-diff] .io{grid-template-columns:minmax(0,300px) minmax(0,1fr)}
.cp[data-view=text-diff] [data-section=outputs]{display:flex;flex-direction:column;gap:14px}
.cp[data-view=text-diff] [data-pane-output]{scroll-margin-top:12px}
.cp[data-view=text-diff] [data-pane-output] h3{margin:0 0 4px;font-size:var(--fs-body)}
.cp[data-view=text-diff] [data-pane-output]:target{outline:2px solid var(--line-strong);outline-offset:6px;border-radius:2px}
.cp[data-view=text-diff] [data-section=changed] li a{display:block;padding:4px 6px;overflow-wrap:anywhere}
.cp[data-view=text-diff] [data-section=changed] :is(h2,h3){margin:0 0 6px;font-size:15px}
.cp[data-view=text-diff] [data-section=changed] ul{margin:0}
.cp[data-view=text-diff] [data-section=changed] li{margin:0}
.cp[data-view=text-diff] [data-section=changed] [data-input]{margin:0 0 6px;font-size:var(--fs-small);color:var(--ink-muted)}
.cp [data-scroll=printed]{max-height:448px;overflow:auto}
.cp[data-view=receipt] table[data-section=receipt] td,
.cp[data-view=receipt] table[data-section=receipt] td :is(.mono,q,code,span){white-space:normal;
  overflow-wrap:anywhere}
.cp .io .fp,.cp .io .fp .mono{overflow-wrap:anywhere}
.cp p[data-input]{overflow-wrap:anywhere}
.cp .onedoor code,.cp .span-context code,.cp .nesting code,.cp [data-section=descent] code,.cp .model-call code{overflow-wrap:anywhere}
.cp[data-view=incident] [data-section=which] li{overflow-wrap:anywhere}
.cp[data-view=incident] [data-scroll=found-rows]{max-height:448px;overflow:auto}
.cp[data-view=incident] pre[data-found=summary]{white-space:pre-wrap;overflow-wrap:anywhere}
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
.cp [data-attention]{flex-wrap:wrap}
.cp [data-attention]>span:first-child{flex:1 1 16em;min-width:0}
.cp [data-attention]>.value{margin-left:auto}
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
.cp table.board td.value:has(time),.cp [data-section=recent-runs] table.board td.value{white-space:normal}
.cp table.board td .rel{display:block}
.cp details[data-node-fold]>summary>h3{display:inline;margin:0}
.cp [data-section=recent-runs] table.board td:first-child,
.cp [data-section=recent-runs] table.board td:first-child *{overflow-wrap:normal;word-break:normal}
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
.cp [data-section=first-difference]:has(>[data-part]){display:grid;
  grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:6px 24px}
.cp [data-section=first-difference] [data-part=where] p:first-child{font-size:15px;
  font-weight:600;color:var(--cc-ink)}
.cp [data-section=first-difference] [data-part=where] p+p{font-weight:600}
.cp [data-section=first-difference][data-shape=dag] p{font-weight:600}
.cp [data-section=first-difference] [data-part=what] p:last-of-type{font-weight:600}
.cp [data-section=first-difference] [data-part=what] pre{margin:8px 0 0}
.cp [data-section=different-pipelines]{background:var(--cc-bg);color:var(--cc-ink);
  border-radius:var(--r-card);padding:10px 14px;font-size:var(--fs-body)}
.cp [data-section=settings-changed] details>summary{font-size:var(--fs-body)}
.cp svg.graph text{font-family:var(--font-sans)}
.cp svg.graph text.name{font-family:var(--font-mono)}
.cp [data-textdiff] [data-counts]{margin:2px 0 6px;font-size:var(--fs-small);color:var(--ink-muted)}
.cp pre[data-hunk]{white-space:normal;padding:6px 0}
.cp pre[data-hunk]>span[data-op]{display:block;white-space:pre-wrap;padding:0 12px 0 0}
.cp pre[data-hunk]>span[data-op="-"]{background:var(--bad-bg)}
.cp pre[data-hunk]>span[data-op="+"]{background:var(--ok-bg)}
.cp pre[data-hunk] .ln{display:inline-block;width:3.5em;padding-right:8px;text-align:right;
  color:var(--ink-muted);user-select:none}
.cp mark.del{background:transparent;color:var(--bad-ink);font-weight:600;text-decoration:line-through}
.cp mark.ins{background:transparent;color:var(--ok-ink);font-weight:600}
.cp svg.graph [data-tone=ok] .node{stroke:var(--ok-ink)}
.cp svg.graph [data-tone=ok] rect.chip{fill:var(--ok-bg)}
.cp svg.graph [data-tone=ok] text.chip{fill:var(--ok-ink)}
.cp svg.graph [data-tone=bad] .node{stroke:var(--bad-ink)}
.cp svg.graph [data-tone=bad] rect.chip{fill:var(--bad-bg)}
.cp svg.graph [data-tone=bad] text.chip{fill:var(--bad-ink)}
.cp svg.graph [data-tone=cc] .node{stroke:var(--cc-ink)}
.cp svg.graph [data-tone=cc] rect.chip{fill:var(--cc-bg)}
.cp svg.graph [data-tone=cc] text.chip{fill:var(--cc-ink)}
.cp svg.graph [data-tone=neu] .node{stroke:var(--line-node)}
.cp svg.graph [data-tone=fd] .node{fill:var(--hl);stroke:var(--cc-ink);stroke-width:2.5;
  filter:drop-shadow(0 0 10px var(--cc-ink))}
.cp svg.graph [data-tone=fd] rect.chip{fill:var(--cc-ink)}
.cp svg.graph [data-tone=fd] text.chip{fill:var(--page)}
.cp svg.graph [data-tone=ca] .node{stroke:var(--cc-ink)}
.cp svg.graph [data-tone=ca] rect.chip{fill:none;stroke:var(--cc-ink)}
.cp svg.graph [data-tone=ca] text.chip{fill:var(--cc-ink)}
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
.cp table[data-section=changes] tr[data-child-of] td[data-label=node],.cp table[data-section=changes] tr[data-nested-run]>td{padding-left:32px}
.cp table[data-section=changes] tr[data-depth="2"] td[data-label=node],.cp table[data-section=changes] tr[data-nested-run][data-depth="2"]>td{padding-left:52px}
.cp tr[data-child-of] .inside{font-size:var(--fs-small);color:var(--ink-muted)}
.cp table[data-section=changes] td[data-result="FIRST DIFFERENCE"]{color:var(--cc-ink);font-weight:600}
.cp table[data-section=changes] td[data-section=annotations] [data-part=fold]{display:block;margin-top:6px;padding-top:4px;border-top:1px solid var(--line-soft)}
.cp table[data-section=changes] td[data-section=annotations] [data-part=fold] details>summary{font-size:var(--fs-small)}
.cp pre{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);
  padding:10px 12px;overflow-x:auto;max-width:100%;font-size:var(--fs-small)}
.cp>p[data-state=no-records]{align-self:flex-start;margin-top:-8px}
.cp>[data-section=run]{font-size:var(--fs-body);color:var(--ink-muted)}
.cp [data-section=authorization] h2{font-size:15px}
.cp [data-section=authorization] p{font-size:var(--fs-nav)}
.cp [data-section=authorization] p>a{display:inline-block;padding:9px 16px;
  border:1px solid var(--line-node);border-radius:var(--r-ctl);background:var(--surface);
  color:var(--ink);text-decoration:none}
.cp [data-section=authorization] p[data-section=authorization-note]{font-size:var(--fs-small);
  color:var(--ink-muted)}
.cp svg.mark{display:inline-block;vertical-align:-2px;margin-right:2px;flex:none}
.cp svg.mark .f{fill:currentColor}
.cp svg.mark .s{fill:none;stroke:currentColor;stroke-width:1.6}
.cp svg.mark[data-tone=ok]{color:var(--ok-ink)}
.cp svg.mark[data-tone=bad]{color:var(--bad-ink)}
.cp svg.mark[data-tone=cc]{color:var(--cc-ink)}
.cp svg.mark[data-tone=neu]{color:var(--neu-ink)}
.cp .marks{display:flex;flex-wrap:wrap;gap:3px;margin:6px 0}
.cp table.board[data-group]{background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);border-collapse:separate;border-spacing:0}
.cp table.board[data-group] td{vertical-align:top}
.cp ul.legend{display:flex;flex-wrap:wrap;gap:4px 16px;margin:4px 0 0;font-size:var(--fs-small)}
.cp [data-section=legend] p{margin:0;font-size:var(--fs-small);color:var(--ink-muted)}
.cp ol.chain{display:flex;flex-wrap:wrap;gap:6px;list-style:none;margin:8px 0;padding:0}
.cp ol.chain li{display:flex;flex-direction:column;align-items:center;gap:2px}
.cp ol.chain .stage{border:1px solid var(--line-strong);border-radius:6px;padding:2px 8px;
  font-size:var(--fs-small);background:var(--surface)}
.cp ol.chain .n{font-size:var(--fs-small);font-weight:600}
.cp ol.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;
  list-style:none;margin:10px 0;padding:0}
.cp ol.tiles>li{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
  padding:10px 12px;min-width:0}
.cp ol.tiles>li>a{display:block;overflow-wrap:anywhere}
.cp ol.tiles>li p{margin:4px 0 0;font-size:var(--fs-small)}
.cp ol.tiles .n{color:var(--ink-muted)}
.cp svg.bar{display:block;width:100%;height:8px;margin:8px 0 2px;border-radius:4px}
.cp svg.bar [data-tone=ok]{fill:var(--ok-ink)}
.cp svg.bar [data-tone=bad]{fill:var(--bad-ink)}
.cp svg.bar [data-tone=cc]{fill:var(--cc-ink)}
.cp svg.bar [data-tone=neu]{fill:var(--neu-ink)}
.cp [data-section=pipeline-cards]{margin:14px 0}
.cp .pcards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:10px}
.cp a.pcard{display:block;background:var(--surface);border:1px solid var(--line);
  border-radius:var(--r-card);padding:12px 14px;color:var(--ink);text-decoration:none;min-width:0}
.cp a.pcard:hover{border-color:var(--line-strong)}
.cp a.pcard:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cp a.pcard h3{margin:0;font-size:var(--fs-body)}
.cp a.pcard p{margin:4px 0 0;font-size:var(--fs-small);color:var(--ink-muted)}
@media (max-width:760px){.cp .pcards{grid-template-columns:minmax(0,1fr)}}
@media (max-width:1100px){.cp [data-section=cards]{grid-template-columns:repeat(2,minmax(0,1fr))}
  .cp .panels{grid-template-columns:minmax(0,1fr)}
  .cp .io,.cp[data-view=receipt] .io,.cp[data-view=text-diff] .io{grid-template-columns:minmax(0,1fr)}}
@media (max-width:760px){.cp [data-section=first-difference]:has(>[data-part]){
  grid-template-columns:minmax(0,1fr)}
  .cp [data-attention]{flex-direction:column;gap:2px}
  .cp [data-attention]>.value,.cp [data-attention]>.value .rel{text-align:left}
  .cp [data-attention]>.value{white-space:normal}}
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

#: The one chip (0.1.1's one shared style). Every state chip, wherever a page draws it -- the console's
#: pills, the run ladder's rung states, a stage page's two badges, the "No records" chip -- has
#: this one shape, and one of the skin's four tones, by the one rule for every page (`tones.py`):
#: green when a check ran and held, red when it ran and failed, amber when it couldn't be done or
#: wasn't done, neutral when the evidence wasn't made. Every chip keeps its words. A
#: couldn't-check note -- a sentence, not a chip -- is an amber block, as the last-attempt-failed
#: line is. Held by tests/test_shared_style.py and tests/test_tones.py.
CHIP_SHAPE = ("display:inline-block;font-size:var(--fs-small);font-weight:500;padding:3px 8px;"
              "border-radius:var(--r-pill);margin-right:4px")
_RUNG = ".shell .page tr[data-rung]"
#: The runs list's answer cells (F1): the same chips, in a viewer page's frame.
_ANSWER = ".shell .page td[data-answer]"
_BADGE = ".cp tr[data-badge]"
_STATE = ">td:last-child>span:first-child"


def _states(tone: str) -> str:
    """Every rung and badge state the one rule gives `tone`, as selectors."""
    from onetrace_console import tones
    return ",".join(f"{row}[data-state={s}]{_STATE}" for s in tones.RUNG
                    if tones.tone(tones.RUNG, s) == tone for row in (_RUNG, _BADGE))


CHIP_CSS = (
    f".cp .pill,{_ANSWER} .pill,{_RUNG}{_STATE},{_BADGE}{_STATE},.cp>p[data-state=no-records]{{{CHIP_SHAPE}}}\n"
    f".cp .ok,{_ANSWER} .ok,{_states('ok')}{{background:var(--ok-bg);color:var(--ok-ink)}}\n"
    f".cp .cc,{_ANSWER} .cc,{_states('cc')}{{background:var(--cc-bg);color:var(--cc-ink)}}\n"
    f".cp .bad,{_ANSWER} .bad,{_states('bad')}{{background:var(--bad-bg);color:var(--bad-ink)}}\n"
    f".cp .neu,{_ANSWER} .neu,.cp>p[data-state=no-records],{_states('neu')}"
    f"{{background:var(--neu-bg);color:var(--neu-ink)}}\n"
    #: Declined by a step's own rule: outlined in the accent on the page's own ground, never red.
    #: An outline, not a border, so the chip keeps the one shape.
    f":is(.cp,.shell .page) .dec{{background:transparent;color:var(--accent);outline:1px solid var(--accent);"
    f"outline-offset:-1px}}\n"
    #: A rung whose state is the declined kind ("Not reached"), drawn the same way.
    f"{_states('dec')}{{background:transparent;color:var(--accent);outline:1px solid var(--accent);"
    f"outline-offset:-1px}}\n"
    #: A comparison's first difference, amber filled, and a step changed after it, amber outlined.
    f":is(.cp,.shell .page) .fd{{background:var(--cc-ink);color:var(--page)}}\n"
    f":is(.cp,.shell .page) .ca{{background:transparent;color:var(--cc-ink);outline:1px solid var(--cc-ink);"
    f"outline-offset:-1px}}\n"
    f".cp :is(p,section,td)[data-state=couldnt-check]{{background:var(--cc-bg);color:var(--cc-ink);"
    f"border-radius:var(--r-ctl);padding:8px 12px}}\n"
    #: A graph's marks, in the console's stylesheet only (the free file never marks a graph):
    #: the first difference outlined in the bad ink, a failed attempt's box in the amber. The
    #: words stay with them: the node's state line, and the fold's "failed attempt".
    f"svg.graph [data-mark=first] .node{{stroke:var(--cc-ink);stroke-width:2.5;"
    f"filter:drop-shadow(0 0 10px var(--cc-ink))}}\n"
    #: Part V's "First recorded change": the same outline, amber -- a comparison's marker, not a
    #: check's result, so never red.
    #: Specific enough to win over the box's tone (`.cp svg.graph [data-tone=neu] .node`).
    f".cp svg.graph [data-mark=recorded-change][data-tone] .node{{stroke:var(--cc-ink);stroke-width:2}}\n"
    f"svg.graph [data-failed=yes] .node{{stroke:var(--cc-ink);stroke-width:1.5}}\n"
    #: What the layout check (tools/layout_check.py) found past the edge at 390, each fixed in
    #: the console's stylesheet only: the relative time under its time in "Needs attention"; a
    #: run's id, and a long command, breaking where they must (copied, the same characters).
    f".cp [data-attention]>.value .rel{{display:block;text-align:right}}\n"
    f".shell .page table.timeline .mono{{overflow-wrap:anywhere}}\n"
    #: onetrace 0.5.0's parts on a run's page (the viewer's): code in them breaks anywhere at 390.
    f".shell .page .onedoor code,.shell .page .span-context code,.shell .page .nesting code{{overflow-wrap:anywhere}}\n"
    #: Steps inside steps in a run's table of steps (`nesting_ladder`): each child, and each nested
    #: run's row, indented under its calling step.
    f".shell .page tr[data-child-of]>td:first-child{{padding-left:32px}}\n"
    f".shell .page tr[data-depth=\"2\"]>td:first-child{{padding-left:52px}}\n"
    f".shell .page tr[data-child-of] .inside{{font-size:var(--fs-small);color:var(--ink-muted)}}\n"
    f".shell .page tr[data-nested-run] code{{overflow-wrap:anywhere}}\n"
    #: The runs list's run names: at desktop width a name broke every four characters,
    #: because `anywhere` let the table shrink the column to almost nothing. `break-word` still
    #: breaks a name that must, but leaves the column its longest piece between hyphens as its
    #: least width, and the column has a floor of its own: a name breaks at its hyphens.
    f".shell .page table.timeline[data-section=runs-table] td:first-child .mono{{overflow-wrap:break-word}}\n"
    f"@media (min-width:761px){{.shell .page table.timeline[data-section=runs-table] td:first-child"
    f"{{min-width:12ch}}}}\n"
    #: Its answers' chips a little narrower than elsewhere: a "Couldn't check" in "Ran as approved"
    #: (an agent's run, a graph with no plan row) took the table 12 pixels past its frame at 1280.
    f".shell .page table.timeline[data-section=runs-table] td[data-answer] .pill{{margin-right:0;"
    f"padding-left:6px;padding-right:6px}}\n"
    f".cp code{{overflow-wrap:anywhere}}\n"
    #: A runs list with no run in it: its one line, grey as the Overview's zeros are.
    f".shell .page p.zero[data-section=no-runs]{{color:var(--ink-faint)}}\n"
    #: A receipt card's quoted names (an input such as "receipt:lookup_account#2") break where
    #: they must at 390, inside the card's grid, rather than reaching past the window.
    f".shell .page .card .grid>*{{min-width:0}}\n"
    f".shell .page .card .grid q[data-words]{{overflow-wrap:anywhere}}\n")

#: On a narrow screen every table in a region stacks: each row a block, each cell under its column's
#: header (`words.labelled`), long values wrapping where they must. Nothing is cut off, and nothing
#: but a verifier-output or code block scrolls sideways (`tools/layout_check.py`, SCROLL_ALLOWED).
NARROW_CSS = """
.shell .graph-box svg.graph{max-width:100%;height:auto}
@media (max-width:760px){
.shell .graph-box svg.graph{display:none}
.shell .graph-list{display:block;list-style:none;margin:0;padding:0}
.shell .graph-list>li{display:flex;flex-direction:column;gap:2px;border:1px solid var(--line-node);
  border-radius:var(--r-ctl);padding:8px 10px;background:var(--surface);overflow-wrap:anywhere}
.shell .graph-list>li+li{margin-top:14px;position:relative}
.shell .graph-list>li[data-reads-previous=yes]::before{content:"";position:absolute;left:20px;
  top:-15px;height:14px;border-left:2px solid var(--line-strong)}
.shell .graph-list>li[data-list-mark=recorded-change]{border-color:var(--cc-ink);border-width:2px}
.shell .graph-list>li[data-list-mark=first]{border-color:var(--cc-ink);border-width:2px}
.shell .graph-list .state{font-size:var(--fs-small);color:var(--ink-muted)}
.shell .scroll-x{overflow:visible;mask-image:none;-webkit-mask-image:none}
.shell .scroll-x :is(table,thead,tbody,tr,th,td){display:block;width:auto;min-width:0}
.shell .scroll-x thead{display:none}
.shell .scroll-x tr{padding:8px 0;border-bottom:1px solid var(--line-soft)}
.shell .scroll-x tr:last-child{border-bottom:none}
.shell .scroll-x :is(th,td){border:none;padding:2px 0;text-align:left;white-space:normal;
  overflow-wrap:anywhere}
.shell .scroll-x td :is(.mono,code,q,span,time,a){white-space:normal;overflow-wrap:anywhere}
.shell .scroll-x td[data-label]::before{content:attr(data-label);display:block;
  font-size:var(--fs-small);color:var(--ink-muted)}
.shell .scroll-x tr>:first-child:not([data-label]){font-weight:500}
}
"""

#: The theme switch in the footer: the navigation's own ink and lines, in both themes.
THEME_CSS = """
nav.frame footer .theme{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
nav.frame footer .theme button{font:inherit;color:var(--nav-ink);background:var(--nav-bg);
  border:1px solid var(--nav-ink-faint);border-radius:var(--r-ctl);padding:4px 10px;cursor:pointer}
nav.frame footer .theme button:hover{color:var(--nav-on-ink);background:var(--nav-on-bg)}
nav.frame footer .theme button:focus-visible{outline:2px solid var(--nav-on-ink);outline-offset:2px}
nav.frame footer .theme button[hidden]{display:none}
"""

#: "Choose run B"'s Compare button, shaped as the theme switch is, in the page's own ink and lines in
#: both themes; and the line under the request where its script says what the console answered,
#: taking no space while it is empty.
COMPARE_CSS = """
.cp button[data-compare-post]{font:inherit;color:var(--ink);background:var(--surface);
  border:1px solid var(--line-strong);border-radius:var(--r-ctl);padding:4px 10px;cursor:pointer}
.cp button[data-compare-post]:hover{background:var(--surface-sunk)}
.cp button[data-compare-post]:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cp button[data-compare-post]:disabled{color:var(--ink-faint);cursor:default}
.cp button[data-compare-post][hidden]{display:none}
.cp [data-compare-said]{display:block;margin-top:4px}
.cp [data-compare-said]:empty{display:none}
"""

#: The public mode's banner, in the navigation (`banner()`): only a public console's pages carry it.
PUBLIC_CSS = """
nav.frame [data-frame=banner]{margin:0 0 14px;padding:10px 14px;border-radius:var(--r-ctl);
  background:var(--cc-bg);color:var(--cc-ink);font-size:var(--fs-small);line-height:1.4}
nav.frame [data-frame=banner] code{font-family:var(--font-mono);overflow-wrap:anywhere}
"""


@lru_cache(maxsize=1)
def stylesheet() -> bytes:
    """The fonts' faces, the skin's tokens, the viewer's stylesheet, the frame's rules, the console
    pages' rules and the one chip family."""
    from onetrace_console.viewer.page import CSS, FRAME_CSS
    from onetrace_console.viewer.tokens import root_css, scale_css, theme_css
    shipped = sorted(p.name for p in _FONTS.glob("*.woff2"))
    if shipped != sorted(_FACES):
        raise RuntimeError(f"the bundled fonts are not the faces this stylesheet names: {shipped}")
    faces = "".join(
        f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
        f"font-display:swap;src:url(/static/fonts/{name}) format('woff2');unicode-range:{chars}}}\n"
        for name, (family, weight, chars) in _FACES.items())
    from onetrace_console.run_head import HEAD_CSS
    from onetrace_console.views import VIEWS_CSS
    from onetrace_console.short_answer import SHORT_CSS
    from onetrace_console.explain import EXPLAIN_CSS
    from onetrace_console.explain_setup import SETUP_CSS
    from onetrace_console.info_mark import INFO_CSS
    return (faces + root_css() + "\n" + scale_css() + "\n" + theme_css() + "\n" + CSS + FRAME_CSS + PAGE_CSS + CHIP_CSS
            + THEME_CSS + COMPARE_CSS + PUBLIC_CSS + HEAD_CSS + VIEWS_CSS + SHORT_CSS + EXPLAIN_CSS + SETUP_CSS + INFO_CSS
            + NARROW_CSS).encode("utf-8")


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


#: The theme switch, in the footer beside the version: a choice of light, dark, or the system's
#: setting for this browser, kept in its own storage under THEME_KEY and nowhere else -- nothing is
#: sent, and the console stores nothing. With no choice saved, a page is dark, as it is with no
#: script at all. Two buttons, because one that cycled through three states would not say what a
#: press does: the first names the theme it switches to; the second, shown until the system's
#: setting is the choice, follows it. Both are `hidden` until the script shows them, so a page read
#: without scripts is the page it was. Not a form: it posts nothing, and goes nowhere.
THEME_KEY = "onetrace-console-theme"
THEME_SWITCH = ('<div class="theme" data-theme-controls>'
                '<button type="button" data-theme-switch hidden>Switch to light theme</button>'
                '<button type="button" data-theme-system hidden>Follow the system setting</button>'
                "</div>")
#: In `<head>`, before the stylesheet: the saved choice set before the page is first drawn, so a
#: page set to light never shows dark first. Storage that is blocked leaves the default, dark.
THEME_HEAD_SCRIPT = ("<script>try{var t=localStorage.getItem('" + THEME_KEY + "');"
                     "if(t==='light'||t==='dark'||t==='system')"
                     "document.documentElement.setAttribute('data-theme',t)"
                     "}catch(e){}</script>")
#: After the buttons: shows them, and keeps their words true to what a press does. A choice is
#: kept where the browser allows; where it doesn't, it holds for the page in view.
THEME_SCRIPT = (
    "<script>(function(){var d=document.documentElement,k='" + THEME_KEY + "',"
    "a=document.querySelector('[data-theme-switch]'),b=document.querySelector('[data-theme-system]'),"
    "m=matchMedia('(prefers-color-scheme: dark)');if(!a||!b)return;"
    "function now(){var t=d.getAttribute('data-theme');"
    "return t==='light'||t==='dark'?t:t==='system'?(m.matches?'dark':'light'):'dark'}"
    "function keep(v){try{localStorage.setItem(k,v)}catch(e){}}"
    "function draw(){a.textContent='Switch to '+(now()==='dark'?'light':'dark')+' theme';"
    "a.hidden=false;b.hidden=d.getAttribute('data-theme')==='system'}"
    "a.addEventListener('click',function(){var v=now()==='dark'?'light':'dark';"
    "d.setAttribute('data-theme',v);keep(v);draw()});"
    "b.addEventListener('click',function(){d.setAttribute('data-theme','system');keep('system');draw();a.focus()});"
    "m.addEventListener('change',draw);draw()})()</script>")


from onetrace_console.explain_setup import LINK as _SETUP_WORDS, PATH as _SETUP_PATH  # noqa: E402

#: The link to the setup page (`explain_setup`), in a local console's footer as it serves a page.
SETUP_LINK = f'<div><a href="{_SETUP_PATH}" data-frame="setup">{_SETUP_WORDS}</a></div>'


def _footer(mode: str, setup_link: bool = False) -> str:
    link = SETUP_LINK if setup_link else ""
    return (f"<footer><div>{mode}</div><div>onetrace-console {escape(__version__)}</div>{link}"
            f"{THEME_SWITCH}{THEME_SCRIPT}</footer>")


def footer(user: str | None, *, public: bool = False, setup_link: bool = False) -> str:
    """An unsealed page's footer, filled as it is served: the session and the version; on a local
    console as it serves the page (`setup_link`), the link to the setup page. Never on a public
    console, nor on an export, whose pages are files."""
    from onetrace_console.public import FOOTER_MODE
    if public:
        return _footer(FOOTER_MODE)
    return _footer("Local mode" if user is None else f"Signed in as {escape(user)}", setup_link)


def sealed_footer(sign_in: bool, *, public: bool = False) -> str:
    """A sealed page's footer, filled as it is rendered: the configuration and the version, never
    a user."""
    from onetrace_console.public import FOOTER_MODE
    if public:
        return _footer(FOOTER_MODE)
    return _footer("Sign-in required" if sign_in else "Local mode")


def banner() -> str:
    """The public mode's banner, the first thing under the brand on every page. The command ends its
    sentence: a full stop after it, outside its code type, before the sentence on the demo's runs."""
    from onetrace_console.public import BANNER, BANNER_COMMAND, banner_runs
    return (f'<p data-frame="banner">{escape(BANNER)} <code>{escape(BANNER_COMMAND)}</code>. '
            f'{escape(banner_runs())}</p>')


def nav(rel: str, *, onedoor: bool, foot: str, public: bool = False) -> str:
    here = _current(rel)
    links = "".join(
        f'<a href="{href}"{" aria-current=\"page\"" if label == here else ""}>{label}</a>'
        for label, href, _ in items(onedoor))
    return f'<div class="brand">onetrace</div>{banner() if public else ""}{links}{foot}'


def fill(page: bytes, rel: str, *, onedoor: bool, user: str | None, public: bool = False,
         setup_link: bool = False) -> bytes:
    """An unsealed page with its frame filled as it is served, or the page unchanged when it has
    no empty frame -- a sealed page, whose frame was filled before its seal."""
    from onetrace_console.viewer.page import FRAME_NAV
    marker = FRAME_NAV.encode("utf-8")
    if page.count(marker) != 1:
        return page
    return page.replace(marker, nav(rel, onedoor=onedoor, foot=footer(user, public=public, setup_link=setup_link),
                                    public=public).encode("utf-8"))


# ------------------------------------------------------------------- sealed pages

@dataclass(frozen=True)
class Rendering:
    """The configuration a render runs under: what a sealed page's frame states."""
    onedoor: bool
    sign_in: bool
    public: bool = False
    #: A local console's link pattern to the person's tracing tool (`config.tracing`); "" for none.
    tracing_link: str = ""


_RENDERING: contextvars.ContextVar[Rendering | None] = contextvars.ContextVar("rendering",
                                                                             default=None)


@contextlib.contextmanager
def rendering(*, onedoor: bool, sign_in: bool, public: bool = False, tracing_link: str = ""):
    """`with rendering(...)`: sealed pages drawn inside are framed, under this configuration.
    The server renders every page inside one; outside it -- a caller with no console around it --
    a sealed page is drawn as the viewer draws it, with no frame."""
    token = _RENDERING.set(Rendering(onedoor=onedoor, sign_in=sign_in, public=public,
                                     tracing_link="" if public else tracing_link))
    try:
        yield
    finally:
        _RENDERING.reset(token)


def tracing_link() -> str:
    """The person's link pattern for a render now: a local console's only; "" otherwise."""
    r = _RENDERING.get()
    return r.tracing_link if r is not None and not r.public else ""


def rendering_public() -> bool:
    """Whether the render now is a public console's: such a page offers nothing that computes."""
    r = _RENDERING.get()
    return bool(r is not None and r.public)


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
