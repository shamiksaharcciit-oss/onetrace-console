"""Two run folders that carry the same run and chain head: copies of one run, or two that differ.

Runs are folders, not chain heads. A folder load reads every run folder on its own and stores each
under its own key (`store.folder_key`), so each has its own reading and its own page. What this
module says of two such folders is only what their files say: the same files, byte for byte (the
same paths, each with the same object key), or not. It never says which of the two is right.
"""
from __future__ import annotations

from onetrace_console.store import Store, StoredRun

#: The incident's words, and the run page's, where the two folders' files differ.
DIFFER = "Two folders share a chain head but their contents differ"


def folder_named(run: StoredRun) -> str:
    """The run's folder, as a sentence names it; its run name where it has no folder."""
    return run.folder or run.run_id


def twins(run: StoredRun, store: Store) -> list[tuple[StoredRun, bool]]:
    """Every other stored run with the same run and chain head as `run`, each with whether their
    files are the same, byte for byte -- in folder order."""
    mine = sorted(run.listing)
    found = [(r, sorted(r.listing) == mine) for r in store.runs()
             if r.key != run.key and r.run_id == run.run_id and r.chain_head == run.chain_head]
    return sorted(found, key=lambda pair: (folder_named(pair[0]), pair[0].key))


def differ_said(run: StoredRun, other: StoredRun) -> str:
    """The incident's quoted words: the rule's sentence, naming both folders, A to Z."""
    a, b = sorted((folder_named(run), folder_named(other)))
    return f"{DIFFER}: the folders {a} and {b}"


def sentences(run: StoredRun, store: Store) -> list[str]:
    """What the run's page says of its twins, one sentence each, with each folder's own "Records
    agree" reading in the runs list's words (`records.said`); none where it has none."""
    from onetrace_console.records import said
    out = []
    for other, same in twins(run, store):
        mine, theirs = said(run, store), said(other, store)
        if same:
            out.append(f"The same files as the folder {folder_named(other)}: this folder, "
                       f"{folder_named(run)} ({mine}), is a copy of the folder "
                       f"{folder_named(other)} ({theirs}), and each is read on its own.")
        else:
            out.append(f"{DIFFER}: this folder, {folder_named(run)} ({mine}), and the folder "
                       f"{folder_named(other)} ({theirs}). Each is read on its own.")
    return out
