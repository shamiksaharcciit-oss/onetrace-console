# onetrace-console

A local web console for runs recorded with [onetrace](https://oneproof.dev/onetrace/): every run in one place, each one checked by the verifier, and any two compared stage by stage.

The console never computes a verdict of its own. It keeps each run's files exactly as they were written, runs `onetrace-verify` and the SDK's own `diff` over them, and shows what those report. If the console and the run folder ever disagree, the folder is right.

## Install

```
pip install onetrace-console
```

It needs Python 3.12 or later. It installs from PyPI alone: `onetrace` 0.2.0 and `onetrace-verify` 0.2.0, with the `[crypto]` extra so signatures and anchors are checked. The pages' viewer ships inside the package.

## See it with the demo's runs

```
onetrace-console demo
```

This copies the reference demo's two runs into `onetrace-console-demo/` under the folder you start it from, starts the console, loads both runs, compares them, and prints the pages' addresses. The demo keeps its store and its trust file in that folder too. It runs in local mode, so it refuses to start while `ONETRACE_CONSOLE_CONFIG` is set.

![The overview, with the demo's two runs](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.1.0/docs/screenshots/overview.png)

A read-only copy of the demo is hosted at https://demo.oneproof.dev. To try the read-only mode yourself, run `onetrace-console demo --public`.

## Your own runs

```
onetrace-console <runs folder>
onetrace-console <runs folder> --compare <run A> <run B>
onetrace-console <runs folder> --open
```

- `onetrace-console <runs folder>` loads every run folder in it: every folder holding a `MANIFEST.json`. It compares nothing unless you ask.
- A run folder is skipped, with the reason, while the others load: a run still being recorded (it holds onetrace's `.lock`), a folder that holds a link, or a folder whose `SHA256SUMS` doesn't match its files.
- `--compare A B` compares two of them, named by their folder names; A is the baseline.
- `--open` opens the console in your browser.
- `--port N` listens on port N, here and for `demo`. The default is 8080.

![One run's page, with the verifier's result](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.1.0/docs/screenshots/run.png)

![A comparison of two runs, with the first stage that changed](https://raw.githubusercontent.com/shamiksaharcciit-oss/onetrace-console/v0.1.0/docs/screenshots/comparison.png)

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

Started as above, it listens on 127.0.0.1 only, and makes no network calls; `--open` asks your browser to open the local page. A folder load keeps what it stores in a `store` folder under the folder you start it from, and `demo` keeps it in `onetrace-console-demo/`.

To run it for a team, as a container with sign-in, see [OPERATOR_README.md](https://github.com/shamiksaharcciit-oss/onetrace-console/blob/v0.1.0/OPERATOR_README.md).

## For contributors

On Windows, run the test suite from a short path (for example `C:\src\oc`), or turn on long paths: some of the files the suite writes have paths longer than Windows' 260-character limit.

## Licence

Copyright 2026 Shamik Saha. Licensed under Apache-2.0; see LICENSE.

The bundled IBM Plex fonts are under the SIL Open Font License 1.1.
