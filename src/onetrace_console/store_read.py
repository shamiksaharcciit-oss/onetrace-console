"""The store read interface: three questions a program outside the console asks of a console store.

Read-only. It opens a store root (the folder `--store` names: the store's own `store/` folder and the
run index `run_index.json` beside it), writes nothing there, runs no check, no comparison and no
model, and reads no kept input except to ask the neighbours extra's stored vectors.

    from onetrace_console import store_read
    reader = store_read.open_store("path/to/store-root")
    reader.runs_by_config("retrieve", "sha256:...")      # a stage's exact configuration
    reader.runs_by_model_files("sha256:...")             # a model-call record's model files
    reader.neighbours(run_key)                           # near kept inputs, where the extra is on

Versioned with the store: each answer is read from the run index, and the interface reads exactly the
index formats in `INDEX_FORMATS`. A store whose index is another format, or that has none, is refused
with the reason, never read as if it were one this version knows; an earlier format's reason says who
writes it again, in the search page's own two sentences. `VERSION` names the interface; it
changes when an answer's shape does. docs/store_read.md says the same for a reader of the docs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from onetrace_console import run_index
from onetrace_console.bounded_json import load_json_bounded

VERSION = "onetrace-console-store-read/1"
#: The run index formats this version reads.
INDEX_FORMATS = (run_index.FORMAT,)
#: The model-call record field the model-files question asks, by the index's name for it, and the
#: states that name the files.
FILES_FIELD, FILES_STATES = "weights", ("observed", "declared")


class Refused(Exception):
    """A question this store cannot answer here, with the reason as its message."""


@dataclass(frozen=True)
class Found:
    """One run's answer: the run, the step that matched, and what the record says there."""
    run_key: str
    run_id: str
    pipeline: str
    step: str
    value: str
    #: For a model-files answer, the value's state as the record gives it ("observed" or "declared");
    #: for a neighbour, how the nearness was got ("record" or "embedder"); otherwise "".
    state: str = ""
    #: For a neighbour: the input it is near by, and the nearness.
    name: str = ""
    nearness: float | None = None


def open_store(store_root) -> "Reader":
    """The reader over a store root. Refused where the root holds no run index, or one of a format
    this version does not read; an earlier format with its own reason, a local console's and a public
    one's, as the search page says them."""
    root = Path(store_root)
    path = root / run_index.FILE_NAME
    if not path.is_file():
        raise Refused(f"{root} holds no run index ({run_index.FILE_NAME}): the console writes it when it "
                      f"draws its pages, so start the console on this store once")
    try:
        index = load_json_bounded(path.read_text(encoding="utf-8"), run_index.FILE_NAME)
    except OSError as e:
        from onetrace_console.oserror import said
        raise Refused(f"{path} cannot be read as a run index: {said(e)}") from None
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        raise Refused(f"{path} cannot be read as a run index: {e}") from None
    found = index.get("format") if isinstance(index, dict) else None
    if found not in INDEX_FORMATS and isinstance(found, str) and run_index.earlier(found):
        from onetrace_console import __version__, search_page
        raise Refused(f"{path} is {json.dumps(found)}, an earlier format than the {', '.join(INDEX_FORMATS)} this "
                      f"interface ({VERSION}) reads. On a local console: "
                      f"{search_page.EARLIER_LOCAL.format(found=found)} On a public console: "
                      f"{search_page.EARLIER_PUBLIC.format(found=found, version=__version__)}")
    if found not in INDEX_FORMATS:
        raise Refused(f"{path} is {json.dumps(found)}, and this interface ({VERSION}) reads "
                      f"{', '.join(INDEX_FORMATS)} only")
    return Reader(root, index)


class Reader:
    """Answers from one store root's run index, read once when opened."""

    def __init__(self, root: Path, index: dict):
        self.root, self.index = root, index

    def _runs(self):
        return [r for r in self.index.get("runs", []) if isinstance(r, dict)]

    def runs_by_config(self, step: str, config_digest: str) -> list[Found]:
        """The runs whose step `step` records exactly this configuration digest (its instrument's
        `config_digest`), in the console's order of runs. `step` "*" asks every step."""
        out = []
        for r in self._runs():
            for s in r.get("steps", []):
                digest = (s.get("instrument") or {}).get("config_digest", "")
                if digest and digest == config_digest and step in ("*", s.get("name")):
                    out.append(Found(r["key"], r.get("run_id", ""), r.get("pipeline_label", ""),
                                     s.get("name", ""), digest))
        return out

    def runs_by_model_files(self, files_digest: str) -> list[Found]:
        """The runs with a model-call record naming these model files (`model.files_digest`, observed or
        declared), each with the step, the value and its state, in the console's order of runs."""
        out = []
        for r in self._runs():
            for s in r.get("steps", []):
                for call in s.get("model_calls", []):
                    field = (call.get("fields") or {}).get(FILES_FIELD) or {}
                    if field.get("status") in FILES_STATES and field.get("value") == files_digest:
                        out.append(Found(r["key"], r.get("run_id", ""), r.get("pipeline_label", ""),
                                         s.get("name", ""), files_digest, state=field["status"]))
        return out

    def neighbours(self, run_key: str) -> list[Found]:
        """The runs of the same configuration whose kept inputs are near this run's, nearest first, as the
        run's page lists them. Refused where neighbours by input is not on for this store."""
        from onetrace_console import neighbours
        from onetrace_console.store import Store
        if not neighbours.installed():
            raise Refused("neighbours by input is not installed here: pip install \"onetrace-console[neighbours]\"")
        if not all((self.root / "store" / d).is_dir() for d in ("objects", "runs")):
            raise Refused(f"{self.root} holds no store folder (store/objects and store/runs)")
        store = Store(self.root / "store")
        if not neighbours.active(store):
            raise Refused("neighbours by input is not turned on for this store: a person turns it on at "
                          "/neighbours/setup on a local console")
        run = store.get_run(run_key)
        if run is None:
            raise Refused(f"this store holds no run {run_key}")
        from onetrace_console.neighbours import nearness
        with store.reading():
            got = nearness.suggestions(run, store)
        if got is None:
            raise Refused("this store holds no embedded vectors for the embedder in use yet")
        label = {r["key"]: (r.get("run_id", ""), r.get("pipeline_label", "")) for r in self._runs()}
        return [Found(row.other.key, *label.get(row.other.key, (row.other.run_id, "")), row.step, "",
                      state=row.near.how, name=row.name, nearness=row.near.value) for row in got.rows]
