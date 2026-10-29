"""Neighbours by input (console 0.5.0 part 6): each rule, held by a test that fails
without its change.

The store here is a few of the demo's runs, recorded and delivered as the console takes them in: P4's
two support replies (one setting apart, so in two groups), P7's cold-chain baseline and the run with one
reading changed (one configuration, near kept inputs), and P3's first ticket, which keeps nothing.

The embedder for most tests is an OpenAI-compatible endpoint (`embedder.Endpoint`, the console's own
code) whose server is a function here: a bag of words, so near texts are near. The local ONNX model is
tested where its files are at hand (`ONETRACE_NEIGHBOURS_MODEL_FILES`); the gate sets it.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SPECS = ("p4-29-reply-30-days", "p4-30-reply-14-days", "p7-39-cold-chain-baseline",
         "p7-40-cold-chain-one-reading-changed", "p3-23-t-1-rules1")
ENDPOINT = {"kind": "endpoint", "base_url": "http://127.0.0.1:9/v1", "model": "bag-of-words"}
#: What names the feature on a page: its sections, its headings and label, its setup page. Not the word
#: "embedder" alone, which a demo pipeline's own record holds as an instrument's kind.
NAMES = re.compile(r'data-section="(?:neighbours|nearness)"|data-neighbours|Runs with near inputs|Neighbours by input|'
                   r"Nearness ladder|/?neighbours/(?:setup|on|off)|embedding model you turned on", re.I)

needs_extra = pytest.mark.skipif(
    not __import__("onetrace_console.neighbours", fromlist=["installed"]).installed(),
    reason="the neighbours extra is not installed: pip install --require-hashes -r requirements-neighbours.lock")


# ------------------------------------------------------------------------------ the store

def bag_of_words(url: str, body: dict) -> dict:
    """The stand-in endpoint: each text a count of its words, hashed into 64 dimensions."""
    out = []
    for i, text in enumerate(body["input"]):
        v = [0.0] * 64
        for w in re.findall(r"[a-z0-9]+", text.lower()):
            v[hashlib.sha256(w.encode()).digest()[0] % 64] += 1.0
        out.append({"index": i, "embedding": v})
    return {"model": body["model"], "data": out}


def _record(names, folder: Path) -> list[Path]:
    from onetrace_console import demo_store
    specs = {s.folder: s for s in demo_store.runs()}
    out = []
    for name in names:
        d = folder / name
        demo_store._record(specs[name], d)
        out.append(d)
    return out


@pytest.fixture(scope="module")
def recorded(tmp_path_factory) -> Path:
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("neighbours-runs")
    _record(SPECS, folder)
    return folder


def _store(recorded: Path, root: Path):
    from onetrace_console.compare import compare
    from onetrace_console.config import Config
    from onetrace_console.folder_load import deliver_one
    from onetrace_console.store import Store
    store = Store(root / "store")
    config = Config(sign_in={**Config().sign_in, "enabled": False})
    runs = {}
    for name in SPECS:
        got = deliver_one(recorded / name, store, config)
        assert got.run is not None, got.refused
        runs[name] = got.run
    compare(runs["p7-39-cold-chain-baseline"], runs["p7-40-cold-chain-one-reading-changed"], store)
    compare(runs["p4-29-reply-30-days"], runs["p4-30-reply-14-days"], store)
    return store, runs


@pytest.fixture(scope="module")
def held(recorded, tmp_path_factory):
    """The store, with neighbours off."""
    return _store(recorded, tmp_path_factory.mktemp("neighbours-store"))


@pytest.fixture
def on(held, monkeypatch, tmp_path):
    """A copy of the store with neighbours on, through the stand-in endpoint, every kept text embedded."""
    from onetrace_console.neighbours import batches, embedder, settings
    from onetrace_console.store import Store
    store, runs = held
    shutil.copytree(store.root, tmp_path / "store")
    copy = Store(tmp_path / "store")
    monkeypatch.setattr(embedder, "_post_json", bag_of_words)
    settings.turn_on(copy, ENDPOINT, who="a test", confirmed=settings.confirmation(ENDPOINT))
    batches.refresh(copy)
    return copy, {n: copy.get_run(r.key) for n, r in runs.items()}


def _comparison(store, a, b):
    return next(c for c in store.comparisons() if (c.run_a, c.run_b) == (a.key, b.key))


def _case(run, store) -> str:
    from onetrace_console.pages import CASE, render_execution
    with store.reading():
        return render_execution(run, store, generated_at="2026-10-28T00:00:00Z").pages[CASE]


def _diff(comparison, store) -> str:
    from onetrace_console.render import render_diff
    with store.reading():
        return render_diff(comparison, store, generated_at="2026-10-28T00:00:00Z")


def _absent(monkeypatch):
    """The extra's packages not found, as on a base install."""
    import importlib.util
    real = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name, *a, **k: None if name in ("onnxruntime", "tokenizers", "numpy") else real(name, *a, **k))


