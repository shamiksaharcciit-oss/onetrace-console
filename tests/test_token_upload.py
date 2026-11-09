"""A tokenizer picked on a model step's page, kept by a local console (`token_upload`): checked against the
record's `tokenizer.digest` before anything is kept; kept in a folder named by that digest; listed in
Settings with Remove; and its limits -- a local console only, at most 100 MB, a zip's members each
checked, no network.

The tokenizer is test data built here (`tests/test_token_text.py`'s word-level `tokenizer.json`), its
digest reproduced with onetrace's own `manifest_digest`, never typed. Where the `tokenizers` package is
not installed (it comes with the console's [neighbours] extra), a kept tokenizer is still chosen for a
record whose digest it matches, and the page says the package is missing, as for a configured one.
"""
from __future__ import annotations

import http.client
import io
import json
import re
import socket
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from tests.http_limits import limit

TOKENIZER = json.dumps({"version": "1.0", "model": {"type": "WordLevel", "unk_token": "[UNK]",
                        "vocab": {"[UNK]": 0, "the": 1, "cat": 2}}, "pre_tokenizer": {"type": "Whitespace"},
                        "normalizer": None, "post_processor": None, "decoder": None, "added_tokens": [],
                        "padding": None, "truncation": None}).encode("utf-8")
NOTE = b"written for this test\n"


def _digest(files: dict[str, bytes]) -> str:
    from tests.test_token_text import _digest as d
    return d(files)


