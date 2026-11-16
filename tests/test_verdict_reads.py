"""A page that lists runs reads each run's verdict once per reading.

Every runs table draws each run's verdict pill, and each pill read the pipeline's reference and the run's
kept verdict again: drawing the demo's pages read the reference 1,680 times for 54 runs, and a press of
"Mark as benchmark", which draws them again, took 0.8 s. Within one reading (`Store.reading`), a run's
verdict is now read once and given again; a write forgets it, as it forgets every read.
"""

from __future__ import annotations


def test_drawing_every_page_reads_each_run_s_verdict_once(shared_demo, monkeypatch, examined):
    from onetrace_console import verdicts
    from onetrace_console.render import render_all
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    #: Each run's verdict, as the pill reads it: the reference read for it, then its own verdict. Before,
    #: a reading read it for every pill (1,680 references for 54 runs); the pages that read a pipeline's
    #: reference themselves read it apart.
    real = getattr(verdicts, "_verdict_record", verdicts.verdict_record)
    seen = []

    def counted(run, store, *, compute):
        seen.append(run.key)
        return real(run, store, compute=compute)

    monkeypatch.setattr(
        verdicts, "_verdict_record" if hasattr(verdicts, "_verdict_record") else "verdict_record", counted
    )
    with store.reading():
        runs = list(store.runs())
        render_all(store, generated_at="2026-11-10T12:00:00+00:00")
    examined(len(runs), "runs, each listed on several pages")
    assert 0 < len(seen) <= 2 * len(runs), f"{len(seen)} reads of a run's verdict for {len(runs)} runs"


def test_a_write_in_the_reading_forgets_the_verdict_read(shared_demo, monkeypatch, examined):
    from onetrace_console import verdicts
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    real, seen = verdicts.reference_record, []
    monkeypatch.setattr(
        verdicts, "reference_record", lambda p, s, *, compute: seen.append(1) or real(p, s, compute=compute)
    )
    with store.reading():
        run = next(r for r in store.runs() if verdicts.pipeline_of(r, store) is not None)
        first = verdicts.verdict_record(run, store, compute=False)
        assert verdicts.verdict_record(run, store, compute=False) == first and len(seen) == 1
        store._forget()
        assert verdicts.verdict_record(run, store, compute=False) == first and len(seen) == 2
    examined(1, "a run read, again, and after a write")


def test_drawing_every_page_draws_each_run_s_line_and_the_incidents_once(shared_demo, monkeypatch, examined):
    """The Runs tables' one line per run, and the incidents several pages list, likewise once per reading."""
    from onetrace_console import incidents, what_changed
    from onetrace_console.render import render_all
    from onetrace_console.store import Store

    store = Store(shared_demo["folder"] / "store" / "store")
    lines, derived = [], []
    for module, name, seen in ((what_changed, "_runs_line", lines), (incidents, "_derive", derived)):
        real = getattr(module, name)
        monkeypatch.setattr(module, name, lambda *a, _r=real, _s=seen, **k: _s.append(1) or _r(*a, **k))
    with store.reading():
        runs = list(store.runs())
        render_all(store, generated_at="2026-11-10T12:00:00+00:00")
    examined(len(runs), "runs")
    assert 0 < len(lines) <= len(runs), f"{len(lines)} lines drawn for {len(runs)} runs"
    assert len(derived) == 1, f"the incidents derived {len(derived)} times"
