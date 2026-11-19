"""What kind of step this is, and which agent ran it: format 0.5's `step.kind`, `agent`, `run_agent` and `tool_call`
(onetrace 0.8's `docs/format.md`, "What kind of step this is, and which agent ran it"), as a run's record holds them.

Where they are drawn:
- the run's head names the run's agent (`run_agent`);
- each step in the run's table of steps gets a line: its kind, and its agent where the step's differs from the run's;
- each step's page gets a section: its kind, its agent, and, for a step of kind `tool call`, its tool-call record,
  with `requested_by` linked to the model step that asked for it.

The rules, the same on every page:
- **The words are the record's members and the verifier's rows.** Nothing is inferred: a kind is never guessed from
  an instrument, nor an agent from a name.
- **An absent member reads "not recorded",** never a default and never `other`. The members exist from format 0.5
  on, so a receipt in an earlier format gets no line at all: its format has no such member to be absent.
- **A member onetrace-verify fails is not drawn from.** Where the verifier's row about a receipt's `step kind`,
  `step`, `agent`, `tool_call` or `tool_call requested_by` (or the run's `run agent`) reads FAIL, the member is not
  shown: the row is, in its own words.
- **Each section carries what these members do not show**, in `docs/format.md`'s words (`NON_CLAIMS`).
"""

from __future__ import annotations

import re

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.words import escape

#: The format that first holds these members.
FIRST_MINOR = 5
#: The eight kinds a step may record (onetrace 0.8's `emit.STEP_KINDS`; a new kind needs a new minor).
STEP_KINDS = ("model call", "tool call", "retrieval", "decision", "state read", "state write", "transform", "other")
NOT_RECORDED = "not recorded"
KIND_NOT_RECORDED = "kind not recorded"
#: onetrace 0.8's `docs/format.md`, "What kind of step this is, and which agent ran it", "What it does not show".
NON_CLAIMS = (
    "A step's kind and an agent's identity are what the code declares, or what a hook read of the call. They are bound "
    "by the signature to the key that signed them, not a proof of which model or tool answered. `requested_by` shows "
    "the record names a request with that id, not that the tool ran with what the model asked for, unless a reader "
    "that holds both compares the arguments. An absent kind says nothing about the step."
)
HEADING = "What kind of step this is, and which agent ran it"
RUN_AGENT_LEAD = "The run's agent"
#: The verifier's rows that read these members: on a receipt, and on the run.
KIND_ROWS = ("step kind", "step")
AGENT_ROWS = ("agent",)
TOOL_ROWS = ("tool_call",)
REQUESTED_BY_ROWS = ("tool_call requested_by",)
RUN_AGENT_ROW = "run agent"


def holds_members(receipt) -> bool:
    """The receipt's own format is `stage-receipt/0.5` or later in major 0, where these members exist."""
    fmt = receipt.get("format") if isinstance(receipt, dict) else None
    m = re.fullmatch(r"stage-receipt/0\.([0-9]+)", fmt) if isinstance(fmt, str) else None
    return m is not None and int(m.group(1)) >= FIRST_MINOR


_TICKS = re.compile(r"`([^`\n]+)`")


def prose(text: str) -> str:
    """Words from onetrace's documents, escaped, each backtick pair shown as code."""
    return _TICKS.sub(r"<code>\1</code>", escape(text))


def _line(row: dict) -> str:
    from onetrace_console.viewer.report import _text_line

    return _text_line(row)


def failed(rows: list[dict], subject: str, names: tuple[str, ...]) -> list[str]:
    """The verifier's FAIL rows about `subject` (a receipt's file, or "" for the run) on any of `names`, as lines."""
    wanted = {f"{subject}: {n}" if subject else n for n in names}
    return [_line(r) for r in rows if r.get("result") == "FAIL" and r.get("name") in wanted]


def _fail_block(lines: list[str]) -> str:
    return "".join(f'<p class="fail" data-check-row="fail"><span class="mono">{escape(ln)}</span></p>' for ln in lines)


def agent_words(agent) -> str:
    """An agent as recorded: its name, its role where given, and what it runs on where given."""
    if not isinstance(agent, dict) or not isinstance(agent.get("name"), str):
        return ""
    parts = [agent["name"]]
    if isinstance(agent.get("role"), str):
        parts.append(agent["role"])
    ro = agent.get("runs_on")
    if isinstance(ro, dict) and isinstance(ro.get("name"), str):
        on = ro["name"] + (f" {ro['version']}" if isinstance(ro.get("version"), str) else "")
        parts.append(f"on {on}" + (f" ({ro['kind']})" if isinstance(ro.get("kind"), str) else ""))
    return " · ".join(parts)


def run_agent(receipts: list[dict], rows: list[dict]) -> tuple[dict | None, list[str]]:
    """The run's agent (`run_agent`, the same in every receipt), and the verifier's FAIL rows on it. Where the row
    fails, no agent is given."""
    fails = failed(rows, "", (RUN_AGENT_ROW,))
    if fails:
        return None, fails
    agents = [r.get("run_agent") for r in receipts if isinstance(r, dict) and holds_members(r)]
    first = agents[0] if agents else None
    return (first if isinstance(first, dict) and all(a == first for a in agents) else None), []


