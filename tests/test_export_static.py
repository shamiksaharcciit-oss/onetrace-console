"""The command `onetrace-console export-static`: the pages the local console serves for the
listed runs, as static files.

Its four checks, each a test here, against the current demo runs (nothing is exported for
hosting -- that export is made later, from the 0.2.0 demo runs):

1. **Byte-equal to the served pages,** apart from the link rewrite and the banner. Read from a real
   console over HTTP, serving the same store with only the listed runs. A sealed page is sealed
   again after the rewrite and the banner, so the check it prints for its reader still says
   "matches"; with both fingerprints zeroed, the pages are equal.
2. **No stray run:** a planted third run, and its comparison, appear in no file name and no file.
3. **The scans at 0:** the process-id scan over the exported folder; and the fence scan's
   mechanism, shown to fire on a planted test term (the real terms never come to this
   machine).
4. **No external requests:** no link, source or stylesheet URL to another host.
"""
from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request
from pathlib import Path

import pytest

from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_stage_pages import DEMO, _stored

NOW = "2026-10-04T12:00:00+00:00"
BANNER = ("Demo: two runs of a sample pipeline, signed and anchored with test keys. Install "
          "onetrace to record your own.")
STRAY = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / \
    "dag-r37" / "run_P"
_SLOT = re.compile(r"<!--fingerprint-->[0-9a-f]{64}<!--/fingerprint-->")
_ATTR = re.compile(r'\b(href|src)="([^"]*)"')


@pytest.fixture
def source(tmp_path, monkeypatch):
    """A console's data folder holding the demo's two runs, compared, and a stray third run
    compared with day 1 -- the run the export must leave out."""
    _require_installed()
    from onetrace_console import serve
    from onetrace_console.compare import compare
    from onetrace_console.store import Store
    from tests.test_compare import _deliver
    monkeypatch.setattr(serve, "_now", lambda: NOW)
    root = tmp_path / "source"
    store = Store(root / "store")
    a, b = _stored(DEMO / "day-1", store), _stored(DEMO / "day-2", store)
    compare(a, b, store, ran_at=FIXED_RAN_AT)
    from onetrace_console.checks import run_and_record
    stray = run_and_record(_deliver(STRAY, store), store, ran_at=FIXED_RAN_AT)
    stray_cmp = compare(a, stray, store, ran_at=FIXED_RAN_AT)
    return root, store, (a, b), stray, stray_cmp


@pytest.fixture
def exported(source, tmp_path):
    from onetrace_console.export_static import export
    root, store, (a, b), stray, stray_cmp = source
    out = tmp_path / "out"
    files = export(root, [a.key, b.key], out)
    return out, files, source


def _served(source, tmp_path) -> dict[str, bytes]:
    """Every page a real local console serves for a copy of the source holding only the two
    listed runs and their comparison -- the stray run's record and its comparison removed by
    hand, not by the export's own code -- fetched over HTTP."""
    from http.server import ThreadingHTTPServer

    from onetrace_console.access_log import AccessLog
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler, _local_config, _render_startup_pages
    from onetrace_console.store import Store
    root, _, (a, b), stray, stray_cmp = source
    served = tmp_path / "served"
    shutil.copytree(root, served)
    (served / "store" / "runs" / f"{stray.key}.json").unlink()
    (served / "store" / "comparisons" / f"{stray_cmp.key}.json").unlink()
    config = _local_config(Config())
    store = Store(served / "store")
    _render_startup_pages(store, served, config)
    Handler.store_root, Handler.store, Handler.config = served, store, config
    Handler.access_log = AccessLog(served / "access_log",
                                   max_segment_bytes=config.access_log_max_segment_bytes)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        rels = sorted(p.relative_to(served / "pages").as_posix()
                      for p in (served / "pages").rglob("*.html"))
        got = {rel: urllib.request.urlopen(f"{base}/{rel}").read() for rel in rels}
        got["static/console.css"] = urllib.request.urlopen(f"{base}/static/console.css").read()
        for key in (a.key, b.key):
            got[f"runs/{key}/record.tar"] = urllib.request.urlopen(
                f"{base}/runs/{key}/record.tar").read()
        return got
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _unbanner(page: str) -> str:
    banner = re.findall(r'<p data-export="banner"[^>]*>(.*?)</p>', page, re.S)
    assert banner == [BANNER], banner
    return re.sub(r'<p data-export="banner"[^>]*>.*?</p>', "", page, count=1, flags=re.S)


