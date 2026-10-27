"""The check's report: run the standalone check, keep its words, read them strictly.

    Every checkmark is a verification performed at generation time, labelled with when
    it ran, beside the one command that repeats it without us.   — the viewer's specification, §0

The standalone check (`verify.py` in the preview package) prints its findings and a
summary line. It prints no time, so this module runs it and records **when** it ran,
**what command** ran, and **its output byte for byte**. The page shows the output one click
down as the check's own words, and derives every checkmark from it.

READING IT STRICTLY
-------------------
The report is parsed against its exact line grammar, and anything unexpected makes the
report **unreadable** rather than quietly partial:

- a line that is not a finding, a blank, or the summary;
- a summary missing, repeated, or not last;
- counts in the summary that differ from the findings counted;
- an overall result that disagrees with the failures, or an exit status that disagrees
  with the overall result.

Unreadable is its own outcome, and the page says *could not be checked from here* — never
*checked and failed*. A report that cannot be read is an access problem, not evidence
about the record (the three-outcome rule).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from onetrace_console.bounded_json import TooDeep, load_json_bounded
from onetrace_console.viewer.depth import too_deep
from onetrace_console.child import utf8_env

REPORT_FORMAT = "onetrace-viewer/check-report/0.1"

#: Core's machine-readable report, as `verifier_call.Call.to_json` writes it. **This is
#: the viewer's primary input**, and its rows are read structurally.
#: That module's own docstring puts the discipline in one line -- *"the call is built
#: from the rows, never from the text"* -- and this is the same rule at the far end of
#: the wire.
VERIFIER_CALL_FORMAT = "onetrace-verifier-call/0.1"

#: Which input a report was read from. Carried ON the report rather than worked out
#: later, because the page has to be able to say which one it is showing, and a page
#: that cannot name its own source is the thing the fallback label exists to prevent.
SOURCE_ROWS = "verifier-call"
SOURCE_TEXT = "text-fallback"

#: Every key a verifier call carries. **Measured, not assumed**: across core's 21
#: delivered samples (`onetrace-report-samples-c325c94`, all 121 files matching its
#: `SHA256SUMS`) and one live `call_run` over a canary fixture, the key set is exactly
#: this, every time. All of them are required and nothing else is accepted.
#:
#: A field outside this set makes the report **unreadable**, which is the reader's
#: second check and F16's lesson moved to the input. F16 was a report carrying a
#: topology that the viewer read as a line: not a wrong answer from a wrong input, but
#: a confident answer from an input it had never been taught. An unknown field is that
#: input arriving again, and the only safe reading of it is to decline to read.
_CALL_KEYS = frozenset({
    "format", "kind", "target", "verifier_dir", "sums_file", "checked_sha256",
    "rows", "exit", "raised", "refused", "text_file", "notes",
})

#: A row's keys, and the closed verdict vocabulary. Note the spelling: this format says
#: `NOT-RUN`, while `sdk_verify.check_run`'s rows say `NOT RUN` and key the verdict as
#: `outcome` rather than `result`. Two spellings of one idea in one SDK is exactly the
#: place a reader starts being helpful, so this one is not: it accepts the vocabulary of
#: the format it declares it is reading, and refuses the other.
_ROW_KEYS = frozenset({"result", "name", "detail", "check"})
_ROW_RESULTS = {"PASS": "pass", "FAIL": "fail", "NOT-RUN": "not_run"}

#: `Call.kind`'s four values, from its own annotation. `refused` is a string here, not a
#: boolean -- ACJ canonical form keeps scalars as strings, and "false" is not falsey.
_CALL_KINDS = frozenset({"run", "receipt", "receipt-lines", "roots"})
_REFUSED = frozenset({"true", "false"})

_FINDING = re.compile(r"^\[(PASS   |FAIL   |NOT-RUN|SIGNED-UNTRUSTED)\] (.+?)(?: -- (.*))?$")
#: A row's tag and its outcome. SIGNED-UNTRUSTED (the third development build, 246ca51) is a
#: signature by a key not on the reader's trust list: never a pass, counted in none of the summary's
#: three counts, and accounted for by its own line after the summary.
_TAG_OUTCOME = {"PASS": "pass", "FAIL": "fail", "NOT-RUN": "not_run",
                "SIGNED-UNTRUSTED": "signed_untrusted"}
#: 0.1.2 also closes with `->  NOT VERIFIED (receipt format not implemented: N receipt(s))` and
#: exits 2 when a receipt names a format it does not implement.
_SUMMARY = re.compile(r"^(\d+) pass, (\d+) fail, (\d+) not-run  ->  "
                      r"(PASS|FAIL|NOT VERIFIED)(?: \(.*\))?$")
#: Each summary result and the one exit status that goes with it.
_RESULT_EXIT = {"pass": "0", "fail": "1", "not_verified": "2"}


def _lf(text: str) -> str:
    """The verifier's output with each \\r\\n written as \\n, where the console reads it (a page
    never carries \\r). Only \\r\\n, never a lone \\r: the verifier escapes
    every control character in a record's words one-to-one (onetrace_verify.escaping), so a \\r
    before a line feed in its output can only be the platform's line ending -- Windows writes \\r\\n
    to the pipe. The stored run record is not touched; this is the console's capture of the
    verifier's words."""
    return text.replace("\r\n", "\n")


