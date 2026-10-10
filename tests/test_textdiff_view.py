"""The text diff, as the SDK wrote it (`onetrace-textdiff/0.3`).

A strict reader, a renderer that escapes once and draws only verified outputs, and the SDK's own
golden warranty pair. Where a stored comparison's text diff comes from, "Show more" and the
corpus trace are tests/test_textdiff_more.py's.

The documents here are the SDK's own: `python -m onetrace diff A B --text --json --no-follow` run
over the warranty pair from the hash-checked development sdist (`tools/fetch_sdk_fixtures.py`).
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.textdiff_view import FORMAT, TextDiffUnreadable, read_textdiff, render_textdiff
from tools.fetch_sdk_fixtures import WARRANTY, check as fixtures_ready

RUNS = WARRANTY / "runs"


def _require_warranty():
    if not fixtures_ready():
        pytest.fail("the SDK's fixtures are not there or do not match:\n"
                    "    python tools/fetch_sdk_fixtures.py")


def _sdk_textdiff(baseline: Path, candidate: Path) -> str:
    """The SDK's own document for the pair, as `onetrace diff --text --json` prints it. `--out`
    goes to a temporary folder: without it the SDK writes `onetrace-report/` where it runs, which
    is this repository."""
    import tempfile
    with tempfile.TemporaryDirectory(prefix="onetrace-textdiff-") as out:
        proc = subprocess.run([sys.executable, "-m", "onetrace", "diff", str(baseline),
                               str(candidate), "--text", "--json", "--no-follow", "--out", out],
                              capture_output=True, text=True)
    assert proc.stdout.strip(), proc.stderr[-600:]
    return proc.stdout


@pytest.fixture
def golden() -> dict:
    _require_warranty()
    return read_textdiff(_sdk_textdiff(RUNS / "query-v1", RUNS / "query-v2"))


def _node(html: str, node: str) -> str:
    found = re.search(rf'<article data-node="{node}">(.*?)</article>', html, re.S)
    assert found, f"no node {node}"
    return found.group(1)


# ------------------------------------------------------------------ the golden: twelve -> six

def test_the_golden_warranty_pair_renders_twelve_to_six(golden, examined):
    html = render_textdiff(golden)
    examined(len(golden["nodes"]), "nodes drawn")
    assert golden["format"] == FORMAT and golden["shown"] is True
    assert [n["node"] for n in golden["nodes"]] == ["retrieve", "prompt", "answer"]
    answer = _node(html, "answer")
    assert '<mark class="del">twelve</mark>' in answer and '<mark class="ins">six</mark>' in answer
    assert "answer · downstream" in unescape(answer)
    #: Each output shown carries the badge, and every one of the three is verified.
    assert html.count('data-badge="verified"') == 3
    assert unescape(re.search(r"<p data-first-line>(.*?)</p>", html).group(1)) == golden["first_line"]


def test_the_retrieve_node_shows_its_hits_and_the_input_with_no_content(golden):
    retrieve = unescape(_node(render_textdiff(golden), "retrieve"))
    assert "settings: none changed" in retrieve
    assert "content not stored" in retrieve, "an input's content is never shown (fingerprinted)"
    assert "The warranty covers [-twelve-]{+six+} months from the date of purchase." in retrieve


def test_text_is_shown_as_the_sdk_escaped_it_once(golden):
    """The prompt's text holds the SDK's own escapes (`\\n` inside a JSON string): drawn as given,
    HTML-escaped once, never doubled."""
    prompt = _node(render_textdiff(golden), "prompt")
    raw = next(line["text"] for out in golden["nodes"][1]["outputs"] for h in out["hunks"]
               for line in h["lines"] if line["op"] == "-")
    assert "\\n" in raw
    assert "\\n" in unescape(prompt) and "\\\\n" not in unescape(prompt)


# ------------------------------------------------------------------ never an unverified output

def test_a_tampered_artifact_shows_not_shown_never_its_text(tmp_path, examined):
    """ed5: "a tampered artifact shows 'not shown', never text"."""
    _require_warranty()
    tampered = tmp_path / "query-v2"
    shutil.copytree(RUNS / "query-v2", tampered)
    (tampered / "artifacts" / "03-answer" / "return.json").write_bytes(
        b'"The warranty covers sixty months.\\n"')
    doc = read_textdiff(_sdk_textdiff(RUNS / "query-v1", tampered))
    html = render_textdiff(doc)
    examined(1, "tampered pair drawn")
    assert "sixty" not in html
    said = [o["reason"] for n in doc.get("nodes", []) for o in n["outputs"] if not o["verified"]]
    said += [doc["reason"]] if not doc["shown"] else []
    assert said, "the SDK said nothing of the tampered output"
    for reason in said:
        assert reason in unescape(html), reason


def test_outputs_the_sdk_could_not_verify_show_its_reason_never_text(tmp_path, examined):
    """The per-output path, from the SDK itself: a candidate delivered without its artifacts/
    still verifies, and the SDK marks each output not verified ("not shown: ... is missing").
    (An altered output fails the run's check, and the SDK refuses the pair whole -- above.)"""
    _require_warranty()
    bare = tmp_path / "query-v2"
    shutil.copytree(RUNS / "query-v2", bare)
    shutil.rmtree(bare / "artifacts")
    doc = read_textdiff(_sdk_textdiff(RUNS / "query-v1", bare))
    html = render_textdiff(doc)
    outs = [o for n in doc["nodes"] for o in n["outputs"]]
    examined(len(outs), "outputs the SDK could not verify")
    assert outs and not any(o["verified"] for o in outs)
    assert 'data-badge="verified"' not in html and "six" not in html and "<mark" not in html
    for out in outs:
        assert out["reason"] in unescape(html), out["reason"]


def test_an_unverified_output_is_never_drawn_even_handed_lines(golden):
    """The renderer's own guard, behind the reader's: an output not marked verified gets its reason
    and nothing else -- no lines, no notes, no badge -- whatever it carries."""
    doc = copy.deepcopy(golden)
    out = doc["nodes"][2]["outputs"][0]
    out["verified"] = False
    out["reason"] = "not shown: return.json does not match its receipt"
    html = _node(render_textdiff(doc), "answer")
    assert "twelve" not in html and "six" not in html
    assert 'data-badge="verified"' not in html
    assert "not shown: return.json does not match its receipt" in unescape(html)


# ------------------------------------------------------------------ the reader, strictly

def _refused(doc, match: str) -> None:
    with pytest.raises(TextDiffUnreadable, match=match):
        read_textdiff(json.dumps(doc))


def test_another_format_is_refused(golden):
    _refused(dict(golden, format="onetrace-textdiff/0.2"), "format")


def test_a_field_the_console_has_not_been_taught_is_refused(golden):
    _refused(dict(golden, colour="red"), "not been taught")
    doc = copy.deepcopy(golden)
    doc["nodes"][0]["outputs"][0]["excerpt"] = "x"
    _refused(doc, "not been taught")


def test_an_unverified_output_carrying_lines_is_refused(golden):
    doc = copy.deepcopy(golden)
    out = doc["nodes"][2]["outputs"][0]
    out["verified"], out["reason"] = False, "not shown: x"
    _refused(doc, "not verified and carries lines")


def test_a_span_outside_its_text_is_refused(golden):
    doc = copy.deepcopy(golden)
    line = doc["nodes"][2]["outputs"][0]["hunks"][0]["lines"][0]
    line["spans"] = [["0", str(len(line["text"]) + 1)]]
    _refused(doc, "span outside its text")


def test_a_raw_control_character_in_shown_text_is_refused(golden):
    doc = copy.deepcopy(golden)
    doc["nodes"][2]["outputs"][0]["hunks"][0]["lines"][0]["text"] = "a\rforged"
    _refused(doc, "left unescaped")


def test_an_exit_that_disagrees_with_the_envelope_is_refused(golden):
    _refused(dict(golden, exit="0"), "disagrees with its envelope")
