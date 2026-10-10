"""`onetrace-console <runs folder>` and `onetrace-console demo`: load runs from disk, then serve.

A folder load delivers every run folder in the folder it is given (each one holding a
MANIFEST.json) through the same path `POST /v1/runs` takes: the folder becomes a delivery with
its SHA256SUMS, `ingest.accept` takes it or refuses it, and an accepted run is checked. It
compares nothing unless asked to (`--compare A B`, by folder name, A the baseline).

`demo` is a folder load of the reference demo's two runs, which ship inside this package. They
are copied into `onetrace-console-demo/` under the folder it is started from, with the demo's
trust file, and compared. The demo keeps its store in that folder too, so its trust file never
re-checks runs stored anywhere else.

`demo --public --build <folder>` builds the read-only public demo (`public.py`) into a new folder:
the same two runs and trust file, delivered, checked and compared, and every page drawn with the
public banner -- then it exits. A public console serves that folder's store as it is and draws
nothing. `demo --public` builds one into a temporary folder and serves it on 127.0.0.1, to try.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.config import Config
from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME
from onetrace_console.store import StoredRun, Store
from onetrace_console.words import VERDICT_WORDS

DEMO_FOLDER = "onetrace-console-demo"
DEMO_PAIR = ("day-1", "day-2")
#: onetrace holds this file in a run's folder while it is recording, and removes it after.
RECORDING_LOCK = ".lock"


class LoadRefused(Exception):
    """Nothing can be loaded as asked; the message says why and what to do."""


@dataclass(frozen=True)
class LoadedRun:
    name: str                       # the run folder's name
    run: StoredRun | None           # the stored, checked run; None when refused
    refused: str = ""               # why it was not loaded


@dataclass(frozen=True)
class Loaded:
    runs: tuple[LoadedRun, ...]
    comparison: object | None = None    # the StoredComparison asked for, if made
    compare_note: str = ""              # why the comparison asked for was not made


def run_folders(folder: Path) -> list[Path]:
    if not folder.is_dir():
        raise LoadRefused(f"{folder} is not a folder.")
    found = sorted((p for p in folder.iterdir() if p.is_dir() and (p / MANIFEST_NAME).is_file()),
                   key=lambda p: p.name)
    if not found:
        hint = (f" {folder} is itself a run folder: name the folder that holds it."
                if (folder / MANIFEST_NAME).is_file() else "")
        raise LoadRefused(f"no run folders in {folder}: a run folder is one holding a "
                          f"{MANIFEST_NAME}.{hint}")
    return found


def delivery(run_dir: Path) -> bytes:
    """The run folder as `POST /v1/runs` takes it: every file, and a SHA256SUMS covering them.
    A SHA256SUMS the folder holds is delivered as it is, so the console checks it."""
    files: dict[str, bytes] = {}
    for path in sorted(run_dir.rglob("*")):
        rel = path.relative_to(run_dir).as_posix()
        if path.is_symlink():
            raise _Undeliverable(f"it holds a link ({rel}), and a run folder holds files only")
        if path.name == RECORDING_LOCK:
            raise _Undeliverable(f"it is still being recorded (onetrace's {RECORDING_LOCK} is in "
                                 f"it); load it once the run has finished")
        if path.is_file():
            files[rel] = path.read_bytes()
    if SUMS_NAME not in files:
        files[SUMS_NAME] = "".join(f"{hashlib.sha256(b).hexdigest()}  {p}\n"
                                   for p, b in sorted(files.items())).encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for rel, blob in files.items():
            info = tarfile.TarInfo(name=rel)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


class _Undeliverable(Exception):
    pass


def load_folder(folder: Path, store: Store, config: Config, *,
                compare: tuple[str, str] | None = None) -> Loaded:
    """Deliver, check and (if asked) compare; nothing is stored when the request itself is wrong."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import Rejection, accept

    found = run_folders(folder)
    names = [p.name for p in found]
    if compare is not None:
        missing = [n for n in compare if n not in names]
        if missing:
            raise LoadRefused(f"--compare names {', '.join(missing)}, not a run folder in {folder} "
                              f"(there: {', '.join(names)}).")
    loaded: list[LoadedRun] = []
    for run_dir in found:
        try:
            data = delivery(run_dir)
        except _Undeliverable as e:
            loaded.append(LoadedRun(run_dir.name, None, f"not loaded: {e}"))
            continue
        except OSError as e:
            loaded.append(LoadedRun(run_dir.name, None, f"not loaded: cannot read it: {e}"))
            continue
        accepted = accept(data, store, limits=config)
        if isinstance(accepted, Rejection):
            loaded.append(LoadedRun(run_dir.name, None,
                                    "refused: " + "; ".join(r.strip() for r in accepted.rows)))
            continue
        run = run_and_record(accepted.run, store, trust_file=config.trust_file)
        loaded.append(LoadedRun(run_dir.name, run))
    comparison, note = None, ""
    if compare is not None:
        comparison, note = _compare(loaded, compare, store)
    return Loaded(tuple(loaded), comparison, note)


