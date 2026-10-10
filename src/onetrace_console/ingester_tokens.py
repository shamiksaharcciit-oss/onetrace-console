"""Per-ingester bearer tokens (design note §1 item 11).

A token is a machine credential, never a cookie: random (`secrets`), shown once
at creation and never again, stored only as a hash, checked with
`hmac.compare_digest`, and sent as `Authorization: Bearer <token>`. A token
grants `ingester` and nothing else -- never `viewer` -- the same way a browser
session grants `viewer` and never `ingester` (`roles.py` is where that mutual
exclusion is actually enforced; this module only answers "whose token is this,
if anyone's").

WHY sha256, NOT scrypt, FOR THE TOKEN'S OWN HASH
-------------------------------------------------
`accounts.py` uses scrypt because a human-chosen password is low-entropy and
must be defended against offline guessing. A bearer token here is 256 bits from
`secrets.token_urlsafe` -- guessing it is infeasible regardless of hash speed, so
a slow, memory-hard KDF buys nothing and would only add a real cost to every
ingest request. A plain, fast, salt-free `hashlib.sha256` over the raw token is
the correct tool for a high-entropy secret; the security property this table
needs is "the raw token is never stored," which sha256 gives exactly as well as
scrypt would, at a fraction of the CPU cost.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.store import _atomic_write

#: 256 bits, matching the session id / CSRF token sizing this codebase already uses.
TOKEN_BYTES = 32
_PRINCIPAL_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class TokenError(RuntimeError):
    """A token operation refused: a bad principal name, or an unknown id to revoke."""


@dataclass(frozen=True, slots=True)
class TokenRecord:
    token_id: str
    principal: str
    hash_hex: str
    created_at: str
    revoked: bool

    def to_json(self) -> str:
        return json.dumps(
            {"token_id": self.token_id, "principal": self.principal,
             "hash_hex": self.hash_hex, "created_at": self.created_at,
             "revoked": self.revoked},
            sort_keys=True, indent=1) + "\n"

    @staticmethod
    def from_json(text: str) -> "TokenRecord":
        return TokenRecord(**load_json_bounded(text, "a token record"))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class TokenStore:
    """One record per file, `<root>/<token_id>.json` -- the same shape
    `AccountStore` already uses, and for the same reason: a token is mutated
    (revoked), which a content-addressed name cannot represent.
    """
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, token_id: str) -> Path:
        return self.root / f"{token_id}.json"

    def create(self, principal: str) -> tuple[TokenRecord, str]:
        """Returns `(record, raw_token)`. `raw_token` is returned exactly once --
        the caller (the CLI) must print it and never store it anywhere itself;
        this store persists only its hash.
        """
        if not _PRINCIPAL_RE.match(principal):
            raise TokenError(
                f"{principal!r} is not a usable principal name: lowercase letters, "
                f"digits, '_' or '-', starting with a letter, 2-64 characters.")
        token_id = secrets.token_hex(8)
        raw = secrets.token_urlsafe(TOKEN_BYTES)
        record = TokenRecord(token_id=token_id, principal=principal,
                             hash_hex=_hash_token(raw), created_at=_now_iso(),
                             revoked=False)
        _atomic_write(self._path(token_id), record.to_json().encode("utf-8"))
        return record, raw

    def get(self, token_id: str) -> TokenRecord | None:
        path = self._path(token_id)
        if not path.is_file():
            return None
        return TokenRecord.from_json(path.read_text(encoding="utf-8"))

    def revoke(self, token_id: str) -> bool:
        """`True` if a record existed and is now marked revoked; `False` for an
        unknown id. The record is kept, not deleted -- a revoked token still
        names who it was issued to and when, for whoever reads the store later.
        """
        record = self.get(token_id)
        if record is None:
            return False
        revoked = TokenRecord(token_id=record.token_id, principal=record.principal,
                              hash_hex=record.hash_hex, created_at=record.created_at,
                              revoked=True)
        _atomic_write(self._path(token_id), revoked.to_json().encode("utf-8"))
        return True

    def principal_for(self, raw_token: str) -> str | None:
        """The issuing principal if `raw_token` matches a live (non-revoked)
        record; `None` for no match or a revoked one -- the two are never
        distinguished in the response, so a revoked token cannot be told apart
        from one that never existed.
        """
        want = _hash_token(raw_token)
        for path in sorted(self.root.glob("*.json")):
            record = TokenRecord.from_json(path.read_text(encoding="utf-8"))
            if record.revoked:
                continue
            if hmac.compare_digest(record.hash_hex, want):
                return record.principal
        return None
