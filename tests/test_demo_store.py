"""The demo store, 0.1.1: made from real runs by one builder.

Checked here:
- two builds give the same bytes, apart from what the SDK stamps with the time and what is hashed
  over it -- exactly that, and nothing broader (`_without_time`);
- the build record names every file changed, added or removed after the build, and the console
  refuses a demo folder it doesn't vouch for (here, and at the demo's and a public console's
  start: tests/test_folder_load.py, tests/test_public_mode.py);
- P2 is the reference demo's pipeline unchanged: its outputs, and the text diff between its
  two runs, are those of the committed runs in examples/;
- every run reads, by the console's own check, as the store's table says -- read from the
  stored check and the pages the console draws, never set;
- the two keys: the trusted one's label says what a public-seed key proves.
"""
from __future__ import annotations

import copy
import html
import json
import re
import subprocess
from pathlib import Path

import pytest
#: The SDK run as the console runs it (compare.py): UTF-8 forced on the child's output, so the bytes
#: compared are the console's, on a machine whose default encoding is not UTF-8 too.
from onetrace_console.child import utf8_env  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
EXAMPLE = REPO / "examples" / "reference-demo"


@pytest.fixture(scope="module")
def two_builds(tmp_path_factory) -> tuple[Path, Path]:
    from onetrace_console.demo_store import build
    root = tmp_path_factory.mktemp("two-builds")
    build(root / "a")
    build(root / "b")
    return root / "a", root / "b"


@pytest.fixture(scope="module")
def built(shared_demo) -> Path:
    """The public demo, built once, as the image builds it (`demo --public --build`)."""
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    return folder


def _files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


# ------------------------------------------------------------- 1. two builds, the same bytes apart from time

def _without_time(rel: str, data: bytes):
    """A file's content with what the clock decides removed, and nothing else: a receipt's
    `time`, and the digests the chain builds over receipts that hold it -- `prev`, an input that
    is an upstream receipt, the manifest's chain digests and head, a signature over that head.
    Every other byte, and every other file (each output, each input file), is compared as is.

    And since onetrace 0.5.0, what the build's throwaway issuer key decides, or a run inside a step
    whose chain holds the clock: a gated step's permit (signed with that key, its expiry from the
    clock) and the issuers file naming the key; an input that is an inner run (`run:<id>`, its
    digest that run's chain head); and a trace file, compared by its spans' names, kinds, attribute
    names and status in order (its ids and times come from the chain head and the clock)."""
    parts = rel.split("/")
    name = parts[2] if len(parts) > 2 else parts[-1]
    if parts[1:2] == ["traces"]:
        doc = json.loads(data)
        return [(s["name"], s["kind"], [a["key"] for a in s["attributes"]], s.get("status"))
                for r in doc["resourceSpans"] for sc in r["scopeSpans"] for s in sc["spans"]]
    if name == "permit-issuers.json":
        doc = json.loads(data)
        for issuer in doc["issuers"]:
            issuer.pop("public_key")
        return doc
    if name not in ("MANIFEST.json", "receipts", "signatures"):
        return data
    doc = json.loads(data)
    if name == "receipts":
        doc.pop("time")
        doc.pop("prev")
        for item in doc["inputs"]:
            if item["name"].startswith(("receipt:", "run:")):
                item.pop("digest")
        for decision in (doc.get("authorization") or {}).get("decisions", []):
            decision.pop("permit", None)
    elif name == "MANIFEST.json":
        doc.pop("chain_head")
        for entry in doc["chain"]:
            entry.pop("digest")
    else:
        doc.pop("chain_head")
        doc.pop("signature")
    return doc


