"""The restyle states what the pages stated before, and nothing goes missing.

`tests/fixtures/visible_text/baseline.json` is every page kind's visible text, taken by
`tools/visible_text.py` from the tree before the restyle changed any styling. This test takes it again
from the tree as it is and compares page by page, as multisets of text blocks: a block may move
within its page, but not vanish, change or appear unexplained.

Every difference must be declared below, with its reason:
- `MOVED`: blocks that move from one page to another (the Overview's "every count" lists to the
  All counts page). The two pages are compared as one, and the new one is also named in
  `NEW_PAGES`.
- `EXPLAINED`: a block gone or new on one page, with why. A wording change is also reported as
  before/after.
- `NEW_PAGES`: a page that did not exist before, with why.

Before comparing, both sides lose exactly two things that belong to the machine, not the page
And nothing else: any path ending in `onetrace_verify/verify.py` becomes
`<verifier>` (the venv is wherever the host keeps it), and in the verifier's own output CR LF
becomes LF (Windows writes that output in text mode). A CR LF anywhere else is data -- a forged
digest's, say -- and is compared as it is. `EXPLAINED` blocks are written in normalised form.

One block is left out of both sides: the Overview's old sentence on why counts were kept below
the cards, which quoted an internal id. It was removed from `baseline.json` and from the
`EXPLAINED` blocks together; `tests/test_no_internal_ids.py` holds every page to showing no
such id, which covers it.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "tests" / "fixtures" / "visible_text" / "baseline.json"

#: (from page, to page): blocks may move between these pages; compared as one.
MOVED: list[tuple[str, str]] = [("home.html", "counts.html")]
#: page -> {"gone": {block: reason}, "new": {block: reason}}
#: The execution graph goes on every run's case page, between the ladder and the
#: timeline: its heading, the boxes' labels (each node's id as recorded),
#: the "Show as table" view with its headings, each node's recorded position, and the note and
#: the "Recorded order" link; a run with no `edges` (the three SDK-made
#: runs here) also carries the straight line's label. Nothing on any page is gone. Generated
#: from the measured difference by tooling, not typed.
_GRAPH = "the execution graph's section on the case page"
#: The Overview's full list of counts moves to its own page, All counts, one link
#: from the Overview, as a declared moved block. Every count
#: moves whole; what is new or gone is only the page's own frame, and one reworded sentence.
#: Generated from the measured difference by tooling, not typed.
_COUNTS = "the Overview's list of counts moved to the All counts page"
_COUNTS_WHY = (_COUNTS + ': "kept whole below the cards" is untrue on a page of its own, so it '
               "names the Overview's cards instead, in the fixed words, with no "
               "internal id on the page")
#: The recent runs' delivery column counts declared stages
#: with at least one receipt, and states retries apart; its heading says so. Generated from the
#: measured difference by tooling, not typed.
_DELIVERED = ("declared stages with at least one receipt, retries stated "
              "apart, in place of a count of receipts")
#: In the console the Runs page is exactly the list of the stored runs, so
#: the free viewer file's sentence is replaced there by the fixed words. Generated from the
#: measured difference by tooling, not typed.
_RUNS_STORED = "the console's Runs page states that it lists every stored run"
#: In the console every other list a count opens is drawn from the store,
#: so the free file's sentence is replaced there by the fixed words. Generated from the measured
#: difference by tooling, not typed.
_RUNS_IN_LIST = "a filtered list states it is part of the stored runs"
#: The preview banner in the console's fixed words, on the one
#: preview run's case page the baseline holds. Generated from the measured difference by
#: tooling, not typed.
_PREVIEW_BANNER = "the preview banner says the record's format, not \"sample\""
#: "Last attempt failed" joins the needs-attention order after a declared stage
#: missing, and the order's own sentence names it there. Generated from the measured difference.
_LAST_FAILED = "the needs-attention order names the failed last attempt"
EXPLAINED: dict[str, dict[str, dict[str, str]]] = {
    "executions-changed-vs-baseline.html": {
        "gone": {
            "Runs this page was given: 1 of 4, and it lists that one. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-contradicts.html": {
        "gone": {
            "Runs this page was given: 1 of 4, and it lists that one. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-could-not-check.html": {
        "gone": {
            "Runs this page was given: 0 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-holds.html": {
        "gone": {
            "Runs this page was given: 3 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 3 of 4 stored, and this page lists all 3. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-missing-a-declared-stage.html": {
        "gone": {
            "Runs this page was given: 0 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-missing-not-established.html": {
        "gone": {
            "Runs this page was given: 0 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-most-recent.html": {
        "gone": {
            "Runs this page was given: 4 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 4 of 4 stored, and this page lists all 4. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-needs-attention.html": {
        "gone": {
            "Runs this page was given: 2 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 2 of 4 stored, and this page lists all 2. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-not-checked.html": {
        "gone": {
            "Runs this page was given: 0 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-nothing-missing.html": {
        "gone": {
            "Runs this page was given: 4 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 4 of 4 stored, and this page lists all 4. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-pipeline-p1.html": {
        "gone": {
            "Runs this page was given: 1 of 4, and it lists that one. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-pipeline-p2.html": {
        "gone": {
            "Runs this page was given: 3 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 3 of 4 stored, and this page lists all 3. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-records-agree.html": {
        "gone": {
            "Runs this page was given: 0 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "executions-run-id-reused.html": {
        "gone": {
            "Runs this page was given: 1 of 4, and it lists that one. It is not a view of a store, and nothing is summarised across runs.":
                _RUNS_IN_LIST,
        },
        "new": {
            "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.":
                _RUNS_IN_LIST,
        },
    },
    "run[preview]/case.html": {
        "gone": {"Generated from a preview sample record, not from a production run.":
                 _PREVIEW_BANNER},
        "new": {"This record is in a preview format (stage-receipt-chain/0.0-preview).":
                _PREVIEW_BANNER},
    },
    "executions-all.html": {
        "gone": {"Runs this page was given: 4 of 4, and it lists every one of them. It is not a view of a store, and nothing is summarised across runs.":
                 _RUNS_STORED},
        "new": {"Runs stored: 4 of 4, and this page lists every one of them. Nothing is summarised across runs on this page.":
                _RUNS_STORED},
    },
    "home.html + counts.html": {
        "gone": {
            "Order: contradicts itself, then couldn't check, then not checked, then a declared stage missing, then changed vs baseline; newest first within each.":
                _LAST_FAILED,
            "2 of 2 delivered":
                _DELIVERED,
            "3 of 3 delivered":
                _DELIVERED,
            "Receipts delivered of stages declared":
                _DELIVERED,
            "Every count":
                _COUNTS + ": the list's heading, now the page's heading, All counts",
        },
        "new": {
            "Order: contradicts itself, then couldn't check, then not checked, then a declared stage missing, then last attempt failed, then changed vs baseline; newest first within each.":
                _LAST_FAILED,
            "2 of 2 declared stages":
                _DELIVERED,
            "3 of 3 declared stages":
                _DELIVERED,
            "Declared stages delivered":
                _DELIVERED,
            "All counts":
                _COUNTS + ": the page's heading, and the Overview's link to it",
            "Every count is kept whole here, because the Overview's cards draw on only some of them: the reused-run-id flag, the most recent runs, each pipeline and each incident rule have no card of their own.":
                _COUNTS_WHY,
            "Generated <time> by onetrace-console.":
                _COUNTS + ": the new page's footer",
        },
    },
    "run[forged]/case.html": {"new": {block: _GRAPH for block in (
        "1",
        "2",
        "A link shows which recorded output a stage read. It does not by itself prove that one stage caused the next.",
        "From",
        "Node",
        "Recorded order",
        "Recorded position",
        "Show as table",
        "Stage",
        "The execution graph",
        "To",
        "alpha",
        "beta",
        "recorded as a straight line (no graph recorded)",
    )}},
    "run[held-a]/case.html": {"new": {block: _GRAPH for block in (
        "1",
        "2",
        "A link shows which recorded output a stage read. It does not by itself prove that one stage caused the next.",
        "From",
        "Node",
        "Recorded order",
        "Recorded position",
        "Show as table",
        "Stage",
        "The execution graph",
        "To",
        "alpha",
        "beta",
        "recorded as a straight line (no graph recorded)",
    )}},
    "run[held-b]/case.html": {"new": {block: _GRAPH for block in (
        "1",
        "2",
        "A link shows which recorded output a stage read. It does not by itself prove that one stage caused the next.",
        "From",
        "Node",
        "Recorded order",
        "Recorded position",
        "Show as table",
        "Stage",
        "The execution graph",
        "To",
        "alpha",
        "beta",
        "recorded as a straight line (no graph recorded)",
    )}},
    "run[r11]/case.html": {"new": {block: _GRAPH for block in (
        "1",
        "2",
        "3",
        "A link shows which recorded output a stage read. It does not by itself prove that one stage caused the next.",
        "From",
        "Node",
        "Recorded order",
        "Recorded position",
        "Show as table",
        "Stage",
        "The execution graph",
        "To",
        "alpha",
        "join",
        "zeta",
    )}},
}

#: Canary 35c643b, re-vendored: drawn outside the console's frame, as these pages
#: are, the boundary section reads "Where the record stops", and an answer page with no answer step
#: draws no receipt disclosure. Generated from the measured difference by tooling, not typed.
_29DZ4 = "the boundary heading, and no empty receipt disclosure"
_29DZ4_PAGES: dict[str, dict[str, list[str]]] = {
    "run[forged]/answer.html": {"gone": ["The receipt for this step"]},
    "run[forged]/case.html": {"gone": ["Incidents"], "new": ["Where the record stops"]},
    "run[held-a]/answer.html": {"gone": ["The receipt for this step"]},
    "run[held-a]/case.html": {"gone": ["Incidents"], "new": ["Where the record stops"]},
    "run[held-b]/answer.html": {"gone": ["The receipt for this step"]},
    "run[held-b]/case.html": {"gone": ["Incidents"], "new": ["Where the record stops"]},
    "run[preview]/case.html": {"gone": ["Incidents"], "new": ["Where the record stops"]},
    "run[r11]/answer.html": {"gone": ["The receipt for this step"]},
    "run[r11]/case.html": {"gone": ["Incidents"], "new": ["Where the record stops"]},
}
for _page, _kinds in _29DZ4_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _29DZ4))

#: The run names: a run is named by its run id, then its short key, wherever a
#: page names it -- the compare page's pair, and every incident row. Generated from the
#: measured difference by tooling, not typed.
_29DZ4_NAMES = "a run named by its run id and short key"
_29DZ4_NAMES_PAGES: dict[str, dict[str, list[str]]] = {
    "diff[held-a,held-b]": {"gone": ["baseline <hex> against candidate <hex>"], "new": ["baseline nb2-base \u00b7 <hex> against candidate nb2-cand \u00b7 <hex>"]},
    "incidents-i-contradicts.html": {"gone": ["I-CONTRADICTS \u2014 run <hex>, field stdout[whole]"], "new": ["I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[whole]"]},
    "incidents-i-could-not-check.html": {"gone": ["I-COULD-NOT-CHECK \u2014 run <hex>, field topology_note"], "new": ["I-COULD-NOT-CHECK \u2014 run dag-r37-r \u00b7 <hex>, field topology_note"]},
    "incidents-i-runid-reused.html": {"gone": ["I-RUNID-REUSED \u2014 run <hex>, field flags[run_id reused]"], "new": ["I-RUNID-REUSED \u2014 run nb2-cand \u00b7 <hex>, field flags[run_id reused]"]},
    "incidents.html": {"gone": ["I-CONTRADICTS \u2014 run <hex>, field stdout[whole]", "I-COULD-NOT-CHECK \u2014 run <hex>, field topology_note", "I-RUNID-REUSED \u2014 run <hex>, field flags[run_id reused]"], "new": ["I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[whole]", "I-COULD-NOT-CHECK \u2014 run dag-r37-r \u00b7 <hex>, field topology_note", "I-RUNID-REUSED \u2014 run nb2-cand \u00b7 <hex>, field flags[run_id reused]"]},
    "run[forged]/answer.html": {"gone": ["I-CONTRADICTS \u2014 run <hex>, field stdout[whole]", "I-RUNID-REUSED \u2014 run <hex>, field flags[run_id reused]"], "new": ["I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[whole]", "I-RUNID-REUSED \u2014 run nb2-cand \u00b7 <hex>, field flags[run_id reused]"]},
    "run[forged]/case.html": {"gone": ["I-CONTRADICTS \u2014 run <hex>, field stdout[whole]", "I-RUNID-REUSED \u2014 run <hex>, field flags[run_id reused]"], "new": ["I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[whole]", "I-RUNID-REUSED \u2014 run nb2-cand \u00b7 <hex>, field flags[run_id reused]"]},
    "run[r11]/answer.html": {"gone": ["I-COULD-NOT-CHECK \u2014 run <hex>, field topology_note"], "new": ["I-COULD-NOT-CHECK \u2014 run dag-r37-r \u00b7 <hex>, field topology_note"]},
    "run[r11]/case.html": {"gone": ["I-COULD-NOT-CHECK \u2014 run <hex>, field topology_note"], "new": ["I-COULD-NOT-CHECK \u2014 run dag-r37-r \u00b7 <hex>, field topology_note"]},
}
for _page, _kinds in _29DZ4_NAMES_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _29DZ4_NAMES))
#: Board 5: the case page links the run receipt from its Policy section.
#: Generated from the measured difference by tooling, not typed.
_ITEM8 = "the case page links the run receipt (board 5)"
_ITEM8_PAGES: dict[str, dict[str, list[str]]] = {
    "run[forged]/case.html": {"new": ["The run receipt"]},
    "run[held-a]/case.html": {"new": ["The run receipt"]},
    "run[held-b]/case.html": {"new": ["The run receipt"]},
    "run[preview]/case.html": {"new": ["The run receipt"]},
    "run[r11]/case.html": {"new": ["The run receipt"]},
}
for _page, _kinds in _ITEM8_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _ITEM8))
#: Canary 75f13ac: the run ladder asks "Ran as approved". A
#: straight-line run reads its line alone; a graph run checked by 0.1.2 reads that the check that
#: ran can't say; the forged run's check rows can't be read one by one, so its plan rows
#: aren't. Generated from the measured difference by tooling, not typed.
_ITEM21 = "the run ladder's Ran as approved rung"
_ITEM21_PAGES: dict[str, dict[str, list[str]]] = {
    "run[forged]/case.html": {"new": ["Couldn't check · the check's rows can't be read one by one, so its plan rows aren't read", "Ran as approved"]},
    "run[held-a]/case.html": {"new": ["Ran as approved", "a straight-line run: there is no plan to compare"]},
    "run[held-b]/case.html": {"new": ["Ran as approved", "a straight-line run: there is no plan to compare"]},
    "run[preview]/case.html": {"new": ["Ran as approved", "a straight-line run: there is no plan to compare"]},
    "run[r11]/case.html": {"new": ["Couldn't check · the check that ran, onetrace-verify 0.1.2, has no plan row, so it can't say whether the run followed its plan", "Ran as approved"]},
}
for _page, _kinds in _ITEM21_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _ITEM21))
#: Before 0.2.0, the Overview's evidence gains
#: its anchoring rung, reading its placeholder; nothing on the page is gone or reworded.
_A1 = "the Overview's anchoring rung, item 8's placeholder until 0.2.0"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Committed by a known time", "not available until onetrace 0.2.0"], _A1))
#: Before 0.2.0, the Diff page gains its text-diff frame,
#: reading its placeholder; board 7 has no frame before 0.2.0. Nothing is
#: gone or reworded. Generated from the measured difference.
_A2 = "the text diff's frame, item 8's placeholder until 0.2.0"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["The text diff", "not available until onetrace 0.2.0"], _A2))
#: ---- Group C, re-measured after step 2 on the 0.2.0 development build. Every
#: line below was classified by cause by tooling, from the measured difference; none is regenerated wholesale.
#: Step 2: the check's command is `onetrace-verify MANIFEST.json` and a page
#: regenerates with `generate --cli`; each step's rows are the CLI's (graph-edge rows included); a run
#: holding artifacts/ whose outputs-required run passed reads "Records agree: Yes"; the r11 graph run's
#: plan rung reads yes. Generated from the measured difference by tooling, not typed.
_STEP2 = "step 2: the check is the installed onetrace-verify, its rows read from --json, outputs required where the run holds artifacts/"
_STEP2_PAGES: dict[str, dict[str, list[str]]] = {
    "executions-records-agree.html": {"new": ["2", "<time> \u2192 <time>", "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.", "alpha \u2192 beta", "nb2-base"]},
    "home.html + counts.html": {"gone": ["0 runs of 4 \u2014 whose records agree: the check held, with the run's output files required (--require-artifacts)"], "new": ["1 run of 4 \u2014 whose records agree: the check held, with the run's output files required (--require-artifacts)"]},
    "run[forged]/answer.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[forged]/case.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[held-a]/answer.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[held-a]/case.html": {"gone": ["Not checked \u00b7 The check that ran did not require the run's output files, so this page does not say the records agree.", "python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["Yes \u00b7 53 checks made \u2014 all hold.", "onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[held-b]/answer.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[held-b]/case.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[preview]/case.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[r11]/answer.html": {"gone": ["python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
    "run[r11]/case.html": {"gone": ["[PASS ] receipts/01-zeta.json: receipt format [PASS ] receipts/01-zeta.json: bytes are canonical [PASS ] receipts/01-zeta.json: required field 'format' [PASS ] receipts/01-zeta.json: required field 'run_id' [PASS ] receipts/01-zeta.json: required field 'stage' [PASS ] receipts/01-zeta.json: required field 'prev' [PASS ] receipts/01-zeta.json: required field 'time' [PASS ] receipts/01-zeta.json: required field 'coverage' [PASS ] receipts/01-zeta.json: required field 'emission' [PASS ] receipts/01-zeta.json: required field 'anchor' [PASS ] receipts/01-zeta.json: required field 'instrument' [PASS ] receipts/01-zeta.json: required field 'inputs' [PASS ] receipts/01-zeta.json: required field 'outputs' [PASS ] receipts/01-zeta.json: required field 'assertions' [PASS ] receipts/01-zeta.json: required field 'outcome' [PASS ] receipts/01-zeta.json: time.started carries its zone [PASS ] receipts/01-zeta.json: time.ended carries its zone [PASS ] receipts/01-zeta.json: instrument is named and pinned [PASS ] receipts/01-zeta.json: assertions name their constants [PASS ] receipts/01-zeta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-zeta.json: coverage declares completeness [PASS ] receipts/01-zeta.json: anchor state is declared, not absent [NOT-RUN] receipts/01-zeta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-zeta.json: digest matches the manifest [PASS ] receipts/01-zeta.json: chain link [PASS ] receipts/02-alpha.json: receipt format [PASS ] receipts/02-alpha.json: bytes are canonical [PASS ] receipts/02-alpha.json: required field 'format' [PASS ] receipts/02-alpha.json: required field 'run_id' [PASS ] receipts/02-alpha.json: required field 'stage' [PASS ] receipts/02-alpha.json: required field 'prev' [PASS ] receipts/02-alpha.json: required field 'time' [PASS ] receipts/02-alpha.json: required field 'coverage' [PASS ] receipts/02-alpha.json: required field 'emission' [PASS ] receipts/02-alpha.json: required field 'anchor' [PASS ] receipts/02-alpha.json: required field 'instrument' [PASS ] receipts/02-alpha.json: required field 'inputs' [PASS ] receipts/02-alpha.json: required field 'outputs' [PASS ] receipts/02-alpha.json: required field 'assertions' [PASS ] receipts/02-alpha.json: required field 'outcome' [PASS ] receipts/02-alpha.json: time.started carries its zone [PASS ] receipts/02-alpha.json: time.ended carries its zone [PASS ] receipts/02-alpha.json: instrument is named and pinned [PASS ] receipts/02-alpha.json: assertions name their constants [PASS ] receipts/02-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-alpha.json: coverage declares completeness [PASS ] receipts/02-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/02-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-alpha.json: digest matches the manifest [PASS ] receipts/02-alpha.json: chain link [PASS ] receipts/03-join.json: receipt format [PASS ] receipts/03-join.json: bytes are canonical [PASS ] receipts/03-join.json: required field 'format' [PASS ] receipts/03-join.json: required field 'run_id' [PASS ] receipts/03-join.json: required field 'stage' [PASS ] receipts/03-join.json: required field 'prev' [PASS ] receipts/03-join.json: required field 'time' [PASS ] receipts/03-join.json: required field 'coverage' [PASS ] receipts/03-join.json: required field 'emission' [PASS ] receipts/03-join.json: required field 'anchor' [PASS ] receipts/03-join.json: required field 'instrument' [PASS ] receipts/03-join.json: required field 'inputs' [PASS ] receipts/03-join.json: required field 'outputs' [PASS ] receipts/03-join.json: required field 'assertions' [PASS ] receipts/03-join.json: required field 'outcome' [PASS ] receipts/03-join.json: time.started carries its zone [PASS ] receipts/03-join.json: time.ended carries its zone [PASS ] receipts/03-join.json: instrument is named and pinned [PASS ] receipts/03-join.json: inputs/receipt:zeta declares a trust class [PASS ] receipts/03-join.json: inputs/receipt:alpha declares a trust class [PASS ] receipts/03-join.json: assertions name their constants [PASS ] receipts/03-join.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/03-join.json: coverage declares completeness [PASS ] receipts/03-join.json: 'complete' is consistent with the stage lists [PASS ] receipts/03-join.json: anchor state is declared, not absent [NOT-RUN] receipts/03-join.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/03-join.json: digest matches the manifest [PASS ] receipts/03-join.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt 76 pass, 0 fail, 4 not-run -> PASS", "python -m viewer generate RUN_FOLDER --verifier <verifier> --out OUT_FOLDER", "python3 <verifier> MANIFEST.json"], "new": ["Yes \u00b7 the check's plan row and its edges row both passed, and the run itself verified", "[PASS ] receipts/01-zeta.json: receipt format [PASS ] receipts/01-zeta.json: bytes are canonical [PASS ] receipts/01-zeta.json: required field 'format' [PASS ] receipts/01-zeta.json: required field 'run_id' [PASS ] receipts/01-zeta.json: required field 'stage' [PASS ] receipts/01-zeta.json: required field 'prev' [PASS ] receipts/01-zeta.json: required field 'time' [PASS ] receipts/01-zeta.json: required field 'coverage' [PASS ] receipts/01-zeta.json: required field 'emission' [PASS ] receipts/01-zeta.json: required field 'anchor' [PASS ] receipts/01-zeta.json: required field 'instrument' [PASS ] receipts/01-zeta.json: required field 'inputs' [PASS ] receipts/01-zeta.json: required field 'outputs' [PASS ] receipts/01-zeta.json: required field 'assertions' [PASS ] receipts/01-zeta.json: required field 'outcome' [PASS ] receipts/01-zeta.json: time.started carries its zone [PASS ] receipts/01-zeta.json: time.ended carries its zone [PASS ] receipts/01-zeta.json: instrument is named and pinned [PASS ] receipts/01-zeta.json: assertions name their constants [PASS ] receipts/01-zeta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-zeta.json: coverage declares completeness [PASS ] receipts/01-zeta.json: anchor state is declared, not absent [NOT-RUN] receipts/01-zeta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-zeta.json: digest matches the manifest [PASS ] receipts/01-zeta.json: chain link [PASS ] receipts/02-alpha.json: receipt format [PASS ] receipts/02-alpha.json: bytes are canonical [PASS ] receipts/02-alpha.json: required field 'format' [PASS ] receipts/02-alpha.json: required field 'run_id' [PASS ] receipts/02-alpha.json: required field 'stage' [PASS ] receipts/02-alpha.json: required field 'prev' [PASS ] receipts/02-alpha.json: required field 'time' [PASS ] receipts/02-alpha.json: required field 'coverage' [PASS ] receipts/02-alpha.json: required field 'emission' [PASS ] receipts/02-alpha.json: required field 'anchor' [PASS ] receipts/02-alpha.json: required field 'instrument' [PASS ] receipts/02-alpha.json: required field 'inputs' [PASS ] receipts/02-alpha.json: required field 'outputs' [PASS ] receipts/02-alpha.json: required field 'assertions' [PASS ] receipts/02-alpha.json: required field 'outcome' [PASS ] receipts/02-alpha.json: time.started carries its zone [PASS ] receipts/02-alpha.json: time.ended carries its zone [PASS ] receipts/02-alpha.json: instrument is named and pinned [PASS ] receipts/02-alpha.json: assertions name their constants [PASS ] receipts/02-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-alpha.json: coverage declares completeness [PASS ] receipts/02-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/02-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-alpha.json: digest matches the manifest [PASS ] receipts/02-alpha.json: chain link [PASS ] receipts/03-join.json: receipt format [PASS ] receipts/03-join.json: bytes are canonical [PASS ] receipts/03-join.json: required field 'format' [PASS ] receipts/03-join.json: required field 'run_id' [PASS ] receipts/03-join.json: required field 'stage' [PASS ] receipts/03-join.json: required field 'prev' [PASS ] receipts/03-join.json: required field 'time' [PASS ] receipts/03-join.json: required field 'coverage' [PASS ] receipts/03-join.json: required field 'emission' [PASS ] receipts/03-join.json: required field 'anchor' [PASS ] receipts/03-join.json: required field 'instrument' [PASS ] receipts/03-join.json: required field 'inputs' [PASS ] receipts/03-join.json: required field 'outputs' [PASS ] receipts/03-join.json: required field 'assertions' [PASS ] receipts/03-join.json: required field 'outcome' [PASS ] receipts/03-join.json: time.started carries its zone [PASS ] receipts/03-join.json: time.ended carries its zone [PASS ] receipts/03-join.json: instrument is named and pinned [PASS ] receipts/03-join.json: inputs/receipt:zeta declares a trust class [PASS ] receipts/03-join.json: inputs/receipt:alpha declares a trust class [PASS ] receipts/03-join.json: assertions name their constants [PASS ] receipts/03-join.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/03-join.json: coverage declares completeness [PASS ] receipts/03-join.json: 'complete' is consistent with the stage lists [PASS ] receipts/03-join.json: anchor state is declared, not absent [NOT-RUN] receipts/03-join.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/03-join.json: digest matches the manifest [PASS ] receipts/03-join.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt [PASS ] edges conform to declared_edges [PASS ] edges equal the edges derived from the receipts 78 pass, 0 fail, 4 not-run -> PASS", "onetrace-verify MANIFEST.json", "python -m viewer generate RUN_FOLDER --cli --out OUT_FOLDER"]},
}
for _page, _kinds in _STEP2_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _STEP2))
#: The 0.2.0 verifier FAILs the forged output digest (`digest is sha256: and 64
#: lower-case hex`), its rows read line by line, the run contradicts and the SDK refuses to compare it
#: ("does not verify", exit 3); every list, count and incident follows. The SDK's own text prints the
#: refused candidate's run id as None (reported to the SDK's maintainers). Generated from the measured
#: difference by tooling, not typed.
_B2_0_2_0 = "B2: the 0.2.0 verifier refuses the forged digest, so nb2-cand contradicts and the SDK refuses to compare it"
_B2_0_2_0_PAGES: dict[str, dict[str, list[str]]] = {
    "diff[held-a,held-b]": {"gone": ["#", "1", "2", "First difference", "First difference: stage 1 \u00b7 alpha.", "No recorded setting of it differs. Its output differs.", "No recorded settings or code digest at stage 1 \u00b7 alpha differs between the two runs, so there is no recorded change to look for elsewhere.", "No stage comes before it.", "Of the 1 stage after it, 0 differ, 1 is the same again.", "Same again", "The first difference is at stage 1 \u00b7 alpha. No smaller set was reported.", "Why stage 1 \u00b7 alpha's output differs is not established by this evidence.", "alpha", "baseline", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) nb2-cand (run) diff: diverged stage baseline candidate verdict -------------------------------------------------------------------- alpha <hex> ab\\u000d\\u00 FIRST DIFFERENCE beta <hex> <hex> reconverged first difference stage 1, 'alpha' comparisons performed 2; stages identical before the first difference 0 carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) nb2-cand (run) localize: diverged stage baseline candidate verdict -------------------------------------------------------------------- alpha <hex> ab\\u000d\\u00 FIRST DIFFERENCE beta <hex> <hex> reconverged first difference stage 1, 'alpha' comparisons performed 2; stages identical before the first difference 0 CAUSE at stage 1, 'alpha' instrument instrument unchanged config <hex> -> <hex> neither instrument nor config differs at the first difference; the difference is on the outputs upstream every stage before this one carries an identical output digest BLAST RADIUS COULD NOT CHECK \u2014 no chunk index found by digest among both runs' declared outputs carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "beta", "candidate", "diff: diverged (exit 1)", "localize: diverged (exit 1)", "no recorded setting differs", "result", "settings", "sha256:<hex>", "sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000", "stage"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "The report names no localized set. That is what it says, not a gap in this page.", "This console can't read a first difference from this comparison's diff report, so it doesn't look for other runs with the same change.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "all incidents", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) None (run) diff: refused \u2014 does not verify: (the candidate run's folder) REFUSED \u2014 candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) None (run) localize: refused \u2014 does not verify: (the candidate run's folder) REFUSED \u2014 candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "diff: refused \u2014 does not verify: (the candidate run's folder) (exit 3)", "localize: refused \u2014 does not verify: (the candidate run's folder) (exit 3)", "the report it came from"]},
    "executions-changed-vs-baseline.html": {"gone": ["2", "<time> \u2192 <time>", "alpha \u2192 beta", "nb2-cand"], "new": ["Runs in this list: none of the 4 stored. Nothing is summarised across runs on this page."]},
    "executions-contradicts.html": {"new": ["2", "<time> \u2192 <time>", "Runs in this list: 2 of 4 stored, and this page lists all 2. Nothing is summarised across runs on this page.", "alpha \u2192 beta", "nb2-cand"]},
    "executions-holds.html": {"gone": ["2", "<time> \u2192 <time>", "alpha \u2192 beta", "nb2-cand"], "new": ["Runs in this list: 2 of 4 stored, and this page lists all 2. Nothing is summarised across runs on this page."]},
    "home.html + counts.html": {"gone": ["1 incident of 3 raised from stored runs", "1 of 4", "1 run of 4 \u2014 changed vs baseline, each the candidate of a stored comparison that found a first difference", "1 run of 4 \u2014 runs raising I-CONTRADICTS", "1 run of 4 \u2014 verdict: contradicts", "3 incidents raised, from 2 of 4 runs", "3 of 4", "3 runs of 4 \u2014 verdict: holds", "Changed vs baseline \u00b7 nb2-cand \u00b7 <time>", "First difference \u00b7 stage 1 \u00b7 alpha", "verdict: holds"], "new": ["0 runs of 4 \u2014 changed vs baseline, each the candidate of a stored comparison that found a first difference", "1 incident of 4 raised from stored runs", "2 incidents of 4 raised from stored runs", "2 of 4", "2 runs of 4 \u2014 runs raising I-CONTRADICTS", "2 runs of 4 \u2014 verdict: contradicts", "2 runs of 4 \u2014 verdict: holds", "4 incidents raised, from 3 of 4 runs", "Contradicts itself \u00b7 nb2-cand \u00b7 <time>", "Couldn't check", "verdict: contradicts"]},
    "incidents-i-contradicts.html": {"gone": ["I-CONTRADICTS \u2014 1 run of 4", "The check's rows could not be read line by line; shown as written, escaped.", "[PASS ] receipts/01-alpha.json: receipt format\\u000a[PASS ] receipts/01-alpha.json: bytes are canonical\\u000a[PASS ] receipts/01-alpha.json: required field 'format'\\u000a[PASS ] receipts/01-alpha.json: required field 'run_id'\\u000a[PASS ] receipts/01-alpha.json: required field 'stage'\\u000a[PASS ] receipts/01-alpha.json: required field 'prev'\\u000a[PASS ] receipts/01-alpha.json: required field 'time'\\u000a[PASS ] receipts/01-alpha.json: required field 'coverage'\\u000a[PASS ] receipts/01-alpha.json: required field 'emission'\\u000a[PASS ] receipts/01-alpha.json: required field 'anchor'\\u000a[PASS ] receipts/01-alpha.json: required field 'instrument'\\u000a[PASS ] receipts/01-alpha.json: required field 'inputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'outputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'assertions'\\u000a[PASS ] receipts/01-alpha.json: required field 'outcome'\\u000a[PASS ] receipts/01-alpha.json: time.started carries its zone\\u000a[PASS ] receipts/01-alpha.json: time.ended carries its zone\\u000a[PASS ] receipts/01-alpha.json: instrument is named and pinned\\u000a[PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class\\u000a[PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/01-alpha.json: coverage declares completeness\\u000a[PASS ] receipts/01-alpha.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/01-alpha.json: digest matches the manifest\\u000a[PASS ] receipts/01-alpha.json: chain link\\u000a[FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>\\u000a[PASS ] receipts/02-beta.json: receipt format\\u000a[PASS ] receipts/02-beta.json: bytes are canonical\\u000a[PASS ] receipts/02-beta.json: required field 'format'\\u000a[PASS ] receipts/02-beta.json: required field 'run_id'\\u000a[PASS ] receipts/02-beta.json: required field 'stage'\\u000a[PASS ] receipts/02-beta.json: required field 'prev'\\u000a[PASS ] receipts/02-beta.json: required field 'time'\\u000a[PASS ] receipts/02-beta.json: required field 'coverage'\\u000a[PASS ] receipts/02-beta.json: required field 'emission'\\u000a[PASS ] receipts/02-beta.json: required field 'anchor'\\u000a[PASS ] receipts/02-beta.json: required field 'instrument'\\u000a[PASS ] receipts/02-beta.json: required field 'inputs'\\u000a[PASS ] receipts/02-beta.json: required field 'outputs'\\u000a[PASS ] receipts/02-beta.json: required field 'assertions'\\u000a[PASS ] receipts/02-beta.json: required field 'outcome'\\u000a[PASS ] receipts/02-beta.json: time.started carries its zone\\u000a[PASS ] receipts/02-beta.json: time.ended carries its zone\\u000a[PASS ] receipts/02-beta.json: instrument is named and pinned\\u000a[PASS ] receipts/02-beta.json: inputs/a.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outputs/b.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/02-beta.json: coverage declares completeness\\u000a[PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists\\u000a[PASS ] receipts/02-beta.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/02-beta.json: digest matches the manifest\\u000a[PASS ] receipts/02-beta.json: chain link\\u000a[PASS ] receipts/02-beta.json: output artifact 'b.json' matches\\u000a[PASS ] manifest: chain head matches the last receipt\\u000a\\u000a52 pass, 1 fail, 2 not-run -> FAIL\\u000a"], "new": ["I-CONTRADICTS \u2014 2 runs of 4", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "the report it came from"]},
    "incidents.html": {"gone": ["I-CONTRADICTS \u2014 1 run of 4", "The check's rows could not be read line by line; shown as written, escaped.", "[PASS ] receipts/01-alpha.json: receipt format\\u000a[PASS ] receipts/01-alpha.json: bytes are canonical\\u000a[PASS ] receipts/01-alpha.json: required field 'format'\\u000a[PASS ] receipts/01-alpha.json: required field 'run_id'\\u000a[PASS ] receipts/01-alpha.json: required field 'stage'\\u000a[PASS ] receipts/01-alpha.json: required field 'prev'\\u000a[PASS ] receipts/01-alpha.json: required field 'time'\\u000a[PASS ] receipts/01-alpha.json: required field 'coverage'\\u000a[PASS ] receipts/01-alpha.json: required field 'emission'\\u000a[PASS ] receipts/01-alpha.json: required field 'anchor'\\u000a[PASS ] receipts/01-alpha.json: required field 'instrument'\\u000a[PASS ] receipts/01-alpha.json: required field 'inputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'outputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'assertions'\\u000a[PASS ] receipts/01-alpha.json: required field 'outcome'\\u000a[PASS ] receipts/01-alpha.json: time.started carries its zone\\u000a[PASS ] receipts/01-alpha.json: time.ended carries its zone\\u000a[PASS ] receipts/01-alpha.json: instrument is named and pinned\\u000a[PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class\\u000a[PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/01-alpha.json: coverage declares completeness\\u000a[PASS ] receipts/01-alpha.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/01-alpha.json: digest matches the manifest\\u000a[PASS ] receipts/01-alpha.json: chain link\\u000a[FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>\\u000a[PASS ] receipts/02-beta.json: receipt format\\u000a[PASS ] receipts/02-beta.json: bytes are canonical\\u000a[PASS ] receipts/02-beta.json: required field 'format'\\u000a[PASS ] receipts/02-beta.json: required field 'run_id'\\u000a[PASS ] receipts/02-beta.json: required field 'stage'\\u000a[PASS ] receipts/02-beta.json: required field 'prev'\\u000a[PASS ] receipts/02-beta.json: required field 'time'\\u000a[PASS ] receipts/02-beta.json: required field 'coverage'\\u000a[PASS ] receipts/02-beta.json: required field 'emission'\\u000a[PASS ] receipts/02-beta.json: required field 'anchor'\\u000a[PASS ] receipts/02-beta.json: required field 'instrument'\\u000a[PASS ] receipts/02-beta.json: required field 'inputs'\\u000a[PASS ] receipts/02-beta.json: required field 'outputs'\\u000a[PASS ] receipts/02-beta.json: required field 'assertions'\\u000a[PASS ] receipts/02-beta.json: required field 'outcome'\\u000a[PASS ] receipts/02-beta.json: time.started carries its zone\\u000a[PASS ] receipts/02-beta.json: time.ended carries its zone\\u000a[PASS ] receipts/02-beta.json: instrument is named and pinned\\u000a[PASS ] receipts/02-beta.json: inputs/a.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outputs/b.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/02-beta.json: coverage declares completeness\\u000a[PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists\\u000a[PASS ] receipts/02-beta.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/02-beta.json: digest matches the manifest\\u000a[PASS ] receipts/02-beta.json: chain link\\u000a[PASS ] receipts/02-beta.json: output artifact 'b.json' matches\\u000a[PASS ] manifest: chain head matches the last receipt\\u000a\\u000a52 pass, 1 fail, 2 not-run -> FAIL\\u000a"], "new": ["I-CONTRADICTS \u2014 2 runs of 4", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "the report it came from"]},
    "run[forged]/answer.html": {"gone": ["2 of the 3 incidents raised from stored runs when this page was generated came from this page's reports", "The check's rows could not be read line by line; shown as written, escaped.", "This answer's trail was checked on <time> \u2014 the check failed. Its rows could not be read one by one, so no step below is named.", "[PASS ] receipts/01-alpha.json: receipt format\\u000a[PASS ] receipts/01-alpha.json: bytes are canonical\\u000a[PASS ] receipts/01-alpha.json: required field 'format'\\u000a[PASS ] receipts/01-alpha.json: required field 'run_id'\\u000a[PASS ] receipts/01-alpha.json: required field 'stage'\\u000a[PASS ] receipts/01-alpha.json: required field 'prev'\\u000a[PASS ] receipts/01-alpha.json: required field 'time'\\u000a[PASS ] receipts/01-alpha.json: required field 'coverage'\\u000a[PASS ] receipts/01-alpha.json: required field 'emission'\\u000a[PASS ] receipts/01-alpha.json: required field 'anchor'\\u000a[PASS ] receipts/01-alpha.json: required field 'instrument'\\u000a[PASS ] receipts/01-alpha.json: required field 'inputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'outputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'assertions'\\u000a[PASS ] receipts/01-alpha.json: required field 'outcome'\\u000a[PASS ] receipts/01-alpha.json: time.started carries its zone\\u000a[PASS ] receipts/01-alpha.json: time.ended carries its zone\\u000a[PASS ] receipts/01-alpha.json: instrument is named and pinned\\u000a[PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class\\u000a[PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/01-alpha.json: coverage declares completeness\\u000a[PASS ] receipts/01-alpha.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/01-alpha.json: digest matches the manifest\\u000a[PASS ] receipts/01-alpha.json: chain link\\u000a[FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>\\u000a[PASS ] receipts/02-beta.json: receipt format\\u000a[PASS ] receipts/02-beta.json: bytes are canonical\\u000a[PASS ] receipts/02-beta.json: required field 'format'\\u000a[PASS ] receipts/02-beta.json: required field 'run_id'\\u000a[PASS ] receipts/02-beta.json: required field 'stage'\\u000a[PASS ] receipts/02-beta.json: required field 'prev'\\u000a[PASS ] receipts/02-beta.json: required field 'time'\\u000a[PASS ] receipts/02-beta.json: required field 'coverage'\\u000a[PASS ] receipts/02-beta.json: required field 'emission'\\u000a[PASS ] receipts/02-beta.json: required field 'anchor'\\u000a[PASS ] receipts/02-beta.json: required field 'instrument'\\u000a[PASS ] receipts/02-beta.json: required field 'inputs'\\u000a[PASS ] receipts/02-beta.json: required field 'outputs'\\u000a[PASS ] receipts/02-beta.json: required field 'assertions'\\u000a[PASS ] receipts/02-beta.json: required field 'outcome'\\u000a[PASS ] receipts/02-beta.json: time.started carries its zone\\u000a[PASS ] receipts/02-beta.json: time.ended carries its zone\\u000a[PASS ] receipts/02-beta.json: instrument is named and pinned\\u000a[PASS ] receipts/02-beta.json: inputs/a.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outputs/b.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/02-beta.json: coverage declares completeness\\u000a[PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists\\u000a[PASS ] receipts/02-beta.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/02-beta.json: digest matches the manifest\\u000a[PASS ] receipts/02-beta.json: chain link\\u000a[PASS ] receipts/02-beta.json: output artifact 'b.json' matches\\u000a[PASS ] manifest: chain head matches the last receipt\\u000a\\u000a52 pass, 1 fail, 2 not-run -> FAIL\\u000a"], "new": ["2 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "Checked \u2014 and the record contradicts itself here: output artifact 'a.json' matches \u2014 expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>.", "Checked \u2014 it holds.", "Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "The check's own words", "This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "[PASS ] receipts/02-beta.json: receipt format [PASS ] receipts/02-beta.json: bytes are canonical [PASS ] receipts/02-beta.json: required field 'format' [PASS ] receipts/02-beta.json: required field 'run_id' [PASS ] receipts/02-beta.json: required field 'stage' [PASS ] receipts/02-beta.json: required field 'prev' [PASS ] receipts/02-beta.json: required field 'time' [PASS ] receipts/02-beta.json: required field 'coverage' [PASS ] receipts/02-beta.json: required field 'emission' [PASS ] receipts/02-beta.json: required field 'anchor' [PASS ] receipts/02-beta.json: required field 'instrument' [PASS ] receipts/02-beta.json: required field 'inputs' [PASS ] receipts/02-beta.json: required field 'outputs' [PASS ] receipts/02-beta.json: required field 'assertions' [PASS ] receipts/02-beta.json: required field 'outcome' [PASS ] receipts/02-beta.json: time.started carries its zone [PASS ] receipts/02-beta.json: time.ended carries its zone [PASS ] receipts/02-beta.json: instrument is named and pinned [PASS ] receipts/02-beta.json: inputs/a.json declares a trust class [PASS ] receipts/02-beta.json: outputs/b.json declares a trust class [PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-beta.json: coverage declares completeness [PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-beta.json: anchor state is declared, not absent [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-beta.json: digest matches the manifest [PASS ] receipts/02-beta.json: chain link [PASS ] receipts/02-beta.json: output artifact 'b.json' matches"]},
    "run[forged]/case.html": {"gone": ["2 of the 3 incidents raised from stored runs when this page was generated came from this page's reports", "No \u00b7 This answer's trail was checked on <time> \u2014 the check failed. Its rows could not be read one by one, so no step below is named.", "The check's rows could not be read line by line; shown as written, escaped.", "This answer's trail was checked on <time> \u2014 the check failed. Its rows could not be read one by one, so no step below is named.", "[PASS ] receipts/01-alpha.json: receipt format\\u000a[PASS ] receipts/01-alpha.json: bytes are canonical\\u000a[PASS ] receipts/01-alpha.json: required field 'format'\\u000a[PASS ] receipts/01-alpha.json: required field 'run_id'\\u000a[PASS ] receipts/01-alpha.json: required field 'stage'\\u000a[PASS ] receipts/01-alpha.json: required field 'prev'\\u000a[PASS ] receipts/01-alpha.json: required field 'time'\\u000a[PASS ] receipts/01-alpha.json: required field 'coverage'\\u000a[PASS ] receipts/01-alpha.json: required field 'emission'\\u000a[PASS ] receipts/01-alpha.json: required field 'anchor'\\u000a[PASS ] receipts/01-alpha.json: required field 'instrument'\\u000a[PASS ] receipts/01-alpha.json: required field 'inputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'outputs'\\u000a[PASS ] receipts/01-alpha.json: required field 'assertions'\\u000a[PASS ] receipts/01-alpha.json: required field 'outcome'\\u000a[PASS ] receipts/01-alpha.json: time.started carries its zone\\u000a[PASS ] receipts/01-alpha.json: time.ended carries its zone\\u000a[PASS ] receipts/01-alpha.json: instrument is named and pinned\\u000a[PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class\\u000a[PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/01-alpha.json: coverage declares completeness\\u000a[PASS ] receipts/01-alpha.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/01-alpha.json: digest matches the manifest\\u000a[PASS ] receipts/01-alpha.json: chain link\\u000a[FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>\\u000a[PASS ] receipts/02-beta.json: receipt format\\u000a[PASS ] receipts/02-beta.json: bytes are canonical\\u000a[PASS ] receipts/02-beta.json: required field 'format'\\u000a[PASS ] receipts/02-beta.json: required field 'run_id'\\u000a[PASS ] receipts/02-beta.json: required field 'stage'\\u000a[PASS ] receipts/02-beta.json: required field 'prev'\\u000a[PASS ] receipts/02-beta.json: required field 'time'\\u000a[PASS ] receipts/02-beta.json: required field 'coverage'\\u000a[PASS ] receipts/02-beta.json: required field 'emission'\\u000a[PASS ] receipts/02-beta.json: required field 'anchor'\\u000a[PASS ] receipts/02-beta.json: required field 'instrument'\\u000a[PASS ] receipts/02-beta.json: required field 'inputs'\\u000a[PASS ] receipts/02-beta.json: required field 'outputs'\\u000a[PASS ] receipts/02-beta.json: required field 'assertions'\\u000a[PASS ] receipts/02-beta.json: required field 'outcome'\\u000a[PASS ] receipts/02-beta.json: time.started carries its zone\\u000a[PASS ] receipts/02-beta.json: time.ended carries its zone\\u000a[PASS ] receipts/02-beta.json: instrument is named and pinned\\u000a[PASS ] receipts/02-beta.json: inputs/a.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outputs/b.json declares a trust class\\u000a[PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused']\\u000a[PASS ] receipts/02-beta.json: coverage declares completeness\\u000a[PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists\\u000a[PASS ] receipts/02-beta.json: anchor state is declared, not absent\\u000a[NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality\\u000a[PASS ] receipts/02-beta.json: digest matches the manifest\\u000a[PASS ] receipts/02-beta.json: chain link\\u000a[PASS ] receipts/02-beta.json: output artifact 'b.json' matches\\u000a[PASS ] manifest: chain head matches the last receipt\\u000a\\u000a52 pass, 1 fail, 2 not-run -> FAIL\\u000a", "\u2014"], "new": ["2 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "Checked \u2014 and the record contradicts itself here: output artifact 'a.json' matches \u2014 expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>.", "Checked \u2014 it holds.", "Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "No \u00b7 This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "The check's own words", "The list of steps \u2014 1 check made \u2014 it holds.", "This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex>", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link [FAIL ] receipts/01-alpha.json: output artifact 'a.json' matches -- expected sha256:ab\\u000aFORGED\\u0009ROW\\u000a0000000000000000000000000000000000000000, found sha256:<hex> [PASS ] receipts/02-beta.json: receipt format [PASS ] receipts/02-beta.json: bytes are canonical [PASS ] receipts/02-beta.json: required field 'format' [PASS ] receipts/02-beta.json: required field 'run_id' [PASS ] receipts/02-beta.json: required field 'stage' [PASS ] receipts/02-beta.json: required field 'prev' [PASS ] receipts/02-beta.json: required field 'time' [PASS ] receipts/02-beta.json: required field 'coverage' [PASS ] receipts/02-beta.json: required field 'emission' [PASS ] receipts/02-beta.json: required field 'anchor' [PASS ] receipts/02-beta.json: required field 'instrument' [PASS ] receipts/02-beta.json: required field 'inputs' [PASS ] receipts/02-beta.json: required field 'outputs' [PASS ] receipts/02-beta.json: required field 'assertions' [PASS ] receipts/02-beta.json: required field 'outcome' [PASS ] receipts/02-beta.json: time.started carries its zone [PASS ] receipts/02-beta.json: time.ended carries its zone [PASS ] receipts/02-beta.json: instrument is named and pinned [PASS ] receipts/02-beta.json: inputs/a.json declares a trust class [PASS ] receipts/02-beta.json: outputs/b.json declares a trust class [PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-beta.json: coverage declares completeness [PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-beta.json: anchor state is declared, not absent [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-beta.json: digest matches the manifest [PASS ] receipts/02-beta.json: chain link [PASS ] receipts/02-beta.json: output artifact 'b.json' matches [PASS ] manifest: chain head matches the last receipt 52 pass, 2 fail, 2 not-run -> FAIL", "[PASS ] receipts/02-beta.json: receipt format [PASS ] receipts/02-beta.json: bytes are canonical [PASS ] receipts/02-beta.json: required field 'format' [PASS ] receipts/02-beta.json: required field 'run_id' [PASS ] receipts/02-beta.json: required field 'stage' [PASS ] receipts/02-beta.json: required field 'prev' [PASS ] receipts/02-beta.json: required field 'time' [PASS ] receipts/02-beta.json: required field 'coverage' [PASS ] receipts/02-beta.json: required field 'emission' [PASS ] receipts/02-beta.json: required field 'anchor' [PASS ] receipts/02-beta.json: required field 'instrument' [PASS ] receipts/02-beta.json: required field 'inputs' [PASS ] receipts/02-beta.json: required field 'outputs' [PASS ] receipts/02-beta.json: required field 'assertions' [PASS ] receipts/02-beta.json: required field 'outcome' [PASS ] receipts/02-beta.json: time.started carries its zone [PASS ] receipts/02-beta.json: time.ended carries its zone [PASS ] receipts/02-beta.json: instrument is named and pinned [PASS ] receipts/02-beta.json: inputs/a.json declares a trust class [PASS ] receipts/02-beta.json: outputs/b.json declares a trust class [PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-beta.json: coverage declares completeness [PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-beta.json: anchor state is declared, not absent [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-beta.json: digest matches the manifest [PASS ] receipts/02-beta.json: chain link [PASS ] receipts/02-beta.json: output artifact 'b.json' matches", "a straight-line run: there is no plan to compare", "step 1 of 2 \u00b7 alpha \u2014 24 checks made \u2014 all hold.", "step 1 of 2 \u00b7 alpha \u2014 Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "step 1 of 2 \u00b7 alpha \u2014 Checked \u2014 and the record contradicts itself here: output artifact 'a.json' matches \u2014 expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>.", "step 1 of 2 \u00b7 alpha \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 2 of 2 \u00b7 beta \u2014 27 checks made \u2014 all hold.", "step 2 of 2 \u00b7 beta \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."]},
    "run[held-b]/answer.html": {"gone": ["Checked \u2014 it holds.", "This answer's trail was checked on <time> \u2014 each check that ran held.", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link", "all incidents", "the report it came from"]},
    "run[held-b]/case.html": {"gone": ["Checked \u2014 it holds.", "Not checked \u00b7 The check that ran did not require the run's output files, so this page does not say the records agree.", "This answer's trail was checked on <time> \u2014 each check that ran held.", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link [PASS ] receipts/02-beta.json: receipt format [PASS ] receipts/02-beta.json: bytes are canonical [PASS ] receipts/02-beta.json: required field 'format' [PASS ] receipts/02-beta.json: required field 'run_id' [PASS ] receipts/02-beta.json: required field 'stage' [PASS ] receipts/02-beta.json: required field 'prev' [PASS ] receipts/02-beta.json: required field 'time' [PASS ] receipts/02-beta.json: required field 'coverage' [PASS ] receipts/02-beta.json: required field 'emission' [PASS ] receipts/02-beta.json: required field 'anchor' [PASS ] receipts/02-beta.json: required field 'instrument' [PASS ] receipts/02-beta.json: required field 'inputs' [PASS ] receipts/02-beta.json: required field 'outputs' [PASS ] receipts/02-beta.json: required field 'assertions' [PASS ] receipts/02-beta.json: required field 'outcome' [PASS ] receipts/02-beta.json: time.started carries its zone [PASS ] receipts/02-beta.json: time.ended carries its zone [PASS ] receipts/02-beta.json: instrument is named and pinned [PASS ] receipts/02-beta.json: inputs/a.json declares a trust class [PASS ] receipts/02-beta.json: outputs/b.json declares a trust class [PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-beta.json: coverage declares completeness [PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-beta.json: anchor state is declared, not absent [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-beta.json: digest matches the manifest [PASS ] receipts/02-beta.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt 51 pass, 0 fail, 3 not-run -> PASS"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "No \u00b7 This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "This answer's trail was checked on <time> \u2014 the record contradicts itself at step 1.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link", "[PASS ] receipts/01-alpha.json: receipt format [PASS ] receipts/01-alpha.json: bytes are canonical [PASS ] receipts/01-alpha.json: required field 'format' [PASS ] receipts/01-alpha.json: required field 'run_id' [PASS ] receipts/01-alpha.json: required field 'stage' [PASS ] receipts/01-alpha.json: required field 'prev' [PASS ] receipts/01-alpha.json: required field 'time' [PASS ] receipts/01-alpha.json: required field 'coverage' [PASS ] receipts/01-alpha.json: required field 'emission' [PASS ] receipts/01-alpha.json: required field 'anchor' [PASS ] receipts/01-alpha.json: required field 'instrument' [PASS ] receipts/01-alpha.json: required field 'inputs' [PASS ] receipts/01-alpha.json: required field 'outputs' [PASS ] receipts/01-alpha.json: required field 'assertions' [PASS ] receipts/01-alpha.json: required field 'outcome' [PASS ] receipts/01-alpha.json: time.started carries its zone [PASS ] receipts/01-alpha.json: time.ended carries its zone [PASS ] receipts/01-alpha.json: instrument is named and pinned [PASS ] receipts/01-alpha.json: outputs/a.json declares a trust class [PASS ] receipts/01-alpha.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-alpha.json: coverage declares completeness [PASS ] receipts/01-alpha.json: anchor state is declared, not absent [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' [PASS ] receipts/01-alpha.json: digest matches the manifest [PASS ] receipts/01-alpha.json: chain link [PASS ] receipts/02-beta.json: receipt format [PASS ] receipts/02-beta.json: bytes are canonical [PASS ] receipts/02-beta.json: required field 'format' [PASS ] receipts/02-beta.json: required field 'run_id' [PASS ] receipts/02-beta.json: required field 'stage' [PASS ] receipts/02-beta.json: required field 'prev' [PASS ] receipts/02-beta.json: required field 'time' [PASS ] receipts/02-beta.json: required field 'coverage' [PASS ] receipts/02-beta.json: required field 'emission' [PASS ] receipts/02-beta.json: required field 'anchor' [PASS ] receipts/02-beta.json: required field 'instrument' [PASS ] receipts/02-beta.json: required field 'inputs' [PASS ] receipts/02-beta.json: required field 'outputs' [PASS ] receipts/02-beta.json: required field 'assertions' [PASS ] receipts/02-beta.json: required field 'outcome' [PASS ] receipts/02-beta.json: time.started carries its zone [PASS ] receipts/02-beta.json: time.ended carries its zone [PASS ] receipts/02-beta.json: instrument is named and pinned [PASS ] receipts/02-beta.json: inputs/a.json declares a trust class [PASS ] receipts/02-beta.json: outputs/b.json declares a trust class [PASS ] receipts/02-beta.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-beta.json: coverage declares completeness [PASS ] receipts/02-beta.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-beta.json: anchor state is declared, not absent [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-beta.json: digest matches the manifest [PASS ] receipts/02-beta.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt 51 pass, 1 fail, 3 not-run -> FAIL", "all incidents", "step 1 of 2 \u00b7 alpha \u2014 Checked \u2014 and the record contradicts itself here: digest is sha256: and 64 lower-case hex \u2014 outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'.", "the report it came from"]},
    "run[r11]/answer.html": {"gone": ["1 of the 3 incidents raised from stored runs when this page was generated came from this page's reports"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports"]},
    "run[r11]/case.html": {"gone": ["1 of the 3 incidents raised from stored runs when this page was generated came from this page's reports"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports"]},
}
for _page, _kinds in _B2_0_2_0_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _B2_0_2_0))
#: The preview run's receipts are NOT-RUN under 0.2.0 and the run is NOT
#: VERIFIED, so its page reads couldn't check, in the check's own words, step by step. Generated from
#: the measured difference by tooling, not typed.
_PREVIEW_0_2_0 = "the 0.2.0 verifier reads the preview format as NOT VERIFIED; the run couldn't be checked"
_PREVIEW_0_2_0_PAGES: dict[str, dict[str, list[str]]] = {
    "run[preview]/case.html": {"gone": ["Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "Not checked \u00b7 The check that ran did not require the run's output files, so this page does not say the records agree.", "This answer's trail was checked on <time> \u2014 each check that ran held.", "[PASS ] receipts/01-document-in.json: receipt format [PASS ] receipts/01-document-in.json: bytes are canonical [PASS ] receipts/01-document-in.json: required field 'format' [PASS ] receipts/01-document-in.json: required field 'run_id' [PASS ] receipts/01-document-in.json: required field 'stage' [PASS ] receipts/01-document-in.json: required field 'prev' [PASS ] receipts/01-document-in.json: required field 'time' [PASS ] receipts/01-document-in.json: required field 'coverage' [PASS ] receipts/01-document-in.json: required field 'emission' [PASS ] receipts/01-document-in.json: required field 'anchor' [PASS ] receipts/01-document-in.json: required field 'instrument' [PASS ] receipts/01-document-in.json: required field 'inputs' [PASS ] receipts/01-document-in.json: required field 'outputs' [PASS ] receipts/01-document-in.json: required field 'assertions' [PASS ] receipts/01-document-in.json: required field 'outcome' [PASS ] receipts/01-document-in.json: time.started carries its zone [PASS ] receipts/01-document-in.json: time.ended carries its zone [PASS ] receipts/01-document-in.json: instrument is named and pinned [PASS ] receipts/01-document-in.json: inputs/corpus declares a trust class [PASS ] receipts/01-document-in.json: outputs/documents.manifest declares a trust class [PASS ] receipts/01-document-in.json: assertions name their constants [PASS ] receipts/01-document-in.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-document-in.json: coverage declares completeness [PASS ] receipts/01-document-in.json: 'complete' is consistent with the stage lists [PASS ] receipts/01-document-in.json: anchor state is declared, not absent [NOT-RUN] receipts/01-document-in.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-document-in.json: digest matches the manifest [PASS ] receipts/01-document-in.json: chain link", "[PASS ] receipts/01-document-in.json: receipt format [PASS ] receipts/01-document-in.json: bytes are canonical [PASS ] receipts/01-document-in.json: required field 'format' [PASS ] receipts/01-document-in.json: required field 'run_id' [PASS ] receipts/01-document-in.json: required field 'stage' [PASS ] receipts/01-document-in.json: required field 'prev' [PASS ] receipts/01-document-in.json: required field 'time' [PASS ] receipts/01-document-in.json: required field 'coverage' [PASS ] receipts/01-document-in.json: required field 'emission' [PASS ] receipts/01-document-in.json: required field 'anchor' [PASS ] receipts/01-document-in.json: required field 'instrument' [PASS ] receipts/01-document-in.json: required field 'inputs' [PASS ] receipts/01-document-in.json: required field 'outputs' [PASS ] receipts/01-document-in.json: required field 'assertions' [PASS ] receipts/01-document-in.json: required field 'outcome' [PASS ] receipts/01-document-in.json: time.started carries its zone [PASS ] receipts/01-document-in.json: time.ended carries its zone [PASS ] receipts/01-document-in.json: instrument is named and pinned [PASS ] receipts/01-document-in.json: inputs/corpus declares a trust class [PASS ] receipts/01-document-in.json: outputs/documents.manifest declares a trust class [PASS ] receipts/01-document-in.json: assertions name their constants [PASS ] receipts/01-document-in.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/01-document-in.json: coverage declares completeness [PASS ] receipts/01-document-in.json: 'complete' is consistent with the stage lists [PASS ] receipts/01-document-in.json: anchor state is declared, not absent [NOT-RUN] receipts/01-document-in.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/01-document-in.json: digest matches the manifest [PASS ] receipts/01-document-in.json: chain link [PASS ] receipts/02-converted.json: receipt format [PASS ] receipts/02-converted.json: bytes are canonical [PASS ] receipts/02-converted.json: required field 'format' [PASS ] receipts/02-converted.json: required field 'run_id' [PASS ] receipts/02-converted.json: required field 'stage' [PASS ] receipts/02-converted.json: required field 'prev' [PASS ] receipts/02-converted.json: required field 'time' [PASS ] receipts/02-converted.json: required field 'coverage' [PASS ] receipts/02-converted.json: required field 'emission' [PASS ] receipts/02-converted.json: required field 'anchor' [PASS ] receipts/02-converted.json: required field 'instrument' [PASS ] receipts/02-converted.json: required field 'inputs' [PASS ] receipts/02-converted.json: required field 'outputs' [PASS ] receipts/02-converted.json: required field 'assertions' [PASS ] receipts/02-converted.json: required field 'outcome' [PASS ] receipts/02-converted.json: time.started carries its zone [PASS ] receipts/02-converted.json: time.ended carries its zone [PASS ] receipts/02-converted.json: instrument is named and pinned [PASS ] receipts/02-converted.json: inputs/documents.manifest declares a trust class [PASS ] receipts/02-converted.json: outputs/converted.manifest declares a trust class [PASS ] receipts/02-converted.json: assertions name their constants [PASS ] receipts/02-converted.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-converted.json: coverage declares completeness [PASS ] receipts/02-converted.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-converted.json: anchor state is declared, not absent [NOT-RUN] receipts/02-converted.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-converted.json: digest matches the manifest [PASS ] receipts/02-converted.json: chain link [PASS ] receipts/03-cleaned.json: receipt format [PASS ] receipts/03-cleaned.json: bytes are canonical [PASS ] receipts/03-cleaned.json: required field 'format' [PASS ] receipts/03-cleaned.json: required field 'run_id' [PASS ] receipts/03-cleaned.json: required field 'stage' [PASS ] receipts/03-cleaned.json: required field 'prev' [PASS ] receipts/03-cleaned.json: required field 'time' [PASS ] receipts/03-cleaned.json: required field 'coverage' [PASS ] receipts/03-cleaned.json: required field 'emission' [PASS ] receipts/03-cleaned.json: required field 'anchor' [PASS ] receipts/03-cleaned.json: required field 'instrument' [PASS ] receipts/03-cleaned.json: required field 'inputs' [PASS ] receipts/03-cleaned.json: required field 'outputs' [PASS ] receipts/03-cleaned.json: required field 'assertions' [PASS ] receipts/03-cleaned.json: required field 'outcome' [PASS ] receipts/03-cleaned.json: time.started carries its zone [PASS ] receipts/03-cleaned.json: time.ended carries its zone [PASS ] receipts/03-cleaned.json: instrument is named and pinned [PASS ] receipts/03-cleaned.json: inputs/converted.manifest declares a trust class [PASS ] receipts/03-cleaned.json: outputs/cleaned.manifest declares a trust class [PASS ] receipts/03-cleaned.json: assertions name their constants [PASS ] receipts/03-cleaned.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/03-cleaned.json: coverage declares completeness [PASS ] receipts/03-cleaned.json: 'complete' is consistent with the stage lists [PASS ] receipts/03-cleaned.json: anchor state is declared, not absent [NOT-RUN] receipts/03-cleaned.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/03-cleaned.json: digest matches the manifest [PASS ] receipts/03-cleaned.json: chain link [PASS ] receipts/04-split.json: receipt format [PASS ] receipts/04-split.json: bytes are canonical [PASS ] receipts/04-split.json: required field 'format' [PASS ] receipts/04-split.json: required field 'run_id' [PASS ] receipts/04-split.json: required field 'stage' [PASS ] receipts/04-split.json: required field 'prev' [PASS ] receipts/04-split.json: required field 'time' [PASS ] receipts/04-split.json: required field 'coverage' [PASS ] receipts/04-split.json: required field 'emission' [PASS ] receipts/04-split.json: required field 'anchor' [PASS ] receipts/04-split.json: required field 'instrument' [PASS ] receipts/04-split.json: required field 'inputs' [PASS ] receipts/04-split.json: required field 'outputs' [PASS ] receipts/04-split.json: required field 'assertions' [PASS ] receipts/04-split.json: required field 'outcome' [PASS ] receipts/04-split.json: time.started carries its zone [PASS ] receipts/04-split.json: time.ended carries its zone [PASS ] receipts/04-split.json: instrument is named and pinned [PASS ] receipts/04-split.json: inputs/cleaned.manifest declares a trust class [PASS ] receipts/04-split.json: outputs/chunks.manifest declares a trust class [PASS ] receipts/04-split.json: assertions name their constants [PASS ] receipts/04-split.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/04-split.json: coverage declares completeness [PASS ] receipts/04-split.json: 'complete' is consistent with the stage lists [PASS ] receipts/04-split.json: anchor state is declared, not absent [NOT-RUN] receipts/04-split.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/04-split.json: digest matches the manifest [PASS ] receipts/04-split.json: chain link [PASS ] receipts/05-embedded.json: receipt format [PASS ] receipts/05-embedded.json: bytes are canonical [PASS ] receipts/05-embedded.json: required field 'format' [PASS ] receipts/05-embedded.json: required field 'run_id' [PASS ] receipts/05-embedded.json: required field 'stage' [PASS ] receipts/05-embedded.json: required field 'prev' [PASS ] receipts/05-embedded.json: required field 'time' [PASS ] receipts/05-embedded.json: required field 'coverage' [PASS ] receipts/05-embedded.json: required field 'emission' [PASS ] receipts/05-embedded.json: required field 'anchor' [PASS ] receipts/05-embedded.json: required field 'instrument' [PASS ] receipts/05-embedded.json: required field 'inputs' [PASS ] receipts/05-embedded.json: required field 'outputs' [PASS ] receipts/05-embedded.json: required field 'assertions' [PASS ] receipts/05-embedded.json: required field 'outcome' [PASS ] receipts/05-embedded.json: time.started carries its zone [PASS ] receipts/05-embedded.json: time.ended carries its zone [PASS ] receipts/05-embedded.json: instrument is named and pinned [PASS ] receipts/05-embedded.json: inputs/chunks.manifest declares a trust class [PASS ] receipts/05-embedded.json: outputs/vectors.manifest declares a trust class [PASS ] receipts/05-embedded.json: assertions name their constants [PASS ] receipts/05-embedded.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/05-embedded.json: coverage declares completeness [PASS ] receipts/05-embedded.json: 'complete' is consistent with the stage lists [PASS ] receipts/05-embedded.json: anchor state is declared, not absent [NOT-RUN] receipts/05-embedded.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/05-embedded.json: digest matches the manifest [PASS ] receipts/05-embedded.json: chain link [PASS ] receipts/06-indexed.json: receipt format [PASS ] receipts/06-indexed.json: bytes are canonical [PASS ] receipts/06-indexed.json: required field 'format' [PASS ] receipts/06-indexed.json: required field 'run_id' [PASS ] receipts/06-indexed.json: required field 'stage' [PASS ] receipts/06-indexed.json: required field 'prev' [PASS ] receipts/06-indexed.json: required field 'time' [PASS ] receipts/06-indexed.json: required field 'coverage' [PASS ] receipts/06-indexed.json: required field 'emission' [PASS ] receipts/06-indexed.json: required field 'anchor' [PASS ] receipts/06-indexed.json: required field 'instrument' [PASS ] receipts/06-indexed.json: required field 'inputs' [PASS ] receipts/06-indexed.json: required field 'outputs' [PASS ] receipts/06-indexed.json: required field 'assertions' [PASS ] receipts/06-indexed.json: required field 'outcome' [PASS ] receipts/06-indexed.json: time.started carries its zone [PASS ] receipts/06-indexed.json: time.ended carries its zone [PASS ] receipts/06-indexed.json: instrument is named and pinned [PASS ] receipts/06-indexed.json: inputs/vectors.manifest declares a trust class [PASS ] receipts/06-indexed.json: outputs/index.manifest declares a trust class [PASS ] receipts/06-indexed.json: assertions name their constants [PASS ] receipts/06-indexed.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/06-indexed.json: coverage declares completeness [PASS ] receipts/06-indexed.json: 'complete' is consistent with the stage lists [PASS ] receipts/06-indexed.json: anchor state is declared, not absent [NOT-RUN] receipts/06-indexed.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/06-indexed.json: digest matches the manifest [PASS ] receipts/06-indexed.json: chain link [PASS ] receipts/07-retrieved.json: receipt format [PASS ] receipts/07-retrieved.json: bytes are canonical [PASS ] receipts/07-retrieved.json: required field 'format' [PASS ] receipts/07-retrieved.json: required field 'run_id' [PASS ] receipts/07-retrieved.json: required field 'stage' [PASS ] receipts/07-retrieved.json: required field 'prev' [PASS ] receipts/07-retrieved.json: required field 'time' [PASS ] receipts/07-retrieved.json: required field 'coverage' [PASS ] receipts/07-retrieved.json: required field 'emission' [PASS ] receipts/07-retrieved.json: required field 'anchor' [PASS ] receipts/07-retrieved.json: required field 'instrument' [PASS ] receipts/07-retrieved.json: required field 'inputs' [PASS ] receipts/07-retrieved.json: required field 'outputs' [PASS ] receipts/07-retrieved.json: required field 'assertions' [PASS ] receipts/07-retrieved.json: required field 'outcome' [PASS ] receipts/07-retrieved.json: time.started carries its zone [PASS ] receipts/07-retrieved.json: time.ended carries its zone [PASS ] receipts/07-retrieved.json: instrument is named and pinned [PASS ] receipts/07-retrieved.json: inputs/index.manifest declares a trust class [PASS ] receipts/07-retrieved.json: inputs/question declares a trust class [PASS ] receipts/07-retrieved.json: outputs/retrieved.manifest declares a trust class [PASS ] receipts/07-retrieved.json: assertions name their constants [PASS ] receipts/07-retrieved.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/07-retrieved.json: coverage declares completeness [PASS ] receipts/07-retrieved.json: 'complete' is consistent with the stage lists [PASS ] receipts/07-retrieved.json: anchor state is declared, not absent [NOT-RUN] receipts/07-retrieved.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/07-retrieved.json: digest matches the manifest [PASS ] receipts/07-retrieved.json: chain link [PASS ] receipts/08-prompt-built.json: receipt format [PASS ] receipts/08-prompt-built.json: bytes are canonical [PASS ] receipts/08-prompt-built.json: required field 'format' [PASS ] receipts/08-prompt-built.json: required field 'run_id' [PASS ] receipts/08-prompt-built.json: required field 'stage' [PASS ] receipts/08-prompt-built.json: required field 'prev' [PASS ] receipts/08-prompt-built.json: required field 'time' [PASS ] receipts/08-prompt-built.json: required field 'coverage' [PASS ] receipts/08-prompt-built.json: required field 'emission' [PASS ] receipts/08-prompt-built.json: required field 'anchor' [PASS ] receipts/08-prompt-built.json: required field 'instrument' [PASS ] receipts/08-prompt-built.json: required field 'inputs' [PASS ] receipts/08-prompt-built.json: required field 'outputs' [PASS ] receipts/08-prompt-built.json: required field 'assertions' [PASS ] receipts/08-prompt-built.json: required field 'outcome' [PASS ] receipts/08-prompt-built.json: time.started carries its zone [PASS ] receipts/08-prompt-built.json: time.ended carries its zone [PASS ] receipts/08-prompt-built.json: instrument is named and pinned [PASS ] receipts/08-prompt-built.json: inputs/retrieved.manifest declares a trust class [PASS ] receipts/08-prompt-built.json: outputs/prompt.manifest declares a trust class [PASS ] receipts/08-prompt-built.json: assertions name their constants [PASS ] receipts/08-prompt-built.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/08-prompt-built.json: coverage declares completeness [PASS ] receipts/08-prompt-built.json: 'complete' is consistent with the stage lists [PASS ] receipts/08-prompt-built.json: anchor state is declared, not absent [NOT-RUN] receipts/08-prompt-built.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/08-prompt-built.json: digest matches the manifest [PASS ] receipts/08-prompt-built.json: chain link [PASS ] receipts/09-answer.json: receipt format [PASS ] receipts/09-answer.json: bytes are canonical [PASS ] receipts/09-answer.json: required field 'format' [PASS ] receipts/09-answer.json: required field 'run_id' [PASS ] receipts/09-answer.json: required field 'stage' [PASS ] receipts/09-answer.json: required field 'prev' [PASS ] receipts/09-answer.json: required field 'time' [PASS ] receipts/09-answer.json: required field 'coverage' [PASS ] receipts/09-answer.json: required field 'emission' [PASS ] receipts/09-answer.json: required field 'anchor' [PASS ] receipts/09-answer.json: required field 'instrument' [PASS ] receipts/09-answer.json: required field 'inputs' [PASS ] receipts/09-answer.json: required field 'outputs' [PASS ] receipts/09-answer.json: required field 'assertions' [PASS ] receipts/09-answer.json: required field 'outcome' [PASS ] receipts/09-answer.json: time.started carries its zone [PASS ] receipts/09-answer.json: time.ended carries its zone [PASS ] receipts/09-answer.json: instrument is named and pinned [PASS ] receipts/09-answer.json: inputs/prompt.manifest declares a trust class [PASS ] receipts/09-answer.json: outputs/answer.manifest declares a trust class [PASS ] receipts/09-answer.json: assertions name their constants [PASS ] receipts/09-answer.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/09-answer.json: coverage declares completeness [PASS ] receipts/09-answer.json: 'complete' is consistent with the stage lists [PASS ] receipts/09-answer.json: anchor state is declared, not absent [NOT-RUN] receipts/09-answer.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/09-answer.json: digest matches the manifest [PASS ] receipts/09-answer.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt 245 pass, 0 fail, 10 not-run -> PASS", "[PASS ] receipts/02-converted.json: receipt format [PASS ] receipts/02-converted.json: bytes are canonical [PASS ] receipts/02-converted.json: required field 'format' [PASS ] receipts/02-converted.json: required field 'run_id' [PASS ] receipts/02-converted.json: required field 'stage' [PASS ] receipts/02-converted.json: required field 'prev' [PASS ] receipts/02-converted.json: required field 'time' [PASS ] receipts/02-converted.json: required field 'coverage' [PASS ] receipts/02-converted.json: required field 'emission' [PASS ] receipts/02-converted.json: required field 'anchor' [PASS ] receipts/02-converted.json: required field 'instrument' [PASS ] receipts/02-converted.json: required field 'inputs' [PASS ] receipts/02-converted.json: required field 'outputs' [PASS ] receipts/02-converted.json: required field 'assertions' [PASS ] receipts/02-converted.json: required field 'outcome' [PASS ] receipts/02-converted.json: time.started carries its zone [PASS ] receipts/02-converted.json: time.ended carries its zone [PASS ] receipts/02-converted.json: instrument is named and pinned [PASS ] receipts/02-converted.json: inputs/documents.manifest declares a trust class [PASS ] receipts/02-converted.json: outputs/converted.manifest declares a trust class [PASS ] receipts/02-converted.json: assertions name their constants [PASS ] receipts/02-converted.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/02-converted.json: coverage declares completeness [PASS ] receipts/02-converted.json: 'complete' is consistent with the stage lists [PASS ] receipts/02-converted.json: anchor state is declared, not absent [NOT-RUN] receipts/02-converted.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/02-converted.json: digest matches the manifest [PASS ] receipts/02-converted.json: chain link", "[PASS ] receipts/03-cleaned.json: receipt format [PASS ] receipts/03-cleaned.json: bytes are canonical [PASS ] receipts/03-cleaned.json: required field 'format' [PASS ] receipts/03-cleaned.json: required field 'run_id' [PASS ] receipts/03-cleaned.json: required field 'stage' [PASS ] receipts/03-cleaned.json: required field 'prev' [PASS ] receipts/03-cleaned.json: required field 'time' [PASS ] receipts/03-cleaned.json: required field 'coverage' [PASS ] receipts/03-cleaned.json: required field 'emission' [PASS ] receipts/03-cleaned.json: required field 'anchor' [PASS ] receipts/03-cleaned.json: required field 'instrument' [PASS ] receipts/03-cleaned.json: required field 'inputs' [PASS ] receipts/03-cleaned.json: required field 'outputs' [PASS ] receipts/03-cleaned.json: required field 'assertions' [PASS ] receipts/03-cleaned.json: required field 'outcome' [PASS ] receipts/03-cleaned.json: time.started carries its zone [PASS ] receipts/03-cleaned.json: time.ended carries its zone [PASS ] receipts/03-cleaned.json: instrument is named and pinned [PASS ] receipts/03-cleaned.json: inputs/converted.manifest declares a trust class [PASS ] receipts/03-cleaned.json: outputs/cleaned.manifest declares a trust class [PASS ] receipts/03-cleaned.json: assertions name their constants [PASS ] receipts/03-cleaned.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/03-cleaned.json: coverage declares completeness [PASS ] receipts/03-cleaned.json: 'complete' is consistent with the stage lists [PASS ] receipts/03-cleaned.json: anchor state is declared, not absent [NOT-RUN] receipts/03-cleaned.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/03-cleaned.json: digest matches the manifest [PASS ] receipts/03-cleaned.json: chain link", "[PASS ] receipts/04-split.json: receipt format [PASS ] receipts/04-split.json: bytes are canonical [PASS ] receipts/04-split.json: required field 'format' [PASS ] receipts/04-split.json: required field 'run_id' [PASS ] receipts/04-split.json: required field 'stage' [PASS ] receipts/04-split.json: required field 'prev' [PASS ] receipts/04-split.json: required field 'time' [PASS ] receipts/04-split.json: required field 'coverage' [PASS ] receipts/04-split.json: required field 'emission' [PASS ] receipts/04-split.json: required field 'anchor' [PASS ] receipts/04-split.json: required field 'instrument' [PASS ] receipts/04-split.json: required field 'inputs' [PASS ] receipts/04-split.json: required field 'outputs' [PASS ] receipts/04-split.json: required field 'assertions' [PASS ] receipts/04-split.json: required field 'outcome' [PASS ] receipts/04-split.json: time.started carries its zone [PASS ] receipts/04-split.json: time.ended carries its zone [PASS ] receipts/04-split.json: instrument is named and pinned [PASS ] receipts/04-split.json: inputs/cleaned.manifest declares a trust class [PASS ] receipts/04-split.json: outputs/chunks.manifest declares a trust class [PASS ] receipts/04-split.json: assertions name their constants [PASS ] receipts/04-split.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/04-split.json: coverage declares completeness [PASS ] receipts/04-split.json: 'complete' is consistent with the stage lists [PASS ] receipts/04-split.json: anchor state is declared, not absent [NOT-RUN] receipts/04-split.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/04-split.json: digest matches the manifest [PASS ] receipts/04-split.json: chain link", "[PASS ] receipts/05-embedded.json: receipt format [PASS ] receipts/05-embedded.json: bytes are canonical [PASS ] receipts/05-embedded.json: required field 'format' [PASS ] receipts/05-embedded.json: required field 'run_id' [PASS ] receipts/05-embedded.json: required field 'stage' [PASS ] receipts/05-embedded.json: required field 'prev' [PASS ] receipts/05-embedded.json: required field 'time' [PASS ] receipts/05-embedded.json: required field 'coverage' [PASS ] receipts/05-embedded.json: required field 'emission' [PASS ] receipts/05-embedded.json: required field 'anchor' [PASS ] receipts/05-embedded.json: required field 'instrument' [PASS ] receipts/05-embedded.json: required field 'inputs' [PASS ] receipts/05-embedded.json: required field 'outputs' [PASS ] receipts/05-embedded.json: required field 'assertions' [PASS ] receipts/05-embedded.json: required field 'outcome' [PASS ] receipts/05-embedded.json: time.started carries its zone [PASS ] receipts/05-embedded.json: time.ended carries its zone [PASS ] receipts/05-embedded.json: instrument is named and pinned [PASS ] receipts/05-embedded.json: inputs/chunks.manifest declares a trust class [PASS ] receipts/05-embedded.json: outputs/vectors.manifest declares a trust class [PASS ] receipts/05-embedded.json: assertions name their constants [PASS ] receipts/05-embedded.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/05-embedded.json: coverage declares completeness [PASS ] receipts/05-embedded.json: 'complete' is consistent with the stage lists [PASS ] receipts/05-embedded.json: anchor state is declared, not absent [NOT-RUN] receipts/05-embedded.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/05-embedded.json: digest matches the manifest [PASS ] receipts/05-embedded.json: chain link", "[PASS ] receipts/06-indexed.json: receipt format [PASS ] receipts/06-indexed.json: bytes are canonical [PASS ] receipts/06-indexed.json: required field 'format' [PASS ] receipts/06-indexed.json: required field 'run_id' [PASS ] receipts/06-indexed.json: required field 'stage' [PASS ] receipts/06-indexed.json: required field 'prev' [PASS ] receipts/06-indexed.json: required field 'time' [PASS ] receipts/06-indexed.json: required field 'coverage' [PASS ] receipts/06-indexed.json: required field 'emission' [PASS ] receipts/06-indexed.json: required field 'anchor' [PASS ] receipts/06-indexed.json: required field 'instrument' [PASS ] receipts/06-indexed.json: required field 'inputs' [PASS ] receipts/06-indexed.json: required field 'outputs' [PASS ] receipts/06-indexed.json: required field 'assertions' [PASS ] receipts/06-indexed.json: required field 'outcome' [PASS ] receipts/06-indexed.json: time.started carries its zone [PASS ] receipts/06-indexed.json: time.ended carries its zone [PASS ] receipts/06-indexed.json: instrument is named and pinned [PASS ] receipts/06-indexed.json: inputs/vectors.manifest declares a trust class [PASS ] receipts/06-indexed.json: outputs/index.manifest declares a trust class [PASS ] receipts/06-indexed.json: assertions name their constants [PASS ] receipts/06-indexed.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/06-indexed.json: coverage declares completeness [PASS ] receipts/06-indexed.json: 'complete' is consistent with the stage lists [PASS ] receipts/06-indexed.json: anchor state is declared, not absent [NOT-RUN] receipts/06-indexed.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/06-indexed.json: digest matches the manifest [PASS ] receipts/06-indexed.json: chain link", "[PASS ] receipts/07-retrieved.json: receipt format [PASS ] receipts/07-retrieved.json: bytes are canonical [PASS ] receipts/07-retrieved.json: required field 'format' [PASS ] receipts/07-retrieved.json: required field 'run_id' [PASS ] receipts/07-retrieved.json: required field 'stage' [PASS ] receipts/07-retrieved.json: required field 'prev' [PASS ] receipts/07-retrieved.json: required field 'time' [PASS ] receipts/07-retrieved.json: required field 'coverage' [PASS ] receipts/07-retrieved.json: required field 'emission' [PASS ] receipts/07-retrieved.json: required field 'anchor' [PASS ] receipts/07-retrieved.json: required field 'instrument' [PASS ] receipts/07-retrieved.json: required field 'inputs' [PASS ] receipts/07-retrieved.json: required field 'outputs' [PASS ] receipts/07-retrieved.json: required field 'assertions' [PASS ] receipts/07-retrieved.json: required field 'outcome' [PASS ] receipts/07-retrieved.json: time.started carries its zone [PASS ] receipts/07-retrieved.json: time.ended carries its zone [PASS ] receipts/07-retrieved.json: instrument is named and pinned [PASS ] receipts/07-retrieved.json: inputs/index.manifest declares a trust class [PASS ] receipts/07-retrieved.json: inputs/question declares a trust class [PASS ] receipts/07-retrieved.json: outputs/retrieved.manifest declares a trust class [PASS ] receipts/07-retrieved.json: assertions name their constants [PASS ] receipts/07-retrieved.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/07-retrieved.json: coverage declares completeness [PASS ] receipts/07-retrieved.json: 'complete' is consistent with the stage lists [PASS ] receipts/07-retrieved.json: anchor state is declared, not absent [NOT-RUN] receipts/07-retrieved.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/07-retrieved.json: digest matches the manifest [PASS ] receipts/07-retrieved.json: chain link", "[PASS ] receipts/08-prompt-built.json: receipt format [PASS ] receipts/08-prompt-built.json: bytes are canonical [PASS ] receipts/08-prompt-built.json: required field 'format' [PASS ] receipts/08-prompt-built.json: required field 'run_id' [PASS ] receipts/08-prompt-built.json: required field 'stage' [PASS ] receipts/08-prompt-built.json: required field 'prev' [PASS ] receipts/08-prompt-built.json: required field 'time' [PASS ] receipts/08-prompt-built.json: required field 'coverage' [PASS ] receipts/08-prompt-built.json: required field 'emission' [PASS ] receipts/08-prompt-built.json: required field 'anchor' [PASS ] receipts/08-prompt-built.json: required field 'instrument' [PASS ] receipts/08-prompt-built.json: required field 'inputs' [PASS ] receipts/08-prompt-built.json: required field 'outputs' [PASS ] receipts/08-prompt-built.json: required field 'assertions' [PASS ] receipts/08-prompt-built.json: required field 'outcome' [PASS ] receipts/08-prompt-built.json: time.started carries its zone [PASS ] receipts/08-prompt-built.json: time.ended carries its zone [PASS ] receipts/08-prompt-built.json: instrument is named and pinned [PASS ] receipts/08-prompt-built.json: inputs/retrieved.manifest declares a trust class [PASS ] receipts/08-prompt-built.json: outputs/prompt.manifest declares a trust class [PASS ] receipts/08-prompt-built.json: assertions name their constants [PASS ] receipts/08-prompt-built.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/08-prompt-built.json: coverage declares completeness [PASS ] receipts/08-prompt-built.json: 'complete' is consistent with the stage lists [PASS ] receipts/08-prompt-built.json: anchor state is declared, not absent [NOT-RUN] receipts/08-prompt-built.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/08-prompt-built.json: digest matches the manifest [PASS ] receipts/08-prompt-built.json: chain link", "[PASS ] receipts/09-answer.json: receipt format [PASS ] receipts/09-answer.json: bytes are canonical [PASS ] receipts/09-answer.json: required field 'format' [PASS ] receipts/09-answer.json: required field 'run_id' [PASS ] receipts/09-answer.json: required field 'stage' [PASS ] receipts/09-answer.json: required field 'prev' [PASS ] receipts/09-answer.json: required field 'time' [PASS ] receipts/09-answer.json: required field 'coverage' [PASS ] receipts/09-answer.json: required field 'emission' [PASS ] receipts/09-answer.json: required field 'anchor' [PASS ] receipts/09-answer.json: required field 'instrument' [PASS ] receipts/09-answer.json: required field 'inputs' [PASS ] receipts/09-answer.json: required field 'outputs' [PASS ] receipts/09-answer.json: required field 'assertions' [PASS ] receipts/09-answer.json: required field 'outcome' [PASS ] receipts/09-answer.json: time.started carries its zone [PASS ] receipts/09-answer.json: time.ended carries its zone [PASS ] receipts/09-answer.json: instrument is named and pinned [PASS ] receipts/09-answer.json: inputs/prompt.manifest declares a trust class [PASS ] receipts/09-answer.json: outputs/answer.manifest declares a trust class [PASS ] receipts/09-answer.json: assertions name their constants [PASS ] receipts/09-answer.json: outcome class is one of ['error', 'ok', 'refused'] [PASS ] receipts/09-answer.json: coverage declares completeness [PASS ] receipts/09-answer.json: 'complete' is consistent with the stage lists [PASS ] receipts/09-answer.json: anchor state is declared, not absent [NOT-RUN] receipts/09-answer.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [PASS ] receipts/09-answer.json: digest matches the manifest [PASS ] receipts/09-answer.json: chain link", "step 1 of 9 \u00b7 document in \u2014 27 checks made \u2014 all hold.", "step 1 of 9 \u00b7 document in \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 2 of 9 \u00b7 converted \u2014 27 checks made \u2014 all hold.", "step 2 of 9 \u00b7 converted \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 3 of 9 \u00b7 cleaned \u2014 27 checks made \u2014 all hold.", "step 3 of 9 \u00b7 cleaned \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 4 of 9 \u00b7 split \u2014 27 checks made \u2014 all hold.", "step 4 of 9 \u00b7 split \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 5 of 9 \u00b7 embedded \u2014 27 checks made \u2014 all hold.", "step 5 of 9 \u00b7 embedded \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 6 of 9 \u00b7 indexed \u2014 27 checks made \u2014 all hold.", "step 6 of 9 \u00b7 indexed \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 7 of 9 \u00b7 retrieved \u2014 28 checks made \u2014 all hold.", "step 7 of 9 \u00b7 retrieved \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 8 of 9 \u00b7 prompt built \u2014 27 checks made \u2014 all hold.", "step 8 of 9 \u00b7 prompt built \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 9 of 9 \u00b7 answer \u2014 27 checks made \u2014 all hold.", "step 9 of 9 \u00b7 answer \u2014 Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], "new": ["Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "Couldn't check \u00b7 This answer's trail was checked on <time> \u2014 it was not verified: a receipt names a format the check does not implement, so the check did not read its contents.", "The list of steps \u2014 Could not be checked from here, and the check says why: 'stage-receipt-chain/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; the chain checks still run", "This answer's trail was checked on <time> \u2014 it was not verified: a receipt names a format the check does not implement, so the check did not read its contents.", "[NOT-RUN] manifest: chain format -- 'stage-receipt-chain/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; the chain checks still run [NOT-RUN] receipts/01-document-in.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/01-document-in.json: digest matches the manifest [PASS ] receipts/01-document-in.json: chain link [NOT-RUN] receipts/02-converted.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/02-converted.json: digest matches the manifest [PASS ] receipts/02-converted.json: chain link [NOT-RUN] receipts/03-cleaned.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/03-cleaned.json: digest matches the manifest [PASS ] receipts/03-cleaned.json: chain link [NOT-RUN] receipts/04-split.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/04-split.json: digest matches the manifest [PASS ] receipts/04-split.json: chain link [NOT-RUN] receipts/05-embedded.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/05-embedded.json: digest matches the manifest [PASS ] receipts/05-embedded.json: chain link [NOT-RUN] receipts/06-indexed.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/06-indexed.json: digest matches the manifest [PASS ] receipts/06-indexed.json: chain link [NOT-RUN] receipts/07-retrieved.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/07-retrieved.json: digest matches the manifest [PASS ] receipts/07-retrieved.json: chain link [NOT-RUN] receipts/08-prompt-built.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/08-prompt-built.json: digest matches the manifest [PASS ] receipts/08-prompt-built.json: chain link [NOT-RUN] receipts/09-answer.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/09-answer.json: digest matches the manifest [PASS ] receipts/09-answer.json: chain link [NOT-RUN] run: artifacts -- artifacts not present; output files not checked [PASS ] manifest: chain head matches the last receipt 19 pass, 0 fail, 11 not-run -> NOT VERIFIED (chain format not implemented; receipt format not implemented: 9 receipt(s))", "[NOT-RUN] receipts/01-document-in.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/01-document-in.json: digest matches the manifest [PASS ] receipts/01-document-in.json: chain link", "[NOT-RUN] receipts/02-converted.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/02-converted.json: digest matches the manifest [PASS ] receipts/02-converted.json: chain link", "[NOT-RUN] receipts/03-cleaned.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/03-cleaned.json: digest matches the manifest [PASS ] receipts/03-cleaned.json: chain link", "[NOT-RUN] receipts/04-split.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/04-split.json: digest matches the manifest [PASS ] receipts/04-split.json: chain link", "[NOT-RUN] receipts/05-embedded.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/05-embedded.json: digest matches the manifest [PASS ] receipts/05-embedded.json: chain link", "[NOT-RUN] receipts/06-indexed.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/06-indexed.json: digest matches the manifest [PASS ] receipts/06-indexed.json: chain link", "[NOT-RUN] receipts/07-retrieved.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/07-retrieved.json: digest matches the manifest [PASS ] receipts/07-retrieved.json: chain link", "[NOT-RUN] receipts/08-prompt-built.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/08-prompt-built.json: digest matches the manifest [PASS ] receipts/08-prompt-built.json: chain link", "[NOT-RUN] receipts/09-answer.json: receipt format -- 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked [PASS ] receipts/09-answer.json: digest matches the manifest [PASS ] receipts/09-answer.json: chain link", "step 1 of 9 \u00b7 document in \u2014 2 checks made \u2014 all hold.", "step 1 of 9 \u00b7 document in \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 2 of 9 \u00b7 converted \u2014 2 checks made \u2014 all hold.", "step 2 of 9 \u00b7 converted \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 3 of 9 \u00b7 cleaned \u2014 2 checks made \u2014 all hold.", "step 3 of 9 \u00b7 cleaned \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 4 of 9 \u00b7 split \u2014 2 checks made \u2014 all hold.", "step 4 of 9 \u00b7 split \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 5 of 9 \u00b7 embedded \u2014 2 checks made \u2014 all hold.", "step 5 of 9 \u00b7 embedded \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 6 of 9 \u00b7 indexed \u2014 2 checks made \u2014 all hold.", "step 6 of 9 \u00b7 indexed \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 7 of 9 \u00b7 retrieved \u2014 2 checks made \u2014 all hold.", "step 7 of 9 \u00b7 retrieved \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 8 of 9 \u00b7 prompt built \u2014 2 checks made \u2014 all hold.", "step 8 of 9 \u00b7 prompt built \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked", "step 9 of 9 \u00b7 answer \u2014 2 checks made \u2014 all hold.", "step 9 of 9 \u00b7 answer \u2014 Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked"]},
}
for _page, _kinds in _PREVIEW_0_2_0_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _PREVIEW_0_2_0))
#: The comparison names the SDK it ran, now the development build. Generated
#: from the measured difference by tooling, not typed.
_VERSION_0_2_0 = "the SDK pinned is 0.2.0, from PyPI"
_VERSION_0_2_0_PAGES: dict[str, dict[str, list[str]]] = {
    "diff[held-a,held-b]": {"gone": ["Compared with onetrace 0.1.2, build wheel:<hex>, at <time>."], "new": ["Compared with onetrace 0.2.0, build wheel:<hex>, at <time>."]},
}
for _page, _kinds in _VERSION_0_2_0_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _VERSION_0_2_0))
#: No incident for a check the pinned release does not ship, so the topology
#: incidents and every count that included them go. Generated from the measured difference by
#: tooling, not typed.
_NO_TOPOLOGY_INCIDENT = "no incident for a check the pinned release does not ship"
_NO_TOPOLOGY_INCIDENT_PAGES: dict[str, dict[str, list[str]]] = {
    "diff[held-a,held-b]": {"new": ["1 of the 3 incidents raised from stored runs when this page was generated came from this page's reports"]},
    "home.html + counts.html": {"gone": ["1 run of 4 \u2014 runs raising I-COULD-NOT-CHECK"], "new": ["0 runs of 4 \u2014 runs raising I-COULD-NOT-CHECK", "2 incidents of 3 raised from stored runs"]},
    "incidents-i-could-not-check.html": {"gone": ["I-COULD-NOT-CHECK \u2014 1 run of 4", "the reference topology check (verifier/verify_topology.py) is not shipped by any distribution at the pinned commit, so it was not run", "the report it came from"], "new": ["I-COULD-NOT-CHECK \u2014 0 runs of 4", "This rule raised nothing from the 4 runs stored."]},
    "incidents.html": {"gone": ["I-COULD-NOT-CHECK \u2014 1 run of 4", "the reference topology check (verifier/verify_topology.py) is not shipped by any distribution at the pinned commit, so it was not run"], "new": ["I-COULD-NOT-CHECK \u2014 0 runs of 4", "This rule raised nothing from the 4 runs stored."]},
    "run[held-b]/answer.html": {"new": ["1 of the 3 incidents raised from stored runs when this page was generated came from this page's reports"]},
    "run[held-b]/case.html": {"new": ["1 of the 3 incidents raised from stored runs when this page was generated came from this page's reports"]},
    "run[r11]/answer.html": {"gone": ["all incidents", "the reference topology check (verifier/verify_topology.py) is not shipped by any distribution at the pinned commit, so it was not run", "the report it came from"]},
    "run[r11]/case.html": {"gone": ["all incidents", "the reference topology check (verifier/verify_topology.py) is not shipped by any distribution at the pinned commit, so it was not run", "the report it came from"]},
}
for _page, _kinds in _NO_TOPOLOGY_INCIDENT_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _NO_TOPOLOGY_INCIDENT))
#: The authorization row in plain words, naming no internal or draft vocabulary.
#: Generated from the measured difference by tooling, not typed.
_PLAIN_AUTHORIZATION = "the authorization row says this console does not record authorization"
_PLAIN_AUTHORIZATION_PAGES: dict[str, dict[str, list[str]]] = {
    "home.html + counts.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
    "run[forged]/case.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
    "run[held-a]/case.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
    "run[held-b]/case.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
    "run[preview]/case.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
    "run[r11]/case.html": {"gone": ["No records \u00b7 needs an AADP policy engine"], "new": ["No records \u00b7 This console does not record authorization."]},
}
for _page, _kinds in _PLAIN_AUTHORIZATION_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _PLAIN_AUTHORIZATION))
#: On one line: nb2-base's records agree (step 2) and nb2-cand
#: contradicts. Generated from the measured difference by tooling, not typed.
_STEP2_AND_B2 = "step 2 and B2: one run's records agree, and nb2-cand contradicts"
_STEP2_AND_B2_PAGES: dict[str, dict[str, list[str]]] = {
    "home.html + counts.html": {"gone": ["0 of 4 \u00b7 3 held without their output files required \u00b7 0 couldn't check \u00b7 1 contradict \u00b7 0 not checked"], "new": ["1 of 4 \u00b7 1 held without its output files required \u00b7 0 couldn't check \u00b7 2 contradict \u00b7 0 not checked"]},
}
for _page, _kinds in _STEP2_AND_B2_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _STEP2_AND_B2))
#: The Diff page's text diff is the comparison's own stored run of `onetrace diff
#: --text --json --no-follow`, drawn as the SDK wrote it: the limit it shows, its command, and -- on
#: the forged pair, which the SDK refuses -- the SDK's own reason. Measured, not typed.
_TEXTDIFF_29KT = "the text diff, the comparison's own stored run"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Command: python -m onetrace diff RUN_A RUN_B --text --json --no-follow",
     "Shown with at most 200 lines per output (the SDK's default).",
     "refused: no text is shown"], _TEXTDIFF_29KT))
#: The Overview's anchoring rung counts what each run's
#: own page reads from this console's check, in the fixed words, zeros left out; All counts gains
#: one count per form, each with its denominator. Measured, not typed.
_OVERVIEW_29KZ = "the Overview's anchoring row, counted as each run's page reads it"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["0 runs of 4 \u2014 committed by a known time: couldn't check, as each run's own page says",
     "0 runs of 4 \u2014 committed by a known time: not checked, with no check of this console's whose rows the run's page reads",
     "0 runs of 4 \u2014 committed by a known time: the check failed, as each run's own page says",
     "0 runs of 4 \u2014 committed by a known time: yes, as each run's own page says",
     "4 not anchored",
     "4 runs of 4 \u2014 committed by a known time: not anchored, as each run's own page says",
     "Committed by a known time?"], _OVERVIEW_29KZ))
#: The Signed half: the run ladder's signing rung reads the check's own signature
#: rows; on these runs, with none, Unsigned. Measured, not typed.
_SIGNED_C18E5_22 = "Signed by a known recorder, read from the check's own signature rows"
for _page in ['run[forged]/case.html', 'run[held-a]/case.html', 'run[held-b]/case.html', 'run[preview]/case.html', 'run[r11]/case.html']:
    EXPLAINED.setdefault(_page, {}).setdefault("gone", {})[
        "Not yet available · records are unsigned in this release"] = _SIGNED_C18E5_22
    EXPLAINED.setdefault(_page, {}).setdefault("new", {})[
        "Unsigned · no signature beside the chain"] = _SIGNED_C18E5_22
#: The SDK's text names a missing run id "(no run id)" since the third development
#: build, in its refused diff and localize layers on the forged pair. The SDK's words, shown as
#: written (B1). Measured, not typed.
_NO_RUN_ID_29KK = "the SDK's text writes '(no run id)' for a missing run id"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) (no run id) (run) diff: refused — does not verify: (the candidate run's folder) REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) (no run id) (run) localize: refused — does not verify: (the candidate run's folder) REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked"], _NO_RUN_ID_29KK))
#: The Overview's signing rung counts what each run's own page reads from this
#: console's check, in the fixed words, zeros left out; All counts gains one count per form, each
#: over all runs stored. Measured, not typed.
_OVERVIEW_29LK = "the Overview's signing row, counted as each run's page reads it"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("gone", {}).update(dict.fromkeys(
    ['Signed by a known recorder', 'not yet available · records are unsigned in this release'], _OVERVIEW_29LK))
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["0 runs of 4 — signed by a known recorder: couldn't check, as each run's own page says", "0 runs of 4 — signed by a known recorder: key not trusted, as each run's own page says", "0 runs of 4 — signed by a known recorder: not checked, as each run's own page says", "0 runs of 4 — signed by a known recorder: the check failed, as each run's own page says", "0 runs of 4 — signed by a known recorder: yes, as each run's own page says", "4 runs of 4 — signed by a known recorder: unsigned, as each run's own page says", '4 unsigned', 'Signed by a known recorder?'], _OVERVIEW_29LK))
#: The Overview's banner states a fact about the stored runs, in the fixed words, shown
#: only when none reads Yes on "Signed by a known recorder?" (none of these fixture runs is signed).
#: Measured, not typed.
_BANNER_29LM = "the unsigned banner as a statement about the stored runs"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("gone", {}).update(dict.fromkeys(
    ['Records are unsigned in this release. The check reads each record against itself, as far as its checks reach; nothing here yet shows who wrote them.'], _BANNER_29LM))
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ['None of these runs is signed by a key you trust: nothing here shows who wrote them.'], _BANNER_29LM))
#: The page polish before the release: text and layout only, each page stating the same facts.
#: Every footer names one product and version, as the console's frame does. Measured, not typed.
_FOOTER_POLISH = 'every footer names onetrace-console and its version'
#: Each step's receipt is named for its step. Measured, not typed.
_RECEIPT_POLISH = 'each receipt named for its step'
#: The reason every step shares is said once above the step table. Measured, not typed.
_SHARED_POLISH = 'the shared reason said once above the step table'
#: A step's start and end are one line, each in its <time>. Measured, not typed.
_TIMES_POLISH = "a step's times as one line, the date said once"
#: No developer wording: the comparison's heading, its envelope without the exit code, and
#: the Overview's records-agree words. Measured, not typed.
_WORDS_POLISH = 'plain words in place of developer wording'
EXPLAINED.setdefault('diff[held-a,held-b]', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('diff[held-a,held-b]', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-all.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-all.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-changed-vs-baseline.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-changed-vs-baseline.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-contradicts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-contradicts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-could-not-check.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-could-not-check.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-holds.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-holds.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-a-declared-stage.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-a-declared-stage.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-not-established.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-not-established.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-most-recent.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-most-recent.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-needs-attention.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-needs-attention.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-not-checked.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-not-checked.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-nothing-missing.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-nothing-missing.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p1.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p1.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p2.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p2.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-records-agree.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-records-agree.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-run-id-reused.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-run-id-reused.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-contradicts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-contradicts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-could-not-check.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-could-not-check.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-header-disagrees.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-header-disagrees.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-runid-reused.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-runid-reused.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/failed', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/failed', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unchecked', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unchecked', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unreadable', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unreadable', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-issuer-rule.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-issuer-rule.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-denied.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-denied.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-executed.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-executed.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-proposed.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-proposed.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-08d1-4b41-a649-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-08d1-4b41-a649-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-6972-457f-a26d-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-6972-457f-a26d-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-bdc3-4a22-bb79-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-bdc3-4a22-bb79-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-c0dd-4040-b704-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-c0dd-4040-b704-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-cfd0-494e-b98e-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-cfd0-494e-b98e-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console 0.1.0."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["The receipt for this step"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-a]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["The receipt for this step"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-b]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["The receipt for this step"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 2 · alpha", "Receipt · step 2 of 2 · beta"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["The receipt for this step"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 9 · document in", "Receipt · step 2 of 9 · converted", "Receipt · step 3 of 9 · cleaned", "Receipt · step 4 of 9 · split", "Receipt · step 5 of 9 · embedded", "Receipt · step 6 of 9 · indexed", "Receipt · step 7 of 9 · retrieved", "Receipt · step 8 of 9 · prompt built", "Receipt · step 9 of 9 · answer"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[r11]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 3 · zeta", "Receipt · step 2 of 3 · alpha", "Receipt · step 3 of 3 · join"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["The receipt for this step"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Receipt · step 1 of 3 · zeta", "Receipt · step 2 of 3 · alpha", "Receipt · step 3 of 3 · join"], _RECEIPT_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made."], _SHARED_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["<time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["<time> → <time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["<time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["<time> → <time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["<time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["<time> → <time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["<time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["<time> → <time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["<time>"], _TIMES_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["<time> → <time>"], _TIMES_POLISH))
EXPLAINED.setdefault('diff[held-a,held-b]', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Repeat it without us:", "diff"], _WORDS_POLISH))
EXPLAINED.setdefault('diff[held-a,held-b]', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Repeat this yourself:", "The comparison was refused. — does not verify: (the candidate run's folder)", "What changed between the two runs", "localize: refused — does not verify: (the candidate run's folder)"], _WORDS_POLISH))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["1 run of 4 — whose records agree: the check held, with the run's output files present", "Verified: the check held, with the run's output files present."], _WORDS_POLISH))
#: page -> why it is new
#: The viewer moved into the console, so the command a run page prints to regenerate itself names
#: `onetrace_console.viewer`, the module that runs it. Generated from the measured difference.
_VIEWER_MODULE = "the regenerate command names the viewer's module in the console"
for _page in (
    'run[forged]/answer.html',
    'run[forged]/case.html',
    'run[held-a]/answer.html',
    'run[held-a]/case.html',
    'run[held-b]/answer.html',
    'run[held-b]/case.html',
    'run[preview]/case.html',
    'run[r11]/answer.html',
    'run[r11]/case.html',
):
    EXPLAINED.setdefault(_page, {}).setdefault("new", {})['python -m onetrace_console.viewer generate RUN_FOLDER --cli --out OUT_FOLDER'] = _VIEWER_MODULE

#: The first-impression polish: each verdict shown by its plain word (Verified, Contradicts its
#: record, Couldn't check), the run-id flag said in words, and on the incident pages the names of
#: stored fields and values drawn as code. Generated from the measured difference.
_PLAIN_WORDS = "verdicts and flags in plain words; stored names drawn as code"
_PLAIN_WORDS_PAGES: dict[str, dict[str, list[str]]] = {
    'home.html + counts.html': {'gone': ['0 runs of 4 — no verdict recorded', '0 runs of 4 — verdict: could_not_check', "1 run of 4 — runs flagged 'run_id reused'", 'no verdict recorded', 'verdict: contradicts', 'verdict: could_not_check'], 'new': ["0 runs of 4 — Couldn't check", '0 runs of 4 — No verdict recorded', '1 run of 4 — whose run id was already used by a stored run', '2 runs of 4 — Contradicts its record', '2 runs of 4 — Verified', 'Contradicts its record', 'No verdict recorded', 'Verified']},
    'incidents-i-contradicts.html': {'gone': ["the verifier's report carries a failing row. Raised when the run's recorded verdict is `contradicts`. Source: the run's stored verifier report (`check_report`), field `stdout`, its `[FAIL ]` rows, or all of it where the rows cannot be read line by line."], 'new': ["the verifier's report carries a failing row. Raised when the run's recorded verdict is contradicts. Source: the run's stored verifier report (check_report), field stdout, its [FAIL ] rows, or all of it where the rows cannot be read line by line."]},
    'incidents-i-could-not-check.html': {'gone': ["a check was not run, and the record says why. Raised when the runner recorded a check it did not run, with a stated reason. Source: the check runner's record on the run, field `check_note` and `topology_note`."], 'new': ["a check was not run, and the record says why. Raised when the runner recorded a check it did not run, with a stated reason. Source: the check runner's record on the run, field check_note and topology_note."]},
    'incidents-i-header-disagrees.html': {'gone': ["the delivery's header contradicted its own manifest. Raised when the store flagged that a delivery header disagrees with the manifest. Source: the run's own record, as the store wrote it, field `flags`, the header entry."], 'new': ["the delivery's header contradicted its own manifest. Raised when the store flagged that a delivery header disagrees with the manifest. Source: the run's own record, as the store wrote it, field flags, the header entry."]},
    'incidents-i-runid-reused.html': {'gone': ["two chains arrived under one run name. Raised when the store flagged 'run_id reused' at ingest. Source: the run's own record, as the store wrote it, field `flags`, the `run_id reused` entry."], 'new': ["two chains arrived under one run name. Raised when the store flagged 'run_id reused' at ingest. Source: the run's own record, as the store wrote it, field flags, the run_id reused entry."]},
    'incidents.html': {'gone': ["the verifier's report carries a failing row. Raised when the run's recorded verdict is `contradicts`. this rule's list"], 'new': ["the verifier's report carries a failing row. Raised when the run's recorded verdict is contradicts. this rule's list"]},
}
for _page, _kinds in _PLAIN_WORDS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _PLAIN_WORDS))

#: The overview's cards lead with one short line each, the count with its denominator; what the
#: count rests on moves to the card's muted lines, in the words the longer lead carried.
#: Generated from the measured difference.
_SHORT_LEADS = "each overview card leads with one short line; its detail is the line below"
_SHORT_LEADS_PAGES: dict[str, dict[str, list[str]]] = {
    'home.html + counts.html': {'gone': ['4 runs stored, in 2 pipelines', 'A pipeline here is a declared stage list: runs that declare the same stages, in the same order. No record names its pipeline.', 'This console keeps no open or closed state for an incident, so none is called open.'], 'new': ['0 of 4 runs changed vs baseline', '1 of 4 runs verified', '3 incidents', '3 incidents raised from 2 of 4 runs. This console keeps no open or closed state for an incident, so none is called open.', '4 runs stored', 'Changed: the run was the candidate in a stored comparison that found a first difference.', 'Stored in 2 pipelines. A pipeline here is a declared stage list: runs that declare the same stages, in the same order. No record names its pipeline.', "Verified: the check held, with the run's output files required (--require-artifacts)."]},
}
for _page, _kinds in _SHORT_LEADS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _SHORT_LEADS))

#: A "Not checked" reason every step shares is said once for the run ("Every step"), and only
#: reasons that differ are listed per step. Generated from the measured difference.
_ONCE = "a reason every step shares is said once for the run"
_ONCE_PAGES: dict[str, dict[str, list[str]]] = {
    'run[forged]/case.html': {'new': ['Every step — Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made.']},
    'run[held-a]/case.html': {'gone': ["step 1 of 2 · alpha — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 2 of 2 · beta — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], 'new': ['Every step — Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made.']},
    'run[held-b]/case.html': {'gone': ["step 1 of 2 · alpha — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 2 of 2 · beta — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], 'new': ['Every step — Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made.']},
    'run[preview]/case.html': {'new': ["Every step — Could not be checked from here, and the check says why: 'stage-receipt/0.0-preview': the pre-standard preview literal, which draft-00 section 14 reads as a version this verifier does not implement; content not checked"]},
    'run[r11]/case.html': {'gone': ["step 1 of 3 · zeta — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 2 of 3 · alpha — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made.", "step 3 of 3 · join — Held under the checks that ran; not anchored, so it can't be shown to be the record that was made."], 'new': ['Every step — Held under the checks that ran; not anchored, so none of these steps can be shown to be the record that was made.']},
}
for _page, _kinds in _ONCE_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _ONCE))

#: Where space is tight (the needs-attention list) a time reads YYYY-MM-DD HH:MM UTC; tables and the
#: receipt keep the full ISO timestamp. Generated from the measured difference.
_SHORT_TIME = "the needs-attention list says a time as YYYY-MM-DD HH:MM UTC"
_SHORT_TIME_PAGES: dict[str, dict[str, list[str]]] = {
    'home.html + counts.html': {'gone': ['Contradicts itself · nb2-cand · <time>'], 'new': ['Contradicts itself · nb2-cand · <time> UTC']},
}
for _page, _kinds in _SHORT_TIME_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _SHORT_TIME))

#: A run page's banner is a headline: its "checked on" time reads YYYY-MM-DD HH:MM UTC, the full
#: value kept in the <time> element. Generated from the measured difference.
_BANNER_TIME = "the run page banner says its time in the short form"
_BANNER_TIME_PAGES: dict[str, dict[str, list[str]]] = {
    'run[forged]/answer.html': {'new': ["This answer's trail was checked on <time> UTC — the record contradicts itself at step 1."]},
    'run[forged]/case.html': {'new': ["No · This answer's trail was checked on <time> UTC — the record contradicts itself at step 1.", "This answer's trail was checked on <time> UTC — the record contradicts itself at step 1."]},
    'run[held-a]/answer.html': {'gone': ["This answer's trail was checked on <time> — each check that ran held."], 'new': ["This answer's trail was checked on <time> UTC — each check that ran held."]},
    'run[held-a]/case.html': {'gone': ["This answer's trail was checked on <time> — each check that ran held."], 'new': ["This answer's trail was checked on <time> UTC — each check that ran held."]},
    'run[held-b]/answer.html': {'new': ["This answer's trail was checked on <time> UTC — the record contradicts itself at step 1."]},
    'run[held-b]/case.html': {'new': ["No · This answer's trail was checked on <time> UTC — the record contradicts itself at step 1.", "This answer's trail was checked on <time> UTC — the record contradicts itself at step 1."]},
    'run[preview]/case.html': {'new': ["Couldn't check · This answer's trail was checked on <time> UTC — it was not verified: a receipt names a format the check does not implement, so the check did not read its contents.", "This answer's trail was checked on <time> UTC — it was not verified: a receipt names a format the check does not implement, so the check did not read its contents."]},
    'run[r11]/answer.html': {'gone': ["This answer's trail was checked on <time> — each check that ran held."], 'new': ["This answer's trail was checked on <time> UTC — each check that ran held."]},
    'run[r11]/case.html': {'gone': ["This answer's trail was checked on <time> — each check that ran held."], 'new': ["This answer's trail was checked on <time> UTC — each check that ran held."]},
}
for _page, _kinds in _BANNER_TIME_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _BANNER_TIME))

NEW_PAGES: dict[str, str] = {
    "executions-signed-couldnt-check.html": "the runs one signing count counted",
    "executions-signed-failed.html": "the runs one signing count counted",
    "executions-signed-not-checked.html": "the runs one signing count counted",
    "executions-signed-unsigned.html": "the runs one signing count counted",
    "executions-signed-untrusted.html": "the runs one signing count counted",
    "executions-signed-yes.html": "the runs one signing count counted",
    "executions-anchored-yes.html": "the runs one anchoring count counted",
    "executions-anchored-couldnt-check.html": "the runs one anchoring count counted",
    "executions-anchored-failed.html": "the runs one anchoring count counted",
    "executions-anchored-not-anchored.html": "the runs one anchoring count counted",
    "executions-anchored-not-checked.html": "the runs one anchoring count counted",
    "comparisons.html": "the Comparisons index, an approved addition",
    "counts.html": "the All counts page, the Overview's counts moved whole",
    "run[forged]/stage-1.html": "a stage's inputs and outputs, board 4",
    "run[forged]/stage-2.html": "a stage's inputs and outputs, board 4",
    "run[held-a]/stage-1.html": "a stage's inputs and outputs, board 4",
    "run[held-a]/stage-2.html": "a stage's inputs and outputs, board 4",
    "run[held-b]/stage-1.html": "a stage's inputs and outputs, board 4",
    "run[held-b]/stage-2.html": "a stage's inputs and outputs, board 4",
    "run[r11]/stage-1.html": "a stage's inputs and outputs, board 4",
    "run[r11]/stage-2.html": "a stage's inputs and outputs, board 4",
    "run[r11]/stage-3.html": "a stage's inputs and outputs, board 4",
    "run[forged]/receipt.html": "the run receipt, board 5",
    "run[held-a]/receipt.html": "the run receipt, board 5",
    "run[held-b]/receipt.html": "the run receipt, board 5",
    "run[r11]/receipt.html": "the run receipt, board 5",
}


@pytest.fixture(scope="module")
def now(tmp_path_factory):
    from tools.visible_text import pages
    return pages(tmp_path_factory.mktemp("visible-text"))


@pytest.fixture(scope="module")
def before():
    return json.loads(BASELINE.read_text(encoding="utf-8"))


#: A row of the verifier's output, as it prints one: "[PASS ] ...", "[FAIL ] ...", "[NOT-RUN] ...".
_VERIFIER_ROW = re.compile(r"\[[A-Z][A-Z-]* *\] ")
#: The verifier's path, wherever the venv is: anything up to `onetrace_verify/verify.py`.
_VERIFIER_PATH = re.compile(r"\S*onetrace_verify[/\\]verify\.py")
#: A line ending in the verifier's output, as the pages escape it. Text mode on Windows adds a CR
#: before EVERY LF the verifier writes, including one inside data it echoes (a forged digest's CR
#: LF arrives as CR CR LF), so one or more CRs before an LF go.
_VERIFIER_EOL = re.compile(r"(?:\\u000d)+\\u000a")


def _machine_free(block: str) -> str:
    """`block` without the two things that belong to the machine."""
    if _VERIFIER_ROW.search(block):
        block = _VERIFIER_EOL.sub(r"\\u000a", block)
    return _VERIFIER_PATH.sub("<verifier>", block)


def _grouped(snapshot: dict[str, list[str]]) -> dict[str, Counter]:
    groups = {page: Counter(_machine_free(b) for b in blocks) for page, blocks in snapshot.items()}
    for src, dst in MOVED:
        merged = groups.pop(src, Counter()) + groups.pop(dst, Counter())
        groups[f"{src} + {dst}"] = merged
    return groups


def test_no_page_is_lost_and_every_new_page_is_declared(now, before, examined):
    examined(len(before), "pages in the baseline")
    lost = sorted(set(before) - set(now))
    assert not lost, f"pages that no longer exist: {lost}"
    undeclared = sorted(set(now) - set(before) - set(NEW_PAGES))
    assert not undeclared, f"new pages not declared in NEW_PAGES: {undeclared}"


def test_every_page_states_what_it_stated_before(now, before, examined):
    was, is_ = _grouped(before), _grouped({p: b for p, b in now.items() if p in before
                                           or any(p in pair for pair in MOVED)})
    examined(sum(len(v) for v in before.values()), "text blocks in the baseline")
    problems = []
    for page in sorted(was):
        explained = EXPLAINED.get(page, {})
        gone = was[page] - is_.get(page, Counter())
        new = is_.get(page, Counter()) - was[page]
        for block in sorted(gone):
            if block not in explained.get("gone", {}):
                problems.append(f"{page}: GONE  {block[:160]!r}")
        for block in sorted(new):
            if block not in explained.get("new", {}):
                problems.append(f"{page}: NEW   {block[:160]!r}")
    assert not problems, (f"{len(problems)} unexplained text differences:\n" + "\n".join(problems[:60]))


def test_the_baseline_is_the_tool_s_own_output_format(before, examined):
    examined(len(before), "baseline pages")
    assert all(isinstance(v, list) and v == sorted(v) for v in before.values())
    assert len(before) == 49, len(before)


# ---------------------------------------------------------------------------------------------
# What belongs to the machine, normalised on both sides; nothing else.

PC_PATH = "../../../../../projects/onetrace-console/.venv/Lib/site-packages/onetrace_verify/verify.py"
POD_PATH = "../../../root/venvs/console/lib/python3.12/site-packages/onetrace_verify/verify.py"


@pytest.mark.parametrize("path", [PC_PATH, POD_PATH, "RUN_FOLDER/" + PC_PATH,
                                  r"C:\venv\Lib\site-packages\onetrace_verify\verify.py",
                                  "/opt/anywhere/onetrace_verify/verify.py"])
def test_the_verifier_path_is_the_same_token_wherever_the_venv_is(path):
    assert _machine_free(f"python3 {path} MANIFEST.json") == "python3 <verifier> MANIFEST.json"


def test_a_word_beside_the_verifier_path_still_counts():
    a = _machine_free(f"python -m viewer generate RUN_FOLDER --verifier RUN_FOLDER/{PC_PATH} --out OUT_FOLDER")
    b = _machine_free(f"python -m viewer generate RUN_FOLDER --verifier RUN_FOLDER/{POD_PATH} --out OUT_FOLDER")
    c = _machine_free(f"python -m viewer regenerate RUN_FOLDER --verifier RUN_FOLDER/{POD_PATH} --out OUT_FOLDER")
    assert a == b and a != c


def test_the_verifier_s_line_endings_are_one_on_every_platform():
    """Windows writes the verifier's stdout in text mode: every LF gains a CR -- including an LF
    inside data the verifier echoes, so a forged digest's own CR LF becomes CR CR LF there."""
    windows = r"[PASS ] manifest: chain link\u000d\u000a[FAIL ] a: expected sha256:ab\u000d\u000d\u000aX\u000d\u000a"
    linux = r"[PASS ] manifest: chain link\u000a[FAIL ] a: expected sha256:ab\u000d\u000aX\u000a"
    assert _machine_free(windows) == _machine_free(linux)


