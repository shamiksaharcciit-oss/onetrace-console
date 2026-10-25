r"""A path in a message is shown as written: a Windows path's backslashes single, never doubled.

Python's own words for an `OSError` quote its file name with `repr`, so `C:\data\x.json` reads
`'C:\\data\\x.json'` there. A message that quoted the error whole showed every backslash of a
Windows path doubled (as the watched-folder line once did). Each place below quotes an error's
reason and its path as written, through `oserror.said`. The doubling is repr's on every platform,
so these hold on Linux as well as Windows.
"""
from __future__ import annotations

import errno
from pathlib import Path

import pytest

WIN = r"C:\Users\operator\store\runs\run.json"
DOUBLED = WIN.replace("\\", "\\\\")


def _as_written(text: str) -> list[str]:
    """What is wrong with how `text` shows WIN."""
    out = []
    if WIN not in text:
        out.append(f"the path as written is not there: {text!r}")
    if DOUBLED in text:
        out.append(f"the path is shown with its backslashes doubled: {text!r}")
    return out


def _denied() -> OSError:
    return PermissionError(errno.EACCES, "Permission denied", WIN)


def test_the_helper_says_the_reason_and_the_paths_as_written(examined):
    from onetrace_console.oserror import said
    examined(3, "errors")
    assert said(_denied()) == f"Permission denied: {WIN}"
    assert said(OSError(errno.EXDEV, "Invalid cross-device link", WIN, None, WIN + "2")) == (
        f"Invalid cross-device link: {WIN} -> {WIN}2")
    assert said(OSError("no errno at all")) == "no errno at all"


def test_sabotage_python_s_own_words_are_named():
    """The check above, against `str(e)`: it must fail."""
    assert _as_written(str(_denied())), "repr does not double the backslashes here"


def test_a_stored_record_the_store_cannot_read_is_said_by_its_reason_alone(examined):
    """The record is named by its file name beside the reason; a page never shows the server's own
    path to it."""
    from onetrace_console.store import _why
    examined(1, "store reason")
    assert _why(_denied()) == "PermissionError: Permission denied"


def test_a_run_folder_that_cannot_be_read_names_its_path_as_written(tmp_path, monkeypatch, examined):
    import onetrace_console.folder_load as folder_load
    from onetrace_console.config import Config
    from onetrace_console.store import Store

    def denied(run_dir):
        raise _denied()
    monkeypatch.setattr(folder_load, "delivery", denied)
    got = folder_load.deliver_one(tmp_path / "run", Store(tmp_path / "store"), Config())
    examined(1, "refused folder")
    assert got.run is None and _as_written(got.refused) == []


@pytest.mark.parametrize("fails", ["append", "head"])
def test_an_access_log_that_cannot_be_written_names_its_path_as_written(tmp_path, monkeypatch, fails,
                                                                       examined):
    import onetrace_console.access_log as access_log
    log = access_log.AccessLog(tmp_path / "access_log", max_segment_bytes=1 << 20)
    if fails == "append":
        monkeypatch.setattr(access_log, "open", lambda *a, **k: (_ for _ in ()).throw(_denied()),
                            raising=False)
    else:
        monkeypatch.setattr(log, "_write_head", lambda: (_ for _ in ()).throw(_denied()))
    examined(1, f"access log {fails}")
    with pytest.raises(access_log.AccessLogExhausted) as e:
        log.append(principal="p", method="GET", path="/home.html", status=200)
    assert _as_written(str(e.value)) == []


def test_the_viewers_fingerprint_check_names_an_unreadable_page_as_written(tmp_path, monkeypatch, capsys,
                                                                           examined):
    from onetrace_console.viewer.__main__ import main
    page = tmp_path / "page.html"
    page.write_text("x", encoding="utf-8")
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(_denied()))
    examined(1, "fingerprint check")
    main(["fingerprint", str(page)])
    assert _as_written(capsys.readouterr().out) == []


def test_the_viewer_names_a_file_it_cannot_write_as_written(tmp_path, monkeypatch, capsys, examined):
    import onetrace_console.viewer.__main__ as viewer_main
    monkeypatch.setattr(viewer_main, "_write_views",
                        lambda *a, **k: (_ for _ in ()).throw(_denied()))
    examined(1, "render")
    assert viewer_main.main(["render", str(tmp_path / "run"), "--out", str(tmp_path / "out")]) == 2
    assert _as_written(capsys.readouterr().err) == []


# ------------------------------------------------------------------ nowhere else, statically

SRC = Path(__file__).resolve().parent.parent / "src" / "onetrace_console"
#: OSError and the subclasses a handler here names.
_OS_ERRORS = {"OSError", "PermissionError", "FileNotFoundError", "IsADirectoryError",
              "NotADirectoryError", "FileExistsError", "SSLError"}
#: (file relative to src/onetrace_console/, line) -> why the error is quoted whole there.
ALLOWED: dict[tuple[str, int], str] = {
    ("serve.py", 1501): "the TLS files: `load_cert_chain` raises with no file name, and an "
                        "SSLError's own words are the only reason it gives",
    ("serve.py", 1422): "the store at start: quoted whole only where the error has no reason of "
                        "the system's (the ValueError, KeyError or TypeError it also catches); "
                        "an OSError's reason and file name are quoted apart, as written",
}


