r"""An `OSError` in words, its paths as written.

Python's own words for an `OSError` quote its file name with `repr`, so a Windows path reads with
every backslash doubled there: `[Errno 13] Permission denied: 'C:\\data\\x.json'`. A message
quotes `said(e)` instead: the reason, then each path the error names, as written.
"""
from __future__ import annotations

import os


def said(e: OSError) -> str:
    """The error's reason and the paths it names, as written; its own words where it has no
    reason of the system's."""
    if not e.strerror:
        return str(e)
    names = [os.fsdecode(n) for n in (e.filename, e.filename2) if n is not None]
    return e.strerror + (": " + " -> ".join(names) if names else "")


def shown(text) -> str:
    """Text for a log line, a terminal or a plain-text answer, as the console shows text that is not
    a record's words: each control, bidirectional or invisible character as \\uXXXX, as a page
    shows it, and the rest -- a Windows path's backslashes among it -- as written (`words.path_text`,
    without the HTML). `said` leaves a path unchanged; whatever prints it shows it through this."""
    from onetrace_console.viewer.page import _UNSHOWN
    return _UNSHOWN.sub(lambda m: f"\\u{ord(m.group(0)):04x}", str(text))
