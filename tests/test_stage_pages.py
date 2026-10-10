"""Board 4: a stage's inputs and outputs.

    Inputs: an upstream stage's stored output is shown as text only after its bytes match that
    stage's receipt, with a Verified badge. Each input from outside the run is shown by name, trust
    class and fingerprint, marked "fingerprint only"; its content is never shown. Outputs: this
    stage's stored outputs as text, each Verified. Binary: size and fingerprint, "not shown".
    Against a compared run, before 0.2.0: "same in ... / differs from ..." from the stored verdict.

An input's content is shown only when its digest equals an output recorded in an
upstream stage's receipt AND the stored bytes of that output match it; the label says what was
checked -- "matches the stored output of <stage>" -- never where it came from. In the console's
frame a graph node links to its sibling `stage-<n>.html`; the free file keeps `#step-N`.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import tarfile
from html import unescape
from pathlib import Path

import pytest

from onetrace_console.frame import rendering
from tests.test_checks import FIXED_RAN_AT, _require_installed

DEMO = Path(__file__).resolve().parent.parent / "examples" / "reference-demo" / "runs"
GENERATED_AT = "2026-10-04T12:00:00+00:00"


def _delivery(folder: Path) -> bytes:
    """The whole run folder as a sender delivers it, artifacts and the files beside them too."""
    from onetrace_console.ingest import SUMS_NAME
    files = {p.relative_to(folder).as_posix(): p.read_bytes()
             for p in sorted(folder.rglob("*")) if p.is_file()}
    files[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                  for p, b in files.items()) + "\n").encode()
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


def _stored(folder: Path, store):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    accepted = accept(_delivery(folder), store)
    assert accepted.run is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)


def _pages(run, store, framed: bool = True) -> dict[str, str]:
    from onetrace_console.pages import render_execution
    if framed:
        with rendering(onedoor=False, sign_in=False):
            return render_execution(run, store, generated_at=GENERATED_AT).pages
    return render_execution(run, store, generated_at=GENERATED_AT).pages


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))


def _item(page: str, kind: str, name: str) -> str:
    found = re.search(rf'<li data-{kind}="{re.escape(name)}">(.*?)</li>', page, re.S)
    assert found, f"no {kind} {name!r} on the page"
    return found.group(1)


@pytest.fixture
def demo(store):
    _require_installed()
    return _stored(DEMO / "day-1", store), store


@pytest.fixture
def tampered(tmp_path, store):
    """Day 1 with the request stage's stored output changed after its receipt was written."""
    _require_installed()
    folder = tmp_path / "day-1"
    shutil.copytree(DEMO / "day-1", folder)
    out = folder / "artifacts" / "01-request" / "request.json"
    out.write_bytes(out.read_bytes().replace(b"{", b'{"tampered": "1", ', 1))
    return _stored(folder, store), store


# ------------------------------------------------------------------ outputs

def test_a_stored_output_that_matches_its_receipt_is_shown_verified(demo):
    run, store = demo
    page = _pages(run, store)["stage-1.html"]
    item = _item(page, "output", "request.json")
    stored = json.loads((DEMO / "day-1" / "artifacts" / "01-request" / "request.json").read_text())
    assert "Verified" in _text(item)
    assert json.dumps(stored, indent=2, ensure_ascii=False).splitlines()[1].strip() in _text(item)
    #: Laid out as written: its line breaks are line breaks, not written-out escapes.
    pre = re.search(r'<pre data-content="verified">(.*?)</pre>', item, re.S).group(1)
    assert "\n" in pre and "\\u000a" not in pre, pre[:120]


def test_a_tampered_output_is_never_shown(tampered):
    run, store = tampered
    page = _pages(run, store)["stage-1.html"]
    item = _text(_item(page, "output", "request.json"))
    assert "does not match its receipt, not shown" in item
    assert "tampered" not in _text(page) and "Verified" not in item


# ------------------------------------------------------------------ inputs

def test_an_input_matching_an_upstream_stored_output_is_shown_with_what_was_checked(demo):
    run, store = demo
    page = _pages(run, store)["stage-2.html"]
    item = _text(_item(page, "input", "request.json"))
    assert "matches the stored output of request" in item and "Verified" in item
    assert not re.search(r"\b(?:read )?from request\b", item), "a route the receipt doesn't record"


def test_an_input_whose_digest_matches_but_whose_stored_bytes_do_not_is_not_shown(tampered):
    run, store = tampered
    page = _pages(run, store)["stage-2.html"]
    item = _text(_item(page, "input", "request.json"))
    assert "matches the stored output of" not in item and "Verified" not in item
    assert "tampered" not in _text(page)


