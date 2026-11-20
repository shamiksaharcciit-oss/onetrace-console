"""The model's rows and choices at the first difference: where both runs' model calls at a comparison's first differing
step carry a per-step capture (`model-call-record/1.1`'s steps file), what the two captures say there.

L3 (`l3_reading`): each delivered token's logits-row digest (`sha256-tree-512/v0`). The view gives the first token
position whose digests differ, the first whose chosen token differs, and how many positions before the token difference
had a changed digest with the same token. Only delivered tokens are compared: the digests a capture took beyond them
are counted in the record's `steps.surplus`, shown, and never compared. Where one run has L3 and the other doesn't, or
their digest methods differ, the pair is not comparable, said with why, with no position.

L2 (`l2_reading`): at the first position whose chosen token differs, whether each run's token is among the other's
top-k there and its rank, or that it is not, with k as recorded. A self-hosted capture gives ids and ranks (the console
loads no vocabulary); a hosted one, on a local console, the candidates' text, labelled as the provider returned it. A
public console gives ranks only, and text or ids only for the demo builder's own example data, labelled so. Mixed
levels or a differing k are not comparable. Where sampling was not greedy, a token outside the other run's top-k can
come from sampling alone, and the page says so.

Before any position is shown, both runs' records must verify: each run's check (onetrace-verify, which reads a 1.1
record's capture rows) reads Yes. Otherwise the pair reads "couldn't check" and nothing is compared.

The capture as recorded sits beside the reading: its level and digest method, the model runner, and batch-invariant
mode. With batch-invariant mode not on, the non-claim is said there: a changed digest can come from how requests were
batched, not from the model. A digest difference is not a verdict and changes none.

Where no record at the first differing step names an L2 or L3 capture on either side, there is no section, and the
page is the page it was.
"""

from __future__ import annotations

from dataclasses import dataclass

from onetrace_console import model_call as mc
from onetrace_console.words import escape

HEADING = "At the first difference: the model's rows and choices"
LABEL = (
    "Where both runs' model calls at the first differing step kept a per-step capture, what the two captures "
    "say there, from the steps files as the records name them. It reads the files; it runs no model."
)
L3_HEADING = "Logits rows (L3)"
SAME = "The logits rows and the chosen tokens are the same at every delivered token ({n})."
ROW_THEN_TOKEN = "The logits row changed at token {row}; the chosen token first changed at token {token}."
ROW_ONLY_BEFORE = "{n} position{s} before token {token} had a changed logits row and the same chosen token."
ROW_NO_TOKEN = (
    "The logits row changed at token {row}; the chosen token did not change in the {n} delivered tokens both runs hold."
)
TOKEN_NO_ROW = "The logits rows are the same through token {token}; the chosen token changed there."
LENGTHS = "The baseline delivered {a} tokens and the candidate {b}; positions past {n} are not compared."
SURPLUS = "digests computed beyond the delivered tokens, counted and never compared: baseline {a}, candidate {b}"
NOT_COMPARABLE = "Not comparable: {why}; no position is shown."
COULD_NOT_CHECK = "Couldn't check: {who} records do not verify (its check does not read Yes), so no position is shown."
NOT_READ = "{name}, {side}: not read ({why}); nothing compared."
BATCHING = (
    "With batch-invariant mode not on, a changed digest can come from how requests were batched, not from the model."
)
L3_NON_CLAIMS = (
    "L3 shows whether the row the sampler chose from was the same bytes, not why it changed.",
    "The cost and repeat figures in onetrace's docs are from one GPU, two models and greedy decoding.",
    "A digest difference is not a verdict and changes no verdict.",
)
#: The capture, as the record holds it: (the words, the record's field).
L3_CAPTURE = (
    ("capture level", "steps.level"),
    ("digest method", "steps.method"),
    ("model runner", "engine.settings.model_runner"),
    ("batch-invariant mode", "batch.batch_invariant"),
)
CAPTURED_LEVELS = ("L2", "L3", "L2-hosted")
#: L2's words.
L2_HEADING = "Candidates (L2)"
#: Where a run's receipt names a record's steps file and the run doesn't hold its bytes (onetrace's keep_outputs off).
STEPS_NOT_KEPT = "The steps file wasn't kept, so no candidates or ranks can be shown."
L2_SAME = "The chosen tokens are the same at every delivered token ({n}); no rank is shown."
L2_AT = "At token {at}, the first token whose choice differs:"
L2_RANK = "{who}'s token{tok} was {other}'s {rank} candidate"
L2_OUTSIDE = "{who}'s token{tok} is not among {other}'s top {k}"
L2_NOT_COMPARABLE = "Not comparable: {why}; no rank is shown."
L2_K = "k as recorded: {a} and {b}"
L2_SAMPLED = "Sampling was not greedy ({how}): a token outside the other run's top-k can come from sampling alone."
L2_TEXT_LABEL = "model-generated, as the provider returned it"
L2_EXAMPLE_LABEL = "example data, constructed: the demo's own, not a real run's"
L2_PUBLIC = "ranks only on a public console: no token id or text from a run is shown"
L2_NON_CLAIMS = (
    "A rank shows how the candidates were ordered, not why a different one was chosen.",
    "L2 shows no probabilities unless the record holds them.",
    "A candidate difference is not a verdict and changes no verdict.",
)
#: The capture's members for L2, as the record holds them.
L2_CAPTURE = (
    ("capture level", "steps.level"),
    ("k requested", "steps.k_requested"),
    ("k returned, fewest", "steps.k_returned_min"),
    ("k returned, most", "steps.k_returned_max"),
    ("log-probabilities", "steps.logprobs"),
)
#: A field the record does not hold, in its cell.
NOT_RECORDED = "not recorded"
#: The capture settings, folded where every one is identical, open where any differs.
#: Each is compared only where both records state it.
SETTINGS_SAME = "Capture settings: {n} recorded by both, all identical"
SETTINGS_NONE = "Capture settings: none recorded by both, so none compared"
SETTINGS_DIFFER = "Capture settings: {d} of the {n} recorded by both differ, shown here; the rest folded below."
SETTINGS_REST = "{n} identical"
SETTINGS_UNCOMPARED = "{k} not recorded by both, not compared"
#: The caveats each part keeps folded under its one short line.
WHAT_NOT = "What this does not show"
#: L3's strip of token positions.
STRIP_LEGEND = (
    "Each position: whether its logits row and its chosen token are the same, and where ids are shown the chosen "
    "token's id, baseline / candidate."
)
STRIP_WINDOW = "Positions {a} to {b} of the {n} compared, around the first change."
STRIP_MAX = 40
STATE_WORDS = {"same": "same", "row": "row changed, same token", "token": "choice changed"}
FIRST_WORDS = {"row": "first row change", "choice": "first choice change"}
#: L2's table at a differing token.
L2_TABLE = "At token {at}: each side's candidates, by rank"
L2_ALL = "Show all {n} differing positions"
L2_CHOSEN = "chosen"
L2_MISSING = "not in the {other}'s top {k}"
L2_COLUMNS = ("rank", "baseline", "candidate")
L2_LOGPROB = "logprob"


