"""Kept input text: shown only where the record lists it as kept and the file matches its digest.

onetrace 0.2.2 can keep a stage's text inputs beside their digests. Each kept input is stored in
`inputs/<receipt stem>/<name>.json`, holding exactly the bytes its digest was computed over, and
listed in the stage's constant `onetrace.kept_inputs`; `onetrace.inputs_not_kept` names each input
it did not keep, with why. The prefix `onetrace.` is the SDK's own from 0.2.2 on.

An input's text is shown only when both hold: its receipt lists it as kept, and the sha256 of the
stored file equals the input's digest (and the file is the JSON string the SDK writes). Otherwise
the input reads, in the SDK's own words: "not kept"; "not kept: file missing" (removing kept text is
supported, and the digest still holds); or "text does not match its digest; not shown", with both
digests and never the text. A run recorded by an SDK before 0.2.2 has no kept inputs: a constant of
its named `onetrace.kept_inputs` is its own. Files under `inputs/` that no receipt lists are never
shown; the step pages count them. On a public console an externally sourced input's kept text is
never shown, on a step page or in the text diff. This module only reads.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass

from onetrace_console.words import escape, verbatim

KEPT = "onetrace.kept_inputs"
NOT_KEPT_CONSTANT = "onetrace.inputs_not_kept"
FOLDER = "inputs"
#: The first SDK that writes the two constants, and reserves their prefix.
FIRST_SDK = (0, 2, 2)
EXTERNALLY_SOURCED = "externally-sourced"

#: The readings, in the SDK's own words (onetrace.kept).
NOT_KEPT = "not kept"
MISSING = "not kept: file missing"
MISMATCH = "text does not match its digest; not shown"
#: What the console adds.
KEPT_SAID = "kept text, matches its digest"
ERASED = "Removing kept text is supported: the input's digest still holds."
RECORDED_DIGEST = "recorded digest"
FILE_DIGEST = "the file's digest"
EXTERNAL = "kept, not shown on this public console: an externally sourced input"
OLDER_SDK = ("not kept: recorded with onetrace {version}, before kept inputs; its "
             "onetrace.kept_inputs is the run's own setting")
BANNER_KEPT = ("Outputs are stored and shown after checking; inputs from outside the run are "
               "fingerprinted, and an input's text is shown only where its step kept it and the "
               "text matches its digest.")
INPUTS_NOTE_KEPT = ("A fingerprint shows whether an input changed between runs. This page shows an "
                    "input's content where its bytes match a stored output of an earlier stage, or "
                    "where its step kept its text and the text matches its digest.")
UNTIED = "kept text not shown: this console can't tie the line to the runs' records"
PUBLIC_RECORD = ("Kept inputs aren't included in this public console's downloads: removing them is "
                 "supported, and the run still verifies without them.")
#: Kept text past this many characters is cut on the page, its full size said.
SHOWN_CAP = 4096


def older_sdk(version: str) -> str:
    return OLDER_SDK.format(version=version)


def size_said(characters: int) -> str:
    return f"{characters:,} character{'' if characters == 1 else 's'} in all"


def unlisted_note(n: int) -> str:
    return (f"{n} file{'' if n == 1 else 's'} in this run's inputs/ folder "
            f"{'is' if n == 1 else 'are'} listed by no step as kept, and never shown.")


def _constants(receipt: dict) -> dict:
    assertions = receipt.get("assertions")
    constants = assertions.get("constants") if isinstance(assertions, dict) else None
    return constants if isinstance(constants, dict) else {}


def listed(receipt: dict) -> list[str]:
    """The inputs a receipt lists as kept, in its order (the SDK joins them with ", ")."""
    value = _constants(receipt).get(KEPT)
    return [n for n in value.split(", ") if n] if isinstance(value, str) else []


def not_kept_reasons(receipt: dict) -> dict[str, str]:
    """{input: why} from `onetrace.inputs_not_kept` ("name: why; name: why")."""
    value = _constants(receipt).get(NOT_KEPT_CONSTANT)
    out: dict[str, str] = {}
    if isinstance(value, str):
        for part in value.split("; "):
            name, sep, why = part.partition(": ")
            if name and sep:
                out.setdefault(name, why)
    return out


def declares(receipt: dict) -> bool:
    """The receipt carries either of the SDK's two kept-input constants."""
    constants = _constants(receipt)
    return KEPT in constants or NOT_KEPT_CONSTANT in constants


