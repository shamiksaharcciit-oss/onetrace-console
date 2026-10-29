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
- `GONE_PAGES`: a page no longer drawn, on purpose, with why.

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

from onetrace_console import __version__

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
    "diff[held-a,held-b]": {"gone": ["#", "1", "2", "First difference", "First difference: stage 1 \u00b7 alpha.", "No recorded setting of it differs. Its output differs.", "No recorded settings or code digest at stage 1 \u00b7 alpha differs between the two runs, so there is no recorded change to look for elsewhere.", "No stage comes before it.", "Of the 1 stage after it, 0 differ, 1 is the same again.", "Same again", "The first difference is at stage 1 \u00b7 alpha. No smaller set was reported.", "Why stage 1 \u00b7 alpha's output differs is not established by this evidence.", "alpha", "baseline", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) nb2-cand (run) diff: diverged stage baseline candidate verdict -------------------------------------------------------------------- alpha <hex> ab\\u000d\\u00 FIRST DIFFERENCE beta <hex> <hex> reconverged first difference stage 1, 'alpha' comparisons performed 2; stages identical before the first difference 0 carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) nb2-cand (run) localize: diverged stage baseline candidate verdict -------------------------------------------------------------------- alpha <hex> ab\\u000d\\u00 FIRST DIFFERENCE beta <hex> <hex> reconverged first difference stage 1, 'alpha' comparisons performed 2; stages identical before the first difference 0 CAUSE at stage 1, 'alpha' instrument instrument unchanged config <hex> -> <hex> neither instrument nor config differs at the first difference; the difference is on the outputs upstream every stage before this one carries an identical output digest BLAST RADIUS COULD NOT CHECK \u2014 no chunk index found by digest among both runs' declared outputs carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "beta", "candidate", "diff: diverged (exit 1)", "localize: diverged (exit 1)", "no recorded setting differs", "result", "settings", "sha256:<hex>", "sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000", "stage"], "new": ["1 of the 4 incidents raised from stored runs when this page was generated came from this page's reports", "I-CONTRADICTS \u2014 run nb2-cand \u00b7 <hex>, field stdout[FAIL]", "The report names no localized set. That is what it says, not a gap in this page.", "[FAIL ] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000'", "all incidents", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) None (run) diff: refused \u2014 does not verify: (the candidate run's folder) REFUSED \u2014 candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) None (run) localize: refused \u2014 does not verify: (the candidate run's folder) REFUSED \u2014 candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [baseline] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/01-alpha.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] receipts/02-beta.json: originality -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "diff: refused \u2014 does not verify: (the candidate run's folder) (exit 3)", "localize: refused \u2014 does not verify: (the candidate run's folder) (exit 3)", "the report it came from"]},
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
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-all.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-all.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-changed-vs-baseline.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-changed-vs-baseline.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-contradicts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-contradicts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-could-not-check.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-could-not-check.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-holds.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-holds.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-a-declared-stage.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-a-declared-stage.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-not-established.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-missing-not-established.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-most-recent.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-most-recent.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-needs-attention.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-needs-attention.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-not-checked.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-not-checked.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-nothing-missing.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-nothing-missing.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p1.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p1.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p2.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-pipeline-p2.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-records-agree.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-records-agree.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-run-id-reused.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('executions-run-id-reused.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-contradicts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-contradicts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-could-not-check.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-could-not-check.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-header-disagrees.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-header-disagrees.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-runid-reused.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents-i-runid-reused.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('incidents.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/failed', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/failed', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unchecked', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unchecked', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unreadable', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('notice/unreadable', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-issuer-rule.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-issuer-rule.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-denied.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-denied.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-executed.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-executed.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-proposed.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy-verdict-proposed.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-08d1-4b41-a649-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-08d1-4b41-a649-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-6972-457f-a26d-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-6972-457f-a26d-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-bdc3-4a22-bb79-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-bdc3-4a22-bb79-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-c0dd-4040-b704-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-c0dd-4040-b704-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-cfd0-494e-b98e-<key>.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('policy/policy/<key>-cfd0-494e-b98e-<key>.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[forged]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-a]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[held-b]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[preview]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/answer.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/answer.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/authorization.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated <time> by onetrace-console."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/authorization.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Generated on <time> by onetrace viewer 0.1 (preview)."], _FOOTER_POLISH))
EXPLAINED.setdefault('run[r11]/case.html', {}).setdefault('new', {}).update(dict.fromkeys(
    [f"Generated <time> by onetrace-console {__version__}."], _FOOTER_POLISH))
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

#: The Overview's cards in 0.1.1's look: a one-line subtitle, the page's rule folded under "How
#: these counts work", each card's count with one short line and its definition behind a "?",
#: and the states at 0 folded into one line that still names each. Measured, not typed.
_OVERVIEW_011 = "the Overview's cards: one line under each count, the definitions folded"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("gone", {}).update(dict.fromkeys(
    ["The baseline is the run each was compared with; this console picks none. 3 of 4 runs are no comparison's candidate."], _OVERVIEW_011))
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["0 of 4 in the other states: Couldn't check, No verdict recorded", "2 of 4 Verified · 2 of 4 Contradicts its record", "3 incidents raised from 2 of 4 runs.", "3 of 4 runs are no comparison's candidate.", "?", "Below the count: each verdict the check recorded, as a count of runs; All counts has each in full.", "How these counts work", "Stored in 2 pipelines.", "The baseline is the run each was compared with; this console picks none.", "The runs delivered to this console, and what the evidence for each one establishes."], _OVERVIEW_011))

#: 0.1.1's colour rule: "Not anchored" is the anchoring rung's own state, evidence not made, never a
#: "No"; its evidence says what the check found, as the signing rung's does. Measured, not typed.
_NOT_ANCHORED_011 = "'Not anchored' as the anchoring rung's own state"
for _page in ["run[forged]/case.html", "run[held-a]/case.html", "run[held-b]/case.html", "run[preview]/case.html", "run[r11]/case.html"]:
    EXPLAINED.setdefault(_page, {}).setdefault("gone", {})["No · not anchored"] = _NOT_ANCHORED_011
    EXPLAINED.setdefault(_page, {}).setdefault("new", {})[
        "Not anchored · no anchor beside the chain"] = _NOT_ANCHORED_011

#: The SDK the comparison ran with is named as installed: 0.2.1 since console 0.1.1's pin, the
#: 0.2.0 line it replaces declared earlier. Measured, not typed.
_SDK_021 = "the comparison names the installed SDK, 0.2.1"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.2.1, build wheel:<hex>, at <time>."], _SDK_021))
#: 0.2.2 since console 0.2.0's pin. Measured, not typed.
_SDK_022 = "the comparison names the installed SDK, 0.2.2"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.2.2, build wheel:<hex>, at <time>."], _SDK_022))
#: 0.3.0 since the pins moved to its release candidate's wheels. Measured, not typed.
_SDK_030 = "the comparison names the installed SDK, 0.3.0"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.3.0, build wheel:<hex>, at <time>."], _SDK_030))
#: Since 0.3.0 the SDK's text says a carried verifier line repeated on several receipts of one side
#: once, with the count; its JSON keeps each. The refused layers on the forged pair, as written.
#: Measured, not typed.
_CARRIED_030 = "the SDK's text says a carried line on several receipts of a side once, with the count"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) (no run id) (run) diff: refused — does not verify: (the candidate run's folder) REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline (the baseline run's folder) nb2-base (run) candidate (the candidate run's folder) (no run id) (run) localize: refused — does not verify: (the candidate run's folder) REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked"], _CARRIED_030))

