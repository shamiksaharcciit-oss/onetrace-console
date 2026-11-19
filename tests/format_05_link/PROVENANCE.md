# Format 0.5's cross-service link: where these runs come from

## The three recorded runs

`link-desk/`, `link-billing/` and `link-garbled/` were recorded by `tools/make_link_runs.py` running
`tools/onetrace_runs/linked_desk.py` and `tools/onetrace_runs/linked_billing.py` (`MADE.json` names each command), with
onetrace 0.8.0 installed from its release files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

The desk's step calls the billing service, run as a process of its own, with `onetrace-parent`, and records its
`onetrace-child` (`head returned`), then a call that returns none (`called, head not returned`). `link-garbled` is the
billing service given a header that does not parse: its `parent_link` holds `status` alone.

## onetrace's own vectors

`accept/` and `reject/` hold eleven of onetrace 0.8.0's own vectors, copied byte for byte from its release sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

- `accept/A222-link-origin-two-hops`: a run called by a run called by a third, each naming the first as its origin;
  the other two are under its `linked/`.
- `accept/A224-link-origin-nested-caller`: a run called by a run nested in-process in a third; the nested run
  (`linked/vector-origin-nested-n`) records no origin of its own.
- `reject/R81-link-names-another-run`: with its callee's folder, `linked runs match` FAILs: the callee names another
  run.
- `reject/R85-link-manifest-copy-differs`: alone, `linked runs match` FAILs: the manifest's copies differ from the
  first receipt's link.
- `reject/R86-calls-status-outside`: alone, `linked runs match` FAILs: a `calls` status outside the four.
- `reject/R83-link-head-not-in-chain`: with its callee's folder, `linked runs match` FAILs: the head returned is not
  in the callee's chain.
- `reject/R84-link-parent-head-not-in-chain`: with its caller's folder, `linked runs match` FAILs: the head the caller
  gave is not in its own chain.
