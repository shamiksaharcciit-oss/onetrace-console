"""Every call this console makes to the verifier and to the SDK's verbs is one they accept.

The verifier refuses, by name and with exit 2, an option it does not know and a second run folder
in one call: a mistyped gate must not let a run pass unchecked. The SDK's verbs refuse an option
they do not know the same way. So each call the console makes is recorded here as it runs -- the
demo store built whole (its runs checked, with its trust file, and every comparison made, the
corpus trace included), and a check with a time-stamp authority's files -- and each is held to
not being refused as a call. The commands a page gives a reader to repeat the check are run the
same way.

What a call asks for is listed by its arguments, and the list is checked to hold each form the
console builds: the check three ways (its words, `--json`, `--json --require-artifacts`), and for a
run recorded in format 0.3 a fourth (`--json --require-complete`), each with the evidence options; the two verbs; the text diff with and without a line limit; and the
trace with its runs root; and since onetrace 0.5.0, the decision files for a gated run, an inner run
for an agent's, and the verifier named for the verbs.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

VERIFIER = "onetrace_verify.cli"
SDK = "onetrace"
#: How the verifier and the SDK's verbs refuse a call (not a run): each in its own words.
REFUSED_CALL = ("unknown option", "one run folder or manifest per call", "unrecognized arguments",
                "the following arguments are required", "invalid choice", "needs --trust FILE")


def refusal(argv, returncode: int, stderr: str, *_) -> str:
    """Why the call itself was refused, in the refusing tool's words, or "" where it was not."""
    if returncode != 2:
        return ""
    found = [w for w in REFUSED_CALL if w in stderr]
    return f"{' '.join(map(str, argv[2:]))}: {found[0]}" if found else ""


def _recorded(monkeypatch) -> list[tuple[list[str], int, str, str]]:
    """Every verifier and verb call made through `subprocess.run` from here on: (argv, exit,
    stderr, stdout)."""
    calls = []
    real = subprocess.run

    def run(cmd, *a, **k):
        proc = real(cmd, *a, **k)
        argv = [str(c) for c in cmd] if isinstance(cmd, (list, tuple)) else []
        if argv[1:3] in (["-m", VERIFIER], ["-m", SDK]):
            err, out = (s if isinstance(s, str) else (s or b"").decode("utf-8", "replace")
                        for s in (proc.stderr, proc.stdout))
            calls.append((argv, proc.returncode, err, out))
        return proc
    monkeypatch.setattr(subprocess, "run", run)
    return calls


def _form(argv: list[str]) -> tuple[str, ...]:
    """A call's options, its values and folders left out: what it asks for."""
    takes_value = {"--trust", "--tsa-cert", "--tsa-root", "--headers", "--out", "--runs-root",
                   "--max-lines", "--verifier", "--decisions", "--permit-issuers", "--nested-run"}
    out, skip = [argv[2]] + ([argv[3]] if argv[2] == SDK else []), False
    for a in argv[4 if argv[2] == SDK else 3:]:
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            out.append(a)
            skip = a in takes_value
    return tuple(out)


@pytest.fixture(scope="module")
def demo_calls(tmp_path_factory):
    from onetrace_console.folder_load import build_public
    from tests.test_checks import _require_installed
    _require_installed()
    mp = pytest.MonkeyPatch()
    try:
        calls = _recorded(mp)
        build_public(tmp_path_factory.mktemp("calls") / "demo")
    finally:
        mp.undo()
    return calls


@pytest.fixture
def warranty_calls(store, tmp_path, monkeypatch):
    """The SDK's warranty pair, its runs checked with no trust file and compared: the comparison
    follows its changed corpus link, so the trace runs with its runs root."""
    from tests.test_board7 import _pair, _require_warranty
    _require_warranty()
    calls = _recorded(monkeypatch)
    _pair(store, tmp_path)
    return calls


def test_every_call_the_demo_store_makes_is_one_the_verifier_and_the_verbs_accept(demo_calls, examined):
    examined(len(demo_calls), "verifier and verb calls made building the demo store")
    assert demo_calls, "no call recorded"
    assert [refusal(*c) for c in demo_calls if refusal(*c)] == []


