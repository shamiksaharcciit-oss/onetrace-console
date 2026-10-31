# Reading a console store from another program

`onetrace_console.store_read` answers three questions about a console store, for a program outside the
console (onetrace-explain's store probes among them). It is read-only: it writes nothing under the
store, runs no check, no comparison and no model, and reads no kept input except to ask the
neighbours extra's stored vectors.

```python
from onetrace_console import store_read

reader = store_read.open_store("path/to/store-root")
reader.runs_by_config("retrieve", "sha256:...")   # a stage's exact configuration
reader.runs_by_model_files("sha256:...")          # a model-call record's model files
reader.neighbours(run_key)                        # near kept inputs, where the extra is on
```

The store root is the folder the console keeps its store in: it holds the store's own `store/`
folder and the run index, `run_index.json`, beside it.

## The questions

- **`runs_by_config(step, config_digest)`**: the runs whose step `step` records exactly this
  configuration digest, its instrument's `config_digest`, in the console's order of runs. `"*"` asks
  every step.
- **`runs_by_model_files(files_digest)`**: the runs with a model-call record naming these model files
  (`model.files_digest`) in the state `observed` or `declared`, as the run page's "same model files"
  line matches them, each with its step and the value's state. A record whose files are
  `declared, not observed` or `declared, contradicted` is not matched.
- **`neighbours(run_key)`**: the runs of the same configuration whose kept inputs are near this run's,
  nearest first, each with the input it is near by, the nearness and how it was got ("record" where
  the two digests are equal, "embedder" otherwise), as the run's page lists them. Nearness is a
  reading of the kept inputs, not a judgement that two runs did the same thing.

Each answer is a list of `Found`: the run's key, id and pipeline, the step, the value matched, and
for the model-files question the value's state.

## Versions and refusals

The interface is `onetrace-console-store-read/1`. Its answers are read from the run index, and it
reads the index format `onetrace-console-run-index/0.2` only. Each refusal raises `Refused`, with the
reason as its message:

- the store root holds no run index (the console writes it when it draws its pages: start the console
  on the store once);
- the index is in an earlier format: a local console writes it again in its own format itself, when it
  next draws its pages; a public console reads its build's index and never writes one, so its build is
  made again with this release (the message gives both, in the search page's words);
- the index is another format, a later one or another index's, or none;
- `neighbours` where the `[neighbours]` extra is not installed, where the store root holds no store
  folder (`store/objects` and `store/runs`), where it is not turned on for this store, or where the
  store holds no vectors for the embedder in use yet.

A store is never read as if it were a version the interface knows.

## What it does not say

It reads only what the records state: a run not recorded, or recorded without the field, is not
found. A run found by its configuration or its model files shares that field with the run asked
about; it is not said to have done the same thing.
