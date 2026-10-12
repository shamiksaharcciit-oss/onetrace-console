"""`onetrace-console <runs folder> --trust FILE --tsa-cert FILE --tsa-root FILE`: what a reader
trusts, passed to every check as the verifier's own options.

1. Signing, end to end: a key made, a run recorded and signed, the console started on its folder.
   With `--trust` naming the key, the run reads "Signed by a known recorder: Yes" with the key's
   label, on its page and on the Overview (green). Without it: "Signed, key not trusted" (amber).
2. Anchoring: a run anchored by an RFC 3161 time-stamp authority. With `--tsa-cert` and
   `--tsa-root` naming that authority, "Committed by a known time" reads Yes (green) -- though
   every receipt still declares the run unanchored, as it was written. Without them it reads
   "Couldn't check" (amber), naming the two options to add.
3. A stored check records the files it ran with; started again with the same files, nothing is
   checked again, and with different ones every run is.
4. Each flag is refused at start, with its fix, when it can't be read; --tsa-cert and --tsa-root
   go together. A configuration file's relative paths are read from that file's own folder.

THE TIME-STAMP AUTHORITY. tests/rfc3161_test_tsa.py is the SDK's own test-only TSA, copied byte
for byte from the SDK's repository at commit b1feb06 (`tests/rfc3161_test_tsa.py`, 6928 bytes,
sha256 ad4a3bc682c268e38ccd636e23ef04b260684bb149b9c3468b2631da505a1984, held below). It makes its
root and certificate when a test runs, in memory; the files a check reads are written to the
test's own temporary folder. Nothing reaches a network. It lives under tests/ only, never in the
package. A real authority (FreeTSA) is checked by hand at the release, not here.
"""
from __future__ import annotations

import base64
import hashlib
import json
from html import unescape
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
TSA_HELPER_SHA256 = "ad4a3bc682c268e38ccd636e23ef04b260684bb149b9c3468b2631da505a1984"
LABEL = "my laptop (test)"


def test_the_tsa_helper_is_the_sdks_own_byte_for_byte(examined):
    helper = REPO / "tests" / "rfc3161_test_tsa.py"
    examined(1, "copied file")
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == TSA_HELPER_SHA256
    assert not list((REPO / "src").rglob("rfc3161_test_tsa.py")), "never in the package"


# ------------------------------------------------------------------ making the evidence

def _record(folder: Path, run_id: str) -> None:
    from onetrace.emit import Instrument, Recorder
    rec = Recorder(str(folder), run_id=run_id, declared_stages=["write"], manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="written before it was anchored")
    rec.run_node("write", None, Instrument("writer", "tool", "1.0.0", {"k": "v"}),
                 lambda ctx: ctx.write("out.txt", b"hello\n", "text/plain"))
    rec.close()


