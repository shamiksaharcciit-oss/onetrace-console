"""The model-call record panel: a step's `model_call.json` and `model_call.<N>.json`, in the draft
format `model-call-record/0.1-draft`, shown as written under the format's label, and refused with
its reason where it is anything else. Each refusal has its planted record; the demo's step shows its
two example records.
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

from onetrace_console import model_call as mc
from onetrace_console.demo_store import model_call_example as ex


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def test_the_schema_beside_the_console_is_the_draft_s(examined):
    schema = mc.load_schema()
    examined(1, "schema")
    assert schema["$id"] == mc.FORMAT == schema["properties"]["format"]["const"]


@pytest.mark.parametrize("make", [ex.self_hosted, ex.hosted])
def test_the_demo_s_example_records_hold_to_the_schema(make, examined):
    examined(1, "example record")
    record = mc.read(ex.record_bytes(make()))
    assert set(mc.load_schema()["required"]) <= set(record)
    assert all(ex.SOURCE in v["source"] for v in record.values() if isinstance(v, dict))


#: Each planted record and the reason it is refused with.
PLANTED = {
    "another format": ({**ex.hosted(), "format": "model-call-record/0.2"},
                       'the record\'s format is "model-call-record/0.2", not model-call-record/0.1-draft'),
    "a field left out": ({k: v for k, v in ex.hosted().items() if k != "dtype"}, "the record has no dtype"),
    "a field the format does not name": ({**ex.hosted(), "colour": "blue"},
                                         "the record has a field the format does not name: colour"),
    "a hosted call with an internal value": (
        {**ex.hosted(), "dtype": {"status": "observed", "value": "fp16", "source": "x"}},
        'dtype\'s status is "observed", not one of "not observed"'),
    "a self-hosted call with a credential": ({**ex.self_hosted(), "credential": "present"},
                                             'credential is "present", not "absent"'),
    "a state the format does not have": (
        {**ex.hosted(), "dtype": {"status": "guessed", "source": "x"}},
        'dtype is not a value in one of the format\'s states (its status is "guessed") (and 1 more)'),
    "a number where the format writes a string": (
        {**ex.self_hosted(), "batch.size": {"status": "observed", "value": 4, "source": "x"}},
        'batch.size is not a value in one of the format\'s states (its status is "observed")'),
}


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_a_record_that_does_not_hold_is_refused_with_its_reason(name, examined):
    record, why = PLANTED[name]
    examined(1, "planted record")
    with pytest.raises(mc.Refused) as got:
        mc.read(json.dumps(record).encode("utf-8"))
    assert str(got.value) == why


@pytest.mark.parametrize("raw, why", [
    (b'{"format":"a","format":"b"}', "the record names format more than once"),
    (b'{"x":NaN}', "the record holds NaN, which is not JSON"),
    (b"\xff{}", "the record is not UTF-8"),
    (b"[]", "the record is not a JSON object"),
    (b"{}", "the record names no format; this reader reads model-call-record/0.1-draft"),
    (b"{", "the record is not JSON"),
    (b"[" * 5000 + b"]" * 5000, "the record nests more deeply than this reader reads"),
])
def test_bytes_that_are_not_a_record_are_refused(raw, why, examined):
    examined(1, "planted bytes")
    with pytest.raises(mc.Refused, match=re.escape(why)):
        mc.read(raw)


def test_a_schema_keyword_the_reader_does_not_apply_refuses_the_schema(examined):
    schema = json.loads(mc.SCHEMA.read_text(encoding="utf-8"))
    schema["properties"]["dtype"] = {"maxLength": 3}
    examined(1, "planted schema")
    with pytest.raises(mc.Refused, match="the schema uses maxLength, which this reader does not apply"):
        mc.read(ex.record_bytes(ex.hosted()), schema)


def _step(records: dict[str, bytes], digests: dict[str, str] | None = None):
    receipt = {"outputs": [{"name": n, "digest": (digests or {}).get(n, "sha256:" + hashlib.sha256(b).hexdigest())}
                           for n, b in records.items()]}
    files = {f"artifacts/02-call/{n}": b for n, b in records.items()}
    return receipt, files.get


def test_a_step_shows_each_record_grouped_under_the_label(examined):
    receipt, read_file = _step({"model_call.json": ex.record_bytes(ex.self_hosted()),
                                "model_call.1.json": ex.record_bytes(ex.hosted())})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(2, "records shown")
    shown = _text(page)
    label = re.search(r"<p class=\"label\" data-model-call-label>(.*?)</p>", page).group(1)
    assert label == ("Model-call record, draft format <code>model-call-record/0.1-draft</code>: shown as written; "
                     "the format may change.")
    assert re.findall(r'data-model-call="([^"]+)"', page) == ["model_call.json", "model_call.1.json"]
    groups = re.findall(r'<tr class="group"><th colspan="4">([^<]+)</th>', page)
    assert groups[:6] == ["The call", "The model", "The tokenizer", "The engine and runtime",
                          "The batch context", "The output fingerprints"]
    assert 'data-field="batch.padded_width" data-state="not applicable"' in page
    assert "vLLM pads no batch to a width" in shown
    assert "data-refused" not in page


def test_a_record_whose_bytes_do_not_match_its_receipt_is_not_shown(examined):
    raw = ex.record_bytes(ex.hosted())
    receipt, read_file = _step({"model_call.json": raw}, {"model_call.json": "sha256:" + "0" * 64})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "record not matching its receipt")
    assert "Not shown: its stored bytes do not match its receipt." in _text(page)
    assert "data-field" not in page


def test_a_refused_record_shows_no_part_of_itself(examined):
    raw = json.dumps({**ex.hosted(), "colour": "blue"}).encode("utf-8")
    receipt, read_file = _step({"model_call.json": raw})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "refused record")
    assert "Not shown: the record has a field the format does not name: colour." in _text(page)
    assert "data-field" not in page and "example-hosted-model" not in page


def test_a_step_with_no_record_gets_no_section(examined):
    examined(2, "steps")
    assert mc.step_section({"outputs": [{"name": "answer.json"}]}, "receipts/01-a.json", lambda p: b"") == ""
    assert mc.step_section({"outputs": [{"name": "model_call.01.json"}]}, "receipts/01-a.json", lambda p: b"") == ""


def test_the_console_does_not_import_the_writer_s_package(examined):
    from tests.test_folder_load import REPO
    src = (REPO / "src" / "onetrace_console")
    texts = {p.name: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
    examined(len(texts), "source files")
    assert [n for n, t in texts.items() if "onetrace_model_call" in t] == []


def test_the_demo_s_agent_step_shows_its_two_example_records(shared_demo, examined):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    runs = {r.run_id: r for r in store.runs()}
    examined(2, "agent runs' step pages")
    for name in ("pz-51-agent-baseline", "pz-53-agent-amount-changed"):
        page = (folder / "store" / "pages" / "runs" / runs[name].key / "stage-1.html").read_text(encoding="utf-8")
        assert re.findall(r'data-model-call="([^"]+)"', page) == ["model_call.json", "model_call.1.json"], name
        assert "data-refused" not in page and ex.SOURCE in _text(page), name
    #: No other run's step writes one.
    others = [r for n, r in runs.items() if n not in ("pz-51-agent-baseline", "pz-53-agent-amount-changed")]
    assert not any('data-section="model-call"' in p.read_text(encoding="utf-8")
                   for r in others for p in (folder / "store" / "pages" / "runs" / r.key).glob("stage-*.html"))


def _schema_words() -> list[str]:
    """Every `description` and `$comment` text the schema holds, anywhere in it."""
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("description", "$comment") and isinstance(v, str):
                    found.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(mc.load_schema())
    return found


def schema_text_problems(page: str) -> list[str]:
    """The page shows the record's fields, the format's name and the label; never the schema's own
    words, its descriptions and comments (which name documents the console does not hold)."""
    shown = html.unescape(page)
    return [w[:60] for w in _schema_words() if w in shown]


def test_a_step_s_records_show_none_of_the_schema_s_own_words(shared_demo, examined):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    run = next(r for r in store.runs() if r.run_id == "pz-51-agent-baseline")
    page = (folder / "store" / "pages" / "runs" / run.key / "stage-1.html").read_text(encoding="utf-8")
    words = _schema_words()
    examined(len(words), "the schema's descriptions and comments")
    assert words and 'data-model-call="model_call.json"' in page
    assert schema_text_problems(page) == []


def test_sabotage_a_schema_description_drawn_on_the_page_is_named(examined):
    receipt, read_file = _step({"model_call.json": ex.record_bytes(ex.self_hosted())})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    planted = page.replace("</section>", f"<p>{html.escape(_schema_words()[0])}</p></section>")
    examined(1, "planted page")
    assert schema_text_problems(page) == [] and schema_text_problems(planted) == [_schema_words()[0][:60]]
