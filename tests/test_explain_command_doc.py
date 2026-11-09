"""`explain.command()` says what it does: the `onetrace-explain` beside this interpreter, and where there is
none, the first `onetrace-explain` on `PATH`. The fallback is held as it is for 0.7.0."""
from __future__ import annotations

import inspect
from pathlib import Path


def test_the_docstring_names_the_path_fallback(examined):
    from onetrace_console import explain
    doc = " ".join(inspect.getdoc(explain.command).split())
    examined(1, "docstring")
    assert "falls back to the first `onetrace-explain` on `PATH`" in doc, doc


def test_where_none_is_beside_the_interpreter_the_first_on_path_is_taken(tmp_path, examined):
    from onetrace_console import explain
    on_path = tmp_path / "elsewhere" / "onetrace-explain"
    asked = []
    found = explain.find(False, str(tmp_path / "scripts"), str(tmp_path / "bin" / "python"),
                         lambda name: asked.append(name) or str(on_path))
    examined(1, "lookup")
    assert found == Path(on_path) and asked == ["onetrace-explain"]
