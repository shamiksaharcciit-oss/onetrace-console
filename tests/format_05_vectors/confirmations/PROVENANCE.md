# The recipient's confirmation: four more of onetrace 0.8.0's own vectors

Copied byte for byte from onetrace 0.8.0's release sdist (`onetrace-0.8.0.tar.gz`,
`sha256:57e5f8e3c1ff825f11d0554debae336da7477b728b72c3bf3c91d6f0324b3fb3`), folder `tests/format_0_4/`.
onetrace's `tests/format_0_4/INDEX.json` gives each file's sha256, and these are the same.

- `A103-real-effect-unknown`: a step whose recipient's confirmation says the effect is unknown: every row holds.
- `R118-confirmation-c03`: the step reported ok, the recipient says refused: `confirmation: outcome` FAILs.
- `R119-confirmation-c04`: the confirmation does not verify under the recipient's listed key. It FAILs only with
  `--recipients`; without it, the key row reads NOT-RUN and the others PASS.
- `R121-confirmation-c07`: the recipient confirmed a different request body: `confirmation: request` FAILs.

## The files

- `A103-real-effect-unknown/MANIFEST.json`: `sha256:1c39bc495fc1d1fffb28edf07678e056a9af8c451aede0ff6584295a12f7245c`
- `A103-real-effect-unknown/authorization/01-approve-payment/confirmation.jwt`: `sha256:ecb1fd903b674416ad90cbca7a7cb6d0b318d5351e2b220fca5fcb4bf7554029`
- `A103-real-effect-unknown/receipts/01-approve-payment.json`: `sha256:51f44e0bc0d29ef5b772f2fee75243634fd2c095c6ff65dba6a4e8283e8f4e1c`
- `A103-real-effect-unknown/receipts/02-onetrace-close.json`: `sha256:e65c7e7fb0ba11d65051026cead2ad4227247b18ee224172ca5994395a6fee9e`
- `A103-real-effect-unknown/recipients.json`: `sha256:9475df81330e739d74213f023414144c7502401367b0eb9312f0783c5d9ff258`
- `R118-confirmation-c03/MANIFEST.json`: `sha256:897d5a5805ef7281e2c160e0ed2d49b9c3ad3469064ddb1694debb02b24b28eb`
- `R118-confirmation-c03/authorization/01-approve-payment/confirmation.jwt`: `sha256:cd2be0e89557ea775f7056c25b4673213626f283096b32558263956f1045971e`
- `R118-confirmation-c03/receipts/01-approve-payment.json`: `sha256:d42161342b54a00604d53b87494ef8d3740a4ec8eda08b12bcf60eb10751a761`
- `R118-confirmation-c03/receipts/02-onetrace-close.json`: `sha256:b605a29d322797c90014ab2850693292a2a459de1e7c5c263df04b502f845464`
- `R118-confirmation-c03/recipients.json`: `sha256:9475df81330e739d74213f023414144c7502401367b0eb9312f0783c5d9ff258`
- `R119-confirmation-c04/MANIFEST.json`: `sha256:1f98e7418ea4f8f61c831c6def30fa9e124e3929db580391355a5c064a8c655a`
- `R119-confirmation-c04/authorization/01-approve-payment/confirmation.jwt`: `sha256:70ffda41945bd8623141550265126e7b778fd9e5e574e8c09b9c86dce656f402`
- `R119-confirmation-c04/receipts/01-approve-payment.json`: `sha256:6ad19f5d3a9f6e112c656971c928f9f76205055e3142ff49448714bfb93d4088`
- `R119-confirmation-c04/receipts/02-onetrace-close.json`: `sha256:0ef843babd21e3320d23f603b1d71439fc4afe46ba7a78073cfc6aade0b8cdd5`
- `R119-confirmation-c04/recipients.json`: `sha256:9475df81330e739d74213f023414144c7502401367b0eb9312f0783c5d9ff258`
- `R121-confirmation-c07/MANIFEST.json`: `sha256:f84fb1878ef320ce7864cf51ab456821d51c92072369160e94c9a9769302fe1d`
- `R121-confirmation-c07/authorization/01-approve-payment/confirmation.jwt`: `sha256:6c4d6f8b0e55d170c8d23db7ea1724f6cde7138600d7f79886ca8a24ffc9e823`
- `R121-confirmation-c07/receipts/01-approve-payment.json`: `sha256:bd2cc7f03681e0a6e94b4e6d2ce49db639987560498770ea210d1cb6ed654f53`
- `R121-confirmation-c07/receipts/02-onetrace-close.json`: `sha256:e6b15039f98e1d70ed68028c523f2656de9a620443017ce89049fa578d6bb6f8`
- `R121-confirmation-c07/recipients.json`: `sha256:9475df81330e739d74213f023414144c7502401367b0eb9312f0783c5d9ff258`
