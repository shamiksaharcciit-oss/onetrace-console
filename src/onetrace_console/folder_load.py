"""`onetrace-console <runs folder>` and `onetrace-console demo`: load runs from disk, then serve.

A folder load delivers every run folder in the folder it is given (each one holding a
MANIFEST.json) through the same path `POST /v1/runs` takes: the folder becomes a delivery with
its SHA256SUMS, `ingest.accept` takes it or refuses it, and an accepted run is checked. It
compares nothing unless asked to (`--compare A B`, by folder name, A the baseline).

`demo` is a folder load of the demo store (`demo_store`): the runs of its small pipelines,
recorded by the demo's builder into `onetrace-console-demo/` under the folder it is started from,
at the time it is started, with the demo's trust file, and its comparisons stored. The demo
keeps its store in that folder too, so its trust file never re-checks runs stored anywhere else.
Started again in the same folder, it re-uses the runs there, but only while every byte of them is
the one the builder's record holds.

`demo --public --build <folder>` builds the read-only public demo (`public.py`) into a new folder:
the demo store's runs and trust file, delivered, checked and compared, and every page drawn with
the public banner, and then a build record over all of it -- then it exits. A public console
serves that folder's store as it is and draws nothing. `demo --public` builds one into a
temporary folder and serves it on 127.0.0.1, to try.
"""
from __future__ import annotations

import hashlib
import io
import os
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.config import Config
from onetrace_console.oserror import shown
from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME
from onetrace_console.store import StoredRun, Store
from onetrace_console import records

DEMO_FOLDER = "onetrace-console-demo"
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


def identity(run_dir: Path) -> tuple[str, str] | None:
    """The run and chain head a run folder's MANIFEST.json names, or None where it can't be read:
    what tells two folders carrying one run apart from two runs. Its reading never refuses a folder;
    the delivery does that, in its own words."""
    from onetrace_console.bounded_json import load_json_bounded
    try:
        m = load_json_bounded((run_dir / MANIFEST_NAME).read_bytes(), "a run's manifest")
    except Exception:  # noqa: BLE001 - unreadable here is refused by the delivery, said there
        return None
    if not isinstance(m, dict):
        return None
    run_id, head = m.get("run_id"), m.get("chain_head")
    return (run_id, head) if isinstance(run_id, str) and isinstance(head, str) else None


def shared_heads(run_dirs) -> set[str]:
    """The names of the folders among `run_dirs` that carry the same run and chain head as another
    of them."""
    by_identity: dict[tuple[str, str], list[str]] = {}
    for d in run_dirs:
        found = identity(d)
        if found is not None:
            by_identity.setdefault(found, []).append(d.name)
    return {n for names in by_identity.values() if len(names) > 1 for n in names}


def deliver_one(run_dir: Path, store: Store, config: Config, *,
                shared: set[str] | None = None) -> LoadedRun:
    """One run folder, delivered and checked: what `load_folder` does for each folder at start,
    and the folder watcher for each finished run after (`watch.py`). There is no second path.

    Runs are folders, not chain heads: a folder that carries the same run and chain head as
    another folder beside it is stored under its own folder's key, and read on its own. `shared`:
    the names of such folders, where the caller has read them all already."""
    from onetrace_console.checks import check_options, run_and_record
    from onetrace_console.ingest import Rejection, accept
    if shared is None:
        shared = shared_heads(p for p in run_dir.parent.iterdir()
                              if p.is_dir() and (p / MANIFEST_NAME).is_file())
    try:
        data = delivery(run_dir)
    except _Undeliverable as e:
        return LoadedRun(run_dir.name, None, f"not loaded: {e}")
    except OSError as e:
        from onetrace_console.oserror import said
        return LoadedRun(run_dir.name, None, f"not loaded: cannot read it: {said(e)}")
    accepted = accept(data, store, limits=config, run_folder=run_dir.name,
                      shared_head=run_dir.name in shared)
    if isinstance(accepted, Rejection):
        return LoadedRun(run_dir.name, None,
                         "refused: " + "; ".join(r.strip() for r in accepted.rows))
    return LoadedRun(run_dir.name, run_and_record(accepted.run, store, **check_options(config)))


#: What a watched folder's `--compare` says while it waits for a run folder it names.
WAITING = "waiting for {names}: the comparison is made when both run folders have arrived"


