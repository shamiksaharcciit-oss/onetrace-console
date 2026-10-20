"""Each run page and each comparison page in two linked views: "What changed" and "Proof".

1. Both views exist for every run and every comparison -- in the served console's pages and in a
   static export -- each at its own address, "What changed" at the page's own; two plain links
   at the top are the tabs, the current one marked.
2. Every part of the page as drawn is on exactly one of the two views; the page's own head and
   foot, which carry no finding, on both.
3. "What changed" opens, right after the page's head, with one line saying what the records
   establish and a link to "Proof". For a run that contradicts its record (the demo's tampered
   cold-chain run) and one that couldn't be checked, that line is red and says so first, says the
   step-by-step comparison is not shown and why, and links to "Proof". The step-by-step verdicts
   -- the evidence ladder, the graph, the timeline and the changed steps -- are not on "What
   changed" but on "Proof", under a heading saying the rows come from a record that does not hold
   up (or could not be checked). A run whose records agree keeps its ladder on "What changed".
   On such a red run, "What changed" keeps what is said about the record -- "Records agree: No",
   whether it is signed and anchored, and "What could be re-checked" -- and withholds what is read
   from it: the run head's "Ran as approved", its comparison and declined chips and its count of
   declared stages, the answer trail, the case and a declined step, each on "Proof". One line in
   the head says they are not shown, and links to "Proof". A run whose records agree is unchanged.
   The answer trail's command to repeat the check is the one line of it kept: it says nothing read
   from the record's contents, so a red run's "What changed" shows it with "What could be
   re-checked", and no other line of the trail; "Proof" carries the whole trail.
4. Incident pages link the runs they name at their "Proof" view.
5. No script, and the export's scan for requests to another host passes.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from tests.test_compare_unchecked_side import _compared, _load, _not_verified

TAMPERED = "p7-41-cold-chain-decision-tampered"
P1_RUN = "p1-02-baseline-set2"
P7_PAIR = ("p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed")
STEPS = ("ladder", "graph", "timeline", "changed")
#: Read from the record, so withheld from a red run's "What changed" with the steps.
READ_FROM = ("case", "strip")
#: Said about the record, so kept on a red run's "What changed".
KEPT_RUNGS = ("records-agree", "signed", "anchored")
#: The line in the head where a red run's content-derived answers were.
NOT_SHOWN = {"Contradicts its record": "Not shown: this record does not hold up.",
             "Couldn't check": "Not shown: this record could not be checked."}
#: What each red state says on "What changed", and the heading over the rows on "Proof".
REASON = {"Contradicts its record": "the record does not hold up",
          "Couldn't check": "the record could not be checked"}
#: The answer trail's command to repeat the check, as the trail draws it.
REPEAT = re.compile(r'<details data-layer="4"><summary>Repeat the check</summary>.*?</details>', re.S)
#: Its copy on a red run's "What changed", with "What could be re-checked".
FROM_TRAIL = 'data-from="trail"'
HEADING = {"Contradicts its record": "These rows come from a record that does not hold up.",
           "Couldn't check": "These rows come from a record that could not be checked."}


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The public demo, built with every split recorded: (folder, store, [(kind, whole, what, proof)])."""
    from onetrace_console import views
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    seen = []
    real = views.split

    def recording(page, kind, *a, **kw):
        what, proof = real(page, kind, *a, **kw)
        seen.append((kind, page, what, proof))
        return what, proof
    folder = tmp_path_factory.mktemp("views") / "demo"
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(views, "split", recording)
        build_public(folder)
    return folder, Store(folder / "store" / "store"), seen


def _runs(store):
    return {r.run_id: r for r in store.runs()}


def _views_of(page: str) -> list[tuple[str, bool]]:
    nav = re.search(r'<nav data-section="views"[^>]*>(.*?)</nav>', page, re.S)
    return [(_text(a), "aria-current" in a) for a in re.findall(r"<a [^>]*>.*?</a>", nav.group(1))] if nav else []


