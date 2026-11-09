"""A pipeline's first run to leave its reference, by step and after a time, in recorded order.

1. A planted series with the change at run k: run k is found exactly, beside run k-1, the last run
   to read as the reference, though the runs arrived in another order; the runs are listed by the
   recorder's clock.
2. A series with no change: "No run left the reference." at every step.
3. A gap in recording: a run whose records could not be checked, and a run with no verdict kept, is
   shown as a gap and never read as the reference; a change at the gap is found at the next run, the
   gap named between them.
4. The window form: the first run recorded after a time that left the reference; none after the
   last change; a time with no offset is read as UTC and said; a time it does not read is said.
5. No reference: with no benchmark, and with a benchmark no reference is made from, the page says so
   and walks nothing, never a benchmark's runs in its place.
6. On the public demo as built: a page per pipeline, each step's answer as the kept verdicts read
   it, no command run, and `GET /bisect` on a public console answers and writes nothing.
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from onetrace_console import bisect_page

GENERATED_AT = "2026-09-26T12:00:00+02:00"
SAME, CHANGED = "sha256:" + "b" * 64, "sha256:" + "e" * 64


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


#: The first arrival's time. The runs are received whole seconds apart from it, in `arrival` order, so the
#: console's arrival order is the planted one however fast they are ingested: its arrival time is kept
#: to the second, and runs received in one second are ordered by name.
RECEIVED_FROM = datetime(2026, 9, 26, 9, 0, 0, tzinfo=timezone.utc)


def _series(folder, outputs: list[str], arrival: list[int]):
    """Runs s-1..s-n recorded in that order, the first marked as the benchmark, delivered in `arrival`,
    each received a second after the one before."""
    from onetrace_console import benchmarks
    from onetrace_console.checks import run_and_record
    from onetrace_console.store import Store
    from tests.model_call_runs import record_run
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    made = [record_run(folder / f"s-{i}", f"s-{i}", output=o) for i, o in enumerate(outputs, start=1)]
    store = Store(folder / "store")
    runs = {}
    for n, i in enumerate(arrival):
        run = replace(_deliver(made[i - 1], store, outputs=True),
                      received_at=(RECEIVED_FROM + timedelta(seconds=n)).isoformat(timespec="seconds"))
        store.put_run(run)
        runs[i] = run_and_record(run, store, ran_at=FIXED_RAN_AT)
    benchmarks.mark(store, runs[1], who="test")
    return store, runs


def _page(store, *, public=False, after=None, compute=None):
    from onetrace_console.frame import rendering
    from onetrace_console.overview import pipelines
    with rendering(onedoor=False, sign_in=False, public=public):
        return bisect_page.render_bisect(pipelines(store)[0], store, generated_at=GENERATED_AT, after=after,
                                         compute=compute)


def _row(page: str, step: str = "call") -> str:
    return re.search(rf'<tr data-step="{step}".*?</tr>', page, re.S).group(0)


def _left(page: str, step: str = "call") -> str:
    return re.search(r'data-left="([^"]*)"', _row(page, step)).group(1)


def _before(page: str, step: str = "call") -> str:
    m = re.search(r'<td[^>]*\bdata-before\b[^>]*><a href="runs/([0-9a-f]{64})/case\.html"', _row(page, step))
    return m.group(1) if m else ""


@pytest.fixture(scope="module")
def changed_at_4(tmp_path_factory):
    store, runs = _series(tmp_path_factory.mktemp("bisect-k"), [SAME, SAME, SAME, CHANGED, CHANGED, SAME],
                          arrival=[6, 2, 5, 1, 4, 3])
    return store, runs, _page(store)


def test_the_change_at_run_k_is_found_exactly(changed_at_4, examined):
    store, runs, page = changed_at_4
    examined(len(runs), "planted runs")
    assert _left(page) == runs[4].key and _before(page) == runs[3].key
    assert "output differs" in _text(_row(page))
    order = re.findall(r'<tr data-run="([0-9a-f]{64})">', page)
    #: Each run's start as its receipts state it, in the time's `datetime`; shown in the one form, to the
    #: millisecond where it has them.
    shown = re.findall(r'<td[^>]*class="mono"[^>]*><a [^>]*><time datetime="([^"]+)"[^>]*>([^<]+)</time></a></td>', page)
    assert [a for a, _ in shown] == [bisect_page.recorded_start(runs[i], store)[1] for i in range(1, 7)]
    assert all(re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d(\.\d{3}| UTC)", b) for _, b in shown), shown
    #: The built page carries the one window form, a plain GET; each run's start is a link into it.
    asks = re.findall(r'<a href="bisect\?p=P1&amp;after=([^"]+)" data-bisect-ask', page)
    assert len(asks) == len(runs)
    assert len(re.findall(r'<form method="get" action="bisect" data-bisect-window>', page)) == 1
    assert order == [runs[i].key for i in range(1, 7)], "not the recorder's order"
    from onetrace_console.overview import pipelines
    assert [r.key for r in pipelines(store)[0].runs] != order, "the planted arrival order is the recorded one"
    assert 'data-pair="compare"' in _row(page)
    for line in bisect_page.NON_CLAIMS:
        assert line in _text(page)


def test_sabotage_arrival_order_finds_another_run(changed_at_4, monkeypatch, examined):
    """Placed by when the console received them, the same runs give another answer: the clock is what holds k."""
    store, runs, _ = changed_at_4
    monkeypatch.setattr(bisect_page, "recorded_start", lambda run, st: (_received(run), run.received_at))
    examined(1, "the planted series")
    assert _left(_page(store, compute=False)) != runs[4].key


def _received(run):
    return datetime.fromisoformat(run.received_at)


def test_a_held_comparison_is_side_by_side_with_the_kind_line_at_the_step(changed_at_4, examined):
    from onetrace_console.compare import compare
    from tests.test_checks import FIXED_RAN_AT
    store, runs, _ = changed_at_4
    c = compare(runs[3], runs[4], store, ran_at=FIXED_RAN_AT)
    page = _page(store, compute=False)
    examined(1, "held pair")
    row = _row(page)
    assert f'href="diff/{c.key}.html" data-pair="held"' in row
    assert 'data-section="first-kind"' in row


def test_a_series_with_no_change_says_no_run_left(tmp_path, examined):
    store, runs = _series(tmp_path, [SAME, SAME, SAME], arrival=[1, 2, 3])
    page = _page(store)
    examined(len(runs), "planted runs")
    assert _left(page) == "" and bisect_page.NONE_LEFT in _text(_row(page))
    assert _before(page) == runs[3].key


def test_a_gap_is_shown_as_a_gap_and_never_as_the_reference(tmp_path, monkeypatch, examined):
    """Run 3 changed, and its records could not be checked; run 4 changed: found at 4, 3 named between."""
    from onetrace_console import records, verdicts
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED, CHANGED, SAME], arrival=[1, 2, 3, 4, 5])
    real = records.state
    monkeypatch.setattr(records, "state", lambda run, st: records.COULDNT if run.key == runs[3].key else real(run, st))
    page = _page(store)
    examined(len(runs), "planted runs")
    assert _left(page) == runs[4].key and _before(page) == runs[2].key
    note = _text(_row(page))
    assert "Between them, 1 not seen:" in note and runs[3].run_id in note
    assert 'data-gap="unchecked"' in re.search(rf'<tr data-run="{runs[3].key}">.*?</tr>', page, re.S).group(0)


def test_a_run_with_no_verdict_kept_is_a_gap(tmp_path, examined):
    """Recorded, with no verdict against the reference held, on a page that makes none: a gap."""
    from onetrace_console import verdicts
    from onetrace_console.overview import pipelines
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    verdicts.reference_record(pipelines(store)[0], store, compute=True)
    for k in (1, 3, 4):
        verdicts.verdict_record(runs[k], store, compute=True)
    assert verdicts.verdict_record(runs[2], store, compute=False)[1] is None
    page = _page(store, compute=False)
    examined(len(runs), "planted runs")
    assert 'data-gap="none"' in re.search(rf'<tr data-run="{runs[2].key}">.*?</tr>', page, re.S).group(0)
    assert _before(page) == runs[1].key and _left(page) == runs[3].key
    assert "Between them, 1 not seen:" in _text(_row(page))


def test_the_window_form(changed_at_4, examined):
    from onetrace_console.overview import pipelines
    store, runs, _ = changed_at_4
    start = {i: bisect_page.recorded_start(r, store) for i, r in runs.items()}
    label = pipelines(store)[0].label

    def asked(after):
        from onetrace_console.frame import rendering
        with rendering(onedoor=False, sign_in=False, public=True):
            return bisect_page.page_for(store, label, after, generated_at=GENERATED_AT)
    examined(4, "times asked")
    found = asked(start[2][0].isoformat())
    result = re.search(r'<p data-bisect-window-result="left">(.*?)</p>', found, re.S).group(1)
    assert runs[4].run_id in _text(result) and "diverged at call" in _text(result)
    window = _text(re.search(r'<div data-section="bisect-window">.*?</div>', found, re.S).group(0))
    assert f"The run before it to read as identical: {runs[3].run_id}" in window
    none = asked(start[5][0].isoformat())
    assert 'data-bisect-window-result="none"' in none
    naive = asked(start[2][0].astimezone(__import__("datetime").timezone.utc).replace(tzinfo=None).isoformat())
    assert bisect_page.WINDOW_UTC in _text(naive) and 'data-bisect-window-result="left"' in naive
    bad = asked("last week")
    assert 'data-bisect-window-result="unread"' in bad
    assert asked("").count("data-bisect-window-result") == 0


def test_no_reference_walks_nothing(tmp_path, monkeypatch, examined):
    from onetrace_console import benchmarks, verdicts
    store, runs = _series(tmp_path, [SAME, CHANGED], arrival=[1, 2])
    benchmarks.unmark(store, runs[1].key)
    none = _page(store)
    monkeypatch.setattr(verdicts, "_agree", lambda run, st: False)
    benchmarks.mark(store, runs[1], who="test")
    refused = _page(store)
    examined(2, "pipelines without a reference")
    for page in (none, refused):
        assert bisect_page.NO_REFERENCE in _text(page) and bisect_page.MAKE_COMMAND in _text(page)
        assert 'data-section="bisect-steps"' not in page and 'data-section="bisect-runs"' not in page
    assert "data-bisect-reason" in refused and "data-bisect-reason" not in none


@pytest.mark.parametrize("word", ["caused", "because", "why"])
def test_no_line_says_what_produced_the_difference(word, examined):
    said = [v for k, v in vars(bisect_page).items() if k.isupper() and isinstance(v, str)]
    said += list(bisect_page.NON_CLAIMS) + list(bisect_page.GAP_WORDS.values())
    examined(len(said), "lines")
    assert not any(re.search(rf"\b{word}\b", s, re.I) for s in said)


def test_on_the_public_demo_each_step_reads_as_the_kept_verdicts(shared_demo, monkeypatch, examined):
    from onetrace_console import verdicts
    from onetrace_console.frame import rendering
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    ran = []
    monkeypatch.setattr(verdicts, "_run_in", lambda *a, **k: ran.append(a) or {"exit": "", "note": "", "files": {}})
    checked = 0
    for p in pipelines(store):
        built = (folder / "store" / "pages" / bisect_page.page_href(p.label)).read_text(encoding="utf-8")
        with rendering(onedoor=False, sign_in=False, public=True):
            walk = bisect_page.Walk(p, store, compute=False)
        if walk.doc is None:
            assert bisect_page.NO_REFERENCE in _text(built)
            continue
        placed = [r for r, _ in walk.placed]
        for step in walk.steps():
            left = _left(built, step)
            words = [walk.word(r, step) for r in placed]
            if not left:
                continue
            k = next(i for i, r in enumerate(placed) if r.key == left)
            assert words[k] in bisect_page.LEAVING
            read = [i for i, w in enumerate(words[:k]) if w is not None and w not in bisect_page.LEAVING]
            assert read, (p.label, step)
            before = read[-1]
            #: The first such run: none between the first run read as the reference and it left it.
            assert not any(w in bisect_page.LEAVING for w in words[read[0] + 1:k])
            assert all(w is None for w in words[before + 1:k]) and _before(built, step) == placed[before].key
            checked += 1
    examined(checked, "steps where a run left the reference")
    assert checked > 0 and ran == []


def test_a_public_console_s_window_form_answers_and_writes_nothing(shared_cli_demo, tmp_path, examined):
    import urllib.request
    from tests.http_limits import limit
    from tests.test_folder_load import _Console
    from tests.test_public_mode import _config, _tree
    built = shared_cli_demo["folder"]
    config = _config(tmp_path, built, compare_cache=str(tmp_path / "compared"))
    port = json.loads(config.read_text(encoding="utf-8"))["port"]
    before = _tree(built)
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/bisect?p=P2&after=2000-01-01T00%3A00%3A00Z",
                                    timeout=limit(30)) as r:
            page, status = r.read().decode("utf-8"), r.status
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/bisect?p=..%2Fx&after=x", timeout=limit(30))
            other = 200
        except urllib.error.HTTPError as e:
            other = e.code
    finally:
        c.stop()
    examined(1, "window form on a public console")
    assert status == 200 and 'data-frame="banner"' in page and 'data-bisect-window-result="left"' in page
    assert other == 404 and _tree(built) == before


# ---------------------------------------------------------------- the answer first


def _answer(page: str) -> str:
    """The answer's words, each run named as its id (the short key the page shows beside it set aside)."""
    said = _text(re.search(r'<p data-section="bisect-answer"[^>]*>.*?</p>', page, re.S).group(0))
    return re.sub(r" · [0-9a-f]{12} ", "", said)