def head_line(receipts: list[dict], rows: list[dict]) -> str:
    """The run's head's line: the run's agent, "not recorded", or the verifier's FAIL. None for an earlier format."""
    if not any(isinstance(r, dict) and holds_members(r) for r in receipts):
        return ""
    agent, fails = run_agent(receipts, rows)
    if fails:
        return f'<div data-section="run-agent"><p class="sub">{escape(RUN_AGENT_LEAD)}:</p>{_fail_block(fails)}</div>'
    said = agent_words(agent) or NOT_RECORDED
    return (
        f'<p class="sub" data-section="run-agent">{escape(RUN_AGENT_LEAD)}: '
        f'<span class="mono" data-words="record">{escape(said)}</span></p>'
    )


def _kind(receipt: dict) -> str:
    step = receipt.get("step")
    kind = step.get("kind") if isinstance(step, dict) else None
    return kind if isinstance(kind, str) and kind else ""


def _own_agent(receipt: dict, run_agent_said) -> dict | None:
    """The step's own agent, where it is recorded and is not the run's."""
    agent = receipt.get("agent")
    return agent if isinstance(agent, dict) and agent != run_agent_said else None


def step_line(receipt: dict, receipt_file: str, rows: list[dict], run_agent_said) -> str:
    """A step's line in the run's table of steps: its kind, and its agent where it differs from the run's."""
    if not holds_members(receipt):
        return ""
    kind_fails = failed(rows, receipt_file, KIND_ROWS)
    agent_fails = failed(rows, receipt_file, AGENT_ROWS)
    if kind_fails or agent_fails:
        return f'<div class="step" data-step-kind="fail">{_fail_block(kind_fails + agent_fails)}</div>'
    kind = _kind(receipt)
    words = kind or KIND_NOT_RECORDED
    own = _own_agent(receipt, run_agent_said)
    agent = f" · agent {own['name']}" if own and isinstance(own.get("name"), str) else ""
    return (
        f'<div class="step" data-step-kind="{escape(kind or "not-recorded")}">'
        f'<span data-words="record">{escape(words + agent)}</span></div>'
    )


_STEP_CELL = re.compile(
    r'(<tr data-step="(\d+)"><td data-label="Step"><span id="step-\2"></span>.*?<div class="step">[^<]*</div>)'
)


def with_step_lines(page: str, steps: list[dict], rows: list[dict], run_agent_said) -> str:
    """The run page with each step's line after its "step N of M" in the table of steps. `steps`: the chain's steps,
    [{index, file, receipt}]."""
    by_index = {s["index"]: s for s in steps}

    from onetrace_console import agent_messages

    def put(m: re.Match) -> str:
        s = by_index.get(m.group(2))
        if not s:
            return m.group(1)
        return (
            m.group(1)
            + step_line(s["receipt"], s["file"], rows, run_agent_said)
            + agent_messages.step_line(s["receipt"], s["file"], rows)
        )

    return _STEP_CELL.sub(put, page)


def _requested_by(tc: dict, receipt_file: str, rows: list[dict], node_pages: dict[str, str]) -> str:
    rb = tc.get("requested_by")
    if not isinstance(rb, dict):
        return f"<li>Requested by: {escape(NOT_RECORDED)}</li>"
    fails = failed(rows, receipt_file, REQUESTED_BY_ROWS)
    if fails:
        return f"<li>Requested by:{_fail_block(fails)}</li>"
    step, call_id = str(rb.get("step", "")), str(rb.get("call_id", ""))
    href = node_pages.get(step)
    named = f'<a href="{escape(href)}">{escape(step)}</a>' if href else escape(step)
    return (
        f'<li>Requested by: <span class="mono" data-words="record">{named}</span>, call id '
        f'<span class="mono" data-words="record">{escape(call_id)}</span>. The model step\'s request is in its kept '
        "response, on its page.</li>"
    )


def _digest_or_status(tc: dict, part: str) -> str:
    if isinstance(tc.get(f"{part}_digest"), str):
        return tc[f"{part}_digest"]
    if isinstance(tc.get(f"{part}_status"), str):
        return tc[f"{part}_status"]
    return NOT_RECORDED


def _tool_call(receipt: dict, receipt_file: str, rows: list[dict], node_pages: dict[str, str]) -> str:
    tc = receipt.get("tool_call")
    if tc is None:
        return ""
    fails = failed(rows, receipt_file, TOOL_ROWS)
    if fails or not isinstance(tc, dict):
        return f'<div data-section="tool-call"><h3>The tool call</h3>{_fail_block(fails)}</div>'
    name = tc.get("name") if isinstance(tc.get("name"), str) else NOT_RECORDED
    call_id = tc.get("call_id") if isinstance(tc.get("call_id"), str) else NOT_RECORDED
    return (
        '<div data-section="tool-call"><h3>The tool call</h3><ul class="plain">'
        f'<li>Tool: <span class="mono" data-words="record">{escape(name)}</span> · call id '
        f'<span class="mono" data-words="record">{escape(call_id)}</span></li>'
        f'<li>Arguments: <span class="mono" data-words="record">{escape(_digest_or_status(tc, "arguments"))}</span></li>'
        f'<li>Result: <span class="mono" data-words="record">{escape(_digest_or_status(tc, "result"))}</span></li>'
        + _requested_by(tc, receipt_file, rows, node_pages)
        + "</ul></div>"
    )


