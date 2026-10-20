"""Compare shows the SDK's own sentence when the first difference has no recorded cause.

When nothing recorded about the first difference's stage differs, the SDK's localize report says so
in one sentence (`no_recorded_cause`, in its `cause`, or in a `frontier_causes` entry on a graph):
the stage, whether its instrument declares itself not rederivable, and the next recorded change
downstream of it (instrument and constants only) or that nothing recorded changes after it. The
comparison shows that sentence as the SDK wrote it, escaped as any record words, and computes none
of its own; where the SDK's report has none, it shows none. On a straight-line pair the step that
sentence names also gets a "First recorded change" chip on the graph and its rows first in
"Settings that changed", by the SDK's rule. A stage with a recorded change of its own (a setting, or
an own input the console names) gets no sentence, nor that why its output differs is not
established. The card uses no causal word.

States, each with its sabotage: a later change (the demo's own pair, and a pair made here), none
after it, a stage that does not declare itself not rederivable, the stage's own change, a
graph-shaped pair with a later change and with none, and the two pairs where the SDK's rule names
no later step though a later change is recorded: on another branch of a graph, and a later step's
own input. A localize report without the field shows no sentence.
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from tests.test_compare_page import _page, demo  # noqa: F401
from tests.test_times_and_words import _console

DEMO_PAIR = ("p4-29-reply-30-days", "p4-30-reply-14-days")
#: The SDK's sentence, as its localize report writes it (onetrace.localize.no_recorded_cause).
HEAD = "no recorded cause: nothing recorded differs at {first!r} (same instrument, version and settings)"
VARIES = ", and its instrument declares itself not rederivable, so its output can vary on its own"
LATER = "; the next recorded change is at {later!r}: {what}"
NONE = "; nothing recorded changes after it"
#: The console's own sentence, which it no longer says.
OWN_WORDS = ("No recorded cause at", "nothing recorded about it differs", "Nothing recorded changes after it.",
             "The next recorded change is at")


def sentence(first: str, later: str = "", what: str = "", varies: bool = True) -> str:
    return (HEAD.format(first=first) + (VARIES if varies else "")
            + (LATER.format(later=later, what=what) if later else NONE))


def sdk_sentences(store, comparison) -> list[str]:
    """Every `no_recorded_cause` the comparison's stored localize report carries, as written."""
    import json
    run = comparison.verb("localize")
    report = json.loads(store.get(dict(run.reports)["localize.json"]))
    causes = [report.get("cause") or {}] + list(report.get("frontier_causes") or [])
    return [c["no_recorded_cause"] for c in causes if c.get("no_recorded_cause")]


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _pair(root: Path, *, rederivable: str = "false", own_change: bool = False,
          later_change: bool = True, graph: bool = False, side_change: bool = False,
          check_input: bool = False, stub_input: bool = False) -> Path:
    """Two runs: `stub` varies its output per run; `check` records `days`, changed between the
    runs where `later_change`; `stub` also records a changed `temperature` where `own_change`.
    Where `graph`, a `side` stage also reads `ask`, and `check` reads both `stub` and `side`, so the
    runs are graph-shaped; `side` records a `mode` that differs where `side_change` (a change on
    another branch). `check` reads a policy file whose text differs where `check_input`, and
    `stub` reads a style file whose text differs where `stub_input` (an own input, not a setting)."""
    from onetrace.emit import Instrument, Recorder
    runs = root / "runs"
    stages = ["ask", "stub", "side", "check", "send"] if graph else ["ask", "stub", "check", "send"]
    for name, days, temp in (("a", "30", "0.7"), ("b", "14" if later_change else "30",
                                                   "0.9" if own_change else "0.7")):
        out = runs / name
        out.mkdir(parents=True)
        (out / "q.json").write_text('{"q": "Can I return it?"}', encoding="utf-8")
        edges = ({"declared_edges": [{"from": x, "to": y} for x, y in (
            ("ask", "stub"), ("ask", "side"), ("stub", "check"), ("side", "check"), ("check", "send"))]}
                 if graph else {})
        rec = Recorder(str(out), run_id=f"v-{name}", declared_stages=stages,
                       manifest=Path(__file__), policy="fail-closed", anchor_reason="a test record", **edges)

        def ask(ctx, out=out):
            ctx.read_external(out / "q.json", "application/json", name="question",
                              trust_class="operator-authored")
            return ctx.write("q.txt", b"Can I return it?", "text/plain")

        def stub(ctx, asked, name=name, temp=temp, out=out):
            ctx.read_receipt("ask")
            ctx.read(asked)
            if stub_input:
                (out / "style.txt").write_text(f"style {name}", encoding="utf-8")
                ctx.read_external(out / "style.txt", "text/plain", name="style",
                                  trust_class="operator-authored")
            ctx.constant("temperature", temp)
            return ctx.write("draft.txt", f"Reply {name}: within {{days}} days.".encode(), "text/plain")

        def side(ctx, asked, name=name):
            ctx.read_receipt("ask")
            if side_change:
                ctx.constant("mode", name)
            return ctx.write("side.txt", ctx.read(asked), "text/plain")

        def check(ctx, drafted, *more, days=days, out=out, name=name):
            ctx.read_receipt("stub")
            if check_input:
                (out / "policy.txt").write_text(f"policy {name}", encoding="utf-8")
                ctx.read_external(out / "policy.txt", "text/plain", name="policy",
                                  trust_class="operator-authored")
            if more:
                ctx.read_receipt("side")
                ctx.read(more[0])
            text = ctx.read(drafted).decode()
            ctx.constant("days", days)
            return ctx.write("checked.txt", text.replace("{days}", days).encode(), "text/plain")

        def send(ctx, checked):
            ctx.read_receipt("check")
            return ctx.write("sent.txt", ctx.read(checked), "text/plain")

        asked = rec.run_node("ask", None, Instrument("asker", "reader", "1.0.0", {"k": "v"}), ask)
        drafted = rec.run_node("stub", None, Instrument("reply-stub", "model-stub", "1.0.0", {"k": "v"},
                                                        rederivable=rederivable,
                                                        rederivable_note="a stub that varies per run"
                                                        if rederivable == "false" else None),
                               stub, asked)
        more = ([rec.run_node("side", None, Instrument("copier", "tool", "1.0.0", {"k": "v"}), side, asked)]
                if graph else [])
        checked = rec.run_node("check", None, Instrument("checker", "tool", "1.0.0", {"k": "v"}),
                               check, drafted, *more)
        rec.run_node("send", None, Instrument("outbox", "writer", "1.0.0", {"k": "v"}), send, checked)
        rec.close()
    return runs