def test_every_call_a_traced_comparison_makes_is_one_they_accept(warranty_calls, examined):
    examined(len(warranty_calls), "verifier and verb calls made checking and comparing the warranty pair")
    assert warranty_calls, "no call recorded"
    assert [refusal(*c) for c in warranty_calls if refusal(*c)] == []


def test_the_calls_hold_each_form_the_console_builds(demo_calls, warranty_calls, examined):
    forms = {_form(c[0]) for c in demo_calls + warranty_calls}
    examined(len(forms), "forms of call")
    want = {
        (VERIFIER,), (VERIFIER, "--json"), (VERIFIER, "--json", "--require-artifacts"),
        (VERIFIER, "--trust"), (VERIFIER, "--json", "--trust"),
        (VERIFIER, "--json", "--require-artifacts", "--trust"),
        (VERIFIER, "--json", "--require-complete", "--trust"),
        #: Since onetrace 0.5.0: the verifier's copy beside the runs, named for the verbs; the
        #: decision files for a gated run's check; an inner run beside an agent's check and its
        #: comparison.
        (SDK, "diff", "--verifier", "--out"), (SDK, "localize", "--verifier", "--out"),
        (SDK, "diff", "--text", "--json", "--no-follow", "--verifier", "--out"),
        (SDK, "diff", "--text", "--json", "--runs-root", "--verifier", "--out"),
        (VERIFIER, "--json", "--require-artifacts", "--trust", "--decisions", "--permit-issuers"),
        (VERIFIER, "--json", "--require-artifacts", "--trust", "--nested-run"),
        (SDK, "diff", "--nested-run", "--nested-run", "--verifier", "--out"),
    }
    assert want <= forms, sorted(want - forms)


def test_a_check_with_a_time_stamp_authority_s_files_is_a_call_the_verifier_accepts(tmp_path, monkeypatch,
                                                                                    examined):
    from onetrace_console.checks import check
    from tests.test_checks import _require_installed
    from tests.test_diff_sdk_text_layer import _sdk_run
    _require_installed()
    _sdk_run(tmp_path / "run", "calls-tsa")
    for name in ("trust.json", "tsa-cert.pem", "tsa-root-1.pem", "tsa-root-2.pem"):
        (tmp_path / name).write_text('{"format": "onetrace-trust/0.1", "keys": []}\n'
                                     if name == "trust.json" else "not a certificate\n", encoding="utf-8")
    calls = _recorded(monkeypatch)
    check(tmp_path / "run", trust_file=str(tmp_path / "trust.json"), tsa_cert=str(tmp_path / "tsa-cert.pem"),
          tsa_roots=[str(tmp_path / "tsa-root-1.pem"), str(tmp_path / "tsa-root-2.pem")])
    examined(len(calls), "verifier calls")
    assert {_form(c[0]) for c in calls} == {
        (VERIFIER, "--trust", "--tsa-cert", "--tsa-root", "--tsa-root"),
        (VERIFIER, "--json", "--trust", "--tsa-cert", "--tsa-root", "--tsa-root"),
        (VERIFIER, "--json", "--require-artifacts", "--trust", "--tsa-cert", "--tsa-root", "--tsa-root"),
        (VERIFIER, "--json", "--require-complete", "--trust", "--tsa-cert", "--tsa-root", "--tsa-root")}
    assert [refusal(*c) for c in calls if refusal(*c)] == []


def row_names(stdout: str) -> set[str]:
    """The names of the rows a verifier call wrote: its --json rows, or its text's `[RESULT ] name`."""
    import json
    import re
    try:
        return {r["name"] for r in json.loads(stdout)["rows"]}
    except (ValueError, KeyError, TypeError):
        return {m.group(1) for m in re.finditer(r"^\[[A-Z-]+ *\] (.+?)(?: -- .*)?$", stdout, re.M)}


#: The verifier's requirements, each an option a call must ask for, and the row it then adds.
REQUIREMENTS = {"--require-signature": "signature required", "--require-trusted": "trusted signature required",
                "--require-complete": "run complete"}