def shown_value(record: dict, field: str) -> str:
    """A field's value as a cell gives it: its value, or its state, or "not recorded" where the record holds none."""
    got = said(record, field)
    return NOT_RECORDED if got == "absent" else got


def level_words(level_: str, l2: bool = False) -> str:
    """The capture level's row label: on L2's settings, an L3 capture says it includes L2."""
    return "capture level (L3 includes L2)" if l2 and level_ == "L3" else "capture level"


@dataclass(frozen=True)
class L3Reading:
    """`kind`: "same", "positions" or "not-comparable" (with `why`)."""

    kind: str
    row_at: int | None = None
    token_at: int | None = None
    row_only: int = 0
    compared: int = 0
    lengths: tuple[int, int] = (0, 0)
    why: str = ""


def value(record: dict, field: str) -> str | None:
    """A field's value where the record states one (observed, declared or contradicted); None otherwise."""
    v = record.get(field)
    return (
        str(v.get("value")) if isinstance(v, dict) and "value" in v and not isinstance(v.get("value"), list) else None
    )


def said(record: dict, field: str) -> str:
    """A field as the record holds it: its value, or its state where it holds none."""
    v = record.get(field)
    if not isinstance(v, dict):
        return "absent"
    return str(v["value"]) if "value" in v and not isinstance(v["value"], list) else str(v.get("status", "absent"))


def level(record: dict, doc: dict | None) -> str:
    """The capture's level: the record's `steps.level` where it states one, else the steps file's."""
    return value(record, "steps.level") or (str(doc.get("level")) if isinstance(doc, dict) and doc.get("level") else "")


def l3_reading(a_rec: dict, a_doc: dict | None, b_rec: dict, b_doc: dict | None) -> L3Reading | None:
    """The two captures' L3 reading, or None where neither side is at L3."""
    la, lb = level(a_rec, a_doc), level(b_rec, b_doc)
    if la != "L3" and lb != "L3":
        return None
    if la != lb:
        side, other = ("baseline's", "candidate's") if la == "L3" else ("candidate's", "baseline's")
        return L3Reading(
            "not-comparable",
            why=f"only the {side} call captured L3 (the {other} is {(lb if la == 'L3' else la) or 'no capture'})",
        )
    if a_doc is None or b_doc is None:
        #: Both records state L3 and a steps file isn't kept or can't be read: nothing to compare, said so.
        who = (
            "neither call's steps file was"
            if a_doc is None and b_doc is None
            else ("the baseline's steps file wasn't" if a_doc is None else "the candidate's steps file wasn't")
        )
        return L3Reading("not-comparable", why=f"{who} read")
    ma, mb = (str(d.get("method", "")) for d in (a_doc, b_doc))
    if ma != mb:
        return L3Reading("not-comparable", why=f"the digest methods differ: {ma} and {mb}")
    ia, ib = list(a_doc.get("token_ids") or []), list(b_doc.get("token_ids") or [])
    da, db = list(a_doc.get("digests") or []), list(b_doc.get("digests") or [])
    n = min(len(ia), len(ib), len(da), len(db))
    row_at = next((i for i in range(n) if da[i] != db[i]), None)
    token_at = next((i for i in range(n) if ia[i] != ib[i]), None)
    lengths = (len(ia), len(ib))
    if row_at is None and token_at is None:
        return L3Reading("same", compared=n, lengths=lengths)
    upto = token_at if token_at is not None else n
    row_only = sum(1 for i in range(upto) if da[i] != db[i] and ia[i] == ib[i])
    return L3Reading("positions", row_at=row_at, token_at=token_at, row_only=row_only, compared=n, lengths=lengths)


