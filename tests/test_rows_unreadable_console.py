"""On the console: a forged record whose FAIL row carries raw CR/LF.

`onetrace-verify` 0.1.2 checks the candidate's output file against its forged digest, FAILs, exits
1, and quotes the record's digest -- CR, LF and TAB -- inside the row, breaking its rows apart.
Before this change the console could not parse the rows and stored the run as could_not_check. The
verdict comes from the exit status and the summary line, so:
- the run is stored as **contradicts**, and every surface says so;
- no page draws a line the record wrote: the output is shown whole, escaped, with the note;
- the incident quotes the output whole, escaped, not a row cut off at the record's CR;
- the SDK's refusal to compare the pair names no folder of this host.
"""
from __future__ import annotations

import json
import re
import tempfile
from html import unescape
from pathlib import Path

import pytest

from tests.test_diff_sdk_text_layer import _forged_pair, _tar
from tests.test_serve import _get, _post

NOTE = "rows could not be read line by line; shown as written, escaped"


@pytest.fixture
def uploaded(server, tmp_path):
    base, root = server
    a, b = _forged_pair(tmp_path, artifacts=True)
    assert any(n.startswith("artifacts/") for n in b)
    answers = {}
    for side, files in (("a", a), ("b", b)):
        status, body = _post(base, "/v1/runs", _tar(files))
        assert status == 200, body[:300]
        answers[side] = json.loads(body)
    return base, root, answers


def _pre(page: str, marker: str) -> str:
    found = re.search(rf'<pre [^>]*{marker}[^>]*>(.*?)</pre>', page, re.S)
    assert found, f"no <pre> with {marker}"
    return unescape(found.group(1))


def test_the_forged_run_is_stored_as_contradicts_and_every_surface_says_so(uploaded, examined):
    base, _, answers = uploaded
    assert answers["a"]["check_verdict"] == "holds"
    b = answers["b"]
    status, case = _get(base, f"/runs/{b['run_key']}/case.html")
    case = case.decode("utf-8")
    status, home = _get(base, "/counts.html")  # every count, whole
    assert status == 200
    home = home.decode("utf-8")
    tally = {slug: re.search(rf'<li data-tally="{slug}"><a [^>]*>(\d+)', home).group(1)
             for slug in ("holds", "contradicts", "could-not-check")}
    examined(3, "surfaces read")
    assert b["check_verdict"] == "contradicts", b
    assert re.search(r'<section class="strip [a-z]+" data-state="contradicts"', case)
    assert tally == {"holds": "1", "contradicts": "1", "could-not-check": "0"}, tally


def test_on_0_2_0_the_forged_rows_read_and_the_digest_is_quoted_escaped(uploaded, examined):
    """0.1.2 quoted the forged digest's CR, LF and TAB raw inside its
    FAIL row, breaking its rows apart. The 0.2.0 verifier escapes a record's words in its own rows,
    so the rows read line by line: the FAIL row is shown as a row, the digest as the
    verifier escaped it (its backslashes then doubled by the page), and nothing raw."""
    base, _, answers = uploaded
    _, case = _get(base, f"/runs/{answers['b']['run_key']}/case.html")
    _, listed = _get(base, "/incidents-i-contradicts.html")
    #: The incident's own page, from its row on the rule's list: the verifier's rows are quoted there.
    own = re.search(r'<tr data-incident="[0-9a-f]+">.*?<a href="(incidents/[^"]+)">.*?'
                    + re.escape(f"runs/{answers['b']['run_key']}/case.html"), listed.decode("utf-8"), re.S)
    assert own, "the forged run's incident is listed, linked to its page"
    _, incident = _get(base, "/" + own.group(1))
    examined(2, "run page and incident page read")
    for page in (case.decode("utf-8"), incident.decode("utf-8")):
        assert 'data-rows="unreadable"' not in page and NOTE not in unescape(page)
        for raw in ("\r", "\t"):
            assert raw not in page, repr(raw)
        assert not re.search(r"^FORGED", page, re.M)
        assert ("digest is sha256: and 64 lower-case hex -- outputs[0].digest: "
                "'sha256:ab\\\\r\\\\nFORGED\\\\tROW") in unescape(page)


# ------------------- the path kept for a report stored before 0.2.0 (rows a record broke apart)

