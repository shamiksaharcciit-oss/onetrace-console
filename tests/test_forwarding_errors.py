"""Forwarding's setup page says a refusal by the field it is about, and keeps what was typed (`forward_pages`).

- **By its field:** the message sits under the field, `role="alert"`; the field carries `aria-invalid="true"` and
  `aria-describedby` naming the message; the line at the top names it too and links to the field.
- **Kept as typed:** every field comes back as it was sent, the choices too, except the keychain value, which is never
  drawn.
- **The message agrees with the field's label,** "Endpoint (https, or http on this machine)".
- **The page after a refused press carries the session,** "Signed in as …", as the page opened by GET does, never
  "Local mode".
"""

from __future__ import annotations

import re
from html import unescape

from onetrace_console import forward_pages as P
from onetrace_console import forwarding as F
from tests.test_entra_flow import entra, sign_in  # noqa: F401 - the fixture, used by name
from tests.test_forwarding_setup import _get, _post

ADD = {
    "action": "add",
    "name": "audit test",
    "endpoint": "ftp://collector.example/v1/traces",
    "encoding": "protobuf",
    "runs": "agree",
    "header": "x-api-key",
    "where": "keyring",
    "key_env": "",
    "value": "Pl4nted-value-never-drawn",
}


def _input(page: str, form: str, name: str) -> str:
    """The `<input>` or `<select>` named `name` in the form whose data-forwarding is `form`."""
    found = re.search(rf'<form[^>]*data-forwarding="{form}"[^>]*>(.*?)</form>', page, re.S)
    assert found, f"no {form} form"
    tag = re.search(rf'<(?:input|select)\b[^>]*name="{name}"[^>]*>', found.group(1))
    assert tag, f"no {name} in the {form} form"
    return tag.group(0)


def _described(page: str, tag: str) -> str:
    ids = re.search(r'aria-describedby="([^"]+)"', tag)
    assert ids, tag
    said = re.search(rf'<[^>]*id="{ids.group(1)}"[^>]*role="alert"[^>]*>(.*?)</', page, re.S) or re.search(
        rf'<[^>]*role="alert"[^>]*id="{ids.group(1)}"[^>]*>(.*?)</', page, re.S
    )
    assert said, ids.group(1)
    return unescape(said.group(1))


def test_a_refused_endpoint_is_said_by_its_field_and_every_field_comes_back_as_typed(server, examined):
    base, root = server
    status, page = _post(base + P.PATH, ADD)
    examined(8, "fields and the message")
    assert status == 400 and F.read(root) == []
    endpoint = _input(page, "add", "endpoint")
    assert 'aria-invalid="true"' in endpoint and 'value="ftp://collector.example/v1/traces"' in endpoint
    said = _described(page, endpoint)
    assert "https://" in said and "http://" in said and "this machine" in said, said
    assert 'value="audit test"' in _input(page, "add", "name")
    assert 'value="x-api-key"' in _input(page, "add", "header")
    assert re.search(r'<option value="protobuf" selected>', page) and re.search(
        r'<option value="agree" selected>', page
    )
    assert re.search(r'<option value="keyring" selected>', page)
    assert "Pl4nted-value-never-drawn" not in page
    assert "aria-invalid" not in _input(page, "add", "name")
    #: The line at the top names it, and links to the field.
    assert re.search(r'data-forwarding="said"[^>]*>.*?<a href="#[^"]+">', page, re.S), page[-3000:]


def test_a_missing_name_and_a_bad_header_are_each_said_by_their_own_field(server, examined):
    base, _root = server
    examined(2, "refusals")
    _s, page = _post(base + P.PATH, {**ADD, "endpoint": "https://collector.example", "name": ""})
    assert 'aria-invalid="true"' in _input(page, "add", "name")
    assert "aria-invalid" not in _input(page, "add", "endpoint")
    _s, page = _post(base + P.PATH, {**ADD, "endpoint": "https://collector.example", "header": "x api key"})
    assert 'aria-invalid="true"' in _input(page, "add", "header") and "letters, digits" in _described(
        page, _input(page, "add", "header")
    )


def test_the_endpoint_s_message_agrees_with_its_label(examined):
    examined(1, "message")
    said = F.endpoint_problem("ftp://collector.example")
    assert said is not None and "https://" in said and "http://" in said and "this machine" in said, said


def test_the_page_after_a_refused_press_carries_the_session(entra, examined):  # noqa: F811
    base, fake, _root = entra
    examined(2, "pages: a GET's and a refused POST's")
    _s, _p, _h, session, csrf = sign_in(base, fake, roles=("onetrace.admin",))
    cookie = {"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"}
    _status, got = _get(base + P.PATH, cookie)
    status, posted = _post(base + P.PATH, {**ADD, "csrf_token": csrf}, cookie)
    assert status == 400
    for page in (got, posted):
        footer = page[page.index("<footer>") : page.index("</footer>")]
        assert "Signed in as" in footer and "Local mode" not in footer, footer
