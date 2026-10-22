"""A stage page as the console draws it: crumbs back to its run, its title, the stage's instrument as
its receipt records it, a neutral notice saying what is shown, the inputs as a table beside the
outputs, and a tab for each output where there is more than one.

Every stage page of the public demo is held to its own receipt: each input row's "Recorded as" is
the receipt's trust class, word for word, and never a route the receipt doesn't record; the
instrument line is the receipt's instrument, its configuration's fingerprint whole; and each tab
opens an output the page carries. Each check has its sabotage.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pytest


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    return Store(folder / "store" / "store"), folder / "store" / "pages", folder / "runs"


def _receipts(run, store) -> dict[str, dict]:
    """{manifest index: receipt}, read from the stored run."""
    from onetrace_console.stage_pages import _steps
    return {s["index"]: s["receipt"] for s in _steps(run, store)}


def stage_problems(page: str, receipt: dict, run_id: str) -> list[str]:
    from onetrace_console.stage_pages import INPUT_COLUMNS, SHOWN
    out = []
    stage = receipt["stage"]["name"]
    if f'<a href="case.html"><span class="mono" data-words="record">{run_id}' not in page:
        out.append("crumbs")
    h1 = _text(re.search(r"<h1>(.*?)</h1>", page, re.S).group(1))
    if h1 != f"Stage {stage} · inputs and outputs":
        out.append(f"title {h1!r}")
    banner = re.search(r'<p data-section="banner"( class="notice")?>(.*?)</p>', page, re.S)
    if banner is None or not banner.group(1) or not _text(banner.group(2)).startswith(SHOWN):
        out.append("notice")
    inputs = [i for i in receipt.get("inputs") or [] if isinstance(i, dict)]
    if inputs:
        head = re.search(r'<table class="board" data-section="inputs-table"><thead><tr>(.*?)</tr>', page, re.S)
        if head is None or re.findall(r"<th>(.*?)</th>", head.group(1)) != [
                c.replace("'", "&#x27;") for c in INPUT_COLUMNS]:
            out.append("columns")
    for item in inputs:
        row = re.search(rf'<tr data-input="{re.escape(item["name"])}">(.*?)</tr>', page, re.S)
        if row is None:
            out.append(f"no row for {item['name']}")
            continue
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(1), re.S)
        #: "Recorded as": the recorded name (or, for a matched receipt, its stage's link) and the
        #: trust class, both the receipt's own words, and nothing else.
        trust = re.search(r"<span data-trust-class>(.*?)</span>", cells[0], re.S)
        if trust is None or _text(trust.group(1)) != item.get("trust_class", ""):
            out.append(f"{item['name']}: recorded as {_text(cells[0])!r}")
        named_as = re.search(r'data-recorded-name="([^"]*)"', cells[0])
        if named_as is None or unescape(named_as.group(1)) != item["name"]:
            out.append(f"{item['name']}: its recorded name is not the receipt's")
        if item.get("digest") and item["digest"] not in cells[1]:
            out.append(f"{item['name']}: fingerprint not whole")
    inst = receipt.get("instrument") or {}
    line = re.search(r'<div data-section="instrument">(.*?)</div>', page, re.S)
    if isinstance(inst.get("id"), str):
        said = _text(line.group(1)) if line else ""
        for field in ("id", "kind", "version", "config_digest"):
            if isinstance(inst.get(field), str) and inst[field] not in said:
                out.append(f"instrument {field}")
    nav = re.search(r'<nav class="tabs" aria-label="This stage(?:\'|&#x27;)s outputs">(.*?)</nav>', page, re.S)
    tabs = re.findall(r'<a href="([^"]*)"', nav.group(1)) if nav else []
    for tab in tabs:
        if not tab.startswith("#") or f'<span id="{tab[1:]}"></span>' not in page:
            out.append(f"tab {tab} opens nothing")
    outputs = [o for o in receipt.get("outputs") or [] if isinstance(o, dict)]
    if len(outputs) > 1 and len(tabs) != len(outputs):
        out.append("a tab per output")
    return out


def test_every_stage_page_is_held_to_its_receipt(demo, examined):
    store, pages, _ = demo
    n = 0
    for run in store.runs():
        for index, receipt in _receipts(run, store).items():
            page = (pages / "runs" / run.key / f"stage-{index}.html").read_text(encoding="utf-8")
            assert stage_problems(page, receipt, run.run_id) == [], (run.run_id, index)
            n += 1
    examined(n, "stage pages")
    assert n > 100


def test_the_demo_keeps_externally_sourced_inputs_only_as_its_builder_s_example_data(demo, examined):
    """The demo's own data decides what a public console could show as kept text: a step lists an
    externally sourced input as kept only in a pipeline the builder marks as example data, and
    each such input's digest is one of the builder's own invented inputs. (The rule that a public
    console never shows such text otherwise is held in tests/test_kept_inputs.py and
    tests/test_demo_example_inputs.py; this holds the data beside it.)"""
    from onetrace_console.demo_store import EXAMPLE_DATA, example_input_digests, runs as specs
    from onetrace_console.kept_inputs import EXTERNALLY_SOURCED, external_kept, listed
    from onetrace_console.stage_pages import _steps
    store, _, _ = demo
    runs = store.runs()
    marked = {s.run_id or s.folder for s in specs() if s.pipeline in EXAMPLE_DATA}
    allowed = example_input_digests()
    examined(len(runs), "demo runs")
    assert {run.run_id for run in runs if external_kept(_steps(run, store))} <= marked
    for run in runs:
        for step in _steps(run, store):
            names = set(listed(step["receipt"]))
            for i in step["receipt"].get("inputs") or []:
                if i.get("name") in names and i.get("trust_class") == EXTERNALLY_SOURCED:
                    assert i.get("digest") in allowed, (run.run_id, i.get("name"))
    assert any(external_kept(_steps(run, store)) for run in runs), "the demo keeps no example input"


def test_sabotage_a_stage_page_that_strays_from_its_receipt_is_named(demo, examined):
    store, pages, _ = demo
    run = store.runs()[0]
    index, receipt = next((i, r) for i, r in _receipts(run, store).items()
                          if any(not str(x.get("name", "")).startswith("receipt:")
                                 for x in r.get("inputs") or []))
    page = (pages / "runs" / run.key / f"stage-{index}.html").read_text(encoding="utf-8")
    item = next(x for x in receipt["inputs"] if not x["name"].startswith("receipt:"))
    row = re.search(rf'<tr data-input="{re.escape(item["name"])}">.*?</tr>', page, re.S).group(0)
    routed = page.replace(row, row.replace(f"<span data-trust-class>{item['trust_class']}</span>",
                                           "<span data-trust-class>load_docs · this run</span>", 1), 1)
    short = receipt["instrument"]["config_digest"]
    shortened = page.replace(short, short[:19] + "…", 1)
    amber = page.replace('<p data-section="banner" class="notice">', '<p data-section="banner">', 1)
    tab = page.replace("</h1>", '</h1><nav class="tabs" aria-label="This stage&#x27;s outputs">'
                       '<a href="#output-9">x</a></nav>', 1)
    examined(4, "planted pages")
    for planted in (routed, shortened, amber, tab):
        assert planted != page
    assert any("recorded as" in p for p in stage_problems(routed, receipt, run.run_id))
    assert "instrument config_digest" in stage_problems(shortened, receipt, run.run_id)
    assert "notice" in stage_problems(amber, receipt, run.run_id)
    assert "tab #output-9 opens nothing" in stage_problems(tab, receipt, run.run_id)


def test_the_notice_is_neutral_by_the_one_colour_rule(examined):
    """The notice says what is shown; it is no state, so it takes no state's colour. The amber
    belongs to "couldn't check" (`tones.py`)."""
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    rule = re.search(r"\.cp>\[data-section=banner\]\.notice\{([^}]*)\}", css)
    examined(1, "rule")
    assert rule and "--cc-" not in rule.group(1) and "--neu-bg" in rule.group(1)


def test_a_stage_with_two_outputs_has_a_tab_for_each(tmp_path, examined):
    """The demo's stages each write one output, so a run made here writes two."""
    from onetrace.emit import Instrument, Recorder

    from tests.test_times_and_words import _console
    out = tmp_path / "runs" / "two"
    out.mkdir(parents=True)
    rec = Recorder(str(out), run_id="two-outputs", declared_stages=["write"],
                   manifest=Path(__file__), policy="fail-closed", anchor_reason="a test record")
    rec.run_node("write", None, Instrument("writer", "tool", "1.0.0", {"k": "v"}),
                 lambda ctx: (ctx.write("index.json", b'{"n": 2}', "application/json"),
                              ctx.write("text.txt", b"two outputs", "text/plain"))[1])
    rec.close()
    store, pages, _ = _console(tmp_path, tmp_path / "runs")
    run = store.runs()[0]
    (index, receipt), = _receipts(run, store).items()
    page = (pages / "runs" / run.key / f"stage-{index}.html").read_text(encoding="utf-8")
    examined(1, "stage page with two outputs")
    assert len(receipt["outputs"]) == 2
    assert stage_problems(page, receipt, run.run_id) == []
    nav = re.search(r'<nav class="tabs" aria-label="This stage(?:\'|&#x27;)s outputs">(.*?)</nav>', page, re.S)
    assert _text(nav.group(1)) == "index.json text.txt"


