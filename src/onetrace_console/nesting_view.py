"""The nesting view: steps inside steps, runs inside steps, and the comparison's descent.

onetrace 0.5 records, for a step called while another ran, `parent` in its receipt and the caller's
`children` (in call order); for a run started inside another's step, `parent_run` and `parent_stage`
in its manifest, and in the outer step an input named `run:<inner run id>` whose digest is the inner
run's chain head.

The run page shows each step with children, its children indented under it in call order, each
with its own result where this run holds its receipt, and each nested run as "nested run <id>" with
the head recorded for it and a link to the inner run's page where the console holds that run ("not
loaded" where it does not). A run with neither shows nothing new.

On a comparison the SDK descends (`diff`/`localize` with `--nested-run` for each inner run the
console holds) and writes the descent as one line, `nested_at`: "inside <step>, at <child>", ",
into run <id> at <child>", or "nested run <id>: folder not given". The console shows that line as a
path, in the SDK's words, and nothing of its own.
"""
from __future__ import annotations

import re

from onetrace_console.words import escape

HEADING = "Steps inside steps"
NESTED = "nested run"
NOT_LOADED = "not loaded"
DESCENT = "Where the runs part, inside the first difference"
RUN_PREFIX = "run:"


def nested_inputs(receipt: dict) -> list[tuple[str, str]]:
    """[(inner run id, its recorded chain head)] for each `run:<id>` input of the step."""
    out = []
    for i in receipt.get("inputs") or [] if isinstance(receipt, dict) else []:
        if isinstance(i, dict) and isinstance(i.get("name"), str) and i["name"].startswith(RUN_PREFIX):
            out.append((i["name"][len(RUN_PREFIX):], str(i.get("digest", ""))))
    return out


def _name(receipt: dict) -> str:
    st = receipt.get("stage") if isinstance(receipt.get("stage"), dict) else {}
    return str(st.get("name", "")) + ("#" + str(st["instance"]) if st.get("instance") else "")


def _result(receipt: dict | None) -> str:
    oc = receipt.get("outcome") if isinstance(receipt, dict) else None
    return str(oc.get("class")) if isinstance(oc, dict) and oc.get("class") else "no outcome recorded"


def run_section(steps: list[dict], held: dict[str, str]) -> str:
    """`held`: {run id: the href of its page} for each run the console holds."""
    by_name = {_name(s["receipt"]): s["receipt"] for s in steps if isinstance(s.get("receipt"), dict)}
    blocks = []
    for s in steps:
        r = s.get("receipt") or {}
        kids = r.get("children") if isinstance(r.get("children"), list) else []
        inner = nested_inputs(r)
        if not kids and not inner:
            continue
        name = _name(r)
        items = []
        for k in kids:
            child = by_name.get(str(k)) if by_name.get(str(k), {}).get("parent") == name else None
            said = (escape(_result(child)) if child is not None
                    else "recorded in a nested run" if inner else "no receipt in this run")
            items.append(f'<li data-nest-child="{escape(str(k))}"><code>{escape(str(k))}</code> · {said}</li>')
        for rid, head in inner:
            href = held.get(rid)
            where = (f'<a href="{escape(href)}">open its page</a>' if href else escape(NOT_LOADED))
            from onetrace_console.trace_panel import code_or_fold
            items.append(f'<li data-nest-run="{escape(rid)}">{escape(NESTED)} <code>{escape(rid)}</code>, '
                         f'its head recorded as {code_or_fold(head)} · {where}</li>')
        blocks.append(f'<li data-nest-step="{escape(name)}"><code>{escape(name)}</code>'
                      f'<ul class="plain nest">{"".join(items)}</ul></li>')
    if not blocks:
        return ""
    return (f'<section data-section="nesting" class="nesting"><h2>{escape(HEADING)}</h2>'
            f'<ul class="plain">{"".join(blocks)}</ul></section>')


PARENT_HEADING = "Called from another run"


def parent_section(manifest: dict, held: dict[str, str]) -> str:
    """An inner run's page: the run and the step that called it, as its manifest names them
    (`parent_run`, `parent_stage`), with a link where the console holds that run; "" for a run
    that names none."""
    rid = manifest.get("parent_run") if isinstance(manifest, dict) else None
    if not isinstance(rid, str) or not rid:
        return ""
    stage = manifest.get("parent_stage")
    href = held.get(rid)
    where = f'<a href="{escape(href)}">open its page</a>' if href else escape(NOT_LOADED)
    at = f" at step <code>{escape(str(stage))}</code>" if isinstance(stage, str) and stage else ""
    return (f'<section data-section="parent-run" class="nesting"><h2>{escape(PARENT_HEADING)}</h2>'
            f'<p data-parent-run="{escape(rid)}">This run was started by run <code>{escape(rid)}</code>{at}, as '
            f'its manifest records it · {where}</p></section>')


def descent(nested_at: str) -> dict | None:
    """The SDK's line, read as `render_path` writes it ("inside <step>, at <child>[, at <grandchild>]
    [, into run <id> at <child>]"): {"path": [("inside", step), ("at", child) or ("run", id, child),
    ...]}; {"not_given": [ids]} for "nested run <id>: folder not given"; None for anything else,
    which is shown as written."""
    if not isinstance(nested_at, str) or not nested_at.strip():
        return None
    text = nested_at.strip()
    given = re.findall(r"nested run (\S+): folder not given", text)
    if given:
        return {"not_given": given}
    parts = text.split(", ")
    if not parts[0].startswith("inside ") or len(parts) < 2:
        return None
    path: list = [("inside", parts[0][len("inside "):])]
    for seg in parts[1:]:
        m = re.fullmatch(r"into run (\S+) at (.+)", seg)
        if m:
            path.append(("run", m[1], m[2]))
        elif seg.startswith("at "):
            path.append(("at", seg[len("at "):]))
        else:
            return None
    return {"path": path}


def path_parts(path: list) -> list:
    """The path as words and names (each name for `<code>`), in the SDK's own words and order."""
    from onetrace_console.short_answer import Code
    out: list = []
    for i, seg in enumerate(path):
        if i:
            out.append(", ")
        if seg[0] == "inside":
            out += ["inside ", Code(seg[1])]
        elif seg[0] == "at":
            out += ["at ", Code(seg[1])]
        else:
            out += ["into run ", Code(seg[1]), " at ", Code(seg[2])]
    return out


def descent_section(nested_at: str) -> str:
    """The comparison page's path, in the SDK's words, one step a line."""
    from onetrace_console.short_answer import _html
    d = descent(nested_at)
    if d is None:
        return (f'<section data-section="descent"><h2>{escape(DESCENT)}</h2><p>{escape(nested_at)}</p></section>'
                if isinstance(nested_at, str) and nested_at.strip() else "")
    if "not_given" in d:
        items = "".join(f"<li>{escape(NESTED)} <code>{escape(r)}</code>: folder not given</li>" for r in d["not_given"])
        return f'<section data-section="descent"><h2>{escape(DESCENT)}</h2><ul class="plain">{items}</ul></section>'
    steps = "".join(f"<li>{_html(path_parts([seg]))}</li>" for seg in d["path"])
    return (f'<section data-section="descent"><h2>{escape(DESCENT)}</h2>'
            f'<ol class="path" data-descent>{steps}</ol><p class="said">The SDK\'s words: '
            f'<code>{escape(nested_at)}</code></p></section>')