#: The verifier's one-to-one escaping of the words it prints, so a text row can be
#: paired with its --json row, which carries the name raw. Its rule, as onetrace-verify 0.2.0.dev0 of
#: 246ca51 writes it (`onetrace_verify/escaping.py`, sha256 69ec6cfc55a2b6bc...; `verify._escaped`,
#: `verify.py` sha256 f0842dbfb0852253..., lines 47-58): a backslash doubled first, then each
#: character in these ranges, and any lone surrogate, as \\uXXXX (a surrogate pair beyond U+FFFF).
#: The console's suite holds the ranges and the rule equal to the installed verifier's.
VERIFIER_ESCAPED_RANGES = (
    (0x0000, 0x001F), (0x007F, 0x009F), (0x00AD, 0x00AD), (0x0600, 0x0605), (0x061C, 0x061C),
    (0x06DD, 0x06DD), (0x070F, 0x070F), (0x0890, 0x0891), (0x08E2, 0x08E2), (0x180E, 0x180E),
    (0x200B, 0x200F), (0x2028, 0x202E), (0x2060, 0x2064), (0x2066, 0x206F), (0xFEFF, 0xFEFF),
    (0xFFF9, 0xFFFB), (0x110BD, 0x110BD), (0x110CD, 0x110CD), (0x13430, 0x1343F), (0x1BCA0, 0x1BCA3),
    (0x1D173, 0x1D17A), (0xE0001, 0xE0001), (0xE0020, 0xE007F))
_VERIFIER_ESCAPED = re.compile("[" + "".join(re.escape(chr(a)) + ("-" + re.escape(chr(b)) if b > a else "")
                                             for a, b in VERIFIER_ESCAPED_RANGES + ((0xD800, 0xDFFF),))
                               + "]")


def _verifier_escape_char(ch: str) -> str:
    cp = ord(ch)
    if cp > 0xFFFF:
        cp -= 0x10000
        return f"\\u{0xD800 + (cp >> 10):04x}\\u{0xDC00 + (cp & 0x3FF):04x}"
    return f"\\u{cp:04x}"


def verifier_escaped(text: str) -> str:
    """`text` as the verifier prints it in a text row (`verify._escaped`)."""
    return _VERIFIER_ESCAPED.sub(lambda m: _verifier_escape_char(m.group()),
                                 str(text).replace("\\", "\\\\"))


class ReportUnreadable(ValueError):
    """The report exists but cannot be read as a report. Never treated as a failure."""


@dataclass(frozen=True, slots=True)
class Finding:
    outcome: str           # "pass" | "fail" | "not_run"
    subject: str           # the receipt file the finding is about, or "manifest"
    property: str          # what was checked, in the check's own words
    detail: str            # the check's reason, where it gave one
    line: str              # the finding's line, verbatim


@dataclass(frozen=True, slots=True)
class Report:
    ran_at: str            # ISO 8601 with zone, recorded when the check ran
    command: tuple[str, ...]   # the command a reader types to repeat the check
    cwd_note: str          # where to run it from: a key of LABELS ("where.<kind>")
    exit_status: str
    output: str            # the check's output, verbatim
    findings: tuple[Finding, ...]
    overall: str           # "pass" | "fail" | "not_verified", as the check's own summary states it
    source: str            # SOURCE_ROWS or SOURCE_TEXT
    #: False when the rows cannot be read one by one: `overall` still
    #: comes from the exit status and the summary line, `findings` is empty, and the output
    #: is shown whole, escaped.
    rows_readable: bool = True
    #: The result of the same check run again with the run's output files
    #: required (`--json --require-artifacts`), as (exit status, result) -- or None where it was
    #: not run (the run holds no `artifacts/`, or the report predates it).
    outputs_required: tuple[str, str] | None = None
    #: The same check run again with every required stage asked for (`--json
    #: --require-complete`), as (exit status, result, its `run complete` row as the check writes
    #: it) -- or None where it was not run (a run recorded before format 0.3, or a report that
    #: predates it). Format 0.3's optional stages are read from this row, never from the record.
    completeness_required: tuple[str, str, str] | None = None

    def count(self, outcome: str) -> int:
        return sum(1 for f in self.findings if f.outcome == outcome)


