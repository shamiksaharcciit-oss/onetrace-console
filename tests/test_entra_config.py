"""Entra ID sign-in's configuration (`sign_in.method`, `sign_in.oidc`): its keys, what is derived from
them, the client credential read at start, and the refusals, none of which quotes a value."""

from __future__ import annotations

import base64
import datetime
import hashlib
import json

import pytest

from onetrace_console import config as cfg
from onetrace_console import oidc_settings
from onetrace_console.config import Config, ConfigError

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
#: Planted where a secret could be pasted: no refusal may carry it.
PLANTED = "Pl4nted-Secr3t~value_that_must_never_show"


def _load(tmp_path, sign_in: dict, **top):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": sign_in, **top}), encoding="utf-8")
    return cfg.load(path)


def _oidc(**over) -> dict:
    oidc = {"tenant_id": TENANT, "client_id": CLIENT, "client_secret_env": "ONETRACE_ENTRA_SECRET"}
    oidc.update(over)
    return {"enabled": True, "method": "oidc", "public_url": "https://onetrace.example.org", "oidc": oidc}


def _refused(tmp_path, sign_in: dict, says: str, **top) -> str:
    with pytest.raises(ConfigError) as e:
        _load(tmp_path, sign_in, **top)
    text = str(e.value) + "\n" + (e.value.fix or "")
    assert says in text, text
    assert PLANTED not in text, "a refusal quoted a value"
    return text


def test_the_method_is_local_by_default_and_oidc_s_keys_have_their_defaults(tmp_path, examined):
    examined(2, "a file without sign_in.method, and Config() itself")
    for loaded in (_load(tmp_path, {"enabled": True}), Config()):
        assert loaded.sign_in["method"] == "local"
        assert loaded.sign_in["oidc"] == {
            "tenant_id": "",
            "client_id": "",
            "client_certificate": "",
            "client_secret_env": "",
            "session_max_hours": 8,
        }


def test_an_oidc_file_loads_and_the_issuer_and_redirect_uri_are_derived(tmp_path, examined):
    examined(3, "the loaded method, the derived issuer, the derived redirect URI")
    loaded = _load(tmp_path, _oidc())
    assert loaded.sign_in["method"] == "oidc"
    assert cfg.oidc_issuer(TENANT) == f"https://login.microsoftonline.com/{TENANT}/v2.0"
    assert cfg.oidc_redirect_uri(loaded.sign_in["public_url"]) == "https://onetrace.example.org/signin/oidc/callback"


@pytest.mark.parametrize("shared", ["common", "organizations", "consumers", "Common"])
def test_a_shared_tenant_is_refused(tmp_path, shared, examined):
    examined(1, f"tenant_id {shared!r}")
    _refused(tmp_path, _oidc(tenant_id=shared), "lets any organisation's people sign in")


@pytest.mark.parametrize("key", ["tenant_id", "client_id"])
def test_an_id_that_is_not_a_guid_is_refused_without_its_value(tmp_path, key, examined):
    examined(1, f"{key} holding a planted value")
    _refused(tmp_path, _oidc(**{key: PLANTED}), f"sign_in.oidc.{key} must be")


@pytest.mark.parametrize("key", ["client_secret", "secret", "private_key", "password"])
def test_a_credential_written_in_the_file_is_refused_without_its_value(tmp_path, key, examined):
    examined(1, f"sign_in.oidc.{key} holding a planted secret")
    _refused(tmp_path, _oidc(**{key: PLANTED}), "never written in the configuration file")


def test_client_secret_env_must_be_a_variable_s_name(tmp_path, examined):
    examined(1, "client_secret_env holding a planted secret rather than a name")
    _refused(tmp_path, _oidc(client_secret_env=PLANTED), "must be the NAME of an environment variable")


@pytest.mark.parametrize(
    "over,says",
    [
        ({"client_certificate": "/etc/onetrace/entra.pem"}, "names both of"),
        ({"client_secret_env": ""}, "names neither of"),
    ],
    ids=["both", "neither"],
)
def test_exactly_one_client_credential(tmp_path, over, says, examined):
    examined(1, says)
    _refused(tmp_path, _oidc(**over), says)


def test_oidc_needs_the_public_url_both_ids_and_sign_in_on(tmp_path, examined):
    examined(4, "no public_url, no tenant id, no client id, sign_in off")
    _refused(tmp_path, {**_oidc(), "public_url": ""}, "sign_in.public_url is empty")
    _refused(tmp_path, _oidc(tenant_id=""), "has no tenant_id")
    _refused(tmp_path, _oidc(client_id=""), "has no client_id")
    _refused(tmp_path, {**_oidc(), "enabled": False}, "sign_in.method is oidc and sign_in.enabled is false")


def test_an_unknown_method_and_a_session_bound_below_one_are_refused(tmp_path, examined):
    examined(2, "method 'saml', session_max_hours 0")
    _refused(tmp_path, {**_oidc(), "method": "saml"}, "sign_in.method must be one of")
    _refused(tmp_path, _oidc(session_max_hours=0), "session_max_hours must be at least 1")


