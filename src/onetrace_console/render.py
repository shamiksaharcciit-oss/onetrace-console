"""The Home and Diff pages. Rendered here, under the viewer's rules and with its CSS.

    Reuse the viewer's rendering wherever it already renders a diff or localize report.
    Where it doesn't, render in the console under the same rules, and list what you rendered
    fresh.

WHAT IS REUSED, AND WHAT IS FRESH
---------------------------------
**Reused, and not reimplemented:**

- `viewer.verbs.read_report` reads the SDK's `diff.json` / `localize.json` **strictly**, into
  a `TwoRun`, `SingleRun`, `SingleRunDag` or `Reproduce`. Its ladder rows *are* the changes
  table -- the viewer already models it -- so nothing here parses an SDK report.
- `viewer.page.CSS` and `viewer.tokens.root_css()` are the palette, so colour means on these
  pages exactly what it means on the viewer's, and `_head` is its document head.
- `viewer.page.render_executions` renders every Executions list, including the filtered ones
  Home links to.

**Rendered fresh in this console, because the viewer has no page for them:**

1. the **Diff page** as a whole: the viewer renders *sentences* about where a run changed,
   inside a run's own case page. There is no two-run page and no changes table in it.
2. the **changes table** markup: `stage / baseline / candidate / settings / result`, one row per ladder
   row, in the SDK's own order.
3. the **localized set** block.
4. the **repeat command** block.
5. the **Home page** and its tallies.

Everything fresh follows the design note's five prohibitions: no score, no grade, no percentage at all,
no button, colour only for verdicts, nothing inferred. And every sentence about a comparison is the
SDK's: the verdicts, the envelope and the reasons are printed from the report, never restated.
"""
from __future__ import annotations

import os
import re
from onetrace_console.bounded_json import load_json_bounded

from onetrace_console.viewer.graph import instance_label
from onetrace_console.words import (NO_AUTHORIZATION, RELATIVE_TIME_SCRIPT, generated_footer,
                                     scroll_region, short_time, time_html)
from onetrace_console.words import (escape, named, record_href, rest, run_named, shown_name,
                                      verbatim)
from pathlib import Path

from onetrace_console import tones

from onetrace_console.compare import DIFF, LOCALIZE, StoredComparison, report_text
from onetrace_console.home import Tally, tallies
from onetrace_console.preview import label
from onetrace_console.store import Store, create_exclusively

HOME = "home.html"
DIFF_PAGE = "diff.html"

#: The limit sentence, which the design note §6 keeps on every run page. Taken from the
#: viewer's own table rather than retyped, so it cannot drift from the decision that worded it.
def _limit_sentence() -> str:
    """`case.limit`, from the viewer's `FIXED` register.

    Looked up across the registers rather than assumed to be in one, and **refused** if it
    is in none: a page that silently dropped the limit sentence because a register was
    renamed would be the worst kind of quiet change. Measured: it is in `FIXED` at the
    pinned canary commit.
    """
    import onetrace_console.viewer.sentences as S

    for name in ("FIXED", "TABLE", "RULED", "LABELS"):
        source = getattr(S, name, None)
        if isinstance(source, dict) and "case.limit" in source:
            value = source["case.limit"]
            return value if isinstance(value, str) else value[0]
    raise RuntimeError(
        "`case.limit` is in none of the viewer's registers, so the limit sentence the "
        "design note §6 requires cannot be shown. Refusing rather than rendering a page "
        "without it.")


def _document(title: str, body: str) -> str:
    """A page in the console's frame: the viewer's head linking the console's
    one stylesheet, and an empty frame the server fills as it serves the page. No external asset."""
    from onetrace_console.viewer.page import FRAME_NAV, _head, framed
    from onetrace_console.frame import STYLESHEET
    with framed(STYLESHEET):
        head = _head(title)
    return (f'{head}<body>\n<div class="shell"><nav class="frame" data-frame>{FRAME_NAV}</nav>'
            f"<main>\n{body}\n</main></div>\n</body>\n</html>\n")


def _tag(text: str) -> str:
    return escape(str(text), quote=True)


# --------------------------------------------------------------------- the Diff page

#: The SDK's ladder verdicts, worded for a reader (board 6). "downstream" is "changed after
#: it", never "changed as a result": the ladder establishes the order of the differences,
#: not that the first one caused the rest.
_RESULT_WORDS = {
    "same": "Same",
    "FIRST DIFFERENCE": "First difference",
    "downstream": "Changed after it",
    "reconverged": "Same again",
    "COULD NOT CHECK": "Couldn't check",
}


#: The verdicts of a row the SDK compared. Only these rows reached its settings comparison
#: (`onetrace.ladder.build` annotates after the could-not-check exits), so only these can
#: say that no recorded setting differs.
_COMPARED = frozenset({"same", "FIRST DIFFERENCE", "downstream", "reconverged"})


def _annotations(folder: Path, verb: str) -> list[dict]:
    """The report's `annotations`, read strictly. The viewer's reader does not model them.

    Each is `{index, stage, differs: {field: [old, new]}}`, all strings. Anything else is
    refused as the viewer refuses the rest of a report it has not been taught, rather than
    rendering a settings column from a guess.
    """
    import json

    from onetrace_console.viewer.verbs import VerbReportUnreadable

    name = f"{verb}.json"
    notes = load_json_bounded((folder / name).read_text(encoding="utf-8"), name).get("annotations", [])

    def bad(why: str):
        return VerbReportUnreadable(f"{name}: `annotations` {why}")

    if not isinstance(notes, list):
        raise bad("is not a list")
    for note in notes:
        if not isinstance(note, dict):
            raise bad("holds an entry that is not an object")
        if not all(isinstance(note.get(k), str) for k in ("index", "stage")):
            raise bad("holds an entry whose index or stage is not a string")
        differs = note.get("differs")
        if not isinstance(differs, dict):
            raise bad("holds an entry whose `differs` is not an object")
        for field, pair in differs.items():
            if not (isinstance(pair, list) and len(pair) == 2
                    and all(isinstance(v, str) for v in pair)):
                raise bad(f"gives {field!r} as something other than an old/new pair")
    return notes


def _identical_before(folder: Path, verb: str, report) -> int | None:
    """`stages_identical_before_first_difference`, read strictly, or None with no difference.

    Its denominator is the number of stages before the first difference, so a count that is
    not a whole number in 0..that is refused, as is a `first_difference` the ladder does not
    carry. The viewer's reader keeps `first_difference` as given and does not model the count.
    """
    import json

    from onetrace_console.viewer.verbs import VerbReportUnreadable

    first = getattr(report, "first_difference", None)
    if first is None:
        return None
    name = f"{verb}.json"
    marked = [r for r in report.ladder if r.verdict == "FIRST DIFFERENCE"]
    if not (isinstance(first, dict) and len(marked) == 1
            and first.get("index") == marked[0].index and first.get("stage") == marked[0].stage):
        raise VerbReportUnreadable(
            f"{name}: `first_difference` is not the one ladder row marked FIRST DIFFERENCE")
    key = "stages_identical_before_first_difference"
    count = load_json_bounded((folder / name).read_text(encoding="utf-8"), name).get(key)
    before = int(marked[0].index) - 1
    #: The SDK writes it as a string of digits, as it writes `index`.
    if not (isinstance(count, str) and count.isascii() and count.isdigit()
            and int(count) <= before):
        raise VerbReportUnreadable(
            f"{name}: `{key}` is {count!r}, not a whole number from 0 to {before}")
    return int(count)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _listed(items: list[str]) -> str:
    """"a", "a and b", "a, b and c"."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


#: How the stages after the first difference came out, in words that claim order only.
_AFTER_WORDS = {
    "downstream": ("differs", "differ"),
    "reconverged": ("is the same again", "are the same again"),
    "COULD NOT CHECK": ("could not be checked", "could not be checked"),
}


def typed_command(comparison, store: Store, verb: str, *, text: bool = False) -> str:
    """What a reader types to repeat a comparison: the SDK's own command over the two run folders,
    named `runs/<run id>` (this console keeps no folder names, and the demo's folders are named by
    run id), each quoted for a shell where it needs it. `text`: diff's text of the outputs."""
    import shlex

    def folder(key: str) -> str:
        run = _held(store, key)
        return shlex.quote(f"runs/{run.run_id if run is not None and run.run_id else key[:12]}")
    return (f"onetrace {verb} {folder(comparison.run_a)} {folder(comparison.run_b)}"
            + (" --text" if text else ""))


def short_setting(field: str) -> str:
    """A recorded setting by its short name: the last part of its path
    (`assertions.constants.chunk_size` -> `chunk_size`). The whole path is said where it's shown."""
    return field.rsplit(".", 1)[-1]


def _is_digest(value) -> bool:
    import re
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value) is not None


def records_words(comparison, store: Store) -> str:
    """Whether both runs' records agree, each by the Overview's rule: the check held with the run's
    output files required. Said for both together where they read alike."""
    from onetrace_console.checks import CONTRADICTS, HOLDS
    from onetrace_console.home import artifacts_required, verdict_of

    #: (both runs, one run): each reading in the Overview's words.
    words = {
        "agree": ("Both runs' records agree", "{who}'s records agree"),
        "held": ("Both runs' checks held, without their output files required",
                 "{who}'s check held, without its output files required"),
        "contradicts": ("Both runs' records contradict themselves",
                        "{who}'s records contradict themselves"),
        "unchecked": ("Neither run's records were checked", "{who}'s records were not checked"),
    }

    def reads(key: str) -> str:
        run = _held(store, key)
        if run is None:
            return "unchecked"
        if verdict_of(run) == HOLDS:
            return "agree" if artifacts_required(run, store) else "held"
        return "contradicts" if verdict_of(run) == CONTRADICTS else "unchecked"
    a, b = reads(comparison.run_a), reads(comparison.run_b)
    if a == b:
        return words[a][0] + "."
    return (words[a][1].format(who="The baseline") + "; "
            + words[b][1].format(who="the candidate") + ".")


