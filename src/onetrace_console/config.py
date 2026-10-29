"""One read-only configuration file. Its path is the only environment variable this
console reads.

*"One configuration file, mounted read-only, with its keys documented. The only
environment variable allowed is the path to that file."* Before this,
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
"""
from __future__ import annotations

import json
from onetrace_console.bounded_json import TooDeep, load_json_bounded
import math
import os
from dataclasses import dataclass, field, fields
from pathlib import Path, PurePath

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
    #: Rate limiting: per account and per client, both configurable,
    #: over the same sliding window.
    "rate_limit_max_attempts_per_account": (int, 10),
    "rate_limit_max_attempts_per_client": (int, 20),
    "rate_limit_window_seconds": (int, 300),
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
}
_KNOWN_SIGN_IN_KEYS = frozenset(_SIGN_IN_SCHEMA)


class ConfigError(RuntimeError):
    """The named config file could not be read as this console's configuration.

    `fix` is the one line an operator acts on: every entry point that
    reads the file prints the message and then `fix: ...`, never a traceback.
    """

    def __init__(self, message: str, fix: str | None = None) -> None:
        super().__init__(message)
        self.fix = fix or (f"correct the file (OPERATOR_README.md lists every key, its type and "
                           f"its default), or unset {ENV_VAR} to run in local mode.")


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
    sign_in: dict = field(default_factory=lambda: {k: d for k, (_t, d) in _SIGN_IN_SCHEMA.items()})
    #: The signing keys this console's operator trusts, a path to an
    #: `onetrace-trust/0.1` file, or absent (the default). Set, every check runs the verifier with
    #: `--trust <that file>`; absent, without it, and a valid signature then reads "Signed, key not
    #: trusted", never Yes. The console never makes, edits or guesses a trust file: a file the
    #: verifier can't read is its own `--trust` FAIL row, shown as it is.
    trust_file: str | None = None
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


_KEYS = {f.name for f in fields(Config)}

#: What each top-level value must be, read from the dataclass's own annotations (the two
#: mappings are checked by their own validators). `bool` is refused where a number belongs --
#: it is an `int` in Python -- a port is a TCP port, every limit is above zero, and a host or a
#: store root is never empty. Measured before this: a `port` written as a string passed loading
#: and failed at bind with a traceback, and a port past 65535 did the same.
_WANT = {"str": "a non-empty string without control characters",
         "int": "a whole number above zero", "float": "a finite number above zero"}


