"""The pinning checks: the SDK is pinned by hash from PyPI, not a git commit on
PYTHONPATH. The viewer is part of this package (src/onetrace_console/viewer/, with its PROVENANCE.md),
so nothing else is installed for it.

Before that, this file held: three commits named once, cross-checked across two requirements
files and PINS.md; nothing vendored or copied. All three distributions are pinned by hash now
instead, and there is one requirements file instead of two -- the online/offline split existed
because the two source repositories were private and needed credentials; PyPI and a committed
wheelhouse need neither, so the split has nothing left to do.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LOCK = REPO / "requirements.lock"
PINS_DOC = REPO / "PINS.md"

#: The three hashes this channel has independently verified, named once here. If a pin is
#: moved, this fails and names what disagreed -- the point of writing them out at all.
#: The SDK's two: onetrace 0.5.0 and onetrace-verify 0.5.0 from PyPI, each wheel's sha256 written
#: here by script from PyPI's JSON.
ONETRACE_WHL_SHA256 = "02ac0ce2a6b1581571623535c6219b3fec292c97a31fddd62f9dcc71453f0cc6"
ONETRACE_VERIFY_WHL_SHA256 = "972a9de38b072d4a6f5754bdd05fcf831f87ed71316389f294bbc1b3a85ec313"
#: The pinned SDK's version, as its distribution and `onetrace.__version__` report it; and the
#: verifier's, the same (the two are released in series: 0.5.x with 0.5.x).
PINNED_SDK_VERSION = "0.5.0"
PINNED_VERIFY_VERSION = "0.5.0"
ONETRACE_LOCK_KEY = "onetrace==0.5.0"
ONETRACE_VERIFY_LOCK_KEY = "onetrace-verify==0.5.0"

_REQ = re.compile(
    r"^(?P<req>\S+)\s*\\?\s*$\n\s*--hash=sha256:(?P<sha>[0-9a-f]{64})",
    re.MULTILINE)


def lock_entries() -> dict[str, str]:
    """{requirement (as written) -> pinned sha256}, parsed rather than assumed."""
    text = LOCK.read_text(encoding="utf-8")
    return {m.group("req"): m.group("sha") for m in _REQ.finditer(text)}


#: The verifier's crypto extra, exactly the versions the SDK pins at 0.2.0;
#: tests/test_signed_run.py holds each one's hashes.
CRYPTO_PINS = {"asn1crypto==1.5.1", "cffi==2.1.1", "cryptography==50.0.1", "pycparser==3.0",
                 "rfc3161-client==1.0.9"}


def test_the_lock_file_pins_exactly_these_things_by_hash(examined):
    entries = lock_entries()
    examined(len(entries), "hash-pinned requirements")
    assert set(entries) == {
        ONETRACE_LOCK_KEY,
        ONETRACE_VERIFY_LOCK_KEY,
    } | CRYPTO_PINS, (f"the lock file pins {sorted(entries)}; the SDK's two distributions and "
                       f"the crypto extra's five are expected")


def test_onetrace_is_pinned_to_the_wheel_this_channel_verified(examined):
    entries = lock_entries()
    examined(1, "pin checked")
    assert entries.get(ONETRACE_LOCK_KEY) == ONETRACE_WHL_SHA256, entries


def test_onetrace_verify_is_pinned_to_the_wheel_this_channel_verified(examined):
    entries = lock_entries()
    examined(1, "pin checked")
    assert entries.get(ONETRACE_VERIFY_LOCK_KEY) == ONETRACE_VERIFY_WHL_SHA256, entries


def test_the_sdk_s_doctor_reads_the_pinned_pair_as_compatible(tmp_path, examined):
    """`onetrace doctor`, in an empty folder, on what this console installs: its compatibility
    line names the two pinned versions and says they are compatible, by the SDK's own table."""
    p = subprocess.run([sys.executable, "-m", "onetrace", "doctor"], cwd=tmp_path, capture_output=True,
                       text=True, timeout=120)
    examined(1, "doctor's compatibility line")
    line = (f"[ok]  onetrace and onetrace-verify: onetrace {PINNED_SDK_VERSION}, "
            f"onetrace-verify {PINNED_VERIFY_VERSION}: compatible")
    assert line in [l.strip() for l in p.stdout.splitlines()], p.stdout
    assert p.returncode == 0, p.stdout + p.stderr


