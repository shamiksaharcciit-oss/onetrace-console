"""A comparison page laid out so a person debugging two runs meets the answer first, and reaches each next step from
where they are.

Top to bottom:

1. **The header:** "Comparing <run A> against <run B>"; whether both records verify (or what holds instead); whether
   the two runs recorded the same configuration; and **Swap runs**, which does exactly what Compare does here: it
   opens the reverse comparison where the store holds it, and otherwise sends Compare's own request for it, under
   Compare's own limits. A static export, which can send nothing, offers it only where the reverse is held.
2. **The first difference,** as a card: the step, "step N of M · checked from the records", a headline, two or three
   sentences from the records, and the ways on: the text diff, and each run's page at that step. Beside it, **What
   changed here:** the kind of difference, the fields changed, the settings, the model identity and the sizes, each
   read from the records, and "not recorded" where they hold none.
3. **Step by step:** one card per step, SAME, FIRST DIFFERENCE or DOWNSTREAM (or the same again, or couldn't check),
   each with a short reason, each opening that step's row.
4. **Tabs** over the page's existing parts, only those the pair has data for: the text diff (side by side, with an
   inline switch), the kind of change, each run against its pipeline's reference run, the nearness ladder, the spans,
   and the model's rows and choices. Under them, the checks on this pair as commands; a local console runs the two it
   can on the page. Beside the tabs, Explain.
5. **Runs with near inputs,** where the neighbours extra is on (a local console only).

Every value is read from the two runs' records, their kept files and the reports the comparison holds; none is
inferred, no meaning is read into a field's name, and no cause is stated. Equal settings are not an equal environment.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from onetrace_console.words import escape

# ------------------------------------------------------------------------------------------------- the words

COMPARING = "Comparing"
AGAINST = "against"
SWAP = "Swap runs"
BOTH_VERIFY = "Both records verify"
#: A run's record, by its state (`records.state`), where the two do not both verify.
RECORD_STATE = {
    "yes": "verifies",
    "no": "contradicts itself",
    "couldnt-check": "could not be checked",
    "not-checked": "checked without its files",
    "no-verdict": "not checked yet",
}
RECORDS_SAID = "Run A's record {a} · run B's {b}"
SAME_CONFIG = "same configuration"
CONFIG_DIFFERS = "configuration or settings differ at {n} {steps}"
CONFIG_UNKNOWN = "configuration not recorded"

FIRST_LABEL = "First difference"
NO_DIFFERENCE_LABEL = "No difference"
STEP_OF = "step {n} of {m} · checked from the records"
HEADLINE = "The runs first part at"
SAME_HEADLINE = "The runs are the same at every step"
SAME_SAID = "At every step both runs recorded the same outputs, by fingerprint."
SAME_SETTINGS = "The settings recorded differ at {where}: {names}."
#: The sentences, each from the records.
INPUTS_SAME = "Both runs took the same input."
INPUTS_DIFFER = "The runs took different inputs."
STEP_INPUTS_DIFFER = "At {step} the step's own inputs already differ."
OUTPUTS_FIELDS = "At {step} the outputs differ in {fields}."
OUTPUTS_DIFFER = "At {step} the outputs differ."
OUTPUTS_NOT_KEPT = "At {step} the outputs differ by fingerprint; their text was not kept."
AFTER_ALL = "Every step after it differs."
AFTER_SOME = "{n} of the {m} steps after it differ."
AFTER_NONE = "The steps after it are the same again."
SETTINGS_SAME = "The settings recorded at this step are identical."
SETTINGS_DIFFER = "The settings recorded at this step differ: {names}."
SEE_TEXT = "See the text diff"
OPEN_A = "Open run A at this step"
OPEN_B = "Open run B at this step"

HERE_HEADING = "What changed here"
KIND = "Kind of difference"
FIELDS = "Fields changed"
SETTINGS = "Settings"
MODEL = "Model identity"
SIZE = "Size"
NOT_RECORDED = "not recorded"
IDENTICAL = "identical"
#: The kind, from what `first_kind` chose at the step, else from what differs there.
KINDS = {
    "inputs": "inputs",
    "decision": "policy decision",
    "model-call": "model output",
    "model-call-batch": "model call, batch context",
    "output-not-kept": "output, not kept",
    "output": "output",
    "settings": "settings",
}
FIELDS_NOT_KEPT = "not recorded: the output's text was not kept"
FIELDS_NOT_JSON = "not recorded: the output is not JSON"
NO_MODEL_CALL = "no model call recorded at this step"
ONE_MODEL_CALL = "a model call recorded in one run only"
MODEL_DIFFERS = "differs ({field})"
MODEL_NOT_COMPARED = "could not compare"
SIZES_MORE = "{n} outputs, {a} → {b}"

STEPS_HEADING = "Step by step"
STEPS_NOTE = "one verdict per step, against run A"
#: The SDK's verdict on a step, as the card says it, and its reason when the SDK gives none.
MARKS = {
    "same": "Same",
    "FIRST DIFFERENCE": "First difference",
    "downstream": "Downstream",
    "reconverged": "Same again",
    "COULD NOT CHECK": "Couldn't check",
}
REASON_SAME_FIELDS = "input kept · {fields} identical"
REASON_SAME = "inputs identical, by fingerprint"
REASON_FIRST = "output differs · settings {settings}"
REASON_DOWNSTREAM = "differs, after the first difference"
REASON_AGAIN = "the same again, after the first difference"
REASON_COULDNT = "could not be checked"

#: How many output sizes are named before they are summed (`sizes`).
SIZES_NAMED = 3
#: How deep a kept JSON output is read for the fields that differ.
FIELD_DEPTH = 3


# ------------------------------------------------------------------------------------------------- the facts


@dataclass
class Step:
    """One step of the pair, as the SDK's ladder row says it and the two runs' records hold it."""

    index: str
    stage: str
    verdict: str
    reason: str
    a: dict | None = None  # {index, receipt} of run A's step, where held
    b: dict | None = None


@dataclass
class Facts:
    steps: list[Step] = field(default_factory=list)
    first: int | None = None  # the position in `steps` of the first difference
    annotations: dict = field(default_factory=dict)  # {stage: {setting: [a, b]}}
    kind: str = ""  # first_kind's chosen kind at the first difference


def facts(report, annotations: list[dict], comparison, store) -> Facts:
    """The pair's steps from diff's report (`report.ladder`), each matched to its receipt in each run by its stage."""
    from onetrace_console.config_compare import node_id
    from onetrace_console.render import _held, _stage_of
    from onetrace_console.stage_pages import _steps

    def by_name(key: str) -> dict[str, dict]:
        """Each step of the run by its stage's name and by its node id."""
        run = _held(store, key)
        if run is None:
            return {}
        try:
            got = _steps(run, store)
        except Exception:  # noqa: BLE001 - a run that can't be read matches no step
            return {}
        out: dict[str, dict] = {}
        for s in got:
            out.setdefault(_stage_of(s["receipt"]), s)
            try:
                out.setdefault(node_id(s["receipt"]), s)
            except Exception:  # noqa: BLE001 - a receipt without a node id is found by its stage
                pass
        return out

    sa, sb = by_name(comparison.run_a), by_name(comparison.run_b)
    out = Facts()
    for n, row in enumerate(report.ladder, start=1):
        if hasattr(row, "stage"):
            #: A straight-line pair's row: its step by the stage's name, its row `#step-<index>`.
            stage, index, reason = row.stage, str(row.index), str(row.reason or "")
        else:
            #: A graph-shaped pair's row: its node, its row `#step-<position>`, the SDK's notes on it.
            stage, index, reason = row.node, str(n), "; ".join(row.annotations)
        out.steps.append(Step(index, stage, str(row.verdict), reason, sa.get(stage), sb.get(stage)))
    out.first = next((i for i, s in enumerate(out.steps) if s.verdict == "FIRST DIFFERENCE"), None)
    for a in annotations or []:
        if isinstance(a, dict) and isinstance(a.get("differs"), dict):
            out.annotations.setdefault(str(a.get("stage", "")), {}).update(a["differs"])
    if out.first is not None:
        from onetrace_console import first_kind

        try:
            got = first_kind.at_stage(out.steps[out.first].stage, comparison, store)
        except Exception:  # noqa: BLE001 - no kind read is no kind said
            got = None
        out.kind = got[0] if got else ""
    return out


