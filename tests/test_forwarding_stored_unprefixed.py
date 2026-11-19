"""A destination kept before forwarding read only its own variables does not lock the setup page.

A 0.9 build before the rule kept a header's `key_env` with any variable's name. Read now, that destination raised as
the whole file was read: the setup page said the file can't be read, listed no destination, and none could be removed;
nothing was forwarded. Such a destination is now read with the others, said on the page as refused, naming it and the
variable (never a value), never queued or sent, and removable; the others load and forward as before. Read through
the console's own setup page, a file written as that build wrote it.
"""

from __future__ import annotations

import json
from pathlib import Path

from onetrace_console import forwarding as F
from tests.test_forwarding_setup import P, _get, _post, audited  # noqa: F401 - the fixture, requested by name

PLANT = "PLANTED-not-for-forwarding-5e2a"
OLD = {
    "id": "0123456789abcdef",
    "name": "kept-before-the-rule",
    "endpoint": "https://127.0.0.1:9",
    "encoding": "json",
    "headers": [{"name": "x-api-key", "key_env": "SIGNIN_CLIENT_SECRET_FOR_A_TEST"}],
    "runs": "all",
    "enabled": True,
}
GOOD = {**OLD, "id": "fedcba9876543210", "name": "named-for-forwarding"}
GOOD["headers"] = [{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_A_TEST_KEY"}]


def test_a_kept_destination_naming_another_variable_is_said_refused_never_sent_and_can_be_removed(
    audited, monkeypatch, capfd, examined
):  # noqa: F811
    base, root, log = audited
    monkeypatch.setenv("SIGNIN_CLIENT_SECRET_FOR_A_TEST", PLANT)
    path = F.folder(root) / F.DESTINATIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"format": F.FORMAT, "destinations": [OLD, GOOD]}), encoding="utf-8")
    examined(2, "destinations kept")

    #: Both read; the old one refused, by its name and the variable's.
    got = {d.name: d for d in F.read(root)}
    assert sorted(got) == ["kept-before-the-rule", "named-for-forwarding"]
    assert got["named-for-forwarding"].refused() is None
    why = got["kept-before-the-rule"].refused()
    assert why and "kept-before-the-rule" in why and "SIGNIN_CLIENT_SECRET_FOR_A_TEST" in why and PLANT not in why

    #: The page lists both and says the old one is refused; nothing says the file can't be read.
    status, page = _get(base + P.PATH)
    assert status == 200, page[-500:]
    assert 'data-forwarding="unreadable"' not in page
    assert 'data-destination="0123456789abcdef"' in page and 'data-destination="fedcba9876543210"' in page
    assert 'data-forwarding="refused"' in page and "SIGNIN_CLIENT_SECRET_FOR_A_TEST" in page
    assert page.count('data-forwarding="refused"') == 1
    assert PLANT not in page

    #: Queued and sent only to the other.
    assert F.enqueue(root, "run-a", F.CHECK_WORDS["yes"]) == 1
    assert F.queued(root, OLD["id"]) == [] and len(F.queued(root, GOOD["id"])) == 1

    #: Removed from the page, as any destination is; the other stays.
    status, page = _post(base + P.PATH, {"action": "remove", "id": OLD["id"], "sure": "yes"})
    assert status == 200, page[-500:]
    assert [d.name for d in F.read(root)] == ["named-for-forwarding"]

    out = capfd.readouterr()
    assert PLANT not in out.out and PLANT not in out.err
    assert PLANT.encode() not in b"".join(p.read_bytes() for p in Path(log.root).glob("*.jsonl"))
