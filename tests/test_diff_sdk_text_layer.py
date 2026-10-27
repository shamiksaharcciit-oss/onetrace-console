"""The Diff page's layer of the SDK's text, as it stands with the 0.2.0 SDK.

A review found the Diff page's layer of the SDK's text carrying a record's CR, LF and TAB, because
the SDK prints some record words SHORTENED (12 characters of an output or config digest, a document
id's tail). The console then rebuilt the layer with `text()` over a copy of the report with every
string escaped first.

Since 0.2.0 the SDK does that itself: `text()` escapes every record-derived string one-to-one
before drawing (`onetrace.escaping`), with a class covering everything the console
escaped and more (`tests/test_sdk_escaping_class.py`). So the console shows the SDK's stored text
AS IT IS, ONCE -- where `text()` over the stored JSON gives exactly that text -- and its own pass is
retired. And the 0.2.0 verifier refuses the reviewer's forged digest outright, so the
test that delivered it now shows the check refusing it and the SDK refusing to compare.
Where the SDK wrote no JSON, or its text is not what its JSON gives, the whole text is shown
escaped, line breaks included, and the page says so -- unchanged.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import re
import tarfile
from dataclasses import replace as swap
from pathlib import Path

import pytest

from onetrace_console.compare import DIFF, LOCALIZE, compare, report_json, report_text
from onetrace_console.render import render_diff
from tests.conftest import server  # noqa: F401  (fixture)
from tests.test_checks import FIXED_RAN_AT
from tests.test_pages import GENERATED_AT
from tests.test_unreadable import _stored

#: The reviewer's forged output digest: CR, LF and TAB inside the 12 characters the SDK shows.
FORGED = "sha256:ab\r\nFORGED\tROW\r\n" + "0" * 40
RAW = ("\r", "\t", "\x00", "\x1b", "\x85", "‮", "⁦")


def _sdk_run(out: Path, run_id: str) -> None:
    from onetrace.emit import Instrument, Recorder
    code = out.parent / "pipeline.py"
    code.write_text("# the pipeline\n", encoding="utf-8")
    rec = Recorder(out, run_id=run_id, declared_stages=["alpha", "beta"], manifest=code,
                   policy="fail-closed", anchor_reason="a test")

    @rec.stage("alpha", Instrument("a-tool", "transform", "1.0.0", {"k": "1"}))
    def alpha(ctx):
        return ctx.write_json("a.json", {"v": "1"})

    @rec.stage("beta", Instrument("b-tool", "transform", "1.0.0", {"k": "same"}))
    def beta(ctx, x):
        return ctx.write_json("b.json", ctx.read_json(x))

    beta(alpha())
    rec.close()


def _rechain(out: Path) -> None:
    """The reviewer's probe_nb2_digest.py: the first receipt's output digest forged, and the run
    re-chained with the SDK's own canonical form, so the pinned verifier passes it."""
    from onetrace.canonical import canonicalize, digest
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    prev = None
    for i, entry in enumerate(manifest["chain"]):
        path = out / entry["file"]
        receipt = json.loads(path.read_text(encoding="utf-8"))
        if i == 0:
            receipt["outputs"][0]["digest"] = FORGED
        receipt["prev"] = prev
        raw = canonicalize(receipt)
        path.write_bytes(raw)
        entry["digest"] = prev = digest(raw)
    manifest["chain_head"] = prev
    (out / "MANIFEST.json").write_bytes(canonicalize(manifest))


def _files(out: Path) -> dict[str, bytes]:
    files = {p.relative_to(out).as_posix(): p.read_bytes() for p in sorted(out.rglob("*"))
             if p.is_file() and p.name != ".lock"}
    files["SHA256SUMS"] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {n}"
                                     for n, b in files.items()) + "\n").encode()
    return files


