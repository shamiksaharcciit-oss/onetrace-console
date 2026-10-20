"""P6, the demo store's fill-level inspection: a measured frame to a reject command, recorded with
onetrace.

    measure --> classify --> reject_command

A camera's frame of a bottle on a line comes in as a small array of numbers, each the brightness of
one row of the frame, top to bottom; `measure` finds the fill level, the rows whose brightness the
camera's exposure brings past the liquid's edge; `classify` passes a bottle filled to the reject
line or above and rejects one below it; `reject_command` records the command a line would be given.

Every frame, setting and name here is invented example data, made in this module, the same on every
build: no real line, site, product or equipment maker. Nothing contacts a network or any equipment;
the demo records and compares, and never controls anything. Values are whole numbers, so nothing is
rounded.

The demo's runs of it: a baseline; a candidate whose camera exposure changed, so `measure` reads a
different level and `classify` still passes the bottle (the comparison comes back the same after
it); and a candidate whose bottle is filled below the reject line (`classify` rejects it).
"""
from __future__ import annotations

import json
from pathlib import Path

from onetrace.emit import Instrument, Recorder

from onetrace_console.bounded_json import load_json_bounded

STAGES = ["measure", "classify", "reject_command"]

EXAMPLE = "invented example data"
#: The brightness past which a row is liquid, after exposure; each row is 10 mm of the bottle.
EDGE = 100
ROW_MM = 10
#: The fill level a bottle must reach to pass, in mm from the bottom of the frame.
REJECT_LINE_MM = 100

#: The frames, invented: row brightness, top to bottom, of a bottle filled high and one filled low.
FRAMES = {
    "full": [20, 24, 30, 88, 95, 112, 130, 136, 140, 142, 141, 143, 140, 139, 141, 140],
    "low": [20, 22, 25, 28, 30, 34, 40, 52, 70, 118, 131, 139, 141, 140, 142, 140],
}


def frame_bytes(frame: str) -> bytes:
    return json.dumps({"rows": [str(r) for r in FRAMES[frame]], "data": EXAMPLE},
                      sort_keys=True).encode("utf-8")


def main(out_dir, run_id: str, frame: str, exposure_tenths: str) -> None:
    """Record one run: which frame, and the camera's exposure in tenths (10 is 1.0)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame_path = out / "frame.json"
    frame_path.write_bytes(frame_bytes(frame))
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a demo record; anchoring is not part of this demo")

    def measure(ctx):
        raw = ctx.read_external(frame_path, "application/json", name="frame.json",
                                trust_class="externally-sourced")
        ctx.constant("data", EXAMPLE)
        rows = [int(r) for r in load_json_bounded(raw.decode("utf-8"), "the frame")["rows"]]
        liquid = [r * int(exposure_tenths) // 10 > EDGE for r in rows]
        level = sum(liquid) * ROW_MM
        return ctx.write_json("level.json", {"fill_level_mm": str(level)})

    def classify(ctx, measured):
        ctx.read_receipt("measure")
        level = int(ctx.read_json(measured)["fill_level_mm"])
        return ctx.write_json("result.json", {"result": "pass" if level >= REJECT_LINE_MM else "reject"})

    def reject_command(ctx, classified):
        ctx.read_receipt("classify")
        result = ctx.read_json(classified)["result"]
        return ctx.write_json("command.json", {"command": "reject the bottle" if result == "reject"
                                               else "none"})

    measured = rec.run_node("measure", None, Instrument("fill-level-camera", "measurement", "1.0.0",
                                                        {"exposure_tenths": exposure_tenths,
                                                         "edge": str(EDGE)}), measure)
    classified = rec.run_node("classify", None, Instrument("fill-classifier", "rule", "1.0.0",
                                                           {"reject_line_mm": str(REJECT_LINE_MM)}),
                              classify, measured)
    rec.run_node("reject_command", None, Instrument("reject-gate", "command-recorder", "1.0.0",
                                                    {"records": "the command, never sent"}),
                 reject_command, classified)
    rec.close()


def kept_inputs(args: dict) -> list[bytes]:
    """P6 keeps no input's text."""
    return []
