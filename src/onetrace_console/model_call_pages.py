"""A model call's own pages, beside its step's page: Overview, Decode steps, Inputs & outputs, Receipt and Compare.

One set of pages for each model-call record a step's receipt names (`model_call.json` is `call-<n>`, `model_call.2.json`
`call-<n>-2`, and on), linked by one row of tabs, plain links with no script, as a comparison's pages are:

- **Overview** (`call-<n>.html`): tiles, each a field of the record (the decode steps, the runtime, the capture's level),
  and the token timeline: one bar a decode step; its height is the chosen token's probability only where the capture
  holds one (a hosted capture's `logprob`), and otherwise every bar is the same and the page says positions only.
- **Decode steps** (`-decode.html`): against a comparison this console holds, the decode step where the chosen tokens
  first differ, both runs side by side, and the top-k candidates there with the run that chose each; probabilities and
  their bars only where the capture holds them.
- **Inputs & outputs** (`-io.html`): the step's inputs and outputs as its page draws them, verified, with a link to each.
- **Receipt** (`-receipt.html`): the call's fields as the record holds them, its badges, how to check it yourself, and
  what it does not say.
- **Compare** (`-compare.html`): the first output-token divergence, every level checked in order, and the decode steps
  around it; the ones after it were generated from different histories.

Only what the record and its steps file hold is drawn, each value beside the field it is read from. What the format
holds nowhere reads "not recorded": a replay of the sampler, a sampling-state or seed digest (unless the record names a
`sampling.seed`), a teacher-forced check, the call's latency and its input token count. No value is filled in. Decode
steps count from 0, as the step page's timeline does.
"""

from __future__ import annotations

import math
import re

from onetrace_console import model_call as mc
from onetrace_console.words import escape, scroll_region

TITLE = "Model call"
TABS = (
    ("", "Overview"),
    ("-decode", "Decode steps"),
    ("-io", "Inputs & outputs"),
    ("-receipt", "Receipt"),
    ("-compare", "Compare"),
)
NOT_RECORDED = "not recorded"
#: The chips of "Every level, checked in order".
SAME, DIFFERS, NOT_RECORDED_CHIP, NOT_COMPARED = "Same", "Differs", "Not recorded", "Not compared"
NO_COMPARISON = "No comparison this console holds names this call on both sides, so nothing is compared here."
POSITIONS_ONLY = (
    "This capture holds no probabilities (a self-hosted steps file holds token ids), so the timeline shows positions "
    "only: every bar is the same height."
)
PROBABILITIES = "Each bar is the chosen token's probability, from the log-probability the provider returned."
NO_STEPS = "No per-step capture was taken for this call, so there is no token timeline."
DIFFERENT_HISTORY = (
    "Tokens after step {n} were generated from different histories, so a match there is not agreement and a mismatch "
    "is not a new finding. No teacher-forced check is recorded, so an independent change behind the first is not ruled "
    "out."
)
SEED_NOTE = "A seed digest identifies the seed; it hides nothing, since common seeds can be guessed."
DOES_NOT_SAY = (
    "That the output is correct, safe or true.",
    "Why the model chose any token.",
    "That a different GPU, driver or runtime would give the same tokens.",
    "When it was recorded, until it is anchored.",
)
CHECK_YOURSELF = (
    "Anyone with the run's exported record can repeat the check, with no account and no network calls, in the run's "
    "folder:"
)
#: The record's fields that make up the call's envelope: what was run, on what, with which settings.
ENVELOPE = (
    "model.reported",
    "model.files_digest",
    "tokenizer.digest",
    "provider.fingerprint",
    "engine.name",
    "engine.version",
    "runtime.torch",
    "runtime.cuda",
    "runtime.gpu_name",
    "runtime.driver",
    "dtype",
    "attention_backend",
    "batch.batch_invariant",
)
SAMPLING = ("sampling.temperature", "sampling.top_p", "sampling.top_k")
STEP_WINDOW = (2, 3)


def value(record: dict, field: str) -> str | None:
    """A field's value where the record states one (observed, declared or contradicted); None otherwise."""
    v = record.get(field)
    if isinstance(v, dict) and "value" in v and not isinstance(v["value"], (list, dict)):
        return str(v["value"])
    return None


def _field(name: str) -> str:
    return f'<code class="field" title="the record field">{escape(name)}</code>'


_HEX = re.compile(r"(?:sha256:)?[0-9a-f]{40,}")


def _shown(v: str | None) -> str:
    """A value as the record holds it; a digest short, its whole value one fold away (`fingerprint_html`)."""
    if v is None:
        return f'<span class="nr">{NOT_RECORDED}</span>'
    if _HEX.fullmatch(v):
        from onetrace_console.viewer.page import fingerprint_html

        return f'<span class="mono">{fingerprint_html(v)}</span>'
    return f'<span class="mono">{escape(v)}</span>'


def base_name(index: str, name: str) -> str:
    """The pages' stem: `call-<n>` for `model_call.json`, `call-<n>-<k>` for `model_call.<k>.json`."""
    middle = name[len("model_call") : -len(".json")]
    return f"call-{index}" + (f"-{middle[1:]}" if middle else "")


# ---- what the steps file holds ----------------------------------------------------------------------------------