def _elements(html: str, mark: str) -> list[tuple[int, int]]:
    """(start, end) of each element whose start tag carries `mark`, its own tag's nesting counted."""
    out = []
    for m in re.finditer(r"<([a-z0-9]+)\b[^>]*" + re.escape(mark) + r"[^>]*>", html):
        tag, depth, at = m.group(1), 1, m.end()
        for t in re.finditer(rf"<(/?){tag}\b[^>]*>", html[at:]):
            depth += -1 if t.group(1) else 1
            if depth == 0:
                out.append((m.start(), at + t.end()))
                break
    return out


def without(html: str, mark: str) -> str:
    """`html` without the elements whose start tag carries `mark`."""
    for start, end in reversed(_elements(html, mark)):
        html = html[:start] + html[end:]
    return html


def coverage_problems(kind: str, whole: str, what: str, proof: str) -> list[str]:
    """Each top-level part of the page as drawn on exactly one view, or on both where it is the
    page's own head or foot. Parts drawn alike (two identical lines) are counted: as many on the
    two views together as on the page, or twice as many where they are the page's own."""
    from collections import Counter

    from onetrace_console import views
    is_container = ((lambda t, a: t == "main" and "page" in (a.get("class") or "").split()) if kind == "run"
                    else (lambda t, a: t == "div" and "cp" in (a.get("class") or "").split()))
    both = (views.RUN_BOTH if kind == "run" else views.DIFF_BOTH)

    def plain(html: str) -> str:
        #: An in-page link may point at the other view's file: compared without the file. The
        #: run head is on both views; on a red run's "What changed" without what is read from the
        #: record, which its own test finds on "Proof", and with the line said in its place.
        html = without(without(without(html, 'data-from="contents"'), 'data-withheld="true"'), FROM_TRAIL)
        return re.sub(r'href="[^"#]*#', 'href="#', html)
    _inner, items = views.parts(whole, is_container)
    wanted: Counter = Counter()
    names = {}
    for n, part in enumerate(items):
        if views.key(part).startswith("#"):
            continue  # an empty anchor, which goes with its section
        html = plain(whole[part.start:part.end])
        shared = (views.key(part) in both or part.tag == "footer"
                  or (part.tag == "h1" and n == next(i for i, x in enumerate(items) if x.tag == "h1")))
        wanted[html] += 2 if shared else 1
        names[html] = views.key(part)
    out = []
    for html, n in wanted.items():
        found = plain(what).count(html) + plain(proof).count(html)
        if found != n:
            out.append(f"{names[html]} on the views {found} times, not {n}")
    return out


# ------------------------------------------------------------------ 1. both views, the default