def chunk_problems(page: str, chunks: list[dict] | None) -> list[str]:
    """The chunk view against the verified chunk list it comes from (None: the page must have none)."""
    from onetrace_console.stage_pages import CHUNKS_SHOWN
    has = 'data-chunks="index"' in page
    if chunks is None:
        return ["a chunk view on an output that is not a chunk list"] if has else []
    if not has:
        return ["no chunk view"]
    out = []
    docs = len({c.get("doc") for c in chunks if c.get("doc")})
    counts = _text(re.search(r"<p data-chunk-counts>(.*?)</p>", page).group(1))
    if counts != f"{len(chunks)} chunks · {docs} documents":
        out.append(f"counts {counts!r}")
    shown = re.findall(r'<details data-chunk="([^"]+)"><summary[^>]*>.*?</summary><pre data-content="verified">(.*?)</pre>',
                       page, re.S)
    want = chunks[:CHUNKS_SHOWN]
    if [unescape(i) for i, _ in shown] != [c["id"] for c in want]:
        out.append("chunk ids not in the output's order")
    elif any(unescape(t) != c["text"] for (_, t), c in zip(shown, want)):
        out.append("a chunk's text is not its own")
    nav = re.search(r'<nav class="tabs" aria-label="This output(?:\'|&#x27;)s views">(.*?)</nav>', page, re.S)
    for tab in re.findall(r'<a href="#([^"]+)"', nav.group(1) if nav else ""):
        if f'<span id="{tab}"></span>' not in page:
            out.append(f"tab {tab} opens nothing")
    if not nav:
        out.append("no tabs")
    return out


