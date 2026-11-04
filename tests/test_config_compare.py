"""A run's configuration against its pipeline's reference run, step by step (`config_compare`).

1. The reference run is the one the pipeline's current sealed reference was made from
   (`made_from.run_ids[0]`), named with the reference's seal and linked; on its own page the
   section says it is the reference run.
2. A planted change in a step's configuration, on runs with different inputs, is named at its step;
   equal configuration reads "configuration same" at every step; inputs and outputs are not compared,
   and the page says so.
3. An item one record lacks reads "not recorded", never "same"; a step only one run holds reads
   "not in the reference run" or "not in this run".
4. With no current reference the section says so and compares nothing, never falling back to a
   benchmark: with a benchmark whose reference was not made, and with no benchmark at all.
5. A public console draws the section only for the demo's runs, and runs nothing.
"""
from __future__ import annotations

import html
import re

import pytest

GENERATED_AT = "2026-09-26T12:00:00+02:00"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _section(pages: dict, name: str = "config-compare") -> str:
    both = pages["case.html"] + pages.get("proof.html", "")
    m = re.search(rf'<section data-section="{name}".*?</section>', both, re.S)
    return m.group(0) if m else ""


def _steps(section: str) -> dict[str, str]:
    """{step: its word}, from the section's step list."""
    return dict(re.findall(r'<li data-config-step="([^"]+)" data-config-word="([^"]+)">', section))


def _items(section: str, step: str) -> dict[str, str]:
    """{item: its word} at one step."""
    m = re.search(rf'<li data-config-step="{re.escape(step)}".*?</ul></li>', section, re.S)
    return dict(re.findall(r'<li data-config-item="([^"]+)" data-config-word="([^"]+)">', m.group(0))) if m else {}


def _store(folder, made: dict, benchmark: str | None):
    from onetrace_console import benchmarks
    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    store = Store(folder / "store")
    runs = {k: run_and_record(_deliver(p, store, outputs=True), store, ran_at=FIXED_RAN_AT) for k, p in made.items()}
    if benchmark:
        benchmarks.mark(store, runs[benchmark], who="test")
    return store, runs


def _pages(store, runs, *, public: bool = False) -> dict:
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    with rendering(onedoor=False, sign_in=False, public=public):
        return {k: render_execution(r, store, generated_at=GENERATED_AT).pages for k, r in runs.items()}


@pytest.fixture(scope="module")
def local(tmp_path_factory):
    from tests.config_compare_runs import record_run
    folder = tmp_path_factory.mktemp("config")
    made = {"ref": record_run(folder / "ref", "c-ref", x="1"),
            "same": record_run(folder / "same", "c-same", x="2"),
            "tool": record_run(folder / "tool", "c-tool", x="3", config={"call": {"max_retries": "2"}}),
            "short": record_run(folder / "short", "c-short", x="4", skip_prep=True),
            "setting": record_run(folder / "setting", "c-setting", x="5", constants={"prep": {"chunk_size": "512"}}),
            "settings": record_run(folder / "settings", "c-settings", x="6", constants={"prep": {"chunk_size": "256"}}),
            "code": record_run(folder / "code", "c-code", x="7", code_note="one line of the pipeline's code changed"),
            "sampling": record_run(folder / "sampling", "c-sampling", x="8",
                                   records={"model_call.json": {"sampling.temperature": "0.7",
                                                                "engine.settings.max_new_tokens": "128",
                                                                "model.requested": "example-other-model"}}),
            "unpaired": record_run(folder / "unpaired", "c-unpaired", x="9",
                                   records={"model_call.json": {"sampling.temperature": None},
                                            "model_call.2.json": {}})}
    store, runs = _store(folder, made, "ref")
    return {"folder": folder, "store": store, "runs": runs, "pages": _pages(store, runs)}


def test_the_reference_run_is_the_one_the_sealed_reference_was_made_from(local, examined):
    from onetrace_console import verdicts
    store, runs = local["store"], local["runs"]
    ref = verdicts.reference_record(verdicts.pipeline_of(runs["ref"], store), store, compute=False)
    doc = ref["reference"]
    section = _section(local["pages"]["tool"])
    examined(1, "reference")
    assert doc["made_from"]["run_ids"][0] == "c-ref"
    said = _text(section)
    assert "against the pipeline's reference run, c-ref" in said
    assert f'data-fingerprint="whole">{doc["seal"]}<' in section, "the reference is named by its seal"
    assert f'href="../../runs/{runs["ref"].key}/case.html" data-config-reference-run' in section
    assert "Runs are compared within their pipeline, as this console groups them by their declared stages." in said


