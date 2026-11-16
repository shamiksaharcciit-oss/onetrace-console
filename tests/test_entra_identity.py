"""Sign-in through Entra ID: who someone is and which role they have (`oidc_identity`), how long their
session lasts (`sessions`), how the roles nest (`roles.role_includes`), and signing out."""

from __future__ import annotations

import time

import pytest

from tests.fake_entra import CLIENT, TENANT, FakeEntra

OID = "99999999-8888-7777-6666-555555555555"
NO_ROLE = "Your organisation hasn't given you a role in onetrace. Ask your administrator."


def _claims(**over) -> dict:
    now = int(time.time())
    claims = {
        "tid": TENANT,
        "oid": OID,
        "name": "Ada Lovelace",
        "preferred_username": "ada@example.org",
        "exp": now + 3600,
    }
    claims.update(over)
    return {k: v for k, v in claims.items() if v is not None}


def _who(claims: dict, hours: int = 8, now: float | None = None):
    from onetrace_console.oidc_identity import identity

    return identity(claims, session_max_hours=hours, now=time.time() if now is None else now)


@pytest.mark.parametrize(
    "roles,role",
    [
        (["onetrace.viewer"], "viewer"),
        (["onetrace.investigator"], "investigator"),
        (["onetrace.admin"], "admin"),
        (["onetrace.viewer", "onetrace.admin", "onetrace.investigator"], "admin"),
        (["onetrace.investigator", "onetrace.viewer"], "investigator"),
        (["Some.Other.App.Role", "onetrace.viewer"], "viewer"),
    ],
)
def test_the_highest_role_assigned_takes_effect(roles, role, examined):
    examined(1, f"roles {roles}")
    assert _who(_claims(roles=roles)).role == role


@pytest.mark.parametrize(
    "roles", [None, [], ["Some.Other.App.Role"], ["ONETRACE.ADMIN"], "onetrace.admin", [["onetrace.admin"]]]
)
def test_no_role_means_no_sign_in(roles, examined):
    """Only the `roles` claim: an unknown role, a name in another case, a string where a list
    belongs, none at all."""
    from onetrace_console.oidc_identity import NoRole

    examined(1, f"roles {roles!r}")
    with pytest.raises(NoRole) as e:
        _who(_claims(roles=roles))
    assert str(e.value) == NO_ROLE


def test_roles_come_from_the_roles_claim_alone(examined):
    """A group, a scope or a `wids` admin role in the token grants nothing."""
    from onetrace_console.oidc_identity import NoRole

    examined(1, "groups, scp and wids naming onetrace.admin, no roles claim")
    with pytest.raises(NoRole):
        _who(_claims(groups=["onetrace.admin"], scp="onetrace.admin", wids=["onetrace.admin"]))


def test_the_account_is_keyed_by_tenant_and_object_id_never_the_email(examined):
    examined(3, "the key, the same key under another email, the name for display only")
    a = _who(_claims(roles=["onetrace.viewer"]))
    b = _who(_claims(roles=["onetrace.viewer"], preferred_username="ada.renamed@example.org", name="Ada King"))
    assert a.key == f"{TENANT}/{OID}" == b.key
    assert a.display_name == "Ada Lovelace" and b.display_name == "Ada King"


def test_an_object_id_that_is_not_a_guid_is_refused(examined):
    from onetrace_console.oidc_token import TokenRefused

    examined(1, "oid '../../etc'")
    with pytest.raises(TokenRefused, match="object id"):
        _who(_claims(roles=["onetrace.viewer"], oid="../../etc"))


def test_a_session_lasts_until_the_token_expires_or_the_bound_whichever_first(examined):
    examined(2, "a token for 1 h under an 8 h bound; a token for 10 h under it")
    now = 1_800_000_000.0
    assert _who(_claims(roles=["onetrace.viewer"], exp=int(now) + 3600), hours=8, now=now).expires_at == now + 3600
    assert _who(_claims(roles=["onetrace.viewer"], exp=int(now) + 36000), hours=8, now=now).expires_at == now + 8 * 3600


