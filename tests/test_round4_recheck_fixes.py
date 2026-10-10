"""The round-4 re-check's blockers NB1 and NB2, and SF3, fixed alone.

NB1  On a Windows host, an altered delivery was recorded as "holds": a second member named by the
     receipt's 8.3 short name (`receipts/01-ZET~1.JSO`) wrote the original bytes over the altered
     file while it was staged and checked. Every staged and materialised file is now created
     exclusively, a second write to one file is refused, and 8.3-shaped names are refused on
     Windows, naming the member.
NB2  On the Diff page, the SDK's own text quoted a record's run_ids and stage names raw, so a
     record's CR, LF and TAB drew lines of the console's page. The words it copies from records are
     now escaped inside that layer, which keeps the SDK's layout and says so in its label.
SF3  Home's "N of M" counted the manifest's chain entries, so a run missing two receipt files read
     "3 of 3". It counts the receipts delivered.
"""
from __future__ import annotations

import ctypes
import hashlib
import io
import json
import os
import re
import tarfile
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.checks import materialise, run_and_record
from onetrace_console.ingest import Rejection, accept
from onetrace_console.pages import CASE, render_execution
from onetrace_console.render import HOME, render_all
from tests.conftest import make_tar, server  # noqa: F401  (fixture)
from tests.test_checks import FIXED_RAN_AT
from tests.test_pages import GENERATED_AT, checked  # noqa: F401  (fixture)
from tests.test_unreadable import _renamed, _resummed, _stored, _text

WINDOWS = os.name == "nt"
ZETA = "receipts/01-zeta.json"


def _makes_short_names() -> bool:
    """Whether the temp folder's volume gives files 8.3 short names (NTFS does unless turned off)."""
    if not WINDOWS:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        long = Path(tmp) / "a-long-file-name.json"
        long.write_bytes(b"")
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.kernel32.GetShortPathNameW(str(long), buf, 512)
        return "~" in Path(buf.value).name


SHORT_NAMES = _makes_short_names()


def _altered(files, alias: str | None, run_id: str = "altered") -> dict[str, bytes]:
    """The reviewer's probe: `receipts/01-zeta.json` altered after the run (its sums honest, since
    whoever altered it wrote them), and, under `alias`, a member holding the original bytes."""
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = run_id
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    original = out[ZETA]
    receipt = json.loads(original.decode("utf-8"))
    receipt["outcome"]["reason"] = "ALTERED after the run"
    out[ZETA] = json.dumps(receipt, indent=1).encode("utf-8")
    if alias is not None:
        out[alias] = original
    return _resummed(out)


# ---------------------------------------------------------------------------------- NB1

@pytest.mark.skipif(not SHORT_NAMES, reason="this host's temp volume makes no 8.3 short names, "
                                            "so the alias cannot be made here")
def test_the_short_name_upload_is_refused_over_http_and_nothing_is_stored(server, files):
    """The reviewer's probe_short_member_http.py. On f2a792b: POST 200, verdict holds, while the
    stored receipt was the altered one and the exported bundle verified FAIL."""
    from tests.test_serve import _post
    base, root = server
    status, body = _post(base, "/v1/runs", make_tar(_altered(files, "receipts/01-ZET~1.JSO")))
    assert status == 422, body[:400]
    answer = json.loads(body)
    #: Refused by its name, the earlier and clearer reason, before any write.
    assert any("01-ZET~1.JSO" in r and "8.3 short-name shape" in r for r in answer["rows"]), \
        answer["rows"]
    from onetrace_console.store import Store
    assert Store(root / "store").runs() == ()


def test_the_altered_delivery_alone_still_reads_contradicts(files, store):
    """The control: without the alias, the altered receipt is found."""
    run = _stored(_altered(files, None), store)
    assert run.check_verdict == "contradicts"


#: Every other name for `receipts/01-zeta.json` a Windows host resolves to the same file, and the
#: 8.3 shape: each refused at ingest, naming the member. `RECEIP~1/…` is refused for its shape; it
#: is no alias here, since `receipts` fits 8.3 and has no other short name (measured with
#: GetShortPathNameW). A folder's own short name is tested with a longer folder, below.
ALIASES = ["receipts/01-ZETA.json", "receipts/01-zeta.json.", "receipts/01-zeta.json ",
           "receipts/01-zeta.json:alt", "receipts/01-zeta.json::$DATA",
           "receipts/01-ZET~1.JSO", "RECEIP~1/01-zeta.json"]


