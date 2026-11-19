"""SCIM 2.0's service provider for Microsoft Entra ID's provisioning: discovery and Users, the SCIM
bearer token, and the records under `<store_root>/scim/`.

**What is served**, under `/scim/v2`: `/ServiceProviderConfig`, `/Schemas` and `/Schemas/{uri}`,
`/ResourceTypes` and `/ResourceTypes/{name}`, and `/Users` (GET with `filter` `eq` on `userName` and `externalId`,
combined by `and`, `startIndex` and `count`; POST) and `/Users/{id}` (GET, PUT, PATCH, DELETE). Requests and answers
are `application/scim+json`; an error is SCIM's error message, and its `detail` never echoes a token, a header or a
body. `/Groups` and `/Groups/{id}` are served with the same methods as Users. `/Me`, `/.search` and `/Bulk` are `501`.

**What is kept**: a User's console-assigned `id` (32 random hex), `externalId` (the person's Entra ID object id,
GUID-shaped, unique, kept lower-cased), `userName` (unique, compared case-insensitively), `displayName`, `active`
(a JSON boolean, or Entra ID's `"True"` and `"False"`), the work e-mail, and `meta`. Every other attribute is accepted
and dropped, so an answer shows only what is kept.

**The token**: 256 random bits, made on the machine with `scim token create`, printed once and kept as its
sha256 under `scim/tokens/<token id>.json` with when it was made and when it expires; its id is 128 random bits drawn
apart from it. At most two are live. Read from `Authorization: Bearer` only, compared by hash in constant time; a
token in the query string or a form body is refused and never looked up.

**A refused write never keeps access**: a PATCH is all or nothing, `op` is matched without regard to case, a
`path` the console does not keep is dropped, and inside a write that sets `active` false an `externalId` that is not
GUID-shaped or that another User holds is dropped and kept in the audit entry, not refused.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs

from onetrace_console.bounded_json import load_json_bounded
from onetrace_console.store import _atomic_write

DIRNAME = "scim"
PREFIX = "/scim/v2"
MEDIA_TYPE = "application/scim+json"
ERROR = "urn:ietf:params:scim:api:messages:2.0:Error"
LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
PATCH_OP = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
#: RFC 7643's schema URNs all begin so.
SCHEMAS = "urn:ietf:params:scim:schemas:core:2.0:"
USER = SCHEMAS + "User"
GROUP = SCHEMAS + "Group"
SPC = SCHEMAS + "ServiceProviderConfig"
RESOURCE_TYPE = SCHEMAS + "ResourceType"
SCHEMA = SCHEMAS + "Schema"

#: The defaults of the configuration's `scim` key.
DEFAULTS: dict = {
    "enabled": False,
    "tenant_id": "",
    "required_for_sign_in": True,
    "token_max_days": 180,
    "allowed_sources": [],
    "max_body_bytes": 1024 * 1024,
    "max_results": 200,
}
#: `token_max_days` may be set to at most this.
TOKEN_DAYS_CEILING = 365
TOKEN_DAYS_DEFAULT = 90
#: Live tokens at most: one can replace the other without a gap.
LIVE_TOKENS = 2
#: The admin page and the start-up line warn this many days before a token's expiry.
WARN_DAYS = 14

_ID = re.compile(r"[0-9a-f]{32}")
_GUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")
_TOKEN_ID = re.compile(r"[0-9a-f]{32}")


class ScimError(Exception):
    """An answer in SCIM's error form: its status, its `scimType` where one applies, and words that echo nothing
    the request carried."""

    def __init__(self, status: int, detail: str = "", scim_type: str | None = None):
        super().__init__(detail)
        self.status, self.detail, self.scim_type = status, detail, scim_type

    def body(self) -> dict:
        out: dict = {"schemas": [ERROR], "status": str(self.status)}
        if self.scim_type:
            out["scimType"] = self.scim_type
        if self.detail:
            out["detail"] = self.detail
        return out


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(t: datetime) -> str:
    return t.isoformat(timespec="seconds").replace("+00:00", "Z")


def _read(path: Path) -> dict | None:
    try:
        got = load_json_bounded(path.read_text(encoding="utf-8"), path.name)
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    return got if isinstance(got, dict) else None


def _write(path: Path, record: dict) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))


# ------------------------------------------------------------------ tokens


@dataclass(frozen=True)
class Token:
    token_id: str
    sha256: str
    created_at: str
    expires_at: str
    revoked: bool = False

    def live(self, now: datetime | None = None) -> bool:
        return not self.revoked and (now or _now()) < datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))


class TokenStore:
    """The SCIM tokens, `<store_root>/scim/tokens/<token id>.json`: each a sha256 and two times, never the value."""

    def __init__(self, store_root: Path) -> None:
        self.root = Path(store_root) / DIRNAME / "tokens"

    def tokens(self) -> list[Token]:
        out = []
        for p in sorted(self.root.glob("*.json")) if self.root.is_dir() else ():
            r = _read(p)
            if r is None:
                continue
            try:
                t = Token(r["token_id"], r["sha256"], r["created_at"], r["expires_at"], bool(r.get("revoked")))
                t.live()
            except (TypeError, KeyError, ValueError):
                continue
            if _TOKEN_ID.fullmatch(t.token_id) and p.stem == t.token_id:
                out.append(t)
        return out

    def live(self) -> list[Token]:
        return [t for t in self.tokens() if t.live()]

    def create(self, days: int, *, now: datetime | None = None) -> tuple[Token, str]:
        """A new token: (its record, its value, shown once). Its id is drawn apart from its value."""
        now = now or _now()
        raw = secrets.token_urlsafe(32)
        token_id = secrets.token_hex(16)
        token = Token(
            token_id=token_id,
            sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            created_at=_iso(now),
            expires_at=_iso(now + timedelta(days=days)),
        )
        _write(self.root / f"{token_id}.json", token.__dict__)
        return token, raw

    def forget(self, token_id: str) -> None:
        """Take back a token just made and never shown: its making could not be recorded (`audit`)."""
        if _TOKEN_ID.fullmatch(token_id):
            (self.root / f"{token_id}.json").unlink(missing_ok=True)

    def revoke(self, token_id: str) -> bool:
        found = next((t for t in self.tokens() if t.token_id == token_id), None)
        if found is None or found.revoked:
            return False
        _write(self.root / f"{token_id}.json", {**found.__dict__, "revoked": True})
        return True

    def find(self, raw: str) -> Token | None:
        """The live token whose hash is `raw`'s, compared in constant time against every live one; None for an
        unknown, expired or revoked one alike."""
        given = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        found = None
        for t in self.live():
            if hmac.compare_digest(t.sha256, given):
                found = t
        return found


# ------------------------------------------------------------------ users


def prepared(name: str) -> str:
    """`userName` as compared for uniqueness (RFC 7644 §7.8): NFKC, case-folded."""
    return unicodedata.normalize("NFKC", name).casefold()


def _clean(text: object, most: int = 256) -> str:
    """A directory string as kept: text, its control and direction characters taken out,
    at most `most` characters."""
    if not isinstance(text, str):
        return ""
    kept = "".join(c for c in text if unicodedata.category(c) not in ("Cc", "Cf"))
    return kept[:most]


def _active(value: object) -> bool:
    """`active` as Entra ID sends it: a JSON boolean, or the strings "True" and "False"."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    raise ScimError(400, "active is true or false", "invalidValue")


