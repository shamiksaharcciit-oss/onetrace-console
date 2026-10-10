# Changelog

## [0.1.0]

The first release.

- **A local console for onetrace runs.** `onetrace-console <runs folder>` loads every run in a folder; `onetrace-console demo` loads the reference demo's two runs and compares them. It listens on 127.0.0.1 only and makes no network calls.
- **Each run, as the verifier reads it:** the result and every row, the stages, and the run's receipt, including whether it is signed and anchored.
- **Two runs compared** with the SDK's own `diff`, and the text that changed.
- **Counts with what they count,** each linking to the exact runs behind it.
- **A container for a team,** with sign-in, TLS and ingester tokens: see `OPERATOR_README.md`.
- **A read-only demo:** `onetrace-console demo --public` tries it on your machine, and a configuration with `"public": true` serves one, refusing every write.
- Requires `onetrace` 0.2.0 and `onetrace-verify` 0.2.0 with its `[crypto]` extra, on Python 3.12 or later.
