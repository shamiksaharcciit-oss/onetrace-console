"""Each decoded word, searched for as a literal string in the kept inputs of its step and of the steps
it came from (`token_text.searched_inputs`), on a local console's step page.

1. A word a kept input holds reads "appears in: <input> (<step>)", naming each such input, the step's
   own and those of the step it came from.
2. A word no kept input holds reads "appears in no kept input", and names beside it each input that was
   not kept as "not kept, not searched": the result never reads as in no input when some were not kept.
3. The page says once what was searched and what was not, and that it is a string match.

The run is written here by the installed onetrace: `prep` keeps `question` and not `note`; `call` keeps
`system` and not `extra` (and the SDK keeps no earlier stage's output, so prep's output reaches it as
`receipt:prep`, not kept), and writes a model-call record naming the test's tokenizer and
a steps file. Test data, written for these tests; no model is called and nothing is downloaded.
"""
from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path

import pytest

from tests.test_token_text import IDS, _digest, _folder, _text, _tokenizer_json

QUESTION = "Where is the cat?"
NOTE = "the mat is not kept"
EXTRA = "on the mat, not kept either"
SYSTEM = "Answer about a cat."


def _record_run(folder: Path, tokenizer_digest: str) -> Path:
    import onetrace as ot
    from onetrace import model_call as m
    from onetrace.emit import Instrument, current_stage
    from tests.test_model_call import raw, record

    @ot.stage("prep", instrument=Instrument("tool", "tool", "1.0.0", {}), keep_inputs=["question"],
              trust="operator-authored")
    def prep(question, note):
        return "Q: " + question

    @ot.stage("call", instrument=Instrument("example-model", "model", "1.0.0", {}), keep_inputs=["system"],
              trust="operator-authored")
    def call(prompt, system, extra):
        digest, name = m.write_steps(current_stage(), "model_call.json", {"token_ids": IDS, "level": "L1"})
        rec = record(**{"tokenizer.digest": m.observed(tokenizer_digest, "written for this test"),
                        "steps": m.observed(digest, name)})
        current_stage().write("model_call.json", raw(rec), "application/json")
        return "answered"

    @ot.run(str(folder), stages=["prep", "call"])
    def pipeline(q):
        return call(prep(QUESTION, NOTE), SYSTEM, EXTRA)

    pipeline("written for this test")
    return folder


@pytest.fixture
def page(tmp_path, store):
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from tests.test_checks import _require_installed
    from tests.test_stage_pages import _stored
    _require_installed()
    files = {"tokenizer.json": _tokenizer_json()}
    folder = _folder(tmp_path, files)
    run = _stored(_record_run(tmp_path / "run", _digest(files)), store)
    with rendering(onedoor=False, sign_in=False, tokenizers=((folder, ("tokenizer.json",)),)):
        pages = render_execution(run, store, generated_at="2026-11-02T00:00:00+00:00").pages
    return next(p for p in pages.values() if 'data-token-timeline-of="model_call.json"' in p)


def _rows(page: str) -> dict[str, tuple[str, str]]:
    """{word, stripped: (data-appears state, the cell's text)} for each decoded step."""
    out = {}
    for word, state, cell in re.findall(r'<code class="token-text">([^<]*)</code></td><td[^>]*data-appears="(\w+)"'
                                        r'[^>]*>([^<]*)</td>', page):
        out[html.unescape(word).strip()] = (state, html.unescape(cell))
    return out


def test_a_word_a_kept_input_holds_names_each_input_and_its_step(page, examined):
    rows = _rows(page)
    examined(len(rows), "decoded words searched")
    assert rows["cat"][0] == "in"
    assert rows["cat"][1] == "appears in: system (call), question (prep)"
    assert rows["the"][1] == "appears in: question (prep)", "a word only the earlier step's input holds"


def test_a_word_no_kept_input_holds_says_so_and_names_what_was_not_kept(page, examined):
    rows = _rows(page)
    examined(1, "word in no kept input")
    state, cell = rows["mat"]
    assert state == "none"
    assert cell.startswith("appears in no kept input · not kept, not searched: ")
    for name in ("receipt:prep (call)", "extra (call)", "note (prep)"):
        assert name in cell, "an input that was not kept is named, never read as searched"
    assert "mat" in NOTE and "mat" in EXTRA, "the word is in inputs that were not kept, and the page does not claim otherwise"


def test_the_page_says_what_was_searched_and_that_it_is_a_string_match(page, examined):
    said = _text(page)
    examined(1, "search note")
    assert "Each word is searched for, as a literal string, in the kept inputs of this step and of the steps it came from" in said
    assert "A string match says nothing about meaning." in said
    assert "Searched: system (call), question (prep)." in said
    assert re.search(r"not kept, not searched: [^<]*extra \(call\)", said)
