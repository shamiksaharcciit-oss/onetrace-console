"""A run page's graph marked from the latest stored comparison in which the run
is the candidate: each node carries its verdict from that report.

Six cases, on real SDK comparisons of the exam's dag-r37 runs; R is the run whose page is
marked:
1. no comparison -- the page is the page it always was (no marks, no line), byte for byte;
2. one comparison stored -- its marks, every first difference outlined, and the naming line;
3. a newer comparison stored -- the marks and the line switch to it;
4. a restart -- the same page, byte for byte;
5. the run is only ever the baseline -- no marks;
6. a corrupt report -- no marks, and the sentence saying so.
And: storing a comparison over HTTP re-renders the candidate's page, and nothing else does.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from onetrace_console.compare import DIFF, compare
from onetrace_console.pages import CASE, render_execution
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_home_and_diff import GENERATED_AT, _deliver, _require_exam

DAG = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "dag-r37"
LATER = "2026-10-02T12:00:00+00:00"


@pytest.fixture
def runs(store):
    _require_installed()
    _require_exam()
    from onetrace_console.checks import run_and_record
    #: Delivered and checked, as an ingest does: a run page needs the run's own check.
    return {n: run_and_record(_deliver(DAG / f"run_{n}", store), store, ran_at=FIXED_RAN_AT)
            for n in "PQR"}, store


def _case(run, store) -> str:
    return render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]


def _graph(page: str) -> str:
    found = re.search(r'<section data-section="graph">.*?</section>', page, re.S)
    assert found, "no graph"
    return found.group(0)


def _titles(page: str) -> dict[str, str]:
    """Each box's title, with the titles of the lines it quotes from the report after it."""
    from tests.test_compare_graph import _box_titles
    return {t.split(" · ")[0]: t for _attrs, t in _box_titles(_graph(page))}