def _kept(store, run_key: str, digest) -> bytes | None:
    """The bytes the run kept under `digest` (an output's or an input's), verified by the store on the way out; None
    where the run did not keep them."""
    from onetrace_console.render import _held

    run = _held(store, run_key)
    if run is None or not isinstance(digest, str):
        return None
    hexd = digest.split(":", 1)[-1]
    if not re.fullmatch(r"[0-9a-f]{64}", hexd) or not any(k == hexd for _p, k in run.listing):
        return None
    try:
        return store.get(hexd)
    except Exception:  # noqa: BLE001 - bytes that can't be read are not kept, as far as this page says
        return None


def _json(b: bytes | None):
    if b is None:
        return None
    from onetrace_console.bounded_json import TooDeep, load_json_bounded

    try:
        return load_json_bounded(b.decode("utf-8"), "a kept file", "show")
    except (UnicodeDecodeError, ValueError, TooDeep):
        return None


def changed_fields(a, b, at: str = "", depth: int = FIELD_DEPTH) -> list[str]:
    """The paths at which two JSON objects differ, by key, in A's order then B's: a key whose values are both objects
    is read into, `depth` levels down; any other difference is its path."""
    out: list[str] = []
    for k in list(dict.fromkeys([*a.keys(), *b.keys()])):
        path = f"{at}.{k}" if at else str(k)
        if k not in a or k not in b:
            out.append(path)
        elif isinstance(a[k], dict) and isinstance(b[k], dict) and depth > 1:
            out += changed_fields(a[k], b[k], path, depth - 1)
        elif a[k] != b[k]:
            out.append(path)
    return out


def _outputs(receipt: dict | None) -> list[dict]:
    return [o for o in (receipt or {}).get("outputs") or [] if isinstance(o, dict)]


def output_fields(step: Step, comparison, store) -> tuple[list[str] | None, str]:
    """(the output fields that differ, or None, with why none are named) at a step whose outputs both runs kept as
    JSON objects, paired by name."""
    if step.a is None or step.b is None:
        return None, FIELDS_NOT_KEPT
    outs_b = {str(o.get("name")): o for o in _outputs(step.b["receipt"])}
    found, kept_any, json_all = [], False, True
    for oa in _outputs(step.a["receipt"]):
        ob = outs_b.get(str(oa.get("name")))
        if ob is None or oa.get("digest") == ob.get("digest"):
            continue
        ba, bb = _kept(store, comparison.run_a, oa.get("digest")), _kept(store, comparison.run_b, ob.get("digest"))
        if ba is None or bb is None:
            continue
        kept_any = True
        ja, jb = _json(ba), _json(bb)
        if not (isinstance(ja, dict) and isinstance(jb, dict)):
            json_all = False
            continue
        found += changed_fields(ja, jb)
    if not kept_any:
        return None, FIELDS_NOT_KEPT
    if not found and not json_all:
        return None, FIELDS_NOT_JSON
    return list(dict.fromkeys(found)), ""


def _size(n) -> str:
    try:
        v = int(str(n))
    except ValueError:
        return NOT_RECORDED
    for unit, size in (("MB", 1_000_000), ("kB", 1_000)):
        if v >= size:
            return f"{v / size:.1f} {unit}"
    return f"{v} B"


def sizes(step: Step) -> tuple[str, list[tuple[str, str, str]]]:
    """(the line, [(name, A's size, B's size)]) of the step's outputs, by name: each named up to `SIZES_NAMED`;
    beyond that, their count and each run's total, the list behind it."""
    outs_a = {str(o.get("name")): o for o in _outputs(step.a and step.a["receipt"])}
    outs_b = {str(o.get("name")): o for o in _outputs(step.b and step.b["receipt"])}
    names = list(dict.fromkeys([*outs_a, *outs_b]))
    rows = [
        (
            n,
            _size(outs_a[n].get("bytes")) if n in outs_a else NOT_RECORDED,
            _size(outs_b[n].get("bytes")) if n in outs_b else NOT_RECORDED,
        )
        for n in names
    ]
    if not rows:
        return NOT_RECORDED, []
    if len(rows) == 1:
        return f"{rows[0][1]} → {rows[0][2]}", rows
    if len(rows) <= SIZES_NAMED:
        return " · ".join(f"{n} {a} → {b}" for n, a, b in rows), rows

    def total(outs: dict) -> str:
        try:
            return _size(sum(int(str(o.get("bytes"))) for o in outs.values()))
        except ValueError:
            return NOT_RECORDED

    return SIZES_MORE.format(n=len(rows), a=total(outs_a), b=total(outs_b)), rows


def model_identity(step: Step, comparison, store) -> str:
    """The model identity at the step: identical, or the first identity field that differs, where both runs hold a
    model-call record there; otherwise what the records hold instead."""
    from onetrace_console import model_call as mc

    def has(side: dict | None) -> bool:
        try:
            return bool(side and mc.outputs(side["receipt"]))
        except Exception:  # noqa: BLE001 - a record that can't be read is none here
            return False

    on = (has(step.a), has(step.b))
    if not any(on):
        return NO_MODEL_CALL
    if not all(on):
        return ONE_MODEL_CALL
    from onetrace_console import first_kind, model_call_compare

    results = model_call_compare.compared(comparison, store, step.stage)
    if not results:
        return MODEL_NOT_COMPARED
    for r in results:
        if r.result == "diverged" and first_kind.model_kind(r.first) == first_kind.IDENTITY:
            return MODEL_DIFFERS.format(field=r.first)
    if all(r.result == "could not compare" for r in results):
        return MODEL_NOT_COMPARED
    return IDENTICAL


