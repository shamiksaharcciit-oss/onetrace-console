"""Cache the two pinned wheels locally, hash-verified, so pin-related tests never touch
the network.

WHY THIS EXISTS
---------------
`tests/test_pins.py::test_a_wrong_hash_fails_the_install` runs a real `pip install
--require-hashes` against a mutated lock file, to prove pip itself refuses a wrong hash
rather than trusting a hand-written assertion about what pip would do. Run against the
REAL `requirements.lock`'s requirement lines (`onetrace==0.1.2`, `onetrace-verify==0.1.2`,
resolved from PyPI, no direct URL), pip must reach PyPI to resolve and download them before
it ever gets to comparing hashes -- so a network hiccup times the test out, twice,
independently of anything this repository controls.

The fix is not to weaken the check; it is to remove the network from the CALL the test
makes, the same way `fetch_sdk_fixtures.py` already does for `test_compare.py`'s exam
fixtures: fetch once, verify the bytes against the reference this console already pins,
and have the test run `pip install --no-index --find-links <this cache>`, which makes an
outbound connection structurally impossible for that one call, not merely absent this time.

Usage:
    python tools/fetch_wheel_cache.py [--check]

    --check   report whether the cache is present and correct; fetch nothing.

TWO SOURCES
-----------
The two wheels come from PyPI (`SOURCE = "pypi"`), 0.2.0 as released. The
0.2.0 branch took a development build from a committed wheelhouse folder (`SOURCE = "wheelhouse"`)
until the release; that source is kept for such a build. Either way each file is checked against
its pinned hash by `_verified` before anything is cached, and a mismatch refuses.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACHE = REPO / ".wheel-cache"

#: The same two references `requirements.lock` pins by hash -- typed here once, not
#: derived from anything downloaded, so a mismatch is caught rather than assumed away.
#: onetrace 0.2.2 and onetrace-verify 0.2.1 from PyPI, each as PyPI's JSON serves it.
#: The "wheelhouse" source stays for a branch that pins a build on no index; nothing uses it now.
SOURCE = "pypi"
WHEELHOUSE = REPO / "wheelhouse" / "devbuild"
WHEELS = {
    "onetrace==0.2.2": (
        "onetrace-0.2.2-py3-none-any.whl",
        "5fbefd657d0622d8dad8d9506f118be2b417a9586589d8e50d59fd2a5fa21b1f",
    ),
    "onetrace-verify==0.2.1": (
        "onetrace_verify-0.2.1-py3-none-any.whl",
        "c001019740798f907ae8a4adace32c597fb749cf52fca0e668c932723a792119",
    ),
}


#: The verifier's crypto extra, as requirements.lock pins it: {"name==version": {sha256, ...}}, every
#: hash the lock allows (one per platform's file). Cached for this platform, so a test can install
#: the console as `pip install onetrace-console` does, extra included, with no network.
CRYPTO = ("asn1crypto", "cffi", "cryptography", "pycparser", "rfc3161-client")


def crypto_pins() -> dict[str, set[str]]:
    import re
    lock = (REPO / "requirements.lock").read_text(encoding="utf-8")
    pins = {}
    for m in re.finditer(r"^([A-Za-z0-9_.-]+==[^\s;]+)[^\n]*\\\n((?:\s+--hash=sha256:[0-9a-f]{64}[^\n]*\n?)+)",
                         lock, re.M):
        if m.group(1).split("==")[0].lower() in CRYPTO:
            pins[m.group(1)] = set(re.findall(r"sha256:([0-9a-f]{64})", m.group(2)))
    return pins


def _crypto_ready() -> list[str]:
    """What is missing from the cache for the crypto extra: one wheel per pin, of an allowed hash."""
    have = {hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob("*.whl")} if CACHE.is_dir() else set()
    return [pin for pin, hashes in crypto_pins().items() if not hashes & have]


def check() -> bool:
    missing = [name for name, _ in WHEELS.values() if not (CACHE / name).is_file()]
    missing += [f"{pin} (any of its pinned wheels)" for pin in _crypto_ready()]
    if missing:
        print(f"NOT READY: missing under {CACHE}: {missing}")
        return False
    for name, sha in WHEELS.values():
        got = hashlib.sha256((CACHE / name).read_bytes()).hexdigest()
        if got != sha:
            print(f"NOT READY: {name} does not match its pinned hash "
                 f"(expected {sha}, got {got})")
            return False
    print(f"ready: {CACHE}")
    return True


def _verified(wheel: Path, sha: str, source: str) -> None:
    """Refuse, from either source, a wheel whose bytes are not the pinned ones."""
    if not wheel.is_file():
        raise SystemExit(f"{source} did not provide {wheel.name}")
    got = hashlib.sha256(wheel.read_bytes()).hexdigest()
    if got != sha:
        raise SystemExit(
            f"REFUSING: {wheel.name} from {source} does not match the pinned reference.\n"
            f"  expected {sha}\n  got      {got}\n"
            f"This is the lapse condition: what {source} holds is not what this "
            f"console already pins, and nothing is cached from it.")


def fetch() -> None:
    with tempfile.TemporaryDirectory(prefix="onetrace-wheel-cache-") as tmp:
        tmp_path = Path(tmp)
        for requirement, (filename, sha) in WHEELS.items():
            if SOURCE == "wheelhouse":
                if (WHEELHOUSE / filename).is_file():
                    shutil.copyfile(WHEELHOUSE / filename, tmp_path / filename)
                _verified(tmp_path / filename, sha,
                          "the wheelhouse (" + (WHEELHOUSE.relative_to(REPO).as_posix() if WHEELHOUSE.is_relative_to(REPO) else str(WHEELHOUSE)) + ")")
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary", ":all:",
                 "--no-cache-dir", "--dest", str(tmp_path), requirement],
                capture_output=True, text=True)
            if proc.returncode != 0:
                raise SystemExit(f"pip download failed for {requirement}:\n"
                                f"{proc.stdout}\n{proc.stderr}")
            _verified(tmp_path / filename, sha, "PyPI")
        #: The crypto extra: pip picks this platform's file and refuses any not in the lock.
        crypto = tmp_path / "crypto"
        crypto.mkdir()
        req = tmp_path / "crypto.txt"
        req.write_text("".join(f"{pin} " + " ".join(f"--hash=sha256:{h}" for h in sorted(hashes)) + "\n"
                               for pin, hashes in crypto_pins().items()), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "download", "--no-deps", "--only-binary", ":all:",
             "--no-cache-dir", "--require-hashes", "--dest", str(crypto), "-r", str(req)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            raise SystemExit(f"pip download failed for the crypto extra:\n{proc.stdout}\n{proc.stderr}")
        shutil.rmtree(CACHE, ignore_errors=True)
        CACHE.mkdir(parents=True)
        for filename, _ in WHEELS.values():
            shutil.copy(tmp_path / filename, CACHE / filename)
        for wheel in crypto.glob("*.whl"):
            shutil.copy(wheel, CACHE / wheel.name)
    print(f"{'fetched' if SOURCE == 'pypi' else 'read'} and verified {len(WHEELS)} wheel(s) "
          f"from {SOURCE} into {CACHE}")


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
