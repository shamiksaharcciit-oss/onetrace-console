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
#: 0.1.2 (kept below as history) is no longer pinned. Since console 0.1.1, onetrace is 0.2.1
#: from PyPI (its two files, as PyPI serves them, written here by script); onetrace-verify stays 0.2.0.
#: Now onetrace 0.3.0 and onetrace-verify 0.3.0, from PyPI: its four files, as PyPI serves them,
#: written here by script from its JSON. The two wheels are the release candidate's, pinned before.
#: Since console 0.3.0, onetrace 0.4.0 and onetrace-verify 0.4.0, from PyPI: its four files, as PyPI
#: serves them, written here by script from its JSON.
RELEASE_0_4_0 = {
    "onetrace-0.4.0-py3-none-any.whl": "1a064a390de6d912d3bc873041247aa39f6bc4835bc6c2985f6a3b3ce96f0a86",
    "onetrace-0.4.0.tar.gz": "325ad2c41300690afa7db6d57f1ad59ab56b8d9e57485a166e31d12f1511981d",
    "onetrace_verify-0.4.0-py3-none-any.whl": "b2e0df9547a3d6c6761f5722762983b275cd114e5d5b82e4a3a4d5a773a5a2be",
    "onetrace_verify-0.4.0.tar.gz": "12fcc9ac308774be6d031ac33de1e0fa2038f0dcae188ed9106eac67c764ec48",
}
#: Since console 0.4.0, onetrace 0.5.0 and onetrace-verify 0.5.0, from PyPI: its four files, as PyPI
#: serves them, written here by script from its JSON.
RELEASE_0_5_0 = {
    "onetrace-0.5.0-py3-none-any.whl": "02ac0ce2a6b1581571623535c6219b3fec292c97a31fddd62f9dcc71453f0cc6",
    "onetrace-0.5.0.tar.gz": "e6e83977362d3911998254605977491c229d698b9efc89d9759659b7db2515ed",
    "onetrace_verify-0.5.0-py3-none-any.whl": "972a9de38b072d4a6f5754bdd05fcf831f87ed71316389f294bbc1b3a85ec313",
    "onetrace_verify-0.5.0.tar.gz": "2432f3619ff5a5926ce2873349919d210b17ab6f3bf17c0e2f9c390acec41aa8",
}
#: The development wheels of onetrace's c67e8b0, pinned before 0.4.0 was published. They are not the
#: published files, and nothing that installs the console names them now.
DEV_0_4_0 = {
    "onetrace-0.4.0-py3-none-any.whl": "eccd2c5afada6483d0dbe2de8fea8dd6c2c607136c3d4ed22ce9ab005491f818",
    "onetrace_verify-0.4.0-py3-none-any.whl": "35734c54dcdf059dc6f9b0adc85b836e94022677b5d011995d9770a03b2c0b6d",
}
RELEASE_0_3_0 = {
    "onetrace-0.3.0-py3-none-any.whl": "c20cc67cedd92a66b232af1cd970166df3c108cd86b31415ec299490f004a5bf",
    "onetrace-0.3.0.tar.gz": "7fa599d344d53873f077c26207d9df0add2e5d6e710b8cfe21cb90a0690857df",
    "onetrace_verify-0.3.0-py3-none-any.whl": "9b8f4db4ba75b4b7ae6871125246128de620cb25e7966bc1c140c3ad069483d2",
    "onetrace_verify-0.3.0.tar.gz": "44721f8291e64ae1b199d4f03b771eaefed643ef4aa99d658ab559d3badd7771",
}
#: Since console 0.2.0, onetrace 0.2.2 and onetrace-verify 0.2.1, from PyPI, the same way.
RELEASE_0_2_2 = {
    "onetrace-0.2.2-py3-none-any.whl": "5fbefd657d0622d8dad8d9506f118be2b417a9586589d8e50d59fd2a5fa21b1f",
    "onetrace-0.2.2.tar.gz": "b4ffd90b41ea9c2a794c973c35a5468f5f88b7b22922e4f356074c0dd683c26b",
    "onetrace_verify-0.2.1-py3-none-any.whl": "c001019740798f907ae8a4adace32c597fb749cf52fca0e668c932723a792119",
    "onetrace_verify-0.2.1.tar.gz": "6db523beef437a6dc8cf2a22fe54821f90d0b8f2f82f50a7e5f86d9d8f611f10",
}
RELEASE_0_2_1 = {
    "onetrace-0.2.1-py3-none-any.whl": "f55ca407d9ac1dd0451878c44a3c980e8b977b04ab0818d42e9eac780eaeb608",
    "onetrace-0.2.1.tar.gz": "b8d464936d907ac311bbb2969fbb20801cabff46682ba361429603ef7b2a4ff3",
}
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