def test_every_run_and_comparison_has_both_views(built, examined):
    folder, store, _seen = built
    pages = folder / "store" / "pages"
    runs, comparisons = store.runs(), store.comparisons()
    examined(len(runs) + len(comparisons), "runs and comparisons")
    for run in runs:
        what = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
        proof = (pages / "runs" / run.key / "proof.html").read_text(encoding="utf-8")
        assert _views_of(what) == [("What changed", True), ("Proof", False)], run.run_id
        assert _views_of(proof) == [("What changed", False), ("Proof", True)], run.run_id
    for c in comparisons:
        what = (pages / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
        proof = (pages / "diff" / f"{c.key}-proof.html").read_text(encoding="utf-8")
        assert _views_of(what) == [("What changed", True), ("Proof", False)], c.key
        assert _views_of(proof) == [("What changed", False), ("Proof", True)], c.key
        assert 'href="' + c.key + '-proof.html"' in what


def test_the_tabs_are_plain_links(built, examined):
    folder, store, _seen = built
    page = (folder / "store" / "pages" / "runs" / _runs(store)[P1_RUN].key / "case.html").read_text(encoding="utf-8")
    nav = re.search(r'<nav data-section="views"[^>]*>.*?</nav>', page, re.S).group(0)
    examined(1, "tabs")
    assert "<script" not in nav and "onclick" not in nav and "<button" not in nav
    assert re.findall(r'href="([^"]+)"', nav) == ["case.html", "proof.html"]


# ------------------------------------------------------------------ 2. every part on one view

def test_every_part_is_on_exactly_one_view(built, examined):
    _folder, _store, seen = built
    examined(len(seen), "pages split")
    assert {kind for kind, *_ in seen} == {"run", "diff"}
    problems = {}
    for kind, whole, what, proof in seen:
        found = coverage_problems(kind, whole, what, proof)
        if found:
            problems.setdefault(kind, []).extend(found)
    assert problems == {}


# ------------------------------------------------------------------ 3. the line, red and withheld

def _line(page: str):
    return re.search(r'<p data-section="integrity" data-tone="([a-z]+)">(.*?)</p>', page, re.S)


def withheld_problems(what: str, proof: str, lead: str) -> list[str]:
    out = []
    line = _line(what)
    if line is None or line.group(1) != "bad":
        out.append("no red line")
    elif not _text(line.group(2)).startswith(lead):
        out.append(f"the line does not say it first: {_text(line.group(2))[:80]}")
    elif 'href="proof.html"' not in line.group(2):
        out.append("no link to Proof")
    elif f"The step-by-step comparison is not shown on this view: {REASON[lead]}." not in _text(line.group(2)):
        out.append("the line does not say the comparison is withheld, and why")
    heading = re.search(r'<h2 data-section="withheld"[^>]*>(.*?)</h2>', proof, re.S)
    if heading is None or _text(heading.group(1)) != HEADING[lead]:
        out.append("no heading over the rows on Proof")
    for step in STEPS:
        if f'data-section="{step}"' in what:
            out.append(f"{step} shown on What changed")
        if f'data-section="{step}"' not in proof:
            out.append(f"{step} not on Proof")
    if "here, not on What changed" not in _text(proof):
        out.append("Proof does not say why they are there")
    return out


def test_the_tampered_run_s_line_is_red_and_its_verdicts_withheld(built, examined):
    folder, store, _seen = built
    base = folder / "store" / "pages" / "runs" / _runs(store)[TAMPERED].key
    what, proof = ((base / n).read_text(encoding="utf-8") for n in ("case.html", "proof.html"))
    examined(1, "run")
    assert withheld_problems(what, proof, "Contradicts its record") == []


def test_a_run_that_couldn_t_be_checked_is_red_and_withheld(tmp_path, examined):
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1"})
    run = _not_verified(runs["day-1"], store)
    pages = render_execution(run, store, generated_at="2026-01-01T00:00:00+00:00").pages
    examined(1, "run")
    assert withheld_problems(pages[CASE], pages[RUN_PROOF], "Couldn't check") == []


def _head(page: str) -> str:
    return re.search(r'<section data-section="run-head">.*?</nav></section>', page, re.S).group(0)


def kept_problems(whole: str, what: str, proof: str, lead: str) -> list[str]:
    """A red run's "What changed": what is said about the record kept, what is read from it
    withheld, each withheld element on "Proof", and one line in the head where they were."""
    out = []
    head = _head(what)
    rungs = dict(re.findall(r'<li data-head-rung="([^"]+)" data-state="([^"]+)"', head))
    #: "Records agree: No" on a run that contradicts its record; otherwise the rung as Proof gives it
    #: (the couldn't-check stand-in changes the stored state, not the report its rung is read from).
    on_proof = dict(re.findall(r'<li data-head-rung="([^"]+)" data-state="([^"]+)"', _head(proof)))
    want = "no" if lead == "Contradicts its record" else on_proof.get("records-agree")
    if rungs.get("records-agree") != want or want is None:
        out.append(f"Records agree not kept as {want}: {rungs.get('records-agree')}")
    out += [f"{k} not kept" for k in KEPT_RUNGS if k not in rungs]
    out += [f"{k} shown on What changed" for k in rungs if k not in KEPT_RUNGS]
    if 'data-from="contents"' in what:
        out.append("an answer read from the record shown on What changed")
    for start, end in _elements(whole, 'data-from="contents"'):
        if whole[start:end] not in proof:
            out.append(f"not on Proof: {_text(whole[start:end])[:60]}")
    line = re.findall(r'<p [^>]*data-withheld="true"[^>]*>(.*?)</p>', head, re.S)
    if len(line) != 1 or not _text(line[0]).startswith(NOT_SHOWN[lead]) or 'href="proof.html"' not in line[0]:
        out.append(f"not one line saying what is not shown, with the link to Proof: {line}")
    for part in READ_FROM:
        if re.search(rf'<section (data-section|class)="{part}\b', what):
            out.append(f"{part} shown on What changed")
        if not re.search(rf'<section (data-section|class)="{part}\b', proof):
            out.append(f"{part} not on Proof")
    if 'data-section="reproduce"' not in what:
        out.append("What could be re-checked not kept")
    return out


def test_a_red_run_s_what_changed_keeps_what_is_said_about_its_record(built, tmp_path, examined):
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    _folder, _store, seen = built
    #: As drawn: the whole page, both views.
    red = [(w, a, p) for kind, w, a, p in seen if kind == "run" and 'data-tone="bad"' in a
           and 'data-section="withheld"' in p]
    _f, store, runs = _load(tmp_path, {"day-1": "day-1"})
    run = _not_verified(runs["day-1"], store)
    pages = render_execution(run, store, generated_at="2026-01-01T00:00:00+00:00").pages
    examined(len(red) + 1, "red runs")
    assert red
    for whole, what, proof in red:
        assert kept_problems(whole, what, proof, "Contradicts its record") == []
    assert kept_problems(pages[CASE] + pages[RUN_PROOF], pages[CASE], pages[RUN_PROOF], "Couldn't check") == []


def _trail(page: str) -> str | None:
    m = re.search(r'<section class="strip.*?</section>', page, re.S)
    return m.group(0) if m else None


def repeat_problems(what: str, proof: str, whole: str | None = None) -> list[str]:
    """A red run's "What changed": the answer trail's command, with "What could be re-checked", and
    no other line of the trail; "Proof": the whole trail."""
    out = []
    trail = _trail(proof)
    command = REPEAT.search(trail) if trail else None
    if command is None:
        return ["no answer trail with its command on Proof"]
    if whole is not None and _trail(whole) != trail:
        out.append("the answer trail on Proof is not the trail as drawn")
    reproduce = re.search(r'<section data-section="reproduce">.*?</section>', what, re.S)
    copies = [what[a:b] for a, b in _elements(what, FROM_TRAIL)]
    if len(copies) != 1:
        out.append(f"the command shown {len(copies)} times on What changed, not once")
    elif reproduce is None or copies[0] not in reproduce.group(0):
        out.append("the command is not with What could be re-checked")
    elif copies[0].replace(" " + FROM_TRAIL, "", 1) != command.group(0):
        out.append("the command on What changed is not the trail's")
    rest = _text(REPEAT.sub("", trail[trail.index(">") + 1:-len("</section>")]))
    lines = [_text(x) for x in re.findall(r'<(?:div class="lead"|p class="beside"|pre data-layer="3")[^>]*>(.*?)'
                                          r'</(?:div|p|pre)>', trail, re.S)]
    if not lines or " ".join(lines) != rest:
        out.append("the trail's other lines were not all read")
    out += [f"a line of the trail on What changed: {line[:60]}" for line in lines if line in _text(what)]
    return out


def test_a_red_run_s_what_changed_keeps_the_trail_s_command_and_no_other_line(built, tmp_path, examined):
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    _folder, _store, seen = built
    red = [(w, a, p) for kind, w, a, p in seen if kind == "run" and 'data-tone="bad"' in a
           and 'data-section="withheld"' in p]
    _f, store, runs = _load(tmp_path, {"day-1": "day-1"})
    run = _not_verified(runs["day-1"], store)
    pages = render_execution(run, store, generated_at="2026-01-01T00:00:00+00:00").pages
    examined(len(red) + 1, "red runs")
    assert red
    for whole, what, proof in red:
        assert repeat_problems(what, proof, whole) == []
    assert repeat_problems(pages[CASE], pages[RUN_PROOF]) == []


def test_a_run_whose_records_agree_shows_the_command_once_in_its_trail(built, examined):
    _folder, _store, seen = built
    green = [(w, a) for kind, w, a, p in seen if kind == "run" and 'data-tone="ok"' in a]
    examined(len(green), "runs whose records agree")
    assert green
    for whole, what in green:
        assert FROM_TRAIL not in what
        assert _trail(what) == _trail(whole) and REPEAT.search(_trail(what))


def test_a_red_run_s_comparison_and_declined_chips_are_on_proof_only(built, examined):
    """The demo's red run has neither chip: its page, with the chips of runs that have them, split as red."""
    from onetrace_console import views
    _folder, _store, seen = built
    whole = next(w for kind, w, a, p in seen if kind == "run" and 'data-tone="bad"' in a
                 and 'data-section="withheld"' in p)
    found = {}
    for kind, w, _a, _p in seen:
        for start, end in _elements(w, 'class="chips"') if kind == "run" else ():
            found.setdefault("declined" if "data-declined" in w[start:end] else "comparison", w[start:end])
    chips = "".join(found.values())
    planted = re.sub(r"(</h1>)", lambda m: m.group(1) + chips, whole, count=1)
    what, proof = views.split(planted, "run", "case.html", "proof.html", views.RUN_SAID["no"], "no")
    examined(len(found), "chips planted")
    assert set(found) == {"declined", "comparison"} and chips not in whole and chips in planted
    assert chips in proof and 'class="chips"' not in what and 'class="pill' not in _head(what).split("<ul")[0]
    assert kept_problems(planted, what, proof, "Contradicts its record") == []


def test_a_run_whose_records_agree_keeps_its_head_whole(built, examined):
    _folder, _store, seen = built
    green = [(w, a) for kind, w, a, p in seen if kind == "run" and 'data-tone="ok"' in a]
    examined(len(green), "runs whose records agree")
    assert any('class="chips"' in w for w, _a in green)
    for whole, what in green:
        assert _head(what) == _head(whole)
        assert 'data-withheld' not in what
        assert '<section data-section="case">' in what and '<section class="strip' in what


def test_a_run_whose_records_agree_has_a_plain_line_and_its_verdicts(built, examined):
    folder, store, _seen = built
    base = folder / "store" / "pages" / "runs" / _runs(store)[P1_RUN].key
    what = (base / "case.html").read_text(encoding="utf-8")
    examined(1, "run")
    line = _line(what)
    assert line is not None and line.group(1) == "ok" and _text(line.group(2)).startswith("Records agree")
    assert 'data-section="timeline"' in what and 'data-section="ladder"' in what
    assert 'data-section="checked"' not in what


def test_a_comparison_with_an_unchecked_run_withholds_its_verdicts(tmp_path, examined):
    from onetrace_console.serve import _render_diff_page
    _folder, store, runs = _load(tmp_path, {"a": "day-1", "b": "day-2"})
    _not_verified(runs["b"], store)
    c = _compared(store, store.get_run(runs["a"].key), store.get_run(runs["b"].key))
    _render_diff_page(c, store, tmp_path)
    what = (tmp_path / "pages" / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
    proof = (tmp_path / "pages" / "diff" / f"{c.key}-proof.html").read_text(encoding="utf-8")
    examined(1, "comparison")
    line = _line(what)
    assert line is not None and line.group(1) == "bad"
    assert 'data-section="first-difference"' not in what and 'data-section="text-diff"' not in what


# ------------------------------------------------------------------ 4. incidents land on Proof

def test_incident_pages_link_runs_at_their_proof_view(built, examined):
    folder, _store, _seen = built
    pages = folder / "store" / "pages"
    found = [(p, href) for p in [pages / "incidents.html", *(pages / "incidents").glob("*.html")]
             for href in re.findall(r'href="([^"]*runs/[0-9a-f]{64}/[a-z]+\.html)"', p.read_text(encoding="utf-8"))]
    examined(len(found), "run links on incident pages")
    assert found
    for page, href in found:
        assert href.endswith("/proof.html"), (page.name, href)
        assert (page.parent / href).resolve().is_file(), href


# ------------------------------------------------------------------ 1 and 5, in a static export

def test_both_views_are_in_a_static_export_and_its_scan_passes(built, tmp_path, examined):
    from onetrace_console.export_static import export, external_requests
    folder, store, _seen = built
    ids = {r.run_id: r.key for r in store.runs()}
    keys = [ids[n] for n in (TAMPERED, *P7_PAIR)]
    out = tmp_path / "export"
    written = export(folder / "store", keys, out)
    pair = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (ids[P7_PAIR[0]], ids[P7_PAIR[1]]))
    examined(len(keys) + 1, "runs and the comparison")
    for k in keys:
        assert f"runs/{k}/case.html" in written and f"runs/{k}/proof.html" in written
    assert f"diff/{pair.key}.html" in written and f"diff/{pair.key}-proof.html" in written
    assert external_requests(out) == []


# ------------------------------------------------------------------ sabotages

def test_sabotage_a_part_on_both_or_neither_view_is_named(built, examined):
    _folder, _store, seen = built
    kind, whole, what, proof = next(s for s in seen if s[0] == "run")
    checked = re.search(r'<section data-section="checked">.*?</section>', proof, re.S).group(0)
    examined(2, "planted views")
    assert coverage_problems(kind, whole, what.replace("</footer>", checked + "</footer>", 1), proof)
    assert coverage_problems(kind, whole, what, proof.replace(checked, "", 1))


def test_sabotage_verdicts_left_on_what_changed_are_named(built, examined):
    folder, store, _seen = built
    base = folder / "store" / "pages" / "runs" / _runs(store)[TAMPERED].key
    what, proof = ((base / n).read_text(encoding="utf-8") for n in ("case.html", "proof.html"))
    timeline = re.search(r'<section data-section="timeline">.*?</section>', proof, re.S).group(0)
    ladder = re.search(r'<section data-section="ladder">.*?</section>', proof, re.S).group(0)
    examined(3, "planted views")
    assert withheld_problems(what + timeline, proof, "Contradicts its record")
    assert any("ladder shown on What changed" in p
               for p in withheld_problems(what.replace("</footer>", ladder + "</footer>", 1), proof,
                                          "Contradicts its record"))
    assert withheld_problems(what.replace('data-tone="bad"', 'data-tone="ok"'), proof, "Contradicts its record")


def test_sabotage_an_answer_read_from_the_record_on_what_changed_is_named(built, examined):
    folder, store, seen = built
    whole, what, proof = next((w, a, p) for kind, w, a, p in seen if kind == "run" and 'data-tone="bad"' in a
                              and 'data-section="withheld"' in p)
    approved = re.search(r'<li data-head-rung="approved".*?</li>', proof, re.S).group(0)
    strip = proof[slice(*_elements(proof, 'class="strip')[0])]
    examined(5, "planted views")
    assert any("approved shown" in p for p in kept_problems(
        whole, what.replace('<li data-head-rung="signed"', approved + '<li data-head-rung="signed"', 1), proof,
        "Contradicts its record"))
    assert any("not kept" in p for p in kept_problems(
        whole, re.sub(r'<li data-head-rung="signed".*?</li>', "", what, count=1, flags=re.S), proof,
        "Contradicts its record"))
    assert any("not one line" in p for p in kept_problems(
        whole, without(what, 'data-withheld="true"'), proof, "Contradicts its record"))
    assert any("reproduce" in p or "re-checked" in p for p in kept_problems(
        whole, without(what, 'data-section="reproduce"'), proof, "Contradicts its record"))
    assert any("strip shown" in p for p in kept_problems(
        whole, what.replace("</footer>", strip + "</footer>", 1), proof, "Contradicts its record"))


def test_sabotage_the_trail_s_command_dropped_or_another_line_shown_is_named(built, examined):
    _folder, _store, seen = built
    whole, what, proof = next((w, a, p) for kind, w, a, p in seen if kind == "run" and 'data-tone="bad"' in a
                              and 'data-section="withheld"' in p)
    lead = re.search(r'<div class="lead">.*?</div>', _trail(proof), re.S).group(0)
    examined(3, "planted views")
    assert any("shown 0 times" in p for p in repeat_problems(without(what, FROM_TRAIL), proof, whole))
    assert any("a line of the trail" in p
               for p in repeat_problems(what.replace("</footer>", lead + "</footer>", 1), proof, whole))
    assert any("not the trail as drawn" in p
               for p in repeat_problems(what, proof.replace(lead, "", 1), whole))
