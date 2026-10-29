"""`deploy/fly/kept/`: the hosted demo built from fixed inputs, with four kept explanations.

The Dockerfile builds with `--runs-from deploy/fly/kept --explanations deploy/fly/kept` where the
folder is there (deploy/fly/kept/README.md). Held here, each with a sabotage that the check names:

1. the folder holds the runs, the trust file, the two build records, the four records and their
   explanations, and its README; the new build record is the original's entries for `runs/` and
   `trust.json`, and nothing else;
2. a build with the kept inputs keeps exactly the four explanations, each on its comparison's page,
   labelled as the local console labels it, with its model, its claims and their cites, and no
   button; every other comparison's page says none is kept;
3. one changed byte in a kept run stops the build, naming the file; one in a kept record is refused
   with its reason and never shown;
4. the Dockerfile's build line takes the kept inputs where the folder is there, and is the line it
   was where it is not.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_explain_kept import read_only_problems
from tests.test_explain_panel import _panel, _text

REPO = Path(__file__).resolve().parent.parent
KEPT = REPO / "deploy" / "fly" / "kept"
MODEL = "anthropic:claude-sonnet-4-6"
#: Each kept record, and the comparison it explains (baseline, candidate), as kept/README.md lists them.
RECORDS = {
    "2026-10-27T22-36-57.339892Z": ("p1-02-baseline-set2", "p1-08-candidate-set2"),
    "2026-10-27T22-39-02.564172Z": ("p5-32-pump-baseline", "p5-33-pump-offset-changed"),
    "2026-10-27T22-40-04.547696Z": ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"),
    "2026-10-27T22-40-59.861386Z": ("p9-46-torque-baseline", "p9-48-torque-one-bolt-low"),
}


# ------------------------------------------------------------------ 1. the folder and its records

def test_the_folder_holds_the_kept_inputs(examined):
    names = sorted(p.name for p in KEPT.iterdir())
    explained = sorted(p.name for p in (KEPT / "explain").iterdir())
    examined(len(names) + len(explained), "entries in deploy/fly/kept and its explain/")
    assert names == ["BUILD_RECORD.json", "BUILD_RECORD.original.json", "README.md", "explain", "runs", "trust.json"]
    assert explained == sorted([*RECORDS, *(f"{r}.explanation.json" for r in RECORDS),
                                *(f"{r}.explanation.txt" for r in RECORDS)])


def record_problems(new: dict, original: dict) -> list[str]:
    """Where the new build record is not the original's entries for runs/ and trust.json alone."""
    out = []
    if new.get("format") != original.get("format") or sorted(new.get("covers", [])) != ["runs", "trust.json"]:
        out.append(f"the new record's format or covers: {new.get('format')}, {new.get('covers')}")
    for path, digest in new.get("files", {}).items():
        if original["files"].get(path) != digest:
            out.append(f"{path}: {digest} where the original has {original['files'].get(path)}")
    kept = {p for p in original["files"] if p == "trust.json" or p.startswith("runs/")}
    out += [f"{p}: the original's entry is not in the new record" for p in sorted(kept - set(new.get("files", {})))]
    return out


def _records():
    read = lambda name: json.loads((KEPT / name).read_text(encoding="utf-8"))
    return read("BUILD_RECORD.json"), read("BUILD_RECORD.original.json")


def test_the_new_build_record_is_the_originals_entries_for_the_runs_and_the_trust_file(examined):
    from onetrace_console import demo_store
    new, original = _records()
    examined(len(new["files"]), "entries of the new build record")
    assert record_problems(new, original) == []
    assert demo_store.check_build_record(KEPT) == []


@pytest.mark.parametrize("planted", ["a changed entry", "an added entry", "an entry left out", "the original changed"])
def test_sabotage_a_record_changed_is_named(planted, examined):
    new, original = _records()
    first = next(iter(new["files"]))
    if planted == "a changed entry":
        new["files"][first] = "sha256:" + "0" * 64
    elif planted == "an added entry":
        new["files"]["runs/planted.json"] = "sha256:" + "0" * 64
    elif planted == "an entry left out":
        del new["files"][first]
    else:
        original["files"][first] = "sha256:" + "0" * 64
    examined(1, "planted record")
    assert record_problems(new, original) != []


