"""The audit log and its verifier, its second head location and its gaps: the tests of the log itself.

- the verifier passes on a fresh log, and fails on an edited entry, a removed middle entry, a removed segment, and a
  cut tail checked against a checkpoint;
- the console refuses to start with the audit log on and no `audit.head_location`, or with one on the store's volume;
- every append writes its head to the second location, and the verifier with `--heads` fails a cut tail and a chain
  written again from its first entry;
- two writers, a server and a command line, appending at once give one chain with no repeated `seq`;
- `audit export` writes a `SHA256SUMS` that covers every file, and the verifier passes on the export alone, copied
  out and run by the standard interpreter with nothing installed.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tests.test_team_assignment import _body, _refused, _serve


@pytest.fixture
def second(tmp_path, monkeypatch):
    """A folder standing for a second mounted volume: `audit.device_of` reads it as another device."""
    from onetrace_console import audit

    folder = tmp_path / "second-volume"
    folder.mkdir()
    real = audit.device_of

    def device_of(path):
        p = Path(path).resolve()
        return -1 if p == folder or folder in p.parents else real(path)

    monkeypatch.setattr(audit, "device_of", device_of)
    return folder


@pytest.fixture
def log(tmp_path, second):
    """An audit log with small segments, so a few entries span several."""
    from onetrace_console.audit import AuditLog

    return AuditLog(tmp_path / "audit_log", head_location=second / "heads.jsonl", max_segment_bytes=600)


def _fill(log, n=12) -> list[dict]:
    return [log.append("alice", "compare.made", f"c{i}", {"a": f"a{i}", "b": f"b{i}"}) for i in range(n)]


def _verify(folder, **kw) -> list[tuple[str, str, str]]:
    from onetrace_console.audit_verify import verify

    return verify(folder, **kw)


def _failed(rows) -> set[str]:
    return {check for outcome, check, _ in rows if outcome == "FAIL"}


def _segments(log) -> list[Path]:
    return sorted(log.root.glob("*.jsonl"))


def _rewrite_head(log) -> None:
    """Make HEAD.json agree with the segments as they now are, as someone editing the volume would."""
    from onetrace_console.audit import digest

    segs = _segments(log)
    lines = [ln for s in segs for ln in s.read_bytes().splitlines() if ln]
    head = {
        "segment": int(segs[-1].stem),
        "segment_size": segs[-1].stat().st_size,
        "seq": json.loads(lines[-1])["seq"],
        "head": digest(lines[-1]),
    }
    (log.root / "HEAD.json").write_text(json.dumps(head, sort_keys=True) + "\n", encoding="utf-8")


def test_the_verifier_passes_on_a_fresh_log(log, capsys, examined):
    from onetrace_console.__main__ import main as cli_main

    entries = _fill(log)
    assert len(_segments(log)) >= 3, "small segments: the chain crosses them"
    assert [e["seq"] for e in entries] == list(range(1, 13)) and entries[0]["prev"] is None
    rows = _verify(log.root, heads=log.head_location)
    assert _failed(rows) == set(), rows
    assert {c for _o, c, _d in rows} >= {"segments", "chain", "HEAD.json", "heads"}
    assert cli_main(["audit", "verify", str(log.root), "--heads", str(log.head_location)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("[PASS] segments -- ") and "[FAIL]" not in out
    examined(len(entries), "entries across the segments, each checked")


def test_each_entry_s_prev_is_the_sha256_of_the_previous_line_as_stored(log, examined):
    import hashlib

    _fill(log, 4)
    lines = [ln for s in _segments(log) for ln in s.read_bytes().splitlines() if ln]
    for before, line in zip(lines, lines[1:]):
        assert json.loads(line)["prev"] == "sha256:" + hashlib.sha256(before).hexdigest()
    assert set(json.loads(lines[0])) == {"seq", "at", "actor", "event", "object", "detail", "prev"}
    examined(len(lines) - 1, "links, each over the bytes stored")


def _edit_middle(log):
    seg = _segments(log)[1]
    lines = seg.read_bytes().split(b"\n")
    lines[0] = lines[0].replace(b'"a":"a', b'"a":"z')
    seg.write_bytes(b"\n".join(lines))
    _rewrite_head(log)


def _remove_middle_entry(log):
    seg = _segments(log)[1]
    lines = seg.read_bytes().split(b"\n")
    del lines[0]
    seg.write_bytes(b"\n".join(lines))
    _rewrite_head(log)


def _remove_segment(log):
    _segments(log)[1].unlink()
    _rewrite_head(log)


@pytest.mark.parametrize(
    "tamper, caught_by",
    [(_edit_middle, "chain"), (_remove_middle_entry, "chain"), (_remove_segment, "segments")],
    ids=["an edited entry", "a removed middle entry", "a removed segment"],
)
def test_the_verifier_fails_an_edited_or_removed_entry_and_a_removed_segment(log, tamper, caught_by, examined):
    _fill(log)
    tamper(log)
    failed = _failed(_verify(log.root))
    assert caught_by in failed, failed
    examined(1, tamper.__name__)


def _cut_tail(log, n=3):
    """Cut the last `n` entries and write HEAD.json and the segments to agree: what the chain alone cannot show."""
    lines = [ln for s in _segments(log) for ln in s.read_bytes().splitlines() if ln]
    keep = lines[:-n]
    for s in _segments(log):
        s.unlink()
    (log.root / "000001.jsonl").write_bytes(b"".join(ln + b"\n" for ln in keep))
    _rewrite_head(log)


def test_a_cut_tail_passes_the_chain_and_fails_against_a_checkpoint(log, capsys, examined):
    from onetrace_console.__main__ import main as cli_main

    _fill(log, 9)
    head = log.head()
    checkpoint = f"{head['seq']}:{head['head']}"
    _cut_tail(log)
    assert _failed(_verify(log.root)) == set(), "the chain and HEAD.json agree: a chain alone cannot show its tail cut"
    assert "checkpoint" in _failed(_verify(log.root, checkpoint=checkpoint))
    assert cli_main(["audit", "verify", str(log.root), "--checkpoint", checkpoint]) == 1
    assert "[FAIL] checkpoint -- no entry at seq 9" in capsys.readouterr().out
    examined(2, "a cut tail: without the checkpoint, and with it")


def test_every_append_writes_its_head_to_the_second_location(log, examined):
    from onetrace_console.audit import digest

    _fill(log, 7)
    heads = [json.loads(x) for x in log.head_location.read_bytes().splitlines()]
    lines = [ln for s in _segments(log) for ln in s.read_bytes().splitlines() if ln]
    assert [(h["seq"], h["head"]) for h in heads] == [(i + 1, digest(ln)) for i, ln in enumerate(lines)]
    examined(len(heads), "heads, one per append")


def _write_again(log):
    """The chain written again from its first entry, every link made good, HEAD.json too."""
    from onetrace_console.audit import digest, line_of

    entries = log.entries()
    prev = None
    out = []
    for e in entries:
        e = {**e, "detail": {**e["detail"], "a": "rewritten"}, "prev": prev}
        line = line_of(e)
        prev = digest(line)
        out.append(line + b"\n")
    for s in _segments(log):
        s.unlink()
    (log.root / "000001.jsonl").write_bytes(b"".join(out))
    _rewrite_head(log)


@pytest.mark.parametrize("tamper", [_cut_tail, _write_again], ids=["a cut tail", "a chain written again"])
def test_the_verifier_with_heads_fails_a_cut_tail_and_a_chain_written_again(log, tamper, examined):
    _fill(log, 8)
    tamper(log)
    assert _failed(_verify(log.root)) == set(), "the store's volume alone agrees with itself"
    assert _failed(_verify(log.root, heads=log.head_location)) == {"heads"}
    examined(1, tamper.__name__)


# ------------------------------------------------------------------ the start


def test_the_console_refuses_to_start_with_the_audit_log_on_and_no_head_location(
    tmp_path, monkeypatch, capsys, examined
):
    assert _serve(tmp_path, monkeypatch, _body(tmp_path, audit={"enabled": True})) == 1
    err = _refused(capsys)
    assert "audit.enabled is true and audit.head_location is not set" in err, err
    examined(1, "the audit log on, no head location")


def test_the_console_refuses_a_head_location_on_the_store_s_volume(tmp_path, monkeypatch, capsys, examined):
    on_store = (tmp_path / "data-heads.jsonl").as_posix()
    body = _body(tmp_path, audit={"enabled": True, "head_location": on_store})
    assert _serve(tmp_path, monkeypatch, body) == 1
    err = _refused(capsys)
    assert "on the store's volume" in err and "audit.head_location" in err, err
    examined(1, "a head location on the store's device")


def test_the_console_refuses_a_head_location_whose_folder_is_not_there(tmp_path, monkeypatch, capsys, second, examined):
    body = _body(tmp_path, audit={"enabled": True, "head_location": (second / "unmounted" / "h.jsonl").as_posix()})
    assert _serve(tmp_path, monkeypatch, body) == 1
    assert "its folder does not exist" in _refused(capsys)
    examined(1, "a head location in a folder not there")


def test_with_a_second_volume_the_console_starts_and_says_the_head(tmp_path, monkeypatch, capsys, second, examined):
    body = _body(tmp_path, audit={"enabled": True, "head_location": (second / "heads.jsonl").as_posix()})
    assert _serve(tmp_path, monkeypatch, body) == -1, capsys.readouterr().err
    assert "audit log: on, seq " in capsys.readouterr().err
    examined(1, "a head location on another device")


def test_off_by_default_no_audit_log_is_written(tmp_path, monkeypatch, capsys, examined):
    from onetrace_console.config import Config

    assert Config().audit == {"enabled": False, "head_location": None, "max_segment_bytes": 1048576}
    assert _serve(tmp_path, monkeypatch, _body(tmp_path)) == -1, capsys.readouterr().err
    assert not (tmp_path / "data" / "audit_log").exists()
    examined(1, "the default configuration")


@pytest.mark.parametrize(
    "audit, said",
    [
        ("on", "audit must be an object"),
        ({"enabled": "yes"}, "audit.enabled must be true or false"),
        ({"head_location": 3}, "audit.head_location must be a path"),
        ({"max_segment_bytes": 100}, "audit.max_segment_bytes must be a whole number of at least 4096"),
        ({"keep": True}, "unknown audit key(s) ['keep']"),
    ],
)
def test_the_audit_key_s_values_are_checked(tmp_path, audit, said, examined):
    from onetrace_console.config import ConfigError, load

    path = tmp_path / "c.json"
    path.write_text(json.dumps({"audit": audit}), encoding="utf-8")
    with pytest.raises(ConfigError) as e:
        load(path)
    assert said in str(e.value), str(e.value)
    examined(1, f"audit {audit!r}")


# ------------------------------------------------------------------ two writers


_WRITER = """
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from onetrace_console.audit import AuditLog
log = AuditLog(Path(sys.argv[2]), head_location=Path(sys.argv[3]), max_segment_bytes=4096)
for i in range(int(sys.argv[4])):
    log.append("cli", "token.created", f"cli-{i}", {"principal": "ci"})