#: Two times, each named: "Received" is when this console took a run in, and the run's own start
#: time, from its record, stands beside it under "Ran". Measured, not typed.
_TWO_TIMES = "the run's own time beside the time this console received it, each named"
_TWO_TIMES_PAGES: dict[str, dict[str, list[str]]] = {'home.html + counts.html': {'gone': ['Latest received', 'Received'], 'new': ['<time>', 'Contradicts itself · nb2-cand · received <time>', 'Latest received by this console', 'Ran', 'Received by this console']}}
for _page, _kinds in _TWO_TIMES_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _TWO_TIMES))

#: The runs lists in the console's words: "Every run stored here" or "The runs in this list" in
#: place of the free file's "The runs this page was given", and "When it ran" for "ran".
#: Measured, not typed.
_LIST_WORDS = "the runs lists say what they hold and when each run ran"
_LIST_WORDS_PAGES: dict[str, dict[str, list[str]]] = {
    'executions-all.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['Every run stored here', 'When it ran']},
    'executions-changed-vs-baseline.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-contradicts.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-could-not-check.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-holds.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-missing-a-declared-stage.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-missing-not-established.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-most-recent.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-needs-attention.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-not-checked.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-nothing-missing.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-pipeline-p1.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-pipeline-p2.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-records-agree.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
    'executions-run-id-reused.html': {'gone': ['The runs this page was given', 'ran'], 'new': ['The runs in this list', 'When it ran']},
}
for _page, _kinds in _LIST_WORDS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _LIST_WORDS))

#: The run page's head in place of the viewer's header: the run's id and pipeline as its title and
#: crumbs; its stages, its record's format, when it ran and when this console received it; four of
#: the ladder's rungs as the ladder states them; and tabs to the run's other pages. Measured, not
#: typed.
_RUN_HEAD = "the run page's head: who the run is, its two times, four rungs, its tabs"
_RUN_HEAD_PAGES: dict[str, dict[str, list[str]]] = {
    'run[forged]/case.html': {'gone': ['Case', 'The run, step by step', 'nb2-cand'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree No', 'Runs / P2 / nb2-cand', 'Signed by a known recorder Unsigned', 'nb2-cand · P2']},
    'run[held-a]/case.html': {'gone': ['Case', 'The run, step by step', 'nb2-base'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree Yes', 'Runs / P2 / nb2-base', 'Signed by a known recorder Unsigned', 'nb2-base · P2']},
    'run[held-b]/case.html': {'gone': ['Case', 'The run, step by step', 'nb2-cand'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree No', 'Runs / P2 / nb2-cand', 'Signed by a known recorder Unsigned', 'nb2-cand · P2']},
    'run[preview]/case.html': {'gone': ['Case', 'The run, step by step', 'ingest-r1-chunker-3.4'], 'new': ['9 of 9 declared stages · recorded in the format stage-receipt-chain/0.0-preview · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', "Records agree Couldn't check", 'Runs / P1 / ingest-r1-chunker-3.4', 'Signed by a known recorder Unsigned', 'ingest-r1-chunker-3.4 · P1']},
    'run[r11]/case.html': {'gone': ['Case', 'The run, step by step', 'dag-r37-r'], 'new': ['3 of 3 declared stages · recorded in the format stage-receipt-chain/0.1 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved Yes', 'Records agree Not checked', 'Runs / P1 / dag-r37-r', 'Signed by a known recorder Unsigned', 'dag-r37-r · P1']},
}
for _page, _kinds in _RUN_HEAD_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _RUN_HEAD))


#: The commands as a reader types them: the SDK's own, over the two run folders by their run ids,
#: in place of the stored placeholder form. Measured, not typed.
_TYPED_COMMANDS = "each command as a reader types it, over the two run folders"
_TYPED_COMMANDS_PAGES: dict[str, dict[str, list[str]]] = {'diff[held-a,held-b]': {'gone': ['python -m onetrace diff RUN_A RUN_B --out OUT', 'python -m onetrace localize RUN_A RUN_B --out OUT'], 'new': ['Command: onetrace diff runs/nb2-base runs/nb2-cand --text', 'onetrace diff runs/nb2-base runs/nb2-cand', 'onetrace localize runs/nb2-base runs/nb2-cand']}}
for _page, _kinds in _TYPED_COMMANDS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _TYPED_COMMANDS))

#: The graph's boxes as a list in reading order, which a narrow screen shows in place of the
#: drawing (hidden at full width; its words are the boxes' own). Measured, not typed.
_GRAPH_LIST = "the graph's boxes as a list, for a narrow screen"
_GRAPH_LIST_PAGES: dict[str, dict[str, list[str]]] = {'run[preview]/case.html': {'new': ['answer', 'cleaned', 'converted', 'document in', 'embedded', 'indexed', 'prompt built', 'retrieved', 'split']}}
for _page, _kinds in _GRAPH_LIST_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _GRAPH_LIST))

