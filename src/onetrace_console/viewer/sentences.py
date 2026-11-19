"""The translation table: every sentence a reader of the page reads, in one place.

The viewer has its technical states translated to plain language once, centrally, in a
checked table, never ad hoc in templates. The table's words are fixed; its tests check them.

FOUR KINDS OF ENTRY, KEPT APART
--------------------------------
`TABLE`       the anchor rows, one per state a record or report can be in, **in their settled words**.
              Every page's text is held by `tests/test_visible_text.py`, so a sentence typed
              wrong here fails a test rather than shipping.
`FIXED`       other settled sentences (the verdict strip, the timeline's outcome
              words, the limit sentence). **Settled words**, held the same way.
`RULED`       sentences proposed for the viewer and then settled: reworded, or adopted as
              written. Each carries, beside its sentence, what its words are for or why they are
              worded so; no page draws that. `LABELS` and `STEP_WORDS`
              were adopted the same way.
`PROVISIONAL` sentences the page needs that no settled wording supplies. **Empty.** The rule stands:
              anything added later is provisional again until it is agreed, and the tests assert
              the set exactly, so it cannot fill up quietly.

`{name}` marks a value filled in from the record or from the check's report. The page
never fills a placeholder with text it composed itself.

ROWS WHOSE INPUTS DO NOT EXIST YET
-----------------------------------
Six of the anchor rows describe the verbs' reports (`localize`, `diff`, `reproduce`), whose format
arrives with the SDK's verb reports, and a seventh (`anchor.anchored`) needs a date the
preview format does not define. All seven are carried here verbatim so the table is whole,
and named in `PENDING_ROWS` with what they wait for. A row that waits is counted and
named, not silently dropped.
"""
from __future__ import annotations

#: The anchor rows. Key: the record or report state. Value: what the reader sees.
TABLE: dict[str, str] = {
    "check.pass": "Checked — it holds.",
    "check.fail": "Checked — and the record contradicts itself here: {reason}.",
    "check.not_run.originality":
        "Consistent with itself; not anchored, so it can't be shown to be the record that "
        "was made.",
    "verb.not_run.boundary": "The record stops here. Nothing past this step is claimed.",
    "outcome.ok": "Completed.",
    "outcome.refused": "It declined to answer, and says why: {reason}.",
    "outcome.error": "Failed — {status}: {body}.",
    "rederivable.false": "The model step is recorded, not replayable.",
    "reproduce.pass": "Re-checked from the record — same result.",
    "reproduce.fail":
        "Re-checked from the record — a different result. The recorded one is kept; the new "
        "one is beside it.",
    "reproduce.not_run.unavailable":
        "Couldn't be re-checked from here. That is an access problem, not evidence of "
        "tampering — here is what would resolve it.",
    "localize.located": "It changed — here is the step where.",
    "diff.pass": "The two runs are the same at every step.",
    "emission.gaps":
        "{n} items couldn't be processed at this step. They are counted, named, and "
        "excluded — not silently dropped.",
    "coverage.incomplete":
        "Part of this run wasn't recorded. What is shown is what was recorded, and nothing "
        "more is claimed.",
    "anchor.anchored":
        "This record existed by {date} and hasn't changed since — checkable against an "
        "independent anchor.",
}

#: Candidate wording this project proposed that was **declined**, with the reason. Not agreed,
#: not provisional, not available: a candidate that was considered and refused is a different
#: state from one nobody has looked at, and conflating them is how a declined sentence comes
#: back through a path nobody re-read. A test asserts none of these renders.
DECLINED: dict[str, tuple[str, str]] = {
    "trail.checked_as_they_arrive": (
        "Trails are checked as they arrive; a trail with no verdict yet is shown as such, never "
        "as passing.",
        "Found in the delivered target-UX canvas and offered as candidate wording. "
        "Declined for viewer v1: it describes a trail still being checked, which implies "
        "checking over time while the page is viewed. The viewer's fence is static \u2014 generated "
        "once, no network at view time, nothing arriving. It is the live console's vocabulary, "
        "not this viewer's."),
}

#: Agreed wording later withdrawn outright, kept with the reason. A test asserts
#: none of these is rendered, so a withdrawn sentence cannot come back through a path nobody
#: re-read — the same guard as SUPERSEDED, for the case where nothing replaces the sentence
#: because the state already had one.
WITHDRAWN: dict[str, tuple[str, str]] = {
    "absence.no_comparison": (
        "No comparison was made.",
        "withdrawn as a duplicate wording of a state that already had settled words "
        "(`verbs.not_run`). The comparison section renders that sentence, unchanged."),
}

#: Agreed sentences later replaced for the state they were written for. They are kept
#: — settled wording is not edited away — and a test asserts none of them is rendered, so a superseded
#: sentence cannot come back through a code path nobody re-read.
SUPERSEDED: dict[str, str] = {}
#: Empty again. `verbs.not_run` was listed here for one day, on the premise that its words had
#: never been agreed. That was corrected (they had been), so it is the comparison
#: section's sentence again and nothing supersedes it.

#: The anchor rows whose input does not exist yet, with what each waits for. The six verb
#: rows have left this map: the report format's draft gives each of them a trigger in
#: a report the verbs already write, and `viewer/verbs.py` reads them. **The draft also corrects
#: the rows' triggers** from PASS/FAIL/NOT RUN to the fields that exist — the sentences themselves
#: stand.
PENDING_ROWS: dict[str, str] = {
    "anchor.anchored": "an anchored record: the preview format defines no anchor date field",
}

#: Settled sentences outside the table of anchor rows, in their own words.
FIXED: dict[str, str] = {
    # The verdict strip: one sentence, one of three states
    "strip.holds": "This answer's trail was checked on {date} — every step checks out.",
    "strip.contradicts":
        "This answer's trail was checked on {date} — the record contradicts itself at step "
        "{n}.",
    # The answer panel when the answer was a refusal
    "answer.refused": "It declined to answer, and says why:",
    # What could not be checked
    "unchecked.gaps_at_step":
        "{n} items couldn't be processed at the {step} step. They are counted, named, and "
        "excluded — not silently dropped.",
    "unchecked.unanchored":
        "This record is consistent with itself. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
    # The timeline's outcome words
    "timeline.refused": "declined — {reason}",
    "timeline.error": "failed — {status}: {body}",
    "timeline.boundary":
        "the record stops here — the next step ran outside what was recorded",
    # Closing every case, verbatim
    "case.limit":
        "This record shows what was verified and evaluated at the time — not what was "
        "ultimately true.",
}