def _broken_rows(store):
    """A forged run's stored check report, as onetrace-verify 0.1.2 wrote it for this record: its
    FAIL row carrying the digest's CR, LF and TAB raw, so its rows can't be read one by one. A store
    may hold such reports from before the pin moved; they are planted here, not produced, since the
    0.2.0 verifier no longer writes one."""
    from dataclasses import replace

    from tests.test_unreadable import _stored
    with tempfile.TemporaryDirectory() as tmp:
        a, b = _forged_pair(Path(tmp), artifacts=True)
        _stored(a, store)
        run = _stored(b, store)
    envelope = json.loads(store.get(run.check_report).decode("utf-8"))
    #: As 0.1.2 stored it: one text run, no --json rows or outputs-required run.
    envelope.pop("rows_json", None)
    envelope.pop("outputs_required", None)
    envelope["stdout"] = ("[PASS   ] manifest: format\n"
                          "[FAIL   ] artifacts/01-alpha/a.json: digest matches -- 'sha256:ab\r\n"
                          "FORGED\tROW\r\n0000'\n"
                          "1 pass, 1 fail, 0 not-run  ->  FAIL\n")
    envelope["exit_status"] = "1"
    planted = replace(run, check_report=store.put(json.dumps(envelope).encode("utf-8")),
                      check_exit="1", check_verdict="contradicts", check_note="")
    store.put_run(planted)
    return planted


def test_a_stored_report_whose_rows_a_record_broke_is_shown_whole_and_escaped(store, examined):
    from onetrace_console.pages import CASE, render_execution
    run = _broken_rows(store)
    case = render_execution(run, store, generated_at="2026-10-06T12:00:00+00:00").pages[CASE]
    layer = _pre(case, 'data-rows="unreadable"')
    examined(1, "unreadable-rows layer")
    assert NOTE in unescape(case)
    for raw in ("\r", "\n", "\t"):
        assert raw not in layer, repr(raw)
    assert "FORGED" in layer and "ab\\u000d" in layer, "the record's characters, escaped"


def test_its_incident_quotes_the_output_whole_and_escaped(store, examined):
    from onetrace_console.incident_pages import render_incident_page
    from onetrace_console.incidents import derive
    run = _broken_rows(store)
    (incident,) = [i for i in derive(store) if i.subject == run.key and i.rule == "I-CONTRADICTS"]
    page = render_incident_page(incident, store, generated_at="2026-10-06T12:00:00+00:00")
    quoted = _pre(page, 'data-rows="unreadable"')
    examined(1, "incident quote")
    assert NOTE in unescape(page)
    for raw in ("\r", "\n", "\t"):
        assert raw not in quoted, repr(raw)
    assert "FORGED" in quoted and "->  FAIL" in quoted, "the whole output, to its summary"


def test_the_sdk_s_refusal_to_compare_names_no_folder_of_this_host(uploaded, examined):
    base, root, answers = uploaded
    status, body = _post(base, f"/compare?a={answers['a']['run_key']}&b={answers['b']['run_key']}")
    assert status == 200, body[:300]
    page = (root / "pages" / json.loads(body)["pages"]["diff"].lstrip("/")).read_text(encoding="utf-8")
    examined(1, "diff page")
    assert '<p data-section="diff-envelope" data-verdict="refused">' in page, "the SDK did not refuse"
    assert "(the candidate run&#x27;s folder)" in page or "(the candidate run's folder)" in page \
        or "(a temporary folder of this host&#x27;s)" in page, "the refusal's folder is not named"
    temp = str(Path(tempfile.gettempdir()).resolve())
    for shown in (temp, temp.replace("\\", "\\\\"), "onetrace-compare-"):
        assert shown not in page and shown not in unescape(page), shown


def test_the_consoles_own_words_on_a_refused_comparison_name_no_none(uploaded, examined):
    """A missing candidate is never shown as "None" in the console's words. The
    SDK's own text layers, which the console shows as written (B1), wrote "None" for a refused input
    with no run id until the third development build; since it, they write the named absence
    "(no run id)", and that is held here too."""
    base, root, answers = uploaded
    status, body = _post(base, f"/compare?a={answers['a']['run_key']}&b={answers['b']['run_key']}")
    assert status == 200, body[:300]
    page = (root / "pages" / json.loads(body)["pages"]["diff"].lstrip("/")).read_text(encoding="utf-8")
    layers = re.findall(r"<pre[^>]*>.*?</pre>", page, re.S)
    outside = page
    for layer in layers:
        outside = outside.replace(layer, "")
    examined(1, "refused Diff page read outside the SDK's layers")
    assert not re.search(r"\bNone\b", unescape(re.sub(r"<[^>]+>", " ", outside)))
    #: The SDK's layers too, now that the SDK writes the named absence.
    sdk = unescape(re.sub(r"<[^>]+>", " ", "".join(layers)))
    examined(len(layers), "the SDK's text layers on the refused Diff page")
    assert not re.search(r"\bNone\b", sdk), "the SDK's layers still write None"
    assert "(no run id)" in sdk
