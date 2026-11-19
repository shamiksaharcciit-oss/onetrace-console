"""onetrace-verify's own lines on what format 0.5's members do not show, drawn as a list on the pages they concern.

onetrace-verify 0.8 prints, after its rows, one line per kind of member a run holds: `<topic>: <claim>; <claim>; …`
(`a step's recorded store state does not show: …`, `the writer and recovery: …`). The console showed them only in
the check's text. Each is now drawn as a list, in the verifier's words, inside the section of the page it concerns:
the store state, kind, messages and calls sections of a step's page; the case page's "Called by" and "Code"; the
expectations section; and a recovered run's case page. The lines are read from the run's stored check, never
composed; a topic the check did not print is not drawn.
"""

from __future__ import annotations

from onetrace_console.words import escape

#: Each topic onetrace-verify 0.8 prints, by the section that draws it.
TOPICS = {
    "store": "a step's recorded store state does not show",
    "kinds": "a step's kind, agent and tool-call record do not show",
    "messages": "a step's recorded messages do not show",
    "link": "a cross-service link does not show",
    "code": "a re-run with parts chosen separately, and a recorded code version",
    "expect": "expectations checked during the run",
    "recovery": "the writer and recovery",
    "usage": "what a model call adds beside its record does not show",
}
LEAD = "onetrace-verify's own words"
RECOVERY_HEADING = "Recovery"


def of_text(stdout: str) -> dict[str, list[str]]:
    """The verifier's lines on what members do not show, from its text output: each topic's claims, as written."""
    by_topic = {v: k for k, v in TOPICS.items()}
    out: dict[str, list[str]] = {}
    for line in stdout.splitlines():
        topic, sep, rest = line.partition(": ")
        if sep and topic in by_topic and not line.startswith("["):
            out[by_topic[topic]] = [c.strip() for c in rest.split("; ") if c.strip()]
    return out


def of_envelope(envelope) -> dict[str, list[str]]:
    """The lines from a run's stored check (its text output, `stdout`)."""
    text = envelope.get("stdout") if isinstance(envelope, dict) else None
    return of_text(text) if isinstance(text, str) else {}


def of_run(run, store) -> dict[str, list[str]]:
    from onetrace_console.home import _envelope

    try:
        return of_envelope(_envelope(run, store))
    except Exception:  # noqa: BLE001 - a check that can't be read prints no such line
        return {}


def block(notes: dict[str, list[str]], key: str) -> str:
    """The list for one topic, in the verifier's words; "" where the check printed none."""
    claims = notes.get(key)
    if not claims:
        return ""
    items = "".join(f'<li><span data-words="check">{escape(c)}</span></li>' for c in claims)
    return (
        f'<div class="note" data-verifier-non-claims="{escape(key, quote=True)}"><p>{escape(LEAD)}, '
        f'<span data-words="check">{escape(TOPICS[key])}</span>:</p><ul class="plain">{items}</ul></div>'
    )


def within(section: str, notes: dict[str, list[str]], key: str) -> str:
    """`section` with its topic's list as its last part; `section` as it is where it is empty or the check printed
    none."""
    extra = block(notes, key)
    if not section or not extra or not section.endswith("</section>"):
        return section
    return section[: -len("</section>")] + extra + "</section>"


def recovery_section(notes: dict[str, list[str]], recovered: bool) -> str:
    """A recovered run's case page: the verifier's lines on the writer and recovery. "" for any other run."""
    extra = block(notes, "recovery") if recovered else ""
    return f'<section data-section="recovery"><h2>{escape(RECOVERY_HEADING)}</h2>{extra}</section>' if extra else ""