def _work_email(emails: object) -> str:
    if not isinstance(emails, list):
        return ""
    for e in emails:
        if (
            isinstance(e, dict)
            and (e.get("type") == "work" or e.get("primary") is True)
            and isinstance(e.get("value"), str)
        ):
            return _clean(e["value"])
    return ""


class Users:
    """The SCIM Users, `<store_root>/scim/users/<id>.json`, and the tombstones of deleted ones, `scim/gone/<id>.json`."""

    def __init__(self, store_root: Path) -> None:
        self.root = Path(store_root) / DIRNAME / "users"
        self.gone = Path(store_root) / DIRNAME / "gone"

    def all(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")) if self.root.is_dir() else ():
            r = _read(p)
            if r is not None and r.get("id") == p.stem and _ID.fullmatch(p.stem):
                out.append(r)
        return out

    def get(self, user_id: str) -> dict | None:
        if not _ID.fullmatch(user_id):
            return None
        r = _read(self.root / f"{user_id}.json")
        return r if r is not None and r.get("id") == user_id else None

    def by_external_id(self, external_id: str) -> list[dict]:
        key = external_id.lower()
        return [u for u in self.all() if u.get("externalId") == key]

    def tombstone(self, external_id: str) -> dict | None:
        key = external_id.lower()
        for p in sorted(self.gone.glob("*.json")) if self.gone.is_dir() else ():
            r = _read(p)
            if r is not None and r.get("externalId") == key:
                return r
        return None

    def _check_unique(self, record: dict, *, but: str | None = None) -> None:
        for u in self.all():
            if u["id"] == but:
                continue
            if prepared(u.get("userName", "")) == prepared(record["userName"]):
                raise ScimError(409, "a User with this userName is held", "uniqueness")
            if u.get("externalId") == record["externalId"]:
                raise ScimError(409, "a User with this externalId is held", "uniqueness")

    def put(self, record: dict) -> None:
        _write(self.root / f"{record['id']}.json", record)

    def delete(self, user: dict, token_id: str) -> None:
        """Remove the User and write its tombstone: its `externalId`, when, by which token."""
        _write(
            self.gone / f"{user['id']}.json",
            {"id": user["id"], "externalId": user.get("externalId", ""), "at": _iso(_now()), "token": token_id},
        )
        (self.root / f"{user['id']}.json").unlink(missing_ok=True)


def user_from(body: dict, *, user_id: str, created: str | None = None) -> dict:
    """A User record from a SCIM User resource: what is kept, checked. ScimError for a value the console refuses."""
    if not isinstance(body, dict):
        raise ScimError(400, "the body is a SCIM User", "invalidSyntax")
    name = body.get("userName")
    if not isinstance(name, str) or not name.strip():
        raise ScimError(400, "userName is required", "invalidValue")
    ext = body.get("externalId")
    if not isinstance(ext, str) or not _GUID.fullmatch(ext.lower()):
        raise ScimError(400, "externalId is required, and is the person's Entra ID object id (a GUID)", "invalidValue")
    now = _iso(_now())
    return {
        "id": user_id,
        "externalId": ext.lower(),
        "userName": _clean(name),
        "displayName": _clean(body.get("displayName", "")),
        "active": _active(body["active"]) if "active" in body else True,
        "email": _work_email(body.get("emails")),
        "created": created or now,
        "lastModified": now,
    }


def resource(user: dict, base: str) -> dict:
    """A User as SCIM answers it: only what is kept."""
    out: dict = {
        "schemas": [USER],
        "id": user["id"],
        "externalId": user.get("externalId", ""),
        "userName": user.get("userName", ""),
        "active": bool(user.get("active")),
        "meta": {
            "resourceType": "User",
            "created": user.get("created", ""),
            "lastModified": user.get("lastModified", ""),
            "location": f"{base}{PREFIX}/Users/{user['id']}",
        },
    }
    if user.get("displayName"):
        out["displayName"] = user["displayName"]
    if user.get("email"):
        out["emails"] = [{"value": user["email"], "type": "work", "primary": True}]
    return out


# ------------------------------------------------------------------ filters


_FILTER_TERM = re.compile(r'\s*([A-Za-z][A-Za-z0-9.]*)\s+(\S+)\s+"((?:[^"\\]|\\.)*)"\s*')


def parse_filter(text: str, attributes: tuple[str, ...]) -> list[tuple[str, str]]:
    """`attr eq "value"` terms joined by `and`: [(attribute, value)]. ScimError `invalidFilter` naming what
    is not served: another operator, `or`, `not`, a group of terms, an attribute it does not filter on."""
    outside = _outside_quotes(text)
    for word in ("or", "not"):
        if re.search(rf"\b{word}\b", outside, re.I):
            raise ScimError(400, f"the filter operator {word!r} is not served; eq and and are", "invalidFilter")
    if "(" in outside or "[" in outside:
        raise ScimError(400, "grouped filters are not served; eq and and are", "invalidFilter")
    terms = re.split(r"\s+and\s+", _outside_quotes_marked(text), flags=re.I)
    out = []
    for marked in terms:
        term = _unmark(marked, text)
        m = _FILTER_TERM.fullmatch(term)
        if m is None:
            raise ScimError(400, 'the filter is not attribute eq "value"', "invalidFilter")
        attr, op, value = m.group(1), m.group(2), m.group(3)
        if op.lower() != "eq":
            raise ScimError(400, f"the filter operator {op.lower()!r} is not served; eq and and are", "invalidFilter")
        if attr not in attributes:
            raise ScimError(400, f"filtering on {attr!r} is not served; on {', '.join(attributes)}", "invalidFilter")
        out.append((attr, value.replace('\\"', '"').replace("\\\\", "\\")))
    return out


def _outside_quotes(text: str) -> str:
    return re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)