def test_a_wrong_hash_fails_the_install(examined):
    """Step 1's sabotage, verbatim: a wrong hash in the pin fails the install.

    Runs a real `pip install --require-hashes` into a throwaway venv-less target
    (`--target`, no venv needed) with one hash character flipped, and asserts pip refuses.
    Slow relative to the rest of this file (a real subprocess), which is what "runs the
    actual install" means here rather than parsing the lock file's text.

    RUN WITH THE NETWORK OFF. The real `requirements.lock` names
    `onetrace==0.1.2` and `onetrace-verify==0.1.2` as bare PyPI requirements (not a direct
    URL), so pip must resolve and download them before it ever gets to comparing hashes --
    a real earlier run of exactly this test timed out twice on a slow network, independent
    of anything this repository controls. `tools/fetch_wheel_cache.py` caches both wheels
    once, hash-verified against the same reference this file already names; `--no-index
    --find-links <cache>` below makes an outbound connection structurally impossible for
    THIS call, not merely absent this time around.
    """
    import tempfile

    from tools.fetch_wheel_cache import CACHE as WHEEL_CACHE
    from tools.fetch_wheel_cache import check as wheel_cache_ready

    if not wheel_cache_ready():
        pytest.fail(
            f"the local wheel cache is not there or does not match: {WHEEL_CACHE}\n"
            f"    python tools/fetch_wheel_cache.py\n"
            f"This refuses rather than skips, and rather than falling back to the network.")

    examined(1, "wrong-hash install attempts")
    text = LOCK.read_text(encoding="utf-8")
    #: One character changed, whatever the hash begins with (0.2.0's onetrace wheel begins with "0").
    bad_sha = ("1" if ONETRACE_WHL_SHA256[0] == "0" else "0") + ONETRACE_WHL_SHA256[1:]
    assert bad_sha != ONETRACE_WHL_SHA256
    bad_text = text.replace(ONETRACE_WHL_SHA256, bad_sha)
    assert bad_sha in bad_text and ONETRACE_WHL_SHA256 not in bad_text.replace(bad_sha, "")

    with tempfile.TemporaryDirectory(prefix="onetrace-console-badpin-") as tmp:
        tmp_path = Path(tmp)
        bad_lock = tmp_path / "requirements.bad.lock"
        bad_lock.write_text(bad_text, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--require-hashes",
             "--no-index", "--find-links", str(WHEEL_CACHE),
             "--target", str(tmp_path / "target"), "-r", str(bad_lock)],
            cwd=REPO, capture_output=True, text=True, timeout=30)
    assert proc.returncode != 0, (
        f"a wrong hash was accepted by pip; exit {proc.returncode}\n{proc.stdout}")
    combined = proc.stdout + proc.stderr
    assert "do not match the hashes" in combined.lower(), combined


@pytest.mark.skipif(not PINS_DOC.is_file(),
                    reason="PINS.md is the repository's own record of its pins and is left out "
                           "of the public tree")
def test_the_pins_document_names_both_hashes(examined):
    doc = PINS_DOC.read_text(encoding="utf-8")
    shas = (ONETRACE_WHL_SHA256, ONETRACE_VERIFY_WHL_SHA256)
    examined(len(shas), "hashes checked against PINS.md")
    for sha in shas:
        assert sha in doc, f"PINS.md does not name {sha}"


@pytest.mark.skipif(not PINS_DOC.is_file(),
                    reason="PINS.md is the repository's own record of its pins and is left out "
                           "of the public tree")
def test_the_pins_document_names_the_0_5_0_release_s_four_files_and_keeps_the_earlier_releases(examined):
    """The current section names 0.5.0's four files and says nothing of an index they are not on;
    the development wheels' section is gone; the sections before still name 0.4.0's and 0.3.0's four."""
    from tests.test_pin_012 import RELEASE_0_3_0, RELEASE_0_4_0, RELEASE_0_5_0
    doc = PINS_DOC.read_text(encoding="utf-8")
    now, before = doc.split("\n## Before", 1)
    examined(len(RELEASE_0_5_0) + len(RELEASE_0_4_0) + len(RELEASE_0_3_0), "files checked against PINS.md")
    for name, sha in RELEASE_0_5_0.items():
        assert sha in now, f"PINS.md's current section does not name {name}"
    assert "on no index" not in now and "--find-links" not in now and "development wheel" not in now
    for name, sha in {**RELEASE_0_4_0, **RELEASE_0_3_0}.items():
        assert sha in before, f"PINS.md no longer names {name}"


def test_no_pythonpath_clone_apparatus_remains(examined):
    """"Remove the PYTHONPATH clones and the pins to source trees." Checked, not
    promised: none of the files that used to make that mechanism work exist any more."""
    gone = ["requirements.local", "tools/make_pins.py", ".pins"]
    examined(len(gone), "removed paths checked for absence")
    present = [f for f in gone if (REPO / f).exists()]
    assert not present, f"still present, and should not be: {present}"


