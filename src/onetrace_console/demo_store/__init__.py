"""The demo store: the runs `onetrace-console demo` serves, made from real runs by one builder.

`build(folder)` is the only way the demo's runs are made:

1. it records every run of the pipelines below with onetrace, at the time it is built --
   the times in the record are read from the clock, never set;
2. it signs the runs that are signed, with one of two keys from public seeds (`keys.py`);
3. it applies, after a run has closed, the one action that gives that run its state -- a byte
   changed, a file deleted, the output folder removed -- and nothing else. No state is set: the
   console's own check reads each run, and what it reads is the run's state;
4. it writes the demo's trust file and `BUILD_RECORD.json`, the sha256 of every file it made.

`deliver(folder, store, config)` then hands the runs to the console the way `POST /v1/runs`
takes them (`folder_load.load_folder`), checks them, and stores the demo's comparisons (`COMPARISONS`).

The pipelines:
- P1, `refund_policy.py`: a small retrieval Q&A over an example shop's policy pages;
- P2, `reference_pipeline.py`: the reference demo's pipeline, byte for byte the
  `examples/reference-demo/demo.py` it ships beside, run with the real clock;
- P3, `ticket_triage.py`: a support-ticket triage shaped as a graph;
- P4, `support_reply.py`: a reply drafted by a stub that varies per run (marked not re-runnable),
  then a policy stage whose recorded refund window changes between the demo's first two runs of it.
  The draft names the window in words, and the policy stage puts in the number of days. Its third
  run asks for a window longer than the policy allows, and the policy stage declines it. Its intake
  keeps the customer's ticket, invented example data, beside its digest.
- P5, `pump_maintenance.py`: a pump's vibration readings to a maintenance work order;
- P6, `fill_inspection.py`: a camera frame of a bottle to a fill level and a reject command;
- P7, `cold_chain.py`: a temperature logger's readings to releasing or quarantining a shipment; it
  keeps the logger's file, invented example data, beside its digest;
- P8, `invoice_match.py`: a supplier's invoice matched against its purchase order and goods receipt,
  to paying or holding it; it keeps the invoice's file, invented example data, beside its digest.
  Its last run is over the approver's limit, and the approval stage declines it;
- P9, `torque_check.py`: a tightening tool's wheel-bolt torques to passing the wheel or sending it to
  rework.

P5, P6, P7 and P9 are physical-world pipelines over invented data the builder makes: the demo
records and compares them, and controls no equipment. P8 pays nothing: the demo records and compares
it, and contacts no payment system.

A run folder or trust file whose bytes the build record doesn't hold -- edited, added or removed
after the build -- is refused wherever the built folder is used again (`check_build_record`).
Its limit: it catches a change made after the build. A hand-made run fed into the builder is
prevented by the builder being the only thing that writes the demo, not by the record.

Anchoring is not part of the demo: every run reads "not anchored", as the SDK records it.
"""
from __future__ import annotations

import hashlib
import os
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from onetrace_console.demo_store import keys

BUILD_RECORD = "BUILD_RECORD.json"
BUILD_FORMAT = "onetrace-console-demo-build/0.1"
TRUST_NAME = "trust.json"
RUNS_DIRNAME = "runs"
#: What the builder writes beside the run folders, in `runs/`: P8's decision export, its sidecar and
#: the issuer's public key (`onedoor_demo`), and every run's trace (`write_traces`).
BESIDE_RUNS = ("decisions.jsonl", "decisions.jsonl.sha256", "permit-issuers.json", "traces")


@dataclass(frozen=True)
class RunSpec:
    """One run of the demo: its folder (also its run id, unless `run_id` says otherwise), the
    pipeline and its arguments, the key that signs it, and the action taken after it closed."""
    folder: str
    pipeline: str
    args: dict = field(default_factory=dict)
    sign: str = "trusted"                   # "trusted", "untrusted" or "" (unsigned)
    after: str = ""                         # "", "tamper", "delete-one", "no-artifacts",
    #                                         "tamper-decision"
    run_id: str = ""


def _p1(n: int, kind: str, qs: str, **kw) -> RunSpec:
    from onetrace_console.demo_store import refund_policy as p1
    settings = p1.BASELINE if kind == "baseline" else p1.CANDIDATE
    tail = kw.pop("tail", "")
    return RunSpec(f"p1-{n:02d}-{kind}-set{qs}{tail}", "p1",
                   {"settings": settings, "question_set": qs, "fault": kw.pop("fault", "")}, **kw)


