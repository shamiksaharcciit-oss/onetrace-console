"""What `pip install onetrace-console` gives a user: the right version, the SDK it was tested with,
its pins readable from the installed package, and comparisons that work on a plain install.

The last test builds the wheel, installs it into a fresh venv with the SDK's own wheels (the
same bytes PyPI serves, from the local wheel cache, so no network is needed), and checks that a
comparison there answers 200 with the same report as the pinned install.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from tests.test_pins import PINNED_SDK_VERSION

REPO = Path(__file__).resolve().parent.parent
META = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_the_version_is_0_2_0_everywhere(examined):
    import onetrace_console
    examined(3, "places the version is stated")
    assert META["version"] == "0.5.0"
    assert onetrace_console.__version__ == "0.5.0"
    out = subprocess.run([sys.executable, "-m", "onetrace_console", "--version"], capture_output=True,
                         text=True, env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert out.stdout.strip() == "0.5.0", out


def test_the_metadata_names_the_sdk_it_was_tested_with(examined):
    deps = META["dependencies"]
    examined(len(deps), "declared dependencies")
    assert "onetrace==0.6.0" in deps
    assert "onetrace-verify[crypto]==0.6.0" in deps
    assert META["requires-python"] == ">=3.12"
    assert len(META["authors"]) == 1 and META["authors"][0].get("name", "").strip(), META["authors"]


def test_no_private_username_in_the_shipped_project_files(examined):
    """No machine's own user folder is named: a `pytest-of-<user>` path may appear only with the
    placeholder, never a real account name."""
    import re
    files = [REPO / "pyproject.toml", REPO / "requirements.lock"]
    examined(len(files), "project files read")
    for f in files:
        named = re.findall(r"pytest-of-(?!<user>)[A-Za-z0-9_]+", f.read_text(encoding="utf-8"))
        assert not named, (f.name, named)


def test_the_pins_command_reads_the_lock_shipped_in_the_package(examined):
    """`onetrace-console pins` prints the lock from the installed package, which is the
    repository's own lock, byte for byte."""
    shipped = REPO / "src" / "onetrace_console" / "requirements.lock"
    examined(1, "shipped lock compared with the repository's")
    assert shipped.read_bytes() == (REPO / "requirements.lock").read_bytes()
    out = subprocess.run([sys.executable, "-m", "onetrace_console", "pins"], capture_output=True,
                         env={**os.environ, "PYTHONPATH": str(REPO / "src")})
    assert out.returncode == 0, out.stderr
    assert out.stdout.replace(b"\r\n", b"\n") == shipped.read_bytes().replace(b"\r\n", b"\n")


def test_the_shipped_lock_pins_the_0_5_0_wheels(examined):
    """The lock the installed package carries pins the SDK's two wheels as PyPI serves them."""
    from tests.test_pin_012 import RELEASE_0_6_0
    from tests.test_pins import _REQ
    text = (REPO / "src" / "onetrace_console" / "requirements.lock").read_text(encoding="utf-8")
    entries = {m.group("req"): m.group("sha") for m in _REQ.finditer(text)}
    examined(2, "SDK pins in the shipped lock")
    assert entries["onetrace==0.6.0"] == RELEASE_0_6_0["onetrace-0.6.0-py3-none-any.whl"]
    assert entries["onetrace-verify==0.6.0"] == RELEASE_0_6_0["onetrace_verify-0.6.0-py3-none-any.whl"]


#: onetrace-explain is never a dependency: the console runs it as a command where it is installed.
EXPLAIN_NAMES = re.compile(r"onetrace[-_.]explain", re.I)
#: The one sentence each README gives it, and the page it links.
EXPLAIN_INSTALL = "`pip install onetrace-explain`"
EXPLAIN_FORMAT = "https://oneproof.dev/onetrace/explain-format.md"


def dependency_problems(files: dict[str, str]) -> list[str]:
    """{name: text} of pyproject.toml and the two locks: none names onetrace-explain."""
    return [f"{name} names onetrace-explain" for name, text in files.items() if EXPLAIN_NAMES.search(text)]


def _dependency_files() -> dict[str, str]:
    return {n: (REPO / n).read_text(encoding="utf-8")
            for n in ("pyproject.toml", "requirements.lock", "src/onetrace_console/requirements.lock")}