def load_folder(folder: Path, store: Store, config: Config, *,
                compare: tuple[str, str] | None = None, watched: bool = False) -> Loaded:
    """Deliver, check and (if asked) compare; nothing is stored when the request itself is wrong.
    `watched`: the folder is watched while the console runs (`watch.py`), so a folder with no run
    yet is not refused, and a `--compare` naming a folder not there yet waits for it."""
    try:
        found = run_folders(folder)
    except LoadRefused:
        if not (watched and Path(folder).is_dir()):
            raise
        found = []                      # nothing yet: a watched folder waits for its runs
    names = [p.name for p in found]
    if compare is not None:
        missing = [n for n in compare if n not in names]
        if missing and watched:
            shared = shared_heads(found)
            loaded = [deliver_one(run_dir, store, config, shared=shared) for run_dir in found]
            return Loaded(tuple(loaded), None, WAITING.format(names=" and ".join(missing)))
        if missing:
            raise LoadRefused(f"--compare names {', '.join(missing)}, not a run folder in {folder} "
                              f"(there: {', '.join(names)}).")
    shared = shared_heads(found)
    loaded = [deliver_one(run_dir, store, config, shared=shared) for run_dir in found]
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


def announce(folder: Path, loaded: Loaded, store: Store) -> tuple[list[tuple[str, str]], str]:
    """What to print once the console is listening, as (text, page path or None) pairs, and the
    page `--open` opens: the comparison when one was made, otherwise the overview (""). Each run
    says its "Records agree" as its own page reads it (`records.said`)."""
    lines: list[tuple[str, str | None]] = []
    ok = [r for r in loaded.runs if r.run is not None]
    lines.append((f"loaded {len(ok)} of {len(loaded.runs)} run folders from {folder}", None))
    width = max(len(r.name) for r in loaded.runs)
    for r in loaded.runs:
        if r.run is None:
            lines.append((shown(f"  {r.name.ljust(width)}  {r.refused}"), None))
        else:
            word = records.said(r.run, store)
            lines.append((f"  {r.name.ljust(width)}  {word}", f"runs/{r.run.key}/case.html"))
    opened = ""
    if loaded.comparison is not None:
        by_key = {r.run.key: r.name for r in ok}
        cmp = loaded.comparison
        opened = f"diff/{cmp.key}.html"
        unchecked = records.unchecked_sides(cmp, store)
        said = (" " + records.UNCHECKED_SAID.format(
            names=" and ".join(by_key.get(r.key, r.run_id) for _, r in unchecked))) if unchecked else ""
        lines.append((f"compared {by_key[cmp.run_a]} with {by_key[cmp.run_b]}:{said}", opened))
    elif loaded.compare_note:
        lines.append((loaded.compare_note, None))
    lines.append(("overview:", ""))
    return lines, opened


def demo_folder(cwd: Path) -> Path:
    """Build the demo store into `onetrace-console-demo/`, or check that the one already there is
    the builder's, byte for byte (its build record). Returns that folder."""
    from onetrace_console import demo_store
    target = cwd / DEMO_FOLDER
    if not target.exists():
        demo_store.build(target)
        return target
    problems = demo_store.check_build_record(target)
    if problems:
        raise LoadRefused(
            f"{target} is not the demo as its builder made it: {'; '.join(problems[:5])}"
            f"{' and more' if len(problems) > 5 else ''}. Remove {target.name}, or run the demo "
            f"from another folder.")
    return target


def build_public(folder: Path) -> tuple[list[tuple[str, str | None]], str]:
    """Build the public demo into `folder`, which must not exist yet or be empty: the demo store's
    runs and trust file, the runs delivered, checked and compared, every page drawn as a public
    console serves it, and a build record over all of it, which a public console checks before it
    starts. Returns what to print once it is served, and the page `--open` opens."""
    from onetrace_console import demo_store
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages
    if folder.exists() and (not folder.is_dir() or any(folder.iterdir())):
        raise LoadRefused(f"{folder} is not a new, empty folder; the public demo is built into one.")
    demo_store.build(folder)
    store_root = folder / "store"
    config = Config(public=True, store_root=str(store_root),
                    trust_file=str(folder / demo_store.TRUST_NAME),
                    sign_in={**Config().sign_in, "enabled": False})
    store = Store(store_root / "store")
    #: The demo's own example inputs, its build record vouching for them, are drawn as shown.
    with demo_store.allowing_examples(folder):
        loaded = demo_store.deliver(folder, store, config)
        _render_startup_pages(store, store_root, config)
    demo_store.write_build_record(folder, (demo_store.RUNS_DIRNAME, demo_store.TRUST_NAME, "store"))
    return announce(folder / demo_store.RUNS_DIRNAME, loaded, store)


