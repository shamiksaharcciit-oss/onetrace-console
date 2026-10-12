"""The translation table: every sentence a reviewer reads, in one place (019 §4).

The viewer's specification (019 §4) has technical states translated to plain language once,
centrally, in a checked table, never ad hoc in templates. The table's words are fixed; its
tests check them.

FOUR KINDS OF ENTRY, KEPT APART
--------------------------------
`TABLE`       019 §4's anchor rows, **the specified words**. Every entry is tested to appear
              verbatim in the sealed 019 (`viewer/tests/test_sentences.py`), so a sentence
              typed wrong here fails a test rather than shipping.
`FIXED`       other sentences 019 fixes in §2 and §3 (the verdict strip, the timeline's
              outcome words, the limit sentence). **The specified words**, checked the same way.
`RULED`       sentences proposed for the viewer and then fixed (the wording review, 023 §3
              Q2 and §4; 024 §3): reworded at review, or adopted as written from Note 015 §7,
              or worded by 024. Each names the sealed document its exact words are checked
              against, and 024 §1 adopted that practice for every generated page in the
              programme. `LABELS` and `STEP_WORDS` were adopted the same way (023 §4).
`PROVISIONAL` sentences the page needs that no ruling supplies. **Empty since 024 §3.** The
              rule stands: anything added later is provisional again until ruled, and the
              tests assert the set exactly, so it cannot fill up quietly.

`{name}` marks a value filled in from the record or from the check's report. The page
never fills a placeholder with text it composed itself.

ROWS WHOSE INPUTS DO NOT EXIST YET
-----------------------------------
Six §4 rows describe the verbs' reports (`localize`, `diff`, `reproduce`), whose format
arrives with the SDK (2 October), and a seventh (`anchor.anchored`) needs a date the
preview format does not define. All seven are carried here verbatim so the table is whole,
and named in `PENDING_ROWS` with what they wait for. A row that waits is counted and
named, not silently dropped.
"""
from __future__ import annotations

#: 019 §4, anchor rows. Key: the record or report state. Value: what the reviewer sees.
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

#: Candidate wording this channel proposed and core **declined**, with the reason. Not ruled,
#: not provisional, not available: a candidate that was considered and refused is a different
#: state from one nobody has looked at, and conflating them is how a declined sentence comes
#: back through a path nobody re-read. A test asserts none of these renders.
DECLINED: dict[str, tuple[str, str]] = {
    "trail.checked_as_they_arrive": (
        "Trails are checked as they arrive; a trail with no verdict yet is shown as such, never "
        "as passing.",
        "Found in the delivered target-UX canvas and offered to core as candidate wording. "
        "Declined for viewer v1: it describes a trail still being checked, which implies "
        "checking over time while the page is viewed. 019 §0's fence is static \u2014 generated "
        "once, no network at view time, nothing arriving. It is the live console's vocabulary, "
        "not this viewer's."),
}

#: Ruled wording a later ruling withdrew outright, kept with what withdrew it. A test asserts
#: none of these is rendered, so a withdrawn sentence cannot come back through a path nobody
#: re-read — the same guard as SUPERSEDED, for the case where nothing replaces the sentence
#: because the state already had one.
WITHDRAWN: dict[str, tuple[str, str]] = {
    "absence.no_comparison": (
        "No comparison was made.",
        "duplicate-wording withdrawal (033 §2): withdrawn as a duplicate wording of a state the "
        "wording review had already fixed (`verbs.not_run`). The comparison section renders that "
        "review's sentence, unchanged."),
}

#: Ruled sentences a later ruling replaced for the state they were written for. They are kept
#: — a ruling is not edited away — and a test asserts none of them is rendered, so a superseded
#: sentence cannot come back through a code path nobody re-read.
SUPERSEDED: dict[str, str] = {}
#: Empty again. `verbs.not_run` was listed here for one day, on C031 §3's premise that no ruling
#: had made it. C033 §1 corrects that — C023 §4 ruled it, line 70 — so it is the comparison
#: section's sentence again and nothing supersedes it.

#: 019 §4 rows whose input does not exist yet, with what each waits for. The six verb rows left
#: this map on 2026-09-18: the report format's draft (029 §6) gives each of them a trigger in
#: a report the verbs already write, and `viewer/verbs.py` reads them. **029 §6 also corrects
#: 019 §4's triggers** from PASS/FAIL/NOT RUN to the fields that exist — the sentences themselves
#: stand.
PENDING_ROWS: dict[str, str] = {
    "anchor.anchored": "an anchored record: the preview format defines no anchor date field",
}

#: Sentences 019 fixes outside the §4 table, in its own words.
FIXED: dict[str, str] = {
    # §2.1, the verdict strip: one sentence, one of three states
    "strip.holds": "This answer's trail was checked on {date} — every step checks out.",
    "strip.contradicts":
        "This answer's trail was checked on {date} — the record contradicts itself at step "
        "{n}.",
    # §2.2, the answer panel when the answer was a refusal
    "answer.refused": "It declined to answer, and says why:",
    # §2.4, what could not be checked
    "unchecked.gaps_at_step":
        "{n} items couldn't be processed at the {step} step. They are counted, named, and "
        "excluded — not silently dropped.",
    "unchecked.unanchored":
        "This record is consistent with itself. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
    # §3.2, the timeline's outcome words
    "timeline.refused": "declined — {reason}",
    "timeline.error": "failed — {status}: {body}",
    "timeline.boundary":
        "the record stops here — the next step ran outside what was recorded",
    # §3.5, closing every case, verbatim
    "case.limit":
        "This record shows what was verified and evaluated at the time — not what was "
        "ultimately true.",
}