#: R's case page with no comparison stored, P, Q and R ingested and checked, less the two things
#: that belong to the machine, not the page: the verifier's path (a path relative to wherever
#: pytest made its temp folder, into wherever the host keeps its venv) and so the
#: fingerprint that covers it. Everything else is pinned, byte for byte.
#: Measured by tooling, and measured equal to the page drawn by the earlier code
#: (the vendored viewer 8fdf301 and the console as it was at f8c506a): with no comparison the
#: page is today's page. It moves only when the page itself does, as any golden pin.
#: Moved for canary 0fad8d7: the graph panel's scrollbar is drawn, five
#: lines of the viewer's CSS that the page carries; rendered by tooling with the previous
#: wheel (ed28d32, which gives the previous pin) and the new one, nothing else moves.
#: Previously `b262a43b…`.
#: A third thing belongs to the machine (as test_visible_text already holds):
#: the verifier's line endings. Windows writes its stdout in text mode, so every LF it writes
#: arrives as CR LF, and the page's verbatim layer of that output carries the CRs raw. The
#: Windows check of daa3c2b (run #2) failed here with 1e27ccb5... -- reproduced exactly off Windows
#: by giving the verifier's stdout CR LF line endings, and nothing else on the page differed. So
#: inside a verbatim block of the verifier's rows, one or more CRs before an LF go; a CR anywhere
#: else on the page is kept.
#: Moved again for canary 35c643b: quoted fields wrap anywhere (two lines of
#: CSS) and the boundary section, drawn here outside the console's frame, is headed "Where the
#: record stops"; rendered by tooling with the previous wheel (0fad8d7, giving the previous pin)
#: and the new one, nothing else moves. Previously `782d75b0…`.
#: And for the run names: R's own incident row names it "dag-r37-r · 721042dcd617"
#: rather than by its key alone; rendered by tooling at 977c80a and now, nothing else moves.
#: Previously `c3eda474…`.
#: And for canary 64c4026: the viewer's stylesheet carries the failed-last-
#: attempt line's rule (R has none to state); rendered by tooling with 35c643b's wheel and
#: 64c4026's, only those two lines of CSS differ. Previously `0d9abcae…`.
#: And for board 5: the case page links the run receipt in its Policy section;
#: rendered by tooling at b691e8f and now, only that one paragraph differs, and the page without it
#: hashes to the previous pin. Previously `9cf4ca13…`.
#: And for the dead links: the incident's "the report it came from" now links the run's
#: case page and "all incidents" the Incidents page, each relative to the page; with those two
#: links put back as they were, the page hashes to the previous pin. Previously `8c93bd6a…`.
#: And for canary 75f13ac: the ladder gains "Ran as approved", which on R --
#: a graph run checked by 0.1.2 -- says the check that ran can't say; with exactly that one row
#: taken out, the page hashes to the previous pin. Previously `1f16c575…`.
#: And for canary 02c6204, on the 0.2.0 development build: the check is the
#: installed onetrace-verify, so its command reads `onetrace-verify MANIFEST.json` (twice), the page
#: regenerates with `generate --cli`, the check's own words gain the CLI's two graph-edge rows (76 to
#: 78 pass), and "Ran as approved" reads yes from them. Rendered by tooling with 682eb99 (the console
#: on 0.1.2 and its viewer, which gives the previous pin exactly) and now: nothing else moves.
#: Previously `691c07fb…`.
#: And for the Signed half (canary 7a15842, on the third development build): the
#: signing rung reads Unsigned from the check's own signature rows, which R has none of; with exactly
#: that row put back to "Not yet available · records are unsigned in this release", the page hashes
#: to the previous pin (measured with this test's own fixture). Previously `fc15cabb…`.
#: Moved when the first screens were made plain, from aedd4f5a9b2f2d74d159846fb92ee1cf2ab69afd14e38554ca3e5ba56bef03c5.
#: The page before and after differs in exactly two places, measured by diffing the two renderings:
#: the topology I-COULD-NOT-CHECK incident block is gone (no incident for a check the pinned release
#: does not ship), and the authorization rung reads "This console does not record authorization."
#: Moved when the viewer moved into the console, from f8158f989de92a091b6354469148f3671e07e4174e1184bf3f9493acd64d24c7.
#: The page before and after differs in exactly one line, measured by diffing the two renderings:
#: the regenerate command names the viewer's module in the console, `python -m onetrace_console.viewer`.
#: Moved when a reason every step shares was said once, from 0998006ef80266fff64a42479a6d05f877d401c601edcd1f4ae3c18b28b434df.
#: The page before and after differs in exactly one place, measured by diffing the two renderings:
#: the "Not checked" list's three identical lines (one per step) are one line, "Every step — ... so
#: none of these steps can be shown to be the record that was made."
#: Moved when the banner's time was drawn short, from a3ebbf35bff54dbbc1477b38a94f03f3d3b727fe318b36df02a65fd1b86a65b9.
#: The page before and after differs in exactly one place, measured by diffing the two renderings:
#: the banner's "checked on" time is a <time> element reading "2026-09-26 10:00 UTC", its full value
#: (2026-09-26T12:00:00+02:00) kept in the element.
#: Moved by 0.1.1's type scale (the one shared style), from 47406d079f96605c111af274fcce1b72a3119fd73e3f5edca961fecea019885d.
#: Measured by diffing the two renderings: only the inlined stylesheet's font sizes differ -- 17px
#: to 15px (the strip's lead), 13.5px to 13px (.grid, table.timeline), 12.5px to 12px (.fp, pre),
#: 11.5px to 12px (.grid .k, table.timeline th). No word, element or attribute moves.
#: Moved by 0.1.1's colour rule, from 2052d9e95eeabf5de121ceefb60e18a955fb07dfba8944dbe2260398a9ca5f33.
#: Measured by diffing the two renderings: two rungs' states only -- the signing rung's
#: data-state "no" to "unsigned" (its words unchanged), and the anchoring rung's "no" with
#: "No · not anchored" to "not-anchored" with "Not anchored · no anchor beside the chain".
#: Moved by the version, 0.1.0 to 0.1.1, from 12d02707dc514462dd18ae0c57ee77662748f842a43ba46abb8d9110d2982433.
#: Measured by diffing the two renderings: the footer's "onetrace-console 0.1.0." only.
#: Moved by the run page's head, from 0762e213bd912524f4fa66531fdda9c3e23b266be42aedbeb4fb32b0136a6452.
#: Measured by diffing the two renderings: the viewer's header ("Case", "The run, step by step",
#: the run id) is replaced by the head section (crumbs; the run id and its pipeline label as the
#: title; "3 of 3 declared stages · recorded in the format ... · ran <time> · received by this
#: console <time>"; the four rungs as the ladder states them; tabs to #graph, #timeline,
#: stage-1.html, receipt.html; a space between each rung's question and state, and between
#: tabs), and an empty anchor before the graph and the step table. Nothing else moves. The received time and the label are normalised above (_RECEIVED, _LABEL).
#: Moved by the release polish, merged from 0.1.1, from e76f06092894779af0674c36aca0016b4b3e7c81df43632f6e38ec8f53fc70e8.
#: Measured by diffing the two renderings, 14 edits of three kinds only: a `data-label` on each of
#: the 12 body cells of the page's headed tables (a narrow screen's column labels); the viewer's
#: stylesheet hiding the graph's narrow-screen list (`.graph-list{display:none}`); and that list,
#: the graph's boxes in reading order, each saying whether it reads the box before it. This run
#: records no reads, so no line is drawn. No word, and no other element or attribute, moves.
#: Moved by the head on the run's other pages, from cd6522684f466657a748ed3d7614e3b8c9142a858c439fd814e7555a264dfb00.
#: Measured by diffing the two renderings: one edit, ` class="run-title"` on the head's title.
#: Moved by the version, 0.1.1 to 0.1.2, from 5a3853b83f21088410c1edc1792ed15c50f6b5f32b249656e3f20db69b46a0c1.
#: Measured by diffing the two renderings: the footer's "onetrace-console 0.1.1." only.
#: Moved by the run stopped by a step's own rule, from 2bb4307c6b36f955ab5c52d974e8162b834f8b05f5bca785f2c35cc22f2204c4.
#: Measured by diffing the two renderings, three edits: the stylesheet's `.declined` rule; the
#: head's chip "Declined at join" (R's last step, join, declined: "inputs never arrived: both
#: roots refused"); and the banner saying where the run stopped, why, and that no declared step
#: was left without a receipt.
#: Moved by the dark theme, from 041514605624f0dec7f740f2e12595600c9b3260f17153fc08b8c7c951ad9067.
#: Measured by diffing the two renderings: three lines added to the page's stylesheet -- the light
#: theme's colour scheme, the dark roles for a system set to dark, and the same for a root set to
#: dark. Nothing outside the stylesheet moves.
#: Moved by the graph redrawn, from 5b77cad5ec688588676bca3aa54084f116648206b27e3ef0b439d88cae69fb01.
#: Measured by diffing the two renderings: the stylesheet's graph rules (the box's line, the
#: link's width, the name, the state lines and the chip), and the graph's own drawing -- the same
#: three names, in wider boxes, each name whole. Nothing outside the stylesheet and the graph moves.
#: Moved by the fingerprints shown short, from c8c09fd8b2881b2fccb6dfe4c439667c4b63f5025061ed94505a8457f6663e9f.
#: Measured by diffing the two renderings: the stylesheet's rules for a fingerprint's fold, and
#: each fingerprint drawn as its fold -- 12 hex characters, the same whole value beside them. With
#: each fold read back to its whole value and those rules removed, the two renderings are equal.
#: Moved by the visual target's type scale and corners, from f0a1932189b77ce226f9e334c7cf5236a22e2ed4880a9cc176a9073630cd7f2b.
#: Measured by diffing the two renderings: one line added to the stylesheet, the scale's rule.
#: Moved by "Choose as run A" in the run's tabs, from 6344062af4d45a258c6a89c2366063ff98b21162d236ba322527a8edd1cf80d4.
#: Measured by diffing the two renderings: one link added to the head's tabs, to the run's
#: page as run A. Nothing else moves.
#: Moved by the version, 0.1.2 to 0.2.0, from aa21e3982cf46deeada85767157489ee1e6263d1d96a7b0581a4b2cec07751cc.
#: Measured by diffing the two renderings: the footer's "onetrace-console 0.1.2." only.
#: Moved by the dark theme as the default and the version, 0.2.0 to 0.2.1, from 99adf5163b1670ec8e54cfdd1f90195dec01a8adca56067b1e77d808516d238e.
#: Measured by diffing the two renderings: the stylesheet's theme rules (dark the default, light by
#: choice or a light system followed by choice, light in print) and the footer's
#: "onetrace-console 0.2.0." only.
#: Moved by marking what the head reads from the record's contents, from 58aca7003ffa82a53b7d76457f62b81c7ddecdfc860164d3a06e15643f0c5ab8.
#: Measured by diffing the two renderings: `data-from="contents"` on the "Ran as approved" rung,
#: the chips in a span that carries it, and the count of declared stages in one. The words are
#: the same.
#: Moved by the version, 0.2.1 to 0.3.0, from d4bb6b42f8ffa52c21f055ee42c469476114e081a911581516229ca2d90f6bfc.
#: Measured by diffing the two renderings: the footer's "onetrace-console 0.2.1." only.
#: Moved by the version, 0.3.0 to 0.3.1, from ae2ee920bb68f3c50940679ef5dce8ac0a04cdffcefc345f6e110e0d51a4a1c4.
#: Measured by rendering it with the version alone set back to 0.3.0: the old digest.
UNMARKED_R_CASE_SHA256 = "e12450fa1001a7b56d0cd7b00206dd5218eb5299272b26555f600c5b750595a9"
_VERIFIER_PATH = re.compile(r"\S*onetrace_verify[/\\]verify\.py")
_FINGERPRINT = re.compile(r"<!--fingerprint-->[0-9a-f]{64}<!--/fingerprint-->")
_VERIFIER_BLOCK = re.compile(r'(<pre data-layer="3">)(\[[A-Z][A-Z-]* *\] .*?)(</pre>)', re.S)
_VERIFIER_EOL = re.compile(r"\r+\n")
#: The time this console received the run, in the run page's head: the console's clock at
#: delivery, which differs between any two deliveries of the same record.
_RECEIVED = re.compile(r'received by this console <time datetime="[^"]*" title="[^"]*">[^<]*</time>')
#: The run's pipeline label in the head (its crumbs and its title): labels follow the order the
#: pipelines first arrived in, which differs between deliveries whose arrivals share a second.
_LABEL = re.compile(r'( / | · )P\d+(</h1>| / )')


