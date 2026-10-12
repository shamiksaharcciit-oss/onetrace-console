"""The Overview in 0.1.1's look: what moved, and what may not be lost on the way.

Checked on the demo's own Overview, as a public console serves it:
1. one subtitle line; the page's counting rule folded under "How these counts work", word for word;
2. each card: its count, one short line, and its definition behind a native "?" (a `<details>`,
   reached by the keyboard, no script needed); no card's definition is empty;
3. zeros folded: every verdict state at 0 is still named and linked, in one grey line; every
   state with runs is a count with its denominator; together they are the four states;
4. times: every `<time>` still shows its absolute UTC time; the relative-time script is carried
   once, and a public console's policy names its hash.

Each check is a function returning the problems it finds; each has its sabotage, a planted page
or header that must be named.
"""
from __future__ import annotations

import html
import re

import pytest

STATES = ("Verified", "Couldn't check", "Contradicts its record", "No verdict recorded")


@pytest.fixture(scope="module")
def home(tmp_path_factory) -> str:
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("overview") / "demo"
    build_public(folder)
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
    if [c for c, _ in cards] != ["runs", "records-agree", "changed-vs-baseline", "incidents"]:
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
        out.append(f"the states named are {named}, not the four")
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
    planted = re.sub(r'(<div data-card="incidents">.*?<summary[^>]*>\?</summary>).*?(</details>)',
                     r"\1\2", home, count=1, flags=re.S)
    assert "incidents: no definition behind its '?'" in card_problems(planted)


def test_sabotage_a_state_at_zero_hidden_outright_is_named(home, examined):
    examined(1, "planted page")
    planted = re.sub(r'<p class="zero" data-line="zero">.*?</p>', "", home, count=1, flags=re.S)
    assert any("not the four" in p for p in zero_problems(planted))


def test_sabotage_a_time_shown_only_relative_is_named(home, examined):
    examined(1, "planted page")
    planted = re.sub(r'(<time datetime="[^"]+"[^>]*>)[^<]*(</time>)', r"\g<1>2 h ago\2", home, count=1)
    assert any("not its absolute UTC time" in p for p in time_problems(planted))