def test_two_builds_are_the_same_apart_from_time(two_builds, examined):
    a, b = two_builds
    files = _files(a / "runs")
    assert files == _files(b / "runs")
    examined(len(files), "files compared across two builds")
    as_is = [rel for rel in files if rel.split("/")[1:2] not in (["MANIFEST.json"], ["receipts"], ["signatures"])
             and not rel.startswith("traces/") and rel != "permit-issuers.json"]
    assert as_is, "outputs and inputs are compared byte for byte"
    for rel in files:
        x, y = (a / "runs" / rel).read_bytes(), (b / "runs" / rel).read_bytes()
        assert _without_time(f"runs/{rel}", x) == _without_time(f"runs/{rel}", y), rel
    assert (a / "trust.json").read_bytes() == (b / "trust.json").read_bytes()


def test_the_comparison_is_not_wider_than_time(two_builds, examined):
    """Sabotage of the comparison itself: a changed output, and a changed receipt field that
    isn't the clock's, each still differ after `_without_time`."""
    a, _ = two_builds
    (out,) = sorted((a / "runs" / "p1-01-baseline-set1").glob("artifacts/*-answer/answers.json"))
    receipt = sorted((a / "runs" / "p1-01-baseline-set1" / "receipts").glob("*.json"))[0]
    examined(2, "planted differences")
    rel = out.relative_to(a).as_posix()
    data = out.read_bytes()
    assert _without_time(rel, data) != _without_time(rel, data.replace(b"a", b"b", 1))
    doc = json.loads(receipt.read_bytes())
    other = copy.deepcopy(doc)
    other["stage"]["name"] = "renamed"
    rel = receipt.relative_to(a).as_posix()
    assert _without_time(rel, json.dumps(doc).encode()) != _without_time(rel, json.dumps(other).encode())


# ------------------------------------------------------------- 2. the build record

def test_a_fresh_build_is_vouched_for(two_builds, examined):
    from onetrace_console.demo_store import check_build_record
    a, _ = two_builds
    record = json.loads((a / "BUILD_RECORD.json").read_text(encoding="utf-8"))
    examined(len(record["files"]), "files the build record holds")
    assert record["covers"] == ["runs", "trust.json"]
    assert check_build_record(a) == []


