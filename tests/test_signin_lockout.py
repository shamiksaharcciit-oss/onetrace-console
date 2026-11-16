"""Sign-in lock-out a stranger can't hold: known browser, else per (account, address) pair, under an
account ceiling. A right password sets a device cookie; an attempt carrying a valid one for the account
it names counts only in that device's window. Every other attempt counts in its pair's window and in the
account's ceiling. `admin unlock <account>` clears the ceiling; `admin device-key rotate` ends every
device cookie. The page's words name no account's state: a name with no account reads the same.
"""

from __future__ import annotations

import io
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from onetrace_console.__main__ import main as cli_main
from onetrace_console.accounts import AccountStore
from onetrace_console.config import ENV_VAR, Config
from onetrace_console.config import load as load_config
from onetrace_console.serve import ACCOUNTS_DIRNAME, Handler
from onetrace_console.sessions import SessionStore
from tests.http_limits import limit

REPO = Path(__file__).resolve().parent.parent
PASSWORD = "correct horse battery staple"
CEILING_WORDS = (
    "too many sign-in attempts for this account from new browsers; sign in from a browser "
    "you have used before, or ask an admin"
)


class _NoRedirect(urllib.request.HTTPErrorProcessor):
    def http_response(self, request, response):
        return response

    https_response = http_response


_opener = urllib.request.build_opener(_NoRedirect)


def _cookie(headers, name):
    raw = "; ".join(headers.get_all("Set-Cookie") or [])
    m = re.search(rf"{name}=([^;,]+)", raw)
    return m.group(1) if m else None


def _form(base):
    resp = _opener.open(urllib.request.Request(base + "/signin"), timeout=limit(10))
    body = resp.read()
    csrf = _cookie(resp.headers, "onetrace_csrf")
    return csrf, re.search(rb'name="csrf_token" value="([^"]+)"', body).group(1).decode()


def _try(base, username, password, *, address="203.0.113.1", device=None):
    """One sign-in POST from `address` (the X-Forwarded-For a trusted proxy appends), with `device` as
    its device cookie. Returns the status, the body, and the response's headers."""
    csrf, token = _form(base)
    cookie = f"onetrace_csrf={csrf}" + (f"; onetrace_device={device}" if device else "")
    data = f"username={username}&password={password.replace(' ', '+')}&csrf_token={token}".encode()
    req = urllib.request.Request(
        base + "/signin",
        data=data,
        method="POST",
        headers={"Cookie": cookie, "Content-Type": "application/x-www-form-urlencoded", "X-Forwarded-For": address},
    )
    resp = _opener.open(req, timeout=limit(10))
    return resp.status, resp.read(), resp.headers


_SAVED = (
    "config",
    "account_store",
    "session_store",
    "token_store",
    "rate_limit_per_account",
    "rate_limit_per_client",
    "rate_limit_concurrent_hashes",
    "rate_limit_per_pair",
    "rate_limit_per_device",
)


@pytest.fixture
def lockout(server):
    """A sign-in console behind a trusted proxy (so each attempt names its own address), with the
    limiters its configuration's defaults make, the device key made as at first start, and `alice`."""
    from onetrace_console.device_cookie import ensure_key
    from onetrace_console.serve import signin_limiters

    base, store_root = server
    old = {n: getattr(Handler, n, None) for n in _SAVED}
    config = Config(sign_in={**Config().sign_in, "enabled": True, "trusted_proxies": ["127.0.0.1/32"]})
    Handler.config = config
    Handler.account_store = AccountStore(store_root / ACCOUNTS_DIRNAME)
    Handler.account_store.create("alice", PASSWORD.encode())
    Handler.session_store = SessionStore(idle_timeout_seconds=1800, absolute_timeout_seconds=43200)
    Handler.token_store = None
    for name, limiter in signin_limiters(config).items():
        setattr(Handler, name, limiter)
    ensure_key(store_root / ACCOUNTS_DIRNAME)
    #: The windows are what these tests read, not scrypt (its own tests hold it): a password check
    #: that answers at once, so a hundred guesses take seconds, not minutes.
    known = {"alice": PASSWORD.encode()}
    real_create = Handler.account_store.create

    def create(username, password):
        known[username] = password
        return real_create(username, password)

    Handler.account_store.create = create
    Handler.account_store.verify_password = lambda u, p: known.get(u) == p
    try:
        yield base, store_root
    finally:
        for n, v in old.items():
            setattr(Handler, n, v)


def _device_of(base):
    """Alice's right password from a new browser: 303, and the device cookie it sets."""
    status, _body, headers = _try(base, "alice", PASSWORD, address="198.51.100.7")
    assert status == 303
    device = _cookie(headers, "onetrace_device")
    assert device
    return device