#: Proposed by this project and agreed. Each entry: (sentence, what its words are for, or why they are
#: worded so).
RULED_STRIP_AND_CHECKS = "the wording settled for the strip and the checks' lines"
RULED_REMAINING = "the remaining wording"
RULED_RECHECK_LABELS = "the wording settled with the re-check labels"
RULED_STATE_LABELS = "labels bound to the states that trigger them"
RULED_ABSENCE = "the absence sentences"
RULED_STOPPED = "the declined-run wording"
RULED_STOPPED_AT = "stopped-at-a-step wording"
RULED_ERROR_ORIGIN = "the error-origin wording"
RULED_RATIONALE = "the recorded-rationale sentence, settled as fresh wording on its own terms"
ADOPTED_AS_PROPOSED = "adopted as written, as the proposing note worded it"
RULED_NO_AUTHORIZATION = "release 1 without authorization"
RULED_LADDER = "ladder wording"
RULED_UNREADABLE_ROWS = "unreadable-rows note"
#: The execution graph's own words, kept as given.
RULED_GRAPH = "graph wording"
RULED_LADDER_TIME_RUNG = "ladder table, time rung"
#: The ladder's table gives the signing rung's words; kept as given.
RULED_LADDER_SIGNING_RUNG = "ladder table, signing rung"
#: The signing rung's words where the ladder's table is silent, as settled.
RULED_SIGNING_RUNG = "signing rung wording"
#: The graph's provisional sentences and its labels, as settled.
RULED_GRAPH_SENTENCES = "graph sentences and labels"
#: The names a scroll region gives a screen reader: what scrolls, and that it scrolls sideways.
RULED_SCROLL = "scroll region names"
#: The run-page marks' naming line, its failure sentence and its link, as settled.
RULED_RUN_PAGE_MARKS = "run-page marks wording"
RULED_FREE_FILE = "free-file wording"
#: "Ran as approved"'s words, as settled.
RULED_PLAN_RUNG = "plan rung wording"
RULED_OUTPUTS_RUNG = "outputs-required rung wording"
RULED_RUN_LEVEL_AND_STRIP = "the run-level and strip sentences proposed for 0.1.2"
#: The time rung's reason frame, as written, and the answer view's anchor sentence.
RULED_ANCHOR_RUNG = "anchor rung wording"
#: The stage page's anchoring badge, as settled.
RULED_STAGE_ANCHORING = "stage anchoring badge"
#: The three sentences format 0.3 puts before the check's own row, as agreed.
RULED_FORMAT_03 = "format 0.3 sentences"

#: Sentences whose wording is **in force** but whose source text this package does not hold, so no test
#: here can look the words up in it. Holding and force are kept apart, and this keeps the consequence apart
#: too: the sentence is built and used, and the fact that its source is not held is counted and named
#: rather than silent.
RULED_PENDING_DELIVERY: dict[str, str] = {
    "outcome.error_origin":
        "The error-origin wording added the third field. Its source text is not held here, so "
        "its words cannot be checked against it here — only against the copy passed on.",
    "field.recorded_rationale":
        "Settled as fresh wording: the sentence had been offered as an existing source's own, "
        "and is not in that source. The source was rechecked, the claim was found to be an "
        "error, and the sentence was fixed on its own terms instead. That source is not held "
        "here, so the citation is to the copy passed on.",
}

