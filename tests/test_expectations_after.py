"""Expectations declared after the run (onetrace's manual, 16.22): an `onetrace-expectations/1` file the
person names on a local console's run page. The console checks the run against it with onetrace-verify
(`--expectations`), keeps the verifier's rows in its own store, never in the record, and shows them
apart from the run's own expectations, labelled "declared after the run".

The run is `tests/onetrace_runs/0.7.1/expect/calibrate-holds`, and the file `after-the-run.json` beside
it, written by onetrace's own `onetrace expect write`: three entries, one that holds, one that fails,
and one about a step the run does not record.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.http_limits import limit
from tests.test_format_04 import RAN_AT, _tar

EXPECT = Path(__file__).resolve().parent / "onetrace_runs" / "0.7.1" / "expect"
FILE = EXPECT / "after-the-run.json"
SEAL = json.loads(FILE.read_text(encoding="utf-8"))["seal"]


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed
    _require_installed()


def _text(block: str) -> str:
    inline = re.sub(r"</?(?:span|code|strong|a|time)\b[^>]*>", "", block)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inline))).strip()


def _stored(store, name: str = "calibrate-holds"):
    from onetrace_console.checks import run_and_record
    from onetrace_console.ingest import accept
    return run_and_record(accept(_tar(EXPECT / name), store).run, store, ran_at=RAN_AT)


def _sections(run, store) -> dict[str, str]:
    from onetrace_console.pages import render_execution
    pages = render_execution(store.get_run(run.key), store, generated_at="2026-10-04T12:00:00+00:00").pages
    out = {}
    for name in ("expectations", "expectations-after"):
        found = [m.group(0) for p in ("case.html", "proof.html")
                 for m in [re.search(rf'<section data-section="{name}".*?</section>', pages[p], re.S)] if m]
        out[name] = found[0] if found else ""
    return out


def test_a_run_checked_against_a_named_file_keeps_the_verifier_s_rows_in_the_store_not_the_record(store, examined):
    from onetrace_console import expectations_after
    run = _stored(store)
    before = [(p, store.get(k)) for p, k in store.get_run(run.key).listing]
    entry = expectations_after.check(store, run, str(FILE))
    examined(len(entry["rows"]), "rows kept")
    assert [(r["name"].split(" (")[0], r["result"]) for r in entry["rows"]] == [
        ("expectations file", "PASS"), ("expect calibrate.after-under-450", "PASS"),
        ("expect calibrate.after-serial", "FAIL"), ("expect missing.after-missing-step", "FAIL")]
    assert all(f"(declared after the run, {SEAL})" in r["name"] for r in entry["rows"][1:])
    assert entry["seal"] == SEAL and entry["file"] == FILE.name
    assert entry["file_sha256"] == hashlib.sha256(FILE.read_bytes()).hexdigest()
    assert expectations_after.kept(store, run.key) == entry
    assert [(p, store.get(k)) for p, k in store.get_run(run.key).listing] == before
    assert store.get_run(run.key).check_verdict == run.check_verdict


def test_the_rows_are_shown_apart_and_labelled_declared_after_the_run(store, examined):
    from onetrace_console import expectations_after
    run = _stored(store)
    expectations_after.check(store, run, str(FILE))
    secs = _sections(run, store)
    examined(2, "sections")
    own, after = _text(secs["expectations"]), _text(secs["expectations-after"])
    assert "declared after the run" not in own and "after-under-450" not in own
    assert after.startswith("Expectations declared after the run Declared after the run."), after
    assert f"Checked against {FILE.name}, its seal {SEAL}," in after
    assert "1 of 3 expectations held." in after
    assert expectations_after.SAYS_NOTHING in after
    assert f"FAIL expect missing.after-missing-step (declared after the run, {SEAL}) — the run records no step 'missing'" in after
    assert re.findall(r'<p data-expectations="count">(.*?)</p>', secs["expectations"]) == ["4 of 5 expectations held."]


@pytest.mark.parametrize("why", ["relative", "missing", "too large", "not json", "another format", "a 0.3 run"])
def test_a_file_it_does_not_read_is_refused_in_words_and_nothing_is_kept(why, store, tmp_path, monkeypatch, examined):
    from onetrace_console import expectations_after
    run = _stored(store)
    named = str(FILE)
    if why == "relative":
        named = "after-the-run.json"
    elif why == "missing":
        named = str(tmp_path / "nothing-here.json")
    elif why == "too large":
        monkeypatch.setattr(expectations_after, "MAX_BYTES", 10)
    elif why == "not json":
        (tmp_path / "x.json").write_text("not json", encoding="utf-8")
        named = str(tmp_path / "x.json")
    elif why == "another format":
        (tmp_path / "x.json").write_text(json.dumps({"format": "onetrace-reference/1"}), encoding="utf-8")
        named = str(tmp_path / "x.json")
    elif why == "a 0.3 run":
        from onetrace_console.checks import run_and_record
        from onetrace_console.ingest import accept
        run = run_and_record(accept(_tar(EXPECT.parent.parent / "0.6.1" / "refund-closed"), store).run, store,
                             ran_at=RAN_AT)
    examined(1, f"a file refused: {why}")
    with pytest.raises(expectations_after.ExpectationsError) as e:
        expectations_after.check(store, run, named)
    assert str(e.value)
    assert expectations_after.kept(store, run.key) is None


def test_a_public_page_has_no_press_and_an_export_keeps_what_was_kept_read_only(store, examined):
    from onetrace_console import expectations_after
    from onetrace_console.export_static import without_run_tools
    from onetrace_console.public import content_security_policy, _script_hash
    from onetrace_console.expectations_script import EXPECTATIONS_SCRIPT
    run = _stored(store)
    examined(4, "pages and policies")
    assert expectations_after.section(run, store, public=True) == ""
    local = expectations_after.section(run, store, public=False)
    assert "data-expectations-after-post" in local and without_run_tools(local) == ""
    expectations_after.check(store, run, str(FILE))
    kept = without_run_tools(expectations_after.section(run, store, public=False))
    assert 'data-expectations-after="rows"' in kept and "data-expectations-after-post" not in kept
    assert EXPECTATIONS_SCRIPT not in kept
    assert _script_hash(EXPECTATIONS_SCRIPT) in content_security_policy(local=True)
    assert _script_hash(EXPECTATIONS_SCRIPT) not in content_security_policy()


def test_the_press_on_a_local_console_checks_keeps_and_draws_the_page_again(tmp_path, examined):
    from onetrace_console.store import Store
    from tests.test_folder_load import _Console, _free_port
    root = tmp_path / "console"
    store = Store(root / "store")
    run = _stored(store)
    port = _free_port()
    config = tmp_path / "local.json"
    config.write_text(json.dumps({"host": "127.0.0.1", "port": port, "store_root": str(root),
                                  "sign_in": {"enabled": False}}), encoding="utf-8")
    base = f"http://127.0.0.1:{port}"

    def post(query: str, body: bytes) -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}/expectations?{query}", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=limit(300)) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())
    c = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        refused = [post("run=nope", b'{"path": "/x"}'), post(f"run={run.key}", b"[1]"),
                   post(f"run={run.key}", json.dumps({"path": "relative.json"}).encode())]
        done = post(f"run={run.key}", json.dumps({"path": str(FILE)}).encode())
        with urllib.request.urlopen(f"{base}/runs/{run.key}/case.html", timeout=limit(60)) as r:
            page = r.read().decode("utf-8")
    finally:
        c.stop()
    examined(4, "presses")
    assert [s for s, _ in refused] == [400, 400, 400], refused
    assert "whole path" in refused[2][1]["error"]
    assert done == (200, {"run_key": run.key, "file": FILE.name, "seal": SEAL, "rows": 4}), done
    sec = re.search(r'<section data-section="expectations-after".*?</section>', page, re.S).group(0)
    assert "Declared after the run." in _text(sec) and "data-expectations-after-post" in sec


def test_sabotage_rows_shown_without_their_label_are_named(store, monkeypatch, examined):
    from onetrace_console import expectations_after
    run = _stored(store)
    expectations_after.check(store, run, str(FILE))
    monkeypatch.setattr(expectations_after, "LABEL", "checked")
    examined(1, "a section without its label")
    after = _text(_sections(run, store)["expectations-after"])
    assert "Declared after the run." not in after