#: Proposed by this channel and ruled by core. Each entry: (sentence, the sealed source its
#: exact words are checked against).
RULED_023 = "the wording review"
RULED_024 = "the remaining wording"
RULED_030 = "the labels decision"
RULED_031 = "the label-trigger decision"
RULED_033 = "the duplicate-wording withdrawal"
RULED_BR047 = "the error-origin decision"
RULED_RATIONALE = "the relayed ruling of 2026-09-25 adopting the recorded-rationale sentence as fresh wording"
ADOPTED_NOTE_015 = "Note 015 §7, adopted as written in the wording review (023 §4)"
RULED_28N = "release 1 without authorization"
RULED_29X = "ladder wording review"
RULED_30BZ = "unreadable-rows note"
#: The execution graph's specification gives these words itself; checked against it.
RULED_C18E5 = "graph specification"
RULED_C18E5_23 = "ladder table, time rung"
#: The ladder's specification gives the signing rung's words in its table; checked against it.
RULED_C18E5_22 = "ladder table, signing rung"
#: The signing rung's words where the ladder's table is silent, as specified.
RULED_29LK = "signing rung wording"
#: The graph's provisional sentences and its labels, as specified.
RULED_29DB = "graph sentences and labels"
#: The names a scroll region gives a screen reader: what scrolls, and that it scrolls sideways.
RULED_SCROLL = "scroll region names"
#: The run-page marks' naming line, its failure sentence and its link, as specified.
RULED_29DF = "run-page marks wording"
RULED_29FC = "free-file wording"
#: "Ran as approved"'s words, as specified.
RULED_29GS = "plan rung wording"
RULED_29KT = "outputs-required rung wording"
RULED_10CD = "pin report sentences"
#: The time rung's reason frame, as written, and the answer view's anchor sentence.
RULED_29KZ = "anchor rung wording"
#: The stage page's anchoring badge, as specified.
RULED_29LD = "stage anchoring badge"

#: Sentences whose ruling is **in force by relay** but whose sealed source has not been
#: delivered to the archive of sealed sources yet, so no test can look the words up in it. C025 §2 keeps
#: delivery and force apart, and this keeps the consequence apart too: the sentence is built
#: and used, and the fact that its pin is missing is counted and named rather than silent.
#:
#: The entry leaves the moment the memo lands: `test_every_ruled_sentence_is_in_its_sealed_
#: source` looks for the file, and if it finds it, pins the sentence and **fails while the key
#: is still named here**. Self-cancelling, like R11's block.
RULED_PENDING_DELIVERY: dict[str, str] = {
    "outcome.error_origin":
        "The error-origin decision (seal relayed as b011bbdb…10c2a0c52) added the third field. "
        "The memo has not been delivered to the archive of sealed sources, so its words cannot be verified "
        "against a sealed source here — only against the relay.",
    "field.recorded_rationale":
        "Ruled as fresh wording on 2026-09-25, after R-C007: the sentence had been offered as "
        "C034 §4's own, and is not in C034. The sealed text was rechecked, the claim was found to "
        "be an error, and the sentence was fixed on its own terms instead. That memo has not "
        "been delivered to the archive of sealed sources, so the citation is to the relay until it lands.",
}

