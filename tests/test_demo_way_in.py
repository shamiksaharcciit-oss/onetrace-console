"""The public demo's way in: a pipeline whose every run's records agree first, then every run the
demo builder breaks on purpose, each tagged and with its true reading, then all pipelines.

1. The demo builder keeps one line per run it breaks on purpose (`demo_store.PLANTED`), beside the
   code that breaks it: every planted run has a line, and every line names a planted run. A run is
   planted where the builder acts on it after it closed, signs it otherwise than with its trusted
   key, or makes one of its stages fail.
2. On a public demo, the Overview opens on the pipeline with the most runs whose every run's
   records agree (ties by id), with its marks and "n of n records agree", and a link to its page.
3. Then "Then see what onetrace catches": each planted run once, in a table of three columns: Run
   (the run's link), What was done to it (the builder's line), and What its page reads: one badge,
   the run's "Records agree" state (`records.state`) with its mark and its words
   (`records.said`); where the plant is about signing (the builder signs it otherwise than with its
   trusted key, `RunSpec.sign`), the signing result follows, as its own page reads it
   (`pages.run_answers`, in the runs list's words), and on no other row. No row carries a chip, and
   the section says no "Needs attention:". A run whose page reads otherwise than "Records agree"
   never reads "Records agree" here. Under the heading, only the planted runs with at least one
   reading that is not the clean one (records that do not agree, a signer other than Yes, a reason
   to need attention); below it, "Also planted, and not flagged by any check:", a second table with
   the same columns, the planted runs whose every reading is clean. Every planted run is in exactly
   one. At 390 wide each row stacks and nothing scrolls sideways (tools/layout_check.py).
4. Then a link to all pipelines. A local console's Overview has none of this.

Each check is a function returning the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import html
import re

import pytest

DEMO: dict = {}


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    pages = folder / "store" / "pages"
    DEMO.update(store=Store(folder / "store" / "store"), pages=pages,
                home=(pages / "home.html").read_text(encoding="utf-8"))
    return DEMO


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def planted_problems(specs, lines) -> list[str]:
    from onetrace_console.demo_store import planted
    broken = {s.folder for s in specs if planted(s)}
    out = [f"{f}: planted, and no line says what was done" for f in sorted(broken - set(lines))]
    out += [f"{f}: a line, and no planted run" for f in sorted(set(lines) - broken)]
    out += [f"{f}: an empty line" for f, line in lines.items() if not line.strip()]
    return out


def _first(store):
    """The pipeline the rule picks: most runs, every run's records agree, ties by id."""
    from onetrace_console import records
    from onetrace_console.overview import pipelines
    clean = [p for p in pipelines(store) if all(records.state(r, store) == records.YES for r in p.runs)]
    return max(clean, key=lambda p: (len(p.runs), -int(p.label[1:])), default=None)


def first_problems(page: str, store) -> list[str]:
    from onetrace_console.pipeline_pages import count_line, page_href
    want = _first(store)
    m = re.search(r'<section data-section="way-in" data-pipeline="(P\d+)">(.*?)</section>', page, re.S)
    if not m:
        return ["no way in"]
    out = []
    if m.group(1) != want.label:
        out.append(f"opens on {m.group(1)}, the rule picks {want.label}")
    body = m.group(2)
    if count_line(want.runs, store) not in _text(body):
        out.append("its count line is not said")
    if f'href="{page_href(want.label)}"' not in body:
        out.append("no link to its page")
    if page.index('data-section="way-in"') > page.index('data-section="cards"'):
        out.append("the way in is not first")
    return out


def _flagged(run, store) -> bool:
    """At least one reading that is not the clean one, read here from the run's own answers."""
    from onetrace_console import records
    from onetrace_console.overview import attention_kind
    from onetrace_console.pages import run_answers
    return (records.state(run, store) != records.YES or run_answers(run, store)["signed"] != "yes"
            or attention_kind(run, store) is not None)


COLUMNS = ("Run", "What was done to it", "What its page reads")


def _table(page: str, name: str) -> str | None:
    m = re.search(rf'<table class="board" data-group="{name}">(.*?)</table>', page, re.S)
    return m.group(1) if m else None


def _rows(page: str, name: str) -> list[tuple[str, str]]:
    return re.findall(r'<tr data-planted="([0-9a-f]{64})">(.*?)</tr>', _table(page, name) or "", re.S)


