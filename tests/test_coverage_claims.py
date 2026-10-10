"""No text a reader gets claims more than `onetrace-verify` 0.1.2 checks.

0.1.2 checks each receipt's format and fields, its canonical bytes, its digest against the
manifest, the chain's links and head, and each output file against its digest **when the run
carries `artifacts/`**. It runs **no stage-order check**, no topology check ships, and it
confirms nothing of a receipt's own coverage statement. So a sentence that names one of the
claims below must, in the same sentence, say it is not checked or say it is the receipts' own
account. The claims, and what may qualify each:

    stage order            -- 0.1.2 runs no stage-order check
    topology               -- no topology check ships in the pinned release
    completeness           -- the receipts state it; no check confirms it
    every step/check/...   -- a claim of universal coverage
    nothing is missing     -- the receipts' own account at most
    consistency            -- a receipt misstating its stage order still passes 0.1.2
    proof of time          -- "existed by", "hasn't changed since", "independent anchor": 0.1.2
                              checks only that an anchor is declared (10-01cc §1)
    fully checked/verified -- a claim of universal coverage

**What is read:** every page the console draws for real runs through the pinned verifier -- one
without `artifacts/`, a pair it compares, and a forged run it stores as contradicts -- with the
verifier's and the records' own words (in `<pre>` layers and quotations marked `data-words`) left
out, as they are quoted, not said; every sentence in the vendored viewer's table; and every
shipped document, paragraph by paragraph.

**Documents, since the pin moved to 0.2.0** (`requirements.lock`): its `onetrace-verify` runs the
stage-order check (`verify.py`, `check_stage_order`), and checks anchors, with the `[crypto]`
packages the lock pins for an anchor's proof (the SDK's CHANGELOG, 0.2.0). So the shipped
documents are read against what 0.2.0 checks: a stage-order or proof-of-time sentence there is no
longer a claim beyond the verifier. Every other claim is read as before. The drawn pages and the
viewer's table keep the 0.1.2 list until the viewer's sentences are rewritten for 0.2.0.

**Its limit, plainly:** it catches the listed phrasings, and only in pages the runs above draw, in
the viewer's table, and in the documents. A claim worded some other way, or on a page state those
runs do not reach, is outside it. The list of every coverage sentence, before and after, is in the
pin report for the reviewer to read.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from tests.conftest import make_tar
from tests.test_diff_sdk_text_layer import _forged_pair, _tar
from tests.test_serve import _post
try:
    from tools.export_public import NEVER
except ImportError:   # the public tree has no export tool, and its never-ship files are already absent
    NEVER = ()

REPO = Path(__file__).resolve().parent.parent

CLAIMS = {
    "stage order": re.compile(r"stage[\s_-]*order", re.I),
    #: A claim to check it, not the word: `topology_note` is a field's name.
    "topology": re.compile(r"\btopology check", re.I),
    "completeness": re.compile(r"\bcompleteness\b|\b(?:is|are|was|were) complete\b", re.I),
    #: Universal coverage: "every step" and a word of checking in the same sentence. "Every stage
    #: after it changes too" describes a pipeline, and is not a claim about a check.
    "every step/check/receipt/stage/record": re.compile(
        r"\bevery (?:step|check|receipt|stage|record)s?\b[^.;]{0,60}?"
        r"\b(?:checks? out|holds?|held|checked|verified|pass(?:es|ed)?)\b", re.I),
    "nothing is missing": re.compile(r"\bnothing (?:is |was )?missing\b", re.I),
    #: 0.1.2 passes a receipt that misstates its stage order, so "consistent with itself" and
    #: "checked for consistency" say more than it checks (30bv §3.5 reworded both).
    "consistency": re.compile(r"\bconsistent with itself\b|\bchecked for consistency\b", re.I),
    #: Proof of time. 0.1.2 checks only that an anchor state is declared, and
    #: this console checks no anchor.
    "proof of time": re.compile(r"\bexisted by\b|\bhasn't changed since\b|\bindependent anchor\b",
                                re.I),
    "fully checked/verified": re.compile(
        r"\bfully (?:checked|verified)\b|\b(?:checked|verified) (?:in full|completely)\b", re.I),
}
QUALIFIED = re.compile(
    r"\b(?:not|no|never|cannot|can't|isn't|doesn't|didn't|none|nor)\b"
    r"|\bas the receipts\b|\bthe receipts themselves\b|\breceipts' own\b|\bdeclare[sd]?\b"
    r"|\bwill ship\b", re.I)

#: A conditional: what something WOULD show, not what this record has. It qualifies the proof-of-time
#: claim of its sentence only -- the fixed "Anchored, it would read: this record existed by ..." (015).
WHOLE_SENTENCE_QUALIFIED = re.compile(r"\bit would read:", re.I)


#: The run receipt's "What this receipt does not say" is the work order's fixed
#: list of what the receipt does NOT claim, and one line says what an anchor would show ("the record
#: existed by then") in order to deny more. Under that heading the proof-of-time claim is qualified,
#: and only that one: every other claim is still read there.
NOT_SAID = re.compile(r'<section data-section="does-not-say">.*?</section>', re.S)


#: The viewer's fixed sentences for a verified anchor PASS, allowed by name -- their proof-of-time
#: claim only, every other claim still read. Rewriting this list to what 0.2.0 checks waits for
#: the RC repin.
RULED_PROOF_OF_TIME = {
    "rung.anchored.yes": "the anchored rung's sentence for a verified anchor",
    "answer.anchor.yes": "the answer view's anchor sentence for a verified anchor",
    "badge.anchored.yes": "the anchored badge's sentence for a verified anchor",
}


#: The claims 0.2.0's `onetrace-verify` checks that 0.1.2 did not, so a document may make them.
CHECKED_BY_0_2_0 = ("stage order", "proof of time")


def _table_hits(key: str, text: str) -> list[str]:
    """What the guard finds in one sentence of the viewer's table, under its key."""
    hits = _unqualified(key, _sentences(text))
    if key in RULED_PROOF_OF_TIME:
        hits = [h for h in hits if not h.startswith(f"{key}: [proof of time]")]
    return hits


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.;!?])\s+", " ".join(text.split())) if s]