def _compare(loaded: list[LoadedRun], pair: tuple[str, str], store: Store):
    from onetrace_console.compare import ComparisonError, compare
    from onetrace_console.store import SameFileError
    by_name = {r.name: r for r in loaded}
    a, b = by_name[pair[0]], by_name[pair[1]]
    if a.run is None or b.run is None:
        return None, f"not compared: {', '.join(r.name for r in (a, b) if r.run is None)} did not load"
    if a.run.key == b.run.key:
        return None, f"not compared: {a.name} and {b.name} are the same run"
    try:
        return compare(a.run, b.run, store), ""
    except (ComparisonError, SameFileError) as e:
        return None, f"not compared: {e}"


def announce(folder: Path, loaded: Loaded) -> tuple[list[tuple[str, str]], str]:
    """What to print once the console is listening, as (text, page path or None) pairs, and the
    page `--open` opens: the comparison when one was made, otherwise the overview ("")."""
    lines: list[tuple[str, str | None]] = []
    ok = [r for r in loaded.runs if r.run is not None]
    lines.append((f"loaded {len(ok)} of {len(loaded.runs)} run folders from {folder}", None))
    width = max(len(r.name) for r in loaded.runs)
    for r in loaded.runs:
        if r.run is None:
            lines.append((f"  {r.name.ljust(width)}  {r.refused}", None))
        else:
            word = VERDICT_WORDS.get(r.run.check_verdict, r.run.check_verdict)
            lines.append((f"  {r.name.ljust(width)}  {word}", f"runs/{r.run.key}/case.html"))
    opened = ""
    if loaded.comparison is not None:
        by_key = {r.run.key: r.name for r in ok}
        cmp = loaded.comparison
        opened = f"diff/{cmp.key}.html"
        lines.append((f"compared {by_key[cmp.run_a]} with {by_key[cmp.run_b]}:", opened))
    elif loaded.compare_note:
        lines.append((loaded.compare_note, None))
    lines.append(("overview:", ""))
    return lines, opened


def demo_folder(cwd: Path) -> Path:
    """Copy the reference demo's runs and trust file into `onetrace-console-demo/`, or check that
    the copy already there is the shipped one. Returns that folder."""
    return _demo_copy(cwd / DEMO_FOLDER)


def _demo_copy(target: Path) -> Path:
    from importlib.resources import as_file, files
    with as_file(files("onetrace_console") / "reference_demo") as shipped:
        shipped = Path(shipped)
        want = {p.relative_to(shipped).as_posix(): p for p in sorted(shipped.rglob("*"))
                if p.is_file() and "__pycache__" not in p.parts}
        if target.exists():
            have = {p.relative_to(target).as_posix() for p in target.rglob("*")
                    if p.is_file() and p.relative_to(target).parts[0] in ("runs", "trust.json")}
            changed = sorted(rel for rel in set(want) | have
                             if rel not in want or rel not in have
                             or (target / rel).read_bytes() != want[rel].read_bytes())
            if changed:
                raise LoadRefused(
                    f"{target} is not the demo as shipped: {', '.join(changed[:5])}"
                    f"{' and more' if len(changed) > 5 else ''} differ. Remove {target.name}, or "
                    f"run the demo from another folder.")
            return target
        for rel, src in want.items():
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, target / rel)
    return target


def build_public(folder: Path) -> tuple[list[tuple[str, str | None]], str]:
    """Build the public demo into `folder`, which must not exist yet or be empty: the shipped runs
    and trust file, the runs delivered, checked and compared, and every page drawn as a public
    console serves it. Returns what to print once it is served, and the page `--open` opens."""
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise LoadRefused(f"{folder} is not a new, empty folder; the public demo is built into one.")
    _demo_copy(folder)
    store_root = folder / "store"
    config = Config(public=True, store_root=str(store_root), trust_file=str(folder / "trust.json"),
                    sign_in={**Config().sign_in, "enabled": False})
    store = Store(store_root / "store")
    loaded = load_folder(folder / "runs", store, config, compare=DEMO_PAIR)
    _render_startup_pages(store, store_root, config)
    return announce(folder / "runs", loaded)