def test_the_reference_run_s_own_page_says_it_is_the_reference_run(local, examined):
    section = _section(local["pages"]["ref"])
    examined(1, "page")
    assert "This run is the pipeline's reference run: the reference" in _text(section)
    assert "data-config-steps" not in section, "the reference run is not compared with itself"


def test_a_planted_tool_configuration_change_is_named_at_its_step(local, examined):
    section = _section(local["pages"]["tool"])
    steps = _steps(section)
    examined(len(steps), "steps")
    assert steps == {"prep": "configuration same", "call": "configuration differs"}
    assert "call : configuration differs: configuration fingerprint" in _text(section)
    assert _items(section, "call")["configuration fingerprint"] == "differs"
    assert _items(section, "prep")["configuration fingerprint"] == "same"


def test_equal_configuration_reads_same_at_every_step_whatever_the_inputs(local, examined):
    section = _section(local["pages"]["same"])
    steps = _steps(section)
    examined(len(steps), "steps")
    assert steps == {"prep": "configuration same", "call": "configuration same"}
    assert "Inputs and outputs are not compared here." in _text(section)


def test_a_step_only_one_run_holds_is_never_same(local, examined):
    section = _section(local["pages"]["short"])
    steps = _steps(section)
    examined(len(steps), "steps")
    assert steps == {"prep": "not in this run", "call": "configuration same"}


def test_declared_settings_are_compared_by_name_and_one_that_one_run_lacks_is_not_recorded(local, examined):
    store, runs = local["store"], local["runs"]
    from onetrace_console import config_compare
    #: The reference run declares no setting; c-setting declares chunk_size at prep.
    section = _section(local["pages"]["setting"])
    items = _items(section, "prep")
    examined(len(items), "items")
    assert items["declared setting chunk_size"] == "not recorded"
    assert "declared setting chunk_size: not recorded in the reference run" in _text(section)
    assert _steps(section)["prep"] == "configuration same", "a setting not recorded counted as a difference"
    #: Two runs that both declare it, with different values: named at its step, with both values.
    a, b = (config_compare.steps_of(runs[k], store) for k in ("setting", "settings"))
    got = config_compare.declared_settings(a[0], b[0], store)
    assert [(i.name, i.word, i.reference, i.this) for i in got] == [
        ("declared setting chunk_size", "differs", "512", "256")]
    assert config_compare.step_word(config_compare.compare_step(a[0], b[0], store)) == "configuration differs"


def test_a_code_change_is_named_at_every_step_it_ran(local, examined):
    section = _section(local["pages"]["code"])
    steps = _steps(section)
    examined(len(steps), "steps")
    assert steps == {"prep": "configuration differs", "call": "configuration differs"}
    assert "prep : configuration differs: code fingerprint" in _text(section)
    items = _items(section, "call")
    assert items["configuration fingerprint"] == "same" and items["code fingerprint"] == "differs"
    assert [k for k, v in items.items() if v == "differs"] == ["code fingerprint"]
    #: and an unchanged run reads it same.
    assert _items(_section(local["pages"]["same"]), "call")["code fingerprint"] == "same"


def test_model_call_settings_are_compared_by_the_comparator_s_groups(local, examined):
    section = _section(local["pages"]["sampling"])
    items = _items(section, "call")
    examined(len(items), "items")
    differs = [k for k, v in items.items() if v == "differs"]
    #: identity, then engine settings, then sampling, in the comparator's order.
    assert differs == ["model_call.json model.requested", "model_call.json engine.settings.max_new_tokens",
                       "model_call.json sampling.temperature"]
    assert _steps(section)["call"] == "configuration differs"
    said = _text(section)
    assert "model_call.json sampling.temperature differs: reference run 0 , this run 0.7" in said
    assert ("call : configuration differs: model_call.json model.requested, model_call.json "
            "engine.settings.max_new_tokens, model_call.json sampling.temperature") in said
    #: Nothing outside the three groups is compared: not the output, not the record's fingerprints.
    assert not [k for k in items if " output." in k or k.endswith(" fingerprints") or " batch." in k]
    from onetrace.model_call.comparator import IDENTITY
    assert all(_items(_section(local["pages"]["same"]), "call")[f"model_call.json {f}"] == "same" for f in IDENTITY)


def test_a_model_call_field_or_record_one_run_lacks_reads_not_recorded(local, examined):
    section = _section(local["pages"]["unpaired"])
    items = _items(section, "call")
    examined(len(items), "items")
    assert items["model_call.json sampling.temperature"] == "not recorded"
    assert items["model-call record model_call.2.json"] == "not recorded"
    said = _text(section)
    assert "model_call.json sampling.temperature: not recorded in this run (reference run observed, this run absent)" in said
    assert "model-call record model_call.2.json: not recorded in the reference run" in said
    assert _steps(section)["call"] == "configuration same"