def test_the_answer_comes_first_naming_the_run_its_step_and_the_run_before_it(changed_at_4, examined):
    store, runs, page = changed_at_4
    examined(1, "the planted series' page")
    assert page.index('data-section="bisect-answer"') < page.index('data-section="what"')
    assert _answer(page).startswith(
        f"The first run to leave the reference is {runs[4].run_id}, at step call (output differs). "
        f"The run before it, {runs[3].run_id}, reads as the reference.")
    assert 'data-pair="compare"' in re.search(r'<p data-section="bisect-answer".*?</p>', page, re.S).group(0)


def test_where_no_run_left_the_answer_says_so(tmp_path, examined):
    store, runs = _series(tmp_path, [SAME, SAME, SAME], arrival=[1, 2, 3])
    examined(len(runs), "planted runs")
    assert _answer(_page(store)) == bisect_page.ANSWER_NONE


def test_with_no_reference_there_is_no_answer_and_today_s_words(tmp_path, examined):
    from onetrace_console import benchmarks
    store, runs = _series(tmp_path, [SAME, CHANGED], arrival=[1, 2])
    benchmarks.unmark(store, runs[1].key)
    page = _page(store)
    examined(1, "a pipeline with no reference")
    assert 'data-section="bisect-answer"' not in page and bisect_page.NO_REFERENCE in _text(page)


