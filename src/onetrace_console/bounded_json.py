"""Every JSON value the console reads goes through here: one rule for how deep it may nest.

The console used to catch `RecursionError` from its own `json.loads`, so "too deep" meant
wherever the interpreter ran out: `json.loads` first fails at 2995 levels on Windows 3.12 and at
9995 on Linux. A manifest 5000 deep was refused at ingest on Windows and taken on Linux.
Now the console parses, then applies the vendored viewer's own rule -- `viewer.depth`'s
`json_depth` against `MAX_JSON_DEPTH`, imported, never copied -- so every reader gives the same
answer on every platform. Text nested past what `json.loads` itself parses is past the limit
too, so the parser's own `RecursionError` is refused here as `TooDeep`, in the same words: left
to the sites, a receipt that deep was skipped and its run stored, where one nested 257 levels
was refused. The `RecursionError` handlers at the sites stay, as a backstop only.

`TooDeep` is a `json.JSONDecodeError` (so a `ValueError`): every site that already refuses JSON it
cannot read refuses JSON nested too deep through the same path. Sites that put the reason into
words name it in the viewer's words, "nested too deeply to read" (reports, files) or "... to
show" (pages); ingest refuses the run in the fixed words of `ingest_refusal`.

`tests/test_bounded_json.py` holds every `json.load`/`json.loads` in `src/onetrace_console/` to
this module.

One condition: ingest refuses any run with a record nested past the limit, and
that end-to-end pair (at the limit, one past) is what covers every later reader of a stored run's
files -- they only meet records ingest has already bounded. The console's own records it writes
itself. So if the console ever reads a run's files from anywhere other than its ingested store (an
import, or a path given on the command line), that reader needs its own end-to-end pair.
"""
from __future__ import annotations

import json

from onetrace_console.viewer.depth import MAX_JSON_DEPTH, too_deep

ROLES = ("read", "show")


class TooDeep(json.JSONDecodeError):
    """A JSON value nested more than `MAX_JSON_DEPTH` levels deep."""

    def __init__(self, what: str, role: str = "read"):
        self.what, self.role = what, role
        message = f"{what} is nested too deeply to {role}"
        ValueError.__init__(self, message)
        self.msg, self.doc, self.pos, self.lineno, self.colno = message, "", 0, 1, 1

    def __str__(self) -> str:
        return self.msg

    def __reduce__(self):
        return (TooDeep, (self.what, self.role))


def load_json_bounded(text: str | bytes, what: str, role: str = "read"):
    """`json.loads(text)`, refused with `TooDeep` when it nests past `MAX_JSON_DEPTH`.
    `what` names the value in the refusal; `role` is "read" or "show", as the site's role is."""
    if role not in ROLES:
        raise ValueError(f"role must be one of {ROLES}, not {role!r}")
    try:
        value = json.loads(text)
    except RecursionError:
        #: Past what the parser reads, so past the limit: json.loads gives out thousands of
        #: levels after MAX_JSON_DEPTH on every interpreter the console runs on.
        raise TooDeep(what, role) from None
    if too_deep(value):
        raise TooDeep(what, role)
    return value


def ingest_refusal(what: str) -> str:
    """The words a refused delivery carries, the number from the constant."""
    return (f"Not ingested: {what} is nested more than {MAX_JSON_DEPTH} levels deep, past what "
            f"the console reads.")