def _control(text: str) -> bool:
    """A control character: a NUL in a path or a host broke the start with a traceback (the
    second confirmation review, S2)."""
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def _text(value: str) -> bool:
    """Text a host, path or page can carry: no lone surrogate (the third review, NEW-8)."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _fits(name: str, kind: str, value: object) -> bool:
    if kind == "str":
        return (isinstance(value, str) and bool(value.strip()) and not _control(value)
                and _text(value))
    if isinstance(value, bool) or not isinstance(value, (int, float) if kind == "float" else int):
        return False
    #: Finite: an infinite timeout was accepted, and every POST then dropped (NEW-9).
    return math.isfinite(value) and value > 0 and (name != "port" or value <= 65535)


def _validate_top(data: dict, *, source: str) -> None:
    for f in fields(Config):
        if f.name not in data or f.type not in _WANT:
            continue
        if isinstance(data[f.name], str) and not _text(data[f.name]):
            #: Named as what it is: it was refused as "a control character", and the fix
            #: pointed at the wrong thing.
            raise ConfigError(
                f"{source}: {f.name} holds a lone surrogate escape, which is not text: "
                f"{data[f.name]!r}",
                fix=f"write {f.name} in {source} as plain text: remove the escape of a "
                    f"surrogate (U+D800 to U+DFFF) that has no pair.")
        if not _fits(f.name, f.type, data[f.name]):
            want = "a TCP port, 1 to 65535" if f.name == "port" else _WANT[f.type]
            raise ConfigError(
                f"{source}: {f.name} must be {want}, got {data[f.name]!r}",
                fix=f"give {f.name} {want} in {source} (its default is {f.default!r}), or "
                    f"remove the key to use that default.")


def _validate_tracing(value: object, *, source: str) -> dict:
    """`tracing`: an object with one key, `link`, an http(s) address holding `{trace_id}`."""
    import re
    fix = (f'give tracing as {{"link": "https://your-tool.example/trace/{{trace_id}}?span={{span_id}}"}} '
           f"in {source}, or remove it.")
    if not isinstance(value, dict) or set(value) - {"link"}:
        raise ConfigError(f"{source}: tracing must be an object with one key, link, got {value!r}", fix=fix)
    link = value.get("link")
    if link is None:
        return {}
    if not (isinstance(link, str) and _text(link) and re.match(r"https?://", link) and "{trace_id}" in link):
        raise ConfigError(f"{source}: tracing.link must be an http(s) address holding {{trace_id}}, "
                          f"got {link!r}", fix=fix)
    return {"link": link}


def _validate_extensions(value: object, *, source: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(
            f"{source}: 'extensions' must be a JSON object, got {type(value).__name__}")
    unknown = set(value) - _KNOWN_EXTENSIONS
    if unknown:
        raise ConfigError(
            f"{source}: unknown extension(s) {sorted(unknown)}. "
            f"Known extensions: {sorted(_KNOWN_EXTENSIONS)}.")
    not_bool = {k: v for k, v in value.items() if not isinstance(v, bool)}
    if not_bool:
        raise ConfigError(
            f"{source}: extension flags must be true or false, got {not_bool}")
    merged = {name: False for name in _KNOWN_EXTENSIONS}
    merged.update(value)
    return merged


def _validate_sign_in(value: object, *, source: str) -> dict:
    if not isinstance(value, dict):
        raise ConfigError(
            f"{source}: 'sign_in' must be a JSON object, got {type(value).__name__}")
    unknown = set(value) - _KNOWN_SIGN_IN_KEYS
    if unknown:
        raise ConfigError(
            f"{source}: unknown sign_in key(s) {sorted(unknown)}. "
            f"Known keys: {sorted(_KNOWN_SIGN_IN_KEYS)}.")
    for key, v in value.items():
        expected, _default = _SIGN_IN_SCHEMA[key]
        if expected is bool:
            if not isinstance(v, bool):
                raise ConfigError(
                    f"{source}: sign_in.{key} must be true or false, got {v!r}")
        elif expected is int:
            #: `bool` is an `int` subclass in Python -- excluded explicitly, so
            #: `true`/`false` typed where a count belongs is refused, not silently 1/0.
            if isinstance(v, bool) or not isinstance(v, int):
                raise ConfigError(f"{source}: sign_in.{key} must be an integer, got {v!r}")
        elif expected is str:
            if not isinstance(v, str):
                raise ConfigError(f"{source}: sign_in.{key} must be a string, got {v!r}")
            if not _text(v):
                raise ConfigError(
                    f"{source}: sign_in.{key} holds a lone surrogate escape, which is not "
                    f"text: {v!r}",
                    fix=f"write sign_in.{key} in {source} as plain text: remove the escape "
                        f"of a surrogate (U+D800 to U+DFFF) that has no pair.")
            if _control(v):
                raise ConfigError(
                    f"{source}: sign_in.{key} holds a control character: {v!r}",
                    fix=f"remove the control character from sign_in.{key} in {source}.")
    cert = value.get("tls_cert_path", "")
    key_path = value.get("tls_key_path", "")
    if bool(cert) != bool(key_path):
        raise ConfigError(
            f"{source}: sign_in.tls_cert_path and sign_in.tls_key_path must be set "
            f"together, or neither -- one alone ({cert=!r}, {key_path=!r}) is not a "
            f"usable TLS configuration and would otherwise be silently incomplete.")
    merged = {k: default for k, (_typ, default) in _SIGN_IN_SCHEMA.items()}
    merged.update(value)
    return merged


def _from_mapping(data: dict, *, source: str) -> Config:
    unknown = set(data) - _KEYS
    if unknown:
        raise ConfigError(
            f"{source}: unknown configuration key(s) {sorted(unknown)}. "
            f"Every key this file may set: {sorted(_KEYS)}. A typo here would otherwise "
            f"be silently ignored, which is worse than refusing.",
            fix=f"remove {sorted(unknown)} from {source}, or correct the spelling to one of "
                f"the keys listed above.")
    _validate_top(data, source=source)
    if "public" in data and not isinstance(data["public"], bool):
        raise ConfigError(
            f"{source}: public must be true or false, got {data['public']!r}",
            fix=f"give public true or false in {source} (its default is false), or remove the "
                f"key to leave the console as it is.")
    shipped = Config()
    for name in ("compare_per_minute", "compare_running", "compare_queue", "compare_wait_seconds",
                 "compare_verb_seconds"):
        if name in data and _fits(name, type(getattr(shipped, name)).__name__, data[name]) \
                and data[name] > getattr(shipped, name):
            raise ConfigError(
                f"{source}: {name} is {data[name]!r}, above the shipped {getattr(shipped, name)!r}; Compare's "
                f"bounds can be lowered, not raised, so every page's \"at most\" stays true",
                fix=f"give {name} a number from 1 to {getattr(shipped, name)!r} in {source}, or remove the key.")
    if data.get("compare_client_header") is not None and data.get("public") is not True:
        raise ConfigError(
            f"{source}: compare_client_header is set and public is not true. Only a public console's "
            f"Compare reads a client-address header; any other console reads none.",
            fix=f"remove compare_client_header from {source}, or set public to true.")
    for name, what in (("compare_cache", "a folder's path"), ("compare_client_header", "a header's name")):
        if name in data and data[name] is not None and not _fits(name, "str", data[name]):
            raise ConfigError(
                f"{source}: {name} must be {what} ({_WANT['str']}) or null, got {data[name]!r}",
                fix=f"give {name} {what} in {source}, or null, or remove the key.")
    if "trust_file" in data and data["trust_file"] is not None and not _fits(
            "trust_file", "str", data["trust_file"]):
        raise ConfigError(
            f"{source}: trust_file must be a path ({_WANT['str']}) or null, got "
            f"{data['trust_file']!r}",
            fix=f"give trust_file the path of an onetrace-trust/0.1 file in {source}, or remove the "
                f"key to check without one (a valid signature then reads \"Signed, key not "
                f"trusted\").")
    if "tsa_cert" in data and data["tsa_cert"] is not None and not _fits(
            "tsa_cert", "str", data["tsa_cert"]):
        raise ConfigError(
            f"{source}: tsa_cert must be a path ({_WANT['str']}) or null, got {data['tsa_cert']!r}",
            fix=f"give tsa_cert the path of the time-stamp authority's certificate in {source}, or "
                f"remove the key (an RFC 3161 anchor then reads \"Couldn't check\").")
    if "tsa_roots" in data:
        roots = data["tsa_roots"]
        if not (isinstance(roots, list) and all(_fits("tsa_roots", "str", r) for r in roots)):
            raise ConfigError(
                f"{source}: tsa_roots must be a list of paths ({_WANT['str']}), got {roots!r}",
                fix=f"give tsa_roots a list of the root certificates' paths in {source}, for "
                    f"example [\"tsa-root.pem\"], or remove the key.")
        data = {**data, "tsa_roots": list(roots)}
    if bool(data.get("tsa_cert")) != bool(data.get("tsa_roots")):
        raise ConfigError(
            f"{source}: tsa_cert and tsa_roots go together: the verifier checks a time-stamp "
            f"authority's certificate against the root it chains to.",
            fix=f"set both tsa_cert and tsa_roots in {source}, or neither.")
    if "tracing" in data:
        data = {**data, "tracing": _validate_tracing(data["tracing"], source=source)}
    if "extensions" in data or "sign_in" in data:
        data = dict(data)
        if "extensions" in data:
            data["extensions"] = _validate_extensions(data["extensions"], source=source)
        if "sign_in" in data:
            data["sign_in"] = _validate_sign_in(data["sign_in"], source=source)
    try:
        return Config(**data)
    except TypeError as e:
        raise ConfigError(f"{source}: {e}") from None


def load(path: Path) -> Config:
    """Read one config file. Refuses -- never falls back -- on anything wrong with it."""
    if not path.is_file():
        raise ConfigError(f"{ENV_VAR} names {path}, which is not a file",
                          fix=f"point {ENV_VAR} at the configuration file, or unset it to run "
                              f"in local mode.")
    try:
        #: `utf-8-sig`: Notepad saves UTF-8 with a byte order mark, and the file is still the
        #: operator's JSON (the confirmation review, note 8).
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise ConfigError(f"{path} cannot be read: {e.strerror or e}",
                          fix=f"let this console's user read {path}, or point {ENV_VAR} at a "
                              f"file it can read.") from None
    except UnicodeDecodeError as e:
        raise ConfigError(f"{path}: not valid UTF-8: {e}") from None
    try:
        data = load_json_bounded(raw, str(path))
    except TooDeep:
        raise ConfigError(f"{path}: nested too deeply to read",
                          fix="write the configuration as one flat JSON object, "
                              "{\"key\": value, ...}.") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path}: not valid JSON: {e}",
                          fix="correct the JSON at the line and column named above.") from None
    except RecursionError:
        raise ConfigError(f"{path}: nested too deeply to read",
                          fix="write the configuration as one flat JSON object, "
                              "{\"key\": value, ...}.") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: the top level must be a JSON object, got "
                          f"{type(data).__name__}",
                          fix='write the configuration as one JSON object, {"key": value, ...}.')
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
    """`config` with each relative trust file, TSA certificate and TSA root read from `base`."""
    from dataclasses import replace

    def absolute(value):
        return value if value is None else from_folder(value, base)
    return replace(config, trust_file=absolute(config.trust_file),
                   tsa_cert=absolute(config.tsa_cert),
                   tsa_roots=[absolute(r) for r in config.tsa_roots])


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