def _first_difference_summary(report, annotations: list[dict], identical: int,
                              command: str = "", records: str = "", variance: str = "") -> str:
    """Board 6's stage-level summary of where two runs first differ, and what that leaves open,
    as the Compare page's headline card: where (the stage, and the stages identical before it)
    beside what (its settings and output, the stages after it, what is not established) and the
    command that repeats it.

    Every number is the report's, each with its denominator. It says the recorded settings
    and the output of the first differing stage both differ; it never says one produced the
    other, and it says outright that why the output differs is not established.
    """
    row = next(r for r in report.ladder if r.verdict == "FIRST DIFFERENCE")
    at = f"stage {row.index} · {shown_name(row.stage)}"
    name = shown_name(row.stage)
    before = int(row.index) - 1
    #: The stages before it that the report reads the same, by name, in its order.
    same = [shown_name(r.stage) for r in report.ladder
            if int(r.index) < int(row.index) and r.verdict == "same"]
    if not before:
        alike = ""
    elif not same:
        alike = "No stage before it was the same in both."
    elif len(same) <= 4:
        alike = f"{_listed(same)} {'was' if len(same) == 1 else 'were'} the same in both."
    else:
        alike = f"The {len(same)} stages before it were the same in both."
    #: Each differing setting by its short name, with both values; a digest-valued one (a
    #: configuration's fingerprint) is named under Details, not here.
    differs = next((n["differs"] for n in annotations if n["index"] == row.index), None) or {}
    plain = [f"{short_setting(f)}: {old} → {new}" for f, (old, new) in differs.items()
             if not (_is_digest(old) or _is_digest(new))]
    if plain:
        settings = f"{name}'s settings differ in {_listed(plain)}."
    elif differs:
        settings = f"{name}'s recorded configuration differs (see Details)."
    else:
        settings = f"No recorded setting of {name} differs."
    after = [r for r in report.ladder if int(r.index) > int(row.index)]
    changed = sum(r.verdict == "downstream" for r in after)
    if not after:
        later = "Its output differs; no stage comes after it."
    elif changed == len(after):
        later = (f"Its output differs, and {'the stage' if changed == 1 else f'all {changed} stages'}"
                 " after it changed too.")
    else:
        rest = {v: n for v, n in ((v, sum(r.verdict == v for r in after))
                                  for v in dict.fromkeys(r.verdict for r in after)) if v != "downstream"}
        others = "; ".join(_plural(n, *_AFTER_WORDS.get(v, (f"is reported {v}", f"are reported {v}")))
                           for v, n in rest.items())
        later = (f"Its output differs, and {changed} of the {_plural(len(after), 'stage', 'stages')}"
                 f" after it changed too; {others}.")
    sentence = " ".join(s for s in (records, alike, settings, later) if s)
    lines = [
        f"First difference: {at}.",
        f"Stages identical before it: {identical} of {before}." if before
        else "No stage comes before it.",
        sentence,
        #: Part V: past a stage that varies with nothing recorded changed, where to look.
        *([variance] if variance else []),
        f"Why {at}'s output differs is not established by this evidence.",
    ]
    where, what = lines[:2], lines[2:]
    copy = (f'<pre data-section="headline-command"><code>{verbatim(command)}</code></pre>'
            if command else "")
    return ('<section data-section="first-difference">'
            '<div data-part="where">' + "".join(f"<p>{escape(line)}</p>" for line in where)
            + '</div><div data-part="what">' + "".join(f"<p>{escape(line)}</p>" for line in what)
            + copy + "</div></section>")


#: When the two runs declare different stage lists: said first, so a pair from
#: two pipelines doesn't read as a broken result. Built from the two runs' declared stages only.
DIFFERENT_PIPELINES = ("These runs come from different pipelines (different stage lists), so most "
                       "differences below are expected. Compare runs from the same pipeline to "
                       "find what changed.")


def _different_pipelines(pair) -> str:
    """The line, only where both runs are held and their declared stage lists differ."""
    from onetrace_console.overview import declared_list
    if len(pair) == 2 and declared_list(pair[0]) != declared_list(pair[1]):
        return f'<p data-section="different-pipelines">{escape(DIFFERENT_PIPELINES)}</p>'
    return ""


def _short_value(value: str) -> str:
    """A setting's value as the table shows it: a digest in short form, its whole value one
    click away; anything else whole."""
    import re
    if re.fullmatch(r"sha256:[0-9a-f]{64}", value):
        return (f'<details data-cell="digest"><summary class="mono">{escape(value[:15])}…'
                f'{escape(value[-6:])}</summary><code>{escape(value)}</code></details>')
    return f'<span class="mono">{escape(value)}</span>'


def _settings_changed(annotations: list[dict], first: str = "") -> str:
    """"Settings that changed": each recorded setting the report's annotations say differs, by
    stage, its baseline and candidate values. From the report's own fields, nothing else."""
    def row(note, field, old, new) -> str:
        return (f'<tr data-setting="{_tag(note["index"])}:{_tag(field)}"><td>{named(note["stage"])}</td>'
                f"<td>{setting_name(field)}</td><td>{_short_value(old)}</td>"
                f"<td>{_short_value(new)}</td></tr>")

    def table(rows: str, label: str, name: str) -> str:
        return scroll_region('<table class="board"><thead><tr><th>Stage</th><th>Setting</th>'
                             f"<th>Baseline</th><th>Candidate</th></tr></thead><tbody>{rows}</tbody>"
                             "</table>", label, name)
    #: Part V: the first later stage with a recorded change (`first`, its ladder index) right
    #: under the first difference's own rows, which are first already (it is the earliest).
    order = sorted(annotations, key=lambda n: (n["index"] != first, int(n["index"])))
    every = [(note, field, old, new) for note in order
             for field, (old, new) in note["differs"].items()]
    #: A configuration's fingerprint (a digest) says that something differs, not what: it is
    #: kept whole, under Details, below the settings a reader can read.
    plain = "".join(row(*x) for x in every if not (_is_digest(x[2]) or _is_digest(x[3])))
    digests = "".join(row(*x) for x in every if _is_digest(x[2]) or _is_digest(x[3]))
    if not every:
        body = "<p>No recorded setting differs between the two runs.</p>"
    else:
        body = (table(plain, "Settings that changed", "settings") if plain else
                "<p>No readable setting differs; only a recorded fingerprint, under Details.</p>")
        if digests:
            body += ('<details data-section="settings-details"><summary>Details</summary>'
                     + table(digests, "Recorded fingerprints that differ", "settings-details")
                     + "</details>")
    return ('<section data-section="settings-changed"><h2>Settings that changed</h2>'
            f"{body}</section>")


def recorded_reads(run_key: str, store: Store) -> dict[str, tuple[str, ...]]:
    """{stage: the receipts its receipt records reading}, from a stored run's receipts: each
    `receipt:<node>` input. Empty where the run or a receipt can't be read."""
    from onetrace_console.stage_pages import _steps
    run = _held(store, run_key)
    if run is None:
        return {}
    out: dict[str, tuple[str, ...]] = {}
    try:
        steps = _steps(run, store)
    except Exception:  # noqa: BLE001 - no reads read, no lines drawn
        return {}
    for step in steps:
        receipt = step["receipt"]
        stage = receipt.get("stage") if isinstance(receipt.get("stage"), dict) else {}
        name = stage.get("name")
        if isinstance(name, str):
            out.setdefault(name, tuple(
                i["name"][len("receipt:"):] for i in receipt.get("inputs") or []
                if isinstance(i, dict) and isinstance(i.get("name"), str)
                and i["name"].startswith("receipt:")))
    return out


#: Part V's words: the sentence after the first difference, and the graph's chip.
VARIANCE_LATER = ("{first}'s output differs, but nothing recorded about it changed; it's marked as "
                  "not reproducible. The first stage with a recorded change is {later}: {what}.")
VARIANCE_NONE = ("No later stage has a recorded change. The differences after {first} follow from "
                 "its output.")
FIRST_RECORDED_CHANGE = "First recorded change"


def _receipts_in_order(run_key: str, store: Store) -> list[dict]:
    """A stored run's receipts in the chain's order; empty where the run or a receipt can't be read."""
    from onetrace_console.stage_pages import _steps
    run = _held(store, run_key)
    if run is None:
        return []
    try:
        return [s["receipt"] for s in _steps(run, store)]
    except Exception:  # noqa: BLE001 - nothing read, nothing said
        return []


def _stage_of(receipt: dict) -> str:
    stage = receipt.get("stage") if isinstance(receipt.get("stage"), dict) else {}
    return stage.get("name") if isinstance(stage.get("name"), str) else ""


def own_inputs(receipts: list[dict]) -> dict[str, dict[str, str]]:
    """{stage: {input name: digest}} of each stage's OWN inputs, as its receipt records them: not
    another stage's receipt (`receipt:<node>`), and not an earlier stage's recorded output in the
    same run (an input whose digest is one of those outputs' digests). What is left came from
    outside the run's stages -- a file, a question, a policy -- so a difference there is a recorded
    change of the stage's own, never one it inherited."""
    produced: set[str] = set()
    out: dict[str, dict[str, str]] = {}
    for receipt in receipts:
        name = _stage_of(receipt)
        inputs = {}
        for i in receipt.get("inputs") or []:
            if not isinstance(i, dict) or not isinstance(i.get("name"), str):
                continue
            if i["name"].startswith("receipt:") or i.get("digest") in produced:
                continue
            inputs[i["name"]] = str(i.get("digest", ""))
        out.setdefault(name, inputs)
        for o in receipt.get("outputs") or []:
            if isinstance(o, dict) and isinstance(o.get("digest"), str):
                produced.add(o["digest"])
    return out


def _not_rederivable(receipts: list[dict], stage: str) -> bool:
    found = [r for r in receipts if _stage_of(r) == stage]
    inst = found[0].get("instrument") if found and isinstance(found[0].get("instrument"), dict) else {}
    return inst.get("rederivable") == "false"


def variance_look_past(report, annotations: list[dict], comparison, store: Store):
    """When the first difference is a stage both runs mark not re-runnable (`rederivable="false"`)
    and nothing recorded about it changed but its output -- no setting, constant or instrument field
    the SDK's own comparison names, and no own input of it -- the first later stage, in the record's
    order, with a recorded change: (first stage, later ladder row or None, its differing settings as
    the SDK names them, its differing own inputs). None where either condition fails, and the page
    is then as it was."""
    first = next((r for r in report.ladder if r.verdict == "FIRST DIFFERENCE"), None)
    if first is None:
        return None
    a, b = _receipts_in_order(comparison.run_a, store), _receipts_in_order(comparison.run_b, store)
    if not (a and b and _not_rederivable(a, first.stage) and _not_rederivable(b, first.stage)):
        return None
    notes = {n["index"]: n["differs"] for n in annotations}
    ins_a, ins_b = own_inputs(a), own_inputs(b)

    def changed_inputs(stage: str) -> list[str]:
        x, y = ins_a.get(stage, {}), ins_b.get(stage, {})
        return sorted(n for n in x.keys() | y.keys() if x.get(n) != y.get(n))
    if notes.get(first.index) or changed_inputs(first.stage):
        return None
    for row in report.ladder:
        if int(row.index) <= int(first.index):
            continue
        differs, inputs = notes.get(row.index) or {}, changed_inputs(row.stage)
        if differs or inputs:
            return first.stage, row, differs, inputs
    return first.stage, None, {}, []


def variance_sentence(found) -> str:
    """Part V's sentence, from `variance_look_past`'s finding. Never a cause: a recorded change."""
    first, row, differs, inputs = found
    if row is None:
        return VARIANCE_NONE.format(first=shown_name(first))
    plain = [f"{short_setting(f)} differs" for f, (o, n) in differs.items()
             if not (_is_digest(o) or _is_digest(n))]
    prints = [f for f, (o, n) in differs.items() if _is_digest(o) or _is_digest(n)]
    said = plain + (["its recorded configuration differs (see Details)"] if prints and not plain else [])
    said += [f"its input {name} differs" for name in inputs]
    return VARIANCE_LATER.format(first=shown_name(first), later=shown_name(row.stage),
                                 what=_listed(said))


def _linear_graph(report, annotations: list[dict], inputs: dict[str, str] | None = None,
                  reads: dict[str, tuple[str, ...]] | None = None,
                  recorded_change: str = "") -> str:
    """A straight-line pair drawn as the stage table is: its stages in the SDK's order, wrapped to
    four boxes a row so it fits the page, a line drawn between two boxes next to each other only
    where the candidate's receipt records reading the earlier one's (`reads`). Each box carries
    its verdict in the page's words (and "inputs differ" where a "same" stage's recorded inputs
    differ, `inputs`), its tone by the one colour rule, and the report's own words for a setting
    that differs, by its short name."""
    from onetrace_console.viewer.graph import GraphNode
    from onetrace_console.viewer.graph import render as graph_render
    notes = {n["index"]: n["differs"] for n in annotations}
    nodes = [GraphNode(
        node_id=row.stage, name=row.stage, index=n, href=f"#step-{row.index}",
        reads=(reads or {}).get(row.stage, ()),
        label=shown_name(row.stage), shown=shown_name(row.stage),
        tags=(_RESULT_WORDS.get(row.verdict, row.verdict),)
        + (("inputs differ",) if inputs and row.verdict == "same" and row.stage in inputs else ()),
        quoted=tuple(f"{short_setting(field)} {old} → {new}"
                     for field, (old, new) in notes.get(row.index, {}).items()
                     if not (_is_digest(old) or _is_digest(new))),
        mark=("first" if row.verdict == "FIRST DIFFERENCE"
              else "recorded-change" if row.index == recorded_change else ""),
        tone=tones.tone(tones.DIFF, row.verdict))
        for n, row in enumerate(report.ladder, start=1)]
    #: Part V: the first later stage with a recorded change carries its chip, its own verdict kept.
    from dataclasses import replace
    nodes = [replace(n, tags=n.tags + (FIRST_RECORDED_CHANGE,)) if n.mark == "recorded-change" else n
             for n in nodes]
    return graph_render(nodes, None, esc=escape, own_table=False, recorded_order=False,
                        region="graph.region.comparison", wrap=4, wrap_labels=True)


