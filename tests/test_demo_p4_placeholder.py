"""P4's draft shows `{days}` by design, and its description says so.

`draft` is a stub that leaves the refund window as the placeholder `{days}`; `policy_check` fills it
from its recorded setting `refund_days`. A reader of the demo's Compare page sees `{days}` in the
draft's output, so the README, the PyPI description and the changelog say it is on purpose. Held
here to a run of P4 recorded now: the description is true of the draft and of the policy stage's
output, and each document carries it. Each check has its sabotage.
"""
from __future__ import annotations

import json

import pytest

from tests.test_folder_load import REPO

DOCS = ("README.md", "PYPI_DESCRIPTION.md", "CHANGELOG.md")
SAID = "The draft leaves the refund window as `{days}` on purpose; a later policy stage fills in the number."


def run_problems(folder, refund_days: str) -> list[str]:
    draft = json.loads((folder / "artifacts" / "02-draft" / "draft.json").read_text(encoding="utf-8"))
    checked = json.loads((folder / "artifacts" / "03-policy-check" / "checked.json").read_text(encoding="utf-8"))
    out = []
    if "{days}" not in draft["reply"]:
        out.append("the draft does not leave {days}")
    if checked["reply"] != draft["reply"].replace("{days}", refund_days):
        out.append("the policy stage does not fill {days} with refund_days")
    return out


def doc_problems(text: str) -> list[str]:
    n = text.count(SAID)
    return [] if n == 1 else [f"the placeholder's words said {n} times"]


def _record(folder, refund_days):
    from onetrace_console.demo_store import support_reply
    support_reply.main(folder, "p4-placeholder", refund_days)
    return folder


def test_p4_s_draft_leaves_days_and_the_policy_stage_fills_it(tmp_path, examined):
    examined(1, "run of P4")
    assert run_problems(_record(tmp_path / "run", "30"), "30") == []


@pytest.mark.parametrize("name", DOCS)
def test_each_document_says_the_placeholder_is_on_purpose(name, examined):
    examined(1, name)
    assert doc_problems((REPO / name).read_text(encoding="utf-8")) == []


def test_sabotage_each_check_catches_its_fault(tmp_path, monkeypatch, examined):
    from onetrace_console.demo_store import support_reply
    caught = 0
    #: The builder filling the number in the draft: the description would then be false.
    monkeypatch.setattr(support_reply, "PHRASINGS", [p.replace("{days}", "30") for p in support_reply.PHRASINGS])
    assert "the draft does not leave {days}" in run_problems(_record(tmp_path / "filled", "30"), "30")
    monkeypatch.undo()
    caught += 1
    #: The policy stage leaving the placeholder.
    folder = _record(tmp_path / "unfilled", "30")
    path = folder / "artifacts" / "03-policy-check" / "checked.json"
    path.write_text(path.read_text(encoding="utf-8").replace("30 days", "{days} days"), encoding="utf-8")
    assert "the policy stage does not fill {days} with refund_days" in run_problems(folder, "30")
    caught += 1
    #: A document without the words.
    text = (REPO / "README.md").read_text(encoding="utf-8")
    assert SAID in text and doc_problems(text.replace(" " + SAID, "")) != []
    caught += 1
    examined(caught, "faults caught")
