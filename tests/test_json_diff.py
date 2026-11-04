"""The structured view of a JSON output that changed: added, removed and changed members by path.

1. Members by path, in a stable order: an object's by name, an array's by position; a value of
   another type is changed; a number is kept as written; a name holding `/` or `~` is escaped as
   JSON Pointer escapes it; the heading says numbers are compared as written.
2. Only JSON read strictly: not UTF-8, a repeated name, `NaN` or text that is not JSON is not read,
   and there the text diff stands alone.
3. A value longer than the limit is shown by its digest; past the most members listed, how many more.
4. On recorded runs: a JSON output with an added, a removed and a changed member shows them under its
   text diff on the comparison page and on the text diff's own page; a pair where either output is not
   JSON shows none.
5. On the demo as the public build draws it, the view is under outputs its text diff shows verified,
   and nowhere else.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest

from onetrace_console import json_diff as jd

GENERATED_AT = "2026-09-26T12:00:00+02:00"


def _v(text: str):
    ok, value = jd.parse(text.encode("utf-8"))
    assert ok, text
    return value


def _found(a: str, b: str) -> list[tuple[str, str, str | None, str | None]]:
    """Each member, its values as JSON text, the side it is not on as None (a JSON null is `null`)."""
    return [(op, path, None if op == "added" else jd.text(x), None if op == "removed" else jd.text(y))
            for op, path, x, y in jd.members(_v(a), _v(b))]


def test_members_by_path_in_a_stable_order(examined):
    a = '{"b": 1, "a": {"x": "1", "gone": true}, "list": [1, 2, 3], "t": [1]}'
    b = '{"a": {"x": "2", "new": null}, "b": 1, "list": [1, 5], "t": {"0": 1}}'
    got = _found(a, b)
    examined(len(got), "members")
    assert got == [("removed", "/a/gone", "true", None), ("added", "/a/new", None, "null"),
                   ("changed", "/a/x", '"1"', '"2"'), ("changed", "/list/1", "2", "5"),
                   ("removed", "/list/2", "3", None), ("changed", "/t", "[1]", '{"0":1}')]
    assert _found(b, a) != got and _found(a, b) == got


def test_a_number_is_kept_as_written_and_never_a_float(examined):
    examined(3, "numbers")
    assert _found('{"n": 1.0}', '{"n": 1.00}') == [("changed", "/n", "1.0", "1.00")]
    assert _found('{"n": 1}', '{"n": "1"}') == [("changed", "/n", "1", '"1"')]
    assert not any(isinstance(v, float) for v in _v('{"n": 0.1, "m": [2.5e3]}').values())


def test_the_heading_says_numbers_are_compared_as_written(examined):
    """Under the heading, with members and with none: `1.0` and `1.00` are named as two values."""
    shown = [jd.render(jd.members(_v('{"n": 1.0}'), _v('{"n": 1.00}'))), jd.render([])]
    examined(len(shown), "views")
    for s in shown:
        assert f'<p class="label">{jd.HEADING}</p><p data-json-numbers>{jd.NUMBERS}</p>' in s
    assert jd.NUMBERS == "Numbers are compared as written, so 1.0 and 1.00 differ."


def test_a_name_with_a_slash_or_tilde_is_escaped_and_the_whole_value_has_its_words(examined):
    examined(2, "paths")
    assert _found('{"a/b~c": 1}', '{"a/b~c": 2}') == [("changed", "/a~1b~0c", "1", "2")]
    assert _found("1", "2") == [("changed", "", "1", "2")]
    assert jd.ROOT in jd.render(jd.members(_v("1"), _v("2")))


@pytest.mark.parametrize("data", [b'{"a": 1, "a": 2}', b'{"a": NaN}', b"{'a': 1}", b"plain text",
                                  b'{"a": "\xff"}', b""])
def test_only_json_read_strictly_is_read(data, examined):
    examined(1, "planted bytes")
    assert jd.parse(data) == (False, None)


def test_a_long_value_is_shown_by_its_digest(examined):
    long = "x" * (jd.LIMIT + 1)
    shown = jd.render(jd.members(_v(json.dumps({"k": "short"})), _v(json.dumps({"k": long}))))
    examined(1, "long value")
    assert "short" in shown and long not in shown and "data-json-digest" in shown
    assert f"({jd.LIMIT + 3} characters)" in shown


def test_past_the_most_members_listed_it_says_how_many_more(examined):
    n = jd.MAX_MEMBERS + 7
    shown = jd.render(jd.members(_v("{}"), _v(json.dumps({f"k{i:04d}": i for i in range(n)}))))
    examined(n, "members")
    assert shown.count('data-json-op="added"') == jd.MAX_MEMBERS
    assert jd.MORE.format(n=7) in html.unescape(shown)


def test_sabotage_a_float_reader_reads_two_numbers_as_one(monkeypatch, examined):
    """Read as floats, `1.0` and `1.00` are one value and the change is gone: the reader is what holds it."""
    real = jd.load_json_bounded
    monkeypatch.setattr(jd, "load_json_bounded",
                        lambda text, *a, **k: real(text, *a, **{**k, "parse_float": None, "parse_int": None}))
    examined(1, "the planted pair")
    assert _found('{"n": 1.0}', '{"n": 1.00}') == []


def _run(folder: Path, run_id: str, name: str, data: bytes, media: str) -> Path:
    from onetrace.emit import Instrument, Recorder
    out = folder / run_id
    rec = Recorder(str(out), run_id=run_id, declared_stages=["make"], manifest=Path(__file__),
                   policy="fail-closed", anchor_reason="a test")

    def make(ctx):
        ctx.read_memory(b"the same question", "text/plain", name="question", trust_class="externally-sourced")
        return ctx.write(name, data, media)

    rec.run_node("make", None, Instrument("example-step", "model", "1.0.0", {}), make)
    rec.close()
    return out


A = {"order": "PO-1", "lines": [{"qty": 2, "price": "9.50"}], "note": "first", "status": "open"}
B = {"order": "PO-1", "lines": [{"qty": 3, "price": "9.50"}], "status": "open", "flag": True}


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    from onetrace_console.checks import run_and_record
    from onetrace_console.compare import compare
    from onetrace_console.frame import rendering
    from onetrace_console.render import render_diff
    from onetrace_console.store import Store
    from onetrace_console.textdiff_page import render_text_diff_page
    from tests.test_checks import FIXED_RAN_AT
    from tests.test_compare import _deliver
    folder = tmp_path_factory.mktemp("json-diff")
    s = folder / "s"
    made = {
        "j-a": _run(s, "j-a", "order.json", json.dumps(A, indent=1).encode(), "application/json"),
        "j-b": _run(s, "j-b", "order.json", json.dumps(B, indent=1).encode(), "application/json"),
        "t-a": _run(s, "t-a", "order.txt", b"qty 2\n", "text/plain"),
        "t-b": _run(s, "t-b", "order.txt", b"qty 3\n", "text/plain"),
        "h-a": _run(s, "h-a", "order.json", json.dumps(A).encode(), "application/json"),
        "h-b": _run(s, "h-b", "order.json", b"qty 3, not JSON\n", "application/json"),
    }
    store = Store(folder / "store")
    runs = {k: run_and_record(_deliver(p, store, outputs=True), store, ran_at=FIXED_RAN_AT) for k, p in made.items()}
    pairs = {"json": ("j-a", "j-b"), "text": ("t-a", "t-b"), "half": ("h-a", "h-b")}
    comparisons = {k: compare(runs[a], runs[b], store, ran_at=FIXED_RAN_AT) for k, (a, b) in pairs.items()}
    with rendering(onedoor=False, sign_in=False, public=True):
        pages = {k: render_diff(c, store, generated_at=GENERATED_AT) for k, c in comparisons.items()}
        own = {k: render_text_diff_page(c, store, generated_at=GENERATED_AT) for k, c in comparisons.items()}
    return {"pages": pages, "own": own}


def _members(page: str) -> list[tuple[str, str]]:
    return [(op, html.unescape(re.sub(r"<[^>]+>", "", body)).strip())
            for op, body in re.findall(r'<li data-json-op="([^"]+)">(.*?)</li>', page, re.S)]


WANT = [("removed", '/note removed: "first"'), ("added", "/flag added: true"), ("changed", "/lines/0/qty changed: 2 → 3")]


def test_a_json_output_s_members_are_under_its_text_diff(built, examined):
    page, own = built["pages"]["json"], built["own"]["json"]
    examined(2, "pages")
    for p in (page, own):
        assert sorted(_members(p)) == sorted(WANT)
        assert [m[1].split(" ", 1)[0] for m in _members(p)] == ["/flag", "/lines/0/qty", "/note"]
        assert "1 added · 1 removed · 1 changed" in html.unescape(p)
    text = page[page.index('data-section="text-diff"'):]
    assert text.index("data-hunk") < text.index("data-json-diff")


@pytest.mark.parametrize("pair", ["text", "half"])
def test_where_either_output_is_not_json_the_text_diff_stands_alone(built, pair, examined):
    page = built["pages"][pair]
    examined(1, f"the {pair} pair's page")
    assert 'data-output data-verified="true"' in page and "data-hunk" in page
    assert "data-json-diff" not in page and "data-json-diff" not in (built["own"][pair] or "")


def test_on_the_public_demo_the_view_is_only_under_verified_outputs(shared_demo, examined):
    pages = sorted((shared_demo["folder"] / "store" / "pages" / "diff").glob("*.html"))
    shown = 0
    for p in pages:
        page = p.read_text(encoding="utf-8")
        for at in (m.start() for m in re.finditer("<div data-json-diff>", page)):
            #: The output whose div holds it: the nearest output opened before it.
            opened = re.findall(r'<div data-output data-verified="(true|false)">', page[:at])
            assert opened and opened[-1] == "true", p.name
            shown += 1
    examined(len(pages), "demo comparison pages")
    assert shown > 0
