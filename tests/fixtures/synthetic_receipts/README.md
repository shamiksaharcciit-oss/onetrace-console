Synthetic until the SDK records decision references.

The "Decisions cited" panel is built to its specified shape now, but the SDK does
not emit `decision_refs` yet (out of scope: `ctx.decision` and `gated_stages` come
from the SDK after 0.1.1). Everything in this folder is **hand-made**, not
SDK output, so that the join and panel can be built and tested against that shape
ahead of the SDK actually producing it. To be replaced by SDK-made receipts once
the SDK emits them.

`five_states.json` describes one synthetic run's stages, covering ruling 26z's five
panel states exactly once each. Three of its `decision_refs` cite real request_ids
from `tests/fixtures/onedoor/onedoor-export.jsonl` (rebuilt from onedoor's
pushed `main` at commit `947666e`); their
`decision_digest` values were computed by hand from that file's own lines
(`sha256(line)`, no trailing newline), not invented:

    e5504d65-cfd0-494e-b98e-9a49f77207b3  exec_intent  sha256:1043199e...86b5381  (permit)
    395fa044-08d1-4b41-a649-619f1e3731a3  decision     sha256:4ff68f0a...0692b28  (deny)

The state-2 (mismatch) stage cites the second of those with its **last hex digit
changed** (`...b28` -> `...b29`) -- a deliberate, minimal corruption, not a
different real digest. The state-4 (missing, gated) stage's comment names the real
fixture row it stands in for: `demo.observed` (id=7), an observe-mode decision that
onedoor itself returns no reference for (ruling 27b) -- a gated stage running under
observe mode genuinely has nothing to cite, which is exactly what this state means.

**Not used here, and why:** the real fixture's propose (request_id `dd52541b…`) and
its resumption (request_id `14be2756…`) do **not** share a `request_id` -- onedoor's
own `docs/decision-ref.md`: a resumption "runs as a fresh decide with its own new
request id." Ruling 27h item 3's own test (a reference to a resumption and a
reference to the original, under the SAME `request_id`, each resolving to their own
row) is therefore built from **hand-crafted rows** in
`tests/test_decision_refs.py::test_a_request_id_naming_two_rows_resolves_each_
reference_to_its_own_row`, mirroring the exact adversarial shape onedoor's own
`tests/test_decision_ref_checker.py` uses for the same reason -- not from this
folder, since the real fixture cannot demonstrate it honestly.
