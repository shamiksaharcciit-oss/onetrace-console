"""Every page kind's visible text, for the restyle: before and after must state the same.

Item 12 restyles the console to the v6 boards' look. It must not drop or reword a sentence, a caveat
or a denominator. Restyling may move them. So each page's text is read as a multiset of blocks:
the text of each block-level element, whitespace collapsed. A block may move within its page; it may
not vanish or change. What `pages()` reads:

- Home, every Executions page, Incidents and every rule list (`render_all`);
- each fixture run's answer, case and authorization pages (`render_execution`);
- the compare page of a pair (`render_diff`);
- the unreadable, unchecked and failed notices, and the sign-in page;
- the onedoor policy pages, over the committed onedoor fixture.
- one preview run's case page, the exam's ingest-r1 run B, in a store of its own.

The runs are the committed r11 run (no artifacts/), and the SDK-made pair the NB2 tests use: one
held, and one forged with artifacts/, which contradicts. Run keys, digests and times differ from
build to build, so 8+ hex digits, ISO times and temp paths are replaced by fixed markers before
comparing. This compares sentences, not values. The navigation frame (`data-frame`) is the
console's own chrome and is left out.

    python tools/visible_text.py <out.json>     # writes {page: [block, ...]} for this tree
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GENERATED_AT = "2026-10-01T12:00:00+00:00"

BLOCK = {"p", "div", "section", "article", "header", "footer", "main", "nav", "aside", "li",
         "ul", "ol", "table", "tr", "td", "th", "thead", "tbody", "h1", "h2", "h3", "h4", "h5",
         "h6", "pre", "details", "summary", "dl", "dt", "dd", "figure", "figcaption", "form",
         "label", "br", "hr", "blockquote", "caption",
         #: An SVG <text> is one box's label in the execution graph: its own
         #: block, not run together with the next box's.
         "text"}
SKIP = {"script", "style", "head", "title"}


class _Blocks(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.buf: list[str] = []
        self.skip = 0
        self.frame = 0

    def _flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        if text:
            self.blocks.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        if self.frame or any(k == "data-frame" for k, _ in attrs):
            self.frame += 1 if tag not in {"br", "hr", "img", "input", "meta", "link"} else 0
        if tag in BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        if self.frame and tag not in {"br", "hr", "img", "input", "meta", "link"}:
            self.frame -= 1
        if tag in BLOCK:
            self._flush()

    def handle_data(self, data):
        if not self.skip and not self.frame:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


#: A time as recorded (ISO) or as a page shows it ("2026-10-10 01:58:22 UTC"), and a time of day
#: alone after a date said once ("01:58:22 UTC", "10:00:00.000").
_TIME = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2}| UTC)?")
_CLOCK = re.compile(r"(?<![\d:])\d{2}:\d{2}:\d{2}(\.\d{3})?( UTC)?(?![\d:])")
_HEX = re.compile(r"\b[0-9a-f]{8,}\b")
_TEMP = re.compile(r"[A-Za-z]:[\\/][^\s'\"<>]*?(?:Temp|tmp)[\\/][^\s'\"<>]*", re.I)
_SECONDS = re.compile(r"\b\d+(\.\d+)?\s?s\b")


def normalise(text: str) -> str:
    text = _TEMP.sub("<temp path>", text)
    text = _TIME.sub("<time>", text)
    text = _CLOCK.sub("<time>", text)
    text = _HEX.sub("<hex>", text)
    return _SECONDS.sub("<seconds>", text)


def blocks(html: str) -> list[str]:
    p = _Blocks()
    p.feed(html)
    p.close()
    return sorted(normalise(b) for b in p.blocks)


def _page_name(name: str) -> str:
    return _HEX.sub("<key>", name)


#: When each fixture run arrives: fixed, one second apart, in the order `pages()` stores them.
#: The Overview labels pipelines P1, P2 ... by first arrival, read to the second, ties by run key.
#: Left to the clock, a fast host stored every run in one second and the tie fell to keys that
#: differ from build to build, so P1 and P2 swapped in some builds (7 of 10 on one Linux host,
#: at 85950fd). The baseline was taken with r11 first; these keep it first on every host.
RECEIVED_AT = ("2026-10-01T11:00:01+00:00", "2026-10-01T11:00:02+00:00",
               "2026-10-01T11:00:03+00:00", "2026-10-01T11:00:04+00:00")


def _stored_at(files: dict[str, bytes], store, received_at: str):
    """`tests.test_unreadable._stored`, with the run's arrival time given rather than read."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from tests.conftest import make_tar
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    _require_installed()
    from onetrace_console.preview import PREVIEW_FORMAT
    from tests.conftest import preview_veto_off
    if json.loads(files["MANIFEST.json"].decode("utf-8")).get("format") == PREVIEW_FORMAT:
        #: A preview fixture is stored directly (a new preview delivery is
        #: refused since 0.2.0); these pages show what the console does with runs it holds.
        with preview_veto_off():
            accepted = accept(make_tar(files), store, received_at=received_at)
    else:
        accepted = accept(make_tar(files), store, received_at=received_at)
    assert accepted.run is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT)