def ordinal(n: int) -> str:
    """1st, 2nd, 3rd, 4th, ..., 11th, 12th, 13th, 21st."""
    tail = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{tail}"


def rank_of(token, candidates: list) -> int | None:
    """`token`'s rank among `candidates` as listed, from 1; None where it is not among them."""
    return candidates.index(token) + 1 if token in candidates else None


@dataclass(frozen=True)
class L2Reading:
    """`kind`: "same", "rank" or "not-comparable" (with `why`). At `at`: each side's chosen token, its rank among the
    other's candidates (None: outside them), and each side's k as recorded."""

    kind: str
    at: int | None = None
    chosen: tuple = ("", "")
    rank_in_other: tuple = (None, None)
    k: tuple = ("", "")
    compared: int = 0
    hosted: bool = False
    why: str = ""


def _steps_of(doc: dict, hosted: bool) -> tuple[list, list]:
    """(each step's chosen token, each step's candidates): ids for a self-hosted capture, text for a hosted one."""
    if hosted:
        steps = [s for s in doc.get("steps") or [] if isinstance(s, dict)]
        return (
            [str((s.get("chosen") or {}).get("text", "")) for s in steps],
            [[str((c or {}).get("text", "")) for c in s.get("candidates") or []] for s in steps],
        )
    return [str(t) for t in doc.get("token_ids") or []], [[str(t) for t in x] for x in doc.get("top_k_ids") or []]


def l2_reading(a_rec: dict, a_doc: dict | None, b_rec: dict, b_doc: dict | None) -> L2Reading | None:
    """The two captures' L2 reading, or None where neither side holds candidates."""
    la, lb = level(a_rec, a_doc), level(b_rec, b_doc)
    if la not in CAPTURED_LEVELS and lb not in CAPTURED_LEVELS:
        return None
    if la != lb:
        return L2Reading(
            "not-comparable", why=f"the capture levels differ: {la or 'no capture'} and {lb or 'no capture'}"
        )
    ka, kb = value(a_rec, "steps.k_requested") or "", value(b_rec, "steps.k_requested") or ""
    if ka != kb:
        return L2Reading("not-comparable", why=f"k differs: {ka or 'not recorded'} and {kb or 'not recorded'}")
    hosted = la.endswith("-hosted")
    (ca, xa), (cb, xb) = _steps_of(a_doc or {}, hosted), _steps_of(b_doc or {}, hosted)
    n = min(len(ca), len(cb), len(xa), len(xb))
    at = next((i for i in range(n) if ca[i] != cb[i]), None)
    if at is None:
        return L2Reading("same", compared=n, k=(ka, kb), hosted=hosted)
    return L2Reading(
        "rank",
        at=at,
        chosen=(ca[at], cb[at]),
        rank_in_other=(rank_of(ca[at], xb[at]), rank_of(cb[at], xa[at])),
        k=(ka, kb),
        compared=n,
        hosted=hosted,
    )


def l3_words(r: L3Reading) -> list[str]:
    """The reading in words, one line each."""
    if r.kind == "not-comparable":
        return [NOT_COMPARABLE.format(why=r.why)]
    lines = []
    if r.kind == "same":
        lines.append(SAME.format(n=r.compared))
    elif r.row_at is not None and r.token_at is not None and r.row_at <= r.token_at:
        lines.append(ROW_THEN_TOKEN.format(row=r.row_at, token=r.token_at))
        lines.append(ROW_ONLY_BEFORE.format(n=r.row_only, s="" if r.row_only == 1 else "s", token=r.token_at))
    elif r.row_at is not None and r.token_at is not None:
        lines.append(ROW_THEN_TOKEN.format(row=r.row_at, token=r.token_at))
    elif r.row_at is not None:
        lines.append(ROW_NO_TOKEN.format(row=r.row_at, n=r.compared))
    else:
        lines.append(TOKEN_NO_ROW.format(token=r.token_at))
    if r.lengths[0] != r.lengths[1]:
        lines.append(LENGTHS.format(a=r.lengths[0], b=r.lengths[1], n=r.compared))
    return lines


