"""The pipeline page's "Compare two runs" picker: each label and its select one field, label above select.

When the line wrapped, "Candidate (run B)" sat on one line and its select on the next, beside Compare.
Each label now holds its own words and then its own select (`compare-field`), and the form lays out its
two fields side by side where they fit and stacked where they don't, Compare at the selects' bottom edge
(or below them, stacked), the selects one width. The local console's picker and the public console's are
the same form. The browser check of the layout, at 1280, 1024 and 390 px in both themes, is the round's
rendered check; here, the markup and the stylesheet's rules.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from onetrace_console import pipeline_pages, visitor_compare
from onetrace_console.frame import PAGE_CSS, rendering

RUNS = [SimpleNamespace(run_id=f"p1-0{i}-run", key=f"{i:064x}", received_at=f"2026-11-07T10:0{i}:00+00:00")
        for i in range(1, 4)]
PIPELINE = SimpleNamespace(label="P1", runs=RUNS)

FIELD = re.compile(r'<label class="compare-field"><span class="compare-label">([^<]+)</span>'
                   r'<select name="([ab])"[^>]*>.*?</select></label>', re.S)


def _forms() -> dict[str, str]:
    with rendering(onedoor=False, sign_in=False, public=False):
        local = pipeline_pages._local_picker(PIPELINE)
    return {"local": local, "public": visitor_compare.picker(PIPELINE)}


def test_each_label_holds_its_own_words_then_its_own_select(examined):
    forms = _forms()
    examined(len(forms), "pickers")
    for which, form in forms.items():
        assert FIELD.findall(form) == [("Baseline (run A)", "a"), ("Candidate (run B)", "b")], (which, form)
        #: Compare comes after the two fields, never between a label and its select.
        assert form.index("</label>", form.index('name="b"')) < form.index("<button")


def test_the_stylesheet_lays_the_fields_out_side_by_side_or_stacked_with_compare_at_their_bottom(examined):
    rules = {k.strip(): v for k, v in re.findall(r"([^{}]+)\{([^{}]*)\}", PAGE_CSS)}
    examined(len(rules), "page rules")
    pick = rules[".cp form:is([data-local-compare],[data-visitor-compare])"]
    assert "display:flex" in pick and "flex-wrap:wrap" in pick and "align-items:flex-end" in pick
    field = rules[".cp .compare-field"]
    assert "flex-direction:column" in field and "flex:1 1 16rem" in field and "max-width:24rem" in field
    assert "width:100%" in rules[".cp .compare-field select"]