def _stage_inputs(run, store: Store) -> dict[str, tuple[dict[str, str], bool]]:
    """Each stage's recorded inputs, from the run's own receipts: {stage: ({input name: digest},
    whether it recorded any output)}. Upstream receipts read as inputs are left out: their
    digests carry the times they were written, so they differ between any two runs."""
    out: dict[str, tuple[dict[str, str], bool]] = {}
    for path, key in run.listing:
        if not (path.startswith("receipts/") and path.endswith(".json")):
            continue
        try:
            receipt = load_json_bounded(store.get(key).decode("utf-8"), path)
            stage = receipt["stage"]["name"]
            inputs = {i["name"]: i["digest"] for i in receipt.get("inputs", [])
                      if not str(i.get("name", "")).startswith("receipt:")}
            outputs = bool(receipt.get("outputs"))
        except Exception:  # noqa: BLE001 - a receipt this can't read says nothing here
            continue
        out.setdefault(stage, (inputs, outputs))
    return out


def input_notes(comparison, store: Store) -> dict[str, str]:
    """For a stage the comparison reads "Same" whose recorded inputs differ between the two runs:
    the plain words saying so. The verdict compares outputs, so a stage that records only its
    inputs reads "Same" even when they differ -- which reads as a contradiction unless said."""
    a, b = _held(store, comparison.run_a), _held(store, comparison.run_b)
    if a is None or b is None:
        return {}
    left, right = _stage_inputs(a, store), _stage_inputs(b, store)
    notes = {}
    for stage in left.keys() & right.keys():
        (ins_a, has_out), (ins_b, _) = left[stage], right[stage]
        differ = sorted(n for n in ins_a.keys() | ins_b.keys() if ins_a.get(n) != ins_b.get(n))
        if differ:
            notes[stage] = (f"its inputs differ ({', '.join(differ)})"
                            + ("; the verdict compares outputs, and this stage records none"
                               if not has_out else "; its outputs are the same"))
    return notes


def _settings(row, notes: dict[str, dict]) -> str:
    """One row's settings cell, as HTML: each recorded setting that differs, by its short name
    with its whole path in its tooltip, and its two values verbatim and whole (a digest is not
    shortened here either). A row with no annotation says that no recorded setting differs -- not
    "same", since the SDK also annotates nothing for a stage that recorded no settings to compare
    -- and only if the SDK compared that row at all.
    """
    differs = notes.get(str(row.index))
    if differs:
        return "; ".join(f'{setting_name(field)} {escape(str(old))} → {escape(str(new))}'
                         for field, (old, new) in differs.items())
    if row.verdict in _COMPARED:
        return escape("no recorded setting differs")
    return escape("not compared")


def setting_name(field: str) -> str:
    """A setting as a page names it: its short name, its whole recorded path in its tooltip."""
    return (f'<span class="mono" data-setting-path="{escape(field)}" title="{escape(field)}">'
            f"{escape(short_setting(field))}</span>")


def _ladder_table(report, verb: str, *, annotations: list[dict], anchors: bool = False,
                  inputs: dict[str, str] | None = None) -> str:
    """The changes table, one row per ladder row, in the SDK's order. Nothing re-sorted.

    `data-verdict` carries the SDK's verdict verbatim, and the first difference is marked on
    its own row (`data-first-difference`). The settings column is the report's annotations;
    the result column words the verdict and carries the SDK's reason.
    """
    notes = {n["index"]: n["differs"] for n in annotations}
    rows = []
    for row in report.ladder:
        first = row.verdict == "FIRST DIFFERENCE"
        word = _RESULT_WORDS.get(row.verdict, row.verdict)
        rows.append(
            f'<tr data-verdict="{_tag(row.verdict)}"'
            + (' data-first-difference="true"' if first else "")
            + (f' id="step-{_tag(row.index)}"' if anchors else "") + ">"
            f"<td>{escape(row.index)}</td>"
            f"<td>{named(row.stage)}</td>"
            f'<td class="mono" data-cell="digest">{escape(_side(row.baseline))}</td>'
            f'<td class="mono" data-cell="digest">{escape(_side(row.candidate))}</td>'
            f'<td data-section="settings">{_settings(row, notes)}</td>'
            f'<td data-result="{_tag(row.verdict)}">{escape(word)}'
            + (f" · {escape(row.reason)}" if row.reason else "")
            + (f' · <span data-inputs-differ="true">{escape(inputs[row.stage])}</span>'
               if inputs and row.verdict == "same" and row.stage in inputs else "")
            + "</td></tr>")
    #: Every stage's whole digests are the detail behind the page's sentence and graph: folded,
    #: under Details, and opened by a link into it (a graph box's `#step-N`).
    return (f'<details data-section="stage-table" data-verb="{_tag(verb)}"><summary>{STAGE_TABLE}'
            "</summary>"
            + _scrolls(
                f'<table data-section="changes" data-verb="{_tag(verb)}"><thead><tr>'
                "<th>#</th><th>stage</th><th>baseline</th><th>candidate</th>"
                "<th>settings</th><th>result</th></tr></thead>"
                f"<tbody>{''.join(rows)}</tbody></table>")
            + "</details>")


#: The fold over a comparison's stage table.
STAGE_TABLE = "Details: each stage, with its recorded outputs' digests whole"


def _union_edges(comparison, store: Store):
    """Both runs' recorded `edges`, as one list (`topology._union_edges`), or None where
    neither run's manifest carries `edges`. A manifest whose `edges` is not a list of links each
    naming a `from` and a `to` raises ValueError: nothing is drawn from a guess."""
    import json
    found, recorded = set(), False
    for key in (comparison.run_a, comparison.run_b):
        run = _held(store, key)
        manifest_key = dict(run.listing).get("MANIFEST.json") if run is not None else None
        if not manifest_key:
            continue
        manifest = load_json_bounded(store.get(manifest_key), "MANIFEST.json")
        if "edges" not in manifest:
            continue
        edges = manifest["edges"]
        if not (isinstance(edges, list) and all(
                isinstance(e, dict) and isinstance(e.get("from"), str)
                and isinstance(e.get("to"), str) for e in edges)):
            raise ValueError("a manifest's edges are not links")
        recorded = True
        found |= {(e["from"], e["to"]) for e in edges}
    return [{"from": f, "to": t} for f, t in sorted(found)] if recorded else None


def _runs_ab(comparison, store: Store) -> str:
    """Which run the SDK's "A" and "B" are: its words for the baseline and the candidate, each
    named by its run id and short key."""
    return (f'<p data-section="runs-ab">A is the baseline {run_named(store, comparison.run_a)}; '
            f'B is the candidate {run_named(store, comparison.run_b)}.</p>')


def _compare_graph(report, comparison, store: Store) -> str:
    """One graph over both runs' nodes, matched by node id, in the
    SDK's own order (its rows, which `topology.order` wrote). Each node carries the verdict in
    this page's words and the SDK's annotations in its own; every first difference is marked.
    The page's changes table, just below, is its table; each node links to its row there."""
    from onetrace_console.viewer.graph import GraphNode
    from onetrace_console.viewer.graph import render as graph_render
    from onetrace_console.viewer.sentences import template
    try:
        edges = _union_edges(comparison, store)
    except ValueError:
        return (f'<section data-section="graph"><p data-section="graph-unreadable">'
                f'{escape(template("graph.unreadable"))}</p></section>')
    nodes = [GraphNode(
        node_id=row.node, name=row.node.split("#", 1)[0], index=n, href=f"#step-{n}",
        label=shown_name(row.node), shown=shown_name(row.node.split("#", 1)[0]),
        tags=(_RESULT_WORDS.get(row.verdict, row.verdict),), quoted=tuple(row.annotations),
        mark="first" if row.verdict == "FIRST DIFFERENCE" else "",
        tone=tones.tone(tones.DIFF, row.verdict))
        for n, row in enumerate(report.ladder, start=1)]
    return graph_render(nodes, edges, esc=escape, own_table=False, recorded_order=False,
                        region="graph.region.comparison", wrap_labels=True)


def _graph_caveat(report) -> str:
    """What a graph comparison leaves open, as the linear summary says it (board 6): for every
    node where the two runs first differ, that why its output differs is not established. A
    graph names no single first difference, so the sentence names each frontier node where the
    linear page names "stage N · name". Without it, a page marking first differences on a graph
    said nothing of what the marks do not establish."""
    if report.envelope != "diverged" or not report.first_difference_frontier:
        return ""
    lines = [f"Why {shown_name(node)}'s output differs is not established by this evidence."
             for node in report.first_difference_frontier]
    return ('<section data-section="first-difference" data-shape="dag">'
            + "".join(f"<p>{escape(line)}</p>" for line in lines) + "</section>")


#: The frames 0.2.0 fills, each reading its placeholder
#: until then. They state nothing about the pair: no field, count or state of their own.
#: Board 7 has no frame before 0.2.0: the work order shows it only where the
#: first difference sits at a node whose corpus link changed, which only 0.2.0 can say, and a
#: frame on every diverged pair would suggest a source change that may not exist.
TEXT_DIFF_HEADING = "The text diff"


#: What the text diff's section says of where it came from. Canary's words,
#: fixed as written, marked beside each.
#: Fixed as written.
TEXT_DIFF_NOT_KEPT = ("This comparison was made before the text diff was kept. Comparing the pair "
                      "again keeps it.")
#: Fixed as written.
TEXT_DIFF_UNREADABLE = "This console can't read this text diff: {why}"