def _card(page: str) -> str:
    """Every first-difference section's words: the straight-line card, or a graph's."""
    return " ".join(_text(m) for m in re.findall(r'<section data-section="first-difference"[^>]*>.*?</section>',
                                                  page, re.S))


def variance_problems(page: str, state: str, first: str = "", later: str = "", what: str = "",
                      varies: bool = True, graph: bool = False) -> list[str]:
    """`state`: "later" (a later stage named), "none" (nothing after it) or "absent" (the stage has
    a recorded change of its own: no sentence, and no "not established")."""
    out = []
    card = _card(page)
    for word in ("caused", "because", "follow from"):
        if word in card.lower():
            out.append(f"a causal word: {word}")
    for words in OWN_WORDS:
        if words in card:
            out.append(f"the console's own sentence: {words}")
    if state in ("later", "none"):
        if sentence(first, later, what, varies) not in card:
            out.append(f"the sentence: {card[:400]}")
        if "not established" in card:
            out.append("'not established' beside the sentence")
    chips = re.findall(r'data-mark="recorded-change"', page)
    if state == "later" and not graph:
        graph_svg = re.search(r'<svg class="graph".*?</svg>', page, re.S)
        marked = re.findall(r'<a href="[^"]*"[^>]*data-mark="recorded-change"[^>]*><rect[^>]*/><title>([^<]*)</title>',
                            graph_svg.group(0) if graph_svg else "")
        if len(marked) != 1 or not marked[0].startswith(f"{later} · ") or "First recorded change" not in marked[0]:
            out.append(f"the chip on {later}: {marked}")
        elif "Changed after it" not in marked[0]:
            out.append("the chip's stage lost its own verdict")
        section = re.search(r'<section data-section="settings-changed">.*?</section>', page, re.S).group(0)
        row = re.search(r'<tr data-setting="[^"]*"><td[^>]*>(.*?)</td>', section, re.S)
        if row is None or _text(row.group(1)) != later:
            out.append(f"Settings that changed opens with {_text(row.group(1)) if row else None}, not {later}")
    if state in ("none", "absent") and chips:
        out.append(f"a chip where the sentence names no later step: {len(chips)}")
    if state == "absent":
        if "no recorded cause" in card.lower() or "nothing recorded changes" in card.lower():
            out.append("the sentence where the stage has a recorded change")
        if "not established" in card:
            out.append("'not established' where the stage has a recorded change")
    return out


def _diff(tmp_path, **kw) -> str:
    return _diff_and_sdk(tmp_path, **kw)[0]