def test_where_runs_leave_at_more_steps_the_earliest_run_is_named_and_the_rest_counted(changed_at_4, monkeypatch,
                                                                                    examined):
    store, runs, _ = changed_at_4
    real = bisect_page.Walk.at_step
    monkeypatch.setattr(bisect_page.Walk, "steps", lambda self: ["early", "call", "late"])
    def at_step(self, step):
        if step == "call":
            return real(self, step)
        got = real(self, "call")
        k = 5 if step == "early" else 6
        return {**got, "left": runs[k], "before": runs[k - 1], "word": "setting differs"}
    monkeypatch.setattr(bisect_page.Walk, "at_step", at_step)
    examined(3, "steps")
    said = _answer(_page(store, compute=False))
    assert said.startswith(f"The first run to leave the reference is {runs[4].run_id}, at step call (output differs).")
    assert "And 2 more steps: below." in said


def test_on_the_demo_p10_s_answer_names_its_run_step_and_word(shared_demo, examined):
    built = (shared_demo["folder"] / "store" / "pages" / bisect_page.page_href("P10")).read_text(encoding="utf-8")
    examined(1, "P10's page as built")
    assert _answer(built).startswith("The first run to leave the reference is pz-53-agent-amount-changed, at step "
                                     "agent_step (output differs). The run before it, pz-51-agent-baseline, reads as "
                                     "the reference.")


