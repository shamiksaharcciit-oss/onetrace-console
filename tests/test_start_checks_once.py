"""A public console checks its build record once at start, before its first answer.

The start read the record twice, both before listening: the start's refusal (`public.start_refusal`, which refuses a
store that is not the one its builder recorded) and the example inputs' allowance (`demo_store.serve_examples`), each
hashing every file the record covers (5,206 for the demo). The allowance now takes the start's own check, which has
just passed, so the record is read once; a store that is not as built is still refused before anything is served
(`tests/test_public_mode.py` holds that). Each covered file's path is read once, as a string under the folder.
"""

from __future__ import annotations

import json
from pathlib import Path


def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start(shared_demo, tmp_path, monkeypatch) -> tuple[int, list[Path]]:
    """`serve.main` on the shared demo, as the image starts it, stopped where it would listen; and each folder whose
    record was checked."""
    from onetrace_console import demo_store, serve
    from onetrace_console.config import ENV_VAR

    built = shared_demo["folder"]
    config = json.loads((Path(__file__).resolve().parent.parent / "deploy" / "fly" / "public.json").read_text())
    config.update(
        host="127.0.0.1",
        port=_free_port(),
        store_root=str(built / "store"),
        trust_file=str(built / "trust.json"),
        compare_cache=str(tmp_path / "compared"),
    )
    (tmp_path / "compared").mkdir()
    (tmp_path / "public.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv(ENV_VAR, str(tmp_path / "public.json"))
    real, checked = demo_store.check_build_record, []

    def counted(folder, only=None):
        checked.append(Path(folder))
        return real(folder, only=only)

    monkeypatch.setattr(demo_store, "check_build_record", counted)

    def listened(self):
        raise KeyboardInterrupt

    monkeypatch.setattr(serve.ConsoleServer, "serve_forever", listened)
    return serve.main([]), checked


def test_the_start_checks_the_build_record_once_and_the_examples_stay_allowed(
    shared_demo, tmp_path, monkeypatch, examined
):
    from onetrace_console import kept_inputs

    before = kept_inputs.set_examples(())
    try:
        code, checked = _start(shared_demo, tmp_path, monkeypatch)
        allowed = kept_inputs.set_examples(before)
    finally:
        kept_inputs.set_examples(before)
    examined(len(checked), "build-record checks at start")
    assert code == 0
    assert checked == [shared_demo["folder"]], checked
    #: The examples are still the ones the record vouches for.
    from onetrace_console.demo_store import example_digests_for

    assert allowed and allowed == example_digests_for(shared_demo["folder"])


def test_each_covered_path_is_read_as_a_string_under_the_folder(tmp_path, examined):
    from onetrace_console import demo_store

    (tmp_path / "runs" / "a").mkdir(parents=True)
    (tmp_path / "runs" / "a" / "x.json").write_text("{}")
    (tmp_path / "trust.json").write_text("{}")
    got = demo_store._covered(tmp_path, ("runs", "trust.json"))
    examined(len(got), "covered files")
    assert got == {"runs/a/x.json": tmp_path / "runs" / "a" / "x.json", "trust.json": tmp_path / "trust.json"}
