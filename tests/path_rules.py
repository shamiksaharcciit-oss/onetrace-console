"""The tests' one rule for "an absolute path", whichever system runs them.

A path is absolute when it has a root or a drive under POSIX rules or under Windows rules:
`/srv/...`, `C:\\...`, `C:/...`, `\\\\server\\share\\...`. Both rules apply on every system, as the
console's own rule for a configured path does (`config.from_folder`): a page drawn on Windows
holds a drive path, and a checker that knows only a leading `/` lets it through.
"""
from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

#: Characters a path may sit between in a sentence or a command: quotes, brackets, punctuation.
_EDGES = "\"'`()[]{}<>,;"


def is_absolute(text: str) -> bool:
    windows = PureWindowsPath(text)
    return bool(PurePosixPath(text).root or windows.root or windows.drive)


def absolute_paths_in(text: str, rule=is_absolute) -> list[str]:
    """Each whitespace-separated word of `text` that is an absolute path by `rule`."""
    return [w for w in (word.strip(_EDGES) for word in text.split()) if w and rule(w)]
