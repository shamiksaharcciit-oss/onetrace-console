"""The capture store: P10's three capture runs, whose self-hosted model call is written in `model-call-record/1.1`
with an L3 steps file (L2's top-k with it), example data constructed through onetrace's own writer: a baseline, a
run whose logits row changes before its chosen token, and one with batch-invariant mode off; the baseline compared
with each. A store of its own, built by `demo_store.captures` from the demo builder's code, never into the demo's
own runs: the demo's tables, counts and comparisons stay as they are.

Built here as a public console builds it (`demo --public --build --captures`): every run verifies; each pair reads
at the first difference as built; on its public pages the runs' ids are the capture builder's own example data,
labelled so; and its build record names its builder, whose example registry is its own, the demo's being its kept
inputs alone.
"""

from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

from onetrace_console import demo_store
from onetrace_console.demo_store import captures

RUNS = ("pz-59-agent-capture-baseline", "pz-61-agent-capture-row-changed", "pz-63-agent-capture-batch-off")
PAIRS = [
    ("pz-59-agent-capture-baseline", "pz-61-agent-capture-row-changed"),
    ("pz-59-agent-capture-baseline", "pz-63-agent-capture-batch-off"),
]


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.folder_load import build_public

    folder = tmp_path_factory.mktemp("capture-store") / "built"
    build_public(folder, builder=captures)
    pages = folder / "store" / "pages"
    return {
        "folder": folder,
        "pages": {p.relative_to(pages).as_posix(): p.read_text(encoding="utf-8") for p in pages.rglob("*.html")},
    }


def test_the_capture_store_is_its_own_and_the_demo_s_runs_stay_as_they_are(examined):
    folders = {s.folder for s in captures.runs()}
    demo = {s.folder for s in demo_store.runs()}
    examined(len(folders), "capture runs")
    assert set(RUNS) <= folders and not folders & demo
    assert captures.COMPARISONS == PAIRS
    assert not any(set(p) & folders for p in demo_store.COMPARISONS)


def test_every_run_verifies(built, examined):
    from onetrace_console import records
    from onetrace_console.store import Store

    store = Store(built["folder"] / "store" / "store")
    with store.reading():
        runs = list(store.runs())
        examined(len(runs), "capture store runs")
        assert {r.run_id for r in runs} >= set(RUNS)
        assert all(records.state(r, store) == records.YES for r in runs), [
            (r.run_id, records.state(r, store)) for r in runs
        ]


def test_each_pair_reads_at_the_first_difference_as_built(built, examined):
    diffs = [p for rel, p in built["pages"].items() if rel.startswith("diff/") and 'data-section="token-levels"' in p]
    examined(len(diffs), "comparisons with the view")
    said = [_text(p) for p in diffs]
    assert len(said) == len(PAIRS)
    assert all("The logits row changed at token 2; the chosen token first changed at token 4." in s for s in said)
    assert sum("a changed digest can come from how requests were batched, not from the model" in s for s in said) == 1


def test_public_pages_show_ids_only_as_the_builder_s_labelled_example_data(built, examined):
    pages = [p for rel, p in built["pages"].items() if rel.startswith("diff/") and 'data-token-level="L2"' in p]
    examined(len(pages), "public comparisons with L2")
    assert len(pages) == len(PAIRS)
    for p in pages:
        assert "example data, constructed: the demo's own, not a real run's" in _text(p)
        assert "<code>40</code>" in p


def test_a_capture_run_s_step_says_no_log_probabilities_are_recorded(built, examined):
    flagged = {rel: p for rel, p in built["pages"].items() if "data-close-calls" in p}
    examined(len(flagged), "step pages with the close-call view")
    assert len(flagged) >= len(RUNS)
    assert all("No close-call flag: no log-probabilities recorded." in _text(p) for p in flagged.values())


def test_the_build_record_names_its_builder_and_its_registry_is_its_own(built, examined):
    from onetrace_console.demo_store import model_call_example as mce

    record = json.loads((built["folder"] / demo_store.BUILD_RECORD).read_text(encoding="utf-8"))
    files = ["sha256:" + hashlib.sha256(mce.capture_bytes(v)).hexdigest() for v in mce.CAPTURES]
    examined(len(files) + 1, "the record's builder and the steps files")
    assert record["builder"] == captures.NAME
    assert set(files) <= captures.example_input_digests()
    assert not set(files) & demo_store.example_input_digests()
    assert demo_store.example_digests_for(built["folder"]) == captures.example_input_digests()