def _tar(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        for n, b in files.items():
            info = tarfile.TarInfo(n)
            info.size = len(b)
            t.addfile(info, io.BytesIO(b))
    return buf.getvalue()


def _forged_pair(tmp_path: Path, *, artifacts: bool = False) -> tuple[dict, dict]:
    """The baseline, and the candidate with its first output digest forged.

    `onetrace-verify` 0.1.2 checks each output file against its digest when the run carries
    `artifacts/`, and a forged digest then FAILs, with the record's CR/LF
    in the row. So the candidate is delivered **without** `artifacts/` by default: it holds, with
    `run: artifacts` NOT-RUN, and the SDK's diff draws its layer -- the page these NB2 tests are
    about. `artifacts=True` keeps them, for the rule on rows a record broke apart."""
    _sdk_run(tmp_path / "a", "nb2-base")
    _sdk_run(tmp_path / "b", "nb2-cand")
    _rechain(tmp_path / "b")
    b = _files(tmp_path / "b")
    if not artifacts:
        b = {n: v for n, v in b.items() if not n.startswith("artifacts/") and n != "SHA256SUMS"}
        b["SHA256SUMS"] = ("\n".join(f"{hashlib.sha256(v).hexdigest()}  {n}"
                                     for n, v in b.items()) + "\n").encode()
    return _files(tmp_path / "a"), b


def _both_views(path) -> str:
    """A comparison page's two views together: the SDK's reports as it wrote them are on "Proof"."""
    return path.read_bytes().decode() + path.with_name(path.stem + "-proof.html").read_bytes().decode()


def _layer(page: str, verb: str = DIFF) -> tuple[str, str]:
    """(the note, if the page gives one, and the layer's text)."""
    found = re.search(rf"<summary>The {verb} report as the SDK wrote it[^<]*</summary>"
                      rf'(?:<p data-section="{verb}-text-note">(.*?)</p>)?'
                      r'<pre data-layer="3">(.*?)</pre>', page, re.S)
    assert found, f"no {verb} text layer"
    from html import unescape
    return unescape(found.group(1) or ""), found.group(2)


# ------------------------------------------------------------------ the digest, over HTTP

def test_the_forged_output_digest_is_refused_by_the_check_and_the_comparison_over_http(
        server, tmp_path):
    """B2. Before 0.2.0 the forged digest passed the check, and this test showed the
    layer drawing no line from it. The 0.2.0 verifier refuses a digest that is not `sha256:` and 64
    lower-case hex, so the run contradicts, and the SDK refuses to compare a run that doesn't
    verify. The page shows that in the SDK's words, escaped once, and the record draws no line."""
    from tests.test_serve import _post
    base, root = server
    a, b = _forged_pair(tmp_path)
    keys, verdicts = {}, {}
    for side, files in (("a", a), ("b", b)):
        status, body = _post(base, "/v1/runs", _tar(files))
        assert status == 200, body[:300]
        answer = json.loads(body)
        keys[side], verdicts[side] = answer["run_key"], answer["check_verdict"]
    assert verdicts == {"a": "holds", "b": "contradicts"}, verdicts
    status, body = _post(base, f"/compare?a={keys['a']}&b={keys['b']}")
    assert status == 200, body[:300]
    page = _both_views(root / "pages" / json.loads(body)["pages"]["diff"].lstrip("/"))
    for c in RAW:
        assert c not in page, repr(c)
    assert not re.search(r"^FORGED", page, re.M), "a record drew a line of the page"
    assert "diff: refused — does not verify" in page, "the SDK's own words for the refusal"
    assert "\\\\u000d" not in page, "escaped twice"


# ------------------------------------------------------------ the layer and the SDK agree

@pytest.fixture
def forged(tmp_path, store):
    """A real comparison of two SDK runs that both hold, whose stored reports these tests then
    give record words to. Before 0.2.0 it was the forged pair; since 0.2.0 the verifier refuses the
    forged digest and the SDK won't compare it (B2), so the record words are carried by the report
    instead -- the layer's job is the same: show what the SDK wrote, escaped once."""
    _sdk_run(tmp_path / "a", "nb2-base")
    _sdk_run(tmp_path / "b", "nb2-cand")
    run_a, run_b = _stored(_files(tmp_path / "a"), store), _stored(_files(tmp_path / "b"), store)
    return compare(run_a, run_b, store, ran_at=FIXED_RAN_AT)


@pytest.mark.parametrize("verb", [DIFF, LOCALIZE])
def test_the_stored_text_is_the_sdks_text_of_its_stored_report(forged, store, verb):
    """The layer can be rebuilt from the report only because the SDK's text IS its
    report's text: `text()` over the stored JSON, drawn as the verb draws it (its repeated carried
    lines once, `verbose=False`), gives the stored `.txt`, byte for byte."""
    from onetrace.report import text

    from onetrace_console.render import _ordered_as
    rep = report_json(forged, verb, store)
    assert rep is not None, f"the SDK wrote no {verb}.json"
    stored = report_text(forged, verb, store)
    assert text(rep, verbose=False) == stored
    assert text(_ordered_as(rep, stored), verbose=False) == stored


def test_a_report_the_sdk_wrote_in_its_own_order_agrees_once_its_keys_are_in_that_order(
        tmp_path):
    """Measured while fixing the escaping: that `text()` over the stored JSON gives the stored
    text holds only up to key order. The SDK's JSON is
    canonical, keys sorted; its text walks an annotation's `differs` in the order it built them.
    A real pair whose first differing stage has two settings that differ shows it: `text()` over
    the stored JSON is not the stored text, and the same keys in the stored text's order are."""
    from onetrace.report import text

    from onetrace_console.render import _ordered_as
    from onetrace_console.store import Store
    from tests.test_compare import RUN_C, RUN_C_POPPLER24, _deliver, _require_exam
    _require_exam()
    store = Store(tmp_path / "store")
    comparison = compare(_deliver(RUN_C, store), _deliver(RUN_C_POPPLER24, store), store,
                         ran_at=FIXED_RAN_AT)
    rep, stored = report_json(comparison, DIFF, store), report_text(comparison, DIFF, store)
    assert any(len(a["differs"]) > 1 for a in rep["annotations"]), "no two settings differ"
    assert text(rep, verbose=False) != stored
    assert text(_ordered_as(rep, stored), verbose=False) == stored
    note, layer = _layer(render_diff(comparison, store, generated_at=GENERATED_AT))
    assert note == "", "a real report's layer is rebuilt, its layout kept"
    from html import escape
    #: The folders it was given, relative to where the console ran it: no folder of this host, so
    #: the SDK's words are shown as written.
    assert {side: given["path"] for side, given in rep["inputs"].items()} == {"baseline": "a", "candidate": "b"}
    assert layer == escape(stored, quote=True), "no record word to escape: the text itself"


# ------------------------------------------------------ the other two places, each tested

CONFIG = "sha256:cd\r\nFORGED\tCFG" + "1" * 40
DOC_ID = "doc-1#AB\r\nFORGED\tDOC"


def _with(forged, store, verb: str, change) -> tuple[str, dict]:
    """The comparison with its JSON report changed and its text the SDK's own for that report."""
    from onetrace.report import text
    run = forged.verb(verb)
    rep = copy.deepcopy(report_json(forged, verb, store))
    change(rep)
    keys = {f"{verb}.json": store.put(json.dumps(rep).encode("utf-8")),
            f"{verb}.txt": store.put(text(rep).encode("utf-8"))}
    swapped = swap(run, reports=tuple((n, keys.get(n, k)) for n, k in run.reports))
    changed = swap(forged, verbs=tuple(swapped if v is run else v for v in forged.verbs))
    return render_diff(changed, store, generated_at=GENERATED_AT), rep


def test_a_config_digest_the_cause_block_shortens_is_escaped(forged, store):
    def cause(rep):
        rep["cause"] = {"stage": {"index": "1", "stage": "alpha"},
                        "instrument_change": "instrument unchanged",
                        "instrument": {"baseline": {"config_digest": "sha256:" + "2" * 64},
                                       "candidate": {"config_digest": CONFIG}},
                        "constants": None, "axis": None, "upstream": "none",
                        "blast_radius": {"status": "could not check", "reason": "a test"}}
    page, rep = _with(forged, store, DIFF, cause)
    from onetrace.report import text
    #: 0.2.0: the SDK escapes the digest before it shortens it (B1).
    assert "  config       222222222222 -> cd\\u000d\\u00\n" in text(rep), "the SDK's own 12"
    note, layer = _layer(page)
    assert note == ""
    for c in RAW:
        assert c not in layer, repr(c)
    assert not re.search(r"^FORGED", layer, re.M)
    #: Shown as the SDK wrote it, once: one backslash, not two.
    assert "  config       222222222222 -&gt; cd\\u000d\\u00\n" in layer
    assert "\\\\u000d" not in layer, "escaped twice"


def test_the_tail_of_a_document_id_is_escaped(forged, store):
    def document(rep):
        rep["doc"] = {"document": "doc-1", "status": "shown", "stage": "alpha",
                      "chunks": {"baseline": "1", "candidate": "0"},
                      "rows": [{"digest": "sha256:" + "3" * 64, "chars": "3",
                                "baseline": {"position": "1", "id": DOC_ID},
                                "candidate": None, "present": "baseline only",
                                "retrieved": []}],
                      "findings": [],
                      #: 0.2.0 names what the block read (localize --doc); none here.
                      "content_read": "none: digests, ids and character counts only"}
    page, rep = _with(forged, store, DIFF, document)
    from onetrace.report import text
    assert "#1 AB\\u000d\\u000aFORGED\\u0009DOC" in text(rep), "the SDK escapes the id's tail"
    note, layer = _layer(page)
    assert note == ""
    for c in RAW:
        assert c not in layer, repr(c)
    assert not re.search(r"^FORGED", layer, re.M)
    assert "#1 AB\\u000d\\u000aFORGED\\u0009DOC" in layer
    assert "\\\\u000d" not in layer, "escaped twice"


# ------------------------------------------------------------------------- the fallbacks

def test_where_the_sdk_wrote_no_report_the_whole_text_is_escaped_and_said(forged, store):
    run = forged.verb(DIFF)
    said = store.put(b"line one\r\nline\ttwo\nFORGED\n")
    bare = swap(run, reports=tuple((n, k) for n, k in run.reports
                                   if n not in (f"{DIFF}.json", f"{DIFF}.txt")),
                stdout_key=said)
    page = render_diff(swap(forged, verbs=tuple(bare if v is run else v for v in forged.verbs)),
                       store, generated_at=GENERATED_AT)
    note, layer = _layer(page)
    assert "wrote no report" in note and "line break" in note
    assert "\n" not in layer and "\r" not in layer and "\t" not in layer
    assert "line one\\u000d\\u000aline\\u0009two\\u000aFORGED\\u000a" in layer


def test_a_text_that_is_not_its_reports_is_escaped_whole_and_said(forged, store):
    run = forged.verb(DIFF)
    other = store.put((report_text(forged, DIFF, store) + "added\r\nFORGED\n").encode("utf-8"))
    swapped = swap(run, reports=tuple((n, other if n == f"{DIFF}.txt" else k)
                                      for n, k in run.reports))
    page = render_diff(swap(forged, verbs=tuple(swapped if v is run else v
                                                for v in forged.verbs)),
                       store, generated_at=GENERATED_AT)
    note, layer = _layer(page)
    assert "not what the SDK's own report gives" in note
    assert "\n" not in layer and "\r" not in layer
    assert "added\\u000d\\u000aFORGED\\u000a" in layer


#: A carried verifier line the verbs print once for several receipts of one side, with the count.
COLLAPSED = re.compile(r"\] \S[^\n]* on \d+ receipts")


@pytest.mark.parametrize("verb", [DIFF, LOCALIZE])
def test_a_text_whose_repeated_carried_lines_the_sdk_collapsed_is_shown_as_it_wrote_it(forged, store, verb):
    """The verbs print and write the same carried verifier line on several receipts of one side once,
    with a count ("originality on 2 receipts"); `--verbose` and the JSON keep each line. The stored
    text is the collapsed form, it is its report's text drawn that way, and the layer shows it as
    it is."""
    stored = report_text(forged, verb, store)
    assert COLLAPSED.search(stored), f"the SDK collapsed no carried line in {verb}.txt:\n{stored}"
    note, layer = _layer(render_diff(forged, store, generated_at=GENERATED_AT), verb)
    assert note == "", note
    assert COLLAPSED.search(layer), "the collapsed line, as the SDK wrote it"


def test_a_text_with_every_carried_line_is_its_reports_and_shown_as_written(forged, store):
    """The same report's text with every carried line -- as `--verbose` writes it, and as the SDK
    wrote it before it collapsed them -- is its report's text too, and is shown as it is."""
    from onetrace.report import text

    from onetrace_console.render import _ordered_as
    run, stored = forged.verb(DIFF), report_text(forged, DIFF, store)
    full = text(_ordered_as(report_json(forged, DIFF, store), stored), verbose=True)
    assert full != stored and not COLLAPSED.search(full), "the verbose text keeps each line"
    key = store.put(full.encode("utf-8"))
    swapped = swap(run, reports=tuple((n, key if n == f"{DIFF}.txt" else k) for n, k in run.reports))
    page = render_diff(swap(forged, verbs=tuple(swapped if v is run else v for v in forged.verbs)),
                       store, generated_at=GENERATED_AT)
    note, _layer_text = _layer(page)
    assert note == "", note


# ------------------------------------------------------------------ NB2-a

#: A raw CR, and the six characters `\\u000d` written out: two names that display alike.
TWIN = ("assertions.constants.a\r", "assertions.constants.a\\u000d")
TWIN_WHY = "two names in the report display the same once escaped"


#: The two names as the SDK's one-to-one escaping draws them (0.2.0): never alike. The
#: console's own collision check went with its own escaping pass.
TWIN_SHOWN = ("assertions.constants.a" + chr(92) + "u000d",
              "assertions.constants.a" + chr(92) * 2 + "u000d")


def test_a_report_with_two_names_that_escape_alike_drops_no_line(forged, store):
    """The reviewer's two-key case, in-process (NB2-a): the console's rebuild once merged the two
    keys. Since 0.2.0 the SDK escapes one-to-one itself, so its text names both, apart, and the
    layer shows that text as it is: both lines, each as the SDK wrote it, once."""
    def twins(rep):
        rep["annotations"] = [{"index": "1", "stage": "alpha",
                               "differs": {TWIN[0]: ["1", "2"], TWIN[1]: ["3", "4"]}}]
    page, rep = _with(forged, store, DIFF, twins)
    from onetrace.report import text
    assert text(rep).count("assertions.constants.a") == 2, "the SDK writes both lines"
    assert f"{TWIN_SHOWN[0]}   1  ->  2" in text(rep) and f"{TWIN_SHOWN[1]}   3  ->  4" in text(rep)
    note, layer = _layer(page)
    assert note == "", note
    for c in RAW:
        assert c not in layer, repr(c)
    assert f"{TWIN_SHOWN[0]}   1  -&gt;  2" in layer and f"{TWIN_SHOWN[1]}   3  -&gt;  4" in layer


def _twin_run(out: Path, run_id: str, first: str, second: str) -> dict[str, bytes]:
    """A run from the pinned SDK whose stage records two constants under names that display
    alike (`ctx.constant`), so the SDK's diff names both `assertions.constants.<key>`."""
    from onetrace.emit import Instrument, Recorder
    code = out.parent / "pipeline.py"
    code.write_text("# the pipeline\n", encoding="utf-8")
    rec = Recorder(out, run_id=run_id, declared_stages=["alpha"], manifest=code,
                   policy="fail-closed", anchor_reason="a test")

    @rec.stage("alpha", Instrument("a-tool", "transform", "1.0.0", {"k": "1"}))
    def alpha(ctx):
        ctx.constant("a\r", first)
        ctx.constant("a\\u000d", second)
        return ctx.write_json("a.json", {"v": "1"})

    alpha()
    rec.close()
    return _files(out)


def test_two_names_that_escape_alike_drop_no_line_end_to_end(server, tmp_path):
    """End to end over HTTP: two SDK runs, both holding, compared. On e767c40 the layer
    was rebuilt with the two names merged: one of the SDK's two lines, and no note."""
    from tests.test_serve import _post
    base, root = server
    keys = {}
    for side, (first, second) in (("a", ("1", "3")), ("b", ("2", "4"))):
        status, body = _post(base, "/v1/runs",
                             _tar(_twin_run(tmp_path / side, f"twin-{side}", first, second)))
        answer = json.loads(body)
        assert status == 200 and answer["check_verdict"] == "holds", body[:300]
        keys[side] = answer["run_key"]
    status, body = _post(base, f"/compare?a={keys['a']}&b={keys['b']}")
    assert status == 200, body[:300]
    page = _both_views(root / "pages" / json.loads(body)["pages"]["diff"].lstrip("/"))
    note, layer = _layer(page)
    #: One-to-one escaping (30bj §4): the two names stay apart, and the layer is rebuilt.
    assert note == "", note
    assert f"{TWIN_SHOWN[0]}   1  -&gt;  2" in layer and f"{TWIN_SHOWN[1]}   3  -&gt;  4" in layer
    for c in RAW:
        assert c not in layer, repr(c)
