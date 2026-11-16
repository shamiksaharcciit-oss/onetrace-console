"""Sign-in through Entra ID: the ID token's checks (`oidc_token.check_id_token`). Its signature, RS256
only, against the issuer's published key; its claims: `iss` exactly the configured issuer, `aud` the
client id, `tid` the tenant id, `exp`, `nbf` and `iat` within five minutes of skew, `nonce` the flow's.
Each refusal is plain words that hold no token, code or claim value."""

from __future__ import annotations

import base64
import json
import time

import pytest

from tests.fake_entra import CLIENT, DROP, FakeEntra, b64url, rsa_key

PLANTED = "Pl4nted-claim-value-never-shown"
NONCE = "n0nce-of-this-flow"


@pytest.fixture
def fake():
    with FakeEntra() as f:
        yield f


def _check(fake, token: str, *, nonce: str = NONCE, now: float | None = None) -> dict:
    from onetrace_console.oidc_issuer import Issuer
    from onetrace_console.oidc_token import check_id_token

    return check_id_token(
        token,
        issuer=Issuer(fake.issuer),
        expected_issuer=fake.issuer,
        client_id=fake.client_id,
        tenant_id=fake.tenant,
        nonce=nonce,
        now=now,
    )


def _refused(fake, token: str, says: str, **kw) -> str:
    from onetrace_console.oidc_token import TokenRefused

    with pytest.raises(TokenRefused) as e:
        _check(fake, token, **kw)
    reason = str(e.value)
    assert says in reason, reason
    assert PLANTED not in reason and (not token or token not in reason), "a refusal holds a token or a claim value"
    for value in (fake.tenant, fake.client_id, NONCE, fake.user["oid"]):
        assert value not in reason, f"a refusal holds a claim value: {reason}"
    return reason


def test_a_good_token_is_accepted_and_its_claims_returned(fake, examined):
    examined(3, "oid, tid and roles read back")
    claims = _check(fake, fake.id_token(nonce=NONCE))
    assert claims["oid"] == fake.user["oid"] and claims["tid"] == fake.tenant
    assert claims["roles"] == ["onetrace.viewer"]


@pytest.mark.parametrize(
    "claim,value,says",
    [
        ("iss", PLANTED, "was not issued by the configured issuer"),
        ("aud", PLANTED, "is not for this console"),
        ("aud", [CLIENT, PLANTED], "is not for this console"),
        ("tid", PLANTED, "is from another organisation"),
    ],
    ids=["iss", "aud", "aud-list", "tid"],
)
def test_the_wrong_issuer_audience_or_tenant_is_refused(fake, claim, value, says, examined):
    examined(1, f"{claim} not the configured one")
    fake.claims_override = {claim: value}
    _refused(fake, fake.id_token(nonce=NONCE), says)


def test_an_issuer_differing_only_by_a_trailing_slash_is_refused(fake, examined):
    examined(1, "iss with a trailing slash")
    fake.claims_override = {"iss": fake.issuer + "/"}
    _refused(fake, fake.id_token(nonce=NONCE), "was not issued by the configured issuer")


def test_an_expired_token_is_refused_and_five_minutes_of_skew_allowed(fake, examined):
    examined(2, "exp 301 s ago refused, 299 s ago accepted")
    now = time.time()
    fake.claims_override = {"exp": int(now) - 301}
    _refused(fake, fake.id_token(nonce=NONCE), "has expired", now=now)
    fake.claims_override = {"exp": int(now) - 299}
    assert _check(fake, fake.id_token(nonce=NONCE), now=now)


def test_a_token_not_valid_yet_or_issued_in_the_future_is_refused(fake, examined):
    examined(3, "nbf and iat 301 s ahead refused; 299 s ahead accepted")
    now = time.time()
    fake.claims_override = {"nbf": int(now) + 301}
    _refused(fake, fake.id_token(nonce=NONCE), "is not valid yet", now=now)
    fake.claims_override = {"iat": int(now) + 301}
    _refused(fake, fake.id_token(nonce=NONCE), "was issued in the future", now=now)
    fake.claims_override = {"nbf": int(now) + 299, "iat": int(now) + 299}
    assert _check(fake, fake.id_token(nonce=NONCE), now=now)