# ------------------------------------------------------------------------------ 2. the extra

def test_the_base_install_gains_no_dependency():
    import tomllib
    project = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["dependencies"] == ["onetrace==0.6.0", "onetrace-verify[crypto]==0.6.0"]
    assert project["optional-dependencies"] == {
        "neighbours": ["onnxruntime==1.31.0", "tokenizers==0.23.3", "numpy==2.5.4"]}
    base = (REPO / "requirements.lock").read_text(encoding="utf-8")
    assert not re.search(r"^(onnxruntime|tokenizers|numpy|huggingface)", base, re.M)


def test_the_extra_is_pinned_by_hash_in_its_own_lock():
    lock = (REPO / "requirements-neighbours.lock").read_text(encoding="utf-8")
    pins = re.findall(r"^([a-z0-9-]+)==(\S+)", lock, re.M)
    assert {"onnxruntime": "1.31.0", "tokenizers": "0.23.3", "numpy": "2.5.4"}.items() <= dict(pins).items()
    assert "torch" not in dict(pins)
    #: Every pin carries at least one hash, and no line names an index or a URL.
    for block in re.split(r"\n(?=[a-z0-9-]+==)", lock.split("\n", 1)[1]):
        if re.match(r"[a-z0-9-]+==", block):
            assert "--hash=sha256:" in block, block
    assert "://" not in "".join(l for l in lock.splitlines() if not l.startswith("#"))
    #: A name both locks pin is the same version.
    base = dict(re.findall(r"^([a-z0-9-]+)==(\S+)", (REPO / "requirements.lock").read_text(encoding="utf-8"), re.M))
    assert all(base[n] == v for n, v in pins if n in base)


def test_the_console_never_imports_the_extra_until_it_is_on():
    """Importing the console, drawing its pages' code and asking whether neighbours exist imports none of
    the extra's packages, nor huggingface_hub, which tokenizers brings and the console never uses."""
    code = ("import sys, onetrace_console.serve, onetrace_console.render, onetrace_console.pages, "
            "onetrace_console.neighbours.pages as p, onetrace_console.neighbours as n; n.installed(); "
            "print(sorted(m for m in ('onnxruntime','tokenizers','numpy','huggingface_hub') if m in sys.modules))")
    out = subprocess.run([sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(REPO / 'src')!r}); {code}"],
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


@needs_extra
def test_with_the_extra_absent_no_page_has_a_word_of_it(on, monkeypatch):
    store, runs = on
    #: The sabotage first: with the extra present the pages do name it, so the check below can see it.
    assert NAMES.search(_case(runs["p7-40-cold-chain-one-reading-changed"], store))
    _absent(monkeypatch)
    from onetrace_console import neighbours
    assert not neighbours.installed()
    for run in runs.values():
        assert not NAMES.search(_case(run, store)), run.run_id
    for c in store.comparisons():
        assert not NAMES.search(_diff(c, store))


def test_with_the_extra_absent_no_route_answers(server, monkeypatch):
    import urllib.error
    import urllib.request
    base, _root = server
    _absent(monkeypatch)

    def ask(path, data=None):
        try:
            r = urllib.request.urlopen(urllib.request.Request(base + path, data=data), timeout=30)
            return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
    #: Exactly what a page or a route the console never had answers.
    assert ask("/neighbours/setup") == (404, b"not rendered: neighbours/setup\n")
    assert ask("/neighbours/on", b"embedder=all-MiniLM-L6-v2") == ask("/no-such-route", b"x") == (404, b"no such route\n")
    assert ask("/neighbours/off", b"") == (404, b"no such route\n")


def test_without_the_extra_the_feature_does_not_exist(monkeypatch):
    from onetrace_console import neighbours
    _absent(monkeypatch)
    assert not neighbours.exists(public=False)
    assert not neighbours.here()
    assert not neighbours.active(object())


