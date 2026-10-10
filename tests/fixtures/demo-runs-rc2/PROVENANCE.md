# The demo's runs: four run folders and the trust file

Recorded by the onetrace 0.2.0 demo (a small help-desk pipeline over invented pages), on the
released 0.2.0 wheels, and copied here byte for byte:

- `ingest-day1`, `ingest-day2`: the help pages indexed on two days; one page changed between them.
- `query-day1`, `query-day2`: the same question asked against each day's index. The query runs
  link to their ingest runs (`ot.corpus_from`), so a comparison can follow the change into them.
- `query-day1` is signed with a test key; `trusted-keys.json`, a trust file, names that key as "test key (demo)".

`SHA256SUMS` lists every file's digest. The tests that use these runs check it before reading them,
so a changed byte fails rather than passes silently.
