"""Trace forwarding's setup page and the Settings gear's row (`forward_pages`, `settings_menu`): what the page says
and where it begins, a destination added, edited, turned off and removed, a header's value typed into the keychain
and found nowhere else, the test trace, the roles, the gear's row and dot, and the audit log. Every request goes to a
recording receiver on loopback; the keychain is a folder of the test's own (`tests/keychain.py`)."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

import pytest

from onetrace_console import forward_pages as P
from onetrace_console import forwarding as F
from tests.http_limits import limit
from tests.keychain import KEY, keychain, keyring_lib, planted_key_searched  # noqa: F401 - fixtures, by name
from tests.otlp_receiver import Receiver
from tests.test_entra_flow import entra  # noqa: F401 - a fixture, requested by name


def _get(url: str, headers: dict | None = None) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=limit(30)) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _post(url: str, fields: dict, headers: dict | None = None) -> tuple[int, str]:
    data = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=limit(60)) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _text(html: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


@pytest.fixture
def audited(server, tmp_path, monkeypatch):
    """The local console (sign-in off) with its audit log on: (base, store root, log)."""
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler

    base, root = server
    log = AuditLog(tmp_path / "audit_log", head_location=tmp_path / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", Audit(log))
    return base, root, log


def test_the_page_begins_with_a_trace_is_a_view_of_a_record_never_evidence(server, examined):
    base, _root = server
    status, html = _get(base + P.PATH)
    assert status == 200
    main = html[html.index("<main") :]
    said = _text(main)
    assert said.startswith(f"{P.TITLE} {P.NOT_EVIDENCE}"), said[:200]
    assert P.RETRIES.format(n=F.MAX_ATTEMPTS) in said
    assert P.NONE_YET in said
    examined(1, "page")


def test_a_destination_is_added_edited_turned_off_and_removed_and_each_change_is_audited(
    audited, monkeypatch, examined
):
    base, root, log = audited
    monkeypatch.setenv("ONETRACE_FORWARD_PAGE_KEY", "a-value-never-drawn")
    status, html = _post(
        base + P.PATH,
        {
            "action": "add",
            "name": "collector",
            "endpoint": "https://collector.example.com:4318",
            "encoding": "json",
            "runs": "agree",
            "header": "x-api-key",
            "where": "env",
            "key_env": "ONETRACE_FORWARD_PAGE_KEY",
        },
    )
    assert status == 200, _text(html)[:300]
    (d,) = F.read(root)
    assert (d.name, d.endpoint, d.runs, d.headers[0].key_env) == (
        "collector",
        "https://collector.example.com:4318",
        "agree",
        "ONETRACE_FORWARD_PAGE_KEY",
    )
    assert re.search(r"from the variable ONETRACE_FORWARD_PAGE_KEY\s*: set", _text(html))
    assert "a-value-never-drawn" not in html
    status, html = _post(
        base + P.PATH,
        {"action": "edit", "id": d.id, "name": "collector", "endpoint": d.endpoint, "encoding": "json", "runs": "all"},
    )
    assert status == 200 and F.read(root)[0].runs == "all"
    assert _post(base + P.PATH, {"action": "toggle", "id": d.id})[0] == 200 and not F.read(root)[0].enabled
    assert _post(base + P.PATH, {"action": "remove", "id": d.id})[0] == 400, "the box must be ticked"
    assert _post(base + P.PATH, {"action": "remove", "id": d.id, "sure": "yes"})[0] == 200 and F.read(root) == []
    entries = [e for e in log.entries() if e["event"] == "forwarding.changed"]
    assert [(e["detail"]["action"], e["detail"]["fields"]) for e in entries] == [
        ("add", list(F.FIELDS)),
        ("edit", ["runs"]),
        ("toggle", ["enabled"]),
        ("remove", ["removed"]),
    ]
    assert all(e["object"] in ("new", d.id) for e in entries)
    assert "a-value-never-drawn" not in json.dumps(entries)
    examined(len(entries), "changes recorded")


def test_http_is_refused_off_this_machine_and_nothing_is_written(server, examined):
    base, root = server
    status, html = _post(
        base + P.PATH,
        {
            "action": "add",
            "name": "x",
            "endpoint": "http://collector.example.com:4318",
            "encoding": "json",
            "runs": "all",
        },
    )
    assert status == 400 and "http is only for an address on this machine" in _text(html)
    assert F.read(root) == []
    examined(1, "refused")


def test_a_planted_value_is_sent_in_its_header_and_found_nowhere_else(
    server,
    keychain,
    files,
    planted_key_searched,
    capfd,
    monkeypatch,
    examined,  # noqa: F811 - fixtures, by name
):
    """The value typed into the page once: sent in the header it names, and in none of the configuration file, any
    page or answer, the logs, the audit log, the queue's files or an export (every file the test wrote is searched
    afterwards, the keychain's own folder set aside, by `planted_key_searched`)."""
    from onetrace_console import export_static
    from onetrace_console.audit import Audit, AuditLog
    from onetrace_console.serve import Handler
    from tests.conftest import make_tar

    base, root = server
    log = AuditLog(root.parent / "audit_log", head_location=root.parent / "heads.jsonl")
    monkeypatch.setattr(Handler, "audit", Audit(log))
    with Receiver() as r:
        status, added = _post(
            base + P.PATH,
            {
                "action": "add",
                "name": "recv",
                "endpoint": r.endpoint,
                "encoding": "json",
                "runs": "all",
                "header": "x-api-key",
                "where": "keyring",
                "value": KEY,
            },
        )
        assert status == 200, _text(added)[:300]
        (d,) = F.read(root)
        assert "from the keychain: stored" in _text(added)
        pages = [added, _get(base + P.PATH)[1]]
        status, test = _post(base + P.PATH, {"action": "test", "id": d.id})
        pages.append(test)
        assert "answered 200 OK" in _text(test)
        req = urllib.request.Request(base + "/v1/runs", data=make_tar(files), method="POST")
        with urllib.request.urlopen(req, timeout=limit(60)) as resp:
            pages.append(resp.read().decode())
        sender = F.Forwarder(root, Handler.store, every=0.05)
        sender.start()
        try:
            sent = r.wait_for(2)
        finally:
            sender.stop()
        assert [q.headers.get("x-api-key") for q in sent] == [KEY, KEY]
        for rel in ("/home.html", "/runs", "/forwarding/setup"):
            pages.append(_get(base + rel)[1])
        export_static.export(root, [x.key for x in Handler.store.runs()], root.parent / "export")
    assert any(e["event"] == "forwarding.changed" for e in log.entries())
    out, err = capfd.readouterr()
    assert all(KEY not in p for p in pages)
    assert KEY not in out and KEY not in err
    assert KEY not in (root / F.FOLDER / F.DESTINATIONS).read_text()
    examined(len(pages), "pages and answers read")


