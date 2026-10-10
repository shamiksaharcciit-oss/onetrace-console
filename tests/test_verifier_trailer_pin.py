"""The viewer reads only the lines the verifier writes after its summary, which
it holds as constants taken from the verifier's code at the pinned build. This holds them equal to
the installed verifier's own, so a build that changes a word fails here before a page misreads it.
"""
from __future__ import annotations

import inspect


def test_the_viewers_trailer_lines_are_the_installed_verifiers_own(examined):
    import onetrace_verify.beside as beside
    import onetrace_verify.cli as cli
    from onetrace_console.viewer.report import ANCHOR_NON_CLAIM, BESIDE_NOT_RUN_NOTE
    examined(3, "trailer lines compared")
    assert ANCHOR_NON_CLAIM == cli.ANCHOR_NON_CLAIM
    assert BESIDE_NOT_RUN_NOTE == beside.NOT_RUN_NOTE
    #: The count line's form, as the code writes it, and in that order before the caveat.
    source = inspect.getsource(cli)
    count = 'verify._out(f"records beside the chain: {state[\'not_run\']} not run -- {beside.NOT_RUN_NOTE}")'
    caveat = "verify._out(ANCHOR_NON_CLAIM)"
    assert count in source and caveat in source
    assert source.index(count) < source.index(caveat)


def test_the_viewers_signing_lines_are_the_installed_verifiers_own(examined):
    """As of the third development build: the untrusted count and what a signature
    does not show, their words and their order among the four lines, as the installed code writes
    them."""
    import onetrace_verify.cli as cli
    import onetrace_verify.signatures as signatures
    from onetrace_console.viewer.report import SIGNATURE_CAVEAT, SIGNATURE_NON_CLAIMS, UNTRUSTED_NOTE
    examined(2, "signing lines compared")
    assert UNTRUSTED_NOTE == signatures.UNTRUSTED_NOTE
    assert SIGNATURE_NON_CLAIMS == tuple(signatures.NON_CLAIMS)
    assert SIGNATURE_CAVEAT == "a signature does not show: " + "; ".join(signatures.NON_CLAIMS)
    source = inspect.getsource(cli)
    order = ["signed by an untrusted key",
             'verify._out(f"records beside the chain: {state[\'not_run\']} not run -- {beside.NOT_RUN_NOTE}")',
             "verify._out(ANCHOR_NON_CLAIM)",
             'verify._out("a signature does not show: " + "; ".join(signatures.NON_CLAIMS))']
    at = [source.index(line) for line in order]
    assert at == sorted(at), "the four lines are written in this order"


def test_the_viewers_escaping_is_the_installed_verifiers_own(examined):
    """The viewer pairs a text row with its --json row by the name as the verifier
    escapes it; its ranges and rule equal the installed verifier's, character for character."""
    import onetrace_verify.escaping as escaping
    import onetrace_verify.verify as verify
    from onetrace_console.viewer.report import VERIFIER_ESCAPED_RANGES, verifier_escaped
    assert tuple(VERIFIER_ESCAPED_RANGES) == tuple(escaping.ESCAPED_RANGES)
    samples = ["plain", "C:\\Users\\runner\\trust.json", "a\\\\b", "bell\u0007", "line\nbreak",
               "rtl\u202eover", "soft\u00adhyphen", "tag\U000e0001", "lone\ud800surrogate", "\\u0007"]
    examined(len(samples), "names escaped by both")
    for text in samples:
        assert verifier_escaped(text) == verify._escaped(text), repr(text)