def _text_diff_section(comparison, store) -> str:
    """Item 4: the comparison's own stored run of `onetrace diff --text --json
    --no-follow`, read strictly and drawn as the SDK wrote it, with the limit it was drawn at and
    how to ask for the larger one. Never the console's own diff."""
    from onetrace_console.compare import (TEXT_DIFF, TEXT_DIFF_DEFAULT_LINES, TEXT_DIFF_MORE_LINES,
                                          text_diff_raw)
    from onetrace_console.textdiff_view import TextDiffUnreadable, read_textdiff, render_textdiff
    head = f'<section data-section="text-diff"><h2>{escape(TEXT_DIFF_HEADING)}</h2>'
    found = text_diff_raw(comparison, store)
    if found is None:
        return f"{head}<p>{escape(TEXT_DIFF_NOT_KEPT)}</p></section>"
    raw, verb = found
    run = comparison.verb(verb)
    import re as _re
    #: The lines per output this text diff was made with, where it asked for more than the
    #: SDK's default: as the stored command recorded it.
    more = _re.search(r"--max-lines \d+", run.shown_command)
    command = (f'<p data-section="text-diff-command">Command: '
               f"<code>{escape(typed_command(comparison, store, 'diff', text=True))}"
               f"{escape(' ' + more.group(0)) if more else ''}</code></p>")
    try:
        doc = read_textdiff(raw)
    except TextDiffUnreadable as e:
        return (f"{head}<p>{escape(TEXT_DIFF_UNREADABLE.format(why=e))}</p>{command}</section>")
    more = verb != TEXT_DIFF
    lines = TEXT_DIFF_MORE_LINES if more else TEXT_DIFF_DEFAULT_LINES
    #: The limit line, with its variant: fixed as written.
    limit = (f"Shown with at most {lines} lines per output"
             + (" (this console's larger limit, ten times the SDK's default)." if more
                else " (the SDK's default)."))
    cut = any("truncated" in o for n in doc.get("nodes", []) for o in n["outputs"])
    ask = ""
    if cut and not more:
        #: A command the reader can type (the SDK's own line cap), never a route of this console.
        longer = (typed_command(comparison, store, "diff", text=True)
                  + f" --max-lines {TEXT_DIFF_MORE_LINES}")
        ask = (f'<p data-section="text-diff-more">Some outputs are cut at {lines} lines. To see up '
               f"to {TEXT_DIFF_MORE_LINES} lines per output: <code>{escape(longer)}</code></p>")
    #: The same document on a page of its own, two panes (the TextDiff board), where it was shown.
    from onetrace_console.textdiff_page import OPEN, page_name, shown_document
    own = (f'<p data-section="text-diff-page"><a href="{escape(page_name(comparison))}">{escape(OPEN)}</a></p>'
           if shown_document(comparison, store) is not None else "")
    return (f"{head}<p data-section=\"text-diff-limit\">{escape(limit)}</p>{ask}{own}"
            f"{render_textdiff(doc)}{command}</section>")


def _dag_table(report, verb: str) -> str:
    """The changes table for two graph-shaped runs: one row per node, in the SDK's order,
    each node's position in either run as the report gives it (empty where it is not in that
    run), the SDK's annotations verbatim, and the verdict in this page's words."""
    rows = []
    for n, row in enumerate(report.ladder, start=1):
        first = row.verdict == "FIRST DIFFERENCE"
        rows.append(
            f'<tr data-node-row="{n}" data-verdict="{_tag(row.verdict)}"'
            + (' data-first-difference="true"' if first else "") + ">"
            f'<td><span id="step-{n}"></span>{n}</td>'
            f'<td class="mono">{named(instance_label(row.node))}</td>'
            f'<td class="mono">{escape(row.index_baseline or "")}</td>'
            f'<td class="mono">{escape(row.index_candidate or "")}</td>'
            f'<td data-section="annotations">{escape("; ".join(row.annotations))}</td>'
            f'<td data-result="{_tag(row.verdict)}">'
            f'{escape(_RESULT_WORDS.get(row.verdict, row.verdict))}</td></tr>')
    return _scrolls(
        f'<table data-section="changes" data-verb="{_tag(verb)}" data-shape="dag"><thead><tr>'
        "<th>#</th><th>node</th><th>baseline</th><th>candidate</th>"
        "<th>annotations</th><th>result</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>")


#: The changes table's scroll region's name, for a screen reader.
CHANGES_REGION = "Changes, scrolls sideways"


def _scrolls(table: str) -> str:
    """The changes table in a scroll region of its own: on a narrow screen it scrolls inside its
    panel instead of making the whole page scroll sideways. A keyboard can reach it and a screen
    reader names it."""
    return scroll_region(table, CHANGES_REGION, "changes")


def _side(side) -> str:
    """One side of a ladder row, as the report gives it. Digests shown, never shortened.

    Truncating a digest on a page is how two different records come to look like one.
    """
    if not isinstance(side, dict):
        return ""
    outputs = side.get("outputs") or []
    #: The SDK writes null for an output its receipt gave no digest (records.py).
    return " ".join(o if isinstance(o, str) else "(no digest recorded)" for o in outputs)


def _localized(report) -> str:
    """The minimal-unclean or localized set, where one exists; an absence sentence otherwise."""
    nodes = tuple(getattr(report, "minimal_unclean_nodes", ()) or ())
    if not nodes:
        located = getattr(report, "nodes", None)
        if located:
            nodes = tuple(n.node for n in located)
    if not nodes:
        first = getattr(report, "first_difference", None)
        if first:
            #: Named as the report names it, "stage 4 · split" -- not the dict's repr (the
            #: second confirmation review, S4).
            where = (f"stage {first.get('index')} · {first.get('stage')}"
                     if isinstance(first, dict) else str(first))
            return (f'<p data-section="localized">The first difference is at '
                    f"{escape(where)}. No smaller set was reported.</p>")
        return ('<p data-section="localized">The report names no localized set. That is '
                "what it says, not a gap in this page.</p>")
    items = "".join(f'<li class="mono">{named(str(n))}</li>' for n in nodes)
    #: No count in the heading: the report carries no total for the
    #: nodes it walked, so there is no honest denominator. The list below is the set.
    return (f'<h3>The set it localized</h3>'
            f'<ul class="plain" data-section="localized">{items}</ul>')


#: The panel's words where nothing is matched. `none` is said only of two identical runs, the
#: one case where the comparison found no first difference. `graph` and
#: `undecided` are canary's proposed words, after a form fixed for a cause that turned out
#: not to be this one; they are not yet fixed.
SAME_CHANGE_WORDS = {
    "none": "The two runs do not differ, so there is no change to look for.",
    "graph": ("This console doesn't match a graph comparison's first differences against other "
              "runs, so it doesn't look for other runs with the same change."),
    "undecided": ("This console can't read a first difference from this comparison's diff "
                  "report, so it doesn't look for other runs with the same change."),
}


def _same_change(comparison, store: Store) -> str:
    """The "Other runs with the same change" panel, below the pair.

    Its matching rule is on the page, by exact equality; it shows counts with their
    denominators and a plain list of run ids; it never says what the change did in them.
    Nothing is compared automatically: the pair is the one somebody asked for, and this only
    counts which other stored runs carry the same recorded digest.
    """
    from onetrace_console.overview import same_change

    found = same_change(comparison, store)
    head = "<h2>Other runs with the same change</h2>"
    if found.state in SAME_CHANGE_WORDS:
        said = SAME_CHANGE_WORDS[found.state]
        return (f'<section data-section="same-change" data-state="{found.state}">{head}'
                f"<p>{escape(said)}</p></section>")
    at = f"stage {found.index} · {found.stage}"
    if found.state == "unreadable":
        said = f"The receipts of this pair could not be read at {at}, so no other run is matched."
        return f'<section data-section="same-change">{head}<p>{escape(said)}</p></section>'
    if found.state == "unchanged":
        return (f'<section data-section="same-change">{head}<p>'
                + escape(f"No recorded settings or code digest at {at} differs between the two "
                         "runs, so there is no recorded change to look for elsewhere.")
                + "</p></section>")
    n = len(found.matches)
    runs = "run" if n == 1 else "runs"
    total = "run" if found.in_pipeline == 1 else "runs"
    items = "".join(f'<li data-run="{_tag(r.key)}"><span class="mono" data-words="record">'
                    f"{named(r.run_id, record_href(r))}</span></li>" for r in found.matches)
    return (f'<section data-section="same-change">{head}'
            f"<p>Matching rule: the same {escape(found.what)} digest at {escape(at)}, by exact "
            f'equality: <span class="mono">{escape(found.digest)}</span>.</p>'
            f'<p><a href="#same-change-list">{n} other {runs} in {escape(found.pipeline)} carry '
            f"it, of {found.in_pipeline} {total} in {escape(found.pipeline)}</a>.</p>"
            "<p>Nothing here says what the change did in those runs.</p>"
            f'<ul class="plain" id="same-change-list">{items or "<li>none</li>"}</ul></section>')


def _held(store: Store, key: str):
    """A stored run, or None where there is none -- or its record cannot be read:
    the store names that on Home, and a Diff page is not stopped by it."""
    from onetrace_console.store import StoreError
    try:
        return store.get_run(key)
    except StoreError:
        return None


#: What the layer says where it cannot show the SDK's own layout. The SDK's line breaks
#: and a record's are then told apart by nothing, so every one is shown escaped.
SDK_TEXT_NO_REPORT = ("The SDK wrote no report for this, so its output is shown with every line "
                      "break and control character escaped.")
SDK_TEXT_NOT_REBUILT = ("This text is not what the SDK's own report gives, so it is shown with "
                        "every line break and control character escaped.")
#: Where the SDK's text is its report's but holds a character of the SDK's own escaped class raw:
#: the SDK leaves three fields as given (`path`, `carried`, `text` -- `onetrace.report._NOT_ESCAPED`),
#: so a report written elsewhere can carry one through. Canary's words, submitted for review.
SDK_TEXT_RAW = ("This text holds a character the SDK left unescaped, so it is shown with every line "
                "break and control character escaped.")


def _ordered_as(value, stored: str):
    """The report with every object's keys in the order they first appear in the SDK's stored
    text. The SDK writes its JSON canonical, keys sorted, while its text walks some objects in the
    order it built them -- an annotation's `differs` -- so the stored text is the only record of
    that order. Nothing but the order changes, and `text()` over the result is checked against the
    stored text, byte for byte, before anything is drawn from it.

    Each distinct key is looked for once (measured before: every key of every object searched
    the whole text, and 5,000 ladder rows took 156 s). It still grows faster than linearly, each
    key searched from the start of the text; what bounds it is the number of stages a report can
    hold, which is bounded by the members a delivery may have: `Config.max_members`, 512 by
    default and in `config/default.json` and `config/container.json`, enforced at ingest by
    `ingest.read_tar` ("the archive holds no more than the configured member limit"). At 512 this
    takes about 0.1 s; an operator raising that limit raises this cost with it."""
    #: Since 0.2.0 the stored text names a key as the SDK escaped it: looked for in
    #: that form first, then as it is (a key with nothing to escape is the same either way).
    from onetrace.escaping import escaped
    seen: dict[str, int] = {}

    def first_seen(key) -> int:
        if not isinstance(key, str):
            return len(stored)
        if key not in seen:
            shown = escaped(key)
            at = stored.find(shown)
            if at < 0 and shown != key:      # one search for a key with nothing to escape
                at = stored.find(key)
            seen[key] = at if at >= 0 else len(stored)
        return seen[key]

    def ordered(value):
        if isinstance(value, dict):
            return {k: ordered(value[k]) for k in sorted(value, key=first_seen)}
        if isinstance(value, list):
            return [ordered(v) for v in value]
        return value

    return ordered(value)


def _sdk_layer(comparison: StoredComparison, verb: str, store: Store) -> tuple[str, str]:
    """`_sdk_layer_as_written`, with this host's folders taken out of it: the SDK's
    text names the folders it was given, which were this console's temporary folders. The pair's
    are named for what they held; any other under this host's temp folder is said to be one."""
    shown, note = _sdk_layer_as_written(comparison, verb, store)
    return _without_host_folders(shown, comparison, verb, store), note


#: On Windows the pair's folders are matched case-insensitively.
_FOLDERS_CASE_INSENSITIVE = os.name == "nt"


