"""The scratch staging area: where a delivery is examined before the store is touched.

The pre-store checks (sums, chain_head, format) run in a scratch staging area. The staging
area is outside the store and never reachable by any GET. It is deleted after every upload,
whether accepted or rejected, and a 422 returns the verifier's own message word for word.

WHY A FOLDER AND NOT MEMORY
---------------------------
The first implementation held the delivery in a dict and checked it there, and the three
rejection rows were therefore the store's own words. The point of staging is that the
verifier can be *made* to speak if the delivery is put somewhere it can read -- so it is,
and its message is what a refused upload gets back.

WHAT "OUTSIDE THE STORE" BUYS
-----------------------------
A staged delivery has been through no check yet. If it lived under the store root, then
every read path would need to know which subtrees are real and which are provisional, and
the first one that forgot would serve unverified bytes as evidence. Keeping it out means
the question never arises: `Store.get` addresses objects by digest under `objects/`, and
nothing staged is ever an object. `tests/test_staging.py` asserts that no staged path is
reachable through the store's own API.

DELETED AFTER EVERY UPLOAD, WHICH MEANS EVERY EXIT
--------------------------------------------------
Accepted, rejected, refused as unreadable, or raising something nobody predicted -- the
directory goes in a `finally`. A staging area that survives a crash is a staging area that
accumulates other people's unverified records on someone's disk.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.store import create_exclusively

#: Where a staging directory is made. `None` means the OS temp root, which is outside the
#: store by construction. A caller may name somewhere else; it is checked, not trusted.
DEFAULT_STAGING_ROOT: Path | None = None

PREFIX = "onetrace-staging-"


class StagingError(RuntimeError):
    """Staging could not be set up or torn down honestly."""


@dataclass(frozen=True, slots=True)
class VerifierSaid:
    """The verifier's own output over a staged delivery, kept verbatim.

    `text` is stdout exactly as it was printed -- the thing a 422 returns word for word.
    `rows` is the FAIL lines, for deciding which pre-store check failed; the deciding never
    rewrites the words.
    """
    text: str
    exit_status: str
    rows: tuple[str, ...]

    @property
    def refused(self) -> bool:
        return self.exit_status != "0"

    def failed_rows(self) -> tuple[str, ...]:
        return tuple(r for r in self.rows if r.startswith("[FAIL"))


@contextmanager
def staging(root: Path | None = None):
    """A scratch directory for one upload, removed on every exit path.

    Yields the directory. Raises `StagingError` if it cannot be removed afterwards, because
    a staging area that silently failed to delete is the thing this module exists to
    prevent, and swallowing the error is how it would go unnoticed.
    """
    base = Path(root) if root is not None else (
        Path(DEFAULT_STAGING_ROOT) if DEFAULT_STAGING_ROOT else None)
    if base is not None:
        base.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix=PREFIX, dir=str(base) if base else None))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():                                    # pragma: no cover - defensive
            raise StagingError(
                f"the staging area could not be deleted: {path}. The ruling requires it "
                f"gone after every upload, and a silent failure here leaves someone "
                f"else's unverified records on this disk.")


def write_delivery(files: dict[str, bytes], dest: Path) -> Path:
    """Write the delivery's files into the staging area, bytes untouched.

    The paths were already refused if they escaped the run folder, by the tar reader; this
    re-checks, because "already checked elsewhere" is how a path traversal gets written to
    disk. Two cheap checks beat one clever one.
    """
    dest = Path(dest)
    for path, blob in files.items():
        target = (dest / path).resolve()
        if dest.resolve() not in target.parents and target != dest.resolve():
            raise StagingError(f"{path!r} resolves outside the staging area")
        target.parent.mkdir(parents=True, exist_ok=True)
        #: Never over a file already written: `SameFileError` names the member.
        create_exclusively(target, blob, named=path)
    return dest


def ask_the_verifier(folder: Path, *, timeout: int = 180) -> VerifierSaid:
    """Run the shipped verifier over the staged folder and keep what it said, verbatim.

    Invoked through `sys.executable` and never the name `python3`, and the exit
    status is the process's own rather than a shell pipeline's (R29).
    """
    from onetrace_console.checks import shipped_verifier

    verifier = shipped_verifier()
    proc = subprocess.run([sys.executable, str(verifier), "MANIFEST.json"],
                          cwd=str(folder), capture_output=True, timeout=timeout)
    text = proc.stdout.decode("utf-8", errors="replace")
    return VerifierSaid(text=text, exit_status=str(proc.returncode),
                        rows=tuple(text.splitlines()))
