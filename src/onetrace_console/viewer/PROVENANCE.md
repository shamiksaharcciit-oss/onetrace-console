# Where the viewer came from

The files in this folder were copied byte for byte from `viewer/` at commit `8578503` of the
private repository the viewer was developed in. Its tests stay there: they read that repository's
own fixtures. Six that stand alone were moved to `tests/viewer/`.

Each row gives the file's sha256 at that commit and its sha256 here. The two columns differ only
for a file changed since the copy. `tests/test_viewer_provenance.py` checks the second column
against the files, and that this table lists every file in the folder.

| file | sha256 at 8578503 | sha256 here |
|---|---|---|
| `__init__.py` | `5f521063c2f138c0856b6dfc9a137103833562c2e28a349e5ac6ee9815920774` | `265241c73121654796b73062b4190c02e237a21d1aa8ab2c050b70333fb6b242` |
| `__main__.py` | `f0855c2ce7ed2261f38d26981e18ef0dc9500ae8bd2805cad8f87c0a3c1270de` | `e14bd8963edcb7c7cf0b3fa68ac1dad1ee19d0b86e6612977fbca9535510bf27` |
| `_vendor/ONETRACE_CONSOLE_SKIN_v1.md` | `8df6ccbcb9c0b20a84d3bffd2d2a1b78a6db33f0a1a3147c568af23b7303511f` | `6386e640be5a9f47111b6a54cd55bad8afe504c803fb995562837da3844a517b` |
| `_vendor/skin.SHA256` | `53deb2f52380abaea1fad45bfab04c0164745ebbb19c9f69c91d00feb48abd24` | `4909027f8a58a2d8417e0b8ed28c674d431372f5700c8894ee8221e9803592c4` |
| `depth.py` | `f0762ec0287d6cf68bc0431b0bf2328a32802481852de3bc6dc831849eaf1ab6` | `572c9d2959df6e71bd3a42a0717eacafc4c088d9023685207b1e04add92f1564` |
| `fingerprint.py` | `98a46cd0211e695ba063e6946fae13e75b04424b37f20443b0366e063e0aca65` | `e98cc242d27f0f8b9a0d4a5fec1ac614a15e2f34ecb4686e90d57ace84d74a45` |
| `graph.py` | `8bdccf003213f89d7c6bc7e0ba5572e3a7ed9e2765eabd8dadeb5c1afb0dfb2e` | `c192dba683e02ddcbead2da5c7c925a124bbdae0b400d2517e87f81802e8d6d4` |
| `model.py` | `4ba956939f6d22c3381824958eb2782d515f2224c92cbf388bfafceb32eabfae` | `3f32c3763226242d3583d6e427942b16e48f4ce99c5f59a815c43ae7aa2f1e80` |
| `page.py` | `7defb7d7def93b3ef9f96ddf6651af37f12ecf2b9776289cb4bb1210e4084931` | `40c5d3570607e396eb0f2021f9246eafd1234bbff26fb45dafb0c0826f95d795` |
| `record.py` | `25396f5cec18aa69d5b43b581655065432830fc8ce0e0e8d653eb1344dcc3c3b` | `75eb787628b24441baf6c0c3771d4cb4452646e150f5bc3cf1dd54021f8f79f1` |
| `report.py` | `42c5df1f9c05749e0a2d8332a0cdae1b9adda9eea6e0a14774b6f40d6a513681` | `1660ccc04feb17bcca853aa5674219fdfc19c746c8edfd15ab14230d8d817f09` |
| `sentences.py` | `1194b0dbad220e71f2be2c3afae9e3d795bdd3fb021cc45a68c28a0eb9727d80` | `9c5ad5f644df9e298e332dffdb7ea1861f30664655e3c6bef6add9877203fb70` |
| `slot.py` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` |
| `tokens.py` | `792b6759de97b9f0b68304d79a1b26fa3e38f2b804f8b3363eaa9475698c9d26` | `e6d0f5ca5d983309aaafbb4a16c0b0b07e3eade148c12d7390d96464a2f1fe68` |
| `verbs.py` | `22d2e2456324cbe990e1e40c68cd8fb8d2bd463853f93b93ba4faeb8e203f64a` | `fdcc1ac7ba72586d37f7c6eab2b12c87c0dc79bca78493bea468922c1559a098` |

`_vendor/ONETRACE_CONSOLE_SKIN_v1.md`: header removed; tokens unchanged. Its sha256 at 8578503 was
`8df6ccbcb9c0b20a84d3bffd2d2a1b78a6db33f0a1a3147c568af23b7303511f`; here it is
`6386e640be5a9f47111b6a54cd55bad8afe504c803fb995562837da3844a517b`, the value `tokens.SPEC_DIGEST` and
`_vendor/skin.SHA256` now pin. Its `css` block is byte for byte the original's, so
`tokens.SPEC_FENCE_DIGEST` is unchanged; `tests/viewer/test_skin_note.py` checks the tokens.
