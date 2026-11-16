"""Sign-in through Entra ID, over HTTP, against the fake (`tests/fake_entra.py`): the authorization code
flow with PKCE (S256), `state` and `nonce` single-use and bound to the browser by a cookie that expires
after ten minutes, `response_mode=query`; after sign-in, only a same-origin path recorded before the flow.
Every refusal is a page in plain words, and no secret, code or token reaches a log line, a page or the
access log."""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
from urllib.parse import parse_qs, quote, urlsplit

import pytest

from tests.fake_entra import CLIENT, TENANT, FakeEntra
from tests.test_signin_flow import _get, _post

PLANTED = "Pl4nted-client-secret-never-shown-0123456789"
NO_ROLE = "Your organisation hasn't given you a role in onetrace. Ask your administrator."
REFUSED_ROLE = b"this credential does not grant the required role"


def _set_cookies(headers) -> list[str]:
    raw = headers.get("Set-Cookie")
    return raw if isinstance(raw, list) else [raw] if raw else []


def _cookie(headers, name: str) -> str | None:
    for line in _set_cookies(headers):
        m = re.match(rf"{name}=([^;]*)", line)
        if m:
            return m.group(1)
    return None


@pytest.fixture
def entra(server, monkeypatch):
    """A console signing people in through the fake, with a client secret."""
    from onetrace_console.config import Config, oidc_issuer
    from onetrace_console.oidc_flow import FlowStore
    from onetrace_console.oidc_issuer import Issuer
    from onetrace_console.oidc_settings import Credential, OidcSettings
    from onetrace_console.serve import Handler
    from onetrace_console.sessions import SessionStore

    base, root = server
    names = ("config", "session_store", "oidc_settings", "oidc_issuer", "oidc_flows")
    saved = {n: getattr(Handler, n, None) for n in names}
    with FakeEntra(client_secret=PLANTED) as fake:
        assert oidc_issuer(TENANT).endswith(f"/{TENANT}/v2.0")
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
        Handler.oidc_settings = OidcSettings(
            tenant_id=TENANT,
            client_id=CLIENT,
            issuer=fake.issuer,
            redirect_uri=base + "/signin/oidc/callback",
            session_max_hours=8,
            credential=Credential(kind="secret", secret=PLANTED),
        )
        Handler.oidc_issuer = Issuer(fake.issuer)
        Handler.oidc_flows = FlowStore()
        try:
            yield base, fake, root
        finally:
            for n, v in saved.items():
                setattr(Handler, n, v)


def _start(base, next_path: str | None = None):
    """GET the flow's start: (the authorize URL, the flow cookie, the response's headers)."""
    q = f"?next={quote(next_path, safe='')}" if next_path is not None else ""
    status, _b, headers, _ = _get(base, "/signin/oidc/start" + q)
    assert status == 303, status
    return headers["Location"], _cookie(headers, "onetrace_oidc"), headers


def _authorize(fake, url: str) -> str:
    """The person signs in at the fake: the callback URL it sends the browser to."""
    status, _b, headers, _ = _get(fake.base, url[len(fake.base) :])
    assert status == 302, status
    return headers["Location"]


def _callback(base, url: str, flow_cookie: str | None):
    path = url[len(base) :] if url.startswith(base) else url
    headers = {"Cookie": f"onetrace_oidc={flow_cookie}"} if flow_cookie else {}
    return _get(base, path, headers=headers)


def sign_in(base, fake, *, roles=("onetrace.viewer",), next_path: str | None = None):
    """A whole sign-in: (status, page, headers, session cookie value, csrf value)."""
    fake.user = {**fake.user, "roles": list(roles) if roles is not None else None}
    url, flow, _h = _start(base, next_path)
    status, body, headers, _ = _callback(base, _authorize(fake, url), flow)
    return status, body.decode(), headers, _cookie(headers, "onetrace_session"), _cookie(headers, "onetrace_csrf")


# ------------------------------------------------------------------ the request to Entra


