"""Role enforcement, from one place: every route has a role, and a route without one is refused.

This is the single dispatch every request goes through: a role name, or `None` for
no principal required, or a refusal for a route this table has never heard of --
never a silent default to "open". The route table of sign-in and roles is the source
of truth this module encodes; a route added to `serve.py`
later without a matching entry here raises `NoRouteTableEntry`, which the caller
turns into a refusal rather than an unauthenticated pass-through.
"""

from __future__ import annotations

import re

VIEWER = "viewer"
#: Sign-in through Entra ID's middle role: a viewer who may also start work (`required_role(oidc=True)`).
INVESTIGATOR = "investigator"
INGESTER = "ingester"
ADMIN = "admin"
#: SCIM's principal: its token reaches `/scim/v2/*` and nothing else, and no session or ingester
#: token reaches `/scim/v2/*`.
SCIM = "scim"
#: The browser roles, in order: each includes the ones before it. `ingester` is apart.
_NESTED = (VIEWER, INVESTIGATOR, ADMIN)

#: A route's team rule, one of three:
#: - scoped by run: it reads or writes a run or a comparison, and answers another team's key as an unknown one;
#: - `admin`, unscoped: a console-wide setting, read or written across teams;
#: - draws nothing from runs: its answer holds nothing drawn from a run, and no count of runs.
#: Every row below has one, in both sets of rules; a row with none is refused, as a row with no role is.
SCOPED_BY_RUN = "scoped by run"
ADMIN_UNSCOPED = "admin, unscoped"
DRAWS_NOTHING = "draws nothing from runs"
_TEAM_RULES = (SCOPED_BY_RUN, ADMIN_UNSCOPED, DRAWS_NOTHING)

#: (method, exact path) pairs that need no principal at all -- the rule's own
#: two exceptions (health, sign-in) plus sign-out, which is either a no-op (no
#: session to invalidate) or itself invalidates the one credential a principal
#: check would otherwise have relied on.
_UNAUTHENTICATED_EXACT = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/signin"),
        ("POST", "/signin"),
        ("POST", "/signout"),
    }
)

