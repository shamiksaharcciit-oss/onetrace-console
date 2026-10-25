"""One reading of "Records agree" per run, on every page that says or counts it.

A run's rung 1 is decided once, as its own page decides it, and every other page reads that one
state (`records.state`). The PC check of the 0.2.0 candidate found one run read three ways: "held
without its output files required" on the Overview's card, counted as "Verified" in the Pipelines
table and Verdicts by day, and "Not checked" on the Runs page. Checked here, on the demo as a public
console serves it, for every run and every state:

1. the one function is the run page's own rung, run by run;
2. each page and table that says or counts it agrees with that function: the Runs list, the
   receipt page, the Overview's Records agree card and its rung row, the Pipelines table, Verdicts
   by day, All counts, Recent runs, Needs attention first, the comparison pages, the public
   Overview's table of planted runs, and the start-up list the console prints;
3. "Verified", the verifier's own word, is no run-level summary's label;
4. a run whose check held but whose run with the output files required failed contradicts its
   record everywhere (a fixture run, not in the demo).

Each check returns the problems it finds, and each has its sabotage: a planted page or line that
must be named.
"""
from __future__ import annotations

import html
import re
import shutil
from pathlib import Path

import pytest

#: Each state as a count says it in a sentence ("28 of 31 records agree"), and as the receipt page
#: and the comparison pages say it of one run.
COUNTED = {"yes": "records agree", "no": "contradict their record", "couldnt-check": "couldn't check",
           "not-checked": "not checked", "no-verdict": "no verdict recorded"}
RECEIPT = {"yes": "Records agree: yes", "no": "Records agree: no",
           "couldnt-check": "Records agree: couldn't check", "not-checked": "Records agree: not checked"}
#: Needs attention first: the kind each state is listed under (a yes is not listed for it).
ATTENTION = {"no": "contradicts", "couldnt-check": "couldnt-check", "not-checked": "not-checked",
             "no-verdict": "no-verdict"}
#: One run in a comparison's records sentence.
COMPARED = {"yes": "records agree", "no": "contradict", "couldnt-check": "couldn't be checked",
            "not-checked": "not checked", "no-verdict": "no verdict recorded"}


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def reread(run, store):
    """`run` with its "Records agree" read again from its stored report, as the check reads it
    (`checks.agree_state`): for a test that puts a report of its own in place of a check's, so the
    run's reading is the one its report gives, as a real check's always is."""
    import json
    import tempfile
    from dataclasses import replace

    from onetrace_console.checks import agree_state, materialise
    envelope = json.loads(store.get(run.check_report).decode("utf-8")) if run.check_report else None
    with tempfile.TemporaryDirectory() as tmp:
        fields = agree_state(materialise(run, store, Path(tmp) / "run"), envelope)
    return replace(run, **fields)


class Demo:
    def __init__(self, folder: Path, said):
        from onetrace_console import records
        from onetrace_console.store import Store
        self.folder, self.pages = folder, folder / "store" / "pages"
        self.store = Store(folder / "store" / "store")
        self.runs = self.store.runs()
        self.state = {r.key: records.state(r, self.store) for r in self.runs}
        self.why = {r.key: records.why(r, self.store) for r in self.runs}
        self.said = said

    def page(self, rel: str) -> str:
        return (self.pages / rel).read_text(encoding="utf-8")


def _build(folder: Path) -> Demo:
    from onetrace_console.folder_load import build_public
    said, _ = build_public(folder)
    return Demo(folder, said)


@pytest.fixture(scope="module")
def demo(shared_demo) -> Demo:
    from tests.test_checks import _require_installed
    _require_installed()
    return Demo(shared_demo["folder"], shared_demo["said"])


# ------------------------------------------------------------- the checks

