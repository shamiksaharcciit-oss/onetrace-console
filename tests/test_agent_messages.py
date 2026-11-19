"""Messages between agents on a run's pages (`agent_messages`): each step's page shows the messages it sent and took
in, a received one linked to the message on the sender's page, a sent one's kept bytes shown as a message where the
run kept them; each step that sent or took in any has a line in the table of steps. Each present, absent, not kept
and failed by the verifier, on the runs in `tests/format_05_agents/`."""

from __future__ import annotations

import re

import pytest

from tests.test_step_kinds import HERE, OLDER, _pages, _text


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _section(page: str) -> str:
    m = re.search(r'<section data-section="messages">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def _lines(pages) -> list[str]:
    return [
        _text(m.group(0)) for m in re.finditer(r'<div class="step" data-step-messages.*?</div>', pages["proof.html"])
    ]


def test_present_sent_taken_in_kept_and_each_step_s_line(tmp_path, examined):
    from onetrace_console.agent_messages import KEPT_LABEL, NON_CLAIMS
    from onetrace_console.step_kinds import prose

    pages = _pages(HERE / "agents-kept", tmp_path)
    sent, taken = _section(pages["stage-2.html"]), _section(pages["stage-3.html"])
    examined(3, "the sender's page, the receiver's page and the table of steps")
    assert _lines(pages) == ["1 message sent", "1 taken in"]
    assert "triage:1 : from triage to researcher , kind task · 59 bytes" in _text(sent)
    assert KEPT_LABEL in _text(sent)
    assert '{"find":"order status","question":"Where is order A-1001?"}' in _text(sent)
    assert '<a href="stage-2.html#message-1">triage:1</a>' in taken and 'id="message-1"' in sent
    assert prose(NON_CLAIMS) in sent and prose(NON_CLAIMS) in taken


def test_not_kept_absent_and_an_earlier_format(tmp_path, examined):
    from onetrace_console.agent_messages import KEPT_LABEL, NOT_KEPT

    not_kept = _pages(HERE / "agents-not-kept", tmp_path / "n")
    kept = _pages(HERE / "agents-kept", tmp_path / "k")
    older = _pages(OLDER, tmp_path / "o")
    examined(3, "a run that kept no outputs, steps with no message, and a format 0.4 run")
    sent = _section(not_kept["stage-2.html"])
    assert NOT_KEPT in _text(sent) and KEPT_LABEL not in sent
    assert _section(kept["stage-4.html"]) == "" and _section(kept["stage-5.html"]) == ""
    assert not any('data-section="messages"' in p or "data-step-messages" in p for p in older.values())


def test_malformed_a_message_member_the_verifier_fails_is_not_drawn_its_row_is(tmp_path, examined):
    sent = _pages(HERE / "reject" / "R74-message-digest-out-of-form", tmp_path / "s")
    taken = _pages(HERE / "reject" / "R79-received-no-such-seq", tmp_path / "t")
    examined(2, "runs whose sent and taken-in messages the verifier fails")
    page = _section(sent["stage-1.html"])
    assert "[FAIL ] receipts/01-s.json: messages -- messages[1]: digest 'sha256:00' is out of form" in _text(page)
    assert "data-message=" not in page
    page = _section(taken["stage-2.html"])
    assert (
        "[FAIL ] receipts/02-billing.json: messages_received -- messages_received[1]: answer has no message"
        in _text(page)
    )
    #: No message drawn; the verifier's own list on what messages do not show comes after them (`verifier_notes`).
    assert "<li>" not in page.split("Messages this step took in")[1].split("data-verifier-non-claims")[0]


def test_sabotage_a_console_that_draws_a_failed_message_is_named(tmp_path, monkeypatch, examined):
    from onetrace_console import agent_messages

    monkeypatch.setattr(agent_messages, "failed", lambda rows, subject, names: [])
    sent = _pages(HERE / "reject" / "R74-message-digest-out-of-form", tmp_path)
    examined(1, "a run whose message the verifier fails, drawn from anyway")
    assert "sha256:00" in _section(sent["stage-1.html"]).split("Messages this step sent")[1]
