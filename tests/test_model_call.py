"""The model-call record panel: a step's records in `model-call-record/1.0`, named as 1.0 names them
(`model_call.json`, then `model_call.2.json` and on), read by the installed onetrace's own
`onetrace.model_call` and shown as written; anything else named with its reason and not shown.

1. A record the SDK's own helpers write is read and shown, field by field under the schema copy's
   groups in their order, with whether its per-step capture was taken.
2. A record in the draft format, an incomplete one, one with a field the format does not name, and bytes
   that are not a record are each refused with the reason; a refused record shows no part of itself.
3. An output named like a record that 1.0 does not name (`model_call.1.json`) is named and not shown.
4. The reader checks a record with the installed SDK only. The console holds one copy of the format's
   schema, by digest, from the pinned source package, for the panel's groups and descriptions only.
5. The demo's agent step shows its two 1.0 example records, nothing observed; a draft record, as runs
   recorded before 1.0 hold, is named and not shown.
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

from onetrace_console import model_call as mc

SOURCE = "written for this test; nothing was observed"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def record(**over) -> dict:
    """A complete 1.0 record built with the SDK's own value-object helpers; `over` replaces fields."""
    from onetrace import model_call as m
    from onetrace.model_call import record as r
    rec = {"format": m.FORMAT, "call.kind": "self-hosted", "call.api": "example.generate", "credential": "absent"}
    for k in r.REQUIRED:
        if k not in r.PLAIN and k != "fingerprints":
            rec[k] = m.not_observed(SOURCE)
    rec["fingerprints"] = []
    rec["engine.name"] = m.observed("vllm", "written for this test")
    rec["dtype"] = m.declared("bfloat16", "written for this test")
    rec.update(over)
    return rec


def raw(rec: dict) -> bytes:
    from onetrace import model_call as m
    return m.record_bytes(rec)


def test_a_record_the_sdk_writes_is_read(examined):
    rec = record()
    examined(1, "record")
    assert mc.read(raw(rec)) == rec


#: The schema copy's digest and source, written here by the tool that made the copy, never typed.
SCHEMA_SHA256 = "877f40cb6fde322adf321b8b0e4860ccc5ec63db24983bb531f31d5bd2d76ab6"
SDIST_SHA256 = "abad114580f0d82dc35f44011d9644ca6bc2eb42ef309d0ce5994af6dcb17964"


def test_the_reader_reads_the_installed_sdk_and_holds_one_schema_copy_by_digest(examined):
    """Exactly one `*.schema.json` in the console: the 1.0 schema copy, by digest. No draft returns."""
    from tests.test_folder_load import REPO
    src = REPO / "src" / "onetrace_console"
    schemas = {p.relative_to(src).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in src.rglob("*.schema.json")}
    text = (src / "model_call.py").read_text(encoding="utf-8")
    examined(len(schemas), "schema files")
    assert schemas == {mc.SCHEMA_FILE: SCHEMA_SHA256}, schemas
    assert mc.SCHEMA_SHA256 == SCHEMA_SHA256
    assert "from onetrace import model_call" in text and "validate(" in text
    assert mc.FORMAT == __import__("onetrace.model_call", fromlist=["FORMAT"]).FORMAT


def test_the_schema_copy_is_1_0_and_names_where_it_came_from(examined):
    from importlib.resources import files
    raw = files("onetrace_console").joinpath(mc.SCHEMA_FILE).read_bytes()
    examined(1, "schema copy")
    assert hashlib.sha256(raw).hexdigest() == SCHEMA_SHA256
    assert json.loads(raw)["$id"] == "model-call-record/1.0" == mc.FORMAT
    assert mc.SCHEMA_SOURCE == ("docs/model_call_record.schema.json in onetrace-0.6.0.tar.gz (sha256 "
                                f"{SDIST_SHA256}), copied byte for byte")
    from tests.test_pins import PINNED_SDK_VERSION
    assert PINNED_SDK_VERSION == "0.6.0", "the copy is 0.6.0's; a new pin reads the installed schema or recopies"


def test_the_copy_gives_labels_only_and_its_groups_hold_every_field_the_sdk_names(examined):
    """The groups name each field the installed SDK requires, and its steps field, each once; the copy
    is read for labels, never to check or import anything."""
    from onetrace.model_call import record as r
    from tests.test_folder_load import REPO
    labels = mc.schema_labels()
    grouped = [f for fs in labels["groups"].values() for f in fs]
    examined(len(grouped), "grouped fields")
    assert len(grouped) == len(set(grouped)), grouped
    assert set(grouped) == set(r.REQUIRED) | {r.STEPS}, set(grouped) ^ (set(r.REQUIRED) | {r.STEPS})
    assert all(labels["descriptions"].get(f) for f in grouped)
    text = (REPO / "src" / "onetrace_console" / "model_call.py").read_text(encoding="utf-8")
    assert "jsonschema" not in text and text.count("SCHEMA_FILE") == 2, "the copy is read in one place"


