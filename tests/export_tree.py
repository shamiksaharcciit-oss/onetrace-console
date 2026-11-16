"""Which tree the suite runs in: this repository's own, or a public export of it (`tools/export_public.py`).

A public export holds no export tool: the export recipe leaves `tools/export_public.py` out, as every never-ship
file, and this repository always holds it. The tests that read the export tool's never-ship list take the same
signal (`except ImportError: ... the public tree has no export tool`).

`tool(name)`: the path of a tool under `tools/` a test runs or loads. Where the tool is absent, the test skips in a
public export (the export leaves the gate's own tools out), and fails, naming the tool, in this repository's tree,
where a missing tool is never a skip.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EXPORT_TOOL = REPO / "tools" / "export_public.py"


def is_public_export() -> bool:
    """True in a public export: no export tool."""
    return not EXPORT_TOOL.is_file()


def tool(name: str) -> Path:
    """`tools/<name>`, where it is; a skip in a public export, and a failure in this repository's tree, where not."""
    import pytest

    path = REPO / "tools" / name
    if path.is_file():
        return path
    if is_public_export():
        pytest.skip(f"the public export leaves tools/{name} out")
    pytest.fail(
        f"tools/{name} is missing from this tree, which is not a public export (tools/export_public.py is here)",
        pytrace=False,
    )