def _named_folder(shown: str, path: str, name: str) -> str:
    """`path` named in the SDK's words in every form they can hold it: as given and
    as resolved, each as written and with its backslashes doubled -- the SDK's text escapes a
    backslash one-to-one since 0.2.0 (B1, `onetrace.escaping`) -- stated here, not through the
    viewer's display(); case-insensitively on Windows. 8.3 short names are not expanded
    (not observed)."""
    given = {path}
    try:
        given.add(str(Path(path).resolve()))
    except (OSError, ValueError, RuntimeError):
        pass
    forms = {f for g in given for f in (g, g.replace("\\", "\\\\"))}
    flags = re.IGNORECASE if _FOLDERS_CASE_INSENSITIVE else 0
    for form in sorted(forms, key=len, reverse=True):
        shown = re.sub(re.escape(form), lambda _m: name, shown, flags=flags)
    return shown


def _without_host_folders(shown: str, comparison: StoredComparison, verb: str, store: Store) -> str:
    """The SDK's words with this host's folders taken out: the pair's named for what
    they held, any other under this host's temp folder said to be one. For the text layer, and
    for the envelope's reason, which names a folder when the SDK refuses a pair (30bv §3.3)."""
    import tempfile

    from onetrace_console.compare import report_json
    try:
        rep = report_json(comparison, verb, store)
    except (ValueError, UnicodeDecodeError, RecursionError):
        rep = None
    inputs = rep.get("inputs") if isinstance(rep, dict) else None
    for side, given in (inputs.items() if isinstance(inputs, dict) else ()):
        path = given.get("path") if isinstance(given, dict) else None
        if isinstance(path, str) and len(path) > 3:
            shown = _named_folder(shown, path, f"(the {side} run's folder)")
    roots = {tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve())}
    for root in sorted(roots | {r.replace("\\", "\\\\") for r in roots}, key=len, reverse=True):
        shown = re.sub(re.escape(root) + r"[^\s'\"]*", "(a temporary folder of this host's)",
                       shown, flags=re.IGNORECASE)
    return shown


def _sdk_layer_as_written(comparison: StoredComparison, verb: str,
                          store: Store) -> tuple[str, str]:
    """(the SDK's text as the layer shows it, and a note where that is not the SDK's layout).

    Since the 0.2.0 SDK its text report escapes every record-derived
    string itself, one-to-one (`onetrace.escaping`; `printable()` before `text()` draws), with a
    class that covers everything the viewer's `display` escapes and 163 code points more
    (`tests/test_sdk_escaping_class.py` holds that). So the layer shows the SDK's stored text **as
    it is, once** -- where `text()` over the stored JSON report, its keys in the stored text's order
    (`_ordered_as`), gives exactly the stored text, so the layer and the SDK agree. The console's
    own pass over the report escaped it a second time and is retired. Otherwise --
    no report, a report this `text()` cannot draw, or a text that is not its report's -- the whole
    text is escaped, line breaks included, and the note says so.
    """
    from onetrace.report import text as sdk_text
    from onetrace_console.viewer.page import display

    from onetrace_console.compare import report_json
    stored = report_text(comparison, verb, store)
    try:
        rep = report_json(comparison, verb, store)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return display(stored), SDK_TEXT_NOT_REBUILT
    if not isinstance(rep, dict):
        return display(stored), SDK_TEXT_NO_REPORT if rep is None else SDK_TEXT_NOT_REBUILT
    try:
        if sdk_text(_ordered_as(rep, stored)) == stored:
            from onetrace.escaping import escaped
            #: Shown as it is only if no character of the SDK's own class is in it raw -- its own
            #: line breaks aside -- since the SDK leaves three fields as given.
            if any(escaped(line) != line.replace("\\", "\\\\") for line in stored.split("\n")):
                return display(stored), SDK_TEXT_RAW
            return stored, ""
    except Exception:  # noqa: BLE001 - a report its own text() cannot draw is shown escaped
        pass
    return display(stored), SDK_TEXT_NOT_REBUILT


#: The comparison page's headings for the SDK's verbs, in plain words.
VERB_HEADINGS = {DIFF: "What changed between the two runs"}

#: The diff report's envelope, said plainly. The SDK's own word and its exit code stay in its
#: report, shown as it wrote it.
DIFF_ENVELOPES = {
    "identical": "The two runs do not differ.",
    "diverged": "The two runs differ.",
    "not comparable": "The two runs cannot be compared.",
    "refused": "The comparison was refused.",
    "could not check": "The comparison could not check the two runs.",
}

#: What a graph-shaped pair's pages do not draw, said once at the end of the page.
NOT_SHOWN = "Not shown for graph-shaped runs: where the change started, and other runs with the same change."
NOT_SHOWN_WHY = {
    "localize": ("This console draws where the change started only for two linear runs; the SDK's "
                 "localize report for this pair is below, as it wrote it."),
    "same-change": ("Other runs with the same change are not looked for: this console doesn't match a "
                    "graph comparison's first differences against other runs."),
}


def _not_shown(hidden: list[tuple[str, list[str]]]) -> str:
    """The one closed line for what a graph-shaped pair's pages cannot draw: each reason in one
    plain sentence, then the SDK's own words for it."""
    body = "".join(f'<p data-section="not-shown-{name}">{escape(NOT_SHOWN_WHY[name])}</p>'
                   + "".join(parts) for name, parts in hidden)
    return (f'<details data-section="not-shown"><summary>{escape(NOT_SHOWN)}</summary>'
            f"{body}</details>")