RULED: dict[str, tuple[str, str]] = {
    #: Format 0.3's three sentences, each followed by the check's own row, quoted whole.
    "declined.held": (
        "The check says:",
        RULED_FORMAT_03 + ": beside the banner, the check's own row for a step the plan held before "
        "it ran (refused.attempted); accepted as written"),
    "rung.missing.optional": (
        "The check, asked whether every required step ran, says:",
        RULED_FORMAT_03 + ": rung 3 when the check run with --require-complete passes a run that left "
        "out only stages it declares optional; reworded and settled"),
    "rung.records.outputs_not_kept": (
        "The check did not look at the run's output files. This page does not say the records agree. "
        "The check says:",
        RULED_FORMAT_03 + ": rung 1 when the check's run: artifacts row says the run declares it keeps "
        "no output files (outputs_kept: none); reworded and settled"),
    #: Rung 3 for a run stopped at a step's own rule. The agreed "Not reached: stopped at {step}" is
    #: drawn as the rung's state word, "Not reached", then this line.
    "rung.missing.stopped_at": (
        "Stopped at {step}.",
        RULED_STOPPED_AT + ": rung 3 for a run stopped at a step's own rule, the step it stopped at"),
    "rung.missing.not_reached": (
        "Declared steps not reached: {steps}.",
        RULED_STOPPED_AT + ": rung 3, underneath, the declared steps after it"),
    "declined.chip": (
        "Declined at {stage}",
        RULED_STOPPED + ": the chip on the run header and in the runs list, in its words"),
    "declined.overview": (
        "stopped by a step",
        RULED_STOPPED + ": the Overview's count, \"Stopped by a step\", as a count's label"),
    # The free file in the console's settled words. `{error}` is its "{error type}".
    "last_failed.one": (
        "A declared stage's last recorded attempt failed: {stage} ({error}).",
        RULED_FREE_FILE + ": the settled words for one declared stage whose last recorded attempt failed"),
    "last_failed.several": (
        "{n} declared stages' last recorded attempts failed: {stages}",
        RULED_FREE_FILE + ": the settled words for several, as fixed (no full stop)"),
    # The sentences proposed when the check was pinned at 0.1.2, accepted as written
    # and fixed.
    "run_row.pass": (
        "For the run as a whole — {check}: checked, and it holds.",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: a run-level row that passed, on its own "
        "line beside the strip"),
    "run_row.not_run": (
        "For the run as a whole — {check}: not checked. The check says:",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: a run-level NOT-RUN, such as 0.1.2's "
        "`run: artifacts` on a run without artifacts/, followed by the check's own reason"),
    "run_row.fail": (
        "For the run as a whole — {check}: checked, and it failed. The check says:",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: a run-level FAIL, such as `run: "
        "artifacts` under --require-artifacts on a run without artifacts/, followed by the "
        "check's own reason"),
    "strip.contradicts_run": (
        "This answer's trail was checked on {date} — a check of the run as a whole failed.",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: the strip when the only failure is "
        "run-level, so no step is named"),
    "strip.not_verified": (
        "This answer's trail was checked on {date} — it was not verified: a receipt names a "
        "format the check does not implement, so the check did not read its contents.",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: exit 2, the check's NOT VERIFIED; never "
        "holds, never contradicts"),
    "strip.rows_unread_fail": (
        "This answer's trail was checked on {date} — the check failed. Its rows could not be "
        "read one by one, so no step below is named.",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: a FAIL (exit 1) whose rows a record "
        "broke apart"),
    "strip.rows_unread_pass": (
        "This answer's trail was checked on {date} — the check passed as a whole. Its rows could "
        "not be read one by one, so no step below is shown as checked.",
        RULED_RUN_LEVEL_AND_STRIP + ", proposed and accepted as written: a PASS (exit 0) whose rows a record "
        "broke apart"),
    # The note beside a report whose rows a record broke apart. Its intent was given
    # as "the verifier's rows ..."; "verifier" is retired on the page, and these words
    # were fixed instead.
    "rows.unreadable": (
        "The check's rows could not be read line by line; shown as written, escaped.",
        RULED_UNREADABLE_ROWS + " (the fixed words, quoted there without the full stop the page closes it with)"),
    # The middle strip state counts the steps
    "strip.not_checked_one": (
        "This answer's trail was checked on {date} — one step could not be checked from here.",
        RULED_STRIP_AND_CHECKS + ": the middle strip state, counting the steps; the singular form"),
    "strip.not_checked_n": (
        "This answer's trail was checked on {date} — {n} steps could not be checked from here.",
        RULED_STRIP_AND_CHECKS + ": the middle strip state, counting the steps"),
    # Reworded when the wording was settled
    "checks.gaps_none": (
        "Every step that was declared left a receipt; nothing is missing from the trail.",
        RULED_STRIP_AND_CHECKS + ": every declared step left a receipt"),
    "checks.held": ("{n} checks made — all hold.", RULED_STRIP_AND_CHECKS + ": a count of checks, each holding"),
    "checks.held_one": ("1 check made — it holds.", RULED_STRIP_AND_CHECKS + ": the singular, one check holding"),
    "verbs.not_run": (
        "No comparison with another run was made, so this page does not say where anything "
        "changed.",
        RULED_STRIP_AND_CHECKS + ": no comparison was made, so no place of change is claimed"),
    "strip.not_performed": (
        "This answer's trail has not been checked for this page. Nothing here is shown as "
        "checked.",
        RULED_STRIP_AND_CHECKS + ": the strip when no check was run for this page"),
    # The two forms called for when the wording was settled, and not worded then
    "strip.contradicts_n": (
        "This answer's trail was checked on {date} — the record contradicts itself at {n} "
        "steps.",
        RULED_REMAINING + ": several contradicting steps, counted; this channel's wording, adopted"),
    "strip.not_checked_list": (
        "This answer's trail was checked on {date} — the list of steps could not be checked "
        "from here, so no step below is shown as checked.",
        RULED_REMAINING + ": the list of steps could not be checked; the settled wording, replacing the "
        "proposed one"),
    # Agreed as **fresh wording**, and deliberately **not** cited to the source it was first
    # offered under. It was first offered as that source's own sentence, needing nothing new; it
    # is not in that source's text, which says a recorded rationale renders verbatim, set as
    # quoted and labelled as recorded, with the label provisional until the reader settles it —
    # the opposite of already agreed. The source's text was rechecked, the error recorded, and the
    # sentence agreed on its own terms.
    #
    # So the citation names what made it: an agreed sentence is checkable against the source it
    # claims, or it is not agreed.
    #
    # **It is a sentence, not a short label.** The block is also to be "labelled as recorded";
    # no word for that label has been agreed, and none is invented here. If a
    # short label is wanted beside this sentence, it is still unworded.
    "field.recorded_rationale": (
        "A stated reason is what the model wrote. It is recorded, not verified.",
        RULED_RATIONALE),
    # `outcome.error` gains a third field, completing an earlier three-field instruction (it
    # already named status/body/origin) rather than rewording the settled sentence independently.
    # **The settled two-field sentence is not replaced** — it keeps its state.
    # The format requires a `body` on an error (`rejection/R06`) and has **no vector requiring
    # `origin`**, so a recorded error without an origin is conforming, not malformed: it cannot
    # be sent down the as-recorded path, and the page must not compose the missing field
    # either. So the two forms are agreed sentences bound to two states, the way
    # `strip.not_checked_one`/`_n` and `checks.held`/`_one` already are:
    #
    #   origin recorded  -> this sentence
    #   origin absent    -> `outcome.error`, the settled words, unchanged
    #
    # The settled timeline form is untouched: the change is to `outcome.error` alone.
    "outcome.error_origin": (
        "Failed — {status}: {body}, reported by {origin}.", RULED_ERROR_ORIGIN),
    # The eighth sentence, agreed. It deliberately does NOT carry the unavailable
    # row's "not evidence of tampering" clause: absence says nothing and the reader must be
    # told so, but a mismatch is the presence of the wrong code. The page names the fact and
    # says nothing about why — it neither accuses nor absolves.
    "reproduce.not_run.mismatch": (
        "Couldn't be re-checked: the code available here is not the code that ran.",
        RULED_RECHECK_LABELS + ": the code here is not the code that ran; the fact is named, with no "
        "accusation and no excuse"),
    # Blank means no report, and nothing else. A clean result renders a sentence.
    # Worded against its neighbours: a single run compares nothing to anything, so neither
    # "comparison" nor `reproduce`'s "re-checked" belongs in it.
    "localize.clean": (
        "The record holds together — there is no step to point at.",
        RULED_RECHECK_LABELS + ": a clean single-run result, with no step to point at"),
    # One fixed frame per no-result state, filled with the verb's own words verbatim.
    # No assessment clause, no paraphrase: the reader sees the verb's sentence as the verb's.
    "comparison.not_comparable": (
        "These two can't be compared — {reason}.", RULED_RECHECK_LABELS + ": a fixed frame, the verb's words"),
    "comparison.refused": (
        "Refused before checking — {reason}.", RULED_RECHECK_LABELS + ": a fixed frame, the verb's words"),
    "comparison.could_not_check": (
        "Couldn't be checked from here — {reason}.", RULED_RECHECK_LABELS + ": a fixed frame, the verb's words"),
    "localize.could_not_check": (
        "Couldn't be checked from here — {words}.", RULED_RECHECK_LABELS + ": a fixed frame, the verb's words"),
    "verb.did_not_start": (
        "The check didn't start — {reason}.", RULED_RECHECK_LABELS + ": a fixed frame, the verb's words"),
    # A section ON the page which received no report says so in one fixed sentence, and blank
    # means the section is not there at all. That much stands. Its two sentences did not both
    # survive:
    #
    #   - the comparison section already had an agreed sentence (`verbs.not_run`), so the second
    #     one was a duplicate wording of an agreed state and is WITHDRAWN. A state that has a
    #     sentence does not get another.
    #   - the re-check section had none, so its sentence stands — reworded once, before any test
    #     pinned it, into the shape of `verbs.not_run` so the two absences read as a pair.
    "absence.no_recheck": (
        "No re-check from the record was run, so this page does not say whether anything comes "
        "out the same.",
        RULED_ABSENCE + ": a section with no report says so; worded as a pair with the comparison's"),
    # Adopted as written
    "strip.unreadable": (
        "This answer's trail could not be checked from here — the check's report could not "
        "be read. That is an access problem, not evidence of tampering.",
        ADOPTED_AS_PROPOSED),
    "strip.contradicts_list": (
        "This answer's trail was checked on {date} — the record contradicts itself in its "
        "list of steps.",
        ADOPTED_AS_PROPOSED),
    "anchoring.would_add": (
        "Anchored, it would read: this record existed by a stated date and hasn't changed "
        "since — checkable against an independent anchor.",
        ADOPTED_AS_PROPOSED),
    "answer.not_in_package": (
        "The answer's text is not part of this record package. It is identified by its "
        "fingerprint below.",
        ADOPTED_AS_PROPOSED),
    "question.not_in_package": (
        "The question's text is not part of this record package. It is identified by its "
        "fingerprint.",
        ADOPTED_AS_PROPOSED),
    "sample.label": (
        "Generated from a preview sample record, not from a production run.",
        ADOPTED_AS_PROPOSED),
    "card.ran_as": ("Ran as {id}, version {version}.", ADOPTED_AS_PROPOSED),
    "card.read_by": ("Read by {id}, pinned.", ADOPTED_AS_PROPOSED),
    "answer.no_step": (
        "This record has no step that wrote an answer, so there is no answer to show.",
        ADOPTED_AS_PROPOSED),
    "not_run.other": (
        "Could not be checked from here, and the check says why:",
        ADOPTED_AS_PROPOSED),
    "outcome.unknown": (
        "The record states an outcome this page has no words for, shown exactly as recorded:",
        ADOPTED_AS_PROPOSED),
    "anchor.anchored_no_date": (
        "The record says it is anchored and states no date for the anchor, so this page "
        "claims none.",
        ADOPTED_AS_PROPOSED),
    # Release 1 ships with no authorization records, and "The ladder rung
    # reads 'No records · needs an AADP policy engine'". The state and its evidence are the
    # rung's two parts; the page joins them. Never a pass, never blank.
    "rung.state.no_records": ("No records", RULED_NO_AUTHORIZATION),
    "rung.authorized.no_records": ("needs an AADP policy engine", RULED_NO_AUTHORIZATION),
    # "It holds whether or not the run proposed a change." It replaces
    # the earlier provisional "None of these says the change was the right one to make."
    "ladder.limit": ("None of these says the run's output or action was correct.",
                     RULED_LADDER + ": it holds whether or not the run proposed a change"),
    # The execution graph's own words, kept as given.
    "graph.linear": (
        "recorded as a straight line (no graph recorded)",
        RULED_GRAPH + ": a run with no `edges` is drawn as a line with this label"),
    "graph.note": (
        "A link shows which recorded output a stage read. It does not by itself prove that "
        "one stage caused the next.",
        RULED_GRAPH + ": the note the graph keeps"),
    "graph.table": ("Show as table", RULED_GRAPH + ": the graph's text equivalent"),
    "graph.region": ("The execution graph, scrolls sideways",
                     RULED_SCROLL + ": the run page's graph panel"),
    "graph.region.comparison": ("Comparison graph, scrolls sideways",
                                RULED_SCROLL + ": the comparison page's graph panel"),
    "region.ladder": ("What the evidence establishes, scrolls sideways",
                      RULED_SCROLL + ": the run page's ladder"),
    "region.steps": ("The steps, scrolls sideways", RULED_SCROLL + ": the run page's step table"),
    "graph.recorded_order": (
        "Recorded order", RULED_GRAPH + ": the link to the existing ordered view"),
    "graph.fold": (
        "{name} ×{n}",
        RULED_GRAPH + ': instances of one stage name fold into one node, "name ×n"'),
    # The graph's three provisional sentences, and the singular of one, as settled.
    "graph.too_large": (
        "This run's graph would need {n} boxes, more than the {max} this page draws. Its nodes "
        "and links are listed in the table below instead.",
        RULED_GRAPH_SENTENCES + ": reworded -- the limit stated as a fact about this page"),
    "graph.outside": (
        "{n} recorded links name a node this run did not record, so they are not drawn: "
        "{links}.",
        RULED_GRAPH_SENTENCES + ": two or more such links"),
    "graph.outside_one": (
        "1 recorded link names a node this run did not record, so it is not drawn: {link}.",
        RULED_GRAPH_SENTENCES + ": exactly one such link"),
    "graph.unreadable": (
        "This record's links cannot be read as links between its steps, so no graph is drawn "
        "for it.",
        RULED_GRAPH_SENTENCES + ": as proposed"),
    # The line naming where a run page's marks come from, and the sentence for a comparison
    # with no readable verdicts, as settled.
    "graph.marked_from": (
        "These verdicts come from the latest comparison of this run against the baseline "
        "{baseline}, stored {at}.",
        RULED_RUN_PAGE_MARKS + ": reworded -- \"against the baseline\" already says which side this run "
        "is on"),
    "graph.marks_unreadable": (
        "The latest comparison of this run against the baseline {baseline}, stored {at}, gave "
        "no verdicts that could be read, so none are shown on this graph.",
        RULED_RUN_PAGE_MARKS + ": reworded -- one sentence for an unreadable report and a diff that did "
        "not start"),
    # The time rung's yes, read from the verifier's own anchor row.
    "rung.anchored.yes": (
        "existed by {time} · {source}",
        RULED_LADDER_TIME_RUNG + ": Anchor PASS, as the table words it"),
    # The ladder's table: the signing rung read from the verifier's own signature rows with
    # the console's trust file: Yes, No and Not checked as the table words them.
    "rung.signed.yes": (
        "{label} · {key_id}",
        RULED_LADDER_SIGNING_RUNG + ": Valid, key trusted, as the table words it"),
    "rung.signed.no": (
        "the signature doesn't match this record",
        RULED_LADDER_SIGNING_RUNG + ": FAIL, as the table words it"),
    # Where the ladder's table is silent on the signing rung. The verifier's own reason, where it gives
    # one, is shown bare: "the check says" is kept for a failed check.
    "rung.signed.none": (
        "no signature beside the chain",
        RULED_SIGNING_RUNG + ": no signature row, Unsigned"),
    "rung.signed.unreadable": (
        "this page can't read the check's words",
        RULED_SIGNING_RUNG + ": Couldn't check, words this page can't read"),
    "rung.signed.no_own_check": (
        "a signature is read only from this page's own check",
        RULED_SIGNING_RUNG + ": no own check, Not checked"),
    "rung.signed.not_installed": (
        "install onetrace-verify[crypto]",
        RULED_LADDER_SIGNING_RUNG + ": Extra not installed, as the table words it"),
    "rung.anchored.reason": (
        "the check says: {detail}",
        RULED_ANCHOR_RUNG + ": the time rung's reason frame, as written"),
    # The answer view states an anchor only when the verifier's
    # anchor row passes; otherwise it states the case. No anchor row: nothing about anchoring.
    "answer.anchor.yes": (
        "This record existed by {time} ({source}). That doesn't show when the run happened, that "
        "its outputs were correct, or who wrote it.",
        RULED_ANCHOR_RUNG + ": the answer view's Yes"),
    # The stage page's anchoring badge states the run's own rung; its Yes
    # names the whole run's record, since an anchor covers the record, not one stage.
    "badge.anchored.yes": (
        "existed by {time} · {source} (the whole run's record)",
        RULED_STAGE_ANCHORING + ": Yes"),
    "answer.anchor.couldnt_check": (
        "Anchor present, not checked: {detail}.",
        RULED_ANCHOR_RUNG + ": the answer view's Couldn't check, {detail} the verifier's reason"),
    "answer.anchor.failed": (
        "Anchor present; the check says: {detail}.",
        RULED_ANCHOR_RUNG + ": the answer view's No, the check failed"),
    # Rung 1's "no" from the outputs-required check, reworded and fixed.
    "rung.records.outputs_differ": (
        "The receipts and links agree, but an output file doesn't match its receipt (checked with "
        "the run's output files required).",
        RULED_OUTPUTS_RUNG + ": reworded and settled"),
    # "Ran as approved"'s evidence, as proposed, with one change: the doesn't-verify sentence
    # was reworded.
    "rung.approved.yes": (
        "the check's plan row and its edges row both passed, and the run itself verified",
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.departed": (
        'it departed from the plan: {detail}',
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.edges": (
        "the links the record lists don't match the receipts: {detail}",
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.no_plan": (
        'no approved plan recorded',
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.linear": (
        'a straight-line run: there is no plan to compare',
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.cant_check": (
        "the check that ran, {checker}, has no plan row, so it can't say whether the run followed"
        ' its plan',
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.cant_check_unnamed": (
        "the check that ran has no plan row, so it can't say whether the run followed its plan",
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.not_verified": (
        "the run doesn't verify, so whether it followed its plan can't be read from its record; "
        'its own result is above',
        RULED_PLAN_RUNG + ": the fixed words, in place of the proposed 'No' reading"),
    "rung.approved.not_checked": (
        'this page did not run the check itself, so it says nothing of the plan',
        RULED_PLAN_RUNG + ": as proposed"),
    "rung.approved.unreadable": (
        "the check's rows can't be read one by one, so its plan rows aren't read",
        RULED_PLAN_RUNG + ": as proposed"),
}

