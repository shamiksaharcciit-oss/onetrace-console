"""Access control without its record is not offered: `audit.enabled` stays
off by default, and a console with `teams` or with `scim.enabled` refuses to start with it off, naming the keys. With
the audit log on, each starts."""

from __future__ import annotations

import pytest

from tests.test_audit_log import second  # noqa: F401 - a fixture, requested by name
from tests.test_team_assignment import TEAMS, A, _body, _cli, _refused, _serve


@pytest.fixture
def audit_on(second):  # noqa: F811
    return {"enabled": True, "head_location": (second / "heads.jsonl").as_posix()}


def test_the_audit_log_is_off_by_default(examined):
    from onetrace_console.config import Config

    assert Config().audit.get("enabled") is False
    examined(1, "default")


@pytest.mark.parametrize("what", ["teams", "scim"])
def test_teams_or_scim_with_the_audit_log_off_refuses_to_start_naming_the_keys(
    tmp_path, monkeypatch, capsys, audit_on, what, examined
):
    more = {"teams": TEAMS} if what == "teams" else {"scim": {"enabled": True}}
    off = _body(tmp_path, audit={"enabled": False}, **more)
    if what == "teams":
        assert _cli(tmp_path, monkeypatch, off, "token", "create", "ci", "--team", A) == 0
        capsys.readouterr()
    assert _serve(tmp_path, monkeypatch, off) == 1
    err = _refused(capsys)
    assert "audit.enabled" in err and ("teams" if what == "teams" else "scim.enabled") in err
    assert _serve(tmp_path, monkeypatch, {**off, "audit": audit_on}) == -1, capsys.readouterr().err
    examined(2, f"starts with {what}: the audit log off, then on")