def test_a_crlf_outside_the_verifier_s_output_is_data_and_kept():
    """The console's own rendering of a forged digest carries its CR LF as escaped data
    (one-to-one escaping). That is not a line ending and is compared as it is."""
    forged = r"sha256:ab\u000d\u000aFORGED\u0009ROW\u000d\u000a0000"
    assert _machine_free(forged) == forged
    assert _machine_free(forged) != _machine_free(forged.replace(r"\u000d\u000a", r"\u000a"))


def test_nothing_else_is_normalised(before):
    plain = [b for blocks in before.values() for b in blocks
             if "onetrace_verify" not in b and not _VERIFIER_ROW.search(b)]
    assert plain and all(_machine_free(b) == b for b in plain)


def test_the_fixture_runs_arrive_in_a_fixed_order_whatever_the_clock(tmp_path, monkeypatch,
                                                                     examined):
    """The Overview labels pipelines P1, P2 ... by first arrival, read to the second, ties by run
    key. Left to the clock, a fast host stores every fixture run in one second, the tie falls to
    keys that change from build to build, and P1 and P2 swap: 26 "differences" on the pipeline
    and Overview pages in some builds and not others (canary's machine: 7 of 10 runs at 85950fd).
    So the tool gives each run a fixed arrival time, in the order it stores them, and r11 --
    first, as when the baseline was taken -- is P1 on every host. Here the clock is frozen at one
    second, the very case that raced."""
    from datetime import datetime, timezone

    import onetrace_console.ingest as ingest
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    from tools.visible_text import RECEIVED_AT, pages

    class OneSecond(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(ingest, "datetime", OneSecond)
    pages(tmp_path)
    store = Store(tmp_path / "store")
    arrived = sorted(r.received_at for r in store.runs())
    examined(len(arrived), "fixture runs, their arrival times read back from the store")
    assert arrived == list(RECEIVED_AT), arrived
    r11 = json.loads((REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes" / "MANIFEST.json")
                     .read_text(encoding="utf-8"))["run_id"]
    assert [r.run_id for r in pipelines(store)[0].runs] == [r11], "r11 alone is not P1"
