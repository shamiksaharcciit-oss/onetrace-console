# Format 0.5's store state: where these runs come from

## The two recorded runs

`state-kept/` and `state-not-kept/` were recorded by `tools/make_state_runs.py` running
`tools/onetrace_runs/store_state.py` (`MADE.json` names each command), with onetrace 0.8.0 installed from its release
files, each by its sha256:

- `onetrace-0.8.0-py3-none-any.whl`: `sha256:859976cf7aab2bd67bdf171718550304fb0db8ac098d30ba1176d82df7871751`
- `onetrace_verify-0.8.0-py3-none-any.whl`: `sha256:552e1d37f740507ba8b04ee3b7344d7c92c093ba15230aefc6a99697e7ac585f`

## onetrace's own vectors

`accept/` and `reject/` hold six of onetrace 0.8.0's own vectors, copied byte for byte from its release sdist
(`onetrace-0.8.0.tar.gz`, `sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder
`tests/format_0_4/`. onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

`accept/A41-state-cut` is a step that kept its first 1000 reads and counted the rest in `state_cut`: it reads PASS.
Each reject vector is a run whose verifier reads one FAIL, on the row named:

- `R51-state-digest-out-of-form`: `[FAIL   ] receipts/01-sql.json: state entries -- state_reads[1]: digest 'sha256:00' is out of form`
- `R60-state-writes-labelled-read`: `[FAIL   ] receipts/02-object.json: state_writes against effect_label -- labelled read and records a state write`
- `R61-state-kept-does-not-recompute`: `[FAIL   ] receipts/01-s.json: state kept -- state_reads[1]: the kept file's sha256 is not its digest`
- `R70-state-at-open-copy-differs`: `[FAIL   ] state at open -- the manifest's copy differs from the first receipt's`
- `R71-state-at-open-not-first`: `[FAIL   ] state at open -- receipts/02-b.json holds it, and it is not the first receipt`

## The files

- `accept/A41-state-cut/MANIFEST.json`: `sha256:9fcf0f7a44dfe3953d2529b8d8fc2210acc62ae89b905b8b47169b44454d8923`
- `accept/A41-state-cut/artifacts/01-s/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `accept/A41-state-cut/receipts/01-s.json`: `sha256:315e407f1cf58196113773328231afa88f08fb8aee3f6701cecf17d6a857f8be`
- `accept/A41-state-cut/receipts/02-onetrace-close.json`: `sha256:77fb4f2b6bd37dddeec5c93448f908cedd0d53baac97820b3b1aacdcd0cc3d1a`
- `reject/R51-state-digest-out-of-form/MANIFEST.json`: `sha256:0d8c60fcad416a3c61a9794b52d074e05bf1f83edc1d1e532dd6698c30b4bb7d`
- `reject/R51-state-digest-out-of-form/artifacts/01-sql/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/02-object/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/03-kv/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/04-docs/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/05-vector-query/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/06-vector-change/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/artifacts/07-checkpoint/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R51-state-digest-out-of-form/receipts/01-sql.json`: `sha256:dd56afab710705790722cf126b1d8c1e4013b1d08eb5ca3e26cacb2bb8196c1b`
- `reject/R51-state-digest-out-of-form/receipts/02-object.json`: `sha256:501e831cdee1893ed10fd8afac302e5cc83e716fad877f98e728c94675f17c04`
- `reject/R51-state-digest-out-of-form/receipts/03-kv.json`: `sha256:3c15bd36d4967096272d050b3c221c5f62080a4e5c3a3fc831c706f321db2559`
- `reject/R51-state-digest-out-of-form/receipts/04-docs.json`: `sha256:b83656e3c5f889d6a9894c2ff2b67da92a3dcae57dddc6141f80fbd5c606be83`
- `reject/R51-state-digest-out-of-form/receipts/05-vector-query.json`: `sha256:b4587e221f2c78d150afa6b1421ac1bb6e57efb9d8d0f36389b6036995ecc54a`
- `reject/R51-state-digest-out-of-form/receipts/06-vector-change.json`: `sha256:a5c6d21db13216a644800e22a8dd705099a42b5a8dc6b84147db86e962578b17`
- `reject/R51-state-digest-out-of-form/receipts/07-checkpoint.json`: `sha256:ae9999aba1a370f9d9c905db865e3f130a6e99e9a9caf9d457d7f267818f59da`
- `reject/R51-state-digest-out-of-form/receipts/08-onetrace-close.json`: `sha256:9a1e7802cd5971019f1bfff944ff8ec09b0f2e3d74dcfded5046db6f9feadc9c`
- `reject/R60-state-writes-labelled-read/MANIFEST.json`: `sha256:62db236b5209153bd690bae413984155ed23ab5f0bf32916649af27d840fee6a`
- `reject/R60-state-writes-labelled-read/artifacts/01-sql/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/02-object/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/03-kv/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/04-docs/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/05-vector-query/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/06-vector-change/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/artifacts/07-checkpoint/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R60-state-writes-labelled-read/receipts/01-sql.json`: `sha256:ed451ad90adc89e171802b115e555813b111ce9041da42e2bed065e7c350a7d6`
- `reject/R60-state-writes-labelled-read/receipts/02-object.json`: `sha256:c36d3b6569565fbe6431fb39c4e907266176b62ada2d8955e5f2787f1032ac55`
- `reject/R60-state-writes-labelled-read/receipts/03-kv.json`: `sha256:99abaeb59ebc35101b2152fd6a392c6129329dee4d319e27741a940b330b167e`
- `reject/R60-state-writes-labelled-read/receipts/04-docs.json`: `sha256:f4bb49a1cf7d92301aee55c72ceceae58064c0730b0b116665d0b3e270718799`
- `reject/R60-state-writes-labelled-read/receipts/05-vector-query.json`: `sha256:87e41fb67a76be6ca7e9ff703b9d67647fd02dc3d46bfa4b5e4a64c5a1324c3b`
- `reject/R60-state-writes-labelled-read/receipts/06-vector-change.json`: `sha256:246fd3c931e8b7ee93816a822afc4dcd45c72a3d4d6f955b93485be600844bd8`
- `reject/R60-state-writes-labelled-read/receipts/07-checkpoint.json`: `sha256:b6d8d0bed7b49f9790cb25876857162a08b60d0995f4a275c89489e39321a1a3`
- `reject/R60-state-writes-labelled-read/receipts/08-onetrace-close.json`: `sha256:32c0692837a7efa933ddb1de7fd525f5ef2cae071d0a76083ab1651cfb0cd4cf`
- `reject/R61-state-kept-does-not-recompute/MANIFEST.json`: `sha256:8246987a9e6df2f566caa0df7282bf82331ae8f38b0505df116a90d215c974b0`
- `reject/R61-state-kept-does-not-recompute/artifacts/01-s/out.json`: `sha256:b8513f1a0c28d8dd9b3b175bee09eabca97c4819614ec9a2df7442a5b4eff8d7`
- `reject/R61-state-kept-does-not-recompute/receipts/01-s.json`: `sha256:af128bfcc2f2dcfdc21981830982a7c6516e3fca6f1c3dce59a6fb9566c07965`
- `reject/R61-state-kept-does-not-recompute/receipts/02-onetrace-close.json`: `sha256:d643badea898f809a7ed8013e3c0ff96abfb3cc2b84556efeee0cd1f6cc7dc6a`
- `reject/R61-state-kept-does-not-recompute/state/01-s/reads/1`: `sha256:eba4458e0b538c50ed05a6c3249072a3a8b4a3643f67f18fe7ce0adb251779d7`
- `reject/R70-state-at-open-copy-differs/MANIFEST.json`: `sha256:2a0e4110603e8d45d9db06b317692f0280f31021f355aef159e99325ba283d14`
- `reject/R70-state-at-open-copy-differs/artifacts/01-a/out.json`: `sha256:ece1fa5e6f63aea714943e77ad134cf9a767c3a4c759533186d13425e4ea85d6`
- `reject/R70-state-at-open-copy-differs/artifacts/02-b/out.json`: `sha256:1b00ede16212c7a5646c9b4ddb35fe0307ba3b068358622be9d3d2833f3beaae`
- `reject/R70-state-at-open-copy-differs/receipts/01-a.json`: `sha256:959aa81dae0c73d1524d9c8b20d25a9dbadb82275b7c8ad38f6d6af3c5d34855`
- `reject/R70-state-at-open-copy-differs/receipts/02-b.json`: `sha256:5021302852406ee07da66fa9281c610b90d8f8374356fbb2b37a5849a00ead4e`
- `reject/R70-state-at-open-copy-differs/receipts/03-onetrace-close.json`: `sha256:d797e3d6a5b48cc4671513bc79bff969a94b539b331b6971579da0f81db5c99c`
- `reject/R71-state-at-open-not-first/MANIFEST.json`: `sha256:fac1753d6bfc8f1afdc452fb2108f5e67434f98d721890ca3a3dc9344e574601`
- `reject/R71-state-at-open-not-first/artifacts/01-a/out.json`: `sha256:ece1fa5e6f63aea714943e77ad134cf9a767c3a4c759533186d13425e4ea85d6`
- `reject/R71-state-at-open-not-first/artifacts/02-b/out.json`: `sha256:1b00ede16212c7a5646c9b4ddb35fe0307ba3b068358622be9d3d2833f3beaae`
- `reject/R71-state-at-open-not-first/receipts/01-a.json`: `sha256:959aa81dae0c73d1524d9c8b20d25a9dbadb82275b7c8ad38f6d6af3c5d34855`
- `reject/R71-state-at-open-not-first/receipts/02-b.json`: `sha256:e723dfc9070f3a7c19f4f78e86675554375cba61a2bf742567615a35ebe2dea4`
- `reject/R71-state-at-open-not-first/receipts/03-onetrace-close.json`: `sha256:206f445001eace70247bbfba97c4bdf73901478f9ca212edea92600c56879ee1`