#: How close a qualifier must stand to the claim it qualifies. Anywhere in the sentence was too
#: loose: "the topology check as shipped, called with paths, with no verdict logic" read as
#: qualified by a "no" that is about something else.
NEAR = 30


def _unqualified(where: str, sentences: list[str], not_said: bool = False,
                 checked: tuple[str, ...] = ()) -> list[str]:
    out = []
    for s in sentences:
        #: "it would read:" qualifies the proof-of-time claim of its sentence and nothing else
        #: (the pin re-check, note 3): the fixed anchoring.would_add is a hypothetical. So does the
        #: receipt's "does not say" list (`NOT_SAID`).
        hypothetical = not_said or bool(WHOLE_SENTENCE_QUALIFIED.search(s))
        for claim, pattern in CLAIMS.items():
            if hypothetical and claim == "proof of time" or claim in checked:
                continue
            for m in pattern.finditer(s):
                if not QUALIFIED.search(s[max(0, m.start() - NEAR):m.end() + NEAR]):
                    out.append(f"{where}: [{claim}] {s[:200]}")
    return out


def _page_words(html: str) -> str:
    """A page's own words: its `<pre>` layers and marked quotations left out."""
    from tests.viewer.pagetext import own_words
    return own_words(re.sub(r"<pre\b.*?</pre>", " ", html, flags=re.S))


def _drawn_pages(server, files, tmp_path) -> dict[str, str]:
    base, root = server
    assert _post(base, "/v1/runs", make_tar(files))[0] == 200
    (tmp_path / "held").mkdir()
    (tmp_path / "forged").mkdir()
    a, b = _forged_pair(tmp_path / "held")
    keys = []
    for delivery in (a, b):
        status, body = _post(base, "/v1/runs", _tar(delivery))
        assert status == 200, body[:200]
        keys.append(json.loads(body)["run_key"])
    status, body = _post(base, f"/compare?a={keys[0]}&b={keys[1]}")
    assert status == 200, body[:200]
    _, forged = _forged_pair(tmp_path / "forged", artifacts=True)
    status, body = _post(base, "/v1/runs", _tar(forged))
    assert json.loads(body)["check_verdict"] == "contradicts"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((root / "pages").rglob("*.html"))}


def _documents() -> dict[str, str]:
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    return {rel: (REPO / rel).read_text(encoding="utf-8", errors="replace") for rel in tracked
            if rel.endswith(".md") and not rel.startswith(("tests/", *NEVER))}


def test_no_page_the_console_draws_claims_more_than_0_1_2_checks(server, files, tmp_path,
                                                                  examined):
    pages = _drawn_pages(server, files, tmp_path)
    examined(len(pages), "pages drawn and read")
    kinds = {p.split("/")[1].split("-")[0] if "/" in p[6:] else p for p in pages}
    assert any("diff/" in p for p in pages) and any("incidents-" in p for p in pages), kinds
    assert any(p.startswith("pages/runs/") and p.endswith("case.html") for p in pages), kinds
    assert any(NOT_SAID.search(html) for html in pages.values()), "no receipt page was read"
    bad = [hit for rel, html in pages.items()
           for hit in _unqualified(rel, _sentences(_page_words(NOT_SAID.sub(" ", html))))
           + [h for said in NOT_SAID.findall(html)
              for h in _unqualified(rel, _sentences(_page_words(said)), not_said=True)]]
    assert not bad, "a page claims more than 0.1.2 checks:\n" + "\n".join(bad)


