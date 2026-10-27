"""A comparison page's short answer: one headline, one line under it, and a strip of its stages,
from the comparison's own report and the two runs' receipts, with no model.

Where the runs first differ, and what differs there: a setting by its recorded name and values, an
input by its name, a configuration whose fingerprint alone differs, or only the output. Which
stages come before and after it, in counts. The same report gives the same words every time; the
explanation below, where there is one, is a model's and never feeds these.

The headline names the first-difference stage by what differs at that stage only. A setting the
record says changed at a later stage is said on the second line as a plain fact, with no link drawn
between the two. A setting is named only where the record names it: a fingerprint is "its
configuration". Runs whose recorded outputs are all the same "agree" only where nothing recorded
differs; otherwise the setting, the configuration or the input that differs is named.

On a graph-shaped pair, the first difference is the one the report names. Where it names none, the
differences begin at each stage that differs while every stage it reads from (the runs' recorded
edges) is the same. The strip follows the graph view's order, and the line under the headline gives
counts only: on a graph, "before" has no single meaning.
"""
from __future__ import annotations

from dataclasses import dataclass

from onetrace_console import tones
from onetrace_console.words import escape, shown_name

#: The short answer's look, in the console's stylesheet (`frame.stylesheet`): a panel at the top of
#: the page, its strip a row of marks that wraps, each mark its stage's name over its result in
#: words, so colour is never the only signal; the stages where differences begin carry a heavier
#: border and a heavier word.
SHORT_CSS = """
.cp .short-answer{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);
  padding:14px 16px;margin:0 0 18px}
.cp .short-answer .kicker{margin:0 0 4px;font-size:var(--fs-small);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-muted)}
.cp .short-answer .headline{margin:0 0 6px;font-size:15px;line-height:1.4;color:var(--ink);font-weight:500}
.cp .short-answer [data-short=second]{margin:0 0 10px;color:var(--ink-soft)}
.cp .short-answer .strip{display:flex;flex-wrap:wrap;gap:6px;list-style:none;margin:0 0 10px;padding:0}
.cp .short-answer .strip>li{display:flex;flex-direction:column;gap:2px;min-width:0;max-width:100%;
  padding:6px 10px;border-radius:var(--r-ctl);border:1px solid transparent;overflow-wrap:anywhere}
.cp .short-answer .strip>li .name{font-family:var(--font-mono);font-size:var(--fs-small)}
.cp .short-answer .strip>li .word{font-size:var(--fs-small)}
.cp .short-answer .strip>li[data-mark=first]{border:2px solid var(--ink);outline:none}
.cp .short-answer .strip>li[data-mark=first] .word{font-weight:600}
.cp .short-answer .checked{margin:0;font-size:var(--fs-small);color:var(--ink-muted)}
.cp .short-answer code{font-family:var(--font-mono)}
"""
KICKER = "The short answer"
CHECKED = "Checked from the records. The same answer every time."
#: The ladder's verdicts in the console's own words (`render._RESULT_WORDS`), for the strip.
DIFFERS = frozenset({"FIRST DIFFERENCE", "downstream"})
#: How the stages after the first difference came out, counted.
_AFTER = (("downstream", "differs", "differ"),
          ("reconverged", "is the same again", "are the same again"),
          ("COULD NOT CHECK", "could not be checked", "could not be checked"))


@dataclass(frozen=True)
class Code:
    """A name from the record, set as code: a stage, a setting, an input or a value."""
    text: str


def _html(parts) -> str:
    return "".join(f"<code>{escape(p.text)}</code>" if isinstance(p, Code) else escape(p) for p in parts)


def text(parts) -> str:
    """The words as plain text, each name from the record between backticks."""
    return "".join(f"`{p.text}`" if isinstance(p, Code) else p for p in parts)


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _and(items: list) -> list:
    """`a`, `a and b`, `a, b and c`, kept as parts."""
    out: list = []
    for i, item in enumerate(items):
        if i:
            out.append(" and " if i == len(items) - 1 else ", ")
        out.append(item)
    return out


def _split(differs: dict) -> tuple[list[tuple[str, str, str]], bool]:
    """(each setting named with its values, whether a fingerprint differs) from an annotation's
    `differs`: a digest-valued field is a fingerprint, said as the configuration."""
    from onetrace_console.render import _is_digest, short_setting
    named = [(short_setting(f), old, new) for f, (old, new) in differs.items()
             if not (_is_digest(old) or _is_digest(new))]
    prints = any(_is_digest(old) or _is_digest(new) for old, new in differs.values())
    return named, prints


def _where(differs: dict, inputs: list[str]) -> list:
    """What differs at the first-difference stage, as the headline's "where ..." clause."""
    named, prints = _split(differs)
    said: list = []
    if len(named) == 1:
        name, old, new = named[0]
        said.append(["", Code(name), f" went from {old} to {new}"])
    elif named:
        said.append([f"{len(named)} settings changed"])
    if len(inputs) == 1:
        said.append(["input ", Code(inputs[0]), " changed"])
    elif inputs:
        said.append([f"{len(inputs)} inputs changed"])
    if not said:
        return [", where its configuration changed."] if prints else [", where its output changed."]
    out: list = [", where "]
    for i, piece in enumerate(said):
        if i:
            out.append(" and ")
        out.extend(piece)
    return out + ["."]