# ------------------------------------------------------------------ 2. a build with them

@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """The demo built as the Dockerfile builds it where kept/ is there."""
    from onetrace_console.folder_load import build_public
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path_factory.mktemp("kept-build") / "demo"
    build_public(folder, runs_from=KEPT, explanations=KEPT, site_links=SITE_LINKS)
    store = Store(folder / "store" / "store")
    runs = {r.key: r.run_id for r in store.runs()}
    pairs = {(runs[c.run_a], runs[c.run_b]): c for c in store.comparisons()}
    return folder, store, pairs


SITE_LINKS = KEPT.parent / "site_links.txt"


def link_problems(pages: Path, links: list[str]) -> list[str]:
    """Each listed path that opens no page, or a moved page whose target is not a real page."""
    import re
    from onetrace_console import site_links
    out = []
    for path in links:
        f = pages / site_links.page_of(path)
        if not f.is_file():
            out.append(f"{path}: no page")
            continue
        text = f.read_text(encoding="utf-8")
        moved = re.search(r'<meta http-equiv="refresh" content="0; url=([^"]+)">', text)
        if moved is None:
            continue
        if "noindex" not in text or f"{site_links.MOVED}: " not in text:
            out.append(f"{path}: a moved page without its noindex or its line")
        target = f.parent / moved.group(1)
        if not target.is_file() or 'http-equiv="refresh"' in target.read_text(encoding="utf-8"):
            out.append(f"{path}: moved to {moved.group(1)}, which is not a page")
    return out


def test_every_link_the_public_site_makes_into_the_demo_resolves(built, examined):
    """Built as the Dockerfile builds it, with the site's links: each listed path opens a page, or a page
    sending a reader on to a real one; the site's comparison link, named by an earlier SDK build, is sent
    to this build's page between the same two runs; each listed pipeline page is there."""
    from onetrace_console import site_links
    folder, store, pairs = built
    pages = folder / "store" / "pages"
    links = site_links.read(SITE_LINKS)
    examined(len(links), "site links")
    assert len(links) == 9 and links[0] == "/"
    assert link_problems(pages, links) == []
    for path in links:
        if path.startswith("/pipeline-p"):
            assert (pages / path.lstrip("/")).is_file(), path
    old = "diff/b56e0b73e5e3324556fbdbcfc2a5561a1389322ba405c2184f2fdb620f8284da.html"
    new = pairs[("p1-02-baseline-set2", "p1-08-candidate-set2")].key
    assert not (pages / f"diff/{new}.html").read_text(encoding="utf-8").count('http-equiv="refresh"')
    assert f'url={new}.html"' in (pages / old).read_text(encoding="utf-8")
    dockerfile = (KEPT.parent / "Dockerfile").read_text(encoding="utf-8")
    assert "--site-links /app/deploy/fly/site_links.txt" in dockerfile


def test_the_moved_page_is_a_public_page_with_the_banner_once(built, examined):
    """The page at the site's old comparison name, as a public console serves it (its frame filled):
    the banner once, by the container check's own rule, the console's stylesheet, noindex, the moved
    line and its link; no other moved page is there."""
    import re
    from onetrace_console import site_links
    from onetrace_console.frame import STYLESHEET, fill
    from tools import container_check
    folder, _store, pairs = built
    old = "diff/b56e0b73e5e3324556fbdbcfc2a5561a1389322ba405c2184f2fdb620f8284da.html"
    new = pairs[("p1-02-baseline-set2", "p1-08-candidate-set2")].key
    raw = (folder / "store" / "pages" / old).read_bytes()
    served = fill(raw, old, onedoor=False, user=None, public=True).decode("utf-8")
    examined(1, "moved page")
    assert served.count(container_check._BANNER_TAG) == 1 and container_check.BANNER in served
    assert f'href="{STYLESHEET}"' in served and '<nav class="frame" data-frame>' in served
    assert '<meta name="robots" content="noindex">' in served
    #: The name in code, which breaks where it must: at 390 it would otherwise run past the window.
    assert re.search(rf'<p data-moved>{site_links.MOVED}: <a href="{new}.html"><code>{new}.html</code></a></p>', served)
    moved = [p for p in (folder / "store" / "pages").rglob("*.html") if 'http-equiv="refresh"' in p.read_text(encoding="utf-8")]
    assert [p.relative_to(folder / "store" / "pages").as_posix() for p in moved] == [old]


