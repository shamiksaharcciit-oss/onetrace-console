"""The setup page, `/explain/setup`: a local console's read-only guide to setting up Explain.

Held here:
- it is served on a local console in its three steps, with the provider and model the console
  already reads, the kinds always sent, the two flags and whether the Explain button uses them,
  the three promises and the steps a person takes, and linked from the panel and the sidebar;
- it writes nothing (the store and the configuration's folder byte for byte, before and after), and
  has no form and no control that sends or saves;
- it never holds a value of `key_env`, `base_url` or `params`, nor the key: a value is planted in
  each, and in the variable `key_env` names, and none must appear (a sabotage that reads `base_url`
  is named);
- a public console has no setup page, and none of its pages links to one.
"""
from __future__ import annotations

import dataclasses
import hashlib
import re
import urllib.error
import urllib.request
from html import unescape

import pytest

from tests.test_explain_config_read import MARKS, leaks
from tests.test_explain_panel import REPLIES, pair, toml_string  # noqa: F401  (pair: a fixture)

#: A value for the key itself, in the variable the configuration names; found nowhere else.
KEY_VALUE = "never-shown-key-value-0123456789"


def _planted(config) -> None:
    """A configuration naming a model, with a value in each key the console must not take."""
    config.write_text(
        f"[model]\nprovider = \"fake\"\nname = {toml_string(str(REPLIES / 'mixed.json'))}\n"
        f"base_url = \"{MARKS['base_url']}\"\nkey_env = \"{MARKS['key_env']}\"\nother = \"{MARKS['other']}\"\n\n"
        f"[model.params]\ntemperature = \"{MARKS['temperature']}\"\n\n[elsewhere]\nvalue = \"{MARKS['table']}\"\n",
        encoding="utf-8")


def _get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _main(page: str) -> str:
    found = re.search(r"<main>(.*)</main>", page, re.S)
    return found.group(1) if found else ""


def _text(fragment: str) -> str:
    """The words, as a reader reads them: an inline element joins its neighbours, a block parts them."""
    fragment = re.sub(r"</?(code|strong|span|a)\b[^>]*>", "", fragment)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _tree(*roots) -> dict[str, str]:
    """Every file under the folders, by path: its sha256 and its modification time."""
    out = {}
    for root in roots:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                out[str(p)] = f"{hashlib.sha256(p.read_bytes()).hexdigest()} {p.stat().st_mtime_ns}"
    return out


@pytest.fixture
def local(pair, server, monkeypatch):
    from onetrace_console.serve import Handler, _render_all_pages, _render_diff_page
    store, comparison, config = pair
    base, root = server
    monkeypatch.setattr(Handler, "store", store)
    _render_all_pages(store, root, Handler.config)
    _render_diff_page(comparison, store, root)
    return base, root, store, comparison, config


# ------------------------------------------------------------------ what it says

def content_problems(main: str, *, named: str | None, path: str) -> list[str]:
    from onetrace_console import explain_setup as S
    said = _text(main)
    out = []
    heads = re.findall(r'<section class="step" id="step-(\d)" data-step="\d"><h2>(.*?)</h2>', main, re.S)
    if [(n, unescape(h)) for n, h in heads] != [(str(i), f"{i} · {w}") for i, w in enumerate(S.STEPS, start=1)]:
        out.append(f"steps {heads}")
    if named is not None and f"onetrace-explain's configuration names {named}." not in said:
        out.append("the model is not named")
    if named is None and f"No model is named in {path}. {S.SET_HERE}" not in said:
        out.append("no model, and the path and 'Set your model here.' are not said")
    for words in (*S.ALWAYS_SENT, *S.STAYS, *S.PROMISES, S.BUTTON_USES, "--include-text", "--redact NAME",
                  "pip install onetrace-explain", "On this machine", "Your model provider", "Show the packet"):
        if words not in said:
            out.append(f"missing: {words[:50]!r}")
    if f"Set [model] in {path}" not in said:
        out.append("the file's path is not given in the steps")
    if re.search(r"\bwhy\b", unescape(S.TITLE + " ".join(h for _, h in heads)), re.I):
        out.append("a heading says why")
    return out


def test_the_page_shows_its_three_steps_with_the_model_already_read(local, examined):
    base, _, _, _, config = local
    _planted(config)
    status, page = _get(f"{base}/explain/setup")
    examined(1, "setup page")
    assert status == 200
    assert content_problems(_main(page), named=f"fake:{REPLIES / 'mixed.json'}", path=str(config)) == []


def test_with_no_model_named_the_page_gives_the_file_s_path(local, examined):
    base, _, _, _, config = local
    status, page = _get(f"{base}/explain/setup")
    examined(1, "setup page, no model named")
    assert status == 200
    assert content_problems(_main(page), named=None, path=str(config)) == []


