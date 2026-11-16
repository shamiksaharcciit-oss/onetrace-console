"""Sign-in through Entra ID: who someone is, and which role they have, from a checked ID token.

- **The account** is keyed by the tenant id and the object id (`tid` and `oid`), `<tid>/<oid>`: never the
  email or `preferred_username`, which can change. The key holds a `/`, so it can never be a local
  account's name (`accounts._USERNAME_RE`). The name (`name`, else `preferred_username`) is for display
  only.
- **The role** comes from the `roles` claim alone, the app roles assigned in Entra: `onetrace.viewer`,
  `onetrace.investigator` and `onetrace.admin`. Where more than one is assigned, the highest takes
  effect. No role means no sign-in (`NoRole`). Roles are read at each sign-in.
- **The session** lasts until the ID token expires or `session_max_hours`, whichever comes first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from onetrace_console import roles

#: The app roles, as the registration's manifest names them, and the console's role for each.
APP_ROLES = {
    "onetrace.viewer": roles.VIEWER,
    "onetrace.investigator": roles.INVESTIGATOR,
    "onetrace.admin": roles.ADMIN,
}
_RANK = {roles.VIEWER: 1, roles.INVESTIGATOR: 2, roles.ADMIN: 3}
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")

NO_ROLE_WORDS = "Your organisation hasn't given you a role in onetrace. Ask your administrator."


class NoRole(Exception):
    """Signed in at Entra, with no onetrace role assigned: no sign-in here."""

    def __init__(self) -> None:
        super().__init__(NO_ROLE_WORDS)


@dataclass(frozen=True)
class Identity:
    key: str
    display_name: str
    role: str
    #: time.time() at which the session ends.
    expires_at: float


def role_of(claims: dict) -> str:
    """The highest app role in the `roles` claim; `NoRole` where none of the three is there."""
    assigned = claims.get("roles")
    if not isinstance(assigned, list):
        raise NoRole()
    found = [APP_ROLES[r] for r in assigned if isinstance(r, str) and r in APP_ROLES]
    if not found:
        raise NoRole()
    return max(found, key=_RANK.__getitem__)


def identity(claims: dict, *, session_max_hours: int, now: float) -> Identity:
    """Who signed in, from claims `oidc_token.check_id_token` has already checked."""
    from onetrace_console.oidc_token import TokenRefused

    tid, oid = claims.get("tid"), claims.get("oid")
    if not (isinstance(tid, str) and _GUID.match(tid) and isinstance(oid, str) and _GUID.match(oid)):
        raise TokenRefused("the ID token's tenant id or object id is not a GUID")
    role = role_of(claims)
    shown = claims.get("name") or claims.get("preferred_username") or ""
    expires_at = min(float(claims["exp"]), now + session_max_hours * 3600)
    return Identity(
        key=f"{tid.lower()}/{oid.lower()}",
        display_name=shown if isinstance(shown, str) else "",
        role=role,
        expires_at=expires_at,
    )
