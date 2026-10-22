"""The Overview in 0.1.1's look: what moved, and what may not be lost on the way.

Checked on the demo's own Overview, as a public console serves it:
1. one subtitle line; the page's counting rule folded under "How these counts work", word for word;
2. each card: its count, one short line, and its definition behind a native "?" (a `<details>`,
   reached by the keyboard, no script needed); no card's definition is empty;
3. zeros folded: every verdict state at 0 is still named and linked, in one grey line; every
   state with runs is a count with its denominator; together they are the four states;
4. times: every `<time>` still shows its absolute UTC time; the relative-time script is carried
   once, and a public console's policy names its hash;
5. no card gives two different counts under the same label. The Records agree card led with "28 of
   31 runs verified" and listed the check's "29 of 31 Verified" under it: 28 runs whose check held
   with their output files required, and 29 whose check held. Its line now says what the rung
   below it says, with the same counts: rung 1's five states as each run's own page reads them,
   the reason said under not checked, each opening exactly its runs.

Each check is a function returning the problems it finds; each has its sabotage, a planted page
or header that must be named.
"""
from __future__ import annotations

import html
import re

import pytest

#: The Records agree card's states: rung 1's five, each in its own words, as each run's page reads
#: it -- the demo's one run not checked says why (held without its output files required).
STATES = ("records agree", "not checked (held without its output files required)", "couldn't check",
          "contradict their record", "no verdict recorded")
#: A count and the word that labels it: "28 of 31 runs verified" is (28, "verified"),
#: "2 incidents" is (2, "incidents"); "runs" or "run" between them is skipped.
_COUNT = re.compile(r"(?<![\w.])(\d+)(?: of \d+)?(?: runs?\b)?\s+([A-Za-z']+)")


#: The demo's pages folder, set by `home` for the checks that open a card's lists.
PAGES: list = []


@pytest.fixture(scope="module")
def home(shared_demo) -> str:
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    PAGES[:] = [folder / "store" / "pages"]
    return (folder / "store" / "pages" / "home.html").read_text(encoding="utf-8")


def _text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def subtitle_problems(page: str) -> list[str]:
    from onetrace_console.render import SUBTITLE
    out = []
    if re.findall(r'<p data-section="subtitle">(.*?)</p>', page, re.S) != [html.escape(SUBTITLE)]:
        out.append("no one-line subtitle")
    fold = re.search(r'<details data-section="how"><summary>How these counts work</summary>'
                     r'<p data-section="what">(.*?)</p></details>', page, re.S)
    if not fold or not _text(fold.group(1)).startswith("Every count below carries the number"):
        out.append("the counting rule is not folded under 'How these counts work'")
    return out


def card_problems(page: str) -> list[str]:
    out = []
    cards = re.findall(r'<div data-card="([^"]+)">(.*?)</div>(?=<div data-card|</section>)', page, re.S)
    if [c for c, _ in cards] != ["pipelines", "runs", "records-agree", "need-attention"]:
        out.append(f"the cards are {[c for c, _ in cards]}")
    for name, body in cards:
        if not re.search(r'<p class="lead"><a href="[^"]+"><span class="kpi">\d+</span>', body):
            out.append(f"{name}: no count")
        lines = re.findall(r'</p>(<p[^>]*>.*?</p>)(?=<p|<details)', body, re.S)
        if not lines:
            out.append(f"{name}: no line under the count")
        fold = re.search(r'<details class="def"><summary title="What this count means" '
                         r'aria-label="What this count means">\?</summary>(.*?)</details>', body, re.S)
        if not fold or not _text(fold.group(1)):
            out.append(f"{name}: no definition behind its '?'")
    return out


def zero_problems(page: str) -> list[str]:
    card = re.search(r'<div data-card="records-agree">(.*?)</div>', page, re.S).group(1)
    said = re.findall(r'<a href="executions-[a-z-]+\.html">(\d+) of (\d+) ([^<]+)</a>',
                      re.search(r'<p data-line="states">(.*?)</p>', card, re.S).group(1)
                      if 'data-line="states"' in card else "")
    zero_line = re.search(r'<p class="zero" data-line="zero">0 of \d+ in the other states: (.*?)</p>',
                          card, re.S)
    zeros = [html.unescape(z) for z in re.findall(r'<a href="executions-[a-z-]+\.html">([^<]+)</a>',
                                                  zero_line.group(1))] if zero_line else []
    out = [f"'{html.unescape(w)}' is shown with 0 runs instead of folded" for n, _, w in said if n == "0"]
    named = sorted([html.unescape(w) for _, _, w in said] + zeros)
    if named != sorted(STATES):
        out.append(f"the states named are {named}, not the five")
    return out


