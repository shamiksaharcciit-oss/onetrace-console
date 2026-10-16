# Changelog

## [0.2.0]

- **Kept input text.** onetrace 0.2.2 can keep a step's text inputs beside their digests. A step's page shows an input's text only when the step lists it as kept and the stored text matches its digest, with the digest beside it; long text is cut, its full size said. Otherwise it says "not kept" (with the reason the step recorded), "not kept: file missing" (removing kept text is supported; the digest still holds), or "text does not match its digest; not shown" with both digests. Files in a run's `inputs/` folder that no step lists are counted, never shown. The text diff shows kept text only where the console reads both runs' texts as listed and matching; otherwise each side's reading. A public console never shows an externally sourced input's kept text, on a step's page or in the text diff, and its downloaded records leave out kept inputs (the run verifies without them); the demo keeps none. A run recorded by an older onetrace has no kept inputs, whatever its settings are named. The console never writes in `inputs/`.
- **The pins move to onetrace 0.2.2 and onetrace-verify 0.2.1,** from PyPI, each by its wheel's sha256. The verifier's signature extra pins the same versions as before.
- **The demo** records 31 runs of four small example pipelines. The new one is a run of the support reply that asks for a refund window longer than the policy allows: its policy step declines it, records why, and the run stops there.
- **Runs stopped by a step.** A run whose last recorded step declined by its own rule shows "Declined at <step>" on its page and in the runs list, with the reason the step recorded and the declared steps left without a receipt. The Overview counts the runs stopped by a step. It is never shown as a failure: the check ran, and a rule declined.
- **Steps not reached.** On such a run, "Nothing declared is missing" reads "Not reached", names the step it stopped at and the declared steps after it, and is drawn in the declined outline, not red. The Overview counts these runs as "Stopped at a step", not as missing a declared stage. A step missing before the declining one, a run that stopped with no step declining, and a declined run with receipts for later steps still read No.
- **This step in the other runs.** Each step page lists the same step in the other runs of its pipeline: the outcome, and the settings, tool and outputs each recorded, with the values equal to this run's marked. Inputs are not compared across runs.
- **Choose two runs.** Under Comparisons, each pipeline lists its newest runs, and each run's page has a tab, "Choose as run A"; choosing one as run A opens a page of the other runs as run B, each linking to the comparison of the two where the console holds one, and otherwise saying "Not compared yet" with the request that makes it, both keys filled in. No page makes a comparison. A public console lists only the pairs it holds, and says so.
- **Other runs that recorded the same value** (before: "Other runs with the same change") now matches the setting that changed, and counts the pipeline's stored runs that recorded its value, the candidate among them: "<n> of <m> stored runs in P1 recorded chunk_size 512 at stage 2 · split, the candidate among them".
- **"Records agree" reads one way for each run, on every page.** A run's page decides it, and every other page and count says the same: the Runs list, the run's receipt, the Overview's Records agree card and its rung, the Pipelines table, Verdicts by day, All counts, Recent runs, Needs attention first, the comparison pages, and the list the console prints when it starts. Each state has its own words: records agree, contradicts its record, couldn't check, not checked, no verdict recorded. A run whose check held without its output files required is "Not checked (held without its output files required)" everywhere, where it was counted as verified in some places and not checked in others. "Verified", the verifier's word for its own result, is no longer used to count runs. Needs attention first lists runs not checked, and runs with no verdict recorded, in the order it states. A run whose check held, but whose check with its output files required failed, contradicts its record everywhere.
- **"Ran as approved"** is in the runs list, as each run's page reads it. Where the plan can't be decided, it says "Couldn't check".
- **A dark theme**, following the system setting, with a switch in the sidebar to choose light or dark for this browser, or to follow the system again. The choice stays in the browser; nothing is sent. The console's own fonts are in smaller files. The graph draws each step's whole name and its state as a label; the first difference is amber. Fingerprints show their first 12 characters, the whole value beside them.
- **Run names in the runs list** break only at their hyphens at desktop width; they broke every few characters.
- **README.** The three screenshots are retaken from this release's demo.
- **Paths in messages, as written.** Where a file can't be read or written, the access log, a run folder, a stored record and the viewer's own commands named its path with every backslash doubled on Windows. They name it as written.

## [0.1.2]

Fixes only. The pins are 0.1.1's: onetrace 0.2.1 and onetrace-verify 0.2.0.

- **A test that failed in the public repository.** On the `v0.1.1` tag, `tests/test_container_watch_step.py` read a workflow file the public repository doesn't hold, and the suite failed on Linux. That test is no longer in the public repository, and before each release every public test is checked to read only files the public repository holds. The 0.1.1 source distribution still contains the test.
- **The watched folder on Windows.** The line saying which folder is watched showed every backslash doubled. It shows the path as written.
- **Settings that changed, on a graph-shaped comparison.** The table said no recorded setting differs, while the step's note named a changed constant. It lists each setting the steps' notes name, with the value each run's receipt records.
- **The text diff's settings count.** Each step's "settings: N changed" is held to the rows the settings table lists for that step.
- **The demo's support reply.** The draft names the refund window in words; a later policy stage puts in the number of days. Until now the draft left a `{days}` placeholder, which the demo's pages showed.
- **README.** It documents live folder watching and the `--trust`, `--tsa-cert` and `--tsa-root` options. The three screenshots are retaken from the current demo.

## [0.1.1]

- **A richer demo.** `onetrace-console demo` now records 30 runs of four small example pipelines when you start it: a question-and-answer pipeline over an example shop's refund policy, the reference demo's coding agent, a support-ticket triage, and a support reply drafted by a stub whose wording varies from run to run. The draft leaves the refund window as `{days}` on purpose; a later policy stage fills in the number. They make no network calls and use no hosted model. Some are altered after recording on purpose, so the console has something to find.
- **One look on every page,** and one rule for colour: green when a check ran and held, red when it ran and failed, amber when it couldn't be done or wasn't done, grey when the evidence wasn't made. Every coloured label keeps its words. "Unsigned" and "Not anchored" are now their own states.
- **The Overview** has a one-line summary, a count and one line per card, and each definition behind a "?". Times show "2 h ago" beside the time.
- **The comparison page** opens with where the two runs first differ and the command that repeats it, draws a graph for runs recorded as a straight line too, lists the settings that changed, and says so when the two runs come from different pipelines.
- **The text diff** shows line numbers, coloured lines, struck-through removed words, and a count of lines removed and added.
- **Windows:** the console now reads the SDK's output correctly whatever the system's code page. Before, a text diff with an em dash or an accented letter couldn't be read.
- `--help` and `-h` print the usage and succeed; a stopped `demo --public` removes its temporary folder; the console has an icon; the port-in-use message names `--port`.

## [0.1.0]

The first release.

- **A local console for onetrace runs.** `onetrace-console <runs folder>` loads every run in a folder; `onetrace-console demo` loads the reference demo's two runs and compares them. It listens on 127.0.0.1 only and makes no network calls.
- **Each run, as the verifier reads it:** the result and every row, the stages, and the run's receipt, including whether it is signed and anchored.
- **Two runs compared** with the SDK's own `diff`, and the text that changed.
- **Counts with what they count,** each linking to the exact runs behind it.
- **A container for a team,** with sign-in, TLS and ingester tokens: see `OPERATOR_README.md`.
- **A read-only demo:** `onetrace-console demo --public` tries it on your machine, and a configuration with `"public": true` serves one, refusing every write.
- Requires `onetrace` 0.2.0 and `onetrace-verify` 0.2.0 with its `[crypto]` extra, on Python 3.12 or later.