def test_the_sign_in_page_offers_microsoft_and_no_password(entra, examined):
    base, _fake, _root = entra
    examined(3, "the page, its link, no password field")
    status, body, _h, _ = _get(base, "/signin?next=%2Fcomparisons.html")
    page = body.decode()
    assert status == 200 and "Sign in with Microsoft" in page
    assert (
        'action="/signin/oidc/start"' in page and '<input type="hidden" name="next" value="/comparisons.html">' in page
    )
    assert '<button class="btn-primary" data-busy="Signing in…" type="submit">Sign in with Microsoft</button>' in page
    assert 'type="password"' not in page


def test_the_authorization_request_carries_pkce_state_nonce_and_query_response_mode(entra, examined):
    base, fake, _root = entra
    examined(9, "the endpoint and each parameter, two starts differing")
    url, _flow, _h = _start(base)
    assert url.startswith(fake.endpoint("authorize") + "?")
    q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
    assert q["client_id"] == CLIENT and q["response_type"] == "code" and q["response_mode"] == "query"
    assert q["redirect_uri"] == base + "/signin/oidc/callback"
    assert "openid" in q["scope"].split()
    assert q["code_challenge_method"] == "S256" and re.fullmatch(r"[A-Za-z0-9_-]{43}", q["code_challenge"])
    assert len(q["state"]) >= 32 and len(q["nonce"]) >= 32
    q2 = {k: v[0] for k, v in parse_qs(urlsplit(_start(base)[0]).query).items()}
    assert {q2["state"], q2["nonce"], q2["code_challenge"]}.isdisjoint({q["state"], q["nonce"], q["code_challenge"]})


def test_the_flow_cookie_is_httponly_lax_scoped_and_lasts_ten_minutes(entra, examined):
    from onetrace_console.serve import Handler

    base, _fake, _root = entra
    examined(5, "HttpOnly, SameSite=Lax, Path, Max-Age; Secure where cookies are")
    _url, _flow, headers = _start(base)
    line = next(c for c in _set_cookies(headers) if c.startswith("onetrace_oidc="))
    assert "HttpOnly" in line and "SameSite=Lax" in line and "Path=/signin/oidc" in line and "Max-Age=600" in line
    assert "Secure" not in line
    Handler.config.sign_in["insecure_cookie_for_local_dev"] = False
    try:
        _url, _flow, headers = _start(base)
        assert "Secure" in next(c for c in _set_cookies(headers) if c.startswith("onetrace_oidc="))
    finally:
        Handler.config.sign_in["insecure_cookie_for_local_dev"] = True


# ------------------------------------------------------------------ a sign-in for each role


@pytest.mark.parametrize("role", ["viewer", "investigator", "admin"])
def test_a_sign_in_for_each_role_and_its_routes(entra, role, examined):
    """Signed in through the flow: the session holds the role, and the routes answer for it."""
    from onetrace_console import roles
    from onetrace_console.serve import Handler

    base, fake, _root = entra
    examined(5, f"{role}: the session, the page, Compare, Set up Explain's page, the Overview")
    status, page, _h, session, csrf = sign_in(base, fake, roles=[f"onetrace.{role}"])
    assert status == 200 and session and csrf
    assert Handler.session_store.get(session).role == role
    assert 'http-equiv="refresh" content="0;url=/"' in page
    auth = {"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}", "X-CSRF-Token": csrf, "Origin": base}
    status, body, _h, _ = _post(base, "/compare", b"", headers=auth)
    assert (status == 403 and REFUSED_ROLE in body) is not roles.role_includes(role, roles.INVESTIGATOR)
    status, body, _h, _ = _get(base, "/explain/setup", headers=auth)
    assert (status == 403 and REFUSED_ROLE in body) is not roles.role_includes(role, roles.ADMIN)
    assert _get(base, "/", headers=auth)[0] == 200


def test_no_role_means_no_sign_in(entra, examined):
    base, fake, _root = entra
    examined(3, "403, the sentence, no session")
    status, page, _h, session, _csrf = sign_in(base, fake, roles=None)
    assert status == 403 and NO_ROLE in html.unescape(page) and session is None


