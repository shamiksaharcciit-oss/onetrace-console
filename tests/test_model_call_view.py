"""The model-call view on recorded runs: a step's records grouped as the schema copy groups them, the
token timeline from a steps file, the runs that share a record's model files, and a comparison's
records compared by the installed onetrace's own comparator, in its words.

1. A comparison whose step holds a record of the same name on both sides shows, under the short answer,
   the comparator's report line for line as the SDK's `compare` gives it for the two stored records.
2. Where both runs hold a steps file, the `diverged` result's first-differing-step line links to that
   step's decode-step row on the candidate's step page, and the row is there.
3. `same` and a `diverged` with no steps files are shown as the comparator words them; a record only
   one run holds is named with the side that holds it; a pair with no record on either side shows no
   section.
4. A step's page draws its steps file as the token timeline: one row per decode step, each chosen
   token as an id, and the capture level as the file names it.
5. A steps file that does not match its receipt or its record, or does not hold ids, is named with
   its reason and not drawn; what else a steps file holds is named and not shown.
6. A record's model files: the other runs whose records name the same value are listed and linked;
   where none does, it says so.
7. Each field's description is the schema copy's; a field no group lists is under its own heading.
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

from onetrace_console import model_call as mc

GENERATED_AT = "2026-09-26T12:00:00+02:00"
IDS_A, IDS_B = ["5", "9", "13", "20"], ["5", "9", "14", "21"]


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("model-call-view")
    made = {
        "a": record_run(folder / "a", "mc-a", token_ids=IDS_A),
        "b": record_run(folder / "b", "mc-b", fingerprint="sha256:" + "d" * 64, output="sha256:" + "e" * 64,
                        token_ids=IDS_B),
        "c": record_run(folder / "c", "mc-c", token_ids=IDS_A),
        "d": record_run(folder / "d", "mc-d", files_digest="sha256:" + "f" * 64),
        "n": record_run(folder / "n", "mc-n", with_record=False),
        "m": record_run(folder / "m", "mc-m", with_record=False),
    }
    store = Store(folder / "store")
    runs = {k: run_and_record(_deliver(p, store, outputs=True), store, ran_at=FIXED_RAN_AT) for k, p in made.items()}
    pairs = {p: compare(runs[p[0]], runs[p[1]], store, ran_at=FIXED_RAN_AT) for p in ("ab", "ac", "ad", "an", "nm")}
    with rendering(onedoor=False, sign_in=False, public=True):
        diffs = {p: render_diff(c, store, generated_at=GENERATED_AT) for p, c in pairs.items()}
        pages = {k: render_execution(r, store, generated_at=GENERATED_AT).pages for k, r in runs.items()}
    return {"folders": made, "runs": runs, "diffs": diffs, "pages": pages}


def _stored(folder) -> tuple[dict, list[str] | None]:
    """The record and steps ids as the run's own folder holds them, read here without the console."""
    step = next((folder / "artifacts").iterdir())
    rec = json.loads((step / "model_call.json").read_bytes())
    steps = step / "model_call.steps.json"
    return rec, json.loads(steps.read_bytes())["token_ids"] if steps.exists() else None


def _section(page: str) -> str:
    m = re.search(r'<section data-section="model-call-compare".*?</section>', page, re.S)
    return m.group(0) if m else ""


def _lines(section: str) -> list[str]:
    """Each line as the comparator said it: its short fingerprints read back whole from the fold, which
    holds each whole value once."""
    out = []
    for li in re.findall(r"<li[^>]*>(.*?)</li>", section, re.S):
        wholes = re.findall(r'<span class="mono" data-fingerprint="whole">([^<]+)</span>', li)
        inline = re.sub(r"<details.*?</details>", "", li, flags=re.S)
        for w in wholes:
            inline = inline.replace(f'<span class="mono">{w[:len("sha256:") + 12]}…</span>', w)
        out.append(_text(inline))
    return out