#: The runs lists' own table: the run, its pipeline, when it ran and when this console received it,
#: how far it got, and the three answers the store holds per run, each as its page says it; a list
#: with no run, one line. Measured, not typed.
_RUNS_TABLE = "the runs lists' own table, and one line where a list has no run"
_RUNS_TABLE_PAGES: dict[str, dict[str, list[str]]] = {
    'executions-all.html': {'gone': ['2', '3', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta', 'zeta → alpha → join'], 'new': ['2 of 2 declared stages', '3 of 3 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'Not checked', 'P1', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-changed-vs-baseline.html': {'gone': ['Run', 'Steps', 'What it was for'], 'new': ['No run is listed here.']},
    'executions-contradicts.html': {'gone': ['2', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta'], 'new': ['2 of 2 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned']},
    'executions-could-not-check.html': {'gone': ['Run', 'Steps', 'What it was for'], 'new': ['No run is listed here.']},
    'executions-holds.html': {'gone': ['3', 'Steps', 'What it was for', 'zeta → alpha → join'], 'new': ['2 of 2 declared stages', '3 of 3 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'Not anchored', 'Not checked', 'P1', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-missing-a-declared-stage.html': {'gone': ['Run', 'Steps', 'What it was for'], 'new': ['No run is listed here.']},
    'executions-missing-not-established.html': {'gone': ['Run', 'Steps', 'What it was for'], 'new': ['No run is listed here.']},
    'executions-most-recent.html': {'gone': ['2', '3', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta', 'zeta → alpha → join'], 'new': ['2 of 2 declared stages', '3 of 3 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'Not checked', 'P1', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-needs-attention.html': {'gone': ['2', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta'], 'new': ['2 of 2 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned']},
    'executions-not-checked.html': {'gone': ['Run', 'Steps', 'What it was for'], 'new': ['No run is listed here.']},
    'executions-nothing-missing.html': {'gone': ['2', '3', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta', 'zeta → alpha → join'], 'new': ['2 of 2 declared stages', '3 of 3 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'Not checked', 'P1', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-pipeline-p1.html': {'gone': ['3', '<time> → <time>', 'Steps', 'What it was for', 'zeta → alpha → join'], 'new': ['3 of 3 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'Not anchored', 'Not checked', 'P1', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned']},
    'executions-pipeline-p2.html': {'gone': ['2', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta'], 'new': ['2 of 2 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-records-agree.html': {'gone': ['Steps', 'What it was for'], 'new': ['2 of 2 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'Not anchored', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned', 'Yes']},
    'executions-run-id-reused.html': {'gone': ['2', '<time> → <time>', 'Steps', 'What it was for', 'alpha → beta'], 'new': ['2 of 2 declared stages', '<time>', 'Committed by a known time', 'How far it got', 'No', 'Not anchored', 'P2', 'Pipeline', 'Received by this console', 'Records agree', 'Signed by a known recorder', 'Unsigned']},
}
for _page, _kinds in _RUNS_TABLE_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _RUNS_TABLE))

#: The answer and authorization pages carry the run page's head (the authorization page without its
#: four answers, as it must never read as a pass). Measured, not typed.
_PAGE_HEADS = "the run's head on its answer and authorization pages"
_PAGE_HEADS_PAGES: dict[str, dict[str, list[str]]] = {
    'run[forged]/answer.html': {'gone': ['Answer', 'Where this answer came from', 'nb2-cand'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree No', 'Runs / P2 / nb2-cand', 'Signed by a known recorder Unsigned', 'nb2-cand · P2']},
    'run[forged]/authorization.html': {'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Runs / P2 / nb2-cand', 'nb2-cand · P2']},
    'run[held-a]/answer.html': {'gone': ['Answer', 'Where this answer came from', 'nb2-base'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree Yes', 'Runs / P2 / nb2-base', 'Signed by a known recorder Unsigned', 'nb2-base · P2']},
    'run[held-a]/authorization.html': {'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Runs / P2 / nb2-base', 'nb2-base · P2']},
    'run[held-b]/answer.html': {'gone': ['Answer', 'Where this answer came from', 'nb2-cand'], 'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved a straight-line run: there is no plan to compare', 'Records agree No', 'Runs / P2 / nb2-cand', 'Signed by a known recorder Unsigned', 'nb2-cand · P2']},
    'run[held-b]/authorization.html': {'new': ['2 of 2 declared stages · recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>', 'Runs / P2 / nb2-cand', 'nb2-cand · P2']},
    'run[r11]/answer.html': {'gone': ['Answer', 'Where this answer came from', 'dag-r37-r'], 'new': ['3 of 3 declared stages · recorded in the format stage-receipt-chain/0.1 · ran <time> · received by this console <time>', 'Committed by a known time Not anchored', 'Ran as approved Yes', 'Records agree Not checked', 'Runs / P1 / dag-r37-r', 'Signed by a known recorder Unsigned', 'dag-r37-r · P1']},
    'run[r11]/authorization.html': {'new': ['3 of 3 declared stages · recorded in the format stage-receipt-chain/0.1 · ran <time> · received by this console <time>', 'Runs / P1 / dag-r37-r', 'dag-r37-r · P1']},
}
for _page, _kinds in _PAGE_HEADS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _PAGE_HEADS))

#: The incidents lists draw a table -- the rule's chip, the run, its pipeline, when it was raised --
#: and each incident has its own page, which the chip opens. Measured, not typed.
_INCIDENT_TABLE = "the incidents lists' own table; each incident's quote moved to its own page"
_INCIDENT_TABLE_PAGES: dict[str, dict[str, list[str]]] = {
    'incidents-i-contradicts.html': {'gone': ['the report it came from'], 'new': ['<time>', 'Contradicts itself', 'Incident', 'P2', 'Pipeline', 'Raised', 'Run', 'nb2-cand · <hex>']},
    'incidents-i-runid-reused.html': {'gone': ['run_id reused', 'the report it came from'], 'new': ['<time>', 'Incident', 'P2', 'Pipeline', 'Raised', 'Run', 'Run id reused', 'nb2-cand · <hex>']},
    'incidents.html': {'gone': ['run_id reused', 'the report it came from'], 'new': ['<time>', 'Contradicts itself', 'Incident', 'P2', 'Pipeline', 'Raised', 'Run', 'Run id reused', 'nb2-cand · <hex>']},
}
for _page, _kinds in _INCIDENT_TABLE_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _INCIDENT_TABLE))
NEW_PAGES.update({
    "incidents/i-contradicts-<key>.html": "one incident's own page, the Check board",
    "incidents/i-runid-reused-<key>.html": "one incident's own page, the Check board",
})

#: "Ran as approved" in the runs list, as each run's own page reads it: the column's heading and
#: each run's state word. Generated from the measured difference by tooling, not typed.
_APPROVED_LISTED = "the runs list shows \"Ran as approved\", as each run's own page reads it"
_APPROVED_LISTED_PAGES: dict[str, dict[str, list[str]]] = {
    "executions-all.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-contradicts.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-holds.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-most-recent.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-needs-attention.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-nothing-missing.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-pipeline-p1.html": {"new": ["Ran as approved", "Yes"]},
    "executions-pipeline-p2.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-records-agree.html": {"new": ["Not a graph run", "Ran as approved"]},
    "executions-run-id-reused.html": {"new": ["Not a graph run", "Ran as approved"]},
}
for _page, _kinds in _APPROVED_LISTED_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _APPROVED_LISTED))

#: The panel below a pair says what it computes: other runs that recorded the same value, never
#: "the same change". Its heading, and the sentence it says where it can't read a first difference
#: (which the B2 block above had listed as new in its earlier words).
_RECORDED_VALUE = "the same-value panel's words: runs that recorded the same value"
_RECORDED_VALUE_PAGES: dict[str, dict[str, list[str]]] = {
    "diff[held-a,held-b]": {"gone": ["Other runs with the same change"],
                            "new": ["Other runs that recorded the same value",
                                    "This console can't read a first difference from this comparison's diff "
                                    "report, so it doesn't look for other runs that recorded the same value."]},
}
for _page, _kinds in _RECORDED_VALUE_PAGES.items():
    for _kind, _blocks in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_blocks, _RECORDED_VALUE))

#: A run stopped by a step's own rule: the r11 run's last step, join, declined ("inputs never
#: arrived: both roots refused"), so its pages carry the chip and the banner, the runs lists the chip,
#: and the Overview the count. Measured, not typed.
_STOPPED = "a run stopped by a step's own rule: its chip, its banner, and the Overview's count"
_STOPPED_PAGES: dict[str, dict[str, list[str]]] = {
    'executions-all.html': {'new': ['3 of 3 declared stages Declined at join']},
    'executions-holds.html': {'new': ['3 of 3 declared stages Declined at join']},
    'executions-most-recent.html': {'new': ['3 of 3 declared stages Declined at join']},
    'executions-nothing-missing.html': {'new': ['3 of 3 declared stages Declined at join']},
    'executions-pipeline-p1.html': {'new': ['3 of 3 declared stages Declined at join']},
    'home.html + counts.html': {'new': ['1 of 4 stopped by a step', '1 run of 4 — stopped by a step: a step declined by its own rule, and the run ended there']},
    'run[r11]/answer.html': {'new': ['Declined at join', 'The run stopped at join: the step declined by its own rule, and recorded why: inputs never arrived: both roots refused. No declared step was left without a receipt.']},
    'run[r11]/authorization.html': {'new': ['Declined at join']},
    'run[r11]/case.html': {'new': ['Declined at join', 'The run stopped at join: the step declined by its own rule, and recorded why: inputs never arrived: both roots refused. No declared step was left without a receipt.']},
}
for _page, _kinds in _STOPPED_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _STOPPED))
NEW_PAGES.update({
    "executions-stopped-by-a-step.html": "the list the Overview's count of runs stopped by a step opens",
})