def test_the_lock_pins_exactly_the_0_5_0_wheels(examined):
    entries = lock_entries()
    examined(2, "pins checked against PyPI's sha256")
    from tests.test_pins import CRYPTO_PINS
    #: The crypto extra's five, from PyPI, are held by tests/test_signed_run.py.
    assert set(entries) - CRYPTO_PINS == {
        "onetrace==0.5.0", "onetrace-verify==0.5.0"} and CRYPTO_PINS <= set(entries), entries
    assert {k: v for k, v in entries.items() if k not in CRYPTO_PINS} == {
        "onetrace==0.5.0": RELEASE_0_5_0["onetrace-0.5.0-py3-none-any.whl"],
        "onetrace-verify==0.5.0": RELEASE_0_5_0["onetrace_verify-0.5.0-py3-none-any.whl"],
    }, entries
    assert ONETRACE_WHL_SHA256 == RELEASE_0_5_0["onetrace-0.5.0-py3-none-any.whl"]
    assert ONETRACE_VERIFY_WHL_SHA256 == RELEASE_0_5_0["onetrace_verify-0.5.0-py3-none-any.whl"]


#: Where the pins are written for an install, and the one record of them.
PIN_SOURCES = ("requirements.lock", "src/onetrace_console/requirements.lock", "tools/fetch_wheel_cache.py", "PINS.md")


def development_wheel_problems(texts: dict[str, str]) -> list[str]:
    """{name: text} of the pin sources: none names a development wheel's hash; neither lock, nor
    PINS.md's current section, says the pins are on no index or names a local folder. (PINS.md's
    earlier sections keep their own history, and the wheel cache its unused wheelhouse source.)"""
    out = []
    for name, text in texts.items():
        out += [f"{name} names the development wheel {wheel}" for wheel, sha in DEV_0_4_0.items() if sha in text]
        if name == "PINS.md":
            text = text.split("\n## Before", 1)[0]
        elif not name.endswith(".lock"):
            continue
        flat = " ".join(text.split())
        out += [f"{name} says {phrase!r}" for phrase in ("on no index", "release candidate", "development wheels of")
                if phrase in flat]
        if name.endswith(".lock") and ("--no-index" in text or "--find-links" in text):
            out.append(f"{name} names a local source")
    return out


def _pin_sources() -> dict[str, str]:
    return {name: (REPO / name).read_text(encoding="utf-8") for name in PIN_SOURCES if (REPO / name).is_file()}


def test_the_0_5_0_pins_read_from_the_package_index(examined):
    """The release's four files are held, and no pin source still names the development wheels,
    an index they are not on, or a local source. (The wheel cache's own install from its verified
    folder is its design, and not looked at here.)"""
    from tools import fetch_wheel_cache as w
    texts = _pin_sources()
    examined(len(RELEASE_0_5_0) + len(texts), "release files and pin sources checked")
    assert sorted(RELEASE_0_5_0) == ["onetrace-0.5.0-py3-none-any.whl", "onetrace-0.5.0.tar.gz",
                                     "onetrace_verify-0.5.0-py3-none-any.whl", "onetrace_verify-0.5.0.tar.gz"]
    assert set(DEV_0_4_0.values()).isdisjoint(RELEASE_0_5_0.values())
    assert w.SOURCE == "pypi"
    assert development_wheel_problems(texts) == []


def test_sabotage_a_development_wheel_s_hash_back_in_the_lock_is_named(examined):
    texts = _pin_sources()
    dev = DEV_0_4_0["onetrace-0.4.0-py3-none-any.whl"]
    texts["requirements.lock"] = texts["requirements.lock"].replace(RELEASE_0_5_0["onetrace-0.5.0-py3-none-any.whl"], dev)
    examined(1, "planted lock")
    assert dev in texts["requirements.lock"]
    assert development_wheel_problems(texts) == [
        "requirements.lock names the development wheel onetrace-0.4.0-py3-none-any.whl"]


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
    assert set(w.WHEELS) == {"onetrace==0.5.0", "onetrace-verify==0.5.0"}
    for req, (name, sha) in w.WHEELS.items():
        assert entries[req] == sha, (req, sha)
        assert RELEASE_0_5_0[name] == sha, (name, sha)


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


def test_both_installed_distributions_are_the_pinned_ones(examined):
    """onetrace 0.5.0 and onetrace-verify 0.5.0, since console 0.4.0."""
    from tests.test_pins import PINNED_SDK_VERSION, PINNED_VERIFY_VERSION
    examined(2, "installed distributions read")
    for dist, want in (("onetrace", PINNED_SDK_VERSION), ("onetrace-verify", PINNED_VERIFY_VERSION)):
        got = importlib.metadata.version(dist)
        assert got == want, (
            f"{dist} {got} is installed, not the pinned {want} -- install "
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
    from tests.test_pins import PINNED_VERIFY_VERSION
    assert importlib.metadata.version("onetrace-verify") == PINNED_VERIFY_VERSION
    package = Path(importlib.util.find_spec("onetrace_verify").submodule_search_locations[0])
    source = (package / "verify.py").read_text(encoding="utf-8")
    assert "\ndef check_stage_order(" in source and "check_stage_order(obj," in source