@pytest.mark.parametrize("change", ["changed", "added", "removed"])
def test_a_hand_edit_after_the_build_is_named(two_builds, tmp_path, change, examined):
    import shutil
    from onetrace_console.demo_store import check_build_record
    folder = tmp_path / "demo"
    shutil.copytree(two_builds[0], folder)
    receipt = folder / "runs" / "p3-23-t-1-rules1" / "receipts" / "02-classify.json"
    rel = receipt.relative_to(folder).as_posix()
    if change == "changed":
        data = bytearray(receipt.read_bytes())
        data[len(data) // 2] ^= 0x01
        receipt.write_bytes(bytes(data))
    elif change == "added":
        rel = rel.replace("02-classify", "99-handmade")
        (folder / rel).write_bytes(receipt.read_bytes())
    else:
        receipt.unlink()
    examined(1, f"file {change} after the build")
    assert check_build_record(folder) == [f"{rel} was {change}"]


def test_a_missing_or_foreign_build_record_vouches_for_nothing(two_builds, tmp_path, examined):
    import shutil
    from onetrace_console.demo_store import BUILD_RECORD, check_build_record
    folder = tmp_path / "demo"
    shutil.copytree(two_builds[0], folder)
    record = folder / BUILD_RECORD
    record.write_text('{"format": "something-else", "covers": [], "files": {}}', encoding="utf-8")
    examined(2, "build records")
    assert check_build_record(folder) == [f"{BUILD_RECORD} is not a build record this console reads"]
    record.unlink()
    assert check_build_record(folder)[0].startswith(f"{BUILD_RECORD} is missing")


# ------------------------------------------------------------- 3. P2 is the reference pipeline, unchanged (Q1)

def test_p2s_outputs_and_text_diff_are_the_committed_runs(two_builds, tmp_path, examined):
    a, _ = two_builds
    pairs = [(EXAMPLE / "runs" / "day-1", a / "runs" / "p2-21-demo-run-1"),
             (EXAMPLE / "runs" / "day-2", a / "runs" / "p2-22-demo-run-2")]
    for committed, built in pairs:
        same = [rel for rel in _files(committed)
                if rel.startswith("artifacts/") or rel in ("documents.json", "test-results.json")]
        examined(len(same), f"output and input files of {built.name}")
        assert same and _files(built / "artifacts") == _files(committed / "artifacts")
        for rel in same:
            assert (built / rel).read_bytes() == (committed / rel).read_bytes(), rel
    from tests.test_checks import _require_installed
    _require_installed()
    import sys
    #: As the console runs the SDK's verbs (compare.py): through `sys.executable -m onetrace`, in a
    #: scratch folder -- the SDK writes `onetrace-report/` where it runs.
    docs = [subprocess.run([sys.executable, "-m", "onetrace", "diff", str(x), str(y), "--text",
                            "--json", "--no-follow"], capture_output=True, check=False,
                           cwd=tmp_path, env=utf8_env()).stdout
            for x, y in ((pairs[0][0], pairs[1][0]), (pairs[0][1], pairs[1][1]))]
    examined(2, "text diffs, production -> staging")
    assert docs[0] and docs[0] == docs[1], "the text diff of the built pair is the committed pair's"


# ------------------------------------------------------------- 4. every run reads as the store's table says

#: The store's table, as the console's own check reads each run: its verdict, the
#: records-agree and signed rungs' states on its case page, the Overview's needs-attention kind,
#: and its state against its baseline. Not set by the builder: each comes from one real action.
TRUSTED, UNSIGNED, UNTRUSTED = "yes", "unsigned", "signed-untrusted"
EXPECTED = {
    **{f"p1-0{n}-baseline-set{n}": ("holds", "yes", TRUSTED, None, "not-compared") for n in range(1, 7)},
    **{f"p1-{n + 6:02d}-candidate-set{n}": ("holds", "yes", TRUSTED, None, "not-compared")
       for n in (1, 3, 4, 5, 6)},
    "p1-08-candidate-set2": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p1-13-baseline-set1-again": ("holds", "yes", TRUSTED, None, "same"),
    "p1-14-candidate-set3-byte-changed": ("contradicts", "no", TRUSTED, "contradicts", "not-compared"),
    "p1-15-candidate-set4-file-deleted": ("contradicts", "no", TRUSTED, "contradicts", "not-compared"),
    #: Its check held without its output files required: rung 1 Not checked, and listed under
    #: not checked in Needs attention first, as the order sentence says.
    "p1-16-candidate-set5-no-artifacts": ("holds", "not-checked", TRUSTED, "not-checked", "not-compared"),
    "p1-17-baseline-set2-unsigned": ("holds", "yes", UNSIGNED, None, "not-compared"),
    "p1-18-baseline-set3-unsigned": ("holds", "yes", UNSIGNED, None, "not-compared"),
    "p1-19-baseline-set4-untrusted-key": ("holds", "yes", UNTRUSTED, None, "not-compared"),
    "p1-20-candidate-set6-answer-failed": ("holds", "yes", TRUSTED, "last-attempt-failed",
                                           "not-compared"),
    "demo-run-1": ("holds", "yes", TRUSTED, None, "not-compared"),
    "demo-run-2": ("holds", "yes", TRUSTED, "changed", "changed"),
    **{f"p3-2{n}-t-{t}-rules1": ("holds", "yes", TRUSTED, None, "not-compared")
       for n, t in ((3, 1), (4, 2), (5, 3), (6, 4))},
    "p3-27-t-1-rules2": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p3-28-t-3-rules1-lookup-retried": ("holds", "yes", TRUSTED, None, "not-compared"),
    #: P4: the stub that varies per run, and the refund window changed two stages later.
    "p4-29-reply-30-days": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p4-30-reply-14-days": ("holds", "yes", TRUSTED, "changed", "changed"),
    #: Declined at policy_check by its own rule, `send` not reached: the check holds, and the
    #: Overview lists it as stopped at a step -- as the run's own page reads rung 3, "Not reached".
    "p4-31-reply-60-days-declined": ("holds", "yes", TRUSTED, "stopped-at-a-step", "not-compared"),
    #: P5, pump maintenance: the calibration offset changed (its first difference calibrate); the
    #: sensor firmware changed and the readings did not (same, the version a changed setting);
    #: declined at work_order, the last declared step, so no declared step is left unreached and
    #: Needs attention first doesn't list it (its page carries the declined chip).
    "p5-32-pump-baseline": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p5-33-pump-offset-changed": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p5-34-pump-firmware-changed": ("holds", "yes", TRUSTED, None, "same"),
    "p5-35-pump-outside-window-declined": ("holds", "yes", TRUSTED, "stopped-at-a-step", "not-compared"),
    #: P6, fill-level inspection: the exposure changed (measure differs, classify comes back the
    #: same); a bottle below the reject line (classify changes after measure).
    "p6-36-fill-baseline": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p6-37-fill-exposure-changed": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p6-38-fill-below-reject-line": ("holds", "yes", TRUSTED, "changed", "changed"),
    #: P7, cold-chain release: one logger reading changed; one byte of a decision changed after
    #: the run closed.
    "p7-39-cold-chain-baseline": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p7-40-cold-chain-one-reading-changed": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p7-41-cold-chain-decision-tampered": ("contradicts", "no", TRUSTED, "contradicts", "not-compared"),
    #: P8, invoice match: the price tolerance changed, 2% to 5% (first difference match); one line's
    #: quantity changed (first difference read_invoice); declined at approve_payment, its last
    #: declared step, as over the approver's limit.
    "p8-42-invoice-tolerance-2pct": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p8-43-invoice-tolerance-5pct": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p8-44-invoice-quantity-changed": ("holds", "yes", TRUSTED, "changed", "changed"),
    "p8-45-invoice-over-limit-declined": ("holds", "yes", TRUSTED, "stopped-at-a-step", "not-compared"),
    #: P9, wheel-bolt torque check: the tool's firmware changed and its readings did not (same, the
    #: version a changed setting); one bolt below the window (first difference read_tool_log).
    "p9-46-torque-baseline": ("holds", "yes", TRUSTED, None, "not-compared"),
    "p9-47-torque-tool-firmware-changed": ("holds", "yes", TRUSTED, None, "same"),
    "p9-48-torque-one-bolt-low": ("holds", "yes", TRUSTED, "changed", "changed"),
    #: P8's two runs broken on purpose (onetrace 0.5.0): paid on a deny; a permit for another amount.
    #: Each contradicts its record on the verifier's own `decisions:` row.
    "p8-49-invoice-paid-on-deny": ("contradicts", "no", TRUSTED, "contradicts", "not-compared"),
    "p8-50-invoice-permit-other-amount": ("contradicts", "no", TRUSTED, "contradicts", "not-compared"),
    #: P10, an agent whose one step calls a sub-agent's run, and P11, the sub-agent's runs: the
    #: amount the sub-agent records changed, two levels down.
    "pz-51-agent-baseline": ("holds", "yes", TRUSTED, None, "not-compared"),
    "pz-52-agent-baseline-subagent": ("holds", "yes", TRUSTED, None, "not-compared"),
    "pz-53-agent-amount-changed": ("holds", "yes", TRUSTED, "changed", "changed"),
    "pz-54-agent-amount-changed-subagent": ("holds", "yes", TRUSTED, None, "not-compared"),
}


def _rungs(case: str) -> dict[str, str]:
    return {html.unescape(re.sub(r"<[^>]+>", "", q)).strip(): state for state, q in
            re.findall(r'<tr data-rung="[^"]*" data-state="([^"]*)"><td>(.*?)</td>', case, re.S)}


def test_every_run_reads_as_the_stores_table_says(built, examined):
    from onetrace_console.overview import attention_kind, pipelines, vs_baseline
    from onetrace_console.store import Store
    store = Store(built / "store" / "store")
    pages = built / "store" / "pages"
    runs = store.runs()
    examined(len(runs), "stored runs read")
    assert sorted(r.run_id for r in runs) == sorted(EXPECTED)
    got = {}
    for run in runs:
        #: The ladder is on "What changed", or on "Proof" for a run whose records don't hold up.
        rungs = _rungs("".join((pages / "runs" / run.key / n).read_text(encoding="utf-8")
                               for n in ("case.html", "proof.html")))
        got[run.run_id] = (run.check_verdict, rungs["Records agree"],
                           rungs["Signed by a known recorder"], attention_kind(run, store),
                           vs_baseline(run, store)[0])
        assert rungs["Committed by a known time"] == "not-anchored", (run.run_id, "every run")
    assert got == EXPECTED
    #: 11 pipelines, labelled P1-P11 in order of first arrival. That order is read from
    #: `received_at`, kept to the second, so two pipelines whose first runs arrive in the same
    #: second take their labels in key order -- which varies from build to build. The demo's
    #: pipelines are held by their stages and runs here, not by the label each one gets.
    found = {(p.stages[0], len(p.runs)) for p in pipelines(store)}
    assert sorted(p.label for p in pipelines(store)) == sorted(f"P{n}" for n in range(1, 12))
    assert found == {("load_docs", 20), ("request", 2), ("intake", 6), ("question", 3),
                     ("readings", 4), ("measure", 3), ("fill_gaps", 3), ("read_invoice", 6),
                     ("read_tool_log", 3), ("agent_step", 2), ("intake", 2)}
    assert len(store.comparisons()) == 15


def test_the_headline_comparison_moves_an_answer_at_split(built, examined):
    """P1's headline pair, chunk_size 1024 against 512: the first difference is split, and an
    answer the pipeline wrote differs -- as produced, never edited."""
    from onetrace_console.demo_store import COMPARISONS
    base, cand = (built / "runs" / name for name in COMPARISONS[0])
    answers = [json.loads(next(r.glob("artifacts/*-answer/answers.json")).read_text(encoding="utf-8"))
               ["answers"] for r in (base, cand)]
    examined(len(answers[0]), "answers compared")
    assert [a["question"] for a in answers[0]] == [a["question"] for a in answers[1]]
    assert any(x["answer"] != y["answer"] for x, y in zip(*answers))


def test_the_retried_lookup_and_the_failed_answer_are_kept(built, examined):
    from onetrace_console.store import Store
    store = Store(built / "store" / "store")
    by_id = {r.run_id: r for r in store.runs()}
    retried = by_id["p3-28-t-3-rules1-lookup-retried"]
    case = (built / "store" / "pages" / "runs" / retried.key / "case.html").read_text(encoding="utf-8")
    failed = (built / "store" / "pages" / "runs" / by_id["p1-20-candidate-set6-answer-failed"].key
              / "case.html").read_text(encoding="utf-8")
    examined(2, "run pages")
    assert "lookup_account ×2" in case and 'data-failed="yes"' in case
    assert "A declared stage's last recorded attempt failed: answer" in html.unescape(failed)


# ------------------------------------------------------------- 5. the keys (Q5)

def test_the_trusted_keys_label_says_what_a_public_seed_proves_and_the_other_key_is_not_trusted(examined):
    from onetrace_console.demo_store import keys
    trust = json.loads(keys.trust_file_bytes())
    examined(len(trust["keys"]), "trust file entries")
    assert trust["keys"] == [{"key_id": keys.key_id(keys.TRUSTED_SEED), "label": keys.TRUSTED_LABEL}]
    assert "public seed" in keys.TRUSTED_LABEL and "not who signed it" in keys.TRUSTED_LABEL
    assert keys.key_id(keys.UNTRUSTED_SEED) != keys.key_id(keys.TRUSTED_SEED)


def test_no_private_key_is_kept_in_the_package(examined):
    files = [p for p in (REPO / "src" / "onetrace_console" / "demo_store").rglob("*") if p.is_file()]
    examined(len(files), "demo store files")
    for p in files:
        assert b"PRIVATE KEY-----" not in p.read_bytes(), p
