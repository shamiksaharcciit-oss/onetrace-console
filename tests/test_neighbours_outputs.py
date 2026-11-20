"""Neighbours by output: on a comparison, beside the runs with near inputs, the runs of run A's configuration whose
kept output at the step of the first difference is nearest to run A's, by the same embedder as near inputs. Only a
kept output whose bytes match its receipt's digest is read; a run whose output there is not kept, or whose kept bytes
do not match, is left out and counted. Like near inputs, it exists only on a local console with the extra installed.

The store is `test_neighbours`'s: P7's cold-chain baseline and the run with one reading changed, one configuration,
with the stand-in embedder (a bag of words). The near and the far output, the output not kept and the one whose bytes
do not match its digest are each a part of a run of the group, given to `nearness.near_outputs` as `kept.parts` would.
"""

from __future__ import annotations

import hashlib
import re
from types import SimpleNamespace

import pytest

from tests.test_neighbours import (  # noqa: F401 - fixtures, requested by name
    NAMES,
    _absent,
    _comparison,
    _diff,
    bag_of_words,
    held,
    needs_extra,
    on,
    recorded,
)

BASE, CHANGED = "p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed"
SECTION = re.compile(r'<section class="near-runs" data-section="near-outputs".*?</section>', re.S)


def _part(step: str, name: str, text: str | None, held_as: str):
    from onetrace_console.neighbours import kept

    data = text.encode() if text is not None else None
    digest = "sha256:" + hashlib.sha256(data or held_as.encode()).hexdigest()
    return kept.Part(step, "3", kept.OUTPUT, name, digest, text, data, "", held_as)


def _vector(text: str) -> str:
    import numpy as np

    from onetrace_console.neighbours.batches import encode

    v = np.array(bag_of_words("", {"model": "m", "input": [text]})["data"][0]["embedding"], dtype=np.float32)
    return encode(v / np.linalg.norm(v))


@pytest.fixture
def group(monkeypatch):
    """Run A and four runs of its configuration: one whose output at `reply` is near, one far, one not kept, and one
    whose kept bytes don't match their digest."""
    from onetrace_console import neighbours
    from onetrace_console.neighbours import batches, grouping, kept

    A, NEAR, FAR, NOT_KEPT, MISMATCH = (SimpleNamespace(key=k) for k in ("a", "near", "far", "not-kept", "mismatch"))
    texts = {
        "a": "the parcel arrives on monday morning",
        "near": "the parcel arrives on tuesday morning",
        "far": "invoice forty euros paid to the vendor",
    }
    parts = {k: [_part("reply", "answer.json", t, kept.KEPT)] for k, t in texts.items()}
    parts["not-kept"] = [_part("reply", "answer.json", None, kept.ABSENT)]
    parts["mismatch"] = [_part("reply", "answer.json", None, kept.MISMATCH)]
    runs = {r.key: r for r in (A, NEAR, FAR, NOT_KEPT, MISMATCH)}
    vectors = {p.digest: _vector(p.text) for ps in parts.values() for p in ps if p.text is not None}
    monkeypatch.setattr(neighbours, "active", lambda store: True)
    monkeypatch.setattr(batches, "current", lambda store: ("an embedder", vectors))
    monkeypatch.setattr(kept, "parts", lambda run, store: parts[run.key])
    monkeypatch.setattr(grouping, "signatures", lambda store: dict.fromkeys(runs, "one configuration"))
    monkeypatch.setattr(grouping, "group_of", lambda store, key: [k for k in runs if k != key])
    return A, SimpleNamespace(get_run=runs.get), runs


@needs_extra
def test_the_near_output_is_first_the_far_one_after_and_the_two_left_out_are_counted(group, examined):
    from onetrace_console.neighbours.nearness import BY_EMBEDDER, near_outputs

    a, store, runs = group
    got = near_outputs(a, store, "reply")
    assert [r.other.key for r in got.rows] == ["near", "far"]
    assert got.rows[0].near.value > got.rows[1].near.value and got.rows[0].near.how == BY_EMBEDDER
    assert (got.not_kept, got.mismatched, got.mine) == (1, 1, True)
    assert {r.name for r in got.rows} == {"answer.json"} and {r.step for r in got.rows} == {"reply"}
    examined(len(runs) - 1, "runs of the configuration")


