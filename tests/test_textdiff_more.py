"""Where the text diff comes from, "Show more", and the corpus trace.

5.1 Each comparison stores its own run of `onetrace diff A B --text --json --no-follow`, its JSON
    byte for byte and its command shown; `diff.txt` and `diff.json` stay as they are.
5.2 "Show more" re-runs it at the console's one larger limit (ten times the SDK's 200), for who may
    compare, behind the same guard as `/compare`; stored as a run of its own; the page names which
    limit it shows; nothing earlier changes.
5.3 `--no-follow`: the corpus trace is board 7's.
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import replace

import pytest

from onetrace_console.compare import (DIFF, LOCALIZE, TEXT_DIFF, TEXT_DIFF_MORE_LINES, compare,
                                      show_more, text_diff_raw)
from onetrace_console.render import render_diff
from onetrace_console.textdiff_view import read_textdiff
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, _deliver, _require_exam
from tests.test_pages import GENERATED_AT

MORE = f"{TEXT_DIFF} --max-lines {TEXT_DIFF_MORE_LINES}"


@pytest.fixture
def pq(store, tmp_path):
    _require_installed()
    _require_exam()
    a = _deliver(EXAM / "dag-r37" / "run_P", store)
    b = _deliver(EXAM / "dag-r37" / "run_Q", store)
    return compare(a, b, store, ran_at=FIXED_RAN_AT, work_root=tmp_path / "work"), store, tmp_path


def test_the_text_diff_is_a_run_of_its_own_and_its_json_is_the_sdks_bytes(pq, examined):
    comparison, store, tmp_path = pq
    run = comparison.verb(TEXT_DIFF)
    examined(1, "text-diff run")
    assert run is not None and run.shown_command == (
        "python -m onetrace diff RUN_A RUN_B --text --json --no-follow")
    assert "--no-follow" in run.command and "--max-lines" not in run.command
    #: The recorded command, run by hand over the same two folders, prints the same bytes.
    argv = list(run.command)
    argv[argv.index("--out") + 1] = str(tmp_path / "by-hand")
    again = subprocess.run(argv, capture_output=True).stdout
    assert store.get(run.stdout_key) == again
    doc = read_textdiff(again)
    assert doc.get("corpus_traces") in (None, []) or all(
        t["status"] == "not followed" for t in doc["corpus_traces"]), "5.3: never followed here"
    #: diff and localize are the verbs they were.
    assert [v.verb for v in comparison.verbs][:2] == [DIFF, LOCALIZE]


def test_a_comparison_stored_without_a_text_diff_is_made_again(pq, examined):
    comparison, store, _ = pq
    older = replace(comparison, verbs=tuple(v for v in comparison.verbs if v.verb != TEXT_DIFF))
    store.put_comparison(older)
    run_a, run_b = store.get_run(comparison.run_a), store.get_run(comparison.run_b)
    again = compare(run_a, run_b, store, ran_at=FIXED_RAN_AT)
    examined(1, "comparison made again")
    assert again.verb(TEXT_DIFF) is not None


def test_show_more_is_a_run_of_its_own_and_changes_nothing_earlier(pq, examined):
    comparison, store, _ = pq
    before = store.get_comparison(comparison.key)
    after = show_more(comparison, store)
    examined(len(before.verbs), "earlier runs compared")
    assert after.verbs[:len(before.verbs)] == before.verbs, "an earlier run changed"
    more = after.verb(MORE)
    assert more is not None and f"--max-lines {TEXT_DIFF_MORE_LINES}" in more.shown_command
    assert store.get_comparison(comparison.key) == after
    #: The verdict is the same: the larger limit draws more lines, never another answer.
    first, larger = (read_textdiff(store.get(v.stdout_key)) for v in (before.verb(TEXT_DIFF), more))
    assert (first["envelope"], first["exit"]) == (larger["envelope"], larger["exit"])
    assert [n["verdict"] for n in first["nodes"]] == [n["verdict"] for n in larger["nodes"]]
    assert show_more(after, store) == after, "asked again, the stored run is the answer"


def test_the_page_names_the_limit_it_shows(pq):
    comparison, store, _ = pq
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    assert "Shown with at most 200 lines per output (the SDK&#x27;s default)." in page
    after = show_more(comparison, store)
    page = render_diff(after, store, generated_at=GENERATED_AT)
    assert (f"Shown with at most {TEXT_DIFF_MORE_LINES} lines per output (this console&#x27;s "
            f"larger limit, ten times the SDK&#x27;s default).") in page
    assert f"--max-lines {TEXT_DIFF_MORE_LINES}" in page
    assert text_diff_raw(after, store)[1] == MORE


@pytest.fixture
def warranty(store, tmp_path):
    """The SDK's own warranty pair, stored and compared: its text diff has outputs with lines."""
    from tools.fetch_sdk_fixtures import WARRANTY
    _require_installed()
    _require_exam()
    from onetrace_console.ingest import accept
    from tests.conftest import make_tar
    from tests.test_diff_sdk_text_layer import _files

    def whole(folder):
        #: Delivered whole, artifacts/ included: `_deliver` sends the chain alone, and an output
        #: whose file was not delivered is one the SDK marks not shown.
        got = accept(make_tar(_files(folder)), store)
        assert got.run is not None, getattr(got, "body", got)
        return got.run
    a, b = whole(WARRANTY / "runs" / "query-v1"), whole(WARRANTY / "runs" / "query-v2")
    return compare(a, b, store, ran_at=FIXED_RAN_AT), store


