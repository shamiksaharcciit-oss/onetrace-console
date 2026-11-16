"""The operator guide lists the routes that need no principal as the role table holds them.

Its sentence names each route the role table answers with no principal, with local sign-in and with Entra ID, and the
static files served before any role is asked for: the same sources `test_served_before_roles` reads, so the guide
cannot fall behind the table.
"""

from __future__ import annotations

import re
from pathlib import Path

from onetrace_console import roles

GUIDE = Path(__file__).resolve().parent.parent / "OPERATOR_README.md"
LEAD = "**The routes that need no principal:**"


def test_the_guide_names_every_route_that_needs_no_principal_and_no_other(examined):
    text = GUIDE.read_text(encoding="utf-8")
    assert text.count(LEAD) == 1
    sentence = text[text.index(LEAD) :].split("\n\n", 1)[0]
    named = set(re.findall(r"`((?:GET|POST) /[^`]*)`", sentence))
    table = {f"{m} {p}" for m, p in roles._UNAUTHENTICATED_EXACT | roles._OIDC_UNAUTHENTICATED_EXACT}
    examined(len(table), "routes that need no principal")
    assert named == table, (sorted(named - table), sorted(table - named))
    assert "`/static/`" in sentence and "/static/" in roles.SERVED_BEFORE_ROLES