def _machine_free(page: str) -> str:
    page = _VERIFIER_BLOCK.sub(lambda m: m.group(1) + _VERIFIER_EOL.sub("\n", m.group(2))
                               + m.group(3), page)
    page = _VERIFIER_PATH.sub("<verifier>", page)
    page = _RECEIVED.sub("received by this console <time>", page)
    page = _LABEL.sub(lambda m: m.group(1) + "P<n>" + m.group(2), page)
    return _FINGERPRINT.sub("<!--fingerprint--><fingerprint><!--/fingerprint-->", page)


@pytest.fixture
def windows_runs(store, monkeypatch):
    """P, Q and R checked as on Windows: the verifier's stdout in text mode, every LF a CR LF, as it
    reaches the console through the pipe -- before the viewer reads it."""
    import subprocess

    import onetrace_console.viewer.report as report
    real = subprocess.run

    def text_mode(cmd, *args, **kwargs):
        done = real(cmd, *args, **kwargs)
        if any("onetrace_verify" in str(part) for part in cmd) and isinstance(done.stdout, bytes):
            #: CR LF once, whether the platform wrote LF or, on Windows, CR LF already.
            done = subprocess.CompletedProcess(done.args, done.returncode,
                                               re.sub(rb"(?<!\r)\n", b"\r\n", done.stdout), done.stderr)
        return done
    monkeypatch.setattr(report.subprocess, "run", text_mode)
    _require_installed()
    _require_exam()
    from onetrace_console.checks import run_and_record
    return {n: run_and_record(_deliver(DAG / f"run_{n}", store), store, ran_at=FIXED_RAN_AT)
            for n in "PQR"}, store