def _settings_said(found: list[tuple[str, str, str, str]]) -> list:
    """`name` at `stage`, `a` → `b`; each from the record, joined by semicolons."""
    out: list = []
    for i, (name, stage, old, new) in enumerate(found):
        if i:
            out.append("; ")
        out += [Code(name), " at ", Code(stage), ", ", Code(old), " → ", Code(new)]
    return out


def _agree(notes: list[dict], inputs: list[tuple[str, str]]) -> list:
    """The headline where every recorded output is the same: "The two runs agree." only where
    nothing recorded differs; otherwise what does, named."""
    found, prints = [], []
    for note in notes:
        named, printed = _split(note["differs"])
        found += [(name, note["stage"], old, new) for name, old, new in named]
        if printed and not named:
            prints.append(note["stage"])
    if not (found or prints or inputs):
        return ["The two runs agree."]
    out: list = ["Every recorded output is the same."]
    if found:
        out += [" A setting differs: " if len(found) == 1 else f" {len(found)} settings differ: "]
        out += _settings_said(found) + ["."]
    for stage in prints:
        out += [" ", Code(stage), "'s configuration differs."]
    for stage, name in inputs:
        out += [" Input ", Code(name), " differs at ", Code(stage), "."]
    return out


@dataclass(frozen=True)
class Answer:
    headline: list
    second: list
    strip: tuple[tuple[str, str, bool], ...]   # (stage, verdict, marked as where differences begin)


def for_line(report, annotations: list[dict], inputs_at, input_notes: dict[str, list[str]]) -> Answer:
    """A straight-line pair. `inputs_at(stage)`: the first-difference stage's own inputs that
    differ, by name; `input_notes`: {stage: its inputs that differ} for stages that read the same."""
    ladder = list(report.ladder)
    first = next((r for r in ladder if r.verdict == "FIRST DIFFERENCE"), None)
    notes = {n["index"]: n for n in annotations}
    strip = tuple((r.stage, r.verdict, r is first) for r in ladder)
    if first is None:
        unchecked = [r for r in ladder if r.verdict == "COULD NOT CHECK"]
        if unchecked:
            return Answer(["No recorded output differs where checked; ",
                           _plural(len(unchecked), "stage", "stages"), " could not be checked."], [], strip)
        ins = [(s, n) for s in (r.stage for r in ladder) for n in input_notes.get(s, [])]
        return Answer(_agree(annotations, ins), [], strip)
    differs = (notes.get(first.index) or {}).get("differs") or {}
    head = ["The runs first differ at ", Code(first.stage)] + _where(differs, inputs_at(first.stage))
    before = [r for r in ladder if int(r.index) < int(first.index)]
    after = [r for r in ladder if int(r.index) > int(first.index)]
    second: list = []
    if not before:
        second.append("No stage comes before it.")
    elif all(r.verdict == "same" for r in before):
        second.append("Every stage before it is the same.")
    else:
        same = sum(r.verdict == "same" for r in before)
        second.append(f"{same} of the {_plural(len(before), 'stage', 'stages')} before it "
                      f"{'is' if same == 1 else 'are'} the same.")
    if not after:
        second.append(" No stage comes after it.")
    else:
        counts = [(n, one, many) for v, one, many in _AFTER
                  if (n := sum(r.verdict == v for r in after))]
        if len(counts) == 1 and counts[0][0] == len(after):
            n, one, many = counts[0]
            second.append(f" The stage after it {one}." if n == 1 else f" Both stages after it {many}." if n == 2
                          else f" All {n} stages after it {many}.")
        else:
            said = "; ".join(f"{n} {one if n == 1 else many}" for n, one, many in counts)
            second.append(f" Of the {_plural(len(after), 'stage', 'stages')} after it, {said}.")
    later = []
    for r in after:
        named, _ = _split((notes.get(r.index) or {}).get("differs") or {})
        later += [(name, r.stage, old, new) for name, old, new in named]
    if later:
        second += [" A recorded setting also changed later: " if len(later) == 1
                   else " Recorded settings also changed later: "] + _settings_said(later) + ["."]
    return Answer(head, second, strip)


def begins(ladder, edges) -> list[str]:
    """Where differences begin on a graph: each node that differs while every node it reads from
    is the same. A node with no recorded edge into it reads from nothing."""
    verdict = {r.node: r.verdict for r in ladder}
    reads: dict[str, list[str]] = {}
    for e in edges or ():
        reads.setdefault(e["to"], []).append(e["from"])
    return [r.node for r in ladder if r.verdict in DIFFERS
            and all(verdict.get(u) == "same" for u in reads.get(r.node, []))]


