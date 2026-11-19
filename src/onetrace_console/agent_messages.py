"""Messages between agents: format 0.5's `messages` and `messages_received` (onetrace 0.8's `docs/format.md`, "Messages
between agents"), as a run's record holds them.

Where they are drawn:
- each step's page gets two sections, "Messages this step sent" and "Messages this step took in": a message by its
  id (`<node id>:<seq>`), sender, receiver, kind, digest and size; a received one linked to the step that sent it,
  where `from_step` names one; and a sent message's kept bytes, where the run kept them, shown as a message and
  never as an output;
- each step that sent or took in any gets a line in the run's table of steps, with the counts.

The rules are `step_kinds`' (the record's words alone; a member the verifier fails, `messages`, `messages kept` or
`messages_received`, is not drawn from and its row is shown; what messages do not show, in `docs/format.md`'s
words, on each section). A step with no message gets no section and no line: the format says no message was
recorded, and nothing more.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath

from onetrace_console.step_kinds import _fail_block, failed, holds_members, prose
from onetrace_console.words import escape

#: onetrace 0.8's `docs/format.md`, "Messages between agents", "What it does not show".
NON_CLAIMS = (
    "A message record shows what was sent, not that the receiver acted on it. `messages_received` shows the "
    "receiving step's code said it took the message in, or that a framework's state held it when the node started, "
    "not that the node read it. `to` is what the code declared; under LangGraph it is a channel, not a route. A "
    "message passed with no helper and no adapter is not seen."
)
SENT = "Messages this step sent"
TAKEN = "Messages this step took in"
SENT_ROWS = ("messages",)
KEPT_ROWS = ("messages kept",)
TAKEN_ROWS = ("messages_received",)
KEPT_LABEL = "Kept bytes, as sent: a message, not an output of the step"
KEPT_MISMATCH = "the kept bytes do not match the message's digest, not shown"
KEPT_NOT_TEXT = "the kept bytes are not text, not shown"
NOT_KEPT = "not kept"
FROM_UNKNOWN = "no sending step named"


def _list(receipt: dict, member: str) -> list[dict]:
    v = receipt.get(member)
    return [m for m in v if isinstance(m, dict)] if isinstance(v, list) else []


def _node(receipt: dict) -> str:
    stage = receipt.get("stage")
    return str(stage.get("name", "")) if isinstance(stage, dict) else ""


def _stem(receipt_file: str) -> str:
    return PurePosixPath(receipt_file).stem


def _kept(m: dict, receipt_file: str, read_file) -> str:
    if m.get("kept") != "true" or read_file is None:
        return f"<p>{escape(NOT_KEPT)}</p>"
    blob = read_file(f"messages/{_stem(receipt_file)}/{m.get('seq', '')}")
    if blob is None:
        return f"<p>{escape(NOT_KEPT)}</p>"
    if "sha256:" + hashlib.sha256(blob).hexdigest() != m.get("digest"):
        return f"<p>{escape(KEPT_MISMATCH)}</p>"
    try:
        text = blob.decode("utf-8")
    except UnicodeDecodeError:
        return f"<p>{escape(KEPT_NOT_TEXT)}</p>"
    return (
        f"<details data-message-kept><summary>{escape(KEPT_LABEL)}</summary>"
        f'<pre class="mono" data-words="record">{escape(text)}</pre></details>'
    )


def _sent(receipt: dict, receipt_file: str, rows: list[dict], read_file) -> str:
    sent = _list(receipt, "messages")
    fails = failed(rows, receipt_file, SENT_ROWS)
    if not sent and not fails:
        return ""
    if fails:
        return f'<div data-section="messages-sent"><h3>{escape(SENT)}</h3>{_fail_block(fails)}</div>'
    kept_fails = failed(rows, receipt_file, KEPT_ROWS)
    node = _node(receipt)
    items = []
    for m in sent:
        seq = str(m.get("seq", ""))
        size = f" · {escape(str(m['bytes']))} bytes" if isinstance(m.get("bytes"), str) else ""
        media = f" · {escape(m['media_type'])}" if isinstance(m.get("media_type"), str) else ""
        items.append(
            f'<li id="message-{escape(seq, quote=True)}" data-message="{escape(node + ":" + seq, quote=True)}">'
            f'<span class="mono" data-words="record">{escape(node)}:{escape(seq)}</span>: from '
            f'<span class="mono" data-words="record">{escape(str(m.get("from", "")))}</span> to '
            f'<span class="mono" data-words="record">{escape(str(m.get("to", "")))}</span>, kind '
            f'<span class="mono" data-words="record">{escape(str(m.get("kind", "")))}</span>{size}{media}<br>'
            f'<span class="mono" data-words="record">{escape(str(m.get("digest", "")))}</span>'
            + (_fail_block(kept_fails) if kept_fails else _kept(m, receipt_file, read_file))
            + "</li>"
        )
    return f'<div data-section="messages-sent"><h3>{escape(SENT)}</h3><ul class="plain">{"".join(items)}</ul></div>'


def _taken(receipt: dict, receipt_file: str, rows: list[dict], node_pages: dict[str, str]) -> str:
    taken = _list(receipt, "messages_received")
    fails = failed(rows, receipt_file, TAKEN_ROWS)
    if not taken and not fails:
        return ""
    if fails:
        return f'<div data-section="messages-taken"><h3>{escape(TAKEN)}</h3>{_fail_block(fails)}</div>'
    items = []
    for m in taken:
        step, seq = m.get("from_step"), m.get("seq")
        if isinstance(step, str) and isinstance(seq, str):
            href = node_pages.get(step)
            said = f"{step}:{seq}"
            named = (
                f'<a href="{escape(href)}#message-{escape(seq, quote=True)}">{escape(said)}</a>'
                if href
                else escape(said)
            )
            who = f'<span class="mono" data-words="record">{named}</span>'
        else:
            who = escape(FROM_UNKNOWN)
        items.append(
            f'<li>{who} · <span class="mono" data-words="record">{escape(str(m.get("digest", "")))}</span></li>'
        )
    return f'<div data-section="messages-taken"><h3>{escape(TAKEN)}</h3><ul class="plain">{"".join(items)}</ul></div>'


def step_section(receipt: dict, receipt_file: str, rows: list[dict], node_pages: dict[str, str], read_file) -> str:
    """A step's page: the messages it sent and took in. Nothing for a step with none, or an earlier format."""
    if not holds_members(receipt):
        return ""
    parts = _sent(receipt, receipt_file, rows, read_file) + _taken(receipt, receipt_file, rows, node_pages)
    if not parts:
        return ""
    return (
        f'<section data-section="messages"><h2>Messages</h2>{parts}'
        f'<p class="note" data-section="messages-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


def step_line(receipt: dict, receipt_file: str, rows: list[dict]) -> str:
    """A step's line in the run's table of steps: how many messages it sent and took in. Nothing for none."""
    if not holds_members(receipt):
        return ""
    fails = failed(rows, receipt_file, SENT_ROWS + TAKEN_ROWS)
    if fails:
        return f'<div class="step" data-step-messages="fail">{_fail_block(fails)}</div>'
    sent, taken = len(_list(receipt, "messages")), len(_list(receipt, "messages_received"))
    if not sent and not taken:
        return ""
    words = []
    if sent:
        words.append(f"{sent} message{'s' if sent != 1 else ''} sent")
    if taken:
        words.append(f"{taken} taken in")
    return f'<div class="step" data-step-messages="{sent}-{taken}">{escape(" · ".join(words))}</div>'
