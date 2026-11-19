"""The operator guide says what `audit verify` does not catch without `--heads`, and the log holds to it.

Without `--heads`, the check reads the log against its own `HEAD.json`, beside it on the store's volume: entries cut
off the end with `HEAD.json` rewritten to agree pass. Only the heads on the second volume catch it. The guide said
`--heads` exists, not that without it this edit passes. Held here both ways: the guide's words, and the log itself
(an edit, a cut tail, the same cut with `HEAD.json` rewritten, then read with the heads).
"""

from __future__ import annotations

from pathlib import Path

from tests.test_audit_log import _failed, _fill, _rewrite_head, _segments, _verify, log, second  # noqa: F401

GUIDE = Path(__file__).resolve().parent.parent / "OPERATOR_README.md"


def test_the_guide_says_a_cut_tail_with_head_rewritten_passes_without_heads(examined):
    text = " ".join(GUIDE.read_text(encoding="utf-8").split())
    examined(1, "the guide's audit section")
    assert (
        "Without `--heads`, `audit verify` reads the log against its own `HEAD.json`, which lies beside it on the "
        "store's volume: entries cut off the end, with `HEAD.json` rewritten to agree, pass."
    ) in text
    assert "Only the heads on the second volume catch that" in text


def test_the_log_holds_to_what_the_guide_says(log, second, examined):  # noqa: F811
    _fill(log, 12)
    assert not _failed(_verify(log.root))
    last = _segments(log)[-1]
    kept = last.read_bytes()
    last.write_bytes(b"\n".join(kept.rstrip(b"\n").split(b"\n")[:-1]) + b"\n")
    cut = _failed(_verify(log.root))
    _rewrite_head(log)
    rewritten = _failed(_verify(log.root))
    with_heads = _failed(_verify(log.root, heads=second / "heads.jsonl"))
    examined(3, "readings of a cut tail")
    assert cut, "a cut tail fails HEAD.json"
    assert not rewritten, "with HEAD.json rewritten to agree, it passes without --heads, as the guide says"
    assert with_heads, "with --heads, it fails"
