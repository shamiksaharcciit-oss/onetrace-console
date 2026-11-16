"""A tokenizer the person picks on a model step's page, kept by this console: on a local console only.

Where a model step's token cannot be shown as text for want of a tokenizer whose files hash to its
record's `tokenizer.digest`, the token timeline offers a picker: one `tokenizer.json`, or a zip of the
tokenizer's files. The console hashes what was picked as onetrace defines `tokenizer.digest`
(`token_text.hashed`: `onetrace.model_call.manifest_digest` of {each file's name: its sha256}) and keeps
it only where that equals the record's digest exactly: nothing is written before. It is kept in the
store's own folder, `tokenizers/<the digest's hex>/`, with a `kept.json` that names its files, and is
used from then on as a configured tokenizer is. Settings lists each kept tokenizer with Remove.

The limits: a local console only (a public console has no picker and refuses the route unread); at
most `MOST_UPLOAD` bytes, refused by its declared length before a byte is read; a zip's members each
checked before anything is read from it -- a plain file name (no folder that climbs out, no absolute
path, no link), no two with the same name, at most `MOST_MEMBERS` of them, each at most
`token_text.MOST_BYTES` and all together at most `MOST_UPLOAD` uncompressed -- and no network: nothing
is fetched, and the package that decodes reads the very bytes that were hashed.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import stat
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

FOLDER = "tokenizers"
FORMAT = "onetrace-console-tokenizer/1"
KEPT = "kept.json"
#: The most an upload may hold, and a zip's members together, uncompressed.
MOST_UPLOAD = 100 * 1024 * 1024
MOST_MEMBERS = 64
_DIGEST = re.compile(r"sha256:([0-9a-f]{64})")
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")

PICK = "Use a tokenizer from this machine"
PICK_FIELD = "tokenizer.json, or a zip of the tokenizer's files (at most 100 MB)"
PICK_NOTE = (
    "The console keeps it only where its files hash to this record's tokenizer.digest; it reads it on "
    "this machine, and fetches nothing."
)
PATH = "model-tokenizers"
SETTINGS_HEADING = "Tokenizers kept by this console"
SETTINGS_NONE = (
    "This console keeps no tokenizer. A model step's page offers to take one where its token can't be shown."
)
REMOVE = "Remove"
#: The model steps that ask for a tokenizer: the list above the kept ones.
STEPS_HEAD = "Model steps that ask for a tokenizer"
LEAD = (
    "On a step's page below, pick the model's tokenizer.json, or a zip of its files with no folders inside; the "
    "console keeps it only where its files hash to the step's tokenizer.digest."
)
NO_STEP = (
    "No model step in this console needs a tokenizer: every model step's tokens are shown, or its record states "
    "no tokenizer."
)
EXAMPLE = "Example data: this digest was constructed for the demo, so no real tokenizer's files match it."
MISSING_PACKAGE = (
    "The tokenizers package is not installed in the Python this console runs from, so no tokenizer can be used "
    "here yet:"
)
MOST_LISTED = 20
ROW = "{digest}: {files}, {size} bytes, kept {when}"
OTHER_DIGEST = "its files hash to {got}, not this record's tokenizer.digest {want}; nothing was kept"


class UploadError(ValueError):
    """An upload refused, said in words; nothing was kept."""


def root(store_dir) -> Path:
    """`store_dir`: the store's own folder (`Store.root`)."""
    return Path(store_dir) / FOLDER


def folder_of(store_dir, digest: str) -> Path:
    m = _DIGEST.fullmatch(digest or "")
    if m is None:
        raise UploadError(f"not a tokenizer digest: {digest!r}")
    return root(store_dir) / m.group(1)


def files_of(data: bytes, name: str) -> dict[str, bytes]:
    """{file name: bytes} of one picked file: a zip's members, each checked first, or one tokenizer.json."""
    if len(data) > MOST_UPLOAD:
        raise UploadError(f"the file is {len(data)} bytes, over the {MOST_UPLOAD} this console takes")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        if PurePosixPath(name.replace("\\", "/")).name != "tokenizer.json":
            raise UploadError("pick tokenizer.json itself, or a zip of the tokenizer's files")
        return {"tokenizer.json": data}
    from onetrace_console.token_text import MOST_BYTES

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        members = [i for i in z.infolist() if not i.is_dir()]
        if len(members) > MOST_MEMBERS:
            raise UploadError(f"the zip holds {len(members)} files; this console takes at most {MOST_MEMBERS}")
        names: dict[str, zipfile.ZipInfo] = {}
        total = 0
        for i in members:
            path = PurePosixPath(i.filename.replace("\\", "/"))
            mode = (i.external_attr >> 16) & 0o170000
            if path.is_absolute() or ".." in path.parts or ":" in i.filename or mode == stat.S_IFLNK:
                raise UploadError(f"the zip's member {i.filename!r} is not a plain file inside it")
            if not _NAME.fullmatch(path.name):
                raise UploadError(f"the zip's member {i.filename!r} is not named as a tokenizer's file is")
            if path.name in names:
                raise UploadError(
                    f"the zip holds two files named {path.name}: {names[path.name].filename!r} and {i.filename!r}"
                )
            if i.file_size > MOST_BYTES:
                raise UploadError(
                    f"the zip's member {path.name} is {i.file_size} bytes, over the {MOST_BYTES} this console reads"
                )
            total += i.file_size
            if total > MOST_UPLOAD:
                raise UploadError(f"the zip's files together are over the {MOST_UPLOAD} bytes this console takes")
            names[path.name] = i
        out = {}
        for n, i in names.items():
            blob = z.read(i)
            if len(blob) != i.file_size:
                raise UploadError(f"the zip's member {n} is not the size the zip says")
            out[n] = blob
    if not out:
        raise UploadError("the zip holds no file")
    return out