def capture(run_dir: Path, verifier: Path | None, manifest_name: str = "MANIFEST.json",
            timeout: int = 120, report: dict | None = None, *, module: str | None = None,
            shown_as: str | None = None, args: tuple[str, ...] = ()) -> dict:
    """Run the check on a run directory and return the report envelope (not yet parsed).

    Invoked through `sys.executable`, never the name `python3`. The command
    *recorded for the reader* is the portable form, because that is what they will type.

    With `module` the check is run as `python -m <module> <args>`, which a
    package using relative imports requires (`onetrace_verify.cli`), and recorded for the reader
    as `<shown_as> <args> <manifest>`: the installed command they type.
    """
    run_dir = Path(run_dir).resolve()
    ran_at = datetime.now().astimezone().isoformat(timespec="seconds")
    if module is not None:
        cmd = [sys.executable, "-m", module, *args, manifest_name]
    else:
        verifier = Path(verifier).resolve()
        cmd = [sys.executable, str(verifier), *args, manifest_name]
    try:
        p = subprocess.run(cmd, cwd=run_dir, capture_output=True, timeout=timeout, env=utf8_env())
    except subprocess.TimeoutExpired:
        # Recorded, not raised: a check that did not finish said nothing, and the report says
        # so (the second confirmation review, B2: raised, it left a stored run with no report,
        # and the console that stored it could not start again).
        p = None
    # The command is typed FROM the run's folder, so the verifier is named relative to it —
    # including upwards. The SDK's own layout keeps the verifier outside each run
    # (`runs/A/`, `verifier/verify.py`), and naming it `verify.py` told a reader to run a
    # file that is not there.
    where = "run_folder"
    if module is not None:
        command = [shown_as or module, *args, manifest_name]
    else:
        try:
            shown = Path(os.path.relpath(verifier, run_dir)).as_posix()
        except ValueError:                      # a different drive: no relative path exists
            shown = verifier.as_posix()          # absolute, so the command still works
        command = ["python3", shown, *args, manifest_name]
    envelope = {
        "format": REPORT_FORMAT,
        "ran_at": ran_at,
        "command": command,
        "cwd_note": where,
    }
    if p is None:
        envelope["exit_status"] = ""
        envelope["unfinished"] = (f"the check did not finish within {timeout} seconds, so it "
                                  f"said nothing about this record")
        return envelope
    envelope["exit_status"] = str(p.returncode)
    envelope["stderr"] = _lf(p.stderr.decode("utf-8", errors="replace"))
    if report is not None:
        # The machine-readable report, passed in rather than produced here: this
        # module runs the standalone check, and the SDK that writes the rows is not
        # a runtime dependency of the viewer. A caller that has the rows supplies
        # them; a caller that does not gets the labelled fallback.
        envelope["report"] = report
    try:
        envelope["stdout"] = _lf(p.stdout.decode("utf-8", errors="strict"))
    except UnicodeDecodeError as e:
        # Kept out of the envelope rather than repaired: `parse` then reports the missing
        # output as unreadable, which is what it is.
        envelope["stdout_undecodable"] = f"the check's output is not UTF-8: {e}"
    return envelope


