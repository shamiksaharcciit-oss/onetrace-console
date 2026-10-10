"""One run, one name a reader can follow.

    One run, two names: the run id leads, the short store key follows, in mono:
    `demo-run-2 · 1880b4aa455b`. Wherever a run is named (compare pages, incidents rows,
    Comparisons index), so a reader can tell two names are one run.

Before, the Overview and the run page said `demo-run-2` while the compare page and the incidents
above it said `1880b4aa455b`. Where a run's own record cannot be read there is no run id to show,
and none is invented: the key alone.
"""
from __future__ import annotations

import hashlib
import json
import re
from html import unescape

import pytest

from onetrace_console.render import COMPARISONS, render_all
from tests.test_compare_graph import dag_pages  # noqa: F401
from tests.test_home_and_diff import GENERATED_AT

NAME = re.compile(r'<span class="mono" data-run-name>(.*?)</span>', re.S)


def _names(html: str) -> list[str]:
    return [unescape(re.sub(r"<[^>]+>", "", n)) for n in NAME.findall(html)]


def test_the_compare_page_names_both_runs_by_id_and_key(dag_pages, store, examined):  # noqa: F811
    keys = {r.run_id: r.key for r in store.runs()}
    examined(len(keys), "stored runs named on the compare pages")
    page = dag_pages["PR"]
    p, r = f"dag-r37-p · {keys['dag-r37-p'][:12]}", f"dag-r37-r · {keys['dag-r37-r'][:12]}"
    assert 'data-section="pair"' not in page, "a graph pair names its runs once, in its A/B line"
    ab = re.search(r'<p data-section="runs-ab">.*?</p>', page, re.S).group(0)
    assert _names(ab) == [p, r], _names(ab)


def test_the_comparisons_index_names_both_runs(dag_pages, store, examined):  # noqa: F811
    keys = {r.run_id: r.key for r in store.runs()}
    index = render_all(store, generated_at=GENERATED_AT)[COMPARISONS]
    rows = re.findall(r'<tr data-key="[^"]*">(.*?)</tr>', index, re.S)
    examined(len(rows), "comparisons listed")
    assert rows
    for row in rows:
        named = _names(row)
        assert len(named) == 2 and all(" · " in n for n in named), named
        for n in named:
            run_id, key = n.split(" · ")
            assert keys[run_id][:12] == key


def test_an_incident_on_a_run_names_it_by_id_and_key(files, store, examined):
    from onetrace_console.checks import run_and_record
    from onetrace_console.incident_pages import INCIDENTS, render_incidents
    from onetrace_console.ingest import SUMS_NAME, accept
    from tests.conftest import make_tar
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_home_and_diff import _require_exam
    _require_installed()
    _require_exam()
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-changed"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(f"{hashlib.sha256(b).hexdigest()}  {p}"
                                  for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    bad = run_and_record(accept(make_tar(files), store).run, store, ran_at=FIXED_RAN_AT)
    page = render_incidents(store, generated_at=GENERATED_AT)
    examined(1, "the run an incident is raised on")
    assert f"{bad.run_id} · {bad.key[:12]}" in _names(page), _names(page)
    assert INCIDENTS


def test_a_run_whose_record_cannot_be_read_is_named_by_its_key_alone(store, monkeypatch):
    from onetrace_console.store import StoreError
    from onetrace_console.words import run_named

    def unreadable(key):
        raise StoreError("the stored record cannot be read")
    monkeypatch.setattr(store, "get_run", unreadable)
    key = "1880b4aa455b" + "0" * 52
    assert _names(run_named(store, key)) == ["1880b4aa455b"]
