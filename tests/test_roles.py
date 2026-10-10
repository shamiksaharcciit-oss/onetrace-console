"""Role enforcement, from one place, per the design note §3 table."""
from __future__ import annotations

import pytest

from onetrace_console import roles


def test_health_and_signin_and_signout_need_no_principal(examined):
    examined(4, "the unauthenticated exceptions")
    assert roles.required_role("GET", "/health") is None
    assert roles.required_role("GET", "/signin") is None
    assert roles.required_role("POST", "/signin") is None
    assert roles.required_role("POST", "/signout") is None


@pytest.mark.parametrize("rel", [
    "home.html",
    "counts.html",
    "executions-all.html",
    "executions-run-id-reused.html",
    "executions-most-recent.html",
    "incidents.html",
    "incidents-r-c010.html",
    "runs/abc123/answer.html",
    "runs/abc123/case.html",
    "runs/" + "0123456789abcdef" * 4 + "/authorization.html",
    "diff/def456.html",
    "policy.html",
    "policy/req-1.html",
    "policy-verdict-observe.html",
    "policy-issuer-onedoor.html",
])
def test_every_rendered_page_shape_is_viewer(rel, examined):
    """One sub-case per GET row of the design note's own table."""
    examined(1, f"GET against the rendered path {rel!r}")
    assert roles.required_role("GET", "/" + rel, rel_for_get=rel) == roles.VIEWER


def test_post_v1_runs_and_v1_decisions_are_ingester_and_compare_is_viewer(examined):
    examined(3, "the three named POST routes")
    assert roles.required_role("POST", "/v1/runs") == roles.INGESTER
    assert roles.required_role("POST", "/v1/decisions") == roles.INGESTER
    assert roles.required_role("POST", "/compare") == roles.VIEWER


def test_a_get_path_with_no_matching_shape_is_refused(examined):
    """The sabotage target itself: a route added later without an entry here
    must be refused, never silently served open.
    """
    examined(1, "a hypothetical new page shape with no table entry")
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("GET", "/admin.html", rel_for_get="admin.html")


def test_a_post_path_with_no_matching_entry_is_refused(examined):
    examined(1, "a hypothetical new POST route with no table entry")
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("POST", "/v1/new-thing-nobody-wired-up")


def test_role_includes_admin_over_viewer_but_nothing_nests_otherwise(examined):
    examined(6, "every (granted, required) pair that matters")
    assert roles.role_includes(roles.ADMIN, roles.VIEWER) is True
    assert roles.role_includes(roles.VIEWER, roles.VIEWER) is True
    assert roles.role_includes(roles.INGESTER, roles.INGESTER) is True
    #: The mutual exclusions, named explicitly.
    assert roles.role_includes(roles.INGESTER, roles.VIEWER) is False
    assert roles.role_includes(roles.VIEWER, roles.INGESTER) is False
    assert roles.role_includes(roles.ADMIN, roles.INGESTER) is False


def test_sabotage_a_route_with_no_table_entry_is_missed_by_a_catch_all(examined):
    """Demonstrated directly, the way this programme's other sabotages are: a
    naive catch-all implementation (any GET path is 'viewer' if a page exists)
    would NOT catch a route missing from the real table -- proving the real
    `required_role`'s own raise is what item 7's test actually depends on.
    """
    def sabotaged_required_role(method, path, *, rel_for_get=None):
        if method == "GET":
            return roles.VIEWER          # a defaulted-open stand-in, the sabotage
        return roles.required_role(method, path, rel_for_get=rel_for_get)

    examined(1, "a hypothetical new page shape, through the sabotaged stand-in")
    assert sabotaged_required_role("GET", "/admin.html", rel_for_get="admin.html") == roles.VIEWER
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("GET", "/admin.html", rel_for_get="admin.html")


def test_every_page_the_console_renders_has_a_viewer_row(tmp_path, examined):
    """Every page the start-up render writes, read from `pages/` itself rather than a list typed
    here: a page added without a row (`counts.html`, the All counts page, had none -- with sign-in
    on it answered 404) fails here, not in front of a signed-in reader."""
    from onetrace_console.compare import compare
    from onetrace_console.config import Config
    from onetrace_console.serve import PAGES_DIRNAME, _local_config, _render_startup_pages
    from onetrace_console.store import Store
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_stage_pages import DEMO, _stored
    _require_installed()
    store = Store(tmp_path / "store")
    a, b = _stored(DEMO / "day-1", store), _stored(DEMO / "day-2", store)
    compare(a, b, store, ran_at=FIXED_RAN_AT)
    _render_startup_pages(store, tmp_path, _local_config(Config()))
    pages = sorted(p.relative_to(tmp_path / PAGES_DIRNAME).as_posix()
                   for p in (tmp_path / PAGES_DIRNAME).rglob("*") if p.is_file())
    assert "counts.html" in pages and any(p.startswith("diff/") for p in pages), pages
    examined(len(pages), "rendered pages checked against the role table")
    unrouted = []
    for rel in pages:
        try:
            assert roles.required_role("GET", "/" + rel, rel_for_get=rel) == roles.VIEWER, rel
        except roles.NoRouteTableEntry:
            unrouted.append(rel)
    assert not unrouted, f"rendered, with no row in the role table: {unrouted}"