def run_page_problems(d: Demo) -> list[str]:
    """Rung 1 on each run's own page is the one function's state; a run not checked because its
    check held without its output files required says so there."""
    out = []
    for r in d.runs:
        if d.state[r.key] == "no-verdict":
            if (d.pages / "runs" / r.key / "case.html").exists():
                out.append(f"{r.run_id}: no verdict recorded, yet it has a run page")
            continue
        #: The ladder is on "What changed", or on "Proof" for a run whose records don't hold up.
        page = d.page(f"runs/{r.key}/case.html") + d.page(f"runs/{r.key}/proof.html")
        rung = re.search(r'data-rung="records-agree"[^>]*data-state="([^"]+)"', page)
        got = rung.group(1) if rung else None
        if got != d.state[r.key]:
            out.append(f"{r.run_id}: its page's rung 1 is {got!r}, the one function {d.state[r.key]!r}")
        if d.why[r.key] and "did not require the run's output files" not in _text(page):
            out.append(f"{r.run_id}: held without its output files required, and its page doesn't say why")
    return out


def runs_list_problems(d: Demo) -> list[str]:
    page = d.page("executions-all.html")
    out = []
    for r in d.runs:
        row = re.search(rf'<tr data-run="[^"]*" data-key="{r.key}">(.*?)</tr>', page, re.S)
        cell = re.search(r'<td[^>]*data-answer="records-agree"[^>]*>.*?data-state="([^"]+)"', row.group(1), re.S) if row else None
        got = cell.group(1) if cell else None
        if got != d.state[r.key]:
            out.append(f"{r.run_id}: the Runs list says {got!r}, the one function {d.state[r.key]!r}")
    return out


def receipt_problems(d: Demo) -> list[str]:
    out = []
    for r in d.runs:
        if d.state[r.key] == "no-verdict":
            continue
        want = RECEIPT[d.state[r.key]] + (f" ({d.why[r.key]})" if d.why[r.key] else "")
        said = re.findall(r"Records agree(?:: [a-z']+(?: [a-z']+)*(?: \([a-z' ]+\))?)?", _text(d.page(f"runs/{r.key}/receipt.html")))
        if said[:1] != [want]:
            out.append(f"{r.run_id}: the receipt page says {said[:1]}, the one function {want!r}")
    return out


def _count(d: Demo, wanted: str, runs=None) -> int:
    return sum(1 for r in (d.runs if runs is None else runs) if d.state[r.key] == wanted)


def card_problems(d: Demo) -> list[str]:
    """The Records agree card: its headline is the yes count; its line gives each state with runs,
    each opening exactly those runs, and names each state at 0."""
    from onetrace_console.records import HELD_WITHOUT, STATES
    home = d.page("home.html")
    card = re.search(r'<div data-card="records-agree">(.*?)</div>', home, re.S).group(1)
    total, out = len(d.runs), []
    head = re.search(r"(\d+) of (\d+) runs? whose records agree", _text(card))
    if not head or int(head.group(1)) != _count(d, "yes"):
        out.append(f"the card's headline {head.group(0) if head else None!r}, the one function {_count(d, 'yes')}")
    line = re.search(r'<p data-line="states">(.*?)</p>', card, re.S)
    links = re.findall(r'<a href="([^"]+)">(\d+) of \d+ ([^<]+)</a>', line.group(1) if line else "")
    got = {html.unescape(w): (href, int(n)) for href, n, w in links}
    zero = _text(re.search(r'<p class="zero" data-line="zero">(.*?)</p>', card, re.S).group(1)) \
        if 'data-line="zero"' in card else ""
    for s in STATES:
        n = _count(d, s)
        words = COUNTED[s]
        if s == "not-checked" and n and all(d.why[r.key] for r in d.runs if d.state[r.key] == s):
            words += f" ({HELD_WITHOUT})"
        if n:
            if got.get(words, (None, None))[1] != n:
                out.append(f"the card gives {words!r} as {got.get(words)}, the one function {n} of {total}")
                continue
            listed = set(re.findall(r'<tr data-run="[^"]*" data-key="([0-9a-f]+)"', d.page(got[words][0])))
            if listed != {r.key for r in d.runs if d.state[r.key] == s}:
                out.append(f"the card's {words!r} opens {len(listed)} runs, not its {n}")
        elif words.lower() not in zero.lower():
            out.append(f"the card doesn't name {words!r} among the states at 0: {zero!r}")
    return out