def _inputs_kept_fields(step: Step, comparison, store) -> list[str] | None:
    """The fields of the step's inputs both runs kept as JSON objects and recorded alike, or None."""
    if step.a is None or step.b is None:
        return None
    ins_b = {str(i.get("name")): i for i in (step.b["receipt"].get("inputs") or []) if isinstance(i, dict)}
    names: list[str] = []
    for ia in step.a["receipt"].get("inputs") or []:
        if not isinstance(ia, dict) or str(ia.get("name", "")).startswith("receipt:"):
            continue
        ib = ins_b.get(str(ia.get("name")))
        if ib is None or ib.get("digest") != ia.get("digest"):
            return None
        got = _json(_kept(store, comparison.run_a, ia.get("digest")))
        if isinstance(got, dict):
            names += [str(k) for k in got]
    return list(dict.fromkeys(names)) or None


def _first_inputs_same(f: Facts) -> bool | None:
    """Whether the pair's first step recorded the same inputs, by fingerprint; None where it can't be read."""
    if not f.steps or f.steps[0].a is None or f.steps[0].b is None:
        return None

    def ins(side: dict) -> list:
        return sorted(
            (str(i.get("name")), str(i.get("digest")))
            for i in side["receipt"].get("inputs") or []
            if isinstance(i, dict) and not str(i.get("name", "")).startswith("receipt:")
        )

    return ins(f.steps[0].a) == ins(f.steps[0].b)


# ------------------------------------------------------------------------------------------------- the header


def config_badge(comparison, store, settings: dict | None = None) -> str:
    """ "same configuration", with the instrument's version where both runs record one and it is the same, where no
    step's configuration fingerprint differs and diff's report names no setting that differs (`settings`, {stage:
    {setting: [a, b]}}); otherwise at how many steps either does."""
    from onetrace_console.render import _receipts_in_order, _stage_of

    a, b = _receipts_in_order(comparison.run_a, store), _receipts_in_order(comparison.run_b, store)
    if not a or not b:
        return CONFIG_UNKNOWN
    by_b = {_stage_of(r): r for r in b}
    differ, versions = 0, set()
    for ra in a:
        rb = by_b.get(_stage_of(ra))
        ia, ib = (ra.get("instrument") or {}), ((rb or {}).get("instrument") or {})
        if rb is None or ia.get("config_digest") != ib.get("config_digest") or (settings or {}).get(_stage_of(ra)):
            differ += 1
        versions |= {str(x) for x in (ia.get("version"), ib.get("version")) if x}
    if differ:
        return CONFIG_DIFFERS.format(n=differ, steps="step" if differ == 1 else "steps")
    return SAME_CONFIG + (f" · {versions.pop()}" if len(versions) == 1 else "")


def records_badge(comparison, store) -> tuple[str, str]:
    """(the words, the tone) of what the two runs' records establish."""
    from onetrace_console import records
    from onetrace_console.render import _held

    states = []
    for k in (comparison.run_a, comparison.run_b):
        run = _held(store, k)
        states.append(records.state(run, store) if run is not None else records.NOT_CHECKED)
    if all(s == "yes" for s in states):
        return BOTH_VERIFY, "ok"
    tone = "bad" if any(s in ("no", "couldnt-check") for s in states) else "neu"
    return RECORDS_SAID.format(a=RECORD_STATE.get(states[0], states[0]), b=RECORD_STATE.get(states[1], states[1])), tone


def swap(comparison, store, *, public: bool, export: bool) -> str:
    """Swap runs: the reverse comparison where the store holds it; otherwise Compare's own request for it, the same
    form Compare sends on this console (a public one's under its per-minute limit, a local one's with its CSRF token);
    nothing on a static export, which can send no request."""
    from onetrace_console.render import _tag
    from onetrace_console.what_changed import held

    reverse = held(store, comparison.run_b, comparison.run_a)
    if reverse is not None and reverse.key != comparison.key:
        return f'<a class="btn-secondary" data-swap="held" href="{escape(reverse.key)}.html">{escape(SWAP)}</a>'
    if export:
        return ""
    from onetrace_console.frame import CSRF_SLOT

    slot = "" if public else CSRF_SLOT
    return (
        f'<form method="post" action="/compare" data-swap="ask" class="swap">{slot}'
        f'<input type="hidden" name="a" value="{_tag(comparison.run_b)}">'
        f'<input type="hidden" name="b" value="{_tag(comparison.run_a)}">'
        f'<button class="btn-secondary" type="submit" data-busy="Comparing…" data-busy-wait="the comparison">'
        f"{escape(SWAP)}</button></form>"
    )


def head(comparison, store, *, public: bool, export: bool, names: bool = True, settings: dict | None = None) -> str:
    """The header line: the pair, what their records establish, their configuration, Swap. It is the page's pair
    line (`data-section="pair"`); a graph-shaped pair names its runs in its own A/B line, so its header names
    them not again (`names=False`)."""
    from onetrace_console.words import run_named

    said, tone = records_badge(comparison, store)
    pair = (
        f'<p class="pair-line"><span class="eyebrow">{escape(COMPARING)}</span> '
        f'<span class="run-chip">{run_named(store, comparison.run_a)}</span> '
        f'<span class="against">{escape(AGAINST)}</span> '
        f'<span class="run-chip">{run_named(store, comparison.run_b)}</span></p>'
        if names
        else ""
    )
    return (
        f'<div class="compare-head" data-section="{"pair" if names else "compare-head"}">'
        + pair
        + f'<p class="badges"><span class="badge" data-badge="records" data-tone="{tone}">{escape(said)}</span> '
        f'<span class="badge" data-badge="config">{escape(config_badge(comparison, store, settings))}</span> '
        f"{swap(comparison, store, public=public, export=export)}</p></div>"
    )


# ------------------------------------------------------------------------------------------------- the first card


def _code_list(names: list[str]) -> str:
    return ", ".join(f"<code>{escape(n)}</code>" for n in names)


def _step_href(store, run_key: str, side: dict | None) -> str:
    from onetrace_console.stage_pages import stage_page

    if side is None or not str(side.get("index", "")).isdigit():
        return ""
    return f"../runs/{escape(run_key)}/{stage_page(str(side['index']))}"