def test_a_listed_link_the_build_cannot_place_stops_it_naming_the_link(built, tmp_path):
    """A listed comparison name no held comparison was named by, and a listed page the build draws
    nowhere: the build stops on each, naming the link and why; nothing is written for either."""
    from onetrace_console import site_links
    folder, store, _pairs = built
    pages = tmp_path / "pages"
    (pages / "diff").mkdir(parents=True)
    unknown = "/diff/" + "0" * 64 + ".html"
    with pytest.raises(site_links.Unplaced) as got:
        site_links.write_redirects(store, pages, [unknown])
    assert unknown in str(got.value) and "no comparison it holds was named so" in str(got.value)
    with pytest.raises(site_links.Unplaced) as got:
        site_links.write_redirects(store, pages, ["/pipeline-p99.html"])
    assert "/pipeline-p99.html" in str(got.value) and "draws no page there" in str(got.value)
    assert not any(pages.rglob("*.html"))


def test_a_build_with_a_link_it_cannot_place_is_refused(tmp_path, examined):
    """Through the build itself: a site links file naming a comparison no held one reproduces."""
    from onetrace_console.folder_load import LoadRefused, build_public
    links = tmp_path / "site_links.txt"
    links.write_text("/\n/diff/" + "0" * 64 + ".html\n", encoding="utf-8")
    examined(1, "build")
    with pytest.raises(LoadRefused) as got:
        build_public(tmp_path / "demo", runs_from=KEPT, site_links=links)
    assert str(links) in str(got.value) and "0" * 64 in str(got.value)


def test_sabotage_a_link_that_resolves_nowhere_and_a_moved_page_with_no_target_are_named(built, tmp_path):
    folder, _store, _pairs = built
    pages = folder / "store" / "pages"
    assert link_problems(pages, ["/diff/" + "0" * 64 + ".html"]) == ["/diff/" + "0" * 64 + ".html: no page"]
    from onetrace_console import site_links
    (tmp_path / "diff").mkdir()
    (tmp_path / "diff" / ("1" * 64 + ".html")).write_text(site_links.page("gone.html"), encoding="utf-8")
    assert link_problems(tmp_path, ["/diff/" + "1" * 64 + ".html"]) == [
        "/diff/" + "1" * 64 + ".html: moved to gone.html, which is not a page"]


def _said(folder, run) -> tuple[str, str]:
    import html
    import re
    pages = folder / "store" / "pages" / "runs" / run.key
    both = (pages / "case.html").read_text(encoding="utf-8") + (pages / "proof.html").read_text(encoding="utf-8")
    return both, " ".join(html.unescape(re.sub(r"<[^>]+>", " ", both)).split())


def test_p10_is_recorded_again_in_1_0_beside_the_kept_draft_pair(built, examined):
    """The build from the kept runs records P10's agent pair once more, its records in
    model-call-record/1.0, signed by the kept trust file's key, and compares the new pair; the kept
    runs stay byte for byte (the build record vouches for them, as for every run)."""
    from onetrace_console import records
    from onetrace_console.demo_store import COMPARISONS_BESIDE_KEPT, RECORDED_BESIDE_KEPT
    folder, store, pairs = built
    runs = {r.run_id: r for r in store.runs()}
    examined(len(RECORDED_BESIDE_KEPT), "runs recorded beside the kept ones")
    for spec in RECORDED_BESIDE_KEPT:
        assert spec.folder in runs, spec.folder
        assert records.state(runs[spec.folder], store) == records.YES, spec.folder
    for pair in COMPARISONS_BESIDE_KEPT:
        assert pair in pairs, pair
    for name in ("pz-51-agent-baseline", "pz-53-agent-amount-changed"):
        for f in (KEPT / "runs" / name).rglob("*"):
            if f.is_file():
                assert (folder / "runs" / name / f.relative_to(KEPT / "runs" / name)).read_bytes() == f.read_bytes(), f