def _version(text: str) -> tuple[int, ...] | None:
    if not re.fullmatch(r"\d+(\.\d+)*", text):
        return None
    return tuple(int(p) for p in text.split("."))


def honoured(version: str | None) -> bool:
    """Whether a run made by this SDK version has kept inputs: 0.2.2 or later. A record that
    doesn't say is read (the digest still decides what is shown); a version that isn't a plain
    release (a development build, or not a version at all) is not."""
    if version is None:
        return True
    parsed = _version(version.strip())
    return parsed is not None and parsed + (0,) * (3 - len(parsed)) >= FIRST_SDK


def recorded_with(steps: list[dict]) -> str | None:
    """The SDK version the run's intake stage records, or None where the record does not say."""
    from onetrace_console.receipt_page import INTAKE_INSTRUMENT
    for step in steps:
        instrument = step["receipt"].get("instrument")
        if isinstance(instrument, dict) and instrument.get("id") == INTAKE_INSTRUMENT:
            version = instrument.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
    return None


def _stem(receipt_file: str) -> str:
    return receipt_file.rsplit("/", 1)[-1].rsplit(".", 1)[0]


def _one_part(name: str) -> bool:
    """A name that is one path part: a kept file's name never leaves its stage's folder."""
    return bool(name) and name not in (".", "..") and "/" not in name and "\\" not in name


def _matches(data: bytes, digest: str) -> bool:
    return "sha256:" + hashlib.sha256(data).hexdigest() == digest


#: The demo's one exception: the digests of the example inputs the demo builder invents itself, set
#: only by `demo_store.allowing_examples` -- for a folder whose build record vouches for every byte
#: -- and empty otherwise. An input outside the pipeline is shown on a public console only where its
#: digest is one of these, so only the builder's own invented bytes can ever be shown; no setting or
#: store can add to them (the digests are the builder's code's, not a file's).
_EXAMPLES: frozenset = frozenset()
#: What a public console's run receipt says where the run's download includes its kept inputs.
EXAMPLE_RECORD = ("This run's kept inputs are the demo's invented example data, so this public "
                  "console shows them and its download includes them.")


def set_examples(digests) -> frozenset:
    """Set the example digests; returns the ones set before, to put back."""
    global _EXAMPLES
    before, _EXAMPLES = _EXAMPLES, frozenset(digests)
    return before


def example_allowed(digest: str) -> bool:
    """`digest` ("sha256:<hex>") is one of the demo builder's own example inputs, in a demo whose
    build record vouches for it."""
    return digest in _EXAMPLES


def hidden_here(item: dict) -> bool:
    """On a public console, an externally sourced input's kept text is never shown -- except the
    demo builder's own invented example data (`example_allowed`)."""
    from onetrace_console.frame import rendering_public
    return (rendering_public() and item.get("trust_class") == EXTERNALLY_SOURCED
            and not example_allowed(str(item.get("digest", ""))))


def _fp(digest: str) -> str:
    from onetrace_console.viewer.page import fingerprint_html
    return fingerprint_html(digest)


@dataclass(frozen=True)
class Kept:
    """One input's kept-text reading: `state` is shown, not-kept, missing, mismatch, external or
    older; `text` only where shown."""
    state: str
    text: str | None = None
    why: str | None = None
    digests: tuple[str, str] | None = None
    version: str = ""

    def words(self) -> str:
        """The reading in plain words, as the text diff says it for one side."""
        return {"not-kept": NOT_KEPT, "missing": MISSING, "mismatch": MISMATCH, "external": EXTERNAL,
                "older": older_sdk(self.version), "shown": KEPT_SAID}[self.state]


def read_kept(item: dict, receipt: dict, receipt_file: str, read, version: str | None) -> Kept | None:
    """The input's kept-text reading where its receipt declares kept inputs, or None where it
    doesn't. `read(path)` is the stored file's bytes, or None where the run holds none."""
    if not declares(receipt):
        return None
    name = str(item.get("name", ""))
    if not honoured(version):
        return Kept("older", version=version or "")
    if name not in listed(receipt):
        return Kept("not-kept", why=not_kept_reasons(receipt).get(name))
    if hidden_here(item):
        return Kept("external")
    data = read(f"{FOLDER}/{_stem(receipt_file)}/{name}.json") if _one_part(name) else None
    if data is None:
        return Kept("missing")
    digest = str(item.get("digest", ""))
    text = _text(data) if _matches(data, digest) else None
    if text is None:
        return Kept("mismatch", digests=(digest, "sha256:" + hashlib.sha256(data).hexdigest()))
    return Kept("shown", text=text)