def sentences(f: Facts, comparison, store) -> str:
    """Two or three sentences at the first difference, each from the records."""
    step = f.steps[f.first]  # type: ignore[index]  # called only with a first difference
    code = f"<code>{escape(step.stage)}</code>"
    out = []
    same = _first_inputs_same(f)
    if f.first and same is True:
        out.append(escape(INPUTS_SAME))
    elif same is False and f.first:
        out.append(escape(INPUTS_DIFFER))
    if f.kind == "inputs":
        out.append(STEP_INPUTS_DIFFER.format(step=code))
    else:
        fields, why = output_fields(step, comparison, store)
        if fields:
            out.append(OUTPUTS_FIELDS.format(step=code, fields=_code_list(fields[:4])))
        elif why == FIELDS_NOT_KEPT:
            out.append(OUTPUTS_NOT_KEPT.format(step=code))
        else:
            out.append(OUTPUTS_DIFFER.format(step=code))
    after = f.steps[f.first + 1 :]  # type: ignore[operator]  # a first difference is a position
    if after:
        differ = sum(1 for s in after if s.verdict == "downstream")
        out.append(
            escape(
                AFTER_ALL
                if differ == len(after)
                else (AFTER_SOME.format(n=differ, m=len(after)) if differ else AFTER_NONE)
            )
        )
    settings = f.annotations.get(step.stage)
    out.append(SETTINGS_DIFFER.format(names=_code_list(list(settings))) if settings else escape(SETTINGS_SAME))
    return " ".join(out)


def first_card(f: Facts, comparison, store, *, text_tab: bool) -> str:
    """The first-difference card and, beside it, What changed here; for a pair the same at every step, that."""
    total = len(f.steps)
    if f.first is None:
        return (
            '<div class="compare-first" data-section="compare-first" data-state="same">'
            '<section class="first-card" data-first="none">'
            f'<p class="card-label"><span class="mark" data-mark="same">{escape(NO_DIFFERENCE_LABEL)}</span></p>'
            f'<h2>{escape(SAME_HEADLINE)}</h2><p data-section="said">{escape(SAME_SAID)}{_same_settings(f)}</p>'
            "</section></div>"
        )
    step = f.steps[f.first]
    buttons = []
    if text_tab:
        buttons.append(f'<a class="btn-primary" href="#compare-tab-text" data-open-tab="text">{escape(SEE_TEXT)}</a>')
    for words, key, side in ((OPEN_A, comparison.run_a, step.a), (OPEN_B, comparison.run_b, step.b)):
        href = _step_href(store, key, side)
        if href:
            buttons.append(f'<a class="btn-secondary" href="{href}">{escape(words)}</a>')
    card = (
        '<section class="first-card" data-first="step">'
        f'<p class="card-label"><span class="mark" data-mark="first">{escape(FIRST_LABEL)}</span> '
        f'<span class="note">{escape(STEP_OF.format(n=f.first + 1, m=total))}</span></p>'
        f'<h2 data-section="headline">{escape(HEADLINE)} <code>{escape(step.stage)}</code></h2>'
        f'<p data-section="said">{sentences(f, comparison, store)}</p>'
        f'<p class="actions">{" ".join(buttons)}</p></section>'
    )
    return (
        '<div class="compare-first" data-section="compare-first" data-state="first">'
        + card
        + what_changed_here(f, comparison, store)
        + "</div>"
    )


def _same_settings(f: Facts) -> str:
    """Where every step is the same, the settings diff's report names as differing, and at which steps; "" with none."""
    if not f.annotations:
        return ""
    where = ", ".join(f"<code>{escape(s)}</code>" for s in f.annotations)
    names = _code_list(list(dict.fromkeys(k for d in f.annotations.values() for k in d)))
    return " " + SAME_SETTINGS.format(where=where, names=names)


def what_changed_here(f: Facts, comparison, store) -> str:
    step = f.steps[f.first]  # type: ignore[index]  # called only with a first difference
    fields, why = output_fields(step, comparison, store)
    settings = f.annotations.get(step.stage)
    line, rows = sizes(step)
    kind = KINDS.get(f.kind) or (KINDS["output"] if fields or why != FIELDS_NOT_KEPT else KINDS["output"])
    size = escape(line)
    if len(rows) > SIZES_NAMED:
        size = (
            f'<details><summary>{escape(line)}</summary><ul class="plain">'
            + "".join(f"<li><code>{escape(n)}</code> {escape(a)} → {escape(b)}</li>" for n, a, b in rows)
            + "</ul></details>"
        )
    items = (
        (KIND, escape(kind)),
        (FIELDS, _code_list(fields) if fields else escape(why or NOT_RECORDED)),
        (SETTINGS, escape(IDENTICAL) if not settings else _code_list(list(settings))),
        (MODEL, escape(model_identity(step, comparison, store))),
        (SIZE, size),
    )
    return (
        f'<aside class="changed-here" data-section="changed-here" aria-labelledby="changed-here-h">'
        f'<h2 id="changed-here-h">{escape(HERE_HEADING)}</h2><dl>'
        + "".join(f"<dt>{escape(k)}</dt><dd>{v}</dd>" for k, v in items)
        + "</dl></aside>"
    )


# ------------------------------------------------------------------------------------------------- the steps


def step_reason(step: Step, f: Facts, comparison, store) -> str:
    if step.verdict == "same":
        names = _inputs_kept_fields(step, comparison, store)
        return REASON_SAME_FIELDS.format(fields=", ".join(names[:3])) if names else REASON_SAME
    if step.verdict == "FIRST DIFFERENCE":
        return REASON_FIRST.format(settings="differ" if f.annotations.get(step.stage) else IDENTICAL)
    if step.verdict == "downstream":
        return REASON_DOWNSTREAM
    if step.verdict == "reconverged":
        return REASON_AGAIN
    return step.reason or REASON_COULDNT


def step_cards(f: Facts, comparison, store) -> str:
    """One card per step, each its verdict in words and a short reason, each opening that step's row."""
    marks = {
        "same": "same",
        "FIRST DIFFERENCE": "first",
        "downstream": "downstream",
        "reconverged": "again",
        "COULD NOT CHECK": "couldnt",
    }
    cards = "".join(
        f'<li data-mark="{marks.get(s.verdict, "couldnt")}"><a href="#step-{escape(s.index)}">'
        f'<span class="step-name"><code>{escape(s.stage)}</code></span> '
        f'<span class="mark" data-mark="{marks.get(s.verdict, "couldnt")}">{escape(MARKS.get(s.verdict, s.verdict))}</span>'
        f'<span class="reason">{escape(step_reason(s, f, comparison, store))}</span></a></li>'
        for s in f.steps
    )
    return (
        '<section class="step-cards" data-section="step-cards" aria-labelledby="step-cards-h">'
        f'<h2 id="step-cards-h">{escape(STEPS_HEADING)} <span class="note">{escape(STEPS_NOTE)}</span></h2>'
        f'<ol class="cards">{cards}</ol></section>'
    )


# ------------------------------------------------------------------------------------------------- the tabs

