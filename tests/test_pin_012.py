"""The pin moves from 0.1.0 to 0.1.2, skipping 0.1.1, for both
distributions exactly -- against the four accepted files.

And the known gap that comes with it: the published
`onetrace-verify` 0.1.2 runs no stage-order check, and PASSes the 0.1 copies of three receipts
that misstate their stage order. It is fixed in 0.2.0. Until the pin moves there, nothing this
console shows or ships may say an upload is checked for stage order.

The pin has since moved to 0.2.0 (`requirements.lock`), whose `onetrace-verify` runs the
stage-order check (its `verify.py`, `check_stage_order`; the SDK's CHANGELOG, 0.2.0: "The bench
verifier checks stage order"). So the operator README's non-claim for 0.1.2 is retired: the test
that required it now requires that no user document still states it.
"""
from __future__ import annotations

import importlib.metadata
import re
import subprocess
from pathlib import Path

import pytest

from tests.test_pins import ONETRACE_VERIFY_WHL_SHA256, ONETRACE_WHL_SHA256, lock_entries
try:
    from tools.export_public import NEVER
except ImportError:   # the public tree has no export tool, and its never-ship files are already absent
    NEVER = ()

REPO = Path(__file__).resolve().parent.parent

#: The pin is now 0.2.0 from PyPI. RC2's SHA256SUMS (ci's build of
#: fce500e656e83ee05cb9f6f223779be4a37ec0ce), which PyPI serves. The development
#: builds before it were committed in a wheelhouse folder on the 0.2.0 branch only; that folder is gone.
#: 0.1.2 (kept below as history) is no longer pinned.
RELEASE_COMMIT = "fce500e656e83ee05cb9f6f223779be4a37ec0ce"
RELEASE_0_2_0 = {
    "onetrace-0.2.0-py3-none-any.whl": "0e8df2304582e1ab7f6ed7309b3d0ac4c4654897cd77e1c96194ce8a708ee481",
    "onetrace-0.2.0.tar.gz": "ff9932abb2cbd920f428d02b84e7fca83992c9d4e9bd8169e202341c69bd796f",
    "onetrace_verify-0.2.0-py3-none-any.whl": "74b3c862bdf997ec71b20de02c6bbdb445b89ffc0017497b3ed6ce91b2bce89c",
    "onetrace_verify-0.2.0.tar.gz": "876b73ece416143b3b23fd60f5699dc5afcdfdbd8856653d2cdf8f281f89e63b",
}

#: The accepted table, typed here, not derived from any download. The onetrace sdist's
#: value was confirmed from PyPI itself.
ACCEPTED_29AG = {
    "onetrace-0.1.2-py3-none-any.whl": "77c1e735f5c33a351b99c9e0d9926390277f3e14cfb400b5fb3e7fe4b69a55b4",
    "onetrace-0.1.2.tar.gz": "c7ec33c72ae6807017ac6ff3add59dbc0432773818371dd145d73bfa2dd535e9",
    "onetrace_verify-0.1.2-py3-none-any.whl": "e69188e6486de0e669b24005f355acf5823afeee2aa123c81bc8c1bef58930cc",
    "onetrace_verify-0.1.2.tar.gz": "bbb3871f9e49a48f486ddec8b283a4cbddda953b7fc14e60ee58e3e770f07108",
}


def test_the_lock_pins_exactly_the_0_2_0_wheels(examined):
    entries = lock_entries()
    examined(3, "pins checked against RC2's SHA256SUMS")
    from tests.test_pins import CRYPTO_PINS
    #: The crypto extra's five, from PyPI, are held by tests/test_signed_run.py.
    assert set(entries) - CRYPTO_PINS == {
        "onetrace==0.2.0", "onetrace-verify==0.2.0"} and CRYPTO_PINS <= set(entries), entries
    assert {k: v for k, v in entries.items() if k not in CRYPTO_PINS} == {
        "onetrace==0.2.0": RELEASE_0_2_0["onetrace-0.2.0-py3-none-any.whl"],
        "onetrace-verify==0.2.0": RELEASE_0_2_0["onetrace_verify-0.2.0-py3-none-any.whl"],
    }, entries
    assert ONETRACE_WHL_SHA256 == RELEASE_0_2_0["onetrace-0.2.0-py3-none-any.whl"]
    assert ONETRACE_VERIFY_WHL_SHA256 == RELEASE_0_2_0["onetrace_verify-0.2.0-py3-none-any.whl"]


