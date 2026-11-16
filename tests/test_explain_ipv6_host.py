"""A model at an IPv6 address, `[::1]` on this machine among them: its panel and the gear's row are drawn.

onetrace-explain names where a packet goes without the address's brackets (`http://::1:9/v1`, its
`Model.endpoint`), and the console reads its record of what it sent by that name, so the name stays as it
writes it. The address a button and a line show, `explain.host`, is read from it without raising.
"""

from __future__ import annotations

from tests.test_explain_panel import _diff, _panel, pair, toml_string  # noqa: F401  (pair: a fixture)


def test_an_ipv6_model_s_address_is_read_and_its_panel_drawn(pair, examined):
    from onetrace_console import explain, settings_menu

    store, comparison, config = pair
    config.write_text(
        f'[model]\nprovider = "openai"\nname = "m"\nbase_url = {toml_string("http://[::1]:9/v1")}\nkey_env = ""\n',
        encoding="utf-8",
    )
    where = explain.endpoint(explain.model_config())
    examined(3, "the endpoint, the panel and the gear's row")
    assert where == "http://::1:9/v1"
    assert explain.host(where) == "::1:9"
    assert 'data-flow="ready"' in _panel(_diff(store, comparison))
    assert settings_menu.explain_row().state == "on"
