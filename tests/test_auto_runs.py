"""Zero-configuration runs (onetrace-auto, onetrace 0.7) open: the run page shows the libraries the run
hooked and their versions, the boundaries of what it saw, and each gap where a call went ahead
unrecorded, in the record's own words, and onetrace-verify's own rows about them.

The runs are `tests/onetrace_runs/0.7.1/auto-orders` and `auto-bound` (`tests/test_onetrace_runs.py`):
the second's store bound is reached at its second call, so its manifest and its close receipt hold a gap.
"""
from __future__ import annotations

import html
import json
import re

import pytest

from tests.test_format_04 import RUNS, _pages

AUTO = RUNS / "0.7.1"


@pytest.fixture(scope="module", autouse=True)
def _installed():
    from tests.test_checks import _require_installed
    _require_installed()


def _manifest(name: str) -> dict:
    return json.loads((AUTO / name / "MANIFEST.json").read_text(encoding="utf-8"))


def _section(page: str) -> str:
    m = re.search(r'<section data-section="auto".*?</section>', page, re.S)
    return m.group(0) if m else ""


def _text(block: str) -> str:
    inline = re.sub(r"</?(?:span|code|strong)\b[^>]*>", "", block)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", inline))).strip()


def _drawn(name: str, tmp_path):
    from onetrace_console.store import Store
    run, pages = _pages(AUTO / name, Store(tmp_path / name))
    return run, {k: v for k, v in pages.items() if k != "the run list"}


@pytest.mark.parametrize("name", ("auto-orders", "auto-bound"))
def test_a_zero_configuration_run_s_page_shows_its_hooks_in_the_record_s_words(name, tmp_path, examined):
    run, pages = _drawn(name, tmp_path)
    hooks = _manifest(name)["auto"]["hooks"]
    examined(len(hooks), f"hooks of {name}")
    shown = [_section(p) for p in pages.values() if _section(p)]
    assert shown, f"no zero-configuration section on {sorted(pages)}"
    text = _text(shown[0])
    for h in hooks:
        line = " ".join(filter(None, (h["library"], h.get("version"), "—", h["status"])))
        assert line in text, (line, text)
    assert f'Boundary: {_manifest(name)["auto"]["boundary"]}' in text, text
    for b in _manifest(name).get("boundaries") or []:
        assert f'{b["name"]} — {b["kind"]}: {b["note"]}' in text, (b, text)


def test_a_run_s_gap_is_shown_once_in_the_record_s_words(tmp_path, examined):
    """auto-bound's gap is in its manifest and in its close receipt: shown once, as the record says it."""
    _run, pages = _drawn("auto-bound", tmp_path)
    (gap,) = _manifest("auto-bound")["gaps"]
    close = json.loads((AUTO / "auto-bound" / _manifest("auto-bound")["chain"][-1]["file"]).read_text(encoding="utf-8"))
    examined(2, "places the record holds its gap")
    assert gap in close["emission"]["gaps"], close["emission"]
    text = _text(next(_section(p) for p in pages.values() if _section(p)))
    line = f'{gap["stage"]} #{gap["index"]} — {gap["reason"]}'
    assert text.count(line) == 1, text
    assert "The record names no gap." not in text


def test_a_run_with_no_gap_says_so(tmp_path, examined):
    _run, pages = _drawn("auto-orders", tmp_path)
    examined(1, "a zero-configuration run with no gap")
    assert "The record names no gap." in _text(next(_section(p) for p in pages.values() if _section(p)))


@pytest.mark.parametrize("name", ("auto-orders", "auto-bound"))
def test_the_verifier_s_auto_rows_are_listed_and_records_agree_is_checked(name, tmp_path, examined):
    """onetrace-verify's `auto:` rows are about the run as a whole: listed in the section, each as the
    verifier wrote it, and never read as rows about something not in this run. auto-orders, whose
    every row holds, reads "Records agree" as any run the check holds; auto-bound keeps no outputs,
    and the verifier's NOT-RUN on its step's status output is read as any step's NOT-RUN is."""
    run, pages = _drawn(name, tmp_path)
    from onetrace_console import auto_panel
    from onetrace_console.home import _envelope
    from onetrace_console.store import Store
    rows = auto_panel.rows(_envelope(run, Store(tmp_path / name)))
    examined(len(rows), f"onetrace-verify's auto rows on {name}")
    assert rows and all(r["result"] == "PASS" for r in rows), rows
    text = _text(next(_section(p) for p in pages.values() if _section(p)))
    for r in rows:
        assert f'{r["result"]} {r["name"]}' in text, (r, text)
    assert not any("not in this run" in _text(p) for p in pages.values())
    if name == "auto-orders":
        assert run.agree == "yes", (run.agree, run.agree_why)
        assert not any("couldn't check" in _text(p) for p in pages.values())
    else:
        assert "HTTP step's status output -- the output was not kept" in "".join(_text(p) for p in pages.values())


def test_a_decorated_run_has_no_zero_configuration_section(tmp_path, examined):
    _run, pages = _drawn("refund-closed", tmp_path)
    examined(len(pages), "pages of a decorated 0.4 run")
    assert not any(_section(p) for p in pages.values())


def test_sabotage_a_hook_s_version_left_out_is_named(tmp_path, examined, monkeypatch):
    from onetrace_console import auto_panel
    real = auto_panel.run_section

    def without_versions(manifest, receipts, envelope):
        m = json.loads(json.dumps(manifest))
        for h in (m.get("auto") or {}).get("hooks") or []:
            h.pop("version", None)
        return real(m, receipts, envelope)
    monkeypatch.setattr(auto_panel, "run_section", without_versions)
    examined(1, "a section drawn without versions")
    with pytest.raises(AssertionError):
        test_a_zero_configuration_run_s_page_shows_its_hooks_in_the_record_s_words("auto-orders", tmp_path, lambda *a: None)