def test_no_development_build_is_left_in_the_tree(examined):
    """The release replaces the development build: no wheelhouse folder of one, no .devN file
    tracked, and no .devN requirement in the lock (what gate.sh's nodev check refuses on main)."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    examined(len(tracked), "tracked paths checked")
    assert not [t for t in tracked if t.startswith("wheelhouse/devbuild")], "a development wheelhouse folder is tracked"
    assert not [t for t in tracked if re.search(r"\.dev\d+[-.]", t)], "a .devN file is tracked"
    lock = "\n".join(line for line in (REPO / "requirements.lock").read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#"))
    assert not re.search(r"\.dev\d", lock), "the lock pins a development build"


def test_no_0_1_0_or_0_1_1_sdk_pin_is_left_in_the_lock(examined):
    """Requirement lines only: the lock's comments quote words which name 0.1.0
    as history, and a quotation is not a pin."""
    text = "\n".join(line for line in (REPO / "requirements.lock").read_text(
        encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))
    examined(1, "lock file read")
    for gone in ("onetrace==0.1.0", "onetrace-verify==0.1.0",
                 "onetrace==0.1.1", "onetrace-verify==0.1.1",
                 "onetrace==0.1.2", "onetrace-verify==0.1.2"):
        assert gone not in text, f"requirements.lock still names {gone}"


def test_the_fixture_tree_comes_from_the_0_2_0_sdist_on_pypi(examined):
    from tools import fetch_sdk_fixtures as f

    examined(1, "fixture source checked")
    assert f.SOURCE == "pypi"
    assert f.SDIST_NAME == "onetrace-0.2.0.tar.gz"
    assert f.SDIST_SHA256 == RELEASE_0_2_0[f.SDIST_NAME], f.SDIST_SHA256
    assert f.REQUIREMENT == "onetrace==0.2.0"


def test_the_wheel_cache_names_what_the_lock_pins(examined):
    from tools import fetch_wheel_cache as w

    entries = lock_entries()
    examined(len(w.WHEELS), "cached wheels checked against the lock")
    assert w.SOURCE == "pypi"
    assert set(w.WHEELS) == {"onetrace==0.2.0", "onetrace-verify==0.2.0"}
    for req, (name, sha) in w.WHEELS.items():
        assert entries[req] == sha, (req, sha)
        assert RELEASE_0_2_0[name] == sha, (name, sha)


def _fake_exam(root: Path) -> None:
    from tools import fetch_sdk_fixtures as f
    for p in f.EXPECTED:
        (root / "exam" / p).mkdir(parents=True)


def test_a_fixture_cache_from_another_sdist_is_not_ready(tmp_path, monkeypatch, examined):
    """The fixture folders are the same shape in 0.1.0 and 0.1.2, so their presence alone
    cannot tell a stale 0.1.0 cache from a current one. The cache records which sdist it came
    from, and `check()` reads that record."""
    from tools import fetch_sdk_fixtures as f

    monkeypatch.setattr(f, "CACHE", tmp_path)
    monkeypatch.setattr(f, "EXAM", tmp_path / "exam")
    _fake_exam(tmp_path)
    examined(4, "fixture caches checked")

    assert not f.check(), "a cache that names no source was accepted"
    (tmp_path / f.SOURCE_FILE).write_text(
        "onetrace-0.1.0.tar.gz 51344b75b779ddeb138b6e2e60f547f341b5c550a4864ec632863f41878121d5\n",
        encoding="utf-8")
    assert not f.check(), "a cache taken from the 0.1.0 sdist was accepted"
    (tmp_path / f.SOURCE_FILE).write_text(
        f"onetrace-0.1.2.tar.gz {ACCEPTED_29AG['onetrace-0.1.2.tar.gz']}\n", encoding="utf-8")
    assert not f.check(), "a cache taken from the 0.1.2 sdist was accepted"
    (tmp_path / f.SOURCE_FILE).write_text(f"{f.SDIST_NAME} {f.SDIST_SHA256}\n", encoding="utf-8")
    assert f.check(), "a cache from the accepted sdist was refused"


def test_both_installed_distributions_are_0_2_0(examined):
    examined(2, "installed distributions read")
    for dist in ("onetrace", "onetrace-verify"):
        got = importlib.metadata.version(dist)
        assert got == "0.2.0", (
            f"{dist} {got} is installed, not the pinned 0.2.0 -- install "
            f"with `python tools/install_pinned.py`")


# ------------------------------------------------------- the stage-order non-claim

_STAGE_ORDER = re.compile(r"stage[\s_-]*order", re.IGNORECASE)

#: The 0.1.2 non-claim, retired with the move to 0.2.0: its heading, and the gap it stated.
RETIRED_NON_CLAIM = ("No stage-order check in the pinned verifier", "runs no stage-order check")
#: The documents a user reads: the README, and the operator guide that carried the non-claim.
USER_DOCUMENTS = ("README.md", "OPERATOR_README.md")


def _shipped_text() -> dict[str, str]:
    """Every tracked text the console serves or ships, and the vendored viewer's modules."""
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                         check=True).stdout.split("\0")
    texts = {}
    for rel in out:
        if not rel or rel.startswith(("tests/", *NEVER)):
            continue
        if not (rel.startswith("src/") or rel.endswith(".md") or rel in ("Dockerfile",)):
            continue
        texts[rel] = (REPO / rel).read_text(encoding="utf-8", errors="replace")
    #: The viewer's code is under src/ (src/onetrace_console/viewer/), so it is read above.
    return texts


