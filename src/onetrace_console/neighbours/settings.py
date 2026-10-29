"""Whether neighbours are on for a store, with which embedder, and who confirmed it: one file in the
store's neighbours/ folder, `setting.json`. No file, or one this version does not read: off.

Turning on is one confirmed act (`turn_on`): the confirmation names the embedder (the model and its
revision, or the endpoint and its model) and says that kept inputs will be embedded, and the file keeps
those words as they were confirmed. For the local model its files are fetched then, each checked by its
sha256 (`embedder.fetch`), and the setting is written only once they all match. Turning off removes the
file; the embedder's files and the recorded embedding runs stay, and say nothing until it is on again.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

FORMAT = "onetrace-console-neighbours-setting/0.1"
FILE = "setting.json"


def _path(store) -> Path:
    from onetrace_console.neighbours import FOLDER
    return Path(store.root) / FOLDER / FILE


def confirmation(chosen: dict) -> str:
    """The words a person confirms, naming what will see the kept inputs and where it runs."""
    if chosen.get("kind") == "endpoint":
        return (f"Kept inputs and kept outputs will be sent to the endpoint {chosen['base_url']} "
                f"(model {chosen['model']}), which you named, to be embedded there. Its files are not "
                f"fetched or checked by this console.")
    from onetrace_console.neighbours.embedder import MODELS
    m = MODELS[chosen["model"]]
    return (f"The model {m.repo} at revision {m.revision} will be fetched once to this machine, each file "
            f"checked by its sha256, and kept inputs and kept outputs will be embedded on this machine.")


def read(store) -> dict | None:
    """The setting, where neighbours are on; None where they are off."""
    try:
        from onetrace_console.bounded_json import load_json_bounded
        got = load_json_bounded(_path(store).read_text(encoding="utf-8"), FILE)
    except (OSError, ValueError, UnicodeDecodeError, RecursionError):
        return None
    if not isinstance(got, dict) or got.get("format") != FORMAT or not isinstance(got.get("embedder"), dict):
        return None
    return got


def choose(form: dict) -> dict:
    """The embedder a setup form names: the local default, the local alternate, or an endpoint."""
    from onetrace_console.neighbours.embedder import DEFAULT, MODELS, Refused, endpoint_problem
    kind = form.get("embedder", DEFAULT)
    if kind in MODELS:
        return {"kind": "local", "model": kind}
    if kind == "endpoint":
        base_url, model = form.get("base_url", "").strip(), form.get("model", "").strip()
        problem = endpoint_problem(base_url, model)
        if problem:
            raise Refused(problem)
        return {"kind": "endpoint", "base_url": base_url.rstrip("/"), "model": model}
    raise Refused(f"no embedder is named {kind!r}")


def turn_on(store, chosen: dict, *, who: str, confirmed: str, get=None) -> dict:
    """Turn neighbours on with `chosen`, after `confirmed` -- the exact words `confirmation` gives for
    it -- fetching and checking the local model's files first. Refused, with nothing written, otherwise."""
    from onetrace_console.neighbours import embedder
    from onetrace_console.store import _atomic_write
    said = confirmation(chosen)
    if confirmed != said:
        raise embedder.Refused("the confirmation does not name this embedder; nothing was turned on")
    if chosen["kind"] == "local":
        model = embedder.MODELS[chosen["model"]]
        embedder.fetch(embedder.models_root(store), model, **({"get": get} if get else {}))
    entry = {"format": FORMAT, "embedder": chosen, "who": who, "confirmed": said,
             "when": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path = _path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, (json.dumps(entry, indent=1, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8"))
    return entry


def turn_off(store) -> bool:
    path = _path(store)
    had = path.is_file()
    path.unlink(missing_ok=True)
    return had