def rung_row_problems(d: Demo) -> list[str]:
    """What the evidence establishes: rung 1's row, each state's count."""
    row = _text(re.search(r'<tr data-rung="records-agree">(.*?)</tr>', d.page("home.html"), re.S).group(1))
    out = []
    first = re.search(r"(\d+) of \d+", row)
    if not first or int(first.group(1)) != _count(d, "yes"):
        out.append(f"the rung row's lead {first.group(0) if first else None!r}, the one function {_count(d, 'yes')}")
    for s in ("not-checked", "couldnt-check", "no", "no-verdict"):
        m = re.search(rf"(\d+) {re.escape(COUNTED[s])}", row)
        if not m or int(m.group(1)) != _count(d, s):
            out.append(f"the rung row gives {COUNTED[s]!r} as {m.group(1) if m else None}, the one function {_count(d, s)}")
    return out


def _table(section: str) -> tuple[list[str], list[list[str]]]:
    head = [_text(c) for c in re.findall(r"<th>(.*?)</th>", section, re.S)]
    rows = [[_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            for r in re.findall(r"<tr data-(?:pipeline|day)=.*?</tr>", section, re.S)]
    return head, rows


def table_problems(d: Demo, name: str) -> list[str]:
    """The Pipelines table and Verdicts by day: a column per state, under the state's own label,
    each cell the one function's count of that row's runs."""
    from onetrace_console.overview import days, pipelines
    from onetrace_console.records import LABEL, STATES
    home = d.page("home.html")
    section = re.search(rf'<section data-section="{name}">.*?</section>', home, re.S).group(0)
    head, rows = _table(section)
    groups = [p.runs for p in pipelines(d.store)] if name == "pipelines" else [x.runs for x in days(d.store)]
    out = []
    at = {LABEL[s]: head.index(LABEL[s]) if LABEL[s] in head else None for s in STATES}
    out += [f"{name}: no column {label!r} in {head}" for label, i in at.items() if i is None]
    if out or len(rows) != len(groups):
        return out + ([f"{name}: {len(rows)} rows for {len(groups)} groups"] if len(rows) != len(groups) else [])
    for row, runs in zip(rows, groups):
        for s in STATES:
            want = f"{_count(d, s, runs)} of {len(runs)}"
            if row[at[LABEL[s]]] != want:
                out.append(f"{name} {row[0]}: {LABEL[s]!r} reads {row[at[LABEL[s]]]!r}, the one function {want!r}")
    return out


def counts_problems(d: Demo) -> list[str]:
    """All counts: each state's tally, under its slug, counts the one function's runs."""
    page = d.page("counts.html")
    slugs = {"yes": "records-agree", "no": "contradicts", "couldnt-check": "could-not-check",
             "not-checked": "not-checked", "no-verdict": "no-verdict"}
    out = []
    for s, slug in slugs.items():
        m = re.search(rf'href="executions-{slug}\.html"[^>]*>\s*(\d+) runs? of', page)
        if not m or int(m.group(1)) != _count(d, s):
            out.append(f"All counts gives {slug} as {m.group(1) if m else None}, the one function {_count(d, s)}")
    return out


def recent_problems(d: Demo) -> list[str]:
    from onetrace_console import records
    home = d.page("home.html")
    out, by_key = [], {r.key: r for r in d.runs}
    rows = re.findall(r'<tr data-recent="([0-9a-f]+)">(.*?)</tr>', home, re.S)
    for key, row in rows:
        cell = re.search(r'<td data-label="Records">(.*?)</td>', row, re.S)
        want = records.said(by_key[key], d.store)
        if not cell or _text(cell.group(1)) != want:
            out.append(f"Recent runs: {by_key[key].run_id} reads {_text(cell.group(1)) if cell else None!r}, not {want!r}")
    return out + ([] if rows else ["Recent runs: no rows"])


def attention_problems(d: Demo) -> list[str]:
    """Needs attention first, in full: each run whose rung 1 needs attention is listed under its
    state's kind."""
    from onetrace_console.checks import is_preview_not_verified
    from onetrace_console.overview import needs_attention
    listed = {r.key: kind for kind, r in needs_attention(d.store)}
    out = []
    for r in d.runs:
        kind = ATTENTION.get(d.state[r.key])
        if kind == "couldnt-check" and is_preview_not_verified(r):
            continue
        if kind and listed.get(r.key) != kind:
            out.append(f"{r.run_id}: rung 1 {d.state[r.key]!r}, listed as {listed.get(r.key)!r}, not {kind!r}")
    home = d.page("home.html")
    words = re.findall(r'<li data-attention="([a-z-]+)">', home)
    if sorted(words) != sorted(k for k in listed.values())[:len(words)] and len(words) == len(listed):
        out.append(f"the Overview lists {sorted(words)}, needs_attention {sorted(listed.values())}")
    return out


def comparison_problems(d: Demo) -> list[str]:
    """Each comparison whose page summarises its first difference says each run's rung 1."""
    out, seen = [], 0
    for c in d.store.comparisons():
        text = _text(d.page(f"diff/{c.key}.html"))
        if "First difference:" not in text:
            continue
        seen += 1
        for who, key in (("baseline", c.run_a), ("candidate", c.run_b)):
            words = COMPARED[d.state[key]]
            if words not in text:
                out.append(f"comparison {c.key[:12]}: its {who}'s rung 1 is {d.state[key]!r}, "
                           f"and the page doesn't say {words!r}")
    return out + ([] if seen else ["no comparison summarises a first difference"])


def startup_problems(d: Demo) -> list[str]:
    """The start-up list: each run folder's line ends with the one function's words for it."""
    from onetrace_console import records
    by_key = {r.key: r for r in d.runs}
    out, seen = [], 0
    for text, href in d.said:
        m = re.match(r"\s+(\S+)\s+(.+)$", text)
        key = re.fullmatch(r"runs/([0-9a-f]{64})/case\.html", href or "")
        if not m or not key or key.group(1) not in by_key:
            continue
        seen += 1
        want = records.said(by_key[key.group(1)], d.store)
        if m.group(2) != want:
            out.append(f"start-up list: {m.group(1)} reads {m.group(2)!r}, not {want!r}")
    return out + ([] if seen == len(d.runs) else [f"start-up list: {seen} lines for {len(d.runs)} runs"])


#: The run-level summaries: the Overview, All counts, every runs list, and the start-up list.
def verified_problems(d: Demo) -> list[str]:
    out = []
    for p in [d.pages / "home.html", d.pages / "counts.html", *sorted(d.pages.glob("executions-*.html"))]:
        if re.search(r"\bVerified\b", _text(p.read_text(encoding="utf-8"))):
            out.append(f"{p.name} says 'Verified'")
    out += [f"start-up list: {t!r}" for t, _ in d.said if re.search(r"\bVerified\b", t)]
    return out


def planted_table_problems(d: Demo) -> list[str]:
    """The public Overview's table of planted runs: each row's badge is the one function's state,
    in its words, and every run the builder planted has its row."""
    from onetrace_console import demo_store, records
    home = d.page("home.html")
    rows = re.findall(r'<tr data-planted="([0-9a-f]{64})">(.*?)</tr>', home, re.S)
    by_key = {r.key: r for r in d.runs}
    planted = {s.run_id or s.folder for s in demo_store.runs() if demo_store.planted(s)}
    out = []
    if sorted(by_key[k].run_id for k, _ in rows if k in by_key) != sorted(planted):
        out.append(f"{len(rows)} rows in the planted table, the builder planted {len(planted)}")
    for key, row in rows:
        badge = re.search(r'<span data-reading="([^"]+)">(.*?)</span>', row, re.S)
        got = badge.group(1) if badge else None
        if got != d.state.get(key):
            out.append(f"{by_key[key].run_id if key in by_key else key[:12]}: the planted table says {got!r}, "
                       f"its page {d.state.get(key)!r}")
        elif _text(badge.group(2)) != records.said(by_key[key], d.store):
            out.append(f"{by_key[key].run_id}: the planted table's words {_text(badge.group(2))!r}")
    return out


CHECKS = (run_page_problems, runs_list_problems, receipt_problems, card_problems, rung_row_problems,
          lambda d: table_problems(d, "pipelines"), lambda d: table_problems(d, "by-day"),
          counts_problems, recent_problems, attention_problems, comparison_problems,
          startup_problems, verified_problems, planted_table_problems)


# ------------------------------------------------------------- on the demo

def test_the_demo_reads_as_its_table_says(demo, examined):
    """The demo's states, from the one function: the run held without its output files required is
    not checked, and says why."""
    by_id = {r.run_id: r.key for r in demo.runs}
    counts = {s: _count(demo, s) for s in COUNTED}
    examined(len(demo.runs), "runs read")
    assert counts == {"yes": 44, "no": 3, "couldnt-check": 0, "not-checked": 1, "no-verdict": 0}
    key = by_id["p1-16-candidate-set5-no-artifacts"]
    assert (demo.state[key], demo.why[key]) == ("not-checked", "held without its output files required")


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: getattr(c, "__name__", "table"))
def test_every_page_reads_the_one_state(demo, check, examined):
    examined(len(demo.runs), "runs, each on this page or table")
    assert check(demo) == []


