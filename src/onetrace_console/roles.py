"""Role enforcement, from one place (design note §3, §1 item 8).

This is the single dispatch every request goes through: a role name, or `None` for
no principal required, or a refusal for a route this table has never heard of --
never a silent default to "open". `docs/design/signin-and-roles.md` §3's own route
table is the source of truth this module encodes; a route added to `serve.py`
later without a matching entry here raises `NoRouteTableEntry`, which the caller
turns into a refusal rather than an unauthenticated pass-through.
"""
from __future__ import annotations

import re

VIEWER = "viewer"
INGESTER = "ingester"
ADMIN = "admin"

#: (method, exact path) pairs that need no principal at all -- §1 item 3's own
#: two exceptions (health, sign-in) plus sign-out, which is either a no-op (no
#: session to invalidate) or itself invalidates the one credential a principal
#: check would otherwise have relied on.
_UNAUTHENTICATED_EXACT = frozenset({
    ("GET", "/health"),
    ("GET", "/signin"),
    ("POST", "/signin"),
    ("POST", "/signout"),
})

#: Every GET page this console renders is `viewer` (§3's table) -- matched against
#: the same `rel` path `serve.py`'s `do_GET` already computes relative to
#: `pages/`, never against the raw URL. Deliberately a closed list of SHAPES, not
#: a catch-all: a new kind of page wired up later without a new pattern here
#: falls through to `NoRouteTableEntry`, which is the whole point of item 7's own
#: sabotage (add a route with no entry; the test must name it).
_VIEWER_GET_PATTERNS = tuple(re.compile(p) for p in (
    r"^home\.html$",
    #: The All counts page, the Overview's counts moved whole: it had no row, so
    #: with sign-in on it answered 404.
    r"^counts\.html$",
    r"^executions-[\w-]+\.html$",
    r"^incidents\.html$",
    r"^incidents-[\w.-]+\.html$",
    r"^runs/[^/]+/answer\.html$",
    r"^runs/[^/]+/case\.html$",
    #: A run key is sha256 hex (`store.run_key`), so exactly that: `[^/]+` admitted `..`.
    r"^runs/[0-9a-f]{64}/authorization\.html$",
    #: A stage's inputs and outputs, one page per manifest index.
    r"^runs/[0-9a-f]{64}/stage-[0-9]+\.html$",
    #: The run receipt.
    r"^runs/[0-9a-f]{64}/receipt\.html$",
    #: The run's own record, the delivery byte for byte (`ingest.bundle`): what a page that
    #: shortens a run's words offers for download.
    r"^runs/[0-9a-f]{64}/record\.tar$",
    r"^diff/[^/]+\.html$",
    r"^comparisons\.html$",
    #: Choose two runs: a pipeline's runs as run A, and run A's page of the others as run B.
    r"^choose-p[0-9]+\.html$",
    r"^choose-p[0-9]+-[0-9a-f]{64}\.html$",
    r"^policy\.html$",
    r"^policy/[^/]+\.html$",
    r"^policy-verdict-[\w-]+\.html$",
    r"^policy-issuer-[\w.-]+\.html$",
))

#: POST routes, exact path -> required role.
_POST_ROLES = {
    "/v1/runs": INGESTER,
    "/v1/decisions": INGESTER,
    "/compare": VIEWER,
    #: "Show more" on a comparison's text diff -- who may run a comparison
    #: may run its text diff at the console's larger limit.
    "/text-diff/more": VIEWER,
}


class NoRouteTableEntry(LookupError):
    """Raised for a request this table has no row for at all -- refused, per §1
    item 8: a route added later without an explicit role assignment fails closed.
    """


def required_role(method: str, path: str, *, rel_for_get: str | None = None) -> str | None:
    """The role a request needs. `None` means no principal is required at all.
    Raises `NoRouteTableEntry` for anything this table does not name -- there is
    no default role a caller falls back to.

    `rel_for_get` is the same store-relative path `serve.py` resolves a GET
    against (`"home.html"` for `/` or `""`, `path.lstrip("/")` otherwise) --
    passed in rather than recomputed here so there is exactly one place that
    turns a URL into a page path.
    """
    if (method, path) in _UNAUTHENTICATED_EXACT:
        return None
    if method == "GET":
        rel = rel_for_get if rel_for_get is not None else path.lstrip("/")
        for pattern in _VIEWER_GET_PATTERNS:
            if pattern.match(rel):
                return VIEWER
        raise NoRouteTableEntry(
            f"GET {path!r} (rendered path {rel!r}) has no row in the role table")
    if method == "POST":
        if path in _POST_ROLES:
            return _POST_ROLES[path]
        raise NoRouteTableEntry(f"POST {path!r} has no row in the role table")
    raise NoRouteTableEntry(f"{method} {path!r} has no row in the role table")


def role_includes(granted: str, required: str) -> bool:
    """`admin` includes `viewer`; `ingester` includes nothing else at all --
    roles are not nested unless stated. A bearer
    token's `ingester` never satisfies a `viewer` requirement, and a browser
    session's `viewer` never satisfies `ingester` (§1 item 11).
    """
    if granted == required:
        return True
    if granted == ADMIN and required == VIEWER:
        return True
    return False