def _group(page: str, name: str) -> list[str]:
    return [k for k, _ in _rows(page, name)]


def split_problems(page: str, store) -> list[str]:
    from onetrace_console import demo_store
    from onetrace_console.pipeline_pages import NOT_FLAGGED_HEAD
    by_id = {r.run_id: r for r in store.runs()}
    by_key = {r.key: r for r in store.runs()}
    planted = [by_id[s.run_id or s.folder] for s in demo_store.runs() if demo_store.planted(s)]
    caught, quiet = _group(page, "caught"), _group(page, "not-flagged")
    out = [f"{by_key[k].run_id}: under the heading, and nothing flags it" for k in caught
           if not _flagged(by_key[k], store)]
    out += [f"{by_key[k].run_id}: not flagged, and something flags it" for k in quiet
            if _flagged(by_key[k], store)]
    for run in planted:
        n = caught.count(run.key) + quiet.count(run.key)
        if n != 1:
            out.append(f"{run.run_id}: in the two groups {n} times")
    if bool(quiet) != (NOT_FLAGGED_HEAD in html.unescape(page)):
        out.append("the not-flagged group's words without its runs, or its runs without them")
    return out


def table_problems(page: str) -> list[str]:
    """Each group a table of the three columns; each row its three cells: the run's link, the
    builder's line, the badge first in the last."""
    out = []
    for name in ("caught", "not-flagged"):
        body = _table(page, name)
        if body is None:
            if name == "caught" or 'data-group="not-flagged"' in page:
                out.append(f"the {name} group is not a table")
            continue
        head = re.search(r"<thead>(.*?)</thead>", body, re.S)
        cols = tuple(_text(h) for h in re.findall(r"<th\b[^>]*>(.*?)</th>", head.group(1), re.S)) if head else ()
        if cols != COLUMNS:
            out.append(f"the {name} table's columns are {cols}")
        for key, row in _rows(page, name):
            cells = re.findall(r"<td\b[^>]*>(.*?)</td>", row, re.S)
            if len(cells) != 3:
                out.append(f"{key[:12]}: {len(cells)} cells, not 3")
                continue
            if f'href="runs/{key}/case.html"' not in cells[0] or re.search(r"data-reading|data-signed", cells[0] + cells[1]):
                out.append(f"{key[:12]}: the first two cells are not the run's link and the builder's line")
            if not cells[2].startswith('<span data-reading="') or '<svg class="mark"' not in cells[2]:
                out.append(f"{key[:12]}: the last cell does not start with the badge")
    return out


def noise_problems(page: str) -> list[str]:
    """The section holds no per-row chip and no "Needs attention:"."""
    m = re.search(r'<section data-section="planted">(.*?)</section>', page, re.S)
    if not m:
        return ["no planted runs section"]
    text, out = _text(m.group(1)), []
    if "planted for the demo" in text or 'class="pill' in m.group(1):
        out.append("a planted-for-the-demo chip in the section")
    if "Needs attention:" in text or "data-needs=" in m.group(1):
        out.append("Needs attention: in the section")
    return out


def caught_problems(page: str, store) -> list[str]:
    from onetrace_console import demo_store, records
    from onetrace_console.pages import run_answers
    m = re.search(r'<section data-section="planted">(.*?)</section>', page, re.S)
    if not m:
        return ["no planted runs section"]
    rows = _rows(page, "caught") + _rows(page, "not-flagged")
    by_id = {r.run_id: r for r in store.runs()}
    specs = {s.run_id or s.folder: s for s in demo_store.runs() if demo_store.planted(s)}
    planted = [by_id[i] for i in specs]
    want = [r for r in planted if _flagged(r, store)] + [r for r in planted if not _flagged(r, store)]
    out = []
    if [k for k, _ in rows] != [r.key for r in want]:
        out.append(f"{len(rows)} planted rows, the builder planted {len(want)}")
    for key, body in rows:
        run = next((r for r in want if r.key == key), None)
        if run is None:
            continue
        text, spec = _text(body), specs[run.run_id]
        if demo_store.PLANTED[spec.folder] not in text:
            out.append(f"{run.run_id}: the builder's line is not said")
        said = re.search(r'<span data-reading="([\w-]+)">(.*?)</span>', body, re.S)
        state = records.state(run, store)
        if not said or said.group(1) != state or _text(said.group(2)) != records.said(run, store):
            out.append(f"{run.run_id}: reads {said.groups() if said else None}, its page {state}")
        #: About signing, read from the plant's own data: signed otherwise than with the trusted key.
        signing = spec.sign != "trusted"
        signed = re.findall(r'<span data-signed="([\w-]+)">', body)
        if not signing and signed:
            out.append(f"{run.run_id}: a signing result, on a plant not about signing")
        if signing and signed != [run_answers(run, store)["signed"]]:
            out.append(f"{run.run_id}: signed {signed}, its page {run_answers(run, store)['signed']}")
        if signing and signed and body.index("data-signed=") < body.index("data-reading="):
            out.append(f"{run.run_id}: the signing result before the badge")
        if state != records.YES and "Records agree" in text:
            out.append(f"{run.run_id}: reads Records agree")
    return out


