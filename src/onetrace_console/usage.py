"""Tokens and cost, as recorded: format 0.5's `model_usage` (onetrace 0.8's `docs/format.md`, "What a model call adds
beside its record"), each `{record, input_tokens, output_tokens, total_tokens, cost}` as the provider's response gave
them, in onetrace's words.

Where they are drawn:
- a step's page: one line per model-call record, its model and its tokens;
- a run's case page: per model, the calls and the tokens the records hold;
- a pipeline's page: per model, across its runs, read through the run index (`run_index`), never the store's records;
- a comparison: each run's totals side by side, composing no verdict on them.

The rules:
- a value onetrace marks `not observed` reads "not recorded", never 0, and a total says how many calls recorded none;
- cost is drawn only where a record holds `cost` (`{value, currency}`), summed only within one currency, never across
  currencies, never from a price table; where no record in a view holds one, the cost reads "not recorded", with one
  line on why;
- an entry the verifier fails (`<receipt>: model_usage`) is not drawn from, and its row is shown;
- each section carries `docs/format.md`'s words on what usage does not show.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from onetrace_console.step_kinds import _fail_block, failed, holds_members, prose
from onetrace_console.words import escape

HEADING = "Tokens and cost"
NOT_RECORDED = "not recorded"
#: Why a view with no cost says so: what onetrace records of cost (`docs/format.md`).
NO_COST = "onetrace records cost only where the provider reports it, and no record here holds one."
#: onetrace 0.8's `docs/format.md`, "What it does not show", on usage and cost.
NON_CLAIMS = (
    "Usage and cost are what the provider reported; onetrace does not check them against a bill or a tokenizer. "
    "`cost` is as the provider reports it, never computed from a price list."
)
ROWS = ("model_usage",)
TOKENS = (("input_tokens", "Input tokens"), ("output_tokens", "Output tokens"), ("total_tokens", "Total tokens"))
UNRECORDED = "{n} call{s} with none recorded"
COLUMNS = ("Model", "Calls", "Input tokens", "Output tokens", "Total tokens", "Cost")
NOT_INDEXED = "not indexed for tokens: the run index these pages were drawn with holds none"


def _observed(v) -> str | None:
    """The value of an `observed` member, as written; None where onetrace marks it otherwise (`not observed`)."""
    if isinstance(v, dict) and v.get("status") == "observed" and isinstance(v.get("value"), (str, dict)):
        return v["value"] if isinstance(v["value"], str) else None
    return None


def _cost(v) -> tuple[str, str] | None:
    if isinstance(v, dict) and v.get("status") == "observed" and isinstance(v.get("value"), dict):
        value, currency = v["value"].get("value"), v["value"].get("currency")
        if isinstance(value, str) and isinstance(currency, str):
            return value, currency
    return None


def entries(receipt: dict) -> list[dict]:
    """A step's usage entries, as the index keeps them: the record's name, each token count as written or None where
    not observed, and the cost as (value, currency) or None."""
    out = []
    for e in receipt.get("model_usage") or [] if isinstance(receipt.get("model_usage"), list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("record"), str):
            continue
        out.append(
            {
                "record": e["record"],
                **{k: _observed(e.get(k)) for k, _ in TOKENS},
                "cost": list(c) if (c := _cost(e.get("cost"))) else None,
            }
        )
    return out


def usable(receipt: dict, receipt_file: str, rows: list[dict]) -> tuple[list[dict], list[str]]:
    """(the step's entries, the verifier's FAIL rows on them): no entry where its row FAILs."""
    if not holds_members(receipt):
        return [], []
    fails = failed(rows, receipt_file, ROWS)
    return ([] if fails else entries(receipt)), fails


def _dec(text: str) -> Decimal | None:
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _total(values: list[str | None]) -> str:
    """A sum of the recorded counts, said with how many recorded none; "not recorded" where none did."""
    got = [d for v in values if v is not None and (d := _dec(v)) is not None]
    missing = len(values) - len(got)
    if not got:
        return NOT_RECORDED
    said = str(sum(got, Decimal(0)))
    return said + (f" ({UNRECORDED.format(n=missing, s='' if missing == 1 else 's')})" if missing else "")


def _costs(costs: list) -> str:
    """Cost summed within each currency, each currency on its own; "" where none is recorded."""
    by: dict[str, Decimal] = {}
    for c in costs:
        if c and (d := _dec(c[0])) is not None:
            by[c[1]] = by.get(c[1], Decimal(0)) + d
    return "; ".join(f"{v} {cur}" for cur, v in sorted(by.items()))


def totals(by_model: dict[str, list[dict]]) -> list[dict]:
    """Per model: the calls, each token total, and the cost by currency (or "")."""
    return [
        {
            "model": model,
            "calls": str(len(es)),
            **{k: _total([e.get(k) for e in es]) for k, _ in TOKENS},
            "cost": _costs([e.get("cost") for e in es]),
        }
        for model, es in sorted(by_model.items())
    ]


def _cell(text: str) -> str:
    return f'<td><span class="mono" data-words="record">{escape(text)}</span></td>'


def table(rows_: list[dict], label: str) -> str:
    """The totals as a table; where no model's cost is recorded, its column reads "not recorded", with the line."""
    from onetrace_console.words import scroll_region

    any_cost = any(r["cost"] for r in rows_)
    head = "".join(f'<th scope="col">{escape(c)}</th>' for c in COLUMNS)
    body = "".join(
        "<tr>"
        + "".join(_cell(r[k]) for k in ("model", "calls", "input_tokens", "output_tokens", "total_tokens"))
        + _cell(r["cost"] or NOT_RECORDED)
        + "</tr>"
        for r in rows_
    )
    region = scroll_region(
        f'<table class="usage"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>', label, "usage"
    )
    return region + ("" if any_cost else f'<p data-usage="no-cost">{escape(NO_COST)}</p>')