def _outside_quotes_marked(text: str) -> str:
    """`text` with each quoted string replaced by a numbered mark, so `and` inside a value is not a separator."""
    i = 0

    def mark(_m) -> str:
        nonlocal i
        i += 1
        return f"\x00{i - 1}\x00"

    return re.sub(r'"(?:[^"\\]|\\.)*"', mark, text)


def _unmark(marked: str, text: str) -> str:
    quoted = re.findall(r'"(?:[^"\\]|\\.)*"', text)
    return re.sub(r"\x00(\d+)\x00", lambda m: quoted[int(m.group(1))], marked)


# ------------------------------------------------------------------ discovery


def service_provider_config(settings: dict, base: str) -> dict:
    return {
        "schemas": [SPC],
        "patch": {"supported": True},
        "bulk": {"supported": False, "maxOperations": 0, "maxPayloadSize": 0},
        "filter": {"supported": True, "maxResults": settings["max_results"]},
        "changePassword": {"supported": False},
        "sort": {"supported": False},
        "etag": {"supported": False},
        "authenticationSchemes": [
            {
                "type": "oauthbearertoken",
                "name": "OAuth Bearer Token",
                "description": "A token made on the console's machine with onetrace-console scim token create",
                "primary": True,
            }
        ],
        "meta": {"resourceType": "ServiceProviderConfig", "location": f"{base}{PREFIX}/ServiceProviderConfig"},
    }


def _attr(name: str, kind: str = "string", *, required: bool = False, mutability: str = "readWrite", **more) -> dict:
    return {
        "name": name,
        "type": kind,
        "multiValued": more.pop("multi", False),
        "required": required,
        "caseExact": more.pop("case_exact", False),
        "mutability": mutability,
        "returned": "default",
        "uniqueness": more.pop("uniqueness", "none"),
        **more,
    }


def schemas(base: str) -> list[dict]:
    """RFC 7643's User and Group schemas, cut to the attributes kept."""
    user = {
        "schemas": [SCHEMA],
        "id": USER,
        "name": "User",
        "description": "A person provisioned from Entra ID: only these attributes are kept",
        "attributes": [
            _attr("userName", required=True, uniqueness="server"),
            _attr("externalId", required=True, case_exact=False, uniqueness="server"),
            _attr("displayName"),
            _attr("active", "boolean", required=True),
            _attr(
                "emails",
                "complex",
                multi=True,
                subAttributes=[_attr("value"), _attr("type", canonicalValues=["work"]), _attr("primary", "boolean")],
            ),
        ],
        "meta": {"resourceType": "Schema", "location": f"{base}{PREFIX}/Schemas/{USER}"},
    }
    group = {
        "schemas": [SCHEMA],
        "id": GROUP,
        "name": "Group",
        "description": "An Entra ID group; a team names one by its externalId",
        "attributes": [
            _attr("displayName", required=True),
            _attr("externalId", required=True),
            _attr("members", "complex", multi=True, subAttributes=[_attr("value", mutability="immutable")]),
        ],
        "meta": {"resourceType": "Schema", "location": f"{base}{PREFIX}/Schemas/{GROUP}"},
    }
    return [user, group]


