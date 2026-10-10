"""The Overview's banner is a statement about the stored runs, from each run's own
"Signed by a known recorder?" rung. Shown only when none reads Yes, in the fixed words:

  "None of these runs is signed by a key you trust: nothing here shows who wrote them."

With one run signed by a trusted key, there is no banner.
"""
from __future__ import annotations

import re
from dataclasses import replace

import pytest

from onetrace_console.render import HOME, render_all
from tests.test_pages import GENERATED_AT

WORDS = "None of these runs is signed by a key you trust: nothing here shows who wrote them."


@pytest.fixture
def stored(store):
    """The exam run, checked (unsigned), and two copies whose signing reading each test sets."""
    from onetrace_console.checks import run_and_record
    from tests.test_checks import FIXED_RAN_AT, _require_installed
    from tests.test_compare import _require_exam
    from tests.test_home_and_diff import RUN_C, _deliver, _fake_run
    _require_installed()
    _require_exam()
    real = run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    made = [_fake_run(store, real, run_id=f"copy-{n}", verdict=real.check_verdict, note=real.check_note)
            for n in (1, 2)]
    return store, real, made


def _banners(store) -> list[str]:
    home = render_all(store, generated_at=GENERATED_AT)[HOME]
    return [re.sub(r"<[^>]+>", "", b).replace("&#x27;", "'")
            for b in re.findall(r'<p data-section="banner">(.*?)</p>', home, re.S)]


def test_with_no_signed_run_the_banner_is_shown(stored):
    store, real, _made = stored
    assert real.signed == "unsigned" and not any(r.signed == "yes" for r in store.runs())
    assert _banners(store) == [WORDS]


def test_with_only_untrusted_signatures_the_banner_is_shown(stored):
    store, _real, made = stored
    for run in made:
        store.put_run(replace(run, signed="untrusted"))
    assert _banners(store) == [WORDS]


def test_with_one_run_signed_by_a_trusted_key_there_is_no_banner(stored):
    store, _real, made = stored
    store.put_run(replace(made[0], signed="untrusted"))
    store.put_run(replace(made[1], signed="yes"))
    assert _banners(store) == []