def test_p10_s_reference_is_the_new_baseline_and_the_kept_pair_gets_no_verdict(built, examined):
    """The new 1.0 baseline is P10's benchmark marked most recently, so the reference is made from it;
    the kept pair, whose own records could not be checked, gets no verdict word and its one line."""
    import html
    import re
    from onetrace_console import model_call, records, verdicts
    from onetrace_console.demo_store import BENCHMARK_BESIDE_KEPT
    folder, store, _pairs = built
    runs = {r.run_id: r for r in store.runs()}
    kept = [runs["pz-51-agent-baseline"], runs["pz-53-agent-amount-changed"]]
    examined(len(kept), "kept P10 runs")
    assert {records.state(r, store) for r in kept} == {records.COULDNT}
    ref = verdicts.reference_record(verdicts.pipeline_of(kept[0], store), store, compute=False)
    seal = ref["reference"]["seal"]
    assert ref["reference"]["made_from"]["run_ids"][0] == BENCHMARK_BESIDE_KEPT
    for r in kept:
        both, said = _said(folder, r)
        assert verdicts.UNCHECKED in said, r.run_id
        assert "data-verdict-lines" not in both and verdicts.word_of(r, store) is None, r.run_id
        assert f"Made by onetrace from this pipeline's benchmark, {BENCHMARK_BESIDE_KEPT}" in said, r.run_id
        assert "the one marked most recently of its 2 benchmarks" in said and seal in both, r.run_id
        line = re.search(r'<section data-section="draft-records" class="notice"><p>(.*?)</p></section>', both)
        assert line is not None, r.run_id
        assert html.unescape(re.sub(r"</?code>", "", line.group(1))) == model_call.DRAFT_LINE.format(
            formats="model-call-record/0.1-draft"), r.run_id
        assert model_call.draft_formats(r, store) == ["model-call-record/0.1-draft"]
    new = runs["pz-57-agent-amount-changed-1-0"]
    both, said = _said(folder, new)
    assert verdicts.word_of(new, store) is not None and "data-verdict-lines" in both
    assert 'data-section="draft-records"' not in both


def _page(folder: Path, comparison) -> str:
    return (folder / "store" / "pages" / "diff" / f"{comparison.key}.html").read_text(encoding="utf-8")


def kept_problems(folder, store, pairs) -> list[str]:
    """Where the build did not keep exactly the four, each on its comparison's page as the command
    wrote it, in 0.3.2's layout: the heading once, the AI line with its model, one card per claim
    with its badge, its text and a chip for each cite, no button."""
    from onetrace_console import explain
    out = []
    record = explain.kept_record(store) or {}
    got = {k["record"]: k["comparison"] for k in record.get("kept", [])}
    want = {r: pairs[pair].key for r, pair in RECORDS.items() if pair in pairs}
    if got != want or record.get("refused"):
        out.append(f"kept {got}, refused {record.get('refused')}")
    for rid, pair in RECORDS.items():
        if pair not in pairs:
            out.append(f"{pair}: no such comparison in the build")
            continue
        panel = _panel(_page(folder, pairs[pair]))
        said = _text(panel)
        e = json.loads((KEPT / "explain" / f"{rid}.explanation.json").read_text(encoding="utf-8"))
        if (said.count(explain.TITLE) != 1 or f"{explain.AI_LINE} · model {MODEL}" not in said
                or e["model"] != MODEL):
            out.append(f"{rid}: its heading, its AI line or its model is not on its page")
        cards = re.findall(r'<div class="card claim" data-claim="([^"]*)">'
                           r'<span class="badge" data-kind="[^"]*">([^<]*)</span>'
                           r'<p data-claim-text>(.*?)</p><ul class="chips"[^>]*>(.*?)</ul></div>', panel, re.S)
        if len(cards) != len(e["claims"]):
            out.append(f"{rid}: {len(cards)} cards, {len(e['claims'])} claims made")
        for claim in e["claims"]:
            mine = [c for c in cards if " ".join(_text(c[2]).split()) == " ".join(claim["text"].split())]
            if not mine:
                out.append(f"{rid}: a claim is not on its page: {claim['text'][:60]!r}")
                continue
            kind, badge, _, chips = mine[0]
            if (kind, badge) != (claim["kind"], explain.KIND_WORDS[claim["kind"]]):
                out.append(f"{rid}: a claim's badge reads {badge!r}")
            if re.findall(r'data-cite="([^"]*)"', chips) != claim["cites"]:
                out.append(f"{rid}: a claim's chips are not its cites")
        out += [f"{rid}: {p}" for p in read_only_problems(panel)]
    return out