def _p3(n: int, ticket: str, rules: str, **kw) -> RunSpec:
    tail = kw.pop("tail", "")
    return RunSpec(f"p3-{n:02d}-{ticket.lower()}-rules{rules}{tail}", "p3",
                   {"ticket": ticket, "rules": rules, "fault": kw.pop("fault", "")}, **kw)


def runs() -> list[RunSpec]:
    """Every run of the demo, in delivery order: P1's first, then P2's, and so on to P9's, so the
    console's pipeline labels (first arrival) read P1 to P9."""
    out = [_p1(n, "baseline", str(n)) for n in range(1, 7)]
    out += [_p1(n + 6, "candidate", str(n)) for n in range(1, 7)]
    out += [
        _p1(13, "baseline", "1", tail="-again"),
        _p1(14, "candidate", "3", tail="-byte-changed", after="tamper"),
        _p1(15, "candidate", "4", tail="-file-deleted", after="delete-one"),
        _p1(16, "candidate", "5", tail="-no-artifacts", after="no-artifacts"),
        _p1(17, "baseline", "2", tail="-unsigned", sign=""),
        _p1(18, "baseline", "3", tail="-unsigned", sign=""),
        _p1(19, "baseline", "4", tail="-untrusted-key", sign="untrusted"),
        _p1(20, "candidate", "6", tail="-answer-failed", fault="answer-last"),
        RunSpec("p2-21-demo-run-1", "p2", {"day": 1}, run_id="demo-run-1"),
        RunSpec("p2-22-demo-run-2", "p2", {"day": 2}, run_id="demo-run-2"),
        _p3(23, "T-1", "1"), _p3(24, "T-2", "1"), _p3(25, "T-3", "1"), _p3(26, "T-4", "1"),
        _p3(27, "T-1", "2"),
        _p3(28, "T-3", "1", tail="-lookup-retried", fault="lookup-once"),
        RunSpec("p4-29-reply-30-days", "p4", {"refund_days": "30"}),
        RunSpec("p4-30-reply-14-days", "p4", {"refund_days": "14"}),
        #: Declined at policy_check by its own rule: the run stops there.
        RunSpec("p4-31-reply-60-days-declined", "p4", {"refund_days": "60"}),
        RunSpec("p5-32-pump-baseline", "p5", {"offset_mg": "0", "firmware": "3.1", "slot": "02:30"}),
        RunSpec("p5-33-pump-offset-changed", "p5", {"offset_mg": "40", "firmware": "3.1", "slot": "02:30"}),
        RunSpec("p5-34-pump-firmware-changed", "p5", {"offset_mg": "0", "firmware": "3.2", "slot": "02:30"}),
        #: Declined at work_order by its own rule: the slot is outside the maintenance window.
        RunSpec("p5-35-pump-outside-window-declined", "p5",
                {"offset_mg": "0", "firmware": "3.1", "slot": "14:00"}),
        RunSpec("p6-36-fill-baseline", "p6", {"frame": "full", "exposure_tenths": "10"}),
        RunSpec("p6-37-fill-exposure-changed", "p6", {"frame": "full", "exposure_tenths": "12"}),
        RunSpec("p6-38-fill-below-reject-line", "p6", {"frame": "low", "exposure_tenths": "10"}),
        RunSpec("p7-39-cold-chain-baseline", "p7", {"changed": False}),
        RunSpec("p7-40-cold-chain-one-reading-changed", "p7", {"changed": True}),
        RunSpec("p7-41-cold-chain-decision-tampered", "p7", {"changed": False}, after="tamper-decision"),
        RunSpec("p8-42-invoice-tolerance-2pct", "p8", {"invoice": "base", "tolerance_bp": "200"}),
        RunSpec("p8-43-invoice-tolerance-5pct", "p8", {"invoice": "base", "tolerance_bp": "500"}),
        RunSpec("p8-44-invoice-quantity-changed", "p8", {"invoice": "quantity-400", "tolerance_bp": "500"}),
        #: Declined at approve_payment by its own rule: over the approver's limit.
        RunSpec("p8-45-invoice-over-limit-declined", "p8", {"invoice": "large", "tolerance_bp": "500"}),
        RunSpec("p9-46-torque-baseline", "p9", {"firmware": "4.2", "low_bolt": False}),
        RunSpec("p9-47-torque-tool-firmware-changed", "p9", {"firmware": "4.3", "low_bolt": False}),
        RunSpec("p9-48-torque-one-bolt-low", "p9", {"firmware": "4.2", "low_bolt": True}),
        #: P8's gated step broken on purpose (onetrace 0.5): paid on a denied decision; and a
        #: permit for another amount than the payment the step records.
        RunSpec("p8-49-invoice-paid-on-deny", "p8", {"invoice": "base", "tolerance_bp": "500",
                                                     "plant": "pay-on-deny"}),
        RunSpec("p8-50-invoice-permit-other-amount", "p8", {"invoice": "base", "tolerance_bp": "500",
                                                            "plant": "permit-other-amount"}),
        #: P10, an agent whose step calls a sub-agent run, and P11, the sub-agent's runs, which each
        #: agent run records (`agent_settle`); named so each agent run arrives before its sub-agent's.
        RunSpec("pz-51-agent-baseline", "p10", {"inner": "pz-52-agent-baseline-subagent", "amount": "10"}),
        RunSpec("pz-52-agent-baseline-subagent", "p11", {"of": "pz-51-agent-baseline"}),
        RunSpec("pz-53-agent-amount-changed", "p10", {"inner": "pz-54-agent-amount-changed-subagent",
                                                      "amount": "20"}),
        RunSpec("pz-54-agent-amount-changed-subagent", "p11", {"of": "pz-53-agent-amount-changed"}),
    ]
    return out


