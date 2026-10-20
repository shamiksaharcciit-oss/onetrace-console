"""The demo's one exception to "a public console never shows an input from outside the pipeline".

A run the demo builder built, of a pipeline its spec marks as example data, in a demo whose build
record vouches for every byte: its kept inputs -- the builder's own invented example data, and
nothing else -- are shown on the public demo, and its download includes them. Everything else
keeps the rule:

1. the public demo shows P4's kept ticket text on its intake step's page, and that run's download
   includes `inputs/`;
2. the same demo with one byte of that run changed after the build is refused by the build-record
   check, as before, and the exception is off for it;
3. a public store that is not the demo never shows kept inputs from outside the pipeline, nor
   includes them in a download -- not with the demo's own pipeline and bytes, and not with any
   other text, whatever its configuration says (the exception is decided by the builder's code,
   which no setting reaches).
"""
from __future__ import annotations

import html
import io
import json
import re
import shutil
import tarfile
from pathlib import Path

import pytest

GENERATED_AT = "2026-01-01T00:00:00+00:00"
P4_RUN = "p4-29-reply-30-days"


def _text(page: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("example-inputs") / "demo"
    build_public(folder)
    return folder


def _run(folder: Path, name: str):
    from onetrace_console.store import Store
    store = Store(folder / "store" / "store")
    (run,) = [r for r in store.runs() if r.run_id == name]
    return run, store


def _intake_page(folder: Path, run) -> str:
    return (folder / "store" / "pages" / "runs" / run.key / "stage-1.html").read_text(encoding="utf-8")


def _members(data: bytes) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        return tar.getnames()


def test_the_public_demo_shows_the_kept_ticket_and_its_download_includes_it(built, examined):
    from onetrace_console.demo_store import allowing_examples, support_reply
    from onetrace_console.ingest import bundle
    from onetrace_console.kept_inputs import EXAMPLE_RECORD
    run, store = _run(built, P4_RUN)
    page = _intake_page(built, run)
    examined(1, "the P4 run's intake step page")
    assert 'data-kept="shown"' in page, _text(page)[:800]
    assert support_reply.TICKET in _text(page)
    receipt = (built / "store" / "pages" / "runs" / run.key / "receipt.html").read_text(encoding="utf-8")
    assert EXAMPLE_RECORD in _text(receipt)
    with allowing_examples(built) as allowing:
        assert allowing.allowed
        members = _members(bundle(run, store, public=True))
    assert any(m.startswith("inputs/") for m in members), members


def test_one_byte_changed_after_the_build_is_refused_and_the_exception_is_off(built, tmp_path, examined):
    from onetrace_console.demo_store import allowing_examples, check_build_record
    from onetrace_console.ingest import bundle
    copy = tmp_path / "demo"
    shutil.copytree(built, copy)
    (kept,) = (copy / "runs" / P4_RUN / "inputs").rglob("*.json")
    data = bytearray(kept.read_bytes())
    data[-2] = ord("?") if data[-2] != ord("?") else ord("!")
    kept.write_bytes(bytes(data))
    examined(1, "demo with one byte changed")
    problems = check_build_record(copy)
    assert problems == [f"{kept.relative_to(copy).as_posix()} was changed"], problems
    run, store = _run(copy, P4_RUN)
    with allowing_examples(copy) as allowing:
        assert not allowing.allowed
        assert not any(m.startswith("inputs/") for m in _members(bundle(run, store, public=True)))


def test_the_public_console_refuses_to_start_on_a_changed_demo(built, tmp_path, examined):
    from onetrace_console.config import Config
    from onetrace_console.public import start_refusal
    copy = tmp_path / "demo"
    shutil.copytree(built, copy)
    (kept,) = (copy / "runs" / P4_RUN / "inputs").rglob("*.json")
    kept.write_bytes(kept.read_bytes().replace(b"kettle", b"Kettle", 1))
    config = Config(public=True, store_root=str(copy / "store"), trust_file=str(copy / "trust.json"),
                    sign_in={**Config().sign_in, "enabled": False})
    examined(1, "start refused")
    refused = start_refusal(config, copy / "store")
    assert refused is not None and "was changed" in refused.message


def _record(folder: Path, ticket: str | None) -> Path:
    """A run of P4's own pipeline outside the demo; `ticket` replaces the invented ticket."""
    from onetrace_console.demo_store import support_reply
    run_dir = folder / "runs" / "my-reply"
    if ticket is None:
        support_reply.main(run_dir, "my-reply", "30")
    else:
        saved = support_reply.TICKET
        support_reply.TICKET = ticket
        try:
            support_reply.main(run_dir, "my-reply", "30")
        finally:
            support_reply.TICKET = saved
    return folder / "runs"


@pytest.mark.parametrize("ticket", [None, "A real customer's message, never to be shown."],
                         ids=["the-demo-s-own-bytes", "other-text"])
def test_a_store_that_is_not_the_demo_never_shows_or_downloads_kept_inputs(tmp_path, ticket, examined):
    from onetrace_console.config import Config
    from onetrace_console.demo_store import allowing_examples
    from onetrace_console.folder_load import load_folder
    from onetrace_console.frame import rendering
    from onetrace_console.ingest import bundle
    from onetrace_console.kept_inputs import EXTERNAL, PUBLIC_RECORD
    from onetrace_console.pages import render_execution
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    runs = _record(tmp_path, ticket)
    store = Store(tmp_path / "store")
    run = load_folder(runs, store, Config(public=True)).runs[0].run
    examined(2, "renderings, without and inside the demo's exception")
    for context in (None, allowing_examples(tmp_path)):
        if context is not None:
            context.__enter__()
        try:
            with rendering(onedoor=False, sign_in=False, public=True):
                pages = render_execution(run, store, generated_at=GENERATED_AT).pages
            assert 'data-kept="external"' in pages["stage-1.html"] and EXTERNAL in _text(pages["stage-1.html"])
            assert 'data-kept="shown"' not in pages["stage-1.html"]
            assert PUBLIC_RECORD in _text(pages["receipt.html"])
            assert not any(m.startswith("inputs/") for m in _members(bundle(run, store, public=True)))
        finally:
            if context is not None:
                context.__exit__(None, None, None)