def render_diff(comparison: StoredComparison, store: Store, *, generated_at: str) -> str:
    """One pair's Diff page: the SDK's changes table, its localized set, and the command.

    The reports are read with the viewer's strict reader, so an SDK report this console has
    not been taught is **refused** rather than half-rendered (the F16 lesson at the input).
    """
    import tempfile

    from onetrace_console.viewer.verbs import Failure, TwoRun, TwoRunDag, VerbReportUnreadable, read_report

    #: Both runs of the pair, so a preview run on either side labels the page. A run compared
    #: with itself is one run, not two: keyed, so neither its label nor its incidents double.
    pair = list({r.key: r for r in (_held(store, comparison.run_a),
                                    _held(store, comparison.run_b)) if r is not None}.values())

    from onetrace_console.unreadable import report_refused

    blocks: list[str] = [
        f'<h1>Diff</h1><p data-section="pair">baseline '
        f"{run_named(store, comparison.run_a)} against candidate "
        f"{run_named(store, comparison.run_b)}</p>"]
    #: First, when the two runs come from different pipelines.
    blocks.append(_different_pipelines(pair))
    #: A graph-shaped pair: what its pages cannot draw is one closed line at the end, not
    #: sections that say so (`_not_shown`).
    dag, hidden = False, []

    for verb in (DIFF, LOCALIZE):
        run = comparison.verb(verb)
        if run is None:
            continue
        start = len(blocks)
        blocks.append(f"<h2>{escape(VERB_HEADINGS.get(verb, verb))}</h2>")
        if run.note:
            #: The runner failed to get an answer. Said as the runner's failure, never as
            #: something the SDK reported.
            blocks.append(f'<p data-section="{escape(verb)}-note">This console did not '
                          f"obtain an answer: {escape(run.note)}. Nothing is shown below "
                          "because there is nothing the SDK said.</p>")
            continue

        report, annotations, identical, refused = None, [], None, False
        if any(name == f"{verb}.json" for name, _ in run.reports):
            with tempfile.TemporaryDirectory(prefix="onetrace-render-") as tmp:
                folder = Path(tmp)
                try:
                    #: Never over a file already written; said below if so.
                    for name, key in run.reports:
                        (folder / name).parent.mkdir(parents=True, exist_ok=True)
                        create_exclusively(folder / name, store.get(key), named=name)
                    #: `diff` over two graph-shaped runs is read and drawn on
                    #: the graph; `localize`'s graph report stays refused, as before.
                    report = read_report(folder, two_run_dag=verb == DIFF)
                    #: Only the kinds of report this verb writes on a pair of runs: a
                    #: comparison, or the verb saying it could not start (the review found a
                    #: single-run or re-check report here crashing the page).
                    if not (isinstance(report, (TwoRun, TwoRunDag, Failure))
                            and report.verb == verb):
                        raise VerbReportUnreadable(
                            f"{verb}.json holds a {report.verb} report of another kind, not "
                            f"a comparison of two runs")
                    annotations = _annotations(folder, verb)
                    if verb == DIFF and getattr(report, "ladder", None):
                        identical = _identical_before(folder, verb, report)
                except Exception as e:  # noqa: BLE001 - stated on the page, and logged
                    #: Refused, not half-rendered, and said on the page rather than raised
                    #: past it: nothing is drawn from this report,
                    #: and its own words still follow below.
                    from onetrace_console.pages import refusal
                    viewers = isinstance(e, VerbReportUnreadable)
                    reason = str(e) if viewers else refusal(e)[0]
                    report, annotations, identical = None, [], None
                    blocks.append(report_refused(verb, reason, from_viewer=viewers))
                    refused = True

        if report is not None:
            #: In plain words; the exit code is the SDK's own, kept in its report below.
            blocks.append(
                f'<p data-section="{escape(verb)}-envelope" '
                f'data-verdict="{_tag(report.envelope)}">'
                + (escape(DIFF_ENVELOPES.get(report.envelope, f"diff: {report.envelope}"))
                   if verb == DIFF else f"{escape(verb)}: {escape(report.envelope)}")
                + (f" — {escape(_without_host_folders(str(report.reason), comparison, verb, store))}"
                   if getattr(report, "reason", None) else "")
                + "</p>")
            if isinstance(report, TwoRunDag):
                #: The graph over both runs' nodes, then its table. The SDK names
                #: the runs A and B ("present in B only"), so the page says which is which once,
                #: at the top, in place of the header line.
                dag = dag or verb == DIFF
                ab = _runs_ab(comparison, store)
                if ab not in blocks:
                    blocks[0] = '<h1>Diff</h1>' + ab
                graph = _compare_graph(report, comparison, store)
                blocks.append(graph)
                blocks.append(_dag_table(report, verb))
                blocks.append(_graph_caveat(report))
            #: One summary per page, from diff's report: localize's ladder is the same walk,
            #: and its own contribution is the localized set below.
            #: Part V, on a straight-line pair's diff: found once, said in the headline, marked on
            #: the graph, and its rows first in "Settings that changed".
            #: Only over a ladder: a report the SDK refused (`Failure`) has none, and says so itself.
            found = (variance_look_past(report, annotations, comparison, store)
                     if verb == DIFF and getattr(report, "ladder", None)
                     and not isinstance(report, TwoRunDag) else None)
            later = found[1].index if found and found[1] is not None else ""
            if identical is not None:
                blocks.append(_first_difference_summary(report, annotations, identical,
                                                        typed_command(comparison, store, DIFF,
                                                                      text=True),
                                                        records_words(comparison, store),
                                                        variance_sentence(found) if found else ""))
            if verb == DIFF and getattr(report, "ladder", None):
                if not isinstance(report, TwoRunDag):
                    #: The line drawn as the stage table is: the same stages, joined where the
                    #: candidate's receipts record their reads.
                    blocks.append(_linear_graph(report, annotations, input_notes(comparison, store),
                                                recorded_reads(comparison.run_b, store),
                                                recorded_change=later))
                blocks.append(_settings_changed(annotations, first=later))
            if getattr(report, "ladder", None) and not isinstance(report, TwoRunDag):
                blocks.append(_ladder_table(report, verb, annotations=annotations,
                                            anchors=verb == DIFF,
                                            inputs=input_notes(comparison, store)))
            if not isinstance(report, TwoRunDag):
                blocks.append(_localized(report))
            if verb == DIFF:
                blocks.append(_text_diff_section(comparison, store))
                #: Board 7, only where the comparison holds the trace run a
                #: changed corpus link made; elsewhere nothing, as before (`c171976`).
                from onetrace_console.board7 import board7_section
                blocks.append(board7_section(comparison, store))

        #: The SDK's own words, in its own layout, one layer down: the table above is a
        #: rendering OF this. The words it copies from the records are shown escaped inside it,
        #: and the label says so: a record's CR, LF and TAB drew lines
        #: here. Where its layout cannot be kept, the note says so.
        shown, note = _sdk_layer(comparison, verb, store)
        blocks.append(
            f"<details data-layer=\"3\"><summary>The {escape(verb)} report as the SDK wrote "
            f"it, with names from the records escaped</summary>"
            + (f'<p data-section="{escape(verb)}-text-note">{escape(note)}</p>' if note else "")
            + f'<pre data-layer="3">{verbatim(shown)}</pre></details>')
        blocks.append(
            f'<p data-section="{escape(verb)}-repeat">Repeat this yourself:</p>'
            f"<pre><code>{verbatim(typed_command(comparison, store, verb))}</code></pre>")
        if dag and verb == LOCALIZE and refused:
            #: A graph pair's localize report is refused by design: not drawn as a section. Its
            #: reason and the SDK's own words go in the closed line at the end of the page.
            section = blocks[start:]
            del blocks[start:]
            hidden.append(("localize", [b for b in section[1:]
                                        if 'data-section="localize-unreadable"' not in b
                                        and "report-refused" not in b]))

    same = _same_change(comparison, store)
    if dag and 'data-state="graph"' in same:
        hidden.append(("same-change", []))
    else:
        blocks.append(same)
    if hidden:
        blocks.append(_not_shown(hidden))

    #: `sdk_source_digest` used to be shown here; it was removed as redundant with
    #: `sdk_build_digest` (the installed wheel's own sha256, since the SDK came from PyPI --
    #: a commit, before it), which is what a reader sees instead: a strictly finer signal
    #: for "which exact build produced this", truncated the same way the digest was.
    build = comparison.sdk_build_digest or "unknown"
    blocks.append(
        f'<p data-section="sdk">Compared with onetrace {escape(comparison.sdk_version)}, '
        f'build <span class="mono">{escape(build[:23])}</span>, '
        f"at {time_html(comparison.ran_at)}.</p>")
    blocks.append(f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>')
    blocks.append(generated_footer(generated_at))
    #: The incidents raised from this pair's own runs.
    from onetrace_console.incident_pages import incidents_block
    from onetrace_console.incidents import derive
    every = derive(store)
    keys = {r.key for r in pair}
    raised = tuple(i for i in every if i.subject in keys)
    blocks = ['<div class="cp">', *blocks, "</div>"]  # the console's page skin (item 12)
    #: The Diff page lives at diff/<key>.html: one folder down.
    page = incidents_block(_document("Diff", "\n".join(blocks)), raised, len(every), store,
                           up="../")
    return label(page, pair)


# --------------------------------------------------------------------- the Home page

#: The "?" on each card: the native disclosure, reached by the keyboard, needing no script.
DEFINITION_SUMMARY = "What this count means"


def _card(name: str, title: str, lead: str, href: str, line: str, definition: list[str]) -> str:
    """One Overview card: its title, its count as a link to exactly what it counted, one short
    line under it, and the plain sentences that say what the count rests on behind its "?" --
    folded, never left out."""
    told = "".join(f"<p>{d}</p>" for d in definition)
    return (f'<div data-card="{_tag(name)}"><h3>{escape(title)}</h3>'
            f'<p class="lead"><a href="{_tag(href)}">{_kpi(lead)}</a></p>{line}'
            f'<details class="def"><summary title="{DEFINITION_SUMMARY}" '
            f'aria-label="{DEFINITION_SUMMARY}">?</summary>{told}</details></div>')


def _states_line(tallies) -> str:
    """A card's breakdown in one short line: each state with runs, as a count opening exactly
    those runs; the states at 0 folded into one grey line that still names and links each."""
    said = [t for t in tallies if t.count]
    zero = [t for t in tallies if not t.count]
    #: Each count with its denominator, as every count on the page is.
    line = " · ".join(f'<a href="{_tag(t.href)}">{t.count} of {t.denominator} {escape(t.label)}</a>'
                      for t in said)
    out = f'<p data-line="states">{line}</p>' if said else ""
    if zero:
        named = ", ".join(f'<a href="{_tag(t.href)}">{escape(t.label)}</a>' for t in zero)
        out += (f'<p class="zero" data-line="zero">0 of {zero[0].denominator} in the other '
                f'states: {named}</p>')
    return out


def _kpi(lead: str) -> str:
    """Board 1's large figure: the count a card's sentence opens with, set large, and the rest of
    the same sentence beside it -- inline, so the sentence is still one sentence, word for word."""
    import re
    m = re.match(r"(\d[\d,]*)(.*)", lead, re.S)
    if not m:
        return escape(lead)
    return f'<span class="kpi">{escape(m.group(1))}</span><span class="of">{escape(m.group(2))}</span>'


def _cards(store: Store, by_slug: dict) -> str:
    """The four cards: runs, records agree, changed vs baseline and
    incidents. No permit or decision figure. "Open incidents" is not shown as drawn: an
    incident has no open or closed state in this console, so the card counts incidents
    raised and says why."""
    from onetrace_console.incident_pages import INCIDENTS
    from onetrace_console.incidents import derive
    from onetrace_console.overview import PIPELINE_RULE, pipelines

    runs = store.runs()
    total = len(runs)
    found = pipelines(store)
    word = "pipeline" if len(found) == 1 else "pipelines"
    unit = "run" if total == 1 else "runs"
    agree, changed = by_slug["records-agree"], by_slug["changed-vs-baseline"]
    others = [by_slug[s] for s in ("holds", "could-not-check", "contradicts", "not-checked")]
    compared = sum(1 for r in runs if any(c.run_b == r.key for c in store.comparisons()))
    every = derive(store)
    raised_from = len({i.subject for i in every if i.subject_kind == "run"})
    incident_word = "incident" if len(every) == 1 else "incidents"
    #: Each card leads with its count in one short line; what the count rests on follows in the
    #: card's muted lines, in the words the longer lead used to carry.
    cards = [
        _card("runs", "Runs", f"{total} {unit} stored", by_slug["all"].href,
              f"<p>{escape(f'Stored in {len(found)} {word}.')}</p>", [escape(PIPELINE_RULE)]),
        _card("records-agree", "Records agree", f"{len(agree.runs)} of {total} {unit} verified",
              agree.href, _states_line(others),
              [escape("Verified: " + agree.label.split(": ", 1)[1] + "."),
               escape("Below the count: each verdict the check recorded, as a count of runs; "
                      "All counts has each in full.")]),
        _card("changed-vs-baseline", "Changed vs baseline",
              f"{len(changed.runs)} of {total} {unit} changed vs baseline", changed.href,
              f"<p>{escape(f'{total - compared} of {total} {unit} are no comparison' + chr(39) + 's candidate.')}</p>",
              [escape("Changed: the run was the candidate in a stored comparison that found a "
                      "first difference."),
               escape("The baseline is the run each was compared with; this console picks "
                      "none.")]),
        _card("incidents", "Incidents", f"{len(every)} {incident_word}", INCIDENTS,
              f"<p>{escape(f'{len(every)} {incident_word} raised from {raised_from} of {total} {unit}.')}</p>",
              [escape("This console keeps no open or closed state for an incident, so none "
                      "is called open.")]),
    ]
    return f'<section data-section="cards">{"".join(cards)}</section>'


def _run_link(run) -> str:
    """A run's id, linking to its case page (rendered beside it by `pages.render_execution`)."""
    from onetrace_console.viewer.model import NAME_CAP
    return (f'<a href="runs/{_tag(run.key)}/case.html">'
            f'<span class="mono" data-words="record">{escape(run.run_id[:NAME_CAP])}</span></a>'
            + rest(run.run_id, record_href(run)))


#: How many runs the needs-attention panel shows before "all of them".
ATTENTION_SHOWN = 5

#: Each reason a run needs attention, and a run against its baseline, coloured by the one rule
#: for every page (`tones.py`): a check that ran and failed is red, one that couldn't be done or
#: wasn't done amber, evidence not made neutral, a check that held green.
ATTENTION_TONE = {kind: tones.tone(tones.ATTENTION, kind) for kind in tones.ATTENTION}
BASELINE_TONE = {state: tones.tone(tones.BASELINE, state) for state in tones.BASELINE}


def _preview_runs_line(store: Store) -> str:
    """One line, only where stored preview runs can't be checked by 0.2.0."""
    from onetrace_console.checks import is_preview_not_verified, preview_overview_line
    n = sum(1 for r in store.runs() if is_preview_not_verified(r))
    return f'<p data-preview-runs="{n}">{escape(preview_overview_line(n))}</p>' if n else ""


def _needs_attention(store: Store) -> str:
    """v6 board 1's "Needs attention first": the count with its denominator, the ordering rule
    in words, the first few runs in that order, and all of them one link away.
    Never blank: a store the rule finds nothing in says so."""
    from onetrace_console.overview import ATTENTION_RULE, ATTENTION_WORDS, needs_attention

    listed, total = needs_attention(store), len(store.runs())
    unit = "run" if total == 1 else "runs"
    heading = f"<h2>Needs attention first · {len(listed)} of {total} {unit}</h2>"
    rule = f"<p>{escape(ATTENTION_RULE)}</p>" + _preview_runs_line(store)
    if not listed:
        return (f'<section data-section="needs-attention"><div class="head">{heading}</div>'
                f"{rule}<p>No run needs attention by this rule.</p></section>")
    #: Board 1: the kind as a pill and the run on the left, the time on the right. The words
    #: and their " · " stay in one item, so the item reads as it did.
    items = "".join(
        f'<li data-attention="{_tag(kind)}"><span>'
        f'<span class="pill {ATTENTION_TONE[kind]}">{escape(ATTENTION_WORDS[kind])}</span> · '
        f'{_run_link(run)}</span> <span class="value">· received <time datetime="{escape(run.received_at)}" '
        f'title="{escape(run.received_at)}">{escape(short_time(run.received_at))}</time></span></li>'
        for kind, run in listed[:ATTENTION_SHOWN])
    return (f'<section data-section="needs-attention"><div class="head">{heading}'
            f'<p><a href="executions-needs-attention.html">All {len(listed)} of them</a></p>'
            f'</div>{rule}<ul class="plain">{items}</ul></section>')


def _recorded_of_declared(run) -> str:
    """The declared stages with at least one receipt, out of the stages its receipts declare,
    and the retries recorded: "6 of 6 declared stages; 1 retry recorded". Counting receipts
    read "7 of 6" with a retry, and could hide a missing stage behind one. Where the receipts
    declare none, that is said, never "2 of 0"."""
    if run.stage_count:
        said = f"{run.delivered_stages} of {run.stage_count} declared stages"
        if run.retries:
            said += f"; {run.retries} {'retry' if run.retries == 1 else 'retries'} recorded"
        #: A last failed attempt, appended in its fixed words.
        from onetrace_console.overview import last_failed
        failed = last_failed(run)
        if failed:
            said += "; last attempt failed: " + ", ".join(stage for stage, _ in failed)
        return said
    return f"{run.recorded_count} delivered · none declared"


def _recent_runs(store: Store) -> str:
    """v6 board 1's "Recent runs": newest arrival first, each with what its record says --
    its pipeline (declared stage list), its receipts against its declared stages, how it
    compares with the baseline it was compared against, and its recorded verdict."""
    from onetrace_console.home import MOST_RECENT, VERDICT_LABELS, verdict_of
    from onetrace_console.overview import pipelines, ran_at, vs_baseline

    runs = store.runs()
    recent = runs[:MOST_RECENT]
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}

    def pill(words: str, tone: str) -> str:
        return f'<span class="pill {tone}">{escape(words)}</span>'

    rows = []
    for r in recent:
        state, words = vs_baseline(r, store)
        verdict = verdict_of(r)
        rows.append(
            f'<tr data-recent="{_tag(r.key)}"><td>{_run_link(r)}</td>'
            f"<td>{escape(label[r.key])}</td>"
            f'<td class="value">{_recorded_of_declared(r)}</td>'
            f"<td>{pill(words, BASELINE_TONE.get(state, 'neu'))}</td>"
            f"<td>{pill(VERDICT_LABELS[verdict], tones.tone(tones.VERDICT, verdict))}</td>"
            f'<td class="value">{time_html(ran) if (ran := ran_at(r)) else "not recorded"}</td>'
            f'<td class="value">{time_html(r.received_at)}</td></tr>')
    rows = "".join(rows)
    return (f'<section data-section="recent-runs">'
            f'<div class="head"><h2>Recent runs · {len(recent)} of {len(runs)}</h2>'
            '<p><a href="executions-all.html">All of them</a></p></div>'
            + scroll_region('<table class="board"><thead><tr><th>Run</th><th>Pipeline</th>'
                            "<th>Declared stages delivered</th><th>Vs baseline</th><th>Records</th>"
                            "<th>Ran</th><th>Received by this console</th></tr></thead>"
                            f"<tbody>{rows}</tbody></table>",
                            "Recent runs, scrolls sideways", "recent-runs")
            + "</section>")


