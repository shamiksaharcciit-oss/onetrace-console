"""What the demo is said to hold is what its builder makes.

The public banner on every page says how many example pipelines the demo's runs come from. That
count is read from the builder's own run list (`demo_store.pipeline_names`), never typed, and
held here, on every page a public console serves of the demo built as the image builds it, to the
pipelines the console finds in that store. The README, the PyPI description
and the changelog say the same counts in prose; each is held to the builder: its pipelines, its
runs and its comparisons, and the README and the PyPI description the runs it breaks on purpose
(`demo_store.PLANTED`). The README's Overview image says, in its PNG Description, the runs and
pipelines its Runs card showed when it was taken, and those are the builder's. Each check has its
sabotage.
"""
from __future__ import annotations

import re
import struct
import zlib
from html import unescape

import pytest

from tests.test_folder_load import REPO
from tests.test_public_mode import _pages, built, served  # noqa: F401
from tools import container_check

DOCS = ("README.md", "PYPI_DESCRIPTION.md")


def banner_problems(page: str, pipelines: int) -> list[str]:
    from onetrace_console.public import count_word
    said = re.findall(r'<p data-frame="banner">(.*?)</p>', page, re.S)
    if len(said) != 1:
        return [f"the banner is there {len(said)} times"]
    words = re.search(r"Its runs come from (\w+) small example pipelines", unescape(said[0]))
    if words is None or words.group(1) != count_word(pipelines):
        return [f"the banner says {words.group(1) if words else 'no count'}, the store holds {pipelines}"]
    return []


def doc_problems(name: str, text: str) -> list[str]:
    from onetrace_console.demo_store import COMPARISONS, PLANTED, pipeline_names, runs
    from onetrace_console.public import count_word
    out = []
    wanted = [(r"(\w+) small example pipelines", count_word(len(pipeline_names())), "pipelines")]
    if name in DOCS:
        wanted.append((r"stores (\w+) comparisons", count_word(len(COMPARISONS)), "comparisons"))
        #: The Overview image's description: the runs the image shows are the demo's.
        wanted.append((r"the demo's (\w+) runs", str(len(runs())), "runs"))
        #: The runs the builder breaks on purpose, one line each in its own list.
        wanted.append((r"(\w+) of its runs are broken on purpose when the demo is built",
                       count_word(len(PLANTED)).capitalize(), "runs broken on purpose"))
    else:
        #: The changelog's newest entry that says what the demo records: a release that leaves the
        #: demo's counts as they were (0.1.2's fixes) doesn't say them again.
        entries = text.split("\n## ")[1:]
        text = next((e for e in entries if re.search(r"records \w+ runs", e)), entries[0] if entries else "")
        wanted.append((r"records (\w+) runs", str(len(runs())), "runs"))
    for pattern, word, what in wanted:
        found = re.findall(pattern, text)
        if found != [word]:
            out.append(f"{name}: {what} said as {found}, the builder makes {word}")
    return out


OVERVIEW = REPO / "docs" / "screenshots" / "overview.png"


def image_problems(png: bytes) -> list[str]:
    """The Overview image's Description text chunk: well formed, and the builder's runs and pipelines."""
    from onetrace_console.demo_store import pipeline_names, runs
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        return ["not a PNG"]
    said, at = None, 8
    while at < len(png):
        (size,) = struct.unpack(">I", png[at:at + 4])
        kind, data = png[at + 4:at + 8], png[at + 8:at + 8 + size]
        if struct.unpack(">I", png[at + 8 + size:at + 12 + size])[0] != zlib.crc32(kind + data):
            return [f"a {kind!r} chunk's CRC does not hold"]
        if kind == b"tEXt" and data.startswith(b"Description\x00"):
            said = data.split(b"\x00", 1)[1].decode("latin-1")
        at += 12 + size
    found = re.fullmatch(r"The Overview of onetrace-console's demo: (\d+) runs stored, in (\d+) pipelines", said or "")
    if found is None:
        return [f"the image says {said!r}"]
    want = (str(len(runs())), str(len(pipeline_names())))
    return [] if found.groups() == want else [f"the image shows {found.groups()}, the builder makes {want}"]


