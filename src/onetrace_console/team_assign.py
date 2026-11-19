"""Assignment on arrival: with `teams` configured, every run has exactly one team, and nothing the
uploader writes chooses it.

- **Rule 1:** a run's team is its delivering ingester token's. Every token is bound to one team when it is made
  (`token create <principal> --team <team>`), and a console with a live token bound to none, or to a team it does not
  hold, does not start.
- **Rule 3:** a folder console's runs are its `folder_team`'s (`config.folder_team`).
- **Rule 4:** no run without a team. A console holding a run with none does not start, and says how many and the
  command that assigns them (`run assign --unassigned <team>`).

`start_refusal` is what the console checks at start, before anything is drawn.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from onetrace_console.config import TEAM_NAME_SAID, Config
from onetrace_console.store import TEAM_NAME, Store


@dataclass(frozen=True)
class Refusal:
    message: str
    fix: str


#: Said at every start where teams are configured and sign-in is off: nothing asks who a person is,
#: so nothing can scope them.
SIGN_IN_OFF = (
    "WARNING: teams is configured and sign-in is off, so teams scope nothing: this machine's user reads every team. "
    "Turn sign-in on (sign_in.method oidc) to scope runs to teams."
)


#: The page a person in no team is answered with, whatever they ask for: it names no team, and is
#: the same for every path, so it says nothing of what is there.
NO_TEAM = "You are in no team. Ask your administrator to add you."


def no_team_page() -> str:
    from onetrace_console.render import _document
    from onetrace_console.words import escape

    return _document("No team", f'<div class="cp" data-page="no-team"><h1>No team</h1><p>{escape(NO_TEAM)}</p></div>')


def sign_in_off(config: Config) -> bool:
    """Teams configured, and sign-in off."""
    return bool(config.teams) and not (config.sign_in or {}).get("enabled")


def sign_in_refusal(config: Config) -> Refusal | None:
    """Teams with the console's own accounts (`sign_in.method` `local`) refuse to start: a local account cannot be in a
    team, so every person would be in none."""
    sign_in = config.sign_in or {}
    if config.teams and sign_in.get("enabled") and sign_in.get("method", "local") == "local":
        return Refusal(
            "teams is configured and sign_in.method is local. A team is joined through Entra ID (its app roles, or "
            "SCIM's Groups); a local account cannot be in a team.",
            "set sign_in.method to oidc and configure sign-in through Microsoft Entra ID, or remove teams.",
        )
    return None


def open_ingest_refusal(config: Config, store_root: Path, *, folder: bool) -> Refusal | None:
    """Teams with no live ingester token refuse to start, unless the console reads a folder into its `folder_team`: with
    no token, delivery is open to any caller, and no token names the team a delivered run would take."""
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    if not config.teams or folder:
        return None
    where = store_root / TOKENS_DIRNAME
    live = [r for r in TokenStore(where).records() if not r.revoked] if where.is_dir() else []
    if live:
        return None
    return Refusal(
        "teams is configured and no ingester token is live, so delivery would be open to any caller and no token "
        "names the team a delivered run takes.",
        "make a token bound to a team with onetrace-console token create <principal> --team <team>, or read a "
        "folder whose runs are one team's (folder_team).",
    )


def token_refusal(config: Config, store_root: Path) -> Refusal | None:
    """Every live ingester token bound to a team this console holds, or the tokens that are not, each by its id."""
    from onetrace_console.ingester_tokens import TokenStore
    from onetrace_console.serve import TOKENS_DIRNAME

    if not config.teams or not (store_root / TOKENS_DIRNAME).is_dir():
        return None
    live = [r for r in TokenStore(store_root / TOKENS_DIRNAME).records() if not r.revoked]
    unbound = [r for r in live if not r.team]
    if unbound:
        return Refusal(
            f"teams is configured, and {_count(len(unbound), 'live ingester token', 'is', 'are')} bound to no team: "
            f"{', '.join(r.token_id for r in unbound)}. A run is its delivering token's team's, so a token bound to "
            f"none could deliver into no team.",
            "replace each with a token bound to its team, then revoke it: "
            + "; ".join(
                f"onetrace-console token create {r.principal} --team <team>, then token revoke {r.token_id}"
                for r in unbound
            )
            + ".",
        )
    misnamed = [r for r in live if not TEAM_NAME.match(r.team)]
    if misnamed:
        return Refusal(
            "the team of "
            + ", ".join(f"ingester token {r.token_id} is {r.team!r}" for r in misnamed)
            + f", not a team's name: {TEAM_NAME_SAID}.",
            "replace each with a token bound to a team teams holds, then revoke it: "
            + "; ".join(
                f"onetrace-console token create {r.principal} --team <team>, then token revoke {r.token_id}"
                for r in misnamed
            )
            + ".",
        )
    unheld = [r for r in live if r.team not in config.teams]
    if unheld:
        return Refusal(
            ", ".join(f"ingester token {r.token_id} is bound to {r.team!r}" for r in unheld)
            + f", a team teams does not hold (it holds {', '.join(config.teams)}).",
            "add the team to teams, or replace each with a token bound to a team teams holds, then revoke it: "
            + "; ".join(
                f"onetrace-console token create {r.principal} --team <team>, then token revoke {r.token_id}"
                for r in unheld
            )
            + ".",
        )
    return None


def run_refusal(config: Config, store: Store) -> Refusal | None:
    """No held run without a team, nor with one this console does not hold (rule 4)."""
    if not config.teams:
        return None
    runs = store.runs()
    none = [r for r in runs if not r.team]
    if none:
        return Refusal(
            f"teams is configured, and {_count(len(none), 'held run', 'has', 'have')} no team. Every run is one team's, so a run "
            f"with none would be no one's but an admin's.",
            "stop the console and give them one with onetrace-console run assign --unassigned <team>, then start "
            "it again.",
        )
    unheld = sorted({r.team for r in runs if r.team not in config.teams})
    if unheld:
        count = sum(r.team in unheld for r in runs)
        return Refusal(
            f"{_count(count, 'held run', 'has', 'have').capitalize()} a team teams does not hold: {', '.join(unheld)}.",
            f"add {', '.join(unheld)} to teams, or move each run with onetrace-console run assign <run key> <team>.",
        )
    return None


def folder_refusal(config: Config) -> Refusal | None:
    """A folder console with teams takes its runs into its `folder_team` (rule 3), which the configuration checked
    names a team it holds."""
    if config.teams and not config.folder_team:
        return Refusal(
            "teams is configured and folder_team is not. A folder console takes every run it reads into one team, "
            "and nothing names it.",
            "set folder_team in the configuration file to the team the watched folder's runs belong to.",
        )
    return None


def _count(n: int, noun: str, one: str, many: str) -> str:
    return f"1 {noun} {one}" if n == 1 else f"{n} {noun}s {many}"


# ------------------------------------------------------------------ run assign


def team_key(run, team: str) -> str:
    """The key `run` has as `team`'s: keyed by its folder too where it is now (`store.folder_key`)."""
    from onetrace_console.store import folder_key, run_key

    by_folder = bool(run.folder) and run.key == folder_key(run.run_id, run.chain_head, run.folder, run.team)
    if by_folder:
        return folder_key(run.run_id, run.chain_head, run.folder, team)
    return run_key(run.run_id, run.chain_head, team)


