"""What onetrace 0.5 records, on the console's pages: gated steps and their decisions, the span
context, steps and runs inside steps; the "i" notes; "What changed?"; and the demo's P8 and P10,
which record them. Each held on the public demo as built, with a sabotage the check names.

1. the verifier's `decisions:` and `nesting:` rows are about the run as a whole: a page reads the
   report, and its "Records agree" is the reading kept when the run was checked;
2. the gated steps, each decision and permit as recorded, and the verifier's rows about them, on
   P8's runs only; the decision files passed to the verifier for gated runs only;
3. the span context on each run's page, its link only where a tracing tool is configured, and the
   trace panel at a comparison's first difference;
4. the runs inside a step, linked to their pages, and a comparison's descent into one;
5. the "i" notes, each adding up to the number beside it;
6. no path of the building machine in a built store, and a build from an earlier one reading only
   its runs and trust file;
7. "What changed?": the rule's choice named, and on a public demo no comparison offered to make.
"""
from __future__ import annotations

import html
import json
import re
import shutil

import pytest

GENERATED_AT = "2026-01-01T00:00:00Z"
#: Rung 1 of each run of P8 (gated), P10 (an agent) and P11 (its sub-agent), as the build checks them.
READINGS = {
    "p8-42-invoice-tolerance-2pct": "yes",
    "p8-43-invoice-tolerance-5pct": "yes",
    "p8-44-invoice-quantity-changed": "yes",
    "p8-45-invoice-over-limit-declined": "yes",
    "p8-49-invoice-paid-on-deny": "no",
    "p8-50-invoice-permit-other-amount": "no",
    "pz-51-agent-baseline": "yes",
    "pz-52-agent-baseline-subagent": "yes",
    "pz-53-agent-amount-changed": "yes",
    "pz-54-agent-amount-changed-subagent": "yes",
}
#: The verifier's own `decisions:` rows each P8 run's check holds, in its order.
ROWS = ("decisions: gated steps cite a decision", "decisions: references are well formed",
        "decisions: a step that acted cites a permitting decision",
        "decisions: the permit covers the recorded action", "decisions: the decision is in the export")
DECISION_ROWS = {
    "p8-42-invoice-tolerance-2pct": ("PASS", "PASS", "PASS", "PASS", "PASS"),
    "p8-43-invoice-tolerance-5pct": ("PASS", "PASS", "PASS", "PASS", "PASS"),
    "p8-44-invoice-quantity-changed": ("PASS", "PASS", "PASS", "PASS", "PASS"),
    "p8-45-invoice-over-limit-declined": ("PASS", "PASS", "NOT-RUN", "NOT-RUN", "PASS"),
    "p8-49-invoice-paid-on-deny": ("PASS", "PASS", "FAIL", "NOT-RUN", "PASS"),
    "p8-50-invoice-permit-other-amount": ("PASS", "PASS", "PASS", "FAIL", "PASS"),
}
AGENT, SUB, AGENT_B, SUB_B = ("pz-51-agent-baseline", "pz-52-agent-baseline-subagent",
                              "pz-53-agent-amount-changed", "pz-54-agent-amount-changed-subagent")
DESCENT = f"inside agent_step, into run {SUB} at settle"


def _text(page: str) -> str:
    page = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _section(page: str, name: str) -> str:
    m = re.search(rf'<section data-section="{name}".*?</section>', page, re.S)
    return m.group(0) if m else ""


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    return folder, store, {r.run_id: r for r in store.runs()}


def _pages(folder, run) -> dict[str, str]:
    root = folder / "store" / "pages" / "runs" / run.key
    return {p.name: p.read_text(encoding="utf-8") for p in root.glob("*.html")}


def _rung(pages: dict[str, str]) -> str | None:
    for name in ("case.html", "proof.html"):
        m = re.search(r'<tr data-rung="records-agree" data-state="([a-z-]+)">', pages.get(name, ""))
        if m:
            return m.group(1)
    return None


# ------------------------------------------------------- 1. rows about the run as a whole