def tokens(doc: dict | None) -> list[str] | None:
    """Each decode step's chosen token: the id a self-hosted file holds, the text a hosted one does."""
    if not isinstance(doc, dict):
        return None
    if isinstance(doc.get("token_ids"), list):
        return [str(t) for t in doc["token_ids"]]
    if isinstance(doc.get("steps"), list):
        return [str((s.get("chosen") or {}).get("text", "")) for s in doc["steps"] if isinstance(s, dict)]
    return None


def probabilities(doc: dict | None) -> list[float] | None:
    """Each chosen token's probability, where the capture holds its log-probability (a hosted capture); else None."""
    if not isinstance(doc, dict) or not isinstance(doc.get("steps"), list):
        return None
    out = []
    for s in doc["steps"]:
        try:
            out.append(math.exp(float((s.get("chosen") or {})["logprob"])))
        except (TypeError, KeyError, ValueError, AttributeError):
            return None
    return out


def candidates(doc: dict | None, at: int) -> list[tuple[str, float | None]]:
    """The top-k candidates at a step: (token, probability or None)."""
    if not isinstance(doc, dict):
        return []
    if isinstance(doc.get("top_k_ids"), list) and at < len(doc["top_k_ids"]):
        return [(str(t), None) for t in doc["top_k_ids"][at] or []]
    if isinstance(doc.get("steps"), list) and at < len(doc["steps"]):
        out = []
        for c in doc["steps"][at].get("candidates") or []:
            try:
                p = math.exp(float(c["logprob"]))
            except (TypeError, KeyError, ValueError):
                p = None
            out.append((str(c.get("text", "")), p))
        return out
    return []


def digests(doc: dict | None) -> list[str] | None:
    """An L3 file's logits-row digests, one a step."""
    return [str(d) for d in doc["digests"]] if isinstance(doc, dict) and isinstance(doc.get("digests"), list) else None


def first_differing(a: list | None, b: list | None) -> int | None:
    if a is None or b is None:
        return None
    n = min(len(a), len(b))
    at = next((i for i in range(n) if a[i] != b[i]), None)
    return at if at is not None else (n if len(a) != len(b) else None)


# ---- a held comparison --------------------------------------------------------------------------------------------


class Pair:
    """This call and the same-named call of the same step in a held comparison, as baseline and candidate."""

    def __init__(self, comparison, a: tuple, b: tuple, names: tuple[str, str], this_is_a: bool):
        self.comparison, self.this_is_a = comparison, this_is_a
        (self.ra, self.da), (self.rb, self.db) = a, b
        self.name_a, self.name_b = names
        self.ta, self.tb = tokens(self.da), tokens(self.db)
        self.token_at = first_differing(self.ta, self.tb)
        la, lb = digests(self.da), digests(self.db)
        self.l3 = la is not None and lb is not None
        self.la, self.lb = la, lb
        self.row_at = first_differing(la, lb) if self.l3 else None
        self.compared = min(len(self.ta), len(self.tb)) if self.ta is not None and self.tb is not None else 0

    def command(self) -> str:
        verbs = getattr(self.comparison, "verbs", ()) or ()
        shown = next((v.shown_command for v in verbs if getattr(v, "shown_command", "")), "")
        return shown or "python -m onetrace diff RUN_A RUN_B --text --json --no-follow"


def pairs(run, store, stage: str, name: str, mine: tuple) -> list[Pair]:
    """Every held comparison naming this run whose other run holds a record of the same name at the same step, read."""
    from onetrace_console.model_call_compare import _steps_by_name
    from onetrace_console.render import _held
    from onetrace_console.token_levels import _read

    out = []
    for c in sorted(store.comparisons(), key=lambda c: c.ran_at, reverse=True):
        if run.key not in (c.run_a, c.run_b) or c.run_a == c.run_b:
            continue
        other = _held(store, c.run_b if run.key == c.run_a else c.run_a)
        if other is None:
            continue
        try:
            step = next((s for s in _steps_by_name(other, store) if s["name"] == stage), None)
            if step is None or name not in {str(o["name"]) for o in mc.outputs(step["receipt"])}:
                continue
            theirs = _read(step, name)
        except Exception:  # noqa: BLE001 - an unreadable other side is not compared here
            continue
        from onetrace_console.store import StoreError  # noqa: F401 - the reads above raise it

        this_is_a = run.key == c.run_a
        a, b = (mine, theirs) if this_is_a else (theirs, mine)
        ids = (run.run_id, other.run_id) if this_is_a else (other.run_id, run.run_id)
        out.append(Pair(c, a, b, ids, this_is_a))
    return out


def _chip(word: str, kind: str) -> str:
    return f'<span class="chip call-chip" data-chip="{kind}">{escape(word)}</span>'


#: Same, said over how many of the fields both records hold, where that is fewer than all.
SAME_IN = "Same, in the {n} of {m} fields both records hold"