def _hundred_strangers(base, username="alice"):
    """100 wrong guesses from 100 addresses: each 401 until the account's ceiling is full (an earlier
    sign-in from a new browser counts in it too), then 429; the ceiling is full at the end."""
    statuses = [_try(base, username, "wrong", address=f"192.0.2.{i + 1}")[0] for i in range(100)]
    first = statuses.index(429) if 429 in statuses else len(statuses)
    assert statuses == [401] * first + [429] * (100 - first)
    assert not Handler.rate_limit_per_account.allows(username)


# ---------------------------------------------------------------- the settings
def test_the_five_settings_and_their_defaults(examined):
    from onetrace_console.config import Config

    s = Config().sign_in
    wanted = {
        "rate_limit_max_attempts_per_device": 5,
        "rate_limit_max_attempts_per_pair": 5,
        "rate_limit_pair_window_seconds": 900,
        "rate_limit_max_attempts_per_account": 100,
        "rate_limit_account_window_seconds": 3600,
    }
    examined(len(wanted), "sign-in limit settings and their defaults")
    assert {k: s.get(k) for k in wanted} == wanted
    #: The per-address limit across accounts, as before.
    assert (s["rate_limit_max_attempts_per_client"], s["rate_limit_window_seconds"]) == (20, 300)


def test_each_setting_may_be_raised_or_lowered(tmp_path, examined):
    path = tmp_path / "c.json"
    path.write_text(
        '{"sign_in": {"rate_limit_max_attempts_per_pair": 3, "rate_limit_account_window_seconds": 7200}}',
        encoding="utf-8",
    )
    config = load_config(path)
    examined(2, "settings read from a file")
    assert config.sign_in["rate_limit_max_attempts_per_pair"] == 3
    assert config.sign_in["rate_limit_account_window_seconds"] == 7200


# ---------------------------------------------------------------- the rule, over HTTP
def test_a_known_browser_signs_in_after_a_hundred_guesses_from_a_hundred_addresses(lockout, examined):
    base, _ = lockout
    device = _device_of(base)
    _hundred_strangers(base)
    examined(101, "attempts: 100 strangers' guesses, then the owner's known browser")
    status, _b, headers = _try(base, "alice", PASSWORD, address="198.51.100.8", device=device)
    assert status == 303
    assert _cookie(headers, "onetrace_session")