def test_the_build_keeps_the_four_explanations_each_on_its_page_read_only(built, examined):
    folder, store, pairs = built
    examined(len(RECORDS), "kept explanations")
    assert kept_problems(folder, store, pairs) == []


def test_sabotage_an_explanation_shown_on_another_page_is_named(built, examined):
    folder, store, pairs = built
    p1, p5 = RECORDS["2026-10-27T22-36-57.339892Z"], RECORDS["2026-10-27T22-39-02.564172Z"]
    swapped = {**pairs, p1: pairs[p5], p5: pairs[p1]}
    examined(1, "planted pairing")
    assert kept_problems(folder, store, swapped) != []


def kept_checks_problems(pages: dict) -> list[str]:
    """Each kept explanation's checks on its page: each command once, in the order first asked, as
    text under "This demo runs none of them.", with no button; and no timings, nor a placeholder
    for them (the build kept none)."""
    from onetrace_console import explain
    out = []
    for rid, panel in pages.items():
        e = json.loads((KEPT / "explain" / f"{rid}.explanation.json").read_text(encoding="utf-8"))
        e["_text"] = (KEPT / "explain" / f"{rid}.explanation.txt").read_text(encoding="utf-8")
        want = list(dict.fromkeys(explain.check_lines(e)))
        rows = re.findall(r'<li data-check="\d+">(.*?)</li>', panel, re.S)
        got = [_text(r) for r in rows]
        if got != want:
            out.append(f"{rid}: checks {got}")
        if any("<button" in r for r in rows) or explain.KEPT_CHECKS not in _text(panel):
            out.append(f"{rid}: a check is offered, or the line saying none is run is missing")
        if 'data-explain="steps"' in panel or re.search(r"\bunknown\b", _text(panel), re.I):
            out.append(f"{rid}: timings, or a placeholder for them")
    return out


def _kept_pages(folder, pairs) -> dict[str, str]:
    return {rid: _panel(_page(folder, pairs[pair])) for rid, pair in RECORDS.items()}


def test_each_kept_explanation_s_commands_are_merged_and_shown_as_text_with_no_timings(built, examined):
    folder, _, pairs = built
    pages = _kept_pages(folder, pairs)
    examined(len(pages), "kept explanations' checks")
    assert sum(len(re.findall(r"^  onetrace ", (KEPT / "explain" / f"{r}.explanation.txt").read_text(encoding="utf-8"), re.M))
               for r in RECORDS) > sum(len(re.findall(r'<li data-check="', p)) for p in pages.values())
    assert kept_checks_problems(pages) == []


def test_sabotage_a_kept_explanation_drawn_unmerged_is_named(built, monkeypatch, examined):
    from onetrace_console import explain
    from onetrace_console.render import render_diff
    folder, store, pairs = built
    monkeypatch.setattr(explain, "merged_checks", lambda e: list(enumerate(explain.check_lines(e))))
    pages = {rid: _panel(render_diff(pairs[pair], store, generated_at="2026-01-01T00:00:00+00:00", public=True))
             for rid, pair in RECORDS.items()}
    examined(len(pages), "kept explanations drawn unmerged")
    assert sorted(p.split(":")[0] for p in kept_checks_problems(pages)) == sorted(
        ["2026-10-27T22-39-02.564172Z", "2026-10-27T22-40-59.861386Z"])


