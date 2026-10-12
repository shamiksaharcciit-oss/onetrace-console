"""One colour rule for every page (`tones.py`): colour says what kind of answer a state is.

    a check ran and held -> green; ran and failed -> red;
    couldn't be done or wasn't done -> amber; evidence not made -> neutral.

Checked here:
1. every state, in each table, is the kind this file says the rule makes it -- written out below a
   second time, by hand, from the rule's own words, so a table edited away from the rule fails;
2. every rung and badge state the demo's pages show is placed by the rule (none falls through);
3. the stylesheet draws each rung and badge state in its kind's tone, and the Overview's pills
   carry their state's tone;
4. sabotage: "Not anchored" drawn red is named.
"""
from __future__ import annotations

import re

import pytest

from onetrace_console import tones

#: The rule, applied by hand to each state the console can show.
BY_THE_RULE = {
    "RUNG": {"yes": "held", "no": "failed",
             "couldnt-check": "not-done", "does-not-verify": "not-done", "not-checked": "not-done",
             "signed-untrusted": "not-done",
             "unsigned": "not-made", "not-anchored": "not-made", "not-declared": "not-made",
             "not-a-graph-run": "not-made", "no-records": "not-made", "not-yet-available": "not-made"},
    "ATTENTION": {"contradicts": "failed", "missing-stage": "failed", "couldnt-check": "not-done",
                  "not-checked": "not-done", "last-attempt-failed": "not-done", "changed": "not-made"},
    "BASELINE": {"same": "held", "changed": "not-made", "couldnt-check": "not-done",
                 "not-compared": "not-made"},
    "VERDICT": {"holds": "held", "contradicts": "failed", "could_not_check": "not-done",
                "not checked": "not-done"},
}


@pytest.mark.parametrize("table", sorted(BY_THE_RULE))
def test_every_state_is_the_kind_the_rule_makes_it(table, examined):
    examined(len(BY_THE_RULE[table]), f"{table} states")
    assert getattr(tones, table) == BY_THE_RULE[table]
    assert tones.TONE == {"held": "ok", "failed": "bad", "not-done": "cc", "not-made": "neu"}


@pytest.fixture(scope="module")
def pages(tmp_path_factory) -> dict[str, str]:
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("tones") / "demo"
    build_public(folder)
    root = folder / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}


def test_every_state_the_demo_shows_is_placed_by_the_rule(pages, examined):
    shown = {s for page in pages.values()
             for s in re.findall(r'<tr data-(?:rung|badge)="[^"]*" data-state="([^"]*)">', page)}
    examined(len(shown), "rung and badge states shown")
    assert shown - set(tones.RUNG) == set(), "a state no rule places"
    assert {"yes", "no", "not-anchored", "unsigned", "signed-untrusted", "not-checked"} <= shown


def _drawn(css: str) -> dict[str, set[str]]:
    """Each rung or badge state, the tones the stylesheet gives it."""
    out: dict[str, set[str]] = {}
    for selectors, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        m = re.search(r"background:var\(--(ok|cc|bad|neu)-bg\)", body)
        if not m:
            continue
        for state in re.findall(r"tr\[data-(?:rung|badge)\]\[data-state=([a-z-]+)\]", selectors):
            out.setdefault(state, set()).add(m.group(1))
    return out


def tone_problems(css: str) -> list[str]:
    drawn = _drawn(css)
    return [f"{state} is drawn {sorted(drawn.get(state, set()))}, not {tones.tone(tones.RUNG, state)}"
            for state in tones.RUNG if drawn.get(state) != {tones.tone(tones.RUNG, state)}]


def test_the_stylesheet_draws_each_state_in_its_tone(examined):
    from onetrace_console.frame import stylesheet
    examined(len(tones.RUNG), "rung and badge states")
    assert tone_problems(stylesheet().decode("utf-8")) == []


def test_the_overviews_pills_carry_their_states_tone(pages, examined):
    from onetrace_console.overview import ATTENTION_WORDS
    home = pages["home.html"]
    items = re.findall(r'<li data-attention="([^"]+)"><span><span class="pill (\w+)">([^<]*)</span>', home)
    examined(len(items), "needs-attention pills")
    assert items
    for kind, tone, words in items:
        assert (tone, words) == (tones.tone(tones.ATTENTION, kind), ATTENTION_WORDS[kind]), kind


def test_sabotage_not_anchored_drawn_red_is_named(examined):
    from onetrace_console.frame import stylesheet
    examined(1, "planted rule")
    planted = stylesheet().decode("utf-8") + (
        ".shell .page tr[data-rung][data-state=not-anchored]>td:last-child>span:first-child"
        "{background:var(--bad-bg);color:var(--bad-ink)}")
    assert any(p.startswith("not-anchored is drawn") for p in tone_problems(planted))


def test_sabotage_a_table_moved_off_the_rule_is_named(monkeypatch, examined):
    examined(1, "planted table")
    monkeypatch.setitem(tones.RUNG, "not-anchored", tones.FAILED)
    assert tones.RUNG != BY_THE_RULE["RUNG"]