# ------------------------------------------------------------------------------ 3. grouping

def test_a_group_is_every_steps_configuration_exactly(held):
    from onetrace_console.neighbours import grouping
    store, runs = held
    with store.reading():
        sig = grouping.signatures(store)
        #: P7's two runs: one configuration, inputs apart. P4's two: `refund_days` apart, two groups.
        assert sig[runs["p7-39-cold-chain-baseline"].key] == sig[runs["p7-40-cold-chain-one-reading-changed"].key]
        assert sig[runs["p4-29-reply-30-days"].key] != sig[runs["p4-30-reply-14-days"].key]
        assert grouping.group_of(store, runs["p4-29-reply-30-days"].key) == []
        p = grouping.parts(runs["p4-29-reply-30-days"], store)
    settings = {k for s in p["steps"] for k in s["settings"]}
    assert "refund_days" in settings and not any(k.startswith("onetrace.") for k in settings)
    assert set(p) == {"plan", "steps"}
    #: Inputs and outputs are never part of it.
    assert "digest" not in json.dumps(p["steps"]).replace("config_digest", "")


def test_the_signature_reads_the_run_indexs_own_settings(held, monkeypatch):
    """A setting is what part 1's run index reads as one: changing that reading changes the groups."""
    from onetrace_console import run_index
    from onetrace_console.neighbours import grouping
    store, runs = held
    a, b = runs["p4-29-reply-30-days"], runs["p4-30-reply-14-days"]
    monkeypatch.setattr(run_index, "_settings", lambda receipt: {})
    assert grouping.signature(a, store) == grouping.signature(b, store)


# ------------------------------------------------------------------------------ 4. what is embedded

def test_only_kept_files_are_embedded_never_a_record(held):
    from onetrace_console.neighbours import kept
    from onetrace_console.stage_pages import _steps
    store, runs = held
    seen = 0
    for run in runs.values():
        steps = _steps(run, store)
        recorded = {str(i.get("digest")) for s in steps for k in ("inputs", "outputs")
                    for i in s["receipt"].get(k) or [] if not str(i.get("name", "")).startswith("receipt:")}
        receipts = {json.dumps(s["receipt"]) for s in steps}
        for p in kept.parts(run, store):
            if p.text is None:
                continue
            seen += 1
            #: Each text is a kept file's, by the digest the record gives it, and no receipt's bytes.
            assert p.digest in recorded and "sha256:" + hashlib.sha256(p.data).hexdigest() == p.digest
            assert p.text not in receipts and not p.text.startswith('{"assertions"')
    assert seen


@needs_extra
def test_a_run_that_kept_nothing_has_nothing_embedded_and_its_page_says_so(on):
    from onetrace_console.neighbours import kept
    store, runs = on
    run = runs["p3-23-t-1-rules1"]
    assert all(p.text is None for p in kept.parts(run, store))
    page = _case(run, store)
    assert "This run kept no input, so it has no neighbours." in page


def test_outputs_are_kept_only_under_the_input_opt_in(held):
    """A run that keeps an input has its stored outputs read; one that keeps none has none read."""
    from onetrace_console.neighbours import kept
    store, runs = held
    p7 = kept.parts(runs["p7-39-cold-chain-baseline"], store)
    assert any(p.kind == kept.OUTPUT and p.text is not None for p in p7)
    p3 = kept.parts(runs["p3-23-t-1-rules1"], store)
    assert any(p.kind == kept.OUTPUT for p in p3) and not any(p.text for p in p3)


# ------------------------------------------------------------------------------ the derived file

@needs_extra
def test_deleting_the_derived_file_and_rebuilding_gives_the_same_results(on):
    from onetrace_console.neighbours import batches, nearness
    store, runs = on
    path = Path(store.root) / "neighbours" / batches.DERIVED
    before = path.read_bytes()
    run = runs["p7-40-cold-chain-one-reading-changed"]
    with store.reading():
        said = [(r.other.key, r.name, r.near) for r in nearness.suggestions(run, store).rows]
    path.unlink()
    batches.rebuild(store)
    assert path.read_bytes() == before
    with store.reading():
        assert [(r.other.key, r.name, r.near) for r in nearness.suggestions(run, store).rows] == said
    assert said


