"""The console's entry point.

Step 0 only wired the repository up; ingest, the store, the check runner and the two
pages arrived in steps 1 to 4, as a library. `serve` -- an actual HTTP surface calling
that library -- arrives later, with the first piece of work that needed one: a container
has to have something listening on a port, and nothing before this asked for that. See
`onetrace_console.serve`'s own docstring for why it took this long.
"""

from __future__ import annotations

import sys

from onetrace_console import __version__

USAGE = """\
onetrace-console {version}

  onetrace-console --version
  onetrace-console pins        what this build is pinned to
  onetrace-console demo [--open] [--port N] [--quiet]
                               record the demo's runs (small example pipelines, no
                               network calls) into ./onetrace-console-demo-<version>, load them,
                               compare them, and serve them on 127.0.0.1, printing the
                               pages' addresses; each phase is said on stderr as it
                               happens, unless --quiet
  onetrace-console demo --public [--open] [--port N]
                               the same demo, read-only: every write refused, a banner on
                               every page, built in a temporary folder and served on 127.0.0.1
  onetrace-console demo --public --build <new folder> [--runs-from <earlier build>]
                   [--explanations <folder>] [--site-links <file>] [--captures]
                               build the read-only demo into a new folder and exit; a
                               configuration with "public": true serves its store as it is.
                               --runs-from: an earlier build's runs, as its build record vouches
                               --explanations: keep onetrace-explain's records under
                               <folder>/explain/ of comparisons this build holds, read-only
                               --site-links: the public site's links into the demo, one per
                               line; a listed comparison page named anew gets a page at its
                               old name
                               --captures: the capture store (P10's runs whose model calls are
                               captured at L3, example data) in place of the demo; also
                               without --build, served as the public demo is
  onetrace-console <runs folder> [--compare A B] [--open] [--port N] [--quiet]
                   [--trust FILE] [--tsa-cert FILE --tsa-root FILE]
                               load every run folder in <runs folder> and serve them on
                               127.0.0.1, store in ./store. Compares nothing unless
                               --compare names two run folders (A is the baseline);
                               --open opens the page in your browser
                               --trust FILE: the signing keys you trust (onetrace-trust/0.1)
                               --tsa-cert FILE: the RFC 3161 time-stamp authority you trust
                               --tsa-root FILE: the root it chains to (may be repeated)
  onetrace-console serve       with ONETRACE_CONSOLE_CONFIG naming a configuration file:
                               listen and serve as that file says. With none named: local
                               mode -- 127.0.0.1:8080 only, no sign-in, store in ./store
  onetrace-console admin create <username>
                               create a local account. The password is read from
                               stdin -- never a command-line argument (visible in
                               `ps`/shell history) and never an environment variable
                               (visible to every other process that shares the
                               environment). Run this INSIDE the container
                               (`docker exec -i <container> onetrace-console admin
                               create <name>`); there is no web route that does this,
                               because "whoever reaches the first-run page first
                               becomes admin" is a takeover race, not a feature.
  onetrace-console admin sessions end <account>
  onetrace-console admin sessions end <tenant id>/<object id>
                               end every session of that person, a local account
                               or an Entra ID key, in a running console too: each
                               of its cookies gets the sign-in page at its next
                               request.
  onetrace-console admin unlock <account>
                               clear the account's sign-in ceiling, in a running
                               console too: new browsers may try its password again.
  onetrace-console admin device-key rotate
                               a new device key: every browser's known-browser
                               cookie ends, and each signs in as a new browser.
  onetrace-console audit verify <folder> [--checkpoint <seq>:<digest>] [--heads <file>]
                               check an audit log, or an export of it: its chain,
                               its head, and the heads kept off the store's volume.
  onetrace-console audit checkpoint
                               print the audit log's seq and head digest, to keep.
  onetrace-console audit export <new folder>
                               copy the audit log out, with the verifier and a
                               SHA256SUMS over it all.
  onetrace-console scim token create [--days <n>]
                               make the token Entra ID's provisioning presents,
                               printed once; it lasts 90 days by default.
  onetrace-console scim token revoke <id>
                               revoke a SCIM token by its id.
  onetrace-console scim user activate <externalId>
                               set a SCIM User active again, on this machine.
  onetrace-console scim enforcement off | on
                               admit Entra ID sign-in without SCIM's join, or
                               restore it; said at every start while off.
  onetrace-console token create <principal> [--team <team>]
                               create an ingester bearer token for <principal>.
                               Prints the raw token to stdout ONCE -- it is stored
                               only as a hash and cannot be recovered afterward.
                               Run this INSIDE the container, same as admin create.
                               With teams configured, --team is required: every run
                               the token delivers is that team's.
  onetrace-console token revoke <id>
                               revoke a token by the id `token create` printed
                               alongside it. A revoked token reads exactly like
                               one that never existed to anything that checks it.
  onetrace-console run assign --unassigned <team>
                               with teams configured, give every held run with no
                               team the team named, keyed with it. Run it with the
                               console stopped; a console with such a run refuses
                               to start until it has.
  onetrace-console run assign <run key> <team>
                               move one held run to another team, keyed with it;
                               its old address leads to the new for its team.
  onetrace-console export-static --runs <key> [<key> ...] --out <new folder>
                               [--fence-terms <file>]
                               the pages the local console serves for those stored runs,
                               as static files: links relative, a demo banner on every
                               page, nothing that writes, signs in or ingests. Prints
                               each file's sha256, then the scans' counts.
"""


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("--help", "-h"):
        #: Asked for: the usage on standard output, and success. Anything not understood
        #: still gets it on standard error, with 2.
        print(USAGE.format(version=__version__))
        return 0
    if argv and argv[0] in ("--version", "-V"):
        print(__version__)
        return 0
    if argv and argv[0] == "pins":
        #: The lock ships inside the package, so an installed console can say what it was
        #: tested with; it is the repository's own lock, byte for byte (tests/test_packaging.py).
        from importlib.resources import files

        pins = files("onetrace_console") / "requirements.lock"
        if not pins.is_file():
            print("no requirements.lock in this installation", file=sys.stderr)
            return 1
        sys.stdout.write(pins.read_text(encoding="utf-8"))
        return 0
    if argv and argv[0] == "serve":
        from onetrace_console.serve import main as serve_main

        return serve_main(argv[1:])
    if argv and argv[:1] == ["admin"]:
        return _admin(argv[1:])
    if argv and argv[:1] == ["token"]:
        return _token(argv[1:])
    if argv[:2] == ["run", "assign"]:
        return _run_assign(argv[2:])
    if argv[:1] == ["audit"]:
        return _audit(argv[1:])
    if argv[:2] == ["scim", "token"]:
        return _scim_token(argv[2:])
    if argv[:2] in (["scim", "user"], ["scim", "enforcement"]):
        return _scim_recovery(argv[1:])
    if argv and argv[:1] == ["export-static"]:
        return _export_static(argv[1:])
    if argv and argv[0] == "demo":
        from onetrace_console.folder_load import main as load_main

        return load_main(argv[1:], demo=True)
    if argv and not argv[0].startswith("-"):
        from pathlib import Path

        if not Path(argv[0]).exists():
            #: Neither a command nor a path: a mistyped command, said as that, not as a folder problem.
            print(f"onetrace-console: {argv[0]!r} is not a command or a folder", file=sys.stderr)
            print(USAGE.format(version=__version__), file=sys.stderr)
            return 2
        from onetrace_console.folder_load import main as load_main

        return load_main(argv, demo=False)
    print(USAGE.format(version=__version__), file=sys.stderr)
    return 2