def parse(envelope: dict) -> Report:
    """Read a report envelope strictly, from the rows where they are there.

    **The rows are the input; the text is the fallback**. Both paths
    produce the same `Report`, and the report says which one it came from so the page
    can too. Neither path guesses: `ReportUnreadable` is the answer to anything
    unexpected, and the page then says *could not be checked from here* rather than
    *checked and failed* (the three-outcome rule).

    The check's own words are required in both cases. The page shows them one layer
    down as received bytes -- 019 §0 -- so a report that carries rows but not the words
    is not a report this page can render, and reconstructing the words from the rows
    would put a generated artefact where the reader is told the check's own output is.
    """
    if not isinstance(envelope, dict):
        raise ReportUnreadable("the check's report is not a JSON object")
    if isinstance(envelope.get("unfinished"), str):
        raise ReportUnreadable(envelope["unfinished"])
    from onetrace_console.viewer.record import unshowable
    why = unshowable(envelope)
    if why is not None:
        raise ReportUnreadable(f"the check's report cannot be shown: {why}")
    if envelope.get("format") != REPORT_FORMAT:
        raise ReportUnreadable(f"not a check report this viewer knows: {envelope.get('format')!r}")
    for key in ("ran_at", "command", "cwd_note", "exit_status", "stdout"):
        if key not in envelope:
            raise ReportUnreadable(f"the report has no {key!r}")
    # Each in the one shape `capture` writes it (the second confirmation review, S3: a number
    # here broke the text reader or the command's tuple).
    for key in ("ran_at", "cwd_note", "exit_status", "stdout"):
        if not isinstance(envelope[key], str):
            raise ReportUnreadable(f"the report's {key!r} is not a string: {envelope[key]!r:.80}")
    if not (isinstance(envelope["command"], list)
            and all(isinstance(part, str) for part in envelope["command"])):
        raise ReportUnreadable("the report's command is not a list of strings")
    # "run_folder_verifier_elsewhere" is no longer produced: the command now always carries
    # a path that works from the run's folder. It stays accepted so reports captured before
    # that change still read, and its ruled label (023 §4) stays in the table for them.
    if envelope["cwd_note"] not in ("run_folder", "run_folder_verifier_elsewhere"):
        raise ReportUnreadable(f"the report names no known place to run from: {envelope['cwd_note']!r}")
    try:
        datetime.fromisoformat(envelope["ran_at"])
    except (TypeError, ValueError):
        raise ReportUnreadable(f"the report's time is not a timestamp: {envelope['ran_at']!r}") from None
    if datetime.fromisoformat(envelope["ran_at"]).tzinfo is None:
        raise ReportUnreadable("the report's time carries no zone")
    #: A report stored before capture wrote \r\n as \n reads as one stored since.
    envelope = dict(envelope, stdout=_lf(envelope["stdout"]))
    for part in ("rows_json", "outputs_required", "completeness_required"):
        if isinstance(envelope.get(part), dict) and isinstance(envelope[part].get("stdout"), str):
            envelope[part] = dict(envelope[part], stdout=_lf(envelope[part]["stdout"]))

    if "report" in envelope:
        return _from_rows(envelope["report"], envelope)

    # **The verdict is the exit status and the summary line**. The summary
    # is the output's last line: the verifier prints it last, and a line a record wrote into a
    # row comes before it. The exit status, which no record can write, must agree with it.
    lines = [line for line in envelope["stdout"].splitlines() if line.strip()]
    trailer = _trailer(lines)
    summary = _SUMMARY.match(lines[-1]) if lines else None
    if summary is None:
        raise ReportUnreadable("the report has no summary line")
    overall = summary.group(4).lower().replace(" ", "_")
    if envelope["exit_status"] != _RESULT_EXIT[overall]:
        raise ReportUnreadable(f"exit status {envelope['exit_status']} disagrees with the "
                               f"summary's result {overall!r}")
    n_pass, n_fail, n_not_run = (int(summary.group(i)) for i in (1, 2, 3))
    if (overall == "fail") != (n_fail > 0):
        raise ReportUnreadable(f"the summary's result {overall!r} disagrees with {n_fail} failure(s)")

    # **Then the rows, one by one.** Any that cannot be read -- a line that is no row, a row that
    # names no subject, a not-run without its reason, or rows that do not add up to the summary's
    # own counts -- mean a record's text has broken the rows apart. The verdict stands; no row is
    # trusted, and the output is shown whole, escaped.
    findings: list[Finding] = []
    readable = True
    for line in lines[:-1]:
        m = _FINDING.match(line)
        subject, sep, prop = m.group(2).partition(": ") if m else ("", "", "")
        if (not (m and sep) or (m.group(1) in ("NOT-RUN", "SIGNED-UNTRUSTED") and not m.group(3))
                or (m.group(1) == "SIGNED-UNTRUSTED" and not subject.startswith("signatures/"))):
            readable = False
            break
        findings.append(Finding(outcome=_TAG_OUTCOME[m.group(1).strip()],
                                subject=subject, property=prop, detail=m.group(3) or "",
                                line=line))
    counted = (sum(f.outcome == "pass" for f in findings),
               sum(f.outcome == "fail" for f in findings),
               sum(f.outcome == "not_run" for f in findings))
    if readable and counted != (n_pass, n_fail, n_not_run):
        readable = False

    required = None
    completeness = None
    if "rows_json" in envelope:
        #: The rows from the same check's `--json`, whose summary must agree
        #: with the text's -- exit status, result and counts -- or the report can't be read.
        doc, exit_json, result_json = _json_doc(envelope["rows_json"], "--json")
        json_rows = _json_findings(doc)
        counted_json = tuple(sum(f.outcome == o for f in json_rows) for o in ("pass", "fail", "not_run"))
        if (exit_json, result_json, counted_json) != (envelope["exit_status"], overall,
                                                      (n_pass, n_fail, n_not_run)):
            raise ReportUnreadable(
                f"the check's text and its --json disagree: text exit {envelope['exit_status']}, "
                f"{overall}, {n_pass}/{n_fail}/{n_not_run}; --json exit {exit_json}, {result_json}, "
                f"{'/'.join(map(str, counted_json))}")
        #: Each row keeps the check's own line, never one made up from the row: the text's finding
        #: lines, in order, paired with the --json rows, each pair the same status and name.
        text_lines = lines[:-1]
        if len(text_lines) != len(json_rows):
            raise ReportUnreadable(f"the check's text and its --json disagree: {len(text_lines)} "
                                   f"lines, {len(json_rows)} rows")
        paired = []
        for text_line, row in zip(text_lines, json_rows):
            m = _FINDING.match(text_line)
            status = _TAG_OUTCOME.get(m.group(1).strip()) if m else None
            #: The text row carries the name as the verifier escapes it, the --json
            #: row raw; never raw against raw, which split every row naming a backslash.
            if not m or status != row.outcome or m.group(2) != verifier_escaped(row.line):
                raise ReportUnreadable(f"the check's text and its --json disagree at "
                                       f"{text_line[:120]!r}")
            paired.append(Finding(outcome=row.outcome, subject=row.subject, property=row.property,
                                  detail=row.detail, line=text_line))
        findings, readable = paired, True
        if "outputs_required" in envelope:
            _doc, exit_req, result_req = _json_doc(envelope["outputs_required"],
                                                   "--json --require-artifacts")
            required = (exit_req, result_req)
        if "completeness_required" in envelope:
            doc_c, exit_c, result_c = _json_doc(envelope["completeness_required"],
                                                "--json --require-complete")
            said = [r for r in doc_c.get("rows") or [] if isinstance(r, dict) and r.get("name") == "run complete"
                    and isinstance(r.get("result"), str) and isinstance(r.get("detail"), str)]
            if len(said) != 1:
                raise ReportUnreadable("the --json --require-complete run has no one `run complete` row")
            completeness = (exit_c, result_c, _text_line(said[0]))

    _check_trailer(trailer, findings, readable)
    return Report(ran_at=envelope["ran_at"], command=tuple(envelope["command"]),
                  cwd_note=envelope["cwd_note"], exit_status=envelope["exit_status"],
                  output=envelope["stdout"], findings=tuple(findings) if readable else (),
                  overall=overall, source=SOURCE_TEXT, rows_readable=readable,
                  outputs_required=required, completeness_required=completeness)