#: A run stopped at a step's own rule: rung 3 reads "Not reached", counted on its own beside "missing
#: a declared stage", and the Overview's attention order names its group (the "last attempt
#: failed" block above had listed the order sentence as new in its earlier words). Measured, not typed.
_STOPPED_AT = "rung 3's \"Not reached\" for a run stopped at a step, its count, and its place in the order"
_STOPPED_AT_PAGES: dict[str, dict[str, list[str]]] = {
    "home.html + counts.html": {"new": [
        "0 runs of 4 \u2014 stopped at a step: the declared steps after it not reached",
        "Order: contradicts itself, then couldn't check, then not checked, then a declared stage missing, "
        "then last attempt failed, then stopped at a step, then changed vs baseline; newest first within each."]},
}
for _page, _kinds in _STOPPED_AT_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _STOPPED_AT))
NEW_PAGES.update({
    "executions-stopped-at-a-step.html": "the list rung 3's count of runs stopped at a step opens",
})
#: Each run's tabs gain "Choose as run A", its page as run A (the run-head blocks above had listed
#: the tabs as new in their earlier words). Measured, not typed.
_CHOOSE_TAB = "a run's tabs: Choose as run A"
for _page in ('run[forged]/answer.html', 'run[forged]/authorization.html', 'run[forged]/case.html', 'run[held-a]/answer.html', 'run[held-a]/authorization.html', 'run[held-a]/case.html', 'run[held-b]/answer.html', 'run[held-b]/authorization.html', 'run[held-b]/case.html', 'run[preview]/case.html', 'run[r11]/answer.html', 'run[r11]/authorization.html', 'run[r11]/case.html'):
    EXPLAINED.setdefault(_page, {}).setdefault("new", {})[
        "Graph Table Inputs & outputs Receipt Choose as run A"] = _CHOOSE_TAB
#: Choose two runs: a pipeline's runs as run A, and each run's page of the others as run B.
NEW_PAGES.update({
    "choose-p1.html": "choose two runs: the pipeline's runs, each choosing itself as run A",
    "choose-p2.html": "choose two runs: the pipeline's runs, each choosing itself as run A",
    "choose-p1-<key>.html": "choose two runs: run A's page, the other runs as run B",
    "choose-p2-<key>.html": "choose two runs: run A's page, the other runs as run B",
})

#: Fingerprints in text and tables, short: 12 hex characters, the whole value in a fold beside
#: them, read here as its own block. Measured, not typed.
_SHORT_FINGERPRINTS = "fingerprints shown by their first 12 hex characters, each whole in its fold"
_SHORT_FINGERPRINTS_PAGES: dict[str, dict[str, list[str]]] = {
    'incidents.html': {'gone': ['Rule table digest: <hex>. Rules not built:'], 'new': ['. Rules not built:', '<hex>', '<hex>…', 'Rule table digest:']},
    'run[forged]/answer.html': {'new': ["Checked — and the record contradicts itself here: output artifact 'a.json' matches — expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>….", 'sha256:<hex>…']},
    'run[forged]/case.html': {'new': ["Checked — and the record contradicts itself here: output artifact 'a.json' matches — expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>….", 'sha256:<hex>…', "step 1 of 2 · alpha — Checked — and the record contradicts itself here: output artifact 'a.json' matches — expected sha256:ab\\u000d\\u000aFORGED\\u0009ROW\\u000d\\u000a0000000000000000000000000000000000000000, found sha256:<hex>…."]},
    'run[held-a]/answer.html': {'new': ['sha256:<hex>…']},
    'run[held-a]/case.html': {'new': ['sha256:<hex>…']},
    'run[held-b]/answer.html': {'new': ['sha256:<hex>…']},
    'run[held-b]/case.html': {'new': ['sha256:<hex>…']},
    'run[preview]/case.html': {'new': ['sha256:<hex>…']},
    'run[r11]/answer.html': {'new': ['sha256:<hex>…']},
    'run[r11]/case.html': {'new': ['sha256:<hex>…']},
}
for _page, _kinds in _SHORT_FINGERPRINTS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _SHORT_FINGERPRINTS))

#: 0.4.0 since the pins moved to its development wheels. Measured, not typed.
_SDK_040 = "the comparison names the installed SDK, 0.4.0"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.4.0, build wheel:<hex>, at <time>."], _SDK_040))
#: 0.5.0 since the pins moved to its wheels. Measured, not typed.
_SDK_050 = "the comparison names the installed SDK, 0.5.0"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.5.0, build wheel:<hex>, at <time>."], _SDK_050))
#: 0.6.0 since the pins moved to its wheels (console 0.5.0). Measured, not typed.
_SDK_060 = "the comparison names the installed SDK, 0.6.0"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Compared with onetrace 0.6.0, build wheel:<hex>, at <time>."], _SDK_060))
#: The monitoring view, on a local console (console 0.5.0): its page, and its link on the Runs page.
#: Measured from the pages as drawn, not typed.
_MONITOR = "the monitoring view of each run's verdict against its pipeline's reference, on a local console (console 0.5.0)"
NEW_PAGES.update({"monitor.html": _MONITOR})
EXPLAINED.setdefault("executions-all.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ['Verdicts as runs arrive'], _MONITOR))
#: A benchmark's sentence, on a local console's run pages: its pipeline's runs are read against a
#: reference made from it (console 0.5.0). The pages measured from the run, the words the constant's.
_BENCHMARK_REFERENCE = "a benchmark's sentence says its pipeline's runs are read against a reference made from it (console 0.5.0)"
for _page in ['run[forged]/case.html + run[forged]/proof.html', 'run[held-a]/case.html + run[held-a]/proof.html', 'run[held-b]/case.html + run[held-b]/proof.html', 'run[preview]/case.html + run[preview]/proof.html', 'run[r11]/case.html + run[r11]/proof.html']:
    from onetrace_console.benchmarks import NOT_CORRECT as _NOT_CORRECT
    EXPLAINED.setdefault(_page, {}).setdefault("new", {}).update(dict.fromkeys([_NOT_CORRECT], _BENCHMARK_REFERENCE))
    EXPLAINED.setdefault(_page, {}).setdefault("gone", {}).update(dict.fromkeys(
        ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads "
         "differently for a marked run."], _BENCHMARK_REFERENCE))
#: Beside the local mark: what pressing it does to the pipeline's reference (console 0.5.0). Measured
#: from the pages as drawn, not typed.
_MARK_MOVES = "the local mark says it moves the pipeline's reference and every verdict in it (console 0.5.0)"
for _page, _texts in {'run[forged]/case.html + run[forged]/proof.html': ["Marking this run moves P2's reference: onetrace makes a new one from this run, and every verdict in P2 is then read against the new one."], 'run[held-a]/case.html + run[held-a]/proof.html': ["Marking this run moves P2's reference: onetrace makes a new one from this run, and every verdict in P2 is then read against the new one."], 'run[held-b]/case.html + run[held-b]/proof.html': ["Marking this run moves P2's reference: onetrace makes a new one from this run, and every verdict in P2 is then read against the new one."], 'run[preview]/case.html + run[preview]/proof.html': ["Marking this run moves P1's reference: onetrace makes a new one from this run, and every verdict in P1 is then read against the new one."], 'run[r11]/case.html + run[r11]/proof.html': ["Marking this run moves P1's reference: onetrace makes a new one from this run, and every verdict in P1 is then read against the new one."]}.items():
    EXPLAINED.setdefault(_page, {}).setdefault("new", {}).update(dict.fromkeys(_texts, _MARK_MOVES))
