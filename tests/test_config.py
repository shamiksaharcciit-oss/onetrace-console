"""`onetrace_console.config`: one read-only file, one environment variable.

Per-organisation configuration is one configuration file, mounted read-only, with its
keys documented. The only environment variable allowed is the path to that file.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from onetrace_console.config import Config, ConfigError, load, load_from_env

REPO = Path(__file__).resolve().parent.parent
SHIPPED_DEFAULT = REPO / "config" / "default.json"


def test_the_shipped_default_config_matches_configs_own_defaults(examined):
    """The Dockerfile ships `config/default.json` and points `ONETRACE_CONSOLE_CONFIG` at
    it, so the image works with no operator override at all. If it ever drifted from
    `Config()`'s own defaults, the image and this module's documentation would disagree
    about what "the default" is -- checked directly rather than assumed kept in step.

    `store_root` is deliberately the one exception: `Config()`'s own default (`./store`)
    is for running outside a container at all (every test in this suite, a bare `python -m
    onetrace_console serve`); the shipped file's `/data` is the one mounted volume the
    Dockerfile and `VOLUME ["/data"]` actually give it. Checked as its own, explicit
    assertion below rather than silently excluded from the comparison.

    `sign_in.enabled` is no longer an exception: the schema's
    own default is now ON, the same as the shipped file's. Local mode -- no file named at
    all -- forces it off, and the test server names it off explicitly.
    """
    data = json.loads(SHIPPED_DEFAULT.read_text(encoding="utf-8"))
    examined(len(data), "keys in the shipped default config")
    assert data["store_root"] == "/data", data["store_root"]
    assert data["sign_in"]["enabled"] is True, data["sign_in"]
    rest_shipped = {k: v for k, v in data.items() if k != "store_root"}
    rest_default = {k: v for k, v in asdict(Config()).items() if k != "store_root"}
    assert rest_shipped == rest_default, (
        f"config/default.json (minus store_root, sign_in.enabled) does not match "
        f"Config()'s own defaults:\n  shipped: {rest_shipped}\n  Config(): {rest_default}")


def test_an_unset_env_var_uses_built_in_defaults(monkeypatch, examined):
    monkeypatch.delenv("ONETRACE_CONSOLE_CONFIG", raising=False)
    examined(1, "load_from_env() calls with the variable unset")
    assert load_from_env() == Config()


def test_a_named_but_missing_file_refuses_rather_than_falling_back(monkeypatch, tmp_path, examined):
    missing = tmp_path / "nope.json"
    monkeypatch.setenv("ONETRACE_CONSOLE_CONFIG", str(missing))
    examined(1, "config paths that do not exist")
    with pytest.raises(ConfigError, match="is not a file"):
        load_from_env()


def test_an_unknown_key_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"host": "127.0.0.1", "listen_forever": True}), encoding="utf-8")
    examined(1, "config files with an unknown key")
    with pytest.raises(ConfigError, match="unknown configuration key"):
        load(path)


def test_malformed_json_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    examined(1, "malformed config files")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load(path)


def test_a_valid_file_overrides_only_the_keys_it_names(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"port": 9999}), encoding="utf-8")
    examined(1, "config files with one key set")
    got = load(path)
    assert got.port == 9999
    assert got.host == Config().host, "an unset key should keep its default, not become empty"


def test_extensions_default_off(examined):
    examined(1, "a bare Config()")
    assert Config().extensions == {"onedoor": False}


def test_a_config_file_can_turn_the_onedoor_extension_on(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"extensions": {"onedoor": True}}), encoding="utf-8")
    examined(1, "config files enabling the onedoor extension")
    got = load(path)
    assert got.extensions == {"onedoor": True}


def test_an_unknown_extension_name_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"extensions": {"onedor": True}}), encoding="utf-8")
    examined(1, "config files naming an unknown extension")
    with pytest.raises(ConfigError, match="unknown extension"):
        load(path)


def test_a_non_boolean_extension_flag_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"extensions": {"onedoor": "true"}}), encoding="utf-8")
    examined(1, "config files with a non-boolean extension flag")
    with pytest.raises(ConfigError, match="must be true or false"):
        load(path)


def test_extensions_must_itself_be_an_object(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"extensions": ["onedoor"]}), encoding="utf-8")
    examined(1, "config files where extensions is not an object")
    with pytest.raises(ConfigError, match="'extensions' must be a JSON object"):
        load(path)


def test_sign_in_default_on(examined):
    """The schema's own default is on. A file that leaves `sign_in` out
    gets sign-in; only local mode, with no file at all, forces it off."""
    examined(1, "a bare Config()")
    assert Config().sign_in["enabled"] is True


def test_a_config_file_can_turn_sign_in_on(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"enabled": True}}), encoding="utf-8")
    examined(1, "config files enabling sign_in")
    got = load(path)
    assert got.sign_in["enabled"] is True
    #: Setting one key leaves every other sign_in key at its own default, not blanked.
    assert got.sign_in["session_idle_timeout_seconds"] == 1800


def test_an_unknown_sign_in_key_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"enable": True}}), encoding="utf-8")
    examined(1, "config files naming an unknown sign_in key")
    with pytest.raises(ConfigError, match="unknown sign_in key"):
        load(path)


def test_a_non_boolean_sign_in_enabled_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"enabled": "yes"}}), encoding="utf-8")
    examined(1, "config files with a non-boolean sign_in.enabled")
    with pytest.raises(ConfigError, match="sign_in.enabled must be true or false"):
        load(path)


def test_sign_in_must_itself_be_an_object(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": ["enabled"]}), encoding="utf-8")
    examined(1, "config files where sign_in is not an object")
    with pytest.raises(ConfigError, match="'sign_in' must be a JSON object"):
        load(path)


def test_a_non_integer_session_timeout_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"session_idle_timeout_seconds": "30m"}}),
                    encoding="utf-8")
    examined(1, "config files with a non-integer session timeout")
    with pytest.raises(ConfigError, match="must be an integer"):
        load(path)


def test_a_bool_is_refused_where_an_integer_belongs(tmp_path, examined):
    """`bool` is an `int` subclass in Python -- checked explicitly so `true`/`false`
    typed where a count belongs is refused, not silently read as 1/0."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"rate_limit_window_seconds": True}}),
                    encoding="utf-8")
    examined(1, "a bool given where an integer sign_in value belongs")
    with pytest.raises(ConfigError, match="must be an integer"):
        load(path)


def test_a_non_string_tls_path_is_refused(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"tls_cert_path": 5}}), encoding="utf-8")
    examined(1, "config files with a non-string TLS path")
    with pytest.raises(ConfigError, match="must be a string"):
        load(path)


def test_tls_cert_and_key_must_be_set_together(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"tls_cert_path": "/certs/a.pem"}}),
                    encoding="utf-8")
    examined(1, "config files naming a TLS cert path with no key path")
    with pytest.raises(ConfigError, match="must be set together"):
        load(path)


def test_tls_cert_and_key_together_is_accepted(tmp_path, examined):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"sign_in": {"tls_cert_path": "/certs/a.pem",
                                            "tls_key_path": "/certs/a.key"}}),
                    encoding="utf-8")
    examined(1, "config files naming both a TLS cert and key path")
    got = load(path)
    assert got.sign_in["tls_cert_path"] == "/certs/a.pem"
    assert got.sign_in["tls_key_path"] == "/certs/a.key"