def label_problems(page: str) -> list[str]:
    """Each card's counts by the word labelling them, the "?" left out (it defines, not counts):
    a label carrying two different counts is named."""
    out = []
    for name, body in re.findall(r'<div data-card="([^"]+)">(.*?)</div>', page, re.S):
        body = re.sub(r'<details class="def">.*?</details>', "", body, flags=re.S)
        seen: dict[str, set[int]] = {}
        for count, label in _COUNT.findall(_text(body)):
            seen.setdefault(label.lower(), set()).add(int(count))
        out += [f"{name}: {sorted(counts)} all labelled {label!r}"
                for label, counts in seen.items() if len(counts) > 1]
    return out


def rung_problems(page: str, pages) -> list[str]:
    """The Records agree card's counts are the rung's, and each opens exactly its runs."""
    card = re.search(r'<div data-card="records-agree">(.*?)</div>', page, re.S).group(1)
    rung = _text(re.search(r'<tr data-rung="records-agree">(.*?)</tr>', page, re.S).group(1))
    want = {"records agree": int(re.search(r"(\d+) of \d+", rung).group(1)),
            "not checked (held without its output files required)":
                int(re.search(r"(\d+) not checked", rung).group(1)),
            "couldn't check": int(re.search(r"(\d+) couldn't check", rung).group(1)),
            "contradict their record": int(re.search(r"(\d+) contradict their record", rung).group(1)),
            "no verdict recorded": int(re.search(r"(\d+) no verdict recorded", rung).group(1))}
    line = re.search(r'<p data-line="states">(.*?)</p>', card, re.S)
    said = re.findall(r'<a href="([^"]+)">(\d+) of \d+ ([^<]+)</a>', line.group(1) if line else "")
    got = {html.unescape(w): int(n) for _, n, w in said}
    out = [f"the card says {got}, the rung {want}"] if got != {w: n for w, n in want.items() if n} else []
    for href, n, w in said:
        rows = len(re.findall(r'<tr data-run="', (pages / href).read_text(encoding="utf-8")))
        if rows != int(n):
            out.append(f"{html.unescape(w)}: {n} on the card, {rows} runs on {href}")
    return out