def _section(kind: str, body: str) -> str:
    return (
        f'<section data-section="{kind}"><h2>{escape(HEADING)}</h2>{body}'
        f'<p class="note" data-section="usage-non-claims">{prose(NON_CLAIMS)}</p></section>'
    )


def models_of(receipt: dict, receipt_file: str, read_file) -> dict[str, str]:
    """Each model-call record's model, as the record reports it (`model.reported`): record name to model."""
    from onetrace_console import model_call

    out = {}
    for o in model_call.outputs(receipt):
        try:
            record = model_call.read_output(receipt_file, o, read_file)
        except model_call.Refused:
            continue
        model = _observed(record.get("model.reported"))
        if model:
            out[str(o["name"])] = model
    return out


def step_section(receipt: dict, receipt_file: str, rows: list[dict], read_file) -> str:
    """A step's page: each model-call record's tokens and cost; nothing where the step holds no `model_usage`."""
    if not holds_members(receipt) or "model_usage" not in receipt:
        return ""
    got, fails = usable(receipt, receipt_file, rows)
    if fails:
        return _section("usage", _fail_block(fails))
    models = models_of(receipt, receipt_file, read_file) if read_file is not None else {}
    items = []
    for e in got:
        said = " · ".join(f"{label}: {e[k] if e[k] is not None else NOT_RECORDED}" for k, label in TOKENS)
        cost = f"{e['cost'][0]} {e['cost'][1]}" if e["cost"] else NOT_RECORDED
        items.append(
            f'<li data-usage-record="{escape(e["record"], quote=True)}">'
            f'<span class="mono" data-words="record">{escape(e["record"])}</span>, model '
            f'<span class="mono" data-words="record">{escape(models.get(e["record"], NOT_RECORDED))}</span>: '
            f'<span data-words="record">{escape(said)} · Cost: {escape(cost)}</span></li>'
        )
    return _section("usage", f'<ul class="plain">{"".join(items)}</ul>')


