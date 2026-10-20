"""What the demo is said to hold is what its builder makes.

The public banner on every page says how many example pipelines the demo's runs come from. That
count is read from the builder's own run list (`demo_store.pipeline_names`), never typed, and
held here, on every page a public console serves of the demo built as the image builds it, to the
pipelines the console finds in that store. The README, the PyPI description
and the changelog say the same counts in prose; each is held to the builder: its pipelines, its
runs and its comparisons, and the README and the PyPI description the runs it breaks on purpose
(`demo_store.PLANTED`). Each check has its sabotage.
"""
from __future__ import annotations

import re
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
    typed = page.replace("from seven small", "from three small")
    assert typed != page and "the banner says three" in banner_problems(typed, 7)[0]
    caught += 1
    #: The builder's list read wrong: one pipeline left out of it.
    names = demo_store.pipeline_names()
    monkeypatch.setattr(demo_store, "pipeline_names", lambda: names[:-1])
    assert banner_problems(banner(), len(names)) != []
    monkeypatch.undo()
    caught += 1
    for name, old, new in [("README.md", "from seven small", "from six small"),
                           ("PYPI_DESCRIPTION.md", "stores ten comparisons", "stores nine comparisons"),
                           ("README.md", "the demo's 41 runs", "the demo's 40 runs"),
                           ("CHANGELOG.md", "records 41 runs", "records 40 runs")]:
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