@pytest.mark.skipif(not WINDOWS, reason="these names are aliases only on a Windows host")
@pytest.mark.parametrize("alias", ALIASES)
def test_every_alias_a_windows_host_makes_is_refused_naming_the_member(files, store, alias):
    result = accept(make_tar(_altered(files, alias)), store)
    assert isinstance(result, Rejection), f"{alias!r} was stored"
    assert result.status == 422
    assert any(repr(alias) in r or alias in r for r in result.rows), result.rows
    assert store.runs() == ()


@pytest.mark.skipif(not SHORT_NAMES, reason="this host's temp volume makes no 8.3 short names")
@pytest.mark.parametrize("alias", ["receipts/01-ZET~1.JSO", "receipts/01-zeta.json.",
                                   "receipts/01-zeta.json::$DATA"])
def test_exclusive_create_refuses_an_alias_the_name_checks_do_not(files, store, monkeypatch,
                                                                  alias):
    """The name checks off: the second write to the one file is still refused, inside the set.
    (`receipts/01-zeta.json:alt` is a stream of its own, not the file's data, so it overwrites
    nothing -- measured: with the name checks off it is stored, and the check finds the altered
    receipt, contradicts. The name check alone refuses it.)"""
    import onetrace_console.ingest as ingest
    monkeypatch.setattr(ingest, "_unholdable", lambda name: None)
    result = accept(make_tar(_altered(files, alias)), store)
    assert isinstance(result, Rejection), f"{alias!r} was stored"
    assert any("each path appears once" in r and alias in r for r in result.rows), result.rows


@pytest.mark.skipif(not SHORT_NAMES, reason="this host's temp volume makes no 8.3 short names")
@pytest.mark.parametrize("name_checks", [True, False], ids=["name-checks-on", "name-checks-off"])
def test_a_folders_short_name_is_refused(files, store, monkeypatch, name_checks):
    """`notes-long-folder` is `NOTES-~1` to Windows (measured with GetShortPathNameW)."""
    import onetrace_console.ingest as ingest
    if not name_checks:
        monkeypatch.setattr(ingest, "_unholdable", lambda name: None)
    out = dict(files)
    out.update({"notes-long-folder/a.txt": b"one\n", "NOTES-~1/a.txt": b"two\n"})
    result = accept(make_tar(_resummed(out)), store)
    assert isinstance(result, Rejection), "a folder's short name was stored"
    assert any("NOTES-~1/a.txt" in r for r in result.rows), result.rows


def test_a_delivery_is_never_written_over_itself(tmp_path):
    """Host-independent: two paths to one file, the second write refused, the first kept."""
    from onetrace_console.staging import write_delivery
    from onetrace_console.store import SameFileError
    with pytest.raises(SameFileError, match="notes/./a.txt"):
        write_delivery({"notes/a.txt": b"first", "notes/./a.txt": b"second"}, tmp_path / "run")
    assert (tmp_path / "run" / "notes" / "a.txt").read_bytes() == b"first"


def _aliased(run, store):
    """The stored run with its first receipt altered and the original listed again under another
    path to the same file -- as a store written on another host, or edited, can hold."""
    listing = dict(run.listing)
    original = store.get(listing[ZETA])
    receipt = json.loads(original.decode("utf-8"))
    receipt["outcome"]["reason"] = "ALTERED after the run"
    altered = store.put(json.dumps(receipt, indent=1).encode("utf-8"))
    rows = tuple((p, altered if p == ZETA else k) for p, k in run.listing)
    return replace(run, listing=rows + (("receipts/./01-zeta.json", listing[ZETA]),))


def test_a_stored_run_is_never_laid_out_over_itself(checked, store, tmp_path):  # noqa: F811
    from onetrace_console.store import SameFileError
    with pytest.raises(SameFileError, match="receipts/./01-zeta.json"):
        materialise(_aliased(checked, store), store, tmp_path / "run")


