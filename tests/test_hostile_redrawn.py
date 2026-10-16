"""A hostile run name through every part the visual-quality work redrew: the run's head with its
declined chip, its page's banner, the runs lists' chip, the Overview's count, the fingerprint
folds, and a candidate's comparison chip naming a hostile baseline. Markup stays text; control and
bidirectional characters are shown as escapes, never drawn raw. (The graph's own boxes take hostile
names, states and quoted lines in tests/test_graph_redraw.py.)

The SDK refuses such a run id, so the record is one another tool could write: a delivered run's
manifest given the hostile id, as tests/test_round4_fixes.py stores one. Each check has its sabotage.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace

from onetrace_console.pages import CASE, render_execution
from onetrace_console.render import render_all
from tests.test_pages import GENERATED_AT
from tests.test_unreadable import _resummed, _stored

RLO, BELL = "\u202e", "\x07"
HOSTILE = '<b>run</b>&"q"' + RLO + BELL + "id"
#: Each character no page may draw as itself.
RAW = (RLO, BELL)


def page_problems(name: str, page: str) -> list[str]:
    out = [f"{name}: {c!r} drawn raw" for c in RAW if c in page]
    if "<b>run</b>" in page:
        out.append(f"{name}: the name's markup drawn as markup")
    return out


def _hostile_stopped_run(files, store):
    out = dict(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = HOSTILE
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    run = _stored(_resummed(out), store)
    #: Its stored reading says it stopped at a step, so its chip and the Overview's count are drawn.
    store.put_run(replace(run, declined=json.dumps({"stage": f"a{RLO}<i>step</i>", "reason": f"no{BELL}",
                                                    "left": ["<u>pay</u>"]})))
    return store.get_run(run.key)


def test_a_hostile_run_name_stays_escaped_in_every_redrawn_part(files, store, examined):
    run = _hostile_stopped_run(files, store)
    assert run.run_id == HOSTILE, "ingest keeps a record's words as they are"
    pages = dict(render_all(store, generated_at=GENERATED_AT))
    pages.update({f"run/{k}": v for k, v in render_execution(run, store, generated_at=GENERATED_AT).pages.items()})
    examined(len(pages), "pages drawn with the hostile run")
    assert [p for n, page in pages.items() for p in page_problems(n, page)] == []
    case = pages[f"run/{CASE}"]
    assert "&lt;b&gt;run&lt;/b&gt;&amp;" in case and "\\u202e" in case, "the name is not shown escaped"
    assert 'data-declined="true"' in case and "&lt;i&gt;step&lt;/i&gt;" in case, "the declined chip is not drawn"
    assert '<details class="fingerprint"' in case, "no fingerprint fold on the run page"
    stopped = pages["executions-stopped-by-a-step.html"]
    assert "data-declined" in stopped and not page_problems("stopped", stopped)


def test_a_hostile_baseline_name_in_a_candidate_s_comparison_chip(examined):
    from types import SimpleNamespace

    from onetrace_console.run_head import comparison_chip
    model = SimpleNamespace(graph_source=(HOSTILE, "diff/x.html", "2026-10-14", True),
                            graph_nodes=[SimpleNamespace(mark="first", name=f"s{RLO}<i>x</i>")])
    chip = comparison_chip(model)
    examined(1, "comparison chip")
    assert page_problems("chip", chip) == [] and "&lt;b&gt;run&lt;/b&gt;" in chip, chip


def test_sabotage_raw_characters_and_markup_are_named(examined):
    examined(2, "planted pages")
    assert page_problems("p", f"<p>{RLO}</p>") and page_problems("p", "<b>run</b>")