def test_onetrace_explain_is_never_a_dependency(examined):
    files = _dependency_files()
    examined(len(files), "dependency files read")
    assert dependency_problems(files) == []


def test_sabotage_onetrace_explain_as_an_extra_is_named(examined):
    files = _dependency_files()
    files["pyproject.toml"] = files["pyproject.toml"].replace(
        "\n[project.scripts]", '\n[project.optional-dependencies]\nexplain = ["onetrace-explain==0.1.0"]\n\n[project.scripts]', 1)
    examined(1, "planted pyproject")
    assert "onetrace-explain==0.1.0" in files["pyproject.toml"]
    assert dependency_problems(files) == ["pyproject.toml names onetrace-explain"]


#: The ruled words of "Where it runs": the console's own network, and what the command does.
NETWORK_WORDS = ("The console makes no network calls but those you choose. The Explain button runs onetrace-explain, "
                 "if you install it, and that command sends an evidence packet to the model you configure. The first "
                 "time it would send a kind of item it has never sent to that endpoint, it lists them and asks first. "
                 "Turning on neighbours by input with a local model fetches that model's pinned files once from "
                 "huggingface.co, as above. Turning it on with an embedding endpoint of your own sends that endpoint "
                 "the kept inputs and outputs.")
#: The three network calls the console makes, each one you choose: "Where it runs" names all three.
NETWORK_EXCEPTIONS = ("The Explain button runs onetrace-explain", "fetches that model's pinned files once from huggingface.co",
                      "an embedding endpoint of your own sends that endpoint the kept inputs and outputs")


def _sentences(text: str) -> list[str]:
    """The sentences of `text`: split at its paragraphs first, so a paragraph's end ends its
    sentence, then within each at a stop before a capital or a backquote."""
    return [s for para in re.split(r"\n\s*\n", text) if para.strip()
            for s in re.split(r"(?<=[.!?])\s+(?=[A-Z`])", " ".join(para.split()))]


def explain_sentence_problems(name: str, text: str) -> list[str]:
    """The README says how to install onetrace-explain in one sentence, which links the explain
    format page; its "Where it runs" holds the ruled words, exactly; no other sentence names the
    command."""
    out = []
    install = [s for s in _sentences(text) if EXPLAIN_INSTALL in s]
    if len(install) != 1:
        out.append(f"{name}: {len(install)} sentences give {EXPLAIN_INSTALL}")
    elif EXPLAIN_FORMAT not in install[0]:
        out.append(f"{name}: the install sentence lacks {EXPLAIN_FORMAT!r}")
    where = text.split("\n## Where it runs\n", 1)[1].split("\n## ", 1)[0] if "\n## Where it runs\n" in text else ""
    if NETWORK_WORDS not in " ".join(where.split()):
        out.append(f"{name}: \"Where it runs\" does not hold the ruled words")
    ruled = _sentences(NETWORK_WORDS)
    out += [f"{name}: another sentence names onetrace-explain: {s[:80]!r}" for s in _sentences(text)
            if EXPLAIN_NAMES.search(s) and s not in install and s not in ruled]
    return out


@pytest.mark.parametrize("name", ["README.md", "PYPI_DESCRIPTION.md"])
def test_each_readme_says_how_to_make_explain_work_and_what_it_sends(name, examined):
    examined(1, name)
    assert explain_sentence_problems(name, (REPO / name).read_text(encoding="utf-8")) == []


def test_sabotage_a_readme_without_the_format_link_is_named(examined):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    examined(1, "planted README")
    assert EXPLAIN_FORMAT in text
    assert explain_sentence_problems("README.md", text.replace(EXPLAIN_FORMAT, "https://example.invalid/")) == [
        f"README.md: the install sentence lacks {EXPLAIN_FORMAT!r}"]


