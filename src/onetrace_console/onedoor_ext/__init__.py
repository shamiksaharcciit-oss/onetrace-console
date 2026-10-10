"""The onedoor extension: off by default.

Nothing in this package, or anywhere else in this console, imports the `onedoor`
package itself, at runtime or in tests. This extension reads onedoor's *export
format* -- a JSONL file `python -m onedoor.export` writes -- never onedoor's code.
See `tests/test_onedoor_ext_isolation.py` for the two properties this claims:

  1. a disabled console never imports this package at all (`serve.py` only reaches
     into it from inside the `/v1/decisions` handler, which itself only runs when
     `config.extensions["onedoor"]` is true);
  2. nothing under `onetrace_console`, this package included, imports `onedoor`.
"""
from __future__ import annotations
