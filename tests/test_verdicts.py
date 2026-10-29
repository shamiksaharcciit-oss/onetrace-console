"""A run's verdict against its pipeline's reference, the variation profile, and the monitoring view:
the SDK's own commands over stored runs, read as they report.

1. A run's page shows onetrace's verdict against the pipeline's reference line for line as the SDK
   words it, the same verdict `onetrace verdict` gives by hand over the run's own folder; the Runs
   list shows the run's word beside it.
2. The reference is made by `onetrace reference make` from the pipeline's benchmark and its repeats:
   the same seal as by hand, and the page says how it was chosen and what it was made from.
3. A reference is never made from a benchmark whose records could not be checked: none is made, the
   command is not run, and the page says why.
4. The benchmark's page shows onetrace's profile of it and its repeats, per step, as the SDK counts.
5. A public console runs nothing: what its build kept (`ensure_all`) is drawn, and where nothing is
   kept nothing is drawn.
6. The monitoring view is drawn on a local console only, each run's word counted in the SDK's order.
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import sys

import pytest

GENERATED_AT = "2026-09-26T12:00:00+02:00"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _record(folder):
    from tests.model_call_runs import record_run
    return {"a": record_run(folder / "a", "v-a"), "c": record_run(folder / "c", "v-c"),
            "b": record_run(folder / "b", "v-b", output="sha256:" + "e" * 64)}


def _stored(folder, made):
    from onetrace_console import benchmarks
    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    store = Store(folder / "store")
    runs = {k: run_and_record(_deliver(made[k], store, outputs=True), store, ran_at=FIXED_RAN_AT) for k in ("a", "c", "b")}
    benchmarks.mark(store, runs["a"], who="test")
    return store, runs


@pytest.fixture(scope="module")
def local(tmp_path_factory):
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_all
    folder = tmp_path_factory.mktemp("verdicts")
    made = _record(folder)
    store, runs = _stored(folder, made)
    with rendering(onedoor=False, sign_in=False, public=False):
        pages = {k: render_execution(r, store, generated_at=GENERATED_AT).pages for k, r in runs.items()}
        every = render_all(store, generated_at=GENERATED_AT)
    return {"folder": folder, "made": made, "store": store, "runs": runs, "pages": pages, "all": every}


def _by_hand(folder, made, verb_args: list[str], out: str) -> dict:
    """The SDK's own command over the runs' own folders, as a person would run it."""
    subprocess.run([sys.executable, "-m", "onetrace", *verb_args, "--out", out], cwd=folder, check=False,
                   capture_output=True)
    return json.loads((folder / out / f"{verb_args[0]}.json").read_bytes()) if verb_args[0] != "reference" else \
        json.loads((folder / out).read_bytes())


def _section(pages: dict, name: str) -> str:
    both = pages["case.html"] + pages.get("proof.html", "")
    m = re.search(rf'<section data-section="{name}".*?</section>', both, re.S)
    return m.group(0) if m else ""


def _order(local) -> list[str]:
    """The runs the console made the reference from, in its order (the benchmark, then its repeats as
    the store orders them): as folders of the runs' own, for the commands by hand."""
    from onetrace_console import verdicts
    store, runs, made = local["store"], local["runs"], local["made"]
    pick = verdicts.chosen(verdicts.pipeline_of(runs["a"], store), store)
    by_key = {r.key: k for k, r in runs.items()}
    return [str(made[by_key[r.key]]) for r in [pick["benchmark"], *pick["repeats"]]]


def test_a_run_s_verdict_is_onetrace_s_line_for_line(local, examined):
    from onetrace import reference as sdk_reference
    folder, made = local["folder"], local["made"]
    order = _order(local)
    ref = _by_hand(folder, made, ["reference", "make", *order], "by-hand-ref.json")
    got = _by_hand(folder, made, ["verdict", "--reference", "by-hand-ref.json", str(made["b"]), "--json", "--quiet"],
                   "by-hand-verdict")
    #: Spacing as a page shows text: each run of white space one space, on both sides.
    want = [" ".join(ln.split()) for ln in sdk_reference.verdict_text(got).splitlines() if ln.strip()]
    shown = [_text(li) for li in re.findall(r"<li[^>]*>(.*?)</li>",
                                            re.search(r'<ul class="plain" data-verdict-lines>(.*?)</ul>',
                                                      _section(local["pages"]["b"], "verdict"), re.S).group(1), re.S)]
    examined(len(want), "verdict lines")
    #: The second line names the reference file: by hand its path, on the page the pipeline's reference.
    assert shown[0] == want[0] == "verdict: diverged at call"
    assert shown[1] == "run v-b against the pipeline's reference"
    assert shown[2:] == want[2:]
    assert sorted(ref["made_from"]["run_ids"]) == ["v-a", "v-b", "v-c"] and ref["made_from"]["run_ids"][0] == "v-a"


