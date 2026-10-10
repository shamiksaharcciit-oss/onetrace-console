"""A run's authorization page, in release 1's "no records" state (v6 board 3).

    Only the "no records" authorization board (board 3), rather than waiting for onedoor.
    It is never counted as a pass. It is never blank.

The page is this console's own (the viewer has no authorization page), rendered in the
viewer's shell like the Diff page, beside the run's two viewer pages. The case page's Policy
section links to it, and it links back.

It says what release 1 has -- no authorization records for this run -- and nothing about
what a run's receipts contain or what the pipeline behind them does: this console looks for
neither. The viewer's independent review found the same over-claim in the Policy sentence
(its finding 8), so the page is held to it from the start.
"""
from __future__ import annotations

import json
import re
from html import unescape

import pytest

from onetrace_console.pages import AUTHORIZATION, CASE, render_execution
from tests.test_pages import GENERATED_AT, checked  # noqa: F401


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()


@pytest.fixture
def pages(checked, store):  # noqa: F811
    assert not store.decision_export_records(), "the store holds no onedoor export"
    return render_execution(checked, store, generated_at=GENERATED_AT).pages


def test_every_run_has_an_authorization_page_in_the_no_records_state(pages, checked, examined):
    page = pages[AUTHORIZATION]
    examined(1, "the authorization page of a stored run with no onedoor export")
    text = _text(page)
    assert re.search(r"<h1>Authorization</h1>", page)
    assert re.search(r'<p data-state="no-records">No records</p>', page)
    assert "No authorization records for this run" in text
    assert "Nothing here is counted as a pass." in text
    assert checked.run_id in text, "the page names the run it is about"


def test_the_page_never_reads_as_a_pass_and_is_never_blank(pages):
    text = _text(pages[AUTHORIZATION]).lower()
    for word in ("permitted", "authorized:", "approved", "allowed", "checks passed", "yes"):
        assert word not in text, word
    assert 'data-state="yes"' not in pages[AUTHORIZATION]
    section = re.search(r'<section data-section="authorization"[^>]*>(.*?)</section>',
                        pages[AUTHORIZATION], re.S)
    assert section and _text(section.group(1)), "the section is on the page and says something"


#: Every word the page's own section says, exactly. Pinned whole, so a sentence cannot join
#: it unnoticed: the review of the first version found one ("When a policy engine that speaks
#: AADP is added, this page shows the whole chain...") presupposing no engine was added and
#: promising a feature nothing backs, while the phrase-list test below let it through.
SECTION_WORDS = ('No authorization records for this run That is not a failure of the record. '
                 'Back to the run Nothing here is counted as a pass. "No records" is shown '
                 'wherever authorization would appear.')


def test_the_page_says_exactly_what_release_1_has_and_nothing_more(pages):
    section = re.search(r'<section data-section="authorization"[^>]*>(.*?)</section>',
                        pages[AUTHORIZATION], re.S)
    assert _text(section.group(1)) == SECTION_WORDS


def test_each_runs_page_is_titled_with_its_run(pages, checked):
    assert f"<title>Authorization · {checked.run_id}</title>" in pages[AUTHORIZATION]


def test_the_page_claims_nothing_it_does_not_check(pages):
    """Board 3's "Nothing in the record shows a policy decision, a permit or a confirmation" and
    "this pipeline does not yet send its actions through a policy engine" are claims about the
    receipts and about a system this console does not look at; the drawing's "proposed an
    action (stage 5)" is its own illustrative run."""
    text = _text(pages[AUTHORIZATION]).lower()
    for claim in ("nothing in the record shows", "does not yet send its actions",
                  "proposed an action (stage", "is added, this page shows"):
        assert claim not in text, claim


def test_the_run_and_its_authorization_page_link_to_each_other(pages):
    """A relative link between pages generated together about the same run (the decision that
    let answer and case link to each other). The link sits inside the viewer's own Policy
    section, under its own marker -- never a name the viewer's page might already carry."""
    policy = re.search(r'<section data-section="policy">(.*?)</section>', pages[CASE], re.S)
    assert policy and 'href="authorization.html"' in policy.group(1)
    assert pages[CASE].count('data-section="authorization-link"') == 1
    assert 'href="case.html"' in pages[AUTHORIZATION]


