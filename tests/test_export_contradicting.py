"""A static export of a store holding a run that contradicts its record.

The export refused such a store: the run's incident page links each fix line to the verifier's
published errors page, on another host, and the export's scan refuses any request to another host.
The export now carries the errors page the pinned SDK generates and links those lines to it, at the
same section; the scan is as strict as before, for everything else. Held with the demo's tampered
cold-chain run.
"""
from __future__ import annotations

import re
from html import unescape

from tests.test_compare_page import demo  # noqa: F401

TAMPERED = "p7-41-cold-chain-decision-tampered"
BASELINE = "p7-39-cold-chain-baseline"


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _export(demo, tmp_path):  # noqa: F811
    from onetrace_console.export_static import export
    folder, store = demo
    ids = {r.run_id: r.key for r in store.runs()}
    out = tmp_path / "export"
    written = export(folder / "store", [ids[TAMPERED], ids[BASELINE]], out)
    return out, written, ids


def test_a_store_with_a_tampered_run_exports(demo, tmp_path, examined):  # noqa: F811
    out, written, ids = _export(demo, tmp_path)
    page = (out / "runs" / ids[TAMPERED] / "case.html").read_text(encoding="utf-8")
    examined(1, "exported run page")
    assert "Contradicts its record" in _text(page)
    assert f"runs/{ids[TAMPERED]}/record.tar" in written


def test_its_fix_lines_link_the_export_s_own_errors_page(demo, tmp_path, examined):  # noqa: F811
    from onetrace_console.export_static import ERRORS_FILE, external_requests
    out, _written, _ids = _export(demo, tmp_path)
    links = [(p, m) for p in (out / "incidents").glob("*.html")
             for m in re.findall(r'href="([^"]*errors\.html#([^"]+))"', p.read_text(encoding="utf-8"))]
    examined(len(links), "errors-page links")
    assert links
    errors = (out / ERRORS_FILE).read_text(encoding="utf-8")
    for page, (href, code) in links:
        assert (page.parent / href.split("#")[0]).resolve() == (out / ERRORS_FILE).resolve(), href
        assert f'<section id="{code}">' in errors, code
    assert external_requests(out) == []


def test_sabotage_the_scan_still_refuses_another_host(demo, tmp_path, examined):  # noqa: F811
    from onetrace_console.export_static import external_requests
    out, _written, _ids = _export(demo, tmp_path)
    examined(1, "planted page")
    (out / "planted.html").write_text('<a href="https://example.org/x">x</a>', encoding="utf-8")
    assert external_requests(out) == ["planted.html: https://example.org/x"]
