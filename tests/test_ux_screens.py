"""What a new user's first screens say, over the demo's own four runs.

The demo's runs (`tests/fixtures/demo-runs-rc2/`) are delivered to a real console, the two query
runs are compared, and every page it rendered is read as a reader sees it (`tools.visible_text`):

1. no incident for a check the pinned release does not ship; a run that declares links between its
   stages with no edge row in the verifier's report carries a one-line note, never an incident;
2. "Where it changed" reads the same latest comparison the graph reads, and names its first
   difference; it says there was no comparison only when there was none;
3. no page promises a later version ("until onetrace ...");
4. no page names internal or draft vocabulary: the authorization row says plainly that this
   console does not record authorization;
5. no page renders a month by name; dates are ISO 8601 or plain numbers;
6. user-facing text names no internal process, place or person.
"""
from __future__ import annotations

import calendar
import hashlib
import json
import re
import urllib.request
from pathlib import Path

import pytest

from tests.conftest import make_tar, serving

RUNS = Path(__file__).resolve().parent / "fixtures" / "demo-runs-rc2"
NAMES = ("ingest-day1", "ingest-day2", "query-day1", "query-day2")
#: Every month by name, from the calendar module: Python reads it in the C locale unless a program
#: sets another, so these are the English names on every host. No month is written out here.
MONTHS = re.compile(r"\b(" + "|".join(calendar.month_name[1:]) + r")\b")
#: Words no page may show: internal vocabulary, process ids and places, and personal names.
NOT_ON_A_PAGE = {
    "AADP": re.compile(r"\bAADP\b"),
    "onedoor": re.compile(r"onedoor", re.I),
    "canary": re.compile(r"\bcanary\b", re.I),
    "core": re.compile(r"\bcore\b"),
    "pod": re.compile(r"\bpod\b"),
    "a ruling id": re.compile(r"\bR-20\d\d-\d\d-\d\d"),
    "a work-order id": re.compile(r"\bWO-C\d"),
    "a version promise": re.compile(r"until onetrace", re.I),
}