def test_the_receipt_s_does_not_say_list_qualifies_only_the_proof_of_time_claim(examined):
    """Under "What this receipt does not say", "existed by" is what the receipt denies; any other
    claim there is still caught, and "existed by" anywhere else on the page is too."""
    examined(3, "sentences checked")
    from onetrace_console.receipt_page import DOES_NOT_SAY
    listed = " ".join(DOES_NOT_SAY)
    assert "existed by" in listed
    assert _unqualified("receipt", _sentences(listed), not_said=True) == []
    caught = _unqualified("receipt", _sentences(listed + " Every step checks out."), not_said=True)
    assert any("[every step" in c for c in caught), caught
    assert any("[proof of time]" in c for c in _unqualified("receipt", _sentences(listed)))


def test_no_sentence_in_the_viewer_s_table_claims_more_than_0_1_2_checks(examined):
    from onetrace_console.viewer import sentences as S
    keys = (set(S.TABLE) | set(S.FIXED) | set(S.RULED) | set(S.PROVISIONAL) | set(S.LABELS)
            | set(S.REWORDED))
    examined(len(keys), "sentences in the viewer's table")
    bad = [hit for key in sorted(keys) for hit in _table_hits(key, S.template(key))]
    assert not bad, "a sentence claims more than 0.1.2 checks:\n" + "\n".join(bad)


def test_the_allowance_is_by_name_and_for_proof_of_time_only():
    """"existed by" in any other key is still caught, and an allowed key's other
    claims are still read."""
    from onetrace_console.viewer import sentences as S
    for key in RULED_PROOF_OF_TIME:
        sentence = S.template(key)
        assert "existed by" in sentence, key
        assert _unqualified(key, _sentences(sentence)), f"the premise: the guard reads {key}"
        assert not _table_hits(key, sentence), key
        assert any("[proof of time]" in h for h in _table_hits("rung.other", sentence)), key
        assert any("[every step" in h for h in _table_hits(key, sentence + " Every step checks out.")), key


def test_no_shipped_document_claims_more_than_0_2_0_checks(examined):
    docs = _documents()
    examined(len(docs), "shipped documents")
    bad = []
    for rel, text in docs.items():
        for para in text.replace("\r\n", "\n").split("\n\n"):
            bad += _unqualified(rel, _sentences(para), checked=CHECKED_BY_0_2_0)
    assert not bad, "a document claims more than 0.2.0 checks:\n" + "\n".join(bad)


def test_only_what_0_2_0_checks_is_allowed_in_a_document():
    """The allowance is the two claims 0.2.0 checks, and nothing beside them: in one sentence, a
    stage-order and a proof-of-time claim pass, while every other claim is still caught."""
    allowed = "The verifier checks stage order, and the anchor shows the record existed by then."
    assert _unqualified("doc", _sentences(allowed), checked=CHECKED_BY_0_2_0) == []
    assert _unqualified("doc", _sentences(allowed)), "the premise: 0.1.2's list reads both"
    for claim in ("Every step checks out.", "Nothing is missing.", "The run is fully verified.",
                  "The topology check ran.", "Its completeness is shown.", "It is consistent with itself."):
        assert _unqualified("doc", _sentences(claim), checked=CHECKED_BY_0_2_0), claim


def test_the_operator_readme_says_what_0_1_2_does_not_check(examined):
    """The two non-claims 30bv §3.5 adds beside the stage-order one: output files are checked
    only when a run carries them, and a receipt's coverage is its own account."""
    text = " ".join((REPO / "OPERATOR_README.md").read_text(encoding="utf-8").split())
    examined(2, "non-claims read")
    assert "**Output files are checked only when a run carries them.**" in text
    assert "`--require-artifacts`" in text and "output files not checked" in text
    assert "**What a receipt says of its own coverage is its own account.**" in text
    assert "no check confirms it" in text


def test_it_would_read_qualifies_only_the_proof_of_time_claim(examined):
    """The pin re-check's note 3: "it would read:" excused every claim in its sentence. It now
    qualifies only the proof-of-time claim it was added for (the fixed anchoring.would_add)."""
    from onetrace_console.viewer import sentences as S
    examined(2, "sentences checked")
    assert _unqualified("would_add", _sentences(S.template("anchoring.would_add"))) == []
    caught = _unqualified("made up", _sentences(
        "Every step checks out, and it would read: nothing is missing."))
    assert any("[every step" in c for c in caught) and any("[nothing is missing]" in c
                                                           for c in caught), caught