# ------------------------------------------------------------------ refused


def _refused(status, page: str, session, says: str) -> None:
    page = html.unescape(page)
    assert status in (400, 403), status
    assert says in page, page
    assert "Start again" in page and session is None


def test_a_callback_without_the_browser_s_cookie_is_refused(entra, examined):
    base, fake, _root = entra
    examined(1, "the flow cookie left out")
    url, _flow, _h = _start(base)
    status, body, headers, _ = _callback(base, _authorize(fake, url), None)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "can't be finished in this browser")


@pytest.mark.parametrize("change", ["missing", "mismatched"])
def test_a_missing_or_mismatched_state_is_refused(entra, change, examined):
    base, fake, _root = entra
    examined(1, f"state {change}")
    url, flow, _h = _start(base)
    callback = _authorize(fake, url)
    q = {k: v[0] for k, v in parse_qs(urlsplit(callback).query).items()}
    if change == "missing":
        callback = f"{base}/signin/oidc/callback?code={q['code']}"
    else:
        callback = f"{base}/signin/oidc/callback?code={q['code']}&state={'x' * 43}"
    status, body, headers, _ = _callback(base, callback, flow)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "doesn't match this browser's")


def test_a_replayed_state_is_refused(entra, examined):
    base, fake, _root = entra
    examined(2, "the same callback, cookie and all, twice")
    url, flow, _h = _start(base)
    callback = _authorize(fake, url)
    assert _callback(base, callback, flow)[0] == 200
    status, body, headers, _ = _callback(base, callback, flow)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "can't be finished in this browser")


def test_a_flow_older_than_ten_minutes_is_refused(entra, examined):
    from onetrace_console.serve import Handler

    base, fake, _root = entra
    examined(1, "the callback 601 s after the start")
    clock = [1000.0]
    Handler.oidc_flows.clock = lambda: clock[0]
    url, flow, _h = _start(base)
    clock[0] += 601
    status, body, headers, _ = _callback(base, _authorize(fake, url), flow)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "can't be finished in this browser")


def test_a_pkce_verifier_mismatch_is_refused(entra, examined):
    """The fake holds the code to another challenge than the one the console's verifier answers."""
    base, fake, _root = entra
    examined(1, "the code's challenge changed at the fake")
    url, flow, _h = _start(base)
    callback = _authorize(fake, url)
    code = parse_qs(urlsplit(callback).query)["code"][0]
    fake.codes[code]["challenge"] = base64.urlsafe_b64encode(hashlib.sha256(b"other").digest()).rstrip(b"=").decode()
    status, body, headers, _ = _callback(base, callback, flow)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "refused the token request (invalid_grant)")


def test_a_code_used_twice_is_refused(entra, examined):
    base, fake, _root = entra
    examined(2, "a code redeemed, then sent again under a new flow's state")
    url, flow, _h = _start(base)
    first = _authorize(fake, url)
    assert _callback(base, first, flow)[0] == 200
    code = parse_qs(urlsplit(first).query)["code"][0]
    url2, flow2, _h = _start(base)
    state2 = parse_qs(urlsplit(url2).query)["state"][0]
    status, body, headers, _ = _callback(base, f"{base}/signin/oidc/callback?code={code}&state={state2}", flow2)
    _refused(status, body.decode(), _cookie(headers, "onetrace_session"), "refused the token request (invalid_grant)")


def test_microsoft_s_own_refusal_is_said_by_its_code(entra, examined):
    base, _fake, _root = entra
    examined(1, "error=access_denied at the callback")
    url, flow, _h = _start(base)
    state = parse_qs(urlsplit(url).query)["state"][0]
    status, body, headers, _ = _callback(
        base, f"{base}/signin/oidc/callback?error=access_denied&error_description=AADSTS65004&state={state}", flow
    )
    page = body.decode()
    _refused(status, page, _cookie(headers, "onetrace_session"), "Microsoft did not sign you in (access_denied)")
    assert "AADSTS" not in page