def test_the_test_trace_says_the_destination_s_status(server, examined):
    base, root = server
    with Receiver([401]) as r:
        F.save(root, None, {"name": "recv", "endpoint": r.endpoint})
        (d,) = F.read(root)
        status, html = _post(base + P.PATH, {"action": "test", "id": d.id})
        (req,) = r.traces()
    assert status == 200 and "answered 401 Unauthorized" in _text(html)
    spans = json.loads(req.body)["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert [s["name"] for s in spans] == [F.TEST_SPAN]
    assert F.queued(root, d.id) == [], "the test trace queues nothing"
    examined(1, "test trace")


def test_with_protobuf_chosen_and_the_extra_missing_the_page_gives_the_install_line(server, monkeypatch, examined):
    base, root = server
    monkeypatch.setattr(F, "protobuf_installed", lambda: False)
    F.save(root, None, {"name": "pb", "endpoint": "https://collector.example.com", "encoding": "protobuf"})
    status, html = _get(base + P.PATH)
    assert status == 200 and F.INSTALL in _text(html)
    examined(1, "page")


def test_a_public_console_draws_no_row_and_serves_no_forwarding_route(server, monkeypatch, examined):
    from dataclasses import replace

    from onetrace_console.serve import Handler

    base, _root = server
    monkeypatch.setattr(Handler, "config", replace(Handler.config, public=True))
    assert _get(base + P.PATH)[0] == 404
    assert _post(base + P.PATH, {"action": "add"})[0] in (403, 404)
    examined(2, "routes")


# ------------------------------------------------------------------------------------------------ the roles


def test_forwarding_s_routes_are_an_admin_s_unscoped_in_both_sets_of_rules(examined):
    from onetrace_console import roles

    for oidc in (False, True):
        assert roles.required_role("GET", P.PATH, rel_for_get=P.REL, oidc=oidc) == roles.ADMIN
        assert roles.team_rule("GET", P.PATH, rel_for_get=P.REL, oidc=oidc) == roles.ADMIN_UNSCOPED
        assert roles.required_role("POST", P.PATH, oidc=oidc) == roles.ADMIN
        assert roles.team_rule("POST", P.PATH, oidc=oidc) == roles.ADMIN_UNSCOPED
    examined(4, "rows in each set")


def test_a_viewer_and_an_investigator_are_refused_every_forwarding_route(entra, examined):  # noqa: F811
    from tests.test_entra_flow import sign_in

    base, fake, _root = entra
    got = {}
    for role in ("onetrace.viewer", "onetrace.investigator", "onetrace.admin"):
        _s, _p, _h, session, csrf = sign_in(base, fake, roles=(role,))
        cookie = {"Cookie": f"onetrace_session={session}; onetrace_csrf={csrf}"}
        got[role] = (
            _get(base + P.PATH, cookie)[0],
            _post(base + P.PATH, {"action": "test", "id": "0" * 16, "csrf_token": csrf}, cookie)[0],
        )
    assert got["onetrace.viewer"] == (403, 403) and got["onetrace.investigator"] == (403, 403), got
    assert got["onetrace.admin"][0] == 200 and got["onetrace.admin"][1] == 400, got
    examined(6, "requests")


# --------------------------------------------------------------------------------------------- the gear's row


class _Store:
    def __init__(self, root: Path) -> None:
        self.root = root / "store"


def _row(tmp_path):
    from onetrace_console.settings_menu import forwarding_row

    return forwarding_row(_Store(tmp_path))


def test_the_gear_s_row_says_off_on_and_each_broken_state(tmp_path, monkeypatch, keychain, examined):  # noqa: F811
    from onetrace_console import forward_keys
    from onetrace_console.settings_menu import menu

    assert (_row(tmp_path).words, _row(tmp_path).state) == ("Forwarding: off", "off")
    d, _ = F.save(
        tmp_path,
        None,
        {
            "name": "env",
            "endpoint": "https://a.example",
            "headers": [{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_ROW_KEY"}],
        },
    )
    monkeypatch.delenv("ONETRACE_FORWARD_ROW_KEY", raising=False)
    row = _row(tmp_path)
    assert row.state == "broken" and row.words == "Forwarding: 1 destination on, env: x-api-key not set"
    assert "data-broken" in menu(_Store(tmp_path)) and 'data-frame="settings-dot"' in menu(_Store(tmp_path))
    monkeypatch.setenv("ONETRACE_FORWARD_ROW_KEY", "v")
    assert (_row(tmp_path).words, _row(tmp_path).state) == ("Forwarding: 1 destination on", "on")
    assert "data-broken" not in menu(_Store(tmp_path))
    k, _ = F.save(
        tmp_path,
        None,
        {
            "name": "kc",
            "endpoint": "https://b.example",
            "headers": [{"name": "authorization", "key_source": "keyring"}],
        },
    )
    assert _row(tmp_path).words == "Forwarding: 2 destinations on, kc: authorization not stored"
    forward_keys.store(k.id, "authorization", "v")
    assert _row(tmp_path).state == "on"
    F._note(tmp_path, k.id, last_failure="503 Service Unavailable", last_failure_at="2026-11-15T10:00:00Z")
    assert _row(tmp_path).words == "Forwarding: 2 destinations on, kc: the last attempt failed"
    F._note(tmp_path, k.id, last_send="2026-11-15T10:05:00Z")
    assert _row(tmp_path).state == "on"
    F.save(tmp_path, d.id, {"enabled": False})
    F.save(tmp_path, k.id, {"enabled": False})
    assert _row(tmp_path).words == "Forwarding: off"
    examined(8, "states")


def test_a_destination_s_name_in_the_broken_row_is_escaped(tmp_path, monkeypatch, examined):
    #: A name is the operator's own words, of up to 80 characters, "<" and "&" among them: the broken row says it as
    #: text, never as markup.
    from onetrace_console.settings_menu import menu

    name = '<img src=x onerror="a()"> & co'
    F.save(
        tmp_path,
        None,
        {
            "name": name,
            "endpoint": "https://a.example",
            "headers": [{"name": "x-api-key", "key_env": "ONETRACE_FORWARD_ESC_KEY"}],
        },
    )
    monkeypatch.delenv("ONETRACE_FORWARD_ESC_KEY", raising=False)
    assert _row(tmp_path).words == f"Forwarding: 1 destination on, {name}: x-api-key not set"
    html = menu(_Store(tmp_path))
    assert "<img" not in html and "& co" not in html
    assert "&lt;img src=x onerror=&quot;a()&quot;&gt; &amp; co: x-api-key not set" in html
    assert f"{name}: x-api-key not set" in unescape(html)
    examined(1, "broken row with a name holding markup")


def test_each_header_the_guide_s_worked_examples_name_says_where_its_value_is(examined):
    #: 0.9 has no header whose value is typed in: each comes from a variable or the keychain, and the guide's examples
    #: say so for every header they name, a fixed value such as Langfuse's ingestion version included.
    guide = (Path(__file__).resolve().parents[1] / "OPERATOR_README.md").read_text(encoding="utf-8")
    examples = guide.split("**Worked examples.**", 1)[1].split("\n## ", 1)[0]
    items = [i for i in re.split(r"\n- ", examples)[1:] if " Header" in i or "header" in i.split(".", 2)[-1]]
    named = 0
    for item in items:
        flat = " ".join(item.split())
        for sentence in re.split(r"(?<=[.;])\s+", flat):
            for header in re.findall(r"`((?:x-|X-)[A-Za-z0-9-]+|Authorization|Langsmith-Project)`", sentence):
                named += 1
                if header == "Langsmith-Project":
                    continue  # named as an option; its value is the project's name, set as any header's
                assert "variable" in sentence and "keychain" in sentence, (header, sentence)
    examined(named, "headers named in the worked examples")
    assert named >= 3