def test_no_public_page_shows_a_word_the_scan_refuses_beyond_the_verifier_s_row(built, examined):
    """The scan of every public page (`test_ux_screens.NOT_ON_A_PAGE`, and month names) finds nothing; the capture runs'
    pages quote onetrace-verify's own `engine core` row, which only the allowance passes over (the sabotage)."""
    from tests.test_ux_screens import MONTHS, NOT_ON_A_PAGE, _text, scanned_text

    examined(len(built["pages"]), "public pages read")
    found = [
        f"{rel}: {name}"
        for rel, page in built["pages"].items()
        for name, rx in NOT_ON_A_PAGE.items()
        if rx.search(scanned_text(page))
    ]
    found += [f"{rel}: a month by name" for rel, page in built["pages"].items() if MONTHS.search(scanned_text(page))]
    assert not found, found
    assert any(NOT_ON_A_PAGE["co" + "re"].search(_text(page)) for page in built["pages"].values())


def child_env() -> dict[str, str]:
    """The command's environment: the console's source, and an empty `PATH`, so it finds nothing by name. On Windows
    the parent's `SYSTEMROOT` too, without which Python there cannot load its socket provider."""
    import os

    env = {"PYTHONPATH": str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"), "PATH": ""}
    if os.environ.get("SYSTEMROOT"):
        env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]
    return env


def test_the_command_s_environment_keeps_systemroot_and_nothing_on_path(monkeypatch, examined):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    env = child_env()
    examined(1, "the command's environment")
    assert env["SYSTEMROOT"] == r"C:\Windows" and env["PATH"] == "" and set(env) == {"PYTHONPATH", "PATH", "SYSTEMROOT"}
    monkeypatch.delenv("SYSTEMROOT")
    assert set(child_env()) == {"PYTHONPATH", "PATH"}


def test_the_command_builds_the_capture_store_and_refuses_it_where_it_does_not_apply(tmp_path, examined):
    """`onetrace-console demo --public --build <folder> --captures` builds the capture store, its record naming its
    builder; `--captures` without `--public`, or with `--runs-from`, is refused."""
    import subprocess
    import sys

    env = child_env()
    run = lambda *a: subprocess.run(  # noqa: E731
        [sys.executable, "-B", "-m", "onetrace_console", "demo", *a],
        capture_output=True,
        text=True,
        env=env,
        timeout=600,
    )
    built = run("--public", "--build", str(tmp_path / "built"), "--captures")
    examined(3, "commands")
    assert built.returncode == 0, built.stdout + built.stderr
    assert "built the capture store in" in built.stdout
    record = json.loads((tmp_path / "built" / demo_store.BUILD_RECORD).read_text(encoding="utf-8"))
    assert record["builder"] == captures.NAME
    assert run("--captures").returncode == 2
    refused = run("--public", "--build", str(tmp_path / "other"), "--captures", "--runs-from", str(tmp_path / "built"))
    assert refused.returncode == 1 and "--runs-from is the demo's" in refused.stderr


def test_the_layout_and_look_checks_read_the_two_page_kinds_from_it(built, examined):
    """The layout check takes `comparison-token-levels` and `stage-close-calls` from the capture store, served beside
    the demo, and finds both there; the look check reads the capture store's two comparisons and a capture run's
    step, with the token levels among the parts its contrast probe reads."""
    from tests.export_tree import tool

    tool("layout_check.py")
    tool("explain_look_check.py")
    from tools import explain_look_check, layout_check

    chosen = layout_check._pick(built["folder"] / "store" / "pages")
    examined(4, "page kinds and look-check pages")
    assert (
        set(layout_check.CAPTURE_KINDS) == {"comparison-token-levels", "stage-close-calls"} <= set(layout_check.KINDS)
    )
    assert set(layout_check.CAPTURE_KINDS) <= set(chosen)
    assert sorted(explain_look_check.CAPTURE_PAIRS.values()) == sorted(captures.COMPARISONS)
    assert {r for r, _ in explain_look_check.CAPTURE_RUNS.values()} <= {s.folder for s in captures.runs()}
    assert ".token-levels" in explain_look_check.PARTS