def test_sabotage_the_link_moved_out_of_the_install_sentence_is_named(examined):
    """The link put in a paragraph of its own, after the sentence: a paragraph's end ends its
    sentence, whatever character the next paragraph begins with."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    old = ", and its format is set out at [explain-format.md](https://oneproof.dev/onetrace/explain-format.md)."
    examined(1, "planted README")
    assert old in text
    moved = text.replace(old, ".\n\n[explain-format.md](https://oneproof.dev/onetrace/explain-format.md) sets out its format.")
    assert explain_sentence_problems("README.md", moved) == [
        f"README.md: the install sentence lacks {EXPLAIN_FORMAT!r}"]


NEIGHBOURS_HEAD = "## Neighbours by input (optional, local only)"


def neighbours_section_problems(name: str, text: str) -> list[str]:
    """The README's section on the extra: how to install it; off until turned on, local only; the pinned
    fetch from huggingface.co, checked, and that no text leaves the machine with a local model; what each
    of the ladder's two fixed readings means, in the console's own words, and what neither means; no
    word of why. And "Where it runs" names all three of the console's network calls."""
    from onetrace_console.neighbours.pages import BY_RECORD, NEAR_ONE
    out = []
    if f"\n{NEIGHBOURS_HEAD}\n" not in text:
        return [f"{name}: no section {NEIGHBOURS_HEAD!r}"]
    section = " ".join(text.split(f"\n{NEIGHBOURS_HEAD}\n", 1)[1].split("\n## ", 1)[0].split())
    for said in ('pip install "onetrace-console[neighbours]"', "It is off until you turn it on at `/neighbours/setup`",
                 "it never runs on a public console", "fetches that model's pinned files once from huggingface.co, at "
                 "the pinned revision, and checks each file against its pinned sha256", "Nothing else is fetched, and "
                 "no text leaves the machine", f'"{BY_RECORD}" means the two runs\' digests for that file are equal',
                 f'"{NEAR_ONE}" means the digests are not equal and the embedder\'s number rounds to 1.000',
                 "Neither is a judgement that two runs did the same thing"):
        if said not in section:
            out.append(f"{name}: the section does not say {said[:60]!r}")
    if re.search(r"\b(because|why)\b", section, re.I):
        out.append(f"{name}: the section says why")
    where = " ".join(text.split("\n## Where it runs\n", 1)[1].split("\n## ", 1)[0].split())
    out += [f"{name}: \"Where it runs\" does not name {e!r}" for e in NETWORK_EXCEPTIONS if e not in where]
    return out


@pytest.mark.parametrize("name", ["README.md", "PYPI_DESCRIPTION.md"])
def test_each_readme_says_what_the_neighbours_extra_is_fetches_and_reads(name, examined):
    examined(1, name)
    assert neighbours_section_problems(name, (REPO / name).read_text(encoding="utf-8")) == []


def test_the_neighbours_section_is_the_same_in_both_readmes(examined):
    sections = [(REPO / n).read_text(encoding="utf-8").split(f"\n{NEIGHBOURS_HEAD}\n", 1)[1].split("\n## ", 1)[0]
                for n in ("README.md", "PYPI_DESCRIPTION.md")]
    examined(2, "sections")
    assert sections[0] == sections[1]


@pytest.mark.parametrize("dropped, missing", [
    (" Turning on neighbours by input with a local model fetches that model's pinned files once from huggingface.co, "
     "as above.", 1),
    (" Turning it on with an embedding endpoint of your own sends that endpoint the kept inputs and outputs.", 2),
], ids=["the fetch", "the endpoint"])
def test_sabotage_a_network_sentence_missing_an_exception_is_named(dropped, missing, examined):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    examined(1, "planted README")
    one = text.replace(dropped, "")
    assert one != text
    assert f"README.md: \"Where it runs\" does not name {NETWORK_EXCEPTIONS[missing]!r}" in neighbours_section_problems("README.md", one)
    assert 'README.md: "Where it runs" does not hold the ruled words' in explain_sentence_problems("README.md", one)


def test_sabotage_a_section_saying_why_is_named(examined):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    examined(1, "planted README")
    why = text.replace("Neither is a judgement", "This is why neither is a judgement")
    assert "README.md: the section says why" in neighbours_section_problems("README.md", why)


def test_sabotage_a_readme_whose_network_words_differ_from_the_ruled_ones_is_named(examined):
    text = (REPO / "README.md").read_text(encoding="utf-8")
    examined(1, "planted README")
    assert "and asks first." in text
    assert explain_sentence_problems("README.md", text.replace("and asks first.", "and asks.")) == [
        'README.md: "Where it runs" does not hold the ruled words']