def test_without_its_device_cookie_the_owner_gets_429_and_the_page_s_words_until_admin_unlock(
    lockout, tmp_path, monkeypatch, examined
):
    base, store_root = lockout
    _hundred_strangers(base)
    status, body, _h = _try(base, "alice", PASSWORD, address="198.51.100.9")
    examined(102, "attempts: 100 guesses, the owner from a new browser, and again after unlock")
    assert status == 429
    assert CEILING_WORDS in body.decode("utf-8").replace("&#x27;", "'")
    config_path = tmp_path / "unlock.json"
    config_path.write_text(f'{{"store_root": "{store_root.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    assert cli_main(["admin", "unlock", "alice"]) == 0
    status, _b, _h = _try(base, "alice", PASSWORD, address="198.51.100.9")
    assert status == 303


def test_five_wrong_from_one_address_lock_that_pair_only(lockout, examined):
    base, _ = lockout
    statuses = [_try(base, "alice", "wrong", address="192.0.2.50")[0] for _ in range(6)]
    examined(7, "attempts: six from one address, one from another")
    assert statuses == [401] * 5 + [429]
    assert _try(base, "alice", "wrong", address="192.0.2.51")[0] == 401


@pytest.mark.parametrize("spoil", ["bad tag", "another account", "expired", "not a cookie"])
def test_a_device_cookie_that_is_not_valid_for_the_account_counts_as_none(lockout, spoil, examined):
    from onetrace_console import device_cookie

    base, store_root = lockout
    device = _device_of(base)
    key = device_cookie.read_key(store_root / ACCOUNTS_DIRNAME)
    if spoil == "bad tag":
        device = device[:-4] + ("0000" if not device.endswith("0000") else "1111")
    elif spoil == "another account":
        Handler.account_store.create("bob", b"another real password")
        device = device_cookie.make(key, "bob", now=__import__("time").time())
    elif spoil == "expired":
        device = device_cookie.make(key, "alice", now=__import__("time").time() - 91 * 86400)
    else:
        device = "alice"
    _hundred_strangers(base)
    examined(1, f"a sign-in with a device cookie spoilt by: {spoil}")
    assert _try(base, "alice", PASSWORD, address="198.51.100.10", device=device)[0] == 429


def test_five_wrong_with_a_device_cookie_lock_that_device_and_leave_the_ceiling_untouched(lockout, examined):
    base, _ = lockout
    device = _device_of(base)
    statuses = [_try(base, "alice", "wrong", address="198.51.100.11", device=device)[0] for _ in range(6)]
    examined(6, "wrong passwords from a known browser")
    assert statuses == [401] * 5 + [429]
    #: The ceiling holds only the first sign-in, from a new browser.
    assert len(Handler.rate_limit_per_account._attempts.get("alice", ())) == 1
    assert _try(base, "alice", PASSWORD, address="198.51.100.12")[0] == 303


def test_no_limited_attempt_reaches_verify_password(lockout, monkeypatch, examined):
    base, _ = lockout
    calls = []
    real = Handler.account_store.verify_password

    def spy(username, password):
        calls.append(username)
        return real(username, password)

    monkeypatch.setattr(Handler.account_store, "verify_password", spy)
    statuses = [_try(base, "alice", "wrong", address="192.0.2.60")[0] for _ in range(8)]
    examined(8, "attempts from one address, 3 of them limited")
    assert statuses.count(429) == 3
    assert len(calls) == 5


def test_the_device_cookie_s_value_is_in_no_log_line_and_on_no_page(lockout, capfd, examined):
    base, store_root = lockout
    device = _device_of(base)
    status, body, _h = _try(base, "alice", PASSWORD, address="198.51.100.13", device=device)
    page = urllib.request.urlopen(base + "/signin", timeout=limit(10)).read()
    texts = [p.read_bytes() for p in store_root.rglob("*") if p.is_file() and "access" in str(p)]
    out, err = capfd.readouterr()
    examined(len(texts) + 4, "access-log files, two pages, stdout and stderr")
    assert texts
    for blob in texts + [body, page, out.encode(), err.encode()]:
        assert device.encode() not in blob
        assert device.split(".")[1].encode() not in blob


def test_the_device_cookie_is_http_only_strict_secure_and_lasts_90_days(lockout, examined):
    base, _ = lockout
    _s, _b, headers = _try(base, "alice", PASSWORD, address="198.51.100.14")
    line = next(h for h in headers.get_all("Set-Cookie") if h.startswith("onetrace_device="))
    examined(1, "the device cookie's Set-Cookie line")
    for part in ("HttpOnly", "SameSite=Strict", "Secure", f"Max-Age={90 * 86400}"):
        assert part in line


def test_the_device_key_is_made_at_first_start_beside_the_accounts(tmp_path, examined):
    from onetrace_console.device_cookie import KEY_NAME, ensure_key

    accounts = tmp_path / ACCOUNTS_DIRNAME
    ensure_key(accounts)
    first = (accounts / KEY_NAME).read_bytes()
    ensure_key(accounts)
    examined(1, "the device key file")
    assert (accounts / KEY_NAME).read_bytes() == first and len(first) >= 32
    if sys.platform != "win32":
        assert (accounts / KEY_NAME).stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------- the two additions
def test_device_key_rotate_ends_every_device_cookie(lockout, tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.device_cookie import KEY_NAME

    base, store_root = lockout
    device = _device_of(base)
    before = (store_root / ACCOUNTS_DIRNAME / KEY_NAME).read_bytes()
    config_path = tmp_path / "rotate.json"
    config_path.write_text(f'{{"store_root": "{store_root.as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    assert cli_main(["admin", "device-key", "rotate"]) == 0
    assert "device cookie" in capsys.readouterr().out
    assert (store_root / ACCOUNTS_DIRNAME / KEY_NAME).read_bytes() != before
    _hundred_strangers(base)
    examined(1, "a sign-in with a device cookie made under the old key")
    assert _try(base, "alice", PASSWORD, address="198.51.100.15", device=device)[0] == 429


def test_the_ceiling_s_words_and_status_are_the_same_for_a_name_with_no_account(lockout, examined):
    base, _ = lockout
    _hundred_strangers(base, "alice")
    _hundred_strangers(base, "nobody")
    a = _try(base, "alice", "wrong", address="198.51.100.16")
    n = _try(base, "nobody", "wrong", address="198.51.100.16")
    examined(2, "the ceiling's refusal for an account and for a name with none")

    def plain(body):
        return re.sub(rb'value="[^"]+"', b'value=""', body)

    assert a[0] == n[0] == 429
    assert plain(a[1]) == plain(n[1])
    assert a[2].get("Content-Type") == n[2].get("Content-Type")


def test_the_ceiling_s_words_go_only_to_a_request_naming_that_account(lockout, examined):
    base, _ = lockout
    Handler.account_store.create("bob", b"another real password")
    _hundred_strangers(base, "alice")
    status, body, _h = _try(base, "bob", "wrong", address="198.51.100.17")
    examined(1, "another account's sign-in while alice is at her ceiling")
    assert status == 401
    assert b"new browsers" not in body


@pytest.mark.parametrize("word", ["exist", "no account", "no such", "unknown", "locked"])
def test_the_refusals_name_no_account_s_state(word, examined):
    from onetrace_console.serve import SIGNIN_LIMIT_WORDS

    examined(len(SIGNIN_LIMIT_WORDS), f"refusal lines, for the word {word!r}")
    assert all(word not in w for w in SIGNIN_LIMIT_WORDS.values())


# ---------------------------------------------------------------- the policy, by the clock
def _limiters(**over):
    from onetrace_console.serve import signin_limiters

    s = {**Config().sign_in, **over}
    return signin_limiters(Config(sign_in=s))


def test_a_right_password_resets_the_pair_and_the_device_not_the_ceiling(examined):
    from onetrace_console.rate_limit import account_refusal, after_right_password

    lim = _limiters()
    for _ in range(4):
        assert account_refusal("alice", "a", None, lim, now=0) is None
        assert account_refusal("alice", "a", "dev1", lim, now=0) is None
    after_right_password("alice", "a", "dev1", lim)
    examined(3, "windows after a right password: pair, device, ceiling")
    assert len(lim["rate_limit_per_pair"]._attempts.get("alice\na", ())) == 0
    assert len(lim["rate_limit_per_device"]._attempts.get("dev1", ())) == 0
    assert len(lim["rate_limit_per_account"]._attempts["alice"]) == 4


def test_each_window_is_rolling(examined):
    from onetrace_console.rate_limit import account_refusal

    lim = _limiters()
    seen = [account_refusal("alice", "a", None, lim, now=t) for t in (0, 1, 2, 3, 4, 5)]
    assert seen[:5] == [None] * 5 and seen[5] == "pair"
    assert account_refusal("alice", "a", None, lim, now=899) == "pair"
    assert account_refusal("alice", "a", None, lim, now=900) is None
    dev = [account_refusal("alice", "a", "d", lim, now=t) for t in range(6)]
    assert dev[5] == "device" and account_refusal("alice", "a", "d", lim, now=900) is None
    ceil = _limiters(rate_limit_max_attempts_per_account=3)
    got = [account_refusal("alice", f"x{i}", None, ceil, now=i) for i in range(4)]
    examined(4, "windows read across their spans: pair, device, ceiling")
    assert got == [None, None, None, "ceiling"]
    assert account_refusal("alice", "x9", None, ceil, now=3600) is None


def test_sabotage_a_device_attempt_counted_in_the_ceiling_is_caught(monkeypatch, examined):
    """Plant the defect the rule exists against: a known browser's attempt also counted per account."""
    from onetrace_console import rate_limit

    real = rate_limit.account_refusal

    def planted(username, client, device, lim, *, now=None):
        if device is not None:
            lim["rate_limit_per_account"].check_and_record(username, now=now)
        return real(username, client, device, lim, now=now)

    monkeypatch.setattr(rate_limit, "account_refusal", planted)
    lim = _limiters(rate_limit_max_attempts_per_account=2)
    for _ in range(2):
        rate_limit.account_refusal("alice", "a", "dev", lim, now=0)
    examined(1, "a ceiling after a planted defect")
    assert rate_limit.account_refusal("alice", "b", None, lim, now=0) == "ceiling"


# ---------------------------------------------------------------- the commands and the README
def test_admin_unlock_refuses_an_account_that_does_not_exist(tmp_path, monkeypatch, capsys, examined):
    config_path = tmp_path / "c.json"
    config_path.write_text(f'{{"store_root": "{(tmp_path / "s").as_posix()}"}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    examined(1, "admin unlock of a name with no account")
    assert cli_main(["admin", "unlock", "nobody"]) == 1
    assert "no account named 'nobody'" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["unlock"], ["device-key"], ["device-key", "show"]])
def test_admin_unlock_and_device_key_usage(argv, capsys, monkeypatch, examined):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    examined(1, f"admin {' '.join(argv)}")
    assert cli_main(["admin", *argv]) == 2
    err = capsys.readouterr().err
    assert "admin unlock <account>" in err or "admin device-key rotate" in err


def test_the_operator_readme_says_when_to_rotate_the_device_key(examined):
    text = (REPO / "OPERATOR_README.md").read_text(encoding="utf-8")
    examined(1, "OPERATOR_README.md")
    assert "onetrace-console admin device-key rotate" in text
    assert "onetrace-console admin unlock <account>" in text
    at = text.index("onetrace-console admin device-key rotate")
    section = text[max(0, at - 400) : at + 400]
    assert "lost" in section and "leaked" in section and "back up" in text