@needs_extra
def test_a_changed_embedder_invalidates_the_vectors(on, monkeypatch):
    from onetrace_console.neighbours import batches, embedder, settings
    store, _runs = on
    first = batches.current(store)
    assert first[1]
    other = {**ENDPOINT, "model": "another-model"}
    settings.turn_off(store)
    settings.turn_on(store, other, who="a test", confirmed=settings.confirmation(other))
    who, vectors = batches.current(store)
    assert who != first[0] and vectors == {}
    assert batches.refresh(store) == len(first[1])
    assert set(batches.current(store)[1]) == set(first[1])


# ------------------------------------------------------------------------------ 5. batches are runs

@needs_extra
def test_each_embedding_batch_is_a_recorded_run_with_a_model_call_record_per_text(on):
    from onetrace import model_call
    from onetrace_console.checks import HOLDS, check
    store, _runs = on
    runs = sorted((Path(store.root) / "neighbours" / "runs").iterdir())
    assert runs
    texts = 0
    for folder in runs:
        assert check(folder).verdict == HOLDS, folder.name
        receipt = json.loads((folder / "receipts" / "01-embed.json").read_text(encoding="utf-8"))
        names = [o["name"] for o in receipt["outputs"]]
        inputs = [i for i in receipt["inputs"] if i["name"].startswith("text-")]
        records = [n for n in names if model_call.naming.is_record_name(n)]
        assert len(records) == len(inputs) and "embedder.json" in names and "vectors.json" in names
        texts += len(inputs)
        for n in records:
            rec = model_call.load(folder / "artifacts" / "01-embed" / n)
            model_call.validate(rec)
            assert rec["call.kind"] == "self-hosted" and rec["credential"] == "absent"
            assert rec["fingerprints"] == []
        #: The batch keeps no text: its inputs are digests only.
        assert not (folder / "inputs").exists()
    from onetrace_console.neighbours import batches
    assert texts == len(batches.wanted(store))


@needs_extra
def test_the_local_records_fields_are_honest(tmp_path):
    """The local embedder's record, built without its files: every field it cannot observe says so."""
    from onetrace import model_call
    from onetrace_console.neighbours import embedder
    local = embedder.Local.__new__(embedder.Local)
    local.model = embedder.MODELS[embedder.DEFAULT]
    local.max_length, local.engine_version, local.threads = 256, "1.31.0", 8
    local.files_digest = local.tokenizer_digest = "sha256:" + "0" * 64
    local.output = type("O", (), {"type": "tensor(float)"})()
    local.session = type("S", (), {"get_providers": lambda self: ["CPUExecutionProvider"]})()
    ident = local.identity()
    assert ident["call.api"] == "onnxruntime.InferenceSession.run"
    assert ident["model.files_digest"]["status"] == model_call.OBSERVED
    assert ident["runtime.torch"]["status"] == model_call.NOT_APPLICABLE
    assert ident["engine.settings.max_length"]["value"] == "256"


# ------------------------------------------------------------------------------ 6. the pages

@needs_extra
def test_a_run_page_lists_its_neighbours_with_a_number_and_compare(on):
    store, runs = on
    page = _case(runs["p7-40-cold-chain-one-reading-changed"], store)
    assert "Runs with near inputs (same configuration): 1" in page
    row = re.search(r'<tr data-neighbour="([0-9a-f]{64})">(.*?)</tr>', page, re.S)
    assert row.group(1) == runs["p7-39-cold-chain-baseline"].key
    assert re.search(r'data-nearness="(embedder">[01]\.\d\d\d|record">)', row.group(2))
    assert "suggested by an embedding model you turned on; the comparison itself is exact" in row.group(2)
    assert "Compare" in row.group(2)
    #: Another configuration's run is never offered.
    other = _case(runs["p4-29-reply-30-days"], store)
    assert "Runs with near inputs (same configuration): 0" in other and "data-neighbour=" not in other


@needs_extra
def test_the_nearness_ladder_beside_the_exact_one(on, held):
    store, runs = on
    a, b = runs["p7-39-cold-chain-baseline"], runs["p7-40-cold-chain-one-reading-changed"]
    page = _diff(_comparison(store, a, b), store)
    section = re.search(r'<section data-section="nearness".*?</section>', page, re.S).group(0)
    for column in ("Input nearness", "Output nearness", "Drop", "Exact difference at this step"):
        assert column in section
    assert section.count("data-largest-drop") == 1
    marked = re.search(r"<tr [^>]*data-largest-drop>.*?</tr>", section, re.S).group(0)
    assert "digest differs" in marked
    #: Nothing else on the page moved: without the section it is the page drawn with neighbours off.
    off_store, off_runs = held
    off = _diff(_comparison(off_store, off_runs["p7-39-cold-chain-baseline"],
                            off_runs["p7-40-cold-chain-one-reading-changed"]), off_store)
    assert re.sub(r"\n?" + re.escape(section), "", page) == off
    #: Two runs of another configuration each are not neighbours: no ladder.
    assert 'data-section="nearness"' not in _diff(
        _comparison(store, runs["p4-29-reply-30-days"], runs["p4-30-reply-14-days"]), store)


