"""A public build's banner states what it serves: its pipelines (and, for the capture store, its runs) counted from the
build's own run folders, never from a typed word and not from the builder's list where the build holds other runs. A
build from kept runs that hold no P12 says eleven pipelines; a fresh build with P12, twelve. The demo's post-deploy
check reads the banner's count against the Overview's own pipelines, as the capture store's reads its sentence.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _build(folder: Path, folders) -> Path:
    for name in folders:
        (folder / "runs" / name).mkdir(parents=True)
        (folder / "runs" / name / "MANIFEST.json").write_text("{}", encoding="utf-8")
    return folder


@pytest.fixture
def speaking():
    from onetrace_console import public

    yield public
    public.speaks_for("demo")


def test_a_build_without_p12_says_eleven_pipelines_and_with_it_twelve(speaking, tmp_path, examined):
    from onetrace_console import demo_store

    specs = demo_store.runs()
    kept = _build(tmp_path / "kept", [s.folder for s in specs if s.pipeline != "p12"])
    fresh = _build(tmp_path / "fresh", [s.folder for s in specs])
    examined(2, "builds")
    speaking.speaks_for("demo", kept)
    assert "Its runs come from 11 small example pipelines" in speaking.banner_runs()
    speaking.speaks_for("demo", fresh)
    assert "Its runs come from 12 small example pipelines" in speaking.banner_runs()


def test_the_capture_store_s_sentence_counts_the_runs_it_serves(speaking, tmp_path, examined):
    from onetrace_console.demo_store import captures

    specs = captures.runs()
    examined(2, "capture builds")
    speaking.speaks_for("captures", _build(tmp_path / "all", [s.folder for s in specs]))
    assert "It holds six runs from two small example pipelines" in speaking.banner_runs()
    speaking.speaks_for("captures", _build(tmp_path / "four", [s.folder for s in specs[:4]]))
    assert "It holds four runs from two small example pipelines" in speaking.banner_runs()


def test_a_build_still_recording_falls_back_to_the_builder_s_list(speaking, tmp_path, examined):
    from onetrace_console import demo_store

    examined(1, "empty build")
    speaking.speaks_for("demo", tmp_path / "empty")
    assert f"from {len(demo_store.pipeline_names())} small example pipelines" in speaking.banner_runs()


def test_the_demo_s_post_deploy_check_reads_the_banner_s_count_against_the_overview(examined):
    text = (REPO / "deploy" / "fly" / "postdeploy_080.ps1").read_text(encoding="utf-8")
    examined(1, "post-deploy script")
    assert "'Its runs come from (\\S+) small example pipelines'" in text
    assert "data-pipeline-card=" in text and "Check \"A3b the banner's count of pipelines is the Overview's" in text