def _capture_rows(ra: dict, rb: dict, fields, part: str = "L3") -> str:
    """The capture settings, as the records hold them, each cell its value only ("not recorded" where absent): folded
    into one line where every one is identical; where any differs, those rows shown and marked, the rest folded."""
    from onetrace_console.words import scroll_region

    #: Compared only where both records state a value: those alike are identical, those not differ; the rest, stated by
    #: one record or neither, are not compared, and are neither.
    both = [value(ra, f) is not None and value(rb, f) is not None for _w, f in fields]
    rows = [(words, shown_value(ra, f), shown_value(rb, f)) for words, f in fields]
    differ = [r for r, b in zip(rows, both, strict=True) if b and r[1] != r[2]]
    same = [r for r, b in zip(rows, both, strict=True) if b and r[1] == r[2]]
    rest = [r for r, b in zip(rows, both, strict=True) if not b]
    uncompared = [SETTINGS_UNCOMPARED.format(k=len(rest))] if rest else []

    def table(rs, kind: str) -> str:
        marked = ' data-differs="yes"' if kind == "differ" else ""
        body = "".join(
            f'<tr{marked}><th scope="row">{escape(w)}</th><td>{escape(a)}</td><td>{escape(b)}</td></tr>'
            for w, a, b in rs
        )
        return scroll_region(
            f'<table class="board capture-settings" data-settings="{kind}" data-token-levels-capture><thead><tr>'
            f'<th scope="col">setting</th><th scope="col">baseline</th><th scope="col">candidate</th></tr></thead>'
            f"<tbody>{body}</tbody></table>",
            f"The {part} capture's settings" + (", those that differ" if kind == "differ" else ""),
            f"token-levels-{part.lower()}-{kind}",
        )

    if not differ:
        said = "; ".join([SETTINGS_SAME.format(n=len(same)) if same else SETTINGS_NONE, *uncompared])
        return (
            f'<details data-settings="identical"><summary>{escape(said)}</summary>'
            f"{table(same + rest, 'identical')}</details>"
        )
    compared = len(differ) + len(same)
    out = f"<p data-settings-said>{escape(SETTINGS_DIFFER.format(d=len(differ), n=compared))}</p>{table(differ, 'differ')}"
    if same or rest:
        said = "; ".join(([SETTINGS_REST.format(n=len(same))] if same else []) + uncompared)
        out += (
            f'<details data-settings="identical"><summary>{escape(said)}</summary>'
            f"{table(same + rest, 'identical')}</details>"
        )
    return out


def _caveats(part: str, shown: str, folded: list[str]) -> str:
    """One short caveat under a part, the rest under "What this does not show"."""
    items = "".join(f"<li>{escape(x)}</li>" for x in folded)
    return (
        f'<p class="caveat" data-caveat="{part}">{escape(shown)}</p>'
        f'<details data-caveats="{part}"><summary>{escape(WHAT_NOT)}</summary>'
        f'<ul class="plain nonclaims" data-{part.lower()}-nonclaims>{items}</ul></details>'
    )


def l3_cells(a_doc: dict, b_doc: dict) -> list[tuple[int, str, str, str]]:
    """Each compared position: (its index, "same", "row" (the row changed, the token the same) or "token" (the chosen
    token changed), the baseline's chosen id, the candidate's)."""
    ia, ib = [str(x) for x in a_doc.get("token_ids") or []], [str(x) for x in b_doc.get("token_ids") or []]
    da, db = list(a_doc.get("digests") or []), list(b_doc.get("digests") or [])
    n = min(len(ia), len(ib), len(da), len(db))
    return [(i, "token" if ia[i] != ib[i] else "row" if da[i] != db[i] else "same", ia[i], ib[i]) for i in range(n)]


def _strip(a_doc: dict, b_doc: dict, reading: L3Reading, shown: bool) -> str:
    """L3's positions as a strip, one cell each, its state in words; the first row change and the first choice
    change marked; a window around the first change where there are more than `STRIP_MAX`."""
    cells = l3_cells(a_doc, b_doc)
    if not cells:
        return ""
    n = len(cells)
    changes = [x for x in (reading.row_at, reading.token_at) if x is not None]
    first = min(changes) if changes else 0
    start = max(0, min(first - 8, n - STRIP_MAX)) if n > STRIP_MAX else 0
    end = min(n, start + STRIP_MAX)
    items = []
    for i, state, a, b in cells[start:end]:
        marks = [m for m, at in (("row", reading.row_at), ("choice", reading.token_at)) if at == i]
        first_attr = f' data-first="{" ".join(marks)}"' if marks else ""
        said_first = "".join(f'<span class="first">{escape(FIRST_WORDS[m])}</span>' for m in marks)
        ids = f'<span class="ids">{escape(a)} / {escape(b)}</span>' if shown else ""
        items.append(
            f'<li data-state="{state}"{first_attr}><span class="pos">token {i}</span>'
            f'<span class="state">{escape(STATE_WORDS[state])}</span>{said_first}{ids}</li>'
        )
    window = (
        f"<p data-l3-window>{escape(STRIP_WINDOW.format(a=start, b=end - 1, n=n))}</p>"
        if (start, end) != (0, n)
        else ""
    )
    return (
        f'<ol class="token-strip" data-l3-strip aria-label="Token positions {start} to {end - 1}">{"".join(items)}</ol>'
        f'{window}<p class="legend" data-l3-legend>{escape(STRIP_LEGEND)}</p>'
    )


