"""Kept input text: shown only where the record lists it as kept and the file matches its digest.

onetrace 0.2.2 can keep a stage's text inputs beside their digests: each in
`inputs/<receipt stem>/<name>.json`, holding exactly the bytes the input's digest was computed over,
and listed in the stage's own constant `onetrace.kept_inputs`; the inputs it did not keep are in
`onetrace.inputs_not_kept`, each with why. The prefix `onetrace.` is the SDK's own: 0.2.2 refuses a
user constant that starts with it.

The console shows an input's text only when both hold: the receipt lists it as kept, and the sha256
of the stored file equals the input's digest. Otherwise it says, in plain words, which of three it
is -- "not kept" (with why, where the record says), "not kept: file missing" (removing kept text is
supported: the digest still holds), or "text does not match its digest; not shown" (both digests,
never the text). Files in `inputs/` that no step lists are never shown; a note counts them. Kept
text is escaped like every other value from a record, and long text is cut with its full size
said. A public console never shows the kept text of an externally sourced input -- on the step page
or in the text diff -- and the demo keeps none. The console only reads `inputs/`.

Every run here is written by the installed SDK (0.2.2); the three readings that need a file
removed, changed or added are made by changing the folder after it was written, as an operator or
an attacker would.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.frame import rendering
from tests.test_checks import _require_installed
from tests.test_stage_pages import _item, _stored

GENERATED_AT = "2026-10-14T12:00:00+00:00"
QUESTION = "What is the refund window?"
#: Built with chr(), so no raw control is in this file.
ESC, RLO = chr(0x1B), chr(0x202E)
HOSTILE = "line one" + chr(10) + "<script>alert(1)</script> " + ESC + "[31m" + RLO + "evil"


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def _emit(folder: Path, *, question: str = QUESTION, ask: str = "From outside the run",
          cap: int = 4096, draft_trust: str = "operator-authored") -> Path:
    """A run the SDK writes: its intake keeps `q` (the run's own argument, externally sourced, as
    the SDK records a run's arguments by default); `draft` keeps `question`, can't keep `blob`
    (bytes) or `big` (over the cap), and lists `other` in neither constant."""
    import onetrace as ot
    from onetrace.emit import Instrument
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})

    @ot.stage("draft", instrument=tool, keep_inputs=["question", "blob", "big"], trust=draft_trust,
              keep_inputs_cap=cap)
    def draft(question, blob, big, other):
        #: An output that never quotes the input: outputs are shown, by their own rule.
        return f"an answer to a question of {len(question)} characters"

    @ot.run(str(folder), stages=["draft"], keep_inputs=["q"])
    def pipeline(q):
        return draft(question, b"\x00raw", "x" * (cap + 1), "an input listed in neither constant")

    pipeline(ask)
    return folder


def _emit_older(folder: Path, monkeypatch, question: str = QUESTION) -> Path:
    """A run as an SDK before 0.2.2 could write it: the intake says 0.2.1, the user's own constant
    is named `onetrace.kept_inputs` (0.2.1 did not reserve the prefix), and a file sits where 0.2.2
    would keep the input's text, holding exactly the digested bytes."""
    import onetrace as ot
    import onetrace.decorators as decorators
    import onetrace.kept as kept
    from onetrace.emit import Instrument
    real = decorators._intake_instrument

    def older(*a, **k):
        from dataclasses import replace
        return replace(real(*a, **k), version="0.2.1")
    monkeypatch.setattr(decorators, "_intake_instrument", older)
    monkeypatch.setattr(kept, "PREFIX", "\x00only-the-sdk.")
    tool = Instrument("tool", "tool", "1.0.0", {"x": "1"})

    @ot.stage("draft", instrument=tool, trust="operator-authored")
    def draft(question):
        ot.constant("onetrace.kept_inputs", "question")
        return f"an answer to a question of {len(question)} characters"

    @ot.run(str(folder), stages=["draft"])
    def pipeline(q):
        return draft(question)

    pipeline("From outside the run")
    stem = _stem(folder, "draft")
    (folder / "inputs" / stem).mkdir(parents=True)
    (folder / "inputs" / stem / "question.json").write_bytes(ot.encode_v1(question, "draft", "question"))
    return folder


def _stem(folder: Path, stage: str) -> str:
    import json
    chain = json.loads((folder / "MANIFEST.json").read_text(encoding="utf-8"))["chain"]
    return next(Path(e["file"]).stem for e in chain if e["stage"] == stage)


def _pages(run, store, *, public: bool = False) -> dict[str, str]:
    from onetrace_console.pages import render_execution
    with rendering(onedoor=False, sign_in=False, public=public):
        return render_execution(run, store, generated_at=GENERATED_AT).pages


def _kept(page: str, name: str) -> tuple[str, str]:
    """(the reading's data-kept state, the input row's text) for one input on a step page."""
    raw = _item(page, "input", name)
    state = re.findall(r'data-kept="([^"]+)"', raw)
    assert len(state) == 1, (name, state, raw)
    return state[0], raw


@pytest.fixture
def written(tmp_path):
    _require_installed()
    return _emit(tmp_path / "run")


def _draft(folder: Path, store, **kw) -> str:
    return _pages(_stored(folder, store), store, **kw)["stage-2.html"]


# ------------------------------------------------------------------ 1. kept and matching

def test_a_listed_input_whose_file_matches_shows_its_text_beside_its_digest(written, store, examined):
    page = _draft(written, store)
    examined(1, "kept and matching input")
    state, raw = _kept(page, "question")
    assert state == "shown"
    pre = re.findall(r"<pre data-kept-text>(.*?)</pre>", raw, re.S)
    assert [unescape(p) for p in pre] == [QUESTION], pre
    import onetrace as ot
    digest = "sha256:" + hashlib.sha256(ot.encode_v1(QUESTION, "draft", "question")).hexdigest()
    assert digest[len("sha256:"):] in raw, "the digest beside the text"


def test_the_banner_says_kept_text_is_shown_only_where_it_matches(written, store, examined):
    from onetrace_console.kept_inputs import BANNER_KEPT
    page = _draft(written, store)
    examined(1, "banner")
    from onetrace_console.kept_inputs import INPUTS_NOTE_KEPT
    assert BANNER_KEPT in _text(page) and INPUTS_NOTE_KEPT in _text(page)
    assert "inputs from outside the run are fingerprinted, not stored" not in _text(page)


# ------------------------------------------------------------------ 2. the three "not shown"

def test_an_input_not_kept_says_so_with_the_recorded_reason(written, store, examined):
    from onetrace_console.kept_inputs import NOT_KEPT
    page = _draft(written, store)
    examined(3, "inputs not kept")
    for name, why in (("blob", "not text (bytes)"), ("big", "over 4096 bytes"), ("other", None)):
        state, raw = _kept(page, name)
        assert state == "not-kept", (name, state)
        assert NOT_KEPT in _text(raw) and "<pre" not in raw
        if why:
            assert why in _text(raw), (name, _text(raw))


def test_a_matching_file_for_an_input_not_listed_is_never_shown(written, store, examined):
    """`other` is listed in neither constant. A file at its place, holding exactly its digested
    bytes, still isn't shown: the listing is half the rule."""
    import onetrace as ot
    plain = "an input listed in neither constant"
    (written / "inputs" / _stem(written, "draft") / "other.json").write_bytes(
        ot.encode_v1(plain, "draft", "other"))
    page = _draft(written, store)
    examined(1, "unlisted matching file")
    state, raw = _kept(page, "other")
    assert state == "not-kept" and plain not in _text(raw)


def test_a_listed_input_whose_file_was_removed_says_so_and_that_removing_is_supported(written, store, examined):
    from onetrace_console.kept_inputs import ERASED, MISSING
    (written / "inputs" / _stem(written, "draft") / "question.json").unlink()
    page = _draft(written, store)
    examined(1, "kept file removed")
    state, raw = _kept(page, "question")
    assert state == "missing"
    assert MISSING in _text(raw) and ERASED in _text(raw) and "<pre" not in raw
    assert 'class="pill bad"' not in raw and "data-error" not in page, "a reading, never an error"


def test_a_listed_input_whose_file_differs_shows_both_digests_never_the_text(written, store, examined):
    import onetrace as ot
    from onetrace_console.kept_inputs import MISMATCH
    path = written / "inputs" / _stem(written, "draft") / "question.json"
    recorded = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    changed = ot.encode_v1("Changed after the run", "draft", "question")
    path.write_bytes(changed)
    page = _draft(written, store)
    examined(1, "kept file changed")
    state, raw = _kept(page, "question")
    assert state == "mismatch"
    assert MISMATCH in _text(raw) and "<pre" not in raw
    assert "Changed after the run" not in _text(page) and QUESTION not in _text(raw)
    for digest in (recorded, "sha256:" + hashlib.sha256(changed).hexdigest()):
        assert digest[len("sha256:"):] in raw, f"{digest} not shown"


def test_a_file_that_matches_but_is_not_text_is_not_shown(written, store, examined):
    """The digest can match only bytes the SDK digested; a JSON value that isn't a string
    (planted with its digest recomputed into nothing -- the receipt holds the digest) reads as not
    matching. Here: the stored file replaced by a number, which can't match the recorded digest."""
    from onetrace_console.kept_inputs import MISMATCH
    (written / "inputs" / _stem(written, "draft") / "question.json").write_bytes(b"42")
    page = _draft(written, store)
    examined(1, "kept file not text")
    state, raw = _kept(page, "question")
    assert state == "mismatch" and MISMATCH in _text(raw)


# ------------------------------------------------------------------ 3. unlisted files

def test_files_in_inputs_no_step_lists_are_counted_and_never_shown(written, store, examined):
    from onetrace_console.kept_inputs import unlisted_note
    (written / "inputs" / _stem(written, "draft") / "stray.json").write_bytes(b'"a stray secret"')
    (written / "inputs" / "elsewhere").mkdir()
    (written / "inputs" / "elsewhere" / "x.json").write_bytes(b'"another stray secret"')
    pages = _pages(_stored(written, store), store)
    examined(len(pages), "pages of a run with two unlisted files")
    for name, page in pages.items():
        assert "stray secret" not in _text(page), name
        assert "stray.json" not in page and "elsewhere" not in page, name
    notes = re.findall(r'<p class="note" data-section="unlisted-inputs">(.*?)</p>', pages["stage-2.html"])
    assert [_text(n) for n in notes] == [unlisted_note(2)]
    assert unlisted_note(1) != unlisted_note(2)


def test_a_run_with_no_unlisted_file_has_no_note(written, store, examined):
    pages = _pages(_stored(written, store), store)
    examined(1, "step page")
    assert 'data-section="unlisted-inputs"' not in pages["stage-2.html"]


# ------------------------------------------------------------------ 4. escaping and size

def test_kept_text_is_escaped_like_every_value_from_a_record(tmp_path, store, examined):
    _require_installed()
    folder = _emit(tmp_path / "run", question=HOSTILE)
    page = _draft(folder, store)
    examined(1, "hostile kept text")
    state, raw = _kept(page, "question")
    assert state == "shown"
    assert ESC not in page and RLO not in page
    from tests.test_theme_switch import without_the_console_s_own
    assert "<script>" not in without_the_console_s_own(page) and "&lt;script&gt;" in raw
    assert "\\u001b" in raw and "\\u202e" in raw
    #: The line break is kept as a line break: the text is shown as written, one line per line.
    assert "line one\n" in unescape(raw)


def test_long_kept_text_is_cut_and_its_full_size_said(tmp_path, store, examined):
    from onetrace_console.kept_inputs import SHOWN_CAP, size_said
    _require_installed()
    long = "a" * (SHOWN_CAP + 1000)
    folder = _emit(tmp_path / "run", question=long, cap=20000)
    page = _draft(folder, store)
    examined(1, "long kept text")
    state, raw = _kept(page, "question")
    assert state == "shown"
    pre = unescape(re.search(r"<pre data-kept-text>(.*?)</pre>", raw, re.S).group(1))
    assert pre.startswith("a" * SHOWN_CAP) and "a" * (SHOWN_CAP + 1) not in pre
    assert "1000 more characters" in pre
    assert size_said(len(long)) in _text(raw)


# ------------------------------------------------------------------ 5. an older SDK's constant

def test_a_reserved_prefix_constant_from_an_older_sdk_is_the_runs_own(tmp_path, store, monkeypatch, examined):
    """Before 0.2.2 a user could name a constant `onetrace.kept_inputs`. Such a run's constant is
    its own, not the SDK's listing: nothing is shown as kept, even with a matching file."""
    from onetrace_console.kept_inputs import older_sdk
    _require_installed()
    folder = _emit_older(tmp_path / "run", monkeypatch)
    monkeypatch.undo()
    page = _draft(folder, store)
    examined(1, "older SDK's run")
    state, raw = _kept(page, "question")
    assert state == "older"
    assert older_sdk("0.2.1") in _text(raw)
    assert "<pre" not in raw and QUESTION not in _text(raw)


def test_the_sdk_versions_that_list_kept_inputs():
    from onetrace_console.kept_inputs import honoured
    assert honoured("0.2.2") and honoured("0.2.10") and honoured("0.3.0") and honoured("1.0")
    assert not honoured("0.2.1") and not honoured("0.1.2") and not honoured("0.2.2.dev0")
    #: A record that doesn't say which SDK made it: the listing is read; the digest still decides.
    assert honoured(None)
    assert not honoured("not a version")


# ------------------------------------------------------------------ 6. the public console

def test_a_public_console_never_shows_an_externally_sourced_inputs_kept_text(written, store, examined):
    from onetrace_console.kept_inputs import EXTERNAL
    run = _stored(written, store)
    public, local = _pages(run, store, public=True), _pages(run, store)
    examined(2, "renderings of the intake step")
    state, raw = _kept(public["stage-1.html"], "q")
    assert state == "external" and EXTERNAL in _text(raw)
    assert "From outside the run" not in _text(public["stage-1.html"])
    #: Locally, the operator's own console, it is shown as kept.
    assert _kept(local["stage-1.html"], "q")[0] == "shown"
    #: The step's own operator-authored input is shown on the public console too.
    assert _kept(public["stage-2.html"], "question")[0] == "shown"


def test_the_demo_check_names_a_run_that_keeps_an_externally_sourced_input(written, store, examined):
    """The check the demo is held to (tests/test_stage_page_look.py) sees such a run: the intake's
    `q`, kept and externally sourced; the step's own operator-authored input is not named."""
    from onetrace_console.kept_inputs import external_kept
    from onetrace_console.stage_pages import _steps
    run = _stored(written, store)
    examined(1, "run keeping an externally sourced input")
    assert external_kept(_steps(run, store)) == [("intake", "q")]


def _diff(a: Path, b: Path, out: Path) -> bytes:
    from onetrace_console.compare import utf8_env
    return subprocess.run([sys.executable, "-m", "onetrace", "diff", str(a), str(b), "--text", "--json",
                           "--no-follow", "--out", str(out)], capture_output=True, env=utf8_env(),
                          check=False).stdout


def _compared(tmp_path: Path, store, *, older: bool = False, monkeypatch=None, change=None,
              trust: str = "externally-sourced"):
    """Two runs whose `draft` kept `question` differently, the SDK's text diff of them as written,
    and the pair as the console stores it. `change(folder)`, where given, alters run B's folder
    after the diff was made and before the console stores it: the console's own reading must
    then decide, not the SDK's."""
    from types import SimpleNamespace

    from onetrace_console.textdiff_view import read_textdiff
    _require_installed()
    if older:
        a = _emit_older(tmp_path / "a", monkeypatch, question="own first")
        b = _emit_older(tmp_path / "b", monkeypatch, question="own second")
        monkeypatch.undo()
    else:
        a = _emit(tmp_path / "a", question="own first", draft_trust=trust)
        b = _emit(tmp_path / "b", question="own second", draft_trust=trust)
    doc = read_textdiff(_diff(a, b, tmp_path / "out"))
    if change is not None:
        change(b)
    run_a, run_b = _stored(a, store), _stored(b, store)
    return doc, SimpleNamespace(run_a=run_a.key, run_b=run_b.key)


def _drawn(doc, pair, store, *, public: bool) -> str:
    from onetrace_console.kept_inputs import for_this_console
    from onetrace_console.textdiff_view import render_textdiff
    with rendering(onedoor=False, sign_in=False, public=public):
        return _text(render_textdiff(for_this_console(doc, pair, store)))


def test_a_text_diff_shows_kept_text_where_both_sides_are_listed_and_match(tmp_path, store, examined):
    doc, pair = _compared(tmp_path, store, trust="operator-authored")
    examined(2, "renderings of the text diff")
    for public in (False, True):
        drawn = _drawn(doc, pair, store, public=public)
        assert "own first" in drawn and "own second" in drawn, drawn


def test_a_public_text_diff_never_shows_an_externally_sourced_inputs_kept_text(tmp_path, store, examined):
    """The SDK's text diff prints both kept texts under a changed input's line. On a public
    console, an externally sourced input's are left out, and its line says why."""
    from onetrace_console.kept_inputs import EXTERNAL
    doc, pair = _compared(tmp_path, store)
    examined(2, "renderings of the text diff")
    local, public = _drawn(doc, pair, store, public=False), _drawn(doc, pair, store, public=True)
    assert "own first" in local and "own second" in local, local
    assert "own first" not in public and "own second" not in public, public
    assert EXTERNAL in public


def _changed(folder: Path) -> None:
    import onetrace as ot
    (folder / "inputs" / _stem(folder, "draft") / "question.json").write_bytes(
        ot.encode_v1("Changed after the run", "draft", "question"))


def test_a_text_diff_never_shows_kept_text_the_console_does_not_read_as_matching(tmp_path, store, examined):
    """The console's own reading of each side decides, not the SDK's: a side whose stored file
    does not match its digest shows that side's reading, and neither side's text."""
    from onetrace_console.kept_inputs import MISMATCH
    doc, pair = _compared(tmp_path, store, trust="operator-authored", change=_changed)
    examined(1, "text diff with one side not matching")
    drawn = _drawn(doc, pair, store, public=False)
    assert "own first" not in drawn and "own second" not in drawn and "Changed after" not in drawn, drawn
    assert f"candidate: {MISMATCH}" in drawn, drawn


def test_a_text_diff_side_whose_file_was_removed_reads_file_missing(tmp_path, store, examined):
    from onetrace_console.kept_inputs import MISSING
    doc, pair = _compared(tmp_path, store, trust="operator-authored",
                          change=lambda b: (b / "inputs" / _stem(b, "draft") / "question.json").unlink())
    examined(1, "text diff with one side's file removed")
    drawn = _drawn(doc, pair, store, public=False)
    assert "own first" not in drawn and "own second" not in drawn, drawn
    assert f"candidate: {MISSING}" in drawn, drawn


def test_a_text_diff_of_older_sdk_runs_shows_no_kept_text(tmp_path, store, monkeypatch, examined):
    """The SDK's own reader takes an older run's `onetrace.kept_inputs` setting as a listing and
    prints the text; the console reads it as the run's own setting, and shows none."""
    from onetrace_console.kept_inputs import older_sdk
    doc, pair = _compared(tmp_path, store, older=True, monkeypatch=monkeypatch)
    assert any("own first" in line for n in doc["nodes"] for line in n["inputs"]), "the SDK printed it"
    examined(1, "text diff of older-SDK runs")
    drawn = _drawn(doc, pair, store, public=False)
    assert "own first" not in drawn and "own second" not in drawn, drawn
    assert f"baseline: {older_sdk('0.2.1')}" in drawn, drawn


def test_a_text_diff_line_the_console_cannot_tie_to_a_record_shows_no_kept_text(tmp_path, store, examined):
    """Without the stored pair (or a node or input the records don't name), the console can't read
    either side: the kept text is left out, and the line says so."""
    from onetrace_console.kept_inputs import UNTIED
    doc, pair = _compared(tmp_path, store, trust="operator-authored")
    examined(2, "untied text diffs")
    from onetrace_console.kept_inputs import for_this_console
    from onetrace_console.textdiff_view import render_textdiff
    with rendering(onedoor=False, sign_in=False, public=False):
        alone = _text(render_textdiff(for_this_console(doc, None, store)))
    assert "own first" not in alone and UNTIED in alone, alone
    renamed = {**doc, "nodes": [{**n, "node": "not-a-step"} for n in doc["nodes"]]}
    drawn = _drawn(renamed, pair, store, public=False)
    assert "own first" not in drawn and UNTIED in drawn, drawn


def test_both_text_diff_drawings_read_the_diff_through_the_public_rule():
    """The Diff page and the text-diff page both draw the SDK's input lines; both read the
    document through `for_this_console`, so neither can draw a line the rule left out."""
    import ast

    import onetrace_console.render as render
    import onetrace_console.textdiff_page as textdiff_page
    for module, function in ((render, "_text_diff_section"), (textdiff_page, "shown_document")):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        fn = next((n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function), None)
        assert fn is not None, f"{module.__name__}.{function} is gone"
        calls = {c.func.id for c in ast.walk(fn) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
        assert "for_this_console" in calls, f"{module.__name__}.{function} draws the diff unfiltered"


# ------------------------------------------------------------------ 7. reading only

def test_the_console_only_reads_inputs(written, store, examined):
    """Nothing the console does to a run touches `inputs/`: the folder delivered is unchanged, and
    the module that reads kept text calls nothing that writes, moves or removes a file."""
    import ast

    import onetrace_console.kept_inputs as kept_inputs
    before = {p: p.read_bytes() for p in written.rglob("*") if p.is_file()}
    run = _stored(written, store)
    _pages(run, store)
    _pages(run, store, public=True)
    after = {p: p.read_bytes() for p in written.rglob("*") if p.is_file()}
    examined(len(before), "files of the delivered run folder")
    assert before == after
    tree = ast.parse(Path(kept_inputs.__file__).read_text(encoding="utf-8"))
    names = {n.attr if isinstance(n, ast.Attribute) else n.id
             for n in ast.walk(tree) if isinstance(n, (ast.Attribute, ast.Name))}
    writes = names & {"open", "write_bytes", "write_text", "unlink", "rename", "replace", "rmtree",
                      "remove", "mkdir", "rmdir", "put", "move", "copy", "touch"}
    assert not writes, writes


# ------------------------------------------------------------------ sabotages, each caught

def _sabotaged(monkeypatch, attr, broken):
    import onetrace_console.kept_inputs as kept_inputs
    monkeypatch.setattr(kept_inputs, attr, broken)


def test_sabotage_the_digest_check_taken_away_shows_changed_text(written, store, monkeypatch, examined):
    import onetrace as ot
    (written / "inputs" / _stem(written, "draft") / "question.json").write_bytes(
        ot.encode_v1("Changed after the run", "draft", "question"))
    _sabotaged(monkeypatch, "_matches", lambda data, digest: True)
    examined(1, "sabotaged digest check")
    state, raw = _kept(_draft(written, store), "question")
    assert state == "shown" and "Changed after the run" in _text(raw), "the test above would catch it"


def test_sabotage_the_listing_taken_away_shows_an_unlisted_file(written, store, monkeypatch, examined):
    import onetrace as ot
    (written / "inputs" / _stem(written, "draft") / "other.json").write_bytes(
        ot.encode_v1("an input listed in neither constant", "draft", "other"))
    _sabotaged(monkeypatch, "listed", lambda receipt: [str(i.get("name")) for i in receipt.get("inputs") or []])
    examined(1, "sabotaged listing")
    assert _kept(_draft(written, store), "other")[0] == "shown"


def test_sabotage_the_public_rule_taken_away_shows_external_text(written, store, monkeypatch, examined):
    _sabotaged(monkeypatch, "hidden_here", lambda item: False)
    examined(1, "sabotaged public rule")
    page = _pages(_stored(written, store), store, public=True)["stage-1.html"]
    assert _kept(page, "q")[0] == "shown" and "From outside the run" in _text(page)


def test_sabotage_the_public_rule_taken_away_from_the_text_diff(tmp_path, store, monkeypatch, examined):
    doc, pair = _compared(tmp_path, store)
    _sabotaged(monkeypatch, "hidden_here", lambda item: False)
    _sabotaged(monkeypatch, "_external_line", lambda line: False)
    examined(1, "sabotaged text-diff rule")
    assert "own first" in _drawn(doc, pair, store, public=True)


def test_sabotage_the_digest_check_taken_away_from_the_text_diff(tmp_path, store, monkeypatch, examined):
    doc, pair = _compared(tmp_path, store, trust="operator-authored", change=_changed)
    _sabotaged(monkeypatch, "_matches", lambda data, digest: True)
    examined(1, "sabotaged text-diff digest check")
    assert "own first" in _drawn(doc, pair, store, public=False)


def test_sabotage_the_older_sdk_rule_taken_away_from_the_text_diff(tmp_path, store, monkeypatch, examined):
    doc, pair = _compared(tmp_path, store, older=True, monkeypatch=monkeypatch)
    _sabotaged(monkeypatch, "honoured", lambda version: True)
    examined(1, "sabotaged text-diff older-SDK rule")
    assert "own first" in _drawn(doc, pair, store, public=False)


def test_sabotage_the_escaping_taken_away_puts_raw_controls_on_the_page(tmp_path, store, monkeypatch, examined):
    from html import escape as html_escape
    _require_installed()
    folder = _emit(tmp_path / "run", question=HOSTILE)
    _sabotaged(monkeypatch, "verbatim", lambda text: html_escape(text, quote=False))
    examined(1, "sabotaged escaping")
    assert ESC in _draft(folder, store)


def test_sabotage_the_older_sdk_rule_taken_away_shows_its_text(tmp_path, store, monkeypatch, examined):
    _require_installed()
    folder = _emit_older(tmp_path / "run", monkeypatch)
    monkeypatch.undo()
    _sabotaged(monkeypatch, "honoured", lambda version: True)
    examined(1, "sabotaged older-SDK rule")
    state, raw = _kept(_draft(folder, store), "question")
    assert state == "shown" and QUESTION in _text(raw)


def test_sabotage_the_unlisted_count_taken_away_drops_the_note(written, store, monkeypatch, examined):
    (written / "inputs" / _stem(written, "draft") / "stray.json").write_bytes(b'"a stray secret"')
    _sabotaged(monkeypatch, "unlisted_count", lambda files, steps: 0)
    examined(1, "sabotaged unlisted count")
    page = _pages(_stored(written, store), store)["stage-2.html"]
    assert 'data-section="unlisted-inputs"' not in page


def test_sabotage_a_missing_file_read_as_not_kept_is_caught(written, store, monkeypatch, examined):
    """The missing reading needs the listing and the absent file both; with the listing taken away
    it reads "not kept", which the test above would refuse."""
    (written / "inputs" / _stem(written, "draft") / "question.json").unlink()
    _sabotaged(monkeypatch, "listed", lambda receipt: [])
    examined(1, "sabotaged missing reading")
    assert _kept(_draft(written, store), "question")[0] == "not-kept"


# ------------------------------------------------------------------ the run's record, downloaded

def _members(tar_bytes: bytes) -> dict[str, bytes]:
    import io
    import tarfile
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        return {m.name: tar.extractfile(m).read() for m in tar.getmembers() if m.isfile()}


def _record(server, written, monkeypatch, *, public: bool) -> bytes:
    """The run's record as the console's own server answers `GET /runs/<key>/record.tar`."""
    from dataclasses import replace

    from onetrace_console.serve import Handler
    from tests.test_serve import _get
    base, _ = server
    run = _stored(written, Handler.store)
    if public:
        monkeypatch.setattr(Handler, "config", replace(Handler.config, public=True))
    status, body = _get(base, f"/runs/{run.key}/record.tar")
    assert status == 200, (status, body[:200])
    return body


def _verifies(members: dict[str, bytes], folder: Path) -> int:
    """The installed verifier's exit status on the unpacked record, outputs required."""
    for name, blob in members.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_bytes(blob)
    from onetrace_console.compare import utf8_env
    return subprocess.run([sys.executable, "-m", "onetrace_verify.cli", "--require-artifacts",
                           "MANIFEST.json"], cwd=folder, capture_output=True, env=utf8_env()).returncode


def test_a_private_consoles_record_holds_the_kept_inputs(server, written, monkeypatch, examined):
    members = _members(_record(server, written, monkeypatch, public=False))
    examined(len(members), "files in the private record")
    kept = sorted(n for n in members if n.startswith("inputs/"))
    assert kept == sorted(p.relative_to(written).as_posix() for p in (written / "inputs").rglob("*")
                          if p.is_file()) and kept, kept
    assert any(line.endswith("inputs/" + kept[0][len("inputs/"):]) for line in
               members["SHA256SUMS"].decode().splitlines())


def test_a_public_consoles_record_leaves_out_the_kept_inputs_and_still_verifies(server, written, monkeypatch,
                                                                              tmp_path, store, examined):
    from onetrace_console.ingest import accept
    members = _members(_record(server, written, monkeypatch, public=True))
    examined(len(members), "files in the public record")
    assert not [n for n in members if n.startswith("inputs/") or n == "inputs"], sorted(members)
    assert "inputs/" not in members["SHA256SUMS"].decode(), "its sums name files it doesn't hold"
    assert {n for n in members} >= {"MANIFEST.json", "SHA256SUMS"}
    assert _verifies(members, tmp_path / "unpacked") == 0
    #: And a console takes it in again: its sums name exactly the files it holds.
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name, blob in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    assert accept(buf.getvalue(), store).run is not None


def test_the_download_page_says_public_records_leave_out_kept_inputs(written, store, examined):
    from onetrace_console.kept_inputs import PUBLIC_RECORD
    run = _stored(written, store)
    public, local = _pages(run, store, public=True), _pages(run, store)
    examined(2, "receipt pages")
    page = next(k for k in public if k.endswith("receipt.html") or k == "receipt.html")
    assert PUBLIC_RECORD in _text(public[page])
    assert PUBLIC_RECORD not in _text(local[page])


def test_sabotage_a_public_record_with_its_inputs_is_caught(server, written, monkeypatch, examined):
    import onetrace_console.ingest as ingest
    real = ingest.bundle
    monkeypatch.setattr(ingest, "bundle", lambda run, store, **kw: real(run, store))
    members = _members(_record(server, written, monkeypatch, public=True))
    examined(1, "sabotaged public record")
    assert [n for n in members if n.startswith("inputs/")], "the public test above would catch it"


def test_sabotage_a_private_record_without_its_inputs_is_caught(server, written, monkeypatch, examined):
    import onetrace_console.ingest as ingest
    real = ingest.bundle
    monkeypatch.setattr(ingest, "bundle", lambda run, store, **kw: real(run, store, public=True))
    members = _members(_record(server, written, monkeypatch, public=False))
    examined(1, "sabotaged private record")
    assert not [n for n in members if n.startswith("inputs/")], "the private test above would catch it"