def _checked_fixture() -> None:
    """The fixture is the demo's bytes, or the tests refuse to read it."""
    for line in (RUNS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        assert hashlib.sha256((RUNS / rel).read_bytes()).hexdigest() == digest, rel


def _post(url: str, data: bytes = b"") -> dict:
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-tar"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def _deliver(base: str, name: str) -> str:
    folder = RUNS / name
    files = {p.relative_to(folder).as_posix(): p.read_bytes()
             for p in sorted(folder.rglob("*")) if p.is_file()}
    files["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n"
                                  for n, b in sorted(files.items())).encode()
    got = _post(base + "/v1/runs", make_tar(files))
    assert got["accepted"] and got["run_id"] == name, got
    return got["run_key"]


def _text(html: str) -> str:
    from tools.visible_text import blocks
    return "\n".join(blocks(html))


def _section(html: str, name: str) -> str:
    """One `<section data-section="...">` of a page, as text. Sections do not nest on the case page."""
    found = re.search(rf'<section data-section="{name}">(.*?)</section>', html, re.S)
    assert found, f"no {name} section"
    return _text(found.group(1))


def _pages(root: Path) -> dict[str, str]:
    return {p.relative_to(root / "pages").as_posix(): _text(p.read_text(encoding="utf-8"))
            for p in sorted((root / "pages").rglob("*.html"))}


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    """(base URL, store root, {name: run key}, comparison key) after the four runs are delivered and
    the two query runs compared: once for the module, as every case that takes it only reads it."""
    _checked_fixture()
    with serving(tmp_path_factory.mktemp("ux-screens")) as (base, root):
        keys = {name: _deliver(base, name) for name in NAMES}
        cmp = _post(f"{base}/compare?a={keys['query-day1']}&b={keys['query-day2']}")["comparison_key"]
        yield base, root, keys, cmp


# ------------------------------------------------------------------ 1. no incident for an unshipped check

def test_the_four_demo_runs_raise_no_incidents(demo, examined):
    from onetrace_console.incidents import derive
    from onetrace_console.store import Store
    _base, root, keys, _cmp = demo
    store = Store(root / "store")
    incidents = derive(store)
    examined(len(keys), "demo runs whose incidents were raised")
    assert len(incidents) == 0, [(i.rule, i.quoted) for i in incidents]
    incidents_page = _text((root / "pages" / "incidents.html").read_text(encoding="utf-8"))
    assert incident_page_problems(incidents_page, len(keys)) == []
    assert "0 incidents raised from 0 of 4 runs." in incidents_page.splitlines()


def incident_page_problems(page: str, runs: int) -> list[str]:
    """The Incidents page, where the Overview's incident count is kept: every rule it builds
    reads 0 runs of the runs stored, and says it raised nothing."""
    from onetrace_console.incidents import RULES
    out = []
    for rule in RULES:
        if f"{rule.id} — 0 runs of {runs}" not in page:
            out.append(f"{rule.id}: not 0 runs of {runs}")
    if page.count(f"This rule raised nothing from the {runs} runs stored.") != len(RULES):
        out.append("a rule that raised something")
    return out


def test_sabotage_an_incident_on_the_incidents_page_is_named(demo):
    _base, root, keys, _cmp = demo
    page = _text((root / "pages" / "incidents.html").read_text(encoding="utf-8"))
    raised = page.replace(f"I-CONTRADICTS — 0 runs of {len(keys)}", f"I-CONTRADICTS — 1 runs of {len(keys)}", 1)
    raised = raised.replace(f"This rule raised nothing from the {len(keys)} runs stored.", "", 1)
    assert raised != page
    assert incident_page_problems(raised, len(keys)) == ["I-CONTRADICTS: not 0 runs of 4",
                                                          "a rule that raised something"]


def test_a_run_declaring_links_with_no_edge_row_carries_a_note_not_an_incident(store, examined):
    """A verifier report with no edge row, for a run whose manifest declares edges."""
    from onetrace_console.checks import TOPOLOGY_NO_EDGE_ROWS, topology_note
    examined(2, "reports read for their edge rows")
    without = "[PASS   ] receipts/01-a.json: chain link\n\n1 pass, 0 fail, 0 not-run  ->  PASS\n"
    with_rows = ("[PASS   ] receipts/01-a.json: chain link\n"
                 "[PASS   ] edges equal the edges derived from the receipts\n\n"
                 "2 pass, 0 fail, 0 not-run  ->  PASS\n")
    assert topology_note(declares_edges=True, output=without) == TOPOLOGY_NO_EDGE_ROWS
    assert topology_note(declares_edges=True, output=with_rows) == ""
    assert topology_note(declares_edges=False, output=without) == ""
    assert "incident" not in TOPOLOGY_NO_EDGE_ROWS.lower() and len(TOPOLOGY_NO_EDGE_ROWS) < 160


def test_a_topology_note_raises_no_incident(demo, examined):
    """Even a stored run that carries the note raises no incident from it: a note is not an event."""
    from dataclasses import replace

    from onetrace_console.checks import TOPOLOGY_NO_EDGE_ROWS
    from onetrace_console.incidents import _could_not_check
    from onetrace_console.store import Store
    _base, root, keys, _cmp = demo
    store = Store(root / "store")
    run = replace(store.get_run(keys["query-day2"]), topology_note=TOPOLOGY_NO_EDGE_ROWS)
    examined(1, "run with a topology note")
    assert [i for i in _could_not_check(run, store) if i.field_path == "topology_note"] == []


# ------------------------------------------------------------------ 2. "Where it changed" agrees with the graph

def test_where_it_changed_names_the_first_difference_the_graph_marks(demo, examined):
    _base, root, keys, _cmp = demo
    html = (root / "pages" / "runs" / keys["query-day2"] / "case.html").read_text(encoding="utf-8")
    examined(1, "the compared run's page")
    section = _section(html, "changed")
    assert "These verdicts come from the latest comparison" in _text(html)
    assert "No comparison with another run was made" not in section, section
    assert "retrieve" in section, section


def test_with_no_comparison_both_the_section_and_the_graph_say_so(demo, examined):
    _base, root, keys, _cmp = demo
    #: query-day1 is the comparison's baseline, never its candidate: no comparison of it as the
    #: candidate exists, so neither part of its page may claim one.
    html = (root / "pages" / "runs" / keys["query-day1"] / "case.html").read_text(encoding="utf-8")
    examined(1, "the uncompared run's page")
    section = _section(html, "changed")
    assert "No comparison with another run was made" in section, section
    assert "These verdicts come from the latest comparison" not in _text(html)


# ------------------------------------------------------------------ 3-6. what every page says

def test_the_receipt_shows_the_verifiers_edge_rows_not_a_version_promise(demo, examined):
    _base, root, keys, _cmp = demo
    receipt = _text((root / "pages" / "runs" / keys["query-day2"] / "receipt.html").read_text(encoding="utf-8"))
    examined(1, "receipt page")
    graph = next(b for b in receipt.splitlines() if b.startswith("THE GRAPH") or "nodes ·" in b)
    assert "until onetrace" not in graph and "edges equal the edges derived from the receipts" in graph, graph


def _authors() -> list[str]:
    """The people the package names as its authors, read from its own metadata, not written here."""
    import tomllib
    meta = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    return [a["name"] for a in meta["project"].get("authors", []) if a.get("name")]


def test_no_page_names_a_person(demo, examined):
    _base, root, _keys, _cmp = demo
    pages = _pages(root)
    names = [part for name in _authors() for part in name.split() if len(part) > 2]
    assert names, "the package names no author, so this test would check nothing"
    examined(len(pages), "pages read as a reader sees them")
    hits = {n: [w for w in names if re.search(rf"\b{re.escape(w)}\b", t)] for n, t in pages.items()}
    assert not {n: h for n, h in hits.items() if h}, "a person named on a page"


@pytest.mark.parametrize("what", sorted(NOT_ON_A_PAGE))
def test_no_page_shows_it(demo, examined, what):
    _base, root, _keys, _cmp = demo
    pages = _pages(root)
    examined(len(pages), "pages read as a reader sees them")
    hits = {name: NOT_ON_A_PAGE[what].findall(text) for name, text in pages.items()}
    assert not {n: h for n, h in hits.items() if h}, f"{what} on a page"


def month_problems(pages: dict[str, str]) -> dict[str, list[str]]:
    """{page: the month names it shows}, for each page that shows one."""
    return {n: MONTHS.findall(t) for n, t in pages.items() if MONTHS.search(t)}


def test_no_page_renders_a_month_by_name(demo, examined):
    _base, root, _keys, _cmp = demo
    pages = _pages(root)
    examined(len(pages), "pages read as a reader sees them")
    assert not month_problems(pages)


def test_sabotage_a_month_planted_in_a_rendered_page_is_named(demo, examined):
    """One month name, taken from the calendar module, planted in one real rendered page."""
    _base, root, _keys, _cmp = demo
    pages = _pages(root)
    name = sorted(pages)[0]
    month = calendar.month_name[10]
    planted = {**pages, name: pages[name] + " Generated on 3 " + month + "."}
    examined(1, "planted month")
    assert month_problems(planted) == {name: [month]}


def test_the_authorization_row_says_this_console_does_not_record_authorization(demo, examined):
    _base, root, keys, _cmp = demo
    home = _text((root / "pages" / "home.html").read_text(encoding="utf-8"))
    case = _text((root / "pages" / "runs" / keys["query-day2"] / "case.html").read_text(encoding="utf-8"))
    examined(2, "pages with the authorization row")
    for text in (home, case):
        assert "Action authorized, effect confirmed" in text
        assert "This console does not record authorization." in text


# ------------------------------------------------------------------ the polish round: no raw values

SNAKE = re.compile(r"\b[a-z]+_[a-z_]+\b")


def _reader_text(html: str) -> str:
    """What a reader reads as the page's own words: outside code spans, `<pre>` blocks, quoted record
    or verifier words (`data-words`) and the deeper disclosure layers, where values are shown as they are."""
    from html.parser import HTMLParser

    class Reader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.stack, self.out = [], []

        def handle_starttag(self, tag, attrs):
            if tag not in ("meta", "br", "img", "link", "input", "hr"):
                self.stack.append((tag, dict(attrs)))
            self.out.append(" ")

        def handle_endtag(self, tag):
            while self.stack:
                if self.stack.pop()[0] == tag:
                    break
            self.out.append(" ")

        def handle_data(self, data):
            if any(t in ("style", "script", "code", "pre") or "data-words" in a
                   or a.get("data-layer") in ("3", "4") for t, a in self.stack):
                return
            self.out.append(data)
    r = Reader()
    r.feed(html)
    return re.sub(r"\s+", " ", "".join(r.out))


def _recorded_stage_names() -> set[str]:
    names = set()
    for run in NAMES:
        manifest = json.loads((RUNS / run / "MANIFEST.json").read_text(encoding="utf-8"))
        for entry in manifest["chain"]:
            receipt = json.loads((RUNS / run / entry["file"]).read_text(encoding="utf-8"))
            names.add(receipt["stage"]["name"])
    return names


def test_no_page_shows_a_raw_internal_value(demo, examined):
    """No enum, key or snake_case value in a page's own words: those are shown in plain words. The
    run's own stage names are the record's, and stay as recorded."""
    _base, root, _keys, _cmp = demo
    stages = _recorded_stage_names()
    pages = sorted((root / "pages").rglob("*.html"))
    examined(len(pages), "pages read as a reader reads them")
    hits = {}
    for page in pages:
        found = sorted({w for w in SNAKE.findall(_reader_text(page.read_text(encoding="utf-8")))
                        if w not in stages})
        if found:
            hits[page.relative_to(root / "pages").as_posix()] = found
    assert not hits, hits


def test_each_not_checked_reason_is_said_once(demo, examined):
    """In "What was checked and what was not", a reason every step shares is said once for the run,
    and only reasons that differ are listed per step."""
    _base, root, keys, _cmp = demo
    #: "What was checked and what was not" is on the run page's "Proof" view.
    html = (root / "pages" / "runs" / keys["query-day2"] / "proof.html").read_text(encoding="utf-8")
    found = re.search(r"<h3>Not checked</h3><ul class=\"plain\">(.*?)</ul>", html, re.S)
    assert found, "no Not checked list"
    items = re.findall(r"<li[^>]*>(.*?)</li>", found.group(1), re.S)
    reasons = [_text(i).split(" — ", 1)[-1] for i in items]
    examined(len(items), "Not checked items")
    assert len(reasons) == len(set(reasons)), reasons
    assert any(_text(i).startswith("Every step — ") for i in items), items
    assert "so none of these steps can be shown to be the record that was made" in _text(found.group(1))


def test_every_step_is_named_by_its_recorded_name_first(demo, examined):
    """Each stage is shown by the name it was recorded under; where the console adds friendlier
    words, they follow the name, never stand in its place, so every step's line reads alike."""
    from onetrace_console.viewer.sentences import STEP_WORDS
    _base, root, keys, _cmp = demo
    html = (root / "pages" / "runs" / keys["query-day2"] / "proof.html").read_text(encoding="utf-8")
    section = _section(html, "checked")
    labels = re.findall(r"step \d+ of \d+ · ([^—\n]+?) —", section)
    recorded = [json.loads((RUNS / "query-day2" / e["file"]).read_text(encoding="utf-8"))["stage"]["name"]
                for e in json.loads((RUNS / "query-day2" / "MANIFEST.json").read_text(encoding="utf-8"))["chain"]]
    examined(len(labels), "step labels")
    assert labels, section[:500]
    for label in labels:
        name = label.split(" (", 1)[0]
        assert name in recorded, (label, recorded)
        if name in STEP_WORDS:
            assert label == f"{name} ({STEP_WORDS[name]})", label
    assert any(n in STEP_WORDS for n in recorded), "the demo run has no stage with friendlier words"


SHORT_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\b")
ISO_TIME = re.compile(r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def test_times_are_short_where_space_is_tight_and_whole_in_tables(demo, examined):
    """Every page says a time one way, YYYY-MM-DD HH:MM:SS UTC, the whole value in its <time>: the
    needs-attention list and the receipt alike. No month by name, anywhere (checked for every page
    above)."""
    _base, root, keys, _cmp = demo
    from html import unescape
    #: Read from the HTML with only the tags taken out: the visible-text tool stands every time in
    #: for `<time>`, which is right for comparing pages and wrong for reading a time's form.
    plain = lambda html: unescape(re.sub(r"<[^>]+>", " ", html))
    home = (root / "pages" / "home.html").read_text(encoding="utf-8")
    attention = plain(re.search(r'<section data-section="needs-attention">(.*?)</section>', home, re.S).group(1))
    receipt = plain((root / "pages" / "runs" / keys["query-day1"] / "receipt.html").read_text(encoding="utf-8"))
    examined(2, "pages with times")
    assert SHORT_TIME.search(attention) and not ISO_TIME.search(attention), attention
    assert SHORT_TIME.search(receipt) and not ISO_TIME.search(receipt), receipt[:400]


def test_a_short_time_is_the_same_instant_in_utc(examined):
    from onetrace_console.words import short_time
    examined(4, "times")
    assert short_time("2026-10-09T00:07:26+00:00") == "2026-10-09 00:07:26 UTC"
    assert short_time("2026-10-09T02:07:26.917+02:00") == "2026-10-09 00:07:26 UTC"
    assert short_time("2026-10-08T16:03:42.917Z") == "2026-10-08 16:03:42 UTC"
    assert short_time("not a time") == "not a time", "a value that is not a time is shown as it is"


def test_the_run_page_banner_says_its_time_in_the_short_form(demo, examined):
    """The green banner is a headline: its time reads YYYY-MM-DD HH:MM:SS UTC, as every page says a
    time, the full value kept in the <time> element."""
    _base, root, keys, _cmp = demo
    html = (root / "pages" / "runs" / keys["query-day1"] / "case.html").read_text(encoding="utf-8")
    banner = re.search(r'checked on (<time [^>]*>[^<]*</time>)', html)
    examined(1, "run page banner")
    assert banner, "the banner's time is not a <time> element"
    when = re.search(r'datetime="([^"]+)"[^>]*>([^<]*)</time>', banner.group(1))
    assert ISO_TIME.match(when.group(1)) and SHORT_TIME.fullmatch(when.group(2)), banner.group(1)