#: Every GET page this console renders is `viewer` (the route table) -- matched against
#: the same `rel` path `serve.py`'s `do_GET` already computes relative to
#: `pages/`, never against the raw URL. Deliberately a closed list of SHAPES, not
#: a catch-all: a new kind of page wired up later without a new pattern here
#: falls through to `NoRouteTableEntry`, which is the whole point of item 7's own
#: sabotage (add a route with no entry; the test must name it).
_VIEWER_GET_PATTERNS = tuple(
    re.compile(p)
    for p in (
        r"^home\.html$",
        #: The watched folder's state (`watch.py`), which the Overview's and the runs list's notice polls: a
        #: viewer's wherever a configuration file is named. Local mode answers it before roles (`serve.py`).
        r"^v1/folder$",
        #: The All counts page, the Overview's counts moved whole: it had no row, so
        #: with sign-in on it answered 404.
        r"^counts\.html$",
        r"^executions-[\w-]+\.html$",
        r"^incidents\.html$",
        #: The monitoring view (`verdicts`), a local console's: each run's verdict against its reference.
        r"^monitor\.html$",
        r"^incidents-[\w.-]+\.html$",
        r"^runs/[^/]+/answer\.html$",
        r"^runs/[^/]+/case\.html$",
        #: A run key is sha256 hex (`store.run_key`), so exactly that: `[^/]+` admitted `..`.
        r"^runs/[0-9a-f]{64}/authorization\.html$",
        #: A run page's "Proof" view (`views`), beside its "What changed" at case.html.
        r"^runs/[0-9a-f]{64}/proof\.html$",
        #: A stage's inputs and outputs, one page per manifest index.
        r"^runs/[0-9a-f]{64}/stage-[0-9]+\.html$",
        #: The run receipt.
        r"^runs/[0-9a-f]{64}/receipt\.html$",
        #: The run's own record, the delivery byte for byte (`ingest.bundle`): what a page that
        #: shortens a run's words offers for download.
        r"^runs/[0-9a-f]{64}/record\.tar$",
        r"^diff/[^/]+\.html$",
        r"^comparisons\.html$",
        #: The console's Authorization page: every run with a gated step (`authorization_list`), read as the Runs list.
        r"^authorization\.html$",
        #: A pipeline's page, and its two filters.
        r"^pipeline-p[0-9]+(-agree|-attention)?\.html$",
        #: A pipeline's noise fields (`noise_pages`), drawn as asked: the list a comparison links.
        r"^pipelines/p[0-9]+/noise$",
        #: A pipeline's drift page, against the first run or each run's previous.
        r"^drift-p[0-9]+(-previous)?\.html$",
        #: A pipeline's first run to leave the reference (`bisect_page`), and its window form, drawn as asked.
        r"^bisect-p[0-9]+\.html$",
        r"^bisect$",
        #: Choose two runs: a pipeline's runs as run A, and run A's page of the others as run B.
        r"^choose-p[0-9]+\.html$",
        #: A comparison's explanation press now running, as its panel's script reads it.
        r"^explain/state$",
        #: The setup page, read-only (`explain_setup`).
        r"^explain/setup$",
        #: The index's search results (`search_page`): a read of the index, drawn as asked.
        r"^search$",
        #: The Runs page (`runs_page`): a read of the index, drawn as asked.
        r"^runs$",
        #: Neighbours by input's setup page (`neighbours`), on a local console: the setup itself where the
        #: extra is installed, and where it is not, the page that says so; a public console has none.
        r"^neighbours/setup$",
        #: The tokenizers this console keeps (`token_upload`), with Remove, on a local console.
        r"^model-tokenizers$",
        #: Trace forwarding's setup (`forward_pages`), on a local console: an admin's, in both sets (below).
        r"^forwarding/setup$",
        #: The admin pages (`admin_pages`): people, teams and the audit log, an admin's.
        r"^admin/people$",
        r"^admin/teams$",
        r"^admin/audit$",
        r"^choose-p[0-9]+-[0-9a-f]{64}\.html$",
        r"^policy\.html$",
        r"^policy/[^/]+\.html$",
        r"^policy-verdict-[\w-]+\.html$",
        r"^policy-issuer-[\w.-]+\.html$",
    )
)

#: Each GET row's team rule, by its pattern. The pages are drawn per team (`pages/t/<team>/`) and served from the
#: person's team's set, so every page drawn from runs is scoped by run; the settings pages read no run.
_GET_TEAM_RULES: dict[str, str] = {
    **{
        p.pattern: SCOPED_BY_RUN
        for p in _VIEWER_GET_PATTERNS
        if p.pattern not in (r"^explain/setup$", r"^neighbours/setup$", r"^model-tokenizers$", r"^forwarding/setup$")
        and not p.pattern.startswith(r"^admin/")
    },
    #: The admin pages: people, groups, teams and the audit log's head, the whole console's, drawing no run.
    **{rf"^admin/{name}$": ADMIN_UNSCOPED for name in ("people", "teams", "audit")},
    #: Trace forwarding's setup: a setting of the whole console, which names no run.
    r"^forwarding/setup$": ADMIN_UNSCOPED,
    #: Explain's setup, read-only: this user's onetrace-explain settings, no run.
    r"^explain/setup$": DRAWS_NOTHING,
    #: Neighbours by input's setup: whether the extra is on, and its model; no run.
    r"^neighbours/setup$": DRAWS_NOTHING,
    #: The tokenizers this console keeps: a setting of the whole console; a tokenizer's digest names no run.
    r"^model-tokenizers$": DRAWS_NOTHING,
}

