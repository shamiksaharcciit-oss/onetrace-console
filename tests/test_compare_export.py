"""A static export has no live Compare: the "Choose run B" and "What changed" pages show the Compare control
disabled, with "Needs a running console.", as the first-run-to-leave control is shown. An exported store holds
no script that reads `onetrace_csrf`, no `X-CSRF-Token`, no line about the session's token, and no enabled
button or form but the theme switch's (which changes only the page's look, in the browser). The pages the
console serves keep their Compare."""
from __future__ import annotations

import re

import pytest

from tests.test_bisect_page import CHANGED, SAME, _series

NEEDS = "Needs a running console."
#: The theme switch's two buttons: the look only, kept in an export (tests/test_theme_switch.py).
THEME = ('<button type="button" data-theme-switch hidden>', '<button type="button" data-theme-system hidden>')


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    from onetrace_console.export_static import export
    t = tmp_path_factory.mktemp("compare-export")
    store, runs = _series(t / "made", [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    export(t / "made", [r.key for r in runs.values()], t / "export")
    return {p.relative_to(t / "export").as_posix(): p.read_text(encoding="utf-8", errors="replace")
            for p in sorted((t / "export").rglob("*")) if p.is_file() and p.suffix in (".html", ".css", ".js", ".txt")}


def live_controls(pages: dict[str, str]) -> list[str]:
    out = []
    for rel, s in pages.items():
        for word in ("onetrace_csrf", "X-CSRF-Token", "CSRF token"):
            if word in s:
                out.append(f"{rel}: {word}")
        #: The stylesheet's rules for the console's own Compare button are no control; a page's attribute is.
        if rel.endswith(".html") and "data-compare-post" in s:
            out.append(f"{rel}: data-compare-post")
        for b in re.findall(r"<button\b[^>]*>", s):
            if b not in THEME and " disabled" not in b:
                out.append(f"{rel}: an enabled button {b[:80]}")
        for f in re.findall(r"<form\b[^>]*>", s):
            out.append(f"{rel}: a form {f[:80]}")
    return out


def test_an_exported_store_holds_no_live_compare_csrf_or_enabled_control(exported, examined):
    examined(len(exported), "exported files")
    assert live_controls(exported) == []


@pytest.mark.parametrize("kind", ["choose", "case"])
def test_choose_run_b_and_what_changed_show_compare_disabled_with_its_one_line(exported, kind, examined):
    pages = {rel: s for rel, s in exported.items() if rel.split("/")[-1].startswith(kind) or f"/{kind}" in rel}
    held = {rel: s for rel, s in pages.items() if "data-compare-needs-console" in s}
    examined(len(pages), f"{kind} pages")
    assert held, sorted(pages)
    for rel, s in held.items():
        assert re.search(r'<button type="button" disabled data-compare-needs-console>[^<]+</button>', s), rel
        assert s.count(f"<span data-needs-console>{NEEDS}</span>") == s.count("data-compare-needs-console>"), rel


def test_sabotage_a_live_compare_left_in_is_named(exported, examined):
    rel, page = next((r, s) for r, s in exported.items() if "data-compare-needs-console" in s)
    planted = {rel: page.replace('<button type="button" disabled data-compare-needs-console>',
                                 '<button type="button" data-compare-post="/compare?a=x&amp;b=y">', 1)
               + "<script>document.cookie.match(/onetrace_csrf=/)</script>"}
    examined(1, "planted page")
    assert {f"{rel}: onetrace_csrf", f"{rel}: data-compare-post"} <= set(live_controls(planted))


def test_the_served_choose_page_keeps_its_compare(tmp_path, examined):
    from onetrace_console.choose_pages import render_pair
    from onetrace_console.compare_script import COMPARE_SCRIPT
    from onetrace_console.overview import pipelines
    store, _ = _series(tmp_path / "made", [SAME, SAME, CHANGED, SAME], arrival=[1, 2, 3, 4])
    (p,) = pipelines(store)
    page = render_pair(p, p.runs[0], store, generated_at="2026-11-08T00:00:00+00:00")
    examined(1, "served page")
    assert "data-compare-post=" in page and COMPARE_SCRIPT in page and NEEDS not in page