def resource_types(base: str) -> list[dict]:
    return [
        {
            "schemas": [RESOURCE_TYPE],
            "id": name,
            "name": name,
            "endpoint": f"/{name}s",
            "schema": schema,
            "meta": {"resourceType": "ResourceType", "location": f"{base}{PREFIX}/ResourceTypes/{name}"},
        }
        for name, schema in (("User", USER), ("Group", GROUP))
    ]


def list_response(resources: list[dict], start: int = 1, total: int | None = None) -> dict:
    return {
        "schemas": [LIST],
        "totalResults": len(resources) if total is None else total,
        "startIndex": start,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


# ------------------------------------------------------------------ the requests


@dataclass
class Answer:
    status: int
    body: dict | None = None
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Written:
    """A write, for the audit log's `scim.write`: the method, the attribute names changed and the new values
    of `active`; what was dropped beside a removal; whether it removed access."""

    user_id: str
    method: str
    changed: tuple[str, ...]
    active: bool | None
    dropped: tuple[str, ...] = ()
    removes_access: bool = False
    #: The User's `externalId` (its sessions are ended by it where the write removes its access), or "" for a Group.
    external_id: str = ""
    #: "User" or "Group"; for a Group, its members after the write (the console's User ids).
    kind: str = "User"
    members: tuple[str, ...] | None = None


def allowed_from(settings: dict, address: str) -> bool:
    """Whether `address` may reach `/scim/v2/*` (`scim.allowed_sources`): any, where the list is empty."""
    ranges = settings.get("allowed_sources") or []
    if not ranges:
        return True
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(ip in ipaddress.ip_network(r, strict=False) for r in ranges)


def bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


def unauthorized(given: bool) -> Answer:
    """`401`: a missing token, and one given that is unknown, expired or revoked, which adds `invalid_token`;
    the same for all three, with no detail."""
    challenge = 'Bearer realm="scim"' + (', error="invalid_token"' if given else "")
    return Answer(401, ScimError(401).body(), (("WWW-Authenticate", challenge),))


def answer(
    method: str,
    path: str,
    query: str,
    body: bytes,
    *,
    store_root: Path,
    settings: dict,
    base: str,
    token_id: str = "",
) -> tuple[Answer, Written | None]:
    """The answer to an authenticated SCIM request, and the write it made, if any."""
    try:
        return _route(method, path, query, body, store_root=store_root, settings=settings, base=base, token_id=token_id)
    except ScimError as e:
        return Answer(e.status, e.body()), None


def _json(body: bytes):
    try:
        return load_json_bounded(body.decode("utf-8"), "a SCIM body")
    except (UnicodeDecodeError, ValueError):
        raise ScimError(400, "the body is not JSON", "invalidSyntax") from None


def _route(method, path, query, body, *, store_root, settings, base, token_id="") -> tuple[Answer, Written | None]:
    rest = path[len(PREFIX) :]
    if rest in ("/ServiceProviderConfig",) and method == "GET":
        return Answer(200, service_provider_config(settings, base)), None
    if rest == "/Schemas" and method == "GET":
        found = schemas(base)
        return Answer(200, list_response(found)), None
    if rest.startswith("/Schemas/") and method == "GET":
        found = [s for s in schemas(base) if s["id"] == rest[len("/Schemas/") :]]
        if not found:
            raise ScimError(404, "no such schema")
        return Answer(200, found[0]), None
    if rest == "/ResourceTypes" and method == "GET":
        return Answer(200, list_response(resource_types(base))), None
    if rest.startswith("/ResourceTypes/") and method == "GET":
        found = [r for r in resource_types(base) if r["id"] == rest[len("/ResourceTypes/") :]]
        if not found:
            raise ScimError(404, "no such resource type")
        return Answer(200, found[0]), None
    if rest in ("/Me", "/.search", "/Bulk") or rest.startswith("/Me/") or rest.endswith("/.search"):
        raise ScimError(501, f"{rest.strip('/')} is not served by this console")
    if rest == "/Groups" or rest.startswith("/Groups/"):
        return _groups(method, rest, query, body, store_root=store_root, settings=settings, base=base)
    users = Users(store_root)
    if rest == "/Users":
        if method == "GET":
            return _list_users(users, query, settings, base), None
        if method == "POST":
            return _create_user(users, body, base)
        raise ScimError(405, "the method is not served here")
    if rest.startswith("/Users/"):
        user_id = rest[len("/Users/") :]
        if not _ID.fullmatch(user_id):
            raise ScimError(404, "no such User")
        user = users.get(user_id)
        if user is None:
            raise ScimError(404, "no such User")
        if method == "GET":
            return Answer(200, resource(user, base)), None
        if method == "PUT":
            return _replace_user(users, user, body, base)
        if method == "PATCH":
            return _patch_user(users, user, body, base)
        if method == "DELETE":
            users.delete(user, token_id)
            for g in Groups(store_root).all():
                if user_id in g.get("members", []):
                    Groups(store_root).put({**g, "members": [m for m in g["members"] if m != user_id]})
            ext = user.get("externalId", "")
            return Answer(204), Written(user_id, "DELETE", ("*",), False, removes_access=True, external_id=ext)
        raise ScimError(405, "the method is not served here")
    raise ScimError(404, "no such resource")


def _list_users(users: Users, query: str, settings: dict, base: str) -> Answer:
    q = {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}
    found = users.all()
    if "filter" in q:
        for attr, value in parse_filter(q["filter"], ("userName", "externalId")):
            if attr == "userName":
                found = [u for u in found if prepared(u.get("userName", "")) == prepared(value)]
            else:
                found = [u for u in found if u.get("externalId") == value.lower()]
    try:
        start = max(1, int(q.get("startIndex", "1")))
        count = int(q.get("count", str(settings["max_results"])))
    except ValueError:
        raise ScimError(400, "startIndex and count are whole numbers", "invalidValue") from None
    count = max(0, min(count, settings["max_results"]))
    page = found[start - 1 : start - 1 + count]
    return Answer(200, list_response([resource(u, base) for u in page], start, len(found)))


def _create_user(users: Users, body: bytes, base: str) -> tuple[Answer, Written | None]:
    record = user_from(_json(body), user_id=secrets.token_hex(16))
    users._check_unique(record)
    users.put(record)
    made = resource(record, base)
    changed = tuple(k for k in ("externalId", "userName", "displayName", "active", "emails") if k in made)
    return (
        Answer(201, made, (("Location", made["meta"]["location"]),)),
        Written(record["id"], "POST", changed, record["active"]),
    )


def _replace_user(users: Users, user: dict, body: bytes, base: str) -> tuple[Answer, Written | None]:
    got = _json(body)
    removes = isinstance(got, dict) and "active" in got and _active_or_none(got["active"]) is False
    dropped: list[str] = []
    if removes and isinstance(got, dict):
        got, dropped = _set_aside_for_removal(users, user, got)
    record = user_from(got, user_id=user["id"], created=user.get("created"))
    if not removes:
        users._check_unique(record, but=user["id"])
    changed = tuple(
        k for k in ("externalId", "userName", "displayName", "active", "email") if record.get(k) != user.get(k)
    )
    users.put(record)
    return (
        Answer(200, resource(record, base)),
        Written(
            user["id"],
            "PUT",
            changed,
            record["active"],
            tuple(dropped),
            removes and bool(user.get("active")),
            external_id=record["externalId"],
        ),
    )


def _active_or_none(value: object) -> bool | None:
    try:
        return _active(value)
    except ScimError:
        return None


def _set_aside_for_removal(users: Users, user: dict, got: dict) -> tuple[dict, list[str]]:
    """Inside a write that sets `active` false, an `externalId` that is not GUID-shaped, or that another User holds,
    is dropped: the removal applies, and the value is said in the audit entry. A `userName` the write leaves out is the
    stored user's, filled first, so every shape of a removal applies (a PUT of `{"active": false}` alone)."""
    if not isinstance(got.get("userName"), str):
        got = {**got, "userName": user.get("userName", "")}
    ext = got.get("externalId")
    if ext is None:
        return {**got, "externalId": user.get("externalId", "")}, []
    text = ext.lower() if isinstance(ext, str) else ""
    other = [u for u in users.by_external_id(text) if u["id"] != user["id"]] if text else []
    if not _GUID.fullmatch(text) or other:
        return {**got, "externalId": user.get("externalId", "")}, [f"externalId {_clean(str(ext), 64)!r}"]
    return got, []


_PATCH_PATHS = {
    "active": "active",
    "username": "userName",
    "displayname": "displayName",
    "externalid": "externalId",
    'emails[type eq "work"].value': "email",
    "emails": "emails",
}


def _patch_user(users: Users, user: dict, body: bytes, base: str) -> tuple[Answer, Written | None]:
    """RFC 7644 §3.5.2, all or nothing: every operation is applied to a copy, then the copy is kept."""
    got = _json(body)
    ops = got.get("Operations") if isinstance(got, dict) else None
    if not isinstance(ops, list) or not ops:
        raise ScimError(400, "a PATCH holds Operations", "invalidSyntax")
    staged: dict = {}
    for op in ops:
        if not isinstance(op, dict) or not isinstance(op.get("op"), str):
            raise ScimError(400, "each operation has an op", "invalidSyntax")
        verb = op["op"].lower()
        if verb not in ("add", "replace", "remove"):
            raise ScimError(400, "op is add, replace or remove", "invalidSyntax")
        path = op.get("path")
        if path is None:
            value = op.get("value")
            if not isinstance(value, dict):
                raise ScimError(400, "an operation without a path has an object for its value", "invalidSyntax")
            for k, v in value.items():
                kept = _PATCH_PATHS.get(k.lower())
                if kept is not None:
                    staged[kept] = None if verb == "remove" else v
            continue
        if not isinstance(path, str):
            raise ScimError(400, "path is text", "invalidSyntax")
        kept = _PATCH_PATHS.get(path.strip().lower())
        if kept is None:
            continue  #: a path the console does not keep is dropped, as an unkept attribute is
        staged[kept] = None if verb == "remove" else op.get("value")
    merged = {
        "userName": user.get("userName"),
        "externalId": user.get("externalId"),
        "displayName": user.get("displayName", ""),
        "active": user.get("active"),
        "emails": [{"value": user["email"], "type": "work"}] if user.get("email") else [],
    }
    for k, v in staged.items():
        if k == "email":
            merged["emails"] = [{"value": v, "type": "work"}] if isinstance(v, str) else []
        else:
            merged[k] = v if v is not None else ("" if k == "displayName" else merged.get(k))
    removes = "active" in staged and _active_or_none(staged["active"]) is False
    dropped: list[str] = []
    if removes:
        if "externalId" in staged:
            candidate, dropped = _set_aside_for_removal(users, user, {"externalId": staged["externalId"]})
            merged["externalId"] = candidate["externalId"]
        merged["active"] = False
    record = user_from(merged, user_id=user["id"], created=user.get("created"))
    if not removes:
        users._check_unique(record, but=user["id"])
    changed = tuple(
        k for k in ("externalId", "userName", "displayName", "active", "email") if record.get(k) != user.get(k)
    )
    users.put(record)
    return (
        Answer(200, resource(record, base)),
        Written(
            user["id"],
            "PATCH",
            changed,
            record["active"],
            tuple(dropped),
            removes and bool(user.get("active")),
            external_id=record["externalId"],
        ),
    )


# ------------------------------------------------------------------ the configuration, at start


def start_refusal(config, *, local: bool) -> tuple[str, str] | None:
    """SCIM's start refusals: on in local or public mode, with sign-in off, with local sign-in, each
    naming the keys. (message, fix), or None. The listener's own rule (`signin.refuse_if_insecure`) already refuses
    a non-loopback host without TLS once sign-in is on."""
    s = getattr(config, "scim", None) or {}
    if not s.get("enabled"):
        return None
    if config.public:
        return (
            "scim.enabled is true and public is true. A public console serves its demo to anyone, with no accounts.",
            "remove scim, or remove public to run a team's console.",
        )
    if local:
        return (
            "scim.enabled is true and the console runs in local mode, with no sign-in.",
            "name a configuration file with sign_in.enabled true and sign_in.method oidc.",
        )
    if not config.sign_in.get("enabled"):
        return (
            "scim.enabled is true and sign_in.enabled is false. With sign-in off every route is open, so SCIM's "
            "people would gate nothing.",
            "set sign_in.enabled true and sign_in.method oidc, or turn scim off.",
        )
    if config.sign_in.get("method") != "oidc":
        return (
            "scim.enabled is true and sign_in.method is local. SCIM's Users are joined to sign-in through Entra ID; "
            "a local account has no object id to join.",
            "set sign_in.method to oidc, or turn scim off.",
        )
    tenant = s.get("tenant_id") or ""
    signed = (config.sign_in.get("oidc") or {}).get("tenant_id", "")
    if tenant and tenant.lower() != str(signed).lower():
        return (
            "scim.tenant_id names another tenant than sign_in.oidc.tenant_id. One console serves one Entra ID tenant.",
            "set scim.tenant_id to sign_in.oidc.tenant_id, or leave it out.",
        )
    return None


# ------------------------------------------------------------------ groups


class Groups:
    """The SCIM Groups, `<store_root>/scim/groups/<id>.json`: an id, the Entra ID group's object id as `externalId`,
    `displayName`, and `members`, the console's User ids."""

    def __init__(self, store_root: Path) -> None:
        self.root = Path(store_root) / DIRNAME / "groups"

    def all(self) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json")) if self.root.is_dir() else ():
            r = _read(p)
            if r is not None and r.get("id") == p.stem and _ID.fullmatch(p.stem):
                out.append(r)
        return out

    def get(self, group_id: str) -> dict | None:
        if not _ID.fullmatch(group_id):
            return None
        r = _read(self.root / f"{group_id}.json")
        return r if r is not None and r.get("id") == group_id else None

    def put(self, record: dict) -> None:
        _write(self.root / f"{record['id']}.json", record)

    def delete(self, group_id: str) -> None:
        (self.root / f"{group_id}.json").unlink(missing_ok=True)


def group_resource(group: dict, base: str, *, members: bool = True) -> dict:
    out: dict = {
        "schemas": [GROUP],
        "id": group["id"],
        "externalId": group.get("externalId", ""),
        "displayName": group.get("displayName", ""),
        "meta": {
            "resourceType": "Group",
            "created": group.get("created", ""),
            "lastModified": group.get("lastModified", ""),
            "location": f"{base}{PREFIX}/Groups/{group['id']}",
        },
    }
    if members:
        out["members"] = [{"value": m, "$ref": f"{base}{PREFIX}/Users/{m}"} for m in group.get("members", [])]
    return out


def _member_ids(value: object) -> list[str]:
    """The `value`s of a members list as Entra ID sends it: [{"value": id}, ...]; anything else is none."""
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, list):
        return []
    return [v["value"] for v in value if isinstance(v, dict) and isinstance(v.get("value"), str)]


