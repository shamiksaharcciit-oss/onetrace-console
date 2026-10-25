"""A comparison's explanation panel: the `onetrace-explain` command, run as a person runs it.

Every case is driven by the command itself with a model of `fake:PATH`, whose replies are kept
under tests/fixtures/explain/ only, so no model is ever called and nothing leaves this machine. The
first-send question needs an endpoint the command has not sent to; the tests name an
OpenAI-compatible one on this machine's loopback at a port nothing listens on, which the command
asks about before any send and never reaches without `--yes`.

The pair: three stages, `load`, `score` and `decide`; the candidate's scorer has another setting,
so the comparison first differs at `score#1`.
"""
from __future__ import annotations

import json
import re
import socket
import subprocess
import sys
from html import unescape
from pathlib import Path

import pytest

GENERATED_AT = "2026-10-04T12:00:00+00:00"
RAN_AT = "2026-09-26T12:00:00+02:00"
REPLIES = Path(__file__).resolve().parent / "fixtures" / "explain"
LABEL = "Suggested explanation — AI-generated, may be wrong"
TITLE = "Suggested explanation"


def _make(root: Path) -> list[Path]:
    from onetrace.emit import Instrument, Recorder
    out = []
    for name, x in (("a", "1"), ("b", "2")):
        rec = Recorder(str(root / name), run_id=f"explain-{name}", declared_stages=["load", "score", "decide"],
                       manifest=Path(__file__), policy="fail-closed", topology=True,
                       anchor_reason="a test record")

        def body(stage, value, reads=()):
            def f(ctx):
                for r in reads:
                    ctx.read_receipt(r)
                return ctx.write_json(f"{stage}.json", {stage: value})
            return f
        rec.run_node("load", "1", Instrument("loader", "tool", "1.0.0", {"source": "docs"}), body("load", "1"))
        rec.run_node("score", "1", Instrument("scorer", "tool", "1.0.0", {"threshold": x}),
                     body("score", x, ["load"]))
        rec.run_node("decide", "1", Instrument("decider", "tool", "1.0.0", {"rule": "max"}),
                     body("decide", x, ["score"]))
        rec.close()
        out.append(root / name)
    return out


@pytest.fixture
def pair(tmp_path, monkeypatch, explain_installed):
    """A fresh store holding the pair and its comparison, and a config naming no model yet; the
    console finds the published onetrace-explain, installed apart (tests/conftest.py)."""
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    from tests.test_compare import _deliver
    _require_installed()
    store = Store(tmp_path / "store")
    a, b = (run_and_record(_deliver(f, store, outputs=True), store, ran_at=RAN_AT)
            for f in _make(tmp_path / "made"))
    comparison = compare(a, b, store)
    config = tmp_path / "config" / "explain.toml"
    config.parent.mkdir()
    config.write_text("", encoding="utf-8")
    monkeypatch.setenv("ONETRACE_EXPLAIN_CONFIG", str(config))
    return store, comparison, config


def toml_string(value: str) -> str:
    """A TOML basic string of `value`: each backslash and quote escaped, so a Windows path is read
    back as written."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _model(config: Path, spec: str) -> None:
    provider, _, name = spec.partition(":")
    config.write_text(f"[model]\nprovider = {toml_string(provider)}\nname = {toml_string(name)}\n"
                      + (f"base_url = {toml_string('http://127.0.0.1:%d/v1' % _closed_port())}\n"
                         if provider == "openai" else ""),
                      encoding="utf-8")


def _closed_port() -> int:
    """A loopback port nothing listens on: bound, then released."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fake(config: Path, reply: str) -> None:
    _model(config, f"fake:{REPLIES / reply}")


def in_full(attempt: dict) -> str:
    """A press of the command, for a failure message: its exit and the last line of its stderr
    first, so a message cut short still names them, then its stdout and stderr whole."""
    err = attempt.get("stderr", "")
    last = err.strip().splitlines()[-1] if err.strip() else ""
    return (f"onetrace-explain exit {attempt.get('exit')}; its stderr ends: {last}\n"
            f"--- {attempt.get('command')}, stdout:\n{attempt.get('stdout', '')}\n--- stderr:\n{err}")


def tried(store, comparison) -> str:
    """Every press the console kept for the comparison, in the order pressed, each in full: the
    first that went wrong leads."""
    from onetrace_console import explain
    return "\n".join(in_full(a) for a in explain.attempts(store, comparison.key)) or "no press kept"


def recorded(stdout: str) -> str | None:
    """The run id of the command's `recorded: <its record>` line, read by lines, its path split at
    either separator: on Windows the command ends its lines with CR LF and writes the path with
    backslashes."""
    line = next((ln for ln in stdout.splitlines() if ln.startswith("recorded: ")), None)
    return re.split(r"[\\/]", line[len("recorded: "):].strip())[-1] if line else None


def _diff(store, comparison) -> str:
    from onetrace_console.render import render_diff
    return render_diff(store.get_comparison(comparison.key), store, generated_at=GENERATED_AT)