def test_pipelines_and_by_day_agree(demo, examined):
    examined(len(demo.runs), "runs counted")
    assert table_problems(demo, "pipelines") == [] and table_problems(demo, "by-day") == []


# ------------------------------------------------------------- sabotages

def _planted(demo: Demo, tmp_path: Path, rel: str, old: str, new: str) -> Demo:
    """A copy of the demo's pages with one page changed: `old` replaced by `new`, exactly once."""
    copy = tmp_path / "demo"
    shutil.copytree(demo.folder, copy)
    page = copy / "store" / "pages" / rel
    text = page.read_text(encoding="utf-8")
    assert text.count(old) >= 1, f"{rel} has no {old!r} to plant over"
    page.write_text(text.replace(old, new, 1), encoding="utf-8")
    return Demo(copy, demo.said)


def _p116(demo: Demo) -> str:
    return next(r.key for r in demo.runs if r.run_id == "p1-16-candidate-set5-no-artifacts")


def test_sabotage_the_runs_list_with_its_own_reading_is_named(demo, tmp_path, examined):
    page = demo.page("executions-all.html")
    row = re.search(rf'<tr data-run="[^"]*" data-key="{_p116(demo)}">.*?</tr>', page, re.S).group(0)
    bad = _planted(demo, tmp_path, "executions-all.html", row,
                   row.replace('data-state="not-checked"', 'data-state="yes"', 1))
    examined(1, "planted row")
    assert any("the Runs list says 'yes'" in p for p in runs_list_problems(bad))


