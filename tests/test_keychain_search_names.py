"""The planted-key search (tests/keychain.py) names each file it finds with `/`, on every system, by
`as_posix()`: the same name for a file under a folder on Windows as on Linux (`named`), held here on a
Windows path, and on this system's through the search itself."""
from __future__ import annotations

from pathlib import Path, PureWindowsPath

from tests.keychain import KEY, files_holding


def test_a_windows_file_under_a_folder_is_named_with_a_slash(examined):
    from tests.keychain import named
    root = PureWindowsPath("C:/Users/x/AppData/Local/Temp/pytest-1/test0")
    examined(1, "Windows path")
    assert named(root / "store" / "x" / "attempt.json", root) == "store/x/attempt.json"


def test_on_this_system_the_search_names_files_with_a_slash(tmp_path, examined):
    (tmp_path / "store" / "x").mkdir(parents=True)
    (tmp_path / "store" / "x" / "attempt.json").write_text(KEY, encoding="utf-8")
    (tmp_path / "keychain").mkdir()
    (tmp_path / "keychain" / "entries.json").write_text(KEY, encoding="utf-8")
    found = files_holding(Path(tmp_path), KEY, but=tmp_path / "keychain")
    examined(len(found), "files holding the planted key")
    assert found == ["store/x/attempt.json"]