def _panel(page: str) -> str:
    found = re.search(r'<section data-section="explain"[^>]*>.*?</section>', page, re.S)
    return found.group(0) if found else ""


def _text(fragment: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def _without_panel(page: str) -> str:
    return re.sub(r'<section data-section="explain"[^>]*>.*?</section>', "", page, flags=re.S)


# ------------------------------------------------------------------ what it shows

def explained_problems(page: str) -> list[str]:
    """An explanation as the command wrote mixed.json's: its label and model, the kept claims in
    order with their kinds' words and cites, the checks, the drops."""
    panel = _panel(page)
    out = []
    article = re.search(r"<article data-explanation=.*?</article>", panel, re.S)
    if article is None:
        return ["no explanation drawn"]
    a = article.group(0)
    if LABEL not in unescape(a) or "fake:" not in unescape(a):
        out.append("the label or the model is missing")
    kinds = re.findall(r'<li data-claim="([^"]*)"><span data-kind>([^<]*)</span>', a)
    if kinds != [("lead", "possible culprit"), ("ruled out", "ruled out"), ("note", "note")]:
        out.append(f"claims {kinds}")
    cite = re.search(r'<a href="([^"]*)" class="mono" data-cite>node/score#1/instrument</a>', a)
    if cite is None or cite.group(1) != "#step-2":
        out.append("a cite does not link to its node's row, as the graph links it")
    checks = re.findall(r'<li data-check="(\d+)"><code>([^<]*)</code>', a)
    if [c for _, c in checks][:2] != ["onetrace diff baseline candidate --text --stage score#1".replace(
            "baseline", "a").replace("candidate", "b"), "onetrace localize a b --for decide#1"]:
        out.append(f"checks {checks}")
    if "1 says what caused a difference" not in _text(a) or "1 cites an item the packet doesn't hold" not in _text(a):
        out.append("the drops by reason are not shown")
    return out


def test_an_explanation_is_drawn_as_the_command_wrote_it(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    got = explain.explain(comparison, store)
    examined(1, "comparison page with an explanation")
    assert got["exit"] == "0", in_full(got)
    assert explained_problems(_diff(store, comparison)) == [], tried(store, comparison)


#: A replies folder as a Windows checkout names it: on Windows the fixtures' own path has
#: backslashes; elsewhere the test copies them under a folder whose name holds them.
WINDOWS_SHAPED = "D:\\a\\tests\\fixtures"


def config_problems(config: Path, name: str) -> list[str]:
    """The config the tests write is valid TOML, and gives the model's name back as written."""
    import tomllib
    try:
        got = tomllib.loads(config.read_text(encoding="utf-8"))["model"]["name"]
    except tomllib.TOMLDecodeError as e:
        return [f"not TOML: {e}"]
    return [] if got == name else [f"name read back as {got!r}"]


def _backslashed_replies(tmp_path: Path) -> Path:
    import os
    import shutil
    if os.name == "nt":
        return REPLIES
    return Path(shutil.copytree(REPLIES, tmp_path / WINDOWS_SHAPED / "explain"))


def test_a_replies_path_with_backslashes_is_written_as_valid_toml_and_explained(pair, tmp_path, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    replies = _backslashed_replies(tmp_path)
    _model(config, f"fake:{replies / 'mixed.json'}")
    examined(1, "config with a backslashed path")
    assert config_problems(config, str(replies / "mixed.json")) == []
    got = explain.explain(comparison, store)
    assert got["exit"] == "0", in_full(got)
    assert explained_problems(_diff(store, comparison)) == [], tried(store, comparison)


def test_sabotage_the_path_written_unescaped_is_named(pair, tmp_path, monkeypatch, examined):
    import sys
    store, comparison, config = pair
    replies = _backslashed_replies(tmp_path)
    monkeypatch.setattr(sys.modules[__name__], "toml_string", lambda value: f'"{value}"')
    _model(config, f"fake:{replies / 'mixed.json'}")
    examined(1, "config written unescaped")
    assert [p.split(":")[0] for p in config_problems(config, str(replies / "mixed.json"))] == ["not TOML"]


def test_the_label_is_on_every_explanation(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    articles = re.findall(r"<article data-explanation=.*?</article>", panel, re.S)
    assert len(articles) == 2, tried(store, comparison)
    examined(len(articles), "explanations")
    assert all(LABEL in unescape(a) for a in articles)



def title_problems(panel: str) -> list[str]:
    """The section is titled "Suggested explanation"; each explanation in it keeps the full label
    and its model."""
    out = []
    heads = re.findall(r'<section data-section="explain"[^>]*><h2>(.*?)</h2>', panel, re.S)
    if [unescape(h) for h in heads] != [TITLE]:
        out.append(f"the section's title is {heads}")
    for a in re.findall(r"<article data-explanation=.*?</article>", panel, re.S):
        if f"<h3>{LABEL}</h3>" not in unescape(a) or "fake:" not in unescape(a):
            out.append("an explanation without its label or its model")
    return out


def _titled_panels(store, comparison, config, monkeypatch) -> dict[str, str]:
    from onetrace_console import explain
    from onetrace_console.frame import rendering
    out = {}
    with rendering(onedoor=False, sign_in=False, public=True):
        out["public"] = _panel(_diff(store, comparison))
    with monkeypatch.context() as m:
        m.setattr(explain, "command", lambda: None)
        out["not installed"] = _panel(_diff(store, comparison))
    out["before any press"] = _panel(_diff(store, comparison))
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    explain.explain(comparison, store)
    out["two explanations"] = _panel(_diff(store, comparison))
    return out


def test_the_section_is_titled_suggested_explanation_and_each_explanation_keeps_its_label(
        pair, monkeypatch, examined):
    store, comparison, config = pair
    panels = _titled_panels(store, comparison, config, monkeypatch)
    examined(len(panels), "panels: public, not installed, before any press, two explanations")
    assert panels["two explanations"].count("<article data-explanation=") == 2, tried(store, comparison)
    assert {k: title_problems(v) for k, v in panels.items()} == {k: [] for k in panels}


def test_sabotage_the_section_titled_with_the_label_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    monkeypatch.setattr(explain, "TITLE", LABEL)
    panels = _titled_panels(store, comparison, config, monkeypatch)
    examined(len(panels), "panels, sabotaged")
    assert all(title_problems(v) for v in panels.values())

def test_verdicts_counts_and_exits_are_the_same_with_and_without_an_explanation(pair, examined):
    """The page less the panel, the stored comparison, and Home's counts: byte for byte."""
    from onetrace_console import explain
    from onetrace_console.render import render_counts
    store, comparison, config = pair
    before = (_without_panel(_diff(store, comparison)), store.get_comparison(comparison.key).to_json(),
              render_counts(store, generated_at=GENERATED_AT))
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    after = (_without_panel(_diff(store, comparison)), store.get_comparison(comparison.key).to_json(),
             render_counts(store, generated_at=GENERATED_AT))
    examined(3, "page, comparison record and counts")
    assert explained_problems(_diff(store, comparison)) == [], tried(store, comparison)
    assert before == after


def test_every_claim_dropped_shows_its_line_and_the_checks_only(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "all_dropped.json")
    explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    examined(1, "comparison page")
    assert "No suggestion could be tied to the record" in unescape(panel), tried(store, comparison)
    assert 'data-claim=' not in panel and 'data-check="0"' in panel


def test_an_unreachable_model_shows_no_explanation(pair, examined):
    """Exit 3: the panel says so, and nothing in it looks like an explanation."""
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "not_json.txt")
    got = explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    examined(1, "comparison page")
    assert got["exit"] == "3", in_full(got)
    assert 'data-explain="unreached"' in panel, tried(store, comparison)
    assert "<article" not in panel and "data-claim" not in panel and "data-check" not in panel


#: A reference that would have a page reach outside this machine, as tests/test_home_and_diff.py reads it.
_REMOTE = re.compile(r'(?:src|href)\s*=\s*"(?:https?:|//)[^"]*"', re.I)


def format_page_problems(panel: str) -> list[str]:
    """The explain format page is named as its address, in text, and nothing links or loads it: no
    page of the console references a remote origin."""
    from onetrace_console import explain
    out = [f"references {m}" for m in _REMOTE.findall(panel)]
    if f'<span class="mono">{explain.FORMAT_PAGE}</span>' not in panel:
        out.append("does not show the format page's address as text")
    return out


def test_no_model_configured_is_the_command_s_own_line_with_the_format_page(pair, examined):
    from onetrace_console import explain
    store, comparison, _config = pair
    got = explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    examined(1, "comparison page")
    assert got["exit"] == "2" and "no model is configured" in got["stderr"], in_full(got)
    assert "no model is configured" in unescape(panel) and explain.FORMAT_PAGE in panel
    assert format_page_problems(panel) == []


def test_not_installed_is_one_line_with_the_format_page(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, _config = pair
    monkeypatch.setattr(explain, "command", lambda: None)
    panel = _panel(_diff(store, comparison))
    examined(1, "comparison page")
    assert 'data-explain="not-installed"' in panel and explain.FORMAT_PAGE in panel
    assert "data-explain-post" not in panel
    assert format_page_problems(panel) == []


def test_sabotage_the_format_page_as_a_link_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, _config = pair
    monkeypatch.setattr(explain, "command", lambda: None)
    panel = _panel(_diff(store, comparison))
    linked = panel.replace(f'<span class="mono">{explain.FORMAT_PAGE}</span>',
                           f'<a href="{explain.FORMAT_PAGE}">{explain.FORMAT_PAGE}</a>')
    examined(1, "planted panel")
    assert linked != panel
    assert format_page_problems(linked) == [f'references href="{explain.FORMAT_PAGE}"',
                                            "does not show the format page's address as text"]


def test_the_packet_is_shown_with_its_size_and_sha256(pair, examined):
    import hashlib
    from onetrace_console import explain
    store, comparison, _config = pair
    got = explain.packet(comparison, store)
    examined(1, "dry run")
    assert got["exit"] == "0" and len(got["stdout"].splitlines()) >= 2, in_full(got)
    raw, said = got["stdout"].splitlines()[:2]
    assert said == f"{len(raw.encode('utf-8'))} bytes, sha256 {hashlib.sha256(raw.encode('utf-8')).hexdigest()}; dry run: nothing sent", in_full(got)
    panel = _panel(_diff(store, comparison))
    assert said in unescape(panel) and raw in unescape(panel)


def _ask(pair, sent: dict | None):
    """Explain pressed with an endpoint configured that the command has sent `sent` to before."""
    from onetrace_console import explain
    store, comparison, config = pair
    _model(config, "openai:a-model")
    if sent is not None:
        endpoint = re.search(r'base_url = "([^"]*)"', config.read_text(encoding="utf-8")).group(1)
        (config.parent / "explain-sent.json").write_text(json.dumps({endpoint: sent}), encoding="utf-8")
    got = explain.explain(comparison, store)
    return got, _panel(_diff(store, comparison))


def test_the_first_send_question_appears_before_a_first_send_to_an_endpoint(pair, examined):
    got, panel = _ask(pair, None)
    examined(1, "comparison page")
    assert got["exit"] == "2" and "never sent there before" in got["stdout"], in_full(got)
    asks = re.search(r'<div data-explain="asks">(.*?)</div>', panel, re.S)
    assert asks and "never sent there before" in unescape(asks.group(1))
    assert "constants go with their values" not in got["stdout"] or "constants go" in unescape(asks.group(1))
    assert re.search(r'data-explain-post="/explain\?c=[0-9a-f]{64}&amp;send=yes"', panel), "a Send button"


def test_the_question_is_not_asked_again_of_an_endpoint_sent_those_kinds(pair, examined):
    """The command's own record of what it sent where decides; the console asks only when it does."""
    kinds = ["end_outputs", "instrument", "node", "outcome", "output", "upstream", "verdict"]
    got, panel = _ask(pair, kinds)
    examined(1, "comparison page")
    assert "never sent there before" not in got["stdout"], in_full(got)
    assert got["exit"] == "3", in_full(got)      # it went on to send, and nothing listens there
    assert 'data-explain="asks"' not in panel and "send=yes" not in panel


def test_two_explanations_are_listed_newest_first_and_never_merged(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "all_dropped.json")
    first = explain.explain(comparison, store)
    _fake(config, "mixed.json")
    second = explain.explain(comparison, store)
    records = [recorded(g["stdout"]) for g in (first, second)]
    panel = _panel(_diff(store, comparison))
    shown = re.findall(r'<article data-explanation="([^"]*)"', panel)
    examined(2, "explanations")
    assert shown == [records[1], records[0]], tried(store, comparison)


def test_a_check_s_own_output_and_exit_are_shown_and_no_lead_is_marked_by_the_console(pair, examined):
    """A lead is confirmed or ruled out only by what a check reports: the panel shows the check's
    own output and exit, and marks no lead itself."""
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    assert len(explain.explanations(store, comparison.key)) == 1, tried(store, comparison)
    (e,) = explain.explanations(store, comparison.key)
    got = explain.run_check(store, comparison.key, e["record"], 0)
    panel = _panel(_diff(store, comparison))
    examined(1, "check run")
    out = re.search(r'<li data-check="0">.*?<details data-explain="check-output">(.*?)</details>', panel, re.S)
    assert out and got["output"].strip().splitlines()[0] in unescape(out.group(1))
    assert f"<span data-exit>{got['exit']}</span>" in out.group(1)
    #: The command's own lead line says how a lead is settled; nothing else in the panel does.
    rest = re.sub(r'<p data-explain="checks-lead">.*?</p>', "", panel, flags=re.S)
    rest = re.sub(r"<script>.*?</script>", "", rest, flags=re.S).replace('<span data-kind>ruled out</span>', "")
    assert not re.search(r"\b(confirmed|ruled out by|verified lead)\b", _text(rest), re.I)


def test_a_check_is_rebuilt_from_the_explanation_never_from_the_request(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    assert len(explain.explanations(store, comparison.key)) == 1, tried(store, comparison)
    (e,) = explain.explanations(store, comparison.key)
    examined(3, "check requests")
    with pytest.raises(ValueError):
        explain.run_check(store, comparison.key, e["record"], 99)
    with pytest.raises(ValueError):
        explain.run_check(store, comparison.key, "../../x", 0)
    with pytest.raises(ValueError):            # mask needs a file a person names: shown, not run
        explain.run_check(store, comparison.key, e["record"], 3) if len(e["checks"]) > 3 else \
            explain.run_check(store, comparison.key, e["record"], len(e["checks"]))


def test_each_explanation_s_record_is_linked_with_onetrace_verify_s_verdict(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    examined(1, "explanation")
    verified = re.search(r'<span class="mono" data-verified>([^<]*)</span>', panel)
    assert verified and "->  PASS" in unescape(verified.group(1)) and "(exit 0)" in verified.group(1), \
        tried(store, comparison)


# ------------------------------------------------------------------ failure messages

#: tools/windows_check.py prints each failure's message to the job's log cut to this many
#: characters, the message starting "AssertionError: ".
SHOWN = 200
_PRESS = {"exit": "1", "command": "onetrace-explain report", "stdout": "o" * 5000 + "\nthe last line out",
          "stderr": "Traceback (most recent call last):\n" + "e" * 5000 + "\nValueError: the last line"}


def message_problems(message: str, attempt: dict) -> list[str]:
    """A failure message names the press's exit and its stderr's last line within what the job's
    log shows, and holds its stdout and stderr whole."""
    out = []
    shown = ("AssertionError: " + message)[:SHOWN]
    last = attempt["stderr"].strip().splitlines()[-1]
    if f"exit {attempt['exit']}" not in shown or last not in shown:
        out.append("first: the exit or the stderr's last line is not in what the log shows")
    if attempt["stdout"] not in message or attempt["stderr"] not in message:
        out.append("whole: the output is not in full")
    return out


def test_a_failure_message_gives_the_command_s_exit_and_output_in_full(examined):
    examined(1, "kept press")
    assert message_problems(in_full(_PRESS), _PRESS) == []


def test_sabotage_a_message_cut_short_or_with_its_exit_last_is_named(examined):
    examined(2, "planted messages")
    assert [p.split(":")[0] for p in message_problems(in_full(_PRESS)[:1000], _PRESS)] == ["whole"]
    last_first = f"stdout:\n{_PRESS['stdout']}\nstderr:\n{_PRESS['stderr']}\nexit {_PRESS['exit']}"
    assert [p.split(":")[0] for p in message_problems(last_first, _PRESS)] == ["first"]


# ------------------------------------------------------------------ output as Windows writes it

#: A stand-in `onetrace-explain`: the published command, its output shaped as on Windows. Lines end
#: CR LF, the `recorded:` path has backslashes, and a dry run's packet line ends LF, as the command
#: writes it. It is a package of the command's name, first on the command's import path, so the
#: published launcher runs it on any platform.
WINDOWS_SHAPED_CLI = """import os, subprocess, sys


def shaped(b, packet_first):
    lines = b.replace(b"\\r\\n", b"\\n").split(b"\\n")
    lines = [ln[:10] + ln[10:].replace(b"/", b"\\\\") if ln.startswith(b"recorded: ") else ln for ln in lines]
    if packet_first and len(lines) > 1:
        return lines[0] + b"\\n" + b"\\r\\n".join(lines[1:])
    return b"\\r\\n".join(lines)


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.pathsep.join(p for p in os.environ["PYTHONPATH"].split(os.pathsep) if p != here)
    got = subprocess.run([sys.executable, "-m", "onetrace_explain", *sys.argv[1:]],
                         env=dict(os.environ, PYTHONPATH=path), capture_output=True)
    sys.stdout.buffer.write(shaped(got.stdout, "--dry-run" in sys.argv))
    sys.stderr.buffer.write(shaped(got.stderr, False))
    return got.returncode
"""


def stand_in(tmp_path: Path, monkeypatch, cli: str) -> Path:
    """`cli` as the `onetrace_explain.cli` the published launcher imports, first on its import path."""
    import os
    package = tmp_path / "stand-in" / "onetrace_explain"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "cli.py").write_text(cli, encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([str(package.parent), os.environ["PYTHONPATH"]]))
    return package


def windows_output_problems(store, comparison, config) -> list[str]:
    """The panel drawn from the command's output as Windows writes it: two explanations newest
    first by their `recorded:` lines, the one drawn as the command wrote it, the packet with its
    size and sha256, and the first-send question with Send."""
    import hashlib
    from onetrace_console import explain
    out = []
    _fake(config, "all_dropped.json")
    first = explain.explain(comparison, store)
    _fake(config, "mixed.json")
    second = explain.explain(comparison, store)
    if "\r\n" not in second["stdout"] or "\\" not in second["stdout"]:
        out.append("the stand-in did not shape the output")
    panel = _panel(_diff(store, comparison))
    shown = re.findall(r'<article data-explanation="([^"]*)"', panel)
    if shown != [recorded(second["stdout"]), recorded(first["stdout"])]:
        out.append(f"order: {shown}")
    out += [f"explanation: {p}" for p in explained_problems(_diff(store, comparison))]
    raw, said = explain.packet(comparison, store)["stdout"].splitlines()[:2]
    data = raw.encode("utf-8")
    if said != f"{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()}; dry run: nothing sent":
        out.append(f"the command's packet line {said!r}")
    panel = unescape(_panel(_diff(store, comparison)))
    if said not in panel or raw not in panel:
        out.append("packet: not shown as the command wrote it")
    _model(config, "openai:a-model")
    explain.explain(comparison, store)
    panel = _panel(_diff(store, comparison))
    asks = re.search(r'<div data-explain="asks">(.*?)</div>', panel, re.S)
    #: The console shows a CR as the text `\u000d` (words.escape): a line read with its CR shows it.
    if not asks or "never sent there before" not in unescape(asks.group(1)) or "\\u000d" in asks.group(1):
        out.append("asks: the question is not shown as its lines")
    if not re.search(r'data-explain-post="/explain\?c=[0-9a-f]{64}&amp;send=yes"', panel):
        out.append("asks: no Send button")
    return out


@pytest.fixture
def windows_shaped(pair, tmp_path, monkeypatch):
    stand_in(tmp_path, monkeypatch, WINDOWS_SHAPED_CLI)
    return pair


def test_the_panel_reads_the_command_s_output_as_windows_writes_it(windows_shaped, examined):
    examined(4, "presses and pages: two explanations, the packet, the question")
    assert windows_output_problems(*windows_shaped) == [], tried(*windows_shaped[:2])


def mutated(monkeypatch, name: str, old: str, new: str) -> None:
    """explain.<name>, with `old` in its source replaced by `new`, once; it reads the module's own
    names, as patched, when it runs."""
    import inspect
    import types
    from onetrace_console import explain
    source = inspect.getsource(getattr(explain, name))
    assert source.count(old) == 1, (name, old)
    space = dict(vars(explain))
    exec(compile(source.replace(old, new), explain.__file__, "exec"), space)
    made = space[name]
    monkeypatch.setattr(explain, name, types.FunctionType(made.__code__, vars(explain), name, made.__defaults__,
                                                          made.__closure__))


def test_sabotage_the_packet_read_split_on_newline_is_named(windows_shaped, monkeypatch, examined):
    mutated(monkeypatch, "panel", 'lines = pk.get("stdout", "").splitlines()', 'lines = pk.get("stdout", "").split("\\n")')
    examined(1, "panel with the packet read split on newline")
    assert [p.split(":")[0] for p in windows_output_problems(*windows_shaped)] == ["packet"]


def test_sabotage_the_question_read_split_on_newline_is_named(windows_shaped, monkeypatch, examined):
    mutated(monkeypatch, "_asks", 'a.get("stdout", "").splitlines()', 'a.get("stdout", "").split("\\n")')
    examined(1, "the question read split on newline")
    assert [p.split(":")[0] for p in windows_output_problems(*windows_shaped)] == ["asks"]


# ------------------------------------------------------------------ standard input

#: A stand-in `onetrace-explain` that records what its standard input is, and stops as the
#: command does when a first send is not confirmed.
STDIN_CLI = """import json, os, stat, sys


def main():
    mode = os.fstat(0).st_mode
    seen = {"isatty": sys.stdin.isatty(), "pipe": stat.S_ISFIFO(mode), "character device": stat.S_ISCHR(mode),
            "at end": sys.stdin.buffer.read() == b""}
    with open(os.environ["STAND_IN_RECORD"], "a", encoding="utf-8") as f:
        f.write(json.dumps(seen, sort_keys=True) + "\\n")
    print("onetrace-explain: not confirmed; run it in a terminal, or pass --yes", file=sys.stderr)
    return 2
"""
#: An empty pipe: never a terminal on any platform, and at its end at once.
EMPTY_PIPE = {"isatty": False, "pipe": True, "character device": False, "at end": True}


def stdin_problems(store, comparison, config, tmp_path, monkeypatch) -> list[str]:
    """What the command's standard input is, for a press of Explain, of Show the packet, and for a
    check run from an explanation: an empty pipe each time, never NUL or a terminal."""
    import json
    import sys
    from onetrace_console import explain
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    assert len(explain.explanations(store, comparison.key)) == 1, tried(store, comparison)
    record = explain.explanations(store, comparison.key)[0]["record"]
    seen = tmp_path / "stdin-seen.jsonl"
    monkeypatch.setenv("STAND_IN_RECORD", str(seen))
    stand_in(tmp_path, monkeypatch, STDIN_CLI)
    monkeypatch.setattr(explain, "check_argv",
                        lambda check: [sys.executable, "-c", "import sys; from onetrace_explain.cli import main; sys.exit(main())"])
    explain.explain(comparison, store)
    explain.packet(comparison, store)
    explain.run_check(store, comparison.key, record, 0)
    got = [json.loads(ln) for ln in seen.read_text(encoding="utf-8").splitlines()] if seen.is_file() else []
    out = [f"{what}: stdin {s}" for what, s in zip(("explain", "packet", "check"), got) if s != EMPTY_PIPE]
    return out + ([f"{len(got)} runs recorded, not 3"] if len(got) != 3 else [])


def test_the_command_and_a_check_get_an_empty_pipe_for_stdin(pair, tmp_path, monkeypatch, examined):
    examined(3, "runs: Explain, Show the packet, a check")
    assert stdin_problems(*pair, tmp_path, monkeypatch) == []


def test_sabotage_nul_for_stdin_is_named(pair, tmp_path, monkeypatch, examined):
    mutated(monkeypatch, "_run", 'input=b""', "stdin=subprocess.DEVNULL")
    mutated(monkeypatch, "_press", "stdin=subprocess.PIPE", "stdin=subprocess.DEVNULL")
    mutated(monkeypatch, "run_check", 'input=b""', "stdin=subprocess.DEVNULL")
    examined(3, "runs with NUL for stdin")
    assert [p.split(":")[0] for p in stdin_problems(*pair, tmp_path, monkeypatch)] == ["explain", "packet", "check"]


# ------------------------------------------------------------------ the public demo, and imports

def test_a_public_comparison_page_has_the_place_only(pair, examined):
    from onetrace_console.frame import rendering
    store, comparison, _config = pair
    with rendering(onedoor=False, sign_in=False, public=True):
        page = _diff(store, comparison)
    panel = _panel(page)
    examined(1, "public comparison page")
    assert "Explanations are not set up on this demo" in unescape(panel)
    assert "<button" not in panel and "data-explain-post" not in page and "explain" not in _script_text(page)


def _script_text(page: str) -> str:
    return " ".join(re.findall(r"<script>(.*?)</script>", page, re.S))


def test_the_public_demo_build_makes_no_network_call_and_never_runs_the_command(tmp_path, monkeypatch, examined):
    """The whole public build, with every socket this process opens refused, and every child it
    starts recorded: none is onetrace-explain. Its comparison pages carry the place only."""
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    opened = []

    def refuse(*a, **k):
        opened.append(a)
        raise OSError("a network call from the public demo's build")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    children = []
    real = subprocess.Popen.__init__

    def record(self, args, *a, **k):
        children.append([str(x) for x in args] if isinstance(args, (list, tuple)) else [str(args)])
        return real(self, args, *a, **k)
    monkeypatch.setattr(subprocess.Popen, "__init__", record)
    build_public(tmp_path / "demo")
    pages = list((tmp_path / "demo").rglob("diff/*.html"))
    examined(len(children) + len(pages), "children started and comparison pages built")
    assert opened == []
    assert not [c for c in children if any("onetrace-explain" in x or "onetrace_explain" in x for x in c)]
    drawn = [p for p in pages if 'data-section="explain"' in p.read_text(encoding="utf-8")]
    assert drawn and all("data-explain-post" not in p.read_text(encoding="utf-8") for p in pages)


def test_a_static_export_carries_the_place_only(pair, tmp_path, examined):
    """A static export is files: nothing on it can press anything. Its comparison page has the
    panel's place, with no button and no script, and no explanation is copied into it."""
    from onetrace_console import explain
    from onetrace_console.export_static import export
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    out = tmp_path / "export"
    export(Path(store.root).parent, [comparison.run_a, comparison.run_b], out)
    page = (out / "diff" / f"{comparison.key}.html").read_text(encoding="utf-8")
    examined(1, "exported comparison page")
    assert 'data-section="explain"' in page and "Explanations are not set up" in unescape(page)
    assert "data-explain-post" not in page and "<article data-explanation" not in page
    assert "explain" not in _script_text(page)


def test_the_command_the_tests_run_is_the_published_wheel(explain_command, examined):
    """The panel's tests run onetrace-explain 0.1.0 as PyPI serves it: installed from the wheel
    cache by its pinned hash, apart from this environment, which does not hold it."""
    import importlib.util
    from tools import fetch_wheel_cache as w
    found, lib = explain_command
    (requirement, (name, sha)), = w.TEST_COMMANDS.items()
    examined(1, "installed command")
    assert requirement == "onetrace-explain==0.1.0" and name == "onetrace_explain-0.1.0-py3-none-any.whl"
    assert (lib / "onetrace_explain-0.1.0.dist-info").is_dir()
    assert importlib.util.find_spec("onetrace_explain") is None or not str(
        importlib.util.find_spec("onetrace_explain").origin).startswith(str(lib))
    assert found.is_file()


def test_sabotage_a_wheel_cache_holding_another_command_wheel_is_not_ready(tmp_path, monkeypatch, examined):
    """The cache as it is, with only the command's wheel replaced: `check()` refuses it, so the
    fixture never installs another build under the published one's name."""
    import shutil
    from tools import fetch_wheel_cache as w
    assert w.check(), "the wheel cache is not ready: python tools/fetch_wheel_cache.py"
    planted = tmp_path / "cache"
    shutil.copytree(w.CACHE, planted)
    (name, _), = w.TEST_COMMANDS.values()
    (planted / name).write_bytes(b"not the published wheel")
    monkeypatch.setattr(w, "CACHE", planted)
    examined(1, "planted cache")
    assert not w.check()


def test_the_console_never_imports_onetrace_explain(examined):
    """In a fresh interpreter: the console's modules, the panel drawn, and still no onetrace_explain
    in sys.modules; and no source file imports it."""
    import ast
    src = Path(__file__).resolve().parent.parent / "src"
    files = list(src.rglob("*.py"))
    examined(len(files) + 1, "source files read and one interpreter")
    found = []
    for f in files:
        for node in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            names = ([a.name for a in node.names] if isinstance(node, ast.Import)
                     else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            found += [f"{f.name}: {n}" for n in names if n.split(".")[0] == "onetrace_explain"]
    assert found == []
    code = ("import sys, onetrace_console.explain as e, onetrace_console.render, onetrace_console.serve; "
            "e.command(); print('onetrace_explain' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={"PYTHONPATH": str(src), "PATH": ""})
    assert out.stdout.strip() == "False", out.stderr[-500:]


def test_the_routes_are_a_viewer_s_and_the_script_is_named_in_the_local_policy_only(examined):
    from onetrace_console import roles
    from onetrace_console.explain_script import EXPLAIN_SCRIPT
    from onetrace_console.public import _script_hash, content_security_policy
    examined(4, "routes")
    for path in ("/explain", "/explain/packet", "/explain/check"):
        assert roles.required_role("POST", path) == roles.VIEWER
    h = _script_hash(EXPLAIN_SCRIPT)
    assert h in content_security_policy(local=True) and h not in content_security_policy()


# ------------------------------------------------------------------ the sabotages

def test_sabotage_a_drawn_explanation_missing_its_label_or_a_claim_is_named(pair, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    page = _diff(store, comparison)
    examined(3, "planted pages")
    assert "<article data-explanation=" in page, tried(store, comparison)
    article = re.search(r"<article data-explanation=.*?</article>", page, re.S).group(0)
    assert explained_problems(page.replace(article, article.replace(LABEL, "Explanation"), 1)) != []
    assert explained_problems(re.sub(r'<li data-claim="note">.*?</li>', "", page, count=1, flags=re.S)) != []
    assert explained_problems(re.sub(r'<p data-explain="dropped">.*?</p>', "", page, count=1, flags=re.S)) != []


def test_sabotage_an_explanation_inside_the_verdicts_is_named(pair, examined):
    """A page whose verdict part changed with the explanation fails the equality above."""
    from onetrace_console import explain
    store, comparison, config = pair
    before = _without_panel(_diff(store, comparison))
    _fake(config, "mixed.json")
    explain.explain(comparison, store)
    after = _without_panel(_diff(store, comparison))
    examined(1, "planted page")
    planted = after.replace('data-section="first-difference"', 'data-section="first-difference" data-explained', 1)
    assert before == after and planted != before


def test_sabotage_an_unreachable_reply_drawn_as_an_explanation_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    store, comparison, config = pair
    _fake(config, "not_json.txt")
    explain.explain(comparison, store)
    monkeypatch.setattr(explain, "_attempt_line", lambda a: '<article data-explanation="x"></article>')
    panel = _panel(_diff(store, comparison))
    examined(1, "planted panel")
    assert "<article" in panel, "the test above would name it"


def test_sabotage_a_question_never_shown_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    monkeypatch.setattr(explain, "_asks", lambda a: [])
    _got, panel = _ask(pair, None)
    examined(1, "planted panel")
    assert 'data-explain="asks"' not in panel and "send=yes" not in panel, "the question test would fail"


def test_sabotage_a_console_that_imports_onetrace_explain_is_named(tmp_path, examined):
    import ast
    planted = tmp_path / "planted.py"
    planted.write_text("from onetrace_explain import cli\n", encoding="utf-8")
    examined(1, "planted source")
    names = [n.module for n in ast.walk(ast.parse(planted.read_text())) if isinstance(n, ast.ImportFrom)]
    assert names == ["onetrace_explain"]


def test_sabotage_a_public_page_with_a_button_is_named(pair, monkeypatch, examined):
    from onetrace_console import explain
    from onetrace_console.frame import rendering
    store, comparison, _config = pair
    monkeypatch.setattr(explain, "_public", lambda: False)
    with rendering(onedoor=False, sign_in=False, public=True):
        page = _diff(store, comparison)
    examined(1, "planted public page")
    assert "data-explain-post" in page, "the public test above would name it"


def test_sabotage_a_socket_opened_during_a_build_is_caught(monkeypatch, examined):
    opened = []

    def refuse(*a, **k):
        opened.append(a)
        raise OSError("refused")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    examined(1, "planted connection")
    with pytest.raises(OSError):
        socket.socket().connect(("127.0.0.1", _closed_port()))
    assert opened
