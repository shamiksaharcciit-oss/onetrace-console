"""The public demo's build, with the explanations a builder kept.

An explanation belongs to the two runs it explains, byte for byte, and each build of the demo
records its runs anew. So a builder makes explanations of one build's runs, and a later build takes
that build's runs, as its build record vouches for them (`--runs-from`), and the folder of
onetrace-explain's own records (`--explanations`). The build record then vouches for each kept one,
as for the drift reports the build kept.

Test fixtures only: the explanation is made by the command with a model of `fake:PATH`
(tests/test_explain_panel.py); no model is called, and none goes into the demo.
"""
from __future__ import annotations

import re
import shutil
from html import unescape

import pytest

from tests.test_explain_kept import read_only_problems
from tests.test_explain_panel import _fake, _panel, _text


@pytest.fixture(scope="module")
def first_build(tmp_path_factory):
    """A first build's runs and trust file, as `demo_store.build` writes them."""
    from onetrace_console import demo_store
    folder = tmp_path_factory.mktemp("first") / "demo"
    demo_store.build(folder)
    return folder


def _explained(first, tmp_path, monkeypatch):
    """The demo's first comparison of the first build's runs, explained by the command in a local
    store of the builder's; returns the folder it wrote `explain/` under."""
    from onetrace_console import demo_store, explain
    from onetrace_console.config import Config
    from onetrace_console.store import Store
    store = Store(tmp_path / "builder" / "store")
    with demo_store.allowing_examples(first):
        loaded = demo_store.deliver(first, store, Config(store_root=str(tmp_path / "builder"),
                                                          trust_file=str(first / demo_store.TRUST_NAME)))
    config = tmp_path / "explain.toml"
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    _fake(config, "mixed.json")
    explain.explain(loaded.comparison, store)
    return explain.folder_of(store, loaded.comparison.key) / explain.REPORT, loaded.comparison


def test_a_build_from_an_earlier_build_s_runs_keeps_its_explanation_and_vouches_for_it(
        first_build, tmp_path, monkeypatch, explain_installed, examined):
    from onetrace_console import demo_store, explain
    from onetrace_console.folder_load import build_public
    source, b_cmp = _explained(first_build, tmp_path, monkeypatch)
    folder = tmp_path / "second"
    lines, _ = build_public(folder, runs_from=first_build, explanations=source)
    examined(1, "public build with a kept explanation")
    assert demo_store.check_build_record(folder) == []
    from onetrace_console.store import Store
    record = explain.kept_record(Store(folder / "store" / "store"))
    assert len(record["kept"]) == 1 and record["refused"] == []
    page = (folder / "store" / "pages" / "diff" / f"{record['kept'][0]['comparison']}.html").read_text(encoding="utf-8")
    panel = _panel(page)
    assert (f"<h2>{explain.TITLE}</h2>" in unescape(panel) and explain.AI_LINE in unescape(panel)
            and read_only_problems(panel) == [])
    assert any("kept 1 explanation" in text for text, _ in lines), lines
    (folder / "store" / "store" / explain.FOLDER / explain.KEPT_FILE).write_text("{}", encoding="utf-8")
    assert demo_store.check_build_record(folder) != []


def test_without_the_folder_the_build_reads_as_in_0_3_0(first_build, tmp_path, examined):
    from onetrace_console import explain
    from onetrace_console.folder_load import build_public
    folder = tmp_path / "plain"
    build_public(folder, runs_from=first_build)
    examined(1, "public build without explanations")
    assert not (folder / "store" / "store" / explain.FOLDER / explain.KEPT_FILE).exists()
    pages = list((folder / "store" / "pages" / "diff").glob("*.html"))
    one = next(p for p in pages if re.fullmatch(r"[0-9a-f]{64}\.html", p.name))
    assert _text(_panel(one.read_text(encoding="utf-8"))) == f"{explain.TITLE} {explain.NOT_SET_UP_DEMO}"


def test_runs_from_a_folder_its_build_record_does_not_vouch_for_is_refused(first_build, tmp_path, examined):
    from onetrace_console.folder_load import LoadRefused, build_public
    earlier = tmp_path / "earlier"
    shutil.copytree(first_build, earlier)
    #: A run folder, by name: `runs/` also holds what the builder writes beside the runs, and a
    #: folder's listing order is the filesystem's (Windows lists `decisions.jsonl` first).
    run = next(p for p in sorted((earlier / "runs").iterdir()) if (p / "MANIFEST.json").is_file())
    (run / "MANIFEST.json").write_bytes((run / "MANIFEST.json").read_bytes() + b" ")
    examined(1, "earlier build, one byte changed")
    with pytest.raises(LoadRefused, match="not the demo as its builder made it"):
        build_public(tmp_path / "third", runs_from=earlier)


def test_explanations_are_taken_only_with_public_and_build(tmp_path, capsys):
    from onetrace_console.folder_load import main
    with pytest.raises(SystemExit):
        main(["--explanations", str(tmp_path)], demo=True)
    assert "--explanations" in capsys.readouterr().err