#: The Overview's authorization row: where each run's page reads it (console 0.5.0). Measured, not typed.
_AUTHORIZED_ROW = "the Overview's authorization row says where each run's page reads it (console 0.5.0)"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Read on each run's page from onetrace-verify's decisions rows, where the run declares a gated step or cites a decision; no records where it does neither."], _AUTHORIZED_ROW))
#: Console 0.4.0's new lines, measured from the pages as drawn (not typed), each group with its reason.
_WHAT_CHANGED_SECTION = "a run page's What changed? section: the comparison the stated rule picks, or no earlier run (console 0.4.0)"
_WHAT_CHANGED_SECTION_PAGES: dict[str, dict[str, list[str]]] = {"run[forged]/case.html + run[forged]/proof.html": {"new": ["Compared with nb2-cand, the most recent earlier run of this pipeline.", "What changed?"]}, "run[held-a]/case.html + run[held-a]/proof.html": {"new": ["No earlier run of this pipeline, so there is nothing to compare it with.", "What changed?"]}, "run[held-b]/case.html + run[held-b]/proof.html": {"new": ["Compared with nb2-base, the most recent earlier run of this pipeline.", "What changed?"]}, "run[preview]/case.html + run[preview]/proof.html": {"new": ["No earlier run of this pipeline, so there is nothing to compare it with.", "What changed?"]}, "run[r11]/case.html + run[r11]/proof.html": {"new": ["No earlier run of this pipeline, so there is nothing to compare it with.", "What changed?"]}}
for _page, _kinds in _WHAT_CHANGED_SECTION_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _WHAT_CHANGED_SECTION))
_COUNT_NOTES = "the i note beside each count of checks, read as text after the count: the verifier's rows that add up to it (console 0.4.0)"
_COUNT_NOTES_PAGES: dict[str, dict[str, list[str]]] = {"run[forged]/case.html + run[forged]/proof.html": {"new": ["step 1 of 2 · alpha — 24 checks made — all hold.ionetrace-verify's rows about receipts/01-alpha.json that held: 24. Not counted: 2 FAIL; 1 NOT-RUN.ionetrace-verify's rows that held, by what each checks: 24 on receipts/01-alpha.json + 27 on receipts/02-beta.json + 1 on manifest = 52. Not counted: 2 FAIL; 2 NOT-RUN. (The line shows 24.)", "step 2 of 2 · beta — 27 checks made — all hold.ionetrace-verify's rows about receipts/02-beta.json that held: 27. Not counted: 1 NOT-RUN."]}, "run[held-a]/case.html + run[held-a]/proof.html": {"gone": ["step 1 of 2 · alpha — 25 checks made — all hold.", "step 2 of 2 · beta — 27 checks made — all hold."], "new": ["Yes · 53 checks made — all hold.ionetrace-verify's rows that held, by what each checks: 25 on receipts/01-alpha.json + 27 on receipts/02-beta.json + 1 on manifest = 53. Not counted: 2 NOT-RUN.", "step 1 of 2 · alpha — 25 checks made — all hold.ionetrace-verify's rows about receipts/01-alpha.json that held: 25. Not counted: 1 NOT-RUN.", "step 2 of 2 · beta — 27 checks made — all hold.ionetrace-verify's rows about receipts/02-beta.json that held: 27. Not counted: 1 NOT-RUN."]}, "run[held-b]/case.html + run[held-b]/proof.html": {"gone": ["step 1 of 2 · alpha — 24 checks made — all hold.", "step 2 of 2 · beta — 26 checks made — all hold."], "new": ["step 1 of 2 · alpha — 24 checks made — all hold.ionetrace-verify's rows about receipts/01-alpha.json that held: 24. Not counted: 1 FAIL; 1 NOT-RUN.ionetrace-verify's rows that held, by what each checks: 24 on receipts/01-alpha.json + 26 on receipts/02-beta.json + 1 on manifest = 51. Not counted: 1 FAIL; 3 NOT-RUN. (The line shows 24.)", "step 2 of 2 · beta — 26 checks made — all hold.ionetrace-verify's rows about receipts/02-beta.json that held: 26. Not counted: 1 NOT-RUN."]}, "run[preview]/case.html + run[preview]/proof.html": {"new": ["step 1 of 9 · document in — 2 checks made — all hold.ionetrace-verify's rows about receipts/01-document-in.json that held: 2. Not counted: 1 NOT-RUN.ionetrace-verify's rows that held, by what each checks: 2 on receipts/01-document-in.json + 2 on receipts/02-converted.json + 2 on receipts/03-cleaned.json + 2 on receipts/04-split.json + 2 on receipts/05-embedded.json + 2 on receipts/06-indexed.json + 2 on receipts/07-retrieved.json + 2 on receipts/08-prompt-built.json + 2 on receipts/09-answer.json + 1 on manifest = 19. Not counted: 11 NOT-RUN. (The line shows 2.)", "step 2 of 9 · converted — 2 checks made — all hold.ionetrace-verify's rows about receipts/02-converted.json that held: 2. Not counted: 1 NOT-RUN.", "step 3 of 9 · cleaned — 2 checks made — all hold.ionetrace-verify's rows about receipts/03-cleaned.json that held: 2. Not counted: 1 NOT-RUN.", "step 4 of 9 · split — 2 checks made — all hold.ionetrace-verify's rows about receipts/04-split.json that held: 2. Not counted: 1 NOT-RUN.", "step 5 of 9 · embedded — 2 checks made — all hold.ionetrace-verify's rows about receipts/05-embedded.json that held: 2. Not counted: 1 NOT-RUN.", "step 6 of 9 · indexed — 2 checks made — all hold.ionetrace-verify's rows about receipts/06-indexed.json that held: 2. Not counted: 1 NOT-RUN.", "step 7 of 9 · retrieved — 2 checks made — all hold.ionetrace-verify's rows about receipts/07-retrieved.json that held: 2. Not counted: 1 NOT-RUN.", "step 8 of 9 · prompt built — 2 checks made — all hold.ionetrace-verify's rows about receipts/08-prompt-built.json that held: 2. Not counted: 1 NOT-RUN.", "step 9 of 9 · answer — 2 checks made — all hold.ionetrace-verify's rows about receipts/09-answer.json that held: 2. Not counted: 1 NOT-RUN."]}, "run[r11]/case.html + run[r11]/proof.html": {"gone": ["step 1 of 3 · zeta — 24 checks made — all hold.", "step 2 of 3 · alpha — 24 checks made — all hold.", "step 3 of 3 · join — 27 checks made — all hold."], "new": ["step 1 of 3 · zeta — 24 checks made — all hold.ionetrace-verify's rows about receipts/01-zeta.json that held: 24. Not counted: 1 NOT-RUN.ionetrace-verify's rows that held, by what each checks: 24 on receipts/01-zeta.json + 24 on receipts/02-alpha.json + 27 on receipts/03-join.json + 1 on edges conform to declared_edges + 1 on edges equal the edges derived from the receipts + 1 on manifest = 78. Not counted: 4 NOT-RUN. (The line shows 24.)", "step 2 of 3 · alpha — 24 checks made — all hold.ionetrace-verify's rows about receipts/02-alpha.json that held: 24. Not counted: 1 NOT-RUN.", "step 3 of 3 · join — 27 checks made — all hold.ionetrace-verify's rows about receipts/03-join.json that held: 27. Not counted: 1 NOT-RUN."]}}
for _page, _kinds in _COUNT_NOTES_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _COUNT_NOTES))
_FOLDERS_AS_GIVEN = "the SDK given the two runs' folders relative to where it runs (console 0.4.0): its words name b as given, no folder of this host"
_FOLDERS_AS_GIVEN_PAGES: dict[str, dict[str, list[str]]] = {"diff[held-a,held-b]": {"new": ["The comparison was refused. — does not verify: b", "baseline a nb2-base (run) candidate b (no run id) (run) diff: refused — does not verify: b REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "baseline a nb2-base (run) candidate b (no run id) (run) localize: refused — does not verify: b REFUSED — candidate does not verify: [FAIL] receipts/01-alpha.json: digest is sha256: and 64 lower-case hex -- outputs[0].digest: 'sha256:ab\\\\r\\\\nFORGED\\\\tROW\\\\r\\\\n0000000000000000000000000000000000000000' carried: [baseline] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] originality on 2 receipts -- record is declared unanchored; this verifier can establish consistency, not originality [candidate] [NOT-RUN] run: artifacts -- artifacts not present; output files not checked", "localize: refused — does not verify: b"]}}
for _page, _kinds in _FOLDERS_AS_GIVEN_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _FOLDERS_AS_GIVEN))
#: onetrace 0.4.0 records format 0.3: the runs made here say so in their header, and each receipt
#: quoted on a page names `stage-receipt/0.3` where it named 0.2; nothing else in them differs.
#: Measured, not typed.
_FORMAT_03 = "the runs made here are recorded in format 0.3, onetrace 0.4.0's"
_FORMAT_03_PAGES: dict[str, dict[str, list[str]]] = {"run[forged]/answer.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}, "run[forged]/authorization.html": {"new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>"]}, "run[forged]/case.html + run[forged]/proof.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}, "run[held-a]/answer.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}, "run[held-a]/authorization.html": {"new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>"]}, "run[held-a]/case.html + run[held-a]/proof.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-base\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}, "run[held-b]/answer.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}, "run[held-b]/authorization.html": {"new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>"]}, "run[held-b]/case.html + run[held-b]/proof.html": {"gone": ["{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.2\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"], "new": ["2 of 2 declared stages · recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "recorded in the format stage-receipt-chain/0.3 · ran <time> · received by this console <time>", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"complete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\",\"beta\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"b-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:<hex>\",\"media_type\":\"application/json\",\"name\":\"b.json\",\"trust_class\":\"operator-authored\"}],\"prev\":\"sha256:<hex>\",\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"2\",\"name\":\"beta\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}", "{\"anchor\":{\"reason\":\"a test\",\"state\":\"unanchored\"},\"assertions\":{},\"coverage\":{\"boundaries\":[],\"completeness\":\"incomplete\",\"declared_stages\":[\"alpha\",\"beta\"],\"emitting_stages\":[\"alpha\"]},\"digest_source\":\"emitter\",\"emission\":{\"gaps\":[],\"policy\":\"fail-closed\"},\"format\":\"stage-receipt/0.3\",\"inputs\":[],\"instrument\":{\"config_digest\":\"sha256:<hex>\",\"id\":\"a-tool\",\"kind\":\"transform\",\"manifest_digest\":\"sha256:<hex>\",\"rederivable\":\"true\",\"version\":\"1.0.0\"},\"outcome\":{\"class\":\"ok\"},\"outputs\":[{\"bytes\":\"9\",\"digest\":\"sha256:ab\\r\\nFORGED\\tROW\\r\\n0000000000000000000000000000000000000000\",\"media_type\":\"application/json\",\"name\":\"a.json\",\"trust_class\":\"operator-authored\"}],\"prev\":null,\"run_id\":\"nb2-cand\",\"stage\":{\"index\":\"1\",\"name\":\"alpha\"},\"time\":{\"ended\":\"<time>\",\"started\":\"<time>\"}}"]}}
for _page, _kinds in _FORMAT_03_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _FORMAT_03))

