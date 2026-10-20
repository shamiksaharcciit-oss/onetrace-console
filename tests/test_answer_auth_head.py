"""The answer and authorization pages carry the run page's head: the run and its pipeline, its two
times, and tabs to the run's views (Graph and Table on the run page). The answer page also carries
the four answers, as the run page's ladder states them. The authorization page does not: it must
never read as a pass, and "Ran as approved: Yes" there would read as the action approved. It keeps
its own heading and its "No records" state.

Held over every run of the public demo. Each check has its sabotage.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_runs_list import demo  # noqa: F401


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def head_problems(page: str, case: str, *, answers: bool, proof: str = "") -> list[str]:
    out = []
    head = re.search(r'<section data-section="run-head">.*?</section>', page, re.S)
    if head is None:
        return ["no head"]
    head = head.group(0)
    if not re.search(r'<(h1|p) class="run-title">', head):
        out.append("no run title")
    #: The ladder is on "What changed", or on "Proof" for a run whose records don't hold up.
    ladder = dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', case + proof))
    shown = dict(re.findall(r'<li data-head-rung="([^"]+)" data-state="([^"]+)">', head))
    if answers and (not shown or any(ladder.get(k) != v for k, v in shown.items())):
        out.append(f"answers {shown} against the run page's {ladder}")
    if not answers and shown:
        out.append("answers on a page that must never read as a pass")
    for href in re.findall(r'<nav class="tabs"[^>]*>(.*?)</nav>', head, re.S)[0:1]:
        for target in re.findall(r'href="([^"]+)"', href):
            if target.startswith(("case.html#", "proof.html#")):
                #: The run page's two views: a tab opens the one that holds its section.
                anchor = target.split("#", 1)[1]
                if f'<span id="{anchor}"></span>' not in (case if target.startswith("case") else proof):
                    out.append(f"tab {target} opens nothing")
            elif target.startswith("#"):
                out.append(f"tab {target} points at this page")
    if page.count("<h1") != 1:
        out.append(f"{page.count('<h1')} h1s")
    return out


def test_the_answer_and_authorization_pages_carry_the_head(demo, examined):  # noqa: F811
    store, pages = demo
    runs = store.runs()
    examined(2 * len(runs), "answer and authorization pages")
    for run in runs:
        folder = pages / "runs" / run.key
        case = (folder / "case.html").read_text(encoding="utf-8")
        proof = (folder / "proof.html").read_text(encoding="utf-8")
        answer = (folder / "answer.html").read_text(encoding="utf-8")
        auth = (folder / "authorization.html").read_text(encoding="utf-8")
        assert head_problems(answer, case, answers=True, proof=proof) == [], (run.run_id, "answer")
        assert head_problems(auth, case, answers=False, proof=proof) == [], (run.run_id, "authorization")
        assert "<h1>Authorization</h1>" in auth and '<p data-state="no-records">No records</p>' in auth


def test_sabotage_a_head_missing_misplaced_or_pointing_nowhere_is_named(demo, examined):  # noqa: F811
    store, pages = demo
    folder = pages / "runs" / store.runs()[0].key
    case = (folder / "case.html").read_text(encoding="utf-8")
    proof = (folder / "proof.html").read_text(encoding="utf-8")
    answer = (folder / "answer.html").read_text(encoding="utf-8")
    auth = (folder / "authorization.html").read_text(encoding="utf-8")
    strip = re.search(r'<ul class="seals">.*?</ul>', answer, re.S).group(0)
    planted = {
        "no head": (answer.replace('data-section="run-head"', 'data-section="gone"', 1), True),
        "answers on the authorization page": (auth.replace('<nav class="tabs"', strip + '<nav class="tabs"', 1), False),
        #: The run's graph tab opens whichever view holds the graph (Proof, for a red run).
        "a tab to nowhere": (re.sub(r'href="(case|proof)\.html#graph"', r'href="\1.html#nowhere"', answer, count=1), True),
    }
    examined(len(planted), "planted pages")
    for name, (bad, answers) in planted.items():
        assert bad != (answer if answers else auth), name
        assert head_problems(bad, case, answers=answers, proof=proof), name