@pytest.mark.parametrize(
    "claims,says",
    [
        ({"iss": "http://127.0.0.1:1/other/v2.0"}, "was not issued by the configured issuer"),
        ({"aud": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"}, "is not for this console"),
        ({"tid": "22222222-2222-3333-4444-555555555555"}, "is from another organisation"),
        ({"exp": 1_000_000_000}, "has expired"),
        ({"nbf": 4_000_000_000}, "is not valid yet"),
        ({"nonce": "not-this-flow-s"}, "was not asked for by this sign-in"),
    ],
    ids=["iss", "aud", "tid", "exp", "nbf", "nonce"],
)
def test_a_token_that_fails_its_checks_is_refused_through_the_flow(entra, claims, says, examined):
    base, fake, _root = entra
    examined(1, says)
    fake.claims_override = claims
    status, page, _h, session, _csrf = sign_in(base, fake)
    _refused(status, page, session, says)


def test_a_bad_signature_and_alg_none_are_refused_through_the_flow(entra, examined):
    import jwt

    from tests.fake_entra import b64url, rsa_key

    base, fake, _root = entra
    examined(2, "signed by another key; alg none")
    other = rsa_key()
    fake.token_override = lambda c, f: jwt.encode(c, other, algorithm="RS256", headers={"kid": f.current_kid})
    _refused(*[sign_in(base, fake)[i] for i in (0, 1, 3)], "signature does not check")
    fake.token_override = lambda c, f: (
        f"{b64url(json.dumps({'alg': 'none'}).encode())}.{b64url(json.dumps(c).encode())}."
    )
    _refused(*[sign_in(base, fake)[i] for i in (0, 1, 3)], "is not signed with RS256")


def test_local_sign_in_is_off(entra, examined):
    base, _fake, _root = entra
    examined(1, "POST /signin")
    status, _b, _h, _ = _post(
        base, "/signin", b"username=a&password=b", headers={"Content-Type": "application/x-www-form-urlencoded"}
    )
    assert status == 404


# ------------------------------------------------------------------ where the browser goes after


def test_an_unsigned_in_page_request_records_where_to_return(entra, examined):
    base, _fake, _root = entra
    examined(1, "GET /comparisons.html with no session")
    status, _b, headers, _ = _get(base, "/comparisons.html?x=1")
    assert status == 303 and headers["Location"] == "/signin?next=%2Fcomparisons.html%3Fx%3D1"


@pytest.mark.parametrize(
    "asked,lands",
    [
        ("/comparisons.html?x=1", "/comparisons.html?x=1"),
        ("//evil.example/x", "/"),
        ("https://evil.example/x", "/"),
        ("/\\evil.example", "/"),
        ("/%2F%2Fevil.example", "/%2F%2Fevil.example"),
        ("javascript:alert(1)", "/"),
        ("comparisons.html", "/"),
        ("/x\r\nLocation: https://evil.example", "/"),
    ],
)
def test_after_sign_in_only_a_same_origin_path_recorded_before_the_flow(entra, asked, lands, examined):
    base, fake, _root = entra
    examined(1, f"next {asked!r}")
    status, page, _h, _session, _csrf = sign_in(base, fake, next_path=asked)
    assert status == 200
    target = re.search(r'http-equiv="refresh" content="0;url=([^"]*)"', page).group(1)
    assert target.replace("&amp;", "&") == lands
    assert "evil.example" not in page or lands.startswith("/%2F")


def test_the_return_is_the_one_recorded_not_one_named_at_the_callback(entra, examined):
    base, fake, _root = entra
    examined(1, "next= added to the callback URL")
    url, flow, _h = _start(base, "/comparisons.html")
    status, body, _h, _ = _callback(base, _authorize(fake, url) + "&next=//evil.example", flow)
    assert status == 200 and 'content="0;url=/comparisons.html"' in body.decode()


# ------------------------------------------------------------------ the credential: a certificate


def test_a_certificate_signs_the_client_assertion_and_no_secret_is_sent(entra, tmp_path, examined):
    import datetime

    import jwt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID

    from onetrace_console import oidc_settings
    from onetrace_console.serve import Handler
    from tests.fake_entra import rsa_key

    base, fake, _root = entra
    examined(5, "signed in; the assertion's type, x5t, audience; no client_secret in the form")
    key = rsa_key()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "onetrace test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(7)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem = tmp_path / "entra.pem"
    pem.write_bytes(
        cert.public_bytes(serialization.Encoding.PEM)
        + key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    )
    credential = oidc_settings.load_certificate(str(pem))
    s = Handler.oidc_settings
    Handler.oidc_settings = oidc_settings.OidcSettings(
        s.tenant_id, s.client_id, s.issuer, s.redirect_uri, s.session_max_hours, credential
    )
    fake.client_secret = None
    fake.client_public_key = key.public_key()
    status, _page, _h, session, _csrf = sign_in(base, fake)
    assert status == 200 and session
    form = fake.token_forms[-1]
    assert form["client_assertion_type"] == "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
    assert jwt.get_unverified_header(form["client_assertion"])["x5t"] == credential.x5t
    assert jwt.decode(form["client_assertion"], options={"verify_signature": False})["aud"] == fake.endpoint("token")
    assert "client_secret" not in form


# ------------------------------------------------------------------ nothing secret anywhere


def _everything_written(root, capfd) -> str:
    out, err = capfd.readouterr()
    logs = "".join(
        p.read_text(encoding="utf-8", errors="replace") for p in root.rglob("*") if p.is_file() and "access" in str(p)
    )
    return out + err + logs


def test_a_planted_secret_a_code_and_a_token_appear_nowhere(entra, capfd, examined):
    """On success and on each failure: the console's log lines, its pages, its errors and the access log."""
    from onetrace_console.serve import Handler

    base, fake, root = entra
    pages: list[str] = []
    codes: list[str] = []
    tokens: list[str] = []
    original = fake.id_token

    def kept(*a, **kw):
        t = original(*a, **kw)
        tokens.append(t)
        return t

    fake.id_token = kept

    def one(**override):
        fake.claims_override = override.get("claims", {})
        fake.user = {**fake.user, "roles": override.get("roles", ["onetrace.admin"])}
        url, flow, _h = _start(base, "/comparisons.html")
        callback = _authorize(fake, url)
        codes.append(parse_qs(urlsplit(callback).query)["code"][0])
        status, body, _h, _ = _callback(base, callback, flow)
        pages.append(body.decode())
        if override.get("again"):
            pages.append(_callback(base, callback, flow)[1].decode())
        return status

    examined(6, "a success, a replay, no role, a wrong audience, an expired token, a wrong secret")
    assert one(again=True) == 200
    assert one(roles=None) == 403
    assert one(claims={"aud": "bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee"}) == 400
    assert one(claims={"exp": 1_000_000_000}) == 400
    fake.client_secret = "the-fake-expects-another"
    assert one() == 400
    written = _everything_written(root, capfd) + "".join(pages)
    assert Handler.oidc_settings.credential.secret == PLANTED
    assert PLANTED not in written
    for c in codes:
        assert c not in written, "a code reached a log line or a page"
    for t in tokens:
        assert t not in written and t.split(".")[2] not in written, "a token reached a log line or a page"


# ------------------------------------------------------------------ who the pages say is signed in


@pytest.mark.parametrize("role", ["viewer", "investigator", "admin"])
def test_the_pages_name_the_person_signed_in_never_their_ids(entra, role, examined):
    """The footer says who is signed in, by the name Entra gives, for each role: not "Local mode", and not the
    account's key (the tenant and object ids)."""
    base, fake, _root = entra
    examined(3, f"{role}: the name, not Local mode, not the ids")
    _status, _page, _h, session, csrf = sign_in(base, fake, roles=[f"onetrace.{role}"])
    status, body, _h, _ = _get(base, "/", headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"})
    page = html.unescape(body.decode())
    assert status == 200 and "Signed in as Ada Lovelace" in page
    assert "Local mode" not in page
    assert fake.user["oid"] not in page and TENANT not in page