_RUN_TOOLS = ("the index's search box, on the Runs page and each run's page; a run's benchmark section, its mark and note; and \"Other runs with the same inputs\" under What changed? (console 0.5.0)")
_RUN_TOOLS_PAGES: dict[str, dict[str, list[str]]] = {"executions-all.html": {"new": ["Search", "Search the runs by recorded field"]}, "run[forged]/case.html + run[forged]/proof.html": {"new": ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads differently for a marked run.", "Benchmark", "Mark as benchmark", "Note (optional)", "Search", "Search the runs by recorded field"]}, "run[held-a]/case.html + run[held-a]/proof.html": {"new": ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads differently for a marked run.", "Benchmark", "Mark as benchmark", "Note (optional)", "Search", "Search the runs by recorded field"]}, "run[held-b]/case.html + run[held-b]/proof.html": {"new": ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads differently for a marked run.", "Benchmark", "Mark as benchmark", "Note (optional)", "Search", "Search the runs by recorded field"]}, "run[preview]/case.html + run[preview]/proof.html": {"new": ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads differently for a marked run.", "Benchmark", "Mark as benchmark", "Note (optional)", "Other runs with the same inputs: 0", "Search", "Search the runs by recorded field"]}, "run[r11]/case.html + run[r11]/proof.html": {"new": ["A benchmark is the run to compare against, not a statement that it is correct: no verdict reads differently for a marked run.", "Benchmark", "Mark as benchmark", "Note (optional)", "Search", "Search the runs by recorded field"]}}
for _page, _kinds in _RUN_TOOLS_PAGES.items():
    for _kind, _texts in _kinds.items():
        EXPLAINED.setdefault(_page, {}).setdefault(_kind, {}).update(dict.fromkeys(_texts, _RUN_TOOLS))

#: Each pipeline's drift page, against the first run and against each run's previous: what
#: `onetrace drift` reports over its stored runs.
NEW_PAGES.update({f"drift-{p}{m}.html": "a pipeline's drift page, as onetrace drift reports its runs"
                  for p in ("p1", "p2") for m in ("", "-previous")})

#: The comparison page's explanation panel, below the verdicts: its title, what it is, and its
#: two presses (the console finds onetrace-explain installed beside it). Measured, not typed.
_EXPLAIN_PANEL = "the comparison's suggested explanation panel, nothing asked for yet"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["A suggestion about this comparison's record from a model you configure for onetrace-explain, never a reading of it. The verdicts above are what they are without it. Nothing is sent until you press Explain.", "Explain Show the packet", "Suggested explanation"], _EXPLAIN_PANEL))
#: 0.3.2: the panel's heading is "What may have happened", and a local console's panel links to its
#: setup page. Measured, not typed.
_EXPLAIN_032 = "the explanation panel's 0.3.2 heading, and its link to the setup page"
EXPLAINED.setdefault("diff[held-a,held-b]", {}).setdefault("new", {}).update(dict.fromkeys(
    ["What may have happened", "Set up Explain"], _EXPLAIN_032))

@pytest.fixture(scope="module")
def now(tmp_path_factory, explain_command):
    """The pages as they read with onetrace-explain installed beside the console, whatever this
    environment holds: the panel's state is the one the ledger declares."""
    from onetrace_console import explain
    from tools.visible_text import pages
    with pytest.MonkeyPatch.context() as m:
        m.setattr(explain, "command", lambda: explain_command[0])
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


#: The Records agree card's line, in the rung's split: the runs verified (the check held with the
#: run's output files required), those held without them -- each count opening its own list -- and
#: the check's other verdicts. It replaces the check's "Verified", which the card's headline also
#: called verified with another count. Measured, not typed.
_AGREE_LINE = "the Records agree card's line in the rung's split: verified, and held without its output files"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ['1 of 4 verified · 1 of 4 held without its output files required · 2 of 4 Contradicts its record', "1 run of 4 — whose check held without the run's output files required"], _AGREE_LINE))
NEW_PAGES.update({
    "executions-held-without-output-files.html":
        "the list the Records agree card's count of runs held without their output files opens",
})