def test_1_the_verifier_s_crlf_never_reaches_the_page(windows_runs):
    """The verifier's output in CR LF, as on
    Windows, in; no \\r on the page; the page otherwise the same as with LF."""
    import hashlib
    import json
    found, store = windows_runs
    stored = json.loads(store.get(found["R"].check_report).decode("utf-8"))
    assert "\r" not in stored["stdout"], "read as \\n where the console reads it"
    page = _case(found["R"], store)
    assert "\r" not in page
    assert (hashlib.sha256(_machine_free(page).encode("utf-8")).hexdigest()
            == UNMARKED_R_CASE_SHA256)


def test_1_the_premise_the_verifier_s_output_arrives_in_crlf(windows_runs):
    """The fixture is not vacuous: the pipe it builds carries CR LF before the viewer reads it."""
    import subprocess
    import sys

    import onetrace_console.viewer.report as report
    done = report.subprocess.run([sys.executable, "-c", "print('x')", "onetrace_verify"],
                                 capture_output=True)
    assert done.stdout == b"x\r\n", done.stdout
    assert subprocess.run is report.subprocess.run


def test_1_a_cr_outside_the_verifier_s_output_is_kept():
    """Only the verifier's own line endings are the machine's; any other CR is the page's."""
    rows = '<pre data-layer="3">[PASS   ] a: b\r\n[FAIL   ] c: d\r\n</pre>'
    other = '<pre data-layer="3">{"a": "b"}\r\n</pre><p>x\r\ny</p>'
    assert _machine_free(rows) == '<pre data-layer="3">[PASS   ] a: b\n[FAIL   ] c: d\n</pre>'
    assert _machine_free(other) == other