def _pipelines(store: Store) -> str:
    """The pipelines table, from the data already stored: one row per declared
    stage list, its runs as a count of every run stored (opening exactly those runs), each
    recorded verdict as a count of the pipeline's own runs, and its latest arrival."""
    from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
    from onetrace_console.home import NOT_CHECKED, verdict_of
    from onetrace_console.overview import PIPELINE_RULE, pipelines

    found, total = pipelines(store), len(store.runs())
    rows = []
    for p in found:
        n = len(p.runs)
        verdicts = [sum(1 for r in p.runs if verdict_of(r) == v)
                    for v in (HOLDS, CONTRADICTS, COULD_NOT_CHECK, NOT_CHECKED)]
        stages = " → ".join(shown_name(s) for s in p.stages) if p.stages else "(no stages declared)"
        if p.more:
            #: The first LIST_CAP, then how many more, in the viewer's words.
            from onetrace_console.viewer.sentences import template
            stages += " " + template("list.more").format(n=str(p.more))
        rows.append(
            f'<tr data-pipeline="{_tag(p.label)}"><td>{escape(p.label)}</td>'
            f'<td data-words="record">{escape(stages)}</td>'
            f'<td class="value"><a href="executions-pipeline-{_tag(p.label.lower())}.html">'
            f"{n} of {total}</a></td>"
            + "".join(f'<td class="value">{c} of {n}</td>' for c in verdicts)
            + f'<td class="value">{time_html(max(r.received_at for r in p.runs))}</td></tr>')
    return (f'<section data-section="pipelines">'
            f'<div class="head"><h2>Pipelines · {len(found)}</h2></div>'
            f"<p>{escape(PIPELINE_RULE)}</p>"
            + scroll_region('<table class="board"><thead><tr><th>Pipeline</th><th>Declared stages</th>'
                            "<th>Runs</th><th>Verified</th><th>Contradicts its record</th>"
                            "<th>Couldn't check</th><th>No verdict recorded</th>"
                            "<th>Latest received by this console</th></tr></thead>"
                            f"<tbody>{''.join(rows)}</tbody></table>",
                            "Pipelines, scrolls sideways", "pipelines")
            + "</section>")


def _by_day(store: Store) -> str:
    """Verdicts by day, with a change marker.

    Each day's verdicts are counts of that day's runs, never percentages. Between two days a
    marker row (`data-change-marker`) stands only where a pipeline's recorded digests for a
    stage differ from the day before, and it names what changed, with both digests whole. No
    arrow, and no word for a direction: it says what the records say changed, nothing about
    whether anything got better or worse.
    """
    from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS
    from onetrace_console.home import NOT_CHECKED, verdict_of
    from onetrace_console.overview import days, markers

    found = days(store)
    changes, unreadable = markers(store)
    rows = []
    for i, day in enumerate(found):
        n = len(day.runs)
        counts = [sum(1 for r in day.runs if verdict_of(r) == v)
                  for v in (HOLDS, CONTRADICTS, COULD_NOT_CHECK, NOT_CHECKED)]
        rows.append(f'<tr data-day="{_tag(day.date)}"><td class="value">{escape(day.date)}</td>'
                    f'<td class="value">{n}</td>'
                    + "".join(f'<td class="value">{c} of {n}</td>' for c in counts) + "</tr>")
        if i < len(changes) and changes[i]:
            said = "; ".join(
                f"{m.pipeline} · stage {shown_name(m.stage)} · {m.what} changed: from "
                f"{', '.join(m.before)} to {', '.join(m.after)}" for m in changes[i])
            names = ",".join(sorted({f"{m.pipeline}/{shown_name(m.stage)}/{m.what}"
                                     for m in changes[i]}))
            rows.append(f'<tr data-change-marker="{_tag(names)}"><td colspan="6">'
                        f'<span class="mono">{escape(said)}</span></td></tr>')
    note = (f"<p>The receipts of {unreadable} of {len(store.runs())} runs could not be read, so "
            "no change is marked on their account.</p>" if unreadable else "")
    #: The days are the days the runs arrived, and the heading says so.
    return ('<section data-section="by-day">'
            '<div class="head"><h2>Verdicts by day received</h2></div>'
            "<p>Each day's verdicts are counts of the runs received that day. A marker row "
            "between two "
            "days names a recorded settings or code digest that differs from the day before, "
            "in a pipeline with runs on both days.</p>"
            f"{note}"
            + scroll_region('<table class="board"><thead><tr><th>Day received</th><th>Runs</th>'
                            "<th>Verified</th><th>Contradicts its record</th>"
                            "<th>Couldn't check</th><th>No verdict recorded</th></tr></thead>"
                            f"<tbody>{''.join(rows)}</tbody></table>",
                            "Runs by day, scrolls sideways", "by-day")
            + "</section>")


#: The Overview's banner states a fact about the stored runs, from each run's own
#: "Signed by a known recorder?" rung -- shown only when none of them reads Yes, and then in
#: these words. With a run signed by a trusted key there is no banner; the Signed row gives the counts.
#: (It replaced board 1's "Records are unsigned in this release ...", false once signing shipped.)
BANNER = "None of these runs is signed by a key you trust: nothing here shows who wrote them."


def _banner(by_slug: dict) -> str:
    """Only when no stored run reads Yes on "Signed by a known recorder?", counted as the
    Signed row counts it (each run as its own page reads it)."""
    if by_slug["signed-yes"].count:
        return ""
    return f'<p data-section="banner">{escape(BANNER)}</p>'


def _signing(by_slug: dict) -> str:
    """"{n} yes · {u} key not trusted · {f} the check failed · {s} unsigned · {c} couldn't check ·
    {x} not checked", each count linking to the runs it counted, any at 0 left out."""
    from onetrace_console.home import SIGNATURE_FORMS
    return " · ".join(f'<a href="{_tag(by_slug[f"signed-{slug}"].href)}">'
                      f'{by_slug[f"signed-{slug}"].count} {escape(words)}</a>'
                      for slug, _readings, words in SIGNATURE_FORMS
                      if by_slug[f"signed-{slug}"].count)


def _anchoring(by_slug: dict) -> str:
    """"{n} yes · {c} couldn't check · {f} the check failed · {u} not anchored · {x} not checked",
    each count linking to the runs it counted and any at 0 left out."""
    from onetrace_console.home import ANCHOR_FORMS
    forms = [(by_slug[f"anchored-{reading}"], words) for reading, words in ANCHOR_FORMS]
    forms.append((by_slug["anchored-not-checked"], "not checked"))
    return " · ".join(f'<a href="{_tag(t.href)}">{t.count} {escape(words)}</a>'
                      for t, words in forms if t.count)


def _evidence(store: Store, by_slug: dict) -> str:
    """v6 board 1's "What the evidence establishes", over every stored run: each rung a
    separate question with its own count and denominator. This console runs no re-check; and
    release 1 has no authorization records -- never a count, never a pass. The
    signing and anchoring rungs count each run's own page's reading of this console's check."""
    total = len(store.runs())
    unit = "run" if total == 1 else "runs"
    agree, holds = by_slug["records-agree"], by_slug["holds"]
    nothing, missing, unknown = (by_slug[s] for s in ("nothing-missing",
                                                       "missing-a-declared-stage",
                                                       "missing-not-established"))
    cnc, contra, unchecked = (by_slug[s] for s in ("could-not-check", "contradicts",
                                                   "not-checked"))
    #: The evidence, as on each run's page: only a check run with the run's output files
    #: required counts as agreeing. A check that held without them is said, not counted.
    without = holds.count - agree.count
    def part(n: int, words: str) -> str:
        """One count in a row of counts; at 0, grey, still said (the zeros are folded, not
        left out)."""
        said = f"{n} {words}"
        return f'<span class="zero">{said}</span>' if n == 0 else said

    rows = [
        ("records-agree", "Records agree",
         f'<a href="{_tag(agree.href)}">{agree.count} of {total}</a> · '
         + " · ".join((part(without, f"held without {'its' if without == 1 else 'their'} output "
                                     "files required"),
                       part(cnc.count, "couldn\'t check"), part(contra.count, "contradict"),
                       part(unchecked.count, "not checked")))),
        #: In the fixed words: each form over all runs stored, zeros left out, each count
        #: linking to its runs.
        ("signed", "Signed by a known recorder?", _signing(by_slug)),
        #: Counted as each run's own page decides rung 3, and each count opens
        #: exactly the runs it counted.
        ("nothing-missing", "No declared stage missing",
         f'<a href="{_tag(nothing.href)}">{nothing.count} of {total}</a> · '
         f'<a href="{_tag(missing.href)}">{missing.count} missing a declared stage</a> · '
         f'<a href="{_tag(unknown.href)}">{unknown.count} not established</a>'),
        ("reproduced", "Re-runnable stages re-run and matched",
         "not checked · this console runs no re-check"),
        ("authorized", "Action authorized, effect confirmed",
         f"No records · {NO_AUTHORIZATION}"),
        #: In the fixed words, as corrected: each form over the runs with this console's check
        #: (any at 0 left out), then the runs without one, inline, in the words "Records agree"
        #: uses for them.
        ("anchored", "Committed by a known time?", _anchoring(by_slug)),
    ]
    body = "".join(f'<tr data-rung="{key}"><td>{escape(question)}</td><td>{answer}</td></tr>'
                   for key, question, answer in rows)
    return (f'<section data-section="evidence"><h2>What the evidence establishes · {total} '
            f'{unit}</h2><p>Each rung is a separate question, with its own evidence.</p>'
            f'<table class="rungs"><tbody>{body}</tbody></table></section>')


def underived_note(store: Store) -> str:
    """The runs and rules the last `derive` could not raise incidents for, named -- never
    dropped from the counts without a word, and never a blank page."""
    failed = store.underived
    if not failed:
        return ""
    items = "".join(f"<li>{escape(f)}</li>" for f in failed)
    return (f'<section data-section="underived"><p>The incidents of {len(failed)} run and rule '
            f'pair{"" if len(failed) == 1 else "s"} could not be derived, so '
            f'{"it is" if len(failed) == 1 else "they are"} in no incident count here:</p>'
            f'<ul class="plain">{items}</ul></section>')


