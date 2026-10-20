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
| `__main__.py` | `f0855c2ce7ed2261f38d26981e18ef0dc9500ae8bd2805cad8f87c0a3c1270de` | `578c1dcd6006a84cad7a518e51e151aa2bfa29fc409c7366ce6a3396c4f9e308` |
| `_vendor/ONETRACE_CONSOLE_SKIN_v1.md` | `8df6ccbcb9c0b20a84d3bffd2d2a1b78a6db33f0a1a3147c568af23b7303511f` | `6386e640be5a9f47111b6a54cd55bad8afe504c803fb995562837da3844a517b` |
| `_vendor/skin.SHA256` | `53deb2f52380abaea1fad45bfab04c0164745ebbb19c9f69c91d00feb48abd24` | `4909027f8a58a2d8417e0b8ed28c674d431372f5700c8894ee8221e9803592c4` |
| `_vendor/TOKENS_DARK.css` | added here | `71ff312a749f7541d007482dd49f2aee0b7cb06416809defb66a8e2fe32e6f1b` |
| `_vendor/tokens_dark.SHA256` | added here | `92ae7ef7aeee25054e6cfc3f611a4e260b79076a3181f3157c68cefde136a726` |
| `dark_derived.css` | added here | `b5e914c6acf07da96baccd1aec0eb8743802b4a4765afed49cf84cb3952a9a25` |
| `depth.py` | `f0762ec0287d6cf68bc0431b0bf2328a32802481852de3bc6dc831849eaf1ab6` | `9e855795f04f40ca0ef1d86ed0bb325fbf447173c9430c31a4553371b4918e1f` |
| `fingerprint.py` | `98a46cd0211e695ba063e6946fae13e75b04424b37f20443b0366e063e0aca65` | `e98cc242d27f0f8b9a0d4a5fec1ac614a15e2f34ecb4686e90d57ace84d74a45` |
| `graph.py` | `8bdccf003213f89d7c6bc7e0ba5572e3a7ed9e2765eabd8dadeb5c1afb0dfb2e` | `eee9a7ecffdb0ce11db0e60134f1756c51c52a676381805cd547fcc735fe924a` |
| `model.py` | `4ba956939f6d22c3381824958eb2782d515f2224c92cbf388bfafceb32eabfae` | `6d7f86381fd9d5e5f432775ffdabe7f4d840b1e0917dc732126507d2c0926f49` |
| `page.py` | `7defb7d7def93b3ef9f96ddf6651af37f12ecf2b9776289cb4bb1210e4084931` | `a18a50c7c7a07a17b0b5d5386aa947c030f1e19269aba385fcc001f763fcb317` |
| `record.py` | `25396f5cec18aa69d5b43b581655065432830fc8ce0e0e8d653eb1344dcc3c3b` | `75eb787628b24441baf6c0c3771d4cb4452646e150f5bc3cf1dd54021f8f79f1` |
| `report.py` | `42c5df1f9c05749e0a2d8332a0cdae1b9adda9eea6e0a14774b6f40d6a513681` | `1660ccc04feb17bcca853aa5674219fdfc19c746c8edfd15ab14230d8d817f09` |
| `sentences.py` | `1194b0dbad220e71f2be2c3afae9e3d795bdd3fb021cc45a68c28a0eb9727d80` | `acd2223e506906aeef536f2e410fbf1411a38ea9e32042c884d0224bf631d98c` |
| `slot.py` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` |
| `tokens.py` | `792b6759de97b9f0b68304d79a1b26fa3e38f2b804f8b3363eaa9475698c9d26` | `53a309c87328f79f4cb9e19d4fcee9343aa832e4e6cbf250348a254a3530d589` |
| `verbs.py` | `22d2e2456324cbe990e1e40c68cd8fb8d2bd463853f93b93ba4faeb8e203f64a` | `fdcc1ac7ba72586d37f7c6eab2b12c87c0dc79bca78493bea468922c1559a098` |

`_vendor/ONETRACE_CONSOLE_SKIN_v1.md`: header removed; tokens unchanged. Its sha256 at 8578503 was
`8df6ccbcb9c0b20a84d3bffd2d2a1b78a6db33f0a1a3147c568af23b7303511f`; here it is
`6386e640be5a9f47111b6a54cd55bad8afe504c803fb995562837da3844a517b`, the value `tokens.SPEC_DIGEST` and
`_vendor/skin.SHA256` now pin. Its `css` block is byte for byte the original's, so
`tokens.SPEC_FENCE_DIGEST` is unchanged; `tests/viewer/test_skin_note.py` checks the tokens.

`_vendor/TOKENS_DARK.css`: added here for the dark theme, the visual target's `TOKENS.css` with its
closing comment removed (it named a ruling by its id); its tokens are unchanged. The target's file
was `cb32e24dfc002b54632fb32df0f9f2dbe64e9119a537c7c1e7e7f1f1fc3b3738`; `_vendor/tokens_dark.SHA256` and
`tokens.DARK_DIGEST` pin it as it is here. `dark_derived.css`: the dark values the target gives no
token for, chosen here (`tokens.DARK_DERIVED`).