#: NOT agreed. Emptied once the labels were settled, and refilled when the Executions list was
#: authorised with no words for it. The standing rule applies: provisional until agreed, and the
#: tests assert this set exactly.
#:
#: The Policy and Incidents sections are deliberately **not** here. Both reuse the "record stops
#: here" shape already used for a declared boundary, not new wording, as there is nothing to word
#: yet: no policy object, no incident key, no data model to describe. So
#: those two sections render `verb.not_run.boundary` — the settled sentence, unchanged — and
#: this channel worded nothing for them. **Policy no longer does**: it says
#: "no authorization records", in `policy.none` below. Incidents is unchanged.
#:
#: The run ladder's words. The release design canvas is the target, and it words the ladder;
#: the canvas is not a fixed text, so the words are provisional here until they are fixed, and
#: each entry names the part of the canvas it is taken from.
PROVISIONAL: dict[str, tuple[str, str]] = {
    "rung.approved.no_paths": (
        "no paths were observed: the record declares an approved plan but lists no path the run "
        "took, so whether it followed the plan can't be said",
        RULED_PLAN_RUNG + ", the case a plan is declared and no path observed; no words settled yet"),
    "fingerprint.whole": (
        "Each fingerprint in full",
        "fingerprints short in text and tables (the visual-quality rules): the fold holding "
        "the whole values; no words settled yet"),
    "declined.banner": (
        "The run stopped at {stage}: the step declined by its own rule, and recorded why: {reason}.",
        RULED_STOPPED + " asks for a run-page banner with the recorded reason; no words settled yet"),
    "declined.banner_no_reason": (
        "The run stopped at {stage}: the step declined by its own rule, and recorded no reason.",
        RULED_STOPPED + ", the case the record gives no reason; no words settled yet"),
    "declined.left": (
        "Declared steps left without a receipt: {steps}.",
        RULED_STOPPED + ": the banner names the declared steps left without a receipt; no words settled yet"),
    "declined.none_left": (
        "No declared step was left without a receipt.",
        RULED_STOPPED + ", the case the declining step was the last declared one; no words settled yet"),
    "check.not_run.originality_all": (
        "Held under the checks that ran; not anchored, so none of these steps can be shown to be the "
        "record that was made.",
        "the first-impression polish: the reason every step shares, said once for the run"),
    "executions.corpus": (
        "Runs this page was given: {n} of {total}, and it lists every one of them. It is not "
        "a view of a store, and nothing is summarised across runs.",
        "The Executions list is authorised with no words for it. The sentence exists because the "
        "corpus size must be visible — a real list view over the real corpus, emptiness visible, "
        "no synthesized rows — and a list that does not say how little it holds is a pretence. "
        "The denominator was added later: {total} is the size of the set the caller chose these runs from, in runs"),
    "executions.one": (
        "Runs this page was given: 1 of {total}, and it lists that one. It is not a view of a "
        "store, and nothing is summarised across runs.",
        "the Executions list's singular case, kept so the page never reads \"1 runs\"; the noun "
        "now leads, so no count is ever followed by it. The denominator as above"),
    # The node set, PROPOSED by this project when invited to. The target was named as "the
    # minimal set of unclean nodes `single_run_dag` already returns", and the presentation of that
    # set was left to this project. So this is a proposal, not settled wording, and it renders
    # nowhere; a test asserts that.
    #
    # **The singular case needs nothing new.** Where the set has one member, the settled
    # `localize.located` already fits exactly -- "It changed -- here is the step where." A set
    # of one IS a located step. Only the plural needs words, which is why there is one entry
    # here and not two.
    #
    # What the plural must carry: "A drawn graph invites the eye to find the
    # first red node; on a partial order there is no first." So the sentence names the count,
    # names the steps, and denies the ordering the reader will otherwise supply.
    "localize.located_set": (
        "It changed — here are the {n} steps where. Nothing in the record makes one of them "
        "first.",
        "**This project's wording, by delegation.** The rendering vocabulary here is this "
        "project's call under an existing rule: the page says things in the reader's words, not "
        "the code's. So it is not waiting on anyone else; it is provisional until the READER "
        "settles it, as with `field.recorded_rationale`. It already makes that translation: "
        "`single_run_dag` says 'node', the page says 'step', the reader's word. Still unrendered and "
        "unfixtured — no delivered receipt declares `edges`"),
    "ladder.intro": (
        "Each rung is a separate question, with its own evidence.",
        "run ladder canvas: the sentence under the ladder's heading. Its second "
        "sentence, 'There is no single \"checks out\"', is left out: the strip above it says "
        "'every step checks out' (the verdict strip's words), and the page would contradict "
        "itself"),
    "rung.reproduced.count": (
        "{n} of {total} re-run and matched.",
        "run ladder canvas: the evidence drawn for the re-run rung (\"3 of 3 re-run and "
        "matched\"), with its denominator: the stages the re-check report covers, less those "
        "the record declares not replayable, which the settled `rederivable.false` "
        "names beside it"),
    "rung.anchored.unstated": (
        "The record does not say whether it is anchored, so this page claims no time for it.",
        "run ladder canvas: the time rung when no receipt states an anchor. The canvas draws only "
        "\"not anchored\", which would claim a state the record does not state; this channel's "
        "words, after the adopted `anchor.anchored_no_date`"),
    "policy.none": (
        "No authorization records for this run.",
        "run ladder canvas: the authorization panel's heading. Release 1 ships without "
        "authorization records and the state must still be said here: never blank, never a pass. "
        "The panel's next sentence, that nothing in the record shows a policy outcome, a permit "
        "or a confirmation, is left out: this page does not look for "
        "those in the record, so it cannot say they are absent"),
    # The states a rung can be in without a yes, each said.
    # This channel's words; the canvas draws only the yes and no of each rung.
    "rung.records.partial": (
        "The check's report does not cover every step and the list of steps, so this page "
        "does not say the records agree.",
        "run ladder canvas: rung 1 when the report says nothing about a step or the list of "
        "steps, though nothing it says fails"),
    "list.more": (
        "…and {n} more.",
        "list and text caps: pages draw at most a fixed number of items per list, followed "
        "by '…and N more'. The number is model.LIST_CAP; this channel's punctuation"),
    "text.more": (
        "…and {n} more characters, not shown here.",
        "list and text caps, for a text shown verbatim: at most model.TEXT_CAP characters "
        "are drawn; this channel's words"),
    "name.more": (
        "… (+{n} more characters)",
        "long-name cap: a run_id or stage name longer than model.NAME_CAP characters "
        "is shown as its first NAME_CAP; the cap's own settled words"),
    "name.whole": (
        "the whole value is in the run's record",
        "long-name cap: the page that shortens a value offers the whole value as the "
        "run's own record; this channel's words"),
    "rung.records.no_artifacts": (
        "The check that ran did not require the run's output files, so this page does not say "
        "the records agree.",
        "own-check rung: the rung reads yes only from the verifier run with "
        "--require-artifacts returning PASS. Rung 1 when the check held without that flag. The "
        "pinned verifier (0.1.0) has no such flag (a known blocker), so no page reads yes until it "
        "does; this channel's words"),
    "rung.records.supplied": (
        "This page was given the check's report rather than running the check itself, so it "
        "does not say the records agree.",
        "own-check rung: rung 1 when the report was kept or supplied (`render "
        "--report`). The design requires that such a report never sets the rung, and words "
        "nothing for the state; this channel's words"),
    "rung.missing.unstated": (
        "The record does not say what was declared and what was left out, so this page does "
        "not say nothing is missing.",
        "run ladder canvas: rung 3 when a receipt carries no declared stages, emitted stages, "
        "completeness or gaps list"),
    "rung.missing.unreadable": (
        "The record says what was declared or left out in a form this page cannot read, so "
        "it does not say nothing is missing.",
        "run ladder canvas: rung 3 when one of those fields has a shape the format does not give "
        "it (three-outcome rule: malformed is surfaced)"),
    "rung.reproduced.other": (
        "The re-check report given with this page is not about exactly this run's steps, so "
        "nothing in it is counted here.",
        "run ladder canvas: rung 4 when the report names another run or chain head, is not a "
        "whole-run re-check, or its rows are not this record's steps one for one"),
    "rung.reproduced.disagrees": (
        "The re-check report and the record disagree about which steps can be replayed, so "
        "nothing in it is counted here.",
        "run ladder canvas: rung 4 when the report's declared rows are not the steps the record "
        "declares not replayable"),
    "rung.reproduced.inconsistent": (
        "The re-check report contradicts itself, so nothing in it is counted here.",
        "run ladder canvas: rung 4 when a row's two results disagree with its outcome, or the "
        "report's exit and result are not the ones its rows give"),
    "rung.reproduced.unbound": (
        "The records are not shown to agree here, so this page does not count a re-check of "
        "them.",
        "run ladder canvas: rung 4 when every replayable step matched and rung 1 is not a yes"),
    "rung.reproduced.declared_n": (
        "{n} steps are recorded, not replayable.",
        "run ladder canvas: rung 4 with more than one declared step; the settled "
        "`rederivable.false` "
        "speaks of one model step"),
    "rung.anchored.none": (
        "no anchor beside the chain",
        "0.1.1's colour rule: \"Not anchored\" is its own state; its evidence, as the signing "
        "rung's \"no signature beside the chain\""),
    "rung.anchored.declared_not": (
        "the record declares itself not anchored",
        "0.1.1's colour rule: \"Not anchored\" from what the record declares, with no check of "
        "this console's to read"),
    "rung.anchored.unchecked": (
        "The record says it is anchored. This page does not check an anchor, so it claims no "
        "time from it.",
        "run ladder canvas: rung 6 when every step says anchored. Nothing here verifies an anchor, "
        "so a declared anchor is never a yes"),
    "rung.anchored.partial": (
        "Parts of the record say it is anchored and parts say nothing, so this page claims no "
        "time.",
        "run ladder canvas: rung 6 when the steps and the list of steps are split between anchored "
        "and silent"),
    "rung.anchored.unreadable": (
        "The record states an anchor this page has no words for, so it claims no time.",
        "run ladder canvas: rung 6 when an anchor is not an object with state anchored or "
        "unanchored"),
}

