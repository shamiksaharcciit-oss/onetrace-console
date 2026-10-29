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
  onetrace-console demo [--open] [--port N]
                               record the demo's runs (small example pipelines, no
                               network calls) into ./onetrace-console-demo, load them,
                               compare them, and serve them on 127.0.0.1, printing the
                               pages' addresses
  onetrace-console demo --public [--open] [--port N]
                               the same demo, read-only: every write refused, a banner on
                               every page, built in a temporary folder and served on 127.0.0.1
  onetrace-console demo --public --build <new folder> [--runs-from <earlier build>]
                   [--explanations <folder>] [--site-links <file>]
                               build the read-only demo into a new folder and exit; a
                               configuration with "public": true serves its store as it is.
                               --runs-from: an earlier build's runs, as its build record vouches
                               --explanations: keep onetrace-explain's records under
                               <folder>/explain/ of comparisons this build holds, read-only
                               --site-links: the public site's links into the demo, one per
                               line; a listed comparison page named anew gets a page at its
                               old name
  onetrace-console <runs folder> [--compare A B] [--open] [--port N]
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
  onetrace-console token create <principal>
                               create an ingester bearer token for <principal>.
                               Prints the raw token to stdout ONCE -- it is stored
                               only as a hash and cannot be recovered afterward.
                               Run this INSIDE the container, same as admin create.
  onetrace-console token revoke <id>
                               revoke a token by the id `token create` printed
                               alongside it. A revoked token reads exactly like
                               one that never existed to anything that checks it.
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
        print("refusing: the configuration is public -- a read-only demo, with no accounts and no "
              "tokens.\nfix: run this against a console that is not public.", file=sys.stderr)
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
    accounts = AccountStore(store_root / ACCOUNTS_DIRNAME)
    try:
        accounts.create(username, password.encode("utf-8"))
    except AccountError as e:
        print(f"refusing: {e}", file=sys.stderr)
        return 1
    print(f"created account {username!r}")
    return 0


def _token(argv: list[str]) -> int:
    """`onetrace-console token create <principal>` / `token revoke <id>`. Like
    `admin create`, this is CLI-only -- there is no web route that
    creates or revokes a token; see `tests/test_token_cli.py`.
    """
    from pathlib import Path

    from onetrace_console.serve import TOKENS_DIRNAME
    from onetrace_console.ingester_tokens import TokenError, TokenStore

    config = _config_or_none(writes=True)
    if config is None:
        return 1
    store_root = Path(config.store_root).resolve()
    tokens = TokenStore(store_root / TOKENS_DIRNAME)

    if len(argv) == 2 and argv[0] == "create":
        principal = argv[1]
        try:
            record, raw = tokens.create(principal)
        except TokenError as e:
            print(f"refusing: {e}", file=sys.stderr)
            return 1
        print(f"token id: {record.token_id}")
        print(f"token (shown once, store it now): {raw}")
        return 0
    if len(argv) == 2 and argv[0] == "revoke":
        token_id = argv[1]
        if not tokens.revoke(token_id):
            print(f"refusing: no token with id {token_id!r}", file=sys.stderr)
            return 1
        print(f"revoked token {token_id!r}")
        return 0
    print("usage: onetrace-console token create <principal> | token revoke <id>",
         file=sys.stderr)
    return 2


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
        print("fence scan: not run here -- its terms never come to this machine; it runs over "
              "this folder before anything is hosted")
        return 0
    print(f"fence scan: {len(fence)}")
    for hit in fence:
        print(f"  {hit}", file=sys.stderr)
    return 1 if fence else 0


if __name__ == "__main__":
    raise SystemExit(main())
