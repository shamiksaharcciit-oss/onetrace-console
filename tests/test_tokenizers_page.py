"""The Tokenizers page leads somewhere.

It lists every model step in the store whose record states a `tokenizer.digest` no kept or configured tokenizer
matches, grouped by digest (the digest short, and whole in a fold), with the number of steps and a link to each step's
page, where the picker is: the first 20 per digest, then "and N more". Its lead says what to pick. Where no step asks:
"No model step in this console needs a tokenizer: ...". The kept tokenizers, with Remove, follow as before.

Where a record's `tokenizer.digest` is example data the demo's builder constructed, both the page's entry and the
step's own page say so, and the step offers no picker. Where the `tokenizers` package isn't importable, both say so
with the install line for the console's Python, and the step offers no picker.
"""

from __future__ import annotations

import re
from html import unescape

from onetrace_console import token_upload as T


def _entries(n_first: int, n_second: int) -> list[tuple]:
    a, b = "sha256:" + "1" * 64, "sha256:" + "2" * 64
    return [(a, f"k{i:02d}", f"run-{i}", "1", "call") for i in range(n_first)] + [
        (b, f"m{i:02d}", f"other-{i}", "2", "answer") for i in range(n_second)
    ]


def test_steps_are_grouped_by_digest_with_counts_and_links(examined):
    drawn = T.wanted_section(T.grouped(_entries(2, 1)), example=frozenset(), decodes=True)
    groups = re.findall(r'<div data-tokenizer-wanted="(sha256:[0-9a-f]{64})"', drawn)
    examined(len(groups), "digests asked for")
    assert len(groups) == 2
    assert drawn.count('href="/runs/k00/stage-1.html"') == 1 and drawn.count('href="/runs/m00/stage-2.html"') == 1
    assert "2 model steps" in drawn and "1 model step" in drawn
    assert T.LEAD in unescape(drawn)


def test_the_list_is_bounded_at_20_per_digest(examined):
    drawn = T.wanted_section(T.grouped(_entries(25, 0)), example=frozenset(), decodes=True)
    examined(1, "a digest asked for by 25 steps")
    assert drawn.count('href="/runs/k') == 20 and "and 5 more" in drawn


def test_with_no_step_asking_the_page_says_so(examined):
    examined(1, "an empty list")
    assert T.NO_STEP in unescape(T.wanted_section({}, example=frozenset(), decodes=True))


def test_the_demo_s_constructed_digest_is_said_and_offers_no_picker(examined):
    from onetrace_console import model_call
    from onetrace_console.demo_store import model_call_example as mce
    from onetrace_console.frame import rendering

    record = mce.self_hosted()
    digest = record["tokenizer.digest"]["value"]
    drawn = T.wanted_section(
        T.grouped([(digest, "k", "pz-51-agent-baseline", "1", "agent_step")]), example=T.example_digests(), decodes=True
    )
    with rendering(onedoor=False, sign_in=False, public=False, tokenizers=(("/nowhere", ("tokenizer.json",)),)):
        _dec, step = model_call._as_text(record)
    examined(2, "the page's entry and the step")
    assert digest in T.example_digests()
    assert T.EXAMPLE in unescape(drawn) and T.EXAMPLE in unescape(step)
    assert "data-tokenizer-post" not in step


def test_with_no_tokenizers_package_both_say_so_and_offer_no_picker(monkeypatch, examined):
    from onetrace_console import model_call
    from onetrace_console.frame import rendering

    monkeypatch.setattr(T, "can_decode", lambda: False)
    record = {"tokenizer.digest": {"status": "declared", "value": "sha256:" + "3" * 64, "source": "test"}}
    drawn = T.wanted_section(T.grouped(_entries(1, 0)), example=frozenset(), decodes=False)
    with rendering(onedoor=False, sign_in=False, public=False, tokenizers=(("/nowhere", ("tokenizer.json",)),)):
        _dec, step = model_call._as_text(record)
    examined(2, "the page and the step")
    assert T.MISSING_PACKAGE in unescape(drawn) and T.MISSING_PACKAGE in unescape(step)
    assert "pip install tokenizers" in unescape(drawn)
    assert "data-tokenizer-post" not in step


def test_the_page_from_a_store_lists_its_steps_and_the_kept_ones_follow(shared_demo, tmp_path, examined):
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    with store.reading():
        page = T.page_body(store, tmp_path / "kept-here", named=())
    examined(1, "the demo's Tokenizers page")
    assert 'data-section="tokenizers-wanted"' in page and T.EXAMPLE in unescape(page)
    assert 'data-section="tokenizers"' in page and T.SETTINGS_NONE in unescape(page)


def test_a_digest_the_record_declares_is_read_as_onetrace_writes_it(examined):
    """onetrace writes a declared value's status as `DECLARED` ("declared, not observed"): the record's
    tokenizer.digest is read where observed or declared, as onetrace says each."""
    from onetrace.model_call.record import DECLARED, OBSERVED

    from onetrace_console import token_text

    digest = "sha256:" + "4" * 64
    examined(3, "statuses")
    for status in (OBSERVED, DECLARED):
        assert token_text.recorded_digest({"tokenizer.digest": {"status": status, "value": digest}}) == digest
    assert token_text.recorded_digest({"tokenizer.digest": {"status": "not observed"}}) is None
