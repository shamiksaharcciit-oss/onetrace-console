"""A mark draws only the pages it changes.

Mark as benchmark, or its undo, drew every page of the store again. It now draws its pipeline's run pages and only
the store's pages a mark changes (`render.render_all(marked=...)`): each runs list that holds one of the pipeline's
runs, the monitor, and the pipeline's own pages; then the run index. Held here on a copy of the demo, every page
drawn at one fixed time before and after a mark in its largest pipeline: every page whose bytes change is one the
narrowed drawing draws, drawn byte for byte as the full drawing draws it; and no other page changes.
"""

from __future__ import annotations

import collections

T = "2026-11-10T12:00:00+00:00"


def _everything(store) -> dict[str, str]:
    from onetrace_console.frame import rendering
    from onetrace_console.pages import render_execution
    from onetrace_console.render import render_all, render_diff

    out = {}
    with rendering(onedoor=False, sign_in=False, public=False), store.reading():
        out.update(render_all(store, generated_at=T))
        for r in store.runs():
            for k, v in render_execution(r, store, generated_at=T).pages.items():
                out[f"runs/{r.key}/{k}"] = v
        for c in store.comparisons():
            out[f"diff/{c.key}.html"] = render_diff(c, store, generated_at=T)
    return out


def test_a_mark_draws_exactly_the_pages_it_changes(shared_demo, tmp_path, examined):
    from onetrace_console import benchmarks
    from onetrace_console.frame import rendering
    from onetrace_console.overview import declared_list
    from onetrace_console.render import render_all
    from onetrace_console.store import Store
    from onetrace_console.verdicts import pipeline_of
    from tests.conftest import demo_copy

    folder = demo_copy(shared_demo, tmp_path / "demo")
    store = Store(folder / "store" / "store")
    runs = list(store.runs())
    biggest = collections.Counter(pipeline_of(r, store).label for r in runs if pipeline_of(r, store)).most_common(1)
    run = next(r for r in runs if pipeline_of(r, store) and pipeline_of(r, store).label == biggest[0][0])
    run = next(
        r for r in runs if pipeline_of(r, store) == pipeline_of(run, store) and not benchmarks.mark_of(store, r.key)
    )
    before = _everything(store)
    benchmarks.mark(store, run, who="a test", note="")
    after = _everything(store)
    same = [r for r in store.runs() if declared_list(r) == declared_list(run)]
    with rendering(onedoor=False, sign_in=False, public=False), store.reading():
        narrowed = render_all(
            store, generated_at=T, marked=(pipeline_of(run, store).label, frozenset(r.key for r in same))
        )
    run_pages = {k for k in after if any(k.startswith(f"runs/{r.key}/") for r in same)}
    #: A comparison of the pipeline's runs shows each against its reference run, which the mark can make: drawn again.
    keys = {r.key for r in same}
    run_pages |= {f"diff/{c.key}.html" for c in store.comparisons() if c.run_a in keys or c.run_b in keys}
    changed = {k for k in before if before[k] != after[k]}
    examined(len(changed), "pages a mark changed")
    assert changed and changed <= set(narrowed) | run_pages, sorted(changed - set(narrowed) - run_pages)
    assert {k: narrowed[k] for k in narrowed} == {k: after[k] for k in narrowed}
    #: The badge, where the run is listed: on the narrowed lists that hold it.
    lists = [k for k in narrowed if k.startswith("executions-") and f"runs/{run.key}/case.html" in narrowed[k]]
    assert lists and all("data-benchmark" in narrowed[k] or "benchmark" in narrowed[k] for k in lists)
    #: Drawn far fewer than the store's pages.
    assert len(narrowed) < len(render_all_count := [k for k in after if not k.startswith(("runs/", "diff/"))]) / 2, (
        len(narrowed),
        len(render_all_count),
    )
