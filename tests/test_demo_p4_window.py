"""P4's draft names the refund window in words, and no page the demo draws holds an unfilled
`{name}` placeholder.

`draft` is a stub that names the window as "the refund window"; `policy_check` puts in the number
of days from its recorded setting `refund_days`. Until 0.1.2 the draft left the placeholder
`{days}`, and the demo's step and Compare pages showed it. Held here: to a run of P4 recorded now,
to the README, the PyPI description and the changelog, which say what the draft writes, and to
every page of the public demo, none of which may hold a `{name}` placeholder. Each check has its
sabotage.
"""
from __future__ import annotations

import json
import re

import pytest

from tests.test_folder_load import REPO

DOCS = ("README.md", "PYPI_DESCRIPTION.md", "CHANGELOG.md")
SAID = "The draft names the refund window in words; a later policy stage puts in the number of days."

#: A `{name}` placeholder left unfilled: a name in braces, as `str.format` fills it.
PLACEHOLDER = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}")


def run_problems(folder, refund_days: str) -> list[str]:
    from onetrace_console.demo_store.support_reply import WINDOW
    draft = json.loads((folder / "artifacts" / "02-draft" / "draft.json").read_text(encoding="utf-8"))
    checked = json.loads((folder / "artifacts" / "03-policy-check" / "checked.json").read_text(encoding="utf-8"))
    out = []
    if WINDOW not in draft["reply"] or PLACEHOLDER.search(draft["reply"]):
        out.append("the draft does not name the window in words")
    if checked["reply"] != draft["reply"].replace(WINDOW, f"{refund_days} days of delivery"):
        out.append("the policy stage does not put in refund_days")
    return out


def doc_problems(text: str) -> list[str]:
    n = text.count(SAID)
    return [] if n == 1 else [f"the draft's words said {n} times"]


def page_problems(pages: dict[str, str]) -> list[str]:
    """Each page holding a `{name}` placeholder, with what it holds."""
    return [f"{rel}: {sorted(set(PLACEHOLDER.findall(page)))}" for rel, page in sorted(pages.items())
            if PLACEHOLDER.search(page)]


def _record(folder, refund_days):
    from onetrace_console.demo_store import support_reply
    support_reply.main(folder, "p4-window", refund_days)
    return folder


@pytest.fixture(scope="module")
def demo_pages(shared_demo) -> dict[str, str]:
    from tests.test_checks import _require_installed
    _require_installed()
    folder = shared_demo["folder"]
    root = folder / "store" / "pages"
    return {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in root.rglob("*.html")}


def test_p4_s_draft_names_the_window_and_the_policy_stage_puts_in_the_days(tmp_path, examined):
    examined(1, "run of P4")
    assert run_problems(_record(tmp_path / "run", "30"), "30") == []


@pytest.mark.parametrize("name", DOCS)
def test_each_document_says_what_the_draft_writes(name, examined):
    examined(1, name)
    assert doc_problems((REPO / name).read_text(encoding="utf-8")) == []


def test_no_page_of_the_demo_holds_an_unfilled_placeholder(demo_pages, examined):
    examined(len(demo_pages), "pages of the public demo")
    assert page_problems(demo_pages) == []


def test_sabotage_each_check_catches_its_fault(tmp_path, monkeypatch, demo_pages, examined):
    from onetrace_console.demo_store import support_reply
    caught = 0
    #: The draft leaving `{days}` again, as before 0.1.2.
    monkeypatch.setattr(support_reply, "PHRASINGS",
                        [p.replace(support_reply.WINDOW, "{days} days of delivery") for p in support_reply.PHRASINGS])
    assert "the draft does not name the window in words" in run_problems(_record(tmp_path / "old", "30"), "30")
    monkeypatch.undo()
    caught += 1
    #: The policy stage leaving the window unset.
    folder = _record(tmp_path / "unset", "30")
    path = folder / "artifacts" / "03-policy-check" / "checked.json"
    path.write_text(path.read_text(encoding="utf-8").replace("30 days of delivery", support_reply.WINDOW),
                    encoding="utf-8")
    assert "the policy stage does not put in refund_days" in run_problems(folder, "30")
    caught += 1
    #: A document without the words.
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert SAID in text and doc_problems(text.replace(" " + SAID, "")) != []
    caught += 1
    #: A page showing the old draft's reply.
    rel = next(r for r, p in demo_pages.items() if support_reply.WINDOW in p)
    planted = {rel: demo_pages[rel].replace(support_reply.WINDOW, "{days} days of delivery", 1)}
    assert page_problems(planted) == [f"{rel}: ['{{days}}']"]
    caught += 1
    examined(caught, "faults caught")
