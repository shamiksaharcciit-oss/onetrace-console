"""The console's link in each forwarded trace (`forwarding.console_url`): with the setting, the root span of every
trace sent carries `onetrace.console_url`, the run's page under the console's address; without it, no attribute, and
the setup page says the link is off and how to turn it on. Nothing else in the trace changes. Every request goes to a
recording receiver on loopback: no backend, no key and no network."""

from __future__ import annotations

import json
from dataclasses import replace
from html import unescape

import pytest

from onetrace_console import forward_pages as P
from onetrace_console import forwarding as F
from tests.http_limits import limit
from tests.otlp_receiver import Receiver
from tests.test_forwarding import _export, _without_check, stored  # noqa: F401 - a fixture, requested by name

URL = "https://onetrace.example.org"
ID = "0123456789abcdef"


def _spans(doc: dict) -> list[dict]:
    return [s for rs in doc["resourceSpans"] for ss in rs["scopeSpans"] for s in ss["spans"]]


def _root(doc: dict) -> dict:
    [root] = [s for s in _spans(doc) if not s.get("parentSpanId")]
    return root


def _links(doc: dict) -> list[tuple[str, dict]]:
    return [
        (s["spanId"], a["value"])
        for s in _spans(doc)
        for a in s.get("attributes", [])
        if a["key"] == F.CONSOLE_URL_ATTRIBUTE
    ]


def _without_link(doc: dict) -> dict:
    for s in _spans(doc):
        s["attributes"] = [a for a in s.get("attributes", []) if a["key"] != F.CONSOLE_URL_ATTRIBUTE]
    return doc


def test_with_the_setting_the_root_span_links_to_the_run_s_page_and_nothing_else_changes(stored, store, examined):
    sent = json.loads(F.trace_of(stored, store, "records agree", console_url=URL))
    assert F.CONSOLE_URL_ATTRIBUTE == "onetrace.console_url"
    assert _links(sent) == [(_root(sent)["spanId"], {"stringValue": f"{URL}/runs/{stored.key}/case.html"})]
    assert _without_check(_without_link(sent)) == json.loads(_export(stored, store)), "nothing else changes"
    examined(len(_spans(sent)), "spans")


def test_without_the_setting_no_span_carries_the_attribute(stored, store, examined):
    sent = F.trace_of(stored, store, "records agree")
    assert _links(json.loads(sent)) == []
    assert sent == F.with_check(_export(stored, store), "records agree"), "the trace is as it was before the setting"
    assert F.trace_of(stored, store, "records agree", console_url="") == sent
    examined(len(_spans(json.loads(sent))), "spans")


@pytest.mark.parametrize(
    "address, key, page",
    [
        (URL, "ab" * 32, f"{URL}/runs/{'ab' * 32}/case.html"),
        (URL + "/", "ab" * 32, f"{URL}/runs/{'ab' * 32}/case.html"),
        ("https://example.org/one trace/", "ab" * 32, f"https://example.org/one%20trace/runs/{'ab' * 32}/case.html"),
        (URL, "a b/c?d#e%f", f"{URL}/runs/a%20b%2Fc%3Fd%23e%25f/case.html"),
        ("http://127.0.0.1:8080/console", "k" * 64, f"http://127.0.0.1:8080/console/runs/{'k' * 64}/case.html"),
    ],
)
def test_the_run_s_page_is_escaped_under_the_address(address, key, page, examined):
    assert F.run_page(address, key) == page
    examined(1, "address")


def test_a_run_whose_page_path_needs_escaping_is_linked_escaped(stored, store, examined):
    odd = "a b/c?d#e"
    sent = json.loads(F.with_check(_export(stored, store), "records agree", link=F.run_page(URL, odd)))
    assert _links(sent) == [(_root(sent)["spanId"], {"stringValue": f"{URL}/runs/a%20b%2Fc%3Fd%23e/case.html"})]
    examined(1, "trace")