def test_a_stored_comparison_keyed_on_a_commit_is_never_returned_as_a_hit():
    """"Stored reports keyed on commit:<sha> keys are recomputed, not relabelled."

    Nothing in this repository's own history is migrated by hand -- store/ is gitignored, so
    there is no committed data to migrate -- but the CODE PATH that makes an old key a miss
    rather than a silent hit is asserted here rather than trusted from the
    original test alone.
    """
    from dataclasses import replace

    from onetrace_console.compare import comparison_key
    from tests.test_checks import _require_installed

    _require_installed()

    # A key computed as if the build digest were still commit-shaped must not equal today's
    # real key, which is what "recomputed, not relabelled" means at the code level: the
    # lookup in compare() compares held.sdk_build_digest to the CURRENT build's digest, and
    # a commit-shaped one will never match a wheel-shaped one.
    from onetrace_console.compare import sdk_build_digest, sdk_distribution_version

    old_style_key = comparison_key("a" * 64, "b" * 64, sdk_distribution_version(),
                                   "commit:0000000000000000000000000000000000000000")
    real_key = comparison_key("a" * 64, "b" * 64, sdk_distribution_version(),
                              sdk_build_digest())
    assert old_style_key != real_key, (
        "a comparison keyed under a commit-shaped build digest collided with the real, "
        "wheel-shaped key -- it should be impossible for these to match")


# ------------------------------------------------------- nothing is vendored or copied

#: Files that may mention these names without being a copy of them.
ALLOWED_TO_NAME_THEM = {
    "requirements.lock", "PINS.md", "README.md", "DESIGN_GAPS.md", "pyproject.toml",
    ".gitignore",
}


def tracked_files() -> list[str]:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return [f for f in r.stdout.split("\0") if f]


def test_no_source_from_canary_or_onetrace_is_committed_here(examined):
    """"Don't vendor it" and "don't copy it", as a check rather than a promise.

    The SDK's source is never copied here: a `.py` file with these names committed anywhere is
    a copy. The viewer is not in this list: it moved into this package (src/onetrace_console/viewer/,
    its PROVENANCE.md naming where it came from), and is this package's own source now.
    """
    files = tracked_files()
    examined(len(files), "tracked files scanned")
    assert files, "git ls-files reported nothing; this test would pass vacuously"
    copied = [f for f in files
              if Path(f).name in {"verify.py", "canonicalize.py", "verify_roots.py",
                                  "sdk_verify.py", "verifier_call.py"}
              or (Path(f).parts[:1] in (("viewer",), ("onetrace",), ("src", "onetrace"))
                  and not f.startswith("tests/fixtures/"))]
    assert not copied, f"source from a pinned repository is committed here: {copied}"


@pytest.mark.parametrize("package", ["onetrace", "viewer", "canary"])
def test_a_pinned_package_never_resolves_to_a_file_tracked_here(package):
    """It must come from an install, never from a committed copy.

    The property that matters is whether git TRACKS the file the package resolves to -- a
    copy would be committed, an install under `site-packages` is not -- so that is what is
    asked, rather than guessed from a path's shape.
    """
    import importlib.util
    try:
        spec = importlib.util.find_spec(package)
    except (ImportError, ValueError):
        return                      # not importable at all: exactly right
    if spec is None or not spec.origin:
        return
    origin = Path(spec.origin).resolve()
    assert not _tracked_here(origin), (
        f"{package} resolves to {origin}, which is TRACKED in this repository. Depend on "
        f"it, don't copy it.")


def _tracked_here(path: Path) -> bool:
    try:
        rel = path.relative_to(REPO)
    except ValueError:
        return False
    r = subprocess.run(["git", "ls-files", "--error-unmatch", rel.as_posix()],
                       cwd=REPO, capture_output=True, text=True)
    return r.returncode == 0


#: Where each README says which SDK and verifier it installs.
_INSTALLS = re.compile(r"installs from PyPI alone: `onetrace` (\S+) and `onetrace-verify` (\S+),")


def readme_pin_problems(name: str, text: str) -> list[str]:
    """The versions a README says the console installs, against the exact pins in pyproject.toml."""
    import tomllib
    deps = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    pinned = dict(re.match(r"([a-z-]+)(?:\[\w+\])?==(\S+)", d).groups() for d in deps
                  if d.startswith(("onetrace==", "onetrace-verify")))
    said = _INSTALLS.findall(text)
    if said != [(pinned["onetrace"], pinned["onetrace-verify"])]:
        return [f"{name} says it installs {said}, pyproject.toml pins {pinned}"]
    return []


@pytest.mark.parametrize("name", ["README.md", "PYPI_DESCRIPTION.md"])
def test_each_readme_names_the_versions_the_console_pins(name, examined):
    examined(1, name)
    assert readme_pin_problems(name, (REPO / name).read_text(encoding="utf-8")) == []


def test_sabotage_a_readme_naming_another_sdk_version_is_named(examined):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    stale = text.replace(f"`onetrace` {PINNED_SDK_VERSION} and", "`onetrace` 0.2.0 and", 1)
    examined(1, "planted README")
    assert stale != text and readme_pin_problems("README.md", stale) != []
