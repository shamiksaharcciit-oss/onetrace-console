"""What a stored `onetrace check` came back with, said on the runs it checked and on its own run (onetrace 0.8's
`docs/manual.md`, "The check's run").

A check's run holds one receipt of the reserved stage `onetrace.check`: its constants say what was run and what was
predicted (`verb`, `predicted`, `claim`, and `baseline`, `candidate` and `stage` where the verb has them, the runs by
their chain heads), and its assertions what came back (`came_back`: `as predicted`, `otherwise`, or
`did not run: <reason>`). Kept when the run is checked (`rerun_label.kept`).

Where it is said, in onetrace's own words:
- on the head of each run this console holds whose chain head a stored check names as its baseline or candidate:
  "confirmed by a check", "not supported by its check" or "the check did not run: <reason>", the check's run linked;
- on the check's own run's head: its verb, the runs it names (each linked where held, by its chain head), what it
  predicted and what came back.

Neither word is a verdict on the run, and a check's run is never a reference (`rerun_label`).
"""

from __future__ import annotations

from onetrace_console.rerun_label import CHECK_RUN, of_run
from onetrace_console.words import escape

CONFIRMED = "confirmed by a check"
NOT_SUPPORTED = "not supported by its check"
DID_NOT_RUN = "the check did not run: {reason}"
#: onetrace's manual: what neither word is.
NOT_A_VERDICT = (
    'Neither word is a verdict on the run. "Confirmed by a check" says one check\'s result matched what the claim '
    "predicted, on the machine it ran on, once; it is not a proof of the claim."
)
CHECKED_LEAD = "Checked"
CHECK_LEAD = "A check's run"


def outcome(came_back: str) -> str:
    """What came back, in onetrace's words; "" where it says none of the three."""
    if came_back == "as predicted":
        return CONFIRMED
    if came_back == "otherwise":
        return NOT_SUPPORTED
    if came_back.startswith("did not run: "):
        return DID_NOT_RUN.format(reason=came_back.removeprefix("did not run: "))
    return ""


def checks_of(run, store) -> list[tuple]:
    """[(a check's run, its kept label, "baseline" or "candidate")] for each stored check naming `run` by its chain
    head, oldest first."""
    from onetrace_console.store import arrival_order

    out = []
    for other in arrival_order(store.runs(), newest_first=False):
        label = of_run(other)
        if not label or label.get("kind") != CHECK_RUN:
            continue
        for side in ("baseline", "candidate"):
            if run.chain_head and label.get(side) == run.chain_head:
                out.append((other, label, side))
    return out


def _run_by_head(head: str, store, up: str) -> str:
    """The run this store holds with the chain head `head`, linked; else the head, short, and "not held in this
    store"."""
    held = [r for r in store.runs() if r.chain_head == head]
    if len(held) == 1:
        r = held[0]
        return (
            f'<a href="{up}runs/{escape(r.key)}/case.html"><span class="mono" data-words="record">'
            f"{escape(r.run_id)}</span></a>"
        )
    short = head.removeprefix("sha256:")[:12]
    return f'<span class="mono" data-words="record">{escape(short)}…</span> (not held in this store)'


def checked_line(run, store, up: str) -> str:
    """A checked run's head: each stored check naming it, what came back, the check's run linked; "" for none."""
    items = []
    for check, label, side in checks_of(run, store):
        said = outcome(str(label.get("came_back", "")))
        if not said:
            continue
        items.append(
            f'<li data-check-came-back="{escape(str(label.get("came_back", "")))}">{escape(said)} '
            f'(check <a href="{up}runs/{escape(check.key)}/case.html"><span class="mono" data-words="record">'
            f"{escape(check.run_id)}</span></a>; this run its {escape(side)})</li>"
        )
    if not items:
        return ""
    return (
        f'<div class="sub" data-section="checked"><p>{escape(CHECKED_LEAD)}:</p><ul class="plain">{"".join(items)}</ul>'
        f'<p class="note">{escape(NOT_A_VERDICT)}</p></div>'
    )


def check_line(run, store, up: str) -> str:
    """A check's own run's head: its verb, the runs it names, what it predicted and what came back; "" for any other
    run."""
    label = of_run(run)
    if not label or label.get("kind") != CHECK_RUN:
        return ""
    parts = [f'<span data-words="record">{escape(str(label.get("verb", "")))}</span>']
    for side in ("baseline", "candidate"):
        if label.get(side):
            parts.append(f"{side} {_run_by_head(str(label[side]), store, up)}")
    if label.get("stage"):
        parts.append(f'from <span class="mono" data-words="record">{escape(str(label["stage"]))}</span>')
    if label.get("predicted"):
        parts.append(f'predicted <q data-words="record">{escape(str(label["predicted"]))}</q>')
    said = outcome(str(label.get("came_back", "")))
    came = f"; {escape(said)}" if said else ""
    return (
        f'<div class="sub" data-section="check-run"><p>{escape(CHECK_LEAD)}: {", ".join(parts)}{came}.</p>'
        f'<p class="note">{escape(NOT_A_VERDICT)}</p></div>'
    )