def _text_line(row: dict) -> str:
    """The row as the check writes it. **Rendered from the row, never received.**

    The page shows each finding's line, so reading from rows has to produce the same
    bytes the text carried or the switch would be visible as a diff in the pages.
    `[PASS   ]`, `[FAIL   ]` and `[NOT-RUN]` are all seven characters wide, which is
    what the text grammar's own regex encodes. That this reconstruction is faithful is
    not asserted here -- it is measured, row against line, in the tests, because a
    claim of byte-identity made by the code that does the rendering is not a check.
    """
    line = f"[{row['result']:<7}] {row['name']}"
    return line + (f" -- {row['detail']}" if row["detail"] else "")


def _cli_run(run_dir: Path, module: str, shown_as: str, args: tuple[str, ...],
             manifest_name: str, timeout: int) -> dict:
    """One `--json` run of the CLI, kept as the reader would repeat it: command, exit, stdout."""
    try:
        p = subprocess.run([sys.executable, "-m", module, *args, manifest_name], cwd=run_dir,
                           capture_output=True, timeout=timeout, env=utf8_env())
    except subprocess.TimeoutExpired:
        return {"command": [shown_as, *args, manifest_name], "exit_status": "",
                "unfinished": f"did not finish within {timeout} seconds"}
    return {"command": [shown_as, *args, manifest_name], "exit_status": str(p.returncode),
            "stdout": _lf(p.stdout.decode("utf-8", errors="replace"))}


def capture_cli(run_dir: Path, *, outputs: bool, module: str = "onetrace_verify.cli",
                shown_as: str = "onetrace-verify", manifest_name: str = "MANIFEST.json",
                timeout: int = 120, trust: Path | None = None,
                tsa: tuple[Path, list[Path]] | None = None, complete: bool = False,
                extra: tuple[str, ...] = ()) -> dict:
    """The check as the installed CLI, three ways.

    1. `onetrace-verify MANIFEST.json`: the verdict and the check's own words (the envelope).
    2. `onetrace-verify --json MANIFEST.json`: its rows (`rows_json`), which the text can't carry
       for a row that names no subject (0.2.0's two graph rows). `parse` requires the two
       summaries to agree.
    3. Only where `outputs` (the run holds `artifacts/`): `onetrace-verify --json
       --require-artifacts MANIFEST.json` (`outputs_required`), the evidence for "Records agree".
       Without `artifacts/` it is not run: run with the flag, a run
       without output files FAILs, which is not a verdict about its records.
    4. Only where `complete` (a run recorded in format 0.3): `onetrace-verify --json
       --require-complete MANIFEST.json` (`completeness_required`), whose `run complete` row says
       whether only stages the run declares optional were left out. Its exit is never the verdict.

    `trust`: the reader's trust file of signing keys, passed to all three as
    `--trust <file>` and kept in each command as it was run; None runs them without it.
    `tsa`: the time-stamp authority's certificate and roots, passed to all three as
    `--tsa-cert <file>` and a `--tsa-root <file>` for each root; None runs them without.
    `extra`: more of the verifier's options naming files beside the run (onetrace-verify 0.5's
    `--decisions`, `--permit-issuers`, `--nested-run`), passed to every call as `trust` is.
    """
    run_dir = Path(run_dir).resolve()
    trusted = ("--trust", str(trust)) if trust is not None else ()
    if tsa is not None:
        cert, roots = tsa
        trusted += ("--tsa-cert", str(cert)) + tuple(a for r in roots for a in ("--tsa-root", str(r)))
    trusted += tuple(extra)
    envelope = capture(run_dir, None, manifest_name, timeout, module=module, shown_as=shown_as,
                       args=trusted)
    if envelope.get("unfinished"):
        return envelope
    envelope["rows_json"] = _cli_run(run_dir, module, shown_as, ("--json", *trusted),
                                     manifest_name, timeout)
    if outputs:
        envelope["outputs_required"] = _cli_run(run_dir, module, shown_as,
                                                ("--json", "--require-artifacts", *trusted),
                                                manifest_name, timeout)
    if complete:
        envelope["completeness_required"] = _cli_run(run_dir, module, shown_as,
                                                     ("--json", "--require-complete", *trusted),
                                                     manifest_name, timeout)
    return envelope