@needs_extra
def test_equal_fingerprints_are_one_by_the_record_and_not_embedded(on):
    from onetrace_console.neighbours import kept, nearness
    store, runs = on
    a, b = runs["p7-39-cold-chain-baseline"], runs["p7-40-cold-chain-one-reading-changed"]
    #: Equal digests: 1.00 by the record, with no text and no vector at all.
    nothing = type("P", (), {"digest": "sha256:x", "text": None})()
    assert nearness.near(nothing, nothing, {}) == nearness.Near(1.0, nearness.BY_RECORD)
    #: On the ladder, a number is by the record exactly where the two runs' digests are equal.
    with store.reading():
        rungs = nearness.ladder(_comparison(store, a, b), store)
        pa, pb = kept.parts(a, store), kept.parts(b, store)
    for r in rungs:
        for kind, n in ((kept.INPUT, r.inputs), (kept.OUTPUT, r.outputs)):
            da = {p.name: p.digest for p in pa if p.step == r.step and p.kind == kind}
            db = {p.name: p.digest for p in pb if p.step == r.step and p.kind == kind}
            assert (n is not None and n.how == nearness.BY_RECORD) == (bool(da) and da == db), (r.step, kind)
    #: A step that kept nothing has no number: "not kept".
    off = nearness.Rung("s", None, None)
    assert off.drop is None and nearness.largest_drop([off]) is None


@needs_extra
def test_no_threshold_and_no_word_of_cause(on):
    store, runs = on
    page = _case(runs["p7-40-cold-chain-one-reading-changed"], store) + _diff(
        _comparison(store, runs["p7-39-cold-chain-baseline"], runs["p7-40-cold-chain-one-reading-changed"]), store)
    shown = " ".join(re.findall(r'<section data-section="(?:neighbours|nearness)".*?</section>', page, re.S))
    assert shown
    for word in ("caused", "because", "threshold", "same input", "the change that", "changed the answer",
                 "likely", "probably", "offline"):
        assert word not in shown.lower(), word


# ------------------------------------------------------------------------------ 7. never public

@needs_extra
def test_a_public_drawing_names_nothing_even_with_neighbours_on(on, monkeypatch):
    from onetrace_console.frame import rendering
    from onetrace_console import neighbours
    store, runs = on
    run = runs["p7-40-cold-chain-one-reading-changed"]
    c = _comparison(store, runs["p7-39-cold-chain-baseline"], run)
    with rendering(onedoor=False, sign_in=False, public=True):
        assert not NAMES.search(_case(run, store)) and not NAMES.search(_diff(c, store))
    #: Sabotage: the gate that ignores public drawing lets the feature onto the public page.
    monkeypatch.setattr(neighbours, "drawing_public", lambda: False)
    with rendering(onedoor=False, sign_in=False, public=True):
        assert NAMES.search(_case(run, store))


@needs_extra
def test_a_static_export_names_nothing(on):
    from onetrace_console.explain import no_presses
    store, runs = on
    with no_presses():
        assert not NAMES.search(_case(runs["p7-40-cold-chain-one-reading-changed"], store))


def test_a_public_console_refuses_a_store_with_an_embedder(shared_demo, tmp_path):
    from tests.conftest import demo_copy
    from onetrace_console.config import Config
    from onetrace_console.public import start_refusal
    folder = demo_copy(shared_demo, tmp_path / "demo")
    config = Config(public=True, trust_file=str(folder / "trust.json"),
                    sign_in={**Config().sign_in, "enabled": False})
    store_root = folder / "store"
    assert start_refusal(config, store_root) is None
    (store_root / "store" / "neighbours").mkdir()
    said = start_refusal(config, store_root)
    assert said is not None and "embedder" in said.message


