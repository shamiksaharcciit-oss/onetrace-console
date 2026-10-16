# onetrace — instrument-change diff. Addendum to Spec_onetrace_Verbs_v1 (no code)

**An addendum only, with no release planned for it, as for the parent
spec, whose code waits on the test battery** ·
Extends `Spec_onetrace_Verbs_v1_2026-09-13.md`
(sealed e3ec7077c8092a990767f7d394a6cdb3651e9ba3a7e57e72fed3a9e9e3c76a92) ·
Triggered by a scenario, 13 Sept: a new chunker version is introduced;
onetrace's init routine is told an instrument changed; it runs a simulation
and reports the difference.

## 0. What this is, in one line

Not a fourth verb. It is `diff` (§2 of the parent spec), triggered
automatically by an instrument-fingerprint change instead of by a person
naming two runs.

## 1. Trigger — no new record field

The instrument block already carries `config_digest` and `manifest_digest`
per instrument id. The init routine keeps the last-known pair for each
instrument id it has seen and compares the incoming pair against it at
startup. A mismatch is the only signal; nothing in the record format changes.

## 2. What's actually new: a fixed reference corpus

`diff` normally compares two already-recorded runs. Here there is only one
new run — the routine has to manufacture the other side by re-running the
*previous* instrument version, and it cannot do that fairly against whatever
production traffic happens to be flowing that day. It needs a small, fixed,
versioned corpus — held out, checked in, reused every time any instrument
changes — so a 3.4→3.4.1 result and a future 3.4.1→3.5 result are comparable
to each other rather than artifacts of two different days of production data.
Sizing follows the smoke-test discipline already in house (`fetch_corpus.py`'s
5-document check): cheap and fast enough to run on every version bump, not a
full-corpus job.

## 3. Precondition: rederivability must already be known

Before a fingerprint-triggered diff can report FIRST DIFFERENCE and mean "the
version change did this," the instrument's own baseline stability has to be
measured (Run B, 12 Sept) — an instrument that isn't bit-stable run-to-run
will look "different" on every init whether or not the version moved. If that
measurement doesn't exist yet for this instrument, the routine reports
COULD NOT CHECK (§4 of the parent spec) rather than a false verdict. This is a
gate on shipping the feature, not a detail to fix later: an instrument-change
diff without a rederivability baseline is not trustworthy the first time it
runs.

## 4. Report shape

Same stage ladder and closed verdict vocabulary as `diff` (§1.2, §2 of the
parent spec), with one addition at the top: the instrument id, the old/new
version pair, and the old/new `config_digest` pair it fired on — the same
identity fields `localize` already surfaces (§3). The report names the config
that changed; it does not characterize the change as safe, a regression, or
intentional. That judgment stays with whoever reads it, per every other
ruling this week.

## 5. Evidence already in hand

This is not hypothetical. The chunker 3.4→3.4.1 comparison run on the test machine
this week — chunk count nearly tripling, quiet on one corpus and loud on
another — is this exact scenario, done by hand. Automating the trigger does
not require proving the mechanism works; that part is already dogfooded and
counts toward the parent spec's acceptance clause (§5: this week's
hand-worked numbers, reproduced through the SDK, or the verbs don't ship).

## 6. Scope fence — this addendum covers onetrace only

Two adjacent ideas surfaced alongside this one and are explicitly out of
scope here: gating a deploy on a clean diff report is a onedoor (Prevent)
decision consuming this report, not specified by it; watching production for
an instrument change that skipped the gate is a onewatch (Detect) invariant,
not this mechanism. Both are real and both stay unscheduled until named
separately.

## 7. Status

No release is planned for it. Ships, if it ships, as part of the `diff` verb's next line,
with the chunker 3.4→3.4.1 corpus added to the dogfood ring (§5 of the parent
spec) as a named acceptance case: instrument-change diff must reproduce this
week's result before it ships.
Integrity: sha256(body) = fc2a785182ec950b08ab0cb728dcfcc45d28a6447f67c7a94ecfaa8850242c55