@dataclass(frozen=True)
class Assigned:
    """One run given a team: its key before and after, and the team it was and is."""

    old_key: str
    new_key: str
    old_team: str
    team: str


def assign(store: Store, store_root: Path, run, team: str) -> Assigned:
    """Give `run` the team `team` and its key as that team's: its record, what is kept about it by
    its key, the comparisons and kept records that name it, and the map from its old key to the new. Its pages, under
    the old key, are taken away, and so is every other page, in every set, that names the old key (a pipeline's
    choose page, an incidents page): a set the run has left would serve it otherwise, since the next start draws no
    page there for it. The next start draws what still applies, under the new key, in its team's set."""
    import shutil

    from onetrace_console.serve import PAGES_DIRNAME

    old, new = run.key, team_key(run, team)
    if new != old and store.get_run(new) is not None:
        raise AssignRefused(f"run {old} is held in {team} already, as {new}.")
    store.rekey(run, new, team)
    pages = store_root / PAGES_DIRNAME
    for set_root in (pages, *((pages / "t").iterdir() if (pages / "t").is_dir() else ())):
        shutil.rmtree(set_root / "runs" / old, ignore_errors=True)
    #: Every set's other pages, the team sets' among them (they are under the all-teams set's folder).
    named = old.encode("ascii")
    for page in pages.rglob("*.html") if pages.is_dir() else ():
        if page.is_file() and named in page.read_bytes():
            page.unlink()
    return Assigned(old, new, run.team, team)


class AssignRefused(RuntimeError):
    """`run assign` refused: said, and nothing changed."""


def listening(config: Config) -> bool:
    """Whether something answers on the configured host and port: a console started from this configuration, as far
    as this machine can tell."""
    import socket

    host = "127.0.0.1" if config.host in ("0.0.0.0", "", "::") else config.host
    try:
        with socket.create_connection((host, config.port), timeout=1):
            return True
    except OSError:
        return False