#: A configuration's folder as a Windows machine names it: on Windows the test's own folder has
#: backslashes; elsewhere it is put under a folder whose name holds them.
WINDOWS_SHAPED = "C:\\Users\\runneradmin\\AppData\\Local\\Temp"


def _windows_shaped(config, tmp_path, monkeypatch, named: bool):
    """The configuration moved to a folder whose path holds backslashes, the model (where `named`)
    a path in it too, as a Windows run writes both; (the model as the page must name it, the path)."""
    import os
    folder = (tmp_path / "config") if os.name == "nt" else (tmp_path / WINDOWS_SHAPED / "config")
    folder.mkdir(parents=True, exist_ok=True)
    moved = folder / "explain.toml"
    model = str(folder / "mixed.json")
    moved.write_text(f"[model]\nprovider = \"fake\"\nname = {toml_string(model)}\n" if named else "", encoding="utf-8")
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(moved))
    assert "\\" in str(moved)
    return (f"fake:{model}" if named else None), str(moved)


@pytest.mark.parametrize("named", [True, False], ids=["a model named", "none named"])
def test_a_windows_path_is_shown_as_written(local, tmp_path, monkeypatch, named, examined):
    """The model and the file's path with their backslashes as written, one each, under whatever
    the run's default encoding is (windows-noutf8 runs with PYTHONUTF8=0): a record's word is shown
    with each backslash doubled, which is not a path one can copy."""
    base, _, _, _, config = local
    model, path = _windows_shaped(config, tmp_path, monkeypatch, named)
    _, page = _get(f"{base}/explain/setup")
    examined(1, "setup page, its configuration under a backslashed path")
    assert content_problems(_main(page), named=model, path=path) == []


def test_sabotage_the_path_shown_as_a_record_s_word_is_named(local, tmp_path, monkeypatch, examined):
    from onetrace_console import explain_setup
    from onetrace_console.words import escape
    base, _, _, _, config = local
    model, path = _windows_shaped(config, tmp_path, monkeypatch, True)
    monkeypatch.setattr(explain_setup, "_as_written", escape)
    _, page = _get(f"{base}/explain/setup")
    examined(1, "setup page, the path drawn as a record's word")
    assert content_problems(_main(page), named=model, path=path) == [
        "the model is not named", "the file's path is not given in the steps"]


def test_the_panel_and_the_sidebar_link_to_it_on_a_local_console(local, examined):
    from onetrace_console.frame import SETUP_LINK
    base, _, _, comparison, _ = local
    _, page = _get(f"{base}/diff/{comparison.key}.html")
    examined(2, "links: the panel's and the sidebar's")
    panel = re.search(r'<section data-section="explain"[^>]*>.*?</section>', page, re.S).group(0)
    assert '<p data-explain="setup"><a href="/explain/setup">Set up Explain</a></p>' in panel
    assert page.count(SETUP_LINK) == 1


def examples_problems(main: str) -> list[str]:
    """The three `[model]` examples and the install line, each a `<pre>` whose lines are lines, and no
    escape sequence shown anywhere on the page: it is copied from."""
    from tests.test_no_escape_shown import escapes_shown
    blocks = [unescape(b) for b in re.findall(r"<pre><code>(.*?)</code></pre>", main, re.S)]
    out = []
    models = [b for b in blocks if b.startswith("[model]")]
    if len(models) != 2 or not any(b == "pip install onetrace-explain" for b in blocks):
        out.append(f"examples {[b[:20] for b in blocks]}")
    for b in models:
        if b.count("\n") < 3 or not b.splitlines()[1].startswith("provider = "):
            out.append(f"an example's lines are not lines: {b[:40]!r}")
    if escapes_shown(main):
        out.append(f"escapes shown: {escapes_shown(main)[:3]}")
    return out


def test_each_example_shows_its_lines_as_lines(local, examined):
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    examined(1, "setup page's examples")
    assert examples_problems(_main(page)) == []


def test_sabotage_an_escaped_line_break_in_an_example_is_named(local, monkeypatch, examined):
    """The examples drawn as a record's words are (`escape`): each line break shows as an escape."""
    from onetrace_console import explain_setup
    from onetrace_console.words import escape
    base, _, _, _, _ = local
    monkeypatch.setattr(explain_setup, "_code_block", lambda text: f"<pre><code>{escape(text)}</code></pre>")
    _, page = _get(f"{base}/explain/setup")
    examined(1, "planted examples")
    got = examples_problems(_main(page))
    assert len(got) == 3 and got[-1].startswith("escapes shown:"), got


# ------------------------------------------------------------------ it writes nothing, and offers nothing

def control_problems(main: str) -> list[str]:
    """A form, or a control that sends, runs or saves, in the page's own content."""
    out = []
    for tag in ("form", "button", "input", "select", "textarea"):
        if re.search(rf"<{tag}\b", main, re.I):
            out.append(f"a <{tag}>")
    for mark in ("data-explain-post", "data-compare-post", "method=", "/explain?", "/explain/check"):
        if mark in main:
            out.append(f"a press: {mark}")
    return out


