# Format 0.5's tokens and cost: where these runs come from

## The two recorded runs

`usage-a/` and `usage-b/` were recorded by `tools/make_usage_runs.py` running `tools/onetrace_runs/usage_app.py` through
onetrace-auto (`ONETRACE_AUTO=1`) (`MADE.json` names each command), with onetrace 0.8.0 installed from its release
files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`
- `onetrace_auto-0.8.0-py3-none-any.whl`: `sha256:aa573bb5b47ff06cbe957e2bf23b7bfadc3db354a687dca4a10f57c222448138`

and `openai` 1.58.1, which onetrace-auto's `openai` hook needs, from PyPI, with the files it installed beside it, each by
its sha256 (`--only-binary=:all:`, recording only; none of them is the console's):

- `annotated_types-0.8.0-py3-none-any.whl`: `sha256:f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0`
- `anyio-4.16.0-py3-none-any.whl`: `sha256:c66ae634e0b8228396b801741beb3294326d4b6102f7bba4041c0dfb58c29026`
- `certifi-2026.10.23-py3-none-any.whl`: `sha256:e9b54de76e530bb6cf0ccd036787103acb58fd42ba930ea8bf948ddbaa2f61d1`
- `distro-1.9.0-py3-none-any.whl`: `sha256:7bffd925d65168f85027d8da9af6bddab658135b840670a223589bc0c8ef02b2`
- `h11-0.16.0-py3-none-any.whl`: `sha256:63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86`
- `httpcore-1.0.9-py3-none-any.whl`: `sha256:2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55`
- `httpx-0.28.1-py3-none-any.whl`: `sha256:d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad`
- `idna-3.20-py3-none-any.whl`: `sha256:ab7ae7122974553370f0bdb919e1a960b2cd1bc1ef0276416d896db81c14582c`
- `jiter-0.19.0-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`: `sha256:0956b5f58b804221dfb929c120e6d4032138fed20c1cc0ef683a2d1326255e46`
- `openai-1.58.1-py3-none-any.whl`: `sha256:e2910b1170a6b7f88ef491ac3a42c387f08bd3db533411f7ee391d166571d63c`
- `pydantic-2.14.3-py3-none-any.whl`: `sha256:3f7b347782ab7e4cf4c798496ae3a82787d9f21ec12676a9c564355eeef8daa8`
- `pydantic_core-2.50.4-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl`: `sha256:c81d98e27d9d9261909dcccab1ba5d6ea1c98b0bb9470e368604614fd1d36ddd`
- `sniffio-1.3.1-py3-none-any.whl`: `sha256:2f6da418d1f1e0fddd844478f41680e794e6051915791a034ff65e5f100525a2`
- `tqdm-4.70.1-py3-none-any.whl`: `sha256:c293e525e6fef9c20e8728fd4612df02a0aa31bb5fe91ecd93e123b1b7bffa73`
- `typing_extensions-4.16.0-py3-none-any.whl`: `sha256:481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8`
- `typing_inspection-0.4.5-py3-none-any.whl`: `sha256:bc210535442b39e1bf2805e0c7a17dfd6a4ace760c84c7f7d16245d23a6b1c39`

The model the app asks is a server on this machine answering OpenAI's chat completions: the first answer reports its
tokens (12, 5, 17 in `usage-a`; 20, 6, 26 in `usage-b`), the second none, so its tokens are `not observed`. No answer
reports a cost: onetrace 0.8.0 writes none.

## onetrace's own vectors

`accept/` and `reject/` hold five of onetrace 0.8.0's own vectors, copied byte for byte from its release sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

- `accept/A202-model-usage-cost`: a record whose usage holds a cost, `0.0012` `USD`.
- `accept/A203-model-usage-two-records`: a step with two model-call records, each with its usage.
- `reject/R301-usage-total-below-part`: a total below one of its parts: `model_usage` FAILs.
- `reject/R302-usage-record-not-an-output`: an entry naming no output of its receipt: `model_usage` FAILs.
- `reject/R304-usage-second-entry`: a second entry for one record: `model_usage` FAILs.

## The files

- `accept/A202-model-usage-cost/MANIFEST.json`: `sha256:2e8d83a9a5cc8a40e62892087faf970dd0f5f0742300b743fdeb1574d050d9ca`
- `accept/A202-model-usage-cost/artifacts/01-answer-l1/answer.json`: `sha256:dff0e62dc87e0b230e7bbe55f37d82dc0465180f96919d559fef1fad9a8ad0fe`
- `accept/A202-model-usage-cost/artifacts/01-answer-l1/model_call.json`: `sha256:b547f092ff93b2b1821cbb8efba1bae66abece14117fae2464cae88075f6ff93`
- `accept/A202-model-usage-cost/artifacts/01-answer-l1/model_call.steps.json`: `sha256:4dc781a1d58367d42adb74480653560ae5f36b84e41068ee398174d663703008`
- `accept/A202-model-usage-cost/receipts/01-answer-l1.json`: `sha256:b2777a03ce80cd38e987323a5ea2cbf8d5279f093a62e92b09d6f1b8a876e003`
- `accept/A202-model-usage-cost/receipts/02-onetrace-close.json`: `sha256:98ed59941fcb4420e185213f3066e57892f62fca78678c48fa625fdc9be01d97`
- `accept/A203-model-usage-two-records/MANIFEST.json`: `sha256:0d0981e846f6eb435b9f66ac7c8bc52bdf2c84afc247f8e4347b6bf5f3c17426`
- `accept/A203-model-usage-two-records/artifacts/01-answer-l1/answer.json`: `sha256:dff0e62dc87e0b230e7bbe55f37d82dc0465180f96919d559fef1fad9a8ad0fe`
- `accept/A203-model-usage-two-records/artifacts/01-answer-l1/model_call.2.json`: `sha256:265dd48600adfdb8c90e115268a2ef679e94d1ed0e0c011a2b2cc45758d9c985`
- `accept/A203-model-usage-two-records/artifacts/01-answer-l1/model_call.json`: `sha256:265dd48600adfdb8c90e115268a2ef679e94d1ed0e0c011a2b2cc45758d9c985`
- `accept/A203-model-usage-two-records/receipts/01-answer-l1.json`: `sha256:ec000b4651f2ec759ff93a8706b7317abc674c4c4b4b4beb1ba6141fa82f8c73`
- `accept/A203-model-usage-two-records/receipts/02-onetrace-close.json`: `sha256:3e920a00fce110e1e32a01fa0b8fbd25b0083310b8fdf88ddc4fad1cdfa7452a`
- `reject/R301-usage-total-below-part/MANIFEST.json`: `sha256:02aa0572eb9a25f2b74b1bb1e92479fd9d6860740183943c948c2ac58a2bf63c`
- `reject/R301-usage-total-below-part/artifacts/01-answer-l1/answer.json`: `sha256:dff0e62dc87e0b230e7bbe55f37d82dc0465180f96919d559fef1fad9a8ad0fe`
- `reject/R301-usage-total-below-part/artifacts/01-answer-l1/model_call.json`: `sha256:b547f092ff93b2b1821cbb8efba1bae66abece14117fae2464cae88075f6ff93`
- `reject/R301-usage-total-below-part/artifacts/01-answer-l1/model_call.steps.json`: `sha256:4dc781a1d58367d42adb74480653560ae5f36b84e41068ee398174d663703008`
- `reject/R301-usage-total-below-part/receipts/01-answer-l1.json`: `sha256:b0107cde0da05fb93522a3dbf693f07d173fe28fb1b706949fd1194001f55c4c`
- `reject/R301-usage-total-below-part/receipts/02-onetrace-close.json`: `sha256:434fc92baa6e0cc3befd031cfc044a002b5e92c26bb01870c95e19fb7707234d`
- `reject/R302-usage-record-not-an-output/MANIFEST.json`: `sha256:9ceff63fa949f3a3ea0ea3fd14a1caaae5ee93934159e66c7c9093f23922f511`
- `reject/R302-usage-record-not-an-output/artifacts/01-answer-l1/answer.json`: `sha256:dff0e62dc87e0b230e7bbe55f37d82dc0465180f96919d559fef1fad9a8ad0fe`
- `reject/R302-usage-record-not-an-output/artifacts/01-answer-l1/model_call.json`: `sha256:b547f092ff93b2b1821cbb8efba1bae66abece14117fae2464cae88075f6ff93`
- `reject/R302-usage-record-not-an-output/artifacts/01-answer-l1/model_call.steps.json`: `sha256:4dc781a1d58367d42adb74480653560ae5f36b84e41068ee398174d663703008`
- `reject/R302-usage-record-not-an-output/receipts/01-answer-l1.json`: `sha256:c396014bf4cd12ae71d69ebdb65a4a667f0d185064b13543dd789b032b81ea0d`
- `reject/R302-usage-record-not-an-output/receipts/02-onetrace-close.json`: `sha256:99e6b9a5b15227a1bfee7ac1e260d9f8f712284ab6c38662c68444511ff53256`
- `reject/R304-usage-second-entry/MANIFEST.json`: `sha256:45511da93a7bbc5cdf47d24f72e2895ce439eec3f6d3bc24663d69d2da84f18c`
- `reject/R304-usage-second-entry/artifacts/01-answer-l1/answer.json`: `sha256:dff0e62dc87e0b230e7bbe55f37d82dc0465180f96919d559fef1fad9a8ad0fe`
- `reject/R304-usage-second-entry/artifacts/01-answer-l1/model_call.json`: `sha256:b547f092ff93b2b1821cbb8efba1bae66abece14117fae2464cae88075f6ff93`
- `reject/R304-usage-second-entry/artifacts/01-answer-l1/model_call.steps.json`: `sha256:4dc781a1d58367d42adb74480653560ae5f36b84e41068ee398174d663703008`
- `reject/R304-usage-second-entry/receipts/01-answer-l1.json`: `sha256:f31b1b1a64d09e14553252a4247b36a66777b3640b72719ddb7b3558b99d169e`
- `reject/R304-usage-second-entry/receipts/02-onetrace-close.json`: `sha256:750be1995319cf886f9b3e6d54fcebc57a89f5b7d21c897aee66c8ce6c8a9fc0`