#: Section headings and field labels. Adopted as agreed wording, checked against the note
#: that proposed them.
LABELS: dict[str, str] = {
    "kind.answer": "Answer",
    "kind.case": "Case",
    "title.answer": "Where this answer came from",
    "title.case": "The run, step by step",
    "section.answer": "The answer",
    "section.trail": "The trail",
    "section.unchecked": "What could not be checked",
    "section.case_line": "The case",
    "section.timeline": "What happened, in order",
    "section.changed": "Where it changed",
    "section.checked": "What was checked and what was not",
    "section.checked_list": "Checked",
    "section.not_checked_list": "Not checked",
    "checks.every_step": "Every step",
    "field.run": "Run",
    "field.ran": "When it ran",
    "field.for": "What it was for",
    "field.in": "What went in",
    "field.out": "What came out",
    "field.time": "When",
    "field.step": "Step",
    "field.outcome": "Outcome",
    "field.fingerprint": "Fingerprint",
    "field.version": "Version",
    "field.constants": "Settings it ran with",
    "disclose.card": "Receipt · step {n} of {total} · {name}",
    "disclose.raw": "The receipt, exactly as recorded",
    "disclose.report": "The check's own words",
    "check.source_fallback":
        "These words were read as text, because the machine-readable report was not "
        "there. That is the fallback, and it is the only thing on this page that "
        "was read that way.",
    "disclose.commands": "Check it yourself",
    "footer.generated": "Generated {date} by {generator}.",
    "footer.fingerprint": "This file's fingerprint",
    "footer.fingerprint_how":
        "Computed over this file with the fingerprint's own 64 characters set to zeros. To "
        "repeat it without us:",
    "command.verify": "Repeat the check",
    "command.regenerate": "Regenerate this page",
    "nothing.in": "nothing",
    "nothing.out": "nothing",
    "step.of": "step {n} of {total}",
    "label.manifest": "The list of steps",
    "label.close": "The close receipt",
    "unit.bytes": "bytes",
    "section.reproduce": "What could be re-checked",
    # The settled words for the two digests beneath the eighth sentence, and nothing else.
    # Written when the labels were settled, so agreed — see `LABELS_RECHECK`.
    "field.ran": "ran",
    "field.available_here": "available here",
    "field.where": "The step",
    "field.what_changed": "What changed",
    "field.reach": "How far it reached",
    "field.recorded_result": "The recorded result",
    "field.new_result": "The result now",
    "where.run_folder": "Run it from the run's folder:",
    "where.run_folder_verifier_elsewhere": "Run it from the run's folder, with the check's script beside you:",
    # The page-additions proposal's items, and its recorded rationale. **This channel's wording,
    # not agreed** — see `LABELS_UNRULED`, which carries the item each one comes from. They are
    # registered and not rendered: the proposal orders its items into `LABELS_UNRULED` **unbuilt**.
    "section.established": "Established",
    "section.not_established": "Not established",
    "field.predecessors": "Came after",
    "disclose.request": "The request, exactly as recorded",
    "disclose.response": "The response, exactly as recorded",
    #: Fixed: the label over the question's lines on the answer page.
    "disclose.question": "The question, as recorded",
    # The Executions list's labels. **This channel's wording, not agreed** — see
    # `LABELS_UNRULED`. The list was authorised with no words for these pages, and for Policy and
    # Incidents there is nothing to word yet.
    "kind.executions": "Runs",
    "title.executions": "The runs this page was given",
    "section.executions": "The runs",
    "field.steps": "Steps",
    "section.policy": "Policy",
    #: Fixed: the free file's heading for the boundary section.
    "section.incidents": "Where the record stops",
    # The run ladder, as its design canvas draws it. **This channel's copy of the
    # canvas's words, not agreed** — see `LABELS_UNRULED`.
    "section.ladder": "What the evidence establishes",
    "rung.records-agree": "Records agree",
    "rung.signed": "Signed by a known recorder",
    "rung.nothing-missing": "Nothing declared is missing",
    "rung.approved": "Ran as approved",
    "rung.state.not_declared": "Not declared",
    "rung.reproduced": "Re-runnable stages reproduced",
    "rung.authorized": "Action authorized, effect confirmed",
    "rung.anchored": "Committed by a known time",
    "rung.state.yes": "Yes",
    "rung.state.no": "No",
    "rung.state.couldnt_check": "Couldn't check",
    "rung.state.not_checked": "Not checked",
    "rung.state.no_verdict": "No verdict recorded",
    "rung.state.not_yet": "Not yet available",
    "rung.state.unsigned": "Unsigned",
    "rung.state.not_anchored": "Not anchored",
    "rung.state.not_a_graph_run": "Not a graph run",
    "rung.state.signed_untrusted": "Signed, key not trusted",
    "rung.state.not_reached": "Not reached",
    # The execution graph's table and folds, as settled -- see LABELS_GRAPH -- and the
    # link to a run page's comparison -- see LABELS_RUN_PAGE_MARKS.
    "graph.col_node": "Node",
    "graph.col_stage": "Stage",
    "graph.col_index": "Recorded position",
    "graph.col_from": "From",
    "graph.col_to": "To",
    "graph.failed": "failed attempt",
    "graph.link_outside": "names a node this run did not record",
    "section.graph": "The execution graph",
    "graph.open_comparison": "Open that comparison",
}

