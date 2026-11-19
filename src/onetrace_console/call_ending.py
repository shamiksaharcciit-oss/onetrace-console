"""How a model call ended, and the engine a self-hosted call ran on, from a `model-call-record/1.1` record (onetrace
0.8's `docs/format.md`), in the record's own words, above the record's fields on its step's page.

- **How the request ended:** the record's `output.finish`: its value where observed ("stop", "stop-string"), or its
  state and the reason it gives where it is not ("not observed: the call failed after post").
- **The engine:** where the record's `engine.name` is observed as `vllm`, the engine's `model_runner`, `engine_core`
  and `executor` (`engine.settings.*`), each where the record holds it.

Read where a record in 1.1 holds the field; where it doesn't, nothing is said, and a record in 1.0 gets nothing:
nothing is drawn that the run didn't record. The record's fields stay drawn as written below the lines.
"""

from __future__ import annotations

from onetrace_console.words import escape

FORMAT = "model-call-record/1.1"
ENDED = "How the request ended"
ENGINE = "The engine"
#: The engine's members said, in this order, each by the record's own name.
ENGINE_FIELDS = tuple((f"engine.settings.{name}", name) for name in ("model_runner", "engine_core", "executor"))


def _field(record: dict, name: str) -> dict | None:
    got = record.get(name)
    return got if isinstance(got, dict) and isinstance(got.get("status"), str) else None


def _said(field: dict) -> str:
    """A field as the record states it: its value where observed; else its state and its reason."""
    if field.get("status") == "observed" and isinstance(field.get("value"), str):
        return field["value"]
    reason = field.get("source")
    return field["status"] + (f": {reason}" if isinstance(reason, str) and reason else "")


def ended_line(record: dict) -> str:
    """How the call ended, where a 1.1 record holds `output.finish`; "" otherwise."""
    if record.get("format") != FORMAT:
        return ""
    finish = _field(record, "output.finish")
    if finish is None:
        return ""
    return (
        f'<p data-call-ended="{escape(finish["status"])}">{escape(ENDED)}: '
        f'<span data-words="record">{escape(_said(finish))}</span></p>'
    )


def engine_line(record: dict) -> str:
    """The engine a self-hosted vLLM call ran on, where a 1.1 record observes it as vllm; "" otherwise."""
    if record.get("format") != FORMAT:
        return ""
    name = _field(record, "engine.name")
    if name is None or name.get("status") != "observed" or name.get("value") != "vllm":
        return ""
    parts = [
        f'{escape(words)} <span data-words="record">{escape(_said(f))}</span>'
        for key, words in ENGINE_FIELDS
        if (f := _field(record, key)) is not None
    ]
    return f'<p data-call-engine="vllm">{escape(ENGINE)}: vllm' + (f"; {'; '.join(parts)}" if parts else "") + "</p>"


def lines(record: dict) -> str:
    return ended_line(record) + engine_line(record)