def _scim_recovery(argv: list[str]) -> int:
    """The way back in, on the console's machine, each recorded with actor `cli`:
    `scim user activate <externalId>` sets that User active again, as a PATCH from the directory would;
    `scim enforcement off` admits an Entra ID sign-in on its app roles alone, with no team from SCIM, until
    `scim enforcement on`. The two that grant access are refused when their entry cannot be appended; `on`, which
    removes access, applies and says so."""
    from pathlib import Path

    from onetrace_console import scim
    from onetrace_console.audit import CLI, AuditRefused

    usage = "usage: onetrace-console scim user activate <externalId> | scim enforcement off | scim enforcement on"
    if not (argv[:2] == ["user", "activate"] and len(argv) == 3) and argv not in (
        ["enforcement", "off"],
        ["enforcement", "on"],
    ):
        print(usage, file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    if not config.scim.get("enabled"):
        print("refusing: scim.enabled is false.\nfix: turn scim on in the configuration file.", file=sys.stderr)
        return 1
    on = _cli_audit(config)
    if on is None:
        return 1
    root = Path(config.store_root).resolve()
    try:
        if argv[0] == "user":
            users = scim.Users(root)
            found = users.by_external_id(argv[2])
            if len(found) != 1:
                print(f"refusing: no one User has the externalId {argv[2]!r}", file=sys.stderr)
                return 1
            on.record(
                CLI,
                "scim.user.activated",
                found[0]["id"],
                {"externalId": found[0]["externalId"], "was_inactive": not found[0].get("active")},
            )
            scim.activate(root, argv[2])
            print(
                f"set User {found[0]['id']} active; the directory's next write about it is still the directory's word"
            )
            return 0
        if argv[1] == "off":
            on.record(CLI, "scim.enforcement.changed", "scim", {"enforcement": "off"})
            scim.set_enforcement(root, False)
            print(
                "SCIM's enforcement of sign-in is off: an Entra ID sign-in is admitted on its app roles alone, with no team from SCIM, until scim enforcement on."
            )
            return 0
        scim.set_enforcement(root, True)
        on.record(CLI, "scim.enforcement.changed", "scim", {"enforcement": "on"}, removes_access=True)
        print("SCIM's enforcement of sign-in is on: the join and the active check apply from the next request.")
        return 0
    except AuditRefused as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1


def _scim_token(argv: list[str]) -> int:
    """`onetrace-console scim token create [--days <n>]` / `scim token revoke <id>`: the token
    Entra ID's provisioning pastes into its "Secret Token" field, printed once and kept as its sha256, its id drawn
    apart from it; at most two live, so one can replace the other without a gap."""
    from pathlib import Path

    from onetrace_console import scim
    from onetrace_console.audit import CLI, AuditRefused

    usage = "usage: onetrace-console scim token create [--days <n>] | scim token revoke <id>"
    creating = argv[:1] == ["create"] and (len(argv) == 1 or (len(argv) == 3 and argv[1] == "--days"))
    if not creating and not (len(argv) == 2 and argv[0] == "revoke"):
        print(usage, file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    if not config.scim.get("enabled"):
        print(
            "refusing: scim.enabled is false, so no SCIM token is made.\nfix: turn scim on in the configuration file.",
            file=sys.stderr,
        )
        return 1
    on = _cli_audit(config)
    if on is None:
        return 1
    tokens = scim.TokenStore(Path(config.store_root).resolve())
    if argv[0] == "revoke":
        if not tokens.revoke(argv[1]):
            print(f"refusing: no live SCIM token with id {argv[1]!r}", file=sys.stderr)
            return 1
        on.record(CLI, "scim.token.revoked", argv[1], {}, removes_access=True)
        print(f"revoked SCIM token {argv[1]!r}: it reads as unknown from now on")
        return 0
    most = config.scim["token_max_days"]
    days = scim.TOKEN_DAYS_DEFAULT if len(argv) == 1 else argv[2]
    if isinstance(days, str):
        if not days.isdigit() or int(days) < 1:
            print(f"refusing: --days is {days!r}, not a whole number of days", file=sys.stderr)
            return 1
        days = int(days)
    if days > most:
        print(
            f"refusing: --days is {days}, over scim.token_max_days ({most}).\nfix: give --days {most} or fewer, or "
            f"raise scim.token_max_days in the configuration file (at most {scim.TOKEN_DAYS_CEILING}).",
            file=sys.stderr,
        )
        return 1
    if len(tokens.live()) >= scim.LIVE_TOKENS:
        print(
            f"refusing: {scim.LIVE_TOKENS} SCIM tokens are live already.\nfix: revoke the older one, once Entra ID "
            "has been seen provisioning with the newer, then make the next.",
            file=sys.stderr,
        )
        return 1
    token, raw = tokens.create(days)
    try:
        on.record(CLI, "scim.token.created", token.token_id, {"expires": token.expires_at, "days": days})
    except AuditRefused as e:
        tokens.forget(token.token_id)
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"SCIM token id: {token.token_id}")
    print(f"expires: {token.expires_at}")
    print(f"token (shown once; paste it into Entra ID's Secret Token field now): {raw}")
    return 0


def _audit(argv: list[str]) -> int:
    """`onetrace-console audit verify <folder> [--checkpoint <seq>:<digest>] [--heads <file>]`, `audit checkpoint`
    and `audit export <new folder>`."""
    from pathlib import Path

    from onetrace_console import audit

    if argv[:1] == ["verify"]:
        from onetrace_console.audit_verify import main as verify_main

        return verify_main(argv[1:])
    usage = "usage: onetrace-console audit verify <folder> [--checkpoint <seq>:<digest>] [--heads <file>] | audit checkpoint | audit export <new folder>"
    if argv not in (["checkpoint"],) and not (len(argv) == 2 and argv[0] == "export"):
        print(usage, file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    on = audit.audit_for(config, Path(config.store_root).resolve())
    if on.log is None:
        print(
            "refusing: audit.enabled is false, so there is no audit log.\nfix: turn it on in the configuration file.",
            file=sys.stderr,
        )
        return 1
    try:
        if argv[0] == "export":
            head = audit.export(on.log, Path(argv[1]))
            print(f"exported the audit log to {argv[1]}: seq {head['seq']}, head {head['head']}")
            return 0
        head = on.log.head()
        on.log.append(audit.CLI, "audit.checkpoint", "log", {"seq": head["seq"], "head": head["head"]})
    except audit.AuditUnavailable as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"checkpoint: {head['seq']}:{head['head']}")
    return 0


def _cli_audit(config):
    """The command line's audit (actor `cli`), or None once the start's refusal for the audit log is
    printed: a command appends to the log the console does, under the same lock."""
    from pathlib import Path

    from onetrace_console import audit

    store_root = Path(config.store_root).resolve()
    refused = audit.start_refusal(config, store_root)
    if refused is not None:
        print(f"refusing: {refused[0]}\nfix: {refused[1]}", file=sys.stderr)
        return None
    return audit.audit_for(config, store_root)


def _config_or_none(*, writes: bool = False):
    """The configuration, or None once its refusal and fix are printed. A command that writes
    accounts or tokens is refused for a public configuration, which has neither."""
    from onetrace_console.config import ConfigError, load_from_env

    try:
        config = load_from_env()
    except ConfigError as e:
        print(f"refusing: {e}\nfix: {e.fix}", file=sys.stderr)
        return None
    if writes and config.public:
        print(
            "refusing: the configuration is public -- a read-only demo, with no accounts and no "
            "tokens.\nfix: run this against a console that is not public.",
            file=sys.stderr,
        )
        return None
    return config


def _admin(argv: list[str]) -> int:
    """`onetrace-console admin create <username>`. The password is read from stdin,
    never argv or an environment variable. This is the only place an
    account is ever created -- there is no web route that does it; see `serve.py`,
    which has none, and `tests/test_admin_cli.py`'s own test naming that absence.
    """
    from pathlib import Path

    from onetrace_console.accounts import AccountError, AccountStore
    from onetrace_console.serve import ACCOUNTS_DIRNAME

    if argv[:1] == ["sessions"]:
        return _admin_sessions(argv[1:])
    if argv[:1] == ["unlock"]:
        return _admin_unlock(argv[1:])
    if argv[:1] == ["device-key"]:
        return _admin_device_key(argv[1:])
    if len(argv) != 2 or argv[0] != "create":
        print("usage: onetrace-console admin create <username>", file=sys.stderr)
        return 2
    username = argv[1]

    password = sys.stdin.readline().rstrip("\n")
    if not password:
        print("refusing: no password was read from stdin", file=sys.stderr)
        return 1

    config = _config_or_none(writes=True)
    if config is None:
        return 1
    store_root = Path(config.store_root).resolve()
    on = _cli_audit(config)
    if on is None:
        return 1
    accounts = AccountStore(store_root / ACCOUNTS_DIRNAME)
    try:
        accounts.create(username, password.encode("utf-8"))
    except AccountError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    from onetrace_console.audit import CLI, AuditRefused

    try:
        on.record(CLI, "account.created", username, {})
    except AuditRefused as e:
        #: An account grants access: not made where its making cannot be recorded.
        accounts.forget(username)
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"created account {username!r}")
    return 0