def reading_problems(folder, store, runs) -> list[str]:
    """Each run's rung 1 on its page, against the table and the reading kept at its check."""
    out = []
    for name, want in READINGS.items():
        run = runs[name]
        got = _rung(_pages(folder, run))
        if got != want:
            out.append(f"{name}'s page reads {got}, not {want}")
        if run.agree != got:
            out.append(f"{name} was read {run.agree} when checked, and its page reads {got}")
    return out


def test_gated_and_nested_runs_read_as_their_check_reads_them(demo, examined):
    folder, store, runs = demo
    examined(len(READINGS), "gated and nested runs' rung 1")
    assert reading_problems(folder, store, runs) == []


def test_sabotage_rows_about_the_whole_run_read_as_strays_make_the_report_unreadable(demo, monkeypatch, examined):
    """Before: the viewer took `decisions` and `nesting` for subjects not in the run and refused the
    whole report, so every gated or nested run read "Couldn't check"."""
    from onetrace_console.pages import render_execution
    from onetrace_console.viewer import model
    folder, store, runs = demo
    monkeypatch.setattr(model, "WHOLE_RUN", frozenset({model.RUN_SUBJECT, ""}))
    examined(2, "runs drawn with the earlier whole-run subjects")
    for name in ("p8-42-invoice-tolerance-2pct", AGENT):
        pages = render_execution(runs[name], store, generated_at=GENERATED_AT).pages
        assert _rung(pages) == "couldnt-check", name
        assert "the check&#x27;s report could not be read" in pages["case.html"] + pages.get("proof.html", "")


# ------------------------------------------------------- 2. gated steps and decisions

def onedoor_problems(folder, runs) -> list[str]:
    """P8's runs each show the gated step (on the case page, or on Proof where the record is in
    question) and the verifier's decision rows as the table holds them; no other run shows either."""
    out = []
    for name, run in runs.items():
        pages = _pages(folder, run)
        gated = any(_section(p, "onedoor") for p in pages.values())
        rows = re.findall(r'<li data-onedoor-row="([A-Z-]+)">.*?</span> ([^<]*?) <span class="reason">',
                          _section(pages.get("case.html", ""), "onedoor-rows"), re.S)
        if name in DECISION_ROWS:
            if not gated:
                out.append(f"{name} shows no gated step")
            if tuple(rows) != tuple(zip(DECISION_ROWS[name], ROWS)):
                out.append(f"{name}'s decision rows read {rows}")
            shown = " ".join(_text(_section(p, "onedoor")) for p in pages.values())
            if "Gated step approve_payment" not in shown:
                out.append(f"{name} does not name approve_payment as its gated step")
        elif gated or rows:
            out.append(f"{name} shows a gated step or decision rows, and records none")
    return out


def test_p8_shows_its_gated_step_and_the_verifier_s_rows_about_it(demo, examined):
    folder, store, runs = demo
    examined(len(runs), "runs' pages read for gated steps")
    assert onedoor_problems(folder, runs) == []


def test_sabotage_a_decision_row_lost_from_a_page_is_named(demo, tmp_path, examined):
    folder, store, runs = demo
    run = runs["p8-50-invoice-permit-other-amount"]
    copy = tmp_path / "pages" / "store" / "pages" / "runs" / run.key
    shutil.copytree(folder / "store" / "pages" / "runs" / run.key, copy)
    case = (copy / "case.html").read_text(encoding="utf-8")
    (copy / "case.html").write_text(case.replace('data-onedoor-row="FAIL"', 'data-onedoor-row="PASS"'), encoding="utf-8")
    examined(1, "planted page")
    assert onedoor_problems(tmp_path / "pages", {run.run_id: run}) == [
        f"{run.run_id}'s decision rows read {list(zip(('PASS',) * 5, ROWS))}"]


