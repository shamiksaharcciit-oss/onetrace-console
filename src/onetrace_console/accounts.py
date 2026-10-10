"""Local accounts: hashed passwords, stored in the console's own store.

Standard library only:
`hashlib.scrypt` (RFC 7914), `hmac.compare_digest`, `secrets` for the salt.

WHY scrypt, AND THESE PARAMETERS
------------------------------------
`docs/design/signin-and-roles.md` (§2c) already grounded this choice: OWASP's Password
Storage Cheat Sheet (https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
recommends Argon2id first, with scrypt as the named fallback "when [Argon2id] is not
available" -- true here, since Argon2id has no standard-library implementation and
no new runtime dependency is allowed. OWASP's own scrypt parameter table lists
several equivalent-security choices trading memory against parallelism; this module uses
`N=2**17 (128 MiB), r=8, p=1`, the first row of that table, matching what the design
note's own citation already named as the option needing the least ongoing tuning
(fixed CPU cost per hash, one thread).

THE COMPARISON MUST GO THROUGH hmac.compare_digest -- CHECKED, NOT JUST WRITTEN
-----------------------------------------------------------------------------------
This replaces the timing-test sabotage the first design draft proposed, because
timing tests are unreliable. `verify_password` calls
`hmac.compare_digest` on the two hash byte strings; `tests/test_accounts.py`'s own test
patches `hmac.compare_digest` at the point this module looks it up and asserts the patch
was actually called, on both a wrong and a right password -- proving the code path is
exercised, not merely present. The sabotage replaces the call with `==` and that test
then fails, which is the whole point: a `==` comparison of two fixed-length byte
strings is not provably constant-time the way `hmac.compare_digest` is documented to be,
and nothing about reading the source proves which one is really running without a test
that would tell the two apart.
"""
from __future__ import annotations

import hashlib
from onetrace_console.bounded_json import load_json_bounded
import hmac
import json
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from onetrace_console.store import _atomic_write

#: OWASP Password Storage Cheat Sheet's first listed scrypt row: "N=2^17 (128 MiB), r=8
#: (1024 bytes), p=1" -- equivalent security to the other rows it lists, trading memory
#: for parallelism; this one needs no tuning for a multi-core host.
SCRYPT_N = 2 ** 17
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 64
SALT_BYTES = 16

#: OWASP's Password Storage Cheat Sheet's own minimum-length
#: recommendation for a user-chosen password (its "Implement Proper Password
#: Strength Controls" section) -- no composition rules (no forced digit/symbol),
#: since length is the recommendation, not a checklist of character classes.
MIN_PASSWORD_LENGTH = 12

_USERNAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")


class AccountError(RuntimeError):
    """An account operation refused: a bad username, a duplicate, or similar."""


@dataclass(frozen=True, slots=True)
class Account:
    username: str
    salt_hex: str
    hash_hex: str
    n: int
    r: int
    p: int
    dklen: int
    created_at: str

    def to_json(self) -> str:
        return json.dumps(
            {"username": self.username, "salt_hex": self.salt_hex, "hash_hex": self.hash_hex,
             "n": self.n, "r": self.r, "p": self.p, "dklen": self.dklen,
             "created_at": self.created_at},
            sort_keys=True, indent=1) + "\n"

    @staticmethod
    def from_json(text: str) -> "Account":
        d = load_json_bounded(text, "an account record")
        return Account(**d)


def _scrypt(password: bytes, salt: bytes, *, n: int, r: int, p: int, dklen: int) -> bytes:
    return hashlib.scrypt(password, salt=salt, n=n, r=r, p=p, maxmem=200 * 1024 * 1024,
                          dklen=dklen)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class AccountStore:
    """One account per file, `<root>/<username>.json` -- the same one-record-per-file
    shape `Store`'s `runs/`, `comparisons/` and `decision_exports/` already use.
    Never content-addressed (an account is mutated -- a password can change -- which a
    content-addressed name cannot represent), so this is its own small store, not part
    of `onetrace_console.store.Store`.
    """
    root: Path

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, username: str) -> Path:
        return self.root / f"{username}.json"

    def exists(self, username: str) -> bool:
        return self._path(username).is_file()

    def create(self, username: str, password: bytes) -> Account:
        if not _USERNAME_RE.match(username):
            raise AccountError(
                f"{username!r} is not a usable username: lowercase letters, digits, "
                f"'_' or '-', starting with a letter, 2-64 characters.")
        if self.exists(username):
            raise AccountError(f"an account named {username!r} already exists")
        #: Counted in CHARACTERS (Unicode code points), after
        #: NFC normalization -- never raw bytes. A password's own encoding (how
        #: many bytes one character happens to take in UTF-8) must not change
        #: whether it passes; NFC first so a character that can be written as
        #: either one precomposed code point or a base character plus a combining
        #: mark counts the same length either way.
        try:
            text = password.decode("utf-8")
        except UnicodeDecodeError as e:
            raise AccountError(f"password is not valid UTF-8: {e}") from None
        normalized = unicodedata.normalize("NFC", text)
        if len(normalized) < MIN_PASSWORD_LENGTH:
            raise AccountError(
                f"password is {len(normalized)} characters (after NFC "
                f"normalization); a minimum of {MIN_PASSWORD_LENGTH} is required "
                f"(OWASP Password Storage Cheat Sheet's own length "
                f"recommendation). No other composition rule is enforced.")
        salt = secrets.token_bytes(SALT_BYTES)
        digest = _scrypt(password, salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
        account = Account(username=username, salt_hex=salt.hex(), hash_hex=digest.hex(),
                          n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN,
                          created_at=_now_iso())
        _atomic_write(self._path(username), account.to_json().encode("utf-8"))
        return account

    def get(self, username: str) -> Account | None:
        path = self._path(username)
        if not path.is_file():
            return None
        return Account.from_json(path.read_text(encoding="utf-8"))

    def verify_password(self, username: str, password: bytes) -> bool:
        """`True` iff the account exists and the password matches. A missing account
        still runs one scrypt computation, against fixed dummy parameters, so that
        "no such user" and "wrong password" cost roughly the same wall-clock time --
        not proven constant-time (scrypt's own cost already dwarfs the difference
        that would leak), but a deliberate choice, not an oversight.
        """
        account = self.get(username)
        if account is None:
            _scrypt(password, b"\x00" * SALT_BYTES, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                   dklen=SCRYPT_DKLEN)
            return False
        computed = _scrypt(password, bytes.fromhex(account.salt_hex),
                           n=account.n, r=account.r, p=account.p, dklen=account.dklen)
        return hmac.compare_digest(computed, bytes.fromhex(account.hash_hex))

    def any_exist(self) -> bool:
        return any(self.root.glob("*.json"))
