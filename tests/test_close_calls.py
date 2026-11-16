"""The close-call flag, on one run: on a model step whose record carries L2 with log-probabilities (the hosted form), the
positions where the chosen token's lead over the runner-up is at most `close_call_margin` (a console setting in nats,
default 1.0); the first such position and a count. Without log-probabilities (self-hosted L2 holds ids only): "no
log-probabilities recorded". Without L2: nothing. Shown as a fact of the capture, labelled model-generated, under f2's
text rules: no real run's text on a public console. A close call is not an error, and a wide margin is not correctness.
"""

from __future__ import annotations

import html
import re

import pytest

from tests.token_level_runs import hosted_call, l2_call, record_run


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _flag(page: str) -> str:
    m = re.search(r"<div data-close-calls.*?</div>", page, re.S)
    return m.group(0) if m else ""


def _step(chosen, cands):
    """A hosted step: the candidates' (text, logprob), the chosen one by its text."""
    cs = [{"text": t, "logprob": lp} for t, lp in cands]
    return {"chosen": next(c for c in cs if c["text"] == chosen), "candidates": cs}


#: Position 0 wide (lead 2.0); 1 close (0.3), the first; 2 wide; 3 close (0.5); 4 close (1.0, at the margin).
CLOSE = [
    _step("The", [("The", "-0.10"), ("A", "-2.10")]),
    _step("no", [("no", "-0.40"), ("yes", "-0.70"), ("maybe", "-3.00")]),
    _step(",", [(",", "-0.05"), (".", "-4.00")]),
    _step("then", [("then", "-0.80"), ("so", "-1.30")]),
    _step("ok", [("ok", "-1.00"), ("fine", "-2.00")]),
]
WIDE = [_step("The", [("The", "-0.10"), ("A", "-2.10")]), _step(",", [(",", "-0.05"), (".", "-4.00")])]
CALLS = {
    "close": hosted_call(CLOSE),
    "wide": hosted_call(WIDE),
    "no-logprobs": hosted_call(
        [{"chosen": {"text": "no"}, "candidates": [{"text": "no"}, {"text": "yes"}]}], logprobs="none"
    ),
    "self-hosted": l2_call(["11", "12"], [["11", "9001"], ["12", "9001"]]),
}


def _pages(tmp, public: bool, margin: float = 1.0):
    from onetrace_console.checks import run_and_record
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver

    store = Store(tmp / "store")
    out = {}
    for name, call in CALLS.items():
        run = run_and_record(
            _deliver(record_run(tmp / name, f"cc-{name}", call), store, outputs=True), store, ran_at=FIXED_RAN_AT
        )
        with rendering(onedoor=False, sign_in=False, public=public, close_call_margin=margin):
            pages = render_execution(run, store, generated_at="2026-11-09T12:00:00+00:00").pages
        out[name] = next(v for k, v in pages.items() if k.startswith("stage-"))
    return out


@pytest.fixture(scope="module")
def local(tmp_path_factory):
    return _pages(tmp_path_factory.mktemp("cc-local"), public=False)


@pytest.fixture(scope="module")
def public(tmp_path_factory):
    return _pages(tmp_path_factory.mktemp("cc-public"), public=True)


def test_a_planted_close_call_is_flagged_with_the_first_and_a_count(local, examined):
    said = _text(_flag(local["close"]))
    examined(1, "a step with close calls")
    assert (
        "At token 1: “no” was chosen; “yes” was the 2nd candidate, 0.30 behind; 3 close calls in this output "
        "(a lead of at most 1.0 nats)."
    ) in said
    assert "model-generated" in said


def test_a_wide_margin_is_not_flagged(local, examined):
    said = _text(_flag(local["wide"]))
    examined(1, "a step with wide margins")
    assert "No close call: at every token the chosen token led the runner-up by more than 1.0 nats." in said


def test_no_flag_without_log_probabilities(local, examined):
    hosted, selfh = _text(_flag(local["no-logprobs"])), _text(_flag(local["self-hosted"]))
    examined(2, "steps whose captures hold no log-probabilities")
    assert "No close-call flag: no log-probabilities recorded." in hosted
    assert "No close-call flag: no log-probabilities recorded." in selfh
    assert "close calls in this output" not in hosted + selfh


def test_no_flag_without_l2(tmp_path, examined):
    from onetrace_console import token_levels as tl

    examined(1, "a record with no capture")
    assert tl.close_calls({}, None, 1.0) == ""


def test_the_margin_is_the_console_s_setting(tmp_path, examined):
    said = _text(_flag(_pages(tmp_path, public=False, margin=0.4)["close"]))
    examined(1, "a step under a margin of 0.4")
    #: The leads are 0.30, 0.50 and 1.00: under 0.4, only the first.
    assert "1 close call in this output (a lead of at most 0.4 nats)" in said


def test_a_public_console_shows_no_real_run_s_text(public, examined):
    said = _text(_flag(public["close"]))
    examined(1, "a step on a public console")
    assert "“no”" not in said and "“yes”" not in said
    assert "At token 1: the chosen token led the 2nd candidate by 0.30; 3 close calls in this output" in said


def test_the_non_claim(local, examined):
    examined(1, "the flag's non-claim")
    assert "A close call is not an error, and a wide margin is not correctness." in _text(_flag(local["close"]))


def test_the_setting_is_a_configuration_key(tmp_path, examined):
    from onetrace_console.config import Config, ConfigError, load

    examined(3, "settings")
    assert Config().close_call_margin == 1.0
    p = tmp_path / "c.json"
    p.write_text('{"close_call_margin": 0.5}', encoding="utf-8")
    assert load(p).close_call_margin == 0.5
    p.write_text('{"close_call_margin": 0}', encoding="utf-8")
    with pytest.raises(ConfigError):
        load(p)


def test_sabotage_a_flag_that_counts_strictly_below_the_margin_is_caught(monkeypatch, examined):
    from onetrace_console import token_levels as tl

    examined(1, "a planted comparison")
    doc = {"level": "L2-hosted", "method": "provider-text", "steps": CLOSE}
    assert len(tl.close_positions(doc, 1.0)) == 3
    monkeypatch.setattr(tl, "_close", lambda lead, margin: lead < margin)
    assert len(tl.close_positions(doc, 1.0)) != 3