@pytest.mark.parametrize("console_url, linked", [(URL, True), ("", False)])
def test_the_trace_a_destination_receives_has_the_link_only_with_the_setting(
    tmp_path, stored, store, console_url, linked, examined
):
    with Receiver([200]) as r:
        d = F.destination({"id": ID, "name": "the receiver", "endpoint": r.endpoint})
        F._write(tmp_path, [d])
        F.enqueue(tmp_path, stored.key, "records agree")
        assert F.run_once(tmp_path, store, now=1000.0, console_url=console_url) == ["sent"]
        [got] = r.traces()
    doc = json.loads(got.body)
    want = [(_root(doc)["spanId"], {"stringValue": f"{URL}/runs/{stored.key}/case.html"})] if linked else []
    assert _links(doc) == want
    assert (F.CONSOLE_URL_ATTRIBUTE.encode() in got.body) is linked
    examined(1, "trace received")


@pytest.mark.parametrize(
    "value, refused",
    [
        (URL, None),
        ("https://onetrace.example.org:8443/console/", None),
        ("http://127.0.0.1:8080", None),
        ("http://localhost:8080/", None),
        ("http://onetrace.example.org", "http is only for an address on this machine"),
        ("ftp://onetrace.example.org", "starts https://"),
        ("https://user:pw@onetrace.example.org", "no user or password"),
        ("https://onetrace.example.org/?a=1", "no query or fragment"),
        ("https://onetrace.example.org/#runs", "no query or fragment"),
        ("onetrace.example.org", "starts https://"),
    ],
)
def test_the_setting_is_https_or_http_on_this_machine_as_forwarding_s_rule(tmp_path, value, refused, examined):
    from onetrace_console.config import ConfigError, load

    p = tmp_path / "c.json"
    p.write_text(json.dumps({"forwarding": {"console_url": value}}), encoding="utf-8")
    if refused is None:
        assert load(p).forwarding == {"console_url": value}
    else:
        with pytest.raises(ConfigError, match="forwarding.console_url") as e:
            load(p)
        assert refused in str(e.value)
    examined(1, "value")


def test_the_setting_is_empty_by_default_and_its_section_takes_no_other_key(tmp_path, examined):
    from onetrace_console.config import Config, ConfigError, load

    assert Config().forwarding == {"console_url": ""}
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"forwarding": {}}), encoding="utf-8")
    assert load(p).forwarding == {"console_url": ""}
    p.write_text(json.dumps({"forwarding": {"console_link": URL}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="console_link"):
        load(p)
    p.write_text(json.dumps({"forwarding": {"console_url": 1}}), encoding="utf-8")
    with pytest.raises(ConfigError, match="forwarding.console_url"):
        load(p)
    examined(4, "files")


def _said(html: str) -> str:
    import re

    start = html.rindex("<p", 0, html.index('data-forwarding="link"'))
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html[start : html.index("</p>", start)])).split())


def test_the_setup_page_says_the_link_is_off_and_how_to_turn_it_on(tmp_path, examined):
    said = _said(P.page(tmp_path))
    assert said.startswith(P.LINK_OFF.split("{")[0].strip()), said
    assert "forwarding.console_url" in said and "configuration file" in said
    examined(1, "page")


def test_the_setup_page_says_the_link_is_on_and_to_where(tmp_path, examined):
    said = _said(P.page(tmp_path, console_url=URL))
    assert URL + "/runs/" in said and F.CONSOLE_URL_ATTRIBUTE in said, said
    assert "off" not in said.split()
    examined(1, "page")


def test_the_served_setup_page_and_the_sender_read_the_console_s_setting(server, monkeypatch, examined):
    import urllib.request

    from onetrace_console.serve import Handler, start_forwarding

    base, root = server
    monkeypatch.setattr(Handler, "config", replace(Handler.config, forwarding={"console_url": URL}))
    with urllib.request.urlopen(base + P.PATH, timeout=limit(30)) as r:
        html = r.read().decode("utf-8")
    assert URL + "/runs/" in _said(html)
    sender = start_forwarding(root, Handler.store, Handler.config)
    try:
        assert sender.console_url == URL
    finally:
        sender.stop()
    examined(2, "readers of the setting")
