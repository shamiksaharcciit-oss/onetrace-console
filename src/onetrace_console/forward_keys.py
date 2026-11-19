"""Forwarding's header values in this user's keychain, through `keyring`, where a header says
`key_source = "keyring"` (console 0.9).

The entry: the service `onetrace-console-forwarding`, the user `<destination id>:<header name>`. A value is typed
once into the setup page and written here; after that it is read only to send it, in the header it names, and to say
whether one is stored. No error from here carries it: each is said by its type alone (`explain_keychain`, whose
keychain lookup this shares).
"""

from __future__ import annotations

from onetrace_console.explain_keychain import Unavailable, Unreadable, _keyring

SERVICE = "onetrace-console-forwarding"

__all__ = ["SERVICE", "Unavailable", "Unreadable", "read", "remove", "store", "stored", "user"]


def user(destination_id: str, header: str) -> str:
    return f"{destination_id}:{header.lower()}"


def store(destination_id: str, header: str, value: str) -> None:
    keyring = _keyring()
    try:
        keyring.set_password(SERVICE, user(destination_id, header), value)
    except Exception as e:  # noqa: BLE001 - said by its type, never its text
        raise Unreadable(f"the keychain refused the value ({type(e).__name__})", type(e).__name__) from None


def read(destination_id: str, header: str) -> str | None:
    """The value, to send it; None where none is stored or the keychain can't be read."""
    try:
        keyring = _keyring()
        return keyring.get_password(SERVICE, user(destination_id, header))
    except Exception:  # noqa: BLE001 - nothing to send; the page says why, by `stored`
        return None


def stored(destination_id: str, header: str) -> bool:
    """Whether a value is stored; Unavailable where the keychain can't say."""
    keyring = _keyring()
    try:
        return keyring.get_password(SERVICE, user(destination_id, header)) is not None
    except Exception as e:  # noqa: BLE001 - as above
        raise Unreadable(f"the keychain could not be read ({type(e).__name__})", type(e).__name__) from None


def remove(destination_id: str, header: str) -> bool:
    """Remove the stored value; False where none was stored."""
    keyring = _keyring()
    try:
        keyring.delete_password(SERVICE, user(destination_id, header))
        return True
    except Exception as e:  # noqa: BLE001 - keyring's "not found" is a PasswordDeleteError; anything else, by type
        if type(e).__name__ == "PasswordDeleteError":
            return False
        raise Unreadable(f"the keychain could not be changed ({type(e).__name__})", type(e).__name__) from None