def test_the_runs_list_shows_each_run_s_word(local, examined):
    page = next(v for k, v in local["all"].items() if k.startswith("executions") and 'data-section="runs-stored"' in v)
    keys = {r.key: r.run_id for r in local["runs"].values()}
    pills = {keys[k]: w for k, w in re.findall(r'<tr class="verdict-row" data-verdict-of="([0-9a-f]+)"><td colspan="\d+" '
                                               r'data-answer="verdict"><span class="pill neu" data-verdict-word="[^"]+">([^<]+)</span>',
                                               page)}
    examined(len(pills), "runs listed with a verdict")
    assert pills == {"v-a": "verdict: identical", "v-c": "verdict: identical", "v-b": "verdict: diverged at call"}
    #: Each word with the seal of the reference it was read against, its whole value one fold away.
    from onetrace_console import verdicts
    seal = verdicts.reference_record(verdicts.pipeline_of(local["runs"]["a"], local["store"]), local["store"],
                                     compute=False)["reference"]["seal"]
    seals = {keys[k]: s for k, s in re.findall(r'<tr class="verdict-row" data-verdict-of="([0-9a-f]+)">.*?'
                                               r'<span data-verdict-seal="([^"]+)">against the reference '
                                               r'<span class="mono">sha256:[0-9a-f]{12}…</span>', page)}
    assert seals == {r: seal for r in pills}, seals
    #: In the rows short, so the table keeps its width; under it, each seal whole, once.
    note = re.search(r'<div data-section="reference-seals">.*?</div></div>', page, re.S)
    assert note is not None and note.group(0).count(f'data-fingerprint="whole">{seal}</span>') == 1
    rows = page.split('<div data-section="reference-seals">')[0]
    assert f'data-fingerprint="whole">{seal}<' not in rows


def test_the_reference_says_how_it_was_chosen_and_carries_the_seal_made_by_hand(local, examined):
    folder, made = local["folder"], local["made"]
    by_hand = _by_hand(folder, made, ["reference", "make", *_order(local)], "by-hand-ref-2.json")
    section = _section(local["pages"]["a"], "verdict")
    examined(1, "reference")
    said = _text(section)
    assert "Made by onetrace from this pipeline's benchmark, v-a" in said
    assert "and its 2 repeats recorded on the same configuration." in said
    assert by_hand["seal"] in section
    assert f"made from 3 run(s): {', '.join(by_hand['made_from']['run_ids'])}" in said
    assert "This run is one the reference was made from." in said


def test_no_reference_is_made_from_a_benchmark_whose_records_were_not_checked(tmp_path, monkeypatch, examined):
    from onetrace_console import verdicts
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    made = _record(tmp_path)
    store, runs = _stored(tmp_path, made)
    monkeypatch.setattr(verdicts, "_agree", lambda run, store: run.key != runs["a"].key)
    ran = []
    monkeypatch.setattr(verdicts, "_run_in", lambda *a, **k: ran.append(a) or {"exit": "0", "note": "", "files": {}})
    with rendering(onedoor=False, sign_in=False, public=False):
        section = _section(render_execution(runs["b"], store, generated_at=GENERATED_AT).pages, "verdict")
    examined(1, "run")
    assert ran == [], "a command ran for a benchmark whose records were not checked"
    assert f"No reference: {verdicts.NOT_CHECKED}." in _text(section)
    assert "Made by onetrace" not in _text(section), "a reference said made where none was"
    assert "This pipeline's benchmark is v-a" in _text(section)
    assert "data-verdict-lines" not in section


def test_the_benchmark_s_page_shows_onetrace_s_profile_of_its_repeats(local, examined):
    folder, made = local["folder"], local["made"]
    got = _by_hand(folder, made, ["profile", *_order(local), "--json", "--quiet"], "by-hand-profile")
    section = _section(local["pages"]["a"], "profile")
    rows = re.findall(r'<tr data-step="([^"]+)">(.*?)</tr>', section, re.S)
    examined(len(rows), "steps")
    want = [(s["step"], [s["runs"], s["differs"], s["distinct_outputs"], s["kinds"]["output_only"],
                         s["kinds"]["input_differs"], s["kinds"]["setting_differs"], s["varies_on_its_own"],
                         s["may_vary_declared"]]) for s in got["steps"]]
    assert [(n, [_text(c) for c in re.findall(r'<td[^>]*class="value"[^>]*>(.*?)</td>', cells)]) for n, cells in rows] == want
    assert [_text(li) for li in re.findall(r"<li>(.*?)</li>", section)] == got["non_claims"]
    assert _section(local["pages"]["b"], "profile") == "", "the profile is on the benchmark's page only"


