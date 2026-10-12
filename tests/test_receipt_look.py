"""The run receipt as the console draws it: its pills in their rungs' tones, the command this run's
check needs, what the console's own run of the verifier printed, and the ruled words.

- The command follows what the record carries: the crypto extra and `--trust trust.json` (named in
  the onetrace-trust/0.1 format) for a signed run; the time-stamp authority's files for an RFC 3161
  anchor; neither for a run that carries neither.
- The black box is the stored check's output, as the verifier wrote it (a row past the page's cap
  cut with the count of the rest, as the run page draws the same rows), and its caption names the
  command with file paths cut to their names: no absolute path of this machine is shown.
- "The check makes no network calls": measured, by running the verifier as the page tells a reader
  to, under an audit hook that records any socket use. And "offline" is said on no page.

Each check has its sabotage.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from html import escape, unescape
from pathlib import Path

import pytest

from tests.path_rules import absolute_paths_in, is_absolute
from tests.test_trust_and_tsa_flags import _anchored_run, _pages, _record, _signed_run


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _receipt(pages: Path, store, run_id: str) -> tuple[object, str]:
    run = next(r for r in store.runs() if r.run_id == run_id)
    return run, (pages / "runs" / run.key / "receipt.html").read_text(encoding="utf-8")


def _command(page: str) -> str:
    found = re.search(r'<section data-section="check-yourself">.*?<pre><code>(.*?)</code></pre>', page, re.S)
    return unescape(found.group(1))


# ------------------------------------------------------------------ the command

def test_an_unsigned_unanchored_run_needs_neither(tmp_path, examined):
    _record(tmp_path / "runs" / "plain", "plain-run")
    store, pages = _pages(tmp_path / "runs", tmp_path)
    _run, page = _receipt(pages, store, "plain-run")
    examined(1, "receipt")
    assert _command(page) == "pip install onetrace-verify\nonetrace-verify --require-artifacts ."


def test_a_signed_run_needs_the_crypto_extra_and_a_trust_file(tmp_path, examined):
    runs = _signed_run(tmp_path)
    store, pages = _pages(runs, tmp_path, trust_file=str(tmp_path / "trust.json"))
    _run, page = _receipt(pages, store, "signed-run")
    examined(1, "receipt")
    assert _command(page) == ('pip install "onetrace-verify[crypto]"\n'
                              "onetrace-verify --require-artifacts --trust trust.json .")
    assert "onetrace-trust/0.1" in _text(page)


def test_an_rfc3161_anchored_run_needs_the_authoritys_files(tmp_path, examined):
    runs, cert, root = _anchored_run(tmp_path)
    store, pages = _pages(runs, tmp_path, tsa_cert=str(cert), tsa_roots=[str(root)])
    _run, page = _receipt(pages, store, "anchored-run")
    examined(1, "receipt")
    assert _command(page) == ('pip install "onetrace-verify[crypto]"\n'
                              "onetrace-verify --require-artifacts --tsa-cert tsa-cert.pem "
                              "--tsa-root tsa-root.pem .")
    assert "--trust" not in _command(page)


# ------------------------------------------------------------------ the black box

def printed_problems(page: str, stdout: str, absolute=is_absolute) -> list[str]:
    box = re.search(r'<pre class="term" data-section="verifier-output">(.*?)</pre>', page, re.S)
    out = []
    if box is None:
        return ["no black box"]
    from onetrace_console.viewer.model import NAME_CAP
    shown = unescape(box.group(1)).split("\n")
    wrote = stdout.replace("\r\n", "\n").split("\n")
    #: Each row as the verifier wrote it; a row longer than the page's cap, its first NAME_CAP
    #: characters and the count of the rest, as the run page draws the same rows.
    if len(shown) != len(wrote) or any(
            s != w and not (len(w) > NAME_CAP and s.startswith(w[:NAME_CAP] + " ")
                            and str(len(w) - NAME_CAP) in s[NAME_CAP:])
            for s, w in zip(shown, wrote)):
        out.append("not the verifier's output as it wrote it")
    lead = re.search(r'<section data-section="printed"><h3>[^<]*</h3><p>(.*?)</p>', page, re.S)
    #: An absolute path by POSIX or Windows rules, whichever system drew the page (tests/path_rules).
    if lead is None or absolute_paths_in(_text(lead.group(1)), absolute):
        out.append("an absolute path in the caption")
    return out


def test_the_black_box_is_what_the_verifier_printed(tmp_path, examined):
    from onetrace_console.pages import _envelope
    runs = _signed_run(tmp_path)
    store, pages = _pages(runs, tmp_path, trust_file=str(tmp_path / "trust.json"))
    run, page = _receipt(pages, store, "signed-run")
    envelope = _envelope(run, store)
    examined(1, "receipt")
    assert any(is_absolute(a) for a in envelope["command"]), "the stored command holds a path"
    assert printed_problems(page, envelope["stdout"]) == []
    assert "onetrace-verify --trust trust.json MANIFEST.json" in _text(page)


#: Planted in the caption in place of the trust file's name, on every system: each is named.
PLANTED_PATHS = {"posix": "/srv/onetrace-demo/trust.json", "drive": "C:\\Users\\someone\\trust.json",
                 "drive, forward slashes": "C:/onetrace/trust.json", "unc": "\\\\server\\share\\trust.json"}


def _with_caption_path(page: str, path: str) -> str:
    caption = re.search(r'<section data-section="printed">.*?</p>', page, re.S).group(0)
    planted = page.replace(caption, caption.replace("--trust trust.json", f"--trust {escape(path)}"), 1)
    assert planted != page
    return planted


@pytest.fixture(scope="module")
def signed_receipt(tmp_path_factory):
    from onetrace_console.pages import _envelope
    tmp = tmp_path_factory.mktemp("signed")
    runs = _signed_run(tmp)
    store, pages = _pages(runs, tmp, trust_file=str(tmp / "trust.json"))
    run, page = _receipt(pages, store, "signed-run")
    return page, _envelope(run, store)["stdout"]


def test_sabotage_an_edited_output_is_named(signed_receipt, examined):
    page, stdout = signed_receipt
    edited = page.replace("[PASS   ]", "[PASS]", 1)
    examined(1, "planted page")
    assert edited != page
    assert "not the verifier's output as it wrote it" in printed_problems(edited, stdout)


@pytest.mark.parametrize("kind", PLANTED_PATHS)
def test_a_caption_with_an_absolute_path_of_either_system_is_named(signed_receipt, kind, examined):
    page, stdout = signed_receipt
    examined(1, "planted page")
    assert printed_problems(page, stdout) == [], "the caption as drawn, --trust trust.json alone"
    assert "an absolute path in the caption" in printed_problems(_with_caption_path(page, PLANTED_PATHS[kind]), stdout)


def test_sabotage_the_leading_slash_rule_misses_the_drive_and_unc_plants(signed_receipt, examined):
    """The checker's rule put back as it was, a leading `/` only: the drive and UNC plants pass
    it, so the rule above is what names them."""
    page, stdout = signed_receipt

    def old(word):
        return word.startswith("/")
    missed = [k for k, path in PLANTED_PATHS.items()
              if "an absolute path in the caption" not in printed_problems(_with_caption_path(page, path), stdout, old)]
    examined(len(PLANTED_PATHS), "planted pages under the old rule")
    assert missed == ["drive", "drive, forward slashes", "unc"], missed


# ------------------------------------------------------------------ no network calls

_HOOKED = r'''
import sys
events = []
sys.addaudithook(lambda name, args: events.append(name) if name.startswith("socket.") else None)
if sys.argv[1] == "--control":
    import socket
    try:
        socket.getaddrinfo("localhost", 80)
    except OSError:
        pass
    code = 0
else:
    from onetrace_verify.cli import main
    code = main(sys.argv[1:])
print("RESULT", code, sorted(set(events)), file=sys.stderr)
'''


def _socket_events(args: list[str], cwd: Path) -> tuple[int, list[str]]:
    done = subprocess.run([sys.executable, "-I", "-c", _HOOKED, *args], cwd=cwd,
                          capture_output=True, text=True)
    code, events = re.search(r"RESULT (\S+) (\[.*\])", done.stderr).groups()
    return int(code), eval(events)  # noqa: S307 - a list of str the child printed


def test_the_check_the_page_gives_makes_no_network_calls(tmp_path, examined):
    """The signed run with its trust file and the anchored run with its authority's files, checked
    as the receipt tells a reader to: each passes, and not one socket event is raised."""
    signed = _signed_run(tmp_path / "s")
    runs, cert, root = _anchored_run(tmp_path / "a")
    checks = [(["--require-artifacts", "--trust", str(tmp_path / "s" / "trust.json"), "."],
               signed / "signed"),
              (["--require-artifacts", "--tsa-cert", str(cert), "--tsa-root", str(root), "."],
               runs / "anchored")]
    examined(len(checks), "checks run under the audit hook")
    for args, folder in checks:
        assert _socket_events(args, folder) == (0, []), folder.name


def test_sabotage_the_hook_sees_a_socket_when_there_is_one(tmp_path, examined):
    examined(1, "control")
    code, events = _socket_events(["--control"], tmp_path)
    assert "socket.getaddrinfo" in events


def test_offline_is_said_on_no_page(tmp_path, examined):
    """The ruled words: "no network calls", never "offline"."""
    runs = _signed_run(tmp_path)
    store, pages = _pages(runs, tmp_path, trust_file=str(tmp_path / "trust.json"))
    files = sorted(pages.rglob("*.html"))
    examined(len(files), "pages")
    said = [p.name for p in files if re.search(r"\boffline\b", _text(p.read_text(encoding="utf-8")), re.I)]
    assert said == []


# ------------------------------------------------------------------ the pills

def test_each_pill_takes_its_rungs_tone(tmp_path, examined):
    from onetrace_console import tones
    runs = _signed_run(tmp_path)
    store, pages = _pages(runs, tmp_path, trust_file=str(tmp_path / "trust.json"))
    run, page = _receipt(pages, store, "signed-run")
    case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    ladder = dict(re.findall(r'<tr data-rung="([^"]+)" data-state="([^"]+)">', case))
    pills = re.findall(r'<span class="pill (\w+)">(.*?)</span>',
                       re.search(r'<p data-section="pills">(.*?)</p>', page, re.S).group(1))
    examined(len(pills), "pills")
    assert [t for t, _ in pills] == [tones.tone(tones.RUNG, ladder[k])
                                    for k in ("records-agree", "signed", "anchored")]
    assert pills[1][1].startswith("Signed: ") and pills[2][1].startswith("Anchored: ")
