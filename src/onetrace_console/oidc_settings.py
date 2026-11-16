"""Entra ID sign-in's settings, read once at start: the issuer, the redirect URI and the client
credential (`sign_in.oidc`, `config._validate_oidc`).

The credential is a certificate (private_key_jwt, preferred), read from the PEM file the
configuration names, or a client secret, read from the environment variable it names. Neither is
ever printed, logged, put in an error or drawn on a page: a refusal names the file or the variable,
never what it holds, and `Credential`'s repr says only which kind it is.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from onetrace_console.config import oidc_issuer, oidc_redirect_uri

_PEM_BLOCK = re.compile(rb"-----BEGIN ([A-Z0-9 ]+)-----\r?\n.*?-----END \1-----", re.S)


class CredentialError(RuntimeError):
    """The configured client credential can't be used. `str()` is safe to print: it names where
    the credential was looked for, never its contents."""

    def __init__(self, message: str, fix: str) -> None:
        super().__init__(message)
        self.fix = fix


@dataclass(frozen=True)
class Credential:
    """The client credential. `kind` is `certificate` or `secret`; the key and the secret are kept
    out of the repr, and so out of any log line or traceback that prints this object."""

    kind: str
    private_key: object = field(default=None, repr=False, compare=False)
    #: The certificate's SHA-1 thumbprint, base64url without padding: the client assertion's `x5t`,
    #: by which Entra finds the certificate uploaded to the registration.
    x5t: str = ""
    secret: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True)
class OidcSettings:
    tenant_id: str
    client_id: str
    issuer: str
    redirect_uri: str
    session_max_hours: int
    credential: Credential = field(repr=False)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def load_certificate(path: str) -> Credential:
    """The certificate and its RSA private key, from one PEM file."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    fix = (
        "name in sign_in.oidc.client_certificate a PEM file holding the certificate uploaded to the app "
        "registration and its unencrypted RSA private key, readable by the user the console runs as."
    )
    try:
        data = Path(path).read_bytes()
    except OSError as e:
        raise CredentialError(
            f"cannot read the client certificate at {path} (sign_in.oidc.client_certificate): "
            f"{e.strerror or type(e).__name__}",
            fix,
        ) from None
    blocks = {m.group(1).decode(): m.group(0) for m in _PEM_BLOCK.finditer(data)}
    cert_pem = blocks.get("CERTIFICATE")
    key_pem = next((v for k, v in blocks.items() if k.endswith("PRIVATE KEY")), None)
    if cert_pem is None or key_pem is None:
        missing = " and no ".join(w for w, b in (("certificate", cert_pem), ("private key", key_pem)) if b is None)
        raise CredentialError(
            f"the client certificate file at {path} (sign_in.oidc.client_certificate) holds no {missing}", fix
        )
    try:
        cert = x509.load_pem_x509_certificate(cert_pem)
        key = serialization.load_pem_private_key(key_pem, password=None)
    except (ValueError, TypeError):
        #: The library's own message is not shown: it can quote what it could not parse.
        raise CredentialError(
            f"the client certificate file at {path} (sign_in.oidc.client_certificate) could not be read as a "
            f"PEM certificate and an unencrypted private key",
            fix,
        ) from None
    if not isinstance(key, rsa.RSAPrivateKey):
        raise CredentialError(
            f"the private key in {path} (sign_in.oidc.client_certificate) is not an RSA key; the client "
            f"assertion is signed with RS256",
            fix,
        )
    spki = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if cert.public_key().public_bytes(*spki) != key.public_key().public_bytes(*spki):
        raise CredentialError(
            f"the private key in {path} (sign_in.oidc.client_certificate) is not the certificate's own", fix
        )
    der = cert.public_bytes(serialization.Encoding.DER)
    return Credential(kind="certificate", private_key=key, x5t=_b64url(hashlib.sha1(der).digest()))  # noqa: S324 -- Entra's x5t is the SHA-1 thumbprint


def load_secret(name: str) -> Credential:
    secret = os.environ.get(name, "")
    if not secret.strip():
        raise CredentialError(
            f"the environment variable {name} (sign_in.oidc.client_secret_env) is not set or empty",
            f"set {name} to the app registration's client secret in the environment the console starts "
            f"in, or use a certificate (sign_in.oidc.client_certificate).",
        )
    return Credential(kind="secret", secret=secret)


def load(config) -> OidcSettings:
    """`sign_in.oidc`'s settings with the credential read. Raises `CredentialError`."""
    oidc = config.sign_in["oidc"]
    if oidc.get("client_certificate"):
        credential = load_certificate(oidc["client_certificate"])
    else:
        credential = load_secret(oidc["client_secret_env"])
    return OidcSettings(
        tenant_id=oidc["tenant_id"],
        client_id=oidc["client_id"],
        issuer=oidc_issuer(oidc["tenant_id"]),
        redirect_uri=oidc_redirect_uri(config.sign_in["public_url"]),
        session_max_hours=oidc["session_max_hours"],
        credential=credential,
    )
