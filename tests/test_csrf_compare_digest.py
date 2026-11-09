"""The console compares CSRF values with `hmac.compare_digest`, never `==`: the sign-in form's field
against its cookie (`POST /signin`), and an action's token against its cookie and the session's
(`_check_action_csrf`, as `POST /signout` uses it). Observed by a spy on `hmac.compare_digest` while the
two requests are served; a static look at `serve.py` holds that no CSRF value is compared with `==` or
`!=` there."""
from __future__ import annotations

import ast
import hmac
from pathlib import Path

from tests.test_signin_flow import _cookie_value, _get_signin_form, _post, signin_enabled  # noqa: F401

SERVE = Path(__file__).resolve().parents[1] / "src" / "onetrace_console" / "serve.py"


def test_both_csrf_checks_go_through_compare_digest(signin_enabled, monkeypatch, examined):
    base = signin_enabled
    seen = []
    real = hmac.compare_digest

    def spy(a, b):
        seen.append((a, b))
        return real(a, b)
    monkeypatch.setattr(hmac, "compare_digest", spy)
    csrf, form_token = _get_signin_form(base)
    status, _, headers, _ = _post(
        base, "/signin", f"username=alice&password=correct+horse+battery+staple&csrf_token={form_token}".encode(),
        headers={"Cookie": f"onetrace_csrf={csrf}", "Content-Type": "application/x-www-form-urlencoded"})
    assert status == 303
    signed_in = len(seen)
    session = _cookie_value(headers.get("Set-Cookie"), "onetrace_session")
    action_csrf = _cookie_value(headers.get("Set-Cookie"), "onetrace_csrf")
    status, _, _, _ = _post(base, "/signout", b"",
                            headers={"Cookie": f"onetrace_session={session}; onetrace_csrf={action_csrf}",
                                     "X-CSRF-Token": action_csrf})
    examined(2, "requests whose CSRF check was watched")
    assert status in (200, 303), status
    #: As bytes: the password's check goes through compare_digest too, with its hash's raw bytes.
    as_bytes = [tuple(x if isinstance(x, bytes) else x.encode("utf-8") for x in pair) for pair in seen]
    form, cookie, action = form_token.encode(), csrf.encode(), action_csrf.encode()
    assert (form, cookie) in as_bytes[:signed_in] or (cookie, form) in as_bytes[:signed_in], len(seen)
    assert any(action in pair for pair in as_bytes[signed_in:]), len(seen)


def _csrf_equality(tree: ast.AST) -> list[int]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
            names = [n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else ""
                     for n in [node.left, *node.comparators]]
            if any("csrf" in n.lower() or n in ("submitted", "cookie") for n in names):
                out.append(node.lineno)
    return out


def test_no_csrf_value_is_compared_with_equality_in_serve_py(examined):
    examined(1, "module")
    assert _csrf_equality(ast.parse(SERVE.read_text(encoding="utf-8"))) == []


def test_sabotage_an_equality_on_a_csrf_value_is_named(examined):
    examined(1, "planted module")
    assert _csrf_equality(ast.parse("ok = submitted == cookie == session.csrf_token\n")) == [1]
