"""Every feature, extra and option the CHANGELOG names for a release has its place in the README.

Each entry of the release's CHANGELOG section (its bold lead) is in its table once (`CLAIMS` for this
release, `EARLIER` for the ones before it), with its kind and the words in the README that cover it.
Every feature, extra and option has words; an upgrade note, a fix or the demo's own data has words
where the README states it; an entry a later one supersedes has none. Both readmes (`README.md` and
`PYPI_DESCRIPTION.md`, generated from it) must hold every entry's words, and name each configuration
key added since 0.5.0.
Each rule has its own sabotage below.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import fields
from pathlib import Path

import pytest

from onetrace_console.config import Config

REPO = Path(__file__).resolve().parent.parent
RELEASE = "0.7.0"
#: The package's own version: the next release, whose heading says "(not released)" until the release
#: step drops it. Every other version's heading is plain.
VERSION = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
UNRELEASED = " (not released)"
#: A released heading may give its date: "## [0.6.0] - 2026-11-03".
DATED = re.compile(r" - \d{4}-\d{2}-\d{2}")
_HEADING = re.compile(r"^## \[([^\]]+)\](.*)$", re.M)
READMES = ["README.md", "PYPI_DESCRIPTION.md"]
#: Kinds whose README words are held; the others are listed and need none.
HELD = {"feature", "extra", "option"}

#: 0.6.1's, held as they were: (the entry's lead, as it starts, its kind, the README words that cover it).
CLAIMS_061 = [
    ("The confirm button shows the download", "fix", None),
    ("The extra missing, said plainly", "fix", None),
    ("The ladder marks a drop only where there is one", "fix", None),
    ("Two dropdowns to choose a pair", "feature", "- **Choosing two runs:**"),
    ("Progress while the console starts", "option", "`--quiet` keeps them silent"),
    ("The Explain panel reads as a flow", "feature", "- **The Explain panel's flow:**"),
    ("The first-send question in plain words", "wording", None),
    ("A key variable not set says where to look", "feature",
     "the variable its `key_env` names, and whether it is set, never its value"),
    ("Lead: where to look first", "wording", None),
    ("Backticks as code", "fix", None),
    ("A check the page already ran reads as run", "feature", "A check the page already ran reads \"Run on this page\""),
    ("Include the kept text of outputs that differ", "feature",
     "A checkbox beside Send, off by default, includes the kept text of outputs that differ"),
    ("A settings button at the top right", "feature", "- **Settings, top right:**"),
]
#: 0.6.0's, held as they were.
CLAIMS_060 = [
    ("One line at the first difference names what kind of thing differs there", "feature",
     "- **The kind of difference:**"),
    ("A JSON output's members that differ, by path", "feature", "- **JSON outputs, by member:**"),
    ("The first run to leave the reference, by step or after a time", "feature",
     "- **The first run to leave the reference:**"),
    ("A step's span tree, from the app's own traces", "feature", "- **A step's spans:**"),
    ("The app's spans at the first difference, ranked", "feature", "- **Spans at the first difference:**"),
    ("The demo's app traces, example data", "demo data", None),
    ("A run's configuration against its pipeline's reference run", "feature",
     "- **A run's configuration against the reference run:**"),
    ("A model step's token as text, on a local console", "feature", "- **A model step's token as text:**"),
]
#: 0.5.1's, held as they were.
CLAIMS_051 = [
    ("onetrace 0.6.1 and onetrace-verify 0.6.1", "pins", "`onetrace` 0.6.1 and `onetrace-verify` 0.6.1"),
    ("An earlier console's comparison page says when its pair was compared again", "feature",
     "Since 0.5.1 the earlier page says so, and links to the newer one"),
    ("The operator README says what the container image leaves out", "docs, in the operator README", None),
    ("A read interface over the console store", "feature", "## Reading a store from another program"),
    ("The run index is `onetrace-console-run-index/0.2`", "format", None),
    ("The hosted demo keeps both of the public site's links", "demo data", None),
    ("A run's page links each model-call record to its view", "feature",
     "On a run's page, each record under \"What came out\" links to its section on the step's page"),
    ("Shipped comments and docstrings are reworded", "wording", None),
]
#: 0.5.0's, held as they were but for the pins 0.5.1 moves.
CLAIMS_050 = [
    ("Upgrading from 0.4.0", "upgrade note", "## Upgrading from 0.4"),
    ("onetrace 0.6.0 and onetrace-verify 0.6.0", "pins, superseded by 0.5.1's", None),
    ("Model-call records in `model-call-record/1.0`", "feature", "## Model-call records"),
    ("The demo's two example model-call records", "demo data", None),
    ("A record's fields under the format's own groups", "feature", "under the format's own groups"),
    ("The token timeline", "feature", "drawn as a token timeline"),
    ("Model-call records compared by onetrace's comparator", "feature", "onetrace's comparator's report"),
    ("Runs that share a model's files", "feature", "(`model.files_digest`) lists the other runs"),
    ('"Action authorized, effect confirmed" reads', "feature", "- **Gated steps:**"),
    ("An exact index of the runs", "feature", "## Searching the runs"),
    ("Benchmarks.", "feature", "- **Benchmarks.**"),
    ('"What changed?" takes a benchmark', "feature", '- **"What changed?"** takes a benchmark first'),
    ("A benchmark's variation profile", "feature", "- **A benchmark's variation profile.**"),
    ("A run's verdict against its pipeline's reference", "feature", "- **The reference.**"),
    ("Every verdict names its reference", "feature", 'beside "against the reference" and the seal'),
    ("The mark says what it does", "feature", "the page says so beside the mark and its undo"),
    ("Neighbours by input", "extra", "## Neighbours by input (optional, local only)"),
    ("The Overview opens with its four count cards", "feature", "the Overview opens with its four count cards"),
    ("A run's span context", "feature", "- **Span context:**"),
    ("A run whose model-call records are in a draft format", "feature",
     "A run whose records are in the draft format says so in one line"),
    ("The hosted demo records P10", "demo data", None),
    ("`demo --public --build --site-links FILE`", "option", "- `--site-links FILE`"),
    ("Verdicts as runs arrive", "feature", "- **Verdicts as runs arrive.**"),
    ("Compare on the public demo", "feature", "## Compare on the public demo"),
    ("The console's listen queue", "fix", None),
    ("A graph run that recorded no plan", "fix", None),
    ("A plain `pip install` names the onetrace build alike", "fix",
     "So a pinned install and a plain one name the same comparison differently."),
    ("A run's incident takes", "fix", "An incident's page has a new address; the old address no longer answers."),
]
#: The earlier releases' tables, by release.
EARLIER = {"0.6.1": CLAIMS_061, "0.6.0": CLAIMS_060, "0.5.1": CLAIMS_051, "0.5.0": CLAIMS_050}
#: This release's (0.7.0), under `## [Unreleased]` until its version was set.
CLAIMS: list = [
    ("The same release files on Windows as on Linux", "fix", None),
    ("The PowerShell install line quotes by PowerShell's rules", "fix", None),
    ("Runs recorded by onetrace 0.7 open", "feature", "- Runs recorded by onetrace 0.7, in its format 0.4"),
    ("onetrace 0.7.1 and onetrace-verify 0.7.1", "pins", "`onetrace` 0.7.1 and `onetrace-verify` 0.7.1"),
    ("Runs recorded without configuration open", "feature", "- Runs recorded without configuration, by onetrace-auto, open"),
    ("Whether a run closed, and how it ended", "feature", "- Whether a run closed, and how it ended,"),
    ("Step expectations", "feature", "- Step expectations: a run's page lists each step's declared expectations"),
    ("Expectations declared after the run", "feature", "- Expectations declared after the run: on a local console"),
    ("A tokenizer from this machine", "feature", "- A tokenizer from this machine: where a model step's token"),
    ("The rendered checks name a page view they stalled on", "fix", None),
    ("A sub-agent's run is not read as the step's input", "fix", None),
    ("The first-run-to-leave page says its answer first", "page", None),
    ("The first-run-to-leave page says how to read it in plain words", "wording", None),
    ("The reference line is one line", "fix", None),
    ("Each gap on the first-run-to-leave page gives its reason", "page", None),
    ("One \"Find the first run to leave after\" control", "page", None),
    ("Start-up progress on Windows PowerShell 5.1's console", "fix", None),
    ("The Compare picker keeps each label with its select", "fix", None),
    ("The app's spans at a differing step, attribute by attribute", "page", None),
    ("Set up Explain in the console", "feature", "- Set up Explain here: on a local console"),
    ("Whether a key is stored, with Replace and Remove", "page", None),
    ("No keychain, said plainly", "page", None),
    ("The settings menu reads the keychain", "page", None),
    ("Who can read the key, said on the page", "wording", None),
    ("onetrace-explain 0.3 with its keyring extra, beside the console", "wording", None),
    ("A key no request can carry is refused", "fix", None),
    ("Every demo pipeline keeps its inputs", "feature", "Every pipeline but the reference demo's keeps the inputs its steps read"),
    ("A static export's first-run-to-leave control is shown disabled", "fix", None),
    ("onetrace-explain 0.3.0 beside the console, as released", "pins", 'pip install "onetrace-explain[keyring]>=0.3"'),
    ("The sign-in limit counts a rolling window", "fix", None),
    ("A locked keychain refuses a Save with no key", "fix", None),
    ("The settings menu reads `key_source` before `key_env`", "fix", None),
    ("A static export has no live Compare", "fix", None),
    ("CSRF values are compared in constant time", "fix", None),
]
#: The configuration keys added since 0.5.0, each named in the README.
NEW_KEYS = ["compare_cache", "compare_client_header", "compare_per_minute", "compare_running", "compare_queue",
            "compare_wait_seconds", "compare_verb_seconds", "tracing", "tokenizers"]


def leads(changelog: str, release: str = RELEASE) -> list[str]:
    """The bold leads of a release's CHANGELOG entries, in order."""
    start = changelog.index(f"## [{release}]")
    end = changelog.find("\n## [", start + 1)
    section = changelog[start:end if end != -1 else None]
    return re.findall(r"^- \*\*(.+?)\*\*", section, re.MULTILINE)