def test_a_public_console_has_no_route(monkeypatch, tmp_path):
    """On a public console neither route answers, the extra installed or not: GET is not a page, and
    POST is refused before its body is read, as every write there is."""
    from onetrace_console import neighbours
    assert not neighbours.exists(public=True)
    import onetrace_console.serve as serve
    handler = serve.Handler.__new__(serve.Handler)
    handler.config = type("C", (), {"public": True})()
    assert handler._neighbours() is False
    #: Sabotage: a gate that ignored public would answer.
    monkeypatch.setattr(neighbours, "exists", lambda public: True)
    assert handler._neighbours() is True


#: The first pattern this module had, kept to say why it was replaced: it matched the word "embedder"
#: anywhere, and the demo's own P1 records an instrument of that kind, shown on its public pages.
TOO_BROAD = re.compile(r"neighbour|near input|nearness|embedd", re.I)


def test_the_public_page_check_catches_each_planted_marker(shared_demo):
    """Sabotage for the check below: each marker of the feature, planted on a real public page, is caught;
    and the first pattern, too broad, matched the public pages with nothing planted."""
    from onetrace_console.neighbours import pages as words
    page = next(p for p in sorted(Path(shared_demo["folder"]).rglob("case.html"))).read_text(encoding="utf-8")
    assert not NAMES.search(page)
    planted = (f"<h2>{words.heading(1)}</h2>", f'<span class="note">{words.LABEL}</span>',
               f'<a href="../../{words.PATH}">{words.TURN_ON}</a>', f"<p>{words.OFF}</p>",
               f"<h2>{words.LADDER_TITLE}</h2>", '<section data-section="neighbours">',
               '<section data-section="nearness">', '<form method="post" action="/neighbours/on">')
    for marker in planted:
        at = page.index("</main>")
        assert NAMES.search(page[:at] + marker + page[at:]), marker
    every = " ".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in Path(shared_demo["folder"]).rglob("*.html"))
    assert TOO_BROAD.search(every).group(0).lower() == "embedd" and not NAMES.search(every)


def test_the_public_demo_build_has_no_embedder(shared_demo):
    assert not list(Path(shared_demo["folder"]).rglob("neighbours"))
    pages = " ".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in Path(shared_demo["folder"]).rglob("*.html"))
    assert not NAMES.search(pages)


# ------------------------------------------------------------------------------ 8. words

#: The feature's page in this repository's docs/, which the public export leaves out as it leaves out every
#: doc but the README's images: read where it is here, as tests/test_pins.py reads PINS.md.
DOC = REPO / "docs" / "neighbours.md"


def test_the_non_claims_word_for_word_on_the_setup_page_and_in_the_docs(held, monkeypatch):
    from onetrace_console.neighbours import NON_CLAIMS
    from onetrace_console.neighbours.pages import setup_page
    from onetrace_console.words import escape
    store, _ = held
    page = setup_page(store)
    note = DOC.read_text(encoding="utf-8").replace("\n", " ") if DOC.is_file() else None
    for claim in NON_CLAIMS:
        assert escape(claim) in page and (note is None or claim in note)


def test_the_operator_readme_says_what_the_extra_is_and_what_it_is_not():
    """The operator README, which the export carries where docs/neighbours.md is left out: what the
    extra is, how to install it, local only and off by default, the four non-claims word for word, and
    the setup page; and the image it describes installs no extra."""
    from onetrace_console.neighbours import NON_CLAIMS
    text = (REPO / "OPERATOR_README.md").read_bytes().decode("utf-8")
    head = "## Neighbours by input: an optional extra, local only"
    assert text.count(head) == 1
    section = text.split(head, 1)[1].split("\r\n## ", 1)[0]
    for claim in NON_CLAIMS:
        assert f"- {claim}\r\n" in section, claim
    for said in ("`onetrace-console[neighbours]`", "python -m pip install --require-hashes -r requirements-neighbours.lock",
                 "**Local only.**", "**Off by default.**", "`/neighbours/setup`"):
        assert said in section, said
    assert "neighbours" not in (REPO / "deploy" / "fly" / "Dockerfile").read_text(encoding="utf-8")
    #: As the README says them: what turning it on fetches, and the ladder's two fixed readings.
    from onetrace_console.neighbours.pages import BY_RECORD, NEAR_ONE
    flat = " ".join(section.split())
    for said in ("pinned files, once, from huggingface.co at the pinned revision", "no text leaves the machine",
                 f'"{BY_RECORD}": the two runs\' digests for that file are equal',
                 f'"{NEAR_ONE}": the digests are not equal', "Neither is a judgement that two runs did the same thing"):
        assert said in flat, said