def _admin_sessions(argv: list[str]) -> int:
    """`onetrace-console admin sessions end <account>` or `<tenant id>/<object id>`: ends every session of that
    person. A running console's sessions are in its memory, so a time is written under the store's
    root (`session_ends`), and the console reads it at each request and ends every session of that person made by
    then, through its index: each gets the sign-in page at its next request."""
    from pathlib import Path

    from onetrace_console.accounts import _USERNAME_RE, AccountStore
    from onetrace_console.serve import ACCOUNTS_DIRNAME
    from onetrace_console.session_ends import DIRNAME, ENTRA_KEY_SAID, EndTimes, entra_key

    if len(argv) != 2 or argv[0] != "end":
        print("usage: onetrace-console admin sessions end <account> | <tenant id>/<object id>", file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    store_root = Path(config.store_root).resolve()
    asked = argv[1]
    if "/" in asked:
        principal = entra_key(asked)
        if principal is None:
            print(f"refusing: {asked!r} is not an Entra ID key: {ENTRA_KEY_SAID}", file=sys.stderr)
            return 1
        unchecked = not config.scim.get("enabled")
        if not unchecked:
            #: With SCIM on, a key its records do not hold (active, inactive or deleted) is refused as unknown,
            #: never ended silently.
            from onetrace_console.scim import Users

            users = Users(store_root)
            object_id = principal.split("/", 1)[1]
            if not users.by_external_id(object_id) and users.tombstone(object_id) is None:
                print(f"refusing: SCIM's records hold no User with the object id of {principal!r}", file=sys.stderr)
                return 1
    else:
        if not (_USERNAME_RE.match(asked) and AccountStore(store_root / ACCOUNTS_DIRNAME).exists(asked)):
            print(f"refusing: no account named {asked!r}", file=sys.stderr)
            return 1
        principal, unchecked = asked, False
    on = _cli_audit(config)
    if on is None:
        return 1
    from onetrace_console.audit import CLI

    at = EndTimes(store_root / DIRNAME).write(principal)
    #: Applied whether or not its entry could be appended; the command cannot know the count, so it keeps
    #: the end time it wrote, and the console, ending them, records how many.
    on.record(CLI, "sessions.ended", principal, {"end_time": at, "by": "admin sessions end"}, removes_access=True)
    print(f"ended every session of {principal!r}: each gets the sign-in page at its next request")
    if unchecked:
        print("SCIM is off, so this key could not be checked against a person: a well-formed key is taken as given.")
    return 0


def _admin_unlock(argv: list[str]) -> int:
    """`onetrace-console admin unlock <account>`: clears the account's sign-in ceiling. The time is
    written beside the accounts; a running console clears the ceiling at the account's next attempt."""
    from pathlib import Path

    from onetrace_console.accounts import AccountError, AccountStore
    from onetrace_console.serve import ACCOUNTS_DIRNAME

    if len(argv) != 1:
        print("usage: onetrace-console admin unlock <account>", file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    try:
        AccountStore(Path(config.store_root).resolve() / ACCOUNTS_DIRNAME).unlock(argv[0])
    except AccountError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"cleared the sign-in ceiling of {argv[0]!r}: new browsers may try its password again")
    return 0


def _admin_device_key(argv: list[str]) -> int:
    """`onetrace-console admin device-key rotate`: a new device key beside the accounts. Every device
    cookie made under the old one counts as none, in a running console too. The key is never shown."""
    from pathlib import Path

    from onetrace_console.device_cookie import rotate_key
    from onetrace_console.serve import ACCOUNTS_DIRNAME

    if argv != ["rotate"]:
        print("usage: onetrace-console admin device-key rotate", file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    rotate_key(Path(config.store_root).resolve() / ACCOUNTS_DIRNAME)
    print("rotated the device key: every device cookie has ended, and each browser signs in as a new one")
    return 0


def _token(argv: list[str]) -> int:
    """`onetrace-console token create <principal>` / `token revoke <id>`. Like
    `admin create`, this is CLI-only -- there is no web route that
    creates or revokes a token; see `tests/test_token_cli.py`.
    """
    from pathlib import Path

    from onetrace_console.ingester_tokens import TokenError, TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    config = _config_or_none(writes=True)
    if config is None:
        return 1
    store_root = Path(config.store_root).resolve()
    tokens = TokenStore(store_root / TOKENS_DIRNAME)
    from onetrace_console.audit import CLI, AuditRefused

    on = _cli_audit(config)
    if on is None:
        return 1

    if argv[:1] == ["create"] and (len(argv) == 2 or (len(argv) == 4 and argv[2] == "--team")):
        principal = argv[1]
        team = argv[3] if len(argv) == 4 else ""
        refused = _token_team_refusal(config, team)
        if refused:
            print(f"refusing: {refused}", file=sys.stderr)
            return 1
        try:
            record, raw = tokens.create(principal, team)
        except TokenError as e:
            print(f"refusing: {e}", file=sys.stderr)
            return 1
        try:
            on.record(CLI, "token.created", record.token_id, {"principal": principal, "team": team or None})
        except AuditRefused as e:
            #: Never shown, and taken back: a token is not made where its making cannot be recorded.
            tokens.forget(record.token_id)
            print(f"refusing: {e}", file=sys.stderr)
            return 1
        print(f"token id: {record.token_id}")
        if team:
            print(f"team: {team}")
        print(f"token (shown once, store it now): {raw}")
        return 0
    if len(argv) == 2 and argv[0] == "revoke":
        token_id = argv[1]
        if not tokens.revoke(token_id):
            print(f"refusing: no token with id {token_id!r}", file=sys.stderr)
            return 1
        #: A revoke removes access: it stands whether or not it could be recorded.
        on.record(CLI, "token.revoked", token_id, {}, removes_access=True)
        print(f"revoked token {token_id!r}")
        return 0
    print("usage: onetrace-console token create <principal> [--team <team>] | token revoke <id>", file=sys.stderr)
    return 2


def _run_assign(argv: list[str]) -> int:
    """`onetrace-console run assign --unassigned <team>` / `run assign <run key> <team>`:
    run with the console stopped. Each run given a team is keyed with it; the next start draws its pages under the new
    key, in its team's set, and its old address leads there for a person who can see it."""
    from dataclasses import replace
    from pathlib import Path

    from onetrace_console import team_assign
    from onetrace_console.config import TEAM_NAME_SAID
    from onetrace_console.store import TEAM_NAME, Store

    usage = "usage: onetrace-console run assign --unassigned <team> | run assign <run key> <team>"
    if len(argv) != 2:
        print(usage, file=sys.stderr)
        return 2
    config = _config_or_none(writes=True)
    if config is None:
        return 1
    which, team = argv
    if not config.teams:
        print("refusing: teams is not configured, so a run has no team to be given.", file=sys.stderr)
        return 1
    if not TEAM_NAME.match(team):
        print(f"refusing: {team!r} is not a team's name: {TEAM_NAME_SAID}.", file=sys.stderr)
        return 1
    if team not in config.teams:
        print(
            f"refusing: {team!r} is a team teams does not hold (it holds {', '.join(config.teams)}).", file=sys.stderr
        )
        return 1
    if team_assign.listening(config):
        print(
            f"refusing: something answers on {config.host}:{config.port}, the console's address. Stop the console, "
            f"then run this again: a run's key changes, and a running console would go on serving the old one.",
            file=sys.stderr,
        )
        return 1
    store_root = Path(config.store_root).resolve()
    store = Store(store_root / "store")
    if which == "--unassigned":
        runs = [r for r in store.runs() if not r.team]
        if not runs:
            print("no held run is without a team: nothing to assign.")
            return 0
    else:
        run = store.get_run(which)
        if run is None:
            print(f"refusing: no held run has the key {which!r}.", file=sys.stderr)
            return 1
        if run.team == team:
            print(f"run {which} is {team}'s already: nothing to move.")
            return 0
        runs = [run]
    on = _cli_audit(config)
    if on is None:
        return 1
    from onetrace_console.audit import CLI, AuditRefused

    rule = "run assign --unassigned" if argv[0] == "--unassigned" else "run assign"
    done = []
    for run in runs:
        new = team_assign.team_key(run, team)
        detail = {"from": run.team or None, "to": team, "rule": rule, "old_key": run.key, "new_key": new}
        try:
            #: Recorded before the run moves: a team given a run is a grant of access, never made unrecorded.
            on.record(CLI, "run.assigned", run.key, detail)
            done.append(team_assign.assign(store, store_root, replace(run), team))
        except (team_assign.AssignRefused, AuditRefused) as e:
            for got in done:
                print(f"{got.old_key} -> {got.new_key}: {got.old_team or 'no team'} -> {got.team}")
            print(f"refusing: {e}", file=sys.stderr)
            return 1
    for got in done:
        print(f"{got.old_key} -> {got.new_key}: {got.old_team or 'no team'} -> {got.team}")
    print(f"{len(done)} run{'s' if len(done) != 1 else ''} given to {team}; start the console to draw their pages.")
    return 0


def _token_team_refusal(config, team: str) -> str:
    """With `teams` configured, a token is bound to one of its teams when it is made, and without, to none.
    Empty when the binding asked for is the one the configuration allows."""
    from onetrace_console.config import TEAM_NAME_SAID
    from onetrace_console.store import TEAM_NAME

    if not config.teams:
        return "teams is not configured, so a token is bound to no team: make it without --team." if team else ""
    held = ", ".join(config.teams)
    if not team:
        return (
            f"teams is configured, so every ingester token is bound to one team, the team of every run it delivers. "
            f"Give it one: token create <principal> --team <team> (the teams: {held})."
        )
    if not TEAM_NAME.match(team):
        return f"--team is {team!r}, not a team's name: {TEAM_NAME_SAID}."
    if team not in config.teams:
        return f"--team is {team!r}, a team teams does not hold (it holds {held})."
    return ""


def _export_static(argv: list[str]) -> int:
    """`onetrace-console export-static`: see `onetrace_console.export_static`.
    The store is the configured one, as `admin` and `token` read it."""
    import argparse
    from pathlib import Path

    from onetrace_console.export_static import ExportError, export, fence_hits

    parser = argparse.ArgumentParser(prog="onetrace-console export-static")
    parser.add_argument("--runs", nargs="+", required=True, metavar="KEY")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--fence-terms", type=Path, default=None)
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    config = _config_or_none()
    if config is None:
        return 1
    try:
        files = export(Path(config.store_root).resolve(), args.runs, args.out)
        fence = fence_hits(args.out, args.fence_terms) if args.fence_terms else None
    except ExportError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    for rel, digest in files.items():
        print(f"{digest}  {rel}")
    print("project ids: 0")
    print("external requests: 0")
    if fence is None:
        print(
            "fence scan: not run here -- its terms never come to this machine; it runs over "
            "this folder before anything is hosted"
        )
        return 0
    print(f"fence scan: {len(fence)}")
    for hit in fence:
        print(f"  {hit}", file=sys.stderr)
    return 1 if fence else 0


if __name__ == "__main__":
    raise SystemExit(main())
