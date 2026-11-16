"""OPERATOR_README's configuration example holds every key the console reads, read from `config.py` itself:
each field of `Config`, each `sign_in` key of `_SIGN_IN_SCHEMA`, and each extension `_KNOWN_EXTENSIONS` names.
The example loads as a configuration, and each value in it is the console's own default, but where the
container's store root is shown.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, fields
from pathlib import Path

from onetrace_console import config as config_module
from onetrace_console.config import Config, load

REPO = Path(__file__).resolve().parent.parent
README = REPO / "OPERATOR_README.md"
#: Where the example shows the container's value, not the default.
CONTAINER = {"store_root": "/data"}


def example(text: str | None = None) -> dict:
    """The configuration example: the first JSON block under "## Configuration"."""
    text = README.read_text(encoding="utf-8") if text is None else text
    section = text[text.index("## Configuration") :]
    return json.loads(re.search(r"```json\n(.*?)\n```", section, re.S).group(1))


def missing(shown: dict) -> list[str]:
    """Each key the console reads that `shown` leaves out, as a dotted name; then each it holds that the
    console does not read."""
    want = {f.name for f in fields(Config)}
    out = [k for k in sorted(want) if k not in shown] + [f"unread: {k}" for k in sorted(set(shown) - want)]
    for name, keys in (
        ("sign_in", set(config_module._SIGN_IN_SCHEMA)),
        ("extensions", set(config_module._KNOWN_EXTENSIONS)),
    ):
        inner = shown.get(name) if isinstance(shown.get(name), dict) else {}
        out += [f"{name}.{k}" for k in sorted(keys - set(inner))]
        out += [f"unread: {name}.{k}" for k in sorted(set(inner) - keys)]
    return out


def test_the_example_holds_every_key_the_console_reads(examined):
    shown = example()
    examined(
        len(fields(Config)) + len(config_module._SIGN_IN_SCHEMA) + len(config_module._KNOWN_EXTENSIONS),
        "keys config.py reads",
    )
    assert missing(shown) == []


def test_the_example_loads_and_each_value_is_the_default(tmp_path, examined):
    shown = example()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(shown), encoding="utf-8")
    loaded = asdict(load(path))
    defaults = {**asdict(Config()), **CONTAINER}
    examined(len(defaults), "values in the example")
    assert {k: loaded[k] for k in defaults} == defaults


def test_sabotage_a_key_left_out_or_one_not_read_is_named(examined):
    shown = example()
    dropped = json.loads(json.dumps(shown))
    del dropped["sign_in"]["trusted_proxies"]
    del dropped["tokenizers"]
    dropped["sign_in"]["no_such_key"] = 1
    examined(3, "planted changes to the example")
    assert missing(dropped) == ["tokenizers", "sign_in.trusted_proxies", "unread: sign_in.no_such_key"]


def unexplained(text: str | None = None) -> list[str]:
    """Each key the console reads that no row of the README's table names (`key`, or `sign_in.key`)."""
    text = README.read_text(encoding="utf-8") if text is None else text
    section = text[text.index("## Configuration") :]
    section = section[: section.index("**Creating the first")]
    rows = "\n".join(line for line in section.splitlines() if line.startswith("| `"))
    out = [f.name for f in fields(Config) if f.name != "sign_in" and f"`{f.name}`" not in rows]
    return out + [f"sign_in.{k}" for k in config_module._SIGN_IN_SCHEMA if f"`sign_in.{k}`" not in rows]


def test_the_table_says_what_each_key_means(examined):
    examined(len(fields(Config)) - 1 + len(config_module._SIGN_IN_SCHEMA), "keys config.py reads")
    assert unexplained() == []


def test_sabotage_a_row_taken_out_is_named(examined):
    text = README.read_text(encoding="utf-8")
    row = next(line for line in text.splitlines() if line.startswith("| `tracing` |"))
    examined(1, "a planted change to the table")
    assert unexplained(text.replace(row + "\n", "")) == ["tracing"]


def test_no_source_says_the_configuration_path_is_the_only_variable_read(examined):
    """The guide names every environment variable the console reads; no docstring says there is one alone."""
    src = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
    files = sorted(src.rglob("*.py"))
    examined(len(files), "source files")
    said = [
        p.relative_to(src).as_posix() for p in files if "only environment variable" in p.read_text(encoding="utf-8")
    ]
    assert said == []