def test_the_console_asks_the_verifier_for_one_requirement_only(demo_calls, warranty_calls, examined):
    """The verifier adds a row for each requirement only when a call asks for it. This console asks
    for one, `--require-complete`, in its own `--json` call beside the check of a run recorded in
    format 0.3 (its `run complete` row is how the verifier reads optional stages); never the two
    signing requirements, and never in the check whose verdict the console keeps."""
    calls = [c for c in demo_calls + warranty_calls if c[0][2] == VERIFIER]
    examined(len(calls), "verifier calls read")
    asked = sorted({a for c in calls for a in c[0] if a in REQUIREMENTS})
    assert [c[0][3:] for c in calls if not row_names(c[3])] == [], "a call whose rows were not read"
    assert asked == ["--require-complete"], asked
    alone = [c for c in calls if "--require-complete" in c[0]]
    assert all("--json" in c[0] and "--require-artifacts" not in c[0] for c in alone), [c[0][3:] for c in alone]
    rows = sorted({row for c in calls if "--require-complete" not in c[0]
                   for row in row_names(c[3]) if row in REQUIREMENTS.values()})
    assert rows == [], "a requirement's row in a call that did not ask for it"


def test_sabotage_a_requirement_asked_for_adds_its_row(tmp_path, examined):
    """What the test above looks for is there when asked: each requirement's row, in the verifier's
    text and in its --json rows."""
    from tests.test_checks import _require_installed
    from tests.test_diff_sdk_text_layer import _sdk_run
    _require_installed()
    _sdk_run(tmp_path, "calls-require")
    (tmp_path / "trust.json").write_text('{"format": "onetrace-trust/0.1", "keys": []}\n', encoding="utf-8")
    examined(2 * len(REQUIREMENTS), "planted calls")
    for option, row in REQUIREMENTS.items():
        for json_rows in ((), ("--json",)):
            p = subprocess.run([sys.executable, "-m", VERIFIER, *json_rows, option, "--trust", "trust.json",
                                "MANIFEST.json"], cwd=tmp_path, capture_output=True, text=True)
            assert row in row_names(p.stdout), (option, json_rows, p.stdout)


def _page_commands() -> list[list[str]]:
    """The verifier's arguments in each command a page gives a reader: the receipt page's, for
    every combination of what a record carries, and "Repeat the check"'s, as stored and shown."""
    from types import SimpleNamespace

    import onetrace_console.receipt_page as rp
    from onetrace_console.checks import REPEAT_COMMAND
    out = []
    for signed in (False, True):
        for methods in (set(), {"rfc3161"}, {"opentimestamps"}, {"rfc3161", "opentimestamps"}):
            run = SimpleNamespace(listing=[("signatures/a.json", "k")] if signed else [])
            real = rp._anchor_methods
            rp._anchor_methods = lambda run, store, m=methods: m
            try:
                command, _ = rp._command(run, None)
            finally:
                rp._anchor_methods = real
            out.append(command.splitlines()[-1].split()[1:])
    out.append(REPEAT_COMMAND.split()[1:])
    out.append(["--trust", "trust.json", "MANIFEST.json"])
    return out


def test_every_command_a_page_gives_a_reader_is_one_the_verifier_accepts(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_diff_sdk_text_layer import _sdk_run
    _require_installed()
    _sdk_run(tmp_path, "calls-reader")
    commands = _page_commands()
    examined(len(commands), "commands a page gives")
    refused = []
    for args in commands:
        p = subprocess.run([sys.executable, "-m", VERIFIER, *args], cwd=tmp_path, capture_output=True, text=True)
        if refusal([sys.executable, "-m", VERIFIER, *args], p.returncode, p.stderr):
            refused.append(refusal([sys.executable, "-m", VERIFIER, *args], p.returncode, p.stderr))
    assert refused == []


@pytest.mark.parametrize("args", [["--require-signatures", "MANIFEST.json"], ["MANIFEST.json", "second"],
                                  ["--require-trusted", "MANIFEST.json"]],
                         ids=["a mistyped option", "a second run argument", "a gate missing its trust file"])
def test_sabotage_a_call_the_verifier_refuses_is_named(tmp_path, args, examined):
    from tests.test_checks import _require_installed
    from tests.test_diff_sdk_text_layer import _sdk_run
    _require_installed()
    _sdk_run(tmp_path, "calls-sabotage")
    argv = [sys.executable, "-m", VERIFIER, *args]
    p = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True)
    examined(1, "planted call")
    assert refusal(argv, p.returncode, p.stderr) != "", (p.returncode, p.stderr)
