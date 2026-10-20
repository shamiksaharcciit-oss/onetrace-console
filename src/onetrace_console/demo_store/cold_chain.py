"""P7, the demo store's cold-chain release: a temperature logger's readings to release or
quarantine, recorded with onetrace.

    fill_gaps --> excursion_check --> release

A shipment's temperature logger gives a reading every ten minutes, with a gap or two where it
missed one; `fill_gaps` reads the logger's file -- from outside the pipeline, kept beside its
digest, as invented example data the demo builder marks as such -- and fills each gap with the
reading before it; `excursion_check` lists every reading outside the allowed range; `release`
releases the shipment where there is none, and quarantines it where there is.

Every reading, setting and name here is invented example data, made in this module, the same on
every build: no real shipment, site, product or equipment maker. Nothing contacts a network or any
equipment; the demo records and compares, and never controls anything. Temperatures are whole
tenths of a degree Celsius, so nothing is rounded.

The demo's runs of it: a baseline; a run whose logger file differs in one reading, past the range,
so the comparison shows that reading beside the decision it changes; and a run altered after it was
recorded (one byte of its decision), so it contradicts its record.
"""
from __future__ import annotations

import json
from pathlib import Path

from onetrace.emit import Instrument, Recorder

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["fill_gaps", "excursion_check", "release"]

EXAMPLE = "invented example data"
#: The allowed range, in tenths of a degree Celsius: 2.0 to 8.0.
LOW, HIGH = 20, 80

#: The logger's readings, invented: (minute, tenths of a degree), None where it missed one.
READINGS = [(0, 41), (10, 42), (20, 44), (30, 46), (40, None), (50, 47), (60, 45), (70, 43),
            (80, None), (90, 42), (100, 41), (110, 40)]
#: The one reading that differs in the demo's second run: minute 30, past the range.
CHANGED = {30: 94}


def logger_text(changed: bool) -> str:
    """The logger's file, a CSV: minute, temperature in degrees Celsius; empty where it missed one."""
    rows = ["# invented example data for this demo", "minute,temp_c"]
    for minute, tenths in READINGS:
        if changed and minute in CHANGED:
            tenths = CHANGED[minute]
        rows.append(f"{minute}," + ("" if tenths is None else f"{tenths // 10}.{tenths % 10}"))
    return "\n".join(rows) + "\n"


def logger_bytes(changed: bool) -> bytes:
    """The logger's file as `fill_gaps` reads it, and keeps it: a JSON string of its text, the bytes
    its digest is computed over."""
    return json.dumps(logger_text(changed)).encode("utf-8")


def kept_inputs(args: dict) -> list[bytes]:
    """The bytes of every input a run with `args` keeps: its logger file."""
    return [logger_bytes(args["changed"])]


def _tenths(text: str) -> int:
    whole, _, tenth = text.partition(".")
    return int(whole) * 10 + int(tenth or 0)


def _degrees(tenths: int) -> str:
    return f"{tenths // 10}.{tenths % 10}"


def main(out_dir, run_id: str, changed: bool) -> None:
    """Record one run; `changed`: its logger file holds the one changed reading."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a demo record; anchoring is not part of this demo")
    data = logger_bytes(changed)

    def fill_gaps(ctx):
        ctx.read_memory(data, "application/json", name="logger", trust_class="externally-sourced")
        ctx.keep_declared = True
        ctx.keep_input("logger", data)
        ctx.constant("data", EXAMPLE)
        filled, last = [], None
        for line in load_json_bounded(data.decode("utf-8"), "the logger file").splitlines()[2:]:
            minute, _, temp = line.partition(",")
            last = _tenths(temp) if temp else last
            filled.append({"minute": minute, "temp_c": _degrees(last),
                           "filled": not temp})
        return ctx.write_json("filled.json", {"readings": filled})

    def excursion_check(ctx, readings):
        ctx.read_receipt("fill_gaps")
        out_of_range = [r for r in ctx.read_json(readings)["readings"] if not LOW <= _tenths(r["temp_c"]) <= HIGH]
        return ctx.write_json("excursions.json", {"allowed_c": f"{_degrees(LOW)} to {_degrees(HIGH)}",
                                                  "excursions": out_of_range})

    def release(ctx, checked):
        ctx.read_receipt("excursion_check")
        found = ctx.read_json(checked)["excursions"]
        return ctx.write_json("decision.json", {"decision": "quarantine" if found else "release",
                                                "excursions": str(len(found))})

    readings = rec.run_node("fill_gaps", None, Instrument("logger-gap-fill", "transform", "1.0.0",
                                                          {"gap_fill": "the reading before"}), fill_gaps)
    checked = rec.run_node("excursion_check", None, Instrument("excursion-check", "checker", "1.0.0",
                                                               {"allowed_c": f"{_degrees(LOW)} to {_degrees(HIGH)}"}),
                           excursion_check, readings)
    rec.run_node("release", None, Instrument("release-rule", "rule", "1.0.0",
                                             {"rule": "release only with no excursion"}), release, checked)
    rec.close()