def test_sabotage_a_table_counting_the_check_s_verdict_is_named(demo, tmp_path, examined):
    """The Pipelines table back on the verifier's verdict: P1's 18 of 20 under Records agree."""
    home = demo.page("home.html")
    row = re.search(r'<tr data-pipeline="P1">.*?</tr>', home, re.S).group(0)
    bad = _planted(demo, tmp_path, "home.html", row, row.replace(">17 of 20<", ">18 of 20<", 1))
    examined(1, "planted cell")
    assert any("'Records agree' reads '18 of 20'" in p for p in table_problems(bad, "pipelines"))


def test_sabotage_verified_back_in_a_summary_is_named(demo, tmp_path, examined):
    bad = _planted(demo, tmp_path, "home.html", "<th>Records agree</th>", "<th>Verified</th>")
    examined(1, "planted heading")
    assert "home.html says 'Verified'" in verified_problems(bad)
    said = [(t + "  Verified", h) if i == 1 else (t, h) for i, (t, h) in enumerate(demo.said)]
    assert any("start-up list" in p for p in verified_problems(Demo(demo.folder, said)))


def test_sabotage_the_card_off_the_one_function_is_named(demo, tmp_path, examined):
    home = demo.page("home.html")
    card = re.search(r'<div data-card="records-agree">.*?</div>', home, re.S).group(0)
    n = len(demo.runs)
    new = card.replace(f">1 of {n} not checked", f">0 of {n} not checked", 1)
    assert new != card, "nothing to plant over"
    bad = _planted(demo, tmp_path, "home.html", card, new)
    examined(1, "planted card")
    assert any("not checked" in p for p in card_problems(bad))


