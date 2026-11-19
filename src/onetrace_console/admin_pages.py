"""The admin pages: `/admin/people`, `/admin/teams` and `/admin/audit`, an
`admin`'s alone, each drawn as it is asked for and drawing nothing from runs.

- **People** (`/admin/people`): SCIM's Users, each by its `userName`, `displayName`, work e-mail, `externalId` and
  whether it is active, an `externalId` not shaped like an object id flagged; the SCIM tokens and when each expires,
  warned from 14 days before; the requests refused from outside `scim.allowed_sources`; the values dropped beside a
  removal, and the writes refused that would have removed access.
- **Teams** (`/admin/teams`): each configured team, its `scim_group` and `role_claim`; the Groups with no team; the
  teams that name no provisioned Group.
- **Audit** (`/admin/audit`): whether the log is on, its last `seq` and head, its second location, and the actions
  not recorded since an append last failed.

Every page says, at its top, when SCIM's enforcement of sign-in is off and since when, and when the audit log is
failing. A directory string is escaped as it is drawn, and was bounded and cleaned as it was kept (`scim._clean`).
`Facts` is what a page is drawn from, so the layout check draws them from examples (`tools/signin_pages.py`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from html import escape

PATHS = {"people": "admin/people", "teams": "admin/teams", "audit": "admin/audit"}
TITLES = {"people": "People", "teams": "Teams", "audit": "Audit log"}
_GUID = re.compile(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}")


@dataclass
class Facts:
    """What the admin pages say: gathered from the store's root and the configuration (`gather`), never from runs."""

    scim_on: bool = False
    enforcement: tuple[bool, str | None] = (True, None)
    users: list[dict] = field(default_factory=list)
    tokens: list[dict] = field(default_factory=list)
    refused_sources: int = 0
    dropped: list[dict] = field(default_factory=list)
    refused_writes: list[dict] = field(default_factory=list)
    teams: dict = field(default_factory=dict)
    groups: list[dict] = field(default_factory=list)
    unmapped: list[dict] = field(default_factory=list)
    unprovisioned: list[str] = field(default_factory=list)
    audit_on: bool = False
    head: dict | None = None
    head_location: str = ""
    unrecorded: list[dict] = field(default_factory=list)


def gather(
    store_root, config, *, audit_log=None, refused_sources: int = 0, refused_writes: list[dict] | None = None
) -> Facts:
    """The facts, read from `<store_root>/scim/`, the audit log (the console's own, `audit_log`, where given) and the
    configuration."""
    from datetime import UTC, datetime, timedelta

    from onetrace_console import audit, scim

    on = bool(config.scim.get("enabled"))
    tokens = []
    now = datetime.now(UTC)
    for t in scim.TokenStore(store_root).live() if on else ():
        expires = datetime.fromisoformat(t.expires_at.replace("Z", "+00:00"))
        tokens.append(
            {"id": t.token_id, "expires": t.expires_at, "soon": expires - now <= timedelta(days=scim.WARN_DAYS)}
        )
    log = audit_log if audit_log is not None else audit.audit_for(config, store_root).log
    dropped = []
    head = None
    unrecorded = []
    if log is not None:
        try:
            head = log.head()
            unrecorded = [{"at": n.get("at", ""), "event": n.get("event", "")} for n in log.unrecorded()]
            for e in log.entries():
                if e.get("event") == "scim.write" and e.get("detail", {}).get("dropped"):
                    dropped.append({"at": e["at"], "id": e["object"], "dropped": e["detail"]["dropped"]})
        except (OSError, ValueError, audit.AuditUnavailable):
            head = None
    return Facts(
        scim_on=on,
        enforcement=scim.enforcement(store_root) if on else (True, None),
        users=scim.Users(store_root).all() if on else [],
        tokens=tokens,
        refused_sources=refused_sources,
        dropped=dropped,
        refused_writes=list(refused_writes or []),
        teams=dict(config.teams),
        groups=scim.Groups(store_root).all() if on else [],
        unmapped=scim.unmapped_groups(store_root, config.teams) if on else [],
        unprovisioned=scim.unprovisioned_mappings(store_root, config.teams) if on else [],
        audit_on=log is not None,
        head=head,
        head_location=str(log.head_location) if log is not None else "",
        unrecorded=unrecorded,
    )


def _banners(f: Facts) -> str:
    out = []
    if f.scim_on and not f.enforcement[0]:
        out.append(
            f'<p class="notice" data-admin="enforcement-off"><strong>SCIM\'s enforcement of sign-in is off</strong>, '
            f"since {escape(f.enforcement[1] or 'a time not kept')}: an Entra ID sign-in is admitted on its app roles "
            "alone, with no team from SCIM. Turn it on, on the console's machine, with "
            "<code>onetrace-console scim enforcement on</code>.</p>"
        )
    if f.unrecorded:
        since = min(n["at"] for n in f.unrecorded)
        out.append(
            f'<p class="notice" data-admin="audit-failing"><strong>The audit log is failing</strong>: '
            f"{len(f.unrecorded)} action(s) not recorded since {escape(since)}. Each removal of access was applied; "
            "every other action was refused. The next append that succeeds records them by kind and count.</p>"
        )
    return "".join(out)


