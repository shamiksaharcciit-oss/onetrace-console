"""The cross-service link on a run's pages (`service_link`): "Called by" on the callee's case page, "Calls to other
services" on the caller's step page, `origin-<run id>.html`, and onetrace-verify's `linked runs match` rows, the
pair's checked from both sides and kept. Each present, absent, unreadable and failed by the verifier, on the runs in
`tests/format_05_link/`: three recorded with onetrace 0.8.0's release wheels as two services would record them, and
four of onetrace's own vectors."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from tests.conftest import only
from tests.test_format_03 import _tar
from tests.test_format_05_agents_runs import _verify
from tests.test_step_kinds import _text

HERE = Path(__file__).resolve().parent / "format_05_link"
RAN_AT = "2026-11-12T00:00:00+00:00"
RECORDED = ("link-desk", "link-billing", "link-garbled")
TWO_HOPS = HERE / "accept" / "A222-link-origin-two-hops"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _store(tmp_path, folders: dict[str, Path]):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store

    store = Store(tmp_path / "store")
    keys = {n: run_and_record(accept(_tar(f), store).run, store, ran_at=RAN_AT).key for n, f in folders.items()}
    return store, keys


def _drawn(store, key: str) -> dict[str, str]:
    from onetrace_console import run_index
    from onetrace_console.pages import render_execution

    with run_index.drawing(run_index.build(store)):
        return dict(render_execution(store.get_run(key), store, generated_at=RAN_AT).pages)


def _section(page: str, name: str) -> str:
    m = re.search(rf'<section data-section="{name}">.*?</section>', page, re.S)
    return m.group(0) if m else ""


def test_every_file_is_the_one_its_provenance_names_and_each_run_verifies(examined):
    said = {}
    for line in (HERE / "PROVENANCE.md").read_text(encoding="utf-8").splitlines():
        m = re.fullmatch(r"- `((?:accept|reject)/[^`]+)`: `sha256:([0-9a-f]{64})`", line.strip())
        if m:
            said[m.group(1)] = m.group(2)
    have = {
        p.relative_to(HERE).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ("accept", "reject")
        for p in (HERE / d).rglob("*")
        if p.is_file()
    }
    made = json.loads((HERE / "MADE.json").read_text(encoding="utf-8"))
    examined(len(have) + len(RECORDED), "vector files and recorded runs")
    assert have and have == said
    assert made["versions"]["onetrace"] == "0.8.0" and sorted(made["runs"]) == sorted(RECORDED)
    assert all(r["exit"] == 0 for r in made["runs"].values())
    assert all(_verify(HERE / n) == (0, "PASS", []) for n in RECORDED)
    assert _verify(HERE / "reject" / "R85-link-manifest-copy-differs") == (1, "FAIL", ["linked runs match"])
    assert _verify(HERE / "reject" / "R86-calls-status-outside") == (1, "FAIL", ["linked runs match"])


def test_present_called_by_the_calls_the_origin_page_and_the_kept_pair_check(tmp_path, examined):
    from onetrace_console import run_index, service_link

    store, keys = _store(tmp_path, {n: HERE / n for n in ("link-desk", "link-billing")})
    assert service_link.keep_linked_checks(store) == 1 and service_link.keep_linked_checks(store) == 0
    callee = _section(_drawn(store, keys["link-billing"])["case.html"], "called-by")
    calls = _section(_drawn(store, keys["link-desk"])["stage-2.html"], "calls")
    origin = service_link.origin_pages(run_index.build(store), RAN_AT)
    examined(3, "the callee's case page, the caller's step page and the origin page")
    assert f'href="../../runs/{keys["link-desk"]}/case.html"' in callee
    assert "link-desk , at step billing_call" in _text(callee)
    assert f'href="../../runs/{keys["link-desk"]}/stage-2.html" data-link-step="billing_call"' in callee
    assert f'href="../../{service_link.origin_href("link-desk")}"' in callee
    pass_row = "[PASS ] linked runs match -- link-billing: names link-desk at billing_call; the head returned is its"
    assert 'data-section="from-index"' in callee and 'data-section="from-index"' in calls
    assert pass_row in _text(callee) and pass_row in _text(calls)
    assert "[NOT-RUN] linked runs match -- link-desk: its folder was not given" in _text(callee)
    assert f'href="../../runs/{keys["link-billing"]}/case.html"' in calls
    assert re.findall(r'data-call="([^"]+)"', calls) == ["head returned", "called, head not returned"]
    assert prose_in(callee) and prose_in(calls)
    (page,) = origin.values()
    assert "Read from the run index (onetrace-console-run-index/0.3), written" in _text(page)
    assert list(origin) == ["origin-link-desk.html"]
    assert sorted(re.findall(r'data-link-run="([0-9a-f]{64})"', page)) == sorted(keys.values())


def prose_in(section: str) -> bool:
    from onetrace_console.service_link import NON_CLAIMS
    from onetrace_console.step_kinds import prose

    return prose(NON_CLAIMS) in section


def test_absent_a_caller_not_held_a_run_with_no_link_and_an_earlier_format(tmp_path, examined):
    from onetrace_console.service_link import NOT_HELD

    store, keys = _store(
        tmp_path,
        {
            "billing": HERE / "link-billing",
            "state": HERE.parent / "format_05_state" / "state-kept",
            "older": HERE.parent / "onetrace_runs" / "0.7.1" / "refund-closed",
        },
    )
    callee = _section(_drawn(store, keys["billing"])["case.html"], "called-by")
    examined(3, "a callee whose caller isn't held, a run with no link, and a format 0.4 run")
    assert f"link-desk ({NOT_HELD})" in _text(callee) and "data-link-run" not in callee
    assert "onetrace-verify, given both runs' folders" not in callee
    for name in ("state", "older"):
        assert not any(
            'data-section="called-by"' in p or 'data-section="calls"' in p for p in _drawn(store, keys[name]).values()
        )


def test_unreadable_a_link_with_status_alone_says_so_in_its_words(tmp_path, examined):
    from onetrace_console.service_link import UNREADABLE

    store, keys = _store(tmp_path, {"garbled": HERE / "link-garbled"})
    callee = _section(_drawn(store, keys["garbled"])["case.html"], "called-by")
    examined(1, "a callee given a header that does not parse")
    assert UNREADABLE.format(status="unreadable: not its form") in _text(callee)
    assert "data-link-run" not in callee


def test_malformed_a_link_the_verifier_fails_is_not_drawn_its_row_is(tmp_path, examined):
    from onetrace_console import service_link

    copies = HERE / "reject" / "R85-link-manifest-copy-differs"
    status = HERE / "reject" / "R86-calls-status-outside"
    named = HERE / "reject" / "R81-link-names-another-run"
    (callee_dir,) = (named / "linked").iterdir()
    #: Each in a store of its own: two of onetrace's vectors share a run id, and a link goes to the first run with it.
    store, keys = _store(tmp_path / "a", {"copies": copies, "status": status})
    pair, pair_keys = _store(tmp_path / "b", {"named": named, "named-callee": callee_dir})
    service_link.keep_linked_checks(pair)
    examined(3, "a callee whose copies differ, a caller whose call is out of form, and a pair that names another run")
    page = _section(_drawn(store, keys["copies"])["case.html"], "called-by")
    assert "[FAIL ] linked runs match -- the receipts' parent_link and the manifest's copies disagree" in _text(page)
    assert "data-link=" not in page
    page = _section(_drawn(store, keys["status"])["stage-2.html"], "calls")
    assert "status 'returned' is outside the four" in _text(page) and "data-call=" not in page
    page = _section(_drawn(pair, pair_keys["named"])["stage-2.html"], "calls")
    assert "[FAIL ] linked runs match -- vector-link-earlier-callee names another-run at approve_payment" in _text(page)


def test_two_hops_one_origin_page_lists_every_run_from_the_request(tmp_path, examined):
    from onetrace_console import run_index, service_link

    folders = {"c": TWO_HOPS, **{p.name: p for p in sorted((TWO_HOPS / "linked").iterdir())}}
    store, keys = _store(tmp_path, folders)
    pages = service_link.origin_pages(run_index.build(store), RAN_AT)
    examined(1, "the origin page of a request that went through two hops")
    assert list(pages) == ["origin-vector-origin-a.html"]
    listed = re.findall(r'data-link-run="([0-9a-f]{64})"', pages["origin-vector-origin-a.html"])
    assert sorted(listed) == sorted(keys.values())


def test_sabotage_a_link_drawn_around_link_to_is_named(tmp_path, monkeypatch, examined):
    """Every link to another run goes through `link_to`: with it showing nothing, no page links a run."""
    from onetrace_console import run_index, service_link

    store, keys = _store(tmp_path, {n: HERE / n for n in ("link-desk", "link-billing")})
    service_link.keep_linked_checks(store)
    monkeypatch.setattr(service_link, "link_to", lambda run_id, held, up, page="case.html", **_: "a run")
    drawn = _section(_drawn(store, keys["link-billing"])["case.html"], "called-by")
    drawn += _section(_drawn(store, keys["link-desk"])["stage-2.html"], "calls")
    drawn += "".join(service_link.origin_pages(run_index.build(store), RAN_AT).values())
    examined(3, "pages drawn with link_to showing nothing")
    assert "data-link-run" not in drawn and keys["link-desk"] not in drawn and keys["link-billing"] not in drawn


def test_windows_safe_names_and_paths(examined):
    from onetrace_console.service_link import origin_href

    examined(3, "origin pages' file names")
    assert origin_href("r:1/x") == "origin-r~3a1~2fx.html"
    assert origin_href("2026-11-06T19:10:00.000Z-a1b2") == "origin-2026-11-06T19~3a10~3a00.000Z-a1b2.html"
    assert len(origin_href("x" * 400)) < 100 and "\\" not in origin_href("a\\b")


#: Five of onetrace 0.8.0's further link reject vectors, each failing on the link itself: (the vector, the folder beside it to check it with, the page that
#: carries its link, and the FAIL the page shows).
SIX = (
    (
        "R83-link-head-not-in-chain",
        "callee",
        "stage-2.html",
        "the head returned is not in vector-link-earlier-callee's",
    ),
    ("R84-link-parent-head-not-in-chain", "caller", "case.html", "the head vector-link-earlier-caller gave is not in"),
    ("R87-calls-head-without-run", "", "stage-2.html", "calls[1]: no child_run on head returned"),
    ("R88-calls-head-bare-hex", "", "stage-2.html", "is neither sha256"),
    (
        "R317-link-origin-run-with-no-origin-in-the-receipts",
        "",
        "stage-2.html",
        "no receipt carries parent_link.origin",
    ),
)


@pytest.mark.parametrize(("name", "beside", "page", "said"), SIX, ids=[s[0] for s in SIX])
def test_each_further_reject_vector_shows_its_fail_and_draws_no_link(name, beside, page, said, tmp_path, examined):
    from onetrace_console import run_index, service_link

    folder = HERE / "reject" / name
    folders = {"run": folder, **({beside: only((folder / "linked").iterdir())} if beside else {})}
    store, keys = _store(tmp_path, folders)
    service_link.keep_linked_checks(store)
    drawn = _drawn(store, keys["run"])[page]
    section = _section(drawn, "called-by" if page == "case.html" else "calls")
    examined(1, f"{name}'s page")
    assert "[FAIL ]" in _text(section) and said in _text(section)
    assert "data-link-run" not in section and "data-link-step" not in section
    assert service_link.origin_pages(run_index.build(store), RAN_AT) == {}


TWIN = HERE.parent / "format_05_link_twin"


def test_a_shared_run_id_is_picked_by_the_head_the_link_names_or_every_run_is_listed(tmp_path, examined):
    from onetrace_console import service_link
    from onetrace_console.service_link import SHARED

    store, keys = _store(
        tmp_path, {"desk": HERE / "link-desk", "twin": TWIN / "link-desk", "billing": HERE / "link-billing"}
    )
    service_link.keep_linked_checks(store)
    callee = _section(_drawn(store, keys["billing"])["case.html"], "called-by")
    caller = re.search(r'<p data-link="caller">.*?</p>', callee, re.S).group(0)
    origin = re.search(r'<p data-link="origin">.*?</p>', callee, re.S).group(0)
    examined(2, "a caller picked by its head, and an origin that names no head")
    assert keys["desk"] != keys["twin"]
    #: The head billing was given is in the first desk's chain alone: the link is to it.
    assert re.findall(r'data-link-run="([0-9a-f]{64})"', caller) == [keys["desk"]]
    assert "names link-desk at billing_call" in _text(callee)
    #: The origin names no head: both runs are listed, and neither is linked alone.
    assert "data-link-run" not in origin and SHARED.format(n=2) in _text(origin)
    assert sorted(re.findall(r'data-link-shared="([0-9a-f]{64})"', origin)) == sorted([keys["desk"], keys["twin"]])


def test_two_of_onetrace_s_vectors_sharing_a_run_id_are_told_apart_by_the_head(tmp_path, examined):
    """R81's callee and R85's run are both `vector-link-earlier-callee`. R81's call names a head that its own callee's
    chain does not hold (that is R81's FAIL) and R85's chain does: the run picked is the one whose chain holds it."""
    from onetrace_console import service_link

    named = HERE / "reject" / "R81-link-names-another-run"
    store, keys = _store(
        tmp_path,
        {
            "caller": named,
            "callee": only((named / "linked").iterdir()),
            "other": HERE / "reject" / "R85-link-manifest-copy-differs",
        },
    )
    receipts, _, _ = service_link.context(store.get_run(keys["caller"]), store)
    head = next(c["child_head"] for r in receipts for c in r.get("calls") or [] if c.get("child_head"))
    service_link.keep_linked_checks(store)
    examined(1, "the run a call to a shared run id is checked with")
    assert service_link.chain_holds(store, keys["other"], head)
    assert not service_link.chain_holds(store, keys["callee"], head)
    assert [(c.key, e.key) for c, e in service_link.pairs(store)] == [(keys["caller"], keys["other"])]
    assert service_link.kept_rows(store, keys["caller"], keys["callee"], "from_caller") is None


def test_a_nested_run_reads_origin_not_recorded_never_silence(tmp_path, examined):
    from onetrace_console import run_index, service_link
    from onetrace_console.service_link import ORIGIN_NOT_RECORDED

    nested = HERE / "accept" / "A224-link-origin-nested-caller"
    store, keys = _store(tmp_path, {p.name: p for p in sorted((nested / "linked").iterdir())})
    page = _drawn(store, keys["vector-origin-nested-n"])["case.html"]
    outer = _drawn(store, keys["vector-origin-nested-o"])["case.html"]
    examined(2, "a nested run's case page, and its outer run's")
    assert ORIGIN_NOT_RECORDED in _text(_section(page, "origin"))
    assert _section(outer, "origin") == "" and _section(outer, "called-by") == ""
    origins = {r["key"]: r.get("origin") for r in run_index.build(store)["runs"]}
    assert origins[keys["vector-origin-nested-n"]] is None
    assert origins[keys["vector-origin-nested-o"]] == "vector-origin-nested-o"
    assert service_link.origin_pages(run_index.build(store), RAN_AT) == {}


def test_the_kept_pair_check_is_keyed_by_both_heads_and_says_when_it_ran(tmp_path, monkeypatch, examined):
    from onetrace_console import service_link

    store, keys = _store(tmp_path, {n: HERE / n for n in ("link-desk", "link-billing")})
    assert service_link.keep_linked_checks(store) == 1
    ran = service_link.kept_at(store, keys["link-desk"], keys["link-billing"])
    callee = _section(_drawn(store, keys["link-billing"])["case.html"], "called-by")
    calls = _section(_drawn(store, keys["link-desk"])["stage-2.html"], "calls")
    #: A redraw runs nothing; a callee whose chain head differs is a new pair, checked again.
    assert service_link.keep_linked_checks(store) == 0
    real = store.get_run
    monkeypatch.setattr(
        store,
        "get_run",
        lambda k: replace(real(k), chain_head="sha256:" + "0" * 64) if k == keys["link-billing"] else real(k),
    )
    examined(3, "a pair checked once, its pages, and the same pair with another head")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", ran)
    assert service_link.CHECK_AT.format(at=ran) in _text(callee) and service_link.CHECK_AT.format(at=ran) in _text(
        calls
    )
    assert service_link.kept_rows(store, keys["link-desk"], keys["link-billing"], "from_caller") is None


def test_a_fail_elsewhere_in_the_record_leaves_the_link_drawn_and_shows_on_its_pages(tmp_path, examined):
    """R316's FAIL is an output file, not its link: the link is drawn, and the FAIL shows on the run's pages."""
    from onetrace_console import run_index, service_link

    store, keys = _store(tmp_path, {"run": HERE / "reject" / "R316-link-origin-outer-folder-missing-and-a-fail"})
    pages = _drawn(store, keys["run"])
    section = _section(pages["case.html"], "called-by")
    examined(2, "the case page of a run whose output file fails, and its origin page")
    assert 'data-link="caller"' in section and "vector-origin-nested-n" in _text(section)
    assert "output artifact 'out.json' matches" not in _text(section)
    assert "[FAIL ] receipts/01-quote.json: output artifact 'out.json' matches" in _text(pages["proof.html"])
    assert list(service_link.origin_pages(run_index.build(store), RAN_AT)) == ["origin-vector-origin-nested-o.html"]


def test_a_fail_on_the_record_s_integrity_withholds_the_link(tmp_path, examined):
    """A receipt changed after it was written: the chain and the manifest's agreement FAIL, every member is doubtful,
    and the link drawn from the record is withheld, its integrity FAIL rows in its place."""
    import shutil

    from onetrace_console import run_index, service_link

    changed = tmp_path / "link-billing"
    shutil.copytree(HERE / "link-billing", changed)
    receipt = sorted((changed / "receipts").glob("*.json"))[1]
    data = receipt.read_bytes()
    receipt.write_bytes(data.replace(b'"price"', b'"prics"', 1))
    store, keys = _store(tmp_path / "s", {"desk": HERE / "link-desk", "billing": changed})
    service_link.keep_linked_checks(store)
    section = _section(_drawn(store, keys["billing"])["case.html"], "called-by")
    examined(1, "a callee whose receipt was changed after it was written")
    assert data != receipt.read_bytes()
    assert "digest matches the manifest" in _text(section) and "[FAIL ]" in _text(section)
    assert 'data-link="caller"' not in section and "data-link-run" not in section
    assert service_link.origin_pages(run_index.build(store), RAN_AT) == {}
