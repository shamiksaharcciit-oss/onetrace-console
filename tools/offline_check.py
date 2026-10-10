"""Open the console's pages in a real browser, offline, and count what they request.

WHY THIS IS NOT A GREP
----------------------
`tests/test_pages.py` already asserts that no page references a remote origin, and that is
cheap and runs everywhere. It is not the same claim. A page can reach the network in ways a
regex will not see, and this check has already got it wrong twice:

  - the first attempt classified hosts by NAME and reported `google.com`,
    `clients2.google.com` and `config.edge.skype.com` as page-originated when all three are
    the browser's own infrastructure. **Naming hosts is not a method.**
  - a void run where MSYS paths made both browsers load error pages, caught only because a
    32 KB file produced a 318 KB DOM.

So: DNS is blackholed, the net log is captured, and **the probe is the control**. The same
page is loaded twice -- once as rendered, once with one `<img src="https://control.invalid/…">`
injected -- and the control must show requests the clean page does not. A run where the
control shows zero proves the measurement was broken, not that the page is quiet.

Usage:
    python tools/offline_check.py [--browser chrome|edge|both]
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PROBE = '<img src="https://control.invalid/probe.png" alt="">'
PROBE_HOST = "control.invalid"

BROWSERS = {
    "chrome": [r"C:\Program Files\Google\Chrome\Application\chrome.exe",
               r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"],
    "edge": [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
             r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"],
}


def find_browser(name: str) -> Path | None:
    for candidate in BROWSERS[name]:
        if Path(candidate).is_file():
            return Path(candidate)
    return None


def render_pages(dest: Path) -> dict[str, Path]:
    """Ingest the pinned fixture run, check it, render all three pages to `dest`."""
    sys.path.insert(0, str(REPO / "src"))
    sys.path.insert(0, str(REPO / "tests"))
    import hashlib
    import io
    import tarfile

    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.pages import EXECUTIONS, render_execution, render_executions
    from onetrace_console.store import Store

    run_folder = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"
    if not run_folder.is_dir():
        raise SystemExit(f"the committed r11 fixture is not there: {run_folder}")

    manifest = json.loads((run_folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    files = {"MANIFEST.json": (run_folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        files[entry["file"]] = (run_folder / entry["file"]).read_bytes()
    files["SHA256SUMS"] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}" for p, b in files.items()) + "\n").encode()

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))

    store = Store(dest / "store")
    accepted = accept(buf.getvalue(), store)
    if accepted.run is None:                                  # pragma: no cover
        raise SystemExit(f"the fixture delivery was refused: {accepted.rows}")
    run = run_and_record(accepted.run, store)
    at = "2026-09-26T12:00:00+02:00"
    out: dict[str, Path] = {}
    execution = render_execution(run, store, generated_at=at)
    for name, html in execution.pages.items():
        (dest / name).write_bytes(html.encode("utf-8"))
        out[name] = dest / name
    listing = render_executions([run], store, generated_at=at)
    (dest / EXECUTIONS).write_bytes(listing.encode("utf-8"))
    out[EXECUTIONS] = dest / EXECUTIONS

    #: The console's pages. Home plus one Executions page per tally, and a Diff page over a real
    #: pair from the SDK's own bench -- run_C against run_C_poppler24, the same pipeline
    #: through two pdftotext versions.
    from onetrace_console.compare import compare
    from onetrace_console.render import DIFF_PAGE, render_all, render_diff

    for name, html in render_all(store, generated_at=at).items():
        (dest / name).write_bytes(html.encode("utf-8"))
        out[name] = dest / name
    #: `render_all` includes the Incidents page and one list per rule, so they
    #: are measured here without naming them one by one — a list that had to be kept in step
    #: by hand would fall out of step.

    exam = REPO / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
    pair = (exam / "run_C", exam / "run_C_poppler24")
    if all(p.is_dir() for p in pair):
        stored = []
        for folder in pair:
            manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
            files = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
            for entry in manifest["chain"]:
                files[entry["file"]] = (folder / entry["file"]).read_bytes()
            lines = [f"{hashlib.sha256(b).hexdigest()}  {p}" for p, b in files.items()]
            files["SHA256SUMS"] = ("\n".join(lines) + "\n").encode("utf-8")
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w") as tar:
                for path, blob in files.items():
                    info = tarfile.TarInfo(name=path)
                    info.size, info.mtime = len(blob), 0
                    tar.addfile(info, io.BytesIO(blob))
            accepted = accept(buf.getvalue(), store)
            if accepted.run is None:
                raise SystemExit(f"the diff pair was refused: {accepted.rows}")
            stored.append(accepted.run)
        comparison = compare(stored[0], stored[1], store)
        (dest / DIFF_PAGE).write_bytes(
            render_diff(comparison, store, generated_at=at).encode("utf-8"))
        out[DIFF_PAGE] = dest / DIFF_PAGE
    else:
        print(f"WARNING: the diff pair is not there, so diff.html was NOT measured: {pair}")
    return out


def load(browser: Path, page: Path, workdir: Path, tag: str) -> tuple[int, int]:
    """Load `page` offline with the net log captured. Returns (DOM bytes, probe requests).

    DNS is blackholed with `MAP * ~NOTFOUND`, so nothing can resolve even if something
    tries. The net log is then searched for the control host.
    """
    profile = workdir / f"profile-{tag}"
    netlog = workdir / f"netlog-{tag}.json"
    dump = workdir / f"dom-{tag}.html"
    for p in (profile, netlog, dump):
        shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    argv = [str(browser), "--headless=new", "--disable-gpu", "--no-first-run",
            f"--user-data-dir={profile}", f"--log-net-log={netlog}",
            '--host-resolver-rules=MAP * ~NOTFOUND', "--virtual-time-budget=4000",
            "--dump-dom", page.resolve().as_uri()]
    r = subprocess.run(argv, capture_output=True, timeout=180)
    dump.write_bytes(r.stdout)
    hits = 0
    if netlog.is_file():
        text = netlog.read_text(encoding="utf-8", errors="replace")
        hits = len(re.findall(re.escape(PROBE_HOST), text))
    return len(r.stdout), hits


def main(argv: list[str]) -> int:
    which = "both"
    if "--browser" in argv:
        which = argv[argv.index("--browser") + 1]
    names = ["chrome", "edge"] if which == "both" else [which]

    work = Path(tempfile.mkdtemp(prefix="offline-check-"))
    pages = render_pages(work / "pages")
    print(f"rendered: {', '.join(sorted(p.name for p in pages.values()))}")
    print(f"working directory: {work}")

    problems = 0
    for name in names:
        browser = find_browser(name)
        if browser is None:
            print(f"\n{name}: not installed where this can reach it -- NOT MEASURED")
            problems += 1
            continue
        version = subprocess.run([str(browser), "--version"], capture_output=True,
                                 text=True).stdout.strip()
        print(f"\n{name}: {browser}\n  {version or '(version unavailable headless)'}")
        print(f"  {'page':<18} {'clean DOM':>10} {'clean hits':>11} "
              f"{'control DOM':>12} {'control hits':>13}  verdict")
        for page_name, path in sorted(pages.items()):
            clean_bytes, clean_hits = load(browser, path, work, f"{name}-clean")

            probed = work / f"probed-{name}-{page_name}"
            html = path.read_bytes().decode("utf-8")
            assert "</body>" in html, page_name
            probed.write_bytes(html.replace("</body>", PROBE + "</body>").encode("utf-8"))
            ctrl_bytes, ctrl_hits = load(browser, probed, work, f"{name}-control")

            ok = clean_hits == 0 and ctrl_hits > 0
            verdict = "quiet, control fired" if ok else (
                "*** CONTROL DID NOT FIRE: the measurement is broken ***"
                if ctrl_hits == 0 else "*** THE PAGE REACHED OUT ***")
            if not ok:
                problems += 1
            print(f"  {page_name:<18} {clean_bytes:>10} {clean_hits:>11} "
                  f"{ctrl_bytes:>12} {ctrl_hits:>13}  {verdict}")

    print(f"\nproblems: {problems}")
    print("A control showing zero would mean the measurement was broken, not that the "
          "page was quiet.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