def test_the_comparator_s_fingerprints_are_short_with_each_whole_one_fold_away(built, examined):
    from onetrace_console.viewer.page import shortened_in_text
    from onetrace import model_call as sdk
    (ra, ia), (rb, ib) = _stored(built["folders"]["a"]), _stored(built["folders"]["b"])
    want = sdk.compare(ra, rb, receipts=("verified", "verified"), steps=(ia, ib)).lines()
    items = re.findall(r"<li[^>]*>(.*?)</li>", _section(built["diffs"]["ab"]), re.S)
    examined(len(items), "lines")
    records = next(i for i, ln in enumerate(want) if ln.startswith("records: "))
    inline, folded = shortened_in_text(want[records])
    assert items[records] == f"{inline} {folded}"
    assert "sha256:" + "a" * 64 not in re.sub(r"<details.*?</details>", "", items[records], flags=re.S)


def test_the_comparator_s_report_is_shown_line_for_line_under_the_short_answer(built, examined):
    from onetrace import model_call as sdk
    (ra, ia), (rb, ib) = _stored(built["folders"]["a"]), _stored(built["folders"]["b"])
    want = sdk.compare(ra, rb, receipts=("verified", "verified"), steps=(ia, ib)).lines()
    page = built["diffs"]["ab"]
    section = _section(page)
    examined(len(want), "comparator lines")
    assert _lines(section) == want
    assert want[0] == "result: diverged: fingerprint (tolerant, first-token-logprobs)", want[0]
    #: Directly under the short answer: nothing between them.
    short_end = re.search(r'<section data-section="short-answer".*?</section>', page, re.S).end()
    assert page.index('<section data-section="model-call-compare"') == short_end
    assert "Compared with the comparator's defaults: mode 1, fingerprint form tolerant." in _text(section)


def test_the_first_differing_step_links_to_its_decode_step_row(built, examined):
    section = _section(built["diffs"]["ab"])
    link = re.search(r'<a href="([^"]+)" data-decode-link="(\d+)">first differing token at step 2</a>', section)
    examined(1, "link")
    assert link is not None, section
    href, at = link.groups()
    run_b = built["runs"]["b"]
    assert href == f"../runs/{run_b.key}/stage-1.html#decode-model_call-json-2"
    row = re.search(r'<tr id="decode-model_call-json-2" data-decode-step="2">(.*?)</tr>',
                    built["pages"]["b"]["stage-1.html"], re.S)
    assert row is not None and _text(row.group(1)) == f"2 {IDS_B[2]}"


def test_same_and_a_divergence_without_steps_files_read_as_the_comparator_words_them(built, examined):
    from onetrace import model_call as sdk
    examined(2, "comparisons")
    for pair, other in (("ac", "c"), ("ad", "d")):
        (ra, ia), (ro, io) = _stored(built["folders"]["a"]), _stored(built["folders"][other])
        steps = (ia, io) if ia is not None and io is not None else None
        want = sdk.compare(ra, ro, receipts=("verified", "verified"), steps=steps).lines()
        section = _section(built["diffs"][pair])
        assert _lines(section) == want, pair
        assert "data-decode-link" not in section, pair
    assert _lines(_section(built["diffs"]["ac"]))[0] == "result: same"
    assert _lines(_section(built["diffs"]["ad"]))[0] == "result: diverged: model.files_digest"


def test_a_record_one_run_holds_is_named_and_a_pair_without_records_has_no_section(built, examined):
    examined(2, "comparisons")
    section = _section(built["diffs"]["an"])
    assert "model_call.json at call: only the baseline holds it; nothing compared." in _text(section)
    assert 'data-comparator="' not in section
    assert 'data-section="model-call-compare"' not in built["diffs"]["nm"]


def test_a_step_s_record_output_links_to_its_record_on_the_same_page(built, examined):
    page = built["pages"]["b"]["stage-1.html"]
    links = re.findall(r'<a href="#([^"]+)" data-model-call-link>', page)
    examined(len(links), "links")
    assert links == ["model-call-model_call-json"]
    assert 'id="model-call-model_call-json"' in page
    assert "data-model-call-link" not in built["pages"]["n"]["stage-1.html"]


def test_a_step_page_draws_its_steps_file_as_ids(built, examined):
    page = built["pages"]["b"]["stage-1.html"]
    rows = re.findall(r'<tr id="decode-model_call-json-(\d+)" data-decode-step="\d+"><td[^>]*>\d+</td><td[^>]*><code>(\d+)</code>',
                      page)
    examined(len(rows), "decode-step rows")
    assert rows == [(str(i), t) for i, t in enumerate(IDS_B)]
    assert "capture level, as the steps file names it: L1" in _text(page)
    assert "data-steps-held" not in page
    assert "data-token-timeline" not in built["pages"]["d"]["stage-1.html"], "a record with no steps file"


