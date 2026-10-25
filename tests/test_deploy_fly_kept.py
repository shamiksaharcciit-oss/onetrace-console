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
from tests.test_explain_panel import LABEL, _panel, _text

REPO = Path(__file__).resolve().parent.parent
KEPT = REPO / "deploy" / "fly" / "kept"
MODEL = "anthropic:claude-sonnet-4-6"
#: Each kept record, and the comparison it explains (baseline, candidate), as kept/README.md lists them.
RECORDS = {
    "2026-10-25T13-45-05.744195Z": ("p1-02-baseline-set2", "p1-08-candidate-set2"),
    "2026-10-25T13-39-09.069959Z": ("p5-32-pump-baseline", "p5-33-pump-offset-changed"),
    "2026-10-25T13-50-49.727866Z": ("p8-42-invoice-tolerance-2pct", "p8-43-invoice-tolerance-5pct"),
    "2026-10-25T13-42-26.188702Z": ("p9-46-torque-baseline", "p9-48-torque-one-bolt-low"),
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
    build_public(folder, runs_from=KEPT, explanations=KEPT)
    store = Store(folder / "store" / "store")
    runs = {r.key: r.run_id for r in store.runs()}
    pairs = {(runs[c.run_a], runs[c.run_b]): c for c in store.comparisons()}
    return folder, store, pairs


def _page(folder: Path, comparison) -> str:
    return (folder / "store" / "pages" / "diff" / f"{comparison.key}.html").read_text(encoding="utf-8")


def kept_problems(folder, store, pairs) -> list[str]:
    """Where the build did not keep exactly the four, each on its comparison's page as the command
    wrote it: its label, its model, each claim with its cites, no button."""
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
        if LABEL not in said or f"Model: {MODEL}" not in said or e["model"] != MODEL:
            out.append(f"{rid}: its label or its model is not on its page")
        for claim in e["claims"]:
            if " ".join(claim["text"].split()) not in said:
                out.append(f"{rid}: a claim is not on its page: {claim['text'][:60]!r}")
        if said.count("shown by") != len(e["claims"]):
            out.append(f"{rid}: {said.count('shown by')} claims cited, {len(e['claims'])} made")
        out += [f"{rid}: {p}" for p in read_only_problems(panel)]
    return out


def test_the_build_keeps_the_four_explanations_each_on_its_page_read_only(built, examined):
    folder, store, pairs = built
    examined(len(RECORDS), "kept explanations")
    assert kept_problems(folder, store, pairs) == []


def test_sabotage_an_explanation_shown_on_another_page_is_named(built, examined):
    folder, store, pairs = built
    p1, p5 = RECORDS["2026-10-25T13-45-05.744195Z"], RECORDS["2026-10-25T13-39-09.069959Z"]
    swapped = {**pairs, p1: pairs[p5], p5: pairs[p1]}
    examined(1, "planted pairing")
    assert kept_problems(folder, store, swapped) != []


def test_every_other_comparisons_page_says_none_is_kept(built, examined):
    from onetrace_console import explain
    folder, store, pairs = built
    others = [c for pair, c in pairs.items() if pair not in RECORDS.values()]
    examined(len(others), "comparisons with none kept")
    assert others
    for c in others:
        assert explain.KEPT_NONE in _text(_panel(_page(folder, c))), c.key


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
    rid = "2026-10-25T13-50-49.727866Z"
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
WITH_KEPT = AS_BEFORE + ["--runs-from", "/app/deploy/fly/kept", "--explanations", "/app/deploy/fly/kept"]
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