COUNTS = "counts.html"


def _unread(store: Store) -> str:
    """The records no count includes, named (the third confirmation review, NEW-6),
    on every page that shows those counts."""
    #: Run records the store could not read are named, never silently dropped from the counts
    #: (the third confirmation review, NEW-6).
    lost = store.unreadable_runs
    unread = (f'<p data-section="unreadable-records">{len(lost)} stored run record'
              f'{" could" if len(lost) == 1 else "s could"} not be read, so '
              f'{"it is" if len(lost) == 1 else "they are"} in no count below: '
              f'{escape(", ".join(lost))}.</p>' if lost else "")
    #: And a comparison record, which "changed vs baseline" reads.
    store.comparisons()
    gone = store.unreadable_comparisons
    unread += (f'<p data-section="unreadable-comparisons">{len(gone)} stored comparison record'
               f'{" could" if len(gone) == 1 else "s could"} not be read, so no run is counted '
               f'changed vs baseline on {"its" if len(gone) == 1 else "their"} account: '
               f'{escape(", ".join(gone))}.</p>' if gone else "")
    unread += underived_note(store)
    return unread


def watched_section() -> str:
    """While `onetrace-console <runs folder>` watches its folder: what it watches, how often, when
    it last read it, and each run folder changed or gone since it was taken in (its tone by the
    one colour rule). A notice line, empty until the page's script fills it, says when new runs
    have arrived since the page was drawn. Nothing when no folder is watched."""
    from onetrace_console import watch
    from onetrace_console.words import WATCH_SCRIPT
    watcher = watch.CURRENT
    if watcher is None:
        return ""
    state = watcher.state
    notes = "".join(f'<li data-folder-note="{_tag(name)}"><span class="pill {tone}">'
                    f'{escape(name)}</span> {escape(words)}</li>'
                    for name, (tone, words) in sorted(state.changed.items()))
    return (f'<section data-section="watched" data-version="{state.version}" '
            f'data-taken="{len(state.taken)}" data-interval="{state.interval:g}">'
            f"<p>Watching <code>{escape(state.folder)}</code> for new runs, every "
            f"{state.interval:g} s; a run is taken in once it has finished writing. Last read: "
            f'<time data-part="last-read" datetime="{escape(state.last_read)}">'
            f"{escape(short_time(state.last_read)) if state.last_read else 'not yet'}</time>.</p>"
            '<p data-part="notice" hidden><span></span><a href="">Show them</a></p>'
            + (f'<ul class="plain" data-section="folder-notes">{notes}</ul>' if notes else "")
            + WATCH_SCRIPT + "</section>")


#: The Overview's one-line subtitle; what the page's counts rest on is folded under it.
SUBTITLE = "The runs delivered to this console, and what the evidence for each one establishes."


def render_home(store: Store, *, generated_at: str) -> str:
    """Board 1: the cards, what the evidence establishes beside what needs attention first, then
    the recent runs, the pipelines and the verdicts by day. Every count carries its denominator
    and links to exactly what it counted; the full list of counts is the All counts page."""
    run_tallies = tallies(store)
    body = [
        "<h1>Overview</h1>",
        _unread(store),
        f'<p data-section="subtitle">{escape(SUBTITLE)}</p>',
        '<details data-section="how"><summary>How these counts work</summary>'
        '<p data-section="what">Every count below carries the number it was taken from. '
        "A count of runs opens the list of exactly those runs; a count of incidents is out "
        "of every incident raised from the stored runs.</p></details>",
        _banner({t.slug: t for t in run_tallies}),
        watched_section(),
        _cards(store, {t.slug: t for t in run_tallies}),
        '<div class="panels">',
        _evidence(store, {t.slug: t for t in run_tallies}),
        _needs_attention(store),
        "</div>",
        _recent_runs(store),
        _pipelines(store),
        _by_day(store),
        f'<p data-section="all-counts"><a href="{COUNTS}">All counts</a></p>',
        generated_footer(generated_at),
        RELATIVE_TIME_SCRIPT,
    ]
    #: Home shows counts rather than runs, and the specified words are "every page that shows
    #: a preview run". Labelled anyway when any COUNTED run declares preview: a reader takes
    #: numbers off this page, and some of the runs behind them are records the verifier does
    #: not fully check. A superset of what the specification requires, stated here as a reading.
    body = ['<div class="cp">', *body, "</div>"]
    return label(_document("Overview", "\n".join(body)), store.runs())


def render_counts(store: Store, *, generated_at: str) -> str:
    """Every count the Overview draws on, whole, each with its denominator and each linking to
    exactly the runs it counted -- moved from the foot of the Overview, with
    nothing dropped (merge only if nothing is lost).

    Includes one count per incident rule, which links to that rule's own list
    rather than to a filtered Executions page.
    """
    from onetrace_console.home import incident_tallies
    counted = tallies(store) + incident_tallies(store)
    rows = []
    for t in counted:
        reasons = ""
        if t.reasons:
            items = "".join(f"<li>{escape(r)}</li>" for r in t.reasons)
            reasons = (f'<ul class="plain" data-section="reasons">{items}</ul>')
        rows.append(
            f'<li data-tally="{_tag(t.slug)}">'
            f'<a href="{_tag(t.href)}">{escape(t.sentence)}</a>{reasons}</li>')
    body = [
        '<div class="cp">',
        "<h1>All counts</h1>",
        _unread(store),
        f'<p data-section="counts-why">{escape(COUNTS_WHY)}</p>',
        f'<ul class="plain" data-section="counts">{"".join(rows)}</ul>',
        generated_footer(generated_at),
        "</div>",
    ]
    #: Labelled as the Overview is, for the same reason: numbers are taken off this page.
    return label(_document("All counts", "\n".join(body)), store.runs())


#: Was "These counts are kept whole below the cards, because the cards draw on only some of
#: them: ..." on the Overview. On a page of its own, "below the cards" would be untrue, so it names
#: the Overview's cards instead. The rule it rests on (merge into cards only if nothing is lost)
#: stays here, not on the page; these are the fixed words.
COUNTS_WHY = ("Every count is kept whole here, because the Overview's cards draw on only some of "
              "them: the reused-run-id flag, the most recent runs, each pipeline and each "
              "incident rule have no card of their own.")


COMPARISONS = "comparisons.html"


def _newest_first(c: StoredComparison) -> tuple:
    """A comparison's place on the index: newest first by its own `ran_at`, read as a time, so
    two spellings of one moment sort together; a tie by key, ascending. A
    `ran_at` that is not a time with an offset goes after every one that is, by key."""
    from datetime import datetime
    try:
        t = datetime.fromisoformat(c.ran_at)
        if t.tzinfo is None:
            raise ValueError("no offset")
    except (TypeError, ValueError):
        return (1, 0.0, c.key)
    return (0, -t.timestamp(), c.key)


def render_comparisons(store: Store, *, generated_at: str) -> str:
    """Every stored comparison, newest first, each linking to its compare page (approved by
    the maintainer). Unsealed, so its frame is filled as it is served."""
    every = sorted(store.comparisons(), key=_newest_first)
    gone = store.unreadable_comparisons
    #: Never dropped without a word, as the Overview names it.
    unread = (f'<p data-section="unreadable-comparisons">{len(gone)} stored comparison record'
              f'{" could" if len(gone) == 1 else "s could"} not be read, so '
              f'{"it is" if len(gone) == 1 else "they are"} not listed: '
              f'{escape(", ".join(gone))}.</p>' if gone else "")
    if every:
        rows = "".join(
            f'<tr data-key="{_tag(c.key)}"><td class="mono">{time_html(c.ran_at)}'
            f'{"" if _newest_first(c)[0] == 0 else " (not a time; listed last)"}</td>'
            f"<td>{run_named(store, c.run_a)}</td>"
            f"<td>{run_named(store, c.run_b)}</td>"
            f'<td><a href="diff/{_tag(c.key)}.html">Open the comparison</a></td></tr>'
            for c in every)
        listing = scroll_region('<table class="timeline" data-section="comparisons"><thead><tr>'
                                "<th>Compared at</th><th>Baseline</th><th>Candidate</th><th></th></tr>"
                                f"</thead><tbody>{rows}</tbody></table>",
                                "Comparisons, scrolls sideways", "comparisons")
    else:
        listing = '<p data-section="none">Nothing has been compared yet.</p>'
    body = [
        "<h1>Comparisons</h1>",
        unread,
        f'<p data-section="what">{len(every)} stored comparison{"" if len(every) == 1 else "s"}'
        ", newest first by the time each was run; comparisons run at the same moment are "
        "ordered by their key. Each opens its compare page.</p>",
        listing,
        generated_footer(generated_at),
    ]
    body = ['<div class="cp">', *body, "</div>"]
    pair_runs = {r.key: r for c in every for r in (_held(store, c.run_a), _held(store, c.run_b))
                 if r is not None}
    return label(_document("Comparisons", "\n".join(body)), list(pair_runs.values()))


def render_all(store: Store, *, generated_at: str) -> dict[str, str]:
    """Home plus one Executions page per tally, so every link on Home opens.

    The filtered pages are rendered by the viewer's own `render_executions` over exactly the
    runs the tally counted -- the same objects the count came from, which is what makes
    "the number equals the size of the list" a real check rather than two implementations
    agreeing.
    """
    from onetrace_console.pages import render_executions as console_executions

    from onetrace_console.incident_pages import (INCIDENTS, render_incidents,
                                                 render_rule_list, rule_href)
    from onetrace_console.incidents import RULES

    def drawn(build) -> str:
        """One page, or the page saying it could not be drawn: one page's failure never stops
        the others (the second confirmation review, B1)."""
        try:
            return build()
        except Exception as e:  # noqa: BLE001 - stated on that page, and logged
            from onetrace_console.pages import refusal
            from onetrace_console.unreadable import render_failed_page
            return render_failed_page(refusal(e)[0], generated_at=generated_at)

    pages = {HOME: drawn(lambda: render_home(store, generated_at=generated_at)),
             COUNTS: drawn(lambda: render_counts(store, generated_at=generated_at))}
    try:
        counted = tallies(store)
    except Exception:  # noqa: BLE001 - Home above already says what failed
        counted = ()
    #: Each run's list row, read once for every list this render draws: every
    #: list rebuilt every run's full model, and one run of a million gaps took 26 s per list.
    rows: dict = {}
    for t in counted:
        pages[t.href] = drawn(lambda t=t: console_executions(
            list(t.runs), store, generated_at=generated_at, of=t.denominator,
            file_name=t.href, rows=rows, every_stored=t.slug == "all",
            filtered=t.slug != "all"))
    pages[COMPARISONS] = drawn(lambda: render_comparisons(store, generated_at=generated_at))
    #: The Incidents page and one list per rule, so every count on Home opens.
    pages[INCIDENTS] = drawn(lambda: render_incidents(store, generated_at=generated_at))
    for rule in RULES:
        pages[rule_href(rule.id)] = drawn(lambda rule=rule: render_rule_list(
            store, rule.id, generated_at=generated_at))
    #: One page per incident, which the lists' rows open.
    from onetrace_console.incident_pages import incident_href, render_incident_page
    from onetrace_console.incidents import derive
    try:
        every = derive(store)
    except Exception:  # noqa: BLE001 - the Incidents page above says what failed
        every = ()
    for incident in every:
        pages[incident_href(incident)] = drawn(lambda i=incident: render_incident_page(
            i, store, generated_at=generated_at))
    return pages