def test_the_case_page_is_sealed_over_the_link(pages):
    """The link is spliced BEFORE sealing, so the page's own fingerprint covers it."""
    from onetrace_console.viewer import fingerprint
    ok, why = fingerprint.check(pages[CASE].encode("utf-8"))
    assert ok, why


def test_a_case_page_with_no_policy_section_refuses_rather_than_losing_the_link():
    from onetrace_console.authorization import authorization_link
    with pytest.raises(ValueError, match="Policy section"):
        authorization_link("<html><body><main><p>no policy here</p></main></body></html>")


def test_a_marker_outside_the_policy_section_neither_hides_a_missing_section_nor_the_link():
    """Review finding 3: the "already done" guard ran before the Policy check, so a marker
    anywhere on the page skipped both. It is looked for only inside the Policy section."""
    from onetrace_console.authorization import authorization_link
    stale = '<p data-section="authorization-link">stale</p>'
    with pytest.raises(ValueError, match="Policy section"):
        authorization_link(f"<main>{stale}<section data-section=\"incidents\"></section></main>")
    page = authorization_link(f'<main>{stale}<section data-section="policy"><p>x</p></section></main>')
    policy = re.search(r'<section data-section="policy">(.*?)</section>', page, re.S).group(1)
    assert 'href="authorization.html"' in policy


def test_the_page_carries_the_limit_sentence_and_no_control(pages):
    """The five prohibitions run over this page in test_pages.py, with every other run page;
    here, what is particular to it: the limit sentence is on it, and it has no button --
    board 3 draws two, and both are rendered as plain links or not at all."""
    page = pages[AUTHORIZATION].lower()
    assert "<button" not in page and "<form" not in page
    assert "not what was ultimately true" in page, "the limit sentence, as on every run page"


def test_the_page_opens_offline(pages):
    """No external asset of any kind, like every page this console renders. Its one link is the
    console's own stylesheet, served by the console itself."""
    page = pages[AUTHORIZATION]
    assert not re.search(r'(src|href)="(https?:)?//', page)
    assert re.findall(r"<link[^>]*>", page, re.I) == ['<link rel="stylesheet" href="/static/console.css">']
    assert "<script src" not in page.lower()


def test_the_authorization_page_is_a_viewer_page_in_the_role_table(examined):
    from onetrace_console import roles
    examined(1, "GET against the rendered path of a run's authorization page")
    rel = f"runs/{KEY}/authorization.html"
    assert roles.required_role("GET", "/" + rel, rel_for_get=rel) == roles.VIEWER


#: A run key is sha256 hex (`store.run_key`), so the row admits exactly that and nothing else --
#: in particular not `..` (review finding 2: `[^/]+` let `runs/../authorization.html` through
#: to a file at the top of `pages/`).
KEY = "0123456789abcdef" * 4


@pytest.mark.parametrize("rel", [f"runs/{KEY}/authorization.htm",
                                 f"runs/{KEY}/sub/authorization.html",
                                 "authorization.html",
                                 "runs//authorization.html",
                                 "runs/../authorization.html",
                                 "runs/..\\x/authorization.html",
                                 "runs/abc123/authorization.html",
                                 f"runs/{KEY.upper()}/authorization.html",
                                 f"runs/{KEY[:-1]}/authorization.html",
                                 f"runs/{KEY}0/authorization.html"])
def test_near_misses_of_the_new_shape_are_still_refused(rel, examined):
    """The new row is one exact shape: nothing next to it opens with it."""
    from onetrace_console import roles
    examined(1, f"GET against a near miss {rel!r}")
    with pytest.raises(roles.NoRouteTableEntry):
        roles.required_role("GET", "/" + rel, rel_for_get=rel)


def test_ingest_over_http_then_the_authorization_page_is_served(server, files, examined):
    from tests.test_serve import _get, _post
    from tests.conftest import make_tar
    base, store_root = server
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, body
    result = json.loads(body)
    examined(1, "runs ingested over HTTP")
    assert result["pages"]["authorization"] == f"/runs/{result['run_key']}/authorization.html"
    s, page = _get(base, result["pages"]["authorization"])
    assert s == 200, (s, page[:200])
    assert "No authorization records for this run" in page.decode("utf-8")
    assert (store_root / "pages" / "runs" / result["run_key"] / AUTHORIZATION).is_file()
