""""What changed?" from one run: the comparison to open first, chosen by a stated rule.

From a run's page the console picks the run to compare it with, trying in order, and names the rule
it used (rules 2 to 4; a rule 1, the pipeline's reference run, waits for references). At each rule a
benchmark (`benchmarks`, a run a person vouched for) comes first:

- the nearest earlier benchmark of the same pipeline with the same recorded inputs;
2. the nearest earlier run of the same pipeline with the same recorded inputs (every input digest of
   the first step equal), the one whose final output differs if several do;
- the nearest earlier benchmark of the same pipeline;
3. the most recent earlier run of the same pipeline whose final output differs;
4. the most recent earlier run of the same pipeline.

Where a benchmark is taken over the run the rules would take without benchmarks, the line says so,
and the list of other comparisons badges each benchmark.

"Same pipeline" is the console's own grouping (the declared stage list); "earlier" is the console's
own order of runs (arrival). The rule is deterministic and stated: no score, no "best match". A
comparison is made only when a person asks on a local console; a public console offers only the
pairs it holds. The choice never changes a verdict.
"""
from __future__ import annotations

from onetrace_console.words import escape

BUTTON = "What changed?"
#: The two benchmark rules, by name: each comes before the rule it narrows.
BENCHMARK_INPUTS, BENCHMARK_EARLIER = "benchmark-inputs", "benchmark-earlier"
RULES = {BENCHMARK_INPUTS: "the nearest earlier benchmark with the same inputs",
         2: "the nearest earlier run with the same inputs",
         BENCHMARK_EARLIER: "the nearest earlier benchmark of this pipeline",
         3: "the most recent earlier run whose final output differs",
         4: "the most recent earlier run of this pipeline"}
#: "What changed?"'s line opening the index on the runs whose first-step inputs are this run's.
SAME_INPUTS = "Other runs with the same inputs: {n}"
NO_EARLIER = "No earlier run of this pipeline, so there is nothing to compare it with."
NOT_COMPARED = "not compared"
#: On a public console, which compares nothing: the rule walks its candidates in order and takes the
#: first whose comparison is held, and says so.
HELD_ONLY = "that this demo compared"
PUBLIC_ONLY = "This demo compares nothing; it offers the comparisons it holds."


def _receipts(run, store) -> list[dict]:
    """The run's receipts in order, read once per reading of the store (`Store.reading`)."""
    from onetrace_console.render import _receipts_in_order
    read = store._read()
    if read is None:
        return _receipts_in_order(run.key, store)
    held = read.setdefault("receipts", {})
    if run.key not in held:
        held[run.key] = _receipts_in_order(run.key, store)
    return held[run.key]


def first_inputs(receipts: list[dict]) -> tuple:
    """The first step's own recorded inputs, by name and digest (not another step's receipt)."""
    if not receipts:
        return ()
    ins = receipts[0].get("inputs") or []
    return tuple(sorted((str(i.get("name")), str(i.get("digest"))) for i in ins
                        if isinstance(i, dict) and not str(i.get("name", "")).startswith("receipt:")))


def final_output(receipts: list[dict]) -> tuple:
    """The last step's recorded output digests, in order."""
    if not receipts:
        return ()
    return tuple(str(o.get("digest")) for o in receipts[-1].get("outputs") or [] if isinstance(o, dict))


def candidates(run, store, *, with_benchmarks: bool = True) -> list:
    """[(an earlier run, the rule)], in the order the rules take them: the benchmarks with the same
    inputs, rule 2's (those whose final output differs first, nearest first), the other earlier
    benchmarks, then rule 3's, then rule 4's; each run once."""
    from onetrace_console.overview import declared_list
    from onetrace_console.store import arrival_order
    ordered = [r for r in arrival_order(store.runs(), newest_first=False) if declared_list(r) == declared_list(run)]
    keys = [r.key for r in ordered]
    if run.key not in keys:
        return None
    earlier = ordered[:keys.index(run.key)][::-1]          # nearest first
    if not earlier:
        return []
    mine = _receipts(run, store)
    my_in, my_out = first_inputs(mine), final_output(mine)
    facts = [(r, _receipts(r, store)) for r in earlier]
    same_in = [(r, rs) for r, rs in facts if my_in and first_inputs(rs) == my_in]
    from onetrace_console.benchmarks import marks
    marked = marks(store) if with_benchmarks else {}
    out = [(r, BENCHMARK_INPUTS) for r, _rs in same_in if r.key in marked]
    out += [(r, 2) for r, rs in same_in if final_output(rs) != my_out]
    out += [(r, 2) for r, rs in same_in if final_output(rs) == my_out]
    out += [(r, BENCHMARK_EARLIER) for r in earlier if r.key in marked]
    out += [(r, 3) for r, rs in facts if final_output(rs) != my_out]
    out += [(r, 4) for r in earlier]
    seen, once = set(), []
    for r, rule in out:
        if r.key not in seen:
            seen.add(r.key)
            once.append((r, rule))
    return once


def _public(public) -> bool:
    if public is not None:
        return public
    from onetrace_console.frame import rendering_public
    return rendering_public()