def test_the_build_s_copy_of_each_kept_file_is_byte_identical_to_deploy_fly_kept(built, examined):
    """What the build keeps is the folder's own bytes: each file of each record, and its explanation
    and text, under its comparison's folder in the build's store."""
    from onetrace_console import explain
    folder, store, pairs = built
    compared = 0
    for rid, pair in RECORDS.items():
        into = explain.folder_of(store, pairs[pair].key) / explain.REPORT / "explain"
        for p in sorted((KEPT / "explain").rglob("*")):
            rel = p.relative_to(KEPT / "explain")
            if p.is_file() and rel.parts[0].startswith(rid):
                assert (into / rel).read_bytes() == p.read_bytes(), rel
                compared += 1
    examined(compared, "kept files compared")
    assert compared > len(RECORDS) * 3


# ------------------------------------------------------------------ the explanation's place on the page

#: Where each part begins on a comparison page: the short answer, the explanation, "What changed
#: between the two runs", and the line that repeats diff (the last of diff's own sections).
_PLACES = {"short": '<section data-section="short-answer"', "explain": '<section data-section="explain"',
           "what": "<h2>What changed between the two runs</h2>", "repeat": 'data-section="diff-repeat"'}


def order_problems(page: str, kept: bool) -> list[str]:
    """With an explanation shown (kept, or on a local console): the short answer, then the
    explanation, then "What changed"; with none kept on a public console, the short answer, then
    "What changed", and the explanation's one line at the foot, after diff's sections."""
    at = {k: page.find(v) for k, v in _PLACES.items()}
    if any(v < 0 for v in at.values()):
        return [f"a part is not on the page: {sorted(k for k, v in at.items() if v < 0)}"]
    want = ["short", "explain", "what", "repeat"] if kept else ["short", "what", "repeat", "explain"]
    got = sorted(at, key=at.get)
    return [] if got == want else [f"order {got}"]


def _foot(page: str) -> str:
    """The page with its explanation section moved back to the foot, where 0.3.1 drew it: the end of
    the page's own content."""
    found = re.search(r'<section data-section="explain"[^>]*>.*?</section>', page, re.S).group(0)
    rest = page.replace(found, "", 1)
    at = rest.rindex("</main>")
    return rest[:at] + found + rest[at:]


@pytest.fixture(scope="module")
def local_p1(tmp_path_factory):
    """A local console's store of the kept runs, with the four explanations kept beside their
    comparisons as a press keeps one: P1's page as the local console draws it."""
    from onetrace_console import demo_store, explain
    from onetrace_console.config import Config
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    root = tmp_path_factory.mktemp("local-kept")
    store = Store(root / "store")
    with demo_store.allowing_examples(KEPT):
        demo_store.deliver(KEPT, store, Config(store_root=str(root), trust_file=str(KEPT / demo_store.TRUST_NAME)))
    record = explain.keep(KEPT, store)
    runs = {r.key: r.run_id for r in store.runs()}
    pairs = {(runs[c.run_a], runs[c.run_b]): c for c in store.comparisons()}
    assert len(record["kept"]) == len(RECORDS)
    return store, pairs[RECORDS["2026-10-27T22-36-57.339892Z"]]


def _local_page(store, comparison) -> str:
    from onetrace_console.render import render_diff
    return render_diff(comparison, store, generated_at="2026-01-01T00:00:00+00:00", public=False)


def test_the_explanation_is_directly_under_the_short_answer(built, local_p1, explain_installed, examined):
    """P1 kept on the public build and P1 on a local console with its explanation: right under the
    short answer. P8 43->44, none kept, public: its one line stays at the foot."""
    folder, _, pairs = built
    p1 = _page(folder, pairs[("p1-02-baseline-set2", "p1-08-candidate-set2")])
    p8 = _page(folder, pairs[("p8-43-invoice-tolerance-5pct", "p8-44-invoice-quantity-changed")])
    local = _local_page(*local_p1)
    examined(3, "comparison pages: P1 kept, P8 43->44 none kept, the local P1")
    assert "<article data-explanation=" in local and 'data-explain="buttons"' in local
    assert {"public P1": order_problems(p1, True), "public P8 43->44": order_problems(p8, False),
            "local P1": order_problems(local, True)} == {"public P1": [], "public P8 43->44": [], "local P1": []}


