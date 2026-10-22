# onetrace-console

A local web console for runs recorded with [onetrace](https://oneproof.dev/onetrace/): every run in one place, each one checked by the verifier, and any two compared stage by stage.

The console never computes a verdict of its own. It keeps each run's files exactly as they were written, runs `onetrace-verify` and the SDK's own `diff` over them, and shows what those report. If the console and the run folder ever disagree, the folder is right.

## Install

```
pip install onetrace-console
```

It needs Python 3.12 or later. It installs from PyPI alone: `onetrace` 0.4.0 and `onetrace-verify` 0.4.0, with the `[crypto]` extra so signatures and anchors are checked. The pages' viewer ships inside the package.

`pip install onetrace-explain` makes the Explain button on the local console's comparison page work: the console runs that command, which sends a packet of the comparison to the model you name, and its format is set out at [explain-format.md](https://oneproof.dev/onetrace/explain-format.md).

## See it with the demo's runs

```
onetrace-console demo
```

This records the demo's runs into `onetrace-console-demo/` under the folder you start it from, starts the console, loads them, stores ten comparisons, and prints the pages' addresses. The runs come from seven small example pipelines that ship with the console: a question-and-answer pipeline over an example shop's refund policy, the reference demo's coding agent, a support-ticket triage, a support reply drafted by a stub whose wording varies from run to run, and three over physical readings: a pump's vibration to a maintenance work order, a camera frame of a bottle to a fill-level reject, and a temperature logger to releasing or quarantining a shipment. The draft names the refund window in words; a later policy stage puts in the number of days. Every reading, ticket and name in them is invented example data, and the demo records and compares; it controls no equipment. They make no network calls and use no hosted model: the embedder is a hashed bag of words, the answerer quotes the text it retrieved, and the times in the records are the times you ran it. Nine of its runs are broken on purpose when the demo is built; the read-only demo's Overview lists each one, with what was done to it and what its own page reads. The demo keeps its store and its trust file in that folder too. It runs in local mode, so it refuses to start while `ONETRACE_CONSOLE_CONFIG` is set.

![The Overview, with the demo's 41 runs from seven pipelines](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.3.0/docs/screenshots/overview.png)

A read-only copy of the demo is hosted at https://demo.oneproof.dev. To try the read-only mode yourself, run `onetrace-console demo --public`.

## Your own runs

```
onetrace-console <runs folder>
onetrace-console <runs folder> --compare <run A> <run B>
onetrace-console <runs folder> --open
onetrace-console <runs folder> --trust <file> --tsa-cert <file> --tsa-root <file>
```

- `onetrace-console <runs folder>` loads every run folder in it: every folder holding a `MANIFEST.json`. It compares nothing unless you ask.
- A run folder is skipped, with the reason, while the others load: a run still being recorded (it holds onetrace's `.lock`), a folder that holds a link, or a folder whose `SHA256SUMS` doesn't match its files.
- `--compare A B` compares two of them, named by their folder names; A is the baseline.
- `--open` opens the console in your browser.
- `--port N` listens on port N, here and for `demo`. The default is 8080.

### Watching the folder

While the console runs, it reads the runs folder again every 2 seconds and takes in each new run once it has finished writing: once the run folder holds a `MANIFEST.json`, no `.lock`, and the same files at the same sizes on two reads in a row. A run still being recorded is not shown until then.

- The Overview and the list of every run say which folder is watched and when it was last read. When new runs have been taken in since the page was drawn, the page says so, with a link to show them; it doesn't reload by itself.
- A run is taken in once. If its folder changes afterwards, the stored copy stays as it was recorded and the page says the folder now differs; a run folder deleted afterwards stays in the store, with a note that it is no longer in the folder.
- Started on a folder with no finished run in it, the console waits for one. `--compare A B` naming a run folder that isn't there yet waits too, and the comparison is made when both have arrived.
- The folder is read by polling, the same way on Windows, macOS and Linux.
- `--watch-interval N` reads it every N seconds instead. `--no-watch` reads it once, at start, and not again; a folder with no run folder in it is then refused.

### Signing and anchoring

- `--trust FILE` names the signing keys you trust, in an `onetrace-trust/0.1` file. A run signed with one of them reads "Signed by a known recorder: Yes", with that key's label from the file. Without `--trust`, a signed run reads "Signed, key not trusted".
- `--tsa-cert FILE` and `--tsa-root FILE` name the RFC 3161 time-stamp authority you trust and the root its certificate chains to. They go together; `--tsa-root` may be given more than once. With them, a run's anchor is checked, and "Committed by a known time" reads Yes when the check holds. Without them, an anchored run reads "Couldn't check", and the page names the two options to add.
- Every check runs with these files, and a stored check records which ones it ran with. Started again with the same files, nothing is checked again; with different ones, every run is.
- A file that can't be read is refused at start, with how to fix it.

![One run's page: what was checked, and the verifier's result](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.3.0/docs/screenshots/run.png)

![A comparison of two runs, with the first stage that changed](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.3.0/docs/screenshots/comparison.png)

## What it shows

- **Each run:** the verifier's result and every row it reported, the run's stages, and its receipt, including whether it is signed and anchored.
- **Two runs compared:** the stage-by-stage comparison `onetrace diff` produces, and the text that changed, as the SDK reports them.
- **Counts:** every number with what it counts, and a link to the exact runs behind it.

## What it does not show

Nothing here says which version is correct, who changed the source, or why.

A run's record does not show:

- that the output or the action was correct;
- why the model wrote what it wrote;
- that the signing key wasn't misused (your trust list is what ties a key to a name);
- that the run was correct at the anchored time (the anchor shows only that the record existed by then).

## Where it runs

Started as above, it listens on 127.0.0.1 only; `--open` asks your browser to open the local page. The console makes no network calls. The Explain button runs onetrace-explain, if you install it, and that command sends an evidence packet to the model you configure. The first time it would send a kind of item it has never sent to that endpoint, it lists them and asks first. A folder load keeps what it stores in a `store` folder under the folder you start it from, and `demo` keeps it in `onetrace-console-demo/`.

To run it for a team, as a container with sign-in, see [OPERATOR_README.md](https://github.com/shamiksaharcciit-oss/onetrace-console/blob/v0.3.0/OPERATOR_README.md).

## For contributors

On Windows, run the test suite from a short path (for example `C:\src\oc`), or turn on long paths: some of the files the suite writes have paths longer than Windows' 260-character limit.

## Licence

Copyright 2026 Shamik Saha. Licensed under Apache-2.0; see LICENSE.

The bundled IBM Plex fonts are under the SIL Open Font License 1.1.
