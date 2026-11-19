"""A run's steps as a list shows them: one entry a step, in recorded order, with its mark and its recorded times.

Read from the run's receipts when it is checked (`checks.derived_from`) and kept with it (`StoredRun.steps`), so no
list reads a receipt again, as `list_row` is kept.

- **The mark** is the step's last recorded attempt: `plain` (it ran), `error` (its last attempt failed with an error),
  `retried` (an attempt after one that failed with an error, and its last did not fail), `declined` (its last attempt
  declined by its own rule, the SDK's `refused`) or `not-reached` (declared, with no receipt). The same rules the
  retries, the last failed step and the declined step are counted by (`ingest`). A mark is never a verdict, and none
  is read from the app's own traces: only from what the run recorded.
- **The times** are the receipts' own `time.started` and `time.ended`, as written: the step's first start and its last
  end over its attempts, each only where it reads as a time with its zone; `None` where none does.
"""

from __future__ import annotations

MARKS = ("plain", "error", "retried", "declined", "not-reached")


def _instant(value):
    from onetrace_console.run_index import _instant as read

    return read(value) if isinstance(value, str) else None


def of_attempts(attempts: list[tuple], declared: list, effects: dict | None = None) -> list[dict]:
    """`attempts` is (stage name, outcome class, outcome status, refusal reason, started, ended) in the chain's order;
    `declared` the stages the receipts declare, in order. Each step the run recorded, in the order of its first
    attempt, then each declared step with no attempt: {"step", "mark", "retries", "started", "ended"}, and "effect",
    its last receipt's label ({"value", "basis"}), where `effects` holds one for it (`effect_label.kept`)."""
    steps: dict[str, dict] = {}
    failed: set[str] = set()
    for name, cls, _status, _reason, *times in attempts:
        if not isinstance(name, str):
            continue
        started, ended = (list(times) + [None, None])[:2]
        s = steps.setdefault(name, {"retries": 0, "last": None, "started": [], "ended": []})
        if name in failed:
            s["retries"] += 1
        if cls == "error":
            failed.add(name)
        s["last"] = cls
        for which, value in (("started", started), ("ended", ended)):
            at = _instant(value)
            if at is not None:
                s[which].append((at, value))
    out = []
    for name, s in steps.items():
        if s["last"] == "error":
            mark = "error"
        elif s["last"] == "refused":
            mark = "declined"
        elif s["retries"]:
            mark = "retried"
        else:
            mark = "plain"
        out.append(
            {
                "step": name,
                "mark": mark,
                "retries": s["retries"],
                "started": min(s["started"])[1] if s["started"] else None,
                "ended": max(s["ended"])[1] if s["ended"] else None,
                **({"effect": (effects or {})[name]} if (effects or {}).get(name) else {}),
            }
        )
    for name in dict.fromkeys(declared):
        if isinstance(name, str) and name not in steps:
            out.append({"step": name, "mark": "not-reached", "retries": 0, "started": None, "ended": None})
    return out


# ------------------------------------------------------------------ as a list draws them

#: Each mark's shape, in a 14 px square, told apart by shape and by its words, never by colour alone.
SHAPES = {
    "plain": '<rect class="f" x="4" y="2" width="6" height="10" rx="1"/>',
    "error": '<path class="s" d="M3 3L11 11M11 3L3 11"/>',
    "retried": '<path class="s" d="M11.5 8.5A4.5 4.5 0 1 1 10.2 3.8"/><path class="f" d="M8.4 1.6L12.6 2.4L11.2 6.4Z"/>',
    "declined": '<rect class="s" x="2.5" y="2.5" width="9" height="9"/><path class="s" d="M4.5 7H9.5"/>',
    "not-reached": '<rect class="s" x="4" y="2" width="6" height="10" rx="1" stroke-dasharray="2 1.6"/>',
}
#: Each mark's tone: its words and shape say what it is; the tone only repeats it.
TONES = {"plain": "neu", "error": "bad", "retried": "cc", "declined": "neu", "not-reached": "neu"}
#: The legend's words for each mark.
LEGEND_WORDS = {
    "plain": "ran",
    "error": "its last attempt failed with an error",
    "retried": "retried, an attempt after one that failed with an error",
    "declined": "declined by its own rule",
    "not-reached": "declared, not reached",
}
LEGEND_LEAD = "Steps: one mark a step, in recorded order, read from the run's receipts:"
NO_STEPS = "no step recorded"
#: The page's one line saying what the bars are drawn to, and what they are.
SCALE = "Bars are drawn to the longest run on this page: {longest}. A bar is the recorder's clock, as the receipts give it, not a measure of your app."


