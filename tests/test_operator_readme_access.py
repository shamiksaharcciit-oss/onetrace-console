"""The operator guide's teams, SCIM and audit sections, held to the code:

- Entra ID's "assignment required" setting, required, and where to check it;
- `scim.allowed_sources` and the `AzureActiveDirectory` service tag its ranges come from;
- the SCIM token's lifetime and rotation steps, each number the one the code uses;
- the way back in: the two recovery commands, that they need shell access to the console's machine, held only by
  the people who already administer it, and that for the image this is `docker exec` into the container;
- `audit.head_location`, and that it must not share the store's volume;
- each path's revocation time, path by path;
- every command the sections name is one the console's usage names.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GUIDE = (REPO / "OPERATOR_README.md").read_bytes().decode("utf-8").replace("\r\n", "\n")


def _section(title: str) -> str:
    start = GUIDE.index(f"\n## {title}\n")
    end = GUIDE.find("\n## ", start + 1)
    return GUIDE[start : end if end != -1 else None]


SCIM = _section("SCIM provisioning from Entra ID")
TEAMS = _section("Teams")
AUDIT = _section("The audit log")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def test_assignment_required_is_required_and_where_to_check_it_is_said(examined):
    said = _flat(SCIM)
    assert "**Assignment required?** to *Yes*" in said and "This is required" in said
    assert "**Enterprise applications**, the app, **Properties**" in said
    examined(1, "the assignment-required step")


def test_allowed_sources_and_the_service_tag_its_ranges_come_from(examined):
    from onetrace_console.scim import DEFAULTS

    said = _flat(SCIM)
    assert "`scim.allowed_sources`" in said and "`AzureActiveDirectory` service tag" in said
    assert "change over time" in said and DEFAULTS["allowed_sources"] == []
    assert "answered as a route the console does not have" in said
    examined(1, "allowed sources")


def test_the_token_s_lifetime_and_rotation_steps_are_the_code_s(examined):
    from onetrace_console.scim import DEFAULTS, LIVE_TOKENS, TOKEN_DAYS_CEILING, TOKEN_DAYS_DEFAULT, WARN_DAYS

    said = _flat(SCIM)
    assert f"lasts {TOKEN_DAYS_DEFAULT} days by default" in said
    assert f"({DEFAULTS['token_max_days']} by default, at most {TOKEN_DAYS_CEILING})" in said
    assert f"warns from {WARN_DAYS} days before" in said and LIVE_TOKENS == 2 and "At most two are live" in said
    steps = re.findall(r"^\d\. (.*)$", SCIM.split("### The SCIM token", 1)[1].split("###", 1)[0], re.M)
    assert len(steps) == 4 and "scim token create" in steps[0] and "Secret Token" in steps[1]
    assert "scim:<token id>" in steps[2] and "scim token revoke" in steps[3]
    examined(4, "the rotation's steps")


def test_the_way_back_in_needs_shell_access_and_for_the_image_docker_exec(examined):
    said = _flat(SCIM.split("### The way back in", 1)[1].split("###", 1)[0])
    for command in (
        "onetrace-console scim user activate <externalId>",
        "onetrace-console scim enforcement off",
        "onetrace-console scim enforcement on",
    ):
        assert command in said, command
    assert "shell access to the console's machine" in said and "who already administer that machine" in said
    assert "`docker exec` into the container" in said
    examined(3, "the two commands, and who holds them")


def test_head_location_must_not_share_the_store_s_volume(examined):
    from onetrace_console.config import AUDIT_DEFAULTS

    said = _flat(AUDIT)
    assert "`audit.head_location`, off the store's volume" in said and "not the store's" in said
    assert "refuses to start with the log on and none, or with one on the store's device" in said
    assert AUDIT_DEFAULTS["head_location"] is None
    examined(1, "the head location")


def test_each_path_s_revocation_time_is_said(examined):
    table = SCIM.split("### When access ends", 1)[1]
    rows = [r for r in table.splitlines() if r.startswith("| ") and not r.startswith("| A change") and "---" not in r]
    assert [r.split("|")[1].strip() for r in rows] == [
        "A person disabled, removed from the app, or out of scope",
        "A person deleted",
        "A person removed from a mapped group",
        "A console role removed (app roles)",
        "Any of these, now",
    ]
    assert "about 40 minutes" in rows[0] and "30 days" in rows[1] and "next request" in rows[2]
    assert "30 minutes idle" in rows[3] and "admin sessions end <tenant id>/<object id>" in rows[4]
    examined(len(rows), "paths, each with its time")


def test_every_command_the_sections_name_is_in_the_console_s_usage(examined):
    from onetrace_console.__main__ import USAGE

    named = set(re.findall(r"`onetrace-console ([a-z]+(?: [a-z-]+)*)", SCIM + TEAMS + AUDIT))
    assert named, "the sections name commands"
    for command in sorted(named):
        words = command.split()
        assert any(" ".join(words[:n]) in USAGE for n in (len(words), max(1, len(words) - 1))), command
    examined(len(named), "commands named in the sections")


def test_the_teams_section_says_what_a_console_with_teams_needs_and_the_page_for_no_team(examined):
    """The rules a console with teams must meet to start, as the guide says
    them, each word the code's."""
    from onetrace_console.team_assign import NO_TEAM

    said = _flat(TEAMS)
    assert "with the console's own accounts (`sign_in.method` `local`) it refuses to start" in said
    assert "without it, a console with `teams` or with SCIM refuses to start" in said
    assert "with neither, delivery would be open to any caller, and the console refuses to start" in said
    assert "With sign-in off it starts, and says at every start that teams scope nothing" in said
    assert f'"{NO_TEAM}"' in said.replace('" ', '"')
    examined(5, "rules said")


def test_the_guide_says_decision_exports_stopped_and_active_absent(examined):
    """Decision exports, "stopped", and a User created with no `active`: the guide says each."""
    teams, scim = _flat(TEAMS), _flat(SCIM)
    assert "**Decision exports** (the decisions extension) are drawn in the all-teams set only, for `admin`s" in teams
    assert "takes the console as stopped when nothing answers on its configured host and port" in teams
    assert "a console started on another address is not seen" in teams
    assert "A User Entra ID creates with no `active` is taken as active, as Entra ID always sends it" in scim
    examined(3, "sentences")