def _diff_and_sdk(tmp_path, **kw) -> tuple[str, list[str]]:
    """The comparison page, and the sentences its stored localize report carries."""
    runs = _pair(tmp_path, **kw)
    store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    page = (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")
    return page, sdk_sentences(store, loaded.comparison)


# ------------------------------------------------------------------ the states

DAYS = "assertions.constants.days"


def test_the_demo_pair_names_the_policy_stage(demo, examined):  # noqa: F811
    page = _page(demo, *DEMO_PAIR)
    examined(1, "the demo's pair")
    assert variance_problems(page, "later", "draft", "policy_check",
                             "assertions.constants.refund_days") == []


def test_a_later_recorded_change_is_named(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path)
    examined(1, "comparison page")
    assert sdk == [sentence("stub", "check", DAYS)], "the SDK's own sentence, stored"
    assert variance_problems(page, "later", "stub", "check", DAYS) == []


def test_nothing_recorded_after_it_is_said(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path, later_change=False)
    examined(1, "comparison page")
    assert sdk == [sentence("stub")]
    assert variance_problems(page, "none", "stub") == []


def test_a_stage_not_declared_not_rederivable_keeps_the_rest(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path, rederivable="true")
    examined(1, "comparison page")
    assert sdk == [sentence("stub", "check", DAYS, varies=False)]
    assert variance_problems(page, "later", "stub", "check", DAYS, varies=False) == []


def test_the_stages_own_change_leaves_out_the_sentence(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path, own_change=True)
    examined(1, "comparison page")
    assert sdk == [], "the SDK says none either"
    assert variance_problems(page, "absent") == []
    assert "temperature: 0.7 → 0.9" in _text(page), "its own change, in the headline as before"


def test_a_graph_comparison_shows_the_sdk_s_sentence_for_its_frontier_node(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path, graph=True)
    examined(1, "comparison page")
    assert 'data-shape="dag"' in page, "a graph comparison"
    assert sdk == [sentence("stub", "check", DAYS)], "from the report's frontier_causes"
    assert variance_problems(page, "later", "stub", "check", DAYS, graph=True) == []


def test_a_graph_comparison_with_nothing_after_it(tmp_path, examined):
    page, sdk = _diff_and_sdk(tmp_path, graph=True, later_change=False)
    examined(1, "comparison page")
    assert sdk == [sentence("stub")]
    assert variance_problems(page, "none", "stub", graph=True) == []


def test_a_change_on_another_branch_of_a_graph_is_not_named_after_it(tmp_path, examined):
    """`side` records a setting that differs, on a branch `stub` does not lead to: the SDK names
    only a step downstream of the first difference, so nothing recorded changes after it."""
    page, sdk = _diff_and_sdk(tmp_path, graph=True, later_change=False, side_change=True)
    examined(1, "comparison page")
    assert sdk == [sentence("stub")]
    assert variance_problems(page, "none", "stub", graph=True) == []
    assert "'side'" not in _card(page) and "side:" not in _card(page)


def test_a_later_step_s_own_input_is_not_a_recorded_change_after_it(tmp_path, examined):
    """`check` reads a policy file whose text differs, and records no setting that differs: the
    SDK counts recorded settings only, so nothing recorded changes after it, and no chip."""
    page, sdk = _diff_and_sdk(tmp_path, later_change=False, check_input=True)
    examined(1, "comparison page")
    assert sdk == [sentence("stub")]
    assert variance_problems(page, "none", "stub") == []


def test_the_first_stage_s_own_input_is_named_and_no_sentence_follows(tmp_path, examined):
    """Where the first difference's stage reads an input of its own that differs, the card names
    it and says nothing more, as before, though the SDK's report carries its sentence (it counts
    recorded settings only)."""
    page, sdk = _diff_and_sdk(tmp_path, stub_input=True)
    examined(1, "comparison page")
    assert sdk == [sentence("stub", "check", DAYS)], "the SDK still writes its sentence here"
    assert "input style changed" in _card(page)
    assert variance_problems(page, "absent") == []


def _with_stored_cause(tmp_path, change, **kw) -> str:
    """The pair's comparison page, drawn over its stored localize report as `change` leaves it."""
    import json
    from dataclasses import replace

    from onetrace_console.render import render_diff
    store, _pages, loaded = _console(tmp_path, _pair(tmp_path, **kw), compare=("a", "b"))
    comparison = loaded.comparison
    run = comparison.verb("localize")
    report = json.loads(store.get(dict(run.reports)["localize.json"]))
    change(report)
    key = store.put(json.dumps(report).encode("utf-8"))
    changed = replace(run, reports=tuple((n, key if n == "localize.json" else k) for n, k in run.reports))
    return render_diff(replace(comparison, verbs=tuple(changed if v.verb == "localize" else v
                                                       for v in comparison.verbs)),
                       store, generated_at="2026-01-01T00:00:00+00:00")


def test_a_localize_report_without_the_sentence_shows_none(tmp_path, examined):
    """The same pair, its stored localize report without `no_recorded_cause` (as an SDK before it
    wrote): no sentence, no chip, and the card says why the output differs is not established."""
    pages = {"straight line": _with_stored_cause(tmp_path / "l", lambda r: r["cause"].pop("no_recorded_cause")),
             "graph": _with_stored_cause(tmp_path / "g", lambda r: r["frontier_causes"][0].pop("no_recorded_cause"),
                                         graph=True)}
    examined(len(pages), "comparison pages")
    for name, page in pages.items():
        card = _card(page)
        assert "no recorded cause" not in card.lower() and "nothing recorded" not in card.lower(), (name, card)
        assert "stub's output differs is not established by this evidence." in card, (name, card)
        assert 'data-mark="recorded-change"' not in page, name


def test_the_sdk_s_sentence_is_escaped_as_record_words(tmp_path, examined):
    """Its stage names are the record's: a sentence holding markup is shown as text, never drawn."""
    planted = "no recorded cause: nothing recorded differs at '<b>stub</b>'; nothing recorded changes after it"

    def plant(report):
        report["cause"]["no_recorded_cause"] = planted
    page = _with_stored_cause(tmp_path, plant)
    section = re.search(r'<section data-section="first-difference".*?</section>', page, re.S).group(0)
    examined(1, "comparison page")
    assert "<b>stub</b>" not in section
    assert "&lt;b&gt;stub&lt;/b&gt;" in section
    assert planted in _card(page)


def test_the_console_composes_no_sentence_of_its_own(examined):
    """One sentence, one source: the console's own composition is gone."""
    import onetrace_console.render as render
    gone = ("no_cause_sentence", "variance_sentence", "NO_CAUSE", "NO_CAUSE_LATER", "NO_CAUSE_NONE")
    examined(len(gone), "names")
    assert [n for n in gone if hasattr(render, n)] == []


# ------------------------------------------------------------------ sabotages

def test_sabotage_each_state_s_wrong_page_is_named(tmp_path, examined):
    later = _diff(tmp_path / "l")
    none = _diff(tmp_path / "n", later_change=False)
    absent = _diff(tmp_path / "x", own_change=True)
    planted = {
        "no sentence": (later.replace("the next recorded change is at", "the next change is at", 1),
                        "later", ("stub", "check", DAYS)),
        "no chip": (later.replace('data-mark="recorded-change"', "", 1), "later", ("stub", "check", DAYS)),
        "a cause": (later.replace("nothing recorded differs at", "nothing recorded differs (which follow from) at", 1),
                    "later", ("stub", "check", DAYS)),
        "the console's own words": (later.replace("no recorded cause: nothing recorded differs at",
                                                  "No recorded cause at stub: nothing recorded about it differs. "
                                                  "no recorded cause: nothing recorded differs at", 1),
                                    "later", ("stub", "check", DAYS)),
        "the none sentence missing": (none.replace("; nothing recorded changes after it", "", 1), "none", ("stub",)),
        "not established beside it": (none.replace("; nothing recorded changes after it",
                                                   "; nothing recorded changes after it. Why it is not established.", 1),
                                      "none", ("stub",)),
        "a chip where none is named": (none.replace('#step-3" data-tone=', '#step-3" data-mark="recorded-change" data-tone=', 1),
                                       "none", ("stub",)),
        "said where it shouldn't be": (absent.replace('<div data-part="what">',
                                                      '<div data-part="what"><p>nothing recorded changes after it</p>', 1),
                                       "absent", ()),
        "not established with a change": (absent.replace('<div data-part="what">',
                                                         '<div data-part="what"><p>not established</p>', 1),
                                          "absent", ()),
    }
    examined(len(planted), "planted pages")
    for name, (bad, state, args) in planted.items():
        assert variance_problems(bad, state, *args), name


def test_the_chip_s_outline_is_amber_and_wins_over_the_box_s_tone(examined):
    """The same outline as "First difference", amber (a comparison's marker, not a check's result),
    and more specific than the tone rule that would otherwise draw the box's own stroke."""
    from onetrace_console.frame import stylesheet
    css = stylesheet().decode("utf-8")
    examined(1, "stylesheet")
    rule = ".cp svg.graph [data-mark=recorded-change][data-tone] .node{stroke:var(--cc-ink);stroke-width:2}"
    assert rule in css
    assert css.index(rule) > css.index(".cp svg.graph [data-tone=neu] .node{")
