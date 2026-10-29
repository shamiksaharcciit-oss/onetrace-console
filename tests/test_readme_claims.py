"""Every feature, extra and option the CHANGELOG names for this release has its place in the README.

Each entry of the release's CHANGELOG section (its bold lead) is in `CLAIMS` once, with its kind and
the words in the README that cover it. Every feature, extra and option has words; an upgrade note, a
fix or the demo's own data has words where the README states it. Both readmes (`README.md` and
`PYPI_DESCRIPTION.md`, generated from it) must hold every entry's words, and name each configuration
key the release adds.
Each rule has its own sabotage below.
"""
from __future__ import annotations

import re
from dataclasses import fields
from pathlib import Path

import pytest

from onetrace_console.config import Config

REPO = Path(__file__).resolve().parent.parent
RELEASE = "0.5.0"
READMES = ["README.md", "PYPI_DESCRIPTION.md"]
#: Kinds whose README words are held; the others are listed and need none.
HELD = {"feature", "extra", "option"}

#: (the entry's lead, as it starts, its kind, the README words that cover it).
CLAIMS = [
    ("Upgrading from 0.4.0", "upgrade note", "## Upgrading from 0.4"),
    ("onetrace 0.6.0 and onetrace-verify 0.6.0", "pins", "`onetrace` 0.6.0 and `onetrace-verify` 0.6.0"),
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
#: The configuration keys this release adds, each named in the README.
NEW_KEYS = ["compare_cache", "compare_client_header", "compare_per_minute", "compare_running", "compare_queue",
            "compare_wait_seconds", "compare_verb_seconds", "tracing"]


def leads(changelog: str) -> list[str]:
    """The bold leads of the release's CHANGELOG entries, in order."""
    start = changelog.index(f"## [{RELEASE}]")
    end = changelog.find("\n## [", start + 1)
    section = changelog[start:end if end != -1 else None]
    return re.findall(r"^- \*\*(.+?)\*\*", section, re.MULTILINE)


def claim_problems(changelog: str, readmes: dict[str, str]) -> list[str]:
    """Where an entry has no place in `CLAIMS`, or a held one's words are missing from a readme."""
    out = [f"CLAIMS gives the {kind} {lead!r} no README words" for lead, kind, words in CLAIMS
           if kind in HELD and words is None]
    found = leads(changelog)
    for lead in found:
        matched = [c for c in CLAIMS if lead.startswith(c[0])]
        if len(matched) != 1:
            out.append(f"the entry {lead!r} is in CLAIMS {len(matched)} times")
    out += [f"CLAIMS names {c[0]!r}, which no entry starts with" for c in CLAIMS
            if not any(lead.startswith(c[0]) for lead in found)]
    for name, text in readmes.items():
        out += [f"{name} does not hold {words!r} ({lead})" for lead, kind, words in CLAIMS
                if words is not None and words not in text]
        out += [f"{name} does not name the key {key!r}" for key in NEW_KEYS if f"`{key}`" not in text
                and f'"{key}"' not in text]
    return out


def _read() -> tuple[str, dict[str, str]]:
    return ((REPO / "CHANGELOG.md").read_text(encoding="utf-8"),
            {n: (REPO / n).read_text(encoding="utf-8") for n in READMES})


def test_every_entry_of_the_release_has_its_place_in_both_readmes(examined):
    changelog, readmes = _read()
    examined(len(leads(changelog)), "CHANGELOG entries")
    assert len(leads(changelog)) == len(CLAIMS)
    assert claim_problems(changelog, readmes) == []


def test_each_new_key_is_a_configuration_key(examined):
    examined(len(NEW_KEYS), "configuration keys")
    assert set(NEW_KEYS) <= {f.name for f in fields(Config)}


def test_sabotage_an_entry_with_no_place_is_named(examined):
    changelog, readmes = _read()
    planted = changelog.replace(f"## [{RELEASE}] (not released)\n\n",
                                f"## [{RELEASE}] (not released)\n\n- **A new option.** It does a thing.\n", 1)
    assert planted != changelog
    examined(1, "planted CHANGELOG")
    assert "the entry 'A new option.' is in CLAIMS 0 times" in claim_problems(planted, readmes)


@pytest.mark.parametrize("lead", ["Compare on the public demo", "A run's span context",
                                  "`demo --public --build --site-links FILE`", "Upgrading from 0.4.0",
                                  "A run's incident takes"])
def test_sabotage_a_readme_missing_a_section_is_named(lead, examined):
    changelog, readmes = _read()
    words = next(w for c, _, w in CLAIMS if c == lead)
    for name in READMES:
        planted = {**readmes, name: readmes[name].replace(words, "")}
        examined(1, f"planted {name}")
        assert f"{name} does not hold {words!r} ({lead})" in claim_problems(changelog, planted)


def test_sabotage_a_readme_missing_a_key_is_named(examined):
    changelog, readmes = _read()
    planted = {**readmes, "README.md": readmes["README.md"].replace("`compare_verb_seconds`", "")}
    examined(1, "planted README.md")
    assert "README.md does not name the key 'compare_verb_seconds'" in claim_problems(changelog, planted)
