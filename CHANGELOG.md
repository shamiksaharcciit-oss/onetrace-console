# Changelog

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