def _served_path(rel: str, value: str) -> str:
    """Where an exported relative link points, as the served page spelled it: from the site's
    root, the Overview as `/`."""
    target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), value))
    return "/" if target == "home.html" else "/" + target


# ------------------------------------------------------------------ 1. byte-equal to served

def test_every_exported_page_is_the_served_page_less_the_rewrite_and_the_banner(
        exported, tmp_path, examined):
    out, files, source = exported
    served = _served(source, tmp_path)
    assert {p for p in served if p.endswith(".html")} == {
        p for p in files if p.endswith(".html")}, "a page served and not exported, or the reverse"
    examined(len(served), "served files compared with their exported copies")
    for rel, want in served.items():
        got = (out / rel).read_bytes()
        if rel.endswith(".tar"):
            assert got == want, rel
            continue
        if rel.endswith(".css"):
            #: The stylesheet's only change: its fonts, from the site's root to beside it.
            assert got.decode() == want.decode().replace("url(/static/fonts/", "url(fonts/"), rel
            continue
        page = _unbanner(got.decode("utf-8"))
        served_page = want.decode("utf-8")
        exported_links = _ATTR.findall(page)
        served_links = _ATTR.findall(served_page)
        assert len(exported_links) == len(served_links), rel
        for (kind, mine), (_, theirs) in zip(exported_links, served_links):
            if theirs.startswith("/"):
                assert not mine.startswith("/") and _served_path(rel, mine) == theirs, (rel, mine,
                                                                                         theirs)
            else:
                assert mine == theirs, (rel, mine, theirs)
        restored = _ATTR.sub(lambda m, it=iter(served_links): f'{m.group(1)}="{next(it)[1]}"', page)
        assert _SLOT.sub("<!--fp-->", restored) == _SLOT.sub("<!--fp-->", served_page), rel


def test_the_fonts_are_the_shipped_files(exported):
    from onetrace_console.serve import STATIC_FILES
    out, files, _ = exported
    for path, source in STATIC_FILES.items():
        assert (out / path.lstrip("/")).read_bytes() == source.read_bytes(), path


def test_a_sealed_page_s_printed_check_still_matches_on_the_exported_copy(exported, examined):
    """The page prints a one-liner for its reader; run on the exported file, it says "matches"."""
    from onetrace_console.viewer.slot import STANDALONE_CHECK
    out, files, _ = exported
    sealed = [p for p in files if p.endswith(".html")
              and _SLOT.search((out / p).read_text(encoding="utf-8"))]
    assert len(sealed) >= 4, sealed
    examined(len(sealed), "sealed pages checked as a reader would")
    for rel in sealed:
        command = STANDALONE_CHECK.format(file="PAGE")
        code = re.search(r'-c "(.*)" PAGE$', command).group(1)
        done = subprocess.run([sys.executable, "-c", code, str(out / rel)],
                              capture_output=True, text=True, check=True)
        assert done.stdout.strip() == "matches", (rel, done.stdout)


def test_seals_txt_relates_each_sealed_page_s_exported_fingerprint_to_the_served_one(
        exported, tmp_path, examined):
    """The export writes SEALS.txt -- for each sealed page, one line: the page,
    the fingerprint the console serves it with, and the one it carries exported. Both read here
    from the pages themselves: the served one over HTTP, the exported one from the file."""
    out, files, source = exported
    served = _served(source, tmp_path)
    lines = (out / "SEALS.txt").read_text(encoding="utf-8").splitlines()
    header = [line for line in lines if line.startswith("#")]
    rows = [line.split() for line in lines if line and not line.startswith("#")]
    assert header, "SEALS.txt says what its columns are"
    sealed = sorted(p for p in files if p.endswith(".html")
                    and _SLOT.search((out / p).read_text(encoding="utf-8")))
    assert [r[0] for r in rows] == sealed
    examined(len(rows), "sealed pages related to their served fingerprints")
    fp = re.compile(r"<!--fingerprint-->([0-9a-f]{64})<!--/fingerprint-->")
    for page, served_fp, exported_fp in rows:
        assert served_fp == fp.search(served[page].decode("utf-8")).group(1), page
        assert exported_fp == fp.search((out / page).read_text(encoding="utf-8")).group(1), page
        assert served_fp != exported_fp, page