def _bare_errors(tree) -> list[int]:
    """Lines where an f-string quotes, whole, the error an `except ...OSError... as e` caught."""
    import ast
    out = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ExceptHandler) and node.name and node.type is not None):
            continue
        types = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        names = {t.attr if isinstance(t, ast.Attribute) else getattr(t, "id", "") for t in types}
        if not names & _OS_ERRORS:
            continue
        for inner in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if (isinstance(inner, ast.FormattedValue) and isinstance(inner.value, ast.Name)
                    and inner.value.id == node.name):
                out.append(inner.value.lineno)
    return out


def bare_problems(sources: dict[str, str]) -> list[str]:
    import ast
    found = {(rel, line) for rel, text in sources.items() for line in _bare_errors(ast.parse(text))}
    return ([f"{rel}:{line} quotes an OSError whole" for rel, line in sorted(found - set(ALLOWED))]
            + [f"allowance {a} outlived its line" for a in sorted(set(ALLOWED) - found)])


def _sources() -> dict[str, str]:
    return {p.relative_to(SRC).as_posix(): p.read_text(encoding="utf-8") for p in sorted(SRC.rglob("*.py"))}


def test_no_message_quotes_an_oserror_whole(examined):
    sources = _sources()
    examined(len(sources), "source files")
    assert bare_problems(sources) == []


def test_sabotage_an_oserror_quoted_whole_is_named(examined):
    sources = _sources()
    examined(1, "planted handler")
    sources["planted.py"] = 'try:\n    pass\nexcept OSError as e:\n    print(f"cannot: {e}")\n'
    assert "planted.py:4 quotes an OSError whole" in bare_problems(sources)


# ------------------------------------------------------------------ as written, and still escaped

#: A path with an escape character and a right-to-left override in it: "as written" keeps its
#: text, never its raw controls. Built with chr(), so no raw control is in this file.
ESC, RLO = chr(0x1B), chr(0x202E)
HOSTILE = "C:\\Users\\op" + ESC + "[31m" + RLO + "evil\\run.json"
#: The same path as the console shows text that is not a record's words: each control as \uXXXX,
#: its backslashes single (`words.path_text`, without the HTML).
HOSTILE_SHOWN = "C:\\Users\\op" + "\\u001b" + "[31m" + "\\u202e" + "evil\\run.json"


def _hostile() -> OSError:
    return PermissionError(errno.EACCES, "Permission denied", HOSTILE)


def shown_problems(text: str) -> list[str]:
    """What is wrong with how a log line or a plain-text answer shows HOSTILE."""
    out = []
    if ESC in text or RLO in text:
        out.append(f"a raw control reaches it: {text!r}")
    if HOSTILE_SHOWN not in text:
        out.append(f"the path is not shown as written and escaped: {text!r}")
    return out


def test_shown_escapes_controls_and_keeps_backslashes(examined):
    from onetrace_console.oserror import said, shown
    examined(1, "hostile path")
    assert shown_problems(shown(said(_hostile()))) == []
    assert shown_problems(said(_hostile())), "said alone leaves the text unchanged"


def test_a_page_naming_a_record_the_store_cannot_read_shows_no_path_of_the_servers(tmp_path, monkeypatch,
                                                                                 examined):
    """Home names a run record it cannot read by its file name and the reason; never the server's
    own path to it, and so nothing of a hostile one."""
    from onetrace_console.render import HOME, render_all
    from onetrace_console.store import Store
    store = Store(tmp_path / "store")
    record = store.root / "runs" / f"{'ab' * 32}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("{}", encoding="utf-8")
    real = Path.read_bytes
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: (_ for _ in ()).throw(_hostile()) if self == record else real(self))
    home = render_all(store, generated_at="2026-10-14T12:00:00+00:00")[HOME]
    examined(1, "Home with an unreadable record")
    assert f"{'ab' * 32}.json: PermissionError: Permission denied" in home
    assert ESC not in home and RLO not in home
    assert "evil" not in home and "C:\\" not in home, "the server's path is not on a page"


def test_a_log_line_naming_a_refused_run_folder_shows_the_path_escaped(tmp_path, monkeypatch, capsys,
                                                                      examined):
    import onetrace_console.folder_load as folder_load
    from onetrace_console.config import Config
    from onetrace_console.store import Store
    monkeypatch.setattr(folder_load, "delivery", lambda run_dir: (_ for _ in ()).throw(_hostile()))
    watching = folder_load._Watching(tmp_path, None, 0)
    watching.store, watching.config = Store(tmp_path / "store"), Config()
    examined(1, "watcher log line")
    assert watching._intake(tmp_path / "run") is False
    assert shown_problems(capsys.readouterr().err) == []


def test_the_access_logs_plain_text_refusal_shows_the_path_escaped(server, examined):
    from onetrace_console.access_log import AccessLogExhausted
    from onetrace_console.oserror import said
    from onetrace_console.serve import Handler
    from tests.test_serve import _get
    base, _ = server

    def exhausted(**kw):
        raise AccessLogExhausted(f"cannot append to the access log: {said(_hostile())}")
    Handler.access_log.append = exhausted
    status, body = _get(base, "/home.html")
    examined(1, "plain-text refusal")
    assert status == 500
    assert shown_problems(body.decode("utf-8")) == []


def test_the_viewers_own_output_shows_the_path_escaped(tmp_path, monkeypatch, capsys, examined):
    import onetrace_console.viewer.__main__ as viewer_main
    monkeypatch.setattr(viewer_main, "_write_views",
                        lambda *a, **k: (_ for _ in ()).throw(_hostile()))
    examined(1, "viewer output")
    assert viewer_main.main(["render", str(tmp_path / "run"), "--out", str(tmp_path / "out")]) == 2
    assert shown_problems(capsys.readouterr().err) == []