def _over_both(ra: dict, rb: dict, fields) -> tuple[str, str]:
    """(chip word, kind), comparing only the fields both records state: Differs where any of them differs; Same where
    none does, saying in how many of the fields where that is fewer than all; Not compared where some are stated by
    one record only and none by both; Not recorded where neither states any. A field one record lacks is never read
    as Same, nor as Differs."""
    both = [f for f in fields if value(ra, f) is not None and value(rb, f) is not None]
    if not both:
        either = any(value(ra, f) is not None or value(rb, f) is not None for f in fields)
        return (NOT_COMPARED, "not-compared") if either else (NOT_RECORDED_CHIP, "not-recorded")
    if any(value(ra, f) != value(rb, f) for f in both):
        return DIFFERS, "differs"
    return (SAME, "same") if len(both) == len(fields) else (SAME_IN.format(n=len(both), m=len(fields)), "same")


def _fingerprint(record: dict, quantity: str) -> str | None:
    for f in record.get("fingerprints") or []:
        if isinstance(f, dict) and f.get("quantity") == quantity and isinstance(f.get("value"), dict):
            v = f["value"].get("value")
            return str(v) if v is not None else None
    return None


def levels(p: Pair) -> list[tuple[str, str, str, str]]:
    """Every level, in order: (key, label, chip word, chip kind), and the field each is read from in the label."""

    def by(result: str) -> tuple[str, str]:
        return {
            "same": (SAME, "same"),
            "differs": (DIFFERS, "differs"),
            "not-recorded": (NOT_RECORDED_CHIP, "not-recorded"),
        }[result]

    def one(field: str) -> str:
        va, vb = value(p.ra, field), value(p.rb, field)
        return "not-recorded" if va is None or vb is None else ("same" if va == vb else "differs")

    out = [
        ("input", "The request (input.request_digest)", *by(one("input.request_digest"))),
        ("envelope", "Envelope: model, tokenizer, runtime, settings", *_over_both(p.ra, p.rb, ENVELOPE)),
        ("seed", "Seed (sampling.seed)", *by(one("sampling.seed"))),
        ("input-tokens", "Input tokens (input.token_ids_digest)", *by(one("input.token_ids_digest"))),
    ]
    fa, fb = _fingerprint(p.ra, "prefill-logits"), _fingerprint(p.rb, "prefill-logits")
    prefill = "not-recorded" if fa is None or fb is None else ("same" if fa == fb else "differs")
    out.append(("prefill", "Prefill (a prefill-logits fingerprint)", *by(prefill)))
    out.append(("sampling-state", "First sampling-state difference", NOT_RECORDED_CHIP, "not-recorded"))
    if p.l3:
        logits = (f"Step {p.row_at}", "step") if p.row_at is not None else (SAME, "same")
    else:
        logits = (NOT_COMPARED, "not-compared")
    out.append(("logits", "First logits-row difference (the steps file's digests)", *logits))
    if p.ta is None or p.tb is None:
        token = (NOT_COMPARED, "not-compared")
    else:
        token = (f"Step {p.token_at}", "step") if p.token_at is not None else (SAME, "same")
    out.append(("output-token", "First output-token divergence", *token))
    after = f"After step {p.token_at}, teacher-forced" if p.token_at is not None else "Teacher-forced check"
    out.append(("after", after, NOT_RECORDED_CHIP, "not-recorded"))
    return out


# ---- the pages --------------------------------------------------------------------------------------------------


def _tabs(stem: str, current: str) -> str:
    links = "".join(
        f'<a href="{stem}{suffix}.html"'
        + (' aria-current="page"' if suffix == current else "")
        + f">{escape(label)}</a>"
        for suffix, label in TABS
    )
    return f'<nav class="tabs call-tabs" data-call-tabs aria-label="The model call\'s pages">{links}</nav>'


def _badges(agree: str, signed, anchored) -> str:
    """The call's badges: records agree, as the run's receipt page says it; signed and anchored, each the run page's own
    question with its answer (`stage_pages._BADGES`), in plain words, never the rung's evidence and its markup; and the
    replay, which the format does not record."""
    from onetrace_console.receipt_page import _rung_said
    from onetrace_console.stage_pages import _BADGES

    def said(question: str, rung) -> str:
        return f"{question}: {_rung_said(rung)[0] if rung is not None else NOT_RECORDED}"

    signing, anchoring = _BADGES
    return (
        '<p class="call-badges" data-call-badges>'
        f'<span class="badge" data-badge="agree">{escape(agree)}</span>'
        f'<span class="badge" data-badge="signed">{escape(said(signing, signed))}</span>'
        f'<span class="badge" data-badge="replay">Replay: {NOT_RECORDED}</span>'
        f'<span class="badge" data-badge="anchored">{escape(said(anchoring, anchored))}</span></p>'
    )


def _head(ctx: dict, tab: str, page_title: str) -> str:
    record = ctx["record"]
    model, kind = value(record, "model.reported"), record.get("call.kind")
    crumbs = (
        '<p class="crumbs" data-section="crumbs"><a href="../../executions-all.html">Runs</a>'
        f' / <a href="case.html"><span class="mono">{escape(ctx["run_id"])}</span></a>'
        f' / <a href="{escape(ctx["stage_page"])}">step {escape(ctx["index"])}</a> / {escape(TITLE)}</p>'
    )
    return (
        crumbs
        + f'<h1>{escape(page_title)} <small class="call-model">{_shown(model)}'
        + (f" · {escape(str(kind))}" if isinstance(kind, str) else "")
        + "</small></h1>"
        + f'<p data-section="call-of">{_field("format")} {escape(str(record.get("format", "")))} · '
        f"<code>{escape(ctx['name'])}</code> of step {escape(ctx['index'])}, "
        f'<span class="mono">{escape(ctx["stage"])}</span></p>' + ctx["badges"] + _tabs(ctx["stem"], tab)
    )


