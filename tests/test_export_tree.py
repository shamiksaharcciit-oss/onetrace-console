"""The tests that run a tool the public export leaves out (`tools/layout_check.py`, `tools/explain_look_check.py`):
in a public export they skip, saying the export leaves the tool out; in this repository's own tree a missing tool is a
failure, named, never a skip. A public export is told by the export's own signal: it holds no `tools/export_public.py`
(`tests/export_tree.py`), as the tests that read the export tool's never-ship list already take it.

Shown on two trees built here: a fake export (no export tool, no rendered-check tools) and a fake private tree (the
export tool present, the rendered-check tools absent). The nine tests run in each, in a process of their own.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
#: The nine, by file and the test's own id.
NINE = {
    ("test_rendered_check_stall", "test_the_browser_script_stops_on_a_view_past_its_limit_and_names_it[layout_check]"),
    (
        "test_rendered_check_stall",
        "test_the_browser_script_stops_on_a_view_past_its_limit_and_names_it[explain_look_check]",
    ),
    ("test_rendered_check_stall", "test_with_no_stall_the_script_says_each_view_and_gives_every_result[layout_check]"),
    (
        "test_rendered_check_stall",
        "test_with_no_stall_the_script_says_each_view_and_gives_every_result[explain_look_check]",
    ),
    (
        "test_rendered_check_stall",
        "test_at_the_whole_checks_limit_the_summary_line_names_the_view_it_waited_on[layout_check]",
    ),
    (
        "test_rendered_check_stall",
        "test_at_the_whole_checks_limit_the_summary_line_names_the_view_it_waited_on[explain_look_check]",
    ),
    ("test_rendered_check_stall", "test_the_checks_summary_line_names_the_stalled_view"),
    (
        "test_rendered_check_limits",
        "test_a_check_stops_at_its_own_limit_and_says_so_on_its_summary_line[layout_check.py-layout check-extra0]",
    ),
    (
        "test_rendered_check_limits",
        "test_a_check_stops_at_its_own_limit_and_says_so_on_its_summary_line[explain_look_check.py-explain look check-extra1]",
    ),
}
LEFT_OUT = ("layout_check.py", "explain_look_check.py")


def _tree(root: Path, *, export_tool: bool) -> Path:
    """This repository's tests and tools, less the two rendered-check tools; with or without the export tool."""
    shutil.copytree(REPO / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(
        REPO / "tools", root / "tools", ignore=shutil.ignore_patterns("__pycache__", "export_public.py", *LEFT_OUT)
    )
    if export_tool:
        #: A stand-in: only its presence is read, so this works from a public export too, which has none.
        (root / "tools" / "export_public.py").write_text("", encoding="utf-8")
    return root


def _outcomes(root: Path) -> dict[tuple[str, str], tuple[str, str]]:
    """Each of the nine's outcome in `root`: ("skipped" | "failed" | "passed", the reason or message)."""
    junit = root / "junit.xml"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), str(REPO / "src")])}
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
            "-q",
            "--rootdir",
            str(root),
            f"--junitxml={junit}",
            "tests/test_rendered_check_stall.py",
            "tests/test_rendered_check_limits.py",
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    out = {}
    for case in ET.parse(junit).iter("testcase"):
        key = (case.get("classname", "").rsplit(".", 1)[-1], case.get("name", ""))
        if key not in NINE:
            continue
        for kind in ("skipped", "failure", "error"):
            node = case.find(kind)
            if node is not None:
                out[key] = ("skipped" if kind == "skipped" else "failed", node.get("message", ""))
                break
        else:
            out[key] = ("passed", "")
    return out


@pytest.fixture(scope="module")
def trees(tmp_path_factory):
    return {
        name: _outcomes(_tree(tmp_path_factory.mktemp(name), export_tool=name == "private"))
        for name in ("export", "private")
    }


def _module_reason(module: str) -> str:
    """The reason a module of the nine states for skipping on Windows, read from the module itself."""
    import importlib

    return importlib.import_module(f"tests.{module}").pytestmark.kwargs["reason"]


def expected(tree: str, key: tuple, outcome: str, said: str, platform: str = sys.platform) -> bool:
    """Whether one of the nine read as it should in a fake `tree`: on Windows, skipped in either tree for the reason
    its own module states (the nine come from two modules, each with its own); elsewhere, in an export skipped saying
    the export leaves its tool out, and in a private tree failed naming the missing tool."""
    if platform == "win32":
        return outcome == "skipped" and _module_reason(key[0]) in said
    if tree == "export":
        #: The one test without a parameter loads explain_look_check (which loads layout_check itself).
        tool = (
            next(t for t in LEFT_OUT if t.removesuffix(".py") in key[1]) if "[" in key[1] else "explain_look_check.py"
        )
        return outcome == "skipped" and f"the public export leaves tools/{tool} out" in said
    return outcome == "failed" and "is missing from this tree, which is not a public export" in said


