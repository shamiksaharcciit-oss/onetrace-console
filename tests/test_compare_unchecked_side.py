"""A run that couldn't be checked never compares as Same, and gives no first difference.

Where either side of a comparison couldn't be checked, what the SDK's `diff` says of the pair is
not shown as a finding: the comparison page and the start-up list say "Couldn't check" for that
side, and no page shows a Same or a First difference read from it -- not the comparison page, its
text diff page, the run page's graph and chip, nor the Overview's "Vs baseline".

The SDK's `diff` reads only the receipts it is given: it calls a run the verifier refuses
identical to its baseline. A run whose receipts carry a format the check does not implement --
`stage-receipt/1.0`, re-chained so it is otherwise consistent -- is refused when it is loaded, so
it is never compared at all. A run that is loaded and whose check could not be done (the check
said NOT VERIFIED) is stored with that reading, as the check runner stores it; that is the side
these tests compare.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
RUNS = REPO / "examples" / "reference-demo" / "runs"
GENERATED_AT = "2026-01-01T00:00:00+00:00"
NOT_VERIFIED = "not verified; the check says: 6 pass, 0 fail, 1 not-run  ->  NOT VERIFIED (x)"


def _text(page: str) -> str:
    page = re.sub(r"<style.*?</style>|<script.*?</script>", " ", page, flags=re.S)
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", page)).split())


def _load(tmp_path: Path, names: dict[str, str]):
    """`names`: {folder: the reference demo run it copies}."""
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path / "runs"
    folder.mkdir()
    for name, source in names.items():
        shutil.copytree(RUNS / source, folder / name)
    store = Store(tmp_path / "store")
    loaded = load_folder(folder, store, Config())
    return folder, store, {r.name: r.run for r in loaded.runs}


def _not_verified(run, store):
    """The run as the check runner stores a check that said NOT VERIFIED: couldn't check."""
    from onetrace_console.checks import COULD_NOT_CHECK
    out = replace(run, check_verdict=COULD_NOT_CHECK, check_exit="2", agree="couldnt-check",
                  agree_why="", check_note=NOT_VERIFIED)
    store.put_run(out)
    return out


def _compared(store, a, b):
    from onetrace_console.compare import compare
    return compare(a, b, store, ran_at=GENERATED_AT)


def _diff_page(comparison, store) -> str:
    from onetrace_console.render import render_diff
    return render_diff(comparison, store, generated_at=GENERATED_AT)


VERDICT_CELLS = re.compile(r'data-result="(same|FIRST DIFFERENCE|reconverged|downstream)"')


@pytest.mark.parametrize("side", ["candidate", "baseline"])
def test_the_comparison_page_says_couldnt_check_for_that_side_and_no_verdict(tmp_path, examined, side):
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-2": "day-2"})
    a, b = runs["day-1"], runs["day-2"]
    if side == "candidate":
        b = _not_verified(b, store)
    else:
        a = _not_verified(a, store)
    page = _diff_page(_compared(store, a, b), store)
    text = _text(page)
    examined(1, "comparison page")
    run_id = "demo-run-2" if side == "candidate" else "demo-run-1"
    assert re.search(rf"Couldn't check[^.]*{run_id}", text), text[:1500]
    assert not VERDICT_CELLS.findall(page), VERDICT_CELLS.findall(page)
    assert "First difference" not in text and "First differences" not in text
    assert "The two runs do not differ" not in text


def test_an_unchecked_candidate_is_never_same_on_any_page(tmp_path, examined):
    """A pair the SDK calls identical: the candidate couldn't be checked, so nothing says Same."""
    from onetrace_console.overview import vs_baseline
    from onetrace_console.pages import CASE, RUN_PROOF, render_execution
    from onetrace_console.textdiff_page import render_text_diff_page
    _folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-1-copy": "day-1"})
    a, b = runs["day-1"], runs["day-1-copy"]
    assert a.key != b.key
    b = _not_verified(b, store)
    comparison = _compared(store, a, b)
    examined(4, "pages read")
    assert vs_baseline(b, store) == ("couldnt-check", "Couldn't check")
    drawn = render_execution(b, store, generated_at=GENERATED_AT).pages
    #: Both views: the comparison chip is on "Proof" only for a run that couldn't be checked.
    case = drawn[CASE] + drawn[RUN_PROOF]
    assert "No difference found vs" not in _text(case)
    assert "Couldn't check the comparison with" in _text(case)
    assert not re.search(r'data-mark="first"', case)
    page = _diff_page(comparison, store)
    assert not VERDICT_CELLS.findall(page)
    assert "The two runs do not differ" not in _text(page)
    assert render_text_diff_page(comparison, store, generated_at=GENERATED_AT) is None