def choose(run, store, *, public: bool | None = None):
    """(the earlier run, the rule's number, whether the pick is held only) by rules 2 to 4; None with
    no earlier run. A local console takes the first candidate (a missing comparison can be made); a
    public one the first whose comparison is held, and the first candidate where none is."""
    found = candidates(run, store)
    if not found:
        return None
    if _public(public):
        for other, rule in found:
            if held(store, other.key, run.key) is not None:
                return other, rule, True
    return found[0][0], found[0][1], False


def rule_words(rule, held_only: bool) -> str:
    return f"{RULES[rule]} {HELD_ONLY}" if held_only else RULES[rule]


def without_benchmarks(run, store, *, public: bool | None = None):
    """The run the rules take with no benchmark considered, or None: what a benchmark was taken over."""
    found = candidates(run, store, with_benchmarks=False) or []
    if _public(public):
        found = [(r, rule) for r, rule in found if held(store, r.key, run.key) is not None] or found
    return found[0][0] if found else None


def run_ref(store, run) -> str:
    """How the index's query names a run: its run id where no other run has it, its key otherwise."""
    return run.run_id if run.run_id and len(store.runs_with_id(run.run_id)) == 1 else run.key


def same_inputs_line(run, store, *, up: str) -> str:
    """"Other runs with the same inputs: N", opening the index with `inputs:same-as:` filled; "" for a
    run whose first step records no input of its own."""
    from urllib.parse import quote
    mine = first_inputs(_receipts(run, store))
    if not mine:
        return ""
    n = sum(1 for r in store.runs() if r.key != run.key and first_inputs(_receipts(r, store)) == mine)
    q = quote(f"inputs:same-as:{run_ref(store, run)}", safe=":")
    return (f'<p data-what-changed="same-inputs"><a href="{up}search?q={q}&amp;run={escape(run.key)}">'
            f"{escape(SAME_INPUTS.format(n=n))}</a></p>")


def held(store, a_key: str, b_key: str):
    return next((c for c in store.comparisons() if (c.run_a, c.run_b) == (a_key, b_key)), None)


def section(run, store, *, public: bool, up: str = "../../") -> str:
    """The run page's "What changed?": the comparison the rule picks, opened at its top (its short
    answer), the rule named, and the other comparisons of this run to pick instead."""
    from onetrace_console.words import run_named
    got = choose(run, store, public=public)
    head = f'<section data-section="what-changed" class="what-changed"><h2>{escape(BUTTON)}</h2>'
    if got is None:
        return (head + f'<p data-what-changed="none">{escape(NO_EARLIER)}</p>'
                f'{same_inputs_line(run, store, up=up)}</section>')
    other, rule, held_only = got
    words = f"Compared with {other.run_id}, {rule_words(rule, held_only)}."
    if rule in (BENCHMARK_INPUTS, BENCHMARK_EARLIER):
        over = without_benchmarks(run, store, public=public)
        if over is not None and over.key != other.key:
            words += f" A benchmark, taken over {over.run_id}, which the rules take without benchmarks."
    c = held(store, other.key, run.key)
    if c is not None:
        act = f'<a href="{up}diff/{escape(c.key)}.html" data-what-changed="open">{escape(BUTTON)}</a>'
    elif public:
        act = f'<span data-what-changed="not-held">{escape(NOT_COMPARED)}.</span> {escape(PUBLIC_ONLY)}'
    else:
        from onetrace_console.compare_script import COMPARE_SCRIPT
        act = (f'<button type="button" hidden data-compare-post="/compare?a={escape(other.key)}&amp;b={escape(run.key)}">'
               f'{escape(BUTTON)}</button><span data-compare-said></span>{COMPARE_SCRIPT}')
    others = [x for x in store.comparisons() if x.run_b == run.key and x.run_a != other.key]
    from onetrace_console.benchmarks import badge
    pick = ("".join(f'<li><a href="{up}diff/{escape(x.key)}.html">against {run_named(store, x.run_a)}</a>'
                    f"{badge(store, x.run_a)}</li>" for x in others))
    listing = (f'<details data-what-changed="others"><summary>Pick another comparison ({len(others)})</summary>'
               f'<ul class="plain">{pick}</ul></details>' if others else "")
    mark = " data-held-only" if held_only else ""
    from onetrace_console.benchmarks import badge
    return (head + f'<p data-what-changed="rule" data-rule="{rule}"{mark}>{escape(words)}{badge(store, other.key)}</p>'
            f'<p>{act}</p>{listing}{same_inputs_line(run, store, up=up)}</section>')


def runs_line(run, store, *, public: bool | None = None) -> str:
    """The Runs page's one line: the short answer's headline against the run the rule chooses, where
    that comparison is held; "not compared" otherwise."""
    got = choose(run, store, public=public)
    if got is None:
        return NOT_COMPARED
    c = held(store, got[0].key, run.key)
    if c is None:
        return NOT_COMPARED
    from onetrace_console.render import short_headline
    return short_headline(c, store) or NOT_COMPARED


def chosen_line(comparison, store) -> str:
    """On a comparison page, where the rule picks this baseline for this candidate: which rule."""
    run_b = store.get_run(comparison.run_b)
    got = choose(run_b, store) if run_b is not None else None
    if got is None or got[0].key != comparison.run_a:
        return ""
    return (f'<p data-section="chosen" data-rule="{got[1]}">{escape(BUTTON)} chose this comparison: '
            f'compared with <code>{escape(got[0].run_id)}</code>, {escape(rule_words(got[1], got[2]))}.</p>')