- `reject/R87-calls-head-without-run`: alone, `linked runs match` FAILs: a head returned with no child run.
- `reject/R88-calls-head-bare-hex`: alone, `linked runs match` FAILs: a child head as bare hex.
- `reject/R316-link-origin-outer-folder-missing-and-a-fail`: alone, an output file FAILs; `linked runs match` is
  NOT-RUN, the nested caller's outer folder not given.
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts`: alone, `linked runs match` FAILs: the manifest's
  `origin_run` with no receipt carrying the origin.

## The files

- `accept/A222-link-origin-two-hops/MANIFEST.json`: `sha256:c896970bba577087abfe95fed694b03f4302872cca9bb31d75d96db582a6c300`
- `accept/A222-link-origin-two-hops/artifacts/01-quote/out.json`: `sha256:0fde9bc92a0554cfcd30f342d0ac6e001e9486431483be291db7cee56d7baa8f`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/MANIFEST.json`: `sha256:4368b46ac17f3436fe17d339b03463bfccd49c68070825ab60df7f85b4380fe8`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/receipts/01-prep.json`: `sha256:125d003b9aec33e89609db2c798ad188a031aea9a2443e8e11f5ac3d0246241b`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/receipts/02-approve-payment.json`: `sha256:f7a5703060ebe2108e00a605a1432cb6b36844a5bd93ee3230286705ce418985`
- `accept/A222-link-origin-two-hops/linked/vector-origin-a/receipts/03-onetrace-close.json`: `sha256:22e925c03a33ca63e1eac79ce47d718e524906f7154dc4b2d0bb8d037c495839`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/MANIFEST.json`: `sha256:ebdeb442d2591a61e12d79739fbde8e857de063a40a3227c5fb780ac89802620`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/artifacts/01-look/out.json`: `sha256:e4f07a28ef3c7e138470612371aca1a324328d7ff8a9f391294fed887faf7ec6`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/artifacts/02-ask/out.json`: `sha256:3c9314757746eee516770d37ea20ce1d9e5af1dbb0a3e9897e8028c88bd0a234`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/receipts/01-look.json`: `sha256:11e47c16760418695987a3f669cfc0e5345447d150c62e827f9773246418b920`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/receipts/02-ask.json`: `sha256:1f3b1faaf26544182b4d4afb59c378b016c44552dddb2b122193106ecafd9133`
- `accept/A222-link-origin-two-hops/linked/vector-origin-b/receipts/03-onetrace-close.json`: `sha256:29580ce6656485d8e654e80752a5c45a4e576f49cc2662e89b3ac1d5866ec4ec`
- `accept/A222-link-origin-two-hops/receipts/01-quote.json`: `sha256:4f16e8656a35e9dbb1cf8d7b9928b0b0b56bcaf0ce8f76243ad890d9de5a3673`
- `accept/A222-link-origin-two-hops/receipts/02-onetrace-close.json`: `sha256:435bddfa6d271de9b23830175a24c266926af466a11a382120bd5a2f140fb689`
- `accept/A224-link-origin-nested-caller/MANIFEST.json`: `sha256:11a91474c66d593ab8ce4267bce4364ea124d388ac7a2e5a300d9468cb42eeb2`
- `accept/A224-link-origin-nested-caller/artifacts/01-quote/out.json`: `sha256:0fde9bc92a0554cfcd30f342d0ac6e001e9486431483be291db7cee56d7baa8f`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-n/MANIFEST.json`: `sha256:183f5d77daa6678d2e36a280df8dccbb7b5b683ed812be92774cdd0e2ae6e7e2`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-n/artifacts/01-ask/out.json`: `sha256:3c9314757746eee516770d37ea20ce1d9e5af1dbb0a3e9897e8028c88bd0a234`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-n/receipts/01-ask.json`: `sha256:6989209a1e836fdd45451ca5059ac669860f48a0e29271dd3e4f80b72a699002`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-n/receipts/02-onetrace-close.json`: `sha256:abeb680d88f4f2eea4f7022a51ccb81478e979bf8f87a81231bcc7ab3cc5737e`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-o/MANIFEST.json`: `sha256:6af90408f5e13ab82b569424ecda15f4176068225c88d1903c77651e8c01292a`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-o/artifacts/01-plan/out.json`: `sha256:cbdab473d1d450ca7e676f34cda7702c8a030ede54134ca1c16bce7bce39e39f`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-o/receipts/01-plan.json`: `sha256:24a69c32a6d19d8eb70c29f13722aeb9f02859704b91f762bc5836e960a38c6f`
- `accept/A224-link-origin-nested-caller/linked/vector-origin-nested-o/receipts/02-onetrace-close.json`: `sha256:c1b41b84b527a94ecab3d5ff99d73460548102c575c061c73e22d980d5269f14`
- `accept/A224-link-origin-nested-caller/receipts/01-quote.json`: `sha256:7059df458cf4cd0e242047804e1cf27f8154e24fb7337bea318f193ff96e1686`
- `accept/A224-link-origin-nested-caller/receipts/02-onetrace-close.json`: `sha256:81166b41fdc711933e8ea1195dd65efe9584817b73f775366bb83d799a361150`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/MANIFEST.json`: `sha256:4ed66377df5c344eb453ed173fa532a6e9aad9bf194de9359a3b48035ff3c45c`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/artifacts/01-quote/out.json`: `sha256:6c76040d0c971852b2c5e3b92ac5a8bf9c5db8d05e3a9b4793d36b6c68e81edf`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/linked/vector-origin-nested-n/MANIFEST.json`: `sha256:87a14e4435b054e1295f1a5b7e177b9e640a7637e069e0a7fa99a0d31a3d2c65`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/linked/vector-origin-nested-n/artifacts/01-ask/out.json`: `sha256:3c9314757746eee516770d37ea20ce1d9e5af1dbb0a3e9897e8028c88bd0a234`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/linked/vector-origin-nested-n/receipts/01-ask.json`: `sha256:370055c536ad5179ed48deffae65a069f9089948ac0893db85acd8bf0bf1f04a`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/linked/vector-origin-nested-n/receipts/02-onetrace-close.json`: `sha256:216cbf0a7e4474d6cd1532bb2b1ae9838340109623396a14071a30fbb03669d0`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/receipts/01-quote.json`: `sha256:e1ae4d1190086fb8d1d4bce96722fab75a06c5a34fcc871d1efef05b2883e4e8`
- `reject/R316-link-origin-outer-folder-missing-and-a-fail/receipts/02-onetrace-close.json`: `sha256:efb1953a6230b130d5b0978c1edd397c323367711c0fc6756f7b9f1efd02644e`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/MANIFEST.json`: `sha256:89d012b02022c2986c9057e84ad17519c84dae3e5ed40b61ae3caadd84af607f`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/receipts/01-prep.json`: `sha256:b5dbd8a5c8db73378672deda413020cb07a086c888e6098e41cee90da11be20b`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/receipts/02-approve-payment.json`: `sha256:3d7772f6449b793943ca8b0f101a079e6167902cc676a9af1453c3d9f64e943c`
- `reject/R317-link-origin-run-with-no-origin-in-the-receipts/receipts/03-onetrace-close.json`: `sha256:04624d2724af29e65a4cc1d887337df9eddc35f656fc2ac8f5695df9fde0421a`
- `reject/R81-link-names-another-run/MANIFEST.json`: `sha256:d00f02731f1bf7632c0d1b2e30648c2ed02ac13d799c574ba8112a7b0623a4d7`
- `reject/R81-link-names-another-run/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R81-link-names-another-run/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/MANIFEST.json`: `sha256:04934f5d2ceb49d0dabc72cd4de0b3e55a11589fa72ad331a0a82fb4efe3322b`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/artifacts/01-price/out.json`: `sha256:b37db50207616a069dd618001b3b761e7d76f150d40727d857c99f3e32c08edc`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/artifacts/02-tax/out.json`: `sha256:398cd25eca37fbaac2cee4fa10b2840f8ceeeed9c0874f206fafc858792ed9d6`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/artifacts/03-total/out.json`: `sha256:1156142719468f36e5f1d7d6857d545870da46fdbac29392d77571939f93f9eb`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/receipts/01-price.json`: `sha256:9583cdc6f1c8e80cc5e6418f2c4e6dfd1eefe047dd1ad0bf1b4de2c04d3c27ff`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/receipts/02-tax.json`: `sha256:0d6c23baaf5397f67852e41c9e2fbb2f3aaa15d450e171c41c80052a0ba9e210`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/receipts/03-total.json`: `sha256:c2e7391644a6d9310d9aff85eefdeaf6d1fe574493d318d3f1d2768181079327`
- `reject/R81-link-names-another-run/linked/vector-link-earlier-callee/receipts/04-onetrace-close.json`: `sha256:be13ac1fb2b38ec9786bf5477c1c189897138adb8530890daaea520442d5e28f`
- `reject/R81-link-names-another-run/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R81-link-names-another-run/receipts/02-approve-payment.json`: `sha256:333dc7be7f2465e255a3e7d4783df6393ccf36c7f37b1ddaf19acf3d65147c2d`
- `reject/R81-link-names-another-run/receipts/03-onetrace-close.json`: `sha256:61c19ff022ba736c3143775a22f07d388f070f5c780887639e8e29f16fc483e1`
- `reject/R83-link-head-not-in-chain/MANIFEST.json`: `sha256:8e59bdaaa32902ae1c1ff7131df816c5f4bfae42c4604f39cd7d47e2719ea0af`
- `reject/R83-link-head-not-in-chain/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R83-link-head-not-in-chain/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/MANIFEST.json`: `sha256:00e5228bd936426831dc435a5d8777de1c296b2538c2f535e0d4498cedad5750`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/artifacts/01-price/out.json`: `sha256:b37db50207616a069dd618001b3b761e7d76f150d40727d857c99f3e32c08edc`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/artifacts/02-tax/out.json`: `sha256:398cd25eca37fbaac2cee4fa10b2840f8ceeeed9c0874f206fafc858792ed9d6`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/artifacts/03-total/out.json`: `sha256:1156142719468f36e5f1d7d6857d545870da46fdbac29392d77571939f93f9eb`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/receipts/01-price.json`: `sha256:e0b8d1b1919e8374f0866f5b41c20e9a523e4e19b2cceed1e6ee454ad28a3ad9`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/receipts/02-tax.json`: `sha256:8de86839d31cb1d9f39cb6625d671731b1213a574ab47fb36f38ffd8690b8b6e`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/receipts/03-total.json`: `sha256:5a9a5e64315831f1b54ca984839514e53e988e3e0da8b278bc80a33d09777c20`
- `reject/R83-link-head-not-in-chain/linked/vector-link-earlier-callee/receipts/04-onetrace-close.json`: `sha256:1200f84ea0f7f41e4e418017fb50423204ecfe5ba2e2a50f03005c22997b98de`
- `reject/R83-link-head-not-in-chain/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R83-link-head-not-in-chain/receipts/02-approve-payment.json`: `sha256:a0646c6b874385debbde40001ef273b58ea49a14befc1d102c5dba07695c422b`
- `reject/R83-link-head-not-in-chain/receipts/03-onetrace-close.json`: `sha256:f5d6c6fcf727e59f43798b0cff77d073050241ced0b8dc6fd8756cd38591b197`
- `reject/R84-link-parent-head-not-in-chain/MANIFEST.json`: `sha256:8aadf008c2887b249783a678db716d7482ead5823691815ce2e5505c0ea22a37`
- `reject/R84-link-parent-head-not-in-chain/artifacts/01-price/out.json`: `sha256:b37db50207616a069dd618001b3b761e7d76f150d40727d857c99f3e32c08edc`
- `reject/R84-link-parent-head-not-in-chain/artifacts/02-tax/out.json`: `sha256:398cd25eca37fbaac2cee4fa10b2840f8ceeeed9c0874f206fafc858792ed9d6`
- `reject/R84-link-parent-head-not-in-chain/artifacts/03-total/out.json`: `sha256:1156142719468f36e5f1d7d6857d545870da46fdbac29392d77571939f93f9eb`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/MANIFEST.json`: `sha256:d00f02731f1bf7632c0d1b2e30648c2ed02ac13d799c574ba8112a7b0623a4d7`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/receipts/02-approve-payment.json`: `sha256:333dc7be7f2465e255a3e7d4783df6393ccf36c7f37b1ddaf19acf3d65147c2d`
- `reject/R84-link-parent-head-not-in-chain/linked/vector-link-earlier-caller/receipts/03-onetrace-close.json`: `sha256:61c19ff022ba736c3143775a22f07d388f070f5c780887639e8e29f16fc483e1`
- `reject/R84-link-parent-head-not-in-chain/receipts/01-price.json`: `sha256:9abd6faa7848aa4978d22c8fd1beb5e41d2b55a467e0969ffef4910567ad552d`
- `reject/R84-link-parent-head-not-in-chain/receipts/02-tax.json`: `sha256:8df54bf2ad4471186bac0b4f7543e985e2d6aef7a6b637e0f3b26cad9aa356d9`
- `reject/R84-link-parent-head-not-in-chain/receipts/03-total.json`: `sha256:d3c415b68afdd503c89bfca5d7bce931219bd470a77e39f0f4ff416138ccb525`
- `reject/R84-link-parent-head-not-in-chain/receipts/04-onetrace-close.json`: `sha256:89a81d3364a0658ed2079a6c118cf2c8e5873db451276f35b5ed067cba9f0a96`
- `reject/R85-link-manifest-copy-differs/MANIFEST.json`: `sha256:0b4348be8633a635f84bb698338cfa0872d2bac2d5eb7234c63b896024a115fe`
- `reject/R85-link-manifest-copy-differs/artifacts/01-price/out.json`: `sha256:b37db50207616a069dd618001b3b761e7d76f150d40727d857c99f3e32c08edc`
- `reject/R85-link-manifest-copy-differs/artifacts/02-tax/out.json`: `sha256:398cd25eca37fbaac2cee4fa10b2840f8ceeeed9c0874f206fafc858792ed9d6`
- `reject/R85-link-manifest-copy-differs/artifacts/03-total/out.json`: `sha256:1156142719468f36e5f1d7d6857d545870da46fdbac29392d77571939f93f9eb`
- `reject/R85-link-manifest-copy-differs/receipts/01-price.json`: `sha256:e0b8d1b1919e8374f0866f5b41c20e9a523e4e19b2cceed1e6ee454ad28a3ad9`
- `reject/R85-link-manifest-copy-differs/receipts/02-tax.json`: `sha256:8de86839d31cb1d9f39cb6625d671731b1213a574ab47fb36f38ffd8690b8b6e`
- `reject/R85-link-manifest-copy-differs/receipts/03-total.json`: `sha256:5a9a5e64315831f1b54ca984839514e53e988e3e0da8b278bc80a33d09777c20`
- `reject/R85-link-manifest-copy-differs/receipts/04-onetrace-close.json`: `sha256:1200f84ea0f7f41e4e418017fb50423204ecfe5ba2e2a50f03005c22997b98de`
- `reject/R86-calls-status-outside/MANIFEST.json`: `sha256:e58c86e5db71bbaf73b5dd8e52f40ce532ebed6183f9c6442aaa052dfb0c1e70`
- `reject/R86-calls-status-outside/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R86-calls-status-outside/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R86-calls-status-outside/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R86-calls-status-outside/receipts/02-approve-payment.json`: `sha256:eb9290425912fe8843de48ef392fe4c9a07b3b00e839acb5fc63ad87124386e8`
- `reject/R86-calls-status-outside/receipts/03-onetrace-close.json`: `sha256:e34d2fcc62abd1ef1e0662f3567a6dfc21de942fc23a56c6ad5eedb6e658c158`
- `reject/R87-calls-head-without-run/MANIFEST.json`: `sha256:4a0323f38d88a4c11a84ee04fb3ead561ad95fc2f2d63d9358894f4b1a2075c5`
- `reject/R87-calls-head-without-run/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R87-calls-head-without-run/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R87-calls-head-without-run/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R87-calls-head-without-run/receipts/02-approve-payment.json`: `sha256:a00759e55d5c094b3dbb1181f10279be601a071b0d3334c02b8ba09adfe31f67`
- `reject/R87-calls-head-without-run/receipts/03-onetrace-close.json`: `sha256:a61a354ff9a170c18de084c02e16d32f62bae68c75f9f776139c52deb646c1b4`
- `reject/R88-calls-head-bare-hex/MANIFEST.json`: `sha256:64a9b3cd9ea81b52ec449ce477084813b5660b1d044f202d2bcd04804b9fd649`
- `reject/R88-calls-head-bare-hex/artifacts/01-prep/out.json`: `sha256:5d97bb725f3b79e789eb2c20fc8d06063ae124dab2a9f39e3a67a6db8bea1b16`
- `reject/R88-calls-head-bare-hex/artifacts/02-approve-payment/out.json`: `sha256:805006d10e3b3f61099f6e9c2484ec7718715a98be43d63c276f779015180352`
- `reject/R88-calls-head-bare-hex/receipts/01-prep.json`: `sha256:1261feac6a3b395de0ea4b82a7b9c4af526ca9bb30fed8c28e852ed31bb3aeae`
- `reject/R88-calls-head-bare-hex/receipts/02-approve-payment.json`: `sha256:3dcca6bb4fb48ab85a86c71fe168f81641e2ad5dd425b5b42e5456460e2b03d6`
- `reject/R88-calls-head-bare-hex/receipts/03-onetrace-close.json`: `sha256:b68664572c830bec370d84c83fb5028388db25af803724348dc3568fc180f9a5`
