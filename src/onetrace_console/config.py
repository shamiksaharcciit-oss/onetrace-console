"""One read-only configuration file, its path in `ONETRACE_CONSOLE_CONFIG`.

Every setting of the console is a key of that file, mounted read-only, with its keys documented.
The other environment variables the console reads are each for one thing, and the operator guide
names them all ("Configuration"): Entra ID's client secret, by the name the file gives; the proxy
for Entra ID's addresses; onetrace-explain's configuration; a pinned install's report; the hosted
apps' addresses; and a recorded run's trace context. Before this,
`ONETRACE_CONSOLE_HOST`, `ONETRACE_CONSOLE_PORT` and `ONETRACE_CONSOLE_STORE` were three
separate environment variables; all three are gone, folded into the keys below.

WHY A MISSING FILE IS A DEFAULT, NOT A REFUSAL
------------------------------------------------
`ONETRACE_CONSOLE_CONFIG` unset means "use the built-in defaults" -- which is what every
test in this suite does, and what a first `docker run` with no `-v` mount does. A refusal
here would make every test that starts a server carry its own throwaway config file for no
reason a default cannot serve just as well. What is NOT tolerated is the variable being SET
to a path that does not exist, or a file that does not parse: those refuse, loudly, because
an operator who named a file and got silent defaults instead would not know their
configuration was never read.

The configuration's own exception: with `sign_in.method` `oidc` and a client secret rather than a
certificate, the file names the environment variable that holds the secret
(`sign_in.oidc.client_secret_env`), so the secret itself is never in the file.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path, PurePath

from onetrace_console.bounded_json import TooDeep, load_json_bounded

#: The one environment variable.
ENV_VAR = "ONETRACE_CONSOLE_CONFIG"

#: Extensions this console knows how to switch on. "onedoor" is the first; an unknown
#: name in the "extensions" object is refused the same way an unknown top-level key is --
#: a typo here (e.g. "onedor") must not be silently read as "off".
_KNOWN_EXTENSIONS = frozenset({"onedoor"})

#: Step 1 added only "enabled"; step 2 adds TLS, session and
#: rate-limit keys together with the code that reads them, not ahead of it. Each
#: key's default AND its expected type live in one place, `_SIGN_IN_SCHEMA`, so a new
#: key can't be added to one without the other.
_SIGN_IN_SCHEMA: dict[str, tuple[type, object]] = {
    #: On by default: a file that leaves `sign_in` out gets sign-in. Only
    #: local mode -- no file named at all -- forces it off (`serve._local_config`).
    "enabled": (bool, True),
    #: Empty string means "not configured". Both must be set together, or neither --
    #: checked in `_validate_sign_in`, not left as "one present, one silently ignored".
    "tls_cert_path": (str, ""),
    "tls_key_path": (str, ""),
    #: Session rules. Defaults: 30 minutes idle, 12 hours absolute.
    "session_idle_timeout_seconds": (int, 1800),
    "session_absolute_timeout_seconds": (int, 43200),
    #: An account's live sessions at most; a sign-in beyond it ends that account's oldest.
    "max_sessions_per_account": (int, 3),
    #: Rate limiting, each a rolling window (`rate_limit.account_refusal`). Per client address,
    #: across accounts: at most `rate_limit_max_attempts_per_client` in any span of
    #: `rate_limit_window_seconds`. For an account, an attempt from a browser holding a valid device
    #: cookie for it counts only in that device's window; any other counts in its (account, address)
    #: pair's window and in the account's ceiling, over all addresses. The device's and the pair's
    #: span is `rate_limit_pair_window_seconds`; the ceiling's, `rate_limit_account_window_seconds`.
    "rate_limit_max_attempts_per_client": (int, 20),
    "rate_limit_window_seconds": (int, 300),
    "rate_limit_max_attempts_per_device": (int, 5),
    "rate_limit_max_attempts_per_pair": (int, 5),
    "rate_limit_pair_window_seconds": (int, 900),
    "rate_limit_max_attempts_per_account": (int, 100),
    "rate_limit_account_window_seconds": (int, 3600),
    #: A global cap on how many scrypt computations may run at once,
    #: independent of which account or client is asking -- a burst spread across
    #: many identities could still exhaust memory even with both limits above.
    "rate_limit_max_concurrent_hashes": (int, 2),
    #: Cookies are `Secure` whenever sign-in is on, full stop --
    #: this is the ONLY way to get a non-`Secure` cookie, and it is refused
    #: outright on a non-loopback listener (see `signin.refuse_if_insecure`), so it
    #: can never be used to make a real, network-reachable install serve session
    #: cookies in clear text.
    "insecure_cookie_for_local_dev": (bool, False),
    #: The origin a browser reaches this console at, as `https://host[:port]`, where that is not
    #: the request's own scheme and Host (behind a TLS-terminating proxy). Empty: the request's
    #: own. A session's state-changing request from any other origin is refused (`serve`).
    "public_url": (str, ""),
    #: The proxies in front of this console, as addresses and CIDR ranges. Only where the
    #: connection's peer is one, the sign-in limit's client address is the rightmost
    #: X-Forwarded-For entry that is not one (`rate_limit.client_address`). Empty: the peer's.
    "trusted_proxies": (list, []),
    #: How people sign in, one method at a time: `local`, the console's own accounts, or `oidc`,
    #: Microsoft Entra ID (`sign_in.oidc`). With `oidc`, local sign-in is off; `onetrace-console admin`
    #: on the machine stays the way back, as the console never writes its configuration.
    "method": (str, "local"),
    #: Entra ID's settings, read where `method` is `oidc` (`_validate_oidc`).
    "oidc": (dict, {}),
}
_KNOWN_SIGN_IN_KEYS = frozenset(_SIGN_IN_SCHEMA)
SIGN_IN_METHODS = ("local", "oidc")

#: `sign_in.oidc`'s keys and defaults. The client credential is a certificate file (private_key_jwt,
#: preferred) or the NAME of an environment variable that holds a secret: never the secret itself.
_OIDC_SCHEMA: dict[str, tuple[type, object]] = {
    #: The directory (tenant) id, a GUID: the issuer is derived from it, never `common` or `organizations`.
    "tenant_id": (str, ""),
    #: The app registration's application (client) id, a GUID.
    "client_id": (str, ""),
    #: A PEM file holding the registration's certificate and its private key.
    "client_certificate": (str, ""),
    #: The name of the environment variable that holds the client secret.
    "client_secret_env": (str, ""),
    #: A session lasts until the ID token expires or this many hours, whichever comes first.
    "session_max_hours": (int, 8),
}
_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: Entra's multi-tenant endpoints: an issuer derived from one of them would take any organisation's people.
_SHARED_TENANTS = ("common", "organizations", "consumers")
ENTRA_AUTHORITY = "https://login.microsoftonline.com"
OIDC_CALLBACK_PATH = "/signin/oidc/callback"


def _sign_in_defaults() -> dict:
    """Every sign_in key's default; a list or object default is a fresh copy each time."""
    return {
        k: (list(d) if isinstance(d, list) else _oidc_defaults() if isinstance(d, dict) else d)
        for k, (_t, d) in _SIGN_IN_SCHEMA.items()
    }


