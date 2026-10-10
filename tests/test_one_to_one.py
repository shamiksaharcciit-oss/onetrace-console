"""one-to-one escaping for a record's words, across the console's pages.

The viewer (canary 93d4d87) shows a backslash already in a word doubled, so a raw control and its
written-out escape no longer draw alike. This redraws the measurement's corpus -- the r11 fixture,
the EXAM reference pair and its comparison, the reviewer's digest pair and the control-character
pair -- with the escaping as it was and as it is, and holds that the only difference anywhere is a
backslash drawn doubled, and that the Diff page's folder labels are unchanged.
"""
from __future__ import annotations

import re

import pytest

from onetrace_console.compare import compare
from onetrace_console.pages import PageError, render_execution
from onetrace_console.render import render_all, render_diff
from tests.test_checks import FIXED_RAN_AT
from tests.test_pages import GENERATED_AT
from tests.test_unreadable import _resummed, _stored

BACKSLASH = chr(92)


def _as_it_was(text, *, lines=False):
    """`viewer.page.display` before 30bj §4: a backslash in a word shown as it is."""
    import onetrace_console.viewer.page as page
    return page._UNSHOWN.sub(
        lambda m: m.group(0) if lines and m.group(0) in "\n\r\t" else f"\\u{ord(m.group(0)):04x}",
        str(text))


def _pages(store, comparisons) -> dict[str, str]:
    out = dict(render_all(store, generated_at=GENERATED_AT))
    for run in store.runs():
        try:
            drawn = render_execution(run, store, generated_at=GENERATED_AT).pages
        except PageError:
            continue                                   # delivered unchecked: no run page
        out.update({f"runs/{run.key[:8]}/{n}": p for n, p in drawn.items()})
    for c in comparisons:
        out[f"diff/{c.key[:8]}"] = render_diff(c, store, generated_at=GENERATED_AT)
    return out


@pytest.fixture
def corpus(tmp_path, store, files):
    from tests.test_compare import RUN_C, RUN_C_POPPLER24, _deliver, _require_exam
    from tests.test_diff_sdk_text_layer import _forged_pair
    from tests.test_round4_recheck_fixes import _sdk_delivery
    _require_exam()
    _stored(_resummed(dict(files)), store)
    comparisons = [compare(_deliver(RUN_C, store), _deliver(RUN_C_POPPLER24, store), store,
                           ran_at=FIXED_RAN_AT)]
    (tmp_path / "forged").mkdir()
    a, b = _forged_pair(tmp_path / "forged")
    comparisons.append(compare(_stored(a, store), _stored(b, store), store, ran_at=FIXED_RAN_AT))
    (tmp_path / "nasty").mkdir()
    na, nb = (_sdk_delivery(tmp_path / "nasty", "a", "1"),
              _sdk_delivery(tmp_path / "nasty", "b", "2"))
    comparisons.append(compare(_stored(na, store), _stored(nb, store), store,
                               ran_at=FIXED_RAN_AT))
    return store, comparisons


def test_the_measured_pages_change_only_where_a_word_holds_a_backslash(corpus, monkeypatch,
                                                                       examined):
    import onetrace_console.viewer.page as page
    store, comparisons = corpus
    now = _pages(store, comparisons)
    monkeypatch.setattr(page, "display", _as_it_was)
    was = _pages(store, comparisons)
    monkeypatch.undo()
    examined(len(now), "pages redrawn")
    assert len(now) >= 40, len(now)
    fingerprint = re.compile(r"<!--fingerprint-->[0-9a-f]{64}<!--/fingerprint-->")
    for name, page_now in now.items():
        if page_now == was[name]:
            continue
        #: The only change allowed: a backslash that was one is now two -- on the lines that
        #: changed. Since 0.2.0 a line can hold two backslashes on both sides (the verifier's own
        #: one-to-one escaping of a record's words, quoted as it wrote it), so the pages are compared
        #: line by line rather than collapsed whole. The fingerprint,
        #: over the page's own bytes, moves with any change and is set aside.
        lines_now = fingerprint.sub("", page_now).split("\n")
        lines_was = fingerprint.sub("", was[name]).split("\n")
        assert len(lines_now) == len(lines_was), name
        from difflib import SequenceMatcher
        for line_now, line_was in zip(lines_now, lines_was):
            if line_now == line_was:
                continue
            #: Within a changed line, character by character: every difference is a backslash
            #: inserted beside one that was there, and nothing is replaced or taken away.
            for tag, i1, i2, j1, j2 in SequenceMatcher(None, line_was, line_now,
                                                       autojunk=False).get_opcodes():
                if tag == "equal":
                    continue
                assert tag == "insert" and set(line_now[j1:j2]) == {BACKSLASH} \
                    and (line_was[i1 - 1:i1] == BACKSLASH or line_was[i1:i1 + 1] == BACKSLASH), \
                    (name, tag, line_was[max(0, i1 - 30):i2 + 30], line_now[max(0, j1 - 30):j2 + 30])
    diffs = [p for n, p in now.items() if n.startswith("diff/")]
    assert diffs and all("the baseline run&#x27;s folder" in p or "the baseline run's folder" in p
                         for p in diffs), "the folder labels are unchanged"


def test_a_record_word_with_a_backslash_is_drawn_doubled_on_home(files, store):
    """The measurement's corpus holds no record word with a backslash; this one does."""
    import json
    from tests.test_unreadable import _renamed
    out = _renamed(files)
    manifest = json.loads(out["MANIFEST.json"].decode("utf-8"))
    manifest["run_id"] = "run" + BACKSLASH + "u000d"
    out["MANIFEST.json"] = json.dumps(manifest).encode("utf-8")
    _stored(_resummed(out), store)
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    assert "run" + BACKSLASH * 2 + "u000d" in home
    assert not re.search("run" + re.escape(BACKSLASH) + "u000d", home.replace(BACKSLASH * 2, ""))


from onetrace_console.render import HOME  # noqa: E402