def test_the_page_writes_nothing_and_has_no_control_that_sends_or_saves(local, examined):
    base, root, store, _, config = local
    _planted(config)
    from pathlib import Path
    before = _tree(root, Path(store.root), config.parent)
    status, page = _get(f"{base}/explain/setup")
    after = _tree(root, Path(store.root), config.parent)
    examined(len(before), "files under the store and the configuration's folder")
    assert status == 200
    #: The access log is the console's own record of the request, written for every page.
    changed = sorted(k for k in before.keys() | after.keys()
                     if before.get(k) != after.get(k) and "access_log" not in k)
    assert changed == []
    assert control_problems(_main(page)) == []


def test_sabotage_a_turn_on_button_planted_is_named(local, monkeypatch, examined):
    from onetrace_console import explain_setup
    base, _, _, _, _ = local
    real = explain_setup.body
    monkeypatch.setattr(explain_setup, "body", lambda store: real(store).replace(
        "</div>", '<form method="post" action="/explain/setup"><button>Turn on Explain</button></form></div>', 1))
    _, page = _get(f"{base}/explain/setup")
    examined(1, "planted page")
    assert control_problems(_main(page)) == ["a <form>", "a <button>", "a press: method="]


# ------------------------------------------------------------------ the key and its neighbours, never

def test_no_value_of_key_env_base_url_or_params_nor_the_key_is_on_the_page(local, monkeypatch, examined):
    base, _, _, _, config = local
    _planted(config)
    monkeypatch.setenv(MARKS["key_env"], KEY_VALUE)
    status, page = _get(f"{base}/explain/setup")
    examined(len(MARKS) + 1, "planted values")
    assert status == 200 and "Your model provider" in page
    assert leaks({"the setup page": page}) == []
    assert KEY_VALUE not in page


def test_sabotage_the_model_read_with_its_endpoint_and_key_is_named(local, monkeypatch, examined):
    """`configured_model` reading `base_url` and the key's variable: both are named."""
    import os
    import tomllib
    from pathlib import Path

    from onetrace_console import explain
    base, _, _, _, config = local
    _planted(config)
    monkeypatch.setenv(MARKS["key_env"], KEY_VALUE)

    def wider():
        m = tomllib.loads(Path(config).read_text(encoding="utf-8"))["model"]
        return f"{m['provider']}:{m['name']} at {m['base_url']} with {os.environ.get(m['key_env'], '')}"
    monkeypatch.setattr(explain, "configured_model", wider)
    _, page = _get(f"{base}/explain/setup")
    examined(1, "planted reading")
    assert leaks({"the setup page": page}) == ["the setup page shows base_url's value"]
    assert KEY_VALUE in page


# ------------------------------------------------------------------ a public console

@pytest.fixture
def public(local, monkeypatch):
    from onetrace_console.serve import Handler, _render_all_pages, _render_diff_page
    _, root, store, comparison, _ = local
    monkeypatch.setattr(Handler, "config", dataclasses.replace(Handler.config, public=True))
    _render_all_pages(store, root, Handler.config)
    _render_diff_page(comparison, store, root, public=True)
    return local


def public_problems(base: str, comparison) -> list[str]:
    out = []
    status, _ = _get(f"{base}/explain/setup")
    if status != 404:
        out.append(f"the setup page answers {status}")
    for rel in ("/", "/comparisons.html", f"/diff/{comparison.key}.html"):
        _, page = _get(base + rel)
        if "/explain/setup" in page:
            out.append(f"{rel} links to the setup page")
    return out


def test_a_public_console_has_no_setup_page_and_no_link_to_one(public, examined):
    base, _, _, comparison, _ = public
    examined(4, "a request for the page, and three pages")
    assert public_problems(base, comparison) == []


def test_sabotage_the_link_drawn_on_a_public_console_is_named(public, monkeypatch, examined):
    from onetrace_console import frame
    base, _, _, comparison, _ = public
    real = frame.footer
    monkeypatch.setattr(frame, "footer", lambda user, public=False, setup_link=False: real(user, setup_link=True))
    examined(4, "a request for the page, and three pages")
    assert public_problems(base, comparison) == [f"{rel} links to the setup page"
                                                 for rel in ("/", "/comparisons.html", f"/diff/{comparison.key}.html")]


def test_an_export_s_pages_have_no_link_to_the_setup_page(local, tmp_path, examined):
    """An export's pages are files: nothing on them links to a page only a local console serves."""
    from onetrace_console.export_static import export
    from pathlib import Path
    _, _, store, comparison, _ = local
    dest = tmp_path / "export"
    export(Path(store.root).parent, [comparison.run_a, comparison.run_b], dest)
    pages = [p for p in dest.rglob("*.html")]
    examined(len(pages), "exported pages")
    assert pages and [p.name for p in pages if "/explain/setup" in p.read_text(encoding="utf-8")] == []
