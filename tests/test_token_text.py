"""A model step's token as text, beside its record (`token_text`), on a step page's token timeline.

1. A tokenizer the console's local settings name, whose files hash as named to the record's
   `tokenizer.digest`, decodes each step's token, labelled "decoded with tokenizer <digest>, from
   <folder>: <file>, <file>, on this machine"; the digest is reproduced here with onetrace's own
   `manifest_digest`, never typed.
2. Named files that hash to another digest are refused, with both digests, and nothing is decoded;
   so is a named file that is not there, and a tokenizer.json with no `tokenizers` package to read it.
3. With no tokenizer named, the page says the word cannot be shown and shows the step and the ids only.

The tokenizer is a word-level one built here with the `tokenizers` package and saved as
tokenizer.json: test data, written for these tests; no model is called and nothing is downloaded.
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

from onetrace_console import model_call as mc

VOCAB = {"[UNK]": 0, "the": 1, "cat": 2, "sat": 3, "mat": 4, "on": 5}
IDS = ["1", "2", "3", "5", "1", "4"]
WORDS = ["the", " cat", " sat", " on", " the", " mat"]


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _tokenizer_json() -> bytes:
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers.models import WordLevel
    from tokenizers.pre_tokenizers import Whitespace
    tok = tokenizers.Tokenizer(WordLevel(VOCAB, unk_token="[UNK]"))
    tok.pre_tokenizer = Whitespace()
    return tok.to_str().encode("utf-8")


def _digest(files: dict[str, bytes]) -> str:
    from onetrace.model_call import manifest_digest
    return manifest_digest({n: hashlib.sha256(b).hexdigest() for n, b in files.items()})


def _folder(tmp_path, files: dict[str, bytes]):
    folder = tmp_path / "tok"
    folder.mkdir(exist_ok=True)
    for name, data in files.items():
        (folder / name).write_bytes(data)
    return str(folder)


def step_page(tokenizer_digest: str | None, named=(), *, public: bool = False, ids=IDS) -> str:
    """A step's model-call section, drawn under a console's settings, its record naming
    `tokenizer_digest` (observed) and a steps file of `ids`."""
    from onetrace import model_call as m
    from onetrace_console.frame import rendering
    from tests.test_model_call import raw, record
    steps = json.dumps({"level": "L1", "token_ids": ids}).encode()
    over = {"steps": m.observed("sha256:" + hashlib.sha256(steps).hexdigest(), "model_call.steps.json")}
    if tokenizer_digest is not None:
        over["tokenizer.digest"] = m.observed(tokenizer_digest, "written for this test")
    files = {"model_call.json": raw(record(**over)), "model_call.steps.json": steps}
    receipt = {"outputs": [{"name": n, "digest": "sha256:" + hashlib.sha256(b).hexdigest()} for n, b in files.items()]}
    read = {f"artifacts/02-call/{n}": b for n, b in files.items()}.get
    with rendering(onedoor=False, sign_in=False, public=public, tokenizers=named):
        return mc.step_section(receipt, "receipts/02-call.json", read)


def _words(page: str) -> list[str]:
    return [html.unescape(w) for w in re.findall(r"<code class=\"token-text\">([^<]*)</code>", page)]


def test_a_matching_tokenizer_decodes_each_step_with_the_label(tmp_path, examined):
    files = {"tokenizer.json": _tokenizer_json(), "vocab-note.txt": b"written for this test\n"}
    digest = _digest(files)
    folder = _folder(tmp_path, files)
    page = step_page(digest, ((folder, tuple(files)),))
    examined(len(IDS), "decoded steps")
    assert f"decoded with tokenizer {digest}, from {folder}: tokenizer.json, vocab-note.txt, on this machine" in _text(page), \
        "the label names the folder and each file used, as named"
    assert _words(page) == WORDS
    rows = re.findall(r'data-decode-step="(\d+)"><td[^>]*>\d+</td><td[^>]*><code>(\d+)</code>', page)
    assert rows == [(str(i), t) for i, t in enumerate(IDS)], "the step and its id stay beside the word"
    assert "cannot be shown" not in page


def test_files_that_hash_to_another_digest_are_refused_and_nothing_is_decoded(tmp_path, examined):
    files = {"tokenizer.json": _tokenizer_json()}
    folder = _folder(tmp_path, files)
    want = _digest({"tokenizer.json": b"another tokenizer"})
    page = step_page(want, ((folder, ("tokenizer.json",)),))
    examined(1, "tokenizer whose files hash to another digest")
    said = _text(page)
    assert f"refused: {folder}: its named files hash to {_digest(files)}, not {want}" in said
    assert (f"The word at each step cannot be shown: no tokenizer this console names hashes to the record's "
            f"tokenizer.digest {want}. The step and its token id are shown.") in said
    assert "data-decoded" not in page and 'class="token-text"' not in page
    assert len(re.findall(r"data-decode-step=", page)) == len(IDS)


def test_the_same_files_named_differently_hash_differently_and_are_refused(tmp_path, examined):
    """The digest is of the files as named: the same bytes under another name are another tokenizer."""
    data = _tokenizer_json()
    folder = _folder(tmp_path, {"tokenizer.json": data})
    page = step_page(_digest({"tok/tokenizer.json": data}), ((folder, ("tokenizer.json",)),))
    examined(1, "tokenizer named another way")
    assert "data-tokenizer-refused" in page and 'class="token-text"' not in page


def test_a_named_file_that_is_not_there_is_refused(tmp_path, examined):
    folder = _folder(tmp_path, {"tokenizer.json": b"{}"})
    page = step_page("sha256:" + "a" * 64, ((folder, ("tokenizer.json", "merges.txt")),))
    examined(1, "named file not there")
    assert f"refused: {folder}: merges.txt is not a file in it" in _text(page)
    assert 'class="token-text"' not in page


def test_matching_files_with_no_tokenizers_package_are_said_and_not_decoded(tmp_path, monkeypatch, examined):
    import sys
    files = {"tokenizer.json": b'{"written for this test": true}'}
    folder = _folder(tmp_path, files)
    monkeypatch.setitem(sys.modules, "tokenizers", None)
    page = step_page(_digest(files), ((folder, ("tokenizer.json",)),))
    examined(1, "tokenizer with no package to read it")
    assert "the tokenizers package is not installed" in _text(page)
    assert 'class="token-text"' not in page


@pytest.mark.parametrize("named, why", [
    ((), "this console's local settings name no tokenizer"),
    ((("/nowhere", ("tokenizer.json",)),), None),
])
def test_with_no_matching_tokenizer_the_page_shows_the_step_and_the_ids_only(named, why, examined):
    page = step_page("sha256:" + "a" * 64, named)
    examined(1, "page without a matching tokenizer")
    said = _text(page)
    assert "The word at each step cannot be shown" in said
    if why:
        assert f"cannot be shown: {why}." in said
    assert 'class="token-text"' not in page and "<th>decoded text</th>" not in page
    rows = re.findall(r'data-decode-step="(\d+)"><td[^>]*>\d+</td><td[^>]*><code>(\d+)</code></td></tr>', page)
    assert rows == [(str(i), t) for i, t in enumerate(IDS)]


def test_a_record_with_no_tokenizer_digest_is_not_decoded(tmp_path, examined):
    files = {"tokenizer.json": b"{}"}
    page = step_page(None, ((_folder(tmp_path, files), ("tokenizer.json",)),))
    examined(1, "record with no tokenizer digest")
    assert "cannot be shown: the record states no tokenizer.digest." in _text(page)


WIN = r"C:\Users\operator\tok"


def test_a_windows_folder_is_said_as_written_with_its_backslashes_single(monkeypatch, examined):
    """A folder and a file name the console was given are said as `words.path_text` says a path,
    never with a backslash doubled. The folder is not there on any machine, so this runs, and reads
    the same, on every platform, with or without the tokenizers package."""
    from onetrace_console import token_text
    doubled = WIN.replace("\\", "\\\\")
    refused = _text(step_page("sha256:" + "a" * 64, ((WIN, ("tokenizer.json",)),)))

    class Ids:
        """Not a tokenizer: no file is read here, and only the label is checked."""
        def decode(self, nums, skip_special_tokens):
            return " ".join(map(str, nums))

    dec = token_text.Decoder("sha256:" + "a" * 64, Ids(), WIN, (r"sub\tokenizer.json",))
    monkeypatch.setattr(token_text, "decoder", lambda record, named: (dec, "", []))
    decoded = _text(step_page("sha256:" + "a" * 64, ((WIN, ("tokenizer.json",)),)))
    examined(2, "pages naming a Windows folder")
    assert f"refused: {WIN}: tokenizer.json is not a file in it" in refused and doubled not in refused
    assert (f"decoded with tokenizer sha256:{'a' * 64}, from {WIN}: sub\\tokenizer.json, on this machine"
            in decoded) and doubled not in decoded
