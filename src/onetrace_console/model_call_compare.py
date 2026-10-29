"""A comparison page's model-call records, compared by the installed onetrace's own comparator
(`onetrace.model_call.compare`), under the short answer.

For each step both runs hold (matched by the step's name, in the baseline's order) and each record
name both of those steps hold, the two records are read as a step's page reads them (`model_call`)
and handed to the comparator as they are, with the comparator's own defaults for its mode and its
fingerprint form, and each record's receipt state as the console knows it: "verified" where the
run's check says its records agree, "not verified" otherwise. What comes back is shown in the
comparator's words, line by line: its result (`same`, `diverged` naming the first field that
differs, `could not compare` naming each condition), the mode it applied and what it rested on, and
the rest of its report.

Where both records name a steps file and both are read, the two token-id sequences go to the
comparator too; where its result is `diverged`, its first-differing-step line links to that step's
decode-step row on the candidate's step page (on the baseline's, where only the baseline's sequence
reaches that step). A record or a steps file that cannot be read is named with its reason and
nothing is compared for it. The console adds no verdict and changes no word of the comparator's.
"""
from __future__ import annotations

import re

from onetrace_console import model_call as mc
from onetrace_console.words import escape

HEADING = "Model-call records, compared by onetrace"
LABEL = ("Each step where both runs hold a model-call record of the same name, in the words of the "
         "installed onetrace's comparator: its result, the mode it applied, what it rested on, and the "
         "rest of its report. It reads the two records; it runs no model.")
DEFAULTS = "Compared with the comparator's defaults: mode {mode}, fingerprint form {form}."
ONE_SIDE = "{name} at {step}: only the {side} holds it; nothing compared."
NOT_READ = "{name} at {step}, {side}: not read ({why}); nothing compared."
STEPS_NOT_READ = "The steps files were not both read ({why}); the comparison is of the records alone."
_STEP_LINE = re.compile(r"first differing token at step (\d+)")


def defaults() -> str:
    """The comparator's own defaults for its mode and fingerprint form, read from the installed onetrace."""
    import inspect
    from onetrace import model_call as sdk
    p = inspect.signature(sdk.compare).parameters
    return DEFAULTS.format(mode=p["mode"].default, form=p["form"].default)


def _steps_by_name(run, store) -> list[dict]:
    from onetrace_console.stage_pages import _files, _read, _stage_name, _steps
    files = _files(run, store)
    out, seen = [], set()
    for s in _steps(run, store):
        name = _stage_name(s["receipt"])
        if name in seen:
            continue
        seen.add(name)
        out.append({**s, "name": name, "read": lambda path, files=files: _read(files, store, path)})
    return out


def _receipt_state(run, store) -> str:
    from onetrace_console import records
    return "verified" if records.state(run, store) == records.YES else "not verified"


def _href(run, step: dict, fragment: str) -> str:
    from onetrace_console.stage_pages import stage_page
    return f"../runs/{run.key}/{stage_page(step['index'])}#{fragment}"


def _pair(name: str, sa: dict, sb: dict, run_a, run_b, states) -> str:
    from onetrace import model_call as sdk
    head = (f'<h3><code>{escape(sa["name"])}</code> · <code>{escape(name)}</code> '
            f'(<a href="{escape(_href(run_a, sa, mc.anchor(name)))}">baseline</a>, '
            f'<a href="{escape(_href(run_b, sb, mc.anchor(name)))}">candidate</a>)</h3>')
    got = []
    for side, s in (("baseline", sa), ("candidate", sb)):
        out = next(o for o in mc.outputs(s["receipt"]) if o["name"] == name)
        try:
            got.append(mc.read_output(s["file"], out, s["read"]))
        except mc.Refused as e:
            said = NOT_READ.format(name=name, step=sa["name"], side=side, why=e)
            return f'<div class="model-call-pair" data-model-call-pair="{escape(name)}" data-not-read>{head}<p>{escape(said)}</p></div>'
    steps, note = None, ""
    if "steps" in got[0] and "steps" in got[1]:
        try:
            ids = [mc.read_steps(s["receipt"], s["file"], name, r, s["read"])["token_ids"]
                   for s, r in ((sa, got[0]), (sb, got[1]))]
            steps = (ids[0], ids[1])
        except mc.Refused as e:
            note = f'<p data-steps-not-read>{escape(STEPS_NOT_READ.format(why=e))}</p>'
    result = sdk.compare(got[0], got[1], receipts=states, steps=steps)
    lines = []
    for n, line in enumerate(result.lines()):
        m = _STEP_LINE.fullmatch(line)
        if m is not None and steps is not None:
            at = int(m.group(1))
            side_run, side_step = (run_b, sb) if at < len(steps[1]) else (run_a, sa)
            shown = (f'<a href="{escape(_href(side_run, side_step, mc.decode_anchor(name, at)))}" '
                     f'data-decode-link="{at}">{escape(line)}</a>')
        else:
            #: The comparator's words, each fingerprint in them short and its whole one fold away,
            #: the fold a space after the words.
            from onetrace_console.viewer.page import shortened_in_text
            inline, folded = shortened_in_text(line)
            shown = inline + (" " + folded if folded else "")
        tag = ' data-comparator="result"' if n == 0 else ' data-comparator="mode"' if n == 1 else (
            ' data-comparator="rests-on"' if n == 2 else "")
        lines.append(f"<li{tag}>{shown}</li>")
    return (f'<div class="model-call-pair" data-model-call-pair="{escape(name)}" data-result="{escape(result.result)}">'
            f'{head}<ul class="plain comparator">{"".join(lines)}</ul>{note}</div>')


def section(comparison, store) -> str:
    """The section, or "" where no step both runs hold has a record on either side."""
    from onetrace_console.render import _held
    run_a, run_b = _held(store, comparison.run_a), _held(store, comparison.run_b)
    if run_a is None or run_b is None:
        return ""
    try:
        a, b = _steps_by_name(run_a, store), _steps_by_name(run_b, store)
    except Exception:  # noqa: BLE001 - runs that can't be read compare nothing here
        return ""
    by_b = {s["name"]: s for s in b}
    states = (_receipt_state(run_a, store), _receipt_state(run_b, store))
    blocks = []
    for sa in a:
        sb = by_b.get(sa["name"])
        if sb is None:
            continue
        names_a = [str(o["name"]) for o in mc.outputs(sa["receipt"])]
        names_b = [str(o["name"]) for o in mc.outputs(sb["receipt"])]
        for name in dict.fromkeys(names_a + names_b):
            if name in names_a and name in names_b:
                blocks.append(_pair(name, sa, sb, run_a, run_b, states))
            else:
                side = "baseline" if name in names_a else "candidate"
                said = ONE_SIDE.format(name=name, step=sa["name"], side=side)
                blocks.append(f'<div class="model-call-pair" data-model-call-pair="{escape(name)}" data-one-side>'
                              f"<p>{escape(said)}</p></div>")
    if not blocks:
        return ""
    return (f'<section data-section="model-call-compare" class="model-call"><h2>{escape(HEADING)}</h2>'
            f'<p class="label">{escape(LABEL)}</p><p data-comparator-defaults>{escape(defaults())}</p>'
            f'{"".join(blocks)}</section>')