def tables() -> dict[str, list]:
    """Every release's table, this one's first."""
    return {RELEASE: CLAIMS, **EARLIER}


def claim_problems(changelog: str, readmes: dict[str, str]) -> list[str]:
    """Where an entry has no place in its release's table, or a held one's words are missing from a readme."""
    out = []
    for release, claims in tables().items():
        out += [f"CLAIMS gives the {kind} {lead!r} no README words" for lead, kind, words in claims
                if kind in HELD and words is None]
        found = leads(changelog, release)
        for lead in found:
            matched = [c for c in claims if lead.startswith(c[0])]
            if len(matched) != 1:
                out.append(f"the entry {lead!r} is in CLAIMS {len(matched)} times")
        out += [f"CLAIMS names {c[0]!r}, which no entry starts with" for c in claims
                if not any(lead.startswith(c[0]) for lead in found)]
    for name, text in readmes.items():
        out += [f"{name} does not hold {words!r} ({lead})" for claims in tables().values()
                for lead, kind, words in claims if words is not None and words not in text]
        out += [f"{name} does not name the key {key!r}" for key in NEW_KEYS if f"`{key}`" not in text
                and f'"{key}"' not in text]
    return out


def _read() -> tuple[str, dict[str, str]]:
    return ((REPO / "CHANGELOG.md").read_text(encoding="utf-8"),
            {n: (REPO / n).read_text(encoding="utf-8") for n in READMES})


