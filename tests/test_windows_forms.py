"""What Windows wrote differently, held on every platform.

1. The decision export, its sidecar and the issuer's file are written as bytes, LF everywhere: on
   Windows a text-mode write gave the export CRLF while its sidecar's digest was over LF, and the
   verifier read every gated run's export as damaged ("the decision is in the export" FAIL), so
   every P8 run read "Contradicts its record". Held with Windows text mode emulated here; and the
   verifier's own reading of a CRLF export, planted, is shown to be that FAIL.
2. A path the stored command names relative to the run's folder is written with `/` on every
   platform; Windows gave `..\\evidence\\trust.json`. Held with Windows' separator emulated.
3. An incident page never prints the decisions extension's name, except in onetrace's two format
   names: the verifier's fix line for the export row names it, and is kept in the report instead.
   Held on the incident page of a gated run planted to contradict its record.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

P8 = "p8-42-invoice-tolerance-2pct"
EXPORT_ROW = "decisions: the decision is in the export"


def _windows_text(monkeypatch):
    """Path.write_text as Windows text mode writes it: each "\\n" as "\\r\\n"."""
    real = Path.write_text

    def write_text(self, data, encoding=None, errors=None, newline=None):
        return real(self, data, encoding=encoding, errors=errors, newline="\r\n" if newline is None else newline)
    monkeypatch.setattr(Path, "write_text", write_text)


def beside_problems(runs: Path) -> list[str]:
    """The three files as the verifier reads them: LF only, and the sidecar's digest the export's."""
    out = [f"{name} holds a CR" for name in ("decisions.jsonl", "decisions.jsonl.sha256", "permit-issuers.json")
           if b"\r" in (runs / name).read_bytes()]
    said = (runs / "decisions.jsonl.sha256").read_bytes().split()[0].decode("ascii")
    if said != hashlib.sha256((runs / "decisions.jsonl").read_bytes()).hexdigest():
        out.append("the sidecar's digest is not the export's")
    return out


def test_the_decision_files_are_lf_on_every_platform(tmp_path, monkeypatch, examined):
    from onetrace_console.demo_store.onedoor_demo import Issuer
    _windows_text(monkeypatch)
    issuer = Issuer()
    issuer.decide("req-1", "permit")
    issuer.decide("req-2", "deny")
    issuer.write_beside(tmp_path)
    examined(3, "files written with Windows text mode emulated")
    assert beside_problems(tmp_path) == []


def test_sabotage_an_export_written_in_text_mode_is_named(tmp_path, examined):
    (tmp_path / "decisions.jsonl").write_bytes(b'{"a":1}\r\n')
    (tmp_path / "decisions.jsonl.sha256").write_bytes(
        (hashlib.sha256(b'{"a":1}\n').hexdigest() + "  decisions.jsonl\n").encode())
    (tmp_path / "permit-issuers.json").write_bytes(b"{}\n")
    examined(1, "planted export")
    assert beside_problems(tmp_path) == ["decisions.jsonl holds a CR", "the sidecar's digest is not the export's"]


def _verify_rows(run: Path, beside: Path) -> dict[str, str]:
    proc = subprocess.run([sys.executable, "-m", "onetrace_verify.cli", "--json", "--decisions",
                           str(beside / "decisions.jsonl"), "--permit-issuers", str(beside / "permit-issuers.json"),
                           "MANIFEST.json"], cwd=run, capture_output=True, text=True, timeout=120)
    return {r["name"]: r["result"] for r in json.loads(proc.stdout)["rows"] if r["name"].startswith("decisions:")}


@pytest.fixture(scope="module")
def planted(shared_demo, tmp_path_factory):
    """One gated run of the demo with its export as Windows wrote it in text mode, the sidecar's
    digest over LF: what every P8 run's check read on Windows."""
    src = shared_demo["folder"] / "runs"
    root = tmp_path_factory.mktemp("crlf-export")
    runs = root / "runs"
    runs.mkdir()
    shutil.copytree(src / P8, runs / P8)
    for name in ("decisions.jsonl.sha256", "permit-issuers.json"):
        shutil.copyfile(src / name, runs / name)
    (runs / "decisions.jsonl").write_bytes((src / "decisions.jsonl").read_bytes().replace(b"\n", b"\r\n"))
    shutil.copyfile(shared_demo["folder"] / "trust.json", root / "trust.json")
    return src, root


def test_the_verifier_reads_an_export_written_in_text_mode_as_damaged(planted, examined):
    src, root = planted
    examined(2, "checks of one gated run, its export as built and as Windows wrote it")
    assert _verify_rows(src / P8, src)[EXPORT_ROW] == "PASS"
    assert _verify_rows(root / "runs" / P8, root / "runs")[EXPORT_ROW] == "FAIL"


def test_a_relative_path_in_the_stored_command_is_written_with_slashes(tmp_path, monkeypatch, examined):
    import ntpath
    from onetrace_console.checks import _relative_to
    run_dir = tmp_path / "check" / "run"
    trust = tmp_path / "check" / "evidence" / "trust.json"
    #: Windows' separator, and its relpath, which writes it.
    monkeypatch.setattr(os, "sep", "\\")
    monkeypatch.setattr(os.path, "relpath", lambda p, start: ntpath.join("..", "evidence", "trust.json"))
    examined(1, "path named as on Windows")
    assert str(_relative_to(trust, run_dir)) == "../evidence/trust.json"


@pytest.fixture(scope="module")
def incident_pages(planted):
    """The planted run loaded by the console's own folder load and drawn as a public console draws
    it: its incident page is the one Windows drew for every P8 run."""
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    _src, root = planted
    store_root = root / "store"
    config = Config(public=True, store_root=str(store_root), trust_file=str(root / "trust.json"),
                    sign_in={**Config().sign_in, "enabled": False})
    store = Store(store_root / "store")
    with store.reading():
        load_folder(root / "runs", store, config)
        _render_startup_pages(store, store_root, config)
    pages = store_root / "pages"
    return {p.relative_to(pages).as_posix(): p.read_text(encoding="utf-8")
            for p in pages.glob("incidents/i-contradicts-*.html")}


def word_problems(pages: dict[str, str]) -> list[str]:
    from tests.test_ux_screens import NOT_ON_A_PAGE, _text
    return [f"{rel}: {name}" for rel, page in pages.items() for name, rx in NOT_ON_A_PAGE.items()
            if rx.search(_text(page))]


def test_a_contradicting_gated_run_s_incident_page_holds_the_word_rule(incident_pages, examined):
    from onetrace_console.incident_pages import FIX_KEPT
    examined(len(incident_pages), "incident pages")
    assert incident_pages, "the planted run raised no incident"
    page = next(iter(incident_pages.values()))
    assert EXPORT_ROW in html.unescape(page) and "onedoor-decision-ref/1" in html.unescape(page)
    assert f"fix ({EXPORT_ROW}): {FIX_KEPT};" in html.unescape(page)
    assert word_problems(incident_pages) == []


def test_sabotage_the_verifier_s_fix_line_shown_whole_is_named(incident_pages, examined):
    rel, page = next(iter(incident_pages.items()))
    planted = page.replace("</main>", "<p>fix (decisions: the decision is in the export): pass the onedoor "
                                      "decision export as --decisions</p></main>", 1)
    examined(1, "planted page")
    assert word_problems({rel: planted}) == [f"{rel}: onedoor"]
