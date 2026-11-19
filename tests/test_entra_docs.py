"""OPERATOR_README's section on sign-in through Microsoft Entra ID: the app registration (one tenant, the
redirect URI, the three app roles, assigning groups, a certificate credential), the configuration keys,
what each role may do, and what the console does not claim. Held to the code: every app role and every
`sign_in.oidc` key the console reads is named."""

from __future__ import annotations

from pathlib import Path

import pytest

from onetrace_console import config, oidc_identity

REPO = Path(__file__).resolve().parent.parent
README = REPO / "OPERATOR_README.md"


def _section() -> str:
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("\n## Sign-in through Microsoft Entra ID\n")
    return " ".join(text[start : text.index("\n## ", start + 1)].split())


def test_the_section_is_there(examined):
    examined(1, "the heading")
    assert _section()


def test_it_names_every_app_role_and_every_key_the_console_reads(examined):
    section = _section()
    keys = sorted(config._OIDC_SCHEMA)
    examined(len(oidc_identity.APP_ROLES) + len(keys), "app roles and sign_in.oidc keys")
    for value in oidc_identity.APP_ROLES:
        assert f'"value": "{value}"' in section, value
    for key in keys:
        assert key in section, key


@pytest.mark.parametrize(
    "words",
    [
        "Accounts in this organizational directory only",
        "/signin/oidc/callback",
        "**Assigning groups to roles.**",
        "**A certificate credential** (preferred)",
        "private_key_jwt",
        "Your organisation hasn't given you a role in onetrace. Ask your administrator.",
        "**The console trusts Entra for who someone is.**",
        "**A role removed in Entra takes effect at the next sign-in**",
        "within `session_max_hours`",
        "**Entra's audit log is the record of sign-ins.**",
        "**Without `teams`, every role reads every run.**",
        "Only `login.microsoftonline.com`",
    ],
)
def test_it_says(words, examined):
    examined(1, words)
    assert words in _section()


def test_the_no_role_words_are_the_console_s_own(examined):
    examined(1, "oidc_identity.NO_ROLE_WORDS in the section")
    assert oidc_identity.NO_ROLE_WORDS in _section()


SESSION_END = (
    "A session ends at the ID token's expiry, `session_max_hours` or 30 minutes idle "
    "(`sign_in.session_idle_timeout_seconds`), whichever comes first"
)


def test_it_says_when_a_session_ends(examined):
    examined(1, "the session's three ends in one sentence")
    assert SESSION_END in _section()


def test_an_entra_session_ends_when_idle_too(examined):
    """The idle rule holds for a session from Entra ID, the stricter of the three."""
    from onetrace_console.sessions import SessionStore

    examined(2, "alive 1799 s idle, gone at 1801 s, its token and bound far off")
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    s = store.create("t/o", now=0.0, role="viewer", display_name="Ada", expires_at=store.wall() + 8 * 3600)
    assert store.get(s.session_id, now=1799.0) is not None
    assert store.get(s.session_id, now=1799.0 + 1801.0) is None