TABS = {
    "text": "Text diff",
    "kind": "Kind of change",
    "reference": "Against the reference",
    "nearness": "Nearness ladder",
    "spans": "Spans",
    "model": "Model rows and choices",
}
TABS_LABEL = "This comparison's parts"
SIDE_BY_SIDE = "Side by side"
INLINE = "Inline"
TEXT_CAPTION = "Output of {step}, kept by both runs"
TEXT_FIELDS = " · {n} {fields}"
FIELD_DIFFERS, FIELDS_DIFFER = "field differs", "fields differ"
CHECKS = "Checks on this pair"
RUN_HERE = "Run on this page"
REPRODUCE_NOTE = "To copy: re-running a pipeline needs its own code and environment, which this console does not hold."
REFERENCE_A = "Run A against its pipeline's reference run"
REFERENCE_B = "Run B against its pipeline's reference run"
EXPLAIN_HEADING = "Explain"
EXPLAIN_PUBLIC = "Explain runs on a local console."
NEAR_HEADING = "Runs with near inputs"
NEAR_NOTE = "same configuration · the embedder's reading, not a verdict"
NEAR_ONLY = "Only runs of the same configuration are listed."
NEAR_ALL = "See all runs of this pipeline"
SIMILARITY = "similarity"
COMPARE = "Compare"

#: The tabs, the inline switch and the "See the text diff" button: a list of links to the panels, read without
#: script; with it, a tablist (arrow keys, Home and End), one panel shown. Named by its hash in every console's policy
#: (`public.inline_scripts`).
TABS_SCRIPT = (
    "<script>(function(){var l=document.querySelector('[data-compare-tabs]');if(!l)return;"
    "var tabs=[].slice.call(l.querySelectorAll('a[data-tab]'));l.setAttribute('role','tablist');"
    "function pick(t,f){tabs.forEach(function(x){var on=x===t,p=document.getElementById(x.getAttribute('aria-controls'));"
    "x.setAttribute('aria-selected',on?'true':'false');x.tabIndex=on?0:-1;if(p)p.hidden=!on});if(f)t.focus()}"
    "tabs.forEach(function(t,i){t.setAttribute('role','tab');t.setAttribute('aria-controls',t.getAttribute('href').slice(1));"
    "var p=document.getElementById(t.getAttribute('aria-controls'));if(p){p.setAttribute('role','tabpanel');"
    "p.setAttribute('aria-labelledby',t.id);p.tabIndex=0}"
    "t.addEventListener('click',function(e){e.preventDefault();pick(t,false)});"
    "t.addEventListener('keydown',function(e){var k=e.key,j=k==='ArrowRight'?i+1:k==='ArrowLeft'?i-1:"
    "k==='Home'?0:k==='End'?tabs.length-1:null;if(j===null)return;e.preventDefault();"
    "pick(tabs[(j+tabs.length)%tabs.length],true)})});pick(tabs[0],false);"
    "[].forEach.call(document.querySelectorAll('a[data-open-tab]'),function(a){a.addEventListener('click',function(e){"
    "var t=document.getElementById('compare-tabbtn-'+a.getAttribute('data-open-tab'));if(!t)return;e.preventDefault();"
    "pick(t,false);t.scrollIntoView({block:'start'});t.focus()})});"
    "var v=document.querySelector('[data-diff-views]');if(!v)return;"
    "var bs=[].slice.call(v.querySelectorAll('button[data-view]'));v.hidden=false;"
    "function show(n){bs.forEach(function(b){var on=b.getAttribute('data-view')===n;"
    "b.setAttribute('aria-pressed',on?'true':'false');"
    "var p=document.querySelector('[data-diff-view=\"'+b.getAttribute('data-view')+'\"]');if(p)p.hidden=!on})}"
    "bs.forEach(function(b){b.addEventListener('click',function(){show(b.getAttribute('data-view'))})});"
    "show('side')})()</script>"
)


def _marked_line(line: dict, side: str) -> str:
    """One line of the SDK's text diff, its changed spans marked; `side` is "baseline" or "candidate"."""
    text = str(line.get("text", ""))
    spans = sorted((int(a), int(b)) for a, b in line.get("spans") or [] if str(a).isdigit() and str(b).isdigit())
    out, at = [], 0
    for a, b in spans:
        if a < at or b > len(text):
            continue
        out.append(escape(text[at:a]) + f'<mark data-side="{side}">{escape(text[a:b])}</mark>')
        at = b
    out.append(escape(text[at:]))
    return "".join(out)


def side_by_side(doc: dict, step: str) -> str:
    """The SDK's text diff of `step`'s outputs, each output's two sides beside each other: run A's lines (same and
    removed) on the left, run B's (same and added) on the right, the changed spans marked as the SDK marked them.
    "" where the text diff shows no such step or no text there."""
    node = next(
        (n for n in doc.get("nodes", []) if str(n.get("node", "")).split("#", 1)[0] == step),
        None,
    )
    if not doc.get("shown") or node is None:
        return ""
    blocks = []
    for o in node.get("outputs") or []:
        if o.get("kind") != "text" or not o.get("hunks"):
            continue
        cols: dict[str, list[tuple[str, dict]]] = {"baseline": [], "candidate": []}
        for h in o["hunks"]:
            for ln in h.get("lines") or []:
                op = ln.get("op")
                if op in (" ", "-"):
                    cols["baseline"].append((op, ln))
                if op in (" ", "+"):
                    cols["candidate"].append((op, ln))

        def col(side: str, name: str, cols: dict[str, list[tuple[str, dict]]] = cols) -> str:
            rows = "".join(
                f'<span class="ln" data-op="{"same" if op == " " else ("removed" if op == "-" else "added")}">'
                f"{_marked_line(ln, side)}</span>"
                for op, ln in cols[side]
            )
            return (
                f'<div class="diff-col" data-side="{side}"><p class="col-head">{escape(name)}</p>'
                f'<pre class="diff-text">{rows}</pre></div>'
            )

        blocks.append(
            f'<div class="side-by-side" data-output="{escape(str(o.get("name", "")))}">'
            f'<p class="note"><code>{escape(str(o.get("name", "")))}</code></p>'
            + col("baseline", "A")
            + col("candidate", "B")
            + "</div>"
        )
    return "".join(blocks)


def checks(comparison, store, step: str | None, *, local: bool) -> str:
    """The checks on this pair, as commands: the text diff and localize at the first difference, and the
    counterfactual re-run to copy. A local console runs the first two on the page; no console runs the third."""
    from onetrace_console.frame import CSRF_SLOT
    from onetrace_console.render import DIFF, LOCALIZE, typed_command

    if step is None:
        return ""
    import shlex

    from onetrace_console.render import _held

    def folder(key: str) -> str:
        run = _held(store, key)
        return shlex.quote(f"runs/{run.run_id if run is not None and run.run_id else key[:12]}")

    q = shlex.quote(step)
    rows = [
        ("text", typed_command(comparison, store, DIFF, text=True) + f" --stage {q}"),
        ("for", typed_command(comparison, store, LOCALIZE) + f" --for {q}"),
    ]
    items = []
    for check, command in rows:
        run = (
            f'<form method="post" action="/compare/check" class="run-here" data-check="{check}">{CSRF_SLOT}'
            f'<input type="hidden" name="key" value="{escape(comparison.key)}">'
            f'<input type="hidden" name="check" value="{check}">'
            f'<button class="btn-secondary" type="submit" data-busy="Running…" data-busy-wait="the check">'
            f"{escape(RUN_HERE)}</button></form>"
            if local
            else ""
        )
        items.append(f'<li data-check="{check}"><code>{escape(command)}</code> {run}</li>')
    reproduce = f"onetrace reproduce {folder(comparison.run_a)} --substitute {q} --from {folder(comparison.run_b)}"
    items.append(
        f'<li data-check="reproduce"><code>{escape(reproduce)}</code> '
        f'<span class="note">{escape(REPRODUCE_NOTE)}</span></li>'
    )
    return (
        f'<div class="checks" data-section="pair-checks"><h3>{escape(CHECKS)}</h3>'
        f'<ul class="plain">{"".join(items)}</ul><div data-check-result></div></div>'
    )


