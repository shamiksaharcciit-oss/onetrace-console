"""Compare looks past a stage that varies with nothing recorded changed.

When the first difference is a stage both runs mark not re-runnable (`rederivable="false"`), and
nothing recorded about it changed but its output -- no setting, constant or instrument field the
SDK's comparison names, no own input -- the page also names the first later stage with a recorded
change: one sentence in the headline, a "First recorded change" chip on the graph (amber, its own
verdict kept), and its rows first in "Settings that changed". With no later change it says the
differences after the stage follow from its output. When either condition fails the page is as
before. It never says "caused" or "because".

Four states, each with its sabotage: (a) and (b) with a later change (the demo's own pair, and a
pair made here), (a) and (b) with none, (a) failing (the stage is re-runnable), (b) failing (the
stage's own setting changed).
"""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

from tests.test_compare_page import _page, demo  # noqa: F401
from tests.test_times_and_words import _console

DEMO_PAIR = ("p4-29-reply-30-days", "p4-30-reply-14-days")
LATER = ("{first}'s output differs, but nothing recorded about it changed; it's marked as not "
         "reproducible. The first stage with a recorded change is {later}: {what}.")
NONE = "No later stage has a recorded change. The differences after {first} follow from its output."


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _pair(root: Path, *, rederivable: str = "false", own_change: bool = False,
          later_change: bool = True) -> Path:
    """Two runs: `stub` varies its output per run; `check` records `days`, changed between the
    runs where `later_change`; `stub` also records a changed `temperature` where `own_change`."""
    from onetrace.emit import Instrument, Recorder
    runs = root / "runs"
    for name, days, temp in (("a", "30", "0.7"), ("b", "14" if later_change else "30",
                                                   "0.9" if own_change else "0.7")):
        out = runs / name
        out.mkdir(parents=True)
        (out / "q.json").write_text('{"q": "Can I return it?"}', encoding="utf-8")
        rec = Recorder(str(out), run_id=f"v-{name}", declared_stages=["ask", "stub", "check", "send"],
                       manifest=Path(__file__), policy="fail-closed", anchor_reason="a test record")

        def ask(ctx, out=out):
            ctx.read_external(out / "q.json", "application/json", name="question",
                              trust_class="operator-authored")
            return ctx.write("q.txt", b"Can I return it?", "text/plain")

        def stub(ctx, asked, name=name, temp=temp):
            ctx.read_receipt("ask")
            ctx.read(asked)
            ctx.constant("temperature", temp)
            return ctx.write("draft.txt", f"Reply {name}: within {{days}} days.".encode(), "text/plain")

        def check(ctx, drafted, days=days):
            ctx.read_receipt("stub")
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
        checked = rec.run_node("check", None, Instrument("checker", "tool", "1.0.0", {"k": "v"}),
                               check, drafted)
        rec.run_node("send", None, Instrument("outbox", "writer", "1.0.0", {"k": "v"}), send, checked)
        rec.close()
    return runs


def variance_problems(page: str, state: str, first: str = "", later: str = "", what: str = "") -> list[str]:
    """`state`: "later" (a later stage named), "none" (no later change) or "absent" (as before)."""
    out = []
    card = _text(re.search(r'<section data-section="first-difference">.*?</section>', page, re.S).group(0))
    graph = re.search(r'<svg class="graph".*?</svg>', page, re.S)
    marked = re.findall(r'<a href="[^"]*"[^>]*data-mark="recorded-change"[^>]*><rect[^>]*/><title>([^<]*)</title>',
                        graph.group(0) if graph else "")
    for word in ("caused", "because"):
        if word in card.lower():
            out.append(f"a causal word: {word}")
    if state == "later":
        if LATER.format(first=first, later=later, what=what) not in card:
            out.append("the sentence naming the later stage")
        if len(marked) != 1 or not marked[0].startswith(f"{later} · ") or "First recorded change" not in marked[0]:
            out.append(f"the chip on {later}: {marked}")
        elif "Changed after it" not in marked[0]:
            out.append("the chip's stage lost its own verdict")
        section = re.search(r'<section data-section="settings-changed">.*?</section>', page, re.S).group(0)
        row = re.search(r'<tr data-setting="[^"]*"><td[^>]*>(.*?)</td>', section, re.S)
        if row is None or _text(row.group(1)) != later:
            out.append(f"Settings that changed opens with {_text(row.group(1)) if row else None}, not {later}")
    elif state == "none":
        if NONE.format(first=first) not in card:
            out.append("the no-later-change sentence")
        if marked:
            out.append("a chip with no later change")
    else:
        if "nothing recorded about it changed" in card or "No later stage has" in card or marked:
            out.append("Part V said where its conditions don't hold")
    return out


def _diff(tmp_path, **kw) -> str:
    runs = _pair(tmp_path, **kw)
    _store, pages, loaded = _console(tmp_path, runs, compare=("a", "b"))
    return (pages / "diff" / f"{loaded.comparison.key}.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ the four states

def test_the_demo_pair_names_the_policy_stage(demo, examined):  # noqa: F811
    page = _page(demo, *DEMO_PAIR)
    examined(1, "the demo's pair")
    assert variance_problems(page, "later", "draft", "policy_check", "refund_days differs") == []


def test_a_later_recorded_change_is_named(tmp_path, examined):
    page = _diff(tmp_path)
    examined(1, "comparison page")
    assert variance_problems(page, "later", "stub", "check", "days differs") == []


def test_no_later_change_says_the_differences_follow(tmp_path, examined):
    page = _diff(tmp_path, later_change=False)
    examined(1, "comparison page")
    assert variance_problems(page, "none", "stub") == []


def test_a_re_runnable_stage_leaves_the_page_as_before(tmp_path, examined):
    page = _diff(tmp_path, rederivable="true")
    examined(1, "comparison page")
    assert variance_problems(page, "absent") == []


def test_the_stages_own_change_leaves_the_page_as_before(tmp_path, examined):
    page = _diff(tmp_path, own_change=True)
    examined(1, "comparison page")
    assert variance_problems(page, "absent") == []
    assert "temperature: 0.7 → 0.9" in _text(page), "its own change, in the headline as before"


# ------------------------------------------------------------------ sabotages

def test_sabotage_each_state_s_wrong_page_is_named(tmp_path, examined):
    later = _diff(tmp_path / "l")
    none = _diff(tmp_path / "n", later_change=False)
    absent = _diff(tmp_path / "x", rederivable="true")
    planted = {
        "no sentence": (later.replace("The first stage with a recorded change is", "The first stage is", 1),
                        "later", ("stub", "check", "days differs")),
        "no chip": (later.replace('data-mark="recorded-change"', "", 1), "later", ("stub", "check", "days differs")),
        "a cause": (later.replace("nothing recorded about it changed", "nothing recorded about it changed because", 1),
                    "later", ("stub", "check", "days differs")),
        "the none sentence missing": (none.replace("No later stage has a recorded change.", "", 1), "none", ("stub",)),
        "said where it shouldn't be": (absent.replace("</h1>", "</h1><section data-section=\"first-difference\">"
                                                      "<p>No later stage has a recorded change.</p></section>", 1)
                                       if '<section data-section="first-difference">' not in absent else
                                       absent.replace('<div data-part="what">',
                                                      '<div data-part="what"><p>No later stage has a recorded change.</p>', 1),
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
