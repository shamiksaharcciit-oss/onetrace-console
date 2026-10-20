"""P5, the demo store's pump maintenance: vibration readings to a work order, recorded with onetrace.

    readings --> calibrate --> features --> anomaly_check --> decision --> work_order

A pump's vibration sensor gives a short series of readings (a CSV); `calibrate` takes off the
sensor's offset, a setting of its instrument; `features` computes the series' RMS and peak;
`anomaly_check` compares the RMS with a fixed limit; `decision` asks for an inspection where the
limit is passed; `work_order` books it, and declines by its own rule a slot outside the maintenance
window -- the run then stops there.

Every reading, setting and name here is invented example data, made in this module, the same on
every build: no real pump, site or equipment maker. Nothing contacts a network or any equipment;
the demo records and compares, and never controls anything. Values are whole numbers of milli-g,
so nothing is rounded.

The demo's runs of it: a baseline; a candidate whose calibration offset changed (its first
difference is `calibrate`); a run whose sensor firmware version changed while its readings did
not; and a run asking for a slot outside the window, declined by `work_order`.
"""
from __future__ import annotations

import math
from pathlib import Path

from onetrace.emit import Instrument, Recorder, Refusal

STAGES = ["readings", "calibrate", "features", "anomaly_check", "decision", "work_order"]

EXAMPLE = "invented example data"
#: The RMS above which the series is an anomaly, in milli-g.
RMS_LIMIT_MG = 280
#: The maintenance window, hours of the day, from and to.
WINDOW = ("02:00", "04:00")


def readings_csv() -> str:
    """The pump's readings, invented: 48 samples of a vibration in milli-g, a whole number each,
    from a fixed pattern, so every build makes the same series."""
    pattern = [0, 210, 360, 420, 360, 210, 0, -210, -360, -420, -360, -210]
    rows = ["sample,vibration_mg"] + [f"{i},{pattern[i % len(pattern)] + (i % 5) * 7}"
                                      for i in range(48)]
    return "\n".join(rows) + "\n"


def main(out_dir, run_id: str, offset_mg: str, firmware: str, slot: str) -> None:
    """Record one run: the sensor's offset, its firmware version and the work order's slot."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "readings.csv"
    csv_path.write_text(readings_csv(), encoding="utf-8")
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a demo record; anchoring is not part of this demo")

    def readings(ctx):
        raw = ctx.read_external(csv_path, "text/csv", name="readings.csv",
                                trust_class="externally-sourced")
        ctx.constant("data", EXAMPLE)
        ctx.constant("sensor_firmware", firmware)
        rows = raw.decode("utf-8").splitlines()[1:]
        return ctx.write_json("readings.json", {"vibration_mg": [r.split(",")[1] for r in rows]})

    def calibrate(ctx, got):
        ctx.read_receipt("readings")
        return ctx.write_json("calibrated.json", {"vibration_mg": [
            str(int(v) - int(offset_mg)) for v in ctx.read_json(got)["vibration_mg"]]})

    def features(ctx, calibrated):
        ctx.read_receipt("calibrate")
        values = [int(v) for v in ctx.read_json(calibrated)["vibration_mg"]]
        rms = math.isqrt(sum(v * v for v in values) // len(values))
        return ctx.write_json("features.json", {"rms_mg": str(rms),
                                                "peak_mg": str(max(abs(v) for v in values))})

    def anomaly_check(ctx, found):
        ctx.read_receipt("features")
        f = ctx.read_json(found)
        return ctx.write_json("anomaly.json", {"rms_mg": f["rms_mg"], "limit_mg": str(RMS_LIMIT_MG),
                                               "anomaly": int(f["rms_mg"]) > RMS_LIMIT_MG})

    def decision(ctx, checked):
        ctx.read_receipt("anomaly_check")
        a = ctx.read_json(checked)
        action = "inspect the pump" if a["anomaly"] else "no action"
        return ctx.write_json("decision.json", {
            "action": action, "slot": slot,
            "reason": f"RMS {a['rms_mg']} mg against a limit of {a['limit_mg']} mg"})

    def work_order(ctx, decided):
        ctx.read_receipt("decision")
        d = ctx.read_json(decided)
        if not WINDOW[0] <= d["slot"] <= WINDOW[1]:
            raise Refusal(f"a work order at {d['slot']} is outside the maintenance window "
                          f"{WINDOW[0]} to {WINDOW[1]}")
        return ctx.write_json("work_order.json", {"order": d["action"], "slot": d["slot"],
                                                  "reason": d["reason"]})

    got = rec.run_node("readings", None, Instrument("vibration-sensor-reader", "reader", "1.0.0",
                                                    {"source": "readings.csv"}), readings)
    calibrated = rec.run_node("calibrate", None, Instrument("sensor-calibration", "transform", "1.0.0",
                                                            {"offset_mg": offset_mg}), calibrate, got)
    found = rec.run_node("features", None, Instrument("vibration-features", "transform", "1.0.0",
                                                      {"features": "rms, peak"}), features, calibrated)
    checked = rec.run_node("anomaly_check", None, Instrument("rms-threshold", "checker", "1.0.0",
                                                             {"rms_limit_mg": str(RMS_LIMIT_MG)}),
                           anomaly_check, found)
    decided = rec.run_node("decision", None, Instrument("maintenance-decision", "rule", "1.0.0",
                                                        {"rule": "inspect above the limit"}),
                           decision, checked)
    rec.run_node("work_order", None, Instrument("maintenance-window-policy", "policy", "1.0.0",
                                                {"window": f"{WINDOW[0]} to {WINDOW[1]}"}),
                 work_order, decided)
    rec.close()


def kept_inputs(args: dict) -> list[bytes]:
    """P5 keeps no input's text."""
    return []