#: The demo builder's mark: the pipelines whose runs read invented example data from outside the
#: pipeline and keep it. Only these runs' kept inputs, and only the bytes the builder itself
#: invents for them (`example_input_digests`), may be shown on a public console, and only for a
#: demo whose build record vouches for every byte (`allowing_examples`). It lives here, in the
#: builder's spec, and in no configuration: no setting can extend it to another store.
EXAMPLE_DATA = ("p4", "p7", "p8")


#: Each pipeline's name, as its own module's first line gives it. A public demo shows it beside the
#: console's label; a local console shows the label only.
PIPELINE_NAMES = {"p1": "refund-policy Q&A", "p2": "reference demo pipeline", "p3": "ticket triage",
                  "p4": "support reply", "p5": "pump maintenance", "p6": "fill-level inspection",
                  "p7": "cold-chain release", "p8": "invoice match", "p9": "wheel-bolt torque check",
                  "p10": "agent with a sub-agent", "p11": "sub-agent (called by the agent)"}


def name_of(run_ids) -> str | None:
    """The builder's name for the pipeline that every one of these run ids is a run of, or None
    where any is not the builder's own or they are not all of one pipeline."""
    by_id = {spec.run_id or spec.folder: spec.pipeline for spec in runs()}
    found = {by_id.get(r) for r in run_ids}
    if len(found) != 1 or None in found:
        return None
    return PIPELINE_NAMES[found.pop()]


def _module(pipeline: str):
    from onetrace_console.demo_store import cold_chain, invoice_match, support_reply
    return {"p4": support_reply, "p7": cold_chain, "p8": invoice_match}[pipeline]


def example_input_digests() -> frozenset:
    """The sha256 of every kept input the builder invents for a run of an EXAMPLE_DATA pipeline,
    from the pipelines' own code: "sha256:<hex>"."""
    return frozenset("sha256:" + hashlib.sha256(data).hexdigest()
                     for spec in runs() if spec.pipeline in EXAMPLE_DATA
                     for data in _module(spec.pipeline).kept_inputs(spec.args))


class allowing_examples:
    """While open, the example inputs' digests are the ones a public console may show -- only where
    `folder`'s build record vouches for every byte under it; otherwise none."""

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.allowed = False
        self._before = None

    def __enter__(self):
        from onetrace_console import kept_inputs
        self.allowed = not check_build_record(self.folder)
        self._before = kept_inputs.set_examples(example_input_digests() if self.allowed else ())
        return self

    def __exit__(self, *exc):
        from onetrace_console import kept_inputs
        kept_inputs.set_examples(self._before)
        return False


def serve_examples(folder: Path) -> bool:
    """For a public console serving the demo built in `folder`, for as long as it runs: the example
    inputs may be shown and downloaded only where the build record vouches for every byte. Returns
    whether they may."""
    allowing = allowing_examples(folder)
    allowing.__enter__()
    return allowing.allowed


