"""Each console version builds its own demo folder, `onetrace-console-demo-<version>/`, and an older one is named at
start-up, never used and never touched.

The build record names its builder's console version and the onetrace version its runs were recorded with; a record
with no version is an earlier build's. `demo` builds or reuses only the folder named for the running console, a
folder of its own version after its build-record check, as before. Any other demo folder in the start folder (the
unversioned `onetrace-console-demo/`, or one for another version) is named in one line, printed and on the
Overview's local notice; it isn't read, moved or changed.

The demo's own build is stood in for by a small builder writing a build record over one file, so each case runs in
a moment; the build record's own fields are read from a real one.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from onetrace_console import __version__, demo_store
from onetrace_console import folder_load as fl

OWN = f"onetrace-console-demo-{__version__}"


def _stand_in(folder: Path, console_version: str | None = __version__) -> None:
    (folder / "runs").mkdir(parents=True)
    (folder / "runs" / "run.txt").write_text("a run", encoding="utf-8")
    (folder / "trust.json").write_text("{}", encoding="utf-8")
    demo_store.write_build_record(folder, ("runs", "trust.json"))
    if console_version != __version__:
        record = json.loads((folder / demo_store.BUILD_RECORD).read_text(encoding="utf-8"))
        record.pop("console_version")
        record.pop("onetrace_version")
        if console_version is not None:
            record["console_version"] = console_version
        (folder / demo_store.BUILD_RECORD).write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def built(monkeypatch):
    made = []
    monkeypatch.setattr(demo_store, "build", lambda folder: (made.append(folder), _stand_in(Path(folder)))[0])
    return made


def _bytes(folder: Path) -> dict[str, str]:
    return {
        p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_the_build_record_carries_both_versions(tmp_path, examined):
    from importlib import metadata

    _stand_in(tmp_path / "demo")
    record = json.loads((tmp_path / "demo" / demo_store.BUILD_RECORD).read_text(encoding="utf-8"))
    examined(2, "versions")
    assert record["console_version"] == __version__
    assert record["onetrace_version"] == metadata.version("onetrace")


def test_an_unversioned_older_demo_is_named_and_the_current_one_built_in_its_own_folder(tmp_path, built, examined):
    old = tmp_path / "onetrace-console-demo"
    _stand_in(old, console_version=None)
    before = _bytes(old)
    folder = fl.demo_folder(tmp_path)
    lines = fl.other_demos(tmp_path)
    examined(3, "the folder built, the line, the older folder's bytes")
    assert folder == tmp_path / OWN and built == [folder]
    assert lines == [
        "An older demo, built by an earlier onetrace-console, is in `onetrace-console-demo/`. It isn't used. "
        f"This is {__version__}'s demo, in `{OWN}/`. You can remove the older folder when you like."
    ]
    assert _bytes(old) == before


def test_an_older_version_s_folder_is_named_by_its_version(tmp_path, built, examined):
    _stand_in(tmp_path / "onetrace-console-demo-0.6.1", console_version="0.6.1")
    examined(1, "the line")
    assert fl.other_demos(tmp_path) == [
        "An older demo, built by onetrace-console 0.6.1, is in `onetrace-console-demo-0.6.1/`. It isn't used. "
        f"This is {__version__}'s demo, in `{OWN}/`. You can remove the older folder when you like."
    ]


def test_a_folder_of_the_same_version_is_reused_with_no_line(tmp_path, built, examined):
    _stand_in(tmp_path / OWN)
    before = _bytes(tmp_path / OWN)
    folder = fl.demo_folder(tmp_path)
    examined(2, "the folder reused, no line")
    assert folder == tmp_path / OWN and built == [] and _bytes(folder) == before
    assert fl.other_demos(tmp_path) == []


def test_a_newer_version_s_folder_from_a_downgrade_is_named_and_not_used(tmp_path, built, examined):
    newer = tmp_path / "onetrace-console-demo-99.0.0"
    _stand_in(newer, console_version="99.0.0")
    before = _bytes(newer)
    folder = fl.demo_folder(tmp_path)
    examined(3, "the folder built, the line, the newer folder's bytes")
    assert folder == tmp_path / OWN and built == [folder]
    assert fl.other_demos(tmp_path) == [
        "A newer demo, built by onetrace-console 99.0.0, is in `onetrace-console-demo-99.0.0/`. It isn't used. "
        f"This is {__version__}'s demo, in `{OWN}/`. You can remove the newer folder when you like."
    ]
    assert _bytes(newer) == before


def test_a_damaged_folder_of_the_running_version_is_refused_as_before(tmp_path, built, examined):
    _stand_in(tmp_path / OWN)
    (tmp_path / OWN / "runs" / "run.txt").write_text("changed", encoding="utf-8")
    examined(1, "a damaged folder")
    with pytest.raises(fl.LoadRefused, match="is not the demo as its builder made it"):
        fl.demo_folder(tmp_path)


def test_the_overview_s_local_notice_says_the_line(tmp_path, examined):
    from onetrace_console import render
    from onetrace_console.store import Store

    line = "An older demo, built by onetrace-console 0.6.1, is in `onetrace-console-demo-0.6.1/`. It isn't used."
    store = Store(tmp_path / "store")
    with render.local_notices([line]):
        page = render.render_home(store, generated_at="2026-11-09T12:00:00+00:00")
    examined(1, "the Overview")
    assert 'data-section="local-notice"' in page and "It isn&#x27;t used." in page
    assert 'data-section="local-notice"' not in render.render_home(store, generated_at="2026-11-09T12:00:00+00:00")