def all_problems(page: str) -> list[str]:
    m = re.search(r'<p data-section="all-pipelines"><a href="#pipeline-cards">', page)
    return [] if m and 'id="pipeline-cards"' in page else ["no link to all pipelines"]


def test_every_planted_run_has_its_line_and_every_line_a_run():
    from onetrace_console import demo_store
    assert planted_problems(demo_store.runs(), demo_store.PLANTED) == []


def test_the_way_in_opens_on_the_pipeline_the_rule_picks(demo):
    assert first_problems(demo["home"], demo["store"]) == []


def test_then_every_planted_run_with_its_true_reading(demo, examined):
    assert caught_problems(demo["home"], demo["store"]) == []
    examined(demo["home"].count("data-planted="), "planted runs")


def test_only_runs_something_flags_are_under_the_heading(demo, examined):
    assert split_problems(demo["home"], demo["store"]) == []
    assert _group(demo["home"], "not-flagged"), "the demo has a planted run nothing flags"
    examined(len(_group(demo["home"], "caught")) + len(_group(demo["home"], "not-flagged")), "planted runs placed")


def test_each_group_is_a_table_of_three_columns(demo, examined):
    assert table_problems(demo["home"]) == []
    examined(demo["home"].count("data-planted="), "planted rows")


def test_no_chip_and_no_needs_attention_in_the_section(demo, examined):
    assert noise_problems(demo["home"]) == []
    examined(1, "planted runs section")


def test_the_signing_result_only_on_the_signing_plants(demo, examined):
    """Read from the plant data: at least one plant about signing, and at least one not."""
    from onetrace_console import demo_store
    signing = {s.sign != "trusted" for s in demo_store.runs() if demo_store.planted(s)}
    assert signing == {True, False}, "the demo has plants about signing and plants not"
    by_id = {r.run_id: r.key for r in demo["store"].runs()}
    want = {by_id[s.run_id or s.folder] for s in demo_store.runs() if demo_store.planted(s) and s.sign != "trusted"}
    rows = _rows(demo["home"], "caught") + _rows(demo["home"], "not-flagged")
    assert {k for k, body in rows if "data-signed=" in body} == want
    assert not [p for p in caught_problems(demo["home"], demo["store"]) if "sign" in p]
    examined(len(rows), "planted rows, each with or without a signing result")


def test_then_a_link_to_all_pipelines(demo):
    assert all_problems(demo["home"]) == []


def test_a_local_console_has_no_way_in(demo):
    from onetrace_console.render import render_home
    local = render_home(demo["store"], generated_at="2026-01-01T00:00:00+00:00")
    for part in ('data-section="way-in"', 'data-section="planted"', "planted for the demo",
                 'data-section="all-pipelines"'):
        assert part not in local, part


# ------------------------------------------------------------------------------- sabotages

def test_sabotage_a_planted_line_dropped_or_an_orphan_line_is_named():
    from onetrace_console import demo_store
    lines = dict(demo_store.PLANTED)
    gone = lines.pop("p7-41-cold-chain-decision-tampered")
    assert any("no line" in p for p in planted_problems(demo_store.runs(), lines))
    lines["p7-41-cold-chain-decision-tampered"] = gone
    lines["p6-36-fill-baseline"] = "Nothing was done to it."
    assert any("no planted run" in p for p in planted_problems(demo_store.runs(), lines))


