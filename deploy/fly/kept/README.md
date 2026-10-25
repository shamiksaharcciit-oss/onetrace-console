# Kept inputs of the hosted demo

The hosted read-only demo (deploy/fly/Dockerfile) is built from these files when this folder is
there: its runs are taken from here, not recorded anew, and four comparisons show the explanation
kept for them. Without this folder the image builds as before, its runs recorded at build time and
no explanation shown.

These files were made once, on the maintainer's machine, with onetrace-console 0.3.1 and
onetrace-explain 0.1.0, and are served as files. Nothing here is computed again when the image is
built, and no model is called: a public console presses nothing.

## What is here

- `runs/`: the demo's 48 runs, as the demo's builder recorded them, byte for byte.
- `trust.json`: the demo's trust file, the one its runs are checked against.
- `BUILD_RECORD.original.json`: the build record the demo's builder wrote when it built those runs,
  unchanged. It vouches for `runs/`, `trust.json` and the built store; the store is not kept here.
- `BUILD_RECORD.json`: a build record over `runs/` and `trust.json` only, the two things kept. It was
  written by the console's own build-record code (`demo_store.write_build_record`) over the files
  here, not by the demo's builder, and is not signed by anyone. Each of its entries is the original
  record's entry for the same path, and it has no entry the original lacks;
  tests/test_deploy_fly_kept.py holds that.
- `explain/`: onetrace-explain's own records of four comparisons, as the command wrote them, each a
  record folder with its `.explanation.json` and `.explanation.txt` beside it. The model named in
  each is `anthropic:claude-sonnet-4-6`.

| record | comparison |
|---|---|
| `2026-10-25T13-45-05.744195Z` | P1 `p1-02-baseline-set2` → `p1-08-candidate-set2` |
| `2026-10-25T13-39-09.069959Z` | P5 `p5-32-pump-baseline` → `p5-33-pump-offset-changed` |
| `2026-10-25T13-50-49.727866Z` | P8 `p8-42-invoice-tolerance-2pct` → `p8-43-invoice-tolerance-5pct` |
| `2026-10-25T13-42-26.188702Z` | P9 `p9-46-torque-baseline` → `p9-48-torque-one-bolt-low` |

## How a changed byte is refused

- A run or the trust file: `--runs-from` takes them only where `BUILD_RECORD.json` vouches for every
  byte; one changed, added or removed file stops the build, naming it.
- An explanation: `--explanations` keeps one only where its record verifies with onetrace-verify, its
  explanation is its record's own post-check with its record's model, and its evidence names two
  runs of a comparison the build holds. Each record's evidence pins each of its two runs by the
  sha256 of its `MANIFEST.json`, which names the run's chain head, and of each of its receipts; so an
  explanation is kept only beside the very runs it explains. Anything else is refused with its reason,
  in the built store's `x/kept.json`, and never shown.

A suggested explanation is a suggestion about a record, never a reading of it: each is shown with
its label, its model, its claims and their cites, and nothing the console draws as a verdict, a
badge or a count reads it.