def test_a_stored_comparison_of_the_golden_pair_shows_twelve_to_six_on_its_diff_page(warranty):
    """Item 4 end to end through the console: stored runs, the comparison's own text-diff run,
    the Diff page."""
    comparison, store = warranty
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    section = page[page.index('<section data-section="text-diff">'):]
    section = section[:section.index("</section>")]
    assert '<mark class="del">twelve</mark>' in section and '<mark class="ins">six</mark>' in section
    assert section.count('data-badge="verified"') == 3


def test_the_page_asks_for_more_only_where_an_output_was_cut(warranty):
    comparison, store = warranty
    raw, _verb = text_diff_raw(comparison, store)
    doc = json.loads(raw)
    page = render_diff(comparison, store, generated_at=GENERATED_AT)
    assert "/text-diff/more" not in page, "nothing is cut on the golden pair"
    #: A cut output, as the SDK writes one, and the page asks.
    cut = 0
    for node in doc["nodes"]:
        for out in node["outputs"]:
            if out["verified"] and out["hunks"] and not cut:
                out["truncated"] = {"more_lines": "7"}
                cut += 1
    assert cut == 1, "the premise: one verified output with lines, cut"
    run = comparison.verb(TEXT_DIFF)
    doc_bytes = json.dumps(doc, separators=(",", ":"), sort_keys=True).encode("utf-8")
    cut_run = replace(run, stdout_key=store.put(doc_bytes))
    cut_cmp = replace(comparison, verbs=tuple(cut_run if v is run else v for v in comparison.verbs))
    page = render_diff(cut_cmp, store, generated_at=GENERATED_AT)
    assert f"POST /text-diff/more?c={comparison.key}" in page
    assert "… 7 more lines" in page


# ------------------------------------------------------------------ over HTTP: the guard

def _stored_pair(base):
    from tests.test_serve import _post, _real_delivery
    keys = []
    for name in ("run_P", "run_Q"):
        status, body = _post(base, "/v1/runs", _real_delivery(EXAM / "dag-r37" / name))
        assert status == 200, body[:300]
        keys.append(json.loads(body)["run_key"])
    status, body = _post(base, f"/compare?a={keys[0]}&b={keys[1]}")
    assert status == 200, body[:300]
    return json.loads(body)["comparison_key"]


def test_a_limit_other_than_the_consoles_is_refused(server, examined):
    from tests.test_serve import _post
    _require_installed()
    _require_exam()
    base, _root = server
    key = _stored_pair(base)
    examined(2, "show-more requests")
    status, body = _post(base, f"/text-diff/more?c={key}&max_lines=5000")
    assert status == 400 and b"fixed at 2000" in body, body
    status, body = _post(base, f"/text-diff/more?c={key}")
    assert status == 200, body[:300]
    assert json.loads(body)["max_lines"] == TEXT_DIFF_MORE_LINES


def test_a_cross_site_show_more_is_refused_and_stores_nothing(server, examined):
    from urllib.parse import urlsplit

    from onetrace_console.serve import Handler
    from onetrace_console.store import Store
    from tests.test_local_mode import _call
    _require_installed()
    _require_exam()
    base, root = server
    key = _stored_pair(base)
    saved = Handler.local_port
    Handler.local_port = urlsplit(base).port
    try:
        examined(2, "cross-site show-more requests")
        for headers in ({"Origin": "https://evil.example"}, {"Sec-Fetch-Site": "cross-site"}):
            status, _, _ = _call(base, f"/text-diff/more?c={key}", method="POST", body=b"",
                                 headers=headers)
            assert status == 403, headers
    finally:
        Handler.local_port = saved
    assert Store(root / "store").get_comparison(key).verb(MORE) is None, "nothing was run"