def test_the_panel_says_in_one_line_where_its_labels_come_from(examined):
    receipt, read_file = _step({"model_call.json": raw(record())})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "panel")
    notes = re.findall(r"<p class=\"footnote\" data-model-call-schema>(.*?)</p>", page)
    assert [html.unescape(n) for n in notes] == [mc.SCHEMA_NOTE]
    assert "onetrace 0.6.0" in mc.SCHEMA_NOTE and "\n" not in mc.SCHEMA_NOTE


#: Each planted record and the reason it is refused with.
PLANTED = {
    "the draft format": ({**record(), "format": "model-call-record/0.1-draft"},
                         'the record\'s format is "model-call-record/0.1-draft", not model-call-record/1.0; '
                         "this console reads model-call-record/1.0 only"),
    "a field left out": ({k: v for k, v in record().items() if k != "dtype"},
                         "onetrace's model-call reader refuses it: record incomplete: dtype"),
    "a field the format does not name": ({**record(), "colour": {"status": "observed", "value": "blue", "source": "x"}},
                                         "onetrace's model-call reader refuses it: fields outside the record format: colour"),
    "a state the format does not have": ({**record(), "dtype": {"status": "guessed", "source": "x"}},
                                         "onetrace's model-call reader refuses it: dtype is not a value object"),
    "a number where the format writes a string": (
        {**record(), "batch.size": {"status": "observed", "value": 4, "source": "x"}},
        "onetrace's model-call reader refuses it: batch.size: value is not a string (every scalar in a record is a string)"),
}


@pytest.mark.parametrize("name", sorted(PLANTED))
def test_a_record_that_does_not_hold_is_refused_with_its_reason(name, examined):
    rec, why = PLANTED[name]
    examined(1, "planted record")
    with pytest.raises(mc.Refused) as got:
        mc.read(json.dumps(rec).encode("utf-8"))
    assert str(got.value) == why


@pytest.mark.parametrize("data, why", [
    (b'{"format":"a","format":"b"}', "the record names format more than once"),
    (b'{"x":NaN}', "the record holds NaN, which is not JSON"),
    (b"\xff{}", "the record is not UTF-8"),
    (b"[]", "the record is not a JSON object"),
    (b"{}", "the record names no format; this console reads model-call-record/1.0"),
    (b"{", "the record is not JSON"),
    (b"[" * 5000 + b"]" * 5000, "the record nests more deeply than this reader reads"),
])
def test_bytes_that_are_not_a_record_are_refused(data, why, examined):
    examined(1, "planted bytes")
    with pytest.raises(mc.Refused, match=re.escape(why)):
        mc.read(data)


def _step(records: dict[str, bytes], digests: dict[str, str] | None = None):
    receipt = {"outputs": [{"name": n, "digest": (digests or {}).get(n, "sha256:" + hashlib.sha256(b).hexdigest())}
                           for n, b in records.items()]}
    files = {f"artifacts/02-call/{n}": b for n, b in records.items()}
    return receipt, files.get


def test_a_step_shows_each_record_under_the_label_grouped_as_the_schema_groups_its_fields(examined):
    from onetrace import model_call as m
    second = record(steps=m.observed("sha256:" + "a" * 64, "model_call.2.steps.json"))
    receipt, read_file = _step({"model_call.json": raw(record()), "model_call.2.json": raw(second)})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(2, "records shown")
    label = re.search(r'<p class="label" data-model-call-label>(.*?)</p>', page).group(1)
    assert label == "Model-call record, format <code>model-call-record/1.0</code>: shown as written."
    assert re.findall(r'data-model-call="([^"]+)"', page) == ["model_call.json", "model_call.2.json"]
    first = page.split('data-model-call="model_call.2.json"')[0]
    #: Every field under its group, the groups and their fields in the schema copy's own order, read
    #: here from the copy's bytes; `fingerprints` here is an empty list, so it draws no row.
    from importlib.resources import files
    groups = json.loads(files("onetrace_console").joinpath(mc.SCHEMA_FILE).read_bytes())["x-groups"]
    held = json.loads(raw(record()))
    want = [f for fs in groups.values() for f in fs if f in held and f != "fingerprints"]
    assert re.findall(r'<tr data-field="([^"]+)"', first) == want
    assert re.findall(r'<tr class="group" data-group="([^"]+)"', first) == [
        t for t, fs in groups.items() if any(f in held for f in fs)]
    assert 'data-field="dtype" data-state="declared, not observed"' in page
    assert re.findall(r'data-model-call-steps="([^"]+)"', page) == ["not-taken", "taken"]
    assert "per-step capture: not taken" in _text(page) and "per-step capture: model_call.2.steps.json" in _text(page)
    #: The second names a steps file its step's receipt does not list: no timeline, and why.
    assert ("Token timeline not shown: the step's receipt lists no output model_call.2.steps.json."
            in _text(page))
    assert "data-refused" not in page