def pipeline_names() -> list[str]:
    """The demo's pipelines, in delivery order: the count every page and document says is this."""
    return list(dict.fromkeys(spec.pipeline for spec in runs()))


#: The demo's comparisons, (baseline, candidate) by run folder. The first is the one the demo
#: opens: P1's headline, chunk_size 1024 against 512, on the question set where an answer moves.
COMPARISONS = [
    ("p1-02-baseline-set2", "p1-08-candidate-set2"),
    ("p1-01-baseline-set1", "p1-13-baseline-set1-again"),
    ("p2-21-demo-run-1", "p2-22-demo-run-2"),
    ("p3-23-t-1-rules1", "p3-27-t-1-rules2"),
    #: The stub's wording varies, so its stage is the first difference; the refund window, the
    #: recorded change, is two stages later.
    ("p4-29-reply-30-days", "p4-30-reply-14-days"),
    #: The calibration offset changed: the first difference is calibrate.
    ("p5-32-pump-baseline", "p5-33-pump-offset-changed"),
    #: The sensor's firmware version changed and its readings did not.
    ("p5-32-pump-baseline", "p5-34-pump-firmware-changed"),
    #: The exposure changed: measure differs, and classify comes back the same.
    ("p6-36-fill-baseline", "p6-37-fill-exposure-changed"),
    #: Filled below the reject line: measure differs, and classify changes after it.
    ("p6-36-fill-baseline", "p6-38-fill-below-reject-line"),
    #: One logger reading differs, past the range: the decision changes.
    ("p7-39-cold-chain-baseline", "p7-40-cold-chain-one-reading-changed"),
    #: The price tolerance changed, 2% to 5%: match differs, and the invoice held is paid after it.
    ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"),
    #: One invoice line's quantity differs, 40 to 400: the invoice is held.
    ("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed"),
    #: The tool's firmware version changed and its readings did not.
    ("p9-46-torque-baseline", "p9-47-torque-tool-firmware-changed"),
    #: One bolt reads below the window: the wheel goes to rework.
    ("p9-46-torque-baseline", "p9-48-torque-one-bolt-low"),
    #: The amount the sub-agent's step records changed, two levels down: the comparison descends
    #: into the sub-agent's run and names `settle`.
    ("pz-51-agent-baseline", "pz-53-agent-amount-changed"),
]


#: A build from an earlier build's runs (`build_from`, the hosted demo's) records P10's agent pair once
#: more beside the kept pair, which holds model-call records in the earlier draft format: the same
#: pipeline, its records in model-call-record/1.0. Their pair is compared, and their baseline marked as
#: P10's benchmark after the kept one, so P10's reference is made from it.
RECORDED_BESIDE_KEPT = [
    RunSpec("pz-55-agent-baseline-1-0", "p10", {"inner": "pz-56-agent-baseline-1-0-subagent", "amount": "10"}),
    RunSpec("pz-56-agent-baseline-1-0-subagent", "p11", {"of": "pz-55-agent-baseline-1-0"}),
    RunSpec("pz-57-agent-amount-changed-1-0", "p10", {"inner": "pz-58-agent-amount-changed-1-0-subagent",
                                                      "amount": "20"}),
    RunSpec("pz-58-agent-amount-changed-1-0-subagent", "p11", {"of": "pz-57-agent-amount-changed-1-0"}),
]
COMPARISONS_BESIDE_KEPT = [("pz-55-agent-baseline-1-0", "pz-57-agent-amount-changed-1-0")]
BENCHMARK_BESIDE_KEPT = "pz-55-agent-baseline-1-0"


def _benchmarks() -> tuple[str, ...]:
    """Each pipeline's baseline: the first pair's baseline of each pipeline the demo compares."""
    pipeline = {spec.folder: spec.pipeline for spec in runs()}
    first: dict[str, str] = {}
    for a, _b in COMPARISONS:
        first.setdefault(pipeline[a], a)
    return tuple(first.values())


#: The public demo's benchmarks, by run folder: each compared pipeline's baseline (`benchmarks`).
BENCHMARKS = _benchmarks()