def test_no_network_calls_only_after_the_fetch_and_never_offline():
    texts = [DOC.read_text(encoding="utf-8")] if DOC.is_file() else []
    texts += [p.read_text(encoding="utf-8") for p in (REPO / "src" / "onetrace_console" / "neighbours").glob("*.py")]
    for t in texts:
        assert "offline" not in t.lower()
        for m in re.finditer(r"no network calls", t, re.I):
            assert re.search(r"after the files are fetched", t[max(0, m.start() - 120):m.end()], re.I), t[m.start() - 120:m.end()]


# ------------------------------------------------------------------------------ the embedder's files

def _small_model():
    from onetrace_console.neighbours.embedder import Model
    data = {"onnx/model.onnx": b"weights", "tokenizer.json": b"{}"}
    return Model("tiny", "example/tiny", "0" * 40, "mean", "none",
                 {p: hashlib.sha256(d).hexdigest() for p, d in data.items()}), data


def test_each_file_is_checked_by_sha256_and_a_mismatch_refuses_by_name(tmp_path):
    from onetrace_console.neighbours import embedder
    model, data = _small_model()
    asked = []

    def get(url):
        asked.append(url)
        path = url.split(f"/resolve/{model.revision}/", 1)[1]
        return b"tampered" if path == "tokenizer.json" else data[path]
    with pytest.raises(embedder.Refused, match=r"tokenizer\.json as fetched has sha256 "):
        embedder.fetch(tmp_path, model, get=get)
    assert not (embedder.folder(tmp_path, model) / "tokenizer.json").exists()
    assert all(u.startswith(f"https://huggingface.co/example/tiny/resolve/{model.revision}/") for u in asked)
    embedder.fetch(tmp_path, model, get=lambda url: data[url.rsplit(f"{model.revision}/", 1)[1]])
    (embedder.folder(tmp_path, model) / "onnx" / "model.onnx").write_bytes(b"changed")
    with pytest.raises(embedder.Refused, match=r"onnx/model\.onnx has sha256 .* not the pinned"):
        embedder.check(tmp_path, model)


def test_the_pins_are_the_rulings(monkeypatch):
    from onetrace_console.neighbours import embedder
    d, a = embedder.MODELS[embedder.DEFAULT], embedder.MODELS[embedder.ALTERNATE]
    assert (d.repo, d.revision, d.pooling) == ("sentence-transformers/all-MiniLM-L6-v2",
                                               "1110a243fdf4706b3f48f1d95db1a4f5529b4d41", "mean")
    assert d.files["onnx/model.onnx"] == "6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452"
    assert (a.repo, a.revision, a.pooling) == ("BAAI/bge-small-en-v1.5", "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a", "cls")
    assert a.files["onnx/model.onnx"] == "828e1496d7fabb79cfa4dcd84fa38625c0d3d21da474a00f08db0f559940cf35"
    #: The maximum length is read from the model's own configuration, never written here.
    assert "max_seq_length" in Path(embedder.__file__).read_text(encoding="utf-8")
    assert not re.search(r"max_length\s*=\s*\d", Path(embedder.__file__).read_text(encoding="utf-8"))


def test_turning_on_needs_the_confirmation_that_names_the_embedder(held, tmp_path):
    from onetrace_console.neighbours import embedder, settings
    from onetrace_console.store import Store
    store = Store(tmp_path / "store")
    local = {"kind": "local", "model": embedder.DEFAULT}
    words = settings.confirmation(local)
    assert "sentence-transformers/all-MiniLM-L6-v2" in words and "1110a243fdf4706b3f48f1d95db1a4f5529b4d41" in words
    assert "kept inputs" in words and "this machine" in words
    for wrong in ("", "yes", settings.confirmation(ENDPOINT)):
        with pytest.raises(embedder.Refused):
            settings.turn_on(store, local, who="a test", confirmed=wrong, get=lambda url: pytest.fail("fetched"))
    assert settings.read(store) is None
    with pytest.raises(embedder.Refused):
        settings.choose({"embedder": "endpoint", "base_url": "http://user:pw@127.0.0.1/v1", "model": "m"})
    #: No hosted provider is offered or named.
    from onetrace_console.neighbours.pages import setup_page
    assert not re.search(r"openai\.com|api\.|cohere|voyage|anthropic", setup_page(store), re.I)