def time_problems(page: str) -> list[str]:
    from onetrace_console.words import RELATIVE_TIME_SCRIPT
    out = []
    times = re.findall(r'<time datetime="([^"]+)"[^>]*>([^<]*)</time>', page)
    if not times:
        out.append("no time on the page")
    out += [f"{v}: shows {t!r}, not its absolute UTC time" for v, t in times
            if not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d UTC", t)]
    if page.count(RELATIVE_TIME_SCRIPT) != 1:
        out.append(f"the relative-time script is there {page.count(RELATIVE_TIME_SCRIPT)} times")
    return out


def test_one_subtitle_line_and_the_rule_folded(home, examined):
    examined(1, "Overview")
    assert subtitle_problems(home) == []


def test_each_card_a_count_a_line_and_a_definition_behind_its_question_mark(home, examined):
    examined(4, "cards")
    assert card_problems(home) == []


def test_zeros_are_folded_and_every_state_is_still_named(home, examined):
    examined(len(STATES), "verdict states")
    assert zero_problems(home) == []
    assert 'data-line="zero"' in home, "the demo has a state at 0 to fold"


def test_no_card_gives_two_counts_under_one_label(home, examined):
    examined(4, "cards")
    assert label_problems(home) == []


def test_the_records_agree_card_gives_the_rungs_counts_each_opening_its_runs(home, examined):
    examined(len(STATES), "states")
    assert rung_problems(home, PAGES[0]) == []


def test_every_time_keeps_its_absolute_utc_and_the_script_is_carried_once(home, examined):
    examined(home.count("<time "), "times")
    assert time_problems(home) == []


def test_a_public_policy_names_the_scripts_hash_and_the_checker_catches_it_missing(home, examined):
    """Sabotage: the policy as it was before the script, with only the print helper's hash."""
    from onetrace_console.public import _script_hash, content_security_policy, security_headers
    from onetrace_console.viewer.page import PRINT_SCRIPT
    from onetrace_console.words import RELATIVE_TIME_SCRIPT
    from tools import container_check
    headers = {k.lower(): v for k, v in security_headers()}
    body = home.encode("utf-8")
    examined(2, "policies")
    assert _script_hash(RELATIVE_TIME_SCRIPT) in content_security_policy()
    #: The page as stored, before the server fills its frame: only the policy's findings count.
    scripts = lambda problems: [p for p in problems if "inline script" in p]
    assert scripts(container_check.page_problems(200, headers, body)) == []
    old = content_security_policy().replace(" " + _script_hash(RELATIVE_TIME_SCRIPT), "")
    assert _script_hash(PRINT_SCRIPT) in old and _script_hash(RELATIVE_TIME_SCRIPT) not in old
    problems = container_check.page_problems(200, {**headers, "content-security-policy": old}, body)
    assert any("inline script the policy does not name" in p for p in scripts(problems)), problems


# ------------------------------------------------------------------ the sabotages

def test_sabotage_the_subtitle_paragraph_unfolded_is_named(home, examined):
    examined(1, "planted page")
    planted = home.replace('<details data-section="how"><summary>How these counts work</summary>', "", 1)
    assert "the counting rule is not folded under 'How these counts work'" in subtitle_problems(planted)


def test_sabotage_a_definition_left_out_is_named(home, examined):
    examined(1, "planted page")
    planted = re.sub(r'(<div data-card="need-attention">.*?<summary[^>]*>\?</summary>).*?(</details>)',
                     r"\1\2", home, count=1, flags=re.S)
    assert "need-attention: no definition behind its '?'" in card_problems(planted)


def test_sabotage_a_state_at_zero_hidden_outright_is_named(home, examined):
    examined(1, "planted page")
    planted = re.sub(r'<p class="zero" data-line="zero">.*?</p>', "", home, count=1, flags=re.S)
    assert any("not the five" in p for p in zero_problems(planted))


def test_sabotage_two_counts_under_one_label_are_named_in_each_card(home, examined):
    caught = 0
    #: The Records agree card as it was in 0.2.0's candidate: a second count, 29, under the same
    #: label as the line's 28.
    planted = home.replace('<p data-line="states">',
                           '<p data-line="states"><a href="x">29 of 31 records agree</a> · ', 1)
    assert any(p.startswith("records-agree:") for p in label_problems(planted))
    caught += 1
    for name, plant in (("pipelines", "<p>8 pipelines</p>"), ("runs", "<p>30 runs stored</p>"),
                        ("need-attention", "<p>5 of 31 runs need attention</p>")):
        planted = re.sub(rf'(<div data-card="{name}">.*?)(<details)', rf"\1{plant}\2", home,
                         count=1, flags=re.S)
        assert any(p.startswith(f"{name}:") for p in label_problems(planted)), name
        caught += 1
    examined(caught, "faults caught")


def test_sabotage_a_card_count_off_the_rung_or_off_its_list_is_named(home, examined):
    #: A count changed on the card alone, and a link to the list of another state.
    off = re.sub(r'(<p data-line="states"><a href="[^"]+">)(\d+)', lambda m: m.group(1) + str(int(m.group(2)) + 1),
                 home, count=1)
    assert any("the card says" in p for p in rung_problems(off, PAGES[0]))
    swapped = re.sub(r'(<p data-line="states"><a href=")[^"]+(">)', r"\1executions-all.html\2", home, count=1)
    assert any("runs on executions-all.html" in p for p in rung_problems(swapped, PAGES[0]))
    examined(2, "faults caught")


def test_sabotage_a_time_shown_only_relative_is_named(home, examined):
    examined(1, "planted page")
    planted = re.sub(r'(<time datetime="[^"]+"[^>]*>)[^<]*(</time>)', r"\g<1>2 h ago\2", home, count=1)
    assert any("not its absolute UTC time" in p for p in time_problems(planted))
