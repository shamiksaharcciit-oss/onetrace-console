"""The console's `[crypto]` pins (§1) and its trust file (§2), on a run the SDK really
signed: the demo pipeline recorded by onetrace, then signed with a test-only key `keygen` made in a
folder outside the run. Nothing here hand-writes a signature record.

§1  With the extra installed, the pinned verifier checks the signature: its row is the signature's
    result, never "install onetrace-verify[crypto] to check signatures".
§2  `trust_file`, an operator setting, none by default. Absent: a valid signature reads "Signed, key
    not trusted", never Yes. Naming the key: Yes. A file the verifier can't read: its own `--trust`
    FAIL row, shown as it is. Each stored check records the trust file it ran with (its sha256, or
    "none"), and a change of trust file checks the run again, said, never silently.
"""
from __future__ import annotations

import functools
import json
import re
import sys
from html import unescape

import pytest

from onetrace_console.checks import NO_TRUST_FILE, run_and_record, stored_trust_record
from onetrace_console.config import Config, ConfigError, _from_mapping
from onetrace_console.ingest import accept
from onetrace_console.store import Store
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_reference_demo import DEMO, _delivery
from tests.test_stage_pages import GENERATED_AT

INSTALL_LINE = "install onetrace-verify[crypto] to check signatures"


@pytest.fixture
def signed(tmp_path, monkeypatch):
    """(the signed run's folder, its key_id, its signatures/1.json bytes)."""
    _require_installed()
    from onetrace.signing import keygen, sign_run
    monkeypatch.syspath_prepend(str(DEMO))
    import demo as pipeline
    out = tmp_path / "signed-run"
    pipeline.main(str(out), "exec-signed", 1, "2026-09-28T10:00:00.000+00:00")
    sys.modules.pop("demo", None)
    keys = tmp_path / "keys"
    keys.mkdir()
    _pub, key_id = keygen(keys / "demo-test.pem", test_only=True)
    record = sign_run(out, keys / "demo-test.pem", signer="demo-recorder")
    assert record.parent.name == "signatures"
    return out, key_id, record.read_bytes()


def _checked(signed, tmp_path, trust_file=None):
    folder, _key, sig = signed
    store = Store(tmp_path / "store")
    accepted = accept(_delivery(folder, {"signatures/1.json": sig}), store)
    assert getattr(accepted, "run", None) is not None, getattr(accepted, "rows", accepted)
    return run_and_record(accepted.run, store, ran_at=FIXED_RAN_AT, trust_file=trust_file), store


def _stdout(run, store) -> str:
    return json.loads(store.get(run.check_report).decode("utf-8"))["stdout"]


def _signed_rung(run, store) -> tuple[str, str]:
    from onetrace_console.pages import CASE, render_execution
    case = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    found = re.search(r'<tr data-rung="signed" data-state="([^"]+)"><td>.*?</td><td>(.*?)</td></tr>',
                      case, re.S)
    assert found, "no signing rung"
    return found.group(1), re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", found.group(2)))).strip()


def _trust(tmp_path, key_id: str, label: str, name: str = "trust.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"format": "onetrace-trust/0.1",
                                "keys": [{"key_id": key_id, "label": label}]}), encoding="utf-8")
    return path


# ------------------------------------------------------------------- §1: the extra is installed

def test_the_pinned_verifier_checks_a_signature_rather_than_asking_for_the_extra(signed, tmp_path):
    run, store = _checked(signed, tmp_path)
    out = _stdout(run, store)
    assert INSTALL_LINE not in out, "the signature was not checked: the [crypto] extra is missing"
    assert f"[SIGNED-UNTRUSTED] signatures/1.json: signature -- signed by an untrusted key {signed[1]}" in out


# ------------------------------------------------------------------- §2: the trust file