def _tile(key: str, label: str, shown: str | None, field: str, note: str = "") -> str:
    #: A value the record holds is drawn as the tile's figure; one it does not, small and muted, never as a figure.
    v = f"<strong>{escape(shown)}</strong>" if shown is not None else f'<strong class="nr">{NOT_RECORDED}</strong>'
    return (
        f'<div class="tile" data-tile="{key}"><span class="tile-label">{escape(label)}</span>{v}'
        f"<small>{_field(field) if field else ''}{(' ' + escape(note)) if note else ''}</small></div>"
    )


def timeline(doc: dict | None, divergence: int | None, against: str = "") -> str:
    toks = tokens(doc)
    if toks is None:
        return f"<p data-token-timeline-none>{escape(NO_STEPS)}</p>"
    ps = probabilities(doc)
    n = max(len(toks), 1)
    w, h = 4, 60
    bars = []
    for i in range(len(toks)):
        if ps is not None:
            bh = max(1.0, ps[i] * h)
            bars.append(
                f'<rect data-timeline-bar data-p="{ps[i]:.3f}" x="{i * w}" y="{h - bh:.1f}" width="{w - 1}" '
                f'height="{bh:.1f}"><title>step {i}: {escape(toks[i])}, {ps[i]:.3f}</title></rect>'
            )
        else:
            bars.append(
                f'<rect data-timeline-bar x="{i * w}" y="{h - 12}" width="{w - 1}" height="12">'
                f"<title>step {i}: {escape(toks[i])}</title></rect>"
            )
    mark = ""
    if divergence is not None:
        mark = (
            f'<line data-divergence="{divergence}" x1="{divergence * w + (w - 1) / 2}" x2="{divergence * w + (w - 1) / 2}" y1="0" '
            f'y2="{h}" class="divergence"><title>step {divergence}: first output-token divergence'
            f"{(' against ' + escape(against)) if against else ''}</title></line>"
        )
    said = PROBABILITIES if ps is not None else POSITIONS_ONLY
    marked = (
        f'<p class="legend">The line marks step {divergence}, the first output-token divergence against '
        f"{escape(against)}.</p>"
        if divergence is not None
        else ""
    )
    return (
        '<section data-section="call-timeline"><h2>Token timeline</h2>'
        f'<p class="label">{escape(said)} {len(toks)} decode steps, from 0.</p>{marked}'
        f'<svg class="call-timeline" viewBox="0 0 {n * w} {h}" preserveAspectRatio="none" role="img" '
        f'aria-label="The token timeline, {len(toks)} decode steps">{"".join(bars)}{mark}</svg>'
        f'<p class="legend">step 0 to step {len(toks) - 1}</p></section>'
    )


def overview(ctx: dict) -> str:
    r, doc = ctx["record"], ctx["doc"]
    toks = tokens(doc)
    count = value(r, "steps.count") or (str(len(toks)) if toks is not None else None)
    runtime = " · ".join(v for v in (value(r, "engine.name"), value(r, "engine.version")) if v) or None
    level = value(r, "steps.level") or (str(doc.get("level")) if isinstance(doc, dict) and doc.get("level") else None)
    #: The input tokens' digest, said held only where the record states it; otherwise its state as the record gives it.
    said = r.get("input.token_ids_digest")
    state = str(said.get("status")) if isinstance(said, dict) and said.get("status") else "absent"
    input_note = (
        "the record holds their digest"
        if value(r, "input.token_ids_digest") is not None
        else f"{state}: the record holds no digest of them"
    )
    tiles = (
        _tile("input", "Input tokens", None, "input.token_ids_digest", input_note)
        + _tile("generated", "Decode steps", count, "steps.count")
        + _tile("latency", "Latency", None, "", "the record holds no timing")
        + _tile("runtime", "Runtime", runtime, "engine.name", value(r, "runtime.gpu_name") or "")
        + _tile("level", "Capture level", level, "steps.level", "L4: not recorded")
        + _tile("replay", "Replay", None, "", "no replay of the sampler is recorded")
    )
    p = ctx["pairs"][0] if ctx["pairs"] else None
    against = (p.name_b if p.this_is_a else p.name_a) if p is not None else ""
    return f'<div class="tiles call-tiles">{tiles}</div>' + timeline(doc, p.token_at if p else None, against)