def test_at_check_time_it_could_not_be_checked_and_its_page_says_why(checked, store):  # noqa: F811
    """On f2a792b the original bytes were written over the altered ones, and the check held."""
    from onetrace_console.unreadable import RUN_FAILED
    run = _aliased(checked, store)
    store.put_run(run)
    rechecked = run_and_record(run, store, ran_at=FIXED_RAN_AT)
    assert rechecked.check_verdict == "could_not_check", rechecked.check_verdict
    assert "receipts/./01-zeta.json" in rechecked.check_note
    page = _text(render_execution(rechecked, store, generated_at=GENERATED_AT).pages[CASE])
    assert RUN_FAILED in page and "receipts/./01-zeta.json" in page


def test_compare_says_a_run_cannot_be_laid_out_here(server, files):
    from onetrace_console.serve import Handler
    from tests.test_serve import _post
    base, _root = server
    a = _stored(_resummed(_renamed(files)), Handler.store)
    b = _stored(files, Handler.store)
    Handler.store.put_run(_aliased(a, Handler.store))
    status, body = _post(base, f"/compare?a={a.key}&b={b.key}")
    assert status == 400 and "receipts/./01-zeta.json" in json.loads(body)["error"], body


# ---------------------------------------------------------------------------------- NB2

NASTY = "‮RLO|\x00NUL|\x1b[31mESC|\r\nCRLF|⁦LRI|\x85NEL|\tTAB|"
IDS = {"a": "n11-A|" + NASTY, "b": "n11-B|" + NASTY}
STAGES = ("st1|" + NASTY, "st2|" + NASTY)


#: The names the emitter is given, safe as folder names on any host; the hostile ones are written
#: into the receipts afterwards.
_SAFE_STAGES = ("st1", "st2")


def _sdk_delivery(tmp_path: Path, which: str, setting: str) -> dict[str, bytes]:
    """A run whose run_id and both stage names carry the controls, and which the pinned verifier
    holds, so it verifies and diffs.

    Made by the pinned SDK under safe names, then written directly: 0.1.2's emitter makes a folder
    per stage name, and a name holding NUL cannot be a folder on Windows, so the emitter can no
    longer make this run here. The run_id and the stage names -- in each
    receipt's `run_id`, `stage.name` and coverage lists, and the manifest's `run_id` and chain --
    are replaced with the hostile ones, and the chain is recomputed with the SDK's own canonical
    form and digest, as the review probes did. File and folder names stay the emitter's."""
    from onetrace.canonical import canonicalize, digest
    from onetrace.emit import Instrument, Recorder
    code = tmp_path / "pipeline.py"
    code.write_text("# the pipeline\n", encoding="utf-8")
    out = tmp_path / f"run-{which}"
    rec = Recorder(out, run_id=f"safe-{which}", declared_stages=list(_SAFE_STAGES), manifest=code,
                   policy="fail-closed", anchor_reason="a test")

    @rec.stage(_SAFE_STAGES[0], Instrument("a-tool", "transform", "1.0.0", {"k": setting}))
    def first(ctx):
        return ctx.write_json("a.json", {"v": "1"})

    @rec.stage(_SAFE_STAGES[1], Instrument("b-tool", "transform", "1.0.0", {"k": "same"}))
    def second(ctx, x):
        return ctx.write_json("b.json", ctx.read_json(x))

    second(first())
    rec.close()

    hostile = dict(zip(_SAFE_STAGES, STAGES))
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    prev = None
    for entry in manifest["chain"]:
        path = out / entry["file"]
        receipt = json.loads(path.read_text(encoding="utf-8"))
        receipt["run_id"] = IDS[which]
        receipt["stage"]["name"] = hostile[receipt["stage"]["name"]]
        for key in ("declared_stages", "emitting_stages"):
            receipt["coverage"][key] = [hostile[s] for s in receipt["coverage"][key]]
        receipt["prev"] = prev
        raw = canonicalize(receipt)
        path.write_bytes(raw)
        entry["stage"] = hostile[entry["stage"]]
        entry["digest"] = prev = digest(raw)
    manifest["run_id"] = IDS[which]
    manifest["chain_head"] = prev
    (out / "MANIFEST.json").write_bytes(canonicalize(manifest))
    return _resummed({p.relative_to(out).as_posix(): p.read_bytes()
                      for p in sorted(out.rglob("*")) if p.is_file() and p.name != ".lock"})