def _l3_block(ra: dict, rb: dict, reading: L3Reading, docs: tuple = (None, None), shown: bool = True) -> str:
    lines = "".join(f"<p data-l3-reading>{escape(line)}</p>" for line in l3_words(reading))
    if reading.kind == "not-comparable":
        return f'<div data-token-level="L3" data-l3="not-comparable"><h4>{escape(L3_HEADING)}</h4>{lines}</div>'
    surplus = SURPLUS.format(
        a=value(ra, "steps.surplus") or shown_value(ra, "steps.surplus"),
        b=value(rb, "steps.surplus") or shown_value(rb, "steps.surplus"),
    )
    off = any(value(r, "batch.batch_invariant") != "on" for r in (ra, rb))
    strip = _strip(docs[0], docs[1], reading, shown) if all(isinstance(d, dict) for d in docs) else ""
    folded = [*L3_NON_CLAIMS[:2], *([BATCHING] if off else []), surplus]
    return (
        f'<div data-token-level="L3" data-l3="{escape(reading.kind)}"><h4>{escape(L3_HEADING)}</h4>{lines}{strip}'
        f"{_capture_rows(ra, rb, L3_CAPTURE, 'L3')}{_caveats('L3', L3_NON_CLAIMS[2], folded)}</div>"
    )


def _token_html(token: str, shown: bool, hosted: bool) -> str:
    if not shown:
        return ""
    return f" <code>{escape(token)}</code>" if not hosted else f" “{escape(token)}”"


def _greedy(record: dict) -> str:
    """ "" where the record states greedy sampling (temperature 0); else how it was sampled, as the record says."""
    t = value(record, "sampling.temperature")
    if t is None:
        return "its temperature is not recorded"
    try:
        return "" if float(t) == 0 else f"temperature {t}"
    except ValueError:
        return f"temperature {t}"


def _candidates(doc: dict, hosted: bool) -> tuple[list[str], list[list[tuple[str, str | None]]]]:
    """(each step's chosen token, each step's candidates as (token, its logprob as recorded or None))."""
    if hosted:
        steps = [s for s in doc.get("steps") or [] if isinstance(s, dict)]
        return (
            [str((s.get("chosen") or {}).get("text", "")) for s in steps],
            [
                [
                    (str((c or {}).get("text", "")), None if (c or {}).get("logprob") is None else str(c["logprob"]))
                    for c in s.get("candidates") or []
                ]
                for s in steps
            ],
        )
    return [str(x) for x in doc.get("token_ids") or []], [
        [(str(x), None) for x in xs] for xs in doc.get("top_k_ids") or []
    ]


def _l2_table(at: int, a: tuple, b: tuple, k: str, hosted: bool) -> str:
    """At token `at`: each side's candidates by rank, side by side; the logprob where the record holds one; the chosen
    token marked on each side, and a token missing from the other side's top k marked."""
    (ca, xa), (cb, xb) = a, b
    sa, sb = xa[at], xb[at]
    logprobs = any(lp is not None for _t, lp in sa + sb)
    in_a, in_b = {tok for tok, _ in sa}, {tok for tok, _ in sb}

    def cell(item, chosen: str, other: set, other_name: str) -> str:
        if item is None:
            return "<td></td>" + ("<td></td>" if logprobs else "")
        tok, lp = item
        marks = [L2_CHOSEN] if tok == chosen else []
        marks += [L2_MISSING.format(other=other_name, k=k)] if tok not in other else []
        said_marks = "".join(f' <span class="mark">{escape(m)}</span>' for m in marks)
        token = f"<code>{escape(tok)}</code>" if not hosted else f"“{escape(tok)}”"
        chosen_attr = ' data-chosen="yes"' if tok == chosen else ""
        out = f"<td{chosen_attr}>{token}{said_marks}</td>"
        return out + (f"<td>{escape(lp) if lp is not None else escape(NOT_RECORDED)}</td>" if logprobs else "")

    rows = "".join(
        f'<tr><th scope="row">{r + 1}</th>'
        + cell(sa[r] if r < len(sa) else None, ca[at], in_b, "candidate")
        + cell(sb[r] if r < len(sb) else None, cb[at], in_a, "baseline")
        + "</tr>"
        for r in range(max(len(sa), len(sb)))
    )
    lp_head = f'<th scope="col">{escape(L2_LOGPROB)}</th>' if logprobs else ""
    head = (
        f'<th scope="col">{escape(L2_COLUMNS[0])}</th><th scope="col">{escape(L2_COLUMNS[1])}</th>{lp_head}'
        f'<th scope="col">{escape(L2_COLUMNS[2])}</th>{lp_head}'
    )
    from onetrace_console.words import scroll_region

    return scroll_region(
        f'<table class="board l2" data-l2-at="{at}"><caption>{escape(L2_TABLE.format(at=at))}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>",
        L2_TABLE.format(at=at),
        f"token-levels-l2-{at}",
    )


def _l2_tables(a_doc: dict, b_doc: dict, k: str, hosted: bool) -> str:
    """The tables at each token whose choice differs: the first three, the rest in place behind "Show all"."""
    a, b = _candidates(a_doc, hosted), _candidates(b_doc, hosted)
    n = min(len(a[0]), len(b[0]), len(a[1]), len(b[1]))
    at = [i for i in range(n) if a[0][i] != b[0][i]]
    if not at:
        return ""
    first = "".join(_l2_table(i, a, b, k, hosted) for i in at[:3])
    if len(at) <= 3:
        return first
    rest = "".join(_l2_table(i, a, b, k, hosted) for i in at[3:])
    return f"{first}<details data-l2-all><summary>{escape(L2_ALL.format(n=len(at)))}</summary>{rest}</details>"