def _decode_rows(p: Pair, at: int) -> str:
    def cell(v: str | None) -> str:
        return _shown(v)

    def row(
        key: str, label: str, va: str | None, vb: str | None, result: str | None = None, word: str | None = None
    ) -> str:
        if result is None:
            result = "not-recorded" if va is None or vb is None else ("same" if va == vb else "differs")
        if word is None:
            word = {"same": SAME, "differs": DIFFERS, "not-recorded": NOT_RECORDED_CHIP}[result]
        return (
            f'<tr data-decode-field="{key}" data-result="{result}"><th scope="row">{label}</th>'
            f"<td>{cell(va)}</td><td>{cell(vb)}</td><td>{_chip(word, result)}</td></tr>"
        )

    ta, tb = p.ta or [], p.tb or []
    pa, pb = probabilities(p.da), probabilities(p.db)
    la, lb = (p.la or []), (p.lb or [])

    def at_(seq, i):
        return seq[i] if i < len(seq) else None

    sampling_a = " · ".join(f"{f.split('.')[1]} {value(p.ra, f)}" for f in SAMPLING if value(p.ra, f) is not None)
    sampling_b = " · ".join(f"{f.split('.')[1]} {value(p.rb, f)}" for f in SAMPLING if value(p.rb, f) is not None)
    #: Each record's settings as it states them; compared only in those both state (`_over_both`).
    sampling_word, sampling = _over_both(p.ra, p.rb, SAMPLING)
    return (
        row(
            "token",
            f"Selected token {_field('steps file')}",
            at_(ta, at),
            at_(tb, at),
        )
        + row(
            "probability",
            "Its probability",
            f"{pa[at]:.3f}" if pa and at < len(pa) else None,
            f"{pb[at]:.3f}" if pb and at < len(pb) else None,
            None if pa and pb else "not-recorded",
        )
        + row(
            "logits",
            f"Logits-row digest {_field('digests')}",
            at_(la, at),
            at_(lb, at),
            None if p.l3 else "not-recorded",
        )
        + row(
            "sampling",
            f"Sampling settings {_field('sampling.*')}",
            sampling_a or None,
            sampling_b or None,
            sampling,
            sampling_word,
        )
        + row("sampling-state", "Sampling-state digest", None, None, "not-recorded")
        + row(
            "seed",
            f"Seed {_field('sampling.seed')}",
            value(p.ra, "sampling.seed"),
            value(p.rb, "sampling.seed"),
            None if value(p.ra, "sampling.seed") and value(p.rb, "sampling.seed") else "not-recorded",
        )
        + row(
            "before",
            f"Output so far (steps 0 to {at - 1})" if at > 0 else "Output so far",
            " ".join(ta[:at]) or "none",
            " ".join(tb[:at]) or "none",
            "same" if ta[:at] == tb[:at] else "differs",
        )
    )


def _top_k(p: Pair, at: int) -> str:
    ca, cb = candidates(p.da, at), candidates(p.db, at)
    if not ca and not cb:
        return f"<p data-top-k-none>The steps files hold no candidates at step {at}.</p>"
    chosen_a = (p.ta or [])[at] if p.ta and at < len(p.ta) else None
    chosen_b = (p.tb or [])[at] if p.tb and at < len(p.tb) else None
    order: list[str] = []
    probs: dict[str, float | None] = {}
    for t, pr in ca + cb:
        if t not in order:
            order.append(t)
        probs.setdefault(t, pr)
    held = any(pr is not None for pr in probs.values())
    rows = []
    for i, t in enumerate(order):
        who = [n for n, c in ((p.name_a, chosen_a), (p.name_b, chosen_b)) if c == t]
        pr = probs.get(t)
        bar = (
            f'<span class="bar" data-probability-bar style="width:{max(2, round(pr * 100))}%"></span> {pr:.3f}'
            if pr is not None
            else f'<span class="nr">{NOT_RECORDED}</span>'
        )
        ins = ", ".join(n for n, c in ((p.name_a, ca), (p.name_b, cb)) if any(x == t for x, _ in c))
        rows.append(
            f'<tr data-candidate="{escape(t)}"><td>{i + 1}</td><td class="mono">{escape(t)}</td><td>{bar}</td>'
            f"<td>{escape(ins)}</td><td>{escape('chosen by ' + ' and '.join(who)) if who else ''}</td></tr>"
        )
    note = (
        ""
        if held
        else (
            f'<p class="label">The steps files hold candidate ids at this step, not their probabilities: '
            f"{NOT_RECORDED}.</p>"
        )
    )
    return f"<h3>Top candidates at step {at}</h3>{note}" + scroll_region(
        '<table class="board" data-top-k><thead><tr><th>#</th><th>Token</th><th>Probability</th>'
        f"<th>In the top-k of</th><th>Chosen</th></tr></thead><tbody>{''.join(rows)}</tbody></table>",
        f"The top candidates at step {at}",
        "top-k",
    )