def main(argv: list[str], *, demo: bool) -> int:
    import argparse

    from onetrace_console.config import ENV_VAR
    from onetrace_console.serve import main as serve_main

    parser = argparse.ArgumentParser(
        prog="onetrace-console demo" if demo else "onetrace-console",
        description=("Build the demo store's runs into ./onetrace-console-demo, load them, "
                     "compare them, and serve them on 127.0.0.1." if demo else
                     "Load every run folder in a folder, then serve them on 127.0.0.1."))
    if not demo:
        parser.add_argument("folder", metavar="runs-folder", help="the folder holding run folders")
        parser.add_argument("--compare", nargs=2, metavar=("A", "B"),
                            help="compare run folder A (the baseline) with run folder B")
        parser.add_argument("--trust", metavar="FILE", default=None,
                            help="the signing keys you trust, an onetrace-trust/0.1 file: a run "
                                 "signed by one reads \"Signed by a known recorder: Yes\"")
        parser.add_argument("--tsa-cert", metavar="FILE", default=None,
                            help="the RFC 3161 time-stamp authority's certificate you trust, so "
                                 "a run's anchor can be checked (with --tsa-root)")
        parser.add_argument("--tsa-root", metavar="FILE", action="append", default=[],
                            help="the root that certificate chains to; may be given more than once")
        parser.add_argument("--watch-interval", metavar="N", type=float, default=None,
                            help="read the folder for new runs every N seconds while serving "
                                 "(default 2)")
        parser.add_argument("--no-watch", action="store_true",
                            help="read the folder once, at start, and not again")
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
        runs, pair = folder / "runs", None
        overrides = {"store_root": str(folder / "store"), "trust_file": str(folder / "trust.json")}
    else:
        runs, pair, overrides = Path(args.folder), tuple(args.compare) if args.compare else None, {}
        if args.no_watch and args.watch_interval is not None:
            parser.error("--no-watch reads the folder once: give it no --watch-interval")
        if args.watch_interval is not None and args.watch_interval <= 0:
            parser.error("--watch-interval takes a number of seconds above 0")
        try:
            if args.no_watch:
                run_folders(runs)
            elif not runs.is_dir():
                raise LoadRefused(f"{runs} is not a folder.")
            overrides.update(evidence_files(args))
        except LoadRefused as e:
            print(f"refusing to start: {e}", file=sys.stderr)
            return 1
    if args.port is not None:
        overrides["port"] = args.port

    def prepare(store: Store, config: Config):
        if demo:
            from onetrace_console import demo_store
            loaded = demo_store.deliver(runs.parent, store, config)
        else:
            loaded = load_folder(runs, store, config, compare=pair)
        return announce(runs, loaded, store)

    if demo or args.no_watch:
        return serve_main([], overrides=overrides, prepare=prepare, open_browser=args.open)
    watching = _Watching(runs, pair, args.watch_interval)
    return serve_main([], overrides=overrides, prepare=watching.prepare, open_browser=args.open,
                      watch=watching.watch)