@needs_extra
def test_where_run_a_did_not_keep_its_output_no_run_is_placed_by_it(group, monkeypatch, examined):
    from onetrace_console.neighbours import kept
    from onetrace_console.neighbours.nearness import near_outputs

    a, store, _runs = group
    real = kept.parts
    monkeypatch.setattr(kept, "parts", lambda run, s: [] if run.key == "a" else real(run, s))
    got = near_outputs(a, store, "reply")
    assert (got.mine, got.rows) == (False, [])
    examined(1, "run")


@needs_extra
def test_without_neighbours_on_there_is_nothing(group, monkeypatch, examined):
    from onetrace_console import neighbours
    from onetrace_console.neighbours.nearness import near_outputs

    a, store, _runs = group
    monkeypatch.setattr(neighbours, "active", lambda store: False)
    assert near_outputs(a, store, "reply") is None
    examined(1, "run")


@needs_extra
def test_a_kept_output_whose_bytes_do_not_match_its_digest_is_not_read(on, monkeypatch, examined):
    from onetrace_console import stage_pages
    from onetrace_console.neighbours import kept

    store, runs = on
    run = runs[CHANGED]
    good = [p for p in kept.parts(run, store) if p.kind == kept.OUTPUT and p.text is not None]
    assert good and all(p.held == kept.KEPT for p in good)
    real = stage_pages._read

    def read(files, s, path):
        #: Each stored output read back as other bytes than its receipt's digest names.
        got = real(files, s, path)
        return b'"not what the record says"' if got is not None and path.startswith("artifacts/") else got

    monkeypatch.setattr(stage_pages, "_read", read)
    tampered = [p for p in kept.parts(run, store) if p.kind == kept.OUTPUT]
    assert all(p.text is None and p.data is None for p in tampered)
    assert {p.held for p in tampered} == {kept.MISMATCH}
    examined(len(tampered), "outputs")


@needs_extra
def test_the_comparison_shows_near_outputs_beside_near_inputs_with_the_same_words(on, examined):
    from onetrace_console import compare_view

    store, runs = on
    page = _diff(_comparison(store, runs[BASE], runs[CHANGED]), store)
    from html import unescape

    [section] = [unescape(x) for x in SECTION.findall(page)]
    assert compare_view.NEAR_OUT_HEADING in section
    assert compare_view.NEAR_NOTE.split(" · ")[-1] in section and "same configuration" in section
    assert f'data-near-run="{runs[CHANGED].key}"' in section
    assert re.search(r'<strong><span data-nearness="(?:embedder|record)"', section)
    assert 'data-near-out="left-out"' in section
    #: Beside near inputs: the two sections follow one another.
    assert page.index('data-section="near-outputs"') > page.index("compare-tabs")
    examined(1, "comparison page")


@needs_extra
def test_with_the_extra_absent_the_comparison_has_no_word_of_near_outputs(on, monkeypatch, examined):
    store, runs = on
    _absent(monkeypatch)
    page = _diff(_comparison(store, runs[BASE], runs[CHANGED]), store)
    assert "near-outputs" not in page and "Runs with near outputs" not in page and not NAMES.search(page)
    examined(1, "comparison page")


@needs_extra
def test_a_public_drawing_and_a_static_export_have_no_near_outputs(on, examined):
    from onetrace_console.export_static import without_run_tools
    from onetrace_console.frame import rendering

    store, runs = on
    c = _comparison(store, runs[BASE], runs[CHANGED])
    with rendering(onedoor=False, sign_in=False, public=True):
        assert "near-outputs" not in _diff(c, store)
    assert "near-outputs" not in without_run_tools(_diff(c, store))
    examined(2, "drawings")


@needs_extra
def test_a_near_output_s_quote_of_compact_json_wraps_on_a_narrow_screen(group, monkeypatch, examined):
    """A kept output is often compact JSON, one word as long as the output: its quote breaks anywhere, so a 375 px
    screen does not scroll sideways."""
    from onetrace_console import compare_view

    a, store, _runs = group
    monkeypatch.setattr(compare_view, "_near_quote", lambda *args, **kw: '{"readings":[{"filled":false,"minute":"0"}]}')
    monkeypatch.setattr("onetrace_console.what_changed.held", lambda *args: None)
    monkeypatch.setattr("onetrace_console.words.run_named", lambda store, key: key)
    from onetrace_console.neighbours.nearness import near_outputs

    card = compare_view._near_card(store, a, near_outputs(a, store, "reply").rows[0], "outputs")
    assert "<q>" in card
    rule = re.search(r"\.cp \.near-runs li q\{([^}]*)\}", compare_view.COMPARE_PAGE_CSS).group(1)
    assert "overflow-wrap:anywhere" in rule, rule
    examined(1, "card")
