"""The follow-up's item 2 residue. A verifier row a page quotes is capped as a
record word is.

The limited review found the display caps partly closed: the verifier's own rows quote the
record's names -- `[FAIL] receipts/03-join.json: 'complete' is consistent with the stage lists --
declared but not emitting: ['000nnnn…` -- and the pages drew them whole, in the check lines, the
report block and the incident quotes. 100 declared names of 50,000 characters, a 19 KB upload,
wrote 24.9 MB of run pages and 10 MB of others. Each such row is now drawn as its first NAME_CAP
characters and the same marker; the whole row stays in the check report the run keeps.
"""
from __future__ import annotations

import io
import json
import tarfile

from onetrace_console.checks import run_and_record
from onetrace_console.ingest import accept
from onetrace_console.pages import render_execution
from onetrace_console.render import render_all
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_pages import GENERATED_AT
from tests.test_unreadable import _renamed, _resummed

LENGTH = 50_000
#: The same form as the run_id cap's test: a bound on the bytes each page writes. Before this fix
#: the case page was 24.9 MB less the others, and each incidents page 4.9 MB.
PAGE_BOUND = 400_000


def _long_names(files) -> bytes:
    """The reviewer's probe_longnames_all.py: 97 names of 50,000 characters added to every
    receipt's declared stages -- 100 declared -- as a gzip upload of about 19 KB."""
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    for entry in manifest["chain"]:
        receipt = json.loads(out[entry["file"]].decode("utf-8"))
        receipt["coverage"]["declared_stages"] = receipt["coverage"]["declared_stages"] + [
            f"{i:03d}" + "n" * LENGTH for i in range(97)]
        out[entry["file"]] = json.dumps(receipt, separators=(",", ":")).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, blob in _resummed(out).items():
            info = tarfile.TarInfo(name)
            info.size = len(blob)
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def test_the_reviewers_hundred_long_names_write_bounded_pages(files, store):
    _require_installed()
    body = _long_names(files)
    assert len(body) < 40_000
    run = run_and_record(accept(body, store).run, store, ran_at=FIXED_RAN_AT)
    report = json.loads(store.get(run.check_report).decode("utf-8"))
    assert "n" * LENGTH in report["stdout"], "the verifier's row quotes a name whole"
    pages = dict(render_execution(run, store, generated_at=GENERATED_AT).pages)
    pages.update(render_all(store, generated_at=GENERATED_AT))
    sizes = {name: len(page.encode("utf-8")) for name, page in pages.items()}
    over = {name: n for name, n in sizes.items() if n > PAGE_BOUND}
    assert not over, over
    #: Not a receipt's own bytes, which its raw layer shows as written under TEXT_CAP: the
    #: verifier's rows, wherever a page quotes them.
    rows = [line for page in pages.values() for line in page.split("\n") if "[FAIL" in line]
    assert rows, "the pages quote the verifier's failing rows"
    assert not [r for r in rows if "n" * 300 in r], "a verifier row drawn past the cap"


def test_the_whole_row_stays_in_the_check_report_the_run_keeps(files, store):
    _require_installed()
    run = run_and_record(accept(_long_names(files), store).run, store, ran_at=FIXED_RAN_AT)
    stdout = json.loads(store.get(run.check_report).decode("utf-8"))["stdout"]
    rows = [r for r in stdout.splitlines() if r.startswith("[FAIL") and "n" * LENGTH in r]
    assert rows, "the stored report keeps each row whole"
    from onetrace_console.viewer.sentences import template
    shown = render_execution(run, store, generated_at=GENERATED_AT).pages["case.html"]
    assert template("name.more").split(" (+")[0].strip() in shown