def test_1_no_comparison_the_page_is_unmarked_and_unchanged(runs):
    import hashlib
    found, store = runs
    page = _case(found["R"], store)
    assert (hashlib.sha256(_machine_free(page).encode("utf-8")).hexdigest()
            == UNMARKED_R_CASE_SHA256)
    #: Since step 2 the check is the installed CLI and names no verifier path;
    #: `_machine_free` still takes one out of a page from before.
    assert len(_FINGERPRINT.findall(page)) == 1 and "onetrace-verify MANIFEST.json" in page
    assert not _VERIFIER_PATH.search(page)
    assert 'data-mark=' not in page and "graph-marked-from" not in page
    assert "graph-marks-unreadable" not in page
    assert all(" · " not in t for t in _titles(page).values()), "a node carries a state"
    assert _case(found["R"], store) == page


def test_2_one_comparison_marks_every_first_difference_and_names_itself(runs):
    found, store = runs
    c = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    page = _case(found["R"], store)
    graph = _graph(page)
    assert graph.count('data-mark="first"') == 2, "zeta and alpha"
    titles = _titles(page)
    assert "First difference" in titles["zeta"] and "First difference" in titles["alpha"]
    assert "Changed after it" in titles["join"]
    line = re.search(r'<p data-section="graph-marked-from">(.*?)</p>', graph, re.S).group(1)
    assert found["P"].run_id in line and c.ran_at in line
    assert f'href="../../diff/{c.key}.html"' in line
    assert graph.index("graph-marked-from") < graph.index("<svg")


def test_3_a_newer_comparison_takes_over_the_marks_and_the_line(runs):
    found, store = runs
    compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    newer = compare(found["Q"], found["R"], store, ran_at=LATER)
    page = _case(found["R"], store)
    line = re.search(r'<p data-section="graph-marked-from">(.*?)</p>', page, re.S).group(1)
    assert found["Q"].run_id in line and LATER in line and found["P"].run_id not in line
    assert f'href="../../diff/{newer.key}.html"' in line
    assert "present in B only" in _titles(page)["zeta"], "Q's comparison, not P's"


def test_4_a_restart_draws_the_same_page_byte_for_byte(runs, tmp_path, monkeypatch):
    from onetrace_console import serve
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    #: The page states when it was generated, read from the clock; both renders read one time,
    #: so the bytes compared are the page's own, not two clock readings a second apart.
    monkeypatch.setattr(serve, "_now", lambda: GENERATED_AT)
    found, store = runs
    compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    root = store.root.parent
    _render_startup_pages(store, root)
    before = (root / "pages" / "runs" / found["R"].key / CASE).read_bytes()
    _render_startup_pages(Store(store.root), root)
    after = (root / "pages" / "runs" / found["R"].key / CASE).read_bytes()
    assert after == before and b'data-mark="first"' in after


def test_5_a_run_that_is_only_the_baseline_carries_no_marks(runs):
    found, store = runs
    unmarked = _case(found["R"], store)
    compare(found["R"], found["P"], store, ran_at=FIXED_RAN_AT)
    assert _case(found["R"], store) == unmarked


def test_6_a_corrupt_report_marks_nothing_and_says_so(runs):
    found, store = runs
    c = compare(found["P"], found["R"], store, ran_at=FIXED_RAN_AT)
    run = c.verb(DIFF)
    report = json.loads(store.get(dict(run.reports)["diff.json"]))
    report["counts"]["same"] = "99"
    bad_key = store.put(json.dumps(report).encode("utf-8"))
    reports = tuple((n, bad_key if n == "diff.json" else k) for n, k in run.reports)
    verbs = tuple(replace(v, reports=reports) if v.verb == DIFF else v for v in c.verbs)
    store.put_comparison(replace(c, verbs=verbs))
    page = _case(found["R"], store)
    assert 'data-mark=' not in page and "graph-marked-from" not in page
    assert "gave no verdicts that could be read, so none are shown on this graph" in page


def test_storing_a_comparison_re_renders_the_candidate_s_page(server):
    """Over HTTP: POST /compare stores a comparison and re-renders the candidate's pages."""
    import urllib.request
    _require_installed()
    _require_exam()
    from tests.test_serve import _post, _real_delivery
    base, store_root = server
    keys = {}
    for n in "PR":
        _, body = _post(base, "/v1/runs", _real_delivery(DAG / f"run_{n}"))
        keys[n] = json.loads(body)["run_key"]
    case = store_root / "pages" / "runs" / keys["R"] / CASE
    assert b'data-mark=' not in case.read_bytes()
    status, _ = _post(base, f"/compare?a={keys['P']}&b={keys['R']}")
    assert status == 200
    assert b'data-mark="first"' in case.read_bytes()
    with urllib.request.urlopen(base + f"/runs/{keys['R']}/{CASE}") as resp:
        assert b'data-mark="first"' in resp.read(), "the served page is the re-rendered one"