def test_every_entry_of_the_release_has_its_place_in_both_readmes(examined):
    changelog, readmes = _read()
    examined(sum(len(leads(changelog, r)) for r in tables()), "CHANGELOG entries")
    assert all(len(leads(changelog, r)) == len(c) for r, c in tables().items())
    assert claim_problems(changelog, readmes) == []


def test_each_new_key_is_a_configuration_key(examined):
    examined(len(NEW_KEYS), "configuration keys")
    assert set(NEW_KEYS) <= {f.name for f in fields(Config)}


def test_sabotage_an_entry_with_no_place_is_named(examined):
    changelog, readmes = _read()
    heading = next(m.group(0) for m in _HEADING.finditer(changelog) if m.group(1) == RELEASE)
    planted = changelog.replace(f"{heading}\n\n", f"{heading}\n\n- **A new option.** It does a thing.\n", 1)
    assert planted != changelog
    examined(1, "planted CHANGELOG")
    assert "the entry 'A new option.' is in CLAIMS 0 times" in claim_problems(planted, readmes)


@pytest.mark.parametrize("lead", ["Compare on the public demo", "A run's span context",
                                  "`demo --public --build --site-links FILE`", "Upgrading from 0.4.0",
                                  "A run's incident takes", "onetrace 0.6.1 and onetrace-verify 0.6.1"])