def pages(tmp: Path) -> dict[str, list[str]]:
    """Every page kind's visible text, as blocks, built from the committed fixtures."""
    return {_page_name(k): blocks(v) for k, v in sorted(rendered(tmp).items())}


def rendered(tmp: Path) -> dict[str, str]:
    """Every page kind, built from the committed fixtures in a fresh store under `tmp`, as HTML."""
    sys.path.insert(0, str(REPO))
    from onetrace_console.compare import compare
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_all, render_diff
    from onetrace_console.signin import render_signin_page
    from onetrace_console.store import Store
    from onetrace_console.unreadable import (render_failed_page, render_unchecked_run,
                                             render_unreadable_run)
    from tests.conftest import _delivery_paths
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_diff_sdk_text_layer import _forged_pair
    from tests.test_unreadable import _resummed

    store = Store(tmp / "store")
    r11 = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"
    r11_files = _resummed({p.relative_to(r11).as_posix(): p.read_bytes()
                           for p in _delivery_paths(r11)})
    runs = {"r11": _stored_at(r11_files, store, RECEIVED_AT[0])}
    (tmp / "held").mkdir()
    (tmp / "forged").mkdir()
    a, b = _forged_pair(tmp / "held")
    runs["held-a"] = _stored_at(a, store, RECEIVED_AT[1])
    runs["held-b"] = _stored_at(b, store, RECEIVED_AT[2])
    _, forged = _forged_pair(tmp / "forged", artifacts=True)
    runs["forged"] = _stored_at(forged, store, RECEIVED_AT[3])

    out: dict[str, str] = {}
    for name, run in runs.items():
        for page, html in render_execution(run, store, generated_at=GENERATED_AT).pages.items():
            out[f"run[{name}]/{page}"] = html
    comparison = compare(runs["held-a"], runs["held-b"], store, ran_at=FIXED_RAN_AT)
    out["diff[held-a,held-b]"] = render_diff(comparison, store, generated_at=GENERATED_AT)
    for href, html in render_all(store, generated_at=GENERATED_AT).items():
        out[href] = html
    out["notice/unreadable"] = render_unreadable_run(runs["r11"], "a stated reason",
                                                     generated_at=GENERATED_AT)
    out["notice/unchecked"] = render_unchecked_run(runs["r11"], generated_at=GENERATED_AT)
    out["notice/failed"] = render_failed_page("a stated reason", generated_at=GENERATED_AT)
    out["signin"] = render_signin_page(csrf_token="x" * 32)
    out.update(_policy_pages(store, tmp))
    out.update(_preview_case(tmp))
    return out


def _preview_case(tmp: Path) -> dict[str, str]:
    """One preview run's case page, as its two views, so the check sees the preview banner.

    The SDK exam's ingest-r1 run B, which declares stage-receipt-chain/0.0-preview, in a store of
    its own: in the shared store it would change every count, list and Overview page."""
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    from onetrace_console.store import Store
    from tests.conftest import _delivery_paths
    from tests.test_unreadable import _resummed
    folder = REPO / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1" / "run_B"
    files = _resummed({p.relative_to(folder).as_posix(): p.read_bytes()
                       for p in _delivery_paths(folder)})
    store = Store(tmp / "preview-store")
    run = _stored_at(files, store, RECEIVED_AT[0])
    drawn = render_execution(run, store, generated_at=GENERATED_AT).pages
    #: The run page's two views ("What changed" and "Proof").
    return {"run[preview]/case.html": drawn[CASE], "run[preview]/proof.html": drawn[RUN_PROOF]}


def _policy_pages(store, tmp: Path) -> dict[str, str]:
    """The onedoor extension's pages, over the committed onedoor fixture."""
    from onetrace_console.onedoor_ext.decisions import accept_export
    from onetrace_console.onedoor_ext.policy_pages import render_policy_pages
    from tests.test_upload_hardening import _member, _tar
    fixture = REPO / "tests" / "fixtures" / "onedoor"
    accept_export(_tar(_member("onedoor-export.jsonl", (fixture / "onedoor-export.jsonl").read_bytes()),
                       _member("onedoor-export.jsonl.sha256",
                               (fixture / "onedoor-export.jsonl.sha256").read_bytes())), store)
    return {f"policy/{k}": v for k, v in
            render_policy_pages(store, generated_at=GENERATED_AT).items()}


def main(argv: list[str]) -> int:
    with tempfile.TemporaryDirectory(prefix="visible-text-") as tmp:
        snap = pages(Path(tmp))
    Path(argv[0]).write_text(json.dumps(snap, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                             encoding="utf-8", newline="\n")
    print(f"{len(snap)} pages, {sum(len(v) for v in snap.values())} blocks -> {argv[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
