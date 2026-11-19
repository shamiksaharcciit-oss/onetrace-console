"""`recipients_file`, the recipients a console's operator trusts to confirm an action, named as the trust file is:
read from the configuration (a relative path from the file's folder), passed to every check as the verifier's own
`--recipients`, copied beside the laid-out run so no path of this machine is stored, and recorded by its digest, so a
changed file checks every run again. A recipient's confirmation's key row then reads as the verifier reads it; without
one it reads NOT-RUN, as before."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path

import pytest

from tests.test_step_kinds import _text

VECTORS = Path(__file__).resolve().parent / "format_05_vectors"
RAN_AT = "2026-11-12T00:00:00+00:00"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed

    _require_installed()


def _stored(folder: Path, tmp_path: Path, recipients: Path | None):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    from onetrace_console.store import Store
    from tests.test_format_03 import _tar

    store = Store(tmp_path / "store")
    run = run_and_record(
        accept(_tar(folder), store).run, store, ran_at=RAN_AT, recipients_file=str(recipients) if recipients else None
    )
    return run, store


def _envelope(run, store) -> dict:
    from onetrace_console.home import _envelope as read

    return read(run, store)


def _key_row(run, store) -> dict:
    from onetrace_console.info_mark import rows_of

    (row,) = [r for r in rows_of(_envelope(run, store)) if r.get("name") == "confirmation: recipient key"]
    return row


def test_the_configuration_reads_it_as_a_path_from_its_own_folder_and_refuses_a_non_path(tmp_path, examined):
    from onetrace_console.config import ConfigError
    from onetrace_console.config import load as load_config

    (tmp_path / "console.json").write_text(json.dumps({"recipients_file": "recipients.json"}), encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"recipients_file": 7}), encoding="utf-8")
    examined(2, "configuration files")
    assert Path(load_config(tmp_path / "console.json").recipients_file) == tmp_path / "recipients.json"
    with pytest.raises(ConfigError, match="recipients_file must be a path"):
        load_config(bad)


def test_with_a_recipients_file_the_key_row_reads_as_the_verifier_reads_it(tmp_path, examined):
    folder = VECTORS / "A102-real-effected"
    recipients = tmp_path / "trusted-recipients.json"
    shutil.copyfile(folder / "recipients.json", recipients)
    run, store = _stored(folder, tmp_path, recipients)
    envelope = _envelope(run, store)
    command = " ".join(" ".join(part.get("command", [])) for part in envelope.values() if isinstance(part, dict))
    examined(3, "the check's key row, its command and its record of the file")
    assert _key_row(run, store)["result"] == "PASS", _key_row(run, store)
    assert "--recipients" in command and str(tmp_path) not in command and "\\" not in command
    assert envelope["recipients_file"] == "sha256:" + hashlib.sha256(recipients.read_bytes()).hexdigest()


def test_a_key_that_does_not_verify_fails_and_the_page_draws_no_confirmation(tmp_path, examined):
    """R119: the confirmation does not verify under the recipient's listed key. With the list given it FAILs, and
    the Authorization page draws no step's confirmation."""
    from onetrace_console.pages import render_execution

    folder = VECTORS / "confirmations" / "R119-confirmation-c04"
    run, store = _stored(folder, tmp_path, folder / "recipients.json")
    page = dict(render_execution(store.get_run(run.key), store, generated_at=RAN_AT).pages)["authorization.html"]
    section = re.search(r'<section data-section="confirmations">.*?</section>', page, re.S).group(0)
    examined(2, "the key row and the Authorization page")
    assert _key_row(run, store)["result"] == "FAIL"
    assert "confirmation: recipient key" in _text(section) and "data-confirmation=" not in section


def test_without_one_the_key_row_reads_not_run_as_before(tmp_path, examined):
    run, store = _stored(VECTORS / "A102-real-effected", tmp_path, None)
    examined(2, "the key row and the check's record of the file")
    assert _key_row(run, store)["result"] == "NOT-RUN"
    assert _envelope(run, store)["recipients_file"] == "none"


def test_a_changed_recipients_file_checks_every_run_again(tmp_path, examined):
    from onetrace_console.config import Config
    from onetrace_console.serve import _render_startup_pages_read

    folder = VECTORS / "A102-real-effected"
    recipients = tmp_path / "trusted-recipients.json"
    shutil.copyfile(folder / "recipients.json", recipients)
    run, store = _stored(folder, tmp_path, None)
    root = tmp_path / "site"
    root.mkdir()
    _render_startup_pages_read(store, root, Config(recipients_file=str(recipients)))
    again = store.get_run(run.key)
    examined(1, "a run checked without a recipients file, the console started with one")
    assert _key_row(again, store)["result"] == "PASS"


def test_the_operator_readme_names_it_beside_the_trust_file(examined):
    text = (Path(__file__).resolve().parent.parent / "OPERATOR_README.md").read_text(encoding="utf-8")
    examined(1, "the operator README")
    assert text.index("| `trust_file` |") < text.index("| `recipients_file` |")
    assert '"recipients_file": null' in text
