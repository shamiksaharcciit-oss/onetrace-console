"""The Compare button on a local console's "Choose run B" page: its look, and where it says a refusal.

Held here, each with a sabotage that the check names:

1. the line where the script says what the console answered is its own line, after the request
   text, empty, and takes no space while it is empty;
2. the button takes the console's own button look in both themes: the theme switch's shape, every
   colour a token of the theme, each token defined in light and in dark;
3. run in node: a refusal is said as the console words it, with a full stop put at its end where it
   has none and none added where it has one; the button is offered again.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

import pytest

from tests.test_choose_two_runs import _pages, three  # noqa: F401  (three: a fixture)
from tests.test_home_and_diff import diverging  # noqa: F401  (three's fixture)

NODE = shutil.which("node")
needs_node = pytest.mark.skipif(NODE is None, reason="node is not installed here, so the script can't be run")


def _not_compared_cell(store, comparison) -> str:
    from onetrace_console.choose_pages import pair_href
    from onetrace_console.overview import pipelines
    (p,) = pipelines(store)
    page = _pages(store)[pair_href(p.label, comparison.run_a)]
    (row, *_) = re.findall(r'<tr data-run="[0-9a-f]{64}" data-pair="not-compared">(.*?)</tr>', page, re.S)
    return re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)[-1]


# ------------------------------------------------------------------ 1. the line

def line_problems(cell: str) -> list[str]:
    out = []
    order = [cell.find(m) for m in ("<button", "Not compared yet.", "<code", "<span data-compare-said")]
    if -1 in order or order != sorted(order):
        out.append(f"the said line is not after the request text: {order}")
    if not re.search(r"</code><span data-compare-said role=\"status\"></span>$", cell):
        out.append("the said line is not empty at the cell's end")
    return out


def stylesheet_text() -> str:
    from onetrace_console.frame import stylesheet
    return stylesheet().decode("utf-8")


def test_the_refusal_line_is_its_own_after_the_request_and_takes_no_space_empty(three, examined):
    comparison, store, _hostile = three
    css = stylesheet_text()
    examined(2, "the not-compared cell, the stylesheet")
    assert line_problems(_not_compared_cell(store, comparison)) == []
    assert ".cp [data-compare-said]{display:block" in css and ".cp [data-compare-said]:empty{display:none}" in css


def test_sabotage_the_line_before_the_request_is_named(three, examined):
    comparison, store, _hostile = three
    cell = _not_compared_cell(store, comparison)
    planted = cell.replace('<span data-compare-said role="status"></span>', "").replace(
        "Not compared yet.", '<span data-compare-said role="status"></span> Not compared yet.')
    examined(1, "planted cell")
    assert line_problems(planted) != []


# ------------------------------------------------------------------ 2. the look

def look_problems(css: str) -> list[str]:
    from tests.test_shared_style import _tokens
    rules = re.findall(r"\.cp button\[data-compare-post\][^{]*\{([^}]*)\}", css)
    if not rules:
        return ["no rule for the button"]
    out = []
    light, dark = _tokens("light"), _tokens("dark")
    for body in rules:
        for prop, value in re.findall(r"(color|background|border(?:-color)?|outline)\s*:\s*([^;]+)", body):
            if re.search(r"#[0-9a-fA-F]{3,8}\b|rgb|hsl", value):
                out.append(f"{prop} is a colour of its own: {value}")
            for token in re.findall(r"var\(--([\w-]+)\)", value):
                if token not in light or token not in dark:
                    out.append(f"--{token} is not a colour of both themes")
    base = rules[0]
    for shape in ("font:inherit", "border-radius:var(--r-ctl)", "padding:4px 10px", "cursor:pointer"):
        if shape not in base:
            out.append(f"the button is not shaped as the theme switch: no {shape}")
    return out


def test_the_button_takes_the_consoles_look_from_the_themes_tokens(examined):
    css = stylesheet_text()
    examined(1, "stylesheet")
    assert look_problems(css) == []


def test_sabotage_a_colour_of_its_own_or_no_rule_is_named(examined):
    css = stylesheet_text()
    examined(2, "planted stylesheets")
    assert look_problems(css.replace("background:var(--surface);\n  border:1px solid var(--line-strong)",
                                     "background:#e5e7eb;\n  border:1px solid var(--line-strong)", 1)) != []
    assert look_problems(re.sub(r"\.cp button\[data-compare-post\]", ".cp button[data-other]", css)) != []


# ------------------------------------------------------------------ 3. the script, run

_HARNESS = r"""
const [script, answers] = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const said = {textContent: ''};
let handler = null;
const button = {hidden: true, disabled: false, getAttribute: () => '/compare?a=x&b=y',
  addEventListener: (_, f) => { handler = f; }, parentNode: {querySelector: () => said}};
global.document = {cookie: '', querySelectorAll: () => [button]};
global.location = {href: ''};
let i = 0;
global.fetch = () => { const a = answers[i++];
  return Promise.resolve({ok: a.status < 400, status: a.status, json: () => Promise.resolve(a.body)}); };
new Function(script)();
const seen = [];
(async () => {
  for (const _ of answers) {
    handler();
    await new Promise(r => setTimeout(r, 0)); await new Promise(r => setTimeout(r, 0));
    seen.push({said: said.textContent, offered: !button.disabled, hidden: button.hidden, href: location.href});
  }
  process.stdout.write(JSON.stringify(seen));
})();
"""

MISSING = "run 1350c35dd19e: couldn't check: the stored record is missing MANIFEST.json"


def _run(script: str, answers: list[dict]) -> list[dict]:
    body = script.removeprefix("<script>").removesuffix("</script>")
    done = subprocess.run([NODE, "-e", _HARNESS], input=json.dumps([body, answers]), capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


ANSWERS = [{"status": 409, "body": {"error": MISSING}}, {"status": 409, "body": {"error": "Already said."}},
           {"status": 200, "body": {"answer": "Not compared: the pair is the same run"}}]
WANT = [MISSING + ".", "Already said.", "Not compared: the pair is the same run."]


@needs_node
def test_a_refusal_is_said_as_worded_ending_in_a_full_stop_and_the_button_offered_again(examined):
    from onetrace_console.compare_script import COMPARE_SCRIPT
    seen = _run(COMPARE_SCRIPT, ANSWERS)
    examined(len(seen), "answers")
    assert [s["said"] for s in seen] == WANT
    assert all(s["offered"] and not s["hidden"] and s["href"] == "" for s in seen)


@needs_node
def test_sabotage_a_refusal_said_without_its_full_stop_is_named(examined):
    from onetrace_console.compare_script import COMPARE_SCRIPT
    planted = COMPARE_SCRIPT.replace("s.textContent=said(", "s.textContent=(")
    assert planted != COMPARE_SCRIPT
    examined(1, "planted script")
    assert [s["said"] for s in _run(planted, ANSWERS)] != WANT