def _signed_run(root: Path) -> Path:
    """A run signed with a key made now, and the trust file naming that key."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from onetrace.signing import sign_run
    from onetrace_verify.signatures import key_id_of
    runs = root / "runs"
    _record(runs / "signed", "signed-run")
    key = Ed25519PrivateKey.generate()
    pem = root / "keys" / "key.pem"
    pem.parent.mkdir()
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    sign_run(runs / "signed", pem)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    (root / "trust.json").write_text(json.dumps({"format": "onetrace-trust/0.1", "keys": [
        {"key_id": key_id_of(raw), "label": LABEL}]}), encoding="utf-8")
    return runs


def _anchored_run(root: Path) -> tuple[Path, Path, Path]:
    """A run anchored by the test TSA over its chain head; the authority's certificate and root
    written beside it, as a reader would pin them."""
    import sys
    sys.path.insert(0, str(REPO / "tests"))
    from rfc3161_test_tsa import TestTSA
    from onetrace.anchor import add_anchor
    from onetrace_verify import anchors
    runs = root / "runs"
    _record(runs / "anchored", "anchored-run")
    head = json.loads((runs / "anchored" / "MANIFEST.json").read_text(encoding="utf-8"))["chain_head"]
    tsa = TestTSA()
    proof = tsa.response(bytes.fromhex(head.split(":", 1)[1]))
    record = {"format": anchors.FORMAT, "chain_head": head, "method": "rfc3161",
              "proof": base64.b64encode(proof).decode("ascii"),
              "source": {"tsa_certificate_sha256": tsa.cert_sha256()},
              "asserted_time": "2026-09-30T12:00:00Z"}
    add_anchor(runs / "anchored", record, tsa_trust=anchors.TsaTrust(tsa.cert_der(), [tsa.root_der()]))
    cert, root_cert = root / "tsa" / "cert.der", root / "tsa" / "root.der"
    cert.parent.mkdir()
    cert.write_bytes(tsa.cert_der())
    root_cert.write_bytes(tsa.root_der())
    return runs, cert, root_cert


def _pages(runs: Path, root: Path, **options) -> tuple[object, Path]:
    """Load the folder as `onetrace-console <runs folder>` does, with these options, and draw."""
    from onetrace_console.config import Config
    from onetrace_console.folder_load import load_folder
    from onetrace_console.serve import _render_startup_pages
    from onetrace_console.store import Store
    from tests.test_checks import _require_installed
    _require_installed()
    store_root = root / "store"
    config = Config(**options)
    store = Store(store_root / "store")
    load_folder(runs, store, config)
    _render_startup_pages(store, store_root, config)
    return store, store_root / "pages"


def _rung(pages: Path, store, rung: str) -> tuple[str, str]:
    import re
    (run,) = store.runs()
    case = (pages / "runs" / run.key / "case.html").read_text(encoding="utf-8")
    m = re.search(rf'<tr data-rung="{rung}" data-state="([^"]*)"><td>[^<]*</td><td>(.*?)</td></tr>', case, re.S)
    return m.group(1), unescape(re.sub(r"<[^>]+>", "", m.group(2)))


# ------------------------------------------------------------------ 1. signing, end to end

def test_with_trust_a_signed_run_reads_yes_with_its_label_from_the_command_line(tmp_path, examined):
    from tests.test_checks import _require_installed
    from tests.test_folder_load import _Console, _free_port, _get, _url
    _require_installed()
    runs = _signed_run(tmp_path)
    port = _free_port()
    c = _Console(tmp_path, str(runs), "--trust", "trust.json", "--port", str(port))
    try:
        overview = c.until("overview:")
        line = next(l for l in c.lines if l.strip().startswith("signed"))
        case, home = _get(_url(line)), _get(_url(overview))
    finally:
        c.stop()
    examined(2, "pages")
    import re
    text = lambda page: " ".join(unescape(re.sub(r"<[^>]+>", " ", page)).split())  # noqa: E731
    assert f"Yes · {LABEL}" in text(case) and 'data-rung="signed" data-state="yes"' in case
    assert "1 yes" in text(home)


def test_without_trust_the_same_run_reads_key_not_trusted(tmp_path, examined):
    runs = _signed_run(tmp_path)
    store, pages = _pages(runs, tmp_path)
    state, said = _rung(pages, store, "signed")
    examined(1, "run page")
    assert state == "signed-untrusted" and said.startswith("Signed, key not trusted")
    from onetrace_console import tones
    assert tones.tone(tones.RUNG, state) == "cc", "amber"


# ------------------------------------------------------------------ 2. anchoring

def test_with_the_tsa_files_an_anchored_run_reads_yes_despite_its_receipts(tmp_path, examined):
    runs, cert, root_cert = _anchored_run(tmp_path)
    store, pages = _pages(runs, tmp_path, tsa_cert=str(cert), tsa_roots=(str(root_cert),))
    state, said = _rung(pages, store, "anchored")
    examined(1, "run page")
    assert (state, said.split(" · ")[0]) == ("yes", "Yes"), (state, said)
    receipts = list((runs / "anchored" / "receipts").glob("*.json"))
    assert all(json.loads(r.read_text(encoding="utf-8"))["anchor"]["state"] == "unanchored" for r in receipts), \
        "every receipt declares the run unanchored, as it was written; the passing anchor wins"


def test_without_the_tsa_files_it_reads_couldnt_check_and_names_the_options(tmp_path, examined):
    runs, _cert, _root = _anchored_run(tmp_path)
    store, pages = _pages(runs, tmp_path)
    state, said = _rung(pages, store, "anchored")
    examined(1, "run page")
    assert state == "couldnt-check" and "--tsa-cert" in said and "--tsa-root" in said, (state, said)


# ------------------------------------------------------------------ 3. checked again only when the files change

def test_the_same_files_check_nothing_again_and_different_ones_check_every_run(tmp_path, examined):
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages
    runs, cert, root_cert = _anchored_run(tmp_path)
    options = {"tsa_cert": str(cert), "tsa_roots": (str(root_cert),)}
    store, _ = _pages(runs, tmp_path, **options)
    (first,) = store.runs()
    _render_startup_pages(store, tmp_path / "store", Config(**options))
    (same,) = store.runs()
    _render_startup_pages(store, tmp_path / "store", Config())
    (dropped,) = store.runs()
    examined(3, "starts")
    assert same.check_report == first.check_report, "the same files: not checked again"
    assert dropped.check_report != first.check_report, "the authority dropped: checked again"


# ------------------------------------------------------------------ 4. refusals and relative paths

@pytest.mark.parametrize("args, said", [
    (["--trust", "no-such.json"], "--trust no-such.json: cannot read"),
    (["--tsa-cert", "cert.der"], "--tsa-cert and --tsa-root go together"),
], ids=["unreadable", "alone"])
def test_a_flag_that_cant_be_used_is_refused_at_start_with_its_fix(tmp_path, args, said, examined):
    from tests.test_folder_load import _Console, _free_port
    (tmp_path / "runs").mkdir()
    _record(tmp_path / "runs" / "a", "a")
    (tmp_path / "cert.der").write_bytes(b"x")
    c = _Console(tmp_path, "runs", *args, "--port", str(_free_port()))
    code, out = c.exited()
    examined(1, "start")
    assert code == 1 and said in out and "fix:" in out, out


def test_a_configuration_files_relative_paths_are_read_from_its_own_folder(tmp_path, examined):
    from onetrace_console.config import load
    folder = tmp_path / "conf"
    folder.mkdir()
    path = folder / "console.json"
    path.write_text(json.dumps({"trust_file": "trust.json", "tsa_cert": "tsa/cert.der",
                                "tsa_roots": ["tsa/root.der"], "sign_in": {"enabled": False}}),
                    encoding="utf-8")
    config = load(path)
    examined(3, "paths")
    assert config.trust_file == str(folder / "trust.json")
    assert config.tsa_cert == str(folder / "tsa" / "cert.der")
    assert config.tsa_roots == [str(folder / "tsa" / "root.der")]


#: A path is relative only with neither a root nor a drive: each rooted or drive-letter path is kept
#: as written, under both systems' rules, whichever system runs the test. The early check's Windows
#: run found `/srv/onetrace-demo/trust.json` -- no drive, but a root -- read as relative and
#: resolved to `D:\srv\onetrace-demo\trust.json`.
_KEPT = [("posix", "/srv/onetrace-demo/trust.json"), ("windows", "/srv/onetrace-demo/trust.json"),
         ("windows", "C:\\onetrace\\trust.json"), ("windows", "c:/onetrace/trust.json"),
         ("windows", "\\\\host\\share\\trust.json"), ("windows", "\\onetrace\\trust.json"),
         ("windows", "D:trust.json")]
_JOINED = [("posix", "/etc/onetrace", "trust.json", "/etc/onetrace/trust.json"),
           ("posix", "/etc/onetrace", "../keys/trust.json", "/etc/onetrace/../keys/trust.json"),
           ("windows", "C:\\conf", "trust.json", "C:\\conf\\trust.json"),
           ("windows", "C:\\conf", "tsa/root.der", "C:\\conf\\tsa\\root.der")]


def _flavour(name):
    from pathlib import PurePosixPath, PureWindowsPath
    return {"posix": PurePosixPath, "windows": PureWindowsPath}[name]


@pytest.mark.parametrize("rules, value", _KEPT, ids=[f"{r}:{v}" for r, v in _KEPT])
def test_a_path_with_a_root_or_a_drive_is_kept_as_written_under_either_systems_rules(
        rules, value, examined):
    from onetrace_console.config import from_folder
    examined(1, "path")
    assert from_folder(value, "/etc/onetrace" if rules == "posix" else "C:\\conf",
                       _flavour(rules)) == value


@pytest.mark.parametrize("rules, base, value, joined", _JOINED, ids=[f"{r}:{v}" for r, _, v, _ in _JOINED])
def test_a_relative_path_is_read_from_its_folder_and_never_resolved(rules, base, value, joined, examined):
    from onetrace_console.config import from_folder
    examined(1, "path")
    assert from_folder(value, base, _flavour(rules)) == joined


def test_on_this_system_a_rooted_path_in_a_configuration_file_and_on_the_command_line_is_kept(
        tmp_path, monkeypatch, examined):
    """This system's own rules, end to end: a configuration file naming `/srv/...` (rooted on
    every system), a path with this system's drive or root, and a relative one; and the same three
    as --trust, --tsa-cert, --tsa-root, from the folder the console is started in. The relative
    ones go through `..`, so a path resolved after all reads differently."""
    import argparse
    import os
    from onetrace_console.config import load
    from onetrace_console.folder_load import evidence_files
    folder = tmp_path / "conf"
    folder.mkdir()
    native = str(tmp_path / "elsewhere" / "root.der")   # this system's own absolute form
    path = folder / "console.json"
    path.write_text(json.dumps({"trust_file": "/srv/onetrace-demo/trust.json", "tsa_cert": native,
                                "tsa_roots": ["../conf/tsa/root.der"], "sign_in": {"enabled": False}}),
                    encoding="utf-8")
    config = load(path)
    assert config.trust_file == "/srv/onetrace-demo/trust.json"
    assert config.tsa_cert == native
    assert config.tsa_roots == [str(folder / ".." / "conf" / "tsa" / "root.der")]   # as written, unresolved

    (tmp_path / "elsewhere").mkdir()
    for name in ("trust.json", "cert.der", "root.der"):
        (tmp_path / "elsewhere" / name).write_bytes(b"x")
    monkeypatch.chdir(tmp_path)
    rooted = str(tmp_path / "elsewhere" / "trust.json")
    if os.name == "nt":   # the same file by its root alone, no drive: still not relative
        rooted = rooted[len(tmp_path.drive):]
    out = evidence_files(argparse.Namespace(trust=rooted, tsa_cert=os.path.join("conf", "..", "elsewhere", "cert.der"),
                                            tsa_root=[native]))
    examined(6, "paths")
    assert out == {"trust_file": rooted, "tsa_cert": str(tmp_path / "conf" / ".." / "elsewhere" / "cert.der"),
                   "tsa_roots": [native]}
