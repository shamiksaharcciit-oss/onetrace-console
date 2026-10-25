"""P9, the demo store's wheel-bolt torque check: a tightening tool's readings to pass or rework,
recorded with onetrace.

    read_tool_log --> torque_check --> station_decision

A tightening tool on an assembly line records the final torque of each of a wheel's five bolts (a
CSV); `read_tool_log` reads it, with the tool's firmware version recorded beside it; `torque_check`
lists every bolt outside the specified window; `station_decision` passes the wheel where there is
none and sends it to rework where there is.

Every reading, setting and name here is invented example data, made in this module, the same on
every build: no real vehicle, line, site or tool maker. Nothing contacts a network or any equipment;
the demo records and compares, and never controls anything. Torques are whole tenths of a
newton-metre, so nothing is rounded.

The demo's runs of it: a baseline; a run whose tool firmware version changed while its readings did
not; and a run where one bolt reads below the window, so the wheel goes to rework.
"""
from __future__ import annotations

from pathlib import Path

from onetrace.emit import Instrument, Recorder

STAGES = ["read_tool_log", "torque_check", "station_decision"]

EXAMPLE = "invented example data"
#: The specified torque window, in tenths of a newton-metre: 110.0 to 130.0 Nm.
LOW, HIGH = 1100, 1300

#: The five bolts' final torques, invented, in tenths of a newton-metre.
READINGS = [1184, 1210, 1196, 1223, 1208]
#: The one reading that differs in the demo's low-bolt run: bolt 3, below the window.
LOW_BOLT = {3: 1042}


def _nm(tenths: int) -> str:
    return f"{tenths // 10}.{tenths % 10}"


def _tenths(text: str) -> int:
    whole, _, tenth = text.partition(".")
    return int(whole) * 10 + int(tenth or 0)


def tool_log_csv(low_bolt: bool) -> str:
    """The tool's log: bolt, final torque in newton-metres."""
    rows = ["bolt,torque_nm"]
    for bolt, tenths in enumerate(READINGS, start=1):
        if low_bolt and bolt in LOW_BOLT:
            tenths = LOW_BOLT[bolt]
        rows.append(f"{bolt},{_nm(tenths)}")
    return "\n".join(rows) + "\n"


def main(out_dir, run_id: str, firmware: str, low_bolt: bool) -> None:
    """Record one run: the tool's firmware version, and whether bolt 3 reads low."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "tool_log.csv"
    csv_path.write_text(tool_log_csv(low_bolt), encoding="utf-8")
    rec = Recorder(out_dir, run_id=run_id, declared_stages=STAGES, manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a demo record; anchoring is not part of this demo")

    def read_tool_log(ctx):
        raw = ctx.read_external(csv_path, "text/csv", name="tool_log.csv",
                                trust_class="externally-sourced")
        ctx.constant("data", EXAMPLE)
        ctx.constant("tool_firmware", firmware)
        rows = raw.decode("utf-8").splitlines()[1:]
        return ctx.write_json("torques.json", {"torque_nm": [r.split(",")[1] for r in rows]})

    def torque_check(ctx, got):
        ctx.read_receipt("read_tool_log")
        torques = ctx.read_json(got)["torque_nm"]
        outside = [{"bolt": str(i), "torque_nm": t} for i, t in enumerate(torques, start=1)
                   if not LOW <= _tenths(t) <= HIGH]
        return ctx.write_json("check.json", {"window_nm": f"{_nm(LOW)} to {_nm(HIGH)}",
                                             "outside": outside})

    def station_decision(ctx, checked):
        ctx.read_receipt("torque_check")
        outside = ctx.read_json(checked)["outside"]
        return ctx.write_json("decision.json", {"decision": "rework" if outside else "pass",
                                                "bolts_outside": str(len(outside))})

    got = rec.run_node("read_tool_log", None, Instrument("tightening-tool-log", "reader", "1.0.0",
                                                         {"source": "tool_log.csv"}), read_tool_log)
    checked = rec.run_node("torque_check", None, Instrument("torque-window-check", "checker", "1.0.0",
                                                            {"window_nm": f"{_nm(LOW)} to {_nm(HIGH)}"}),
                           torque_check, got)
    rec.run_node("station_decision", None, Instrument("station-rule", "rule", "1.0.0",
                                                      {"rule": "pass only with every bolt in the window"}),
                 station_decision, checked)
    rec.close()


def kept_inputs(args: dict) -> list[bytes]:
    """P9 keeps no input's text."""
    return []