RULED: dict[str, tuple[str, str]] = {
    # The free file in the console's specified words. The words
    # are the specified ones, checked against their archived text; `{error}` is its "{error type}".
    "last_failed.one": (
        "A declared stage's last recorded attempt failed: {stage} ({error}).",
        RULED_29FC + ": the specified words for one declared stage whose last recorded attempt failed"),
    "last_failed.several": (
        "{n} declared stages' last recorded attempts failed: {stages}",
        RULED_29FC + ": the specified words for several, as fixed (no full stop)"),
    # The sentences the 0.1.2 pin report's §5 proposed, accepted as written
    # and fixed. Checked against the sealed report in the archive.
    "run_row.pass": (
        "For the run as a whole — {check}: checked, and it holds.",
        RULED_10CD + ", as written in the pin report §5: a run-level row that passed, on its own "
        "line beside the strip (30bv §3.2)"),
    "run_row.not_run": (
        "For the run as a whole — {check}: not checked. The check says:",
        RULED_10CD + ", as written in the pin report §5: a run-level NOT-RUN, such as 0.1.2's "
        "`run: artifacts` on a run without artifacts/, followed by the check's own reason "
        "(30bv §3.2)"),
    "run_row.fail": (
        "For the run as a whole — {check}: checked, and it failed. The check says:",
        RULED_10CD + ", as written in the pin report §5: a run-level FAIL, such as `run: "
        "artifacts` under --require-artifacts on a run without artifacts/, followed by the "
        "check's own reason (30bv §3.2)"),
    "strip.contradicts_run": (
        "This answer's trail was checked on {date} — a check of the run as a whole failed.",
        RULED_10CD + ", as written in the pin report §5: the strip when the only failure is "
        "run-level, so no step is named (30bv §3.2)"),
    "strip.not_verified": (
        "This answer's trail was checked on {date} — it was not verified: a receipt names a "
        "format the check does not implement, so the check did not read its contents.",
        RULED_10CD + ", as written in the pin report §5: exit 2, the check's NOT VERIFIED; never "
        "holds, never contradicts (30bz §3)"),
    "strip.rows_unread_fail": (
        "This answer's trail was checked on {date} — the check failed. Its rows could not be "
        "read one by one, so no step below is named.",
        RULED_10CD + ", as written in the pin report §5: a FAIL (exit 1) whose rows a record "
        "broke apart (30bv §3.3)"),
    "strip.rows_unread_pass": (
        "This answer's trail was checked on {date} — the check passed as a whole. Its rows could "
        "not be read one by one, so no step below is shown as checked.",
        RULED_10CD + ", as written in the pin report §5: a PASS (exit 0) whose rows a record "
        "broke apart (30bv §3.3)"),
    # 30bz §1: the note beside a report whose rows a record broke apart. 30bv §3.3 gave its intent
    # as "the verifier's rows ..."; "verifier" is retired on the page (019 §4), and these words
    # were fixed instead.
    "rows.unreadable": (
        "The check's rows could not be read line by line; shown as written, escaped.",
        RULED_30BZ + " (the fixed words, quoted there without the full stop the page closes it with)"),
    # 023 §3 Q2: the middle strip state counts the steps
    "strip.not_checked_one": (
        "This answer's trail was checked on {date} — one step could not be checked from here.",
        RULED_023 + " §3 Q2 (the singular form it names)"),
    "strip.not_checked_n": (
        "This answer's trail was checked on {date} — {n} steps could not be checked from here.",
        RULED_023 + " §3 Q2"),
    # 023 §4, reworded by core
    "checks.gaps_none": (
        "Every step that was declared left a receipt; nothing is missing from the trail.",
        RULED_023 + " §4"),
    "checks.held": ("{n} checks made — all hold.", RULED_023 + " §4"),
    "checks.held_one": ("1 check made — it holds.", RULED_023 + " §4"),
    "verbs.not_run": (
        "No comparison with another run was made, so this page does not say where anything "
        "changed.",
        RULED_023 + " §4"),
    "strip.not_performed": (
        "This answer's trail has not been checked for this page. Nothing here is shown as "
        "checked.",
        RULED_023 + " §4"),
    # 024 §3: the two forms 023 §3 Q2 called for and did not word
    "strip.contradicts_n": (
        "This answer's trail was checked on {date} — the record contradicts itself at {n} "
        "steps.",
        RULED_024 + " §3 (this channel's wording, adopted)"),
    "strip.not_checked_list": (
        "This answer's trail was checked on {date} — the list of steps could not be checked "
        "from here, so no step below is shown as checked.",
        RULED_024 + " §3 (the fixed wording, replacing the proposed one)"),
    # Ruled 2026-09-25 as **fresh wording**, and deliberately **not** cited to C034 §4.
    #
    # R-C007 is why. The sentence was first offered as "C034 §4's own already-ruled sentence,
    # needing no new ruling". It is not in C034: four probes, zero hits, against a footer
    # verified first. C034 §4's actual closing paragraph says a recorded rationale "renders
    # verbatim, set as quoted, labelled as recorded. The label is provisional until the reader
    # rules it" — which is the opposite of already-ruled. Core rechecked the sealed text,
    # recorded the error as its own, and ruled the sentence in on its own terms.
    #
    # So the citation names the ruling that made it. That is the whole value of the refusal:
    # a ruled sentence is checkable against the source it claims, or it is not ruled.
    #
    # **It is a sentence, not a short label.** C034 §4 also calls for the block to be "labelled
    # as recorded"; no word for that label has been ruled, and none is invented here. If a
    # short label is wanted beside this sentence, it is still unworded.
    "field.recorded_rationale": (
        "A stated reason is what the model wrote. It is recorded, not verified.",
        RULED_RATIONALE),
    # Bench Record 047: `outcome.error` gains a third field, completing C034 §2's own
    # three-field instruction (it already named status/body/origin) rather than rewording 019
    # independently. **019 §4's two-field sentence is not replaced** — it keeps its state.
    # The format requires a `body` on an error (`rejection/R06`) and has **no vector requiring
    # `origin`**, so a recorded error without an origin is conforming, not malformed: it cannot
    # be sent down F14's as-recorded path, and the page must not compose the missing field
    # either. So the two forms are ruled sentences bound to two states, the way
    # `strip.not_checked_one`/`_n` and `checks.held`/`_one` already are:
    #
    #   origin recorded  -> this sentence
    #   origin absent    -> `outcome.error`, 019 §4's words, unchanged
    #
    # 019 §3.2's timeline form is untouched: 047 ruled on `outcome.error` alone.
    "outcome.error_origin": (
        "Failed — {status}: {body}, reported by {origin}.", RULED_BR047),
    # 030 §1: the eighth sentence, ruled. It deliberately does NOT carry the unavailable
    # row's "not evidence of tampering" clause: absence says nothing and the reader must be
    # told so, but a mismatch is the presence of the wrong code. The page names the fact and
    # says nothing about why — it neither accuses nor absolves.
    "reproduce.not_run.mismatch": (
        "Couldn't be re-checked: the code available here is not the code that ran.",
        RULED_030 + " §1"),
    # 030 §2: blank means no report, and nothing else. A clean result renders a sentence.
    # Worded against its neighbours: a single run compares nothing to anything, so neither
    # "comparison" nor `reproduce`'s "re-checked" belongs in it.
    "localize.clean": (
        "The record holds together — there is no step to point at.",
        RULED_030 + " §2"),
    # 030 §3: one fixed frame per no-result state, filled with the verb's own words verbatim.
    # No assessment clause, no paraphrase: the reader sees the verb's sentence as the verb's.
    "comparison.not_comparable": (
        "These two can't be compared — {reason}.", RULED_030 + " §3"),
    "comparison.refused": ("Refused before checking — {reason}.", RULED_030 + " §3"),
    "comparison.could_not_check": ("Couldn't be checked from here — {reason}.", RULED_030 + " §3"),
    "localize.could_not_check": ("Couldn't be checked from here — {words}.", RULED_030 + " §3"),
    "verb.did_not_start": ("The check didn't start — {reason}.", RULED_030 + " §3"),
    # 031 §3 ruled that a section ON the page which received no report says so in one fixed
    # sentence, and blank means the section is not there at all. That much stands. Its two
    # sentences did not survive contact with C023:
    #
    #   - the comparison section already had a ruled sentence (`verbs.not_run`, C023 §4), so
    #     031 §3's second one was a duplicate wording of a ruled state and is WITHDRAWN by
    #     033 §2. A state that has a sentence does not get another.
    #   - the re-check section had none, so 031 §3's ruling stands — reworded once by 033 §2,
    #     before any test pinned it, into C023's shape so the two absences read as a pair.
    "absence.no_recheck": (
        "No re-check from the record was run, so this page does not say whether anything comes "
        "out the same.",
        RULED_033 + " §2"),
    # 023 §4, adopted as written
    "strip.unreadable": (
        "This answer's trail could not be checked from here — the check's report could not "
        "be read. That is an access problem, not evidence of tampering.",
        ADOPTED_NOTE_015),
    "strip.contradicts_list": (
        "This answer's trail was checked on {date} — the record contradicts itself in its "
        "list of steps.",
        ADOPTED_NOTE_015),
    "anchoring.would_add": (
        "Anchored, it would read: this record existed by a stated date and hasn't changed "
        "since — checkable against an independent anchor.",
        ADOPTED_NOTE_015),
    "answer.not_in_package": (
        "The answer's text is not part of this record package. It is identified by its "
        "fingerprint below.",
        ADOPTED_NOTE_015),
    "question.not_in_package": (
        "The question's text is not part of this record package. It is identified by its "
        "fingerprint.",
        ADOPTED_NOTE_015),
    "sample.label": (
        "Generated from a preview sample record, not from a production run.",
        ADOPTED_NOTE_015),
    "card.ran_as": ("Ran as {id}, version {version}.", ADOPTED_NOTE_015),
    "card.read_by": ("Read by {id}, pinned.", ADOPTED_NOTE_015),
    "answer.no_step": (
        "This record has no step that wrote an answer, so there is no answer to show.",
        ADOPTED_NOTE_015),
    "not_run.other": (
        "Could not be checked from here, and the check says why:",
        ADOPTED_NOTE_015),
    "outcome.unknown": (
        "The record states an outcome this page has no words for, shown exactly as recorded:",
        ADOPTED_NOTE_015),
    "anchor.anchored_no_date": (
        "The record says it is anchored and states no date for the anchor, so this page "
        "claims none.",
        ADOPTED_NOTE_015),
    # Release 1 ships with no authorization records, and "The ladder rung
    # reads 'No records · needs an AADP policy engine'". The state and its evidence are the
    # rung's two parts; the page joins them. Never a pass, never blank.
    "rung.state.no_records": ("No records", RULED_28N),
    "rung.authorized.no_records": ("needs an AADP policy engine", RULED_28N),
    # "It holds whether or not the run proposed a change." It replaces
    # batch 2's provisional "None of these says the change was the right one to make."
    "ladder.limit": ("None of these says the run's output or action was correct.",
                     RULED_29X + " item 1"),
    # The execution graph's specification words these itself. Checked against it.
    "graph.linear": (
        "recorded as a straight line (no graph recorded)",
        RULED_C18E5 + ": a run with no `edges` is drawn as a line with this label"),
    "graph.note": (
        "A link shows which recorded output a stage read. It does not by itself prove that "
        "one stage caused the next.",
        RULED_C18E5 + ": the note the graph keeps"),
    "graph.table": ("Show as table", RULED_C18E5 + ": the graph's text equivalent"),
    "graph.region": ("The execution graph, scrolls sideways",
                     RULED_SCROLL + ": the run page's graph panel"),
    "graph.region.comparison": ("Comparison graph, scrolls sideways",
                                RULED_SCROLL + ": the comparison page's graph panel"),
    "region.ladder": ("What the evidence establishes, scrolls sideways",
                      RULED_SCROLL + ": the run page's ladder"),
    "region.steps": ("The steps, scrolls sideways", RULED_SCROLL + ": the run page's step table"),
    "graph.recorded_order": (
        "Recorded order", RULED_C18E5 + ": the link to the existing ordered view"),
    "graph.fold": (
        "{name} ×{n}",
        RULED_C18E5 + ': instances of one stage name fold into one node, "name ×n"'),
    # The graph's three provisional sentences, and the singular of one, as specified.
    "graph.too_large": (
        "This run's graph would need {n} boxes, more than the {max} this page draws. Its nodes "
        "and links are listed in the table below instead.",
        RULED_29DB + ": reworded -- the limit stated as a fact about this page"),
    "graph.outside": (
        "{n} recorded links name a node this run did not record, so they are not drawn: "
        "{links}.",
        RULED_29DB + ": two or more such links"),
    "graph.outside_one": (
        "1 recorded link names a node this run did not record, so it is not drawn: {link}.",
        RULED_29DB + ": exactly one such link"),
    "graph.unreadable": (
        "This record's links cannot be read as links between its steps, so no graph is drawn "
        "for it.",
        RULED_29DB + ": as proposed"),
    # The line naming where a run page's marks come from, and the sentence for a comparison
    # with no readable verdicts, as specified.
    "graph.marked_from": (
        "These verdicts come from the latest comparison of this run against the baseline "
        "{baseline}, stored {at}.",
        RULED_29DF + ": reworded -- \"against the baseline\" already says which side this run "
        "is on"),
    "graph.marks_unreadable": (
        "The latest comparison of this run against the baseline {baseline}, stored {at}, gave "
        "no verdicts that could be read, so none are shown on this graph.",
        RULED_29DF + ": reworded -- one sentence for an unreadable report and a diff that did "
        "not start"),
    # The time rung's yes, read from the verifier's own anchor row.
    "rung.anchored.yes": (
        "existed by {time} · {source}",
        RULED_C18E5_23 + ": Anchor PASS, as the table words it"),
    # The ladder's table: the signing rung read from the verifier's own signature rows with
    # the console's trust file: Yes, No and Not checked as the table words them.
    "rung.signed.yes": (
        "{label} · {key_id}",
        RULED_C18E5_22 + ": Valid, key trusted, as the table words it"),
    "rung.signed.no": (
        "the signature doesn't match this record",
        RULED_C18E5_22 + ": FAIL, as the table words it"),
    # Where ed5 §2.2's table is silent. The verifier's own reason, where it gives
    # one, is shown bare: "the check says" is kept for a failed check.
    "rung.signed.none": (
        "no signature beside the chain",
        RULED_29LK + ": no signature row, Unsigned"),
    "rung.signed.unreadable": (
        "this page can't read the check's words",
        RULED_29LK + ": Couldn't check, words this page can't read"),
    "rung.signed.no_own_check": (
        "a signature is read only from this page's own check",
        RULED_29LK + ": no own check, Not checked"),
    "rung.signed.not_installed": (
        "install onetrace-verify[crypto]",
        RULED_C18E5_22 + ": Extra not installed, as the table words it"),
    "rung.anchored.reason": (
        "the check says: {detail}",
        RULED_29KZ + " §1: ruled as written"),
    # The answer view states an anchor only when the verifier's
    # anchor row passes; otherwise it states the case. No anchor row: nothing about anchoring.
    "answer.anchor.yes": (
        "This record existed by {time} ({source}). That doesn't show when the run happened, that "
        "its outputs were correct, or who wrote it.",
        RULED_29KZ + " §4: Yes"),
    # The stage page's anchoring badge states the run's own rung; its Yes
    # names the whole run's record, since an anchor covers the record, not one stage.
    "badge.anchored.yes": (
        "existed by {time} · {source} (the whole run's record)",
        RULED_29LD + ": Yes"),
    "answer.anchor.couldnt_check": (
        "Anchor present, not checked: {detail}.",
        RULED_29KZ + " §4: Couldn't check, {detail} the verifier's reason"),
    "answer.anchor.failed": (
        "Anchor present; the check says: {detail}.",
        RULED_29KZ + " §4: No, the check failed"),
    # Rung 1's "no" from the outputs-required check, reworded and fixed.
    "rung.records.outputs_differ": (
        "The receipts and links agree, but an output file doesn't match its receipt (checked with "
        "the run's output files required).",
        RULED_29KT + ": reworded and ruled"),
    # "Ran as approved"'s evidence, as proposed, with one change: the doesn't-verify sentence
    # was reworded.
    "rung.approved.yes": (
        "the check's plan row and its edges row both passed, and the run itself verified",
        RULED_29GS + ": as proposed"),
    "rung.approved.departed": (
        'it departed from the plan: {detail}',
        RULED_29GS + ": as proposed"),
    "rung.approved.edges": (
        "the links the record lists don't match the receipts: {detail}",
        RULED_29GS + ": as proposed"),
    "rung.approved.no_plan": (
        'no approved plan recorded',
        RULED_29GS + ": as proposed"),
    "rung.approved.linear": (
        'a straight-line run: there is no plan to compare',
        RULED_29GS + ": as proposed"),
    "rung.approved.cant_check": (
        "the check that ran, {checker}, has no plan row, so it can't say whether the run followed"
        ' its plan',
        RULED_29GS + ": as proposed"),
    "rung.approved.cant_check_unnamed": (
        "the check that ran has no plan row, so it can't say whether the run followed its plan",
        RULED_29GS + ": as proposed"),
    "rung.approved.not_verified": (
        "the run doesn't verify, so whether it followed its plan can't be read from its record; "
        'its own result is above',
        RULED_29GS + ": the fixed words, in place of the proposed 'No' reading"),
    "rung.approved.not_checked": (
        'this page did not run the check itself, so it says nothing of the plan',
        RULED_29GS + ": as proposed"),
    "rung.approved.unreadable": (
        "the check's rows can't be read one by one, so its plan rows aren't read",
        RULED_29GS + ": as proposed"),
}

