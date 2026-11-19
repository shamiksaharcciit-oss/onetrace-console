# Format 0.5's step kinds, agents, tool calls and messages: where these runs come from

## The two recorded runs

`agents-kept/` and `agents-not-kept/` were recorded by `tools/make_agent_runs.py` running `tools/onetrace_runs/agents.py`
(`MADE.json` names each command), with onetrace 0.8.0 installed from these wheels, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:67c392fc2bdfb20c878fdc639bc436b75ceebca8c75c75b3ca494eaad2b3e5ab`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:43534ea75af007670de7fbf469380a4e59669cf9cefeb52980f9b97602c29650`

They are onetrace 0.8.0's release files as their first build gave them. The runs keep that record when the console's
pins move to another build of 0.8.0: they are data, recorded once.

## The five reject vectors

`reject/` holds five of onetrace 0.8.0's own reject vectors, copied byte for byte from its sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.
They are the same bytes in an earlier build of onetrace 0.8.0's sdist, which they were first copied from.
Each is a run whose verifier reads one FAIL, on the member named:

- `R41-step-kind-outside-list`: `[FAIL   ] receipts/04-decision.json: step kind -- 'tool' is outside the eight`
- `R45-requested-by-not-earlier`: `[FAIL   ] receipts/02-weather.json: tool_call requested_by -- answer is not an earlier step of this run`
- `R47-run-agent-disagrees`: `[FAIL   ] run agent -- the receipts disagree on run_agent: receipts/03-c.json's is not receipts/01-a.json's`
- `R74-message-digest-out-of-form`: `[FAIL   ] receipts/01-s.json: messages -- messages[1]: digest 'sha256:00' is out of form`
- `R79-received-no-such-seq`: `[FAIL   ] receipts/02-billing.json: messages_received -- messages_received[1]: answer has no message at seq 2`

## The files

