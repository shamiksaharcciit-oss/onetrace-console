"""The script that made the onedoor extension's fixture: onedoor at 947666e (main, pushed).

Run against a throwaway venv OUTSIDE the onetrace-console tree. Only the export
files this script writes are committed into the console repository -- never
this script's own database, and never onedoor's source.

ONEDOOR_ISSUER must be set in the environment before this runs:
without an issuer configured, onedoor returns no decision_ref for anything, not
just for dry-run/observe -- this script asserts that below rather than silently
producing a fixture with no references anywhere.

Scenario, one call for each case the console reads:
  - demo.toggle on        -> Decision.EXECUTED, enforce mode -> a `permit` reference.
  - demo.toggle sideways  -> Decision.DENIED                 -> a `deny` reference.
  - demo.unlisted         -> Decision.PROPOSED               -> a `propose` reference,
                             then approved and resumed -> a second, separate decide
                             with its OWN new request_id (onedoor's own docs:
                             "the resumption runs as a fresh decide with its own
                             new request id"). Both rows are exported so the propose's
                             resolution can be checked against real data,
                             quoting whatever field actually links them, or shows
                             that none does.
  - demo.observed         -> tier 0 (OBSERVE), Decision.EXECUTED, but must carry
                             NO reference at all -- asserted below.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from onedoor.connectors import mock
from onedoor.guardrail import policy_loader
from onedoor.guardrail.executor import EngineConfig, evaluate_and_execute, resume_approval
from onedoor.guardrail.models import ActionRequest, Source
from onedoor.store.db import Database
from onedoor.export import write_export

NOW = datetime(2026, 9, 27, 12, 0, 0, tzinfo=UTC)

ISSUER = os.environ.get("ONEDOOR_ISSUER")
if not ISSUER:
    raise SystemExit("ONEDOOR_ISSUER must be set in the environment before this script runs "
                    "-- without it onedoor issues no reference at all.")

CONFIG = EngineConfig(
    approval_ttl_seconds=3600,
    connector_timeout_seconds=5.0,
    tz=ZoneInfo("Europe/Amsterdam"),
    issuer=ISSUER,
)


def req(action_type: str, source: Source = Source.RULE, **params: object) -> ActionRequest:
    return ActionRequest(
        request_id=uuid4(),
        action_type=action_type,
        params=dict(params),
        source=source,
        rationale="fixture: the console's onedoor extension",
        created_at=NOW,
    )


def show(label: str, result) -> None:
    d = result.decision
    ref = getattr(result, "decision_ref", None)
    print(f"  {label:34s} -> {d.decision.value:9s} (tier {int(d.effective_tier)}, "
         f"reason {d.reason_code.value}, request_id={result.audit_id}) "
         f"ref={'none' if ref is None else ref.verdict}")


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "fixture-out")
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "fixture.db"
    if db_path.exists():
        db_path.unlink()

    db = Database(str(db_path))
    db.init()
    conn = db.connect()
    policy_loader.load_file(conn, Path(__file__).parent / "wo_c9_policies.yaml")
    registry = mock.build_registry()

    print("1) permit-shaped: a reversible Tier-1 action auto-executes (enforce mode)")
    r1 = evaluate_and_execute(
        req("demo.toggle", target="demo.lamp", state="on"),
        conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.toggle on", r1)
    assert r1.decision_ref is not None and r1.decision_ref.verdict == "permit", \
        f"expected a permit reference, got {r1.decision_ref!r}"

    print("2) deny-shaped: an out-of-range parameter is denied before any human sees it")
    r2 = evaluate_and_execute(
        req("demo.toggle", target="demo.lamp", state="sideways"),
        conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.toggle state=sideways", r2)
    assert r2.decision_ref is not None and r2.decision_ref.verdict == "deny", \
        f"expected a deny reference, got {r2.decision_ref!r}"

    print("3) propose-shaped: an unlisted action type falls to a Tier-3 proposal")
    r3 = evaluate_and_execute(
        req("demo.unlisted", anything="goes"),
        conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.unlisted", r3)
    assert r3.decision_ref is not None and r3.decision_ref.verdict == "propose", \
        f"expected a propose reference, got {r3.decision_ref!r}"

    print("3b) that proposal, approved and resumed -- its own fresh decide")
    r3b = resume_approval(
        r3.approval_id, "fixture-session",
        conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.unlisted (resumed)", r3b)
    assert r3b.decision_ref is not None and r3b.decision_ref.verdict == "permit", \
        f"expected a permit reference for the resumption, got {r3b.decision_ref!r}"
    assert r3b.audit_id != r3.audit_id, "the resumption must be its own row, not the original"

    print("4) observe-shaped: tier 0 goes ahead regardless, but carries NO reference")
    r4 = evaluate_and_execute(
        req("demo.observed", target="demo.lamp", state="on"),
        conn=conn, registry=registry, config=CONFIG, now=NOW)
    show("demo.observed", r4)
    assert r4.decision_ref is None, \
        f"observe mode must return no reference; got {r4.decision_ref!r}"

    conn.close()

    conn = db.connect()
    export_path = out_dir / "onedoor-export.jsonl"
    count = write_export(conn, export_path)
    conn.close()
    print(f"\nwrote {count} row(s) to {export_path}")
    print(f"sidecar: {export_path.name}.sha256")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
