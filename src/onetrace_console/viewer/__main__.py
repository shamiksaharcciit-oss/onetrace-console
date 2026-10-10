"""`python -m onetrace_console.viewer` — generate a run's two views, or check a page's fingerprint.

    generate   run the standalone check on a run folder, keep its report, write both views
    render     write both views from a report kept earlier (no check is run; the report is
               shown, and does not set "records agree")
    fingerprint  check that a page's printed fingerprint matches the page

Re-generating is the only way a page changes. Nothing is served, nothing polls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from onetrace_console.viewer import fingerprint
from onetrace_console.viewer.model import GENERATOR, build_model, list_row
from onetrace_console.viewer.page import render_answer, render_case, render_executions
from onetrace_console.viewer.record import RecordError, read_record
from onetrace_console.viewer.report import ReportUnreadable, capture, capture_cli, load
from onetrace_console.viewer.verbs import VerbReportUnreadable, read_report


def _verb_reports(paths: list[Path] | None) -> dict:
    """Read each `--verb` report and file it under the verb that wrote it.

    Two reports from the same verb is an error rather than a silent last-wins: the page would
    show one of them and nothing would say which.
    """
    reports: dict = {}
    for path in paths or []:
        report = read_report(path)
        if report.verb in reports:
            raise SystemExit(f"two reports from `{report.verb}`: {path} and an earlier one")
        reports[report.verb] = report
    return reports


def _write_views(run: Path, envelope: dict | None, out: Path, generated_at: str,
                 verbs: dict | None = None, *, own_check: bool) -> list[Path]:
    record = read_record(run)
    model = build_model(record, envelope, generated_at, verbs=verbs, own_check=own_check)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, render in (("answer.html", render_answer), ("case.html", render_case)):
        html = fingerprint.seal(render(model, name))
        path = out / name
        path.write_bytes(html.encode("utf-8"))
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m onetrace_console.viewer",
                                     description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="run the check, keep its report, write both views")
    g.add_argument("run", type=Path)
    how = g.add_mutually_exclusive_group(required=True)
    how.add_argument("--verifier", type=Path, help="a standalone verifier script, run as a file")
    #: The installed `onetrace-verify`, run as a module, with its --json rows,
    #: and its output files required where the run holds artifacts/.
    how.add_argument("--cli", action="store_true",
                     help="the installed onetrace-verify (run as python -m onetrace_verify.cli)")
    g.add_argument("--out", type=Path, required=True)
    g.add_argument("--verb", type=Path, action="append", metavar="REPORT",
                   help="a verb's report directory or json, repeatable (diff/localize/reproduce)")

    r = sub.add_parser("render", help="write both views from a kept report")
    r.add_argument("run", type=Path)
    r.add_argument("--report", type=Path, help="a check-report.json; omit to render with no check")
    r.add_argument("--out", type=Path, required=True)
    r.add_argument("--generated-at", help="ISO 8601 with zone; defaults to now")
    r.add_argument("--verb", type=Path, action="append", metavar="REPORT",
                   help="a verb's report directory or json, repeatable (diff/localize/reproduce)")

    e = sub.add_parser("executions", help="write the list page over the runs you name")
    e.add_argument("runs", type=Path, nargs="+")
    e.add_argument("--out", type=Path, required=True)
    e.add_argument("--generated-at", help="ISO 8601 with zone; defaults to now")

    f = sub.add_parser("fingerprint", help="check that each page's fingerprint matches it")
    f.add_argument("pages", type=Path, nargs="+")

    args = parser.parse_args(argv)
    now = datetime.now().astimezone().isoformat(timespec="seconds")

    if args.command == "fingerprint":
        worst = 0
        for page in args.pages:
            try:
                ok, why = fingerprint.check(page.read_bytes())
            except (OSError, UnicodeDecodeError, ValueError) as e:
                # A page that cannot be read is said, not raised (the third review, NEW-14).
                ok, why = False, f"cannot be read: {e}"
            print(f"{'matches' if ok else 'DOES NOT MATCH':15} {page}: {why}")
            worst = worst if ok else 1
        return worst

    try:
        if args.command == "executions":
            # The runs are the ones named on the command line. Nothing is discovered, no
            # directory is walked, no store is queried: C036 item 2's list is a list of what
            # it was given, which is what keeps it inside 019 §0's fence.
            #: A list's rows, not whole page models.
            models = [list_row(read_record(r)) for r in args.runs]
            args.out.mkdir(parents=True, exist_ok=True)
            # Where each run was read from, relative to where the page is written, so the link
            # resolves when the page is opened from disk. Generation-time metadata, per core's
            # ruling on addressing: the directory is how a run is addressed, and the run id —
            # which the SDK pair shares between two runs — is not.
            out_dir = args.out.resolve()
            hrefs = [os.path.relpath(r.resolve(), out_dir).replace(os.sep, "/")
                     for r in args.runs]
            page = fingerprint.seal(render_executions(
                models, args.generated_at or now, GENERATOR, hrefs=hrefs))
            path = args.out / "executions.html"
            path.write_bytes(page.encode("utf-8"))
            written = [path]
        elif args.command == "generate":
            envelope = (capture_cli(args.run, outputs=(args.run / "artifacts").is_dir())
                        if args.cli else capture(args.run, args.verifier))
            args.out.mkdir(parents=True, exist_ok=True)
            (args.out / "check-report.json").write_text(
                json.dumps(envelope, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                newline="\n")  # LF on every platform
            #: The check this command just ran itself: the one report that may set rung 1.
            written = _write_views(args.run, envelope, args.out, now, _verb_reports(args.verb),
                                   own_check=True)
        else:
            envelope = load(args.report) if args.report else None
            #: A kept or supplied report: shown as a report, never counted.
            written = _write_views(args.run, envelope, args.out, args.generated_at or now,
                                   _verb_reports(args.verb), own_check=False)
    except RecordError as e:
        print(f"cannot read the run: {e}", file=sys.stderr)
        return 2
    except VerbReportUnreadable as e:
        print(f"cannot read a verb's report: {e}", file=sys.stderr)
        return 2
    except ReportUnreadable as e:
        # Only `load` of a supplied `--report` raises it here: a report read but not believed
        # is rendered as unreadable, inside `build_model`.
        print(f"cannot read the check's report: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        # A folder or file the pages cannot be read from or written to (the third review,
        # NEW-14: `--out` naming a file printed a traceback).
        print(f"cannot read or write a file: {e}", file=sys.stderr)
        return 2
    for path in written:
        ok, why = fingerprint.check(path.read_bytes())
        print(f"wrote {path} ({path.stat().st_size} bytes); fingerprint {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