def test_the_overview_image_shows_the_builder_s_runs(examined):
    examined(1, "image")
    assert image_problems(OVERVIEW.read_bytes()) == []


def _with_description(png: bytes, said: str | None) -> bytes:
    """The image with its Description chunk (right after IHDR) replaced by `said`, or taken out."""
    (size,) = struct.unpack(">I", png[33:37])
    assert png[37:41] == b"tEXt"
    rest = png[:33] + png[45 + size:]
    if said is None:
        return rest
    data = b"Description\x00" + said.encode("latin-1")
    chunk = struct.pack(">I", len(data)) + b"tEXt" + data + struct.pack(">I", zlib.crc32(b"tEXt" + data))
    return rest[:33] + chunk + rest[33:]


def test_sabotage_an_image_from_an_older_demo_without_its_description_or_broken_is_named(examined):
    png = OVERVIEW.read_bytes()
    older = _with_description(png, "The Overview of onetrace-console's demo: 41 runs stored, in 7 pipelines")
    broken = png[:40] + bytes([png[40] ^ 1]) + png[41:]
    examined(3, "planted images")
    assert image_problems(older) == ["the image shows ('41', '7'), the builder makes ('54', '11')"]
    assert image_problems(_with_description(png, None)) == ["the image says None"]
    assert image_problems(broken) != []


def test_every_public_page_s_banner_counts_the_store_s_pipelines(served, examined):  # noqa: F811
    from onetrace_console.demo_store import pipeline_names
    from onetrace_console.overview import pipelines
    from onetrace_console.store import Store
    base, folder, _c = served
    found = len(pipelines(Store(folder / "store" / "store")))
    assert found == len(pipeline_names()), "the store holds the builder's pipelines"
    pages = _pages(folder)
    examined(len(pages), "public pages served and read for the banner")
    assert len(pages) >= 50
    for rel in pages:
        status, _headers, body = container_check.fetch(base, "/" + rel)
        assert status == 200 and banner_problems(body.decode("utf-8"), found) == [], rel


@pytest.mark.parametrize("name", DOCS + ("CHANGELOG.md",))
def test_each_document_counts_what_the_builder_makes(name, examined):
    examined(1, name)
    assert doc_problems(name, (REPO / name).read_text(encoding="utf-8")) == []


def test_sabotage_each_check_catches_its_fault(served, monkeypatch, examined):  # noqa: F811
    from onetrace_console import demo_store
    from onetrace_console.frame import banner
    page = container_check.fetch(served[0], "/home.html")[2].decode("utf-8")
    caught = 0
    #: The count typed into the banner's words, as it was: three.
    typed = page.replace("from 11 small", "from three small")
    assert typed != page and "the banner says three" in banner_problems(typed, 11)[0]
    caught += 1
    #: The builder's list read wrong: one pipeline left out of it.
    names = demo_store.pipeline_names()
    monkeypatch.setattr(demo_store, "pipeline_names", lambda: names[:-1])
    assert banner_problems(banner(), len(names)) != []
    monkeypatch.undo()
    caught += 1
    for name, old, new in [("README.md", "from 11 small", "from ten small"),
                           ("PYPI_DESCRIPTION.md", "stores 15 comparisons", "stores 14 comparisons"),
                           ("README.md", "the demo's 54 runs", "the demo's 48 runs"),
                           ("CHANGELOG.md", "records 54 runs", "records 48 runs")]:
        text = (REPO / name).read_text(encoding="utf-8")
        assert old in text, name
        assert doc_problems(name, text.replace(old, new)) != [], name
        caught += 1
    examined(caught, "faults caught")


def test_sabotage_a_run_planted_and_not_counted_in_the_documents_is_named(monkeypatch):
    from onetrace_console import demo_store
    planted = dict(demo_store.PLANTED, **{"p6-36-fill-baseline": "One more run broken on purpose."})
    monkeypatch.setattr(demo_store, "PLANTED", planted)
    for name in DOCS:
        found = doc_problems(name, (REPO / name).read_text(encoding="utf-8"))
        assert any("runs broken on purpose" in p for p in found), (name, found)