def _oidc_defaults() -> dict:
    return {k: d for k, (_t, d) in _OIDC_SCHEMA.items()}


def oidc_issuer(tenant_id: str) -> str:
    """The issuer, derived from the tenant id alone: Entra ID's v2.0 issuer for that one tenant."""
    return f"{ENTRA_AUTHORITY}/{tenant_id}/v2.0"


def oidc_redirect_uri(public_url: str) -> str:
    """The redirect URI, derived from `sign_in.public_url` (an origin) and the callback's path."""
    origin = origin_of(public_url)
    if origin is None:
        raise ValueError("sign_in.public_url is not an origin")
    return origin + OIDC_CALLBACK_PATH


def _validate_oidc(value: object, *, source: str) -> dict:
    """`sign_in.oidc`, checked. No message here quotes a value: a secret pasted into the wrong key
    must not reach an error, a log or a page. Shapes are described instead."""
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: sign_in.oidc must be a JSON object, got {type(value).__name__}")
    unknown = sorted(set(value) - set(_OIDC_SCHEMA))
    if unknown:
        if any(re.search(r"secret|password|private|key|credential", k, re.I) for k in unknown):
            raise ConfigError(
                f"{source}: sign_in.oidc holds {unknown}. The client credential is never written in the "
                f"configuration file.",
                fix=f"remove {unknown} from {source}; name a PEM file holding the certificate and its private "
                f"key in sign_in.oidc.client_certificate, or the environment variable that holds the secret "
                f"in sign_in.oidc.client_secret_env.",
            )
        raise ConfigError(f"{source}: unknown sign_in.oidc key(s) {unknown}. Known keys: {sorted(_OIDC_SCHEMA)}.")
    for key, v in value.items():
        expected, _default = _OIDC_SCHEMA[key]
        if expected is int:
            if isinstance(v, bool) or not isinstance(v, int):
                raise ConfigError(f"{source}: sign_in.oidc.{key} must be an integer")
            continue
        if not isinstance(v, str):
            raise ConfigError(f"{source}: sign_in.oidc.{key} must be a string")
        if not _text(v) or _control(v):
            raise ConfigError(
                f"{source}: sign_in.oidc.{key} holds a control character or a lone surrogate escape",
                fix=f"write sign_in.oidc.{key} in {source} as plain text.",
            )
    for key, what in (("tenant_id", "the directory (tenant) id"), ("client_id", "the application (client) id")):
        v = value.get(key, "")
        if key == "tenant_id" and v.strip().lower() in _SHARED_TENANTS:
            raise ConfigError(
                f"{source}: sign_in.oidc.tenant_id is {v.strip().lower()!r}, which lets any organisation's "
                f"people sign in. The issuer is derived from one tenant's id.",
                fix=f"set sign_in.oidc.tenant_id in {source} to your directory (tenant) id, a GUID shown on "
                f"the app registration's Overview.",
            )
        if v and not _GUID.match(v):
            raise ConfigError(
                f"{source}: sign_in.oidc.{key} must be {what}, a GUID such as "
                f"00000000-0000-0000-0000-000000000000; the value given is not one.",
                fix=f"copy {what} from the app registration's Overview into sign_in.oidc.{key} in {source}.",
            )
    env = value.get("client_secret_env", "")
    if env and not _ENV_NAME.match(env):
        raise ConfigError(
            f"{source}: sign_in.oidc.client_secret_env must be the NAME of an environment variable "
            f"(letters, digits and _, not starting with a digit); the value given is not a name.",
            fix=f"set sign_in.oidc.client_secret_env in {source} to the variable's name, such as "
            f"ONETRACE_ENTRA_SECRET, and put the secret in that variable, never in the file.",
        )
    if value.get("session_max_hours", 8) < 1:
        raise ConfigError(
            f"{source}: sign_in.oidc.session_max_hours must be at least 1",
            fix=f"set sign_in.oidc.session_max_hours in {source} to 1 or more, or leave it out (8).",
        )
    merged = _oidc_defaults()
    merged.update(value)
    return merged


def _check_oidc_method(value: dict, *, source: str) -> None:
    """With `method` `oidc`: sign-in on, the console's public URL set (the redirect URI is derived
    from it), both ids, and exactly one client credential."""
    oidc = value["oidc"]
    if not value["enabled"]:
        raise ConfigError(
            f"{source}: sign_in.method is oidc and sign_in.enabled is false.",
            fix=f"set sign_in.enabled to true in {source}, or sign_in.method to local.",
        )
    if not value["public_url"]:
        raise ConfigError(
            f"{source}: sign_in.method is oidc and sign_in.public_url is empty. The redirect URI is derived "
            f"from it: <public_url>{OIDC_CALLBACK_PATH}.",
            fix=f"set sign_in.public_url in {source} to the origin your browser opens this console at, such "
            f"as https://onetrace.example.org, and register <public_url>{OIDC_CALLBACK_PATH} as the app's "
            f"redirect URI.",
        )
    missing = [k for k in ("tenant_id", "client_id") if not oidc[k]]
    if missing:
        raise ConfigError(
            f"{source}: sign_in.method is oidc and sign_in.oidc has no {' and no '.join(missing)}.",
            fix=f"copy the directory (tenant) id and the application (client) id from the app "
            f"registration's Overview into sign_in.oidc in {source}.",
        )
    given = [k for k in ("client_certificate", "client_secret_env") if oidc[k]]
    if len(given) != 1:
        said = "both" if given else "neither"
        raise ConfigError(
            f"{source}: sign_in.oidc names {said} of client_certificate and client_secret_env; exactly one "
            f"client credential is used.",
            fix=f"in {source}, name the certificate file in sign_in.oidc.client_certificate (preferred), or "
            f"the environment variable holding the secret in sign_in.oidc.client_secret_env, not both.",
        )


