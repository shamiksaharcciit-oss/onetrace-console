"""The environment of every Python child process the console starts: its output in UTF-8.

The console runs the SDK's verbs and the verifier as `python ...` child processes, and reads what
they write as UTF-8. On Windows, Python does not default to UTF-8: a child writes its output in
the console's code page, and a text diff holding an em dash -- the SDK's own text holds one --
arrives as bytes UTF-8 can't read ("can't decode byte 0x97"). So every child gets UTF-8 forced
on its standard streams here, whatever the machine's default, and the console decodes as before.

Every call site that starts a Python child passes `env=utf8_env()`; tests/test_child_utf8.py holds
each one to it, and runs a child with non-ASCII output with the forcing removed from the parent's
environment, as a user's machine has it.
"""
from __future__ import annotations

import os


def utf8_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` (the console's own environment by default) with UTF-8 forced on a Python child's
    output: UTF-8 mode, and UTF-8 on its standard streams."""
    env = dict(os.environ if base is None else base)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env
