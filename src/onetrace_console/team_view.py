"""A team's view of the store: its runs, its comparisons and what is kept about them, and nothing else.

`TeamView(store, team)` answers what a store answers, for one team's records alone:

- **Runs and comparisons.** `runs()`, `get_run()`, `runs_with_id()`, `comparisons()` and `get_comparison()` answer
  the team's own. For another team's key they answer `None`, exactly as for a key no team holds: the key is looked up
  in the team's own key set, held in memory, first, and an outside key and an unknown key both miss it and go no
  further. A key's team cannot be read from its shape.
- **Kept records** (`get_kept`, `get_drift`): a reference, a verdict, a profile, a pair's linked check and a drift
  report each name the runs they are of; the view answers one only where every run it names is the team's, and
  `None` otherwise, as for a record never kept. It writes one only on the same terms.
- **Kept files** (`kept_path`, `kept_names`): a benchmark's mark, what was kept beside a run, expectations declared
  after it, and a comparison's explanation, each kept by its owner's key; the view answers the team's owners alone.
- **The neighbours' batches** are kept in a folder of the team's own, so no team's inputs are embedded beside
  another's.
- **What is not a team's** is passed through: objects (content-addressed, served by no key, and written by a page
  that keeps a derived one), a run's missing objects, one reading of the store. Within a reading, the view keeps what
  the pages compute in a cache of its own, apart from the store's and every other team's.
- **A record no one can read** names no team, so a team's view holds none: only the all-teams set says how many the
  store holds.

The view has no `root`: a module that reads a folder under the store's root by path would read every team's, so
none may (`tests/test_team_view.py` holds the source to it).
"""

from __future__ import annotations

from pathlib import Path

from onetrace_console.store import TEAM_NAME, Store, StoredRun


def view_of(store: Store, team: str) -> TeamView:
    """The team's view, made once in a reading of the store (`Store.reading`) and kept in it; a write forgets it with
    the rest of what was read. Outside a reading, made afresh."""
    read = store._read()
    if read is None:
        return TeamView(store, team)
    views = read.setdefault("team views", {})
    if team not in views:
        views[team] = TeamView(store, team)
    return views[team]


class TeamView:
    #: A record no one can read names no team (above).
    unreadable_runs: tuple[str, ...] = ()
    unreadable_run_keys: tuple[str, ...] = ()
    unreadable_comparisons: tuple[str, ...] = ()
    unreadable_comparison_keys: tuple[str, ...] = ()
    #: The team's runs and rules the last `incidents.derive` over this view could not raise incidents for, as a
    #: store's; none before it has derived any.
    underived: tuple[str, ...] = ()

    def __init__(self, store: Store, team: str) -> None:
        if not TEAM_NAME.match(team):
            raise ValueError(f"{team!r} is not a team's name")
        self._store = store
        self.team = team
        self._runs = {r.key: r for r in store.runs() if r.team == team}
        self._comparisons = {c.key: c for c in store.comparisons() if c.run_a in self._runs and c.run_b in self._runs}

    # -------------------------------------------------------------- runs and comparisons
    def runs(self) -> tuple[StoredRun, ...]:
        return tuple(self._runs.values())

    def get_run(self, key: str) -> StoredRun | None:
        return self._runs.get(key)

    def runs_with_id(self, run_id: str) -> tuple[StoredRun, ...]:
        return tuple(r for r in self._runs.values() if r.run_id == run_id)

    def comparisons(self) -> tuple:
        return tuple(self._comparisons.values())

    def get_comparison(self, key: str):
        return self._comparisons.get(key)

    # -------------------------------------------------------------- kept records
    def _all_ours(self, record: dict | None) -> bool:
        """Every run the record names is the team's; a record that names none is no team's."""
        if not isinstance(record, dict):
            return False
        named: list = []
        for field in ("runs",):
            if isinstance(record.get(field), list):
                named += record[field]
        for field in ("run", "caller", "callee"):
            if isinstance(record.get(field), str):
                named.append(record[field])
        return bool(named) and all(isinstance(k, str) and k in self._runs for k in named)

    def get_kept(self, kind: str, key: str) -> dict | None:
        record = self._store.get_kept(kind, key)
        return record if self._all_ours(record) else None

    def put_kept(self, kind: str, key: str, record: dict) -> None:
        if not self._all_ours(record):
            raise ValueError(f"a {kind} record names a run outside team {self.team!r}")
        self._store.put_kept(kind, key, record)

    def get_drift(self, key: str) -> dict | None:
        record = self._store.get_drift(key)
        return record if self._all_ours(record) else None

    def put_drift(self, key: str, record: dict) -> None:
        if not self._all_ours(record):
            raise ValueError(f"a drift record names a run outside team {self.team!r}")
        self._store.put_drift(key, record)

    # -------------------------------------------------------------- kept files
    def _owns(self, folder: str, owner: str, kind: str | None = None) -> bool:
        kind = Store.OWNED_FOLDERS.get(folder, kind)
        if kind is None:
            return False
        return owner in (self._runs if kind == "run" else self._comparisons)

    def kept_path(self, folder: str, owner: str, name: str | None = None, *, kind: str | None = None) -> Path | None:
        if not self._owns(folder, owner, kind):
            return None
        return self._store.kept_path(folder, owner, name, kind=kind)

    def kept_names(self, folder: str) -> list[str]:
        """A run's folder names each file by the run's key; a comparison's (`x`) by the first part of its key, so a
        name there is the team's where one of its comparisons' keys begins with it."""
        if Store.OWNED_FOLDERS.get(folder) == "comparison":
            return [n for n in self._store.kept_names(folder) if any(k.startswith(n) for k in self._comparisons)]
        return [n for n in self._store.kept_names(folder) if self._owns(folder, n.split(".", 1)[0])]

    def neighbours_root(self) -> Path:
        return self._store.neighbours_root().parent / "neighbours-by-team" / self.team

    def noise_folder(self) -> Path:
        """The whole console's noise fields: an admin marks a pipeline's for every team, and a field names a step and
        a path, never a run."""
        return self._store.noise_folder()

    def has_decision_exports(self) -> bool:
        return self._store.has_decision_exports()

    # -------------------------------------------------------------- what is no team's
    def _read(self):
        """A reading's cache of the view's own, kept in the store's reading apart from the store's own (which holds
        every team's) and from every other team's, so what the pages compute once per reading (verdicts, incidents,
        benchmarks) is computed once for the team; a write forgets it with the rest. None outside a reading."""
        read = self._store._read()
        if read is None:
            return None
        return read.setdefault("team readings", {}).setdefault(self.team, {})

    def _forget(self) -> None:
        self._store._forget()

    def get(self, key: str) -> bytes:
        return self._store.get(key)

    def put(self, data: bytes) -> str:
        return self._store.put(data)

    def has(self, key: str) -> bool:
        return self._store.has(key)

    def missing(self, run: StoredRun) -> tuple[str, ...]:
        return self._store.missing(run)

    def reading(self):
        return self._store.reading()