def reading(item: dict, receipt: dict, receipt_file: str, read, version: str | None) -> str | None:
    """The input's "What's kept" cell where its receipt declares kept inputs, or None where it
    doesn't (the step page then says what it says for any input)."""
    kept = read_kept(item, receipt, receipt_file, read, version)
    if kept is None:
        return None
    if kept.state == "shown":
        return _shown(kept.text)
    if kept.state == "not-kept":
        return (f'<p data-kept="not-kept">{escape(NOT_KEPT)}'
                + (f' · <q data-words="record">{escape(kept.why)}</q>' if kept.why else "") + "</p>")
    if kept.state == "missing":
        return (f'<p data-kept="missing">{escape(MISSING)}</p>'
                f'<p class="note">{escape(ERASED)}</p>')
    if kept.state == "mismatch":
        recorded, found = kept.digests
        return (f'<p data-kept="mismatch">{escape(MISMATCH)}</p>'
                f'<p class="note">{escape(RECORDED_DIGEST)}: {_fp(recorded)} · '
                f"{escape(FILE_DIGEST)}: {_fp(found)}</p>")
    return f'<p data-kept="{kept.state}">{escape(kept.words())}</p>'


def _text(data: bytes) -> str | None:
    """The kept text: the file is the JSON string the SDK wrote, or it is not kept text."""
    from onetrace_console.bounded_json import load_json_bounded
    try:
        value = load_json_bounded(data.decode("utf-8"), "a kept input", "show")
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None
    return value if isinstance(value, str) else None


def _shown(text: str) -> str:
    from onetrace_console.viewer.page import _t
    shown = verbatim(text[:SHOWN_CAP])
    if len(text) > SHOWN_CAP:
        shown += "\n" + escape(_t("text.more", n=str(len(text) - SHOWN_CAP)))
    return (f'<p data-kept="shown"><span class="pill ok">Verified</span> {escape(KEPT_SAID)} · '
            f"{escape(size_said(len(text)))}</p><pre data-kept-text>{shown}</pre>")


def unlisted_count(files: dict[str, str], steps: list[dict]) -> int:
    """How many files under inputs/ no receipt of the run lists as kept. `files`: {path as
    delivered, normalised: object key}; `steps`: the chain's receipts, as the step pages read them."""
    from onetrace_console.ingest import same_file
    version = recorded_with(steps)
    expected = set()
    if honoured(version):
        for step in steps:
            for name in listed(step["receipt"]):
                if _one_part(name):
                    expected.add(same_file(f"{FOLDER}/{_stem(step['file'])}/{name}.json"))
    #: `same_file` spells a path with the host's own separator.
    folder = same_file(FOLDER) + os.sep
    return sum(1 for p in files if p.startswith(folder) and p not in expected)


def external_kept(steps: list[dict]) -> list[tuple[str, str]]:
    """(stage, input) for each externally sourced input a step lists as kept: what a public
    console's data must not hold (the demo holds none)."""
    if not honoured(recorded_with(steps)):
        return []
    out = []
    for step in steps:
        receipt = step["receipt"]
        stage = receipt.get("stage")
        stage = str(stage.get("name", "")) if isinstance(stage, dict) else ""
        names = set(listed(receipt))
        out += [(stage, str(i.get("name"))) for i in receipt.get("inputs") or []
                if isinstance(i, dict) and i.get("name") in names and i.get("trust_class") == EXTERNALLY_SOURCED]
    return out


# ------------------------------------------------------------------ the text diff

def _external_line(line: str) -> bool:
    """A changed input's line in the SDK's text diff that names an externally sourced input:
    `input <name> (<trust class>[ -> <trust class>]) changed: ...`. Read cautiously: any such line
    that mentions the class at all counts, so a name can only hide more, never show more."""
    return line.startswith("input ") and EXTERNALLY_SOURCED in line


def _kept_line(line: str) -> bool:
    """The SDK's lines under a changed input with both kept texts: `  - "..."` and `  + "..."`."""
    return line.startswith("  - ") or line.startswith("  + ")


def _receipt_for(steps: list[dict], node: str) -> dict | None:
    """The one step a text diff's node names (`<stage>` or `<stage>#<instance>`), or None."""
    found = []
    for step in steps:
        stage = step["receipt"].get("stage")
        if not isinstance(stage, dict):
            continue
        name, instance = str(stage.get("name", "")), stage.get("instance")
        if node == name or (instance is not None and node == f"{name}#{instance}"):
            found.append(step)
    return found[0] if len(found) == 1 else None