def test_in_a_public_export_the_nine_skip_saying_the_export_leaves_their_tool_out(trees, examined):
    got = trees["export"]
    examined(len(got), "tests in a fake export")
    assert set(got) == NINE
    for key, (outcome, said) in got.items():
        assert expected("export", key, outcome, said), (key, outcome, said)


def test_in_the_private_tree_a_missing_tool_fails_named_never_skips(trees, examined):
    got = trees["private"]
    examined(len(got), "tests in a fake private tree")
    assert set(got) == NINE
    for key, (outcome, said) in got.items():
        assert expected("private", key, outcome, said), (key, outcome, said)


def test_on_windows_both_trees_expect_each_of_the_nine_s_own_module_s_skip(examined):
    """On every platform, for every one of the nine: the Windows outcome is the skip its own module states, in both
    trees; another module's reason is not, a Linux outcome read as Windows' is not, and Windows' as Linux's is not."""
    reasons = {module: _module_reason(module) for module, _name in NINE}
    assert len(set(reasons.values())) == len(reasons) == 2, reasons
    for key in sorted(NINE):
        own = reasons[key[0]]
        other = next(r for m, r in reasons.items() if m != key[0])
        for tree in ("export", "private"):
            assert expected(tree, key, "skipped", f"Skipped: {own}", platform="win32"), (tree, key)
            assert not expected(tree, key, "skipped", f"Skipped: {other}", platform="win32"), (tree, key)
            assert not expected(tree, key, "skipped", f"Skipped: {own}", platform="linux"), (tree, key)
        assert not expected(
            "private", key, "failed", "is missing from this tree, which is not a public export", "win32"
        )
    examined(len(NINE), "of the nine, each read against its own module's reason")


def test_the_signal_is_the_export_tool_s_absence(tmp_path, examined):
    """`tests/export_tree.py` reads the tree it sits in: an export where the export tool is absent."""
    import importlib.util

    examined(2, "trees")
    for has_tool in (True, False):
        root = tmp_path / ("private" if has_tool else "export")
        (root / "tests").mkdir(parents=True)
        (root / "tools").mkdir()
        shutil.copy(REPO / "tests" / "export_tree.py", root / "tests" / "export_tree.py")
        if has_tool:
            (root / "tools" / "export_public.py").write_text("", encoding="utf-8")
        spec = importlib.util.spec_from_file_location(f"export_tree_{has_tool}", root / "tests" / "export_tree.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        assert mod.is_public_export() is (not has_tool)


#: A test that loads a tool the export leaves out, with the tool.
TOKEN_FIXTURES = (
    "tests/test_token_level_fixtures.py::test_the_folder_holds_the_six_pairs_the_tool_names",
    "make_token_level_runs.py",
)


def _one(root: Path, node: str) -> tuple[str, str]:
    """One test's outcome in `root`, run alone: ("skipped" | "failed" | "passed", the reason or message)."""
    junit = root / "one.xml"
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), str(REPO / "src")])}
    subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-p",
            "no:randomly",
            "-q",
            "--rootdir",
            str(root),
            f"--junitxml={junit}",
            node,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    (case,) = list(ET.parse(junit).iter("testcase"))
    for kind in ("skipped", "failure", "error"):
        n = case.find(kind)
        if n is not None:
            return ("skipped" if kind == "skipped" else "failed", n.get("message", ""))
    return ("passed", "")


@pytest.mark.parametrize("which", ["export", "private"])
def test_the_token_fixtures_test_skips_in_an_export_and_fails_named_here_without_its_tool(tmp_path, which, examined):
    node, tool = TOKEN_FIXTURES
    root = _tree(tmp_path, export_tool=which == "private")
    (root / "tools" / tool).unlink(missing_ok=True)
    outcome, said = _one(root, node)
    examined(1, f"the token fixtures' tool test in a fake {which} tree")
    if which == "export":
        assert outcome == "skipped" and f"the public export leaves tools/{tool} out" in said, (outcome, said)
    else:
        assert outcome == "failed" and "is missing from this tree, which is not a public export" in said, (
            outcome,
            said,
        )