def test_sabotage_a_readme_missing_a_section_is_named(lead, examined):
    changelog, readmes = _read()
    words = next(w for claims in tables().values() for c, _, w in claims if c == lead)
    for name in READMES:
        planted = {**readmes, name: readmes[name].replace(words, "")}
        examined(1, f"planted {name}")
        assert f"{name} does not hold {words!r} ({lead})" in claim_problems(changelog, planted)


def test_sabotage_a_readme_missing_a_key_is_named(examined):
    changelog, readmes = _read()
    planted = {**readmes, "README.md": readmes["README.md"].replace("`compare_verb_seconds`", "")}
    examined(1, "planted README.md")
    assert "README.md does not name the key 'compare_verb_seconds'" in claim_problems(changelog, planted)


def heading_problems(changelog: str, version: str) -> list[str]:
    """A released version's heading saying "(not released)", or a heading with another suffix: the
    package's own version can say it, until the release step drops it; every other heading is plain or
    gives its date, " - YYYY-MM-DD"."""
    out = []
    for m in _HEADING.finditer(changelog):
        said, suffix = m.group(1), m.group(2)
        if suffix not in ("", UNRELEASED) and not DATED.fullmatch(suffix):
            out.append(f"## [{said}] has the suffix {suffix!r}")
        elif suffix == UNRELEASED and said != version:
            out.append(f"## [{said}] is released and still says (not released)")
    return out


def test_only_the_next_release_says_not_released(examined):
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = _HEADING.findall(changelog)
    examined(len(headings), "CHANGELOG headings")
    assert VERSION == RELEASE
    assert heading_problems(changelog, VERSION) == []


@pytest.mark.parametrize("planted", ["0.5.0", "0.4.0"])
def test_sabotage_a_released_heading_still_unreleased_is_named(planted, examined):
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    examined(1, "planted heading")
    assert f"\n## [{planted}]\n" in changelog
    bad = changelog.replace(f"\n## [{planted}]\n", f"\n## [{planted}]{UNRELEASED}\n", 1)
    assert heading_problems(bad, VERSION) == [f"## [{planted}] is released and still says (not released)"]


def test_the_next_release_can_say_it_or_be_plain_after_the_release_step(examined):
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    examined(2, "the next release's heading, either way")
    plain = changelog.replace(f"## [{VERSION}]{UNRELEASED}", f"## [{VERSION}]", 1)
    assert heading_problems(changelog, VERSION) == heading_problems(plain, VERSION) == []


@pytest.mark.parametrize("suffix", [" - 3 Nov 2026", " 2026-11-03", " - 2026-11-03 (not released)"])
def test_sabotage_a_heading_with_a_date_in_another_form_is_named(suffix, examined):
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    heading = next(m.group(0) for m in _HEADING.finditer(changelog) if m.group(1) == RELEASE)
    examined(1, "planted heading")
    bad = changelog.replace(heading, f"## [{RELEASE}]{suffix}", 1)
    assert heading_problems(bad, VERSION) == [f"## [{RELEASE}] has the suffix {suffix!r}"]