def _record(spec: RunSpec, run_dir: Path, issuer=None) -> None:
    run_id = spec.run_id or spec.folder
    if spec.pipeline == "p1":
        from onetrace_console.demo_store import refund_policy
        refund_policy.main(run_dir, run_id, spec.args["settings"], spec.args["question_set"],
                           fault=spec.args["fault"])
    elif spec.pipeline == "p2":
        from onetrace_console.demo_store import reference_pipeline
        reference_pipeline.main(str(run_dir), run_id, spec.args["day"])
    elif spec.pipeline == "p3":
        from onetrace_console.demo_store import ticket_triage
        ticket_triage.main(run_dir, run_id, spec.args["ticket"], spec.args["rules"],
                           fault=spec.args["fault"])
    elif spec.pipeline == "p4":
        from onetrace_console.demo_store import support_reply
        support_reply.main(run_dir, run_id, spec.args["refund_days"])
    elif spec.pipeline == "p5":
        from onetrace_console.demo_store import pump_maintenance
        pump_maintenance.main(run_dir, run_id, **spec.args)
    elif spec.pipeline == "p6":
        from onetrace_console.demo_store import fill_inspection
        fill_inspection.main(run_dir, run_id, **spec.args)
    elif spec.pipeline == "p7":
        from onetrace_console.demo_store import cold_chain
        cold_chain.main(run_dir, run_id, **spec.args)
    elif spec.pipeline == "p8":
        from onetrace_console.demo_store import invoice_match
        invoice_match.main(run_dir, run_id, issuer=issuer, **spec.args)
    elif spec.pipeline == "p10":
        from onetrace_console.demo_store import agent_settle
        agent_settle.main(run_dir.parent, run_id, spec.args["inner"], spec.args["amount"])
    elif spec.pipeline == "p11":
        return                  # recorded by its agent run, `p10`
    elif spec.pipeline == "p9":
        from onetrace_console.demo_store import torque_check
        torque_check.main(run_dir, run_id, **spec.args)
    else:
        raise ValueError(f"no pipeline {spec.pipeline!r}")


def _answers_file(run_dir: Path) -> Path:
    (found,) = sorted(run_dir.glob("artifacts/*-answer/answers.json"))
    return found


#: What the builder does to each run it breaks on purpose, one line each, beside the code that does
#: it (`_after`, the signing in `build`, and the fault arguments in `runs`). A public demo shows
#: each under "Then see what onetrace catches"; a test fails where a planted run has no line, or a
#: line names no planted run.
PLANTED = {
    "p1-14-candidate-set3-byte-changed": "One byte of a recorded answer changed after the run closed.",
    "p1-15-candidate-set4-file-deleted": "One recorded output file deleted after the run closed.",
    "p1-16-candidate-set5-no-artifacts": "Every recorded output file deleted after the run closed.",
    "p1-17-baseline-set2-unsigned": "Not signed.",
    "p1-18-baseline-set3-unsigned": "Not signed.",
    "p1-19-baseline-set4-untrusted-key": "Signed with a key the demo's trust file does not name.",
    "p1-20-candidate-set6-answer-failed": "Its answer stage made to fail, so the run's last attempt failed.",
    "p3-28-t-3-rules1-lookup-retried": "Its account lookup made to fail once, then run again.",
    "p7-41-cold-chain-decision-tampered": "One byte of its recorded release decision changed after "
                                          "the run closed.",
    "p8-49-invoice-paid-on-deny": "Its gated step paid on a decision that denied it.",
    "p8-50-invoice-permit-other-amount": "Its gated step carried a permit for another amount than the "
                                         "payment it recorded.",
}


def planted(spec: RunSpec) -> bool:
    """Whether the builder breaks the run on purpose: acts on it after it closed, signs it
    otherwise than with the trusted key, or makes one of its stages fail."""
    return (bool(spec.after) or spec.sign != "trusted" or bool(spec.args.get("fault"))
            or bool(spec.args.get("plant")))


def about_signing(spec: RunSpec) -> bool:
    """Whether what the builder does to the run is about signing: it signs it otherwise than with
    the trusted key (`RunSpec.sign`, the field `build` signs by)."""
    return spec.sign != "trusted"


def _after(spec: RunSpec, run_dir: Path) -> None:
    """The one action, after the run closed (and was signed), that gives the run its state."""
    if spec.after == "tamper":
        path = _answers_file(run_dir)
        data = bytearray(path.read_bytes())
        i = max(j for j, b in enumerate(data) if chr(b).isalpha())
        data[i] = ord(chr(data[i]).swapcase())            # one byte of a recorded output
        path.write_bytes(bytes(data))
    elif spec.after == "delete-one":
        _answers_file(run_dir).unlink()                    # one recorded output file
    elif spec.after == "no-artifacts":
        shutil.rmtree(run_dir / "artifacts")               # every recorded output file
    elif spec.after == "tamper-decision":
        (path,) = sorted(run_dir.glob("artifacts/*-release/decision.json"))
        path.write_bytes(path.read_bytes().replace(b"release", b"Release", 1))   # one byte
    elif spec.after:
        raise ValueError(f"no action {spec.after!r}")