def test_no_page_of_the_kept_build_nor_the_local_p1_shows_an_escape(built, local_p1, explain_installed, examined):
    from tests.test_no_escape_shown import pages_problems
    folder, _, _ = built
    root = folder / "store" / "pages"
    pages = {p.relative_to(root).as_posix(): p.read_text(encoding="utf-8") for p in sorted(root.rglob("*.html"))}
    pages["local P1"] = _local_page(*local_p1)
    examined(len(pages), "pages: the kept build's, and the local P1")
    assert pages_problems(pages) == []


def test_sabotage_the_explanation_back_at_the_foot_is_named(built, local_p1, explain_installed, examined):
    folder, _, pairs = built
    p1 = _page(folder, pairs[("p1-02-baseline-set2", "p1-08-candidate-set2")])
    local = _local_page(*local_p1)
    examined(2, "pages with the section moved back to the foot")
    assert order_problems(_foot(p1), True) == ["order ['short', 'what', 'repeat', 'explain']"]
    assert order_problems(_foot(local), True) == ["order ['short', 'what', 'repeat', 'explain']"]


#: How onetrace-verify 0.6 words a model-call record in the earlier draft format: not checked.
DRAFT_RECORD = "model-call-record/0.1-draft: not implemented"


def _holds_draft_records(run, store) -> bool:
    """The run's own check names a model-call record in the draft format, which it does not check."""
    from onetrace_console.info_mark import rows_of
    from onetrace_console.pages import _envelope
    return any(DRAFT_RECORD in str(r.get("detail", "")) for r in rows_of(_envelope(run, store, required=False)))


def _draft_pairs(store, pairs) -> dict:
    runs = {r.key: r for r in store.runs()}
    return {pair: c for pair, c in pairs.items()
            if _holds_draft_records(runs[c.run_a], store) or _holds_draft_records(runs[c.run_b], store)}


def test_every_other_comparisons_page_says_none_is_kept(built, examined):
    """Every comparison with no kept explanation says so, but a pair whose runs hold draft model-call
    records: those runs' records could not be checked, so the page shows no verdict and no panel
    (held below), until the kept runs are recorded again in model-call-record/1.0."""
    from onetrace_console import explain
    folder, store, pairs = built
    drafts = _draft_pairs(store, pairs)
    others = [c for pair, c in pairs.items() if pair not in RECORDS.values() and pair not in drafts]
    examined(len(others), "comparisons with none kept")
    assert others
    for c in others:
        assert explain.KEPT_NONE in _text(_panel(_page(folder, c))), c.key


def test_only_the_agent_pair_s_runs_hold_draft_records_and_its_page_says_they_could_not_be_checked(built, examined):
    """The kept runs were recorded before model-call-record/1.0: P10's agent runs carry two records in
    the draft format, which onetrace-verify 0.6 names and does not check. So that pair alone reads as
    could not be checked, as the verifier reads it; no explanation is kept for it either way."""
    folder, store, pairs = built
    drafts = _draft_pairs(store, pairs)
    examined(len(pairs), "comparisons")
    assert sorted(drafts) == [("pz-51-agent-baseline", "pz-53-agent-amount-changed")], sorted(drafts)
    page = _page(folder, drafts[("pz-51-agent-baseline", "pz-53-agent-amount-changed")])
    assert "Both runs' records couldn't be checked." in _text(page)
    assert not set(drafts) & set(RECORDS.values())


# ------------------------------------------------------------------ 3. a changed byte

def _changed(path: Path) -> None:
    data = bytearray(path.read_bytes())
    i = data.index(b'"') + 1
    data[i] = ord("X") if data[i] != ord("X") else ord("Y")
    path.write_bytes(bytes(data))