def test_the_changelog_link_is_the_public_repositorys_at_the_release_tag(examined):
    """PyPI's page links the upgrade notes: `Changelog`, the public repository's CHANGELOG.md at this
    release's tag, the same address the PyPI description's own CHANGELOG link gives."""
    urls = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    linked = re.findall(r"\]\((https://github\.com/[^/]+/[^/]+/blob/v[^/]+/CHANGELOG\.md)\)",
                        (REPO / "PYPI_DESCRIPTION.md").read_text(encoding="utf-8"))
    examined(1, "project URL")
    assert linked == [urls["Changelog"]] and list(urls) == ["Changelog"]
    assert urls["Changelog"].endswith(f"/blob/v{META['version']}/CHANGELOG.md")


def test_a_plain_install_is_identified_by_its_record(tmp_path, examined):
    """With no install report and no direct_url.json, the build is named by the installed
    distribution's version and the RECORD lines of its own files: the files the wheel itself
    lists, with their hashes. What pip writes per install is left out: the launchers outside the
    install root, compiled files, and its own `.dist-info` bookkeeping."""
    from onetrace_console.compare import record_digest
    lines = ["onetrace/__init__.py,sha256=AAAA,10", "onetrace/emit.py,sha256=BBBB,20",
             "onetrace-0.2.0.dist-info/METADATA,sha256=CCCC,30"]
    unhashed = ["onetrace/__pycache__/emit.cpython-312.pyc,,", "onetrace-0.2.0.dist-info/INSTALLER,,",
                "onetrace-0.2.0.dist-info/RECORD,,"]
    per_install = ["../../bin/onetrace,sha256=DDDD,200", "../../Scripts/onetrace.exe,sha256=EEEE,108000",
                   "onetrace/__pycache__/emit.cpython-312.pyc,sha256=FFFF,900",
                   "onetrace-0.2.0.dist-info/INSTALLER,sha256=GGGG,4",
                   "onetrace-0.2.0.dist-info/REQUESTED,sha256=HHHH,0",
                   "onetrace-0.2.0.dist-info/direct_url.json,sha256=IIII,90"]
    a = record_digest("0.2.0", lines + unhashed)
    b = record_digest("0.2.0", list(reversed(lines)) + ["onetrace/__pycache__/emit.cpython-313.pyc,,"] + per_install)
    examined(2, "RECORDs of one wheel, installed two ways")
    assert a == b and a.startswith("record:0.2.0:")
    assert record_digest("0.2.0", lines[:2]) != a, "a different set of files is a different build"
    assert record_digest("0.2.1", lines) != a, "a different version is a different build"


def _sdk_record(tmp_path, name: str) -> tuple[str, list[str]]:
    """onetrace's version and installed RECORD in a fresh venv, installed with plain pip from the
    local wheel cache (the bytes PyPI serves) and nothing else."""
    _wheels()
    venv = tmp_path / name
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    installed = subprocess.run([str(py), "-m", "pip", "install", "-q", "--no-index", "--find-links",
                                str(REPO / ".wheel-cache"), f"onetrace=={PINNED_SDK_VERSION}"],
                               capture_output=True, text=True, env=clean)
    assert installed.returncode == 0, installed.stderr[-2000:]
    read = subprocess.run([str(py), "-c", "import importlib.metadata as m, json; d = m.distribution('onetrace'); "
                           "print(json.dumps([d.version, d.read_text('RECORD')]))"],
                          capture_output=True, text=True, env=clean, check=True)
    version, record = json.loads(read.stdout)
    return version, record.splitlines()


def _all_hashed(version: str, lines: list[str]) -> str:
    """0.4.0's RECORD digest: every hashed line, the launchers outside the install root included."""
    hashed = sorted(l.strip() for l in lines if l.strip() and l.split(",")[1:2] and l.split(",")[1].startswith("sha256="))
    return f"record:{version}:" + hashlib.sha256("\n".join(hashed).encode("utf-8")).hexdigest()


