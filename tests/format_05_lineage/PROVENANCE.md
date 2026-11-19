# Format 0.5's lineage: where these runs come from

`state-followup/` was recorded by `tools/make_lineage_runs.py` running `tools/onetrace_runs/state_followup.py`
(`MADE.json` names the command), with onetrace 0.8.0 installed from its release files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

Its one step reads the ticket note that `tests/format_05_state/state-kept`'s `note` step wrote (the same store, key,
version and value) and the orders table, which no run writes.

`state-plain-writer/` was recorded by `tools/make_lineage_runs.py --plain` running
`tools/onetrace_runs/state_plain_writer.py`, with the same wheels. Its one step writes the same ticket note, at the same
store, version and value, but keeps its key in plain, where `state-followup` keeps only the key's digest.
