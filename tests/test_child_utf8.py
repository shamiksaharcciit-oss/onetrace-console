"""Every Python child process the console starts writes UTF-8, whatever the machine's default.

On Windows a child's output is in the console's code page unless UTF-8 is forced, and the
console reads it as UTF-8: a text diff holding an em dash failed ("can't decode byte 0x97").

1. Statically: every `subprocess.run` in the console that starts a Python child passes
   `env=utf8_env()` (the one `git` call starts git, not Python).
2. End to end: two runs whose outputs differ by an em dash, an accented letter and a CJK character
   are compared, and the Diff page shows the text. The parent runs with UTF-8 *not* forced: on
   Windows, `PYTHONUTF8` and `PYTHONIOENCODING` are removed, as a user's machine has them; on
   Linux, where Python reads a C or UTF-8 locale as UTF-8 anyway, the parent's
   `PYTHONIOENCODING` names cp1252, as a Windows code page would.
3. Sabotage: the forcing taken out, the same comparison fails to show -- on Linux here, and on the
   windows-check runner when the sabotage branch runs there.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
#: Two pairs: the field's case (an em dash and an accented letter, which a cp1252 child writes as
#: 0x97 and 0xe9, so UTF-8 can't read them), and a CJK line, which cp1252 can't write at all.
PAIRS = {"em-dash": ("The fee is 30 days — café", "The fee is 14 days — café"),
         "cjk": ("The fee is 30 days — café policy 返品", "The fee is 14 days — café policy 返品")}
#: The page's own words when it can't read a text diff (the apostrophe is the page's own).
UNREADABLE = "read this text diff:"


def runs_problems() -> list[str]:
    out = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "run" and getattr(node.func.value, "id", "") == "subprocess"):
                continue
            first = node.args[0] if node.args else None
            if isinstance(first, ast.List) and first.elts and getattr(first.elts[0], "value", "") == "git":
                continue
            env = next((k.value for k in node.keywords if k.arg == "env"), None)
            if not (isinstance(env, ast.Call) and getattr(env.func, "id", "") == "utf8_env"):
                out.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}: no env=utf8_env()")
    return out


def test_every_python_child_gets_utf8_forced(examined):
    found = sum(1 for p in SRC.rglob("*.py") if "subprocess.run(" in p.read_text(encoding="utf-8"))
    examined(found, "modules that start a child")
    assert runs_problems() == []


def test_the_static_check_names_a_site_without_it(tmp_path, monkeypatch, examined):
    """Sabotage of the static check: one site's `env=` taken out is named."""
    import shutil
    examined(1, "planted module")
    copy = tmp_path / "onetrace_console"
    shutil.copytree(SRC, copy)
    target = copy / "board7.py"
    text = target.read_text(encoding="utf-8")
    assert text.count(", env=utf8_env())") == 1
    target.write_text(text.replace(", env=utf8_env())", ")"), encoding="utf-8")
    monkeypatch.setattr(__import__(__name__), "SRC", copy)
    assert [p for p in runs_problems() if p.startswith("board7.py:")]


def _record(folder: Path, run_id: str, text: str) -> None:
    from onetrace.emit import Instrument, Recorder
    rec = Recorder(str(folder), run_id=run_id, declared_stages=["write"], manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a test record")
    rec.run_node("write", None, Instrument("writer", "tool", "1.0.0", {"k": "v"}),
                 lambda ctx: ctx.write("policy.txt", (text + "\n").encode("utf-8"), "text/plain"))
    rec.close()


def _not_forced(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    if os.name == "nt":
        monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    else:
        monkeypatch.setenv("PYTHONIOENCODING", "cp1252")


def _diff_page(tmp_path, pair: str) -> str:
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    runs = tmp_path / "runs"
    _record(runs / "a", "utf8-a", PAIRS[pair][0])
    _record(runs / "b", "utf8-b", PAIRS[pair][1])
    store = Store(tmp_path / "store")
    loaded = load_folder(runs, store, Config(), compare=("a", "b"))
    assert loaded.comparison is not None, loaded.compare_note
    return render_diff(loaded.comparison, store, generated_at="2026-10-11T00:00:00Z")


@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_a_text_diff_with_non_ascii_text_shows_with_utf8_not_forced(tmp_path, monkeypatch, pair,
                                                                    examined):
    from html import unescape
    _not_forced(monkeypatch)
    shown = unescape(_diff_page(tmp_path, pair))
    examined(1, "comparison page")
    assert UNREADABLE not in shown
    assert all(word in shown for word in PAIRS[pair][0].split()[-2:]), "the text is shown"


@pytest.mark.skipif(os.name == "nt", reason="on Windows this sabotage runs in the windows-check job's own step, the UTF-8 proof "
                    "pair (tools/sabotage_small_fixes.py), not in the suite: no separate branch")
@pytest.mark.parametrize("pair", sorted(PAIRS))
def test_sabotage_without_the_forcing_the_same_diff_fails(tmp_path, monkeypatch, pair, examined):
    """With `utf8_env` giving back the environment unforced, the child writes cp1252 and the
    console can't read the text diff: the test above would fail."""
    from onetrace_console import board7, compare, staging
    from onetrace_console.viewer import report
    _not_forced(monkeypatch)
    unforced = lambda base=None: dict(os.environ if base is None else base)  # noqa: E731
    for module in (compare, board7, staging, report):
        monkeypatch.setattr(module, "utf8_env", unforced)
    from html import unescape
    shown = unescape(_diff_page(tmp_path, pair))
    examined(1, "comparison page")
    assert UNREADABLE in shown
    if pair == "em-dash":
        assert "can't decode byte 0x97" in shown.replace("’", "'"), "the field's own failure"