# ---------------------------------------------------------------- plain words, the exact rule kept


def test_plain_words_say_how_to_read_it_and_the_exact_rule_is_kept_word_for_word(changed_at_4, examined):
    store, runs, page = changed_at_4
    examined(1, "the planted series' page")
    plain = re.sub(r" · [0-9a-f]{12} ", "",
                   _text(re.search(r'<div data-section="bisect-how">.*?</div>', page, re.S).group(0)))
    assert plain == (f"Runs are listed in the order they were recorded, by the recorder's clock. Each is compared "
                     f"with the reference run, {runs[1].run_id}. A run leaves the reference at the first step whose "
                     "output, setting or input differs; the same output, only slower, reads as the reference.")
    rule = re.search(r'<details data-section="bisect-rule">(.*?)</details>', page, re.S).group(1)
    assert bisect_page.WHAT in html.unescape(rule) and bisect_page.LEAVES in html.unescape(rule)
    outside = page.replace(re.search(r'<details data-section="bisect-rule">.*?</details>', page, re.S).group(0), "")
    assert bisect_page.WHAT not in html.unescape(outside) and bisect_page.LEAVES not in html.unescape(outside)
    assert page.index('data-section="bisect-how"') < page.index('data-section="bisect-steps"')


def test_the_reference_line_is_one_line_of_text_with_the_seal_short_and_its_whole_value_folded_after(
        changed_at_4, examined):
    """No fold inside the line: a closed Details is a box of its own, and text after it starts a line. The
    seal is shown short in the line, its comma beside it, and whole in a fold after the line."""
    store, runs, page = changed_at_4
    ref = re.search(r'<div data-section="bisect-reference">.*?</div>', page, re.S).group(0)
    line = re.search(r"<p data-reference-line>(.*?)</p>", ref, re.S).group(1)
    examined(1, "the reference line")
    assert "<details" not in line and re.search(r'<span class="mono">sha256:[0-9a-f]+…</span>, made from ', line), line
    assert re.sub(r" · [0-9a-f]{12} ", "", _text(line)).replace(" ,", ",") == (
        f"The reference: {re.search(r'sha256:[0-9a-f]+…', line).group(0)}, made from {runs[1].run_id}.")
    assert re.search(r'</p><details class="fingerprint">.*?data-fingerprint="whole">sha256:[0-9a-f]{64}</span>', ref)