def test_the_hostile_run_carries_every_hostile_name_and_the_pinned_verifier_holds_it(tmp_path,
                                                                                     store):
    """The fixture tests the console, so it must reach the console with the
    names whole -- a NUL, a CR/LF, the bidirectional controls -- however this host names folders,
    and a run the pinned verifier holds, so its diff is drawn."""
    files = _sdk_delivery(tmp_path, "a", "1")
    manifest = json.loads(files["MANIFEST.json"].decode("utf-8"))
    assert manifest["run_id"] == IDS["a"]
    assert [e["stage"] for e in manifest["chain"]] == list(STAGES)
    for entry, stage in zip(manifest["chain"], STAGES):
        receipt = json.loads(files[entry["file"]].decode("utf-8"))
        assert receipt["run_id"] == IDS["a"] and receipt["stage"]["name"] == stage
        assert receipt["coverage"]["declared_stages"] == list(STAGES)
        assert stage in receipt["coverage"]["emitting_stages"]
    assert _stored(files, store).check_verdict == "holds"


@pytest.fixture
def nasty_diff(tmp_path, store):
    from onetrace_console.compare import compare
    from onetrace_console.render import render_diff
    a = _stored(_sdk_delivery(tmp_path, "a", "1"), store)
    b = _stored(_sdk_delivery(tmp_path, "b", "2"), store)
    comparison = compare(a, b, store, ran_at=FIXED_RAN_AT)
    return comparison, render_diff(comparison, store, generated_at=GENERATED_AT)


def _sdk_layer(page: str, verb: str = "diff") -> tuple[str, str]:
    found = re.search(rf"<summary>(The {verb} report[^<]*)</summary>"
                      rf'(?:<p data-section="{verb}-text-note">.*?</p>)?'
                      r'<pre data-layer="3">(.*?)</pre>', page, re.S)
    assert found, f"no {verb} text layer"
    return found.group(1), found.group(2)


def test_the_sdk_text_layer_shows_record_words_escaped_and_keeps_its_layout(nasty_diff, store):
    """Since the 0.2.0 SDK its text escapes the record's words itself, one-to-one, so the text it
    wrote holds none of them raw and the layer shows it as it is, once: the
    same lines, each word as `onetrace.escaping` writes it. (Before 0.2.0 the SDK quoted them raw
    and the console escaped a copy of the report; that pass is retired.)"""
    from html import escape

    from onetrace.escaping import escaped

    from onetrace_console.compare import report_text
    comparison, page = nasty_diff
    label, layer = _sdk_layer(page)
    #: The record's words drew no line: no CR, TAB or control of theirs is in the layer raw, and
    #: no line of it starts with what followed their CRLF.
    for c in ("\r", "\t", "\x00", "\x1b", "\x85", "‮", "⁦"):
        assert c not in layer, repr(c)
    assert not re.search(r"^CRLF\|", layer, re.M)
    words = (*IDS.values(), *STAGES)
    for word in words:
        assert escape(escaped(word)) in layer, word
    written = report_text(comparison, "diff", store)
    for c in ("\r", "\t", "\x00", "\x1b", "\x85", "‮", "⁦"):
        assert c not in written, f"the SDK's own text carries {c!r} raw"
    #: The SDK's own layout, kept line for line.
    assert layer.count("\n") == written.count("\n")


def test_the_sdk_text_layer_says_what_it_is(nasty_diff):
    _comparison, page = nasty_diff
    label, _layer = _sdk_layer(page)
    assert label == "The diff report as the SDK wrote it, with names from the records escaped"
    assert "exactly as the SDK wrote it" not in page


