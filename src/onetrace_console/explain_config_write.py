"""Writing onetrace-explain's `[model]` table, for the Set up Explain form's Save (console 0.7.0).

The file is a person's own: only the `[model]` table's lines for the keys the form writes (`WRITTEN`) are
taken out, and the new ones put where the table starts. Every other line of the file is kept byte for
byte: comments, keys before any table, other tables, the `[model]` table's own other keys and its
subtables. A file with no `[model]` table gains one at its end.

The result is read back (`tomllib`) before anything is written, and must say exactly what was asked and
everything else the file said; where it doesn't (a key written as `model.name` at the top, a value over
several lines), nothing is written and the person is told to edit the file by hand. The write is atomic:
a file beside it, flushed, then put in its place (`os.replace`); a write that fails leaves the file as it
was and removes the file beside it.

The key is never written here: where one is kept, the table says `key_source = "keyring"` and the key is
in the keychain (`explain_keychain`).
"""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

#: The [model] keys the form writes; any other key of the table is kept as written.
WRITTEN = ("provider", "name", "base_url", "key_env", "key_source")
BY_HAND = ("The file can't be changed safely here ({why}); nothing was written. Edit its [model] table "
           "by hand, as in the examples below.")

_HEADER = re.compile(r"\s*\[\s*([^\]\[]+?)\s*\]\s*(#.*)?$")
_KEY = re.compile(r"\s*([A-Za-z0-9_-]+)\s*=")


class Unsafe(ValueError):
    """The file can't be written as asked without changing something else in it."""


def toml_string(value: str) -> str:
    """A TOML basic string of `value`: each backslash, quote and control character escaped."""
    out = []
    for c in value:
        if c in '"\\':
            out.append("\\" + c)
        elif ord(c) < 0x20 or ord(c) == 0x7F:
            out.append(f"\\u{ord(c):04x}")
        else:
            out.append(c)
    return '"' + "".join(out) + '"'


def model_lines(model: dict) -> list[str]:
    """The [model] lines the form writes, in order, for the keys `model` gives."""
    return [f"{k} = {toml_string(model[k])}\n" for k in WRITTEN if model.get(k)]


def new_text(old: str, model: dict, *, keep: tuple[str, ...] = ()) -> str:
    """`old` with its [model] table's written keys replaced by `model`'s (`model_lines`). `keep`: written
    keys whose line, where the file has one, stays as it is (and `model` gives none)."""
    lines = old.splitlines(keepends=True)
    if lines and not lines[-1].endswith(("\n", "\r")):
        lines[-1] += "\n"
    out, table, start = [], None, None
    kept = {}
    for line in lines:
        head = _HEADER.match(line)
        if head:
            table = head.group(1)
            out.append(line)
            if table == "model" and start is None:
                start = len(out)
            continue
        key = _KEY.match(line)
        if table == "model" and key and key.group(1) in WRITTEN:
            if key.group(1) in keep:
                kept[key.group(1)] = line
            continue
        out.append(line)
    new = model_lines(model) + [kept[k] for k in WRITTEN if k in kept]
    if start is None:
        if out and out[-1].strip():
            out.append("\n")
        out += ["[model]\n", *new]
    else:
        out[start:start] = new
    return "".join(out)


def _expected(old: dict, model: dict, keep: tuple[str, ...]) -> dict:
    table = {k: v for k, v in (old.get("model") or {}).items() if k not in WRITTEN or k in keep}
    table.update({k: model[k] for k in WRITTEN if model.get(k)})
    return {**old, "model": table}


def write(path: Path, model: dict, *, keep: tuple[str, ...] = ()) -> list[str]:
    """Write `model`'s keys into `path`'s [model] table (`new_text`), atomically; the lines written. Raises
    Unsafe where the result would say anything else than asked, OSError where the write fails."""
    try:
        old = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        old = ""
    try:
        before = tomllib.loads(old)
    except tomllib.TOMLDecodeError as e:
        raise Unsafe(BY_HAND.format(why=f"it is not TOML as it stands: {e}")) from None
    if not isinstance(before.get("model", {}), dict):
        raise Unsafe(BY_HAND.format(why="its model is not a table"))
    text = new_text(old, model, keep=keep)
    try:
        after = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise Unsafe(BY_HAND.format(why=f"its [model] table would not read back: {e}")) from None
    if after != _expected(before, model, keep):
        raise Unsafe(BY_HAND.format(why="its [model] table is written in a way this form does not change"))
    path.parent.mkdir(parents=True, exist_ok=True)
    beside = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(beside, "w", encoding="utf-8", newline="") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(beside, path)
    except BaseException:
        beside.unlink(missing_ok=True)
        raise
    return ["[model]\n", *model_lines(model)]