def test_sabotage_a_plant_s_state_changed_in_the_planted_table_is_named(demo, tmp_path, examined):
    """One plant's badge changed in the Overview's table: its page reads Contradicts its record."""
    home = demo.page("home.html")
    row = re.search(r'<tr data-planted="[0-9a-f]{64}">.*?</tr>', home, re.S)
    assert row, "no planted table to plant over"
    new = row.group(0).replace('data-reading="no"', 'data-reading="yes"', 1)
    assert new != row.group(0), "the first planted row does not read no"
    bad = _planted(demo, tmp_path, "home.html", row.group(0), new)
    examined(1, "planted row")
    assert any("the planted table says 'yes'" in p for p in planted_table_problems(bad))


def test_sabotage_the_start_up_list_s_own_word_is_named(demo, examined):
    name = "p1-16-candidate-set5-no-artifacts"
    said = [(re.sub(r"^(\s+\S+\s+).*$", r"\1Records agree", t), h) if name in t else (t, h) for t, h in demo.said]
    examined(1, "planted line")
    assert any(name in p for p in startup_problems(Demo(demo.folder, said)))


def test_sabotage_the_receipt_page_s_own_words_are_named(demo, tmp_path, examined):
    rel = f"runs/{_p116(demo)}/receipt.html"
    bad = _planted(demo, tmp_path, rel, "Records agree: not checked", "Records agree: held without")
    examined(1, "planted receipt")
    assert any("receipt page says" in p for p in receipt_problems(bad))


# ------------------------------------------------------------- the latent gap, on a fixture run

@pytest.fixture(scope="module")
def outputs_differ(demo, tmp_path_factory) -> Demo:
    """A run whose check holds but whose run with the output files required fails: one of a demo
    run's output files moved after it was recorded. Not in the demo; delivered with the
    demo's own runs into a store of its own."""
    from onetrace_console import demo_store
    root = tmp_path_factory.mktemp("outputs-differ")
    folder = root / "demo"
    shutil.copytree(demo.folder / demo_store.RUNS_DIRNAME, folder / demo_store.RUNS_DIRNAME)
    shutil.copy(demo.folder / demo_store.TRUST_NAME, folder / demo_store.TRUST_NAME)
    runs = folder / demo_store.RUNS_DIRNAME
    for other in list(runs.iterdir()):
        if other.name not in ("p1-02-baseline-set2", "p1-16-candidate-set5-no-artifacts"):
            shutil.rmtree(other)
    #: Its output files one folder down, in a layout the verifier doesn't recognise: the plain
    #: check leaves them not run and holds; the run with the output files required fails.
    artifacts = runs / "p1-02-baseline-set2" / "artifacts"
    (artifacts / "moved").mkdir()
    for stage in sorted(p for p in artifacts.iterdir() if p.name != "moved"):
        stage.rename(artifacts / "moved" / stage.name)
    from onetrace_console.config import Config
    from onetrace_console.folder_load import announce, load_folder
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    store_root = folder / "store"
    config = Config(public=True, store_root=str(store_root), trust_file=str(folder / demo_store.TRUST_NAME),
                    sign_in={**Config().sign_in, "enabled": False})
    store = Store(store_root / "store")
    loaded = load_folder(runs, store, config)
    _render_startup_pages(store, store_root, config)
    said, _ = announce(runs, loaded, store)
    return Demo(folder, said)


def test_a_check_that_held_whose_outputs_differ_contradicts_its_record_everywhere(outputs_differ, examined):
    d = outputs_differ
    run = next(r for r in d.runs if r.run_id == "p1-02-baseline-set2")
    from onetrace_console.checks import HOLDS
    examined(len(d.runs), "fixture runs")
    assert run.check_verdict == HOLDS, "the fixture's plain check must hold"
    assert d.state[run.key] == "no"
    problems = [p for check in (run_page_problems, runs_list_problems, receipt_problems, rung_row_problems,
                                counts_problems, attention_problems, startup_problems, verified_problems)
                for p in check(d)]
    assert problems == []
    card = _text(re.search(r'<div data-card="records-agree">(.*?)</div>', d.page("home.html"), re.S).group(1))
    #: p1-16 is the one run held without its output files required; the moved run is not.
    assert "1 of 2 contradict their record" in card
    assert "1 of 2 not checked (held without its output files required)" in card
    assert "0 of 2 in the other states: records agree" in card