#: Labels added after the rest were adopted are **this channel's wording and not agreed**; they
#: are in `LABELS_UNRULED`, each with why the page needs it, and the tests assert that set exactly.
#: Every other key in LABELS is adopted wording.
#: Labels whose words were written when the labels were settled. Agreed, not adopted from the
#: proposing note, so they are checked against that settled wording rather than against the note.
LABELS_RECHECK = ("field.ran", "field.available_here")

#: Fixed with the label triggers, each bound to the trigger named for it. They are
#: agreed-pending-reader, like every settled sentence: adopted, and still to be scored
#: by the reader. The trigger is recorded beside the label because a label is agreed FOR A STATE — the
#: same label over a different field would be a new question.
LABELS_BY_STATE: dict[str, str] = {
    "section.reproduce": "no state: a heading for the block of re-check rows",
    "field.where": "a located comparison — single-run `result = located`, or two-run with "
                   "`first_difference` non-null",
    "field.what_changed": "two-run `cause.instrument_change` or `cause.constants`",
    "field.reach": "`cause.blast_radius.status = counted`",
    "field.recorded_result": "`outcome = DIVERGED` — the kept result",
    "field.new_result": "`outcome = DIVERGED` — the new result",
}

#: The execution graph's heading and labels, fixed as proposed. Their words stay in LABELS;
#: this names where each was fixed.
LABELS_GRAPH: dict[str, str] = {
    "section.graph": RULED_GRAPH_SENTENCES + ": the graph's heading",
    "graph.col_node": RULED_GRAPH_SENTENCES + ": the table's node column",
    "graph.col_stage": RULED_GRAPH_SENTENCES + ": the table's stage-name column",
    "graph.col_index": RULED_GRAPH_SENTENCES + ": the table's recorded-position column",
    "graph.col_from": RULED_GRAPH_SENTENCES + ": a link's upstream node",
    "graph.col_to": RULED_GRAPH_SENTENCES + ": the node that read it",
    "graph.failed": RULED_GRAPH_SENTENCES + ": a retry's failed attempt, kept visible",
    "graph.link_outside": RULED_GRAPH_SENTENCES + ": a recorded link to an unrecorded node",
}

