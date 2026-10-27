"""The demo's onedoor decisions, as onetrace 0.5's worked example makes them: P8's `approve_payment`
is a gated step, and each run cites the decision that allowed what it did.

The example never runs onedoor. Each decision reference is made here, `onedoor-decision-ref/1`, its
digest the one the export's row gives it; the permit is a compact JWS signed with a throwaway Ed25519
key minted for this build and held in memory only (a committed private key would be a key anyone
could use, and a committed time-valid permit would expire). Beside the runs the build writes the
decision export (`decisions.jsonl`, with its `.sha256` sidecar) and the issuer's PUBLIC key
(`permit-issuers.json`), so onetrace-verify can check every run from the files beside it.
"""
from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path

ISSUER = "https://payments-approver.example/issuer"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


class Issuer:
    """One build's issuer: its key, minted here and never written, and the export's rows."""

    def __init__(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        self._key = Ed25519PrivateKey.generate()
        self.public = self._key.public_key().public_bytes(serialization.Encoding.Raw,
                                                          serialization.PublicFormat.Raw).hex()
        self.rows: list[dict] = []

    def decide(self, request_id: str, verdict: str, *, in_export: bool = True) -> dict:
        """A decision reference, its row added to the export (`decision` as onedoor words it)."""
        from onetrace import onedoor_ref
        row = {"request_id": request_id, "action_type": "pay",
               "decision": {"permit": "executed", "deny": "denied", "propose": "proposed"}[verdict]}
        if in_export:
            self.rows.append(row)
        return {"format": "onedoor-decision-ref/1", "request_id": request_id,
                "decision_digest": onedoor_ref.decision_digest(row), "verdict": verdict, "issuer": ISSUER}

    def permit(self, action: dict, seconds: int = 7 * 24 * 3600) -> str:
        """A bound permit for `action`, valid from now for `seconds`, as onedoor's profile shapes it."""
        from onetrace import onedoor_ref
        header = {"alg": "EdDSA", "kid": "payments-key-1", "typ": "aadp-permit+jwt"}
        claims = {"iss": ISSUER, "action_digest": onedoor_ref.action_digest(action),
                  "exp": int(time.time()) + seconds}
        signing_input = _b64url(json.dumps(header).encode()) + "." + _b64url(json.dumps(claims).encode())
        return signing_input + "." + _b64url(self._key.sign(signing_input.encode("ascii")))

    def write_beside(self, runs: Path) -> None:
        """The export, its sidecar and the issuer's public key, beside the run folders. Written as
        bytes, LF on every platform: the sidecar's digest is over the export's bytes, and a file
        written in text mode on Windows would carry CRLF the digest was not taken over."""
        export = "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in self.rows).encode("utf-8")
        (runs / "decisions.jsonl").write_bytes(export)
        (runs / "decisions.jsonl.sha256").write_bytes(
            (hashlib.sha256(export).hexdigest() + "  decisions.jsonl\n").encode("utf-8"))
        (runs / "permit-issuers.json").write_bytes((json.dumps(
            {"format": "onedoor-issuer-trust/1",
             "issuers": [{"issuer": ISSUER, "alg": "ed25519", "public_key": self.public}]}, indent=1) + "\n").encode("utf-8"))