def test_a_diff_pages_report_files_are_never_written_over_each_other(nasty_diff, store):
    """The Diff page lays the SDK's reports out to read them: a comparison listing one name twice
    (a store written elsewhere, or edited) is said on the page, never read from the second."""
    from dataclasses import replace as swap

    from onetrace_console.compare import DIFF
    from onetrace_console.render import render_diff
    comparison, _page = nasty_diff
    run = comparison.verb(DIFF)
    other = store.put(b'{"not": "the report"}')
    doubled = swap(run, reports=tuple(run.reports) + (("diff.json", other),))
    twice = swap(comparison, verbs=tuple(doubled if v is run else v for v in comparison.verbs))
    page = _text(render_diff(twice, store, generated_at=GENERATED_AT))
    assert "'diff.json' names a file another of the run's paths already wrote" in page, page[:600]


def test_a_word_only_the_sdk_json_carries_is_escaped_in_the_layer(nasty_diff, store):
    """"Anything else the report copies from a record": a word no stored run holds, as
    the SDK's `carried` lines copy verifier rows. Since 0.2.0 the SDK escapes its text itself but
    leaves `carried` as given (the verifier escaped it already), so a report written elsewhere can
    carry a raw word through a text that is still its report's. The layer then does not show the
    text as it is: it shows it whole and escaped, and says why."""
    from dataclasses import replace as swap

    from onetrace.report import text as sdk_text

    from onetrace_console.compare import DIFF, report_json
    from onetrace_console.render import render_diff
    comparison, _page = nasty_diff
    run = comparison.verb(DIFF)
    word = "copied\r\nforged: row‮"
    rep = report_json(comparison, DIFF, store)
    rep["carried"] = [{"side": "baseline", "line": word}]
    #: The SDK's own text of that report, so the layer is rebuilt from it.
    text = sdk_text(rep)
    keys = {"diff.json": store.put(json.dumps(rep).encode("utf-8")),
            "diff.txt": store.put(text.encode("utf-8"))}
    swapped = swap(run, reports=tuple((n, keys.get(n, k)) for n, k in run.reports))
    page = render_diff(swap(comparison, verbs=tuple(swapped if v is run else v
                                                    for v in comparison.verbs)),
                       store, generated_at=GENERATED_AT)
    _label, layer = _sdk_layer(page)
    assert "copied\\u000d\\u000aforged: row\\u202e" in layer
    assert not re.search(r"^forged: row", layer, re.M)
    from html import unescape

    from onetrace_console.render import SDK_TEXT_RAW
    assert SDK_TEXT_RAW in unescape(page), "the page says why the text is shown escaped whole"


def test_the_sdks_text_escapes_every_string_of_the_report():
    """What the layer now relies on, held here so an SDK that stopped doing it fails
    this suite: the SDK's `printable()`, which `text()` draws from, escapes keys and values alike,
    at any depth, one-to-one; anything that is not a string stays as it was. (This was the
    console's own `_escaped` copy, retired with its pass.)"""
    from onetrace.report import printable
    report = {"inputs": {"baseline": {"run_id": "r\r\nforged: line"}},
              "annotations": [{"differs": {"k\tey": ["a\nb", "c"]}}], "exit": None}
    assert printable(report) == {"inputs": {"baseline": {"run_id": "r\\u000d\\u000aforged: line"}},
                                 "annotations": [{"differs": {"k\\u0009ey": ["a\\u000ab", "c"]}}],
                                 "exit": None}


# ---------------------------------------------------------------------------------- SF3

def _missing_two_receipts(files) -> dict[str, bytes]:
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    for entry in manifest["chain"][1:]:
        del out[entry["file"]]
    return _resummed(out)


def test_a_run_missing_two_receipt_files_reads_one_of_three_delivered(files, store):
    """On f2a792b: "3 of 3", the chain's entries counted as if every receipt had arrived."""
    run = _stored(_missing_two_receipts(files), store)
    assert (run.recorded_count, run.stage_count) == (1, 3)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    recent = _text(re.search(r'<tr data-recent="[^"]*">(.*?)</tr>', home, re.S).group(1))
    #: One declared stage of three with a receipt (stages are counted, not receipts).
    assert run.delivered_stages == 1
    assert "1 of 3 declared stages" in recent, recent


def test_a_whole_delivery_reads_all_delivered(checked, store):  # noqa: F811
    assert (checked.recorded_count, checked.stage_count) == (3, 3)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    recent = _text(re.search(r'<tr data-recent="[^"]*">(.*?)</tr>', home, re.S).group(1))
    assert "3 of 3 declared stages" in recent, recent