def test_a_gated_step_with_no_decision_says_so_and_a_permit_shows_its_payload(examined):
    from onetrace_console import onedoor_panel as o
    from onetrace_console.demo_store.onedoor_demo import ISSUER, Issuer
    issuer = Issuer()
    action = {"action_type": "pay", "amount": "1200.00"}
    ref = issuer.decide("req-1", "permit")
    receipt = {"authorization": {"decisions": [{"ref": ref, "permit": issuer.permit(action),
                                                "action_digest": "sha256:" + "a" * 64}]}}
    examined(5, "step panels drawn")
    assert o.NONE_RECORDED in o.step_block("approve_payment", {}, True)
    assert o.step_block("match", {}, False) == ""
    shown = _text(o.step_block("approve_payment", receipt, True))
    assert f"issuer {ISSUER}" in shown and "allows the action with digest sha-256=:" in shown
    assert "until 20" in shown and "subject not stated in the permit" in shown
    bad = {"authorization": {"decisions": [{"ref": ref, "permit": "not.a.jws!"}]}}
    assert "Permit: the permit's header or payload cannot be read" in _text(o.step_block("s", bad, True))
    other = {"authorization": {"decisions": [{**receipt["authorization"]["decisions"][0],
                                              "permit": issuer.permit({**action, "amount": "9.00"})}]}}
    assert (o.differs(receipt, receipt), o.differs(receipt, other), o.differs(receipt, {})) == ("", "permit", "decision")


def beside_problems(store, runs) -> list[str]:
    """The decision files are given to the verifier for P8's gated runs only, named relative to the
    run's folder."""
    from onetrace_console.home import _envelope
    out = []
    for name, run in runs.items():
        command = str((_envelope(run, store) or {}).get("rows_json", {}).get("command", ""))
        given = "--decisions" in command and "--permit-issuers" in command
        if given != (name in DECISION_ROWS):
            out.append(f"{name}'s check {'is' if given else 'is not'} given the decision files")
        if given and "../beside/decisions.jsonl" not in command:
            out.append(f"{name}'s check names the decision files by another path: {command}")
    return out


def test_the_decision_files_go_to_gated_runs_checks_only(demo, examined):
    folder, store, runs = demo
    examined(len(runs), "stored check commands")
    assert beside_problems(store, runs) == []


def test_sabotage_decision_files_given_to_a_run_with_no_gated_step_are_named(demo, examined):
    from onetrace_console import home
    folder, store, runs = demo
    run = runs["p1-01-baseline-set1"]
    real = home._envelope(run, store)
    planted = {**real, "rows_json": {**real["rows_json"], "command": str(
        ["onetrace-verify", "--json", "--decisions", "../beside/decisions.jsonl", "--permit-issuers", "x"])}}
    examined(1, "planted command")
    orig = home._envelope
    try:
        home._envelope = lambda r, s, **k: planted if r.key == run.key else orig(r, s, **k)
        assert beside_problems(store, {run.run_id: run}) == [f"{run.run_id}'s check is given the decision files"]
    finally:
        home._envelope = orig


# ------------------------------------------------------- 3. span context and the trace panel

def test_each_run_page_shows_its_span_context_without_a_link_on_a_public_demo(demo, examined):
    folder, store, runs = demo
    examined(len(runs), "runs' pages read for their span context")
    missing, linked, loads = [], [], []
    for name, run in runs.items():
        pages = _pages(folder, run)
        if not any(_section(p, "span-context") for p in pages.values()):
            #: The demo's runs broken on purpose lose a receipt or a byte of one.
            if name not in ("p1-14-candidate-set3-byte-changed", "p1-15-candidate-set4-file-deleted",
                            "p7-41-cold-chain-decision-tampered"):
                missing.append(name)
        for page in pages.values():
            if "Open in your tracing tool" in page:
                linked.append(name)
            if re.search(r'<(?:img|script|link|iframe)[^>]+(?:src|href)="https?:', page):
                loads.append(name)
    assert (missing, linked, loads) == ([], [], [])