def _table(head: tuple[str, ...], rows: Sequence[tuple[str, ...]], empty: str, name: str) -> str:
    """A list, one item per row, each field labelled: it reflows at any width, as a table of ids would not."""
    if not rows:
        return f'<p data-admin="{name}-none">{escape(empty)}</p>'
    items = "".join(
        "<li>" + " ".join(f'<span class="field"><b>{escape(h)}</b> {c}</span>' for h, c in zip(head, r) if c) + "</li>"
        for r in rows
    )
    return f'<ul class="admin-list" data-admin="{name}">{items}</ul>'


def people(f: Facts) -> str:
    users = [
        (
            escape(u.get("userName", "")),
            escape(u.get("displayName", "")),
            escape(u.get("email", "")),
            f"<code>{escape(u.get('externalId', ''))}</code>"
            + (
                ""
                if _GUID.fullmatch(u.get("externalId", ""))
                else ' <strong data-admin="not-object-id">not an object id</strong>'
            ),
            "active" if u.get("active") else "<strong>inactive</strong>",
        )
        for u in f.users
    ]
    tokens = [
        (
            f"<code>{escape(t['id'])}</code>",
            escape(t["expires"])
            + (' <strong data-admin="expires-soon">expires within 14 days</strong>' if t["soon"] else ""),
        )
        for t in f.tokens
    ]
    dropped = [(escape(d["at"]), f"<code>{escape(d['id'])}</code>", escape("; ".join(d["dropped"]))) for d in f.dropped]
    refused = [
        (
            escape(r.get("at", "")),
            escape(r.get("method", "")),
            escape(str(r.get("status", ""))),
            escape(r.get("reason", "")),
        )
        for r in f.refused_writes
    ]
    if not f.scim_on:
        body = '<p data-admin="scim-off">SCIM is off: people sign in on their app roles alone. Turn it on with <code>scim.enabled</code>.</p>'
    else:
        body = (
            "<h2>Users</h2>"
            + _table(
                ("userName", "Name", "E-mail", "externalId", "State"), users, "No User is provisioned yet.", "users"
            )
            + "<h2>SCIM tokens</h2>"
            + _table(("Token id", "Expires"), tokens, "No SCIM token is live.", "tokens")
            + f'<h2>Allowed sources</h2><p data-admin="refused-sources">{f.refused_sources} request(s) refused from outside '
            "<code>scim.allowed_sources</code> since the console started.</p>"
            + "<h2>Dropped beside a removal</h2>"
            + _table(("When", "User", "Dropped"), dropped, "Nothing was dropped beside a removal.", "dropped")
            + "<h2>Removals refused</h2>"
            + _table(
                ("When", "Method", "Status", "Reason"),
                refused,
                "No write that would have removed access was refused.",
                "refused",
            )
        )
    return _page("people", f, body)


def teams(f: Facts) -> str:
    members = {g.get("externalId"): len(g.get("members", [])) for g in f.groups}
    rows = [
        (
            escape(name),
            f"<code>{escape(entry.get('scim_group') or '')}</code>" if entry.get("scim_group") else "none",
            escape(entry.get("role_claim") or "none"),
            str(members.get((entry.get("scim_group") or "").lower(), 0)) if f.scim_on else "",
        )
        for name, entry in f.teams.items()
    ]
    unmapped = [
        (
            escape(g.get("displayName", "")),
            f"<code>{escape(g.get('externalId', ''))}</code>",
            str(len(g.get("members", []))),
        )
        for g in f.unmapped
    ]
    body = (
        _table(("Team", "SCIM group", "Role claim", "Members"), rows, "No team is configured.", "teams")
        + "<h2>Groups with no team</h2>"
        + _table(("Group", "externalId", "Members"), unmapped, "Every provisioned Group is a team's.", "unmapped")
        + "<h2>Names no provisioned group</h2>"
        + (
            '<ul data-admin="unprovisioned">' + "".join(f"<li>{escape(t)}</li>" for t in f.unprovisioned) + "</ul>"
            if f.unprovisioned
            else '<p data-admin="unprovisioned-none">Every team that names a group names one provisioned.</p>'
        )
    )
    return _page("teams", f, body)


def audit_page(f: Facts) -> str:
    if not f.audit_on:
        body = '<p data-admin="audit-off">The audit log is off. Turn it on with <code>audit.enabled</code> and <code>audit.head_location</code>.</p>'
    else:
        head = f.head or {}
        body = (
            f'<dl data-admin="head"><dt>Last seq</dt><dd>{escape(str(head.get("seq", "")))}</dd>'
            f"<dt>Head</dt><dd><code>{escape(str(head.get('head') or 'none yet'))}</code></dd>"
            f"<dt>Heads kept at</dt><dd><code>{escape(f.head_location)}</code></dd></dl>"
            "<p>Check it with <code>onetrace-console audit verify</code>, and keep a checkpoint with "
            "<code>onetrace-console audit checkpoint</code>.</p>"
        )
    return _page("audit", f, body)


def _page(which: str, f: Facts, body: str) -> str:
    from onetrace_console.render import _document

    nav = " · ".join(
        f'<a href="/{PATHS[k]}">{escape(TITLES[k])}</a>' if k != which else f"<strong>{escape(TITLES[k])}</strong>"
        for k in ("people", "teams", "audit")
    )
    content = (
        f'<div class="cp setup"><h1>{escape(TITLES[which])}</h1><p data-admin="nav">{nav}</p>{_banners(f)}{body}</div>'
    )
    return _document(TITLES[which], content)


def page(which: str, f: Facts) -> str:
    return {"people": people, "teams": teams, "audit": audit_page}[which](f)
