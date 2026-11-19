"""Re-runs and checks' runs, shown as what they are, and never offered as a reference.

On onetrace 0.8.0's own vectors (`tests/format_04_item8/`): a reproduce, a twin, a counterfactual, the run a check
produced, two twins a re-run rule stopped, a check's own run, and the run they re-run (vector-base, a plain run).

- **Kept when the run is checked** (`StoredRun.rerun`): the mark as its receipts carry it, or the check's constants
  and assertions; nothing for a plain run. A run checked before it was kept is derived again.
- **Said as the verifier says it**, "<kind> of <run>", with its kind's members: on the Runs page's row, and on the
  run's head with its runs linked where held.
- **Never a reference:** a labelled run is not marked a benchmark (the mark is refused in words, the page offers no
  press and says why), and is never one of a benchmark's repeats.
"""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent / "format_04_item8" / "accept"
RAN_AT = "2026-11-13T00:00:00+00:00"
LABELLED = {
    "A06-twin": {
        "kind": "twin",
        "of_run": "vector-base",
        "config_of_run": "vector-other",
    },
    "A07-counterfactual": {"kind": "counterfactual", "of_run": "vector-base"},
    "A08-reproduce": {"kind": "reproduce", "of_run": "vector-base"},
    "A10-check-produced-run": {"kind": "check", "of_run": "vector-base", "from_stage": "b"},
    "A03-rerun-stopped-labelled": {"kind": "twin", "of_run": "vector-base"},
    "A04-rerun-stopped-not-recorded": {"kind": "twin", "of_run": "vector-base"},
}
SAID = {
    "A06-twin": "twin of vector-base, with vector-other's configuration",
    "A07-counterfactual": "counterfactual of vector-base, vector-other's output put in at b",
    "A08-reproduce": "reproduce of vector-base",
    "A10-check-produced-run": "check of vector-base, re-run by a check from b",
    "A09-check-run": "a check's run: reproduce",
}


@pytest.fixture(scope="module")
def held(tmp_path_factory):
    from tests.test_checks import _require_installed

    _require_installed()
    from onetrace_console import run_index
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_format_03 import _tar

    store = Store(tmp_path_factory.mktemp("item8") / "store")
    runs = {}
    for name in [*LABELLED, "A09-check-run", "A02-closed-recorder"]:
        runs[name] = run_and_record(accept(_tar(HERE / name), store).run, store, ran_at=RAN_AT)
    return store, runs, run_index.build(store)


def test_each_re_run_keeps_its_mark_and_a_plain_run_none(held, examined):
    from onetrace_console import rerun_label

    _store, runs, _index = held
    examined(len(runs), "runs")
    for name, want in LABELLED.items():
        got = rerun_label.of_run(runs[name])
        assert got is not None and {k: got.get(k) for k in want} == want, (name, got)
        assert got["of_chain_head"].startswith("sha256:"), name
    assert rerun_label.of_run(runs["A02-closed-recorder"]) is None and runs["A02-closed-recorder"].rerun == ""


def test_a_check_s_run_keeps_its_constants_and_what_came_back(held, examined):
    from onetrace_console import rerun_label

    _store, runs, _index = held
    got = rerun_label.of_run(runs["A09-check-run"])
    examined(1, "check's run")
    assert got == {
        "kind": "check-run",
        "verb": "reproduce",
        "predicted": "equal to the candidate's",
        "claim": "sha256:c777a584a6477b5021191775eef2044ae2a69fb460568f4a4cd10bee5e7d580b",
        "baseline": runs["A02-closed-recorder"].chain_head,
        "candidate": "sha256:7c70470423425f9d6b1af0fa3ba12acacdfcb5463e0fd18998a22f1f17be2fa5",
        "stage": "b",
        "exit": "0",
        "result": "reproduced",
        "came_back": "as predicted",
    }


def test_the_runs_page_labels_each_row_as_the_verifier_says_it(held, examined):
    from onetrace_console import rerun_label, runs_page

    _store, runs, index = held
    page = runs_page.body(index, {"page": "all"}, public=False)
    examined(len(runs), "rows")
    for name, run in runs.items():
        row = re.search(rf'<tr data-run="[^"]*" data-key="{run.key}">.*?</tr>', page, re.S).group(0)
        pill = re.search(r'<span class="pill neu" data-rerun="([a-z-]+)">(.*?)</span>', row)
        if name == "A02-closed-recorder":
            assert pill is None
            continue
        assert pill, name
        assert pill.group(1) == rerun_label.of_run(run)["kind"]
        if name in SAID:
            assert unescape(pill.group(2)) == SAID[name], name


def test_a_re_run_s_head_names_its_runs_linked_where_held(held, examined):
    from onetrace_console.pages import CASE, render_execution

    store, runs, _index = held
    examined(len(LABELLED), "re-runs' heads")
    for name in LABELLED:
        case = render_execution(runs[name], store, generated_at="2026-11-13T00:00:00Z").pages[CASE]
        line = re.search(r'<p class="sub" data-section="rerun-label"[^>]*>(.*?)</p>', case, re.S)
        assert line, name
        assert f'href="../../runs/{runs["A02-closed-recorder"].key}/case.html"' in line.group(1), name
        text = unescape(re.sub(r"<[^>]+>", "", line.group(1)))
        assert text.startswith(f"Re-run: {LABELLED[name]['kind']} of vector-base"), (name, text)
        if name == "A06-twin":
            assert "vector-other" in text and "not held in this store" in text, text
    plain = render_execution(runs["A02-closed-recorder"], store, generated_at="2026-11-13T00:00:00Z").pages[CASE]
    assert 'data-section="rerun-label"' not in plain


def test_a_labelled_run_is_never_marked_a_benchmark_and_says_why(held, examined):
    from onetrace_console import benchmarks, rerun_label

    store, runs, _index = held
    examined(len(runs), "runs offered as a benchmark")
    for name, run in runs.items():
        section = benchmarks.mark_section(run, store, public=False)
        if name == "A02-closed-recorder":
            assert "data-benchmark-post" in section
            continue
        why = rerun_label.never_reference(run)
        assert why.startswith("Not offered as a reference: this run is "), name
        assert "data-benchmark-post" not in section and why in unescape(section), name
        with pytest.raises(benchmarks.MarkError, match="Not offered as a reference"):
            benchmarks.mark(store, run, who="t")
        assert benchmarks.mark_of(store, run.key) is None


def test_a_labelled_run_is_never_one_of_a_benchmark_s_repeats(held, examined):
    from onetrace_console import benchmarks, rerun_label

    store, runs, _index = held
    base = runs["A02-closed-recorder"]
    got = [o for o, _how in benchmarks.repeats(base, store)]
    examined(len(got) + 1, "repeats read")
    assert not any(rerun_label.of_run(o) for o in got), [o.run_id for o in got]


def test_a_run_checked_before_the_label_was_kept_is_derived_again(held, examined):
    from dataclasses import replace

    from onetrace_console.checks import DERIVED, rederive

    store, runs, _index = held
    run = runs["A06-twin"]
    store.put_run(replace(run, rerun="", derived="derivation-13"))
    assert DERIVED != "derivation-13"
    again = rederive(store.get_run(run.key), store)
    examined(1, "run derived again")
    assert again.derived == DERIVED and json.loads(again.rerun) == json.loads(run.rerun)
