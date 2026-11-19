# Format 0.5's cross-service link: a run id two runs share

`link-desk/` and `link-billing-twin/` were recorded by `tools/make_link_runs.py --twin` running
`tools/onetrace_runs/linked_desk.py` and `tools/onetrace_runs/linked_billing.py` (`MADE.json` names the command), with
onetrace 0.8.0 installed from its release files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

The desk is recorded again under the run id `tests/format_05_link/link-desk` has, as a second service that names its
runs alike would: two runs, one id, two chains. A link that names a head picks the run whose chain holds it.