def test_the_span_context_says_what_its_ids_are_for_and_where_they_lead(demo, examined):
    """One sentence under the lead: the ids point into the app's own tracing tool; with a tool
    configured, its link opens it; without one, none does; a public console links to none, and says so."""
    import html as _html
    from onetrace_console import trace_panel
    tid, sid = "0af7651916cd43dd8448eb211c80319c", "b7ad6b7169203331"
    manifest = {"traceparent": f"00-{tid}-{sid}-01"}
    steps = [{"receipt": {"stage": {"name": "a"}, "trace": {"trace_id": tid, "span_id": sid}}}]

    def said(section):
        return [_html.unescape(x) for x in re.findall(r"<p data-span-for>(.*?)</p>", section)]
    cases = {
        "configured": trace_panel.run_section(manifest, steps, "https://tracing.example/t/{trace_id}"),
        "none": trace_panel.run_section(manifest, steps, ""),
        "public": trace_panel.run_section(manifest, steps, "https://tracing.example/t/{trace_id}", public=True),
    }
    examined(len(cases), "consoles")
    assert said(cases["configured"]) == [f"{trace_panel.SPAN_FOR} {trace_panel.SPAN_OPENS}"]
    assert trace_panel.OPEN in cases["configured"]
    assert said(cases["none"]) == [f"{trace_panel.SPAN_FOR} {trace_panel.SPAN_NO_TOOL}"]
    assert said(cases["public"]) == [f"{trace_panel.SPAN_FOR} {trace_panel.SPAN_PUBLIC}"]
    assert "pointers into the app's own tracing tool" in trace_panel.SPAN_FOR
    #: On the public demo's own pages: every run page with a span context says it links to none.
    folder, store, runs = demo
    pages = [p for run in runs.values() for p in _pages(folder, run).values() if 'data-section="span-context" class="span-context"><h2>' in p]
    assert pages and all(trace_panel.SPAN_PUBLIC in _html.unescape(p) for p in pages)


def test_the_link_is_the_configured_pattern_with_the_ids_and_none_without_one(examined):
    from onetrace_console import trace_panel
    tid, sid = "0af7651916cd43dd8448eb211c80319c", "b7ad6b7169203331"
    examined(4, "links made")
    assert trace_panel.link("https://tracing.example/t/{trace_id}?span={span_id}", tid, sid) == \
        f"https://tracing.example/t/{tid}?span={sid}"
    assert trace_panel.link("", tid, sid) == "" and trace_panel.link(None, tid, sid) == ""
    assert trace_panel.OPEN in trace_panel.run_section(
        {"traceparent": f"00-{tid}-{sid}-01"}, [{"receipt": {"stage": {"name": "a"}, "trace": {
            "trace_id": tid, "span_id": sid}}}], "https://tracing.example/t/{trace_id}")
    assert trace_panel.OPEN not in trace_panel.run_section(
        {"traceparent": f"00-{tid}-{sid}-01"}, [{"receipt": {"stage": {"name": "a"}, "trace": {
            "trace_id": tid, "span_id": sid}}}], "")