#: The link to the comparison a run page's graph is marked from, fixed as proposed. Its words
#: stay in LABELS; this names where it was fixed.
LABELS_RUN_PAGE_MARKS: dict[str, str] = {
    "graph.open_comparison": RULED_RUN_PAGE_MARKS + ": the link to the comparison the marks come from",
}

#: The free file's heading for the boundary section is fixed as "Where the
#: record stops", in place of "Incidents", whose heading promised what its text never gave.
LABELS_FREE_FILE_HEADINGS: dict[str, str] = {
    "section.incidents": "free-file headings: the free file's heading for the boundary section",
    "disclose.question": "free-file headings: the label over the question's lines on the answer page",
}

#: "Ran as approved"'s question and its "Not declared" state word, in their settled words.
#: Their words stay in LABELS; this names where they were fixed.
LABELS_LADDER_SIGNING_RUNG: dict[str, str] = {
    "rung.state.unsigned": "ladder table, signing rung: No signature, as the table words it",
    "rung.state.signed_untrusted": "ladder table, signing rung: SIGNED-UNTRUSTED, as the table words it",
}

#: Rung 3's state word for a run stopped at a step's own rule. Its word stays in LABELS.
LABELS_RULED_STOPPED_AT: dict[str, str] = {
    "rung.state.not_reached": RULED_STOPPED_AT + ": rung 3's state where the run stopped at a step",
}

LABELS_PLAN_RUNG: dict[str, str] = {
    "rung.approved": "plan rung wording: the plan rung's question, as proposed",
    "rung.state.not_declared": "plan rung wording: the plan rung's no-plan state word, as proposed",
}

