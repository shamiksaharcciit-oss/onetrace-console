"""The top-level `--help` names every option `demo --public --build` takes.

`demo --help` describes each option that goes into a build ("with --public --build"); the top-level
usage's `demo --public --build` entry must name each of them too, so a reader of either finds them all.
The sabotage below drops one from the usage.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _cli(*args: str) -> str:
    env = {**{k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"},
           "PYTHONPATH": str(REPO / "src")}
    done = subprocess.run([sys.executable, "-B", "-m", "onetrace_console", *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, timeout=120)
    assert done.returncode == 0, done.stderr[-1500:]
    return done.stdout


def build_options(demo_help: str) -> list[str]:
    """The options `demo --help` says go with `--public --build`."""
    flat = " ".join(demo_help.split())
    return sorted(set(re.findall(r"(--[a-z-]+) [A-Z]+ with --public --build", flat)))


def build_entry(usage: str) -> str:
    """The top-level usage's `demo --public --build` entry, up to the next command."""
    start = usage.index("onetrace-console demo --public --build")
    end = usage.find("\n  onetrace-console ", start)
    return usage[start:end if end != -1 else None]


def missing(usage: str, options: list[str]) -> list[str]:
    entry = build_entry(usage)
    return [o for o in options if f"[{o} " not in entry]


def test_the_top_level_help_names_each_build_option(examined):
    options = build_options(_cli("demo", "--help"))
    examined(len(options), "build options in demo --help")
    assert options == ["--explanations", "--runs-from", "--site-links"]
    assert missing(_cli("--help"), options) == []


def test_sabotage_an_option_dropped_from_the_usage_is_named(examined):
    usage = _cli("--help")
    examined(1, "planted usage")
    assert " [--site-links <file>]" in usage
    assert missing(usage.replace(" [--site-links <file>]", ""), ["--site-links"]) == ["--site-links"]
