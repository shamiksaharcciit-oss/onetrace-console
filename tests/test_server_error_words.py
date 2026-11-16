"""A server error's words stay on the server.

`_do_post`'s catch-all answered `500` with the exception's type and message: on `POST /signin`, which needs no
session, an error reading the accounts named a path on the server. It now answers a fixed sentence and a short
reference, and the type, message and traceback go to the server's log under that reference.
"""

from __future__ import annotations

import re

from onetrace_console.serve import Handler
from tests.test_roles_enforcement import _get_signin_form, _post, roles_enabled  # noqa: F401 - a fixture, used by name

PLANTED = "/srv/planted-accounts/alice.json"


def test_an_error_reading_the_accounts_during_sign_in_says_no_path_and_no_exception(
    roles_enabled,  # noqa: F811 - the fixture imported above
    monkeypatch,
    capsys,
    examined,
):
    base, _token = roles_enabled

    def unreadable(_username):
        raise PermissionError(13, "Permission denied", PLANTED)

    monkeypatch.setattr(Handler.account_store, "unlocked_at", unreadable)
    csrf, form_token = _get_signin_form(base)
    status, body, _headers, _ = _post(
        base,
        "/signin",
        f"username=alice&password=wrong-password-here&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    said = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    examined(1, "sign-in with the accounts unreadable")
    assert status == 500, (status, said)
    assert PLANTED not in said and "PermissionError" not in said and "Permission denied" not in said, said
    ref = re.search(r"reference ([0-9a-f]{8})", said)
    assert ref, said
    log = capsys.readouterr().err
    assert ref.group(1) in log and "PermissionError" in log and PLANTED in log
