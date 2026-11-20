"""A pipeline's noise fields page, `/pipelines/<label>/noise` (`noise`): the fields marked, what each matches in the
pipeline's kept outputs, and, on a local console, an admin's Add and Remove. A public console draws the list read from
its build, and no form. Each press is one change, recorded in the audit log before it is made (`serve`)."""

from __future__ import annotations

from onetrace_console import noise
from onetrace_console.words import escape

POST_PATH = "/noise"
TITLE = "Noise fields · {label}"
INTRO = (
    "A field marked noise is set aside when a comparison of this pipeline's runs looks for its first difference that "
    "matters: a difference found only in marked fields is passed over, and the comparison shows both that first "
    "difference and the record's own."
)
LIMITS = (
    "A path names a field of a step's JSON output, from its top: keys joined by dots, such as meta.read_at, and * for "
    "any index of an array, at most once. A difference in an output that isn't kept, or isn't JSON, is never set aside."
)
PUBLIC = "This console reads its noise fields from its build. They are changed on a local console."
NONE_YET = "No field of this pipeline is marked noise."
MATCHES = "the kept outputs of {n} of {m} runs"
MATCHES_NOTHING = "matches nothing in the runs' kept outputs"
ADD_HEAD = "Mark a field as noise"
ADD = "Mark as noise"
REMOVE = "Remove"
ADDED = "Marked noise: {step} · {path}."
REMOVED = "No longer noise: {step} · {path}."
NOT_SAVED = "Not saved: {why}."
COLUMNS = ("Step", "Path", "Matches")


def pipeline_by_label(store, label: str):
    """The pipeline whose label is `label` (as its page's address has it, any case); None where none is."""
    from onetrace_console.overview import pipelines

    return next((p for p in pipelines(store) if p.label.lower() == (label or "").lower()), None)


def _matched(store, pipeline, field: noise.Field) -> tuple[int, int]:
    """(how many of the pipeline's runs keep a JSON output at the field's step that the path names, how many runs)."""
    from onetrace_console.compare_view import _json, _kept, _outputs
    from onetrace_console.render import _stage_of
    from onetrace_console.stage_pages import _steps

    n = 0
    for run in pipeline.runs:
        try:
            steps = [s for s in _steps(run, store) if _stage_of(s["receipt"]) == field.step]
        except Exception:  # noqa: BLE001 - a run that can't be read matches nothing
            continue
        values = [_json(_kept(store, run.key, o.get("digest"))) for s in steps for o in _outputs(s["receipt"])]
        if any(v is not None and noise.matches(v, field.path) for v in values):
            n += 1
    return n, len(pipeline.runs)


def _form(pipeline, action: str, inner: str, button: str, style: str) -> str:
    from onetrace_console.frame import CSRF_SLOT

    return (
        f'<form method="post" action="{POST_PATH}" data-noise-form="{escape(action)}">{CSRF_SLOT}'
        f'<input type="hidden" name="pipeline" value="{escape(pipeline.label.lower())}">'
        f'<input type="hidden" name="action" value="{escape(action)}">{inner}'
        f'<button class="btn-{style}" type="submit" data-busy="Working…">{escape(button)}</button></form>'
    )


def body(store, pipeline, *, public: bool, said: str = "", refused: str = "") -> str:
    fields = noise.read(store, pipeline.runs[0].declared_digest)
    rows = []
    for f in fields:
        n, m = _matched(store, pipeline, f)
        matched = (
            escape(MATCHES.format(n=n, m=m)) if n else f'<span data-noise="nothing">{escape(MATCHES_NOTHING)}</span>'
        )
        remove = (
            ""
            if public
            else "<td>"
            + _form(
                pipeline,
                "remove",
                f'<input type="hidden" name="step" value="{escape(f.step)}">'
                f'<input type="hidden" name="path" value="{escape(f.path)}">',
                REMOVE,
                "secondary",
            )
            + "</td>"
        )
        rows.append(
            f'<tr data-noise-field="{escape(f.step)} {escape(f.path)}"><td><code>{escape(f.step)}</code></td>'
            f"<td><code>{escape(f.path)}</code></td><td>{matched}</td>{remove}</tr>"
        )
    head = "".join(f"<th>{escape(c)}</th>" for c in COLUMNS) + (
        "" if public else '<th><span class="visually-hidden">Action</span></th>'
    )
    table = (
        f'<div class="scroll-x"><table class="timeline" data-section="noise-fields"><thead><tr>{head}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
        if rows
        else f'<p data-noise="none">{escape(NONE_YET)}</p>'
    )
    told = f'<p class="said" role="status" data-noise="said">{escape(said)}</p>' if said else ""
    if refused:
        told = f'<p class="said" role="alert" data-noise="refused">{escape(NOT_SAVED.format(why=refused))}</p>'
    if public:
        add = f'<p data-noise="public">{escape(PUBLIC)}</p>'
    else:
        options = "".join(f'<option value="{escape(s)}">{escape(s)}</option>' for s in pipeline.stages)
        add = f'<h2 id="noise-add-h">{escape(ADD_HEAD)}</h2>' + _form(
            pipeline,
            "add",
            f'<label class="field">Step <select name="step">{options}</select></label>'
            '<label class="field">Path <input type="text" name="path" value="" autocomplete="off" '
            'placeholder="meta.read_at" spellcheck="false"></label>',
            ADD,
            "primary",
        )
    from onetrace_console.pipeline_pages import page_href

    return (
        f"<h1>{escape(TITLE.format(label=pipeline.label))}</h1>"
        f'<p class="lead">{escape(INTRO)}</p><p class="note">{escape(noise.NOT_THE_RECORD)}</p>'
        f"<p>{escape(LIMITS)}</p>{told}{table}{add}"
        f'<p><a href="../../{escape(page_href(pipeline.label))}">The pipeline\'s page</a></p>'
    )


def page(store, pipeline, *, public: bool, said: str = "", refused: str = "") -> str:
    from onetrace_console.render import _document

    return _document(
        TITLE.format(label=pipeline.label),
        f'<div class="cp" data-page="noise">{body(store, pipeline, public=public, said=said, refused=refused)}</div>',
    )


def apply(store, pipeline, form: dict) -> tuple[int, str, str]:
    """One press: (status, what was done, why nothing was). Nothing is written where it is refused."""
    action, step, path = form.get("action", ""), form.get("step", ""), (form.get("path") or "").strip()
    try:
        if action == "add":
            noise.add(store, pipeline, step, path)
            return 200, ADDED.format(step=step, path=path), ""
        if action == "remove":
            noise.remove(store, pipeline, step, path)
            return 200, REMOVED.format(step=step, path=path), ""
        raise noise.Refused("no such press")
    except noise.Refused as e:
        return 400, "", str(e)


def plan(store, pipeline, form: dict) -> str:
    """Why a press would be refused, or "": checked before the audit log records it, so nothing is recorded that is
    not done."""
    action, step, path = form.get("action", ""), form.get("step", ""), (form.get("path") or "").strip()
    have = noise.read(store, pipeline.runs[0].declared_digest)
    if action == "add":
        if step not in pipeline.stages:
            return "the step is not one of the pipeline's"
        why = noise.path_problem(path)
        if why:
            return why
        if noise.Field(step, path) in have:
            return "that field is marked already"
        if len(have) >= noise.MOST_FIELDS:
            return f"a pipeline marks at most {noise.MOST_FIELDS} fields"
        return ""
    if action == "remove":
        return "" if noise.Field(step, path) in have else "that field is not marked"
    return "no such press"
