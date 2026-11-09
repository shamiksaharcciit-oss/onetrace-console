"""The key for Explain, in this user's keychain, through `keyring` (console 0.7.0).

Under exactly the entry onetrace-explain 0.3 reads where its configuration says `key_source = "keyring"`:
the service `onetrace-explain`, and the user `<provider>:<base_url>`, or `<provider>:default` where the
table names no base_url. The console never imports onetrace_explain (tests/test_explain_keychain.py holds
this naming equal to 0.3's own `KEYRING_SERVICE` and `keyring_user`).

`keyring` is imported only here, only when asked, and is no dependency of the console: it comes with
`onetrace-explain[keyring]`. The key is written, and removed; it is read only to say whether one is
stored, and the value goes no further than that test. No error from here carries it: each is said by
its type alone.
"""
from __future__ import annotations

#: onetrace-explain 0.3's keychain service.
SERVICE = "onetrace-explain"


def user(provider: str, base_url: str = "") -> str:
    """The keychain user a provider's key is stored under, as onetrace-explain 0.3 names it."""
    return f"{provider}:{base_url or 'default'}"


class Unavailable(RuntimeError):
    """The keychain can't be used here; the message says why, never with the key. `kind`: the type of the
    error that stopped it, by name (`KeyringLocked`, `ModuleNotFoundError`, or keyring's `NoKeyringError`
    where it finds no keychain, as onetrace-explain 0.3 meets it then)."""

    def __init__(self, message: str, kind: str = "") -> None:
        super().__init__(message)
        self.kind = kind


class Unreadable(Unavailable):
    """The keychain is there and can't be read (locked, or refused), as against no keyring or no keychain."""


def _keyring():
    """keyring, and the keychain it would use; Unavailable where there is none."""
    try:
        import keyring
        import keyring.errors  # noqa: F401
    except ImportError as e:
        raise Unavailable("keyring is not installed in the Python this console runs from", type(e).__name__) from None
    try:
        backend = keyring.get_keyring()
        from keyring.backends import fail
    except Exception as e:  # noqa: BLE001 - said by its type, never its text
        raise Unavailable(f"keyring could not find a keychain ({type(e).__name__})", type(e).__name__) from None
    if isinstance(backend, fail.Keyring):
        raise Unavailable("keyring finds no keychain that works for this user here", "NoKeyringError")
    return keyring


def store(provider: str, base_url: str, key: str) -> None:
    """Keep `key` in the keychain for the provider; Unavailable where it can't be."""
    keyring = _keyring()
    try:
        keyring.set_password(SERVICE, user(provider, base_url), key)
    except Exception as e:  # noqa: BLE001 - said by its type, never its text
        raise Unavailable(f"the keychain did not keep the key ({type(e).__name__})") from None


def stored(provider: str, base_url: str) -> bool:
    """Whether a key is stored for the provider: the entry is read, and only its presence leaves here.
    Unreadable where the keychain is there and can't be read (locked, or refused), said by the error's
    type; Unavailable where there is no keyring or no keychain."""
    keyring = _keyring()
    try:
        return bool(keyring.get_password(SERVICE, user(provider, base_url)))
    except Exception as e:  # noqa: BLE001 - said by its type, never its text
        raise Unreadable(f"the keychain could not be read ({type(e).__name__})", type(e).__name__) from None


def remove(provider: str, base_url: str) -> None:
    """Take the provider's key out of the keychain; nothing where none is stored."""
    keyring = _keyring()
    import keyring.errors
    try:
        keyring.delete_password(SERVICE, user(provider, base_url))
    except keyring.errors.PasswordDeleteError:
        return
    except Exception as e:  # noqa: BLE001 - said by its type, never its text
        raise Unavailable(f"the keychain did not remove the key ({type(e).__name__})") from None
