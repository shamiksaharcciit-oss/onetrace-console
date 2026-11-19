"""A run's page leads with the run and its verdict; what the run raised comes after them.

A run whose record fails its check raises incidents, and its pages list them. They are listed under the run's head and
its verdict, not above: a reader first meets which run this is and what its record says ("Contradicts its
record: ..."), then the incident list, whose lines quote the verifier's own rows. On a phone, the list above them took
the whole first screen.

Read on the public demo's p1-14 (one output's bytes changed after it was recorded): on its What changed
page, the run's head, then the verdict, then the incidents; its Proof page lists none, as before.
"""

from __future__ import annotations

import re


def _pages_of(shared_demo, run_id: str) -> dict[str, str]:
    root = shared_demo["folder"] / "store" / "pages" / "runs"
    for case in sorted(root.glob("*/case.html")):
        page = case.read_text(encoding="utf-8")
        title = re.search(r"<title>(.*?)</title>", page, re.S)
        if title and title.group(1).strip().endswith(run_id):
            return {name: (case.parent / name).read_text(encoding="utf-8") for name in ("case.html", "proof.html")}
    raise AssertionError(f"{run_id} is not in the demo")


def test_a_failing_run_s_head_and_verdict_come_before_its_incidents(shared_demo, examined):
    pages = _pages_of(shared_demo, "p1-14-candidate-set3-byte-changed")
    examined(len(pages), "pages")
    #: What changed lists them: under the head and the verdict.
    page = pages["case.html"]
    head = page.index('data-section="run-head"')
    verdict = page.index('data-section="integrity"')
    raised = page.index('data-section="incidents-raised"')
    assert head < verdict < raised, (head, verdict, raised)
    #: Proof lists none, as before: nothing is added there.
    assert 'data-section="incidents-raised"' not in pages["proof.html"]