#: NOT ruled. Emptied by the labels decision (030) and refilled by C036 item 2, which authorises the
#: Executions list and words nothing for it. 024 §4's standing rule applies: provisional until
#: ruled, and the tests assert this set exactly.
#:
#: C036 item 3 is deliberately **not** here. It directs Policy and Incidents to reuse *"the same
#: 'the record stops here' shape used elsewhere for a declared boundary, not new policy/incident
#: vocabulary"*, and says why: *"No new wording is ruled here because there is nothing to word
#: yet: no policy object, no incident key, no data model to describe. Do not invent one."* So
#: those two sections render `verb.not_run.boundary` — 019 §4's ruled sentence, unchanged — and
#: this channel worded nothing for them. **Policy no longer does**: it says
#: "no authorization records", in `policy.none` below. Incidents is unchanged.
#:
#: The run ladder's words. The v6 release canvas is the target, and its board 2 words the
#: ladder; the canvas is not a sealed text, so the words are provisional here until they are
#: fixed, and each entry names the board it is taken from.
PROVISIONAL: dict[str, tuple[str, str]] = {
    "check.not_run.originality_all": (
        "Held under the checks that ran; not anchored, so none of these steps can be shown to be the "
        "record that was made.",
        "the first-impression polish: the reason every step shares, said once for the run"),
    "executions.corpus": (
        "Runs this page was given: {n} of {total}, and it lists every one of them. It is not "
        "a view of a store, and nothing is summarised across runs.",
        "C036 item 2 authorises the list and words nothing for it. The sentence exists because "
        "the memo requires the corpus size to be visible — \"render it as a real list view over "
        "the real corpus, emptiness visible, no synthesized rows\" — and a list that does not "
        "say how little it holds is the pretence the memo forbids. A later decision adds the "
        "denominator: {total} is the size of the set the caller chose these runs from, in runs"),
    "executions.one": (
        "Runs this page was given: 1 of {total}, and it lists that one. It is not a view of a "
        "store, and nothing is summarised across runs.",
        "C036 item 2, the singular case, kept so the page never reads \"1 runs\"; the noun now "
        "leads, so no count is ever followed by it. The later decision's denominator as above"),
    # R11's node set, PROPOSED by this channel at Response 064's invitation. Core ruled the
    # target (060): "the minimal set of unclean nodes `single_run_dag` already returns", and
    # put the presentation of that set outside its own scope. So this is a proposal, not a
    # ruling, and it renders nowhere -- see
    # `test_red_path.py::test_the_proposed_node_set_sentence_renders_nowhere`.
    #
    # **The singular case needs nothing new.** Where the set has one member, 019 §4's
    # `localize.located` already fits exactly -- "It changed -- here is the step where." A set
    # of one IS a located step. Only the plural needs words, which is why there is one entry
    # here and not two.
    #
    # What the plural must carry, from C034 §2 R11: "A drawn graph invites the eye to find the
    # first red node; on a partial order there is no first." So the sentence names the count,
    # names the steps, and denies the ordering the reader will otherwise supply.
    "localize.located_set": (
        "It changed — here are the {n} steps where. Nothing in the record makes one of them "
        "first.",
        "**This channel's wording, by delegation.** The superseding R11 ruling (seal "
        "`463a37b3...a581`) §3 leaves the rendering vocabulary here: 'that's canary's call "
        "under an existing rule' — C034 §3's layer-1 vocabulary rule. So it is not awaiting "
        "core; it is provisional until the READER rules it, exactly as C034 §4 says of "
        "`field.recorded_rationale`. It already does §3's own translation: `single_run_dag` "
        "says 'node', the page says 'step', which is the layer-1 word. Still unrendered and "
        "unfixtured — no delivered receipt declares `edges`"),
    "ladder.intro": (
        "Each rung is a separate question, with its own evidence.",
        "run ladder canvas: v6 canvas board 2, the sentence under the ladder's heading. Its second "
        "sentence, 'There is no single \"checks out\"', is left out: the strip above it says "
        "'every step checks out' (019 §2.1), and the page would contradict itself"),
    "rung.reproduced.count": (
        "{n} of {total} re-run and matched.",
        "run ladder canvas: v6 canvas board 2's evidence for the re-run rung (\"3 of 3 re-run and "
        "matched\"), with its denominator: the stages the re-check report covers, less those "
        "the record declares not replayable, which 019's own sentence names beside it"),
    "rung.anchored.unstated": (
        "The record does not say whether it is anchored, so this page claims no time for it.",
        "run ladder canvas: the time rung when no receipt states an anchor. The canvas draws only "
        "\"not anchored\", which would claim a state the record does not state; this channel's "
        "words, after 023 §4's `anchor.anchored_no_date`"),
    "policy.none": (
        "No authorization records for this run.",
        "run ladder canvas: v6 canvas board 3's heading. 28n §2 requires the state here: never "
        "blank, never a pass. Board 3's next sentence, 'Nothing in the record shows a policy "
        "decision, a permit or a confirmation', is left out: this page does not look for "
        "those in the record, so it cannot say they are absent"),
    # After the independent review: the states a rung can be in without a yes, each said.
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
        "is shown as its first NAME_CAP; the ruling's own words"),
    "name.whole": (
        "the whole value is in the run's record",
        "long-name cap: the page that shortens a value offers the whole value as the "
        "run's own record; this channel's words"),
    "rung.records.no_artifacts": (
        "The check that ran did not require the run's output files, so this page does not say "
        "the records agree.",
        "own-check rung: the rung reads yes only from the verifier run with "
        "--require-artifacts returning PASS. Rung 1 when the check held without that flag. The "
        "pinned verifier (0.1.0) has no such flag (blocker B4), so no page reads yes until it "
        "does; this channel's words"),
    "rung.records.supplied": (
        "This page was given the check's report rather than running the check itself, so it "
        "does not say the records agree.",
        "own-check rung: rung 1 when the report was kept or supplied (`render "
        "--report`). The ruling requires that such a report never sets the rung, and words "
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
        "run ladder canvas: rung 4 with more than one declared step; 019's `rederivable.false` "
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
        "run ladder canvas: rung 6 when every step says anchored. Nothing here verifies an anchor "
        "(X-8), so a declared anchor is never a yes"),
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

