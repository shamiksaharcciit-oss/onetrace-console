"""The drift timeline, in the Runs page's strip: each run of one pipeline against the first run this console received
of it, one mark a node, as `onetrace drift` reports it (`drift`, against the first).

- **What is kept** (`run_index`, each run's list entry, `drift`): its place in its pipeline's kept report, from the
  report alone: its index; for the first run, that it is the baseline; for every other, the comparison's envelope and
  first difference, and each node's verdict in the report's node order, or none where the comparison does not reach
  it. A run the kept report does not hold has none.
- **The order** is the drift page's and the command's: oldest first as this console received them, each against the
  first. The page says so.
- **How each is drawn** (`cell`): one mark a node, each its own shape with its words in the row, never colour alone;
  the run's line in the command's own words ("against 1: diverged, first difference b"). A run with nothing kept, or a
  node with no verdict, is "not compared": unknown, never drift-free.
- **The first run to leave** is marked as the short answer's strip marks the first difference: the first run, in the
  order above, whose comparison diverged.
- **Counts** are of the runs `runs_page.select` answers, and of nothing else.
"""

from __future__ import annotations

from onetrace_console.words import escape

COLUMN = "Against the first run"
BASELINE = "the first run: each other run is compared with it"
NOT_COMPARED = "not compared: unknown, never read as no drift"
FIRST_TO_LEAVE = "First to leave the first run"
ORDER = (
    "Against the first run: each run of {label} against the first run this console received of it, oldest first, as "
    "onetrace drift reports it, one mark a step. A run or a step the report does not reach is not compared: unknown, "
    "never read as no drift."
)
#: The command's node verdicts (`onetrace.ladder.VOCABULARY`), each with its mark; none is a node not compared.
MARKS = {
    "same": "same",
    "FIRST DIFFERENCE": "first-difference",
    "downstream": "downstream",
    "reconverged": "reconverged",
    "COULD NOT CHECK": "could-not-check",
}
SHAPES = {
    "same": '<rect class="f" x="4" y="2" width="6" height="10" rx="1"/>',
    "first-difference": '<path class="f" d="M7 1L13 7L7 13L1 7Z"/>',
    "downstream": '<path class="s" d="M7 2L12 7L7 12L2 7Z"/>',
    "reconverged": '<circle class="s" cx="7" cy="7" r="4.5"/>',
    "could-not-check": '<path class="s" d="M3 7H11"/><path class="s" d="M7 3V11"/>',
    "not-compared": '<rect class="s" x="3" y="3" width="8" height="8" stroke-dasharray="1.6 1.6"/>',
}
TONES = {
    "same": "neu",
    "first-difference": "bad",
    "downstream": "cc",
    "reconverged": "neu",
    "could-not-check": "cc",
    "not-compared": "neu",
}
#: The envelopes that say a run did not leave the first; every other one but "diverged" (refused, could not check, not
#: comparable, or a word this console does not know) says neither, and is never counted as no drift.
NOT_DIVERGED = ("identical", "identical after masking")
LEGEND_LEAD = "Against the first run: one mark a step, as onetrace drift gives each step's verdict:"
LEGEND_WORDS = {
    "same": "same",
    "first-difference": "first difference",
    "downstream": "downstream of a difference",
    "reconverged": "reconverged",
    "could-not-check": "could not check",
    "not-compared": "not compared",
}


def mark_of(verdict) -> str:
    return MARKS.get(verdict, "not-compared") if isinstance(verdict, str) else "not-compared"