class _Watching:
    """`onetrace-console <runs folder>`, watched (watch.py): the start-up load is the watcher's
    own two reads, an interval apart, so a run still being written is not taken in at start
    either; then the watcher goes on while the console serves, every intake drawing its pages,
    and a `--compare` naming a folder not yet there is made once both have arrived."""

    def __init__(self, runs: Path, pair, interval):
        from onetrace_console import watch
        self.runs, self.pair = runs, pair
        self.interval = watch.INTERVAL if interval is None else interval
        self.loaded: list[LoadedRun] = []
        self.compared = None
        self.store = self.config = self.root = None
        self.serving = False
        self.watcher = None

    def _intake(self, run_dir: Path) -> bool:
        from onetrace_console.serve import INTAKE_LOCK, _render_run_pages
        with INTAKE_LOCK:
            got = deliver_one(run_dir, self.store, self.config)
            self.loaded.append(got)
            if got.run is None:
                print(shown(f"onetrace-console: {run_dir.name}: {got.refused}"), file=sys.stderr, flush=True)
                return False
            if self.serving:
                _render_run_pages(got.run, self.store, self.root, self.config)
                print(f"onetrace-console: took in {run_dir.name}", file=sys.stderr, flush=True)
            return True

    def _examine(self, run_dir: Path) -> tuple[str, str]:
        """A folder changed since it was taken in, as its own check now reads it."""
        from onetrace_console.checks import CONTRADICTS, check, check_options
        try:
            verdict = check(run_dir, **check_options(self.config)).verdict
        except Exception:  # noqa: BLE001 - said, never raised
            verdict = ""
        if verdict == CONTRADICTS:
            return ("bad", "The folder now contradicts its own record. The copy taken in is shown.")
        return ("cc", "The folder has changed since it was taken in. The copy taken in is shown.")

    def _compare_if_ready(self) -> None:
        if self.pair is None or self.compared is not None:
            return
        taken = [r for r in self.loaded if r.run is not None]
        if all(any(r.name == n for r in taken) for n in self.pair):
            self.compared, note = _compare(taken, self.pair, self.store)
            if self.compared is None:
                print(f"onetrace-console: {note}", file=sys.stderr, flush=True)

    def _on_change(self, took) -> None:
        from onetrace_console.serve import INTAKE_LOCK, _render_all_pages, _render_diff_page
        with INTAKE_LOCK:
            before = self.compared
            self._compare_if_ready()
            if not self.serving:
                return              # at start: the start-up drawing draws everything
            if self.compared is not None and before is None:
                _render_diff_page(self.compared, self.store, self.root)
            _render_all_pages(self.store, self.root, self.config)

    def prepare(self, store: Store, config: Config):
        import time

        from onetrace_console import watch
        self.store, self.config = store, config
        self.watcher = watch.Watcher(self.runs, self._intake, interval=self.interval,
                                     on_change=self._on_change, examine=self._examine)
        #: Known before the start-up drawing, so its pages carry the line saying the folder is
        #: watched; set only in `watch()`, it reached a page only after a later pickup redrew it.
        watch.CURRENT = self.watcher
        self.watcher.scan()
        time.sleep(min(self.interval, 2.0))
        self.watcher.scan()
        self._compare_if_ready()
        note = ""
        if self.pair is not None and self.compared is None:
            missing = [n for n in self.pair if not any(r.name == n and r.run is not None
                                                        for r in self.loaded)]
            note = WAITING.format(names=" and ".join(missing))
        if not self.loaded:
            print(f"onetrace-console: no finished run in {self.runs} yet; watching it every "
                  f"{self.interval:g} s", file=sys.stderr, flush=True)
            return ([("overview:", "")], "")
        return announce(self.runs, Loaded(tuple(self.loaded), self.compared, note), store)

    def watch(self, store: Store, root: Path, config: Config):
        from onetrace_console import watch
        self.root, self.serving = root, True
        watch.CURRENT = self.watcher
        return self.watcher



def evidence_files(args) -> dict:
    """`--trust`, `--tsa-cert` and `--tsa-root`, each read from the folder the console is started
    in if relative (a path with a root or a drive is kept as given, never resolved), each refused at
    start -- with its fix -- if it can't be read, and passed to every check as the verifier's own
    option. Nothing else changes: local mode stays local."""
    from onetrace_console.config import from_folder

    def readable(flag: str, value: str) -> str:
        path = from_folder(value, os.getcwd())
        try:
            with open(path, "rb"):
                pass
        except OSError as e:
            raise LoadRefused(f"{flag} {value}: cannot read {path} ({e.strerror or e}).\nfix: give "
                              f"{flag} the path of a file this console can read.") from None
        return str(path)
    out: dict = {}
    if args.trust is not None:
        out["trust_file"] = readable("--trust", args.trust)
    if bool(args.tsa_cert) != bool(args.tsa_root):
        raise LoadRefused("--tsa-cert and --tsa-root go together: the verifier checks the time-stamp "
                          "authority's certificate against the root it chains to.\nfix: give "
                          "both, or neither.")
    if args.tsa_cert:
        out["tsa_cert"] = readable("--tsa-cert", args.tsa_cert)
        out["tsa_roots"] = [readable("--tsa-root", r) for r in args.tsa_root]
    return out


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