#: "Records agree", one reading per run: every page and count says each run's rung 1 as its own
#: page decides it, in rung 1's words, the reason said under not checked; the verifier's "Verified"
#: is no run-level summary's word; Needs attention lists the runs not checked, and those with no
#: verdict, in the order its sentence states. The check's verdict tally ("Verified") and its list
#: go; a list of runs with no verdict recorded is new. Measured by the tool, not typed.
_ONE_READING = "Records agree, one reading per run: rung 1's states everywhere, never the verifier's Verified"
EXPLAINED.setdefault('executions-holds.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Run", "Runs", "The runs", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "dag-r37-r", "nb2-base", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" executions-holds.html"], _ONE_READING))
EXPLAINED.setdefault('executions-needs-attention.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["3 of 3 declared stages Declined at join", "Not checked", "P1", "Runs in this list: 3 of 4 stored, and this page lists all 3. Nothing is summarised across runs on this page.", "Yes", "dag-r37-r"], _ONE_READING))
EXPLAINED.setdefault('executions-not-checked.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["3 of 3 declared stages Declined at join", "<time>", "Committed by a known time", "How far it got", "Not anchored", "Not checked", "P1", "Pipeline", "Ran as approved", "Received by this console", "Records agree", "Runs in this list: 1 of 4 stored, and this page lists it. Nothing is summarised across runs on this page.", "Signed by a known recorder", "Unsigned", "Yes", "dag-r37-r"], _ONE_READING))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('gone', {}).update(dict.fromkeys(
    ["2 runs of 4 — needing attention first, in the order stated on the Overview", "All 2 of them", "Each day's verdicts are counts of the runs received that day. A marker row between two days names a recorded settings or code digest that differs from the day before, in a pipeline with runs on both days.", "Needs attention first · 2 of 4 runs"], _ONE_READING))
EXPLAINED.setdefault('home.html + counts.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["0 of 1", "0 of 3", "0 of 4 in the other states: couldn't check, no verdict recorded", "0 runs of 4 — whose records couldn't be checked", "0 runs of 4 — with no verdict recorded", "1 of 4", "1 of 4 records agree · 2 of 4 contradict their record · 1 of 4 not checked (held without its output files required)", "1 of 4 runs whose records agree", "1 of 4 · 1 not checked (held without its output files required) · 0 couldn't check · 2 contradict their record · 0 no verdict recorded", "1 run of 4 — whose records were not checked", "2 runs of 4 — that contradict their record", "3 runs of 4 — needing attention first, in the order stated on the Overview", "All 3 of them", "Below the count: each run's \"Records agree\" as its own page reads it, as a count of runs; All counts has each in full.", "Each day's counts are counts of the runs received that day, each by its \"Records agree\" as its own page reads it. A marker row between two days names a recorded settings or code digest that differs from the day before, in a pipeline with runs on both days.", "Needs attention first · 3 of 4 runs", "Not checked", "Not checked (held without its output files required)", "Not checked · dag-r37-r · received <time>", "Order: contradicts itself, then couldn't check, then not checked, then no verdict recorded, then a declared stage missing, then last attempt failed, then stopped at a step, then changed vs baseline; newest first within each.", "Records agree", "Records agree: the check held, with the run's output files present.", "held without its output files required"], _ONE_READING))
NEW_PAGES.update({'executions-no-verdict.html': "the list of runs with no verdict recorded, rung 1's own state"})


#: Runs are folders, not chain heads: the incident rule for two run folders carrying the same run
#: and chain head whose files differ. It raises nothing here (no two fixture folders share a head),
#: so the Overview counts it at 0, the Incidents page lists it at 0 with its words, and its own
#: list page is new. Measured, not typed.
_HEAD_SHARED = "the incident rule for two run folders sharing a chain head whose files differ, at 0"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["0 runs of 4 — runs raising I-HEAD-SHARED"], _HEAD_SHARED))
EXPLAINED.setdefault("incidents.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["I-HEAD-SHARED — 0 runs of 4",
     "Two folders share a chain head but their contents differ. Raised when two run folders carry "
     "the same run and chain head, and their files differ. this rule's list"], _HEAD_SHARED))
NEW_PAGES.update({"incidents-i-head-shared.html": "the list of runs the new incident rule raised, "
                  "two run folders sharing a chain head whose files differ"})
#: Each run page in two linked views, "What changed" (the page's own address) and "Proof" (a page
#: beside it): the checks behind it -- what was checked and what was not, the check's own words,
#: and the authorization policy -- move whole to "Proof", so the two views are compared as one, and
#: each run's "Proof" is a new page.
_VIEWS = "each run page in two linked views, What changed and Proof"
for _run in ("r11", "held-a", "held-b", "forged", "preview"):
    MOVED.append((f"run[{_run}]/case.html", f"run[{_run}]/proof.html"))
    NEW_PAGES[f"run[{_run}]/proof.html"] = _VIEWS + ": the run page's Proof view"
    #: What was declared of the run page holds for its two views, compared as one.
    for _kind, _blocks in EXPLAINED.get(f"run[{_run}]/case.html", {}).items():
        EXPLAINED.setdefault(f"run[{_run}]/case.html + run[{_run}]/proof.html", {}).setdefault(
            _kind, {}).update(_blocks)
