"""The demo store's two signing keys, and its trust file.

Both keys are Ed25519, derived from a PUBLIC seed string written below: the private key is the
sha256 of the seed. Anyone can derive them, so a signature by either proves only that the record
was not changed after it was signed -- never who signed it. The trust file's label says exactly
that, and the console shows the label wherever it names the key.

No key file is kept anywhere: a key is written to a temporary file, readable by its owner only,
for the one signing call that needs it, and removed straight after.

The first key is on the demo's trust file; the second is not, so a run it signs reads "Signed,
key not trusted".
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

TRUSTED_SEED = "onetrace-console demo store, key 1: a public seed, so anyone can sign with it"
UNTRUSTED_SEED = "onetrace-console demo store, key 2: a public seed, not on the trust file"

TRUSTED_LABEL = ("demo key (public seed: proves the record wasn't changed since signing, "
                 "not who signed it)")

TRUST_FORMAT = "onetrace-trust/0.1"


def _private(seed: str):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed.encode("utf-8")).digest())


def key_id(seed: str) -> str:
    """The key id the verifier gives the seed's public key."""
    from cryptography.hazmat.primitives import serialization
    from onetrace_verify.signatures import key_id_of
    raw = _private(seed).public_key().public_bytes(serialization.Encoding.Raw,
                                                    serialization.PublicFormat.Raw)
    return key_id_of(raw)


def trust_file_bytes() -> bytes:
    """The demo's trust file: the first key only, with its label."""
    trust = {"format": TRUST_FORMAT, "keys": [{"key_id": key_id(TRUSTED_SEED),
                                                "label": TRUSTED_LABEL}]}
    return (json.dumps(trust, indent=2) + "\n").encode("utf-8")


def sign(run_dir: Path, seed: str) -> None:
    """Sign the finished run in `run_dir` with the seed's key, by onetrace's own `sign_run`."""
    from cryptography.hazmat.primitives import serialization
    from onetrace.signing import sign_run
    pem = _private(seed).private_bytes(serialization.Encoding.PEM,
                                       serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption())
    with tempfile.TemporaryDirectory(prefix="onetrace-console-demo-key-") as tmp:
        path = Path(tmp) / "key.pem"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
        sign_run(run_dir, path)
