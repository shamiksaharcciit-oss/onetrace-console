"""Neighbours by input: runs of one configuration whose kept inputs are near, and the nearness ladder.

An optional extra, `onetrace-console[neighbours]`, on a local console only. Without the extra the
feature does not exist: no tab, no route, no word on any page (`installed`). On a public console it
does not exist either, the extra installed or not (`exists`): no embedder, no route, no page names it.
With the extra on a local console it is off until a person turns it on and confirms, on its setup
page; the default embedder's files are fetched then, and only then (`embedder`).

- **Grouping, exact, first** (`grouping`): a run's invariant signature is the digest of every step's
  configuration as the record states it. Neighbours are looked for only inside a group.
- **What is embedded** (`kept`): kept inputs, under the existing per-input opt-in, and for the
  nearness ladder the stored outputs of a run that keeps inputs. Never a digest, a setting or any
  part of a record.
- **Each embedding batch is a recorded onetrace run** (`batches`), with one model-call-record/1.0
  per text, built with onetrace's own helpers. The vectors are kept in a derived file keyed by
  (input digest, embedder record digest), rebuilt from those runs.
- **The pages** (`pages`): the run page's "Runs with near inputs (same configuration)", and the
  nearness ladder beside the exact ladder on a comparison of two neighbours. Nothing in the short
  answer, the exact ladder or any verdict reads a number from here.

This module imports none of the extra's packages: it only asks whether they are installed.
"""
from __future__ import annotations

import importlib.util

#: The extra's own packages, imported only by `embedder` and only once the feature is on.
EXTRA = ("onnxruntime", "tokenizers", "numpy")
#: The store's folder for everything this feature keeps: its setting, the embedder's files, the
#: embedding batches' runs, and the derived file of vectors.
FOLDER = "neighbours"

#: The note's non-claims, word for word (onetrace_backlog_run_index_and_neighbours.md, item 2): on
#: the page that turns the feature on, and in docs/neighbours.md.
NON_CLAIMS = (
    "Similarity of inputs is a suggestion for which runs to compare, and a drop in the nearness ladder "
    "is a suggestion of where to look; neither is evidence of anything and neither is a verdict.",
    "The embedder reads kept inputs; the console says so, and the feature is off by default.",
    "Nothing about hosted embedders: none is offered.",
    "No fitted threshold: the similarity is shown as a number, ordered, with no cut-off claimed to "
    "mean \"the same\".",
)


def installed() -> bool:
    """The extra's packages are importable here. Asked of the import system, never by importing them."""
    return all(importlib.util.find_spec(name) is not None for name in EXTRA)


def exists(*, public: bool) -> bool:
    """The feature exists on this console: the extra installed, and the console not public."""
    return not public and installed()


def drawing_public() -> bool:
    """The pages now drawn are a public console's, or files (a static export, `explain.no_presses`),
    which can press nothing: either way the feature does not exist on them."""
    from onetrace_console.explain import _NO_PRESSES
    from onetrace_console.frame import rendering_public
    return rendering_public() or _NO_PRESSES.get()


def here() -> bool:
    """The feature exists on the pages now drawn."""
    return exists(public=drawing_public())


def active(store) -> bool:
    """The feature is on for this store: it exists here and a person turned it on and confirmed."""
    if store is None or not here():
        return False
    from onetrace_console.neighbours import settings
    return settings.read(store) is not None