def _group_from(body: object, *, group_id: str, created: str | None, users: Users) -> tuple[dict, list[str]]:
    """A Group record from a SCIM Group resource, and the members dropped as naming no User."""
    if not isinstance(body, dict):
        raise ScimError(400, "the body is a SCIM Group", "invalidSyntax")
    name = body.get("displayName")
    if not isinstance(name, str) or not name.strip():
        raise ScimError(400, "displayName is required", "invalidValue")
    ext = body.get("externalId")
    if not isinstance(ext, str) or not ext.strip():
        raise ScimError(400, "externalId is required, and is the Entra ID group's object id", "invalidValue")
    held = {u["id"] for u in users.all()}
    asked = _member_ids(body.get("members", []))
    now = _iso(_now())
    record = {
        "id": group_id,
        "externalId": ext.strip().lower(),
        "displayName": _clean(name),
        "members": sorted({m for m in asked if m in held}),
        "created": created or now,
        "lastModified": now,
    }
    return record, sorted({m for m in asked if m not in held})


def _groups(method, rest, query, body, *, store_root, settings, base) -> tuple[Answer, Written | None]:
    groups, users = Groups(store_root), Users(store_root)
    q = {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}
    without_members = "members" in [a.strip() for a in q.get("excludedAttributes", "").split(",")]
    if rest == "/Groups":
        if method == "GET":
            found = groups.all()
            if "filter" in q:
                for attr, value in parse_filter(q["filter"], ("displayName", "externalId")):
                    if attr == "displayName":
                        found = [g for g in found if prepared(g.get("displayName", "")) == prepared(value)]
                    else:
                        found = [g for g in found if g.get("externalId") == value.lower()]
            try:
                start = max(1, int(q.get("startIndex", "1")))
                count = max(0, min(int(q.get("count", str(settings["max_results"]))), settings["max_results"]))
            except ValueError:
                raise ScimError(400, "startIndex and count are whole numbers", "invalidValue") from None
            page = found[start - 1 : start - 1 + count]
            listed = [group_resource(g, base, members=not without_members) for g in page]
            return Answer(200, list_response(listed, start, len(found))), None
        if method == "POST":
            record, dropped = _group_from(_json(body), group_id=secrets.token_hex(16), created=None, users=users)
            if any(g.get("externalId") == record["externalId"] for g in groups.all()):
                raise ScimError(409, "a Group with this externalId is held", "uniqueness")
            groups.put(record)
            made = group_resource(record, base)
            return (
                Answer(201, made, (("Location", made["meta"]["location"]),)),
                Written(
                    record["id"],
                    "POST",
                    ("externalId", "displayName", "members"),
                    None,
                    tuple(f"member {m!r}" for m in dropped),
                    kind="Group",
                    members=tuple(record["members"]),
                ),
            )
        raise ScimError(405, "the method is not served here")
    group_id = rest[len("/Groups/") :]
    group = groups.get(group_id) if _ID.fullmatch(group_id) else None
    if group is None:
        raise ScimError(404, "no such Group")
    if method == "GET":
        return Answer(200, group_resource(group, base, members=not without_members)), None
    if method == "DELETE":
        groups.delete(group_id)
        return Answer(204), Written(
            group_id, "DELETE", ("*",), None, removes_access=bool(group.get("members")), kind="Group", members=()
        )
    if method == "PUT":
        record, dropped = _group_from(_json(body), group_id=group_id, created=group.get("created"), users=users)
        removed = set(group.get("members", [])) - set(record["members"])
        groups.put(record)
        changed = tuple(k for k in ("externalId", "displayName", "members") if record.get(k) != group.get(k))
        return (
            Answer(200, group_resource(record, base)),
            Written(
                group_id,
                "PUT",
                changed,
                None,
                tuple(f"member {m!r}" for m in dropped),
                bool(removed),
                kind="Group",
                members=tuple(record["members"]),
            ),
        )
    if method == "PATCH":
        return _patch_group(groups, users, group, body, base)
    raise ScimError(405, "the method is not served here")


