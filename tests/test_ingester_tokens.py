"""per-ingester bearer tokens -- random, shown once, stored only
as a hash, checked with `hmac.compare_digest`.
"""
from __future__ import annotations

import hmac

import pytest

from onetrace_console.ingester_tokens import TokenError, TokenStore


def test_a_created_token_is_recognised_and_names_its_principal(tmp_path, examined):
    store = TokenStore(tmp_path / "tokens")
    record, raw = store.create("ci-pipeline")
    examined(2, "the raw token, checked and rejected-when-wrong")
    assert store.principal_for(raw) == "ci-pipeline"
    assert store.principal_for(raw + "x") is None


def test_the_raw_token_is_never_stored(tmp_path, examined):
    store = TokenStore(tmp_path / "tokens")
    record, raw = store.create("ci-pipeline")
    on_disk = (tmp_path / "tokens" / f"{record.token_id}.json").read_text(encoding="utf-8")
    examined(1, "the token record's own file, searched for the raw token")
    assert raw not in on_disk


def test_a_revoked_token_no_longer_resolves(tmp_path, examined):
    store = TokenStore(tmp_path / "tokens")
    record, raw = store.create("ci-pipeline")
    assert store.principal_for(raw) == "ci-pipeline"
    examined(2, "the token, before and after revocation")
    assert store.revoke(record.token_id) is True
    assert store.principal_for(raw) is None


def test_revoking_an_unknown_id_is_reported_not_raised(tmp_path, examined):
    store = TokenStore(tmp_path / "tokens")
    examined(1, "a revoke call against an id that was never created")
    assert store.revoke("does-not-exist") is False


def test_a_bad_principal_name_is_refused(tmp_path, examined):
    store = TokenStore(tmp_path / "tokens")
    examined(1, "a principal name with an uppercase letter")
    with pytest.raises(TokenError):
        store.create("Not-A-Valid-Name")


def test_two_tokens_for_the_same_principal_are_independent(tmp_path, examined):
    """Revoking one must not affect the other -- each token is its own record,
    not a single credential per principal.
    """
    store = TokenStore(tmp_path / "tokens")
    record_a, raw_a = store.create("ci-pipeline")
    record_b, raw_b = store.create("ci-pipeline")
    store.revoke(record_a.token_id)
    examined(2, "the revoked and the still-live token for the same principal")
    assert store.principal_for(raw_a) is None
    assert store.principal_for(raw_b) == "ci-pipeline"


def test_token_lookup_goes_through_compare_digest(tmp_path, examined, monkeypatch):
    store = TokenStore(tmp_path / "tokens")
    _record, raw = store.create("ci-pipeline")
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((a, b))
        return real(a, b)

    monkeypatch.setattr("onetrace_console.ingester_tokens.hmac.compare_digest", spy)
    examined(1, "a principal_for lookup observed for a compare_digest call")
    assert store.principal_for(raw) == "ci-pipeline"
    assert len(calls) == 1