def decode(ctx: dict) -> str:
    if not ctx["pairs"]:
        from onetrace_console.model_call import timeline as steps_table

        drawn = (
            steps_table(ctx["name"], ctx["steps"], ctx["record"])
            if ctx["steps"] and ctx["steps"].get("token_ids") is not None
            else ""
        )
        return f"<p data-no-comparison>{escape(NO_COMPARISON)}</p>" + drawn
    p = ctx["pairs"][0]
    if p.token_at is None:
        return (
            f"<p data-no-divergence>The chosen tokens are the same at every compared step ({p.compared}) against "
            f"{escape(p.name_b if p.this_is_a else p.name_a)}.</p>"
        )
    at = p.token_at
    commitment = ""
    if p.l3:
        method = value(p.ra, "steps.method") or str((p.da or {}).get("method", ""))
        commitment = (
            "<h3>Logits commitment</h3>"
            f"<div data-logits-commitment>{_field('steps.method')} <code>{escape(method)}</code>: "
            f"a digest of each step's logits row; at step {at}, {escape(p.name_a)} "
            f"{_shown((p.la or [])[at] if at < len(p.la or []) else None)}, {escape(p.name_b)} "
            f"{_shown((p.lb or [])[at] if at < len(p.lb or []) else None)}</div>"
        )
    return (
        f'<h2 data-decode-step="{at}">Decode step {at} · first output-token divergence</h2>'
        f'<p class="label">Compared with the other run of the comparison, {escape(p.name_b if p.this_is_a else p.name_a)}'
        f": {escape(p.name_a)} is its baseline and {escape(p.name_b)} its candidate.</p>"
        "<h3>This step, in both runs</h3>"
        + scroll_region(
            f'<table class="board" data-decode-table><thead><tr><th>Field</th><th>{escape(p.name_a)}</th>'
            f"<th>{escape(p.name_b)}</th><th>Result</th></tr></thead><tbody>{_decode_rows(p, at)}</tbody></table>",
            f"Decode step {at}, in both runs",
            "decode-step",
        )
        + f'<p class="footnote">{escape(SEED_NOTE)}</p>'
        + _top_k(p, at)
        + commitment
    )


def compare(ctx: dict) -> str:
    if not ctx["pairs"]:
        return f"<p data-no-comparison>{escape(NO_COMPARISON)}</p>"
    out = []
    for p in ctx["pairs"]:
        out.append(_compare_one(p, ctx))
    return "".join(out)


def _compare_one(p: Pair, ctx: dict) -> str:
    other = p.name_b if p.this_is_a else p.name_a
    href = f"../../diff/{escape(p.comparison.key)}.html"
    if p.token_at is None:
        card_head = "No output-token divergence"
        sentence = f"The chosen tokens are the same at every compared step ({p.compared})."
    else:
        card_head = f"Decode step {p.token_at}"
        parts = [
            f"The chosen token first differs at decode step {p.token_at}: "
            f"{(p.ta or [''])[p.token_at] if p.token_at < len(p.ta or []) else 'none'} in {p.name_a}, "
            f"{(p.tb or [''])[p.token_at] if p.token_at < len(p.tb or []) else 'none'} in {p.name_b}."
        ]
        if p.l3 and p.row_at is not None:
            parts.append(f"The logits rows first differ at step {p.row_at}.")
        elif p.l3:
            parts.append(f"The logits rows are the same through step {p.token_at}.")
        else:
            #: Which capture is not at L3: the one without logits-row digests, or neither.
            off = [n for n, d in ((p.name_a, p.la), (p.name_b, p.lb)) if d is None]
            why = f"{off[0]}'s capture is not at L3" if len(off) == 1 else "neither capture is at L3"
            parts.append(f"The logits rows were not compared: {why}.")
        sentence = " ".join(parts)
    if p.token_at is None:
        kind = "Same tokens"
    elif p.l3 and p.row_at is not None and p.row_at <= p.token_at:
        kind = "The logits row changed first"
    elif p.l3:
        kind = "Same logits row, a different choice"
    else:
        kind = "A different choice; logits not compared"
    card = (
        '<section data-section="first-divergence" class="call-card">'
        '<div><p class="eyebrow">First output-token divergence</p>'
        f'<p class="call-step">{escape(card_head)}</p><p class="eyebrow">Classification</p>'
        f"<p><strong>{escape(kind)}</strong></p></div>"
        f"<div><p>{escape(sentence)}</p>"
        f'<p class="label">Repeat it, in the folder holding both runs ({escape(p.name_a)} as RUN_A, '
        f"{escape(p.name_b)} as RUN_B):</p><pre><code>{escape(p.command())}</code></pre>"
        f'<p><a href="{href}">The comparison, against {escape(other)}</a></p></div></section>'
    )
    rows = "".join(
        f'<li data-level="{key}"><span>{label}</span>{_chip(word, kind_)}</li>' for key, label, word, kind_ in levels(p)
    )
    lv = f'<section data-section="every-level"><h2>Every level, checked in order</h2><ol class="levels">{rows}</ol></section>'
    table = ""
    if p.token_at is not None and p.ta is not None and p.tb is not None:
        n = p.token_at
        lo, hi = max(0, n - STEP_WINDOW[0]), min(max(len(p.ta), len(p.tb)) - 1, n + STEP_WINDOW[1])
        trs = []
        for i in range(lo, hi + 1):
            a = p.ta[i] if i < len(p.ta) else ""
            b = p.tb[i] if i < len(p.tb) else ""
            la, lb = p.la or [], p.lb or []
            if p.l3 and i < len(la) and i < len(lb):
                logits = "same" if la[i] == lb[i] else "differs"
            else:
                logits = NOT_RECORDED
            status, word = (
                ("same", SAME)
                if i < n and a == b
                else ("differs", DIFFERS)
                if i < n
                else ("diverged", "Diverged")
                if i == n
                else ("different-history", "Different history")
            )
            trs.append(
                f'<tr data-decode-row="{i}" data-status="{status}"'
                + (' class="first"' if i == n else "")
                + f'><td>{i}</td><td class="mono">{escape(a)}</td><td class="mono">{escape(b)}</td>'
                f"<td>{escape(logits)}</td><td>{_chip(word, status)}</td></tr>"
            )
        table = (
            '<section data-section="decode-window"><h2>The decode steps around it</h2>'
            + scroll_region(
                f'<table class="board" data-decode-window><thead><tr><th>Step</th><th>{escape(p.name_a)}</th>'
                f"<th>{escape(p.name_b)}</th><th>Logits row</th><th>Status</th></tr></thead>"
                f"<tbody>{''.join(trs)}</tbody></table>",
                "The decode steps around the first divergence",
                "decode-window",
            )
            + f'<p class="footnote">{escape(DIFFERENT_HISTORY.format(n=n))}</p></section>'
        )
    return f'<div class="call-compare" data-compared="{escape(p.comparison.key)}">{card}{lv}{table}</div>'


