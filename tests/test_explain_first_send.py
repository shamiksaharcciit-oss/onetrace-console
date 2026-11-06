"""Console 0.6.1 item 7: the first-send question in plain words.

"Before anything is sent", then "onetrace-explain has not sent these kinds of item to <host> before:",
each kind as a phrase with its id beside it, from the console's own table (`explain.KIND_PHRASES`); a kind
not in the table shows its id alone. "Show the packet" first, "Send to <host>" the one primary button,
"Cancel". The intro reads "Nothing is sent until you confirm", in every state.
"""
from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from types import SimpleNamespace

import pytest

KEY = "a" * 64


@pytest.fixture
def planted(tmp_path, monkeypatch):
    """A panel drawn from a planted press: a model at a named address, and a prepared packet of `kinds`."""
    from onetrace_console import explain
    from onetrace_console.store import Store
    config = tmp_path / "config" / "explain.toml"
    config.parent.mkdir()
    config.write_text('[model]\nprovider = "anthropic"\nname = "a-model"\nkey_env = "PLANTED_KEY"\n', encoding="utf-8")
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    monkeypatch.setattr(explain, "command", lambda: Path("onetrace-explain"))
    monkeypatch.setattr(explain, "too_long", lambda store: None)
    store = Store(tmp_path / "store")

    def draw(kinds: list[str] | None, kind: str = "prepare") -> str:
        folder = explain.folder_of(store, KEY)
        (folder / explain.REPORT).mkdir(parents=True, exist_ok=True)
        if kinds is not None:
            raw = json.dumps({"format": "onetrace-explain-evidence/0.1", "items": [], "kinds": kinds})
            explain._keep(folder, kind, [explain.REPORT, "--dry-run"], SimpleNamespace(
                returncode=0, stdout=f"{raw}\n{len(raw)} bytes, sha256 x; dry run: nothing sent\n".encode(), stderr=b""))
        return explain.panel(SimpleNamespace(key=KEY), store, public=False)
    return draw, config


def _question(panel: str) -> str:
    got = re.search(r'<div data-explain="first-send">(.*?)</div>', panel, re.S)
    assert got, "no first-send question"
    return got.group(1)


def test_one_kind_reads_as_its_phrase_with_its_id(planted):
    draw, _ = planted
    q = _question(draw(["inputs_differ"]))
    assert "<h3>Before anything is sent</h3>" in q
    assert "<p>onetrace-explain has not sent these kinds of item to api.anthropic.com before:</p>" in q
    assert re.findall(r"<li [^>]*>(.*?)</li>", q) == ["which inputs differ, by name and fingerprint (<code>inputs_differ</code>)"]


def test_several_kinds_each_on_its_line_in_order(planted):
    from onetrace_console import explain
    draw, _ = planted
    kinds = ["end_outputs", "instrument", "node", "outcome", "output", "upstream", "verdict"]
    items = re.findall(r'<li data-kind="([^"]+)">(.*?)</li>', _question(draw(kinds)))
    assert [k for k, _ in items] == kinds
    for k, said in items:
        assert unescape(re.sub(r"<[^>]+>", "", said)) == f"{explain.KIND_PHRASES[k]} ({k})"


def test_an_unknown_kind_shows_its_id_alone(planted):
    draw, _ = planted
    items = re.findall(r'<li data-kind="([^"]+)">(.*?)</li>', _question(draw(["verdict", "a_kind_from_later"])))
    assert dict(items)["a_kind_from_later"] == "<code>a_kind_from_later</code>"


def test_the_buttons_show_the_packet_first_send_named_and_primary_then_cancel(planted):
    draw, _ = planted
    panel = draw(["verdict"])
    row = re.search(r'<p data-explain="buttons">(.*?)</p>', panel, re.S).group(1)
    buttons = re.findall(r"<button([^>]*)>([^<]*)</button>", row)
    assert [w for _, w in buttons] == ["Show the packet", "Send to api.anthropic.com", "Cancel"]
    assert [a for a, _ in buttons if 'class="primary"' in a] == [buttons[1][0]]


def test_every_kind_the_packet_can_hold_has_its_words(explain_command):
    """The kinds the published onetrace-explain writes, as its packet builder names them, each in the table."""
    from onetrace_console import explain
    _found, lib = explain_command
    source = (lib / "onetrace_explain" / "packet.py").read_text(encoding="utf-8")
    kinds = set(re.findall(r'add\("([a-z_]+)"', source)) | {"input", "output"}
    assert kinds - set(explain.KIND_PHRASES) == set()


@pytest.mark.parametrize("state", ["no model", "ready", "first send", "prepared", "cancelled"])
def test_the_intro_says_nothing_is_sent_until_you_confirm_in_each_state(planted, state):
    from onetrace_console import explain
    draw, config = planted
    if state == "no model":
        config.write_text("", encoding="utf-8")
        panel = draw(None)
    elif state == "ready":
        panel = draw(None)
    elif state == "first send":
        panel = draw(["verdict"])
    elif state == "prepared":
        (config.parent / "explain-sent.json").write_text(json.dumps({"https://api.anthropic.com": ["verdict"]}),
                                                         encoding="utf-8")
        panel = draw(["verdict"])
    else:
        draw(["verdict"])
        folder = explain.folder_of(__import__("onetrace_console.store", fromlist=["Store"]).Store(
            config.parent.parent / "store"), KEY)
        explain._keep(folder, "cancel", [], SimpleNamespace(returncode=0, stdout=b"", stderr=b""), command="")
        panel = draw(None)
    intro = re.search(r'<p data-explain="what">(.*?)</p>', panel, re.S).group(1)
    assert unescape(re.sub(r"<[^>]+>", "", intro)).endswith("Nothing is sent until you confirm.")
    assert "until you press Explain" not in panel
    #: Nothing of a key's value, nor the variable that holds it, on the panel.
    assert "PLANTED_KEY" not in panel