def _l2_block(
    ra: dict, rb: dict, reading: L2Reading, shown: bool, why_hidden: str, example: bool, docs: tuple = (None, None)
) -> str:
    if reading.kind == "not-comparable":
        return (
            f'<div data-token-level="L2" data-l2="not-comparable"><h4>{escape(L2_HEADING)}</h4>'
            f"<p data-l2-reading>{escape(L2_NOT_COMPARABLE.format(why=reading.why))}</p></div>"
        )
    lines = []
    if reading.kind == "same":
        lines.append(f"<p data-l2-reading>{escape(L2_SAME.format(n=reading.compared))}</p>")
    else:
        lines.append(f"<p data-l2-reading>{escape(L2_AT.format(at=reading.at))}</p>")
        for who, other, mine, rank, k in (
            ("the candidate", "the baseline", reading.chosen[1], reading.rank_in_other[1], reading.k[0]),
            ("the baseline", "the candidate", reading.chosen[0], reading.rank_in_other[0], reading.k[1]),
        ):
            tok = _token_html(mine, shown, reading.hosted)
            words = (
                L2_RANK.format(who=escape(who), tok="{tok}", other=escape(other), rank=ordinal(rank))
                if rank is not None
                else L2_OUTSIDE.format(who=escape(who), tok="{tok}", other=escape(other), k=escape(k))
            )
            lines.append(f"<p data-l2-rank>{words.format(tok=tok)}</p>")
    if shown and (reading.hosted or example):
        lines.append(
            f'<p class="label" data-l2-text-label>{escape(L2_EXAMPLE_LABEL if example else L2_TEXT_LABEL)}</p>'
        )
    elif why_hidden:
        lines.append(f"<p data-l2-hidden>{escape(why_hidden)}</p>")
    if reading.kind == "rank" and shown and all(isinstance(d, dict) for d in docs):
        lines.append(_l2_tables(docs[0], docs[1], reading.k[0] or NOT_RECORDED, reading.hosted))
    sampled = [h for h in (_greedy(ra), _greedy(rb)) if h]
    folded = [*L2_NON_CLAIMS[:2], L2_K.format(a=reading.k[0], b=reading.k[1])]
    if sampled:
        folded.append(L2_SAMPLED.format(how="; ".join(dict.fromkeys(sampled))))
    sampling = tuple(
        (f"sampling: {k[len('sampling.') :]}", k) for k in sorted(set(ra) | set(rb)) if k.startswith("sampling.")
    )
    lvl = level(ra, docs[0] if isinstance(docs[0], dict) else None)
    fields = (
        tuple((level_words(lvl, l2=True) if f == "steps.level" else w, f) for w, f in L2_CAPTURE if f in ra or f in rb)
        + sampling
    )
    return (
        f'<div data-token-level="L2" data-l2="{escape(reading.kind)}"><h4>{escape(L2_HEADING)}</h4>{"".join(lines)}'
        f"{_capture_rows(ra, rb, fields, 'L2')}{_caveats('L2', L2_NON_CLAIMS[2], folded)}</div>"
    )


def _shown_here(digests: tuple, public: bool | None = None) -> tuple[bool, str, bool]:
    """(whether ids or text are shown, the line said where they are not, whether they are the demo's example data):
    on a local console, shown; on a public one, only where both steps files are the demo builder's own example data.
    `public`: the page's own flag, as `render_diff` is given it; None to read the render now (a step page)."""
    from onetrace_console.frame import rendering_public
    from onetrace_console.kept_inputs import example_allowed

    if public is None:
        public = rendering_public()
    if not public:
        return True, "", False
    if all(d and example_allowed(d) for d in digests):
        return True, "", True
    return False, L2_PUBLIC, False


#: The section's own look, in the skin's tokens: the strip's cells wrap; each state in words, its tone a second cue.
TOKEN_LEVELS_CSS = """
[data-section=token-levels] h3{font-size:var(--fs-body);font-weight:600;margin:14px 0 6px}
[data-section=token-levels] ol.token-strip{list-style:none;display:flex;flex-wrap:wrap;gap:6px;margin:10px 0 6px;
  padding:0}
[data-section=token-levels] ol.token-strip li{display:flex;flex-direction:column;gap:2px;min-width:92px;
  padding:6px 8px;border:1px solid var(--line);border-radius:var(--r-ctl);background:var(--surface);
  font-size:var(--fs-small);color:var(--ink)}
[data-section=token-levels] ol.token-strip li .pos{color:var(--ink-muted)}
[data-section=token-levels] ol.token-strip li[data-state=row]{border-color:var(--cc-ink)}
[data-section=token-levels] ol.token-strip li[data-state=token]{border-color:var(--bad-ink);border-width:2px}
[data-section=token-levels] ol.token-strip li[data-first]{outline:2px solid var(--accent);outline-offset:1px}
[data-section=token-levels] ol.token-strip li .first{font-weight:600}
[data-section=token-levels] ol.token-strip li .ids{font-family:var(--font-mono, ui-monospace, monospace)}
[data-section=token-levels] table.board :is(th,td){padding:6px 10px;vertical-align:top;
  border-bottom:1px solid var(--line-soft)}
[data-section=token-levels] table.board caption{text-align:left;font-size:var(--fs-small);color:var(--ink-muted);
  padding:0 0 4px}
[data-section=token-levels] table.board tr[data-differs=yes] :is(th,td){font-weight:600}
[data-section=token-levels] table.l2 td[data-chosen=yes]{font-weight:600}
[data-section=token-levels] .mark{font-size:var(--fs-small);color:var(--ink-muted)}
[data-section=token-levels] details{margin:6px 0}
[data-section=token-levels] details>summary{cursor:pointer}
[data-section=token-levels] .caveat{font-size:var(--fs-small);color:var(--ink-muted);margin:6px 0 0}
[data-section=token-levels] .legend{font-size:var(--fs-small);color:var(--ink-muted);margin:0 0 8px}
[data-section=token-levels] table.board tbody th{font-size:var(--fs-body);font-weight:400;color:var(--ink-muted);
  text-align:left}
"""