# ---------------------------------------------------------------- gaps with their reason


def _why(page: str, run) -> str:
    row = re.search(rf'<tr data-run="{run.key}">.*?</tr>', page, re.S).group(0)
    #: A full stop after a link reads with no space before it.
    return _text(re.search(r"<p data-gap-why>.*?</p>", row, re.S).group(0)).replace(" .", ".")


def test_a_gap_with_no_reason_in_its_records_says_so(tmp_path, monkeypatch, examined):
    from onetrace_console import records
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED], arrival=[1, 2, 3])
    real = records.state
    monkeypatch.setattr(records, "state", lambda run, st: records.COULDNT if run.key == runs[2].key else real(run, st))
    examined(1, "a gap whose check rows all ran")
    assert _why(_page(store), runs[2]) == bisect_page.GAP_NOT_RECORDED


def test_a_gap_whose_check_left_a_step_unsettled_quotes_the_check_s_rows(tmp_path, monkeypatch, examined):
    """The kept report with rows not run at a step, as onetrace-verify writes for a model-call record format it
    does not implement: quoted whole, and what would include the run."""
    from onetrace_console import records
    from onetrace_console.store import Store
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED], arrival=[1, 2, 3])
    real_get, run = Store.get, runs[2]
    envelope = json.loads(real_get(store, run.check_report).decode("utf-8"))
    receipt = re.search(r"\] (receipts/[^:]+):", envelope["stdout"]).group(1)
    planted = [f"[NOT-RUN] {receipt}: record 'model_call.json' format -- model-call-record/0.1-draft: not implemented",
               f"[NOT-RUN] {receipt}: record 'model_call.json' fields complete and well formed -- record format not implemented"]
    lines = envelope["stdout"].splitlines()
    at = next(i for i, ln in enumerate(lines) if ln.startswith("[") and receipt in ln)
    lines = lines[:at + 1] + planted + lines[at + 1:]
    #: The text, its summary line and the --json rows are one report: each gains the two rows.
    rows = json.loads(envelope["rows_json"]["stdout"])
    rows["rows"][at + 1:at + 1] = [{"name": p.split("] ", 1)[1].split(" -- ")[0], "result": "NOT-RUN",
                                    "detail": p.split(" -- ", 1)[1]} for p in planted]
    rows["summary"]["not_run"] += len(planted)
    envelope["rows_json"]["stdout"] = json.dumps(rows)
    s = rows["summary"]
    lines = [f"{s['pass']} pass, {s['fail']} fail, {s['not_run']} not-run  ->  {s['result']}"
             if re.fullmatch(r"\d+ pass, \d+ fail, \d+ not-run  ->  \w+", ln) else ln for ln in lines]
    envelope["stdout"] = "\n".join(lines) + "\n"
    monkeypatch.setattr(Store, "get", lambda self, key: (json.dumps(envelope).encode("utf-8") if key == run.check_report
                                                          else real_get(self, key)))
    real = records.state
    monkeypatch.setattr(records, "state", lambda r, st: records.COULDNT if r.key == run.key else real(r, st))
    examined(2, "planted rows not run")
    said = _why(_page(store), run)
    assert said.startswith(f"The check did not run: {planted[0]}."), said
    assert "And 1 more row, on its Proof page." in said and said.endswith(bisect_page.GAP_ROWS_INCLUDE)


