"""The viewer's four JSON readers apply the console's one depth rule.

A record, a kept report, a `--json` run kept in a check's envelope and a verb's report are each read
through `onetrace_console.bounded_json.load_json_bounded`: a value nested to exactly the rule's
depth is read; one level deeper is refused, and so is a value deeper than `json.loads` itself can
parse; each refusal says the value is nested too deeply, in the reader's own error, never a crash.
"""
from __future__ import annotations

import json

import pytest

from onetrace_console.viewer.depth import MAX_JSON_DEPTH, json_depth


def _nested_to(depth: int) -> str:
    """A JSON object whose measured depth is exactly `depth`."""
    for levels in range(max(depth - 3, 1), depth + 4):
        text = '{"a":' * levels + "1" + "}" * levels
        if json_depth(json.loads(text)) == depth:
            return text
    raise AssertionError(f"no nesting measures {depth}")


AT, PAST = _nested_to(MAX_JSON_DEPTH), _nested_to(MAX_JSON_DEPTH + 1)
#: Past what json.loads can parse on any interpreter the console runs on.
ABYSS = '{"a":' * 100_000 + "1" + "}" * 100_000


def _record(text: str):
    from onetrace_console.viewer.record import _load_json
    return _load_json(text.encode("utf-8"), "MANIFEST.json")


def _kept_report(text: str, tmp_path):
    from onetrace_console.viewer.report import load
    path = tmp_path / "check-report.json"
    path.write_text(text, encoding="utf-8")
    return load(path)


def _json_run(text: str):
    from onetrace_console.viewer.report import _json_doc
    return _json_doc({"stdout": text, "exit_status": "0"}, "check")


def _verb_report(text: str, tmp_path):
    from onetrace_console.viewer.verbs import read_report
    (tmp_path / "diff.json").write_text(text, encoding="utf-8")
    return read_report(tmp_path / "diff.json")


READERS = {
    "a record": lambda text, tmp_path: _record(text),
    "a kept report": _kept_report,
    "a --json run in an envelope": lambda text, tmp_path: _json_run(text),
    "a verb's report": _verb_report,
}


def _refusal(reader, text, tmp_path) -> str:
    try:
        reader(text, tmp_path)
    except Exception as e:  # noqa: BLE001 - the reader's own error is what is read
        assert not isinstance(e, RecursionError), "a crash, not a refusal"
        return str(e)
    return ""


@pytest.mark.parametrize("name", sorted(READERS))
def test_one_level_past_the_rule_is_refused_as_nested_too_deeply(name, tmp_path, examined):
    said = _refusal(READERS[name], PAST, tmp_path)
    examined(1, f"{name} one level past the rule")
    assert "nested too deeply" in said, (name, said)


@pytest.mark.parametrize("name", sorted(READERS))
def test_deeper_than_json_can_parse_is_refused_as_nested_too_deeply(name, tmp_path, examined):
    said = _refusal(READERS[name], ABYSS, tmp_path)
    examined(1, f"{name} past what json.loads parses")
    assert "nested too deeply" in said, (name, said)


@pytest.mark.parametrize("name", sorted(READERS))
def test_exactly_at_the_rule_is_not_refused_for_depth(name, tmp_path, examined):
    """At the rule's depth a value is read; it may still be refused for its shape, never its depth."""
    said = _refusal(READERS[name], AT, tmp_path)
    examined(1, f"{name} at the rule")
    assert "nested too deeply" not in said, (name, said)