CLOSE_HEADING = "Close calls"
CLOSE_FIRST = "At token {at}: {chosen} was chosen; {runner} was the {rank} candidate, {lead} {way}; {n} close call{s} in this output (a lead of at most {margin} nats)."
CLOSE_FIRST_HIDDEN = "At token {at}: the chosen token led the {rank} candidate by {lead}; {n} close call{s} in this output (a lead of at most {margin} nats)."
CLOSE_FIRST_HIDDEN_BEHIND = "At token {at}: the chosen token trailed the {rank} candidate by {lead}; {n} close call{s} in this output (a lead of at most {margin} nats)."
CLOSE_NONE = "No close call: at every token the chosen token led the runner-up by more than {margin} nats."
CLOSE_NO_LOGPROBS = "No close-call flag: no log-probabilities recorded."
CLOSE_LABEL = "Read from the capture as recorded: model-generated, as the provider returned it."
CLOSE_NON_CLAIM = "A close call is not an error, and a wide margin is not correctness."


def _close(lead: float, margin: float) -> bool:
    """A close call: the chosen token's lead over the runner-up at most the margin."""
    return lead <= margin


def close_positions(doc: dict, margin: float) -> list[tuple[int, str, str, int, float]]:
    """Each close call in a hosted capture with log-probabilities, in step order: (the step, the chosen text, the
    runner-up's text, the runner-up's rank among the candidates as listed, the chosen token's lead over it). The
    runner-up is the candidate with the highest log-probability other than the chosen one."""
    out = []
    for i, s in enumerate(doc.get("steps") or []):
        if not isinstance(s, dict) or not isinstance(s.get("chosen"), dict):
            continue
        chosen, cands = s["chosen"], [c for c in s.get("candidates") or [] if isinstance(c, dict)]
        try:
            mine = float(chosen["logprob"])
            others = [
                (float(c["logprob"]), n, c) for n, c in enumerate(cands, 1) if c.get("text") != chosen.get("text")
            ]
        except (KeyError, TypeError, ValueError):
            continue
        if not others:
            continue
        lp, rank, runner = max(others, key=lambda x: (x[0], -x[1]))
        lead = round(mine - lp, 6)
        if _close(lead, margin):
            out.append((i, str(chosen.get("text", "")), str(runner.get("text", "")), rank, lead))
    return out


def _margin_words(margin: float) -> str:
    return f"{margin:g}" if margin != int(margin) else f"{margin:.1f}"


def close_calls(record: dict, doc: dict | None, margin: float, *, shown: bool = True, example: bool = False) -> str:
    """The step page's flag for one record, or "" where its capture holds no candidates (no L2)."""
    lvl = level(record, doc)
    if lvl not in CAPTURED_LEVELS or not isinstance(doc, dict):
        return ""
    head = f"<h4>{escape(CLOSE_HEADING)}</h4>"
    if not lvl.endswith("-hosted") or value(record, "steps.logprobs") in (None, "none"):
        return f'<div data-close-calls="none">{head}<p>{escape(CLOSE_NO_LOGPROBS)}</p></div>'
    found = close_positions(doc, margin)
    m = _margin_words(margin)
    if not found:
        line = escape(CLOSE_NONE.format(margin=m))
    else:
        at, chosen, runner, rank, lead = found[0]
        n, s = len(found), "" if len(found) == 1 else "s"
        if shown:
            line = escape(
                CLOSE_FIRST.format(
                    at=at,
                    chosen=f"“{chosen}”",
                    runner=f"“{runner}”",
                    rank=ordinal(rank),
                    lead=f"{abs(lead):.2f}",
                    way="behind" if lead >= 0 else "ahead",
                    n=n,
                    s=s,
                    margin=m,
                )
            )
        else:
            words = CLOSE_FIRST_HIDDEN if lead >= 0 else CLOSE_FIRST_HIDDEN_BEHIND
            line = escape(words.format(at=at, rank=ordinal(rank), lead=f"{abs(lead):.2f}", n=n, s=s, margin=m))
    label = L2_EXAMPLE_LABEL if example else (CLOSE_LABEL if shown else L2_PUBLIC)
    return (
        f'<div data-close-calls="{"flagged" if found else "none-close"}">{head}<p data-close-call>{line}</p>'
        f'<p class="label">{escape(label)}</p><p class="nonclaim">{escape(CLOSE_NON_CLAIM)}</p></div>'
    )