def test_a_record_the_reader_refuses_is_not_read_never_same(monkeypatch):
    from onetrace_console import config_compare, model_call
    a = config_compare.Step("call", {"outputs": [{"name": "model_call.json", "digest": "sha256:" + "0" * 64}]},
                            "receipts/call.json", lambda path: b"{}")
    got = config_compare.model_calls(a, a, None)
    assert [(i.name, i.word) for i in got] == [("model-call record model_call.json", "not read")]
    assert "its stored bytes do not match its receipt" in got[0].note


def test_onetrace_s_own_constants_are_not_declared_settings():
    from onetrace_console.config_compare import Step, declared_settings
    a = Step("s", {"assertions": {"constants": {"onetrace.kept": "1", "k": "1"}}}, "r.json", None)
    b = Step("s", {"assertions": {"constants": {"onetrace.kept": "2", "k": "1"}}}, "r.json", None)
    assert [(i.name, i.word) for i in declared_settings(a, b, None)] == [("declared setting k", "same")]


def test_the_non_claims_are_said_and_no_cause_is(local, examined):
    from onetrace_console import config_compare
    section = _section(local["pages"]["tool"])
    examined(len(config_compare.NON_CLAIMS), "non-claims")
    for claim in config_compare.NON_CLAIMS:
        assert claim in _text(section)
    words = " ".join(v for k, v in vars(config_compare).items() if k.isupper() and isinstance(v, str)).lower()
    assert not re.search(r"\b(caused?|because|why)\b", words), "a line says what produced a difference"


def test_an_item_one_record_lacks_reads_not_recorded():
    from onetrace_console.config_compare import NOT_RECORDED, Step, config_fingerprint
    have = Step("call", {"instrument": {"config_digest": "sha256:" + "1" * 64}}, "r.json", None)
    lack = Step("call", {"instrument": {}}, "r.json", None)
    assert [i.word for i in config_fingerprint(have, lack, None)] == [NOT_RECORDED]
    assert [i.word for i in config_fingerprint(lack, lack, None)] == [NOT_RECORDED]


def test_a_benchmark_with_no_reference_shows_the_no_reference_line_not_a_comparison(tmp_path, monkeypatch,
                                                                                     examined):
    from onetrace_console import verdicts
    from tests.config_compare_runs import record_run
    made = {"a": record_run(tmp_path / "a", "n-a", x="1"),
            "b": record_run(tmp_path / "b", "n-b", x="2", config={"call": {"max_retries": "2"}})}
    store, runs = _store(tmp_path, made, "a")
    monkeypatch.setattr(verdicts, "_agree", lambda run, store: run.key != runs["a"].key)
    section = _section(_pages(store, {"b": runs["b"]})["b"])
    examined(1, "run")
    said = _text(section)
    assert "This pipeline has no reference yet." in said
    assert "python -m onetrace reference make" in said
    assert "data-config-steps" not in section and "n-a" not in said, "a benchmark taken in place of a reference"


def test_a_pipeline_with_no_benchmark_has_no_reference_to_compare_against(tmp_path, examined):
    from tests.config_compare_runs import record_run
    made = {"a": record_run(tmp_path / "a", "m-a", x="1"), "b": record_run(tmp_path / "b", "m-b", x="2")}
    store, runs = _store(tmp_path, made, None)
    section = _section(_pages(store, runs)["b"])
    examined(1, "run")
    assert "This pipeline has no reference yet" in _text(section) and "data-config-steps" not in section



def test_a_reference_made_from_a_run_this_console_does_not_hold_compares_nothing(local, monkeypatch, examined):
    from onetrace_console import config_compare
    store, runs = local["store"], local["runs"]
    held = {"reference": {"seal": "sha256:" + "5" * 64, "made_from": {"run_ids": ["gone-run"]}}, "runs": []}
    monkeypatch.setattr(config_compare, "reference_run", lambda run, store, compute: (held, None))
    section = _section(_pages(store, {"tool": runs["tool"]})["tool"])
    examined(1, "run")
    assert "was made from run gone-run, which this console does not hold, so nothing is compared." in _text(section)
    assert "data-config-steps" not in section