def receipt(ctx: dict) -> str:
    import hashlib

    from onetrace_console.receipt_page import _command

    r = ctx["record"]

    def row(field: str, label: str, shown: str) -> str:
        return (
            f'<tr data-field="{escape(field)}"><th scope="row">{escape(label)}</th><td>{shown}</td>'
            f"<td>{_field(field)}</td></tr>"
        )

    steps_v = value(r, "steps")
    gen = (
        f"{_shown(steps_v)} · {escape(value(r, 'steps.count') or NOT_RECORDED)} decode steps"
        if steps_v is not None
        else _shown(None)
    )
    runtime = " · ".join(
        f"{f.split('.')[-1]} {value(r, f)}"
        for f in ("engine.name", "engine.version", "runtime.gpu_name", "dtype", "batch.batch_invariant")
        if value(r, f) is not None
    )
    receipt_digest = "sha256:" + hashlib.sha256(ctx["receipt_bytes"]).hexdigest() if ctx["receipt_bytes"] else None
    envelope = ", ".join(
        f"{f.get('quantity')} ({f.get('form')})" for f in r.get("fingerprints") or [] if isinstance(f, dict)
    )
    rows = (
        row("receipt", "The step's receipt", _shown(receipt_digest))
        + row("format", "Format", _shown(str(r.get("format", ""))))
        + row("stage", "Parent step", f'{escape(ctx["index"])} · <span class="mono">{escape(ctx["stage"])}</span>')
        + row("model.reported", "Model", _shown(value(r, "model.reported")))
        + row("model.files_digest", "Model files", _shown(value(r, "model.files_digest")))
        + row("tokenizer.digest", "Tokenizer", _shown(value(r, "tokenizer.digest")))
        + row("provider.fingerprint", "Provider fingerprint", _shown(value(r, "provider.fingerprint")))
        + row("fingerprints", "Fingerprints", _shown(envelope or None))
        + row("input.token_ids_digest", "Input tokens", _shown(value(r, "input.token_ids_digest")))
        + row("steps", "The steps file", gen)
        + row("output.token_ids_digest", "Output tokens", _shown(value(r, "output.token_ids_digest")))
        + row("output.finish", "How it ended", _shown(value(r, "output.finish")))
        + row("engine.name", "Runtime", _shown(runtime or None))
        + row("recorded", "Recorded with", _shown(ctx["recorded_with"]))
    )
    command, notes = _command(ctx["run"], ctx["store"])
    return (
        '<div class="call-receipt">'
        + scroll_region(
            f'<table class="board" data-call-fields><tbody>{rows}</tbody></table>',
            "The model call's fields",
            "call-fields",
        )
        + '<aside data-section="call-check"><h2>Check it yourself</h2>'
        f"<p>{escape(CHECK_YOURSELF)}</p><pre><code>{chr(10).join(escape(ln) for ln in command.splitlines())}</code></pre>"
        + "".join(f'<p class="label">{n}</p>' for n in notes)
        + "<h2>What this receipt does not say</h2><ul data-does-not-say>"
        + "".join(f"<li>{escape(s)}</li>" for s in DOES_NOT_SAY)
        + "</ul></aside></div>"
    )


def io(ctx: dict) -> str:
    return (
        '<p class="label" data-io-label>The step\'s inputs and outputs, as its page shows them: a text is shown only '
        "where its bytes match the digest its receipt records.</p>" + ctx["io_html"]
    )