def run_totals(steps: list[dict], rows: list[dict], read_file) -> tuple[list[dict], list[str]]:
    """A run's totals per model, from its own record, and the verifier's FAIL rows left out of them."""
    by_model: dict[str, list[dict]] = {}
    all_fails: list[str] = []
    for s in steps:
        receipt, f = s["receipt"], s["file"]
        got, fails = usable(receipt, f, rows)
        all_fails += fails
        models = models_of(receipt, f, read_file) if got else {}
        for e in got:
            by_model.setdefault(models.get(e["record"], NOT_RECORDED), []).append(e)
    return totals(by_model), all_fails


def run_section(run, store) -> str:
    """A run's case page: its tokens and cost per model; nothing where no step records usage."""
    from onetrace_console.info_mark import rows_of
    from onetrace_console.pages import _envelope
    from onetrace_console.stage_pages import _files, _read, _steps

    steps = _steps(run, store)
    if not any(holds_members(s["receipt"]) and "model_usage" in s["receipt"] for s in steps):
        return ""
    files = _files(run, store)
    rows_, fails = run_totals(steps, rows_of(_envelope(run, store, required=False)), lambda p: _read(files, store, p))
    body = (table(rows_, HEADING) if rows_ else "") + (_fail_block(fails) if fails else "")
    return _section("usage", body)


def index_totals(index: dict | None, keys: list[str]) -> list[dict] | None:
    """Totals per model across the runs `keys`, from the run index alone; None where the index holds no usage."""
    from onetrace_console import run_index

    if index is None or index.get(run_index.USAGE) != "model_usage":
        return None
    by_model: dict[str, list[dict]] = {}
    for r in index.get("runs") or []:
        if r.get("key") not in keys:
            continue
        for step in r.get("steps") or []:
            for e in step.get("usage") or []:
                by_model.setdefault(str(e.get("model") or NOT_RECORDED), []).append(e)
    return totals(by_model)


def pipeline_section(keys: list[str]) -> str:
    """A pipeline's page: tokens and cost per model across its runs, through the run index the pages are drawn
    with; nothing where none of its runs records usage."""
    from onetrace_console import run_index

    index = run_index.drawn_with()
    if index is None:
        #: Drawn outside the console's drawing of its pages: there is no index to read, and the store is not scanned.
        return ""
    rows_ = index_totals(index, keys)
    if rows_ is None:
        return _section("usage", f'<p data-usage="not-indexed">{escape(NOT_INDEXED)}</p>')
    if not rows_:
        return ""
    return _section("usage", table(rows_, HEADING) + run_index.index_note())


def comparison_section(a, b, store) -> str:
    """A comparison: each run's totals side by side, in onetrace's words; no verdict on them."""
    from onetrace_console.info_mark import rows_of
    from onetrace_console.pages import _envelope
    from onetrace_console.stage_pages import _files, _read, _steps

    sides: list[tuple[str, Any, list[dict] | None]] = []
    for label, run in (("A", a), ("B", b)):
        steps = _steps(run, store)
        if not any(holds_members(s["receipt"]) and "model_usage" in s["receipt"] for s in steps):
            sides.append((label, run, None))
            continue
        files = _files(run, store)
        rows_, _ = run_totals(
            steps, rows_of(_envelope(run, store, required=False)), lambda p, files=files: _read(files, store, p)
        )
        sides.append((label, run, rows_))
    if all(t is None for _, _, t in sides):
        return ""
    body = "".join(
        f'<div data-usage-side="{label}"><h3>Run {label}: <span class="mono" data-words="record">'
        f"{escape(run.run_id)}</span></h3>"
        + (table(t, f"{HEADING}, run {label}") if t else f"<p>{escape(NOT_RECORDED)}</p>")
        + "</div>"
        for label, run, t in sides
    )
    return _section("usage", body)