def test_every_page_carries_the_banner_once_in_the_work_order_s_words(exported, examined):
    out, files, _ = exported
    pages = [p for p in files if p.endswith(".html")]
    examined(len(pages), "pages read for the banner")
    for rel in pages:
        text = (out / rel).read_text(encoding="utf-8")
        assert re.findall(r'<p data-export="banner"[^>]*>(.*?)</p>', text, re.S) == [BANNER], rel


def test_no_link_is_absolute_and_every_relative_link_resolves_in_the_export(exported, examined):
    out, files, _ = exported
    count = 0
    known = set(files)
    for rel in (p for p in files if p.endswith(".html")):
        for _, value in _ATTR.findall((out / rel).read_text(encoding="utf-8")):
            count += 1
            assert not value.startswith("/"), (rel, value)
            if value.startswith("#"):
                continue
            path, _, anchor = value.partition("#")
            target = posixpath.normpath(posixpath.join(posixpath.dirname(rel), path))
            #: Every link resolves, served and exported: the two that were dead on the served
            #: pages too -- "the report it came from" and "all incidents" -- are fixed in the
            #: console, so nothing is excused here. A link to a place on another page
            #: (`case.html#graph`, a run's head on its other pages) resolves to that page, and the
            #: place is there.
            assert target in known, (rel, value)
            if anchor:
                assert f'id="{anchor}"' in (out / target).read_text(encoding="utf-8"), (rel, value)
    css = (out / "static" / "console.css").read_text(encoding="utf-8")
    for value in re.findall(r"url\(([^)]*)\)", css):
        count += 1
        assert posixpath.normpath(posixpath.join("static", value)) in known, value
    examined(count, "links read")


def test_the_file_list_names_every_file_with_its_hash(exported):
    out, files, _ = exported
    on_disk = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert sorted(files) == on_disk
    for rel, digest in files.items():
        assert digest == hashlib.sha256((out / rel).read_bytes()).hexdigest(), rel


# ------------------------------------------------------------------ 2. no stray run

def test_no_stray_run_appears_in_any_file_name_or_file(exported, examined):
    out, files, (root, store, (a, b), stray, stray_cmp) = exported
    examined(len(files), "exported files read for the stray run")
    for rel in files:
        assert stray.key not in rel and stray_cmp.key not in rel, rel
        data = (out / rel).read_bytes()
        for needle in (stray.key, stray.key[:12], stray_cmp.key, stray.chain_head):
            assert needle.encode() not in data, (rel, needle)
        if rel.endswith(".tar"):
            with tarfile.open(fileobj=io.BytesIO(data)) as tar:
                manifest = json.loads(tar.extractfile("MANIFEST.json").read())
            assert manifest["run_id"] != stray.run_id, rel
    assert any(a.key in rel for rel in files) and any(b.key in rel for rel in files)


def test_a_key_not_stored_or_named_twice_is_refused(source, tmp_path):
    from onetrace_console.export_static import ExportError, export
    root, store, (a, b), stray, _ = source
    with pytest.raises(ExportError, match="no stored run"):
        export(root, [a.key, "0" * 64], tmp_path / "o1")
    with pytest.raises(ExportError, match="twice"):
        export(root, [a.key, a.key], tmp_path / "o2")
    assert not (tmp_path / "o1").exists() and not (tmp_path / "o2").exists()


def test_an_existing_output_folder_is_never_written_into(source, tmp_path):
    from onetrace_console.export_static import ExportError, export
    root, store, (a, b), stray, _ = source
    out = tmp_path / "out"
    out.mkdir()
    (out / "keep.txt").write_text("mine")
    with pytest.raises(ExportError, match="already exists"):
        export(root, [a.key, b.key], out)
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


# ------------------------------------------------------------------ 3. the scans at 0

