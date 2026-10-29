# The incident rule table — the specification

**This document is the specification, and it is written by hand.** The code keeps its own
table in `src/onetrace_console/incidents.py`; a test fails if the two differ in any rule's id,
source, field, condition or displayed words.

That direction matters. This file was generated from the code in its first version, and core
ruled that out: *"Generating the document from the code would make it describe whatever the
code does, rather than what the code was asked to do."* A change to a rule is therefore a
deliberate change here, which core can review, followed by a change to the code to match.

**There is no digest written into this file.** Digests are computed into documents by tooling
and never transcribed (X-11), and a digest typed here by hand would be the one number in the
specification that nobody had checked. The digest of the table lives in `RULES.SHA256`, written
by `tools/rule_digest.py`, and a test asserts it is the digest of the table the code holds —
which is in turn asserted to match this document.

## What an incident is

An incident is a **record that a stored report says a specific thing**. It is raised
mechanically, by one of the rules below, from a report that already exists.

- It has **no severity, no score, no rank and no "risk"**. There is no field for one.
- There is **nothing to do to it**: no acknowledge, assign, close or comment. That needs
  identity and roles, which arrive with tenancy; this slice is read-only.
- It **never re-states a verdict in the console's own words.** It quotes the source field and
  links to the report.

The console never decides that something is an incident on its own judgement. If a rule below
cannot find words to quote, it **raises** rather than inventing any.

## The rules

| id | source | field | condition | words shown |
|---|---|---|---|---|
| `I-CONTRADICTS` | the run's stored verifier report (`check_report`) | `stdout`, its `[FAIL   ]` rows, or all of it where the rows cannot be read line by line | the run's recorded verdict is `contradicts` | the verifier's report carries a failing row |
| `I-RUNID-REUSED` | the run's own record, as the store wrote it | `flags`, the `run_id reused` entry | the store flagged `'run_id reused'` at ingest | two chains arrived under one run name |
| `I-HEADER-DISAGREES` | the run's own record, as the store wrote it | `flags`, the header entry | the store flagged that a delivery header disagrees with the manifest | the delivery's header contradicted its own manifest |
| `I-COULD-NOT-CHECK` | the check runner's record on the run | `check_note` and `topology_note` | the runner recorded a check it did not run, with a stated reason | a check was not run, and the record says why |
| `I-HEAD-SHARED` | the store's records of two run folders | each folder's listing of its files and their object keys | two run folders carry the same run and chain head, and their files differ | Two folders share a chain head but their contents differ |

### Notes on each

**`I-CONTRADICTS`** raises one incident per run, and quotes every `[FAIL   ]` row the stored
report carries, joined and unedited — *"listing each contradicting node or receipt as the report
names it"*. A run recorded as contradicting whose report holds no failing row is a disagreement
inside the stored data: the derivation **raises**, because there is nothing to quote and an
incident that summarised the situation in its own words would be the console forming a view.

**`I-RUNID-REUSED`** and **`I-HEADER-DISAGREES`** read the store's own flags, recorded at
ingest. Their quoted text is the flag exactly as the store wrote it. Each matches only its own
flag: a rule that matched any flag would raise under the wrong id, which a test over a delivery
carrying both flags prevents.

**`I-COULD-NOT-CHECK`** raises one incident per stored reason, and there are two places a reason
is recorded: `check_note`, when the verifier's report could not be read, and `topology_note`,
when the reference topology check is not distributed — the example the rule was written
for. A run recorded as `could not check` with **no** stated reason makes the derivation
**raise**; the reason belongs where the runner records the outcome, not here.

**`I-HEAD-SHARED`** reads two runs a folder load stored from two run folders that carry the same
run and chain head. Runs are folders, not chain heads: each such folder is stored under its own
key and read on its own. Where their files are the same, byte for byte, they are copies of one
run and nothing is raised. Where any file differs, each of the two runs raises one incident,
quoting the rule's sentence and naming both folders. It never says which folder is right; each
folder's own check says what its record holds.

## Incident ids

    id = sha256(rule id ∥ NUL ∥ source sha ∥ NUL ∥ field path)

and, for an incident about a run (every rule above), the run's key after them:

    id = sha256(rule id ∥ NUL ∥ source sha ∥ NUL ∥ field path ∥ NUL ∥ run key)

Deterministic: the same inputs always give the same incident. The NUL separators mean two
different splits of the same characters cannot produce one id. The run's key is there as two
runs' stored check reports can be the same bytes (runs checked in the same second whose rows read
the same): without it, two such runs that contradict their records would share one incident.

**The source sha differs by rule, deliberately.**

- `I-CONTRADICTS`, and the `check_note` half of `I-COULD-NOT-CHECK`, use the **stored check
  report's object key**, which is the sha of the report itself.
- `I-RUNID-REUSED`, `I-HEADER-DISAGREES`, `I-HEAD-SHARED` and the `topology_note` half use the run's
  **`MANIFEST.json` object key**. Those sources are the store's flags and the runner's note —
  recorded *about* a delivery rather than inside a report — and the manifest is the immutable,
  content-addressed thing they were recorded about. Using the mutable run record instead would
  move an incident's id whenever that record later gained a verdict.

## Counting, on the pages

Each group shows **one number, with its denominator and its unit written out in words** — for
example `2 runs of 11`. A second number appears only when it counts a **different unit**, also
written out: `3 incidents across those 2 runs`. Two numbers counting the same unit is one number
too many.

A rule that raised nothing is shown as `0 runs of 11`, **never omitted**. An absent group would
let a reader conclude the rule does not exist (C031 §3: an absence sentence, never a blank).

## Derivation and caching

Incidents are derived from stored reports on every call; nothing is written. No cache exists
today. Any cache **must** include the rule table's digest in its key, so that changing a rule
re-derives and cannot leave a stale incident behind.

## Not built: `I-DIFF-REGRESSION`

**Refused by design, not deferred.**

The rule was made conditional on the SDK labelling a regression itself. It does not, and that
is deliberate. Its own spec addendum:

> The report names the config that changed; it does not characterize the change as safe, a
> regression, or intentional. That judgment stays with whoever reads it, per every other ruling
> this week.

The closed verdict vocabulary is `same · FIRST DIFFERENCE · downstream · reconverged · COULD NOT
CHECK`, with no regression among them. Building the rule would mean this console making exactly
the judgement the SDK reserves for the reader, which C034 §4's *nothing inferred* forbids; a rule
of that name using a threshold of our own would be a score with an incident id.

This was reviewed and kept. A test asserts the spec still refuses the characterisation and
**fails if that changes**, naming the addendum to re-read — at which point quoting the SDK's own
label is all the rule would ever do.