#: Labels this project added that no settled wording covers. The standing rule: anything added
#: later is provisional until agreed.
#:
#: Refilled by the page-additions proposal, which proposes five additions to the page and
#: agrees none of them: each item is provisional, its labels go here, and none is built before
#: the checks it rests on are green. They are green as of this commit, so the labels are
#: registered here — **and only here**. A test asserts that no page renders any of them, as the
#: proposal orders them in *unbuilt*.
#:
#: Each value names the proposal's item (or its rationale) the label serves. The words are
#: this channel's: the proposal gives the items, not their wording, except where noted.
LABELS_UNRULED: dict[str, str] = {
    "label.close":
        "the name onetrace's format note gives the receipt a format 0.4 run writes when it closes, "
        "and the name of onetrace-verify's own row for it, `the close receipt`; no words settled yet",
    "check.source_fallback":
        "the reader's rule: the text parser is kept \"only as a fallback that "
        "says openly that it is the fallback\", which authorises a sentence and words "
        "none. Three things and no more: what was read, why, and how far the fallback "
        "reaches. The last clause is the one that earns its place -- a reader told only "
        "'this page used a fallback' has been handed a doubt with no edges, and the "
        "receipts, the manifest and the verbs on this page did not come through it",
    "section.established":
        "the page additions: the heading for the first of the page's two counted lists. The "
        "proposal supplies the pairing (\"established / not established\") and says the headings "
        "are new words, so they are provisional until the reader settles them",
    "section.not_established":
        "the page additions: the heading for the second list, the other half of the same pairing",
    "field.predecessors":
        "the page additions: for v1 each step card lists its declared predecessors as text and "
        "there is no drawing. A label is needed for that list; the proposal does not word it",
    "disclose.request":
        "the page additions: raw request bytes as a quoted artefact one click down, under the "
        "disclosure rule. Worded after `disclose.raw`, which was adopted as "
        "written",
    "disclose.response":
        "the page additions: raw response bytes, the other half of the same disclosure",
    # The Executions list's, not the proposal's. Kept in the same register: the rule is the same one.
    "kind.executions": "the Executions list: the Executions list's view name, beside kind.answer/case",
    "title.executions": "the Executions list: the list page's title",
    "section.executions": "the Executions list: the heading over the rows",
    "field.steps": "the Executions list: the column naming how many steps a run recorded",
    "section.policy":
        "the Policy section: its heading. The section's *sentence* is settled (the "
        "settled `verb.not_run.boundary`, reused as directed); only this heading is this "
        "channel's word, and no wording is given here because there is nothing to word",
    "section.ladder": "run ladder canvas: the ladder's heading",
    "rung.records-agree": "run ladder canvas: rung 1's question",
    "rung.signed": "run ladder canvas: rung 2's question",
    "rung.state.not_a_graph_run":
        "runs list, plan rung: a straight-line run's state word, where the run page draws no badge "
        "and one line; the plan rung's \"not a graph run\" state, as proposed",
    "rung.nothing-missing": "run ladder canvas: rung 3's question",
    "rung.reproduced": "run ladder canvas: rung 4's question",
    "rung.authorized": "run ladder canvas: rung 5's question",
    "rung.anchored": "run ladder canvas: rung 6's question",
    "rung.state.yes": "run ladder canvas: the state word for an established rung",
    "rung.state.no": "run ladder canvas: the state word for a rung that is not",
    "rung.state.couldnt_check":
        "run ladder canvas: the state word for a rung the check could not settle. Not drawn on "
        "the ladder; the canvas overview's own tag for that state",
    "rung.state.not_checked":
        "run ladder canvas: the state word for a rung with no evidence to read. Not drawn on the "
        "canvas; this channel's words, kept apart from \"No\" (three-outcome rule)",
    "rung.state.no_verdict":
        "the console's runs lists: \"Records agree\" for a run the check has not reached, which has "
        "no page of its own (records.py)",
    "rung.state.not_yet": "run ladder canvas: the state word for signing",
}

#: Plain words for the stage names the preview format uses. A stage name not listed here
#: is shown exactly as recorded, never guessed at. Adopted as agreed wording.
STEP_WORDS: dict[str, str] = {
    "retrieve": "Searched the documents",
    "rerank": "Put the results in order",
    "generate": "Wrote the answer",
    "verify": "Checked the answer against the passages",
}

#: Words that never appear in generator-authored text on the page (the viewer's rule, and the
#: messaging guide). Checked over everything the generator writes; the record's own words and the
#: check's own words are quoted, marked as quotations, and exempt.
RETIRED_WORDS = ("provenance", "lineage", "canonical", "digest", "hash", "verifier",
                 "instrument", "topology", "coverage attestation")
#: Bare state tokens that never appear as words on the page.
BARE_TOKENS = ("PASS", "FAIL", "NOT RUN", "NOT-RUN")


_WHY_CHECK_COVERAGE = ("check coverage wording: a sentence that describes what the check covers says only "
             "what onetrace-verify 0.1.2 checks. ")

#: Agreed sentences that describe what the check covers, reworded to what
#: `onetrace-verify` 0.1.2 checks. The agreed words stay where they are, in the table they were agreed
#: into, and each entry here names them; the page draws from here first. Key -> (the proposed
#: words, the words they replace, why). This project's words, to be checked before merge.
REWORDED: dict[str, tuple[str, str, str]] = {
    "sample.label": (
        "This record is in a preview format ({format}).",
        "Generated from a preview sample record, not from a production run.",
        RULED_FREE_FILE + ": the banner's trigger is the manifest's format ending in -preview, which says "
        "nothing of where the run came from, so 'sample' is untrue; the console's settled words "
        "(the preview banner), the format read from the manifest"),
    "strip.holds": (
        "This answer's trail was checked on {date} — each check that ran held.",
        "This answer's trail was checked on {date} — every step checks out.",
        _WHY_CHECK_COVERAGE + "0.1.2 runs no stage-order check, and checks output files only when the run "
        "carries them, so 'every step checks out' says more than the check did"),
    "checks.gaps_none": (
        "Each declared step left a receipt, as the receipts themselves state.",
        "Every step that was declared left a receipt; nothing is missing from the trail.",
        _WHY_CHECK_COVERAGE + "the reading comes from the receipts' own coverage fields, which no check "
        "confirms; 'nothing is missing from the trail' says more"),
    "check.not_run.originality": (
        "Held under the checks that ran; not anchored, so it can't be shown to be the record "
        "that was made.",
        "Consistent with itself; not anchored, so it can't be shown to be the record that "
        "was made.",
        _WHY_CHECK_COVERAGE + "0.1.2 runs no stage-order check, so a receipt that misstates it still "
        "passes, and the record is shown to hold only as far as the checks reach"),
    "unchecked.unanchored": (
        "This record held under the checks that ran. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
        "This record is consistent with itself. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
        _WHY_CHECK_COVERAGE + "as check.not_run.originality, for what could not be checked"),
    "anchor.anchored": (
        "The record declares an anchor dated {date}. This console doesn't check anchors, so that "
        "date isn't confirmed here.",
        "This record existed by {date} and hasn't changed since — checkable against an "
        "independent anchor.",
        "anchor wording: the fixed words. 0.1.2 checks only that an anchor state is "
        "declared and this console checks no anchor, so the settled sentence read as proof of time "
        "from the record's own word. A verified anchor PASS earns the stronger sentence at the "
        "0.2.0 re-pin"),
    "section.timeline": (
        "What happened, in the order the receipts give",
        "What happened, in order",
        _WHY_CHECK_COVERAGE + "the order is the receipts' own, and 0.1.2 does not check it (the settled heading)"),
}


def _ruled(key: str) -> str:
    """The words a table other than REWORDED holds for `key`: the agreed ones, or this project's."""
    if key in TABLE:
        return TABLE[key]
    if key in FIXED:
        return FIXED[key]
    if key in RULED:
        return RULED[key][0]
    if key in PROVISIONAL:
        return PROVISIONAL[key][0]
    if key in LABELS:
        return LABELS[key]
    raise KeyError(f"no sentence for state {key!r}; the table is the only source")


def template(key: str) -> str:
    """The sentence for a state, with its `{placeholders}` unfilled. Unknown keys raise."""
    if key in REWORDED:
        return REWORDED[key][0]
    if key in TABLE:
        return TABLE[key]
    if key in FIXED:
        return FIXED[key]
    if key in RULED:
        return RULED[key][0]
    if key in PROVISIONAL:
        return PROVISIONAL[key][0]
    if key in LABELS:
        return LABELS[key]
    raise KeyError(f"no sentence for state {key!r}; the table is the only source")


def sentence(key: str, **values: str) -> str:
    """The sentence for a state with every placeholder filled. Missing values raise."""
    return template(key).format(**values)