def traceparent_for(folder: str) -> str:
    """A run's W3C traceparent, made from its folder's name: the same on every build."""
    h = hashlib.sha256(("onetrace-console demo span: " + folder).encode("utf-8")).hexdigest()
    return f"00-{h[:32]}-{h[32:48]}-01"


def write_traces(runs: Path, folders) -> None:
    """Each run's OpenTelemetry trace, as onetrace exports it (`onetrace export otel`), under
    `traces/<run folder>.json` beside the runs: what the trace panel shows on the public demo. A
    run the export refuses has no file, and the panel says so."""
    import subprocess
    import sys
    from onetrace_console.child import utf8_env
    out = runs / "traces"
    out.mkdir(parents=True, exist_ok=True)
    for name in folders:
        if not (runs / name / "MANIFEST.json").is_file():
            continue
        subprocess.run([sys.executable, "-m", "onetrace", "export", "otel", name, "--out",
                        str(Path("traces") / f"{name}.json")], cwd=runs, capture_output=True, timeout=120,
                       env=utf8_env())


def build(folder: Path) -> list[RunSpec]:
    """Record, sign and act on every run into `folder`/runs, and write the trust file and the
    build record. `folder` must be new or empty."""
    folder = Path(folder)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise FileExistsError(f"{folder} is not a new, empty folder")
    specs = runs()
    #: onetrace 0.5: the build's onedoor issuer (P8's gated step), and a span per run.
    from onetrace_console.demo_store.onedoor_demo import Issuer
    issuer = Issuer()
    before = os.environ.get("TRACEPARENT")
    try:
        for spec in specs:
            run_dir = folder / RUNS_DIRNAME / spec.folder
            #: Every run recorded inside a span of its own: a W3C traceparent made from its folder,
            #: the same on every build.
            os.environ["TRACEPARENT"] = traceparent_for(spec.folder)
            _record(spec, run_dir, issuer)
            if spec.sign:
                keys.sign(run_dir, keys.TRUSTED_SEED if spec.sign == "trusted" else keys.UNTRUSTED_SEED)
            _after(spec, run_dir)
    finally:
        if before is None:
            os.environ.pop("TRACEPARENT", None)
        else:
            os.environ["TRACEPARENT"] = before
    issuer.write_beside(folder / RUNS_DIRNAME)
    write_traces(folder / RUNS_DIRNAME, [s.folder for s in specs])
    (folder / TRUST_NAME).write_bytes(keys.trust_file_bytes())
    write_build_record(folder, (RUNS_DIRNAME, TRUST_NAME))
    return specs


def build_from(folder: Path, earlier: Path) -> None:
    """An earlier build's runs and trust file into `folder`, byte for byte, with a build record over
    them, as `build` writes one: only where the earlier build's record vouches for every byte of
    `runs/` and `trust.json`. The record's entries for anything else (a built store) are not read,
    and no store is needed: an earlier build's runs/, trust.json and BUILD_RECORD.json are
    enough. A builder explains one build's runs; a later build from them keeps those explanations."""
    folder, earlier = Path(folder), Path(earlier)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise FileExistsError(f"{folder} is not a new, empty folder")
    problems = check_build_record(earlier, only=(RUNS_DIRNAME, TRUST_NAME))
    if problems:
        raise ValueError(f"{earlier} is not the demo as its builder made it: {'; '.join(problems[:5])}"
                         f"{' and more' if len(problems) > 5 else ''}")
    for p in (earlier / RUNS_DIRNAME).rglob("*"):
        if p.is_symlink():
            raise ValueError(f"{earlier} holds a link, {p.relative_to(earlier)}; a build copies files only")
    shutil.copytree(earlier / RUNS_DIRNAME, folder / RUNS_DIRNAME)
    shutil.copyfile(earlier / TRUST_NAME, folder / TRUST_NAME)
    #: P10's pair recorded once more beside the kept one, signed as every demo run is: the kept trust
    #: file is this builder's own (`keys.trust_file_bytes`).
    if not any((folder / RUNS_DIRNAME / s.folder).exists() for s in RECORDED_BESIDE_KEPT):
        if (folder / TRUST_NAME).read_bytes() != keys.trust_file_bytes():
            raise ValueError(f"{earlier}'s trust file is not this builder's; its runs cannot be recorded beside")
        before = os.environ.get("TRACEPARENT")
        try:
            for spec in RECORDED_BESIDE_KEPT:
                run_dir = folder / RUNS_DIRNAME / spec.folder
                os.environ["TRACEPARENT"] = traceparent_for(spec.folder)
                _record(spec, run_dir)
                keys.sign(run_dir, keys.TRUSTED_SEED)
        finally:
            if before is None:
                os.environ.pop("TRACEPARENT", None)
            else:
                os.environ["TRACEPARENT"] = before
        write_traces(folder / RUNS_DIRNAME, [s.folder for s in RECORDED_BESIDE_KEPT])
    write_build_record(folder, (RUNS_DIRNAME, TRUST_NAME))


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _covered(folder: Path, covers) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in covers:
        top = folder / root
        paths = [top] if top.is_file() else sorted(p for p in top.rglob("*") if p.is_file())
        for p in paths:
            found[p.relative_to(folder).as_posix()] = p
    return found