def text_panel(comparison, store, f: Facts, text_block: str, *, local: bool) -> str:
    """The Text diff tab: the first difference's outputs side by side with the inline switch, where the text diff
    shows them; the comparison's whole text diff, inline, as before; then the checks."""
    from onetrace_console.compare import text_diff_raw
    from onetrace_console.textdiff_view import TextDiffUnreadable, read_textdiff

    step = f.steps[f.first].stage if f.first is not None else None
    side = ""
    if step is not None:
        found = text_diff_raw(comparison, store)
        if found is not None:
            try:
                side = side_by_side(read_textdiff(found[0]), step)
            except TextDiffUnreadable:
                side = ""
    if not side:
        return text_block + checks(comparison, store, step, local=local)
    fields, _why = output_fields(f.steps[f.first], comparison, store)  # type: ignore[index]  # step is set
    caption = TEXT_CAPTION.format(step=f"<code>{escape(step)}</code>") + (
        TEXT_FIELDS.format(n=len(fields), fields=FIELD_DIFFERS if len(fields) == 1 else FIELDS_DIFFER) if fields else ""
    )
    switch = (
        f'<div class="view-switch" data-diff-views hidden role="group" aria-label="{escape(TABS["text"])}">'
        f'<button type="button" class="btn-secondary" data-view="side" aria-pressed="true">{escape(SIDE_BY_SIDE)}</button>'
        f'<button type="button" class="btn-secondary" data-view="inline" aria-pressed="false">{escape(INLINE)}</button>'
        "</div>"
    )
    return (
        f'<div class="text-head"><p>{caption}</p>{switch}</div>'
        f'<div data-diff-view="side">{side}</div>'
        f'<div data-diff-view="inline">{text_block}</div>' + checks(comparison, store, step, local=local)
    )


def reference_panel(comparison, store) -> str:
    """Each run against its pipeline's reference run (`config_compare`), as its own page shows it; "" where neither
    can be drawn."""
    from onetrace_console import config_compare
    from onetrace_console.render import _held

    out = []
    for words, key in ((REFERENCE_A, comparison.run_a), (REFERENCE_B, comparison.run_b)):
        run = _held(store, key)
        if run is None:
            continue
        try:
            drawn = config_compare.section(run, store, up="../")
        except Exception:  # noqa: BLE001 - a run that can't be read is left out here
            drawn = ""
        if drawn:
            out.append(
                f'<div data-reference-side="{"a" if key == comparison.run_a else "b"}"><h3>{escape(words)}</h3>{drawn}</div>'
            )
    return "".join(out)


def tabs(panels: list[tuple[str, str]]) -> str:
    """The tabs over `panels` ([(tab, its HTML)]), only those with content, the first open first."""
    shown = [(k, html) for k, html in panels if html and html.strip()]
    if not shown:
        return ""
    links = "".join(
        f'<a href="#compare-tab-{k}" id="compare-tabbtn-{k}" data-tab="{k}">{escape(TABS[k])}</a>' for k, _ in shown
    )
    bodies = "".join(
        f'<section class="tab-panel" id="compare-tab-{k}" data-tab-panel="{k}">'
        f'<h2 class="visually-hidden">{escape(TABS[k])}</h2>{html}</section>'
        for k, html in shown
    )
    return (
        '<section class="compare-tabs" data-section="compare-tabs">'
        f'<nav class="tablist" data-compare-tabs aria-label="{escape(TABS_LABEL)}">{links}</nav>'
        f"{bodies}{TABS_SCRIPT}</section>"
    )


def explain_aside(panel: str, *, public: bool) -> str:
    """Explain beside the tabs: the console's panel on a local console. On a public one, the panel as a public page
    draws it (the kept readings, read-only, each labelled AI-generated with its time; or that none is kept), then that
    Explain runs on a local console: no step, no button, nothing sent."""
    if public:
        return (
            '<aside class="compare-explain" data-section="explain-aside">'
            f'{panel}<p class="note" data-explain="public">{escape(EXPLAIN_PUBLIC)}</p></aside>'
        )
    return f'<aside class="compare-explain" data-section="explain-aside">{panel}</aside>' if panel else ""


def _near_quote(store, other, step: str, name: str) -> str:
    """The near run's kept input `name` at `step`, as a short quote: a JSON object of one string value as that value,
    else the text; "" where it was not kept or is not text."""
    from onetrace_console.render import _stage_of
    from onetrace_console.stage_pages import _steps

    try:
        s = next((s for s in _steps(other, store) if _stage_of(s["receipt"]) == step), None)
    except Exception:  # noqa: BLE001 - nothing read, nothing quoted
        return ""
    if s is None:
        return ""
    i = next((i for i in s["receipt"].get("inputs") or [] if isinstance(i, dict) and i.get("name") == name), None)
    raw = _kept(store, other.key, (i or {}).get("digest"))
    if raw is None:
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    got = _json(raw)
    if isinstance(got, dict) and len(got) == 1 and isinstance(next(iter(got.values())), str):
        text = next(iter(got.values()))
    text = " ".join(text.split())
    return text if len(text) <= 80 else text[:79] + "…"


