"""Local accounts, scrypt, hmac.compare_digest."""
from __future__ import annotations

import hmac

import pytest

from onetrace_console.accounts import MIN_PASSWORD_LENGTH, AccountError, AccountStore


def test_a_created_account_verifies_its_own_password_and_rejects_others(tmp_path, examined):
    store = AccountStore(tmp_path / "accounts")
    store.create("alice", b"correct horse battery staple")
    examined(2, "password checks: the right one and a wrong one")
    assert store.verify_password("alice", b"correct horse battery staple") is True
    assert store.verify_password("alice", b"wrong password") is False


def test_an_unknown_username_is_refused_not_an_exception(tmp_path, examined):
    store = AccountStore(tmp_path / "accounts")
    examined(1, "password checks against a username that does not exist")
    assert store.verify_password("nobody", b"anything") is False


def test_a_duplicate_username_is_refused(tmp_path, examined):
    store = AccountStore(tmp_path / "accounts")
    store.create("alice", b"first-password")
    examined(1, "attempts to create a second account with the same name")
    with pytest.raises(AccountError, match="already exists"):
        store.create("alice", b"second-password")


def test_stored_parameters_match_the_owasp_scrypt_recommendation(tmp_path, examined):
    store = AccountStore(tmp_path / "accounts")
    account = store.create("alice", b"a password12")
    examined(1, "an account's own stored scrypt parameters")
    assert (account.n, account.r, account.p) == (2 ** 17, 8, 1)


def test_the_salt_is_random_per_account(tmp_path, examined):
    store = AccountStore(tmp_path / "accounts")
    a = store.create("alice", b"same password")
    b = store.create("bob", b"same password")
    examined(2, "accounts created with the identical password")
    assert a.salt_hex != b.salt_hex
    assert a.hash_hex != b.hash_hex


def test_password_check_goes_through_compare_digest(tmp_path, examined, monkeypatch):
    """Patch hmac.compare_digest, observe it is called
    on both a wrong and a right password.
    """
    store = AccountStore(tmp_path / "accounts")
    store.create("alice", b"correct horse battery staple")
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr("onetrace_console.accounts.hmac.compare_digest", spy)
    examined(2, "password checks observed for a compare_digest call")
    assert store.verify_password("alice", b"correct horse battery staple") is True
    assert store.verify_password("alice", b"wrong") is False
    assert len(calls) == 2


def test_a_password_shorter_than_the_minimum_is_refused(tmp_path, examined):
    """`admin create` refuses a password shorter than 12 characters."""
    store = AccountStore(tmp_path / "accounts")
    examined(2, "a too-short password and one exactly at the minimum")
    with pytest.raises(AccountError, match="12"):
        store.create("alice", b"short11char")
    assert len(b"short11char") == MIN_PASSWORD_LENGTH - 1
    store.create("bob", b"exactly12chr")
    assert len(b"exactly12chr") == MIN_PASSWORD_LENGTH
    assert store.verify_password("bob", b"exactly12chr") is True


def test_password_length_is_characters_after_nfc_not_bytes(tmp_path, examined):
    """Counted in Unicode code points, after NFC
    normalization -- never raw bytes, and never raw (pre-normalization) code
    points either. `"e" + COMBINING ACUTE ACCENT` (U+0065 U+0301) is two code
    points and three UTF-8 bytes on its own, but normalizes to one code point,
    `"e"` (U+00E9) -- so 11 repetitions is 22 raw code points and 33 bytes
    (either raw measure would wrongly accept it), but exactly 11 characters
    after NFC, which must still be refused; 12 repetitions must be accepted.
    """
    e_acute_decomposed = "é"
    eleven = (e_acute_decomposed * 11).encode("utf-8")
    twelve = (e_acute_decomposed * 12).encode("utf-8")
    assert len(eleven) == 33 and len(twelve) == 36          # raw bytes: both way over 12
    assert len(eleven.decode("utf-8")) == 22                # raw code points: also both over 12
    store = AccountStore(tmp_path / "accounts")
    examined(2, "11 and 12 repetitions of a decomposed accented character")
    with pytest.raises(AccountError, match="11 characters"):
        store.create("alice", eleven)
    store.create("bob", twelve)
    assert store.verify_password("bob", twelve) is True


def test_an_unknown_username_still_computes_a_dummy_hash_with_the_same_parameters(
        tmp_path, examined, monkeypatch):
    """An unknown username takes the same path as a known one --
    patch the scrypt wrapper and observe it is called once for a real account and
    once for a name that does not exist, with identical scrypt parameters both
    times, so wall-clock time cannot distinguish the two cases.
    """
    import onetrace_console.accounts as accounts_module

    store = AccountStore(tmp_path / "accounts")
    store.create("alice", b"correct horse battery staple")
    calls = []
    real = accounts_module._scrypt

    def spy(password, salt, *, n, r, p, dklen):
        calls.append((n, r, p, dklen))
        return real(password, salt, n=n, r=r, p=p, dklen=dklen)

    monkeypatch.setattr("onetrace_console.accounts._scrypt", spy)
    examined(2, "verify_password against a known and an unknown username")
    assert store.verify_password("alice", b"correct horse battery staple") is True
    assert store.verify_password("nobody-at-all", b"anything") is False
    assert len(calls) == 2
    assert calls[0] == calls[1], "the known and unknown paths used different scrypt parameters"


def test_sabotage_replacing_compare_digest_with_equality_fails_the_spy_test(tmp_path, examined):
    """The sabotage named in the specification: `==` instead of `hmac.compare_digest`. Run
    for real -- never against the real source -- on a copy of `accounts.py` with the
    one line changed, imported fresh under its own module name, then the identical
    spy assertion from the test above is run against the copy and must fail (its own
    call count is 0, not 2).
    """
    import importlib.util
    import inspect
    import sys

    import onetrace_console.accounts as real_accounts

    source = inspect.getsource(real_accounts)
    needle = "return hmac.compare_digest(computed, bytes.fromhex(account.hash_hex))"
    assert needle in source, "the line this sabotage targets has moved or been reworded"
    sabotaged_source = source.replace(
        needle, "return computed == bytes.fromhex(account.hash_hex)  # sabotage", 1)

    sabotaged_path = tmp_path / "accounts_sabotaged.py"
    sabotaged_path.write_text(sabotaged_source, encoding="utf-8")

    module_name = "accounts_sabotaged_for_test"
    spec = importlib.util.spec_from_file_location(module_name, sabotaged_path)
    sabotaged = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = sabotaged
    try:
        spec.loader.exec_module(sabotaged)

        store = sabotaged.AccountStore(tmp_path / "accounts")
        store.create("alice", b"correct horse battery staple")

        #: unittest.mock.patch guarantees restoration of the real, shared hmac module
        #: even on error -- never a hand-rolled assignment to a module every other
        #: test in this process also imports.
        from unittest.mock import patch

        def boom(a, b):
            raise AssertionError("hmac.compare_digest was called -- the sabotage did not take")

        examined(1, "a copy of accounts.py with compare_digest replaced by ==")
        with patch("hmac.compare_digest", side_effect=boom):
            #: The sabotaged source no longer calls compare_digest at all, so `boom`
            #: never fires and both checks still return their correct answer --
            #: which is itself the proof: the real code path is gone.
            assert store.verify_password("alice", b"correct horse battery staple") is True
            assert store.verify_password("alice", b"wrong") is False
    finally:
        del sys.modules[module_name]
