"""Sign-in through Entra ID: the ID token's checks.

**The signature**, against the issuer's published key for the token's `kid` (`oidc_issuer.Issuer`),
with RS256 only: `alg` `none` and every HMAC (`HS*`) are refused before a key is looked up, so the
issuer's public key can never be taken as an HMAC secret (key confusion). PyJWT checks the signature
and nothing else; every claim is checked here, in the console's own words.

**The claims:** `iss` exactly the configured issuer, `aud` the client id, `tid` the tenant id, `exp`,
`nbf` and `iat` within five minutes of skew, `nonce` the flow's, and `oid`, which keys the account.

A `TokenRefused`'s words hold no token, code or claim value: each says which check failed, never
what the token said.
"""

from __future__ import annotations

import hmac
import time

#: Five minutes, the skew allowed between this machine's clock and the issuer's.
SKEW_SECONDS = 300
_NEEDED = ("iss", "aud", "tid", "oid", "exp", "nbf", "iat", "nonce")


class TokenRefused(Exception):
    """The ID token is refused. `str()` says why in plain words, safe on a page and in a log."""


def _equal(a: object, b: str) -> bool:
    return isinstance(a, str) and hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def check_id_token(
    token: str,
    *,
    issuer,
    expected_issuer: str,
    client_id: str,
    tenant_id: str,
    nonce: str,
    now: float | None = None,
    skew: int = SKEW_SECONDS,
) -> dict:
    """The token's claims, once every check passes; `TokenRefused` otherwise."""
    import jwt

    from onetrace_console.oidc_issuer import IssuerError

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise TokenRefused("the ID token could not be read") from None
    if header.get("alg") != "RS256":
        raise TokenRefused("the ID token is not signed with RS256")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid:
        raise TokenRefused("the ID token names no signing key")
    try:
        key = issuer.signing_key(kid)
    except IssuerError as e:
        raise TokenRefused(str(e)) from None
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            options={
                "verify_signature": True,
                "verify_exp": False,
                "verify_nbf": False,
                "verify_iat": False,
                "verify_aud": False,
                "verify_iss": False,
                "require": [],
            },
        )
    except jwt.InvalidSignatureError:
        raise TokenRefused("the ID token's signature does not check against the issuer's key") from None
    except jwt.PyJWTError:
        raise TokenRefused("the ID token could not be read") from None
    if not isinstance(claims, dict):
        raise TokenRefused("the ID token could not be read")
    missing = [c for c in _NEEDED if c not in claims]
    if missing:
        raise TokenRefused(f"the ID token is missing {', '.join(missing)}")
    if not _equal(claims["iss"], expected_issuer):
        raise TokenRefused("the ID token was not issued by the configured issuer")
    if not _equal(claims["aud"], client_id):
        raise TokenRefused("the ID token is not for this console (its audience is another application)")
    if not _equal(claims["tid"], tenant_id):
        raise TokenRefused("the ID token is from another organisation's directory")
    now = time.time() if now is None else now
    times = {}
    for name in ("exp", "nbf", "iat"):
        value = claims[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TokenRefused(f"the ID token's {name} is not a time")
        times[name] = float(value)
    if now > times["exp"] + skew:
        raise TokenRefused("the ID token has expired")
    if now + skew < times["nbf"]:
        raise TokenRefused("the ID token is not valid yet")
    if now + skew < times["iat"]:
        raise TokenRefused("the ID token was issued in the future")
    if not _equal(claims["nonce"], nonce):
        raise TokenRefused("the ID token was not asked for by this sign-in (its nonce is another one)")
    return claims