@pytest.mark.parametrize("claim", ["exp", "iat", "nbf", "nonce", "oid", "tid", "iss", "aud"])
def test_a_token_missing_a_claim_it_needs_is_refused(fake, claim, examined):
    examined(1, f"no {claim}")
    fake.claims_override = {claim: DROP}
    _refused(fake, fake.id_token(nonce=NONCE), "is missing")


def test_a_time_claim_that_is_not_a_number_is_refused(fake, examined):
    examined(1, "exp as a string")
    fake.claims_override = {"exp": PLANTED}
    _refused(fake, fake.id_token(nonce=NONCE), "is not a time")


def test_a_bad_signature_is_refused(fake, examined):
    """Signed by another key, under the published key's id."""
    import jwt

    examined(1, "another key, the published kid")
    claims = json.loads(base64.urlsafe_b64decode(fake.id_token(nonce=NONCE).split(".")[1] + "=="))
    forged = jwt.encode(claims, rsa_key(), algorithm="RS256", headers={"kid": fake.current_kid})
    _refused(fake, forged, "signature does not check")


def test_a_changed_claim_breaks_the_signature(fake, examined):
    examined(1, "the payload swapped after signing")
    head, body, sig = fake.id_token(nonce=NONCE).split(".")
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    claims["roles"] = ["onetrace.admin"]
    _refused(fake, f"{head}.{b64url(json.dumps(claims).encode())}.{sig}", "signature does not check")


def _unsigned(header: dict, claims: dict, signature: bytes = b"") -> str:
    return f"{b64url(json.dumps(header).encode())}.{b64url(json.dumps(claims).encode())}.{b64url(signature)}"


def _claims(fake) -> dict:
    return json.loads(base64.urlsafe_b64decode(fake.id_token(nonce=NONCE).split(".")[1] + "=="))


@pytest.mark.parametrize("alg", ["none", "None", "NONE"])
def test_alg_none_is_refused(fake, alg, examined):
    examined(1, f"alg {alg!r}, no signature")
    _refused(fake, _unsigned({"alg": alg, "kid": fake.current_kid}, _claims(fake)), "is not signed with RS256")


def test_hs256_signed_with_the_public_key_is_refused(fake, examined):
    """Key confusion: an HMAC over the token with the issuer's published public key as the secret."""
    import hashlib
    import hmac

    from cryptography.hazmat.primitives import serialization

    examined(2, "HS256 over the PEM and over the DER of the published key")
    public = fake.keys[fake.current_kid].public_key()
    for secret in (
        public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo),
        public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo),
    ):
        head = b64url(json.dumps({"alg": "HS256", "kid": fake.current_kid}).encode())
        body = b64url(json.dumps(_claims(fake)).encode())
        sig = hmac.new(secret, f"{head}.{body}".encode(), hashlib.sha256).digest()
        _refused(fake, f"{head}.{body}.{b64url(sig)}", "is not signed with RS256")


@pytest.mark.parametrize("alg", ["HS384", "HS512", "RS512", "ES256", "PS256"])
def test_every_other_algorithm_is_refused(fake, alg, examined):
    examined(1, f"alg {alg}")
    _refused(
        fake, _unsigned({"alg": alg, "kid": fake.current_kid}, _claims(fake), b"x" * 32), "is not signed with RS256"
    )


def test_a_nonce_mismatch_is_refused(fake, examined):
    examined(1, "the token's nonce not the flow's")
    _refused(fake, fake.id_token(nonce=PLANTED), "was not asked for by this sign-in", nonce=NONCE)


def test_a_key_id_the_issuer_does_not_publish_is_refused(fake, examined):
    examined(1, "an unknown kid")
    fake.header_override = {"kid": "not-a-published-kid"}
    _refused(fake, fake.id_token(nonce=NONCE), "a key the issuer does not publish")


@pytest.mark.parametrize("token", ["", "a.b", "not-a-token", "....", PLANTED + ".x.y"])
def test_a_token_that_is_not_a_jwt_is_refused(fake, token, examined):
    examined(1, f"{token!r}")
    _refused(fake, token, "could not be read")