def near_runs(comparison, store) -> str:
    """Run A's runs with near inputs, as cards: where the neighbours extra is on (a local console); "" elsewhere."""
    from onetrace_console import neighbours

    if not neighbours.here():
        return ""
    from onetrace_console.neighbours.nearness import suggestions
    from onetrace_console.neighbours.pages import _number
    from onetrace_console.render import _held
    from onetrace_console.what_changed import held
    from onetrace_console.words import run_named

    run = _held(store, comparison.run_a)
    got = suggestions(run, store) if run is not None else None
    if got is None or not got.rows:
        return ""
    cards = []
    for r in got.rows[:3]:
        c = held(store, r.other.key, run.key) or held(store, run.key, r.other.key)
        act = (
            f'<a href="{escape(c.key)}.html" data-near="open">{escape(COMPARE)}</a>'
            if c is not None
            else (
                f'<button class="btn-secondary" data-busy="Comparing…" data-busy-wait="the comparison" type="button" '
                f'hidden data-compare-post="/compare?a={escape(run.key)}'
                f'&amp;b={escape(r.other.key)}">{escape(COMPARE)}</button><span data-compare-said></span>'
            )
        )
        quote = _near_quote(store, r.other, r.step, r.name)
        cards.append(
            f'<li data-near-run="{escape(r.other.key)}"><a href="../runs/{escape(r.other.key)}/case.html">'
            f"{run_named(store, r.other.key)}</a>"
            + (
                f"<q>{escape(quote)}</q>"
                if quote
                else f'<p class="note"><code>{escape(r.step)}</code> · <code>{escape(r.name)}</code></p>'
            )
            + f'<p class="near-foot"><span class="note">{escape(SIMILARITY)}</span> <strong>{_number(r.near)}</strong> {act}</p></li>'
        )
    from onetrace_console.compare_script import COMPARE_SCRIPT

    script = COMPARE_SCRIPT if any("data-compare-post=" in c for c in cards) else ""
    see_all = _pipeline_href(comparison, store)
    cards.append(
        f'<li class="near-all"><p>{escape(NEAR_ONLY)}</p>'
        + (f'<a href="{escape(see_all)}">{escape(NEAR_ALL)}</a>' if see_all else "")
        + "</li>"
    )
    return (
        '<section class="near-runs" data-section="near-runs" aria-labelledby="near-runs-h">'
        f'<h2 id="near-runs-h">{escape(NEAR_HEADING)} <span class="note">{escape(NEAR_NOTE)}</span></h2>'
        f'<ul class="cards">{"".join(cards)}</ul>{script}</section>'
    )


def _pipeline_href(comparison, store) -> str:
    """The Runs page with run A's pipeline chosen, where both runs are of one pipeline; "" otherwise."""
    from urllib.parse import urlencode

    from onetrace_console.verdicts import pipeline_of

    try:
        pa, pb = (pipeline_of(store.get_run(k), store) for k in (comparison.run_a, comparison.run_b))
    except Exception:  # noqa: BLE001 - a run that can't be read has no pipeline to offer
        return ""
    if pa is None or pb is None or pa.label != pb.label:
        return ""
    return "/runs?" + urlencode([("pipeline", pa.label)])


# ------------------------------------------------------------------------------------------------- run on this page

#: Where a check's last result is kept, beside the comparison's laid-out runs (`explain.folder_of`).
CHECKS_FOLDER = "pair-checks"
RESULT_HEAD = "Ran {command} at {at}: exit {exit}."
RESULT_EMPTY = "It printed nothing."


def first_step(comparison, store) -> str | None:
    """The step at which the comparison's diff report names the first difference, or None."""
    from onetrace_console.render import read_diff

    got = read_diff(comparison, store)
    if got is None:
        return None
    f = facts(got[0], got[1], comparison, store)
    return f.steps[f.first].stage if f.first is not None else None


def check_argv(check: str, step: str) -> list[str] | None:
    """The console's own run of a check at `step`, over the laid-out runs `a` and `b`; None for any other check. Only
    these two, never a command from the request."""
    import sys

    if check == "text":
        return [sys.executable, "-m", "onetrace", "diff", "a", "b", "--text", "--stage", step]
    if check == "for":
        return [sys.executable, "-m", "onetrace", "localize", "a", "b", "--for", step]
    return None


