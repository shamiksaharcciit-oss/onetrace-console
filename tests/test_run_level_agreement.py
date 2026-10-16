"""A run without `artifacts/` reads as the pinned verifier says, everywhere.

`onetrace-verify` 0.1.2 prints `[NOT-RUN] run: artifacts -- artifacts not present; output files
not checked` on such a run and exits 0 with PASS. Before the viewer learned run-level rows, the
run's own page read "could not be checked from here" while the ingest answer, Home and the
Overview said "holds". This test uploads one such run to a real console, through the real
pinned verifier, and reads every surface that states the run's check, by name, one by one. Each
surface that presents the verifier's own output agrees with it: it held. Each that counts or lists
the run says its "Records agree" as its own page's rung 1 does: not checked, since the check held
without the run's output files required -- never "Verified", and never "couldn't check".
"""
from __future__ import annotations

import json
import re

from tests.conftest import make_tar
from tests.test_serve import _get, _post

RUN_ROW = "[NOT-RUN] run: artifacts -- artifacts not present; output files not checked"


def _strip_state(page: str) -> str:
    return re.search(r'<section class="strip [a-z]+" data-state="([a-z_]+)"', page).group(1)


def _rung(page: str, key: str) -> str:
    return re.search(rf'<tr data-rung="{key}" data-state="([a-z-]+)"', page).group(1)


def _tally(home: str, slug: str) -> str:
    return re.search(rf'<li data-tally="{slug}"><a [^>]*>([^<]*)</a>', home).group(1)


def test_a_run_without_artifacts_reads_as_the_verifier_says_on_every_surface(server, files,
                                                                              examined):
    base, root = server
    assert not any(p.startswith("artifacts/") for p in files), "the fixture must carry none"
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, body[:300]
    answer = json.loads(body)
    key = answer["run_key"]

    status, case = _get(base, f"/runs/{key}/case.html")
    assert status == 200
    case = case.decode("utf-8")
    assert RUN_ROW in case, "the pinned verifier did not print the run-level row this is about"

    surfaces = {}
    # 1. the ingest answer
    surfaces["ingest JSON check_verdict"] = answer["check_verdict"]
    # 2 and 3. the run's two pages, each drawing the strip from the stored report
    surfaces["case page strip"] = _strip_state(case)
    status, run_answer = _get(base, f"/runs/{key}/answer.html")
    assert status == 200
    surfaces["answer page strip"] = _strip_state(run_answer.decode("utf-8"))
    examined(len(surfaces), "surfaces that present the verifier's own output")
    assert set(surfaces.values()) == {"holds"}, surfaces
    # 4. Rung 1 is its own question: the check ran without --require-artifacts, so "not checked",
    # never "couldn't check" -- on the run's page, and on every surface that counts or lists it.
    counted = {"case page rung 1": _rung(case, "records-agree")}
    status, home = _get(base, "/counts.html")  # every count, whole
    assert status == 200
    home = home.decode("utf-8")
    counts = {slug: _tally(home, slug).split(" ", 1)[0]
              for slug in ("records-agree", "contradicts", "could-not-check", "not-checked", "no-verdict")}
    assert sorted(counts.values()) == ["0", "0", "0", "0", "1"], counts
    counted["Home tallies"] = next(s for s, n in counts.items() if n == "1")
    # 5. the Overview's attention list: the run is listed under not checked, as its order says
    status, overview = _get(base, "/")
    listed = [kind for kind, item in re.findall(r'<li data-attention="([a-z-]+)">(.*?)</li>',
                                                overview.decode("utf-8"), re.S) if key in item]
    counted["Overview attention"] = listed[0] if len(listed) == 1 else listed
    examined(len(counted), "surfaces that count or list the run")
    assert counted == {"case page rung 1": "not-checked", "Home tallies": "not-checked",
                       "Overview attention": "not-checked"}, counted
    assert "For the run as a whole" in case and "artifacts not present" in case