def pages_for_step(
    run,
    store,
    step: dict,
    stage: str,
    read_file,
    io_html: str,
    *,
    agree: str,
    signed,
    anchored,
    document,
    footer: str,
    recorded_with: str,
) -> dict[str, str]:
    """The model-call pages of one step: {file name: page}; nothing for a step whose records can't be read."""
    from onetrace_console.stage_pages import stage_page

    receipt_doc, index = step["receipt"], str(step["index"])
    out: dict[str, str] = {}
    for o in mc.outputs(receipt_doc):
        name = str(o["name"])
        try:
            record = mc.read_output(step["file"], o, read_file)
        except mc.Refused:
            continue
        steps = None
        if "steps" in record:
            try:
                steps = mc.read_steps(receipt_doc, step["file"], name, record, read_file)
            except mc.Refused:
                steps = None
        doc = steps["doc"] if steps else None
        stem = base_name(index, name)
        ctx = {
            "run": run,
            "store": store,
            "run_id": run.run_id,
            "record": record,
            "steps": steps,
            "doc": doc,
            "name": name,
            "index": index,
            "stage": stage,
            "stem": stem,
            "stage_page": stage_page(index),
            "badges": _badges(agree, signed, anchored),
            "io_html": io_html,
            "receipt_bytes": read_file(step["file"]),
            "recorded_with": recorded_with,
            "pairs": pairs(run, store, stage, name, (record, doc)),
        }
        for suffix, label in TABS:
            body_fn = {"": overview, "-decode": decode, "-io": io, "-receipt": receipt, "-compare": compare}[suffix]
            title = TITLE if not suffix else f"{TITLE}: {label}"
            body = (
                f'<div class="cp call-page" data-view="model-call" data-call-tab="{suffix or "overview"}">'
                + _head(ctx, suffix, TITLE)
                + body_fn(ctx)
                + f'<p data-section="back"><a href="{stage_page(index)}">The step\'s page</a></p>'
                + footer
                + "</div>"
            )
            out[f"{stem}{suffix}.html"] = document(title, body)
    return out


def step_link(index: str, name: str) -> str:
    """The step page's link to a record's own pages."""
    return f'<a href="{base_name(index, name)}.html" data-model-call-pages>The model call\'s own pages</a>'


MODEL_CALL_PAGES_CSS = """
.call-page .call-badges{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.call-page .call-badges .badge{font-size:var(--fs-small);padding:2px 8px;border-radius:var(--r-pill);
  background:var(--neu-bg);color:var(--neu-ink)}
.call-page .call-tabs{display:flex;flex-wrap:wrap;gap:4px 18px;border-bottom:1px solid var(--line);margin:0 0 14px}
.call-page .call-tabs a{padding:6px 0;color:var(--ink-muted);text-decoration:none;border-bottom:2px solid transparent}
.call-page .call-tabs a[aria-current=page]{color:var(--ink);border-bottom-color:var(--ink);font-weight:600}
.call-page .call-tabs a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.call-page .field{font-size:var(--fs-small);color:var(--ink-muted);white-space:nowrap}
.call-page .nr{color:var(--ink-muted);font-style:italic}
.call-page .tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 14px}
.call-page .tile{border:1px solid var(--line);border-radius:var(--r-card);background:var(--surface);padding:10px 12px;
  display:flex;flex-direction:column;gap:2px;min-width:0}
.call-page .tile strong{font-size:var(--fs-kpi);overflow-wrap:anywhere}
.call-page .tile strong.nr{font-size:var(--fs-body);font-weight:400}
.call-page .tile .tile-label,.call-page .tile small{font-size:var(--fs-small);color:var(--ink-muted)}
.call-page .tile .field{white-space:normal;overflow-wrap:anywhere}
.call-page svg.call-timeline{width:100%;height:120px;display:block;background:var(--surface-sunk);
  border-radius:var(--r-ctl)}
.call-page svg.call-timeline rect{fill:var(--ink-soft)}
.call-page svg.call-timeline line.divergence{stroke:var(--bad-ink);stroke-width:1.5;vector-effect:non-scaling-stroke}
.call-page .chip[data-chip=same]{background:var(--ok-bg);color:var(--ok-ink)}
.call-page .chip:is([data-chip=differs],[data-chip=step],[data-chip=diverged]){background:var(--bad-bg);
  color:var(--bad-ink)}
.call-page .chip:is([data-chip=not-recorded],[data-chip=not-compared],[data-chip=different-history]){
  background:var(--neu-bg);color:var(--neu-ink)}
.call-page .chip{display:inline-block;font-size:var(--fs-small);padding:1px 8px;border-radius:var(--r-pill)}
.call-page .call-card{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,2fr);gap:18px;
  border:1px solid var(--line);border-radius:var(--r-card);background:var(--surface);padding:14px 16px;margin:0 0 14px}
.call-page .call-card .call-step{font-size:var(--fs-kpi);font-weight:600;color:var(--bad-ink);margin:2px 0 8px}
.call-page .eyebrow{font-size:var(--fs-small);color:var(--ink-muted);margin:0}
.call-page ol.levels{list-style:none;padding:0;margin:0}
.call-page ol.levels li{display:flex;justify-content:space-between;gap:12px;align-items:center;padding:7px 0;
  border-bottom:1px solid var(--line-soft)}
.call-page tr.first td{font-weight:600}
.call-page table.board :is(th,td){padding:6px 10px;vertical-align:top;border-bottom:1px solid var(--line-soft);
  text-align:left}
.call-page .bar{display:inline-block;height:8px;border-radius:4px;background:var(--ink-soft);vertical-align:middle}
.call-page .call-receipt{display:grid;grid-template-columns:minmax(0,3fr) minmax(0,2fr);gap:18px}
.call-page .legend,.call-page .footnote{font-size:var(--fs-small);color:var(--ink-muted)}
@media (max-width:767px){.call-page .call-card,.call-page .call-receipt{grid-template-columns:minmax(0,1fr)}}
"""