#: POST routes, exact path -> (the role it needs with local sign-in, the role with sign-in through Entra
#: ID). With local sign-in a session is always a viewer, so its admin routes refuse every session, as in
#: 0.7.0; with Entra ID, the app role assigned decides (`oidc_identity`).
_POST_ROLES: dict[str, tuple[str, str]] = {
    "/v1/runs": (INGESTER, INGESTER),
    "/v1/decisions": (INGESTER, INGESTER),
    #: Starting a comparison: an investigator's with Entra ID.
    "/compare": (VIEWER, INVESTIGATOR),
    #: "Run on this page" on a comparison (`compare_view.run_check`): who may run a comparison may run its text diff
    #: or localize at its first difference.
    "/compare/check": (VIEWER, INVESTIGATOR),
    #: "Show more" on a comparison's text diff -- who may run a comparison
    #: may run its text diff at the console's larger limit.
    "/text-diff/more": (VIEWER, INVESTIGATOR),
    #: The explanation panel's three presses (`explain`): who may run a comparison may ask for a
    #: suggestion about it, see the packet, and run a check the explanation names.
    "/explain": (VIEWER, INVESTIGATOR),
    "/explain/packet": (VIEWER, INVESTIGATOR),
    "/explain/check": (VIEWER, INVESTIGATOR),
    "/explain/cancel": (VIEWER, INVESTIGATOR),
    "/explain/text": (VIEWER, INVESTIGATOR),
    #: "Mark as benchmark" and its undo (`benchmarks`): a mark in the console's store, never in a
    #: record; who can compare runs can say which run to compare against.
    "/benchmark": (VIEWER, INVESTIGATOR),
    #: "Check against an expectations file" (`expectations_after`): a check of a run against a file the
    #: person names, kept in the console's store, never in a record; who can compare runs can check one.
    "/expectations": (VIEWER, INVESTIGATOR),
    "/runs/load-not-closed": (VIEWER, INVESTIGATOR),
    #: Turning neighbours by input on or off (`neighbours`): a setting of the whole store that decides
    #: which model reads its kept inputs, so an admin's. Only where the extra is installed on a local
    #: console; anywhere else the server has no such route.
    "/neighbours/on": (ADMIN, ADMIN),
    "/neighbours/off": (ADMIN, ADMIN),
    #: Keeping a tokenizer picked on a model step's page (`token_upload`): a setting of the whole store that
    #: decides which tokenizer decodes its model steps, so an admin's with local sign-in; with Entra ID the
    #: tokenizer upload is an investigator's. Removing one stays an admin's.
    "/model-tokenizers": (ADMIN, INVESTIGATOR),
    "/model-tokenizers/remove": (ADMIN, ADMIN),
    #: Set up Explain's Save (`explain_setup`): it writes this user's onetrace-explain configuration and
    #: keychain, so an admin's. A local console's only.
    "/explain/setup": (ADMIN, ADMIN),
    #: Trace forwarding's changes and test trace (`forward_pages`): a setting of the whole console, which sends each new
    #: run's trace out. A local console's only.
    "/forwarding/setup": (ADMIN, ADMIN),
    #: A pipeline's noise fields marked or removed (`noise_pages`): a setting of a pipeline that changes what every
    #: comparison of its runs points to first, so an admin's. A local console's only.
    "/noise": (ADMIN, ADMIN),
}

#: Each POST row's team rule. A run's delivery and a decision export are scoped by the delivering token's team; the
#: settings of the whole console are `admin`'s, unscoped (the tokenizer upload included, though with Entra ID an
#: investigator may make it: it takes a digest, never a run's key, and answers nothing drawn from runs).
_POST_TEAM_RULES: dict[str, str] = {
    **{path: SCOPED_BY_RUN for path in _POST_ROLES},
    "/neighbours/on": ADMIN_UNSCOPED,
    "/neighbours/off": ADMIN_UNSCOPED,
    "/model-tokenizers": ADMIN_UNSCOPED,
    "/model-tokenizers/remove": ADMIN_UNSCOPED,
    "/explain/setup": ADMIN_UNSCOPED,
    "/forwarding/setup": ADMIN_UNSCOPED,
    "/noise": ADMIN_UNSCOPED,
}