#: Section headings and field labels. Adopted as ruled wording (023 §4), checked against
#: Note 015 §7.
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
    "unit.bytes": "bytes",
    "section.reproduce": "What could be re-checked",
    # 030 §1's own words for the two digests beneath the eighth sentence, "nothing else".
    # Core's wording, so ruled — see LABELS_FROM_030.
    "field.ran": "ran",
    "field.available_here": "available here",
    "field.where": "The step",
    "field.what_changed": "What changed",
    "field.reach": "How far it reached",
    "field.recorded_result": "The recorded result",
    "field.new_result": "The result now",
    "where.run_folder": "Run it from the run's folder:",
    "where.run_folder_verifier_elsewhere": "Run it from the run's folder, with the check's script beside you:",
    # C034 §5's proposals, and §4's recorded rationale. **This channel's wording, not ruled**
    # — see LABELS_UNRULED, which carries the bullet each one comes from. They are registered
    # and not rendered: C034 §6 orders §5's items into LABELS_UNRULED **unbuilt**.
    "section.established": "Established",
    "section.not_established": "Not established",
    "field.predecessors": "Came after",
    "disclose.request": "The request, exactly as recorded",
    "disclose.response": "The response, exactly as recorded",
    #: Fixed: the label over the question's lines on the answer page.
    "disclose.question": "The question, as recorded",
    # C036 items 2 and 3. **This channel's wording, not ruled** — see LABELS_UNRULED. C036
    # words nothing for these pages, and says why for items 3: there is nothing to word yet.
    "kind.executions": "Runs",
    "title.executions": "The runs this page was given",
    "section.executions": "The runs",
    "field.steps": "Steps",
    "section.policy": "Policy",
    #: Fixed: the free file's heading for C036 item 3's boundary section.
    "section.incidents": "Where the record stops",
    # The run ladder (v6 canvas board 2). **This channel's copy of the
    # canvas's words, not ruled** — see LABELS_UNRULED.
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
    "rung.state.not_yet": "Not yet available",
    "rung.state.unsigned": "Unsigned",
    "rung.state.not_anchored": "Not anchored",
    "rung.state.signed_untrusted": "Signed, key not trusted",
    # The execution graph's table and folds, as specified -- see LABELS_RULED_29DB -- and the
    # link to a run page's comparison -- see LABELS_RULED_29DF.
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