#: Each run page's two views, measured by the tool, not typed: the two tabs; the line of what
#: the records establish (red, and the verdicts on Proof, for a run that contradicts its record or
#: could not be checked); and the page's own foot (and the preview label), on both views.
_VIEWS_TABS = _VIEWS + ": the two tabs, What changed and Proof"
_VIEWS_LINE = _VIEWS + ": the line of what the records establish, from rung 1"
_VIEWS_BOTH = _VIEWS + ": the page's own foot and its preview label, on both views"
#: A red run's "What changed": the head without what it reads from the record, and one line
#: in its place; the head's count of declared stages is a block of its own (on "Proof" whole).
_VIEWS_WITHHELD = _VIEWS + ": a red run's head on What changed, without what it reads from the record"
EXPLAINED.setdefault('run[forged]/case.html + run[forged]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Not shown: this record does not hold up. Proof says why', 'recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>'], _VIEWS_WITHHELD))
EXPLAINED.setdefault('run[held-b]/case.html + run[held-b]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Not shown: this record does not hold up. Proof says why', 'recorded in the format stage-receipt-chain/0.2 · ran <time> · received by this console <time>'], _VIEWS_WITHHELD))
EXPLAINED.setdefault('run[preview]/case.html + run[preview]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Not shown: this record could not be checked. Proof says why', 'recorded in the format stage-receipt-chain/0.0-preview · ran <time> · received by this console <time>'], _VIEWS_WITHHELD))
EXPLAINED.setdefault('run[forged]/case.html + run[forged]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Regenerate this page", "Repeat the check — Run it from the run's folder:", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "Where this answer came from", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" proof.html"], _VIEWS_BOTH))
EXPLAINED.setdefault('run[forged]/case.html + run[forged]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Contradicts its record: this console's check, with the run's output files required, failed. The step-by-step comparison is not shown on this view: the record does not hold up. Proof says why", "These rows come from a record that does not hold up.", "The step-by-step verdicts are here, not on What changed: Contradicts its record: this console's check, with the run's output files required, failed."], _VIEWS_LINE))
EXPLAINED.setdefault('run[forged]/case.html + run[forged]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["What changedProof"], _VIEWS_TABS))
EXPLAINED.setdefault('run[held-a]/case.html + run[held-a]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Regenerate this page", "Repeat the check — Run it from the run's folder:", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "Where this answer came from", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" proof.html"], _VIEWS_BOTH))
EXPLAINED.setdefault('run[held-a]/case.html + run[held-a]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Records agree: this console's check held, with the run's output files required. Every check behind this is on Proof"], _VIEWS_LINE))
EXPLAINED.setdefault('run[held-a]/case.html + run[held-a]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["What changedProof"], _VIEWS_TABS))
EXPLAINED.setdefault('run[held-b]/case.html + run[held-b]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Regenerate this page", "Repeat the check — Run it from the run's folder:", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "Where this answer came from", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" proof.html"], _VIEWS_BOTH))
EXPLAINED.setdefault('run[held-b]/case.html + run[held-b]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Contradicts its record: this console's check, with the run's output files required, failed. The step-by-step comparison is not shown on this view: the record does not hold up. Proof says why", "These rows come from a record that does not hold up.", "The step-by-step verdicts are here, not on What changed: Contradicts its record: this console's check, with the run's output files required, failed."], _VIEWS_LINE))
EXPLAINED.setdefault('run[held-b]/case.html + run[held-b]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["What changedProof"], _VIEWS_TABS))
EXPLAINED.setdefault('run[preview]/case.html + run[preview]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Regenerate this page", "Repeat the check — Run it from the run's folder:", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "Where this answer came from", "preview format: 1 run shown here declare stage-receipt-chain/0.0-preview. The pinned verifier reads that format but does not perform the draft-00 checks on it, and says so in its own report.", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" proof.html"], _VIEWS_BOTH))
EXPLAINED.setdefault('run[preview]/case.html + run[preview]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Couldn't check: this console's check could not settle whether the records agree. The step-by-step comparison is not shown on this view: the record could not be checked. Proof says why", "These rows come from a record that could not be checked.", "The step-by-step verdicts are here, not on What changed: Couldn't check: this console's check could not settle whether the records agree."], _VIEWS_LINE))
EXPLAINED.setdefault('run[preview]/case.html + run[preview]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["What changedProof"], _VIEWS_TABS))
EXPLAINED.setdefault('run[r11]/case.html + run[r11]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Check it yourself", "Computed over this file with the fingerprint's own 64 characters set to zeros. To repeat it without us:", "Regenerate this page", "Repeat the check — Run it from the run's folder:", "This file's fingerprint: <hex>", "This record shows what was verified and evaluated at the time — not what was ultimately true.", "Where this answer came from", "python3 -c \"import hashlib,re,sys;b=open(sys.argv[1],'rb').read();m=re.findall(rb'<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->',b);assert len(m)==1,'expected exactly one fingerprint';z=b.replace(b'<!--fingerprint-->'+m[0],b'<!--fingerprint-->'+b'0'*64);print('matches' if hashlib.sha256(z).hexdigest()==m[0].decode() else 'DOES NOT MATCH')\" proof.html"], _VIEWS_BOTH))
EXPLAINED.setdefault('run[r11]/case.html + run[r11]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["Not checked: this console's check did not look at what this needs (held without its output files required). Every check behind this is on Proof"], _VIEWS_LINE))
EXPLAINED.setdefault('run[r11]/case.html + run[r11]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ["What changedProof"], _VIEWS_TABS))
#: Pages gone on purpose, each with why.
GONE_PAGES: dict[str, str] = {'executions-holds.html': "the check's verdict tally's list, gone with it: Records agree counts rung 1's states"}


#: A red run's "What changed" keeps the answer trail's command to repeat the check, with "What could
#: be re-checked": it says nothing read from the record's contents. The trail stays whole on "Proof",
#: so the two views together carry its words once more. Measured, not typed.
_VIEWS_REPEAT = _VIEWS + ": a red run's What changed keeps the trail's command, with What could be re-checked"
EXPLAINED.setdefault('run[forged]/case.html + run[forged]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Repeat the check', "Run it from the run's folder:"], _VIEWS_REPEAT))
EXPLAINED.setdefault('run[held-b]/case.html + run[held-b]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Repeat the check', "Run it from the run's folder:"], _VIEWS_REPEAT))
EXPLAINED.setdefault('run[preview]/case.html + run[preview]/proof.html', {}).setdefault('new', {}).update(dict.fromkeys(
    ['Repeat the check', "Run it from the run's folder:"], _VIEWS_REPEAT))

#: A pipeline's page: its stage chain with where its stored comparisons first differ, its runs as
#: tiles, and two filters, each its own page.
_PIPELINE_PAGE = "a pipeline's page, its runs as tiles, and its two filters"
for _p in ("p1", "p2"):
    NEW_PAGES.update({f"pipeline-{_p}.html": _PIPELINE_PAGE,
                      f"pipeline-{_p}-agree.html": _PIPELINE_PAGE + ": the runs whose records agree",
                      f"pipeline-{_p}-attention.html": _PIPELINE_PAGE + ": the runs that need attention"})

#: The Overview, pipelines first: four tiles (pipelines, runs, records agree with its bar, need
#: attention with its parts named) in the four cards' place, then one card per pipeline with one
#: mark per run and a legend. Changed vs baseline and Incidents leave the Overview's top; their
#: counts stay on All counts, and the Incidents page now says why no incident is called open.
_PIPELINES_FIRST = "the Overview leads with its pipelines: four tiles, then a card per pipeline"
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("gone", {}).update(dict.fromkeys(
    ["Changed vs baseline", "Incidents"], _PIPELINES_FIRST))
EXPLAINED.setdefault("home.html + counts.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["1 of 1 not checked (held without its output files required)",
     "1 of 3 records agree · 2 of 3 contradict their record", "1 run", "2 pipelines",
     "3 of 4 runs need attention", "3 runs",
     "A pipeline here is a declared stage list: runs that declare the same stages, in the same "
     "order. No record names its pipeline.",
     "Contradicts itself: 2 · Not checked: 1",
     "Each a stage list its runs declare; one card each below.",
     'Each mark is one run\'s "Records agree", as its own page reads it:',
     "Each pipeline's runs", "Need attention", "P1", "P2", "Pipelines", "alpha", "beta", "join",
     "zeta"], _PIPELINES_FIRST))
EXPLAINED.setdefault("incidents.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["This console keeps no open or closed state for an incident, so none is called open."],
    _PIPELINES_FIRST + ": the Incidents card's reason, now on the Incidents page"))
#: The Incidents card's total, back as the Incidents page's first sentence: the number 0.2.0 showed,
#: drawn by the lines that drew it on the card (`incident_pages.incident_total`).
EXPLAINED.setdefault("incidents.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["3 incidents raised from 2 of 4 runs."],
    "the Incidents card's total, now the Incidents page's first sentence"))
#: The Incidents page's last lines, each on one line: the digest's line ending at the shortened
#: digest, and the rules not built as a sentence of their own, not a list after ". Rules not built:".
EXPLAINED.setdefault("incidents.html", {}).setdefault("gone", {}).update(dict.fromkeys(
    ["I-DIFF-REGRESSION"], "the rules not built, now one sentence on a line of its own"))
EXPLAINED.setdefault("incidents.html", {}).setdefault("new", {}).update(dict.fromkeys(
    ["Rules not built: I-DIFF-REGRESSION."],
    "the rules not built, one sentence on a line of its own"))


def test_no_page_is_lost_and_every_new_page_is_declared(now, before, examined):
    examined(len(before), "pages in the baseline")
    lost = sorted(set(before) - set(now) - set(GONE_PAGES))
    assert not lost, f"pages that no longer exist: {lost}"
    assert not set(GONE_PAGES) & set(now), "a page declared gone is still drawn"
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