def test_only_the_chunk_list_gets_the_chunk_view(demo, examined):
    from onetrace_console.stage_pages import _artifact_path, _files, _read, _steps, _verified
    store, pages, _ = demo
    views = others = 0
    for run in store.runs():
        files = _files(run, store)
        for step in _steps(run, store):
            page = (pages / "runs" / run.key / f"stage-{step['index']}.html").read_text(encoding="utf-8")
            chunks = None
            for o in step["receipt"].get("outputs") or []:
                blob = _read(files, store, _artifact_path(step["file"], o["name"]))
                if blob is not None and _verified(blob, o["digest"]) and o["name"] == "chunks.json":
                    chunks = json.loads(blob)["chunks"]
            assert chunk_problems(page, chunks) == [], (run.run_id, step["index"])
            views += chunks is not None
            others += chunks is None
    examined(views, "chunk views")
    assert views >= 12 and others > 100


def test_sabotage_a_wrong_chunk_view_is_named(demo, examined):
    from onetrace_console.stage_pages import _artifact_path, _files, _read, _steps
    store, pages, _ = demo
    run = next(r for r in store.runs() if r.run_id == "p1-01-baseline-set1")
    step = next(s for s in _steps(run, store) if s["receipt"]["stage"]["name"] == "split")
    page = (pages / "runs" / run.key / f"stage-{step['index']}.html").read_text(encoding="utf-8")
    chunks = json.loads(_read(_files(run, store), store, _artifact_path(step["file"], "chunks.json")))["chunks"]
    other = (pages / "runs" / run.key / "stage-1.html").read_text(encoding="utf-8")
    planted = {
        "a wrong count": page.replace(f"{len(chunks)} chunks", f"{len(chunks) + 1} chunks", 1),
        "a tab to nowhere": page.replace('id="output-1-raw"', 'id="output-1-gone"', 1),
        "a view on another stage": other.replace("</ul>", '<p data-chunks="index"></p></ul>', 1),
    }
    examined(len(planted), "planted pages")
    assert chunk_problems(page, chunks) == []
    assert chunk_problems(planted["a wrong count"], chunks)
    assert chunk_problems(planted["a tab to nowhere"], chunks)
    assert chunk_problems(planted["a view on another stage"], None)