class ConfigError(RuntimeError):
    """The named config file could not be read as this console's configuration.

    `fix` is the one line an operator acts on: every entry point that
    reads the file prints the message and then `fix: ...`, never a traceback.
    """

    def __init__(self, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.fix = fix or (
            f"correct the file (OPERATOR_README.md lists every key, its type and "
            f"its default), or unset {ENV_VAR} to run in local mode."
        )


@dataclass(frozen=True, slots=True)
class Config:
    """Every key this file may set, and what it means. Documented here because this
    dataclass's fields ARE the schema -- an unknown key in the file is refused (below)
    rather than silently ignored, so a typo in an operator's config is never a silent
    no-op.
    """

    #: Network. `host` stays `127.0.0.1` in every example this repository ships --
    #: OPERATOR_README.md is explicit that publishing further is the operator's own choice,
    #: made at `docker run -p`, never assumed here.
    host: str = "127.0.0.1"
    port: int = 8080

    #: Where the store and rendered pages live -- one path, the parent of both `store/`
    #: and `pages/` (see `serve.py`).
    store_root: str = "./store"

    #: Upload hardening. Every limit here is checked BEFORE the
    #: bytes it bounds are read into memory, not after -- see `ingest.py` and `serve.py`.
    #:
    #: 64 MiB is generous for a stage-receipt run (the largest real bench fixture this
    #: console's own tests use is under 40 KB) while still bounding memory use to
    #: something a small container comfortably holds.
    max_request_body: int = 64 * 1024 * 1024
    #: A run with a manifest, a handful of receipts and at most one verb report beside
    #: them. 512 is far more than any real run needs and far less than an archive
    #: bomb's usual member count.
    max_members: int = 512
    #: Per member, and in total across the whole archive -- the second guards
    #: specifically against a small, highly-compressed upload that expands enormously
    #: once every member's declared size is summed (an archive bomb), which a single
    #: per-member cap alone would not catch.
    max_member_size: int = 16 * 1024 * 1024
    max_total_extracted_size: int = 64 * 1024 * 1024

    #: Wall-clock, for reading one request's body. Chosen generously for a slow but real
    #: client (a large upload over a poor connection) while still bounding how long a
    #: stalled or trickling connection can hold a server thread.
    request_timeout_seconds: float = 30.0

    #: Off by default: the extension is separable from the console. A name not in
    #: `_KNOWN_EXTENSIONS`, or a value that isn't a plain true/false, is refused rather
    #: than ignored -- see `_validate_extensions`.
    extensions: dict = field(default_factory=lambda: {"onedoor": False})

    #: JSONL-specific limits for the onedoor decision-export route,
    #: alongside the shared upload-hardening limits above. A fixture export (4 rows,
    #: longest line under 2 KB) is nowhere near either.
    max_decision_rows: int = 100_000
    max_decision_line_length: int = 262_144

    #: Step 1: the access log's per-segment size bound,
    #: before it rotates to a new chained segment (`access_log.py`). 5 MiB holds tens
    #: of thousands of page-view entries (each well under 300 bytes) before rotating.
    access_log_max_segment_bytes: int = 5 * 1024 * 1024

    #: Off by default -- step 1 added the key and the access log; step 2 adds
    #: local accounts, TLS, sessions and CSRF, still off by default; no request is
    #: refused for lacking a principal until step 3 flips this default and role
    #: enforcement lands. A name not in `_KNOWN_SIGN_IN_KEYS`, or a wrongly-typed
    #: value, is refused the same way an unknown `extensions` name is -- see
    #: `_SIGN_IN_SCHEMA` for every key, its type and its default.
    sign_in: dict = field(default_factory=lambda: _sign_in_defaults())
    #: The signing keys this console's operator trusts, a path to an
    #: `onetrace-trust/0.1` file, or absent (the default). Set, every check runs the verifier with
    #: `--trust <that file>`; absent, without it, and a valid signature then reads "Signed, key not
    #: trusted", never Yes. The console never makes, edits or guesses a trust file: a file the
    #: verifier can't read is its own `--trust` FAIL row, shown as it is.
    trust_file: str | None = None
    #: The recipients this console's operator trusts to confirm an action, a path to an
    #: `onetrace-recipient-trust/1` file, or absent (the default). Set, every check runs the verifier with
    #: `--recipients <that file>`, so a recipient's confirmation's key row reads as the verifier reads it; absent, that
    #: row reads NOT-RUN, with format.md's words on a match with an unauthenticated statement. Like the trust file, a
    #: statement of whom to trust: the console never makes, edits or guesses one.
    recipients_file: str | None = None
    #: The RFC 3161 time-stamp authority this console's operator trusts: its certificate, and the
    #: root (or roots) it chains to, paths to PEM or DER files, or absent (the default). Set, every
    #: check runs the verifier with `--tsa-cert <file>` and a `--tsa-root <file>` for each root, so
    #: a run's RFC 3161 anchor can read Yes; absent, such an anchor reads "Couldn't check".
    tsa_cert: str | None = None
    tsa_roots: list[str] = field(default_factory=list)

    #: The read-only public mode, for a demo anyone may open: every write refused before its
    #: body is read, the pages served as they were built and never drawn again, and a banner on
    #: every page (`public.py`). Off unless set, and only by a plain true or false -- one
    #: explicit switch, never a default.
    public: bool = False

    #: A public console's Compare (`visitor_compare`): the folder its comparisons are kept in, where
    #: not `<store root>/compared`; and the request header that names the client's address, where a
    #: proxy in front of the console sets one (on Fly.io, `Fly-Client-IP`). Null: the folder under
    #: the store root, and the connection's own address.
    compare_cache: str | None = None
    compare_client_header: str | None = None
    #: Compare's bounds on a public console (`visitor_compare`), each at most its shipped number so an
    #: operator can lower it and every page's "at most" stays true: new comparisons started a minute
    #: for the whole console, running at once, waiting per address, the wait, and each verb's time.
    compare_per_minute: int = 20
    compare_running: int = 2
    compare_queue: int = 2
    compare_wait_seconds: float = 20.0
    compare_verb_seconds: int = 30

    #: A local console's link to the person's own tracing tool: {"link": "<http(s) address with
    #: {trace_id} and, optionally, {span_id}>"}. Each recorded trace id becomes "Open in your
    #: tracing tool"; the console builds the link and never calls it. A public console shows no
    #: link. Empty: no link.
    tracing: dict = field(default_factory=dict)
    #: A local console's tokenizers, each a folder the person names and the files in it that make the
    #: tokenizer: [{"folder": "<path>", "files": ["tokenizer.json", ...]}]. A model step's token ids are
    #: decoded only where the named files, hashed as named, give the record's `tokenizer.digest`
    #: exactly (`token_text`). The console never downloads one. A public console reads none. Empty: none.
    tokenizers: list = field(default_factory=list)
    #: The close-call flag's margin on a model step's page (`token_levels.close_calls`), in nats: a position whose
    #: chosen token leads the runner-up by at most this much is a close call. Above zero.
    close_call_margin: float = 1.0
    #: Teams: each team's name, and how people are joined to it, {"<team>": {"role_claim":
    #: "<an app role's value>", "scim_group": "<an Entra ID group's object id>"}}. With teams, the pages are drawn
    #: once per team (`pages/t/<team>/`) beside the all-teams set, and each person is served their team's. Without
    #: SCIM, a person is in a team while the ID token's app roles hold its `role_claim`. Empty: no teams.
    teams: dict = field(default_factory=dict)
    #: A folder console's team: with teams, `onetrace-console <runs folder>` started with a
    #: configuration file takes every run it reads into this team, and refuses to start without it. A key of its own
    #: beside `teams`, so it takes no team's name. None: no folder team.
    folder_team: str | None = None
    #: The audit log: `enabled`, off by default; `head_location`, the file on a second mounted
    #: volume each append's head is also written to, required while it is on and refused on the store's volume (at
    #: start); `max_segment_bytes`, where a segment is closed and the next begun.
    audit: dict = field(default_factory=lambda: dict(AUDIT_DEFAULTS))
    #: SCIM 2.0 provisioning from Entra ID: `enabled`, off by default; `tenant_id`, the tenant
    #: SCIM's Users sign in from, `sign_in.oidc.tenant_id`'s where left empty; `required_for_sign_in`;
    #: `token_max_days`, the longest a SCIM token may be made for (at most 365); `allowed_sources`, address ranges
    #: that may reach `/scim/v2/*`, any where empty; `max_body_bytes`; `max_results`, a list's largest page.
    scim: dict = field(default_factory=lambda: _scim_defaults())


def _scim_defaults() -> dict:
    from onetrace_console.scim import DEFAULTS

    return {**DEFAULTS, "allowed_sources": list(DEFAULTS["allowed_sources"])}


#: The audit log's keys and their defaults.
AUDIT_DEFAULTS: dict = {"enabled": False, "head_location": None, "max_segment_bytes": 1024 * 1024}

_KEYS = {f.name for f in fields(Config)}
#: What a team's entry may hold.
_TEAM_KEYS = frozenset({"role_claim", "scim_group"})


#: What a team's name may be, said once for every key that names a team.
TEAM_NAME_SAID = "a lower-case letter, then up to 62 lower-case letters, digits or hyphens"


def refuse_team_name(name: object, key: str, *, source: str, fix: str) -> None:
    """Refuses, naming `key`, a team's name outside the store's rule (`store.TEAM_NAME`): a team so named would be
    taken at start, and every run it took in would then refuse to read."""
    from onetrace_console.store import TEAM_NAME

    if not isinstance(name, str) or not TEAM_NAME.match(name):
        raise ConfigError(
            f"{source}: {key} is {name!r}, not a team's name: {TEAM_NAME_SAID}",
            fix=f"{fix} so that it is {TEAM_NAME_SAID}, such as payments or search-eu.",
        )


def _validate_folder_team(value: object, teams: dict, *, source: str) -> str | None:
    """`folder_team`: a team's name, one `teams` holds."""
    if value is None:
        return None
    refuse_team_name(value, "folder_team", source=source, fix=f"set folder_team in {source}")
    if value not in teams:
        raise ConfigError(
            f"{source}: folder_team is {value!r}, a team teams does not hold"
            + (f" (it holds {', '.join(teams)})" if teams else " (it holds none)"),
            fix=f"set folder_team in {source} to one of the teams in teams, or add {value!r} to teams.",
        )
    return str(value)


def _validate_teams(value: object, *, public: bool, source: str) -> dict:
    """`teams`: an object of team names, each an object with `role_claim` and `scim_group`, both text, both optional."""
    fix = f'give teams as {{"payments": {{"role_claim": "Team.Payments"}}}} in {source}, or remove it.'
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: teams must be an object of team names, got {value!r}", fix=fix)
    if value and public:
        raise ConfigError(
            f"{source}: public is true and teams is set. A public console serves its demo to anyone, with no "
            f"sign-in, so it has no teams.",
            fix=f"remove teams from {source}, or remove public to run a team's console.",
        )
    for name, entry in value.items():
        refuse_team_name(name, f"teams.{name}", source=source, fix=f"rename the team {name!r} in {source}")
        if not isinstance(entry, dict):
            raise ConfigError(f"{source}: teams.{name} must be an object, got {entry!r}", fix=fix)
        unknown = set(entry) - _TEAM_KEYS
        if unknown:
            raise ConfigError(
                f"{source}: unknown key(s) {sorted(unknown)} in teams.{name}. A team's entry may hold "
                f"{sorted(_TEAM_KEYS)}.",
                fix=f"remove {sorted(unknown)} from teams.{name} in {source}.",
            )
        for key, said in entry.items():
            if not isinstance(said, str) or not said.strip() or not _text(said):
                raise ConfigError(f"{source}: teams.{name}.{key} must be text, got {said!r}", fix=fix)
    return {name: dict(entry) for name, entry in value.items()}


#: What each top-level value must be, read from the dataclass's own annotations (the two
#: mappings are checked by their own validators). `bool` is refused where a number belongs --
#: it is an `int` in Python -- a port is a TCP port, every limit is above zero, and a host or a
#: store root is never empty. Measured before this: a `port` written as a string passed loading
#: and failed at bind with a traceback, and a port past 65535 did the same.
_WANT = {
    "str": "a non-empty string without control characters",
    "int": "a whole number above zero",
    "float": "a finite number above zero",
}


def _control(text: str) -> bool:
    """A control character: a NUL in a path or a host once broke the start with a traceback."""
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def _text(value: str) -> bool:
    """Text a host, path or page can carry: no lone surrogate."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _fits(name: str, kind: str, value: object) -> bool:
    if kind == "str":
        return isinstance(value, str) and bool(value.strip()) and not _control(value) and _text(value)
    if isinstance(value, bool) or not isinstance(value, (int, float) if kind == "float" else int):
        return False
    #: Finite: an infinite timeout was accepted, and every POST then dropped.
    return math.isfinite(value) and value > 0 and (name != "port" or value <= 65535)


def _validate_top(data: dict, *, source: str) -> None:
    for f in fields(Config):
        if f.name not in data or f.type not in _WANT:
            continue
        if isinstance(data[f.name], str) and not _text(data[f.name]):
            #: Named as what it is: it was refused as "a control character", and the fix
            #: pointed at the wrong thing.
            raise ConfigError(
                f"{source}: {f.name} holds a lone surrogate escape, which is not text: {data[f.name]!r}",
                fix=f"write {f.name} in {source} as plain text: remove the escape of a "
                f"surrogate (U+D800 to U+DFFF) that has no pair.",
            )
        if not _fits(f.name, f.type, data[f.name]):
            want = "a TCP port, 1 to 65535" if f.name == "port" else _WANT[f.type]
            raise ConfigError(
                f"{source}: {f.name} must be {want}, got {data[f.name]!r}",
                fix=f"give {f.name} {want} in {source} (its default is {f.default!r}), or "
                f"remove the key to use that default.",
            )


def _validate_scim(value: object, *, source: str) -> dict:
    """`scim`: its keys, each checked; `token_max_days` at most 365, said with the limit."""
    import ipaddress
    import re

    from onetrace_console.scim import DEFAULTS, TOKEN_DAYS_CEILING

    fix = f'give scim as {{"enabled": true}} in {source}, beside sign_in.method oidc, or remove it.'
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: scim must be an object, got {value!r}", fix=fix)
    unknown = set(value) - set(DEFAULTS)
    if unknown:
        raise ConfigError(
            f"{source}: unknown scim key(s) {sorted(unknown)}. Known keys: {sorted(DEFAULTS)}.",
            fix=f"remove {sorted(unknown)} from scim in {source}.",
        )
    merged = {**DEFAULTS, **value}
    for key in ("enabled", "required_for_sign_in"):
        if not isinstance(merged[key], bool):
            raise ConfigError(f"{source}: scim.{key} must be true or false, got {merged[key]!r}", fix=fix)
    tenant = merged["tenant_id"]
    guid = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
    if not isinstance(tenant, str) or (tenant and not re.fullmatch(guid, tenant)):
        raise ConfigError(f"{source}: scim.tenant_id must be a tenant's id (a GUID), or empty, got {tenant!r}", fix=fix)
    days = merged["token_max_days"]
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= TOKEN_DAYS_CEILING:
        raise ConfigError(
            f"{source}: scim.token_max_days is {days!r}; it is a whole number of days, at most {TOKEN_DAYS_CEILING}. "
            "A token pasted by hand is never left for longer than a year.",
            fix=f"set scim.token_max_days in {source} to {TOKEN_DAYS_CEILING} or fewer (180 by default).",
        )
    ranges = merged["allowed_sources"]
    if not isinstance(ranges, list) or not all(isinstance(r_, str) for r_ in ranges):
        raise ConfigError(f"{source}: scim.allowed_sources must be a list of address ranges, got {ranges!r}", fix=fix)
    for r_ in ranges:
        try:
            ipaddress.ip_network(r_, strict=False)
        except ValueError:
            raise ConfigError(
                f"{source}: scim.allowed_sources holds {r_!r}, not an address range such as 20.20.32.0/19", fix=fix
            ) from None
    for key, low, high in (("max_body_bytes", 1024, 64 * 1024 * 1024), ("max_results", 1, 1000)):
        n = merged[key]
        if isinstance(n, bool) or not isinstance(n, int) or not low <= n <= high:
            raise ConfigError(f"{source}: scim.{key} must be a whole number from {low} to {high}, got {n!r}", fix=fix)
    return {**merged, "allowed_sources": list(ranges)}


def _validate_audit(value: object, *, source: str) -> dict:
    """`audit`: an object of `enabled` (true or false), `head_location` (a path, or null) and `max_segment_bytes` (a
    whole number of at least 4096)."""
    fix = (
        f'give audit as {{"enabled": true, "head_location": "/mnt/audit-heads/heads.jsonl"}} in {source}, or remove it.'
    )
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: audit must be an object, got {value!r}", fix=fix)
    unknown = set(value) - set(AUDIT_DEFAULTS)
    if unknown:
        raise ConfigError(
            f"{source}: unknown audit key(s) {sorted(unknown)}. Known keys: {sorted(AUDIT_DEFAULTS)}.",
            fix=f"remove {sorted(unknown)} from audit in {source}.",
        )
    merged = {**AUDIT_DEFAULTS, **value}
    if not isinstance(merged["enabled"], bool):
        raise ConfigError(f"{source}: audit.enabled must be true or false, got {merged['enabled']!r}", fix=fix)
    location = merged["head_location"]
    if location is not None and not (isinstance(location, str) and location.strip()):
        raise ConfigError(f"{source}: audit.head_location must be a path, or null, got {location!r}", fix=fix)
    size = merged["max_segment_bytes"]
    if isinstance(size, bool) or not isinstance(size, int) or size < 4096:
        raise ConfigError(
            f"{source}: audit.max_segment_bytes must be a whole number of at least 4096, got {size!r}", fix=fix
        )
    return merged


def _validate_tracing(value: object, *, source: str) -> dict:
    """`tracing`: an object with one key, `link`, an http(s) address holding `{trace_id}`."""
    import re

    fix = (
        f'give tracing as {{"link": "https://your-tool.example/trace/{{trace_id}}?span={{span_id}}"}} '
        f"in {source}, or remove it."
    )
    if not isinstance(value, dict) or set(value) - {"link"}:
        raise ConfigError(f"{source}: tracing must be an object with one key, link, got {value!r}", fix=fix)
    link = value.get("link")
    if link is None:
        return {}
    if not (isinstance(link, str) and _text(link) and re.match(r"https?://", link) and "{trace_id}" in link):
        raise ConfigError(
            f"{source}: tracing.link must be an http(s) address holding {{trace_id}}, got {link!r}", fix=fix
        )
    return {"link": link}


def _validate_tokenizers(value: object, *, source: str) -> list:
    """`tokenizers`: a list of objects, each with `folder`, a path, and `files`, the names in that folder
    (relative, with no `..`), each named once."""
    fix = (
        f'give tokenizers as [{{"folder": "/models/my-model", "files": ["tokenizer.json"]}}] in {source}, or remove it.'
    )
    if not isinstance(value, list):
        raise ConfigError(f"{source}: tokenizers must be a list, got {value!r}", fix=fix)
    out = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) != {"folder", "files"}:
            raise ConfigError(
                f"{source}: each of tokenizers must be an object with the keys folder and files, got {entry!r}", fix=fix
            )
        folder, files = entry["folder"], entry["files"]
        if not (isinstance(folder, str) and _text(folder)):
            raise ConfigError(f"{source}: tokenizers' folder must be a path ({_WANT['str']}), got {folder!r}", fix=fix)
        if not (
            isinstance(files, list)
            and files
            and len(set(map(str, files))) == len(files)
            and all(
                isinstance(f, str)
                and _text(f)
                and not PurePath(f).anchor
                and "\\" not in f
                and ".." not in PurePath(f).parts
                for f in files
            )
        ):
            raise ConfigError(
                f"{source}: tokenizers' files must be a list of names in its folder, each "
                f"relative, without .., and named once, got {files!r}",
                fix=fix,
            )
        out.append({"folder": folder, "files": list(files)})
    return out


def _validate_extensions(value: object, *, source: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: 'extensions' must be a JSON object, got {type(value).__name__}")
    unknown = set(value) - _KNOWN_EXTENSIONS
    if unknown:
        raise ConfigError(
            f"{source}: unknown extension(s) {sorted(unknown)}. Known extensions: {sorted(_KNOWN_EXTENSIONS)}."
        )
    not_bool = {k: v for k, v in value.items() if not isinstance(v, bool)}
    if not_bool:
        raise ConfigError(f"{source}: extension flags must be true or false, got {not_bool}")
    merged = {name: False for name in _KNOWN_EXTENSIONS}
    merged.update(value)
    return merged


_DEFAULT_PORTS = {"http": 80, "https": 443}


def origin_of(url: str, *, path_allowed: bool = False) -> str | None:
    """`scheme://host[:port]`, lower-cased, its port left out where it is the scheme's own, for an
    http or https URL that names a host; None for anything else (`null`, no host, another scheme,
    a port that is not a number). A path, query or fragment makes it None unless `path_allowed`
    (a Referer's), and user info always does."""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url.strip())
        port = parts.port
    except ValueError:
        return None
    scheme, host = parts.scheme.lower(), (parts.hostname or "")
    if scheme not in _DEFAULT_PORTS or not host or "@" in parts.netloc:
        return None
    if not path_allowed and (parts.path not in ("", "/") or parts.query or parts.fragment):
        return None
    host = f"[{host}]" if ":" in host else host
    return f"{scheme}://{host}" + (f":{port}" if port is not None and port != _DEFAULT_PORTS[scheme] else "")


def validate_sign_in_public_url(url: str, *, source: str = "sign_in") -> str:
    """The configured public URL's origin; ConfigError where it is not one."""
    got = origin_of(url)
    if got is None:
        raise ConfigError(
            f"{source}: sign_in.public_url must be an origin, an http or https URL naming a host "
            f"and nothing after it, such as https://console.example.com, got {url!r}",
            fix=f"set sign_in.public_url in {source} to the scheme and host your browser opens this "
            f"console at, or leave it empty.",
        )
    return got


def _validate_sign_in(value: object, *, source: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: 'sign_in' must be a JSON object, got {type(value).__name__}")
    unknown = set(value) - _KNOWN_SIGN_IN_KEYS
    if unknown:
        raise ConfigError(
            f"{source}: unknown sign_in key(s) {sorted(unknown)}. Known keys: {sorted(_KNOWN_SIGN_IN_KEYS)}."
        )
    for key, v in value.items():
        expected, _default = _SIGN_IN_SCHEMA[key]
        if expected is bool:
            if not isinstance(v, bool):
                raise ConfigError(f"{source}: sign_in.{key} must be true or false, got {v!r}")
        elif expected is int:
            #: `bool` is an `int` subclass in Python -- excluded explicitly, so
            #: `true`/`false` typed where a count belongs is refused, not silently 1/0.
            if isinstance(v, bool) or not isinstance(v, int):
                raise ConfigError(f"{source}: sign_in.{key} must be an integer, got {v!r}")
        elif expected is list:
            import ipaddress

            try:
                ok = isinstance(v, list) and all(
                    isinstance(t, str) and ipaddress.ip_network(t, strict=False) for t in v
                )
            except ValueError:
                ok = False
            if not ok:
                raise ConfigError(
                    f"{source}: sign_in.{key} must be a list of addresses and CIDR ranges, such as "
                    f'["127.0.0.1", "10.0.0.0/8"], got {v!r}',
                    fix=f"write sign_in.{key} in {source} as a JSON list of strings, each an IPv4 or "
                    f"IPv6 address or range, or leave it out.",
                )
        elif expected is dict:
            value = {**value, key: _validate_oidc(v, source=source)}
        elif expected is str:
            if not isinstance(v, str):
                raise ConfigError(f"{source}: sign_in.{key} must be a string, got {v!r}")
            if not _text(v):
                raise ConfigError(
                    f"{source}: sign_in.{key} holds a lone surrogate escape, which is not text: {v!r}",
                    fix=f"write sign_in.{key} in {source} as plain text: remove the escape "
                    f"of a surrogate (U+D800 to U+DFFF) that has no pair.",
                )
            if _control(v):
                raise ConfigError(
                    f"{source}: sign_in.{key} holds a control character: {v!r}",
                    fix=f"remove the control character from sign_in.{key} in {source}.",
                )
    if "max_sessions_per_account" in value and value["max_sessions_per_account"] < 1:
        raise ConfigError(
            f"{source}: sign_in.max_sessions_per_account must be at least 1, got {value['max_sessions_per_account']!r}",
            fix=f"set sign_in.max_sessions_per_account in {source} to 1 or more, or leave it out (3).",
        )
    if value.get("public_url"):
        validate_sign_in_public_url(value["public_url"], source=source)
    cert = value.get("tls_cert_path", "")
    key_path = value.get("tls_key_path", "")
    if bool(cert) != bool(key_path):
        raise ConfigError(
            f"{source}: sign_in.tls_cert_path and sign_in.tls_key_path must be set "
            f"together, or neither -- one alone ({cert=!r}, {key_path=!r}) is not a "
            f"usable TLS configuration and would otherwise be silently incomplete."
        )
    if value.get("method", "local") not in SIGN_IN_METHODS:
        raise ConfigError(
            f"{source}: sign_in.method must be one of {list(SIGN_IN_METHODS)}, got {value['method']!r}",
            fix=f"set sign_in.method in {source} to local (the console's own accounts) or oidc "
            f"(Microsoft Entra ID), or leave it out (local).",
        )
    merged = _sign_in_defaults()
    merged.update(value)
    if merged["method"] == "oidc":
        _check_oidc_method(merged, source=source)
    return merged


def _from_mapping(data: dict, *, source: str) -> Config:
    unknown = set(data) - _KEYS
    if unknown:
        raise ConfigError(
            f"{source}: unknown configuration key(s) {sorted(unknown)}. "
            f"Every key this file may set: {sorted(_KEYS)}. A typo here would otherwise "
            f"be silently ignored, which is worse than refusing.",
            fix=f"remove {sorted(unknown)} from {source}, or correct the spelling to one of the keys listed above.",
        )
    _validate_top(data, source=source)
    if "public" in data and not isinstance(data["public"], bool):
        raise ConfigError(
            f"{source}: public must be true or false, got {data['public']!r}",
            fix=f"give public true or false in {source} (its default is false), or remove the "
            f"key to leave the console as it is.",
        )
    shipped = Config()
    for name in (
        "compare_per_minute",
        "compare_running",
        "compare_queue",
        "compare_wait_seconds",
        "compare_verb_seconds",
    ):
        if (
            name in data
            and _fits(name, type(getattr(shipped, name)).__name__, data[name])
            and data[name] > getattr(shipped, name)
        ):
            raise ConfigError(
                f"{source}: {name} is {data[name]!r}, above the shipped {getattr(shipped, name)!r}; Compare's "
                f'bounds can be lowered, not raised, so every page\'s "at most" stays true',
                fix=f"give {name} a number from 1 to {getattr(shipped, name)!r} in {source}, or remove the key.",
            )
    if data.get("compare_client_header") is not None and data.get("public") is not True:
        raise ConfigError(
            f"{source}: compare_client_header is set and public is not true. Only a public console's "
            f"Compare reads a client-address header; any other console reads none.",
            fix=f"remove compare_client_header from {source}, or set public to true.",
        )
    for name, what in (("compare_cache", "a folder's path"), ("compare_client_header", "a header's name")):
        if name in data and data[name] is not None and not _fits(name, "str", data[name]):
            raise ConfigError(
                f"{source}: {name} must be {what} ({_WANT['str']}) or null, got {data[name]!r}",
                fix=f"give {name} {what} in {source}, or null, or remove the key.",
            )
    if "trust_file" in data and data["trust_file"] is not None and not _fits("trust_file", "str", data["trust_file"]):
        raise ConfigError(
            f"{source}: trust_file must be a path ({_WANT['str']}) or null, got {data['trust_file']!r}",
            fix=f"give trust_file the path of an onetrace-trust/0.1 file in {source}, or remove the "
            f'key to check without one (a valid signature then reads "Signed, key not '
            f'trusted").',
        )
    if (
        "recipients_file" in data
        and data["recipients_file"] is not None
        and not _fits("recipients_file", "str", data["recipients_file"])
    ):
        raise ConfigError(
            f"{source}: recipients_file must be a path ({_WANT['str']}) or null, got {data['recipients_file']!r}",
            fix=f"give recipients_file the path of an onetrace-recipient-trust/1 file in {source}, or remove the key "
            "to check without one (a recipient's key row then reads NOT-RUN).",
        )
    if "tsa_cert" in data and data["tsa_cert"] is not None and not _fits("tsa_cert", "str", data["tsa_cert"]):
        raise ConfigError(
            f"{source}: tsa_cert must be a path ({_WANT['str']}) or null, got {data['tsa_cert']!r}",
            fix=f"give tsa_cert the path of the time-stamp authority's certificate in {source}, or "
            f'remove the key (an RFC 3161 anchor then reads "Couldn\'t check").',
        )
    if "tsa_roots" in data:
        roots = data["tsa_roots"]
        if not (isinstance(roots, list) and all(_fits("tsa_roots", "str", r) for r in roots)):
            raise ConfigError(
                f"{source}: tsa_roots must be a list of paths ({_WANT['str']}), got {roots!r}",
                fix=f"give tsa_roots a list of the root certificates' paths in {source}, for "
                f'example ["tsa-root.pem"], or remove the key.',
            )
        data = {**data, "tsa_roots": list(roots)}
    if bool(data.get("tsa_cert")) != bool(data.get("tsa_roots")):
        raise ConfigError(
            f"{source}: tsa_cert and tsa_roots go together: the verifier checks a time-stamp "
            f"authority's certificate against the root it chains to.",
            fix=f"set both tsa_cert and tsa_roots in {source}, or neither.",
        )
    if "tracing" in data:
        data = {**data, "tracing": _validate_tracing(data["tracing"], source=source)}
    if "tokenizers" in data:
        data = {**data, "tokenizers": _validate_tokenizers(data["tokenizers"], source=source)}
    if "teams" in data:
        data = {**data, "teams": _validate_teams(data["teams"], public=data.get("public") is True, source=source)}
    if "audit" in data:
        data = {**data, "audit": _validate_audit(data["audit"], source=source)}
    if "scim" in data:
        data = {**data, "scim": _validate_scim(data["scim"], source=source)}
    if "folder_team" in data:
        data = {**data, "folder_team": _validate_folder_team(data["folder_team"], data.get("teams", {}), source=source)}
    if "extensions" in data or "sign_in" in data:
        data = dict(data)
        if "extensions" in data:
            data["extensions"] = _validate_extensions(data["extensions"], source=source)
        if "sign_in" in data:
            sign_in = data["sign_in"]
            #: Said first, so a public console's file is told the reason that holds for it, not the
            #: sign-in checks that would follow (`public.start_refusal` says the same at start).
            if data.get("public") is True and isinstance(sign_in, dict) and sign_in.get("method") == "oidc":
                raise ConfigError(
                    f"{source}: public is true and sign_in.method is oidc. A public console serves the demo "
                    f"to anyone, with no sign-in; Entra ID sign-in is for a team's own console.",
                    fix=f"remove sign_in.method and sign_in.oidc from {source}, or remove public to run a "
                    f"team's console with Entra ID sign-in.",
                )
            data["sign_in"] = _validate_sign_in(sign_in, source=source)
    try:
        return Config(**data)
    except TypeError as e:
        raise ConfigError(f"{source}: {e}") from None


def load(path: Path) -> Config:
    """Read one config file. Refuses -- never falls back -- on anything wrong with it."""
    if not path.is_file():
        raise ConfigError(
            f"{ENV_VAR} names {path}, which is not a file",
            fix=f"point {ENV_VAR} at the configuration file, or unset it to run in local mode.",
        )
    try:
        #: `utf-8-sig`: Notepad saves UTF-8 with a byte order mark, and the file is still the
        #: operator's JSON.
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConfigError(
            f"{path} cannot be read: {e.strerror or e}",
            fix=f"let this console's user read {path}, or point {ENV_VAR} at a file it can read.",
        ) from None
    except UnicodeDecodeError as e:
        raise ConfigError(f"{path}: not valid UTF-8: {e}") from None
    try:
        data = load_json_bounded(raw, str(path))
    except TooDeep:
        raise ConfigError(
            f"{path}: nested too deeply to read",
            fix='write the configuration as one flat JSON object, {"key": value, ...}.',
        ) from None
    except json.JSONDecodeError as e:
        raise ConfigError(
            f"{path}: not valid JSON: {e}", fix="correct the JSON at the line and column named above."
        ) from None
    except RecursionError:
        raise ConfigError(
            f"{path}: nested too deeply to read",
            fix='write the configuration as one flat JSON object, {"key": value, ...}.',
        ) from None
    if not isinstance(data, dict):
        raise ConfigError(
            f"{path}: the top level must be a JSON object, got {type(data).__name__}",
            fix='write the configuration as one JSON object, {"key": value, ...}.',
        )
    config = _from_mapping(data, source=str(path))
    #: A relative path in the file is read from the file's own folder, as a reader of the file
    #: expects -- never from wherever the console happened to be started.
    return resolve_paths(config, path.parent)


def from_folder(value: str, base, flavour=PurePath) -> str:
    """A configured path, read from `base` only if it is relative: a path with a root or a drive
    (`/srv/x`, `C:\\x`, `\\\\host\\share\\x`, even `D:x`) is kept exactly as given, on every
    system -- on Windows `/srv/x` has no drive, but it has a root, and is not relative. Never
    resolved: a configured path names what the operator wrote, not where a link happens to lead.
    `flavour` is the system's own path rules; a test passes the other system's."""
    if flavour(value).anchor:
        return value
    base = flavour(base)
    if not base.anchor:
        base = flavour(os.getcwd()) / base
    return str(base / value)


def resolve_paths(config: Config, base: Path) -> Config:
    """`config` with each relative trust file, TSA certificate, TSA root and tokenizer folder read from
    `base`."""
    from dataclasses import replace

    def absolute(value):
        return value if value is None else from_folder(value, base)

    return replace(
        config,
        trust_file=absolute(config.trust_file),
        recipients_file=absolute(config.recipients_file),
        tsa_cert=absolute(config.tsa_cert),
        tsa_roots=[absolute(r) for r in config.tsa_roots],
        tokenizers=[{**t, "folder": absolute(t["folder"])} for t in config.tokenizers],
    )


def load_from_env() -> Config:
    """`Config()` (every default) if `ONETRACE_CONSOLE_CONFIG` is unset; otherwise `load()`
    of the file it names, which refuses rather than silently falling back to defaults if
    that file is missing or malformed -- an operator who named a file and got defaults
    instead would not know their configuration was never read.
    """
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return Config()
    return load(Path(raw))