def test_sabotage_the_wrong_pipeline_first_is_named(demo):
    page = re.sub(r'(data-section="way-in" data-pipeline=")P\d+', r"\1P1", demo["home"], count=1)
    assert any("the rule picks" in p for p in first_problems(page, demo["store"]))


def test_sabotage_a_planted_run_shown_as_records_agree_or_dropped_is_named(demo):
    page = demo["home"]
    shown = re.sub(r'(<span data-reading=")no(">)(?:<svg.*?</svg>)?[^<]*(</span>)', r"\1yes\2Records agree\3",
                   page, count=1, flags=re.S)
    assert shown != page
    assert any("reads" in p for p in caught_problems(shown, demo["store"]))
    dropped = re.sub(r'<tr data-planted="[0-9a-f]{64}">.*?</tr>', "", page, count=1, flags=re.S)
    assert any("planted rows" in p for p in caught_problems(dropped, demo["store"]))


def test_sabotage_an_unsigned_planted_run_shown_as_signed_is_named(demo):
    page = demo["home"].replace('data-signed="unsigned"', 'data-signed="yes"', 1)
    assert page != demo["home"]
    assert any("signed" in p for p in caught_problems(page, demo["store"]))


def _with_reading(row: str, extra: str) -> str:
    """A planted row with `extra` after the last cell's readings."""
    assert row.endswith("</td>"), row[-40:]
    return row[:-len("</td>")] + extra + "</td>"


def test_sabotage_a_signing_result_on_a_plant_not_about_signing_is_named(demo):
    page = demo["home"]
    row = next(body for _, body in _rows(page, "caught") if "data-signed=" not in body)
    bad = page.replace(row, _with_reading(row, ' · <span data-signed="yes">Signed by a known recorder: '
                                               "Yes</span>"), 1)
    assert bad != page
    assert any("not about signing" in p for p in caught_problems(bad, demo["store"]))


def test_sabotage_the_signing_result_dropped_from_a_signing_plant_is_named(demo):
    page = demo["home"]
    bad = re.sub(r' · <span data-signed="[\w-]+">.*?</span>', "", page, count=1, flags=re.S)
    assert bad != page
    assert any("signed" in p for p in caught_problems(bad, demo["store"]))


def test_sabotage_the_chip_or_needs_attention_back_is_named(demo):
    page = demo["home"]
    key, row = _rows(page, "caught")[0]
    chip = page.replace(row, re.sub(r"^(<td\b[^>]*>)", r'\1<span class="pill neu">planted for the demo</span> ',
                                    row), 1)
    assert chip != page and any("chip" in p for p in noise_problems(chip))
    need = page.replace(row, _with_reading(row, ' · <span data-needs="contradicts">Needs attention: '
                                                "Contradicts itself</span>"), 1)
    assert need != page and any("Needs attention" in p for p in noise_problems(need))


def test_sabotage_the_link_to_all_pipelines_dropped_is_named(demo):
    assert all_problems(demo["home"].replace('data-section="all-pipelines"', 'data-section="x"'))


def test_sabotage_a_run_nothing_flags_moved_under_the_heading_is_named(demo):
    page = demo["home"]
    quiet = _table(page, "not-flagged")
    assert quiet, "no not-flagged table to move from"
    row = re.search(r'<tr data-planted="[0-9a-f]{64}">.*?</tr>', quiet, re.S).group(0)
    caught = _table(page, "caught")
    moved = page.replace(row, "", 1).replace(caught, caught.replace("<tbody>", "<tbody>" + row, 1), 1)
    assert any("under the heading, and nothing flags it" in p for p in split_problems(moved, demo["store"]))


def test_sabotage_a_row_of_two_cells_or_a_column_renamed_is_named(demo):
    page = demo["home"]
    joined = re.sub(r'(<tr data-planted="[0-9a-f]{64}"><td\b[^>]*>.*?)</td><td\b[^>]*>', r"\1 ", page,
                    count=1, flags=re.S)
    assert joined != page and any("cells, not 3" in p for p in table_problems(joined))
    renamed = page.replace(">What its page reads<", ">Status<", 1)
    assert renamed != page and any("columns are" in p for p in table_problems(renamed))
