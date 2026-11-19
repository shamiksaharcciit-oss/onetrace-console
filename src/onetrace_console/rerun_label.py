"""A re-run and a check's run, shown as what they are (format 0.4's `rerun` mark and the reserved stage
`onetrace.check`, onetrace 0.8's `docs/format.md`), and never offered as a reference.

What is kept, when a run is checked (`StoredRun.rerun`, as JSON, or "" for neither):
- **A re-run:** the mark every receipt carries, read from the first: its `kind` (`reproduce`, `twin`,
  `counterfactual`, or `check`, the run a check of `reproduce` produced), `of_run` and `of_chain_head`, and the members
  its kind holds (a twin's `config_of_run`; a counterfactual's `substituted` step, run and output; a check's
  `from_stage`). Not kept where the verifier FAILs `re-run mark`: a member it fails is not drawn from.
- **A check's run:** its `onetrace.check` receipt's constants (`verb`, `predicted`, `claim`, and `baseline`,
  `candidate` and `stage` where the verb has them) and assertions (`exit`, `result`, `came_back`).

How each is said: a re-run as the verifier says it, "<kind> of <run>", with its kind's members; a check's run as "a
check's run", with its verb. Neither is a verdict, and neither run is offered as a reference: a labelled run is not
marked a benchmark, and is never one of a benchmark's repeats.
"""

from __future__ import annotations

from onetrace_console.words import escape

MARK_ROW = "re-run mark"
CHECK_STAGE = "onetrace.check"
KINDS = ("reproduce", "twin", "counterfactual", "check")
CHECK_RUN = "check-run"
#: The check's constants and assertions kept, each as written.
CHECK_CONSTANTS = ("verb", "predicted", "claim", "baseline", "candidate", "stage")
CHECK_ASSERTIONS = ("exit", "result", "came_back")
#: Said where a labelled run would be offered as a reference.
NEVER_REFERENCE = "Not offered as a reference: this run is {label}."
CHECK_RUN_WORDS = "a check's run"
HEAD_LEAD = "Re-run"


def kept(receipts: list[dict], rows: list[dict]) -> dict | None:
    """What is kept of a run's re-run mark, or of its check, from its receipts (in chain order) and the verifier's rows;
    None for neither."""
    from onetrace_console.step_kinds import failed

    for r in receipts:
        stage = r.get("stage")
        if isinstance(stage, dict) and stage.get("name") == CHECK_STAGE:
            a: dict = given if isinstance(given := r.get("assertions"), dict) else {}
            c: dict = held if isinstance(held := a.get("constants"), dict) else {}
            return {
                "kind": CHECK_RUN,
                **{k: c[k] for k in CHECK_CONSTANTS if isinstance(c.get(k), str)},
                **{k: a[k] for k in CHECK_ASSERTIONS if isinstance(a.get(k), str)},
            }
    mark = next((r["rerun"] for r in receipts if isinstance(r.get("rerun"), dict)), None)
    if mark is None or mark.get("kind") not in KINDS or failed(rows, "", (MARK_ROW,)):
        return None
    out = {k: mark[k] for k in ("kind", "of_run", "of_chain_head") if isinstance(mark.get(k), str)}
    if mark["kind"] == "twin":
        out.update({k: mark[k] for k in ("config_of_run", "config_of_chain_head") if isinstance(mark.get(k), str)})
    if mark["kind"] == "counterfactual" and isinstance(mark.get("substituted"), dict):
        s = mark["substituted"]
        out["substituted"] = {
            k: s[k] for k in ("step", "from_run", "from_chain_head", "output") if isinstance(s.get(k), str)
        }
    if mark["kind"] == "check" and isinstance(mark.get("from_stage"), str):
        out["from_stage"] = mark["from_stage"]
    return out


def read(text: str) -> dict | None:
    """A kept label, or None where none is kept or it doesn't read."""
    from onetrace_console.bounded_json import load_json_bounded

    try:
        got = load_json_bounded(text, "the run's kept label") if text else None
    except ValueError:
        return None
    return got if isinstance(got, dict) and got.get("kind") in (*KINDS, CHECK_RUN) else None


def said(label: dict) -> str:
    """The label in words: "twin of vector-base, with vector-other's configuration"; "a check's run: reproduce"."""
    kind = label.get("kind")
    if kind == CHECK_RUN:
        return CHECK_RUN_WORDS + (f": {label['verb']}" if label.get("verb") else "")
    words = f"{kind} of {label.get('of_run', '')}"
    if kind == "twin" and label.get("config_of_run"):
        words += f", with {label['config_of_run']}'s configuration"
    s = label.get("substituted")
    if kind == "counterfactual" and isinstance(s, dict) and s.get("step") and s.get("from_run"):
        words += f", {s['from_run']}'s output put in at {s['step']}"
    if kind == "check" and label.get("from_stage"):
        words += f", re-run by a check from {label['from_stage']}"
    return words


def pill(label: dict | None) -> str:
    """A list's label for the run, "" for a run that is neither."""
    if not label:
        return ""
    return f'<span class="pill neu" data-rerun="{escape(str(label["kind"]))}">{escape(said(label))}</span>'


def head_line(label: dict | None, held: dict[str, list[str]], store, up: str) -> str:
    """A re-run's head: what it is, its runs linked where this store holds them; "" for a run that is neither."""
    from onetrace_console.service_link import link_to

    if not label or label.get("kind") == CHECK_RUN:
        return ""
    kind = label["kind"]
    words = f"{escape(kind)} of " + link_to(
        str(label.get("of_run", "")), held, up, head=label.get("of_chain_head"), store=store
    )
    if kind == "twin" and label.get("config_of_run"):
        words += ", with " + link_to(
            label["config_of_run"], held, up, head=label.get("config_of_chain_head"), store=store
        )
        words += "'s configuration"
    s = label.get("substituted")
    if kind == "counterfactual" and isinstance(s, dict) and s.get("step") and s.get("from_run"):
        words += ", " + link_to(s["from_run"], held, up, head=s.get("from_chain_head"), store=store)
        words += f'\'s output put in at <span class="mono" data-words="record">{escape(s["step"])}</span>'
    if kind == "check" and label.get("from_stage"):
        words += f', re-run by a check from <span class="mono" data-words="record">{escape(label["from_stage"])}</span>'
    return f'<p class="sub" data-section="rerun-label">{escape(HEAD_LEAD)}: {words}.</p>'


def of_run(run) -> dict | None:
    """The run's kept label."""
    return read(getattr(run, "rerun", "") or "")


def never_reference(run) -> str:
    """Why a labelled run is not offered as a reference, in words; "" for any other run."""
    label = of_run(run)
    return NEVER_REFERENCE.format(label=said(label)) if label else ""