def kept(rep: dict, runs: list) -> dict[str, dict]:
    """{run key: its place in the report} for each run the report holds; `runs` the pipeline's runs in the order the
    report was made over."""
    by_cand = {c.get("candidate"): c for c in rep.get("comparisons") or [] if isinstance(c, dict)}
    comps = [c for c in rep.get("comparisons") or [] if isinstance(c, dict)]
    out: dict[str, dict] = {}
    for r in rep.get("runs") or []:
        i = str(r.get("index", "")) if isinstance(r, dict) else ""
        if not i.isdigit() or not 0 < int(i) <= len(runs):
            continue
        key = runs[int(i) - 1].key
        c = by_cand.get(i)
        if c is None:
            out[key] = {"index": i, "baseline": True} if i == "1" else {"index": i}
            continue
        at = comps.index(c)
        out[key] = {
            "index": i,
            "against": str(c.get("baseline", "")),
            "envelope": str(c.get("envelope", "")),
            "first_difference": [str(x) for x in c.get("first_difference") or []],
            "nodes": [
                [str(n.get("node")), (n.get("verdicts") or [None] * len(comps))[at]]
                for n in rep.get("nodes") or []
                if isinstance(n, dict)
            ],
        }
    return out


def line(entry: dict | None) -> str:
    """A run's words: the command's own line, "the baseline", or not compared."""
    if not entry or ("baseline" not in entry and "envelope" not in entry):
        return NOT_COMPARED
    if entry.get("baseline"):
        return BASELINE
    words = f"against {entry.get('against', '')}: {entry.get('envelope', '')}"
    if entry.get("first_difference"):
        words += f", first difference {', '.join(entry['first_difference'])}"
    return words


def _svg(mark: str) -> str:
    return (
        f'<svg class="mark" data-drift-mark="{mark}" data-tone="{TONES[mark]}" viewBox="0 0 14 14" width="14" '
        f'height="14" aria-hidden="true" focusable="false">{SHAPES[mark]}</svg>'
    )


def cell(entry: dict | None, first: bool) -> str:
    """A run's cell: its marks, one a node, and its words; marked where it is the first run to leave."""
    if not entry or ("baseline" not in entry and "envelope" not in entry):
        marks = _svg("not-compared")
    elif entry.get("baseline"):
        marks = ""
    else:
        marks = "".join(_svg(mark_of(v)) for _n, v in entry.get("nodes") or [])
    lead = (
        f'<span class="pill neu" data-mark="first" data-drift-first>{escape(FIRST_TO_LEAVE)}</span> ' if first else ""
    )
    return (
        lead
        + (f'<span class="step-marks" data-drift>{marks}</span>' if marks else "")
        + f'<span class="note" data-drift-said>{escape(line(entry))}</span>'
    )


def first_to_leave(listed: list[dict]) -> str | None:
    """The key of the first run, by its place in the report, whose comparison diverged; None where none did."""
    found = sorted(
        (int(e["index"]), r["key"])
        for r in listed
        if isinstance(e := (r.get("list") or {}).get("drift"), dict) and e.get("envelope") == "diverged"
    )
    return found[0][1] if found else None


def counts(listed: list[dict]) -> str:
    """How the runs listed (as `runs_page.select` answers them) read against the first run."""
    n = len(listed)
    entries = [(r.get("list") or {}).get("drift") for r in listed]
    compared = [e for e in entries if isinstance(e, dict) and "envelope" in e]
    baseline = sum(1 for e in entries if isinstance(e, dict) and e.get("baseline"))
    diverged = sum(1 for e in compared if e.get("envelope") == "diverged")
    same = sum(1 for e in compared if e.get("envelope") in NOT_DIVERGED)
    unknown = n - len(compared) - baseline
    return (
        f"Against the first run, of the {n} runs listed: {diverged} diverged; {same} identical; "
        f"{len(compared) - diverged - same} refused, could not check or not comparable; {unknown} not compared"
        + ("; the first run itself" if baseline else "")
        + "."
    )


def legend() -> str:
    items = "".join(f'<li data-drift-mark="{m}">{_svg(m)} {escape(w)}</li>' for m, w in LEGEND_WORDS.items())
    return f'<div data-runs="drift-legend"><p class="note">{escape(LEGEND_LEAD)}</p><ul class="plain inline">{items}</ul></div>'
