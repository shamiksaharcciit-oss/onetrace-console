"""Console 0.6.1 item 8: a key variable not set says where to look.

The Set up Explain page and the Explain panel's failure line name the configuration file read, the
variable its `key_env` names, and whether that variable is set in the environment the console started
from -- "set" or "not set", never its value -- with the restart line where it is not set. The file's path
follows `ONETRACE_EXPLAIN_CONFIG`.
"""
from __future__ import annotations

import os
import re
from html import unescape

import pytest

from tests.test_explain_panel import _diff, _panel, in_full, pair, toml_string  # noqa: F401  (pair: a fixture)

VALUE = "a-key-value-never-shown-5551212"
VAR = "PLANTED_KEY_VARIABLE"


def _config(config, *, key_env: str = VAR) -> None:
    from tests.test_explain_panel import _closed_port
    config.write_text(f'[model]\nprovider = "anthropic"\nname = "a-model"\n'
                      f"base_url = {toml_string('http://127.0.0.1:%d' % _closed_port())}\n"
                      f"key_env = {toml_string(key_env)}\n", encoding="utf-8")


def _failed(pair) -> str:
    """The panel after a Send that failed (nothing listens at the address)."""
    from onetrace_console import explain
    store, comparison, _config_path = pair
    explain.prepare(comparison, store)
    got = explain.explain(comparison, store, send=True)
    assert got["exit"] != "0", in_full(got)
    return _panel(_diff(store, comparison))


def test_an_unset_variable_is_named_with_the_file_and_the_restart_line(pair, monkeypatch):
    from onetrace_console import explain
    store, comparison, config = pair
    _config(config)
    monkeypatch.delenv(VAR, raising=False)
    panel = unescape(_failed(pair))
    #: The file's last two parts with this platform's own separator, as the panel shortens it (`/` is
    #: not Windows' separator).
    short = re.escape(f"…{os.sep}config{os.sep}explain.toml")
    assert re.search(rf"onetrace-explain read {short}; its key_env names {VAR}, which is not set in "
                     r"the environment this console started from\.", panel), panel
    assert f"Set {VAR} in the environment you start the console from, then start the console again" in panel
    assert re.search(r'<a class="button" data-explain="setup" href="/explain/setup">Set up Explain</a>',
                     _failed(pair)), "the failure links to Set up Explain"
    page = unescape(explain.panel(comparison, store, public=False))
    assert VALUE not in page


def test_a_set_variable_says_set_and_never_its_value(pair, monkeypatch):
    store, comparison, config = pair
    _config(config)
    monkeypatch.setenv(VAR, VALUE)
    panel = unescape(_failed(pair))
    assert f"its key_env names {VAR}, which is set in the environment this console started from." in panel
    assert "then start the console again" not in panel
    assert VALUE not in panel


def test_the_setup_page_names_the_file_from_the_environment_the_variable_and_its_state(pair, monkeypatch, tmp_path):
    from onetrace_console import explain_setup
    store, _comparison, config = pair
    _config(config)
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    for value, state in ((None, "not set"), (VALUE, "set")):
        if value is None:
            monkeypatch.delenv(VAR, raising=False)
        else:
            monkeypatch.setenv(VAR, value)
        page = unescape(explain_setup.page(store))
        assert f"onetrace-explain read {config}; its key_env names {VAR}, which is {state} in the environment" in page
        assert (f"Set {VAR} in the environment you start the console from" in page) == (value is None)
        assert VALUE not in page


def test_no_key_env_no_line(pair):
    from onetrace_console import explain
    _store, _comparison, config = pair
    _config(config, key_env="")
    assert explain.key_status() is None and explain.key_lines(None) == ""