- `reject/R41-step-kind-outside-list/MANIFEST.json`: `sha256:5b7fa5d4dda497c063c19a8fa142c90b02e4cee108dcc227e0e2267c0206d844`
- `reject/R41-step-kind-outside-list/artifacts/01-model-call/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/02-tool-call/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/03-retrieval/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/04-decision/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/05-state-read/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/06-state-write/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/07-transform/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/artifacts/08-other/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R41-step-kind-outside-list/receipts/01-model-call.json`: `sha256:e23d5aacbe4c40d9c24a5aa6870024cd378737e5f09d3987e4cf06f5ff85af6c`
- `reject/R41-step-kind-outside-list/receipts/02-tool-call.json`: `sha256:6fa3b7673d91b3836d9691fb76030c340e6c7a208fdbc8a94170a2600073c869`
- `reject/R41-step-kind-outside-list/receipts/03-retrieval.json`: `sha256:48396ce2716546ac105ecde94d996cd3081d8cba0baa5c7738cc538f7523e434`
- `reject/R41-step-kind-outside-list/receipts/04-decision.json`: `sha256:30b9efa3ab0720ed5cb288ce889c9b0666919b611ce2448c680b2e008702b1d4`
- `reject/R41-step-kind-outside-list/receipts/05-state-read.json`: `sha256:d1330dc91f37a2962318d532e4b2d98edbb567b7f9ae799fa23e96072d79b0a1`
- `reject/R41-step-kind-outside-list/receipts/06-state-write.json`: `sha256:d13c84cd8abdeea4a04e6ef441e5f98e55fe17c2fc6cf6b145c83f125dd7e9ad`
- `reject/R41-step-kind-outside-list/receipts/07-transform.json`: `sha256:8a9ab763a9192272b4302bf454749acbf6bece11dcafa43b1829d5ba8ef078ac`
- `reject/R41-step-kind-outside-list/receipts/08-other.json`: `sha256:3f1227d16c10ac7d9d1fdd5d2c9f3d0b00207f966b64aad261b79f6217ee6a90`
- `reject/R41-step-kind-outside-list/receipts/09-onetrace-close.json`: `sha256:36e5a68f2ef2b138150e18f0cc08e14a22c1dcb3b607f16c1224b8b6fcca9b1e`
- `reject/R45-requested-by-not-earlier/MANIFEST.json`: `sha256:7a8e20540b15facafe8e691c281ee8422e21be2c14ddd325c072916439ef1c3c`
- `reject/R45-requested-by-not-earlier/artifacts/01-openai-chat-completions-create/response`: `sha256:034b0f15a22fd4674fe6aa9317b37c8a7dd4dca9995b99c9ad4affb0511aab82`
- `reject/R45-requested-by-not-earlier/artifacts/02-weather/out.json`: `sha256:9dd40084bfe87887c08054efa73dc68cfe911c02abb85c5fc283bbbb368e079d`
- `reject/R45-requested-by-not-earlier/artifacts/03-answer/out.json`: `sha256:49e3b292eca69a884503802849939ec453d4b92f536090c0f1a7d7f3677019a7`
- `reject/R45-requested-by-not-earlier/receipts/01-openai-chat-completions-create.json`: `sha256:a11d57782c8ea8215abcc4b01462aeec3da9bb2fc95277a851b683f529a007cc`
- `reject/R45-requested-by-not-earlier/receipts/02-weather.json`: `sha256:c42d260263ad7d8eac93267d488382dff556c49d4bab033f43256a9e5fa9c369`
- `reject/R45-requested-by-not-earlier/receipts/03-answer.json`: `sha256:4fb9b176e850368fe4ac46912fecc0d0325d3bb6ce2e8fb5c454e11233d38515`
- `reject/R45-requested-by-not-earlier/receipts/04-onetrace-close.json`: `sha256:30239c1648442337dcc0d535281e0229eb30b5cd41ecbae207281fec9157fbbf`
- `reject/R47-run-agent-disagrees/MANIFEST.json`: `sha256:6f3f3a2af216ac3013cceea95f7f825b36be46be51be98cfe774bacab0a7cf28`
- `reject/R47-run-agent-disagrees/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `reject/R47-run-agent-disagrees/artifacts/02-b/out.json`: `sha256:10b3cf7aadb15b907075f5d7bff8ef7cfa858c395cb9fb6f729f57313e14cd69`
- `reject/R47-run-agent-disagrees/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `reject/R47-run-agent-disagrees/receipts/01-a.json`: `sha256:5ea92c93190ffd64a5768aec147da5c703928cbc6bebf9cfab0f4627ffbcc7ef`
- `reject/R47-run-agent-disagrees/receipts/02-b.json`: `sha256:d9c1e931437c89e14b5bb32b8c76ab2f215657405141baf68301778fa4982d24`
- `reject/R47-run-agent-disagrees/receipts/03-c.json`: `sha256:6b1d1a3e0d084209e0a647a676185827eaaecfc4daf28b1aa976e9067983fd35`
- `reject/R47-run-agent-disagrees/receipts/04-onetrace-close.json`: `sha256:0245636a6ca5fd3f4965ed27bb6a76f7ecdc8fa12f51e39d605e17dc0546c51b`
- `reject/R74-message-digest-out-of-form/MANIFEST.json`: `sha256:1d373639b1934a107908fe99069e6d8743e5055398ca555e6cf77e78d5589069`
- `reject/R74-message-digest-out-of-form/receipts/01-s.json`: `sha256:29836ff8b9708520747f6c7aaa694f3ccb66c88a37d75c420f204b97ee6b8d39`
- `reject/R74-message-digest-out-of-form/receipts/02-onetrace-close.json`: `sha256:abd48f048ad9168945e35eed74bf0421490ec4a93868557408d4fe3a2ede807a`
- `reject/R79-received-no-such-seq/MANIFEST.json`: `sha256:a04cff7db9327735ae24c747dcbead7db910655ea1032c11a8cf5ef48b178657`
- `reject/R79-received-no-such-seq/artifacts/01-answer/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R79-received-no-such-seq/artifacts/02-billing/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R79-received-no-such-seq/messages/01-answer/1`: `sha256:38c624c304cbf9bd6747db56f837c3dce3acdfa65ba2ab579154b1322f8175dd`
- `reject/R79-received-no-such-seq/receipts/01-answer.json`: `sha256:cddc36cac1abc8cd8ba569c38af57c47dc555fbb8f74b1f9333f81cab6e59e2f`
- `reject/R79-received-no-such-seq/receipts/02-billing.json`: `sha256:5b8824cd3fed6012ac5e3c7fda651625343ff13ded042d0bb6af97c30f04d6fa`
- `reject/R79-received-no-such-seq/receipts/03-onetrace-close.json`: `sha256:5853f1cfb40fcee8efa9dfef34b5267497b9bc6fb68cc8ff8f1d06192b3fb00b`
