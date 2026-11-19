# Format 0.5's code version and a re-run's parts: where these runs come from

## The two recorded runs

`code-clean/` and `code-dirty/` were recorded by `tools/make_code_runs.py` running `tools/onetrace_runs/code_version.py`
(`record_code=True`) from a git repository the tool makes for them, committed with a fixed author, committer and date
(commit `3d85335e8af7553462affb952efec12bed631ef3`), with onetrace 0.8.0 installed from its release files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

`code-clean` ran with every tracked file as committed; `code-dirty` with its lock file changed and not committed.

## onetrace's own vectors

`accept/` and `reject/` hold six of onetrace 0.8.0's own vectors, copied byte for byte from its release sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

- `accept/A76-code-of`: a reproduce that took its code from another run.
- `accept/A77-code-of-lock-differs`: the same, its lock file differing.
- `accept/A80-code-not-observed`: a code file in no git repository: `not observed`.
- `reject/R110-rerun-from-disagrees`: the receipts disagree on `rerun_from`: `re-run from` FAILs.
- `reject/R115-code-commit-out-of-form`: a commit `HEAD`: `code` FAILs.
- `reject/R117-code-manifest-copy-differs`: the manifest's copy says `dirty` `true`: `code` FAILs.

## The files

- `accept/A76-code-of/MANIFEST.json`: `sha256:a2197170d23835893257b1ec2d8fabba66361f2ef83869fa5990de5f5869d8fa`
- `accept/A76-code-of/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `accept/A76-code-of/artifacts/02-b/out.json`: `sha256:70a976e1793a6512c26a84cd64e5f53830fea136a5fe8a88bc1e8f6d9af6106b`
- `accept/A76-code-of/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `accept/A76-code-of/receipts/01-a.json`: `sha256:ba61d965ceb34c824b445f8de3b84a4d59483deffced46a002d5c9018f24a174`
- `accept/A76-code-of/receipts/02-b.json`: `sha256:700edf28147511229a09b4fb38a7a8ffb1f18db057d431ec2d7bdc8b7f94f665`
- `accept/A76-code-of/receipts/03-c.json`: `sha256:b5511f2f30c17e2a0378072cde3a949f1016f7bac1ccf43cc4fe8179d99dcf40`
- `accept/A76-code-of/receipts/04-onetrace-close.json`: `sha256:4ab3ac1f20f912893e8a66fc5f810bee58e9609612a0a96fa78c8fa95da93796`
- `accept/A77-code-of-lock-differs/MANIFEST.json`: `sha256:e52cc6961660abcde28f5d2debf6bb4af925213f12c30a7497f2b5a64323fe73`
- `accept/A77-code-of-lock-differs/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `accept/A77-code-of-lock-differs/artifacts/02-b/out.json`: `sha256:70a976e1793a6512c26a84cd64e5f53830fea136a5fe8a88bc1e8f6d9af6106b`
- `accept/A77-code-of-lock-differs/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `accept/A77-code-of-lock-differs/receipts/01-a.json`: `sha256:e2d2090b199ad5abd3961d6838fed4d08e4d1036af254e14dcab4a3b381c8066`
- `accept/A77-code-of-lock-differs/receipts/02-b.json`: `sha256:8f077bf4aa925a8f1c2892fa35c38479c13fedc50aa00e42c2402621115ae79f`
- `accept/A77-code-of-lock-differs/receipts/03-c.json`: `sha256:236f6184330d55d9c68e99306bd5019f240a054597e2f9fb0378f7bc81d95835`
- `accept/A77-code-of-lock-differs/receipts/04-onetrace-close.json`: `sha256:d4ede88ec09e0907ea055782a1e1be5858142b3f0a5a812c5db70900ebfd0df7`
- `accept/A80-code-not-observed/MANIFEST.json`: `sha256:7e285678d974759445406c1a3e64bd8ebed2a906d8474049e9e56f81b7c60569`
- `accept/A80-code-not-observed/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `accept/A80-code-not-observed/artifacts/02-b/out.json`: `sha256:10b3cf7aadb15b907075f5d7bff8ef7cfa858c395cb9fb6f729f57313e14cd69`
- `accept/A80-code-not-observed/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `accept/A80-code-not-observed/receipts/01-a.json`: `sha256:f3ab65f498a7a96a05d0b3a2e4559fa4f71c60721b97769a4fc1eb46920cc5d6`
- `accept/A80-code-not-observed/receipts/02-b.json`: `sha256:8915390bd7d2a36412151d8508fdb6afc93da4ebbb47ba151f4c66d5f72764dd`
- `accept/A80-code-not-observed/receipts/03-c.json`: `sha256:33fa1ab127252576d79a17c13584a20415a743717ff42b53a707052de76e1d88`
- `accept/A80-code-not-observed/receipts/04-onetrace-close.json`: `sha256:0afb1e61e52ba9e97cff57629281d5d4153c7c75c0ad4c0d084c80a11c18292c`
- `reject/R110-rerun-from-disagrees/MANIFEST.json`: `sha256:c958cce89620843bc8d8f0296edc4d55e2c19423275b8993f03ab65bf3dd8fa5`
- `reject/R110-rerun-from-disagrees/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `reject/R110-rerun-from-disagrees/artifacts/02-b/out.json`: `sha256:e14a877b81dddc03c32c744ad7921539776a12950b7599f98201941db322003c`
- `reject/R110-rerun-from-disagrees/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `reject/R110-rerun-from-disagrees/receipts/01-a.json`: `sha256:1def52e6517fe577d8405d6fbe9b5eab6c4177d46250f6a128032b534dd74cdd`
- `reject/R110-rerun-from-disagrees/receipts/02-b.json`: `sha256:2912dc8d8724bed6a25dbfc2ef28a82ab5cea99bd078d23e29fc0eba8081cf74`
- `reject/R110-rerun-from-disagrees/receipts/03-c.json`: `sha256:e1394da9a68454501ae19e89665f3d387fc409bcd0c7b1fd74e27fd53fcebb25`
- `reject/R110-rerun-from-disagrees/receipts/04-onetrace-close.json`: `sha256:72a6c1e05bf5fb3c597456470980176adef8b20a02b4c54e2fe11894b5d5d290`
- `reject/R115-code-commit-out-of-form/MANIFEST.json`: `sha256:a10522908241904ca826f237b1c6e1f1ad2779f2a9e0c7a7113195a66a3e2ce8`
- `reject/R115-code-commit-out-of-form/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `reject/R115-code-commit-out-of-form/artifacts/02-b/out.json`: `sha256:10b3cf7aadb15b907075f5d7bff8ef7cfa858c395cb9fb6f729f57313e14cd69`
- `reject/R115-code-commit-out-of-form/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `reject/R115-code-commit-out-of-form/receipts/01-a.json`: `sha256:2a91a4d13a537b6e2a7212808a4d4a27323fda61378747351590f2133943aae8`
- `reject/R115-code-commit-out-of-form/receipts/02-b.json`: `sha256:c9bcc8355ad072a914243360285c0f9f42c601681c0b70085e885867a9fad9d3`
- `reject/R115-code-commit-out-of-form/receipts/03-c.json`: `sha256:d83876ca60b11605f6a846c120024b946234f81f43bf1289ff296adad3f5704e`
- `reject/R115-code-commit-out-of-form/receipts/04-onetrace-close.json`: `sha256:3b3a11d5a3553066685cecec483779fda6f77a4a4957a015c74bc15e29ed12e9`
- `reject/R117-code-manifest-copy-differs/MANIFEST.json`: `sha256:579b17f7bae66abe25875c8b978d3fff46220742443ffcd4e7594bf8d468b2f7`
- `reject/R117-code-manifest-copy-differs/artifacts/01-a/out.json`: `sha256:3649771a8092b11d7dfa7ce387cbaccec8dbb7a733917ab682b3e3893adb34a5`
- `reject/R117-code-manifest-copy-differs/artifacts/02-b/out.json`: `sha256:10b3cf7aadb15b907075f5d7bff8ef7cfa858c395cb9fb6f729f57313e14cd69`
- `reject/R117-code-manifest-copy-differs/artifacts/03-c/out.json`: `sha256:821dbaa636e40990919f3a40495daef63aeadf7af7599006e9b4624f8e744028`
- `reject/R117-code-manifest-copy-differs/receipts/01-a.json`: `sha256:b76ca124ac49dbec38497acf91fd8a1e5b24dcab6ebd973c12fdc49ebf22c6f8`
- `reject/R117-code-manifest-copy-differs/receipts/02-b.json`: `sha256:1e05757e4690bf11190f9c219b75ed2de0cf49beaaf3141d8ff8edda239cf222`
- `reject/R117-code-manifest-copy-differs/receipts/03-c.json`: `sha256:19df15e103f7300ea2f931bb094b57fdea312de18ff8866dfcf5c24b37ed22bc`
- `reject/R117-code-manifest-copy-differs/receipts/04-onetrace-close.json`: `sha256:5bfbc3b1ac80aafd3d895963f5b4b3829d2cb336ae8e2ed6fb92ef0ec790e3e1`