_JSON_RESULTS = {"PASS": "pass", "FAIL": "fail", "NOT VERIFIED": "not_verified"}
#: `--json`'s row results: the text's four tags (the CLI's rows, not the verifier-call format's).
_JSON_ROW_RESULTS = _TAG_OUTCOME

#: Widened at the third development build to cover signing: the only lines the
#: verifier writes after its summary, taken from its code at the pinned build -- onetrace-verify
#: 0.2.0.dev0 of `246ca51`, `onetrace_verify/cli.py` (sha256 ab2ae4864a8930fe...) lines 99-100
#: (ANCHOR_NON_CLAIM) and 361-369 (the order), `onetrace_verify/signatures.py` (sha256
#: 8d9141bc65293091...) lines 50-56 (NON_CLAIMS, UNTRUSTED_NOTE), and `onetrace_verify/beside.py`
#: (sha256 938ed164d2f1c1d6...) line 35 (NOT_RUN_NOTE). In that order, byte for byte, with only the
#: counts the code formats: the untrusted count where a row is SIGNED-UNTRUSTED, with that count; the
#: not-run count where a row beside the chain is NOT-RUN, with that count; the anchors' caveat where a
#: row's subject is under anchors/; what a signature does not show where one is under signatures/;
#: none without a row under anchors/ or signatures/. The console's suite holds these equal to the
#: installed verifier's own constants.
BESIDE_NOT_RUN_NOTE = "a record that is not run leaves the result as it would be without it"
ANCHOR_NON_CLAIM = ("anchors show this record existed by the time the source attests; not when the "
                    "run happened, that its outputs were correct, or who wrote it.")
_BESIDE_COUNT = re.compile(r"^records beside the chain: ([1-9][0-9]*) not run -- "
                           + re.escape(BESIDE_NOT_RUN_NOTE) + "$")
UNTRUSTED_NOTE = ("signed, and the signature is valid, but by a key not in your trust file: it shows "
                  "the record is unchanged since signing, not who signed it. It leaves the result as "
                  "it would be without it.")
SIGNATURE_NON_CLAIMS = ("that the key wasn't stolen or misused", "that the run's output is correct",
                        "when the record was signed (an anchor's job)",
                        "who the person behind the key is (the trust list connects a key to a name)")
_UNTRUSTED_COUNT = re.compile(r"^records beside the chain: ([1-9][0-9]*) signed by an untrusted key "
                              r"-- " + re.escape(UNTRUSTED_NOTE) + "$")
SIGNATURE_CAVEAT = "a signature does not show: " + "; ".join(SIGNATURE_NON_CLAIMS)
_BESIDE_SUBJECT = ("anchors/", "signatures/")


def _trailer(lines: list[str]) -> list[str]:
    """Take the lines the verifier writes after its summary off the end of `lines`, in place, and
    return them. Only those four lines, in that order; anything else stays where it is, and the
    summary check then refuses it."""
    trailer = []
    if lines and lines[-1] == SIGNATURE_CAVEAT:
        trailer.insert(0, lines.pop())
    if lines and lines[-1] == ANCHOR_NON_CLAIM:
        trailer.insert(0, lines.pop())
    if lines and _BESIDE_COUNT.match(lines[-1]):
        trailer.insert(0, lines.pop())
    if lines and _UNTRUSTED_COUNT.match(lines[-1]):
        trailer.insert(0, lines.pop())
    return trailer


