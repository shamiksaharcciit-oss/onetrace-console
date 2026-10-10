"""`onetrace_console.serve`: the HTTP surface the console's server needs, tested end to end.

Runs a real server, in a background thread, bound to an ephemeral port on 127.0.0.1, and
exercises it over real HTTP with `urllib` -- no mocking of the handler, because the entire
point of this module is the wiring between a request and the library calls underneath it, and
a mock would test the mock.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from onetrace_console.store import Store
from tests.conftest import make_tar


#: `server` moved to `tests/conftest.py`, shared with `test_upload_hardening.py`.


def _get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post(base: str, path: str, body: bytes = b"") -> tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=body, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_the_health_route_answers_without_touching_the_store(server, examined):
    base, _ = server
    status, body = _get(base, "/health")
    examined(1, "health check requests")
    assert status == 200
    assert body == b"ok\n"


def test_root_serves_the_home_page_rendered_at_startup(server, examined):
    base, _ = server
    status, body = _get(base, "/")
    examined(1, "root requests")
    assert status == 200
    assert b"<html" in body.lower() or b"<!doctype" in body.lower()


def test_an_unrendered_path_is_404_not_an_error(server, examined):
    base, _ = server
    status, _ = _get(base, "/no/such/page.html")
    examined(1, "requests for an unrendered path")
    assert status == 404


def test_a_path_that_escapes_the_pages_directory_is_refused(server, examined):
    """The GET handler resolves the path and checks containment -- checked here rather than
    trusted, since a directory-escape guard that never actually runs is exactly F15's shape."""
    base, store_root = server
    (store_root / "secret.txt").write_text("not for serving", encoding="utf-8")
    status, body = _get(base, "/../secret.txt")
    examined(1, "traversal attempts")
    assert status in (400, 404), (status, body)
    assert b"not for serving" not in body


def test_ingest_a_real_run_then_every_page_renders(server, files, examined):
    """Step 3's own checklist, over real HTTP: ingest, then every page."""
    base, store_root = server
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, body
    result = json.loads(body)
    examined(1, "runs ingested over HTTP")
    assert result["accepted"] is True
    assert result["check_verdict"] in ("holds", "contradicts", "could_not_check")

    for rel in ("/home.html", result["pages"]["answer"], result["pages"]["case"]):
        s, b = _get(base, rel)
        assert s == 200, (rel, s, b[:200])
        assert len(b) > 0

    # And on disk, under the one volume -- not only reachable over HTTP.
    assert (store_root / "pages" / "home.html").is_file()
    assert (store_root / "store" / "runs").is_dir()


def test_a_refused_delivery_ingests_nothing_and_says_so(server, examined):
    base, _ = server
    status, body = _post(base, "/v1/runs", b"not a tar file at all")
    examined(1, "malformed deliveries posted")
    assert status == 422, (status, body)
    result = json.loads(body)
    assert result["accepted"] is False


def _real_delivery(folder: Path) -> bytes:
    """The same packaging `tests/test_compare.py::_deliver` uses, for a real SDK run
    folder on disk -- not a hand-mutated copy, which broke the diff verb's own reading of
    it (a receipt chain has cross-references a naive run_id edit does not keep consistent).
    """
    import hashlib
    import io
    import tarfile

    manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    files = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        files[entry["file"]] = (folder / entry["file"]).read_bytes()
    files["SHA256SUMS"] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}" for p, b in files.items()) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    return buf.getvalue()


#: Its uploads are the exam's preview-format ingest-r1 runs, stored
#: directly (a new preview delivery is refused since 0.2.0): what the console does with runs it holds.
@pytest.mark.usefixtures("preview_stored_directly")
def test_compare_after_two_ingests_renders_the_diff_page(server, examined):
    """Real SDK bench runs -- the same `ingest-r1/run_C` / `run_C_poppler24` pair
    `test_compare.py` uses, fetched by `tools/fetch_sdk_fixtures.py` -- not a hand-mutated
    copy of the small r11 fixture, which is one internally-consistent record and does not
    stay consistent under a naive field edit.
    """
    exam = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
    run_c, run_c_poppler24 = exam / "run_C", exam / "run_C_poppler24"
    if not (run_c.is_dir() and run_c_poppler24.is_dir()):
        pytest.fail(f"the SDK's exam fixtures are not there under {exam}\n"
                   f"    python tools/fetch_sdk_fixtures.py")

    base, store_root = server
    s1, b1 = _post(base, "/v1/runs", _real_delivery(run_c))
    assert s1 == 200, b1
    run_a = json.loads(b1)
    s2, b2 = _post(base, "/v1/runs", _real_delivery(run_c_poppler24))
    assert s2 == 200, b2
    run_b = json.loads(b2)
    examined(2, "runs ingested for the comparison")

    s3, b3 = _post(base, f"/compare?a={run_a['run_key']}&b={run_b['run_key']}")
    assert s3 == 200, b3
    result = json.loads(b3)
    diff_rel = result["pages"]["diff"]
    s4, b4 = _get(base, diff_rel)
    assert s4 == 200, (diff_rel, s4, b4[:200])
    assert len(b4) > 0


def test_compare_with_an_unknown_run_key_is_a_400_not_a_500(server, examined):
    base, _ = server
    status, body = _post(base, "/compare?a=nope&b=alsonope")
    examined(1, "comparisons requested with unknown keys")
    assert status == 400, (status, body)