def main(argv: list[str], *, demo: bool) -> int:
    import argparse

    from onetrace_console.config import ENV_VAR
    from onetrace_console.serve import main as serve_main

    parser = argparse.ArgumentParser(
        prog="onetrace-console demo" if demo else "onetrace-console",
        description=("Copy the reference demo's two runs into ./onetrace-console-demo, load them, "
                     "compare them, and serve them on 127.0.0.1." if demo else
                     "Load every run folder in a folder, then serve them on 127.0.0.1."))
    if not demo:
        parser.add_argument("folder", metavar="runs-folder", help="the folder holding run folders")
        parser.add_argument("--compare", nargs=2, metavar=("A", "B"),
                            help="compare run folder A (the baseline) with run folder B")
    if demo:
        parser.add_argument("--public", action="store_true",
                            help="the read-only public demo: every write refused, a banner on "
                                 "every page")
        parser.add_argument("--build", type=Path, metavar="FOLDER", default=None,
                            help="with --public: build the public demo into a new folder and exit")
    parser.add_argument("--open", action="store_true", help="open the page in your browser")
    parser.add_argument("--port", type=int, default=None,
                        help="the port to listen on (default: 8080, or the configuration file's)")
    args = parser.parse_args(argv)
    if args.port is not None and not 0 < args.port < 65536:
        parser.error("--port takes a TCP port, 1 to 65535")
    if demo and args.build is not None and not args.public:
        parser.error("--build builds the public demo: give --public with it")
    if demo and args.public:
        return _public_demo(args)

    if demo:
        if os.environ.get(ENV_VAR) is not None:
            print(f"refusing to start the demo: {ENV_VAR} is set. The demo runs in local mode, "
                  f"with its own store and trust file.\nfix: run it without {ENV_VAR}.",
                  file=sys.stderr)
            return 1
        try:
            folder = demo_folder(Path.cwd())
        except LoadRefused as e:
            print(f"refusing to start the demo: {e}", file=sys.stderr)
            return 1
        runs, pair = folder / "runs", DEMO_PAIR
        overrides = {"store_root": str(folder / "store"), "trust_file": str(folder / "trust.json")}
    else:
        runs, pair, overrides = Path(args.folder), tuple(args.compare) if args.compare else None, {}
        try:
            run_folders(runs)
        except LoadRefused as e:
            print(f"refusing to start: {e}", file=sys.stderr)
            return 1
    if args.port is not None:
        overrides["port"] = args.port

    def prepare(store: Store, config: Config):
        loaded = load_folder(runs, store, config, compare=pair)
        return announce(runs, loaded)

    return serve_main([], overrides=overrides, prepare=prepare, open_browser=args.open)



def _public_demo(args) -> int:
    """`demo --public --build <folder>`, or `demo --public` built in a temporary folder and served."""
    import tempfile

    from onetrace_console.config import ENV_VAR
    from onetrace_console.serve import main as serve_main
    if args.build is not None:
        if args.open or args.port is not None:
            print("refusing: --build builds the public demo and exits; it serves nothing, so it "
                  "takes no --open or --port.", file=sys.stderr)
            return 2
        try:
            build_public(args.build)
        except LoadRefused as e:
            print(f"refusing to build the public demo: {e}", file=sys.stderr)
            return 1
        print(f"built the public demo in {args.build}: its store is {args.build / 'store'}, its "
              f"trust file {args.build / 'trust.json'}")
        return 0
    if os.environ.get(ENV_VAR) is not None:
        print(f"refusing to start the demo: {ENV_VAR} is set. The demo runs in local mode, "
              f"with its own store and trust file.\nfix: run it without {ENV_VAR}.",
              file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory(prefix="onetrace-console-public-demo-") as tmp:
        folder = Path(tmp) / "demo"
        ready = build_public(folder)
        overrides = {"public": True, "store_root": str(folder / "store"),
                     "trust_file": str(folder / "trust.json")}
        if args.port is not None:
            overrides["port"] = args.port
        return serve_main([], overrides=overrides, announce=ready, open_browser=args.open)