def test_a_gap_with_no_verdict_kept_says_so_and_what_makes_one(tmp_path, examined):
    from onetrace_console import verdicts
    from onetrace_console.overview import pipelines
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    verdicts.reference_record(pipelines(store)[0], store, compute=True)
    for k in (1, 3, 4):
        verdicts.verdict_record(runs[k], store, compute=True)
    examined(1, "a run with no verdict kept")
    assert _why(_page(store, compute=False), runs[2]) == f"{bisect_page.GAP_NONE_WHY} {bisect_page.GAP_NONE_INCLUDE}"


def test_a_refused_verdict_s_gap_gives_the_verdict_s_own_reason(tmp_path, monkeypatch, examined):
    from onetrace_console import verdicts
    store, runs = _series(tmp_path, [SAME, SAME, CHANGED], arrival=[1, 2, 3])
    real = verdicts.verdict_record
    def refused(run, st, *, compute):
        ref, rec = real(run, st, compute=compute)
        if run.key == runs[2].key:
            rec = {**(rec or {}), "verdict": {"verdict": "refused", "reason": "does not verify", "steps": []}}
        return ref, rec
    monkeypatch.setattr(verdicts, "verdict_record", refused)
    examined(1, "a refused verdict")
    assert _why(_page(store), runs[2]) == (f"{bisect_page.GAP_VERDICT_WHY.format(reason='does not verify')} "
                                           f"{bisect_page.GAP_VERDICT_INCLUDE}")


# ---------------------------------------------------------------- one "after a time" control


def test_one_find_after_control_in_place_of_a_link_on_every_row(changed_at_4, examined):
    store, runs, page = changed_at_4
    window = re.search(r'<div data-section="bisect-window">.*?</div>', page, re.S).group(0)
    examined(1, "the planted series' page")
    assert _text(window).startswith("Find the first run to leave after:") and ">Find</button>" in window
    assert '<input type="text" name="after"' in window and 'name="p" value="P1"' in window
    assert bisect_page.WINDOW_AFTER_RUN not in _text(page)
    head = re.search(r'<table data-section="bisect-runs"><thead>(.*?)</thead>', page, re.S).group(1)
    assert _text(head) == "# Run Recorded start Its verdict"


def test_a_public_console_answers_as_the_built_page_and_draws_the_same_form(shared_demo, examined):
    """The page the console answers at `/bisect` (public, nothing run) and the page as built: the same
    answer, and the one form."""
    from onetrace_console.frame import rendering
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    store = Store(folder / "store" / "store")
    checked = 0
    for label in ("P1", "P10"):
        built = (folder / "store" / "pages" / bisect_page.page_href(label)).read_text(encoding="utf-8")
        with rendering(onedoor=False, sign_in=False, public=True):
            served = bisect_page.page_for(store, label, "", generated_at=GENERATED_AT)
        assert _answer(served) == _answer(built), label
        for page in (built, served):
            assert len(re.findall(r'<form method="get" action="bisect" data-bisect-window>', page)) == 1
        checked += 1
    examined(checked, "pipelines, built and served")
