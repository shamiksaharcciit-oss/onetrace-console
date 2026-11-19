# Format 0.5's expectations checked during the run: where these runs come from

## The two recorded runs

`expect-record/` and `expect-stop/` were recorded by `tools/make_expect_runs.py` running
`tools/onetrace_runs/expect_checked.py` (`MADE.json` names each command), with onetrace 0.8.0 installed from its release
files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

In `record`, an expectation that holds, one that fails and a batch under its threshold; in `stop`, one that fails and
stops the run. Both read FAIL, as a FAIL in `record` or a stop does.

## onetrace's own vectors

`accept/` and `reject/` hold five of onetrace 0.8.0's own vectors, copied byte for byte from its release sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

- `accept/A67-expect-not-kept`: a stop on a run that keeps no outputs: the written result can't be re-read.
- `accept/A72-expect-off-identical`: expectations not checked during the run (`off`): no `checked`.
- `reject/R104-stop-not-stopped`: a FAIL in `stop`, and the run ended by `exit`: the stop row FAILs.
- `reject/R105-batch-count-differs`: a batch written as failed 1 of 4 and read as 2 of 4: its row FAILs.
- `reject/R107-batch-outcome-against-count`: a batch written PASS over its threshold: the verifier reads FAIL.

## The files

- `accept/A67-expect-not-kept/MANIFEST.json`: `sha256:b1060bcc0f977afa6bfe37e27b98dcc181b4a78206a3dea42b6a0d4d742fcd9d`
- `accept/A67-expect-not-kept/receipts/01-s.json`: `sha256:a07c952bacee811ecd00eef15b7dd81b0eb50437af4233253a0e549fab4f1068`
- `accept/A67-expect-not-kept/receipts/02-onetrace-close.json`: `sha256:244553999dbd6bd0903f8a9963fe10146dbc9678677e43b4c4229b2e0aa5f5f5`
- `accept/A72-expect-off-identical/MANIFEST.json`: `sha256:c0a3015414ee68b9323e187fedfca63ffa2c975e6d04bba79c9513074ed11f80`
- `accept/A72-expect-off-identical/artifacts/01-s/out.json`: `sha256:130f8600809612d27afaae7f0a8e118bcef4ec66aa984ce2734b49419dd550e3`
- `accept/A72-expect-off-identical/artifacts/02-t/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `accept/A72-expect-off-identical/receipts/01-s.json`: `sha256:29472cf27098fc51ac18495d80dca7a0cd689259327eb5e2d3576af7f5b0cb5b`
- `accept/A72-expect-off-identical/receipts/02-t.json`: `sha256:223c32b40f657f3b22bced6e1d765071744d5a1c05af9945a07f0cc0e8699515`
- `accept/A72-expect-off-identical/receipts/03-onetrace-close.json`: `sha256:26344c280be269535618a4211244f742e3f8b31dcb2ef86fe8869e24cf3c80ce`
- `reject/R104-stop-not-stopped/MANIFEST.json`: `sha256:7380ecc77d83e8ce0cafc106700b963d4daaee3d92aecb92592fe51be225fb8b`
- `reject/R104-stop-not-stopped/artifacts/01-s/out.json`: `sha256:130f8600809612d27afaae7f0a8e118bcef4ec66aa984ce2734b49419dd550e3`
- `reject/R104-stop-not-stopped/receipts/01-s.json`: `sha256:9b8f008ec4c59e643d20a5156e02ca3c2d110302dfb2c58f6de240fc439ac2a6`
- `reject/R104-stop-not-stopped/receipts/02-onetrace-close.json`: `sha256:480000b9dcf2cc3494885812c5374c158142e71a252a6780b919ba6398d9aeaa`
- `reject/R105-batch-count-differs/MANIFEST.json`: `sha256:cc825d8d3a7f582682c9c856585c7f5130f2ecaa4260f3ffea31b00d632660a0`
- `reject/R105-batch-count-differs/artifacts/01-s/out.json`: `sha256:e354dfb0ad8aa83f868952029bbeeb11daf2440f37c74269273cffb446dd483e`
- `reject/R105-batch-count-differs/receipts/01-s.json`: `sha256:a0001ebb16c8366b030aed7f179697a8c788e2ebe422ebc194be39ed9c79b46c`
- `reject/R105-batch-count-differs/receipts/02-onetrace-close.json`: `sha256:8700a9697d2e004d33f0166668743680e1f900d5a0a4122f41430aa4c306e106`
- `reject/R107-batch-outcome-against-count/MANIFEST.json`: `sha256:d6280c7f054bb92e4b3b4e3beaf692046b3e543e961d94a5d54f90e12e6714f5`
- `reject/R107-batch-outcome-against-count/artifacts/01-s/out.json`: `sha256:e354dfb0ad8aa83f868952029bbeeb11daf2440f37c74269273cffb446dd483e`
- `reject/R107-batch-outcome-against-count/receipts/01-s.json`: `sha256:07609abfe5f71055a5904730e5bc259da6344fc77998c12fbd2bb32609fb4328`
- `reject/R107-batch-outcome-against-count/receipts/02-onetrace-close.json`: `sha256:0617fb3c7a689c20d4e0c59911f956e865539fdf111ea47270b6bf03b0500dbb`