def _step(files: dict[str, bytes], digests: dict[str, str] | None = None):
    receipt = {"outputs": [{"name": n, "digest": (digests or {}).get(n, "sha256:" + hashlib.sha256(b).hexdigest())}
                           for n, b in files.items()]}
    return receipt, {f"artifacts/02-call/{n}": b for n, b in files.items()}.get


def _with_steps(steps_bytes: bytes, named: bytes | None = None, digests=None) -> str:
    from onetrace import model_call as m
    from tests.test_model_call import raw, record
    digest = "sha256:" + hashlib.sha256(named if named is not None else steps_bytes).hexdigest()
    rec = record(steps=m.observed(digest, "model_call.steps.json"))
    receipt, read_file = _step({"model_call.json": raw(rec), "model_call.steps.json": steps_bytes}, digests)
    return mc.step_section(receipt, "receipts/02-call.json", read_file)


@pytest.mark.parametrize("make, why", [
    (lambda: _with_steps(b'{"token_ids":["1"]}', named=b"other"), "its bytes do not match the digest the record names"),
    (lambda: _with_steps(b'{"token_ids":["1"]}', digests={"model_call.steps.json": "sha256:" + "0" * 64}),
     "its stored bytes do not match its receipt"),
    (lambda: _with_steps(b'{"token_ids":[1]}'), "the steps file holds no token_ids list of decimal strings"),
    (lambda: _with_steps(b'{"token_ids":["01"]}'), "the steps file holds no token_ids list of decimal strings"),
    (lambda: _with_steps(b"{"), "the steps file is not JSON this reader reads"),
])
def test_a_steps_file_that_does_not_hold_is_named_and_not_drawn(make, why, examined):
    page = make()
    examined(1, "planted steps file")
    assert f"Token timeline not shown: {why}." in _text(page)
    assert "data-decode-step" not in page


def test_what_else_a_steps_file_holds_is_named_and_not_shown(examined):
    page = _with_steps(b'{"level":"L2","token_ids":["7"],"top_k":[["7","8"]]}')
    examined(1, "steps file")
    assert "Also in the steps file, not shown by this console: top_k." in _text(page)
    assert '"8"' not in page and ">8<" not in page
    assert "capture level, as the steps file names it: L2" in _text(page)


def test_the_runs_naming_the_same_model_files_are_listed_and_linked(built, examined):
    runs = built["runs"]
    page = built["pages"]["b"]["stage-1.html"]
    listed = re.findall(r'<li data-same-files-run="[^"]*"><a href="([^"]+)">', page)
    examined(len(listed), "runs listed")
    assert sorted(listed) == sorted(f"../{runs[k].key}/stage-1.html#model-call-model_call-json" for k in ("a", "c"))
    d = built["pages"]["d"]["stage-1.html"]
    line = re.search(r'<div data-same-files="none">(.*?)</div>', d, re.S)
    assert line is not None and "data-same-files-run" not in d
    assert _text(line.group(1)).startswith("No other run's model-call record names the same model files, model.files_digest")
    assert "sha256:" + "f" * 64 in line.group(1)


def test_each_description_is_the_schema_copy_s_and_an_ungrouped_field_has_its_heading(examined):
    from importlib.resources import files
    from onetrace import model_call as m
    from tests.test_model_call import raw, record
    schema = json.loads(files("onetrace_console").joinpath(mc.SCHEMA_FILE).read_bytes())
    rec = record(**{"engine.settings.max_tokens": m.observed("16", "written for this test")})
    receipt, read_file = _step({"model_call.json": raw(rec)})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    folds = re.findall(r'<details class="about" data-about="([^"]+)"><summary>[^<]*</summary><p>(.*?)</p>', page)
    examined(len(folds), "descriptions")
    assert folds and all(html.unescape(t) == schema["properties"][f]["description"] for f, t in folds)
    groups = re.findall(r'<tr class="group" data-group="([^"]+)"', page)
    assert groups[-1] == mc.UNGROUPED
    tail = page.split(f'data-group="{mc.UNGROUPED}"')[1]
    assert re.findall(r'<tr data-field="([^"]+)"', tail) == ["engine.settings.max_tokens"]