def test_a_changed_byte_in_a_kept_run_stops_the_build_naming_the_file(tmp_path, examined):
    from onetrace_console.folder_load import LoadRefused, build_public
    copy = tmp_path / "kept"
    shutil.copytree(KEPT, copy)
    victim = sorted((copy / "runs").rglob("MANIFEST.json"))[0]
    _changed(victim)
    examined(1, "kept run with one byte changed")
    with pytest.raises(LoadRefused, match=re.escape(f"{victim.relative_to(copy).as_posix()} was changed")):
        build_public(tmp_path / "demo", runs_from=copy, explanations=copy)


def test_a_changed_byte_in_a_kept_record_is_refused_with_its_reason(built, tmp_path, examined):
    from onetrace_console import explain
    from onetrace_console.store import Store
    folder, _store, pairs = built
    copy = tmp_path / "kept"
    shutil.copytree(KEPT / "explain", copy / "explain")
    rid = "2026-10-27T22-40-04.547696Z"
    _changed(copy / "explain" / rid / "receipts" / "02-model.json")
    store_copy = tmp_path / "store"
    shutil.copytree(folder / "store" / "store", store_copy)
    #: The copy without what the build kept, so this keeping starts where the build's did.
    shutil.rmtree(store_copy / explain.FOLDER)
    record = explain.keep(copy, Store(store_copy))
    examined(1, "kept record with one byte changed")
    reasons = {r["file"]: r["reason"] for r in record["refused"]}
    assert reasons.get(f"explain/{rid}.explanation.json", "").startswith(explain.NOT_VERIFIED), reasons
    assert rid not in {k["record"] for k in record["kept"]} and len(record["kept"]) == len(RECORDS) - 1


# ------------------------------------------------------------------ 4. the Dockerfile's build line

def _build_line(dockerfile: str) -> str:
    """The Dockerfile's RUN that builds the demo, up to the first `&&` after it."""
    run = re.search(r"^RUN (if \[ -d deploy/fly/kept \].*?fi|python -m onetrace_console demo --public --build \S+)",
                    dockerfile, re.M | re.S)
    return run.group(1).replace("\\\n", " ") if run else ""


def _argv(dockerfile: str, tmp_path: Path, with_kept: bool) -> list[str]:
    """What the build line runs, in a folder like /app with or without deploy/fly/kept: the console
    stood in for by a printer of its arguments."""
    app = tmp_path / ("with" if with_kept else "without")
    (app / "deploy" / "fly" / ("kept" if with_kept else "")).mkdir(parents=True, exist_ok=True)
    line = _build_line(dockerfile).replace("python -m onetrace_console", "printf '%s\\n'")
    done = subprocess.run(["sh", "-c", line], cwd=app, capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    return done.stdout.split()


AS_BEFORE = ["demo", "--public", "--build", "/srv/onetrace-demo"]
#: With the kept inputs, the public site's links too (`site_links`): the build they go into is the kept one.
WITH_KEPT = AS_BEFORE + ["--runs-from", "/app/deploy/fly/kept", "--explanations", "/app/deploy/fly/kept",
                         "--site-links", "/app/deploy/fly/site_links.txt"]
needs_sh = pytest.mark.skipif(os.name == "nt" or shutil.which("sh") is None,
                              reason="the image's build line is a POSIX shell's; this host has none")


@needs_sh
def test_the_build_line_takes_the_kept_inputs_where_they_are_and_builds_as_before_where_not(tmp_path, examined):
    dockerfile = (REPO / "deploy" / "fly" / "Dockerfile").read_text(encoding="utf-8")
    examined(2, "build lines run")
    assert _argv(dockerfile, tmp_path, with_kept=True) == WITH_KEPT
    assert _argv(dockerfile, tmp_path, with_kept=False) == AS_BEFORE
    assert "COPY deploy/fly/ ./deploy/fly/" in dockerfile


@needs_sh
def test_sabotage_a_build_line_without_the_kept_inputs_is_named(tmp_path, examined):
    before = "RUN python -m onetrace_console demo --public --build /srv/onetrace-demo \\\n    && chown -R root:root /app\n"
    examined(1, "planted build line")
    assert _argv(before, tmp_path, with_kept=True) != WITH_KEPT