def test_an_external_input_never_shows_content_even_when_the_file_is_on_disk(demo):
    run, store = demo
    assert (DEMO / "day-1" / "documents.json").is_file(), "the external file is in the delivery"
    page = _pages(run, store)["stage-2.html"]
    item = _text(_item(page, "input", "documents"))
    assert "fingerprint only" in item and "operator-authored" in item
    raw = _item(page, "input", "documents")
    assert "<pre" not in raw, "the external input's item carries content"
    #: The stage's own verified output, context.json, quotes the same documents -- that is a stored
    #: output shown after checking, not the external input, so only this input's own item is held.
    documents = json.loads((DEMO / "day-1" / "documents.json").read_text())
    assert documents[0]["text"] not in _text(raw), "the external file's content"


def test_the_banner_says_what_is_stored_and_what_is_fingerprinted(demo):
    run, store = demo
    page = _pages(run, store)["stage-2.html"]
    assert ("Outputs are stored and shown after checking; inputs from outside the run are "
            "fingerprinted, not stored.") in _text(page)


# ------------------------------------------------------------------ links

def _graph_links(page: str) -> list[str]:
    """The links on the graph's node boxes -- not its "Recorded order" link, which goes to the
    first step's row on the same page, as the viewer's in-page rule allows."""
    graph = re.search(r'<section data-section="graph">.*?</section>', page, re.S)
    assert graph, "no graph"
    return re.findall(r'<a href="([^"]*)"[^>]*><rect', graph.group(0))


def test_a_framed_node_links_to_its_stage_page_and_that_page_exists(demo):
    run, store = demo
    pages = _pages(run, store)
    links = _graph_links(pages["case.html"])
    assert links
    for href in links:
        #: The viewer's link fence: a link to another page is a bare sibling file name.
        assert re.fullmatch(r"stage-\d+\.html", href), href
        for forbidden in ("/", "\\", ":", "?", "#", "&"):
            assert forbidden not in href, href
        assert href in pages, f"{href} is not a page this run has"


def test_a_free_file_node_still_links_in_page(demo):
    run, store = demo
    links = _graph_links(_pages(run, store, framed=False)["case.html"])
    assert links and all(re.fullmatch(r"#step-\d+", h) for h in links), links


# ------------------------------------------------------------------ against a compared run

def test_against_a_compared_run_the_stage_says_same_in_or_differs_from(store):
    """The demo compared day 1 -> day 2: model is the first difference; request is the same."""
    _require_installed()
    from onetrace_console.compare import compare
    a, b = _stored(DEMO / "day-1", store), _stored(DEMO / "day-2", store)
    compare(a, b, store, ran_at=FIXED_RAN_AT)
    pages = _pages(b, store)
    base = f"{a.run_id} · {a.key[:12]}"
    assert f"Same in {base}" in _text(pages["stage-1.html"])
    model = next(n for n, p in pages.items() if n.startswith("stage-") and ">model<" in p)
    assert f"Differs from {base}" in _text(pages[model])


# ------------------------------------------------------------------ receipt-link inputs

def test_an_input_that_is_an_upstream_stored_receipt_links_to_that_stage_s_page(demo):
    """`receipt:request` on stage 2 is the digest of stage 1's stored receipt: what was checked is
    said, and the stage's page is linked -- a bare sibling name of a page this run has."""
    run, store = demo
    pages = _pages(run, store)
    raw = _item(pages["stage-2.html"], "input", "receipt:request")
    item = _text(raw)
    assert "matches the stored receipt of request" in item and "fingerprint only" not in item
    links = re.findall(r'<a href="([^"]*)"', raw)
    assert links == ["stage-1.html"] and "stage-1.html" in pages, links
    #: tests#2's receipt is the fourth in the chain: the link follows the digest, not the name.
    raw = _item(pages["stage-5.html"], "input", "receipt:tests#2")
    assert re.findall(r'<a href="([^"]*)"', raw) == ["stage-4.html"]
    assert "matches the stored receipt of tests" in _text(raw)


def test_a_receipt_input_whose_stored_receipt_does_not_match_stays_fingerprint_only():
    from onetrace_console.stage_pages import _input
    stored = b'{"stage": {"name": "request"}}'
    digest = "sha256:" + hashlib.sha256(stored).hexdigest()
    item = {"name": "receipt:request", "digest": digest, "trust_class": "operator-authored"}
    ok = _text(_input(item, {}, "r.tar", {digest: ("request", "1", stored)}))
    assert "matches the stored receipt of request" in ok
    changed = _input(item, {}, "r.tar", {digest: ("request", "1", stored + b" ")})
    assert "fingerprint only" in _text(changed) and "matches the stored receipt" not in _text(changed)
    assert "<a " not in changed