def test_a_public_console_shows_it_only_for_the_demo_s_runs_and_runs_nothing(local, monkeypatch, examined):
    from onetrace_console import config_compare, verdicts
    store, runs = local["store"], local["runs"]
    ran = []
    monkeypatch.setattr(verdicts, "_run_in", lambda *a, **k: ran.append(a) or {"exit": "0", "note": "", "files": {}})
    #: A delivered run carries no folder, so which runs are the demo's is planted here; the build's
    #: own runs are told by their folders, as its benchmark marks are (`benchmarks.mark_build`).
    monkeypatch.setattr(config_compare, "_demo", lambda run: False)
    shown = _section(_pages(store, {"tool": runs["tool"]}, public=True)["tool"])
    assert shown == "", "drawn on a public console for a run not the demo's"
    monkeypatch.setattr(config_compare, "_demo", lambda run: run.key != runs["same"].key)
    section = _section(_pages(store, {"tool": runs["tool"]}, public=True)["tool"])
    examined(1, "public page")
    assert _steps(section) == {"prep": "configuration same", "call": "configuration differs"}
    assert ran == [], "a public console ran a command"
    #: The reference run must be the demo's too.
    monkeypatch.setattr(config_compare, "_demo", lambda run: run.key != runs["ref"].key)
    assert _section(_pages(store, {"tool": runs["tool"]}, public=True)["tool"]) == ""


def test_a_demo_run_is_told_by_its_folder(monkeypatch):
    from types import SimpleNamespace
    from onetrace_console import config_compare
    monkeypatch.setattr(config_compare, "_demo_folders", lambda: {"p1-base"})
    assert config_compare._demo(SimpleNamespace(folder="/somewhere/p1-base"))
    assert not config_compare._demo(SimpleNamespace(folder="/somewhere/upload"))
    assert not config_compare._demo(SimpleNamespace(folder=""))


# ---- the policy version behind a decision ------------------------------------------------------

def _export(store, rows: list[dict]) -> dict[str, str]:
    """Hold a onedoor export of `rows` in `store`; {request id: its row's decision digest}."""
    import hashlib
    import io
    import json
    import tarfile
    from onetrace_console.onedoor_ext.decisions import accept_export
    lines = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in rows]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    sums = f"{hashlib.sha256(body).hexdigest()}  export.jsonl\n".encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, blob in (("export.jsonl", body), ("export.jsonl.sha256", sums)):
            info = tarfile.TarInfo(name=name)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    accept_export(buf.getvalue(), store, received_at=GENERATED_AT)
    return {r["request_id"]: "sha256:" + hashlib.sha256(ln.encode("utf-8")).hexdigest() for r, ln in zip(rows, lines)}


def _cite(request_id: str, digest: str) -> dict:
    return {"format": "onedoor-decision-ref/1", "request_id": request_id, "decision_digest": digest,
            "verdict": "permit", "issuer": "example-issuer"}


@pytest.fixture(scope="module")
def policy(tmp_path_factory):
    from onetrace_console import benchmarks
    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.config_compare_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("policy")
    store = Store(folder / "store")
    rows = [{"request_id": f"r{n}", "kind": "decision", "decision": "executed", "policy_version": v}
            for n, v in ((1, "policy-7"), (2, "policy-8"), (3, "policy-7"))]
    digests = _export(store, rows)
    cites = {"ref": [_cite("r1", digests["r1"])], "moved": [_cite("r2", digests["r2"])],
             "kept": [_cite("r3", digests["r3"])], "unheld": [_cite("r9", "sha256:" + "9" * 64)]}
    made = {k: record_run(folder / k, f"d-{k}", x=str(n), decisions=c) for n, (k, c) in enumerate(cites.items())}
    runs = {k: run_and_record(_deliver(p, store, outputs=True), store, ran_at=FIXED_RAN_AT) for k, p in made.items()}
    benchmarks.mark(store, runs["ref"], who="test")
    return {"store": store, "runs": runs}


def _policy_pages(policy, *, onedoor: bool) -> dict:
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    with rendering(onedoor=onedoor, sign_in=False, public=False):
        return {k: _section(render_execution(r, policy["store"], generated_at=GENERATED_AT).pages)
                for k, r in policy["runs"].items() if k != "ref"}


def test_the_policy_version_behind_a_decision_is_read_from_both_held_rows(policy, examined):
    sections = _policy_pages(policy, onedoor=True)
    name = "policy version behind decision 1"
    got = {k: _items(s, "call").get(name) for k, s in sections.items()}
    examined(len(got), "runs")
    assert "data-config-steps" in sections["moved"], "no reference was made from a run citing a decision"
    assert got == {"moved": "differs", "kept": "same", "unheld": "not recorded"}
    assert "policy version behind decision 1 differs: reference run policy-7 , this run policy-8" in _text(sections["moved"])
    assert "not recorded in this run" in _text(sections["unheld"])
    #: A step that cites no decision has no policy line.
    assert not [k for k in _items(sections["moved"], "prep") if k.startswith("policy")]


def test_a_console_with_onedoor_off_reads_no_policy_version(policy, examined):
    sections = _policy_pages(policy, onedoor=False)
    got = {k: _items(s, "call").get("policy version behind decision 1") for k, s in sections.items()}
    examined(len(got), "runs")
    assert set(got.values()) == {"not recorded"}