_MEMBER_FILTER = re.compile(r'members\[\s*value\s+eq\s+"([^"]*)"\s*\]', re.I)


def _patch_group(groups: Groups, users: Users, group: dict, body: bytes, base: str) -> tuple[Answer, Written | None]:
    """Members add and remove, and displayName and externalId replaced (RFC 7644 §3.5.2.1 to RFC 7644 §3.5.2.3), all or nothing.
    A member naming no User is dropped from an add and recorded, and is a removal of nothing in a remove."""
    got = _json(body)
    ops = got.get("Operations") if isinstance(got, dict) else None
    if not isinstance(ops, list) or not ops:
        raise ScimError(400, "a PATCH holds Operations", "invalidSyntax")
    held = {u["id"] for u in users.all()}
    members = list(group.get("members", []))
    record = dict(group)
    dropped: list[str] = []
    for op in ops:
        if not isinstance(op, dict) or not isinstance(op.get("op"), str):
            raise ScimError(400, "each operation has an op", "invalidSyntax")
        verb = op["op"].lower()
        if verb not in ("add", "replace", "remove"):
            raise ScimError(400, "op is add, replace or remove", "invalidSyntax")
        path = op.get("path")
        path = path.strip() if isinstance(path, str) else None
        if path is not None and (m := _MEMBER_FILTER.fullmatch(path)) is not None:
            if verb == "remove":
                members = [x for x in members if x != m.group(1)]
            continue
        if path is not None and path.lower() == "members":
            ids = _member_ids(op.get("value"))
            if verb == "remove":
                members = [x for x in members if x not in ids] if ids else []
            else:
                if verb == "replace":
                    members = []
                for i in ids:
                    if i in held and i not in members:
                        members.append(i)
                    elif i not in held:
                        dropped.append(f"member {i[:64]!r}")
            continue
        if path is None and isinstance(op.get("value"), dict):
            items = op["value"].items()
        elif path is not None:
            items = [(path, op.get("value"))]
        else:
            raise ScimError(400, "an operation without a path has an object for its value", "invalidSyntax")
        for k, v in items:
            key = {"displayname": "displayName", "externalid": "externalId"}.get(k.lower())
            if key is None:
                continue
            if verb == "remove" or not isinstance(v, str) or not v.strip():
                raise ScimError(400, f"{key} is required, and text", "invalidValue")
            record[key] = _clean(v) if key == "displayName" else v.strip().lower()
    if record["externalId"] != group.get("externalId") and any(
        g.get("externalId") == record["externalId"] for g in groups.all() if g["id"] != group["id"]
    ):
        raise ScimError(409, "a Group with this externalId is held", "uniqueness")
    record["members"] = sorted(set(members))
    record["lastModified"] = _iso(_now())
    removed = set(group.get("members", [])) - set(record["members"])
    changed = tuple(k for k in ("externalId", "displayName", "members") if record.get(k) != group.get(k))
    groups.put(record)
    return (
        Answer(200, group_resource(record, base)),
        Written(
            group["id"],
            "PATCH",
            changed,
            None,
            tuple(dropped),
            bool(removed),
            kind="Group",
            members=tuple(record["members"]),
        ),
    )


