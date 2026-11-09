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
from datetime import datetime, timezone
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
PICK_NOTE = ("The console keeps it only where its files hash to this record's tokenizer.digest; it reads it on "
             "this machine, and fetches nothing.")
PATH = "model-tokenizers"
SETTINGS_HEADING = "Tokenizers kept by this console"
SETTINGS_NONE = "This console keeps no tokenizer. A model step's page offers to take one where its token can't be shown."
REMOVE = "Remove"
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
        names, total = {}, 0
        for i in members:
            path = PurePosixPath(i.filename.replace("\\", "/"))
            mode = (i.external_attr >> 16) & 0o170000
            if path.is_absolute() or ".." in path.parts or ":" in i.filename or mode == stat.S_IFLNK:
                raise UploadError(f"the zip's member {i.filename!r} is not a plain file inside it")
            if not _NAME.fullmatch(path.name):
                raise UploadError(f"the zip's member {i.filename!r} is not named as a tokenizer's file is")
            if path.name in names:
                raise UploadError(f"the zip holds two files named {path.name}")
            if i.file_size > MOST_BYTES:
                raise UploadError(f"the zip's member {path.name} is {i.file_size} bytes, over the {MOST_BYTES} this "
                                  "console reads")
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
    entry = {"format": FORMAT, "digest": want, "files": sorted(files),
             "bytes": sum(len(b) for b in files.values()), "picked": PurePosixPath(name.replace("\\", "/")).name,
             "when": when or datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _atomic_write(tmp / KEPT, (json.dumps(entry, indent=1, sort_keys=True) + "\n").encode("utf-8"))
    shutil.rmtree(target, ignore_errors=True)
    tmp.rename(target)
    return entry


def kept(store_dir) -> list[dict]:
    """Each tokenizer kept, whose folder and record read, by digest."""
    out = []
    base = root(store_dir)
    for d in sorted(p for p in base.iterdir() if p.is_dir() and re.fullmatch(r"[0-9a-f]{64}", p.name)) \
            if base.is_dir() else ():
        try:
            entry = load_json_bounded((d / KEPT).read_text(encoding="utf-8"), "a kept tokenizer's record")
        except (OSError, ValueError, RecursionError):
            continue
        if isinstance(entry, dict) and entry.get("format") == FORMAT and entry.get("digest") == f"sha256:{d.name}" \
                and isinstance(entry.get("files"), list) and all(isinstance(f, str) for f in entry["files"]):
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


def picker(want: str) -> str:
    """The token timeline's picker, for a record whose `tokenizer.digest` is `want`: a local console's."""
    from onetrace_console.token_script import TOKEN_SCRIPT
    return (f'<div data-tokenizer-pick><label hidden data-tokenizer-pick-field>{escape(PICK_FIELD)} '
            f'<input type="file" accept=".json,.zip,application/json,application/zip" data-tokenizer-file></label> '
            f'<button type="button" hidden data-tokenizer-post="/model-tokenizers?digest={escape(want)}">{escape(PICK)}</button>'
            f'<span data-tokenizer-said></span><p class="note">{escape(PICK_NOTE)}</p>{TOKEN_SCRIPT}</div>')


def settings_page(store_dir) -> str:
    """The body of the Settings page that lists each kept tokenizer, with Remove."""
    from onetrace_console.token_script import TOKEN_SCRIPT
    from onetrace_console.words import time_html
    got = kept(store_dir)
    if not got:
        return f'<section data-section="tokenizers"><h1>{escape(SETTINGS_HEADING)}</h1><p>{escape(SETTINGS_NONE)}</p></section>'
    rows = "".join(
        f'<li data-tokenizer-kept="{escape(e["digest"])}"><span class="mono">{escape(e["digest"])}</span>: '
        f'{escape(", ".join(e["files"]))}, {e["bytes"]} bytes, kept {time_html(e["when"])} '
        f'<button type="button" hidden data-tokenizer-remove="/model-tokenizers/remove?digest={escape(e["digest"])}">'
        f'{escape(REMOVE)}</button></li>' for e in got)
    return (f'<section data-section="tokenizers"><h1>{escape(SETTINGS_HEADING)}</h1><ul class="plain">{rows}</ul>'
            f'<span data-tokenizer-said></span>{TOKEN_SCRIPT}</section>')
