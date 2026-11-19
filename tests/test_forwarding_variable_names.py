"""A forwarding destination may read its key from a variable whose name starts with `ONETRACE_FORWARD_`, or from the
keychain: no other variable of the console's environment.

A destination's key could name any variable, and its endpoint any https host, so an admin could send, for example, the
variable holding the sign-in's client secret to a host of their own. Forwarding needs only the keys made for it: a
variable not named for it is refused when it is set, and is not read when a destination is sent; the setup page says
so.
"""

from __future__ import annotations

import html

import pytest

from onetrace_console import forwarding as F
from tests.test_forwarding_setup import P, _get, audited  # noqa: F401 - the fixture, requested by name

RAW = {
    "id": "0123456789abcdef",
    "name": "to-langsmith",
    "endpoint": "https://a.example",
    "headers": [{"name": "x-api-key", "key_env": ""}],
}


def _with(env: str) -> dict:
    return {**RAW, "headers": [{"name": "x-api-key", "key_env": env}]}


@pytest.mark.parametrize(
    "env", ["LANGSMITH_API_KEY", "ONETRACE_CONSOLE_CLIENT_SECRET", "ONETRACE_FORWARD", "onetrace_forward_x"]
)
def test_a_variable_not_named_for_forwarding_is_refused_on_its_field(env, examined):
    examined(1, "variable name")
    with pytest.raises(F.Refused) as refused:
        F.destination(_with(env))
    assert refused.value.field == "key_env" and "ONETRACE_FORWARD_" in str(refused.value)


def test_a_variable_named_for_forwarding_and_the_keychain_are_kept(examined):
    examined(2, "headers")
    assert F.destination(_with("ONETRACE_FORWARD_LANGSMITH")).headers[0].key_env == "ONETRACE_FORWARD_LANGSMITH"
    keyed = F.destination({**RAW, "headers": [{"name": "x-api-key", "key_source": "keyring"}]})
    assert keyed.headers[0].keyring


def test_a_stored_header_naming_another_variable_is_not_read(monkeypatch, examined):
    monkeypatch.setenv("SOME_OTHER_SECRET", "PLANTED-other-secret")
    dest = F.Destination(
        "d1", "to-langsmith", "https://a.example", headers=(F.Header("x-api-key", "SOME_OTHER_SECRET"),)
    )
    examined(1, "header")
    with pytest.raises(F.KeyMissing) as refused:
        F.value_of(dest, dest.headers[0])
    assert "SOME_OTHER_SECRET" in str(refused.value) and "PLANTED" not in str(refused.value)


def test_the_setup_page_says_which_variables_it_reads(audited, examined):  # noqa: F811
    base, _root, _log = audited
    status, page = _get(base + P.PATH)
    examined(1, "setup page")
    assert status == 200 and html.escape(P.VARIABLES_NAMED) in page
