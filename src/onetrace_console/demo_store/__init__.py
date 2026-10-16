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
  run asks for a window longer than the policy allows, and the policy stage declines it.

A run folder or trust file whose bytes the build record doesn't hold -- edited, added or removed
after the build -- is refused wherever the built folder is used again (`check_build_record`).
Its limit: it catches a change made after the build. A hand-made run fed into the builder is
prevented by the builder being the only thing that writes the demo, not by the record.

Anchoring is not part of the demo: every run reads "not anchored", as the SDK records it.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from onetrace_console.demo_store import keys

BUILD_RECORD = "BUILD_RECORD.json"
BUILD_FORMAT = "onetrace-console-demo-build/0.1"
TRUST_NAME = "trust.json"
RUNS_DIRNAME = "runs"


@dataclass(frozen=True)
class RunSpec:
    """One run of the demo: its folder (also its run id, unless `run_id` says otherwise), the
    pipeline and its arguments, the key that signs it, and the action taken after it closed."""
    folder: str
    pipeline: str
    args: dict = field(default_factory=dict)
    sign: str = "trusted"                   # "trusted", "untrusted" or "" (unsigned)
    after: str = ""                         # "", "tamper", "delete-one", "no-artifacts"
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
    """Every run of the demo, in delivery order: P1's first, then P2's, then P3's, then P4's, so
    the console's pipeline labels (first arrival) read P1, P2, P3, P4."""
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
    ]
    return out


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
]


def _record(spec: RunSpec, run_dir: Path) -> None:
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
    else:
        raise ValueError(f"no pipeline {spec.pipeline!r}")


def _answers_file(run_dir: Path) -> Path:
    (found,) = sorted(run_dir.glob("artifacts/*-answer/answers.json"))
    return found


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
    elif spec.after:
        raise ValueError(f"no action {spec.after!r}")


def build(folder: Path) -> list[RunSpec]:
    """Record, sign and act on every run into `folder`/runs, and write the trust file and the
    build record. `folder` must be new or empty."""
    folder = Path(folder)
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise FileExistsError(f"{folder} is not a new, empty folder")
    specs = runs()
    for spec in specs:
        run_dir = folder / RUNS_DIRNAME / spec.folder
        _record(spec, run_dir)
        if spec.sign:
            keys.sign(run_dir, keys.TRUSTED_SEED if spec.sign == "trusted" else keys.UNTRUSTED_SEED)
        _after(spec, run_dir)
    (folder / TRUST_NAME).write_bytes(keys.trust_file_bytes())
    write_build_record(folder, (RUNS_DIRNAME, TRUST_NAME))
    return specs


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


def write_build_record(folder: Path, covers) -> None:
    """The sha256 of every file under `covers` (paths in `folder`), as `BUILD_RECORD.json`."""
    files = {rel: _digest(p) for rel, p in _covered(folder, covers).items()}
    record = {"format": BUILD_FORMAT, "covers": sorted(covers), "files": files}
    (folder / BUILD_RECORD).write_text(json.dumps(record, indent=1, sort_keys=True) + "\n",
                                       encoding="utf-8")


def check_build_record(folder: Path) -> list[str]:
    """What in `folder` the build record does not vouch for: every file changed, added or removed
    since the builder wrote it, in words. Empty when every byte is the builder's."""
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
    have = _covered(folder, covers)
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
    for i, pair in enumerate(COMPARISONS):
        comparison, why = _compare(list(loaded.runs), pair, store)
        if i == 0:
            first, note = comparison, why
    return replace(loaded, comparison=first, compare_note=note)