def _times(n: int) -> str:
    return f"{n} time{'' if n == 1 else 's'}"


def said(step: dict) -> str:
    """A step's mark in words, with its name: "split: retried 2 times"."""
    mark, n = step.get("mark"), int(step.get("retries") or 0)
    words = {
        "plain": "ran",
        "error": "failed with an error" + (f", after retrying {_times(n)}" if n else ""),
        "retried": f"retried {_times(n)}",
        "declined": "declined by its own rule",
        "not-reached": "not reached",
    }.get(str(mark), "")
    return f"{step.get('step')}: {words}"


def mark_svg(mark: str) -> str:
    return (
        f'<svg class="mark" data-step-mark="{mark}" data-tone="{TONES[mark]}" viewBox="0 0 14 14" width="14" '
        f'height="14" aria-hidden="true" focusable="false">{SHAPES[mark]}</svg>'
    )


def cell(steps: list | None) -> str:
    """A run's marks, one a step, and their words in the row's text: how many steps ran, then each that did not
    simply run. "" where the run's steps were not kept."""
    from onetrace_console.words import escape

    if steps is None:
        return ""
    steps = [s for s in steps if isinstance(s, dict) and s.get("mark") in SHAPES]
    if not steps:
        return f'<span class="note">{escape(NO_STEPS)}</span>'
    marks = "".join(mark_svg(s["mark"]) for s in steps)
    plain = sum(1 for s in steps if s["mark"] == "plain")
    n = len(steps)
    parts = [f"{n} step{'' if n == 1 else 's'}: {plain} ran" if n > 1 else ("1 step: ran" if plain else "1 step")]
    parts += [said(s) for s in steps if s["mark"] in ("error", "retried", "declined")]
    left = [str(s["step"]) for s in steps if s["mark"] == "not-reached"]
    if left:
        parts.append(f"{len(left)} not reached ({', '.join(left)})")
    if n == 1 and not plain:
        parts = [said(steps[0])]
    from onetrace_console.effect_label import words as effect_words

    if labelled := effect_words(steps):
        parts.append(labelled)
    return (
        f'<span class="step-marks" data-steps="{n}">{marks}</span>'
        f'<span class="note" data-steps-said>{escape("; ".join(parts))}</span>'
    )


def seconds(ran: str) -> float | None:
    """A run's duration, from its recorded start and end ("<start> → <end>"); None where either cannot be read or the
    end is before the start."""
    start, _, end = (ran or "").partition(" → ")
    a, b = _instant(start.strip()), _instant(end.strip())
    if a is None or b is None or b < a:
        return None
    return (b - a).total_seconds()


def bar(ran: str, steps: list | None, longest: float) -> str:
    """A run's timing bar, on the page's one scale (`longest`, in seconds): its length the run's duration, split by
    step in recorded order where the step's times read. "" where the run's own duration does not read."""
    took = seconds(ran)
    if took is None or longest <= 0:
        return ""
    start = _instant((ran or "").partition(" → ")[0].strip())
    #: The run's whole length, under its steps', so a bar is as long as the run took on the page's scale.
    rects = [
        f'<rect data-run-length data-tone="neu" opacity=".35" x="0" y="0" '
        f'width="{max(100 * took / longest, 0.5):.3f}" height="8"/>'
    ]
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        a, b = _instant(s.get("started")), _instant(s.get("ended"))
        if a is None or b is None or b < a or start is None:
            continue
        x = 100 * max((a - start).total_seconds(), 0) / longest
        w = max(100 * (b - a).total_seconds() / longest, 0.5)
        x = min(x, 99.5)
        rects.append(
            f'<rect data-tone="{TONES.get(str(s.get("mark")), "neu")}" x="{x:.3f}" y="0" '
            f'width="{min(w, 100 - x):.3f}" height="8"/>'
        )
    return (
        f'<svg class="bar" data-bar viewBox="0 0 100 8" preserveAspectRatio="none" aria-hidden="true" '
        f'focusable="false">{"".join(rects)}</svg>'
    )


def legend() -> str:
    from onetrace_console.words import escape

    items = "".join(f'<li data-step-mark="{m}">{mark_svg(m)} {escape(w)}</li>' for m, w in LEGEND_WORDS.items())
    return (
        f'<div data-runs="step-legend"><p class="note">{escape(LEGEND_LEAD)}</p>'
        f'<ul class="plain inline">{items}</ul></div>'
    )