def test_a_comparison_with_a_first_difference_shows_the_spans_there(demo, examined):
    """The panel where the comparison names a first difference, and not where it names none."""
    from onetrace_console import trace_panel
    folder, store, runs = demo
    names = {r.key: r.run_id for r in store.runs()}
    examined(len(store.comparisons()), "comparison pages")
    wrong = []
    for c in store.comparisons():
        page = (folder / "store" / "pages" / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
        has = bool(_section(page, "trace-panel"))
        first = "First difference" in _text(_section(page, "short-answer")) or "first differ" in _text(
            _section(page, "short-answer"))
        if has != first:
            wrong.append((names[c.run_a], names[c.run_b], has))
        if has and trace_panel.PANEL_LEAD not in _text(page):
            wrong.append((names[c.run_a], names[c.run_b], "no lead"))
    assert wrong == []


# ------------------------------------------------------- 4. runs inside steps

def test_the_agent_s_page_links_its_sub_agent_s_run(demo, examined):
    folder, store, runs = demo
    examined(2, "agent runs' pages")
    for agent, sub in ((AGENT, SUB), (AGENT_B, SUB_B)):
        nest = _section(_pages(folder, runs[agent])["case.html"], "nesting")
        assert f'data-nest-run="{sub}"' in nest, agent
        assert f'href="../{runs[sub].key}/case.html"' in nest, agent


def test_sabotage_a_sub_agent_run_not_held_reads_not_loaded(examined):
    from onetrace_console import nesting_view
    receipt = {"stage": {"name": "agent_step"}, "inputs": [{"name": f"run:{SUB}", "digest": "sha256:" + "b" * 64}]}
    examined(1, "nesting drawn with no run held")
    got = nesting_view.run_section([{"receipt": receipt}], {})
    assert nesting_view.NOT_LOADED in _text(got) and "href" not in got


def test_the_comparison_descends_into_the_sub_agent_in_the_sdk_s_words(demo, examined):
    from onetrace_console import nesting_view
    folder, store, runs = demo
    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (runs[AGENT].key, runs[AGENT_B].key))
    page = (folder / "store" / "pages" / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
    examined(1, "the agent comparison's page")
    assert f"The SDK's words: {DESCENT}" in _text(_section(page, "descent"))
    assert f"The runs first differ {DESCENT.replace(',', ' ,')} ." in _text(_section(page, "short-answer"))
    assert nesting_view.descent(DESCENT) == {"path": [("inside", "agent_step"), ("run", SUB, "settle")]}
    assert nesting_view.descent("nested run x: folder not given") == {"not_given": ["x"]}
    assert nesting_view.descent("somewhere else") is None


# ------------------------------------------------------- 5. the "i" notes

_NOTE = re.compile(r'<span class="value" data-words="value">(\d+)</span> checks? made — (?:all hold|it holds)\.'
                   r'<span class="info"[^>]*aria-label="([^"]*)"')


def note_problems(pages: dict[str, dict[str, str]]) -> list[str]:
    """Each note beside "N checks made" adds up to N: the run's ("... = N"), and each step's
    ("... that held: N")."""
    out = []
    for name, by in pages.items():
        for page in by.values():
            for n, note in _NOTE.findall(page):
                total = re.search(r"(?:= |that held: )(\d+)", html.unescape(note))
                if not total or total.group(1) != n:
                    out.append(f"{name}: {n} beside a note adding up to {total.group(1) if total else None}")
    return out


def test_each_note_adds_up_to_the_number_beside_it(demo, examined):
    folder, store, runs = demo
    pages = {name: _pages(folder, run) for name, run in runs.items()}
    examined(sum(len(_NOTE.findall(p)) for by in pages.values() for p in by.values()), "notes read")
    assert sum(len(_NOTE.findall(by["case.html"])) for by in pages.values()) >= 40
    assert note_problems(pages) == []


def test_sabotage_a_note_that_does_not_add_up_is_named(examined):
    from onetrace_console import info_mark
    rows = [{"name": "receipts/01-a.json: chain", "result": "PASS"}, {"name": "manifest: m", "result": "PASS"}]
    page = ('<span class="value" data-words="value">3</span> checks made — all hold.'
            + info_mark.mark(info_mark.checks_note(rows, 3)))
    examined(1, "planted note")
    assert "(The line shows 3.)" in info_mark.checks_note(rows, 3)
    assert note_problems({"x": {"case.html": page}}) == ["x: 3 beside a note adding up to 2"]


# ------------------------------------------------------- 6. paths and builds

def path_problems(root, needles: list[str]) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            data = p.read_bytes()
            out += [f"{p.relative_to(root).as_posix()} names {n}" for n in needles if n.encode() in data]
    return out


def test_a_built_store_names_no_path_of_the_machine_that_built_it(demo, examined):
    import sys
    from pathlib import Path
    folder, store, runs = demo
    needles = [str(folder.resolve()), str(Path(sys.executable).resolve().parent), str(Path.home())]
    examined(sum(1 for p in (folder / "store").rglob("*") if p.is_file()), "built store files scanned")
    assert path_problems(folder / "store", needles) == []


def test_sabotage_a_planted_path_is_named(tmp_path, examined):
    (tmp_path / "a.json").write_text('{"cwd": "/home/someone/demo"}', encoding="utf-8")
    examined(1, "planted file")
    assert path_problems(tmp_path, ["/home/someone"]) == ["a.json names /home/someone"]


def test_a_build_from_an_earlier_one_reads_only_its_runs_and_trust_file(demo, tmp_path, examined):
    from onetrace_console.demo_store import BUILD_RECORD, RUNS_DIRNAME, TRUST_NAME, build_from, check_build_record
    folder, store, runs = demo
    earlier = tmp_path / "earlier"
    shutil.copytree(folder / RUNS_DIRNAME, earlier / RUNS_DIRNAME)
    shutil.copyfile(folder / TRUST_NAME, earlier / TRUST_NAME)
    shutil.copyfile(folder / BUILD_RECORD, earlier / BUILD_RECORD)
    examined(3, "builds from an earlier one")
    #: No store beside them: the record's entries for it are not read.
    assert check_build_record(earlier, only=(RUNS_DIRNAME, TRUST_NAME)) == []
    build_from(tmp_path / "later", earlier)
    assert check_build_record(tmp_path / "later") == []
    one = next(p for p in sorted((earlier / RUNS_DIRNAME).rglob("*.json")) if p.is_file())
    one.write_bytes(one.read_bytes() + b" ")
    with pytest.raises(ValueError, match="is not the demo as its builder made it"):
        build_from(tmp_path / "refused", earlier)


# ------------------------------------------------------- 7. What changed?

#: Each run's choice, by the rule; None where no earlier run of its pipeline is held. A benchmark
#: comes first at each rule (`benchmarks`): p8-42 is the demo's P8 benchmark, with p8-43's inputs.
CHOICES = {
    "p8-43-invoice-tolerance-5pct": ("p8-42-invoice-tolerance-2pct", "benchmark-inputs"),
    "p8-44-invoice-quantity-changed": ("p8-42-invoice-tolerance-2pct", "benchmark-earlier"),
    "pz-53-agent-amount-changed": (AGENT, "benchmark-earlier"),
    "p1-01-baseline-set1": None,
}


def test_what_changed_names_its_rule_and_offers_only_held_comparisons_on_a_public_demo(demo, examined):
    from onetrace_console import what_changed
    folder, store, runs = demo
    examined(len(runs), "runs' What changed? sections")
    for name, want in CHOICES.items():
        got = what_changed.choose(runs[name], store)
        assert ((got[0].run_id, got[1]) if got else None) == want, name
    for name, run in runs.items():
        case = _pages(folder, run)["case.html"]
        sec = _section(case, "what-changed")
        assert sec, name
        assert "data-compare-post" not in case, f"{name} offers a comparison to make on a public demo"
        #: The page is a public console's: its pick is the first candidate whose comparison is held.
        got = what_changed.choose(run, store, public=True)
        if got is None:
            assert 'data-what-changed="none"' in sec, name
            continue
        assert f'data-rule="{got[1]}"' in sec and what_changed.rule_words(got[1], got[2]) in _text(sec), name
        held = what_changed.held(store, got[0].key, run.key)
        assert ('data-what-changed="open"' in sec) == (held is not None), name
        assert ('data-what-changed="not-held"' in sec) == (held is None), name


def test_sabotage_a_local_console_offers_the_comparison_to_make(demo, examined):
    from onetrace_console import what_changed
    folder, store, runs = demo
    run = runs["p1-02-baseline-set2"]
    examined(1, "section drawn as a local console draws it")
    sec = what_changed.section(run, store, public=False)
    other = what_changed.choose(run, store)[0]
    assert f"data-compare-post=\"/compare?a={other.key}&amp;b={run.key}\"" in sec


def test_the_runs_page_says_what_changed_under_each_run_whose_comparison_is_held(demo, examined):
    """A line under the run, across the table, where the rule's comparison is held; none elsewhere."""
    from onetrace_console import what_changed
    folder, store, runs = demo
    page = (folder / "store" / "pages" / "executions-all.html").read_text(encoding="utf-8")
    lines = dict(re.findall(r'<tr class="what-changed-row" data-what-changed-of="([0-9a-f]{64})">'
                            r'<td colspan="9" data-answer="what-changed">What changed: (.*?)</td></tr>', page))
    examined(len(runs), "runs on the Runs page")
    #: The demo is a public console's: each line against the first candidate it holds.
    want = {r.key: what_changed.runs_line(r, store, public=True) for r in runs.values()
            if what_changed.runs_line(r, store, public=True) != what_changed.NOT_COMPARED}
    assert want and {k: html.unescape(re.sub(r"<[^>]+>", "", v)) for k, v in lines.items()} == {
        k: v.replace("`", "") for k, v in want.items()}
    #: Each line right after its run's own row.
    for key in lines:
        assert re.search(rf'<tr data-run="[^"]*" data-key="{key}">.*?</tr><tr class="what-changed-row" '
                         rf'data-what-changed-of="{key}">', page), key


#: A count of checks the viewer states: run and step, as `info_mark` finds them.
_COUNT = re.compile(r'<span class="value" data-words="value">\d+</span> checks? made — (?:all hold|it holds)\.')


def test_every_count_of_checks_has_its_note(demo, examined):
    folder, store, runs = demo
    pages = {name: _pages(folder, run) for name, run in runs.items()}
    counts = sum(len(_COUNT.findall(p)) for by in pages.values() for p in by.values())
    examined(counts, "counts of checks")
    bare = [(name, page) for name, by in pages.items() for page, html_ in by.items()
            for m in _COUNT.finditer(html_) if not html_.startswith('<span class="info"', m.end())]
    assert counts and bare == []


# ------------------------------------------------------- 8. a public console picks a comparison it holds

def test_what_changed_on_a_public_console_takes_the_first_candidate_it_holds_and_says_so(demo, examined):
    """On p1-13: a local console's rule picks the benchmark p1-02 (same inputs), which the demo never
    compared with it, and offers to make it; a public console walks on to the first candidate it
    holds, p1-01, and says it is one the demo compared."""
    from onetrace_console import what_changed
    folder, store, runs = demo
    run = runs["p1-13-baseline-set1-again"]
    examined(2, "consoles' picks")
    local, public = (what_changed.choose(run, store, public=p) for p in (False, True))
    assert (local[0].run_id, local[1], local[2]) == ("p1-02-baseline-set2", "benchmark-inputs", False)
    assert what_changed.held(store, local[0].key, run.key) is None
    assert (public[0].run_id, public[1], public[2]) == ("p1-01-baseline-set1", 2, True)
    sec = _section(_pages(folder, run)["case.html"], "what-changed")
    assert ("Compared with p1-01-baseline-set1, the nearest earlier run with the same inputs that this demo "
            "compared.") in _text(sec)
    assert 'data-what-changed="open"' in sec and "data-held-only" in sec
    assert "data-compare-post" in what_changed.section(run, store, public=False)
    assert "that this demo compared" not in _text(what_changed.section(run, store, public=False))


# ------------------------------------------------------- 9. steps inside steps in the ladder and the graph

def _children_run(folder):
    """A run with two steps called inside a third (`plan`), as onetrace 0.5 records them: the
    children's receipts first, each naming `plan` its parent; `plan` naming them in call order."""
    import os
    import subprocess
    import sys
    code = folder / "kids.py"
    code.write_text(
        "import os, sys\nimport onetrace as ot\nfrom onetrace.emit import Instrument\n"
        "i = Instrument('t', 'transform', '1.0.0', {})\n"
        "@ot.stage('price_lookup', instrument=i)\ndef price_lookup(x): return {'p': x}\n"
        "@ot.stage('tax', instrument=i)\ndef tax(x): return {'t': x}\n"
        "@ot.stage('plan', instrument=i)\ndef plan(x): return {'plan': [price_lookup(x), tax(x)]}\n"
        "@ot.stage('pay', instrument=i)\ndef pay(x): return {'ok': x}\n"
        "@ot.run(run_dir=sys.argv[1] + '/{run_id}', stages=['plan', 'price_lookup', 'tax', 'pay'], "
        "manifest=__file__, anchor_reason='a test')\ndef run(): return pay(plan('1'))\nrun()\n",
        encoding="utf-8")
    env = {**os.environ, "ONETRACE_RUN_ID": "kids-1"}
    subprocess.run([sys.executable, str(code), str(folder / "runs")], check=True, capture_output=True, env=env,
                   cwd=folder)
    return folder / "runs" / "kids-1"


@pytest.fixture(scope="module")
def children(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_home_and_diff import _deliver
    folder = tmp_path_factory.mktemp("children")
    store = Store(folder / "store")
    run = run_and_record(_deliver(_children_run(folder), store), store, ran_at=FIXED_RAN_AT)
    with rendering(onedoor=False, sign_in=False, public=True):
        return run, store, render_execution(run, store, generated_at=GENERATED_AT).pages


def ladder_problems(page: str) -> list[str]:
    """The table of steps: plan's children under it, in call order, each marked and saying so."""
    order = re.findall(r'<tr data-step="(\d+)"( data-child-of="([^"]*)")?', page)
    want = [("3", "", ""), ("1", ' data-child-of="plan"', "plan"), ("2", ' data-child-of="plan"', "plan"), ("4", "", "")]
    out = [] if order == want else [f"the steps are drawn {order}"]
    if len(re.findall(r'<div class="inside">inside <code>plan</code></div>', page)) != 2:
        out.append("a child does not say it is inside plan")
    return out


def test_a_step_s_children_are_under_it_in_the_ladder_and_counted_in_the_graph(children, examined):
    run, store, pages = children
    examined(2, "views of a run with steps inside a step")
    assert ladder_problems(pages["case.html"]) == []
    assert "2 steps inside" in pages["case.html"]


def test_sabotage_children_drawn_in_the_chain_s_order_are_named(children, examined):
    run, store, pages = children
    examined(1, "planted page")
    flat = re.sub(r' data-child-of="plan" data-depth="1"', "", pages["case.html"])
    assert ladder_problems(flat) != []


def test_a_run_with_no_steps_inside_steps_is_drawn_as_it_was(demo, examined):
    from onetrace_console.nesting_ladder import run_ladder
    from onetrace_console.stage_pages import _steps
    folder, store, runs = demo
    examined(len(runs), "runs' tables of steps")
    for name, run in runs.items():
        if name.startswith("pz-"):
            continue
        page = _pages(folder, run)["case.html"]
        assert run_ladder(page, _steps(run, store), {}) == page, name
        assert "data-child-of" not in page and "data-nested-run" not in page, name


def test_a_nested_run_is_a_row_under_its_calling_step_on_the_run_and_the_comparison(demo, examined):
    folder, store, runs = demo
    case = _pages(folder, runs[AGENT])["case.html"]
    c = next(c for c in store.comparisons() if (c.run_a, c.run_b) == (runs[AGENT].key, runs[AGENT_B].key))
    diff = (folder / "store" / "pages" / "diff" / f"{c.key}.html").read_text(encoding="utf-8")
    examined(3, "pages with a nested run")
    row = re.search(rf'<tr data-nested-run="{SUB}" data-child-of="agent_step" data-depth="1">.*?</tr>', case, re.S)
    assert row and f'href="../{runs[SUB].key}/case.html"' in row.group(0) and "its head recorded as" in _text(row.group(0))
    assert re.search(r'<tr data-step="1">.*?</tr><tr data-nested-run=', case, re.S)
    assert "2 steps inside" in case
    sides = re.findall(r'<tr data-nested-run="([^"]+)" data-child-of="agent_step" data-depth="1"><td colspan="6">'
                       r'(baseline|candidate): ', diff)
    assert sides == [(SUB, "baseline"), (SUB_B, "candidate")]
    assert f'href="../runs/{runs[SUB].key}/case.html"' in diff


def test_an_inner_run_s_page_names_the_run_and_step_that_started_it(demo, examined):
    folder, store, runs = demo
    examined(2, "inner runs' pages")
    for inner, outer in ((SUB, AGENT), (SUB_B, AGENT_B)):
        sec = _section(_pages(folder, runs[inner])["case.html"], "parent-run")
        assert f"This run was started by run {outer} at step agent_step" in _text(sec), inner
        assert f'href="../{runs[outer].key}/case.html"' in sec, inner
    assert not _section(_pages(folder, runs[AGENT])["case.html"], "parent-run")


def test_an_inner_run_whose_parent_is_not_held_says_not_loaded(examined):
    from onetrace_console.nesting_view import NOT_LOADED, parent_section
    examined(1, "parent not held")
    got = parent_section({"parent_run": "elsewhere-1", "parent_stage": "plan"}, {})
    assert NOT_LOADED in _text(got) and "href" not in got
