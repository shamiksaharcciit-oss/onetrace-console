"""0.9.1's notes say what its code does, read once against the code before the release: each sentence below was found
to say more than the code, or a user-visible change had no sentence, and each is held here beside the code it states.

The section is 0.9.1's: `## [Unreleased]` until its version is set, `## [0.9.1]` after."""

from __future__ import annotations

import re
import string
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent


def _section() -> str:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    start = text.index("## [0.9.1]") if "## [0.9.1]" in text else text.index("## [Unreleased]")
    return text[start : text.index("\n## [", start + 1)]


def _entry(lead: str) -> str:
    m = re.search(rf"^- \*\*{re.escape(lead)}\*\*.*$", _section(), re.M)
    assert m, lead
    return m.group(0)


def test_noise_changes_are_audit_entries_only_with_the_audit_log_on(examined):
    from onetrace_console.config import Config

    entry = _entry("Fields marked as noise.")
    examined(3, "the entry's two sentences and the default")
    assert Config().audit["enabled"] is False
    assert (
        "they are kept in the store beside the pipeline. "
        "With the audit log on, each change is an audit-log entry (`noise.changed`). The page says"
    ) in entry
    assert "a comparison of the pipeline's runs that has a first difference says which fields are marked" in entry


def test_a_static_export_keeps_noise_fields_and_drops_the_noise_page_s_links(examined):
    from onetrace_console import export_static

    entry = _entry("Fields marked as noise.")
    examined(2, "the sentence and the export's rule")
    assert hasattr(export_static, "_NOISE_LINKS")
    assert "A static export keeps them, so its comparisons set them aside as the console's do" in entry


def test_the_fingerprint_s_day_is_the_day_the_later_run_was_received(examined):
    from onetrace_console.fingerprint_change import Change

    after = SimpleNamespace(received_at="2026-11-19T08:00:00Z")
    entry = _entry("The model fingerprint across runs.")
    examined(3, "the day, and the entry's two sentences")
    assert Change(before=None, after=after, step="s", name="n", fields=()).date == "2026-11-19"
    assert "on which day this console received the run where the model identity" in entry
    assert "a field is compared only where both runs state it" in entry


def test_near_outputs_count_only_what_the_section_says_it_counts(examined):
    from onetrace_console.compare_view import NEAR_OUT_LEFT

    counted = {f for _t, f, _s, _c in string.Formatter().parse(NEAR_OUT_LEFT) if f}
    entry = _entry("Runs with near outputs, beside runs with near inputs.")
    examined(2, "the section's counts and the entry")
    assert counted == {"not_kept", "mismatched", "step"}
    assert "a run whose output the embedder gives no vector for is left out too, and isn't counted" in entry


def test_the_seed_the_key_and_p12_s_example_data_as_the_code_shows_them(examined):
    from onetrace_console.demo_store import EXAMPLE_DATA

    examined(3, "the three sentences")
    assert "a seed is shown where both records name `sampling.seed`" in _entry("A model call's own pages.")
    assert "the key by its digest, or as written where the record keeps it so" in _entry("A run's memory.")
    assert "p12" in EXAMPLE_DATA
    assert "Its invoices are the demo's example data" in _entry("P12, an invoice agent, in the demo.")


def test_a_changed_time_and_a_near_run_s_quote_have_their_lines(examined):
    from onetrace_console import compare_view, json_diff

    examined(4, "the time, the rule and their two entries")
    assert json_diff._shown("2026-11-19T10:00:00Z").startswith("<time datetime=")
    assert "shows a changed time as every page shows a time" in _entry("A store read or write shows its digests short.")
    rule = re.search(r"^\.cp \.near-runs li q\{.*$", Path(compare_view.__file__).read_text(encoding="utf-8"), re.M)
    assert rule and "overflow-wrap:anywhere" in rule.group(0)
    assert _entry("A near run's quote wraps on a narrow screen.")


def test_the_envelope_is_the_same_only_over_the_fields_both_records_state(examined):
    from onetrace_console.model_call_pages import SAME_IN

    examined(2, "the sentence and the chip's words")
    assert SAME_IN.startswith("Same, in the {n} of {m} fields both records hold")
    assert (
        "the envelope's model, tokenizer, runtime and settings compared only in the fields both records state, and "
        "said to be the same in how many of them where that is fewer than all"
    ) in _entry("A model call's own pages.")


def test_capture_settings_are_counted_only_where_both_records_state_them(examined):
    from onetrace_console import token_levels

    examined(2, "the entry and the line's words")
    assert token_levels.SETTINGS_SAME.startswith("Capture settings: {n} recorded by both")
    assert "It now counts only the settings both records state" in _entry(
        "Two captures' settings are identical only where both state them."
    )


def test_noise_passes_over_a_step_only_where_nothing_else_the_comparison_reads_differs(examined):
    import inspect

    from onetrace_console import noise

    examined(2, "the sentence and the rule")
    assert "settings" in inspect.signature(noise._noise_only).parameters
    assert (
        "passes over a step only where everything the comparison reads there is the same but those fields: its "
        "recorded settings, its outcome and which outputs it gave, in their order"
    ) in _entry("Fields marked as noise.")
