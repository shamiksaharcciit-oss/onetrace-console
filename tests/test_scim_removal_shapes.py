"""Every SCIM write that sets `active` false removes the person, whatever else it carries.

A removal sent as PUT with no user name (`{"active": false}`, alone or with an `externalId` that is not an object id)
was refused with 400, and the person stayed active: the user name was filled from the stored user only after the
early returns for the `externalId`. It is now filled first, so the rule the removal states holds for every shape. Read
on the suite's SCIM console, with the four shapes of a removal.
"""

from __future__ import annotations

from onetrace_console import scim
from tests.test_scim_users import _user, call, scim_console  # noqa: F401 - the fixture, requested by name

SHAPES = {
    "PUT active false alone": ("PUT", lambda u: {"schemas": [scim.USER], "active": False}),
    "PUT active false, a bad externalId": (
        "PUT",
        lambda u: {"schemas": [scim.USER], "active": False, "externalId": "bad"},
    ),
    "PUT the whole user, active false": ("PUT", lambda u: {**u, "active": False}),
    "PATCH active false": (
        "PATCH",
        lambda u: {
            "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
    ),
}


def test_every_shape_of_a_removal_removes_the_person(scim_console, examined):  # noqa: F811
    base, _root, token = scim_console
    got = {}
    for n, (label, (method, body)) in enumerate(SHAPES.items(), start=1):
        user = _user(200 + n)
        status, made, _ = call(base, "POST", "/scim/v2/Users", token=token, body=user)
        assert status == 201, (label, status)
        wrote, _answer, _ = call(base, method, f"/scim/v2/Users/{made['id']}", token=token, body=body(user))
        _status, now, _ = call(base, "GET", f"/scim/v2/Users/{made['id']}", token=token)
        got[label] = (wrote, now.get("active"))
    examined(len(got), "removals")
    assert got == {label: (200, False) for label in SHAPES}, got
