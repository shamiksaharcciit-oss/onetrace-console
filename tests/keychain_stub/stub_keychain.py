"""A keychain for tests: a keyring backend that keeps its entries in a folder the test names
(`ONETRACE_TEST_KEYCHAIN`), never the machine's own keychain. A file `locked` in that folder makes every
read and write raise keyring's own `KeyringLocked`, as a locked keychain does.

Named to keyring as `PYTHON_KEYRING_BACKEND=stub_keychain.FolderKeychain`, with this folder on the import
path, so the console in the test and the onetrace-explain command it runs read the same entries.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import keyring.backend
import keyring.errors

ENTRIES = "entries.json"
LOCKED = "locked"


class FolderKeychain(keyring.backend.KeyringBackend):
    priority = 1

    @staticmethod
    def _folder() -> Path:
        return Path(os.environ["ONETRACE_TEST_KEYCHAIN"])

    def _entries(self) -> dict:
        folder = self._folder()
        if (folder / LOCKED).exists():
            raise keyring.errors.KeyringLocked("the test keychain is locked")
        try:
            return json.loads((folder / ENTRIES).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}

    def _write(self, entries: dict) -> None:
        folder = self._folder()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / ENTRIES).write_text(json.dumps(entries), encoding="utf-8")

    def get_password(self, service, username):
        return self._entries().get(service, {}).get(username)

    def set_password(self, service, username, password):
        entries = self._entries()
        entries.setdefault(service, {})[username] = password
        self._write(entries)

    def delete_password(self, service, username):
        entries = self._entries()
        if username not in entries.get(service, {}):
            raise keyring.errors.PasswordDeleteError("no such entry")
        del entries[service][username]
        self._write(entries)