def _check_trailer(trailer: list[str], findings: list, readable: bool) -> None:
    """The trailer the code writes for these rows, and nothing else."""
    if not trailer:
        expected_any = False
    else:
        expected_any = True
        if not readable:
            raise ReportUnreadable("lines follow the summary, and the rows they are about can't be "
                                   "read one by one")
    beside = [f for f in findings if f.subject.startswith(_BESIDE_SUBJECT)]
    untrusted = sum(f.outcome == "signed_untrusted" for f in beside)
    not_run = sum(f.outcome == "not_run" for f in beside)
    expected = ([f"records beside the chain: {untrusted} signed by an untrusted key -- "
                 f"{UNTRUSTED_NOTE}"] if untrusted else [])
    expected += ([f"records beside the chain: {not_run} not run -- {BESIDE_NOT_RUN_NOTE}"]
                 if not_run else [])
    expected += [ANCHOR_NON_CLAIM] if any(f.subject.startswith("anchors/") for f in beside) else []
    expected += ([SIGNATURE_CAVEAT] if any(f.subject.startswith("signatures/") for f in beside)
                 else [])
    if readable and trailer != expected:
        raise ReportUnreadable(f"the lines after the summary are not the verifier's own for these "
                               f"rows: {trailer!r:.200} (expected {expected!r:.200})")
    if expected_any and not beside:
        raise ReportUnreadable("lines follow the summary, and no row is a record beside the chain")
#: The installed check's command name, as a reader types it.
CLI_COMMAND = "onetrace-verify"


def _json_doc(part, what: str) -> tuple[dict, str, str]:
    """A `--json` run kept in the envelope: (its document, exit status, result), read strictly."""
    if not isinstance(part, dict):
        raise ReportUnreadable(f"the {what} run is not an object")
    if isinstance(part.get("unfinished"), str):
        raise ReportUnreadable(f"the {what} run {part['unfinished']}")
    if not (isinstance(part.get("stdout"), str) and isinstance(part.get("exit_status"), str)):
        raise ReportUnreadable(f"the {what} run has no output or no exit status")
    try:
        doc = load_json_bounded(part["stdout"], f"the {what} run's output")
    except TooDeep:
        raise ReportUnreadable(f"the {what} run's output is nested too deeply to read") from None
    except RecursionError:
        raise ReportUnreadable(f"the {what} run's output is nested too deeply to read") from None
    except ValueError as e:
        raise ReportUnreadable(f"the {what} run's output is not JSON: {e}") from None
    if not isinstance(doc, dict) or too_deep(doc):
        raise ReportUnreadable(f"the {what} run's output is not a report this viewer reads")
    summary = doc.get("summary")
    if not (isinstance(summary, dict) and summary.get("result") in _JSON_RESULTS):
        raise ReportUnreadable(f"the {what} run's summary is not one this viewer reads")
    result = _JSON_RESULTS[summary["result"]]
    if part["exit_status"] != _RESULT_EXIT[result] or str(summary.get("exit")) != part["exit_status"]:
        raise ReportUnreadable(f"the {what} run's exit status {part['exit_status']} disagrees with "
                               f"its summary's result {summary['result']!r}")
    return doc, part["exit_status"], result


def _json_findings(doc: dict) -> tuple[Finding, ...]:
    """`--json`'s rows as findings. A row's name is `<subject>: <property>`, or -- 0.2.0's two
    graph rows -- the property alone, with no subject."""
    rows = doc.get("rows")
    if not isinstance(rows, list):
        raise ReportUnreadable("the --json run's rows are not a list")
    out = []
    for row in rows:
        if not (isinstance(row, dict) and isinstance(row.get("name"), str)
                and row.get("result") in _JSON_ROW_RESULTS and isinstance(row.get("detail", ""), str)):
            raise ReportUnreadable(f"a --json row is not one this viewer reads: {row!r:.120}")
        subject, sep, prop = row["name"].partition(": ")
        if not sep:
            subject, prop = "", row["name"]
        out.append(Finding(outcome=_JSON_ROW_RESULTS[row["result"]], subject=subject, property=prop,
                           detail=row.get("detail", ""), line=row["name"]))
    return tuple(out)


