# A recipient confirmation's run, from onetrace 0.8.0's own vectors

`A102-real-effected/` is copied byte for byte from onetrace 0.8.0's sdist (`onetrace-0.8.0.tar.gz`,
`sha256:b9887f201a5a037a3691cc2bcb424b28f8a951efed52417332694429e7901028`), its folder
`tests/format_0_4/A102-real-effected/`: an accept vector of format 0.5's section J, a step that presented a
permit and kept the recipient's confirmation that it acted. onetrace's `tests/format_0_4/INDEX.json` gives each
file's sha256, and these are the same. `tests/test_format_05_confirmation.py` holds them.

The folder is the same bytes in an earlier build of onetrace 0.8.0's sdist, which it was first copied
from.

## The files

- `MANIFEST.json`: `sha256:c1a008f92f03f9d50ee0ecb325a1521a865d8f25308ce416affb9ff0a238daf8`
- `authorization/01-approve-payment/confirmation.jwt`: `sha256:bc293b3a7ba656e90b8706ba24397375f36d21d1016375b59d1b107b3db25fd8`
- `receipts/01-approve-payment.json`: `sha256:cc09dd29aab94597deaa1bac66e03b0f0ec5a1af0baba3f2d3e0ff3296183f7e`
- `receipts/02-onetrace-close.json`: `sha256:209985246213b91b1b2f6d74bf8925b6d98b210fea89595b7818308d9e9e7796`
- `recipients.json`: `sha256:9475df81330e739d74213f023414144c7502401367b0eb9312f0783c5d9ff258`