#: Under a build's store, what is not the build's: the comparisons visitors made on a public
#: console (`visitor_compare`), kept beside the built store and never vouched for by its record.
NOT_BUILT = "store/compared/"


def write_build_record(folder: Path, covers) -> None:
    """The sha256 of every file under `covers` (paths in `folder`), as `BUILD_RECORD.json`."""
    files = {rel: _digest(p) for rel, p in _covered(folder, covers).items()}
    record = {"format": BUILD_FORMAT, "covers": sorted(covers), "files": files}
    (folder / BUILD_RECORD).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8")


def check_build_record(folder: Path, only: tuple[str, ...] | None = None) -> list[str]:
    """What in `folder` the build record does not vouch for: every file changed, added or removed
    since the builder wrote it, in words. Empty when every byte is the builder's. `only`: read the
    record's entries under these paths alone (`build_from`'s runs/ and trust.json), each required
    present and equal and nothing added under them; entries for any other path are not read, and
    need not be there."""
    folder = Path(folder)
    path = folder / BUILD_RECORD
    from onetrace_console.bounded_json import load_json_bounded
    try:
        record = load_json_bounded(path.read_text(encoding="utf-8"), BUILD_RECORD)
        covers, files = record["covers"], record["files"]
        if record.get("format") != BUILD_FORMAT or not isinstance(files, dict) \
                or not isinstance(covers, list):
            raise ValueError
    except FileNotFoundError:
        return [f"{BUILD_RECORD} is missing, so nothing in {folder} is vouched for"]
    except (OSError, ValueError, KeyError, TypeError):
        return [f"{BUILD_RECORD} is not a build record this console reads"]
    if only is not None:
        missing = [root for root in only if root not in covers]
        if missing:
            return [f"{BUILD_RECORD} does not cover {', '.join(missing)}"]
        covers = list(only)
        files = {rel: d for rel, d in files.items()
                 if any(rel == root or rel.startswith(root + "/") for root in only)}
    have = {rel: p for rel, p in _covered(folder, covers).items() if not rel.startswith(NOT_BUILT)}
    problems = [f"{rel} was removed" for rel in sorted(set(files) - set(have))]
    problems += [f"{rel} was added" for rel in sorted(set(have) - set(files))]
    problems += [f"{rel} was changed" for rel in sorted(set(files) & set(have))
                 if _digest(have[rel]) != files[rel]]
    return problems


def deliver(folder: Path, store, config):
    """Deliver and check every run in `folder`/runs through the console's own path, then store
    the demo's comparisons. Returns the load, its comparison the first of them."""
    from dataclasses import replace

    from onetrace_console.folder_load import _compare, load_folder
    loaded = load_folder(Path(folder) / RUNS_DIRNAME, store, config)
    first, note = None, ""
    #: The comparisons whose two runs are there: a build from an earlier build's runs
    #: (`--runs-from`) holds that build's pipelines only.
    names = {r.name for r in loaded.runs}
    for i, pair in enumerate(p for p in COMPARISONS + COMPARISONS_BESIDE_KEPT if set(p) <= names):
        comparison, why = _compare(list(loaded.runs), pair, store)
        if i == 0:
            first, note = comparison, why
    return replace(loaded, comparison=first, compare_note=note)
