"""The console reads onetrace-explain's configuration for the model's name only.

To say "Sent to provider:name and waiting for its reply", the console reads the [model] table's
`provider` and `name` from the file the command reads, as data; it never imports the package, and
never reads, keeps, logs or shows `key_env`, `base_url`, `params` or any other key. Held here: a
configuration holding all of them, each with a value found nowhere else, and a press through the
console; then the page, the press's state, the attempt file, the access log and the console's own
output name `provider:name` only.

The model is `fake:PATH` (tests/fixtures/explain/): the command calls nothing, and with that provider
its own lines name no endpoint. (With a networked provider the command's own first-send question
names the endpoint it would send to, in its words, as the panel has shown them since 0.3.0; that is
the command's output, not the console's reading of the file.)
"""
from __future__ import annotations

import json
import time
import urllib.request

from tests.test_explain_panel import REPLIES, pair, toml_string  # noqa: F401  (pair: a fixture)

#: A value for each key the console must not take, found nowhere but in the file.
MARKS = {"base_url": "http://never-shown-base.invalid/v1", "key_env": "NEVER_SHOWN_KEY_ENV",
         "temperature": "0.987654321", "other": "never-shown-other-value", "table": "never-shown-other-table"}


def _config(path, reply) -> str:
    """The configuration, with the model's provider and name and every other key."""
    text = (f"[model]\nprovider = \"fake\"\nname = {toml_string(str(reply))}\n"
            f"base_url = \"{MARKS['base_url']}\"\nkey_env = \"{MARKS['key_env']}\"\n"
            f"other = \"{MARKS['other']}\"\n\n[model.params]\ntemperature = \"{MARKS['temperature']}\"\n\n"
            f"[elsewhere]\nvalue = \"{MARKS['table']}\"\n")
    path.write_text(text, encoding="utf-8")
    return text


def leaks(texts: dict[str, str]) -> list[str]:
    return [f"{where} shows {key}'s value" for where, text in texts.items() for key, mark in MARKS.items()
            if mark in text]


def test_only_provider_and_name_reach_the_page_the_state_the_attempt_and_the_logs(
        pair, server, monkeypatch, capsys, examined):
    from onetrace_console import explain
    from onetrace_console.serve import Handler
    store, comparison, config = pair
    base, root = server
    _config(config, REPLIES / "mixed.json")
    monkeypatch.setattr(Handler, "store", store)
    assert explain.configured_model() == f"fake:{REPLIES / 'mixed.json'}"
    seen_states = []
    req = urllib.request.Request(f"{base}/explain?c={comparison.key}", method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        assert r.status == 202
    while True:
        with urllib.request.urlopen(f"{base}/explain/state?c={comparison.key}", timeout=30) as r:
            s = r.read().decode("utf-8")
        seen_states.append(s)
        if not json.loads(s)["running"]:
            break
        time.sleep(0.05)
    assert explain.wait(comparison.key, 120)
    folder = explain.folder_of(store, comparison.key)
    texts = {"the page": explain.panel(comparison, store, public=False),
             "the press's state": "\n".join(seen_states),
             "the attempt file": "\n".join(p.read_text(encoding="utf-8") for p in (folder / "attempts").glob("*.json")),
             "the access log": "\n".join(p.read_text(encoding="utf-8") for p in (root / "access_log").rglob("*") if p.is_file()),
             "the console's output": "\n".join(capsys.readouterr())}
    examined(len(texts), "places the console writes or shows")
    assert leaks(texts) == []
    assert explain.explanations(store, comparison.key), "no explanation was made"


def test_sabotage_the_model_named_with_its_endpoint_is_named(pair, monkeypatch, examined):
    """configured_model() reading base_url too: the page while a press runs shows it."""
    import tomllib
    from pathlib import Path

    from onetrace_console import explain
    store, comparison, config = pair
    _config(config, REPLIES / "mixed.json")

    def wider():
        m = tomllib.loads(Path(config).read_text(encoding="utf-8"))["model"]
        return f"{m['provider']}:{m['name']} at {m['base_url']}"
    monkeypatch.setattr(explain, "configured_model", wider)
    folder = explain.folder_of(store, comparison.key)
    folder.mkdir(parents=True, exist_ok=True)
    explain._set_state(folder, {"kind": "explain", "started_at": explain._now(), "model": explain.configured_model(),
                                "step": "waiting"})
    examined(1, "planted reading")
    assert leaks({"the page": explain.panel(comparison, store, public=False)}) != []
    (folder / explain.RUNNING_FILE).unlink()