#: With Entra ID, the flow's own routes need no principal (`oidc_flow`), and local sign-in's POST is gone.
_OIDC_UNAUTHENTICATED_EXACT = frozenset(
    {
        ("GET", "/health"),
        ("GET", "/signin"),
        ("GET", "/signin/oidc/start"),
        ("GET", "/signin/oidc/callback"),
        ("POST", "/signout"),
    }
)
#: The routes that need no principal, in either set: each draws nothing from runs (`/health` carries no count).
_NO_PRINCIPAL_TEAM_RULES: dict[tuple[str, str], str] = {
    row: DRAWS_NOTHING for row in _UNAUTHENTICATED_EXACT | _OIDC_UNAUTHENTICATED_EXACT
}

#: With Entra ID, the pages that need more than a viewer, by rendered path: the settings, an admin's;
#: the bisect form, drawn as asked, an investigator's.
#: With local sign-in, the pages that need more than a viewer, by rendered path: the admin pages.
_LOCAL_GET_ROLES = {"admin/people": ADMIN, "admin/teams": ADMIN, "admin/audit": ADMIN, "forwarding/setup": ADMIN}

_OIDC_GET_ROLES = {
    "admin/people": ADMIN,
    "admin/teams": ADMIN,
    "admin/audit": ADMIN,
    "explain/setup": ADMIN,
    "neighbours/setup": ADMIN,
    "forwarding/setup": ADMIN,
    "bisect": INVESTIGATOR,
}

#: The paths `serve.py` answers apart from this table's rows, each for a reason that holds with sign-in on:
#: - `/static/`, before any role is asked for: the stylesheet, the fonts and the icon, which hold no data;
#: - `/v1/folder`, the watched folder's state, before roles in local mode only (no configuration file:
#:   loopback, behind the local guard, no sign-in); with a configuration file it is a viewer's, its row above;
#: - `/` and `""`, the Overview's own address, answered as `home.html` through the role check, a viewer's;
#: - `/robots.txt`, before any role is asked for and on a public console only: what search engines may crawl, which
#:   holds no data.
SERVED_BEFORE_ROLES = frozenset({"/static/", "/v1/folder", "/", "", "/robots.txt"})


#: SCIM's routes: each route and method its own row, discovery included,
#: role `scim`. Matched by `serve.py` before the pages lookup, by SCIM's own token check, which stands apart from and
#: before the role check: a SCIM request is never let through by a role check that lets everything through. Each draws
#: nothing from runs. `{id}` is 32 hex; `{uri}` and `{name}` a schema's URN and a resource type's name.
_SCIM_ID = r"[0-9a-f]{32}"
_SCIM_ROWS: tuple[tuple[str, re.Pattern], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("GET", r"/scim/v2/ServiceProviderConfig"),
        ("GET", r"/scim/v2/Schemas"),
        ("GET", r"/scim/v2/Schemas/urn:[A-Za-z0-9:._-]+"),
        ("GET", r"/scim/v2/ResourceTypes"),
        ("GET", r"/scim/v2/ResourceTypes/[A-Za-z]+"),
        ("GET", r"/scim/v2/Users"),
        ("POST", r"/scim/v2/Users"),
        *((m, rf"/scim/v2/Users/{_SCIM_ID}") for m in ("GET", "PUT", "PATCH", "DELETE")),
        ("GET", r"/scim/v2/Groups"),
        ("POST", r"/scim/v2/Groups"),
        *((m, rf"/scim/v2/Groups/{_SCIM_ID}") for m in ("GET", "PUT", "PATCH", "DELETE")),
    )
)


def scim_row(method: str, path: str) -> bool:
    """Whether `method` and `path` are a row of SCIM's table."""
    return any(m == method and pattern.fullmatch(path) for m, pattern in _SCIM_ROWS)


def post_routes() -> dict[str, tuple[str, str]]:
    """Every POST route: (its role with local sign-in, its role with Entra ID)."""
    return dict(_POST_ROLES)