def test_a_public_console_runs_nothing_and_draws_what_its_build_kept(tmp_path, monkeypatch, examined):
    from onetrace_console import verdicts
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    made = _record(tmp_path)
    store, runs = _stored(tmp_path, made)
    real = verdicts._run_in
    ran = []

    def counted(*a, **k):
        ran.append(a[2][0])
        return real(*a, **k)
    monkeypatch.setattr(verdicts, "_run_in", counted)
    with rendering(onedoor=False, sign_in=False, public=True):
        before = _section(render_execution(runs["b"], store, generated_at=GENERATED_AT).pages, "verdict")
    assert ran == [] and before == ""
    verdicts.ensure_all(store)
    built = list(ran)
    with rendering(onedoor=False, sign_in=False, public=True):
        after = _section(render_execution(runs["b"], store, generated_at=GENERATED_AT).pages, "verdict")
    examined(len(built), "commands the build ran")
    assert built == ["reference", "profile", "verdict", "verdict", "verdict"], built
    assert ran == built, "drawing the public page ran a command"
    assert "verdict: diverged at call" in _text(after)


def test_the_monitoring_view_is_local_only_and_counts_in_the_sdk_s_order(local, examined):
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_all
    page = local["all"].get("monitor.html", "")
    counts = re.findall(r"<p data-monitor-counts>(.*?)</p>", page)
    examined(len(counts), "pipelines")
    assert counts == ["3 runs · identical: 2 · diverged: 1"]
    from onetrace_console.overview import pipelines
    word = {"v-a": "identical", "v-c": "identical", "v-b": "diverged"}
    newest_first = [r.run_id for r in reversed(pipelines(local["store"])[0].runs)]
    assert re.findall(r'<td[^>]*data-verdict-word="([^"]+)"', page) == [word[r] for r in newest_first]
    from onetrace_console import verdicts
    seal = verdicts.reference_record(pipelines(local["store"])[0], local["store"], compute=False)["reference"]["seal"]
    assert re.findall(r'<span data-verdict-seal="([^"]+)">', page) == [seal] * len(newest_first)
    with rendering(onedoor=False, sign_in=False, public=True):
        public = render_all(local["store"], generated_at=GENERATED_AT)
    assert "monitor.html" not in public
    assert not any('data-section="monitor-link"' in p for p in public.values())
    assert any('data-section="monitor-link"' in p for p in local["all"].values())


def test_a_run_whose_own_records_could_not_be_checked_gets_no_verdict_word(tmp_path, monkeypatch, examined):
    """Whatever the reference: its page and the Runs list say "No verdict: this run's records could not
    be checked.", the monitoring view counts it apart from every word, and no verdict is made for it."""
    from onetrace_console import records, verdicts
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_all
    made = _record(tmp_path)
    store, runs = _stored(tmp_path, made)
    real = records.state
    monkeypatch.setattr(records, "state", lambda run, st: records.COULDNT if run.key == runs["b"].key else real(run, st))
    ran = []
    real_run_in = verdicts._run_in

    def counted(*a, **k):
        ran.append(a[2][0])
        return real_run_in(*a, **k)
    monkeypatch.setattr(verdicts, "_run_in", counted)
    verdicts.ensure_all(store)
    with rendering(onedoor=False, sign_in=False, public=False):
        page = render_execution(runs["b"], store, generated_at=GENERATED_AT).pages
        every = render_all(store, generated_at=GENERATED_AT)
    section = _section(page, "verdict")
    listed = next(v for k, v in every.items() if k.startswith("executions") and 'data-section="runs-stored"' in v)
    row = re.search(rf'<tr class="verdict-row" data-verdict-of="{runs["b"].key}">.*?</tr>', listed, re.S).group(0)
    examined(1, "unchecked run")
    assert ran.count("verdict") == 2, ran
    unchecked = re.search(r'<p data-verdict="unchecked">(.*?)</p>', section)
    assert unchecked is not None and html.unescape(unchecked.group(1)) == verdicts.UNCHECKED
    assert "data-verdict-lines" not in section and "This pipeline's benchmark is" not in section
    assert "Made by onetrace from this pipeline's benchmark, v-a" in _text(section)
    assert verdicts.word_of(runs["b"], store) is None
    assert verdicts.UNCHECKED in _text(row) and "data-verdict-seal" not in row
    monitor = every["monitor.html"]
    assert "no verdict, records could not be checked: 1" in _text(monitor)
    assert "diverged" not in _text(monitor)