def test_without_a_trust_file_a_valid_signature_is_signed_key_not_trusted(signed, tmp_path):
    run, store = _checked(signed, tmp_path)
    assert stored_trust_record(run, store) == NO_TRUST_FILE
    assert "--trust" not in json.loads(store.get(run.check_report))["command"]
    assert _signed_rung(run, store) == ("signed-untrusted", f"Signed, key not trusted · {signed[1]}")


def test_a_trust_file_naming_the_key_reads_yes_with_its_label(signed, tmp_path):
    trust = _trust(tmp_path, signed[1], "Ops recorder")
    run, store = _checked(signed, tmp_path, trust_file=str(trust))
    import hashlib
    assert stored_trust_record(run, store) == "sha256:" + hashlib.sha256(trust.read_bytes()).hexdigest()
    assert _signed_rung(run, store) == ("yes", f"Yes · Ops recorder · {signed[1]}")


@pytest.mark.parametrize("folder", ["plain", "back\\slash"])
def test_a_trust_file_the_verifier_cannot_read_is_its_own_fail_row_shown_as_it_is(signed, tmp_path,
                                                                                folder):
    """On every OS, a backslash in the trust file's path included (the text row escapes it, the
    --json row doesn't, and the rows still pair)."""
    #: On Windows a backslash is the separator, so "back\\slash" is two folders there --
    #: a path holding backslashes, which every Windows path is; made with its parents.
    (tmp_path / folder).mkdir(parents=True)
    bad = tmp_path / folder / "trust.json"
    bad.write_text('{"format": "not-a-trust-file"}', encoding="utf-8")
    run, store = _checked(signed, tmp_path, trust_file=str(bad))
    out = _stdout(run, store)
    assert re.search(r"^\[FAIL   \] --trust \S+", out, re.M), out[-600:]
    assert run.check_verdict == "contradicts"
    from onetrace_console.pages import CASE, render_execution
    case = unescape(render_execution(run, store, generated_at=GENERATED_AT).pages[CASE])
    assert "--trust" in case, "the verifier's own row is on the page"


def test_a_changed_trust_file_checks_the_run_again_and_says_so(signed, tmp_path, capsys):
    from onetrace_console.serve import _render_startup_pages
    trust = _trust(tmp_path, signed[1], "Ops recorder")
    run, store = _checked(signed, tmp_path, trust_file=str(trust))
    first = stored_trust_record(run, store)
    trust.write_text(json.dumps({"format": "onetrace-trust/0.1", "keys": []}), encoding="utf-8")
    root = tmp_path / "data"
    root.mkdir()
    _render_startup_pages(store, root, Config(trust_file=str(trust)))
    again = store.get_run(run.key)
    assert stored_trust_record(again, store) not in (first, None), "the sha256 moves with the file"
    assert "checked again" in capsys.readouterr().err, "never silently"
    assert _signed_rung(again, store)[0] == "signed-untrusted"


def test_the_setting_is_absent_by_default_and_a_path_or_null(tmp_path):
    assert Config().trust_file is None
    assert _from_mapping({"trust_file": "/etc/onetrace/trust.json"}, source="t").trust_file == (
        "/etc/onetrace/trust.json")
    assert _from_mapping({"trust_file": None}, source="t").trust_file is None
    for wrong in (3, "", "a\x00b", True):
        with pytest.raises(ConfigError):
            _from_mapping({"trust_file": wrong}, source="t")


def test_the_lock_pins_the_sdks_crypto_versions_by_hash():
    """§1: exactly the versions the SDK's crypto extra pins at 0.2.0, each with hashes."""
    from pathlib import Path
    lock = (Path(__file__).resolve().parent.parent / "requirements.lock").read_text(encoding="utf-8")
    for pin in ("cryptography==50.0.1", "rfc3161-client==1.0.9", "asn1crypto==1.5.1", "cffi==2.1.1",
                "pycparser==3.0"):
        block = lock[lock.index(pin):].split("\n\n")[0]
        assert "--hash=sha256:" in block, pin