def _from_rows(call: dict, envelope: dict) -> Report:
    """Read `onetrace-verifier-call/0.1` structurally. Refuses; never guesses."""
    if not isinstance(call, dict):
        raise ReportUnreadable(f"the machine-readable report is not an object: {type(call).__name__}")
    if call.get("format") != VERIFIER_CALL_FORMAT:
        raise ReportUnreadable(f"not a machine-readable report this viewer knows: "
                               f"{call.get('format')!r}")
    unknown = sorted(set(call) - _CALL_KEYS)
    if unknown:
        raise ReportUnreadable(f"the report carries fields this viewer has not been taught: "
                               f"{unknown}. An unknown field is a format change, and the "
                               f"viewer declines to read it rather than read past it")
    missing = sorted(_CALL_KEYS - set(call))
    if missing:
        raise ReportUnreadable(f"the report is missing fields this format carries: {missing}")
    # Each field this reader uses in the one shape `verifier_call.to_dict` writes it: strings,
    # and `raised` a string or null (the third confirmation review, NEW-7: a list was
    # unhashable here, and a number had no `.replace`).
    for key in ("kind", "refused", "exit"):
        if not isinstance(call[key], str):
            raise ReportUnreadable(f"the report's {key!r} is not a string: {call[key]!r:.80}")
    if not (call["raised"] is None or isinstance(call["raised"], str)):
        raise ReportUnreadable(f"the report's 'raised' is neither a string nor null: "
                               f"{call['raised']!r:.80}")
    if call["kind"] not in _CALL_KINDS:
        raise ReportUnreadable(f"the report names a kind of call this viewer does not know: "
                               f"{call['kind']!r}")
    if call["refused"] not in _REFUSED:
        raise ReportUnreadable(f"'refused' is not one of {sorted(_REFUSED)}: {call['refused']!r}")
    if call["raised"]:
        # The check did not finish. That is an access problem, not evidence about the
        # record, and it must not arrive at the page as a failed check.
        raise ReportUnreadable(f"the check raised and did not finish: {call['raised']!r}")
    if not isinstance(call["rows"], list):
        raise ReportUnreadable(f"'rows' is not a list: {type(call['rows']).__name__}")

    findings: list[Finding] = []
    for row in call["rows"]:
        if not isinstance(row, dict):
            raise ReportUnreadable(f"a row is not an object: {row!r}")
        stray = sorted(set(row) - _ROW_KEYS)
        if stray:
            raise ReportUnreadable(f"a row carries fields this viewer has not been taught: {stray}")
        absent = sorted(_ROW_KEYS - set(row))
        if absent:
            raise ReportUnreadable(f"a row is missing fields this format carries: {absent}")
        not_text = sorted(k for k in _ROW_KEYS if not isinstance(row[k], str))
        if not_text:
            raise ReportUnreadable(f"a row's {not_text} are not strings: {row!r:.120}")
        if row["result"] not in _ROW_RESULTS:
            raise ReportUnreadable(
                f"a row's verdict is not one this viewer knows: {row['result']!r}. This "
                f"format's verdicts are {sorted(_ROW_RESULTS)} -- note that "
                f"`sdk_verify.check_run` spells the third one 'NOT RUN', and a reader that "
                f"accepted both spellings would be guessing which format it was handed")
        subject, sep, prop = str(row["name"]).partition(": ")
        if not sep:
            raise ReportUnreadable(f"a row names no subject: {row['name']!r}")
        outcome = _ROW_RESULTS[row["result"]]
        if outcome == "not_run" and not row["detail"]:
            raise ReportUnreadable(f"a not-run row without its reason: {row['name']!r}")
        findings.append(Finding(outcome=outcome, subject=subject, property=prop,
                                detail=row["detail"], line=_text_line(row)))

    overall = "fail" if any(f.outcome == "fail" for f in findings) else "pass"
    #: `Call.refused`'s own definition, asserted rather than trusted: a roots call
    #: refuses on exit 1, any other kind refuses when a row failed. A report whose own
    #: fields disagree is unreadable, the same way the text path refuses a summary whose
    #: counts disagree with the findings it counted.
    expected = "true" if (call["exit"] == "1" if call["kind"] == "roots"
                          else overall == "fail") else "false"
    if call["refused"] != expected:
        raise ReportUnreadable(f"the report says refused={call['refused']!r} but its rows say "
                               f"{expected!r}")
    if (call["exit"] == "0") != (overall == "pass"):
        raise ReportUnreadable(f"the report's exit {call['exit']!r} disagrees with its rows, "
                               f"which are {overall}")
    if str(envelope["exit_status"]) != str(call["exit"]):
        raise ReportUnreadable(f"the run recorded exit {envelope['exit_status']!r} but the "
                               f"report carries exit {call['exit']!r}")

    return Report(ran_at=envelope["ran_at"], command=tuple(envelope["command"]),
                  cwd_note=envelope["cwd_note"], exit_status=envelope["exit_status"],
                  output=envelope["stdout"], findings=tuple(findings),
                  overall=overall, source=SOURCE_ROWS)


def load(path: Path) -> dict:
    """A check report kept earlier. `ReportUnreadable` for a file that cannot be read as one:
    missing, not UTF-8, not JSON, nested too deeply to read, or not an object."""
    try:
        data = load_json_bounded(Path(path).read_bytes().decode("utf-8"), str(path))
    except TooDeep:
        raise ReportUnreadable(f"{path} is nested too deeply to read") from None
    except OSError as e:
        raise ReportUnreadable(f"{path} cannot be read: {e.strerror or e}") from None
    except UnicodeDecodeError as e:
        raise ReportUnreadable(f"{path} is not UTF-8: {e}") from None
    except json.JSONDecodeError as e:
        raise ReportUnreadable(f"{path} is not readable JSON: {e}") from None
    except RecursionError:
        raise ReportUnreadable(f"{path} is nested too deeply to read") from None
    #: The viewer's own depth rule, the same on every interpreter (viewer/depth.py).
    if too_deep(data):
        raise ReportUnreadable(f"{path} is nested too deeply to read")
    if not isinstance(data, dict):
        raise ReportUnreadable(f"{path} is not a JSON object")
    return data