# ------------------------------------------------------------------ the directory, as a request reads it


ENFORCEMENT_NAME = "enforcement.json"


def enforcement(store_root: Path) -> tuple[bool, str | None]:
    """SCIM's enforcement of sign-in: (on, since when it is off). On unless `scim enforcement off` wrote off."""
    r = _read(Path(store_root) / DIRNAME / ENFORCEMENT_NAME)
    if r is None or r.get("on") is not False:
        return True, None
    return False, str(r.get("since", ""))


def set_enforcement(store_root: Path, on: bool) -> None:
    _write(Path(store_root) / DIRNAME / ENFORCEMENT_NAME, {"on": on, "since": _iso(_now())})


class Directory:
    """SCIM's records as a running console reads them on each request: read again only when a folder
    under `scim/` or the enforcement record has changed, so the per-request check is a lookup in memory."""

    def __init__(self, store_root: Path) -> None:
        import threading

        self.store_root = Path(store_root)
        self._lock = threading.Lock()
        self._key: tuple | None = None
        self._by_ext: dict[str, list[dict]] = {}
        self._gone: set[str] = set()
        self._groups: list[dict] = []
        self._enforcement: tuple[bool, str | None] = (True, None)

    def _stamp(self) -> tuple:
        out: list[tuple[int, int] | None] = []
        for name in ("users", "groups", "gone", ENFORCEMENT_NAME):
            p = self.store_root / DIRNAME / name
            try:
                st = p.stat()
                out.append((st.st_mtime_ns, st.st_size))
            except OSError:
                out.append(None)
        return tuple(out)

    def _fresh(self) -> None:
        stamp = self._stamp()
        if stamp == self._key:
            return
        users = Users(self.store_root)
        by_ext: dict[str, list[dict]] = {}
        for u in users.all():
            by_ext.setdefault(u.get("externalId", ""), []).append(u)
        gone = set()
        for p in sorted(users.gone.glob("*.json")) if users.gone.is_dir() else ():
            g = _read(p)
            if g is not None and isinstance(g.get("externalId"), str):
                gone.add(g["externalId"])
        self._by_ext, self._gone, self._groups = by_ext, gone, Groups(self.store_root).all()
        self._enforcement = enforcement(self.store_root)
        self._key = stamp

    def enforcement(self) -> tuple[bool, str | None]:
        with self._lock:
            self._fresh()
            return self._enforcement

    def refusal(self, principal: str, *, tenant: str, required: bool) -> str | None:
        """Why the join refuses `principal` (`<tenant id>/<object id>`), or None where it admits it:
        with `required`, exactly one active User whose `externalId` is the object id, in the configured tenant;
        without, an object id a User or a tombstone holds must be an active User's, and one SCIM never named passes."""
        tid, _, oid = principal.lower().partition("/")
        with self._lock:
            self._fresh()
            if tenant and tid != tenant.lower():
                return "tenant mismatch"
            found = self._by_ext.get(oid, [])
            if len(found) == 1 and found[0].get("active"):
                return None
            if found:
                return "inactive"
            if oid in self._gone:
                return "deleted"
            return "not provisioned" if required else None

    def teams_of(self, principal: str, teams: dict) -> tuple[str, ...]:
        """The configured teams whose `scim_group` names a Group that holds this person's User."""
        _tid, _, oid = principal.lower().partition("/")
        with self._lock:
            self._fresh()
            mine = {u["id"] for u in self._by_ext.get(oid, []) if u.get("active")}
            groups = {g.get("externalId"): set(g.get("members", [])) for g in self._groups}
        return tuple(
            t
            for t, entry in teams.items()
            if (entry.get("scim_group") or "").lower() in groups
            and groups[(entry.get("scim_group") or "").lower()] & mine
        )


def unmapped_groups(store_root: Path, teams: dict) -> list[dict]:
    """The Groups no team's `scim_group` names: kept, members tracked, granting nothing."""
    named = {(e.get("scim_group") or "").lower() for e in teams.values()}
    return [g for g in Groups(store_root).all() if g.get("externalId") not in named]


def unprovisioned_mappings(store_root: Path, teams: dict) -> list[str]:
    """The teams whose `scim_group` names no provisioned Group: granting nothing, never stopping a start."""
    held = {g.get("externalId") for g in Groups(store_root).all()}
    return [t for t, e in teams.items() if e.get("scim_group") and e["scim_group"].lower() not in held]


def activate(store_root: Path, external_id: str) -> tuple[dict, bool]:
    """`scim user activate <externalId>`: the User set active, as a PATCH from the directory would; (it, whether
    it was inactive). ScimError 404 where no User has that externalId."""
    users = Users(store_root)
    found = users.by_external_id(external_id)
    if len(found) != 1:
        raise ScimError(404, "no User has that externalId" if not found else "more than one User has that externalId")
    user = found[0]
    was_inactive = not user.get("active")
    users.put({**user, "active": True, "lastModified": _iso(_now())})
    return user, was_inactive