def for_graph(report, annotations: list[dict], edges, inputs_at, input_notes: dict[str, list[str]]) -> Answer:
    """A graph-shaped pair. `annotations` as `render.dag_annotations` gives them (`index` the row's
    place, from 1)."""
    ladder = list(report.ladder)
    named = [r.node for r in ladder if r.verdict == "FIRST DIFFERENCE"]
    starts = named or begins(ladder, edges)
    strip = tuple((r.node, r.verdict, r.node in starts) for r in ladder)
    if not any(r.verdict in DIFFERS for r in ladder):
        unchecked = [r for r in ladder if r.verdict == "COULD NOT CHECK"]
        if unchecked:
            return Answer(["No recorded output differs where checked; ",
                           _plural(len(unchecked), "stage", "stages"), " could not be checked."], [], strip)
        ins = [(r.node, n) for r in ladder for n in input_notes.get(r.node.split("#", 1)[0], [])]
        return Answer(_agree(annotations, ins), [], strip)
    if len(starts) == 1:
        place = str(next(n for n, r in enumerate(ladder, start=1) if r.node == starts[0]))
        differs = next((a["differs"] for a in annotations if a["index"] == place), {})
        head = ["The runs first differ at ", Code(starts[0])] + _where(differs, inputs_at(starts[0].split("#", 1)[0]))
    else:
        head = [f"Differences begin at {len(starts)} stages: "] + _and([Code(s) for s in starts]) + ["."]
    same = sum(r.verdict in ("same", "reconverged") for r in ladder)
    differ = sum(r.verdict in DIFFERS for r in ladder)
    unchecked = sum(r.verdict == "COULD NOT CHECK" for r in ladder)
    second = [f"Same: {same} · differ: {differ}" + (f" · could not check: {unchecked}" if unchecked else "") + "."]
    return Answer(head, second, strip)


def with_descent(answer: Answer, nested_at: str) -> Answer:
    """Where the SDK descended into the first difference (onetrace 0.5's `nested_at`): the headline
    names the deepest differing step in its words ("inside `plan`, at `price_lookup`"; "into run <id>
    at `settle`"); where an inner run's folder was not given, the second line says so, as the CLI
    does. Unchanged with no descent."""
    from onetrace_console.nesting_view import descent
    d = descent(nested_at)
    if d is None:
        return answer
    if "not_given" in d:
        extra = [" "] + [x for rid in d["not_given"] for x in ("Nested run ", Code(rid), ": folder not given. ")]
        return Answer(answer.headline, (answer.second + extra[:-1] + [extra[-1].rstrip()]) if answer.second
                      else extra[1:-1] + [extra[-1].rstrip()], answer.strip)
    from onetrace_console.nesting_view import path_parts
    head = ["The runs first differ "] + path_parts(d["path"]) + ["."]
    return Answer(head, answer.second, answer.strip)


def with_authorization(answer: Answer, found: list[tuple[str, str]]) -> Answer:
    """A gated step whose recorded decision or permit differs, said as a plain fact on the second
    line: "The permit at `approve_payment` also differs." Unchanged where none differs."""
    if not found:
        return answer
    #: "The two runs agree." only where nothing recorded differs (30ai): a decision or a permit is
    #: recorded, so its difference is named and the outputs said to be the same.
    headline = (["Every recorded output is the same."] if answer.headline == ["The two runs agree."]
                else answer.headline)
    answer = Answer(headline, answer.second, answer.strip)
    extra: list = []
    for stage, what in found:
        extra += [" The ", what, " at ", Code(stage), " also differs."]
    second = answer.second + extra if answer.second else [x.lstrip() if i == 0 else x for i, x in enumerate(extra)]
    return Answer(answer.headline, second, answer.strip)


def _count_mark(answer: Answer) -> str:
    """The line under the headline counts stages; its mark says what was counted, the
    comparison's rows by the SDK's own verdicts, adding up to the stages compared."""
    from collections import Counter
    from onetrace_console.info_mark import mark, stages_note
    if not answer.strip or not any(ch.isdigit() for ch in text(answer.second)):
        return ""
    counts = Counter(v for _, v, _ in answer.strip)
    return mark(stages_note(counts, len(answer.strip)))


def render(answer: Answer) -> str:
    """The short answer, drawn: the kicker, the headline, the line under it, the stage strip, and
    the line saying it is checked from the records."""
    from onetrace_console.render import _RESULT_WORDS
    marks = []
    for stage, verdict, first in answer.strip:
        word = _RESULT_WORDS.get(verdict, verdict)
        marks.append(f'<li data-verdict="{escape(verdict)}"' + (' data-mark="first"' if first else "")
                     + f' class="{tones.tone(tones.DIFF, verdict)}"><span class="name">{escape(shown_name(stage))}'
                     f'</span><span class="word">{escape(word)}</span></li>')
    return ('<section data-section="short-answer" class="short-answer">'
            f'<p class="kicker">{escape(KICKER)}</p>'
            f'<p class="headline" data-short="headline">{_html(answer.headline)}</p>'
            + (f'<p data-short="second">{_html(answer.second)}{_count_mark(answer)}</p>' if answer.second else "")
            + f'<ol class="strip" data-short="strip" aria-label="Each stage, in order, with its result">{"".join(marks)}</ol>'
            f'<p class="checked" data-short="checked">{escape(CHECKED)}</p></section>')
