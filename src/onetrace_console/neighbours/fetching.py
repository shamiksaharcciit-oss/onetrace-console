"""The local model's fetch, in the background: the confirm button starts it and the setup page shows it.

Turning neighbours on with a local model fetches its files (about 90 MB or 133 MB), up to 120 s per file.
Done inside the request, the page showed nothing until it was over. Now the POST starts the fetch in a
thread of its own and answers at once; the setup page reads this module's state and says "Fetching
<model>: <n> of <m> files checked", refreshing itself (a `<meta>` refresh, no script) until the setting
is written. One fetch at a time per store: a second confirm while one runs is answered "already
fetching", and starts nothing.

A console that stops mid-fetch keeps the files already checked (`embedder.fetch` writes each file
atomically, after its sha256 matched); the next confirm checks each file by its sha256 again and fetches
only what is missing or does not match. Nothing here is kept on disk: a restart forgets a fetch, and the
page reads as off until the person confirms again.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path

#: Seconds between the setup page's own refreshes while a fetch runs.
REFRESH_SECONDS = 2


@dataclass
class Fetch:
    """One store's fetch: the model, how many of its files are checked, and how it ended."""
    model: str
    total: int
    checked: int = 0
    running: bool = True
    refused: str = ""             # the refusal, naming the file, once it failed
    thread: threading.Thread | None = field(default=None, repr=False)


_LOCK = threading.Lock()
_FETCHES: dict[str, Fetch] = {}


def _key(store) -> str:
    return str(Path(store.root).resolve())


def now(store) -> Fetch | None:
    """This store's fetch, running or last ended unsuccessfully; None where there is none to show."""
    with _LOCK:
        return _FETCHES.get(_key(store))


def running(store) -> bool:
    got = now(store)
    return got is not None and got.running


def forget(store) -> None:
    """Drop an ended fetch's state (its refusal shown once a later attempt starts or succeeds)."""
    with _LOCK:
        got = _FETCHES.get(_key(store))
        if got is not None and not got.running:
            del _FETCHES[_key(store)]


class AlreadyFetching(Exception):
    """A fetch for this store is running; nothing new was started."""


def start(store, chosen: dict, *, who: str, confirmed: str, after=None, get=None) -> Fetch:
    """Start turning neighbours on with the local model `chosen` in a background thread: the files
    fetched and checked (`embedder.fetch`, reporting each checked file), then the setting written
    (`settings.turn_on`, which checks them again), then `after()` (the server's refresh of the pages).

    The confirmation is checked here, before anything starts, so a wrong one refuses at once with
    nothing fetched. `AlreadyFetching` where one runs for this store."""
    from onetrace_console.neighbours import embedder, settings
    if confirmed != settings.confirmation(chosen):
        raise embedder.Refused("the confirmation does not name this embedder; nothing was turned on")
    model = embedder.MODELS[chosen["model"]]
    key = _key(store)
    with _LOCK:
        got = _FETCHES.get(key)
        if got is not None and got.running:
            raise AlreadyFetching(got.model)
        state = Fetch(model=model.name, total=len(model.files))
        _FETCHES[key] = state
    extra = {"get": get} if get else {}

    def progress(n: int, m: int) -> None:
        with _LOCK:
            state.checked, state.total = n, m

    def work() -> None:
        import sys
        import traceback
        try:
            embedder.fetch(embedder.models_root(store), model, progress=progress, **extra)
            settings.turn_on(store, chosen, who=who, confirmed=confirmed, **extra)
        except embedder.Refused as e:
            with _LOCK:
                state.refused, state.running = str(e), False
            return
        except OSError as e:
            from onetrace_console.oserror import said
            with _LOCK:
                state.refused, state.running = said(e), False
            return
        except Exception as e:  # noqa: BLE001 - said on the page, and logged
            traceback.print_exc(file=sys.stderr)
            with _LOCK:
                state.refused, state.running = f"{type(e).__name__}: {e}", False
            return
        with _LOCK:
            if _FETCHES.get(key) is state:
                del _FETCHES[key]
            state.running = False
        if after is not None:
            try:
                after()
            except Exception:  # noqa: BLE001 - the setting is written; the pages draw on the next refresh
                traceback.print_exc(file=sys.stderr)

    state.thread = threading.Thread(target=work, name=f"neighbours-fetch-{model.name}", daemon=True)
    state.thread.start()
    return state
