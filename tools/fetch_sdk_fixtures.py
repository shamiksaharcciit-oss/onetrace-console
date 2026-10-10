"""Materialise the SDK's own `exam/` fixture tree, from PyPI by hash -- never from a clone.

WHY THIS EXISTS
---------------
`tests/test_compare.py` needs real, multi-stage SDK-emitted runs (`exam/fixtures/ingest-r1/
run_B`, `run_C`, `run_C_poppler24`; `exam/fixtures/dag-r37/run_R`) to test the comparison
runner against. These used to come from a private git clone under `.pins/onetrace/`. That
clone is gone -- the SDK is now a hash-pinned PyPI wheel, not a source checkout --
and this fixture tree is 5.4 MB / 135 files, too large to commit as data the way the small
20 KB r11 fixture was (see `tests/fixtures/r11/PROVENANCE.md` for that one and why it differs).

So this script downloads the ALREADY HASH-VERIFIED sdist (the same reference this console
pins the wheel against, `onetrace==0.1.2`) from PyPI, checks its sha256 before touching
anything, and extracts only `exam/` into a git-ignored local cache. Nothing here is
committed; nothing at runtime depends on it existing (only these specific tests do, and they
refuse with this script's name rather than skip when it is missing).

Usage:
    python tools/fetch_sdk_fixtures.py [--check]

    --check   report whether the cache is present and correct; fetch nothing.

TWO SOURCES
-----------
The SDK's sdist comes from PyPI (`SOURCE = "pypi"`), 0.2.0 as released. The
0.2.0 branch read a development build from a committed wheelhouse folder (`SOURCE = "wheelhouse"`)
until the release; that source is kept for such a build. Either way the bytes are checked against
the one pinned hash by `_verified` before anything is extracted, and a mismatch refuses
(`tests/test_fixture_sources.py` shows each source refusing).
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / ".sdk-fixtures"
EXAM = CACHE / "exam"
#: The text diff's golden: the SDK's own warranty pair, from the same hash-checked sdist.
WARRANTY = CACHE / "tests" / "fixtures" / "warranty"

#: The onetrace SDIST this console's fixtures come from, by sha256: 0.2.0 from PyPI, the release
#: candidate's `SHA256SUMS` value, which PyPI serves. `SOURCE` says where it is read from
#: (see the docstring).
SOURCE = "pypi"
REQUIREMENT = "onetrace==0.2.0"
SDIST_NAME = "onetrace-0.2.0.tar.gz"
SDIST_SHA256 = "ff9932abb2cbd920f428d02b84e7fca83992c9d4e9bd8169e202341c69bd796f"
WHEELHOUSE = REPO / "wheelhouse" / "devbuild"

#: Which sdist the cache was extracted from, as `<name> <sha256>`. The fixture folders have
#: the same shape in every release, so their presence alone cannot tell a stale cache from
#: a current one; this record can.
SOURCE_FILE = "SOURCE"

#: What must be present under EXAM for the fixture-dependent tests to run.
EXPECTED = (
    "fixtures/ingest-r1/run_B",
    "fixtures/ingest-r1/run_C",
    "fixtures/ingest-r1/run_C_poppler24",
    "fixtures/dag-r37/run_R",
)
WARRANTY_EXPECTED = ("runs/query-v1", "runs/query-v2", "runs/ingest-v1", "runs/ingest-v2")


def check() -> bool:
    source = CACHE / SOURCE_FILE
    want = f"{SDIST_NAME} {SDIST_SHA256}"
    got = source.read_text(encoding="utf-8").strip() if source.is_file() else ""
    if got != want:
        print(f"NOT READY: {CACHE} was not extracted from {SDIST_NAME} "
              f"({got or 'no source recorded'}); run tools/fetch_sdk_fixtures.py")
        return False
    missing = [str(EXAM / p) for p in EXPECTED if not (EXAM / p).is_dir()]
    missing += [str(WARRANTY / p) for p in WARRANTY_EXPECTED if not (WARRANTY / p).is_dir()]
    if missing:
        print(f"NOT READY: missing: {missing}")
        return False
    print(f"ready: {EXAM}")
    return True


def _verified(path: Path, source: str) -> Path:
    """`path`, if its bytes are the pinned sdist's; otherwise refuse, from either source."""
    if not path.is_file():
        raise SystemExit(f"{source} did not provide {SDIST_NAME}: no file at {path}")
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    if got != SDIST_SHA256:
        raise SystemExit(
            f"REFUSING: {SDIST_NAME} from {source} does not match the pinned reference.\n"
            f"  expected {SDIST_SHA256}\n  got      {got}\n"
            f"This is the lapse condition: what {source} holds is not what this console "
            f"already checked, and nothing is extracted from it.")
    return path


def _from_pypi(tmp_path: Path) -> Path:
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "download", "--no-deps", "--no-binary", ":all:",
         "--no-cache-dir", "--dest", str(tmp_path), REQUIREMENT],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"pip download failed:\n{proc.stdout}\n{proc.stderr}")
    return _verified(tmp_path / SDIST_NAME, "PyPI")


def _from_wheelhouse(tmp_path: Path) -> Path:
    copy = tmp_path / SDIST_NAME
    if (WHEELHOUSE / SDIST_NAME).is_file():
        shutil.copyfile(WHEELHOUSE / SDIST_NAME, copy)
    return _verified(copy, "the wheelhouse (" + (WHEELHOUSE.relative_to(REPO).as_posix() if WHEELHOUSE.is_relative_to(REPO) else str(WHEELHOUSE)) + ")")


def fetch() -> None:
    with tempfile.TemporaryDirectory(prefix="onetrace-sdist-") as tmp:
        tmp_path = Path(tmp)
        sdist = {"pypi": _from_pypi, "wheelhouse": _from_wheelhouse}[SOURCE](tmp_path)

        shutil.rmtree(CACHE, ignore_errors=True)
        CACHE.mkdir(parents=True)
        with tarfile.open(sdist) as t:
            members = [m for m in t.getmembers() if "/exam/" in "/" + m.name
                       or "/tests/fixtures/warranty/" in "/" + m.name]
            for m in members:
                # Strip the "onetrace-<version>/" wrapper so EXAM is exam/... directly.
                parts = m.name.split("/", 1)
                if len(parts) != 2:
                    continue
                m.name = parts[1]
            t.extractall(CACHE, members=members, filter="data")
        (CACHE / SOURCE_FILE).write_text(f"{SDIST_NAME} {SDIST_SHA256}\n", encoding="utf-8")
    print(f"{'fetched' if SOURCE == 'pypi' else 'read'} and verified {SDIST_NAME} "
          f"({SDIST_SHA256[:16]}…) from {SOURCE}, extracted exam/ to {EXAM}")


def main(argv: list[str]) -> int:
    if "--check" in argv:
        return 0 if check() else 1
    if check():
        print("already present and matching the expected shape; nothing to do")
        return 0
    fetch()
    return 0 if check() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