def test_the_start_up_list_says_couldnt_check_for_that_side(tmp_path, examined):
    from onetrace_console.folder_load import Loaded, LoadedRun, announce
    folder, store, runs = _load(tmp_path, {"day-1": "day-1", "day-2": "day-2"})
    b = _not_verified(runs["day-2"], store)
    comparison = _compared(store, runs["day-1"], b)
    loaded = Loaded((LoadedRun("day-1", runs["day-1"]), LoadedRun("day-2", b)), comparison)
    lines, _ = announce(folder, loaded, store)
    examined(1, "start-up list")
    compared = [t for t, _ in lines if t.startswith("compared")]
    assert compared == ["compared day-1 with day-2: Couldn't check day-2, so no verdict is shown"], lines


def _rechained(run_dir: Path, receipt_format: str) -> None:
    """Every receipt given `receipt_format`, and the chain made consistent again: each receipt's
    `prev`, each `receipt:` input's digest and size, the manifest's entries and its chain head."""
    import onetrace.canonical as canonical
    m = json.loads((run_dir / "MANIFEST.json").read_bytes())
    prev, digests, sizes = None, {}, {}
    for entry in m["chain"]:
        f = run_dir / entry["file"]
        r = json.loads(f.read_bytes())
        r["format"], r["prev"] = receipt_format, prev
        for i in r.get("inputs", []):
            stage = i["name"][len("receipt:"):]
            if i["name"].startswith("receipt:") and stage in digests:
                i["digest"], i["bytes"] = digests[stage], str(sizes[stage])
        data = canonical.canonicalize(r)
        f.write_bytes(data)
        prev = entry["digest"] = digests[entry["stage"]] = canonical.digest(data)
        sizes[entry["stage"]] = len(data)
    m["chain_head"] = prev
    (run_dir / "MANIFEST.json").write_bytes(canonical.canonicalize(m))


def test_a_run_the_check_could_not_check_is_one_the_verbs_could_not_check_and_no_verdict_is_shown(
        tmp_path, examined):
    """Not the stand-in: a run whose check really said NOT VERIFIED. Its receipts carry the preview
    format inside a chain of the current one (re-chained, its signature taken out, so nothing else
    fails), which is loaded and stored as couldn't check. The SDK's verbs then answer "could not
    check" (exit 4) themselves, and the page shows that side as couldn't check, with no verdict."""
    from onetrace_console.checks import COULD_NOT_CHECK
    from onetrace_console.compare import DIFF, LOCALIZE, report_text
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path / "runs"
    folder.mkdir()
    for name in ("day-1", "day-2"):
        shutil.copytree(RUNS / name, folder / name)
    shutil.rmtree(folder / "day-2" / "signatures")
    _rechained(folder / "day-2", "stage-receipt/0.0-preview")
    store = Store(tmp_path / "store")
    loaded = load_folder(folder, store, Config(), compare=("day-1", "day-2"))
    runs = {r.name: r.run for r in loaded.runs}
    assert (runs["day-2"].check_verdict, runs["day-2"].check_exit) == (COULD_NOT_CHECK, "2")
    comparison = loaded.comparison
    examined(3, "verbs' answers and the comparison page")
    for verb in (DIFF, LOCALIZE):
        assert comparison.verb(verb).exit_status == "4", (verb, comparison.verb(verb).exit_status)
        assert "could not check" in report_text(comparison, verb, store), verb
    #: The page before it is split into its two views: every part of both.
    page = _diff_page(comparison, store)
    text = _text(page)
    assert re.search(r"Couldn't check[^.]*demo-run-2", text), text[:1500]
    assert not VERDICT_CELLS.findall(page), VERDICT_CELLS.findall(page)
    assert "First difference" not in text and "The two runs do not differ" not in text


def test_a_run_whose_receipts_carry_an_unimplemented_major_format_is_never_compared(tmp_path, examined):
    from onetrace_console.config import Config
    from onetrace_console.folder_load import announce, load_folder
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    folder = tmp_path / "runs"
    folder.mkdir()
    shutil.copytree(RUNS / "day-1", folder / "day-1")
    shutil.copytree(RUNS / "day-1", folder / "day-1-next")
    _rechained(folder / "day-1-next", "stage-receipt/1.0")
    store = Store(tmp_path / "store")
    loaded = load_folder(folder, store, Config(), compare=("day-1", "day-1-next"))
    examined(1, "re-chained run")
    by_name = {r.name: r for r in loaded.runs}
    assert by_name["day-1-next"].run is None and "stage-receipt/1.0" in by_name["day-1-next"].refused
    assert loaded.comparison is None and list(store.comparisons()) == []
    said = [t for t, _ in announce(folder, loaded, store)[0]]
    assert "not compared: day-1-next did not load" in said
    assert not any("Same" in t or "First difference" in t for t in said)