#: What a paragraph that names stage order must also say: that it is not checked.
_NEGATED = re.compile(r"no stage-order check|not checked for stage order", re.IGNORECASE)


def _flat(text: str) -> str:
    return " ".join(text.split())


def test_nothing_shipped_says_uploads_are_checked_for_stage_order(examined):
    """Code -- the console's own and the vendored viewer's -- never names stage order at all,
    so no page can say it. A document may name it only in a paragraph that says it is NOT
    checked. A claim worded without the phrase "stage order" is outside what a text scan can
    see; that limit is stated in the pin report."""
    texts = _shipped_text()
    examined(len(texts), "shipped texts scanned for stage order")
    bad = []
    for rel, text in texts.items():
        if rel.endswith(".md"):
            for para in text.replace("\r\n", "\n").split("\n\n"):
                flat = _flat(para)
                if _STAGE_ORDER.search(flat) and not _NEGATED.search(flat):
                    bad.append(f"{rel}: {flat[:160]}")
        else:
            #: A code line may name stage order only if the line itself says it is not checked
            #: -- the reasons in the viewer's REWORDED table (30bv §3.5) do. No page draws them.
            bad += [f"{rel}:{n}: {line.strip()}"
                    for n, line in enumerate(text.splitlines(), 1)
                    if _STAGE_ORDER.search(line) and not _NEGATED.search(line)]
    assert not bad, "stage order is named without saying it is not checked:\n" + "\n".join(bad)


def test_no_user_document_states_the_retired_stage_order_gap(examined):
    """0.2.0 checks stage order, so a user document that still says the pinned verifier doesn't
    would understate what the console's verifier checks, and name a release it no longer pins."""
    examined(len(USER_DOCUMENTS), "user documents read for the retired non-claim")
    stated = [f"{rel}: {phrase!r}" for rel in USER_DOCUMENTS
              for phrase in RETIRED_NON_CLAIM
              if phrase in _flat((REPO / rel).read_text(encoding="utf-8"))]
    assert not stated, "the 0.1.2 stage-order gap is still stated:\n" + "\n".join(stated)


def test_the_pinned_verifier_is_one_that_checks_stage_order(examined):
    """The premise of the test above, read from the installed verifier rather than assumed."""
    examined(1, "installed verifier read")
    import importlib.util
    assert importlib.metadata.version("onetrace-verify") == "0.2.0"
    package = Path(importlib.util.find_spec("onetrace_verify").submodule_search_locations[0])
    source = (package / "verify.py").read_text(encoding="utf-8")
    assert "\ndef check_stage_order(" in source and "check_stage_order(obj," in source
