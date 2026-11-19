"""What changed? on a run's page reads as sentences: on a public console, a pair it does not hold is "Not compared.",
starting as a sentence starts, before "This demo compares nothing; it offers the comparisons it holds."

Read over every run page of the public demo that says it.
"""

from __future__ import annotations

import re


def test_not_compared_starts_as_a_sentence(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages" / "runs").glob("*/case.html"))
    said = [
        m.group(1)
        for p in pages
        for m in re.finditer(r'<span data-what-changed="not-held">([^<]*)</span>', p.read_text(encoding="utf-8"))
    ]
    examined(len(said), "not-compared lines")
    assert said, "no run page says it: the demo changed, and this test reads nothing"
    assert {s for s in said if not s[:1].isupper()} == set()