#: Its uploads are the exam's preview-format ingest-r1 runs, stored
#: directly (a new preview delivery is refused since 0.2.0): what the console does with runs it holds.
@pytest.mark.usefixtures("preview_stored_directly")
def test_a_restart_regenerates_every_page_from_the_store_alone(server, examined):
    """The operator README's own claim: `pages/` can always be regenerated from `store/`
    alone. NOT true of `_render_all_pages` on its own -- it never touches a run's detail
    pages or an existing comparison's Diff page, both rendered only at ingest/compare time
    -- which is why `_render_startup_pages` exists and this is what proves it does the job.
    """
    import shutil

    from onetrace_console.serve import _render_startup_pages

    exam = Path(__file__).resolve().parent.parent / ".sdk-fixtures" / "exam" / "fixtures" / "ingest-r1"
    run_c, run_c_poppler24 = exam / "run_C", exam / "run_C_poppler24"
    if not (run_c.is_dir() and run_c_poppler24.is_dir()):
        pytest.fail(f"the SDK's exam fixtures are not there under {exam}\n"
                   f"    python tools/fetch_sdk_fixtures.py")

    base, store_root = server
    _, b1 = _post(base, "/v1/runs", _real_delivery(run_c))
    a = json.loads(b1)
    _, b2 = _post(base, "/v1/runs", _real_delivery(run_c_poppler24))
    b = json.loads(b2)
    _, b3 = _post(base, f"/compare?a={a['run_key']}&b={b['run_key']}")
    diff_rel = json.loads(b3)["pages"]["diff"]

    before = sorted(p.relative_to(store_root / "pages").as_posix()
                    for p in (store_root / "pages").rglob("*.html"))
    examined(len(before), "pages present before the simulated restart")
    assert any("runs/" in p for p in before) and any("diff/" in p for p in before), before

    shutil.rmtree(store_root / "pages")
    assert not (store_root / "pages").exists()

    #: The store itself, opened fresh -- not the handler's live one -- the same way a real
    #: restart would open a Store over the volume's existing contents.
    from onetrace_console.store import Store
    reopened = Store(store_root / "store")
    _render_startup_pages(reopened, store_root)

    after = sorted(p.relative_to(store_root / "pages").as_posix()
                  for p in (store_root / "pages").rglob("*.html"))
    assert after == before, (
        f"regeneration did not reproduce the same pages\n  before: {before}\n  after: {after}")

    s, body = _get(base, diff_rel)
    assert s == 200 and len(body) > 0, (s, diff_rel)


# ------------------------------------------- main() with no config file: local mode

class _ReachedServerConstruction(Exception):
    """Raised by a stand-in server the moment `main()` constructs it, carrying the address."""


def _capture_server(monkeypatch):
    """Replace `ConsoleServer` with a stand-in that records the address `main()` binds
    and stops there -- past every refusal check, config load and store set-up, no socket."""
    import onetrace_console.serve as serve_module

    class _FakeServer:
        def __init__(self, address, handler):
            raise _ReachedServerConstruction(address)

    monkeypatch.setattr(serve_module, "ConsoleServer", _FakeServer)
    return serve_module


def test_a_named_config_file_is_the_explicit_flag_that_binds_elsewhere(tmp_path, monkeypatch,
                                                                     examined):
    """Beyond loopback only by naming a file that says so -- and with sign-in on it must also
    pass the existing plain-HTTP refusal, unchanged."""
    from onetrace_console.config import ENV_VAR
    config_path = tmp_path / "config.json"
    config_path.write_text(
        f'{{"host": "0.0.0.0", "port": 8081, "store_root": "{(tmp_path / "s").as_posix()}", '
        f'"sign_in": {{"enabled": false}}}}', encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    serve_module = _capture_server(monkeypatch)
    examined(1, "serve.main() with a config file naming every interface")
    with pytest.raises(_ReachedServerConstruction) as reached:
        serve_module.main([])
    assert reached.value.args[0] == ("0.0.0.0", 8081)


def test_main_still_starts_with_a_real_config_file_even_if_it_turns_sign_in_off(
        tmp_path, monkeypatch, examined):
    """The refusal is for "no file at all", never for a file that exists and
    makes its own explicit choice -- including explicitly turning sign-in
    off, which stays a warning, not a refusal. Proven without
    a real socket: `ConsoleServer` itself is replaced with a stand-in
    whose constructor raises a sentinel the moment `main()` reaches it -- past
    every refusal check, config load, and store/access-log setup.
    """
    from onetrace_console.config import ENV_VAR
    import onetrace_console.serve as serve_module

    class _ReachedServerConstruction(Exception):
        pass

    class _FakeServer:
        def __init__(self, *a, **kw):
            raise _ReachedServerConstruction()

    store_root = tmp_path / "store"
    config_path = tmp_path / "config.json"
    config_path.write_text(
        f'{{"host": "127.0.0.1", "port": 8080, "store_root": "{store_root.as_posix()}", '
        f'"sign_in": {{"enabled": false}}}}',
        encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(config_path))
    monkeypatch.setattr(serve_module, "ConsoleServer", _FakeServer)

    examined(1, "serve.main() with a real config file that itself disables sign-in")
    with pytest.raises(_ReachedServerConstruction):
        serve_module.main([])