def test_the_process_id_scan_reads_0_over_the_export(exported, examined):
    from onetrace_console.export_static import internal_ids
    out, files, _ = exported
    examined(len(files), "exported files scanned for internal ids")
    assert internal_ids(out) == []


def test_the_process_id_scan_fires_on_a_planted_id(exported):
    from onetrace_console.export_static import internal_ids
    out, files, _ = exported
    page = out / "home.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</main>", "<p>see R-2099-01-01zz</p></main>"),
                    encoding="utf-8")
    assert [hit.split(":", 1)[0] for hit in internal_ids(out)] == ["home.html"]


def test_the_fence_scan_s_mechanism_fires_on_a_planted_test_term(exported, tmp_path):
    """The real terms never come to this machine; the mechanism is shown here with a test
    term, planted in one page, and the clean export reads 0 for it."""
    from onetrace_console.export_static import fence_hits
    out, files, _ = exported
    terms = tmp_path / "planted_terms.txt"
    terms.write_text("# a comment line is not a term\nzebra-quartz-planted\n", encoding="utf-8")
    assert fence_hits(out, terms) == []
    page = out / "home.html"
    page.write_text(page.read_text(encoding="utf-8").replace(
        "</main>", "<p>Zebra-Quartz-Planted</p></main>"), encoding="utf-8")
    assert [h.split(":", 1)[0] for h in fence_hits(out, terms)] == ["home.html"]


def test_an_export_its_own_scans_find_anything_in_is_refused_and_removed(source, tmp_path,
                                                                         monkeypatch):
    """The export scans its output before it returns: an internal id or an external request
    found, and the folder it made is removed and the export refused."""
    import onetrace_console.export_static as ex
    root, store, (a, b), stray, _ = source
    for planted in ("<span>WO-C99</span>", '<img src="https://example.org/x.png">'):
        monkeypatch.setattr(ex, "_BANNER_HTML", ex._BANNER_HTML.replace("</p>", planted + "</p>"))
        out = tmp_path / f"out-{len(planted)}"
        with pytest.raises(ex.ExportError, match="findings in the export"):
            ex.export(root, [a.key, b.key], out)
        assert not out.exists(), planted
        monkeypatch.undo()
        from onetrace_console import serve
        monkeypatch.setattr(serve, "_now", lambda: NOW)


# ------------------------------------------------------------------ 4. no external requests

def test_no_page_or_stylesheet_requests_another_host(exported, examined):
    from onetrace_console.export_static import external_requests
    out, files, _ = exported
    examined(len(files), "exported files scanned for external requests")
    assert external_requests(out) == []


@pytest.mark.parametrize("planted", [
    '<link rel="stylesheet" href="https://fonts.example/x.css">',
    '<script src="//cdn.example/x.js"></script>',
    '<img src="http://example.org/x.png">',
    "<style>@import url(https://example.org/x.css);</style>",
    '<img srcset="https://example.org/x.png 2x">',
])
def test_the_external_request_scan_fires_on_each_kind(exported, planted):
    from onetrace_console.export_static import external_requests
    out, files, _ = exported
    page = out / "home.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</main>", planted + "</main>"),
                    encoding="utf-8")
    assert [h.split(":", 1)[0] for h in external_requests(out)] == ["home.html"]


# ------------------------------------------------------------------ the command

def test_the_command_exports_and_prints_the_file_list(source, tmp_path, monkeypatch, capsys):
    from onetrace_console.__main__ import main
    root, store, (a, b), stray, _ = source
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"store_root": root.as_posix()}), encoding="utf-8")
    monkeypatch.setenv("ONETRACE_CONSOLE_CONFIG", str(config))
    out = tmp_path / "cmd_out"
    assert main(["export-static", "--runs", a.key, b.key, "--out", str(out)]) == 0
    printed = capsys.readouterr().out.splitlines()
    listed = dict(reversed(line.split("  ", 1)) for line in printed if "  " in line)
    assert listed and set(listed) == {p.relative_to(out).as_posix()
                                      for p in out.rglob("*") if p.is_file()}
    assert any(line.startswith("project ids: 0") for line in printed)
    assert any(line.startswith("external requests: 0") for line in printed)
