"""Paths that try to step around the role table are refused.

    In `do_GET`: refuse any path containing `..`, `\\`, or an encoded form of either; require
    the resolved path to stay under `pages/` and equal what the role row matched. Add
    near-miss tests for every row.

Every GET row of the role table gets its own near misses here, sent as raw bytes so that no
client normalises them first. All of them are refused with 400 before any file is read, in
config-file mode (the shared test server) -- the path rule is not local mode's guard.
"""
from __future__ import annotations

import pytest

from tests.test_local_mode import _raw

KEY = "0123456789abcdef" * 4

#: One real path per GET row of the role table.
ROWS = ["home.html", "executions-all.html", "incidents.html", "incidents-r-c010.html",
        f"runs/{KEY}/answer.html", f"runs/{KEY}/case.html", f"runs/{KEY}/authorization.html",
        f"diff/{KEY}.html", "policy.html", "policy/req-1.html", "policy-verdict-denied.html",
        "policy-issuer-onedoor.html"]


def _near_misses(rel: str) -> list[str]:
    """Ways of spelling a path that are not that path."""
    head, _, tail = rel.rpartition("/")
    here = f"{head}/" if head else ""
    return [f"{here}../{tail}", f"{here}x/../{tail}", f"{here}..\\{tail}", rel.replace("/", "\\"),
            f"{here}%2e%2e/{tail}", f"{here}%2E%2E/{tail}", f"{here}%5c{tail}",
            f"{here}.%2e/{tail}", f"{here}./{tail}", f"{here}/{tail}" if head else f"./{tail}"]


@pytest.mark.parametrize("rel", ROWS)
def test_every_rows_near_misses_are_refused(server, rel, examined):
    base, _ = server
    port = base.rsplit(":", 1)[1]
    misses = [m for m in _near_misses(rel) if m != rel]
    examined(len(misses), f"near misses of {rel}")
    for miss in misses:
        status, _ = _raw(base, [f"GET /{miss} HTTP/1.1", f"Host: 127.0.0.1:{port}"])
        assert status == 400, (miss, status)


def test_the_real_paths_still_reach_their_pages(server):
    base, _ = server
    port = base.rsplit(":", 1)[1]
    status, _ = _raw(base, ["GET /home.html HTTP/1.1", f"Host: 127.0.0.1:{port}"])
    assert status == 200
    status, _ = _raw(base, [f"GET /runs/{KEY}/case.html HTTP/1.1", f"Host: 127.0.0.1:{port}"])
    assert status == 404, "an unrendered page is still a 404, not a 400"


@pytest.mark.parametrize("miss", ["home.html.", "HOME.HTML", "Home.html"])
def test_a_spelling_that_resolves_to_another_file_is_never_served(server, miss):
    """The second half of the rule: the page served must be the one the row matched, spelled
    the same way. On Windows a trailing dot, or another case, opens `home.html`; the resolved
    path then differs from the requested one, and that is refused. On a file system where no
    such file exists it is simply not found. Never served either way."""
    import os
    base, _ = server
    port = base.rsplit(":", 1)[1]
    status, _ = _raw(base, [f"GET /{miss} HTTP/1.1", f"Host: 127.0.0.1:{port}"])
    assert status != 200, miss
    if os.name == "nt":
        assert status == 400, (miss, status)
