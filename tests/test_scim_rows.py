"""SCIM's routes in the role table: each route and method its own row,
discovery included, role `scim` and a team rule; matched before the pages lookup, so no SCIM path resolves to a file
under `pages/`; and a SCIM request with no row answers in SCIM's error form after the token, never a page.
"""

from __future__ import annotations

import pytest

from onetrace_console import scim
from tests.test_scim_users import call, scim_console  # noqa: F401 - a fixture, requested by name

ROUTES = [
    ("GET", "/scim/v2/ServiceProviderConfig"),
    ("GET", "/scim/v2/Schemas"),
    ("GET", "/scim/v2/Schemas/" + scim.USER),
    ("GET", "/scim/v2/ResourceTypes"),
    ("GET", "/scim/v2/ResourceTypes/User"),
    ("GET", "/scim/v2/Users"),
    ("POST", "/scim/v2/Users"),
    ("GET", "/scim/v2/Users/" + "a" * 32),
    ("PUT", "/scim/v2/Users/" + "a" * 32),
    ("PATCH", "/scim/v2/Users/" + "a" * 32),
    ("DELETE", "/scim/v2/Users/" + "a" * 32),
    ("GET", "/scim/v2/Groups"),
    ("POST", "/scim/v2/Groups"),
    ("GET", "/scim/v2/Groups/" + "a" * 32),
    ("PUT", "/scim/v2/Groups/" + "a" * 32),
    ("PATCH", "/scim/v2/Groups/" + "a" * 32),
    ("DELETE", "/scim/v2/Groups/" + "a" * 32),
]


@pytest.mark.parametrize("method, path", ROUTES)
def test_every_scim_route_and_method_has_its_own_row_with_role_scim_and_a_team_rule(method, path, examined):
    from onetrace_console import roles

    for oidc in (False, True):
        assert roles.required_role(method, path, oidc=oidc) == roles.SCIM
        assert roles.team_rule(method, path, oidc=oidc) == roles.DRAWS_NOTHING
    examined(2, f"{method} {path[:40]}, in both sets of rules")


@pytest.mark.parametrize(
    "method, path",
    [
        ("PUT", "/scim/v2/Users"),
        ("DELETE", "/scim/v2/Schemas"),
        ("POST", "/scim/v2/ServiceProviderConfig"),
        ("GET", "/scim/v2/Nowhere"),
    ],
)
def test_a_scim_request_with_no_row_has_none_and_answers_in_scim_s_error_form(scim_console, method, path, examined):
    from onetrace_console import roles

    base, _root, token = scim_console
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role(method, path)
    status, body, headers = call(base, method, path, token=token, body={} if method in ("PUT", "POST") else None)
    assert status in (404, 405) and headers["content-type"].startswith("application/scim+json"), (status, body)
    assert body["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]
    examined(1, f"{method} {path}")


def test_no_scim_path_resolves_to_a_file_under_pages(scim_console, examined):
    base, root, token = scim_console
    planted = root / "pages" / "scim" / "v2"
    planted.mkdir(parents=True)
    (planted / "Users").write_text("a page planted where SCIM's route is", encoding="utf-8")
    (planted / "index.html").write_text("planted", encoding="utf-8")
    for path in ("/scim/v2/Users", "/scim/v2/index.html", "/scim/v2/"):
        status, body, _h = call(base, "GET", path, token=token)
        assert b"planted" not in (body if isinstance(body, bytes) else str(body).encode()), path
    examined(3, "SCIM paths over planted pages")