def _zip(members: dict[str, bytes], *, link: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
        if link is not None:
            info = zipfile.ZipInfo(link)
            info.external_attr = (0o120777 << 16)
            z.writestr(info, "tokenizer.json")
    return buf.getvalue()


@pytest.fixture
def store_dir(tmp_path) -> Path:
    d = tmp_path / "store"
    d.mkdir()
    return d


def test_a_tokenizer_json_that_hashes_to_the_digest_is_kept_in_its_digest_s_folder(store_dir, examined):
    from onetrace_console import token_upload
    want = _digest({"tokenizer.json": TOKENIZER})
    entry = token_upload.keep(store_dir, want, TOKENIZER, "tokenizer.json")
    examined(1, "tokenizer kept")
    folder = store_dir / "tokenizers" / want.split(":", 1)[1]
    assert entry["digest"] == want and entry["files"] == ["tokenizer.json"] and entry["bytes"] == len(TOKENIZER)
    assert (folder / "tokenizer.json").read_bytes() == TOKENIZER
    assert json.loads((folder / "kept.json").read_text(encoding="utf-8"))["digest"] == want
    assert token_upload.named(store_dir) == ((str(folder), ("tokenizer.json",)),)


def test_a_zip_of_the_tokenizer_s_files_is_kept_by_its_members_names(store_dir, examined):
    from onetrace_console import token_upload
    files = {"tokenizer.json": TOKENIZER, "note.txt": NOTE}
    want = _digest(files)
    entry = token_upload.keep(store_dir, want, _zip({"my-model/tokenizer.json": TOKENIZER, "my-model/note.txt": NOTE}),
                              "my-model.zip")
    examined(2, "zip members kept")
    assert entry["files"] == ["note.txt", "tokenizer.json"] and entry["picked"] == "my-model.zip"


def test_files_that_hash_to_another_digest_are_refused_and_nothing_is_kept(store_dir, examined):
    from onetrace_console import token_upload
    want = _digest({"tokenizer.json": TOKENIZER, "note.txt": NOTE})
    examined(1, "a tokenizer for another record")
    with pytest.raises(token_upload.UploadError) as e:
        token_upload.keep(store_dir, want, TOKENIZER, "tokenizer.json")
    assert want in str(e.value) and _digest({"tokenizer.json": TOKENIZER}) in str(e.value)
    assert not (store_dir / "tokenizers").exists() or not any((store_dir / "tokenizers").iterdir())


ZIPS = {
    "an absolute member": lambda: _zip({"/etc/tokenizer.json": TOKENIZER}),
    "a member that climbs out": lambda: _zip({"../tokenizer.json": TOKENIZER}),
    "a link": lambda: _zip({"note.txt": NOTE}, link="tokenizer.json"),
    "two members of one name": lambda: _zip({"a/tokenizer.json": TOKENIZER, "b/tokenizer.json": TOKENIZER}),
    "a member named otherwise": lambda: _zip({"tok enizer.json": TOKENIZER}),
    "too many members": lambda: _zip({f"f{i}.txt": NOTE for i in range(65)}),
    "no tokenizer.json": lambda: _zip({"note.txt": NOTE}),
}


@pytest.mark.parametrize("what", sorted(ZIPS))
def test_a_zip_s_members_are_each_checked_before_anything_is_kept(what, store_dir, examined):
    from onetrace_console import token_upload
    data = ZIPS[what]()
    try:
        files = token_upload.files_of(data, "t.zip")
        want = token_upload.digest_of(files)
    except token_upload.UploadError:
        want = _digest({"tokenizer.json": TOKENIZER})
    examined(1, f"zip with {what}")
    with pytest.raises(token_upload.UploadError):
        token_upload.keep(store_dir, want, data, "t.zip")
    assert not (store_dir / "tokenizers").exists() or not any((store_dir / "tokenizers").iterdir())


@pytest.mark.parametrize("what", ["the upload", "a member", "the members together"])
def test_the_size_limits_refuse_before_anything_is_kept(what, store_dir, monkeypatch, examined):
    from onetrace_console import token_text, token_upload
    data = _zip({"tokenizer.json": TOKENIZER, "note.txt": NOTE})
    if what == "the upload":
        monkeypatch.setattr(token_upload, "MOST_UPLOAD", len(data) - 1)
    elif what == "a member":
        monkeypatch.setattr(token_text, "MOST_BYTES", len(NOTE) - 1)
    else:
        monkeypatch.setattr(token_upload, "MOST_UPLOAD", len(data) + 1)
        data = _zip({"tokenizer.json": TOKENIZER, "a.txt": NOTE * 2000, "b.txt": NOTE * 2000})
        monkeypatch.setattr(token_upload, "MOST_UPLOAD", len(TOKENIZER) + len(NOTE) * 2000 + 10)
    examined(1, f"limit on {what}")
    with pytest.raises(token_upload.UploadError):
        token_upload.keep(store_dir, _digest({"tokenizer.json": TOKENIZER, "note.txt": NOTE}), data, "t.zip")
    assert token_upload.MOST_UPLOAD <= 100 * 1024 * 1024


def test_a_file_that_is_neither_a_zip_nor_tokenizer_json_is_refused(store_dir, examined):
    from onetrace_console import token_upload
    examined(1, "another file")
    with pytest.raises(token_upload.UploadError):
        token_upload.keep(store_dir, _digest({"vocab.txt": TOKENIZER}), TOKENIZER, "vocab.txt")


def test_keeping_reaches_no_network(store_dir, monkeypatch, examined):
    from onetrace_console import token_upload

    def no(*a, **k):
        raise AssertionError("a socket was opened")
    monkeypatch.setattr(socket, "socket", no)
    monkeypatch.setattr(socket, "create_connection", no)
    examined(1, "keeping with no network")
    token_upload.keep(store_dir, _digest({"tokenizer.json": TOKENIZER}), TOKENIZER, "tokenizer.json")


def test_remove_takes_the_kept_tokenizer_away_and_settings_says_so(store_dir, examined):
    from onetrace_console import settings_menu, token_upload

    class S:
        root = store_dir
    want = _digest({"tokenizer.json": TOKENIZER})
    examined(3, "settings rows")
    assert settings_menu.tokenizers_row(S).words == "Tokenizers: none kept"
    token_upload.keep(store_dir, want, TOKENIZER, "tokenizer.json")
    row = settings_menu.tokenizers_row(S)
    assert (row.words, row.href) == ("Tokenizers: 1 kept", "/model-tokenizers")
    page = token_upload.settings_page(store_dir)
    assert want in page and f'data-tokenizer-remove="/model-tokenizers/remove?digest={want}"' in page
    assert token_upload.remove(store_dir, want) and token_upload.kept(store_dir) == []
    assert settings_menu.tokenizers_row(S).words == "Tokenizers: none kept"


def test_a_step_page_offers_the_picker_on_a_local_console_only_and_a_kept_one_is_then_chosen(store_dir, examined):
    from onetrace_console import token_text, token_upload
    from onetrace_console.export_static import without_run_tools
    from tests.test_token_text import step_page
    want = _digest({"tokenizer.json": TOKENIZER})
    local, public = step_page(want), step_page(want, public=True)
    examined(3, "step pages")
    assert f'data-tokenizer-post="/model-tokenizers?digest={want}"' in local
    assert "data-tokenizer-pick" not in public and "data-tokenizer-pick" not in without_run_tools(local)
    assert "data-tokenizer-pick" not in step_page(None)
    token_upload.keep(store_dir, want, TOKENIZER, "tokenizer.json")
    after = step_page(want, token_upload.named(store_dir))
    folder = str(store_dir / "tokenizers" / want.split(":", 1)[1])
    try:
        import tokenizers  # noqa: F401
        assert "decoded with tokenizer" in after and folder in after
    except ImportError:
        assert token_text.NO_PACKAGE.split(" (")[0] in after and folder in after


def test_the_policy_names_the_script_on_a_local_console_only(examined):
    from onetrace_console.public import _script_hash, content_security_policy
    from onetrace_console.token_script import TOKEN_SCRIPT
    examined(2, "policies")
    assert _script_hash(TOKEN_SCRIPT) in content_security_policy(local=True)
    assert _script_hash(TOKEN_SCRIPT) not in content_security_policy()


def test_the_routes_on_a_local_console_keep_list_remove_and_refuse_over_100_mb_unread(tmp_path, examined):
    from tests.test_folder_load import _Console, _free_port
    root = tmp_path / "console"
    (root / "store").mkdir(parents=True)
    port = _free_port()
    config = tmp_path / "local.json"
    config.write_text(json.dumps({"host": "127.0.0.1", "port": port, "store_root": str(root),
                                  "sign_in": {"enabled": False}}), encoding="utf-8")
    base = f"http://127.0.0.1:{port}"
    want = _digest({"tokenizer.json": TOKENIZER})

    def post(path: str, body: bytes = b"") -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}{path}", data=body, method="POST",
                                     headers={"Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(req, timeout=limit(120)) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def over() -> int:
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=limit(60))
        c.putrequest("POST", f"/model-tokenizers?digest={want}&name=tokenizer.json")
        c.putheader("Content-Length", str(100 * 1024 * 1024 + 1))
        c.endheaders()
        status = c.getresponse().status
        c.close()
        return status
    con = _Console(tmp_path, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        con.until("onetrace-console serving on")
        big = over()
        other = post(f"/model-tokenizers?digest={_digest({'tokenizer.json': NOTE})}&name=tokenizer.json", TOKENIZER)
        kept = post(f"/model-tokenizers?digest={want}&name=tokenizer.json", TOKENIZER)
        with urllib.request.urlopen(f"{base}/model-tokenizers", timeout=limit(60)) as r:
            listed = r.read().decode("utf-8")
        removed = post(f"/model-tokenizers/remove?digest={want}")
        again = post(f"/model-tokenizers/remove?digest={want}")
    finally:
        con.stop()
    examined(5, "presses")
    assert big == 413
    assert other[0] == 400 and "nothing was kept" in other[1]["error"]
    assert kept == (200, {"digest": want, "files": ["tokenizer.json"], "removed": False}), kept
    assert want in listed and "data-tokenizer-remove" in listed
    assert removed == (200, {"digest": want, "files": [], "removed": True}) and again[0] == 400


def test_sabotage_a_keep_that_writes_before_it_checks_is_named(store_dir, monkeypatch, examined):
    from onetrace_console import token_upload
    real = token_upload.digest_of
    monkeypatch.setattr(token_upload, "digest_of", lambda files: (
        (store_dir / "tokenizers" / "written-before").mkdir(parents=True, exist_ok=True), real(files))[1])
    examined(1, "a keep that writes first")
    with pytest.raises(AssertionError):
        test_files_that_hash_to_another_digest_are_refused_and_nothing_is_kept(store_dir, lambda *a: None)