def test_a_session_past_its_end_is_gone_and_its_role_is_kept_until_then(examined):
    from onetrace_console.sessions import SessionStore

    examined(3, "the role read back twice, then gone at its end")
    store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    clock = [1_800_000_000.0]
    store.wall = lambda: clock[0]
    s = store.create(f"{TENANT}/{OID}", role="investigator", display_name="Ada", expires_at=clock[0] + 60)
    assert store.get(s.session_id).role == "investigator"
    clock[0] += 59
    assert store.get(s.session_id).role == "investigator"
    clock[0] += 1
    assert store.get(s.session_id) is None


@pytest.mark.parametrize(
    "granted,required,ok",
    [
        ("viewer", "viewer", True),
        ("viewer", "investigator", False),
        ("viewer", "admin", False),
        ("investigator", "viewer", True),
        ("investigator", "investigator", True),
        ("investigator", "admin", False),
        ("admin", "viewer", True),
        ("admin", "investigator", True),
        ("admin", "admin", True),
        ("admin", "ingester", False),
        ("investigator", "ingester", False),
        ("ingester", "viewer", False),
        ("ingester", "investigator", False),
    ],
)
def test_the_roles_nest_viewer_investigator_admin_and_never_reach_ingester(granted, required, ok, examined):
    from onetrace_console import roles

    examined(1, f"{granted} for {required}")
    assert roles.role_includes(granted, required) is ok


# ------------------------------------------------------------------ signing out, over HTTP


@pytest.fixture
def oidc_console(server):
    """A console with `sign_in.method` `oidc` against the fake, and a session store."""
    from onetrace_console.config import Config
    from onetrace_console.oidc_issuer import Issuer
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore

    base, _root = server
    names = ("config", "session_store", "oidc_issuer")
    saved = {n: getattr(Handler, n, None) for n in names}
    with FakeEntra() as fake:
        Handler.config = Config(
            sign_in={
                "enabled": True,
                "method": "oidc",
                "public_url": base,
                "insecure_cookie_for_local_dev": True,
                "oidc": {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "X", "session_max_hours": 8},
            }
        )
        Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
        Handler.oidc_issuer = Issuer(fake.issuer)
        try:
            yield base, fake
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)


def test_sign_out_ends_the_session_and_offers_entra_s_own_sign_out(oidc_console, examined):
    from onetrace_console.serve import Handler
    from tests.test_signin_flow import _get, _post

    examined(4, "the page, Entra's link, the session gone, the cookie cleared")
    base, fake = oidc_console
    s = Handler.session_store.create(f"{TENANT}/{OID}", role="viewer", display_name="Ada", expires_at=time.time() + 600)
    cookie = f"onetrace_session={s.session_id}; onetrace_csrf={s.csrf_token}"
    status, body, headers, _ = _post(
        base,
        "/signout",
        f"csrf_token={s.csrf_token}".encode(),
        headers={"Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded", "Origin": base},
    )
    page = body.decode()
    assert status == 200 and "signed out of onetrace" in page
    assert f'action="{fake.endpoint("logout")}"' in page and "Sign out of Microsoft too" in page
    assert Handler.session_store.get(s.session_id) is None
    assert "onetrace_session=;" in str(headers.get("Set-Cookie"))
    status, _b, headers, _ = _get(base, "/", headers={"Cookie": cookie})
    assert status == 303


def test_a_local_console_signs_out_as_before(server, examined):
    """With `local`, sign-out still answers 303 to the sign-in page, and offers nothing else."""
    from onetrace_console.config import Config
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore
    from tests.test_signin_flow import _post

    examined(2, "303, to /signin")
    base, _root = server
    saved = (Handler.config, Handler.session_store)
    Handler.config = Config(sign_in={"enabled": True, "insecure_cookie_for_local_dev": True})
    Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    try:
        s = Handler.session_store.create("alice")
        status, _b, headers, _ = _post(
            base,
            "/signout",
            f"csrf_token={s.csrf_token}".encode(),
            headers={
                "Cookie": f"onetrace_session={s.session_id}; onetrace_csrf={s.csrf_token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        assert status == 303 and headers.get("Location") == "/signin"
    finally:
        Handler.config, Handler.session_store = saved