def test_the_same_wheel_in_two_venvs_has_one_record_identity(tmp_path, examined):
    """The SDK's wheel, installed with plain pip into two fresh venvs: one `record:` identity, though
    each venv's launcher differs; a changed file of the package gives another."""
    from onetrace_console.compare import record_digest
    (v1, r1), (v2, r2) = _sdk_record(tmp_path, "venv-one"), _sdk_record(tmp_path, "venv-two")
    examined(2, "fresh venvs with the same SDK wheel")
    outside = [sorted(l for l in r if l.startswith("../") and ",sha256=" in l) for r in (r1, r2)]
    print(f"launcher lines: venv one {outside[0]}; venv two {outside[1]}")
    print(f"identity: venv one {record_digest(v1, r1)}; venv two {record_digest(v2, r2)}")
    print(f"every hashed line (0.4.0's digest): venv one {_all_hashed(v1, r1)}; venv two {_all_hashed(v2, r2)}")
    assert outside[0] and outside[0] != outside[1], "the premise: each venv's launcher has its own hash"
    assert record_digest(v1, r1) == record_digest(v2, r2) and record_digest(v1, r1).startswith(f"record:{v1}:")
    #: The launcher's hash no longer enters it: change it, and nothing changes.
    launcher = outside[0][0]
    moved = [l if l != launcher else launcher.split(",")[0] + ",sha256=changed," + launcher.split(",")[2] for l in r1]
    assert record_digest(v1, moved) == record_digest(v1, r1)
    #: A different file in the package is a different build.
    own = next(l for l in r1 if l.startswith("onetrace/") and ",sha256=" in l)
    changed = [l if l != own else own.split(",")[0] + ",sha256=another," + own.split(",")[2] for l in r1]
    assert record_digest(v1, changed) != record_digest(v1, r1)
    assert record_digest(v1, r1 + ["onetrace/added.py,sha256=added,10"]) != record_digest(v1, r1)


def test_sabotage_the_launcher_lines_put_back_are_caught(tmp_path, examined):
    """Put the `../` lines back into the digest (0.4.0's way), and the two venvs differ again."""
    (v1, r1), (v2, r2) = _sdk_record(tmp_path, "venv-one"), _sdk_record(tmp_path, "venv-two")
    examined(2, "fresh venvs with the same SDK wheel")
    assert _all_hashed(v1, r1) != _all_hashed(v2, r2)


def _wheels() -> dict[str, Path]:
    from tools.fetch_wheel_cache import check
    cache = REPO / ".wheel-cache"
    found = {p.name.split("-")[0]: p for p in cache.glob("*.whl")}
    if not check():
        pytest.fail(f"the local wheel cache is not ready: {cache}\n    python tools/fetch_wheel_cache.py")
    return found