def digest_of(files: dict[str, bytes]) -> str:
    """The tokenizer digest of `files`, as onetrace defines `tokenizer.digest`."""
    from onetrace.model_call import manifest_digest

    return manifest_digest({n: hashlib.sha256(b).hexdigest() for n, b in files.items()})


def keep(store_dir, want: str, data: bytes, name: str, *, when: str | None = None) -> dict:
    """Keep the picked tokenizer under `want`, only where its files hash to `want`; `UploadError` else."""
    from onetrace_console.store import _atomic_write
    from onetrace_console.token_text import JSON_NAME

    target = folder_of(store_dir, want)
    files = files_of(data, name)
    got = digest_of(files)
    if got != want:
        raise UploadError(OTHER_DIGEST.format(got=got, want=want))
    if JSON_NAME not in files:
        raise UploadError("none of its files is tokenizer.json, the one form this console decodes")
    tmp = target.with_name(target.name + ".part")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for n, b in files.items():
        (tmp / n).write_bytes(b)
    entry = {
        "format": FORMAT,
        "digest": want,
        "files": sorted(files),
        "bytes": sum(len(b) for b in files.values()),
        "picked": PurePosixPath(name.replace("\\", "/")).name,
        "when": when or datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _atomic_write(tmp / KEPT, (json.dumps(entry, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return entry


def kept(store_dir) -> list[dict]:
    """Each tokenizer kept, whose folder and record read, by digest."""
    out = []
    base = root(store_dir)
    for d in (
        sorted(p for p in base.iterdir() if p.is_dir() and re.fullmatch(r"[0-9a-f]{64}", p.name))
        if base.is_dir()
        else ()
    ):
        try:
            entry = load_json_bounded((d / KEPT).read_text(encoding="utf-8"), "a kept tokenizer's record")
        except (OSError, ValueError, RecursionError):
            continue
        if (
            isinstance(entry, dict)
            and entry.get("format") == FORMAT
            and entry.get("digest") == f"sha256:{d.name}"
            and isinstance(entry.get("files"), list)
            and all(isinstance(f, str) for f in entry["files"])
        ):
            out.append(dict(entry, folder=str(d)))
    return out


def named(store_dir) -> tuple:
    """The kept tokenizers as the console names its configured ones: each (folder, (file, ...))."""
    return tuple((e["folder"], tuple(e["files"])) for e in kept(store_dir))


def remove(store_dir, digest: str) -> bool:
    target = folder_of(store_dir, digest)
    had = target.is_dir()
    shutil.rmtree(target, ignore_errors=True)
    return had


def example_digests() -> frozenset:
    """The `tokenizer.digest` values the demo's builder constructs for its example records: no real tokenizer's files
    hash to them."""
    from onetrace_console.demo_store.model_call_example import _digest

    return frozenset({_digest("the tokenizer's files")})


def can_decode() -> bool:
    """Whether the package that decodes (`tokenizers`) is importable in the Python this console runs from."""
    import importlib.util

    return importlib.util.find_spec("tokenizers") is not None


def missing_package() -> str:
    """Why no tokenizer can be used yet, with the install line for this console's Python."""
    import sys

    from onetrace_console.neighbours.pages import _install_named
    from onetrace_console.words import verbatim

    return (
        f"<div data-tokenizers-missing><p>{escape(MISSING_PACKAGE)} <code>{verbatim(sys.executable or '')}</code></p>"
        f"<pre><code>pip install tokenizers</code></pre>{_install_named(verbatim, 'tokenizers')}</div>"
    )


def wanting(store, named: tuple) -> list[tuple[str, str, str, str, str]]:
    """Each model step in `store` whose record states a `tokenizer.digest` no tokenizer in `named` (each (folder,
    (file, ...))) hashes to: (the digest, the run's key, its run id, the step's index, the step's name)."""
    from onetrace_console import model_call as mc
    from onetrace_console import token_text
    from onetrace_console.model_call_compare import _steps_by_name

    have = set()
    for folder, files in named:
        try:
            have.add(token_text.hashed(folder, tuple(files))[0])
        except token_text.Refused:
            continue
    out = []
    for run in store.runs():
        try:
            steps = _steps_by_name(run, store)
        except Exception:  # noqa: BLE001 - a run that can't be read asks for nothing here
            continue
        for s in steps:
            for o in mc.outputs(s["receipt"]):
                try:
                    record = mc.read_output(s["file"], o, s["read"])
                except mc.Refused:
                    continue
                want = token_text.recorded_digest(record)
                if want is not None and want not in have:
                    out.append((want, run.key, run.run_id, str(s["index"]), str(s["name"])))
    return out


def grouped(entries) -> dict[str, list[tuple[str, str, str, str]]]:
    """{digest: [(run key, run id, step index, step name), ...]}, in the order met."""
    out: dict[str, list[tuple[str, str, str, str]]] = {}
    for digest, key, run_id, index, name in entries:
        out.setdefault(digest, []).append((key, run_id, index, name))
    return out


def wanted_section(groups: dict, *, example: frozenset, decodes: bool) -> str:
    """The list of the steps that ask for a tokenizer: each digest short, and whole in a fold, its count, and a link to
    each of its first MOST_LISTED steps' pages, where the picker is; the example-data line where the demo's builder
    constructed it; the install line where the package that decodes is missing."""
    from onetrace_console.stage_pages import stage_page

    head = f'<section data-section="tokenizers-wanted"><h2>{escape(STEPS_HEAD)}</h2>'
    if not groups:
        return head + f"<p data-tokenizers-none>{escape(NO_STEP)}</p></section>"
    body = [f"<p data-tokenizers-lead>{escape(LEAD)}</p>"]
    if not decodes:
        body.append(missing_package())
    for digest, steps in groups.items():
        n = len(steps)
        links = "".join(
            f'<li><a href="/runs/{escape(key)}/{stage_page(index)}">{escape(run_id)} · {escape(name)}</a></li>'
            for key, run_id, index, name in steps[:MOST_LISTED]
        )
        more = f"<li>and {n - MOST_LISTED} more</li>" if n > MOST_LISTED else ""
        said = f"<p data-tokenizer-example>{escape(EXAMPLE)}</p>" if digest in example else ""
        body.append(
            f'<div data-tokenizer-wanted="{escape(digest)}"><p><span class="mono">{escape(digest[:19])}…</span> · '
            f"{n} model step{'' if n == 1 else 's'}</p>{said}"
            f"<details><summary>The whole digest</summary><code>{escape(digest)}</code></details>"
            f'<ul class="plain">{links}{more}</ul></div>'
        )
    return head + "".join(body) + "</section>"


def page_body(store, store_dir, *, named: tuple) -> str:
    """The Tokenizers page: the steps that ask for one, then the tokenizers kept, with Remove."""
    groups = grouped(wanting(store, named))
    #: One section, which a Remove replaces in place: the steps that ask, and the tokenizers kept.
    return (
        "<div data-tokenizer-section>"
        + wanted_section(groups, example=example_digests(), decodes=can_decode())
        + settings_page(store_dir)
        + "</div>"
    )


def picker(want: str) -> str:
    """The token timeline's picker, for a record whose `tokenizer.digest` is `want`: a local console's."""
    from onetrace_console.token_script import TOKEN_SCRIPT

    return (
        f"<div data-tokenizer-pick><label hidden data-tokenizer-pick-field>{escape(PICK_FIELD)} "
        f'<input type="file" accept=".json,.zip,application/json,application/zip" data-tokenizer-file></label> '
        f'<button class="btn-primary" data-busy="Uploading…" type="button" hidden data-tokenizer-post="/model-tokenizers?digest={escape(want)}">{escape(PICK)}</button>'
        f'<span data-tokenizer-said role="status" aria-live="polite"></span><p class="note">{escape(PICK_NOTE)}</p>'
        f"{TOKEN_SCRIPT}</div>"
    )


def settings_page(store_dir) -> str:
    """The body of the Settings page that lists each kept tokenizer, with Remove."""
    from onetrace_console.token_script import TOKEN_SCRIPT
    from onetrace_console.words import time_html

    got = kept(store_dir)
    if not got:
        return f'<section data-section="tokenizers"><h1>{escape(SETTINGS_HEADING)}</h1><p>{escape(SETTINGS_NONE)}</p></section>'
    rows = "".join(
        f'<li data-tokenizer-kept="{escape(e["digest"])}"><span class="mono">{escape(e["digest"])}</span>: '
        f"{escape(', '.join(e['files']))}, {e['bytes']} bytes, kept {time_html(e['when'])} "
        f'<button class="btn-destructive" data-busy="Removing…" type="button" hidden data-tokenizer-remove="/model-tokenizers/remove?digest={escape(e["digest"])}">'
        f"{escape(REMOVE)}</button></li>"
        for e in got
    )
    return (
        f'<section data-section="tokenizers"><h1>{escape(SETTINGS_HEADING)}</h1><ul class="plain">{rows}</ul>'
        f'<span data-tokenizer-said role="status" aria-live="polite"></span>{TOKEN_SCRIPT}</section>'
    )