def _verified(run, store) -> bool:
    from onetrace_console import records

    return records.state(run, store) == records.YES


def _steps_not_kept(step: dict, name: str) -> bool:
    """Whether the step's receipt names the record's steps file (`<record>.steps.json`) and the run holds no bytes
    for it."""
    from onetrace_console.stage_pages import _artifact_path

    steps = name[: -len(".json")] + ".steps.json"
    named = any(str(o.get("name")) == steps for o in step["receipt"].get("outputs") or [] if isinstance(o, dict))
    return named and step["read"](_artifact_path(step["file"], steps)) is None


def _read(step: dict, name: str) -> tuple[dict, dict | None]:
    """A step's record and its steps file (None where the record names none); `mc.Refused` where either is not read."""
    out = next(o for o in mc.outputs(step["receipt"]) if o["name"] == name)
    record = mc.read_output(step["file"], out, step["read"])
    if "steps" not in record:
        return record, None
    return record, mc.read_steps(step["receipt"], step["file"], name, record, step["read"])["doc"]


def _first_stage(report) -> str | None:
    """The first differing step's name, as the span view reads it: the ladder row's node (or stage), less any
    `#<n>`."""
    first = next(
        (
            getattr(r, "node", None) or getattr(r, "stage", None)
            for r in getattr(report, "ladder", ()) or ()
            if r.verdict == "FIRST DIFFERENCE"
        ),
        None,
    )
    return str(first).partition("#")[0] if first is not None else None


def pair_block(name: str, a: tuple, b: tuple, verified: tuple[bool, bool], public: bool | None = None) -> str:
    """One record name's view, or "" where neither side's record names an L2 or L3 capture. L3 and L2 sit together:
    L3 shows where the row changed; L2 where the choice changed, and how far the new choice was from the old one."""
    (ra, da), (rb, db) = a, b
    if level(ra, da) not in CAPTURED_LEVELS and level(rb, db) not in CAPTURED_LEVELS:
        return ""
    head = f"<h3><code>{escape(name)}</code></h3>"
    if not all(verified):
        who = (
            "the baseline's and the candidate's"
            if not any(verified)
            else ("the baseline's" if not verified[0] else "the candidate's")
        )
        return (
            f'<div class="token-levels-pair" data-token-levels="{escape(name)}" data-could-not-check>{head}'
            f"<p>{escape(COULD_NOT_CHECK.format(who=who))}</p></div>"
        )
    blocks = []
    shown, why_hidden, example = _shown_here((value(ra, "steps") or "", value(rb, "steps") or ""), public)
    reading = l3_reading(ra, da, rb, db)
    if reading is not None:
        blocks.append(_l3_block(ra, rb, reading, (da, db), shown))
    second = l2_reading(ra, da, rb, db)
    if second is not None:
        blocks.append(_l2_block(ra, rb, second, shown, why_hidden, example, (da, db)))
    if not blocks:
        return ""
    return f'<div class="token-levels-pair" data-token-levels="{escape(name)}">{head}{"".join(blocks)}</div>'


def section(report, comparison, store, public: bool | None = None) -> str:
    """The section at the first difference, or "" where no record there names an L2 or L3 capture on either side.
    `public`: the comparison page's own flag (`render_diff`'s); None to read the render now."""
    from onetrace_console.model_call_compare import _steps_by_name
    from onetrace_console.render import _held

    stage = _first_stage(report)
    run_a, run_b = _held(store, comparison.run_a), _held(store, comparison.run_b)
    if stage is None or run_a is None or run_b is None:
        return ""
    try:
        sa = next((s for s in _steps_by_name(run_a, store) if s["name"] == stage), None)
        sb = next((s for s in _steps_by_name(run_b, store) if s["name"] == stage), None)
    except Exception:  # noqa: BLE001 - runs that can't be read show nothing here
        return ""
    if sa is None or sb is None:
        return ""
    names_b = {str(o["name"]) for o in mc.outputs(sb["receipt"])}
    verified = None
    blocks = []
    for name in (str(o["name"]) for o in mc.outputs(sa["receipt"])):
        if name not in names_b:
            continue
        if _steps_not_kept(sa, name) or _steps_not_kept(sb, name):
            blocks.append(
                f'<div class="token-levels-pair" data-token-levels="{escape(name)}" data-steps-not-kept>'
                f"<h3><code>{escape(name)}</code></h3><p>{escape(STEPS_NOT_KEPT)}</p></div>"
            )
            continue
        try:
            a, b = _read(sa, name), _read(sb, name)
        except mc.Refused:
            continue
        if verified is None:
            verified = (_verified(run_a, store), _verified(run_b, store))
        block = pair_block(name, a, b, verified, public)
        if block:
            blocks.append(block)
    if not blocks:
        return ""
    return (
        f'<section data-section="token-levels" class="token-levels"><h2>{escape(HEADING)}</h2>'
        f'<p class="label">{escape(LABEL)}</p>{"".join(blocks)}</section>'
    )
