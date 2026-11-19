"""A forwarding value holding a control character is refused when it is read, and goes nowhere.

A header's value read with its line break (a key pasted with its trailing newline, or a variable holding one) made
`http.client` raise, with the value in its message, and the test press's traceback put it on standard error. A value
holding a control character is now refused as it is read, naming the destination and the header, never the value; and
a send that cannot be made is a failed send, said by its kind alone. Read through the console's own setup page.
"""

from __future__ import annotations

from pathlib import Path

from onetrace_console import forwarding as F
from tests.test_forwarding_setup import P, _post, audited  # noqa: F401 - the fixture, requested by name

PLANT = "PLANTED-forward-value-7c1d"


def test_a_value_with_a_newline_is_refused_by_name_and_reaches_no_stream_page_log_or_file(
    audited, monkeypatch, capfd, examined
):  # noqa: F811
    base, root, log = audited
    monkeypatch.setenv("ONETRACE_FORWARD_NEWLINE", "abc\n" + PLANT)
    status, page = _post(
        base + P.PATH,
        {
            "action": "add",
            "name": "with-a-newline",
            "endpoint": "https://127.0.0.1:9",
            "encoding": "json",
            "runs": "all",
            "header": "x-api-key",
            "where": "env",
            "key_env": "ONETRACE_FORWARD_NEWLINE",
        },
    )
    assert status == 200, page[-500:]
    (dest,) = [d for d in F.read(root) if d.name == "with-a-newline"]
    capfd.readouterr()
    status, page = _post(base + P.PATH, {"action": "test", "id": dest.id})
    err = capfd.readouterr()
    examined(4, "places the value could reach")
    #: Answered, as a failed test, naming the destination and the header and why.
    assert status == 200, page[-500:]
    assert "with-a-newline" in page and "x-api-key" in page and "control character" in page
    #: Nowhere: standard error and out, the page, the audit log, the store's files.
    assert PLANT not in err.err and PLANT not in err.out and "Traceback" not in err.err
    assert PLANT not in page
    assert PLANT.encode() not in b"".join(p.read_bytes() for p in Path(log.root).glob("*.jsonl"))
    files = [p for p in Path(root).rglob("*") if p.is_file() and p.stat().st_size < 5_000_000]
    assert not [p for p in files if PLANT.encode() in p.read_bytes()]


def test_value_of_refuses_each_control_character_and_keeps_an_ordinary_value(monkeypatch, examined):
    dest = F.Destination(
        "d1", "a destination", "https://127.0.0.1:9", headers=(F.Header("x-api-key", "ONETRACE_FORWARD_K"),)
    )
    #: Each C0 control an environment can hold (it cannot hold NUL), and DEL.
    bad = ["a\nb", "a\rb", "a\tb", "a\x01b", "a\x1bb", "a\x7fb"]
    examined(len(bad) + 1, "values")
    for value in bad:
        monkeypatch.setenv("ONETRACE_FORWARD_K", value)
        try:
            F.value_of(dest, dest.headers[0])
        except F.KeyMissing as e:
            said = str(e)
        else:
            raise AssertionError(f"{value!r} was read")
        assert "a destination" in said and "x-api-key" in said and value not in said
    monkeypatch.setenv("ONETRACE_FORWARD_K", "an-ordinary-value")
    assert F.value_of(dest, dest.headers[0]) == "an-ordinary-value"
