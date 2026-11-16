"""The committed token-level fixture runs (`tests/token_level_runs_071/`, made by `tools/make_token_level_runs.py`):
six pairs whose one step writes a `model-call-record/1.1` record with its steps file, example data constructed through
onetrace 0.7.1's own writer. Each run verifies; each pair's comparison page reads as its construction says; each run
says it is example data, constructed, in its run and on its step's page; and the folder is outside tests/fixtures/,
which the earlier-format readers read.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FOLDER = REPO / "tests" / "token_level_runs_071"
GENERATED_AT = "2026-11-09T12:00:00+00:00"
#: Each pair, and the words its comparison page says at the first difference.
READS = {
    "l3-invariant-on": [
        "The logits row changed at token 2; the chosen token first changed at token 4.",
        "batch-invariant mode on",
    ],
    "l3-invariant-off": [
        "The logits row changed at token 2; the chosen token first changed at token 4.",
        "With batch-invariant mode not on, a changed digest can come from how requests were batched, "
        "not from the model.",
    ],
    "l2-ids": [
        "At token 2, the first token whose choice differs:",
        "the candidate's token 9001 was the baseline's 2nd candidate",
    ],
    "hosted-l2-text": [
        "the candidate's token “yes” was the baseline's 2nd candidate",
        "model-generated, as the provider returned it",
    ],
    "mixed-levels": ["Not comparable: the capture levels differ: L2 and L3; no rank is shown."],
    "differing-k": ["Not comparable: k differs: 4 and 2; no rank is shown."],
}


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console import records
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    store = Store(tmp_path_factory.mktemp("token-level-fixtures") / "store")
    out = {}
    for pair in READS:
        ra, rb = (
            run_and_record(_deliver(FOLDER / pair / side, store, outputs=True), store, ran_at=FIXED_RAN_AT)
            for side in ("a", "b")
        )
        c = compare(ra, rb, store, ran_at=FIXED_RAN_AT)
        with rendering(onedoor=False, sign_in=False, public=False):
            page = render_diff(c, store, generated_at=GENERATED_AT)
            stage = next(
                v
                for k, v in render_execution(ra, store, generated_at=GENERATED_AT).pages.items()
                if k.startswith("stage-")
            )
        out[pair] = {"page": page, "stage": stage, "verified": (records.state(ra, store), records.state(rb, store))}
    return out


def test_the_folder_holds_the_six_pairs_the_tool_names(examined):
    import importlib.util

    from tests.export_tree import tool

    #: A public export leaves the tool out: there the test skips; here a missing one fails.
    spec = importlib.util.spec_from_file_location("make_token_level_runs", tool("make_token_level_runs.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    PAIRS = module.PAIRS
    found = sorted(p.name for p in FOLDER.iterdir() if p.is_dir())
    examined(len(found), "pairs")
    assert found == sorted(PAIRS) == sorted(READS)
    assert all((FOLDER / p / s / "MANIFEST.json").is_file() for p in found for s in ("a", "b"))


@pytest.mark.parametrize("pair", sorted(READS))
def test_each_pair_verifies_and_reads_as_constructed(built, pair, examined):
    from onetrace_console import records

    got = built[pair]
    examined(len(READS[pair]) + 2, f"the pair {pair}: its two checks and its words")
    assert got["verified"] == (records.YES, records.YES)
    said = _text(got["page"])
    for words in READS[pair]:
        assert words in said, words


@pytest.mark.parametrize("pair", sorted(READS))
def test_each_run_says_it_is_example_data_constructed(built, pair, examined):
    import json

    examined(2, f"the pair {pair}'s runs")
    for side in ("a", "b"):
        (record,) = (FOLDER / pair / side / "artifacts").rglob("model_call.json")
        fields = json.loads(record.read_text(encoding="utf-8"))
        #: Every field that states a value says so; `steps`'s source is the steps file's name, as the format has it.
        sources = [v["source"] for k, v in fields.items() if isinstance(v, dict) and "value" in v and k != "steps"]
        assert sources and all("example data, constructed" in s for s in sources), pair
    assert "example data, constructed; no model was called" in _text(built[pair]["stage"])


def test_the_folder_is_outside_what_the_earlier_format_readers_read(examined):
    examined(1, "the folder")
    assert not FOLDER.is_relative_to(REPO / "tests" / "fixtures")
