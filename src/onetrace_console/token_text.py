"""A model step's token as text, beside its record, on a local console only.

The record and its steps file hold token ids, never text. Where the person names a tokenizer in the
console's local settings (`tokenizers`: a folder and the files in it), the console hashes those files
as onetrace 0.6.1 defines the record's `tokenizer.digest`: `onetrace.model_call.manifest_digest` of
{each file's name, as named: its sha256, as hex} (`onetrace/model_call/record.py:268-270`). Only where
that equals the record's `tokenizer.digest` exactly are the ids decoded, each step's token in the
context of the steps just before it, and labelled "decoded with tokenizer <digest>, from <folder>: <file>,
<file>, on this machine", naming the folder and the files used.
Named files that hash to another digest are refused, with both digests. With no tokenizer that
matches, the page says the word cannot be shown and shows the step and the ids only.

Decoding reads the named `tokenizer.json` with the `tokenizers` package, from the very bytes that
were hashed. The console never downloads a tokenizer and makes no network calls. A public console
reads no tokenizer and shows the ids only, as before: decoding there would publish the model's output
text.

Beside each decoded word, a literal search of the kept inputs of its step and of the steps it came
from (each step whose stored output or receipt one of its inputs matches, and theirs in turn):
"appears in: <input> (<step>)", or "appears in no kept input". An input whose text is not kept is
listed as "not kept, not searched". It is a string match and says nothing about meaning.

A folder or a file name the console was given is said as written, its backslashes single
(`words.path_text`): on Windows they are its separators. The rest of each line is escaped as a
record's words are (`words.escape`).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.words import escape, path_text

DECODED = "decoded with tokenizer {digest}, from {folder}: {files}, on this machine"
CANNOT = "The word at each step cannot be shown: {why}. The step and its token id are shown."
NONE_NAMED = "this console's local settings name no tokenizer"
NO_DIGEST = "the record states no tokenizer.digest"
NONE_MATCH = "no tokenizer this console names hashes to the record's tokenizer.digest {digest}"
REFUSED = "refused: {folder}: {why}"
OTHER_DIGEST = "its named files hash to {got}, not {want}"
MISSING = "{name} is not a file in it"
TOO_BIG = "{name} is {size} bytes, over the {most} this console reads"
NO_JSON = "none of its named files is tokenizer.json, the one form this console decodes"
NO_PACKAGE = "the tokenizers package is not installed (the console's [neighbours] extra installs it)"
NOT_READ = "its tokenizer.json is not one the tokenizers package reads ({why})"
NOT_DECODED = "not decoded: {why}"

SEARCH = ("Each word is searched for, as a literal string, in the kept inputs of this step and of the steps "
          "it came from: the steps whose stored output or receipt one of its inputs matches, and theirs. "
          "A string match says nothing about meaning.")
SEARCHED = "Searched: {inputs}."
SEARCHED_NONE = "Searched: no kept input."
NOT_KEPT = "not kept, not searched: {inputs}"
KEPT_NOT_SEARCHED = "kept, not searched: {inputs}"
APPEARS_IN = "appears in: {inputs}"
APPEARS_IN_NONE = "appears in no kept input"
ONLY_SPACE = "white space only; not searched"
WORD_HEADING = "decoded text"
FOUND_HEADING = "appears in"

#: A named tokenizer file past this size is refused, not read.
MOST_BYTES = 64 << 20
#: The steps before step n decoded with it, so its word reads as it does in context.
CONTEXT = 8
#: The one tokenizer form this console decodes.
JSON_NAME = "tokenizer.json"


class Refused(Exception):
    """A named tokenizer is not used, said in words; `html`, the same words as a page shows them."""

    def __init__(self, template: str, paths: tuple = (), **values):
        super().__init__(template.format(**values))
        self.html = _html(template, paths, **values)


def _html(template: str, paths: tuple = (), **values) -> str:
    """`template` as a page shows it: each value named in `paths` as written (`path_text`), the
    rest escaped."""
    return escape(template).format(**{k: path_text(v) if k in paths else escape(v) for k, v in values.items()})


@dataclass(frozen=True)
class Input:
    """One input searched, or not, for a step's word: its name, its step, and its kept text or None
    with the reason it is not searched (`not-kept` or the kept-input reading's words)."""
    name: str
    step: str
    text: str | None
    kept: bool = False
    why: str = ""

    def label(self) -> str:
        return f"{self.name} ({self.step})"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hashed(folder: str, files: tuple) -> tuple[str, dict[str, bytes]]:
    """(the tokenizer digest of the named files, {name: bytes}); `Refused` where one is not read."""
    from onetrace.model_call import manifest_digest
    blobs = {}
    for name in files:
        path = Path(folder) / name
        if not path.is_file():
            raise Refused(MISSING, ("name",), name=name)
        size = path.stat().st_size
        if size > MOST_BYTES:
            raise Refused(TOO_BIG, ("name",), name=name, size=size, most=MOST_BYTES)
        blobs[name] = path.read_bytes()
    return manifest_digest({name: _sha256(b) for name, b in blobs.items()}), blobs


def recorded_digest(record: dict) -> str | None:
    """The record's `tokenizer.digest`, where observed or declared."""
    v = record.get("tokenizer.digest")
    if isinstance(v, dict) and v.get("status") in ("observed", "declared") and isinstance(v.get("value"), str):
        return v["value"]
    return None


class Decoder:
    """A tokenizer whose named files, in `folder`, hash to a record's `tokenizer.digest`."""

    def __init__(self, digest: str, tokenizer, folder: str = "", files: tuple = ()):
        self.digest, self._tok, self.folder, self.files = digest, tokenizer, folder, tuple(files)

    def label(self) -> str:
        return DECODED.format(digest=self.digest, folder=self.folder, files=", ".join(self.files))

    def label_html(self) -> str:
        """The label as a page shows it: the folder and the files as written."""
        return escape(DECODED).format(digest=escape(self.digest), folder=path_text(self.folder),
                                      files=", ".join(path_text(f) for f in self.files))

    def word(self, ids: list[str], n: int) -> str:
        """Step n's token as text, read in the context of the steps just before it."""
        lo = max(0, n - CONTEXT)
        nums = [int(i) for i in ids[lo:n + 1]]
        before = self._tok.decode(nums[:-1], skip_special_tokens=False)
        with_it = self._tok.decode(nums, skip_special_tokens=False)
        if with_it.startswith(before):
            return with_it[len(before):]
        return self._tok.decode(nums[-1:], skip_special_tokens=False)


def _load(blobs: dict[str, bytes]):
    name = next((n for n in blobs if Path(n).name == JSON_NAME), None)
    if name is None:
        raise Refused(NO_JSON)
    try:
        from tokenizers import Tokenizer
    except ImportError:
        raise Refused(NO_PACKAGE) from None
    try:
        return Tokenizer.from_str(blobs[name].decode("utf-8"))
    except Exception as e:  # noqa: BLE001 - any file the package does not read is refused, said
        raise Refused(NOT_READ, why=str(e).splitlines()[0] if str(e) else type(e).__name__) from None


def decoder(record: dict, named: tuple) -> tuple[Decoder | None, str, list[str]]:
    """(the decoder, or None; where None, the reason the word cannot be shown; each named tokenizer
    refused, with its reason, as a page shows it). `named`: the console's tokenizers, each (folder,
    (file, ...))."""
    if not named:
        return None, NONE_NAMED, []
    want = recorded_digest(record)
    if want is None:
        return None, NO_DIGEST, []
    refused = []
    for folder, files in named:
        try:
            got, blobs = hashed(folder, tuple(files))
            if got != want:
                raise Refused(OTHER_DIGEST, got=got, want=want)
            return Decoder(want, _load(blobs), folder, tuple(files)), "", refused
        except Refused as e:
            refused.append(escape(REFUSED).format(folder=path_text(folder), why=e.html))
    return None, NONE_MATCH.format(digest=want), refused


def appears(word: str, searched: list[Input]) -> tuple[str, str]:
    """(the state, the line) for one word: `in`, `none` or `space`."""
    needle = word.strip()
    if not needle:
        return "space", ONLY_SPACE
    hits = [i.label() for i in searched if i.text is not None and needle in i.text]
    if hits:
        return "in", APPEARS_IN.format(inputs=", ".join(hits))
    return "none", APPEARS_IN_NONE


def search_note(searched: list[Input]) -> str:
    """What the search covers, said once above the timeline."""
    kept = [i.label() for i in searched if i.text is not None]
    not_kept = [i.label() for i in searched if i.text is None and not i.kept]
    other = [f"{i.label()}, {i.why}" for i in searched if i.text is None and i.kept]
    out = (f'<p class="label" data-search-note>{escape(SEARCH)}</p>'
           f'<p data-searched>{escape(SEARCHED.format(inputs=", ".join(kept)) if kept else SEARCHED_NONE)}</p>')
    if not_kept:
        out += f'<p data-not-searched="not-kept">{escape(NOT_KEPT.format(inputs=", ".join(not_kept)))}</p>'
    if other:
        out += f'<p data-not-searched="kept">{escape(KEPT_NOT_SEARCHED.format(inputs="; ".join(other)))}</p>'
    return out


def cells(dec: Decoder, ids: list[str], n: int, searched: list[Input] | None = None) -> str:
    """Step n's word, as decoded, and where `searched` is given, where it appears."""
    try:
        word = dec.word(ids, n)
    except Exception as e:  # noqa: BLE001 - an id the tokenizer does not hold is said, never guessed
        return (f'<td data-decoded="no">{escape(NOT_DECODED.format(why=e))}</td>'
                + ("<td></td>" if searched is not None else ""))
    out = f'<td data-decoded="yes"><code class="token-text">{escape(word)}</code></td>'
    if searched is None:
        return out
    state, line = appears(word, searched)
    if state == "none":
        not_kept = [i.label() for i in searched if i.text is None and not i.kept]
        if not_kept:
            line += " · " + NOT_KEPT.format(inputs=", ".join(not_kept))
    return out + f'<td data-appears="{state}">{escape(line)}</td>'


def searched_inputs(steps: list[dict], read, version: str | None) -> dict[int, list[Input]]:
    """{position of a step in `steps`: the inputs searched for its words}: its own, then those of the
    steps it came from -- each earlier step whose stored output or receipt one of its inputs matches
    by digest, and theirs in turn -- each with its kept text, or the reason it is not searched.
    `read(path)`: a stored file's bytes, or None."""
    from onetrace_console import kept_inputs
    from onetrace_console.stage_pages import _artifact_path, _stage_name

    def inputs(step):
        return [i for i in step["receipt"].get("inputs") or [] if isinstance(i, dict)]

    produced: dict[str, int] = {}
    came: dict[int, set[int]] = {}
    for n, step in enumerate(steps):
        came[n] = {produced[str(i.get("digest", ""))] for i in inputs(step) if str(i.get("digest", "")) in produced}
        for o in step["receipt"].get("outputs") or []:
            if isinstance(o, dict):
                path = _artifact_path(step["file"], str(o.get("name", "")))
                blob = read(path)
                digest = str(o.get("digest", ""))
                if blob is not None and "sha256:" + _sha256(blob) == digest:
                    produced.setdefault(digest, n)
        stored = read(step["file"])
        if stored is not None:
            produced.setdefault("sha256:" + _sha256(stored), n)

    def own(n):
        step, out = steps[n], []
        for i in inputs(step):
            name, stage = str(i.get("name", "")), _stage_name(step["receipt"])
            k = kept_inputs.read_kept(i, step["receipt"], step["file"], read, version)
            if k is not None and k.state == "shown":
                out.append(Input(name, stage, k.text, True))
            elif k is not None and k.state in ("mismatch", "external"):
                out.append(Input(name, stage, None, True, k.words()))
            else:
                out.append(Input(name, stage, None))
        return out

    result = {}
    for n in range(len(steps)):
        seen, order, todo = {n}, [n], sorted(came[n], reverse=True)
        while todo:
            m = todo.pop(0)
            if m not in seen:
                seen.add(m)
                order.append(m)
                todo += sorted(came[m] - seen, reverse=True)
        result[n] = [i for m in order for i in own(m)]
    return result
