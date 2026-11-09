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
#: onetrace 0.7.1 and onetrace-verify 0.7.1 from PyPI, each checked against these hashes.
#: The "wheelhouse" source stays for a branch that pins a build on no index; nothing uses it now.
SOURCE = "pypi"
WHEELHOUSE = REPO / "wheelhouse" / "devbuild"
WHEELS = {
    "onetrace==0.7.1": (
        "onetrace-0.7.1-py3-none-any.whl",
        "889ef744a23c3a5ce05489bfe3a0c75ffbc3f97f46e9e28815f6012637f2f995",
    ),
    "onetrace-verify==0.7.1": (
        "onetrace_verify-0.7.1-py3-none-any.whl",
        "912a1111840a5ad1206385186e2808e1af0fa380406ace7c3b28d9bac92bc05c",
    ),
}


#: A command the tests run, never a dependency of the console and never in the lock: the published
#: onetrace-explain, whose wheel the explanation panel's tests install into a folder of their own
#: (tests/conftest.py, `explain_command`). Typed here once, like WHEELS, from PyPI's JSON.
TEST_COMMANDS = {
    "onetrace-explain==0.1.0": (
        "onetrace_explain-0.1.0-py3-none-any.whl",
        "122ea6af68bad45eecc78681e270955aa7fd27f59bc7bcbde96d8c6cc7fa434f",
    ),
}


#: What a reader installs beside the console in one environment, never a dependency of it and never in
#: the lock: the published onetrace-explain 0.3.0 (which reads the key from the keychain, and accepts onetrace 0.7), and onetrace-auto 0.7.1, whose
#: wheels `tests/test_one_environment.py` installs with the console's, offline, and asks `pip check`
#: about. Typed here once, like WHEELS, from PyPI's JSON.
ONE_ENVIRONMENT = {
    "onetrace-explain==0.3.0": (
        "onetrace_explain-0.3.0-py3-none-any.whl",
        "6d3390459d2854cefcf3e7e5feaa1f8968b86a767f7cec7bf5d943a273ea21c5",
    ),
    "onetrace-auto==0.7.1": (
        "onetrace_auto-0.7.1-py3-none-any.whl",
        "e4413e4f0e11742490407fbd4c85ec49291ece98c882220243a90a2b91850bc0",
    ),
}


#: The keychain's library, for the tests of the console's Set up Explain form (console 0.7.0): `keyring`
#: and what it needs on Python 3.12, from PyPI, typed here once from PyPI's JSON. Never a dependency of the
#: console and never in the lock: a reader installs it with `onetrace-explain[keyring]`. The tests install
#: these into a folder of their own (tests/keychain.py), as the explanation panel's do the command.
KEYCHAIN = {
    "keyring==25.7.0": (
        "keyring-25.7.0-py3-none-any.whl",
        "be4a0b195f149690c166e850609a477c532ddbfbaed96a404d4e43f8d5e2689f",
    ),
    "jaraco.classes==3.4.0": (
        "jaraco.classes-3.4.0-py3-none-any.whl",
        "f662826b6bed8cace05e7ff873ce0f9283b5c924470fe664fff1c2f00f581790",
    ),
    "jaraco.functools==4.6.0": (
        "jaraco_functools-4.6.0-py3-none-any.whl",
        "99e3dc0060c5cbe8fcd1cdb36258e2a65ca40f1566b2033b12abb1bb44dd3c30",
    ),
    "jaraco.context==6.1.2": (
        "jaraco_context-6.1.2-py3-none-any.whl",
        "bf8150b79a2d5d91ae48629d8b427a8f7ba0e1097dd6202a9059f29a36379535",
    ),
    "more-itertools==11.2.1": (
        "more_itertools-11.2.1-py3-none-any.whl",
        "35a7377edd1dd6608dcb2cdf534ded55ea32d49448875ad042cd3f879fb1ded0",
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
    missing = [name for name, _ in (*WHEELS.values(), *TEST_COMMANDS.values(), *ONE_ENVIRONMENT.values(), *KEYCHAIN.values()) if not (CACHE / name).is_file()]
    missing += [f"{pin} (any of its pinned wheels)" for pin in _crypto_ready()]
    if missing:
        print(f"NOT READY: missing under {CACHE}: {missing}")
        return False
    for name, sha in (*WHEELS.values(), *TEST_COMMANDS.values(), *ONE_ENVIRONMENT.values(), *KEYCHAIN.values()):
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
        for requirement, (filename, sha) in {**WHEELS, **TEST_COMMANDS, **ONE_ENVIRONMENT, **KEYCHAIN}.items():
            if SOURCE == "wheelhouse" and requirement in WHEELS:
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
        for filename, _ in (*WHEELS.values(), *TEST_COMMANDS.values(), *ONE_ENVIRONMENT.values(), *KEYCHAIN.values()):
            shutil.copy(tmp_path / filename, CACHE / filename)
        for wheel in crypto.glob("*.whl"):
            shutil.copy(wheel, CACHE / wheel.name)
    print(f"{'fetched' if SOURCE == 'pypi' else 'read'} and verified {len(WHEELS) + len(TEST_COMMANDS) + len(ONE_ENVIRONMENT) + len(KEYCHAIN)} wheel(s) "
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
