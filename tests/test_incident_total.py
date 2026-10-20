"""The Incidents page opens with the total of incidents raised, the sentence the Overview's
Incidents card gave in 0.2.0: "N incidents raised from K of M runs."

1. The page's first sentence after its heading is that total, drawn by
   `incident_pages.incident_total`, which holds the lines that drew it on the Overview's card.
2. The total is read from the store, not from the per-rule counts: N is every incident the rules
   raise, K the runs they were raised from, each run once however many rules it trips.
3. On the demo, the page reads what the function returns for the demo's store; on a store where
   one run trips two rules, the run is counted once.
The four-run fixture of tests/test_ux_screens.py reads "0 incidents raised from 0 of 4 runs."
there.

Each check is a function returning the problems it finds; each has its sabotage.
"""
from __future__ import annotations

import hashlib
import html
import json
import re

import pytest

GENERATED_AT = "2026-09-26T12:00:00+02:00"


def total_problems(page: str, store) -> list[str]:
    """The page's first sentence, against the store's incidents counted here."""
    from onetrace_console.incident_pages import incident_total
    from onetrace_console.incidents import derive
    every = derive(store)
    runs = len(store.runs())
    raised_from = len({i.subject for i in every if i.subject_kind == "run"})
    want = (f"{len(every)} {'incident' if len(every) == 1 else 'incidents'} raised from "
            f"{raised_from} of {runs} {'run' if runs == 1 else 'runs'}.")
    found = re.search(r'<h1>Incidents</h1>\s*<p data-section="total">([^<]*)</p>', page)
    if not found:
        return ["the page does not open with its total"]
    said = html.unescape(found.group(1))
    out = []
    if said != want:
        out.append(f"the page says {said!r}, the store {want!r}")
    if said != incident_total(store):
        out.append(f"the page says {said!r}, incident_total {incident_total(store)!r}")
    return out


@pytest.fixture
def two_rules(files, store):
    """One run tripping two rules: a reused run name and a header that disagrees."""
    from onetrace_console.incidents import derive
    from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME, accept
    from tests.conftest import make_tar
    from tests.test_checks import _require_installed
    _require_installed()
    accept(make_tar(dict(files)), store)
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    dropped = manifest["chain"].pop()
    del files[dropped["file"]]
    manifest["chain_head"] = manifest["chain"][-1]["digest"]
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                  for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    both = accept(make_tar(files), store, headers={"chain_head": "sha256:deadbeef"}).run
    rules = {i.rule for i in derive(store) if i.subject == both.key}
    assert rules == {"I-RUNID-REUSED", "I-HEADER-DISAGREES"}, rules
    return store


def test_one_run_tripping_two_rules_is_counted_once(two_rules, examined):
    from onetrace_console.incident_pages import render_incidents
    page = render_incidents(two_rules, generated_at=GENERATED_AT)
    assert total_problems(page, two_rules) == []
    assert "2 incidents raised from 1 of 2 runs." in page
    examined(1, "Incidents page with one run under two rules")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("incident-total") / "demo"
    build_public(folder)
    pages = folder / "store" / "pages"
    return Store(folder / "store" / "store"), (pages / "incidents.html").read_text(encoding="utf-8")


def test_the_demo_s_incidents_page_opens_with_its_total(demo, examined):
    store, page = demo
    assert total_problems(page, store) == []
    examined(1, "the demo's Incidents page")


# ------------------------------------------------------------------------------- sabotages

def _per_rule_sum(store) -> str:
    """The total drawn from the per-rule counts, which count a run under two rules twice."""
    from onetrace_console.home import incident_tallies
    from onetrace_console.incidents import derive
    every, runs = derive(store), len(store.runs())
    return (f"{len(every)} {'incident' if len(every) == 1 else 'incidents'} raised from "
            f"{sum(len(t.runs) for t in incident_tallies(store))} of {runs} {'run' if runs == 1 else 'runs'}.")


def test_sabotage_the_total_from_the_per_rule_sum_is_named(two_rules, monkeypatch):
    from onetrace_console import incident_pages
    monkeypatch.setattr(incident_pages, "incident_total", _per_rule_sum)
    page = incident_pages.render_incidents(two_rules, generated_at=GENERATED_AT)
    assert "2 incidents raised from 2 of 2 runs." in page
    assert any("the store" in p for p in total_problems(page, two_rules))


def test_sabotage_the_total_dropped_is_named(two_rules):
    from onetrace_console.incident_pages import render_incidents
    page = re.sub(r'<p data-section="total">[^<]*</p>', "",
                  render_incidents(two_rules, generated_at=GENERATED_AT))
    assert total_problems(page, two_rules) == ["the page does not open with its total"]