def _side(store, key: str | None):
    """(steps, a reader of the run's stored files, its SDK version) for one stored run, or None."""
    from onetrace_console.stage_pages import _files, _read, _steps
    run = store.get_run(key) if store is not None and key else None
    if run is None:
        return None
    files, steps = _files(run, store), _steps(run, store)
    return steps, (lambda path: _read(files, store, path)), recorded_with(steps)


def _input_named(line: str, names: set[str]) -> str | None:
    """The input a changed input's line names: the longest recorded name it starts with."""
    found = [n for n in names if line.startswith(f"input {n} (")]
    return max(found, key=len) if found else None


def _sides_read(line: str, node: str, sides) -> list[tuple[str, Kept]] | None:
    """[("baseline", reading), ("candidate", reading)] for the input `line` names, or None where
    the console can't tie the line to both runs' records."""
    found = _named_sides(line, node, sides)
    return found[1] if found else None


def _named_sides(line: str, node: str, sides) -> tuple[str, list[tuple[str, Kept]]] | None:
    """(the input's recorded name, `_sides_read`'s readings), or None."""
    if sides is None or None in sides:
        return None
    steps = [_receipt_for(s[0], node) for s in sides]
    if None in steps:
        return None
    items = [{str(i.get("name", "")): i for i in step["receipt"].get("inputs") or [] if isinstance(i, dict)}
             for step in steps]
    name = _input_named(line, set(items[0]) | set(items[1]))
    if name is None or name not in items[0] or name not in items[1]:
        return None
    out = []
    for label, step, side, its in zip(("baseline", "candidate"), steps, sides, items):
        kept = read_kept(its[name], step["receipt"], step["file"], side[1], side[2])
        out.append((label, kept if kept is not None else Kept("not-kept")))
    return name, out


def diff_lines(lines: list[str], node: str, sides, kept: list | None = None) -> list[str]:
    """A node's input lines as this console may show them. Each changed input's kept texts (the
    SDK's `  - "..."` and `  + "..."`, one escaped line each) are shown only where the console reads
    both sides as shown: listed, matching their digests, recorded by an SDK that keeps inputs, and
    not an externally sourced input on a public console. There they are taken out of the lines and
    appended to `kept` as (the input's line, its name, the baseline's text, the candidate's text),
    for a line diff of the texts as kept. Otherwise each side not shown says its reading, and a
    line the console can't tie to the records says that, never the text."""
    out: list[str] = []
    replaced: list[str] | None = None
    for line in lines:
        if not line.startswith("  "):
            replaced = None
            out.append(line)
            named = _named_sides(line, node, sides) if line.startswith("input ") else None
            read = named[1] if named else None
            #: Shown only where both sides read as shown: on a public console, the demo's own
            #: example data (`hidden_here`), and nothing else.
            hidden = (_external_line(line) and _public()
                      and not (read is not None and all(k.state == "shown" for _, k in read)))
            if hidden:
                replaced = ["  " + EXTERNAL]
            elif line.startswith("input ") and read is None:
                replaced = ["  " + UNTIED]
            elif read is not None and not all(k.state == "shown" for _, k in read):
                replaced = [f"  {label}: {k.words()}" for label, k in read if k.state != "shown"]
            elif read is not None and kept is not None:
                #: Both texts shown: drawn as a line diff below the line, not as the escaped lines.
                kept.append((line, named[0], read[0][1].text, read[1][1].text))
                replaced = []
            continue
        if replaced is not None and _kept_line(line):
            if replaced:
                out.extend(replaced)
                replaced = []
            continue
        out.append(line)
    return out


def _public() -> bool:
    from onetrace_console.frame import rendering_public
    return rendering_public()


def for_this_console(doc: dict, comparison=None, store=None) -> dict:
    """The text diff as this console may show it (`diff_lines`), the comparison's two stored runs
    read for it. The document is read strictly before this, and is not changed."""
    sides = None
    if comparison is not None:
        sides = (_side(store, getattr(comparison, "run_a", None)),
                 _side(store, getattr(comparison, "run_b", None)))
    nodes = []
    for n in doc.get("nodes", []):
        kept: list = []
        nodes.append({**n, "inputs": diff_lines(list(n.get("inputs") or []), str(n.get("node", "")), sides, kept),
                      KEPT_DIFFS: kept})
    return {**doc, "nodes": nodes}


#: The key `for_this_console` gives each node for its kept texts, drawn as line diffs.
KEPT_DIFFS = "_kept_diffs"
