"""A pipeline's model fingerprint across its runs: where the model identity its runs' model-call records state changes.

The identity is what onetrace's comparator groups as a call's identity, three of its fields: `provider.fingerprint`,
`model.reported` and `model.files_digest` (`IDENTITY`). For each run of a pipeline, oldest first as this console
received them, each model-call record (by its step and its name) gives those three values where it states them. Where
a value differs from the same record's in the run before (the last run that held that record), the pipeline's
fingerprint changed between those two runs, on the later run's day (the day this console received it).

Where it is drawn:
- the pipeline's page: one line a change, "This pipeline's model fingerprint changed on <date>", with the runs either
  side, each linked, and the fields that changed, before and after;
- the pipeline's drift page, its runs oldest first as received: a mark, with its date, on the row of each run where a
  change was first seen.

A field neither run states is not compared, and a record only one of the two holds is not a change. What it does not
say is said with it: a fingerprint change says the provider's system changed, not that the output got worse.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from onetrace_console.words import escape

if TYPE_CHECKING:
    from onetrace_console.store import StoredRun

IDENTITY = ("provider.fingerprint", "model.reported", "model.files_digest")
HEADING = "The model fingerprint across runs"
LINE = "This pipeline's model fingerprint changed on {date}"
NONE = "No change: every run's model-call records state the same {fields} as the run before."
NOT_RECORDED = "No run of this pipeline holds a model-call record stating {fields}, so nothing is compared."
NON_CLAIM = (
    "A fingerprint change says the provider's system changed between the two runs. It does not say the output got "
    "worse, or better."
)
MARK = "model fingerprint changed"


@dataclass(frozen=True)
class Change:
    before: StoredRun  # the run before the change
    after: StoredRun  # the run where it was first seen
    step: str
    name: str
    fields: tuple[tuple[str, str, str], ...]  # (field, before, after)

    @property
    def date(self) -> str:
        return str(self.after.received_at)[:10]


def _value(record: dict, field: str) -> str | None:
    v = record.get(field)
    if isinstance(v, dict) and "value" in v and not isinstance(v["value"], (list, dict)):
        return str(v["value"])
    return None


def identities(run, store) -> dict[tuple[str, str], dict[str, str]]:
    """{(step name, record name): {field: value}} for every model-call record of the run that reads, stated fields
    only."""
    from onetrace_console import model_call as mc
    from onetrace_console.model_call_compare import _steps_by_name

    out: dict[tuple[str, str], dict[str, str]] = {}
    try:
        steps = _steps_by_name(run, store)
    except Exception:  # noqa: BLE001 - a run that can't be read states nothing here
        return out
    for step in steps:
        for o in mc.outputs(step["receipt"]):
            try:
                record = mc.read_output(step["file"], o, step["read"])
            except mc.Refused:
                continue
            stated = {f: v for f in IDENTITY if (v := _value(record, f)) is not None}
            if stated:
                out[(step["name"], str(o["name"]))] = stated
    return out


def changes(runs, store) -> tuple[list[Change], bool]:
    """(the changes, oldest first; whether any run states an identity field), over `runs` as given: oldest first as
    this console received them, as a pipeline's own list holds them (`overview.pipelines`). Two runs received in the
    same second keep that list's order."""
    ordered = list(runs)
    last: dict[tuple[str, str], tuple[StoredRun, dict[str, str]]] = {}
    out: list[Change] = []
    stated = False
    for run in ordered:
        for where, ident in identities(run, store).items():
            stated = True
            if where in last:
                prev_run, prev = last[where]
                moved = tuple(
                    (f, prev[f], ident[f]) for f in IDENTITY if f in prev and f in ident and prev[f] != ident[f]
                )
                if moved:
                    out.append(Change(prev_run, run, where[0], where[1], moved))
            last[where] = (run, ident)
    return out, stated


def changed_on(runs, store) -> dict[str, str]:
    """{run key: date} of the runs where a change was first seen: the drift page marks them."""
    return {c.after.key: c.date for c in changes(runs, store)[0]}


def _with_fields(template: str, fields: str) -> str:
    """A sentence naming the record's fields: its words escaped, the field names as code, as recorded."""
    before, after = template.split("{fields}")
    return escape(before) + fields + escape(after)


def section(runs, store, href) -> str:
    """The pipeline page's section. `href(run)`: a run's page from the pipeline page."""
    found, stated = changes(runs, store)
    fields = ", ".join(f"<code>{escape(f)}</code>" for f in IDENTITY)
    head = f'<section data-section="fingerprint-change"><h2>{escape(HEADING)}</h2>'
    if not stated:
        return head + f'<p data-fingerprint-change="not-recorded">{_with_fields(NOT_RECORDED, fields)}</p></section>'
    if not found:
        return head + f'<p data-fingerprint-change="none">{_with_fields(NONE, fields)}</p></section>'
    items = []
    for c in found:
        moved = "; ".join(f"<code>{escape(f)}</code> {escape(a)} → {escape(b)}" for f, a, b in c.fields)
        items.append(
            f'<li data-fingerprint-changed="{escape(c.after.key, quote=True)}"><strong>'
            f"{escape(LINE.format(date=c.date))}</strong>: between "
            f'<a href="{escape(href(c.before), quote=True)}">{escape(c.before.run_id)}</a> and '
            f'<a href="{escape(href(c.after), quote=True)}">{escape(c.after.run_id)}</a>, at step '
            f"<code>{escape(c.step)}</code>, <code>{escape(c.name)}</code>: {moved}.</li>"
        )
    return (
        head
        + f'<ul class="plain">{"".join(items)}</ul><p class="nonclaim" data-fingerprint-nonclaim>{escape(NON_CLAIM)}</p>'
        + "</section>"
    )


def mark(date: str) -> str:
    """The drift page's mark on the run where a change was first seen, with its date."""
    return f' <span class="pill neu" data-fingerprint-mark="{escape(date, quote=True)}">{escape(MARK)} on {escape(date)}</span>'