def test_a_plain_pip_install_compares_with_the_same_report_as_the_pinned_install(tmp_path, examined):
    """Build the wheel; install it into a fresh venv with pip resolving every dependency from the
    SDK's wheels alone, no other index and no install report; deliver two runs and compare them there. The comparison answers, and its
    report is the pinned install's, byte for byte."""
    wheels = _wheels()
    #: Built from a copy of the tracked files, so the build writes nothing into the repository.
    tree = tmp_path / "tree"
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    for rel in filter(None, tracked):
        if (REPO / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((REPO / rel).read_bytes())
    dist = tmp_path / "dist"
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    #: One process for each: run in the same process after build_wheel, setuptools writes the
    #: sdist into a folder left from the wheel's build, not into `dist`.
    for build in ("build_wheel", "build_sdist"):
        subprocess.run([sys.executable, "-c", f"import sys; from setuptools import build_meta as b; "
                        f"print(b.{build}(sys.argv[1]))", str(dist)], cwd=tree, check=True,
                       capture_output=True, env=clean)
    console_whl = next(dist.glob("onetrace_console-0.5.0-*.whl"))
    _check_the_viewer_ships_without_its_tests(console_whl, next(dist.glob("onetrace_console-0.5.0.tar.gz")))
    #: The wheel carries the demo store's builder and trust file, so `onetrace-console demo` works
    #: installed: it builds the demo's runs where it is started (0.1.1).
    import zipfile
    demo = REPO / "src" / "onetrace_console" / "demo_store"
    want = {f"onetrace_console/demo_store/{p.relative_to(demo).as_posix()}"
            for p in demo.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    with zipfile.ZipFile(console_whl) as whl:
        assert want and want <= set(whl.namelist()), sorted(want - set(whl.namelist()))[:5]
        #: The model-call schema copy ships, byte for byte (the record panel's labels).
        from onetrace_console.model_call import SCHEMA_FILE
        assert whl.read(f"onetrace_console/{SCHEMA_FILE}") == (REPO / "src" / "onetrace_console" / SCHEMA_FILE).read_bytes()
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    py = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    #: The console's wheel, with pip resolving its dependencies itself from the wheel cache as a
    #: local index (the bytes PyPI serves for them) and nothing else: no wheelhouse, no other
    #: index. The SDK so arrives as from an index, so pip leaves no direct_url.json for it.
    installed = subprocess.run([str(py), "-m", "pip", "install", "-q", "--no-index", "--find-links",
                                str(REPO / ".wheel-cache"), str(console_whl)],
                               capture_output=True, text=True, env=clean)
    assert installed.returncode == 0, installed.stderr[-2000:]
    subprocess.run([str(py), "-m", "pip", "check"], check=True, capture_output=True, env=clean)
    #: The premise: the SDK arrived as from an index, so neither earlier identity source applies.
    found = subprocess.run([str(py), "-c", "import importlib.metadata as m; d = m.distribution('onetrace'); "
                            "print(d.read_text('direct_url.json') is None)"],
                           capture_output=True, text=True, env=clean).stdout.strip()
    assert found == "True", "the SDK was installed as a direct reference, so the RECORD path is not tested"
    #: And the plain install names its build by RECORD. Asserted, not left to the comparison: the
    #: temporary folder may sit inside a git checkout, where a later source would answer instead.
    named = subprocess.run([str(py), "-c", "from onetrace_console.compare import sdk_build_digest; "
                            "print(sdk_build_digest())"], capture_output=True, text=True, env=clean)
    assert named.stdout.startswith(f"record:{PINNED_SDK_VERSION}:"), (named.stdout, named.stderr[-1500:])
    listed = subprocess.run([str(py), "-m", "pip", "list"], capture_output=True, text=True, env=clean).stdout
    from onetrace_console import __version__
    assert "onetrace-console" in listed and __version__ in listed, listed
    here = _compare_report(sys.executable, {"PYTHONPATH": str(REPO / "src")}, tmp_path / "pinned")
    there = _compare_report(str(py), {}, tmp_path / "plain")
    examined(2, "comparisons of the same two runs: the pinned install and a plain one")
    assert there["status"] == 200, there
    assert here["status"] == 200, here
    #: Every comparison lays the two runs out in a fresh temporary folder, and since console 0.4.0
    #: the SDK is given them relative to it, as `a` and `b`: the report names no temporary folder, so
    #: the two reports are the same bytes with nothing masked.
    assert _mask_compare_folders(there["diff"])[1] == _mask_compare_folders(here["diff"])[1] == 0
    assert re.search(r'"path": ?"a"', there["diff"]) and re.search(r'"path": ?"b"', there["diff"])
    assert there["diff"] == here["diff"], "the plain install's comparison report differs"


#: A comparison folder's path in a report, as JSON writes it: on Windows each backslash is escaped,
#: so the separator before `a` or `b` is two characters there and one (`/`) elsewhere.
_COMPARE_FOLDER = re.compile(r'"path": ?"[^"]*onetrace-compare-[^"/\\]+(?:/|\\\\)([ab])"')


def _mask_compare_folders(report: str) -> tuple[str, int]:
    return _COMPARE_FOLDER.subn(r'"path":"<compare folder>/\1"', report)


def test_the_compare_folder_mask_matches_the_path_on_every_platform(examined):
    """The same report, written on Linux and on Windows: masked, they are the same bytes, and each
    path field is masked once. Nothing else in the report is touched."""
    linux = '{"baseline":{"path":"/tmp/onetrace-compare-k2j8x_1q/a","run_id":"q1"},' \
            '"candidate":{"path":"/tmp/onetrace-compare-k2j8x_1q/b","run_id":"q2"}}'
    windows = ('{"baseline":{"path":"C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\'
               'onetrace-compare-r7b_bv2h\\\\a","run_id":"q1"},'
               '"candidate":{"path":"C:\\\\Users\\\\RUNNER~1\\\\AppData\\\\Local\\\\Temp\\\\'
               'onetrace-compare-r7b_bv2h\\\\b","run_id":"q2"}}')
    import json
    assert json.loads(windows)["baseline"]["path"].endswith("onetrace-compare-r7b_bv2h\\a"), "a real Windows path"
    examined(2, "reports, one per platform")
    (ml, nl), (mw, nw) = _mask_compare_folders(linux), _mask_compare_folders(windows)
    assert (nl, nw) == (2, 2), (nl, nw)
    assert ml == mw
    assert '"run_id":"q1"' in mw and '"run_id":"q2"' in mw


def _check_the_viewer_ships_without_its_tests(wheel: Path, sdist: Path) -> None:
    """The viewer's code ships in both; its tests, and anything named for where they came from,
    in neither."""
    import tarfile
    import zipfile
    with zipfile.ZipFile(wheel) as z:
        in_wheel = z.namelist()
    with tarfile.open(sdist) as t:
        in_sdist = [m.name.split("/", 1)[1] for m in t.getmembers() if "/" in m.name]
    for kind, names in (("wheel", in_wheel), ("sdist", in_sdist)):
        viewer = [n for n in names if "onetrace_console/viewer/" in n]
        assert any(n.endswith("onetrace_console/viewer/page.py") for n in viewer), (kind, viewer[:5])
        assert any(n.endswith("viewer/_vendor/ONETRACE_CONSOLE_SKIN_v1.md") for n in viewer), kind
        assert any(n.endswith("viewer/PROVENANCE.md") for n in viewer), kind
        assert not [n for n in viewer if "/tests/" in n], (kind, "the viewer's tests ship")
        named = [n for n in names if any(w in n for w in ("from_core", "Core_Ruling", ".tar.gz"))]
        assert not named, (kind, named)


_COMPARE = r'''
import json, sys, threading, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from onetrace_console.config import Config
from onetrace_console.serve import Handler, _render_all_pages
from onetrace_console.store import Store
from onetrace_console.access_log import AccessLog
root = Path(sys.argv[1]); root.mkdir(parents=True)
Handler.store_root = root; Handler.store = Store(root / "store")
Handler.config = Config(sign_in={**Config().sign_in, "enabled": False})
Handler.access_log = AccessLog(root / "access_log", max_segment_bytes=Handler.config.access_log_max_segment_bytes)
_render_all_pages(Handler.store, root, Handler.config)
httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{httpd.server_address[1]}"
keys = []
for tar in sys.argv[2:]:
    req = urllib.request.Request(base + "/v1/runs", data=Path(tar).read_bytes(), method="POST")
    keys.append(json.load(urllib.request.urlopen(req))["run_key"])
req = urllib.request.Request(f"{base}/compare?a={keys[0]}&b={keys[1]}", method="POST")
try:
    got = json.load(urllib.request.urlopen(req)); status = 200
except urllib.error.HTTPError as e:
    print(json.dumps({"status": e.code, "body": e.read().decode()[:2000]})); raise SystemExit(0)
from onetrace_console.compare import DIFF
cmp = Handler.store.get_comparison(got["comparison_key"])
run = cmp.verb(DIFF)
report = {name: Handler.store.get(key).decode() for name, key in run.reports}
print(json.dumps({"status": status, "diff": report.get("diff.json")}))
httpd.shutdown()
'''


def _compare_report(python: str, env: dict, root: Path) -> dict:
    from tests.test_ux_screens import RUNS, _checked_fixture
    from tests.conftest import make_tar
    _checked_fixture()
    tars = []
    for name in ("query-day1", "query-day2", "ingest-day1", "ingest-day2"):
        folder = RUNS / name
        files = {p.relative_to(folder).as_posix(): p.read_bytes() for p in sorted(folder.rglob("*")) if p.is_file()}
        files["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {n}\n" for n, b in sorted(files.items())).encode()
        tar = root.parent / f"{root.name}-{name}.tar"
        tar.write_bytes(make_tar(files))
        tars.append(str(tar))
    script = root.parent / f"{root.name}-compare.py"
    script.write_text(_COMPARE, encoding="utf-8")
    out = subprocess.run([python, str(script), str(root), *tars], capture_output=True, text=True,
                         env={**{k: v for k, v in os.environ.items() if k != "PYTHONPATH"}, **env}, timeout=600)
    assert out.returncode == 0, out.stderr[-3000:]
    return json.loads(out.stdout.strip().splitlines()[-1])