def test_off_by_default_and_off_draws_every_page_as_before(held, monkeypatch):
    """Off is the default, and off, every run page and comparison is the page drawn without the extra."""
    from onetrace_console.neighbours import settings
    store, runs = held
    assert settings.read(store) is None
    pages = [_case(r, store) for r in runs.values()] + [_diff(c, store) for c in store.comparisons()]
    assert not any(NAMES.search(p) for p in pages)
    _absent(monkeypatch)
    assert [_case(r, store) for r in runs.values()] + [_diff(c, store) for c in store.comparisons()] == pages


@needs_extra
def test_the_setup_page_turns_it_on_and_off_over_http(server, monkeypatch):
    import urllib.error
    import urllib.parse
    import urllib.request
    from onetrace_console.neighbours import embedder, settings
    from onetrace_console.serve import Handler
    base, _root = server
    monkeypatch.setattr(embedder, "_post_json", bag_of_words)
    page = urllib.request.urlopen(base + "/neighbours/setup?" + urllib.parse.urlencode(
        {"embedder": "endpoint", "base_url": ENDPOINT["base_url"], "model": ENDPOINT["model"]}), timeout=30).read().decode()
    words = settings.confirmation(ENDPOINT)
    assert f'value="{words}"' in page.replace("&#x27;", "'")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    body = urllib.parse.urlencode({"embedder": "endpoint", "base_url": ENDPOINT["base_url"],
                                   "model": ENDPOINT["model"], "confirmed": words}).encode()
    with pytest.raises(urllib.error.HTTPError) as got:
        opener.open(urllib.request.Request(base + "/neighbours/on", data=body), timeout=60)
    assert got.value.code == 303
    assert settings.read(Handler.store)["embedder"] == ENDPOINT
    with pytest.raises(urllib.error.HTTPError) as got:
        opener.open(urllib.request.Request(base + "/neighbours/off", data=b""), timeout=60)
    assert got.value.code == 303 and settings.read(Handler.store) is None


def test_an_embedder_number_that_rounds_to_one_never_reads_as_the_record_s_equality():
    """1.000 is never shown: an embedder's number at 0.9995 or more, where the digests differ, reads
    "≥ 0.9995, digests differ"; the record's equality reads "1.00 by the record"; below, three places."""
    import html as _html
    from onetrace_console.neighbours import pages as np_pages
    from onetrace_console.neighbours.nearness import BY_EMBEDDER, BY_RECORD, Near
    said = lambda v, how=BY_EMBEDDER: _html.unescape(re.sub(r"<[^>]+>", "", np_pages._number(Near(v, how))))
    for v in (0.9995, 0.99996, 1.0, 1.0000002):
        assert said(v) == "≥ 0.9995, digests differ", v
    assert said(0.99949) == "0.999" and said(0.997) == "0.997"
    assert said(1.0, BY_RECORD) == "1.00 by the record"
    assert "1.000" not in said(0.9999)


# ------------------------------------------------------------------------------ the local model

MODEL_FILES = os.environ.get("ONETRACE_NEIGHBOURS_MODEL_FILES", "")


@needs_extra
@pytest.mark.skipif(not MODEL_FILES, reason="ONETRACE_NEIGHBOURS_MODEL_FILES names no folder of the model's "
                                           "files (the gate sets it; the suite never fetches them)")
def test_the_local_model_embeds_on_the_cpu(tmp_path):
    import numpy as np
    from onetrace_console.neighbours import embedder
    for name in (embedder.DEFAULT, embedder.ALTERNATE):
        model = embedder.MODELS[name]
        shutil.copytree(embedder.folder(Path(MODEL_FILES), model), embedder.folder(tmp_path, model))
        local = embedder.Local(tmp_path, model)
        assert local.session.get_providers() == ["CPUExecutionProvider"]
        batch = local.embed(["The kettle leaks.", "My kettle is leaking.", "Torque the wheel bolts to 120 Nm."])
        v = np.stack(batch.vectors)
        assert v.shape == (3, 384) and np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-5)
        assert v[0] @ v[1] > v[0] @ v[2]
        from onetrace import model_call
        for row in batch.rows:
            model_call.validate({"format": model_call.FORMAT, **batch.shared, **row, "fingerprints": []})