def test_a_public_console_with_oidc_is_refused_saying_why(tmp_path, examined):
    """At load, whatever the rest of sign_in says, and by `start_refusal` for a configuration built
    in code."""
    from onetrace_console.public import start_refusal

    examined(3, "a public file with sign_in off, one with it on, and start_refusal")
    for sign_in in ({"enabled": False, "method": "oidc"}, _oidc()):
        _refused(tmp_path, sign_in, "public is true and sign_in.method is oidc", public=True)
    refusal = start_refusal(Config(public=True, sign_in={"enabled": False, "method": "oidc"}), tmp_path)
    assert refusal is not None and "Entra ID sign-in is for a team's own console" in refusal.message


# ------------------------------------------------------------------ the credential


def _rsa_pem(tmp_path, *, with_key=True, with_cert=True, other_key=False):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "onetrace test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    signing = rsa.generate_private_key(public_exponent=65537, key_size=2048) if other_key else key
    pem = b""
    if with_cert:
        pem += cert.public_bytes(serialization.Encoding.PEM)
    if with_key:
        pem += signing.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    path = tmp_path / "entra.pem"
    path.write_bytes(pem)
    return path, cert, key


def test_a_certificate_is_read_with_its_thumbprint_and_kept_out_of_its_repr(tmp_path, examined):
    from cryptography.hazmat.primitives import serialization

    examined(3, "the kind, the x5t thumbprint, the repr")
    path, cert, _key = _rsa_pem(tmp_path)
    credential = oidc_settings.load_certificate(str(path))
    der = cert.public_bytes(serialization.Encoding.DER)
    assert credential.kind == "certificate"
    assert credential.x5t == base64.urlsafe_b64encode(hashlib.sha1(der).digest()).rstrip(b"=").decode()
    assert "PRIVATE" not in repr(credential) and "RSAPrivateKey" not in repr(credential)


@pytest.mark.parametrize(
    "shape,says",
    [
        ({"with_key": False}, "holds no private key"),
        ({"with_cert": False}, "holds no certificate"),
        ({"other_key": True}, "is not the certificate's own"),
    ],
    ids=["no-key", "no-cert", "other-key"],
)
def test_a_certificate_file_it_cannot_use_is_refused_by_name(tmp_path, shape, says, examined):
    examined(1, says)
    path, _cert, _key = _rsa_pem(tmp_path, **shape)
    with pytest.raises(oidc_settings.CredentialError) as e:
        oidc_settings.load_certificate(str(path))
    assert says in str(e.value) and str(path) in str(e.value)


def test_a_file_that_is_not_pem_is_refused_without_its_contents(tmp_path, examined):
    examined(1, "a file holding a planted secret between PEM markers")
    path = tmp_path / "entra.pem"
    path.write_text(
        f"-----BEGIN CERTIFICATE-----\n{PLANTED}\n-----END CERTIFICATE-----\n"
        f"-----BEGIN PRIVATE KEY-----\n{PLANTED}\n-----END PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    with pytest.raises(oidc_settings.CredentialError) as e:
        oidc_settings.load_certificate(str(path))
    assert "could not be read as a PEM certificate" in str(e.value) and PLANTED not in str(e.value) + e.value.fix


def test_a_secret_is_read_from_its_variable_and_kept_out_of_its_repr(monkeypatch, examined):
    examined(3, "the secret read, its repr, and the variable unset")
    monkeypatch.setenv("ONETRACE_ENTRA_SECRET", PLANTED)
    credential = oidc_settings.load_secret("ONETRACE_ENTRA_SECRET")
    assert credential.secret == PLANTED and PLANTED not in repr(credential)
    monkeypatch.delenv("ONETRACE_ENTRA_SECRET")
    with pytest.raises(oidc_settings.CredentialError) as e:
        oidc_settings.load_secret("ONETRACE_ENTRA_SECRET")
    assert "ONETRACE_ENTRA_SECRET (sign_in.oidc.client_secret_env) is not set or empty" in str(e.value)


# ------------------------------------------------------------------ at start


def _serve(tmp_path, monkeypatch, body: dict) -> int:
    from onetrace_console import serve
    from onetrace_console.config import ENV_VAR

    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))

    def listened(self):
        raise AssertionError("it served with a credential it cannot use")

    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", listened)
    return serve.main([])


@pytest.mark.parametrize("kind", ["certificate", "secret"])
def test_a_console_whose_credential_cannot_be_read_refuses_to_start_naming_where(
    tmp_path, monkeypatch, capsys, kind, examined
):
    examined(3, f"the {kind}: the exit, the words, nothing drawn")
    monkeypatch.delenv("ONETRACE_ENTRA_SECRET", raising=False)
    root = tmp_path / "data"
    sign_in = (
        _oidc(client_certificate=str(tmp_path / "missing.pem"), client_secret_env="")
        if kind == "certificate"
        else _oidc()
    )
    assert _serve(tmp_path, monkeypatch, {"store_root": root.as_posix(), "host": "127.0.0.1", "sign_in": sign_in}) == 1
    err = capsys.readouterr().err
    said = "cannot read the client certificate at" if kind == "certificate" else "ONETRACE_ENTRA_SECRET"
    assert "refusing to start: " in err and said in err and "\nfix: " in err and "Traceback" not in err, err
    assert not list((root / "pages").rglob("*.html")), "nothing was drawn before the refusal"