def test_a_name_1_0_does_not_give_a_record_is_named_and_not_shown(examined):
    receipt, read_file = _step({"model_call.1.json": raw(record())})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "output named model_call.1.json")
    assert 'data-model-call="model_call.1.json" data-refused' in page
    assert f"Not shown: {mc.NOT_A_RECORD_NAME}." in _text(page) and "data-field" not in page


def test_a_record_whose_bytes_do_not_match_its_receipt_is_not_shown(examined):
    receipt, read_file = _step({"model_call.json": raw(record())}, {"model_call.json": "sha256:" + "0" * 64})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "record not matching its receipt")
    assert "Not shown: its stored bytes do not match its receipt." in _text(page)
    assert "data-field" not in page


def test_a_refused_record_shows_no_part_of_itself(examined):
    data = json.dumps({**record(), "format": "model-call-record/0.1-draft",
                       "model.reported": {"status": "observed", "value": "example-hosted-model", "source": "x"}}).encode()
    receipt, read_file = _step({"model_call.json": data})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(1, "refused record")
    assert "this console reads model-call-record/1.0 only" in _text(page)
    assert "data-field" not in page and "example-hosted-model" not in page


def test_a_step_with_no_record_gets_no_section(examined):
    examined(3, "steps")
    assert mc.step_section({"outputs": [{"name": "answer.json"}]}, "receipts/01-a.json", lambda p: b"") == ""
    assert mc.step_section({"outputs": [{"name": "model_call.01.json"}]}, "receipts/01-a.json", lambda p: b"") == ""
    #: A per-step capture file is the record's companion, never a record of its own.
    assert mc.step_section({"outputs": [{"name": "model_call.steps.json"}]}, "receipts/01-a.json", lambda p: b"") == ""


def test_the_console_does_not_import_the_draft_s_package(examined):
    from tests.test_folder_load import REPO
    src = (REPO / "src" / "onetrace_console")
    texts = {p.name: p.read_text(encoding="utf-8") for p in src.rglob("*.py")}
    examined(len(texts), "source files")
    assert [n for n, t in texts.items() if "onetrace_model_call" in t] == []


def test_the_demo_s_agent_step_shows_its_two_1_0_records_with_nothing_observed(shared_demo, examined):
    """The demo's agent step writes two example records in 1.0 (`model_call_example`): both shown, no
    field `observed` (no call was made), and no per-step capture taken."""
    from onetrace_console.demo_store import model_call_example as ex
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    runs = {r.run_id: r for r in store.runs()}
    examined(2, "agent runs' step pages")
    for name in ("pz-51-agent-baseline", "pz-53-agent-amount-changed"):
        page = (folder / "store" / "pages" / "runs" / runs[name].key / "stage-1.html").read_text(encoding="utf-8")
        assert re.findall(r'data-model-call="([^"]+)"', page) == list(ex.NAMES), name
        assert "data-refused" not in page and 'data-state="observed"' not in page, name
        assert re.findall(r'data-model-call-steps="([^"]+)"', page) == ["not-taken", "not-taken"], name
        assert ex.SOURCE in _text(page), name
    #: No other run's step writes one.
    others = [r for n, r in runs.items() if n not in ("pz-51-agent-baseline", "pz-53-agent-amount-changed")]
    assert not any('data-section="model-call"' in p.read_text(encoding="utf-8")
                   for r in others for p in (folder / "store" / "pages" / "runs" / r.key).glob("stage-*.html"))


def test_a_draft_record_on_a_step_is_named_and_not_shown(examined):
    """A record in the earlier draft format, as runs recorded before 1.0 hold (the hosted demo's kept
    agent runs): named, its reason said, no part shown."""
    draft = json.dumps({**record(), "format": "model-call-record/0.1-draft"}).encode("utf-8")
    receipt, read_file = _step({"model_call.json": draft, "model_call.1.json": draft})
    page = mc.step_section(receipt, "receipts/02-call.json", read_file)
    examined(2, "draft records")
    assert re.findall(r'data-model-call="([^"]+)" data-refused', page) == ["model_call.json", "model_call.1.json"]
    said = _text(page)
    assert "this console reads model-call-record/1.0 only" in said and mc.NOT_A_RECORD_NAME in said
    assert "data-field" not in page
