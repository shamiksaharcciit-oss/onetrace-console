"""The run index's terms for the Runs page's filters: `agree:`, `word:`, `after:` and `before:`, each read from the
run's list entry (`run_index.LIST`), which the index computes by the rules the runs list draws by.

- `agree:` is the run's "Records agree" as every page reads it (`records.state`).
- `word:` is the run's verdict against its pipeline's reference, in onetrace's word (`verdicts.word_of`).
- `after:` and `before:` compare the run's recorded start, never the time the console took it in; a run whose record
  gives no time matches neither.
- An index written before it held the list refuses these terms and says why.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console import run_index
    from onetrace_console.store import Store

    folder = shared_demo["folder"]
    return Store(folder / "store" / "store"), run_index.read(folder / "store")


def _keys(results) -> set[str]:
    return {r.run["key"] for r in results}


@pytest.mark.parametrize("state", ["yes", "no", "couldnt-check", "not-checked"])
def test_agree_is_the_records_agree_every_page_reads(demo, state, examined):
    from onetrace_console import records, run_index

    store, index = demo
    want = {r.key for r in store.runs() if records.state(r, store) == state}
    examined(len(store.runs()), f"runs read for agree:{state}")
    assert _keys(run_index.query(index, f"agree:{state}")) == want


def test_word_is_the_verdict_word_kept_for_the_run(demo, examined):
    from onetrace_console import run_index, verdicts

    store, index = demo
    words: dict[str, set[str]] = {}
    for r in store.runs():
        got = verdicts.word_of(r, store)
        if got:
            words.setdefault(got[0], set()).add(r.key)
    examined(len(words), "verdict words")
    assert words
    for word, keys in words.items():
        assert _keys(run_index.query(index, f"word:{word}")) == keys


def test_after_and_before_compare_the_recorded_start(demo, examined):
    from onetrace_console import run_index
    from onetrace_console.overview import ran_at

    store, index = demo
    starts = sorted({ran_at(r) for r in store.runs() if ran_at(r)})
    middle = starts[len(starts) // 2]
    after = {r.key for r in store.runs() if ran_at(r) and ran_at(r) > middle}
    before = {r.key for r in store.runs() if ran_at(r) and ran_at(r) < middle}
    examined(len(store.runs()), "runs' recorded starts")
    assert _keys(run_index.query(index, f"after:{middle}")) == after
    assert _keys(run_index.query(index, f"before:{middle}")) == before
    day = middle[:10]
    assert _keys(run_index.query(index, f"after:{day}")) == {
        r.key for r in store.runs() if ran_at(r) and ran_at(r)[:10] >= day
    }


def test_a_run_whose_record_gives_no_time_matches_neither(demo, examined):
    import copy

    from onetrace_console import run_index

    _store, index = demo
    one = copy.deepcopy(index)
    one["runs"] = [copy.deepcopy(index["runs"][0])]
    one["runs"][0]["list"]["ran"] = ""
    examined(1, "a run with no recorded time")
    assert not run_index.query(one, "after:2000-01-01") and not run_index.query(one, "before:2999-01-01")


@pytest.mark.parametrize(
    ("q", "words"),
    [
        ("agree:maybe", "agree takes yes, no, couldnt-check or not-checked"),
        ("after:yesterday", "after takes a date or a time"),
        ("before:12/11/2026", "before takes a date or a time"),
        ("word:", "is not a term"),
    ],
)
def test_a_value_the_term_does_not_hold_is_refused_in_words(demo, q, words, examined):
    from onetrace_console import run_index

    _store, index = demo
    examined(1, "query")
    with pytest.raises(run_index.QueryError, match=words):
        run_index.query(index, q)


@pytest.mark.parametrize("term", ["agree:yes", "word:MATCH", "after:2026-01-01", "before:2026-01-01"])
def test_an_index_written_before_it_held_the_list_refuses_the_term_and_says_why(demo, term, examined):
    from onetrace_console import run_index

    _store, index = demo
    earlier = {k: v for k, v in index.items() if k != run_index.LIST}
    examined(1, "query on an earlier index")
    with pytest.raises(run_index.QueryError, match="written before it held"):
        run_index.query(earlier, term)


def test_the_grammar_names_each_term(examined):
    from onetrace_console.run_index import GRAMMAR

    said = " ".join(t for t, _ in GRAMMAR)
    examined(4, "terms")
    for t in ("agree:", "word:", "after:", "before:"):
        assert t in said
