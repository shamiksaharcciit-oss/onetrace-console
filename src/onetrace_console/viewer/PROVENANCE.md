# Where the viewer came from

The files in this folder were copied byte for byte from `viewer/` at commit `8578503` of the
private repository the viewer was developed in. Its tests stay there: they read that repository's
own fixtures. Six that stand alone were moved to `tests/viewer/`.

Each row gives the file's sha256 at that commit and its sha256 here. The two columns differ only
for a file changed since the copy. `tests/test_viewer_provenance.py` checks the second column
against the files, and that this table lists every file in the folder.

| file | sha256 at 8578503 | sha256 here |
|---|---|---|
| `__init__.py` | `5f521063c2f138c0856b6dfc9a137103833562c2e28a349e5ac6ee9815920774` | `8705b3eb954fc6c635394b6c6e7560abdaa418a0212bbe20bb8dde6f80806c46` |
| `__main__.py` | `f0855c2ce7ed2261f38d26981e18ef0dc9500ae8bd2805cad8f87c0a3c1270de` | `df7c0235a2ab4c05b8723c5bcf83c4f36c223dffe83992fbbb233631d80d4104` |
| `_vendor/TOKENS_DARK.css` | added here | `71ff312a749f7541d007482dd49f2aee0b7cb06416809defb66a8e2fe32e6f1b` |
| `_vendor/tokens_dark.SHA256` | added here | `92ae7ef7aeee25054e6cfc3f611a4e260b79076a3181f3157c68cefde136a726` |
| `dark_derived.css` | added here | `b5e914c6acf07da96baccd1aec0eb8743802b4a4765afed49cf84cb3952a9a25` |
| `depth.py` | `f0762ec0287d6cf68bc0431b0bf2328a32802481852de3bc6dc831849eaf1ab6` | `9e855795f04f40ca0ef1d86ed0bb325fbf447173c9430c31a4553371b4918e1f` |
| `fingerprint.py` | `98a46cd0211e695ba063e6946fae13e75b04424b37f20443b0366e063e0aca65` | `13e58d6703176378df741eafbd0b9edb642edeb1a582e59bc6902a5e14037c62` |
| `graph.py` | `8bdccf003213f89d7c6bc7e0ba5572e3a7ed9e2765eabd8dadeb5c1afb0dfb2e` | `33d25b637f6e3e8dbc7e7571133eb19f38b2e5414b041a437a943e090c9d7711` |
| `model.py` | `4ba956939f6d22c3381824958eb2782d515f2224c92cbf388bfafceb32eabfae` | `b4a1416ba56940f5da2aa760f3370902d582cdd726344bddb9a54269435a62b9` |
| `page.py` | `7defb7d7def93b3ef9f96ddf6651af37f12ecf2b9776289cb4bb1210e4084931` | `8fa491b771deac4045d0571c0939e5bc7039099609729630b78c9666a50be9a9` |
| `record.py` | `25396f5cec18aa69d5b43b581655065432830fc8ce0e0e8d653eb1344dcc3c3b` | `3c26fe334a2ef881b7f5b91bbade0ba32169aa2f056598c8d19caf8b41431325` |
| `report.py` | `42c5df1f9c05749e0a2d8332a0cdae1b9adda9eea6e0a14774b6f40d6a513681` | `0e66060c595c463c625c7c1098d7ad63ab45012ed26cb31db184080ff19d21ad` |
| `sentences.py` | `1194b0dbad220e71f2be2c3afae9e3d795bdd3fb021cc45a68c28a0eb9727d80` | `780c85599334400025c14842477cc8a0d00ed7d75e3dcdd563acea86c4797ab7` |
| `skin_tokens.py` | added here | `20cbaab61c397f964a0737812f562523acce55317de068e5c2d3e6897c94f6e5` |
| `slot.py` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` | `2ea05f47a3063c77e16a873a0e253ba174561431c3d4ee3daf3c87fbe18fed75` |
| `tokens.py` | `792b6759de97b9f0b68304d79a1b26fa3e38f2b804f8b3363eaa9475698c9d26` | `4cb0d2becf0169eb01704a35e9e28eba18eae34b42145edc0e9148b88aedb859` |
| `verbs.py` | `22d2e2456324cbe990e1e40c68cd8fb8d2bd463853f93b93ba4faeb8e203f64a` | `246eb98c10ade29b2ca89dca900c1538b0247edfb06e19b945a572729be08bf2` |

The skin's token block: for 0.8.0 it moved, byte for byte, into `skin_tokens.py` (added here), and the
note that carried it, with its digest file, left the package. The block's sha256 is unchanged, so `tokens.SPEC_FENCE_DIGEST` is too;
`tests/viewer/test_skin_note.py` checks the tokens.

`_vendor/TOKENS_DARK.css`: added here for the dark theme, the visual target's `TOKENS.css` with its
closing comment removed (it named an internal document by its id); its tokens are unchanged. The target's file
was `cb32e24dfc002b54632fb32df0f9f2dbe64e9119a537c7c1e7e7f1f1fc3b3738`; `_vendor/tokens_dark.SHA256` and
`tokens.DARK_DIGEST` pin it as it is here. `dark_derived.css`: the dark values the target gives no
token for, chosen here (`tokens.DARK_DERIVED`).

`model.py`, `page.py`, `sentences.py`, `tokens.py`: for 0.6.0, references to internal documents were
taken out of their comments and docstrings, and in `sentences.py` out of the source notes beside its
sentences (the second value of each entry, which no page draws). No code and no sentence a page draws
changed.

For 0.8.0, the numbers of internal documents (decisions, memos, and the viewer's own) and
"ruled" wording were taken out of the code comments and docstrings of `__init__.py`, `__main__.py`,
`fingerprint.py`, `graph.py`, `model.py`, `page.py`, `record.py`, `report.py`, `sentences.py`, `tokens.py`
and `verbs.py`; `tests/test_no_ids_in_code_comments.py` holds them to it. No code, and no sentence a page
draws, changed.

Also for 0.8.0, the citations left in the values beside the sentences and in three error messages
were taken out of `model.py`, `sentences.py`, `tokens.py` and `verbs.py`: a document's number and section, a note's
number, a requirement's id, a decision's date and an internal file's name. Each place says in words what its rule or
sentence means, and the three error messages say what went wrong and what to do. The export scan holds the
export to it. No code, and no sentence a page draws, changed; the messages' words did.

Also for 0.8.0, the labels of rounds of work and of earlier checks' findings were taken out of the comments of
`__main__.py`, `model.py`, `page.py`, `record.py` and `report.py`; `tests/test_user_facing_strings.py` holds every
shipped file to it. No code, and no sentence a page draws, changed.

`report.py`, also for 0.8.0: it reads the lines onetrace-verify 0.8 writes after its summary on what a format
0.5 section's members do not show (`FORMAT_05_LEADS`, `_section_lines`, `_check_section_lines`), each held to
the same check's `--json`; `tests/test_format_05.py` holds them. Nothing else in it changed.

Also for 0.8.0, the last citations of documents the public tree does not hold were taken out of the comments
and docstrings of `__init__.py`, `fingerprint.py`, `model.py`, `record.py`, `report.py`, `sentences.py`,
`skin_tokens.py` and `tokens.py`, and the labels of earlier checks' findings with them: each place says its rule in words.
`tests/test_shipped_citations.py` holds every shipped file to it. No code, and no sentence a page draws, changed.

Also for 0.8.0, the 30 constants in `sentences.py` that were named after internal documents' numbers were renamed
after what each one's sentences are for, and every use with them. No value, no sentence and no behaviour changed;
`tests/test_visible_text.py`, unchanged, holds every page's text. The export scan reads an id inside a name too.

Also for 0.8.0, `sentences.py`'s header says what each settled entry carries beside its sentence, and no longer
that each names a document its words are checked against. Words only.