def step_section(receipt: dict, receipt_file: str, rows: list[dict], run_agent_said, node_pages: dict[str, str]) -> str:
    """A step's page: its kind, its agent and, for a tool call, its tool-call record. None for an earlier format."""
    if not holds_members(receipt):
        return ""
    kind_fails = failed(rows, receipt_file, KIND_ROWS)
    kind = (
        _fail_block(kind_fails)
        if kind_fails
        else f'<p>Kind: <span class="mono" data-words="record">{escape(_kind(receipt) or NOT_RECORDED)}</span></p>'
    )
    agent_fails = failed(rows, receipt_file, AGENT_ROWS)
    own = _own_agent(receipt, run_agent_said)
    if agent_fails:
        agent = _fail_block(agent_fails)
    elif own is not None:
        agent = (
            f'<p>Agent: <span class="mono" data-words="record">{escape(agent_words(own) or NOT_RECORDED)}</span></p>'
        )
    elif run_agent_said is not None:
        agent = (
            f'<p>Agent: the run\'s, <span class="mono" data-words="record">{escape(run_agent_said["name"])}</span></p>'
        )
    else:
        agent = f"<p>Agent: {escape(NOT_RECORDED)}</p>"
    return (
        f'<section data-section="step-kind"><h2>{escape(HEADING)}</h2>{kind}{agent}'
        + _tool_call(receipt, receipt_file, rows, node_pages)
        + f'<p class="note" data-section="step-kind-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


def context(run, store) -> tuple[list[dict], list[dict], dict | None, dict[str, str]]:
    """What the drawing above needs of a stored run, read once: its steps ([{index, file, receipt}]), the verifier's
    rows of its stored check, the run's agent (None where not recorded or failed), and each node's step page."""
    from onetrace_console.home import _envelope
    from onetrace_console.info_mark import rows_of
    from onetrace_console.stage_pages import _receipts, _steps, stage_page

    rows = rows_of(_envelope(run, store))
    steps = _steps(run, store)
    agent, _ = run_agent([r["receipt"] for r in _receipts(run, store)], rows)
    pages: dict[str, str] = {}
    for s in steps:
        stage = s["receipt"].get("stage")
        name = stage.get("name") if isinstance(stage, dict) else None
        if isinstance(name, str) and s["index"].isdigit():
            pages.setdefault(name, stage_page(s["index"]))
    return steps, rows, agent, pages


def summary(receipts: list[tuple[str, dict]], rows: list[dict]) -> dict | None:
    """What the runs list keeps of a run: the kinds its steps record, in step order, and its agents (the run's
    first, then each step's own), each once; None where no receipt is in format 0.5 or later. A member the
    verifier fails is left out, as the pages leave it out."""
    held = [(f, r) for f, r in receipts if isinstance(r, dict) and holds_members(r)]
    if not held:
        return None
    agent, _ = run_agent([r for _, r in held], rows)
    kinds: list[str] = []
    agents: list[str] = [agent["name"]] if agent is not None and isinstance(agent.get("name"), str) else []
    for f, r in held:
        k = _kind(r)
        if k and k not in kinds and not failed(rows, f, KIND_ROWS):
            kinds.append(k)
        own = r.get("agent")
        name = own.get("name") if isinstance(own, dict) else None
        if isinstance(name, str) and name not in agents and not failed(rows, f, AGENT_ROWS):
            agents.append(name)
    return {"kinds": kinds, "agents": agents}


def cell(kept: str) -> str:
    """The runs list's "Kinds" cell from a run's kept summary: its kinds, then its agents; "not recorded" for a run
    in format 0.5 that records none; empty for a run in an earlier format, or one kept before this was."""
    try:
        said = load_json_bounded(kept, "a run's kept kinds") if kept else None
    except ValueError:
        said = None
    if not isinstance(said, dict):
        return ""
    kinds = [k for k in said.get("kinds") or [] if isinstance(k, str)]
    agents = [a for a in said.get("agents") or [] if isinstance(a, str)]
    if not kinds and not agents:
        return f'<span data-kinds="not-recorded">{escape(NOT_RECORDED)}</span>'
    words = " · ".join(kinds) if kinds else KIND_NOT_RECORDED
    if agents:
        words += "; agents " + ", ".join(agents)
    return f'<span class="mono" data-words="record" data-kinds="recorded">{escape(words)}</span>'


def records_any(kept: str) -> bool:
    """Whether a run's kept summary names a kind or an agent: a runs list draws its Kinds column where one does."""
    try:
        said = load_json_bounded(kept, "a run's kept kinds") if kept else None
    except ValueError:
        return False
    return isinstance(said, dict) and bool(said.get("kinds") or said.get("agents"))
