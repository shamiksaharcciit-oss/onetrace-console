"""A person in no team sees one page, and its frame offers nothing that leads back to it.

The page says "You are in no team. Ask your administrator to add you." whatever is asked for, so the sidebar's
Overview, Runs, Comparisons and Incidents each led to the same page again. On that page the frame draws no run links;
the footer (who is signed in, the theme) and the settings gear with Sign out stay.
"""

from __future__ import annotations

import re


def test_the_no_team_page_s_frame_draws_no_run_links(tmp_path, examined):
    from onetrace_console import frame
    from onetrace_console.store import Store
    from onetrace_console.team_assign import no_team_page

    page = frame.fill(
        no_team_page().encode(),
        "no-team",
        onedoor=False,
        user="Nia None",
        setup_link=True,
        store=Store(tmp_path / "store"),
        csrf="t",
    ).decode()
    nav = re.search(r'<nav class="frame" data-frame>(.*?)</nav>', page, re.S).group(1)
    examined(1, "page")
    assert [label for label, _h, _r in frame.items(False) if f">{label}</a>" in nav] == []
    assert "Signed in as Nia None" in nav and 'data-frame="gear"' in nav


def test_another_page_keeps_its_run_links(tmp_path, examined):
    from onetrace_console import frame
    from onetrace_console.render import _document

    page = frame.fill(
        _document("A page", "<div class='cp'><h1>x</h1></div>").encode(), "home.html", onedoor=False, user=None
    ).decode()
    examined(1, "page")
    assert all(f">{label}</a>" in page for label, _h, _r in frame.items(False))