class NoRouteTableEntry(LookupError):
    """Raised for a request this table has no row for at all -- refused, as the rule is
    that a route added later without an explicit role assignment fails closed.
    """


def _row(method: str, path: str, *, rel_for_get: str | None, oidc: bool) -> tuple[str | None, str]:
    """(the role the row needs, `None` for no principal; its team rule). `NoRouteTableEntry` for a request with no
    row, and for a row with no team rule."""
    if path == "/scim/v2" or path.startswith("/scim/v2/"):
        if scim_row(method, path):
            return SCIM, DRAWS_NOTHING
        raise NoRouteTableEntry(f"{method} {path!r} has no row in SCIM's table")
    if (method, path) in (_OIDC_UNAUTHENTICATED_EXACT if oidc else _UNAUTHENTICATED_EXACT):
        return None, _rule(_NO_PRINCIPAL_TEAM_RULES.get((method, path)), f"{method} {path!r}")
    if method == "GET":
        rel = rel_for_get if rel_for_get is not None else path.lstrip("/")
        for pattern in _VIEWER_GET_PATTERNS:
            if pattern.match(rel):
                role = _OIDC_GET_ROLES.get(rel, VIEWER) if oidc else _LOCAL_GET_ROLES.get(rel, VIEWER)
                return role, _rule(_GET_TEAM_RULES.get(pattern.pattern), f"GET {path!r} (rendered path {rel!r})")
        raise NoRouteTableEntry(f"GET {path!r} (rendered path {rel!r}) has no row in the role table")
    if method == "POST":
        if path in _POST_ROLES:
            local, entra = _POST_ROLES[path]
            return (entra if oidc else local), _rule(_POST_TEAM_RULES.get(path), f"POST {path!r}")
        raise NoRouteTableEntry(f"POST {path!r} has no row in the role table")
    raise NoRouteTableEntry(f"{method} {path!r} has no row in the role table")


def _rule(rule: str | None, row: str) -> str:
    if rule not in _TEAM_RULES:
        raise NoRouteTableEntry(f"{row} has a row in the role table but no team rule")
    return rule  # type: ignore[return-value]  # one of the three, just checked


def team_rule(method: str, path: str, *, rel_for_get: str | None = None, oidc: bool = False) -> str:
    """The request's team rule: `SCOPED_BY_RUN`, `ADMIN_UNSCOPED` or `DRAWS_NOTHING`. `NoRouteTableEntry` as for
    `required_role`."""
    return _row(method, path, rel_for_get=rel_for_get, oidc=oidc)[1]


def required_role(method: str, path: str, *, rel_for_get: str | None = None, oidc: bool = False) -> str | None:
    """The role a request needs. `None` means no principal is required at all.
    Raises `NoRouteTableEntry` for anything this table does not name -- there is
    no default role a caller falls back to.

    `rel_for_get` is the same store-relative path `serve.py` resolves a GET
    against (`"home.html"` for `/` or `""`, `path.lstrip("/")` otherwise) --
    passed in rather than recomputed here so there is exactly one place that
    turns a URL into a page path.

    `oidc`: the console signs people in through Entra ID (`sign_in.method` `oidc`), and the roles are
    viewer, investigator and admin. Otherwise every route needs what it needed before.
    """
    return _row(method, path, rel_for_get=rel_for_get, oidc=oidc)[0]


def role_includes(granted: str, required: str) -> bool:
    """`admin` includes `viewer`; `ingester` includes nothing else at all --
    roles are not nested unless stated. A bearer
    token's `ingester` never satisfies a `viewer` requirement, and a browser
    session's `viewer` never satisfies `ingester`: a machine's and a person's credentials never mix.
    """
    if granted == required:
        return True
    #: viewer < investigator < admin, as sign-in through Entra ID assigns them; a local session is
    #: always `viewer`, so for it this is the rule above (admin includes viewer), unchanged.
    if granted in _NESTED and required in _NESTED:
        return _NESTED.index(granted) >= _NESTED.index(required)
    return False