#: Labels added after 023 §4 adopted the rest, so they are **this channel's wording and not
#: ruled** (024 §4). Each carries why the page needs it, the tests assert this set exactly, and
#: they go to core for ruling in the next note. Every other key in LABELS is adopted wording.
#: Labels whose words core wrote in 030 §1. Ruled, not adopted-from-Note-015, so they are
#: checked against that memo rather than against the note.
LABELS_FROM_030 = ("field.ran", "field.available_here")

#: Fixed by the label-trigger decision (031 §1), each bound to the trigger named for it. They
#: are ruled-pending-reader, like every 019 §4 sentence: adopted, and still to be scored by the
#: reader. The trigger is recorded beside the label because a label is ruled FOR A STATE — the
#: same label over a different field would be a new question.
LABELS_RULED_031: dict[str, str] = {
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
LABELS_RULED_29DB: dict[str, str] = {
    "section.graph": RULED_29DB + ": the graph's heading",
    "graph.col_node": RULED_29DB + ": the table's node column",
    "graph.col_stage": RULED_29DB + ": the table's stage-name column",
    "graph.col_index": RULED_29DB + ": the table's recorded-position column",
    "graph.col_from": RULED_29DB + ": a link's upstream node",
    "graph.col_to": RULED_29DB + ": the node that read it",
    "graph.failed": RULED_29DB + ": a retry's failed attempt, kept visible",
    "graph.link_outside": RULED_29DB + ": a recorded link to an unrecorded node",
}

#: The link to the comparison a run page's graph is marked from, fixed as proposed. Its words
#: stay in LABELS; this names where it was fixed.
LABELS_RULED_29DF: dict[str, str] = {
    "graph.open_comparison": RULED_29DF + ": the link to the comparison the marks come from",
}

#: The free file's heading for C036 item 3's boundary section is fixed as "Where the
#: record stops", in place of "Incidents", whose heading promised what its text never gave.
LABELS_RULED_29DZ: dict[str, str] = {
    "section.incidents": "free-file headings: the free file's heading for the boundary section",
    "disclose.question": "free-file headings: the label over the question's lines on the answer page",
}

#: "Ran as approved"'s question and its "Not declared" state word, the specification's words.
#: Their words stay in LABELS; this names where they were fixed.
LABELS_RULED_C18E5_22: dict[str, str] = {
    "rung.state.unsigned": "ladder table, signing rung: No signature, as the table words it",
    "rung.state.signed_untrusted": "ladder table, signing rung: SIGNED-UNTRUSTED, as the table words it",
}

LABELS_RULED_29GS: dict[str, str] = {
    "rung.approved": "plan rung wording: the plan rung's question, as proposed",
    "rung.state.not_declared": "plan rung wording: the plan rung's no-plan state word, as proposed",
}

#: Labels this channel added that no ruling covers. 024 §4's standing rule: anything added
#: after 023 §4 is provisional until ruled.
#:
#: Refilled by the page-additions proposal (034 §5), which proposes five additions to the page
#: and rules none of them: *"Each item below is provisional. Its labels go into
#: `LABELS_UNRULED`; none is built before §2 is green."* §2 is green as of this commit, so they
#: are registered here — **and only here**.
#: `test_red_path.py::test_c034_s5_labels_are_registered_and_not_rendered` asserts that
#: no page renders any of them, because C034 §6 orders them in *unbuilt*.
#:
#: Each value names the §5 bullet (or §4 paragraph) the label serves. The words are this
#: channel's: C034 gives the items, not their wording, except where noted.
LABELS_UNRULED: dict[str, str] = {
    "check.source_fallback":
        "the reader's specification: it requires the text parser kept \"only as a fallback that "
        "says openly that it is the fallback\", which authorises a sentence and words "
        "none. Three things and no more: what was read, why, and how far the fallback "
        "reaches. The last clause is the one that earns its place -- a reader told only "
        "'this page used a fallback' has been handed a doubt with no edges, and the "
        "receipts, the manifest and the verbs on this page did not come through it",
    "section.established":
        "§5 bullet 4: the heading for the first of V2 §4's two counted lists. C034 supplies the "
        "pairing (\"established / not established\") and says the headings are new words, so "
        "they are provisional until the reader rules them",
    "section.not_established":
        "§5 bullet 4: the heading for the second list, the other half of the same pairing",
    "field.predecessors":
        "§5 bullet 1: for v1 each step card lists its declared predecessors as text and there "
        "is no drawing. A label is needed for that list; C034 does not word it",
    "disclose.request":
        "§5 bullet 3: raw request bytes as a quoted artefact one click down, under 019 §5's "
        "disclosure rule. Worded after `disclose.raw`, which 023 §4 adopted",
    "disclose.response":
        "§5 bullet 3: raw response bytes, the other half of the same disclosure",
    # C036, not C034 §5. Kept in the same register because 024 §4's rule is the same one.
    "kind.executions": "C036 item 2: the Executions list's view name, beside kind.answer/case",
    "title.executions": "C036 item 2: the list page's title",
    "section.executions": "C036 item 2: the heading over the rows",
    "field.steps": "C036 item 2: the column naming how many steps a run recorded",
    "section.policy":
        "C036 item 3: the heading naming the Policy section. The section's *sentence* is ruled "
        "(019 §4's `verb.not_run.boundary`, which C036 directs be reused); only this heading is "
        "this channel's word, and C036 rules no wording here because there is nothing to word",
    "section.ladder": "run ladder canvas: v6 canvas board 2, the ladder's heading",
    "rung.records-agree": "run ladder canvas: v6 canvas board 2, rung 1's question",
    "rung.signed": "run ladder canvas: v6 canvas board 2, rung 2's question",
    "rung.nothing-missing": "run ladder canvas: v6 canvas board 2, rung 3's question",
    "rung.reproduced": "run ladder canvas: v6 canvas board 2, rung 4's question",
    "rung.authorized": "run ladder canvas: v6 canvas board 2, rung 5's question",
    "rung.anchored": "run ladder canvas: v6 canvas board 2, rung 6's question",
    "rung.state.yes": "run ladder canvas: v6 canvas board 2's state word for an established rung",
    "rung.state.no": "run ladder canvas: v6 canvas board 2's state word for a rung that is not",
    "rung.state.couldnt_check":
        "run ladder canvas: the state word for a rung the check could not settle. Not drawn on "
        "board 2; the v6 overview's own tag for that state",
    "rung.state.not_checked":
        "run ladder canvas: the state word for a rung with no evidence to read. Not drawn on the "
        "canvas; this channel's words, kept apart from \"No\" (three-outcome rule)",
    "rung.state.not_yet": "run ladder canvas: v6 canvas board 2's state word for signing",
}

#: Plain words for the stage names the preview format uses. A stage name not listed here
#: is shown exactly as recorded, never guessed at. Adopted as ruled wording (023 §4).
STEP_WORDS: dict[str, str] = {
    "retrieve": "Searched the documents",
    "rerank": "Put the results in order",
    "generate": "Wrote the answer",
    "verify": "Checked the answer against the passages",
}

#: Words that never appear in generator-authored text on the page (019 §4; messaging guide
#: ed. 3 §3). Checked over everything the generator writes; the record's own words and the
#: check's own words are quoted, marked as quotations, and exempt.
RETIRED_WORDS = ("provenance", "lineage", "canonical", "digest", "hash", "verifier",
                 "instrument", "topology", "coverage attestation")
#: Bare state tokens that never appear as words on the page (019 §4).
BARE_TOKENS = ("PASS", "FAIL", "NOT RUN", "NOT-RUN")


_WHY_30BV = ("check coverage wording: a sentence that describes what the check covers says only "
             "what onetrace-verify 0.1.2 checks. ")

#: Sentences of core's that describe what the check covers, reworded to what
#: `onetrace-verify` 0.1.2 checks. Core's words stay where they are, in the table they were ruled
#: into, and each entry here names them; the page draws from here first. Key -> (the proposed
#: words, the words they replace, why). This channel's words, for core to read before merge.
REWORDED: dict[str, tuple[str, str, str]] = {
    "sample.label": (
        "This record is in a preview format ({format}).",
        "Generated from a preview sample record, not from a production run.",
        RULED_29FC + ": the banner's trigger is the manifest's format ending in -preview, which says "
        "nothing of where the run came from, so 'sample' is untrue; the console's specified words "
        "(the preview banner), the format read from the manifest"),
    "strip.holds": (
        "This answer's trail was checked on {date} — each check that ran held.",
        "This answer's trail was checked on {date} — every step checks out.",
        _WHY_30BV + "0.1.2 runs no stage-order check, and checks output files only when the run "
        "carries them, so 'every step checks out' says more than the check did (019 §2.1)"),
    "checks.gaps_none": (
        "Each declared step left a receipt, as the receipts themselves state.",
        "Every step that was declared left a receipt; nothing is missing from the trail.",
        _WHY_30BV + "the reading comes from the receipts' own coverage fields, which no check "
        "confirms; 'nothing is missing from the trail' says more (023 §4)"),
    "check.not_run.originality": (
        "Held under the checks that ran; not anchored, so it can't be shown to be the record "
        "that was made.",
        "Consistent with itself; not anchored, so it can't be shown to be the record that "
        "was made.",
        _WHY_30BV + "0.1.2 runs no stage-order check, so a receipt that misstates it still "
        "passes, and the record is shown to hold only as far as the checks reach (019 §4)"),
    "unchecked.unanchored": (
        "This record held under the checks that ran. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
        "This record is consistent with itself. It has not been anchored, so it cannot be "
        "shown to be the record that was made — here is what anchoring would add.",
        _WHY_30BV + "as check.not_run.originality (019 §2.4)"),
    "anchor.anchored": (
        "The record declares an anchor dated {date}. This console doesn't check anchors, so that "
        "date isn't confirmed here.",
        "This record existed by {date} and hasn't changed since — checkable against an "
        "independent anchor.",
        "anchor wording: the fixed words. 0.1.2 checks only that an anchor state is "
        "declared and this console checks no anchor, so 019 §4's sentence read as proof of time "
        "from the record's own word. A verified anchor PASS earns the stronger sentence at the "
        "0.2.0 re-pin"),
    "section.timeline": (
        "What happened, in the order the receipts give",
        "What happened, in order",
        _WHY_30BV + "the order is the receipts' own, and 0.1.2 does not check it (019's heading)"),
}


def _ruled(key: str) -> str:
    """The words a table other than REWORDED holds for `key`: core's, or this channel's."""
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
