This is data, not source: a real `python -m onedoor.export` output, captured for the console's
onedoor extension. Committed here verbatim; the console's tests read these two files and never
run onedoor (per the order's own words).

**Superseded once, honestly: this replaces the first version of this fixture**, which was
built against onedoor's fallback pin `164ba2e` because onedoor's change was not yet accepted.
onedoor's `main` and `wo-d4` were then pushed at `947666e`, verified
independently here via `git ls-remote origin main` against the real public remote (not a
local clone) before rebuilding anything below.

## What was run

Cloned onedoor fresh from its public remote and checked out
`947666e60e2ad0cc881094a7c6e41303ea4cc05b` (`docs: state the reason in two docstrings instead
of a reference`, 2026-09-27T02:51:13+02:00). Installed with `pip install -e .` into a
throwaway venv **outside** this repository. Set `ONEDOOR_ISSUER` to an issuer name in the
environment (without an issuer configured onedoor returns no reference for anything at all,
not only for dry-run/observe; the name itself is not written into the export). Ran, from a fixture directory outside the
console tree:

```
ONEDOOR_ISSUER=<issuer> python make_fixture.py <output folder>
```

`make_fixture.py` (committed alongside this file) drives
`onedoor.guardrail.executor.evaluate_and_execute()`/`resume_approval()` through:

1. `demo.toggle` -> `state=on`: **permit**-shaped, enforce mode.
2. `demo.toggle` -> `state=sideways`: **deny**-shaped, out of declared bounds.
3. `demo.unlisted`: **propose**-shaped (default-deny, Tier 3), **then approved and
   resumed** — its own fresh decide, with its own new `request_id`, per onedoor's own
   `docs/decision-ref.md`: *"the resumption runs as a fresh decide with its own new
   request id... the reference it returns names that resumption's own decision — not
   the original proposal."*
4. `demo.observed`, a new Tier-0 (`OBSERVE`) policy added for this fixture only
   (`wo_c9_policies.yaml`, committed alongside): executes regardless of policy, and the
   script asserts `result.decision_ref is None` for it — observe mode's own rule, checked
   against the real engine, not merely read from its docs.

Every one of the four `assert`s in `make_fixture.py` about what reference each call
returns (`permit`/`deny`/`propose`/`permit`-on-resume/`None`-on-observe) passed on this
run, so the fixture is proof the behaviour is real, not only documented.

The database (`<output folder>/fixture.db`) is **not** committed; only
`onedoor-export.jsonl`, its `.sha256` sidecar, `make_fixture.py`, and `wo_c9_policies.yaml`
are.

## The seven rows

| id | kind | request_id | decision | approval_id | parent_id |
|---|---|---|---|---|---|
| 1 | exec_intent | `e5504d65…` | executed | — | — |
| 2 | exec_result | `e5504d65…` | executed | — | 1 |
| 3 | decision | `395fa044…` | denied | — | — |
| 4 | decision | `dd52541b…` | proposed | **1** | — |
| 5 | exec_intent | `14be2756…` | executed | — | — |
| 6 | exec_result | `14be2756…` | executed | — | 5 |
| 7 | decision | `b8274738…` | executed (observe) | — | — |

## The finding this settles: no field links a resumption to its original proposal

This was to be checked against real data, quoting the field. Done:
row 4 (the propose) carries `approval_id=1`; rows 5 and 6 (its resumption) carry
`approval_id=None` — **not** `1`, and no other column on either resumption row names
`request_id=dd52541b…`, `id=4`, or `approval_id=1` in any form. `parent_id` links row 6
to row 5 (the resumption's own `exec_result` to its own `exec_intent`), the same
bookkeeping row 2 has to row 1 — it says nothing about the propose. onedoor's own
`docs/decision-ref.md` says the two "are linked in onedoor's audit log the same way any
propose-then-resume pair already is" — true only of the internal `approvals` table
(`approvals.audit_id` points at the resumption's row, checked in `onedoor/guardrail/
approvals.py`'s `mark_executed`), which is **not part of any export** the console can see.
**Recorded as a gap owned by onedoor, not built here.**

## The permit reference names the intent row, not the result row

Confirmed directly, not assumed: `result.decision_ref.decision_digest` for the first
(permit) call equals row 1's digest (`exec_intent`), not row 2's (`exec_result`) —
matching `ActionResult.decision_ref`'s own docstring in `onedoor/guardrail/models.py`:
*"For an executed... outcome, this names the ORIGINAL decision (the exec_intent row,
verdict permit)... not the result row."* This is why the console's join must search every row sharing a `request_id` for the one matching digest, never assume
"the representative row" (`exec_result` first) the Policy page's own list-view grouping
uses for a different purpose (unaffected by this).

## Changed since the run

Only words, never what is run or asserted: `make_fixture.py`'s docstring, the text of two
assertion messages, its default output folder name, and two free-text inputs to onedoor (the
requests' `rationale` and the approval's session name) were reworded after the run, and the
comment in `wo_c9_policies.yaml`. Neither input appears in `onedoor-export.jsonl`, so the export
is byte for byte the one this run wrote; `SHA256SUMS` records the files as they are now.

## `SHA256SUMS`

Generated by `tools/hash_fixture.py`, never hand-typed; `tests/conftest.py`'s fixture
loader checks every file against it before handing the folder to a test.