"""


def test_two_writers_a_server_and_a_command_line_give_one_chain_with_no_repeated_seq(log, tmp_path, examined):
    import onetrace_console

    src = str(Path(onetrace_console.__file__).resolve().parents[1])
    n = 40
    cli = subprocess.Popen(
        [sys.executable, "-c", _WRITER, src, str(log.root), str(log.head_location), str(n)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    def server():
        for i in range(n // 2):
            log.append("console", "signout", f"s-{threading.get_ident()}-{i}", {"how": "idle"})

    threads = [threading.Thread(target=server) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    _out, err = cli.communicate(timeout=120)
    assert cli.returncode == 0, err.decode()
    entries = log.entries()
    seqs = [e["seq"] for e in entries]
    assert seqs == list(range(1, 2 * n + 1)), "one chain: every seq once, in order"
    assert {e["actor"] for e in entries} == {"cli", "console"}
    assert _failed(_verify(log.root, heads=log.head_location)) == set()
    examined(len(entries), "entries from two processes and two threads")


def test_a_writer_that_cannot_have_the_lock_within_the_wait_fails_the_append(log, examined):
    from onetrace_console.audit import AuditUnavailable, _file_lock

    log.lock_wait = 0.3
    with _file_lock(log.root / ".lock", 1.0):
        with pytest.raises(AuditUnavailable, match="held the audit log's lock for over 0.3 seconds"):
            log.append("cli", "token.created", "t", {})
    assert log.entries() == []
    log.append("cli", "token.created", "t", {})
    assert [e["seq"] for e in log.entries()] == [1]
    examined(2, "an append against a held lock, then one after")


# ------------------------------------------------------------------ export and checkpoint


@pytest.fixture
def configured(tmp_path, monkeypatch, second):
    from onetrace_console.config import ENV_VAR

    body = _body(tmp_path, audit={"enabled": True, "head_location": (second / "heads.jsonl").as_posix()})
    path = tmp_path / "config.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(path))
    return tmp_path / "data" / "audit_log", second / "heads.jsonl"


def test_audit_export_writes_sha256sums_over_every_file_and_the_verifier_passes_on_it_alone(
    configured, tmp_path, capsys, examined
):
    import hashlib

    from onetrace_console.__main__ import main as cli_main
    from onetrace_console.audit import AuditLog

    root, heads = configured
    _fill(AuditLog(root, head_location=heads, max_segment_bytes=600), 10)
    out = tmp_path / "export"
    assert cli_main(["audit", "export", str(out)]) == 0, capsys.readouterr().err
    files = sorted(p.name for p in out.iterdir())
    assert {"HEAD.json", "CHECKPOINT", "audit_verify.py", "heads.jsonl", "SHA256SUMS"} <= set(files)
    named = dict(
        reversed(line.split("  ", 1)) for line in (out / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    )
    assert sorted(named) == [f for f in files if f != "SHA256SUMS"], "every file, and only the export's"
    for name, want in named.items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == want, name
    assert not {"tokens", "accounts", "pages", "scim"} & set(files)
    alone = tmp_path / "elsewhere"
    alone.mkdir()
    ran = subprocess.run(
        [sys.executable, "-I", str(out / "audit_verify.py"), str(out)], cwd=alone, capture_output=True, text=True
    )
    assert ran.returncode == 0, ran.stdout + ran.stderr
    for check in ("segments", "chain", "HEAD.json", "checkpoint", "heads", "SHA256SUMS"):
        assert f"[PASS] {check} -- " in ran.stdout, ran.stdout
    exported = AuditLog(root, head_location=heads).entries()[-1]
    assert exported["event"] == "audit.exported" and exported["actor"] == "cli" and exported["detail"]["seq"] == 10
    examined(len(named), "files in the export, each summed; the verifier run alone on it")


def test_an_export_with_a_file_changed_after_fails_its_sums(configured, tmp_path, examined):
    from onetrace_console.__main__ import main as cli_main
    from onetrace_console.audit import AuditLog

    root, heads = configured
    _fill(AuditLog(root, head_location=heads), 3)
    out = tmp_path / "export"
    assert cli_main(["audit", "export", str(out)]) == 0
    (out / "extra.txt").write_text("x", encoding="utf-8")
    assert "SHA256SUMS" in _failed(_verify(out))
    examined(1, "an export with a file added")


def test_audit_checkpoint_prints_the_head_and_records_that_it_did(configured, capsys, examined):
    from onetrace_console.__main__ import main as cli_main
    from onetrace_console.audit import AuditLog

    root, heads = configured
    log = AuditLog(root, head_location=heads)
    _fill(log, 2)
    head = log.head()
    assert cli_main(["audit", "checkpoint"]) == 0
    assert f"checkpoint: {head['seq']}:{head['head']}" in capsys.readouterr().out
    last = log.entries()[-1]
    assert (last["event"], last["actor"], last["detail"]) == (
        "audit.checkpoint",
        "cli",
        {"seq": head["seq"], "head": head["head"]},
    )
    examined(1, "a checkpoint")


def test_the_verifier_says_a_line_nested_past_the_depth_as_not_an_entry(log, examined):
    from onetrace_console.audit_verify import MAX_DEPTH
    from onetrace_console.viewer.depth import MAX_JSON_DEPTH

    assert MAX_DEPTH <= MAX_JSON_DEPTH, "no deeper than the console's own reader"
    _fill(log, 2)
    seg = _segments(log)[-1]
    seg.write_bytes(seg.read_bytes() + b'{"a":' * 100_000 + b"1" + b"}" * 100_000 + b"\n")
    rows = _verify(log.root)
    assert "chain" in _failed(rows) and any("not JSON" in d for _o, c, d in rows if c == "chain"), rows
    examined(1, "a line nested 100000 deep")


def test_an_append_whose_head_location_cannot_be_written_writes_nothing(log, examined):
    from onetrace_console.audit import AuditUnavailable

    _fill(log, 2)
    before = (log.head(), [p.read_bytes() for p in _segments(log)])
    log.head_location.unlink()
    log.head_location.mkdir()
    with pytest.raises(AuditUnavailable, match="could not be written"):
        log.append("cli", "token.created", "t", {})
    assert (log.head(), [p.read_bytes() for p in _segments(log)]) == before, "no entry, no new head"
    examined(1, "an append with the second location unwritable")