def run_check(comparison, store, check: str) -> dict:
    """Run `check` at the comparison's first difference, in the folder its runs are laid out in, and keep its result
    (the command, when, its exit and its output, the folder's own path left out). Raises ValueError for a check this
    console does not run, or a comparison with no first difference."""
    import subprocess
    from datetime import UTC, datetime

    from onetrace_console import explain
    from onetrace_console.child import utf8_env

    step = first_step(comparison, store)
    argv = check_argv(check, step) if step is not None else None
    if argv is None:
        raise ValueError("this console runs only the text diff and localize at the first difference")
    folder = explain.folder_of(store, comparison.key)
    explain._prepare(comparison, store, folder)
    proc = subprocess.run(argv, cwd=folder, capture_output=True, timeout=explain.TIMEOUT, input=b"", env=utf8_env())
    output = (proc.stdout + proc.stderr).decode("utf-8", "replace").replace(str(folder), ".")
    result = {
        "check": check,
        "command": "onetrace " + " ".join(argv[3:]),
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "exit": str(proc.returncode),
        "output": output,
    }
    kept = folder / CHECKS_FOLDER
    kept.mkdir(parents=True, exist_ok=True)
    (kept / f"{check}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


def kept_results(store, key: str) -> list[dict]:
    """The kept result of each check run on this comparison's page, in the checks' order."""
    from onetrace_console import explain

    try:
        folder = explain.folder_of(store, key) / CHECKS_FOLDER
    except ValueError:
        return []
    out = []
    for check in ("text", "for"):
        f = folder / f"{check}.json"
        if not f.is_file():
            continue
        try:
            got = _json(f.read_bytes())
        except OSError:
            got = None
        if isinstance(got, dict) and all(isinstance(got.get(k), str) for k in ("command", "at", "exit", "output")):
            out.append(got)
    return out


def with_results(page: bytes, store, key: str) -> bytes:
    """A served comparison page with each kept check result where the checks are listed; as it is with none."""
    results = kept_results(store, key)
    marker = b"<div data-check-result></div>"
    if not results or marker not in page:
        return page
    from onetrace_console.words import verbatim

    drawn = "".join(
        f'<div data-check-result-of="{escape(r.get("check", ""))}"><p>'
        + escape(RESULT_HEAD.format(command=r["command"], at=r["at"].replace("T", " "), exit=r["exit"]))
        + "</p>"
        + (
            f'<div class="scroll-x" data-scroll="check-output" tabindex="0" role="region" '
            f'aria-label="{escape(r["command"])}"><pre class="term">{verbatim(r["output"])}</pre></div>'
            if r["output"].strip()
            else f"<p>{escape(RESULT_EMPTY)}</p>"
        )
        + "</div>"
        for r in results
    )
    return page.replace(marker, f'<div data-check-result id="pair-checks-result">{drawn}</div>'.encode(), 1)


# ------------------------------------------------------------------------------------------------- the look

#: The page's own look, in the skin's tokens and both themes. Each verdict says itself in words; its tone is a
#: second cue. At 1024 px and above, What changed here sits beside the card and Explain beside the tabs; below, each
#: stacks under the one before it, in the same order.
COMPARE_PAGE_CSS = """
.cp .compare-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 16px;
  margin:4px 0 12px}
.cp .compare-head p{margin:0;display:flex;flex-wrap:wrap;align-items:center;gap:6px 8px}
.cp .compare-head .eyebrow{font-size:var(--fs-small);font-weight:600;letter-spacing:.04em;text-transform:uppercase;
  color:var(--ink-muted)}
.cp .compare-head .run-chip{padding:2px 8px;border:1px solid var(--line);border-radius:var(--r-ctl);
  background:var(--surface);font-family:var(--font-mono)}
.cp .compare-head .against{color:var(--ink-muted)}
.cp .badge{display:inline-block;padding:3px 10px;border-radius:var(--r-pill);border:1px solid var(--line);
  background:var(--surface);color:var(--ink);font-size:var(--fs-small)}
.cp .badge[data-tone=ok]{background:var(--ok-bg);color:var(--ok-ink);border-color:transparent}
.cp .badge[data-tone=bad]{background:var(--bad-bg);color:var(--bad-ink);border-color:transparent;font-weight:600}
.cp .compare-head form.swap{display:inline;margin:0}
.cp :is(.first-card,.changed-here,.step-cards,.compare-tabs,.compare-explain,.near-runs){background:var(--surface);
  border:1px solid var(--line);border-radius:var(--r-card);padding:18px 20px;margin:0 0 16px;min-width:0}
.cp .compare-first,.cp .compare-main{display:grid;grid-template-columns:minmax(0,1fr);gap:0 16px}
@media (min-width:1024px){.cp .compare-first{grid-template-columns:minmax(0,1fr) minmax(260px,340px)}
.cp .compare-main{grid-template-columns:minmax(0,1fr) minmax(280px,360px);align-items:start}}
.cp .first-card .card-label{display:flex;flex-wrap:wrap;align-items:center;gap:6px 10px;margin:0 0 6px}
.cp .first-card h2{font-size:26px;line-height:1.2;margin:0 0 10px}
.cp .first-card h2 code{color:var(--cc-ink)}
.cp .first-card [data-section=said]{max-width:62ch;margin:0 0 14px;font-size:var(--fs-body);color:var(--ink)}
.cp .first-card .actions{display:flex;flex-wrap:wrap;gap:8px;margin:0}
.cp .mark{display:inline-block;padding:2px 8px;border-radius:var(--r-ctl);font-size:var(--fs-small);font-weight:600;
  letter-spacing:.03em;text-transform:uppercase;background:var(--neu-bg);color:var(--neu-ink)}
.cp .mark[data-mark=first]{background:var(--cc-bg);color:var(--cc-ink)}
.cp .mark:is([data-mark=same],[data-mark=again]){background:var(--ok-bg);color:var(--ok-ink)}
.cp .mark[data-mark=couldnt]{background:var(--bad-bg);color:var(--bad-ink)}
.cp .changed-here h2,.cp .step-cards h2,.cp .near-runs h2,.cp .compare-explain h2{font-size:var(--fs-body);
  font-weight:600;margin:0 0 10px}
.cp .changed-here h2{font-size:var(--fs-small);letter-spacing:.04em;text-transform:uppercase;color:var(--ink-muted)}
.cp .changed-here dl{display:grid;grid-template-columns:minmax(0,auto) minmax(0,1fr);gap:6px 14px;margin:0}
.cp .changed-here dt{color:var(--ink-muted)}
.cp .changed-here dd{margin:0;overflow-wrap:anywhere}
.cp .step-cards h2 .note,.cp .near-runs h2 .note{font-weight:400;color:var(--ink-muted);font-size:var(--fs-small)}
.cp ol.cards,.cp ul.cards{list-style:none;margin:0;padding:0;display:grid;gap:10px;
  grid-template-columns:repeat(auto-fit,minmax(210px,1fr))}
.cp .step-cards li a{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:6px 8px;
  height:100%;box-sizing:border-box;padding:10px 12px;border:1px solid var(--line);border-radius:var(--r-ctl);
  color:var(--ink);text-decoration:none;background:var(--surface)}
.cp .step-cards li[data-mark=first] a{border:2px solid var(--cc-ink);background:var(--cc-bg)}
.cp .step-cards li a:hover .step-name{text-decoration:underline}
.cp .step-cards .reason{flex-basis:100%;font-size:var(--fs-small);color:var(--ink-muted)}
.cp .compare-tabs nav.tablist{display:flex;flex-wrap:wrap;gap:4px 20px;margin:0 0 14px;border-bottom:1px solid var(--line)}
.cp .compare-tabs nav.tablist a{padding:8px 2px;color:var(--ink-muted);text-decoration:none;
  border-bottom:2px solid transparent}
.cp .compare-tabs nav.tablist a[aria-selected=true]{color:var(--ink);border-bottom-color:var(--accent)}
.cp .compare-tabs nav.tablist a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.cp .tab-panel:focus-visible{outline:2px solid var(--accent);outline-offset:4px}
.cp .tab-panel>section{margin-top:0}
.cp .text-head{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;margin:0 0 10px}
.cp .text-head p{margin:0}
.cp .view-switch{display:inline-flex;gap:4px}
.cp .view-switch button[aria-pressed=true]{background:var(--surface-alt);font-weight:600}
.cp .side-by-side{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;margin:0 0 12px}
@media (min-width:768px){.cp .side-by-side{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.cp .side-by-side>.note{grid-column:1/-1}}
.cp .side-by-side>.note{margin:0}
.cp .diff-col{border:1px solid var(--line);border-radius:var(--r-ctl);min-width:0}
.cp .diff-col .col-head{margin:0;padding:6px 10px;border-bottom:1px solid var(--line);background:var(--surface-alt);
  font-size:var(--fs-small);color:var(--ink-muted)}
.cp .diff-col pre.diff-text{margin:0;padding:10px;white-space:pre-wrap;overflow-wrap:anywhere;border:0;
  border-radius:0;background:none;font-family:var(--font-mono);font-size:var(--fs-small)}
.cp .diff-col .ln{display:block}
.cp .diff-col .ln[data-op=removed]{background:var(--bad-bg)}
.cp .diff-col .ln[data-op=added]{background:var(--ok-bg)}
.cp .diff-col mark[data-side=baseline]{background:var(--bad-bg);color:var(--bad-ink);font-weight:600}
.cp .diff-col mark[data-side=candidate]{background:var(--ok-bg);color:var(--ok-ink);font-weight:600}
.cp .checks{border-top:1px solid var(--line-soft);margin-top:14px;padding-top:10px}
.cp .checks h3{font-size:var(--fs-small);color:var(--ink-muted);margin:0 0 6px;font-weight:600}
.cp .checks li{display:flex;flex-wrap:wrap;align-items:center;gap:4px 10px;margin:0 0 6px}
.cp .checks code{overflow-wrap:anywhere}
.cp .checks form.run-here{display:inline;margin:0}
.cp .compare-explain>section{margin:0}
.cp .near-runs li{padding:10px 12px;border:1px solid var(--line);border-radius:var(--r-ctl);min-width:0}
.cp .near-runs li q{display:block;margin:4px 0;color:var(--ink-soft)}
.cp .near-runs .near-foot{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;margin:6px 0 0}
.cp .near-runs li.near-all{display:flex;flex-direction:column;justify-content:center;align-items:center;
  text-align:center;color:var(--ink-muted)}
"""


# ------------------------------------------------------------------------------------------------- the page


def main_row(tabs_html: str, aside: str) -> str:
    if not tabs_html and not aside:
        return ""
    return f'<div class="compare-main" data-section="compare-main">{tabs_html}{aside}</div>'
