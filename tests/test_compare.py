"""The comparison runner, and candidates from declared fields only.

The runner's checks:
  - a stored report is byte-identical to running `diff` by hand on the same two folders;
  - a pair whose converter versions differ shows *config differs* exactly as the SDK
    annotates it;
  - a refusal is stored and shown, not retried and not replaced.

The candidates' check:
  - the candidates come only from declared fields, and a test fails if a candidate appears
    that shares no declared field.

Every check reports what it examined. The real run pairs come from
the SDK's own exam fixtures in the pinned clone, so the comparisons are over records the SDK
itself ships as its bench.
"""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

from onetrace_console.compare import (COMPARISON_FORMAT, DIFF, LOCALIZE, TIMED_OUT,
                                      StoredComparison, compare, comparison_key,
                                      report_json, report_text, sdk_version)
from onetrace_console.ingest import SUMS_NAME, accept, bundle
from onetrace_console.preview import PREVIEW_FORMAT
from onetrace_console.partners import (MATCHABLE, NO_DECLARED_FIELD, Candidate, candidates,
                                       shared_fields)
from onetrace_console.store import digest
from tests.conftest import preview_veto_off
from tests.test_checks import _require_installed

REPO = Path(__file__).resolve().parent.parent
#: Materialised by `tools/fetch_sdk_fixtures.py` from PyPI's hash-verified
#: sdist, never a git clone. Too large (5.4 MB, 135 files) to commit as the small r11
#: fixture is; see that script's own docstring.
EXAM = REPO / ".sdk-fixtures" / "exam" / "fixtures"

#: Real SDK bench runs. `run_C` and `run_C_poppler24` are the same pipeline through two
#: different pdftotext versions -- the converter-difference pair step 1's second check needs.
RUN_C = EXAM / "ingest-r1" / "run_C"
RUN_C_POPPLER24 = EXAM / "ingest-r1" / "run_C_poppler24"
RUN_B = EXAM / "ingest-r1" / "run_B"

FIXED_AT = "2026-09-26T12:00:00+00:00"


def _require_exam():
    missing = [p.name for p in (RUN_C, RUN_C_POPPLER24, RUN_B) if not p.is_dir()]
    if missing:
        pytest.fail(
            f"the SDK's exam fixtures are not there: {missing} under {EXAM}\n"
            f"    python tools/fetch_sdk_fixtures.py\n"
            f"This refuses rather than skips: these checks exist to compare real records.")


def _deliver(folder: Path, store, *, outputs: bool = False):
    """Ingest a run folder from disk, building the SHA256SUMS a sidecar would. `outputs`: its
    `artifacts/` too, so its check runs with the output files required."""
    manifest = json.loads((folder / "MANIFEST.json").read_bytes().decode("utf-8"))
    files = {"MANIFEST.json": (folder / "MANIFEST.json").read_bytes()}
    for entry in manifest["chain"]:
        files[entry["file"]] = (folder / entry["file"]).read_bytes()
    if outputs:
        for p in sorted((folder / "artifacts").rglob("*")):
            if p.is_file():
                files[p.relative_to(folder).as_posix()] = p.read_bytes()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items()) + "\n").encode("utf-8")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for path, blob in files.items():
            info = tarfile.TarInfo(name=path)
            info.size, info.mtime = len(blob), 0
            tar.addfile(info, io.BytesIO(blob))
    if manifest.get("format") == PREVIEW_FORMAT:
        #: Since the 0.2.0 pin a NEW preview delivery is refused (422). The
        #: exam's 13 preview fixtures stay usable by direct storage -- ingested with that one veto
        #: off, as a run stored before the pin moved was -- because these tests are about what a
        #: console does with a run it already holds (stored preview runs stay).
        with preview_veto_off():
            result = accept(buf.getvalue(), store)
    else:
        result = accept(buf.getvalue(), store)
    assert result.run is not None, getattr(result, "body", result)
    return result.run


@pytest.fixture
def pair(store):
    """run_C and run_C_poppler24, both stored: same pipeline, different converter."""
    _require_installed()
    _require_exam()
    return _deliver(RUN_C, store), _deliver(RUN_C_POPPLER24, store)


# --------------------------------------------------- the runner keeps what the SDK wrote

def test_a_comparison_stores_the_reports_the_sdk_wrote(pair, store, examined):
    a, b = pair
    c = compare(a, b, store, ran_at=FIXED_AT)
    assert isinstance(c, StoredComparison)
    examined(len(c.verbs), "verb runs stored")
    #: The text diff is a stored run of its own beside diff and localize.
    from onetrace_console.compare import TEXT_DIFF
    assert {v.verb for v in c.verbs} == {DIFF, LOCALIZE, TEXT_DIFF}

    total_reports = 0
    for v in c.verbs:
        assert v.exit_status != "", f"{v.verb} recorded no exit status: {v.note}"
        #: Run through this interpreter, and recorded as `python`: no path of this machine is kept.
        assert v.command[0] == "python", "the verb's interpreter is recorded by a path"
        total_reports += len(v.reports)
        for name, key in v.reports:
            assert store.has(key), f"{v.verb}/{name} is not in the store"
    examined(total_reports, "report files kept, across both verbs")
    assert f"{DIFF}.txt" in c.verb(DIFF).report_names, c.verb(DIFF).report_names
    assert f"{DIFF}.json" in c.verb(DIFF).report_names


def test_the_stored_report_is_byte_identical_to_running_diff_by_hand(pair, store, tmp_path,
                                                                    examined):
    """Step 1's first check, and the comparison is made by a separate process.

    `diff` is run by hand over the same two materialised folders, and its `diff.txt` and
    `diff.json` are compared byte for byte with what the runner stored.
    """
    a, b = pair
    #: `work_root` is named so the by-hand run can use the SAME TWO FOLDERS. The SDK's
    #: reports record the input paths, so byte-identity across two different temp
    #: directories is not a property anything has -- which is why the order says "on the
    #: same two folders". The first version of this test used fresh copies and failed on
    #: a path inside `diff.json`, which was the report being accurate.
    work = tmp_path / "work"
    c = compare(a, b, store, ran_at=FIXED_AT, work_root=work)

    #: The two folders the runner itself laid out, read as it left them: a run's files are
    #: never written a second time over the same folder.
    folder_a, folder_b = work / "a", work / "b"
    assert (folder_a / "MANIFEST.json").is_file() and (folder_b / "MANIFEST.json").is_file()
    #: As the runner runs it: from the work folder, every folder named relative to it, the
    #: verifier its copy beside the runs.
    out = work / "byhand"
    proc = subprocess.run([sys.executable, "-m", "onetrace", DIFF, "a", "b", "--verifier", "verifier",
                           "--out", "byhand"], capture_output=True, cwd=work)
    assert c.verb(DIFF).command[4:] == ("a", "b", "--verifier", "verifier", "--out", "out-diff")
    assert out.is_dir(), f"diff wrote nothing by hand: {proc.stderr[-400:]!r}"

    by_hand = {p.relative_to(out).as_posix(): p.read_bytes()
               for p in sorted(out.rglob("*")) if p.is_file()}
    examined(len(by_hand), "report files produced by hand")
    stored = {name: store.get(key) for name, key in c.verb(DIFF).reports}
    assert set(stored) == set(by_hand), (
        f"stored {sorted(stored)} against by-hand {sorted(by_hand)}")
    for name in sorted(by_hand):
        assert stored[name] == by_hand[name], f"{name} differs from the by-hand run"


def test_the_converter_difference_is_shown_exactly_as_the_sdk_annotates_it(pair, store,
                                                                          examined):
    """Step 1's second check. The SDK's words, not a sentence of ours about config.

    Worth stating what the SDK actually says, because it is not what a reader might expect:
    the envelope is **identical**, since verdicts are on outputs, and the converter
    difference appears as an **annotation** on the stage it belongs to. The console shows
    that as written and does not promote it to a verdict.
    """
    a, b = pair
    c = compare(a, b, store, ran_at=FIXED_AT)
    text = report_text(c, DIFF, store)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    examined(len(lines), "lines of the SDK's diff report")

    annotations = [ln for ln in lines if "pdf_converter_version" in ln or "config_digest" in ln]
    examined(len(annotations), "annotation lines naming the converter or its config digest")
    assert any("pdf_converter_version" in ln for ln in annotations), text[-600:]
    assert "annotation at stage" in text, "the SDK's annotation heading is not on the report"

    #: The console must not have turned an annotation into a verdict.
    assert "diff: identical" in text, (
        "the SDK no longer calls this pair identical; if its verdicts moved, the page's "
        "wording follows it rather than this test being relaxed")


def test_the_two_runs_really_do_differ_only_in_their_converter(pair, store, examined):
    """The premise of the check above, measured rather than taken from a fixture's name."""
    a, b = pair
    c = compare(a, b, store, ran_at=FIXED_AT)
    report = report_json(c, DIFF, store)
    assert report is not None, "the SDK wrote no diff.json"
    examined(len(report), "top-level members of the SDK's diff.json")
    text = report_text(c, DIFF, store)
    verdict_lines = [ln for ln in text.splitlines() if ln.strip().endswith("same")]
    examined(len(verdict_lines), "stages the SDK reports as `same`")
    assert verdict_lines, text[:600]


# ----------------------------------------------------------------- the key, and caching

def test_a_repeated_request_returns_the_stored_comparison(pair, store, examined):
    a, b = pair
    first = compare(a, b, store, ran_at=FIXED_AT)
    before = len(store.comparisons())
    second = compare(a, b, store, ran_at="2026-09-27T00:00:00+00:00")
    examined(len(store.comparisons()), "comparisons in the store after a repeat")
    assert second.key == first.key
    assert second.ran_at == first.ran_at, "the repeat re-ran instead of returning the stored one"
    assert len(store.comparisons()) == before


def test_the_key_carries_the_sdks_build_identity(pair, store, examined):
    """Four components, and the build digest is one of them."""
    from onetrace_console.compare import sdk_build_digest, sdk_distribution_version

    a, b = pair
    c = compare(a, b, store, ran_at=FIXED_AT)
    parts = (digest(bundle(a, store)), digest(bundle(b, store)),
             sdk_distribution_version(), sdk_build_digest())
    examined(len(parts), "components of the comparison key")
    assert c.key == comparison_key(*parts)
    assert c.bundle_sha_a == parts[0] and c.bundle_sha_b == parts[1]
    assert c.sdk_distribution_version == parts[2]
    assert c.sdk_build_digest == parts[3]


def test_the_build_digest_names_which_kind_of_identity_it_is(examined):
    """`wheel:<sha256>` since the SDK is pinned as a wheel; `commit:<sha>` was the case before it.

    Labelled rather than a bare hex string, so a reader of a stored comparison does not have
    to guess which kind they are looking at — and so reports written before the wheel arrived
    stay distinguishable from ones written after.
    """
    from onetrace_console.compare import sdk_build_digest

    got = sdk_build_digest()
    examined(1, "build digest")
    kind, _, value = got.partition(":")
    assert kind in ("commit", "wheel"), got
    assert value, got
    assert kind == "wheel", (
        f"the SDK is now identified as {kind!r}, not 'wheel'. The console pins onetrace by hash "
        f"from PyPI and removes the PYTHONPATH clone; a 'commit' result here means the "
        f"install report is missing or the SDK is still on PYTHONPATH — install with "
        f"`python tools/install_pinned.py`, not a bare `pip install` or a clone.")
    from tests.test_pins import ONETRACE_WHL_SHA256
    assert value == ONETRACE_WHL_SHA256, (
        f"the wheel hash is {value!r}, not the pinned onetrace wheel's {ONETRACE_WHL_SHA256} — "
        f"requirements.lock and this assertion have drifted apart")


def test_the_distribution_version_is_readable_since_the_sdk_is_installed(examined):
    """Before the SDK was pinned as a wheel, `importlib.metadata` had nothing to say while
    it was on PYTHONPATH, and the empty string was the honest answer, recorded rather than
    invented. Since then the SDK is a real installed distribution, so the version is readable, and
    an empty string here would now be the thing needing an explanation.
    """
    from onetrace_console.compare import sdk_distribution_version

    examined(1, "distribution version read")
    got = sdk_distribution_version()
    assert got != "", (
        "sdk_distribution_version() is empty, so importlib.metadata cannot see `onetrace` "
        "as an installed distribution — install with `python tools/install_pinned.py`, not "
        "PYTHONPATH against a clone.")
    from tests.test_pins import PINNED_SDK_VERSION
    assert got == PINNED_SDK_VERSION, f"distribution version is {got!r}, not the pinned {PINNED_SDK_VERSION}"


def test_a_key_without_a_build_digest_is_refused(examined):
    from onetrace_console.compare import ComparisonError

    examined(1, "key computed without a build digest")
    with pytest.raises(ComparisonError, match="needs the SDK's build digest"):
        comparison_key("a" * 64, "b" * 64, "0.1.0", "")


def test_a_stored_comparison_with_no_build_digest_is_recomputed(pair, store, examined):
    """A report with no build digest is unkeyed.

    A record written under the old three-part key must still LOAD — otherwise it cannot be
    recognised as unkeyed — and then be replaced rather than returned.
    """
    from dataclasses import replace

    a, b = pair
    first = compare(a, b, store, ran_at=FIXED_AT)
    store.put_comparison(replace(first, sdk_build_digest=""))
    examined(1, "stored comparison stripped of its build digest")
    again = compare(a, b, store, ran_at="2026-09-30T00:00:00+00:00")
    assert again.ran_at != first.ran_at, "an unkeyed comparison was handed back"
    assert again.sdk_build_digest, "the recomputed comparison has no build digest either"


def test_the_order_of_the_pair_changes_the_key(pair, store, examined):
    """A is the baseline and B the candidate. Swapping them is a different comparison,
    because the SDK's own report is directional, and a key that collapsed them would hand
    back a report with the runs the other way round."""
    a, b = pair
    forward = compare(a, b, store, ran_at=FIXED_AT)
    backward = compare(b, a, store, ran_at=FIXED_AT)
    examined(2, "orderings of the same pair")
    assert forward.key != backward.key


def test_a_stored_comparison_whose_build_digest_disagrees_with_the_key_is_recomputed(
        pair, store, examined):
    """The `other_build` branch, exercised directly rather than assumed correct alongside
    its sibling `unkeyed` branch above.

    `build_digest` **is** one of `comparison_key`'s four inputs, so
    changing it changes the key -- a monkeypatched `sdk_build_digest()` produces a
    DIFFERENT key outright, a plain cache miss that says nothing about this branch
    specifically. (That was this test's first draft, and it failed for exactly that
    reason: the key it expected to stay fixed did not.) To exercise `other_build` -- a
    stored record found AT THE CURRENT KEY whose own `sdk_build_digest` field nonetheless
    disagrees with what is running now -- the record has to be forged directly, the same
    way `test_a_stored_comparison_with_no_build_digest_is_recomputed` (above) forges an
    unkeyed one. In real use this shape means a stored comparison surviving underneath an
    environment whose installed wheel changed without the pinned commit/version changing
    with it: a same-version rebuild, or direct tampering with the store.
    """
    from dataclasses import replace

    a, b = pair
    first = compare(a, b, store, ran_at=FIXED_AT)
    forged = replace(first, sdk_build_digest="wheel:" + "0" * 64)
    store.put_comparison(forged)
    examined(1, "stored comparison whose build digest disagrees with the current build")
    assert store.get_comparison(first.key).sdk_build_digest != first.sdk_build_digest, (
        "the forged record and the real one must actually differ, or this proves nothing")

    again = compare(a, b, store, ran_at="2026-09-28T00:00:00+00:00")
    assert again.ran_at != forged.ran_at, (
        "a comparison whose build digest disagreed with the current build was handed back")
    assert again.sdk_build_digest == first.sdk_build_digest, (
        "the recomputed comparison should report the REAL current build, not the forged one")


def test_the_sdk_version_now_moves_with_the_release(examined):
    """It happened: this test used to assert `0.0.1` and name what to remove when it moved.

    `__version__` was fixed to read back from the installed distribution's own metadata
    rather than a hand-maintained constant, and the PyPI 0.1.0 release is the first pin
    where that fix is live: `onetrace.__version__` now reads `0.1.0`, in step with the
    distribution version, instead of the stale `0.0.1` both of this console's earlier
    pins carried.

    The question this docstring used to ask -- whether `sdk_source_digest`'s cache-validity
    role was now redundant with the key's own `build_digest` -- is answered: yes, and it is
    removed (see `test_a_changed_build_digest_invalidates_a_
    cache_hit`, above, and `compare.py`'s own module docstring).
    """
    version = sdk_version()
    examined(1, "SDK version read")
    from tests.test_pins import PINNED_SDK_VERSION
    assert version == PINNED_SDK_VERSION, (
        f"the SDK reports {version!r}, not the pinned build's own version {PINNED_SDK_VERSION}")


# ------------------------------------------------- a refusal is stored, not retried

def test_a_refusal_is_stored_and_shown_in_the_sdk_s_own_words(store, tmp_path, examined):
    """Step 1's third check. Two runs of different shapes cannot be aligned.

    `ingest-r1/run_C` has nine linear stages; `dag-r37/run_R` is a three-node topology under a
    different pipeline. The SDK is the thing that decides they cannot be compared, and
    whatever it says is what is stored and shown.
    """
    _require_installed()
    _require_exam()
    other = EXAM / "dag-r37" / "run_R"
    if not other.is_dir():
        pytest.fail(f"the dag-r37 fixture is not there: {other}")

    a = _deliver(RUN_C, store)
    b = _deliver(other, store)
    c = compare(a, b, store, ran_at=FIXED_AT)
    examined(len(c.verbs), "verb runs over an unalignable pair")

    shown = {v.verb: report_text(c, v.verb, store) for v in c.verbs}
    for verb, text in shown.items():
        examined(len([ln for ln in text.splitlines() if ln.strip()]),
                 f"lines the SDK wrote for {verb}")
        assert text.strip(), f"{verb} produced nothing at all, so nothing is shown"

    #: Whatever the SDK decided, it is recorded verbatim and the runner added no verdict.
    for v in c.verbs:
        assert v.exit_status != "", f"{v.verb} did not finish: {v.note}"
        assert v.note == "", f"{v.verb} recorded a runner note rather than an SDK answer: {v.note}"


def test_a_refusal_is_not_re_run_on_a_repeat(store, examined):
    _require_installed()
    _require_exam()
    a = _deliver(RUN_C, store)
    b = _deliver(EXAM / "dag-r37" / "run_R", store)
    first = compare(a, b, store, ran_at=FIXED_AT)
    second = compare(a, b, store, ran_at="2026-09-29T00:00:00+00:00")
    examined(len(store.comparisons()), "comparisons stored after repeating a refusal")
    assert second.ran_at == first.ran_at, "the refusal was re-run instead of returned"


def test_a_timeout_is_the_runners_failure_and_never_a_verdict(pair, store, monkeypatch,
                                                              examined):
    """A timeout means no answer was obtained. It must not read as the SDK saying anything."""
    import onetrace_console.compare as mod

    real_run = mod.subprocess.run

    def times_out_for_the_verb_only(command, *a, **kw):
        #: Only the verb times out. `sdk_build_digest()` also shells out — to `git`, for the
        #: pinned commit — and a blanket patch made THAT raise, so the test failed for a
        #: reason that had nothing to do with the verb. Narrowed to what it means to break.
        if command and str(command[0]) == "git":
            return real_run(command, *a, **kw)
        raise subprocess.TimeoutExpired(cmd="onetrace diff", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", times_out_for_the_verb_only)
    a, b = pair
    c = compare(a, b, store, ran_at=FIXED_AT, force=True, timeout=1)
    examined(len(c.verbs), "verb runs that timed out")
    for v in c.verbs:
        assert TIMED_OUT in v.note, v.note
        assert v.exit_status == "", "a timeout recorded an exit status it never saw"
        assert not v.refused, "a timeout was recorded as the SDK refusing"


# --------------------------------------------- step 2: candidates from declared fields

def test_candidates_share_at_least_one_declared_field(pair, store, examined):
    a, b = pair
    found = candidates(a, store)
    examined(len(found), "candidate partners offered")
    assert found, "run_C and run_C_poppler24 declare the same pipeline; expected a candidate"
    for c in found:
        assert c.shared, f"{c.run.run_id} was offered with no shared field"
        assert set(c.shared) <= set(MATCHABLE), c.shared
        assert shared_fields(a, c.run) == c.shared, "the label is not what the runs share"
        assert c.labels and all(lbl for lbl in c.labels)


def test_no_candidate_is_offered_that_shares_no_declared_field(store, examined):
    """Step 2's check, stated as the failure it guards.

    Two runs of genuinely different pipelines share no declared field, so neither may appear
    as a candidate for the other.
    """
    _require_installed()
    _require_exam()
    a = _deliver(RUN_C, store)
    b = _deliver(EXAM / "dag-r37" / "run_R", store)
    pairs = ((a, b), (b, a))
    examined(len(pairs), "directions checked")
    for one, other in pairs:
        assert shared_fields(one, other) == (), (
            f"{one.run_id} and {other.run_id} are held to share "
            f"{shared_fields(one, other)}")
        offered = [c.run.run_id for c in candidates(one, store)]
        assert other.run_id not in offered, (
            f"{other.run_id} was offered as a candidate for {one.run_id} while sharing "
            f"no declared field")


def test_a_run_alone_in_the_store_gets_no_candidates_and_an_absence_sentence(store,
                                                                            examined):
    _require_installed()
    _require_exam()
    a = _deliver(RUN_C, store)
    found = candidates(a, store)
    examined(len(store.runs()), "runs in the store")
    assert found == (), f"a lone run was offered candidates: {found}"
    assert NO_DECLARED_FIELD, "there is no absence sentence to show"


def test_a_field_both_runs_leave_empty_is_not_a_match(pair, store, examined):
    """Two runs that both declare nothing have nothing in common.

    Treating an absence as a match is how a list of everything gets presented as a list of
    relatives — and it is the same shape as the blank-versus-absence rule.
    """
    from dataclasses import replace
    a, b = pair
    blanked_a = replace(a, pipeline="", declared_stages=(), run_id="x")
    blanked_b = replace(b, pipeline="", declared_stages=(), run_id="y")
    examined(len(MATCHABLE), "matchable fields, each blanked on both runs")
    assert shared_fields(blanked_a, blanked_b) == ()


def test_candidates_are_not_ordered_by_how_much_they_share(pair, store, examined):
    """Ordered by run id, a stable name. "3 fields in common" sorted to the top is a
    similarity score with the number filed off.

    **Two candidates, sharing different numbers of fields, with ids that order the opposite
    way.** The first version of this test had one candidate, so any order was sorted and it
    passed while the mutation that sorts by share-count went undetected — a check that could
    not fail. Found by sabotaging it.
    """
    from dataclasses import replace

    a, _ = pair
    #: One candidate shares TWO declared fields with `a` (its run name and its stages); the
    #: other shares ONE (the stages), under a name that sorts first. By run id the second
    #: comes first; by how much is shared the first would. **The two orders disagree**, which
    #: is the only arrangement in which this assertion can fail. (The stored `pipeline`
    #: digest is out of the matchable fields, so only two remain.)
    one_field = "0000-one-field"
    assert a.run_id > one_field, "the orders would agree, and the check could not fail"
    store.put_run(replace(a, key="f" * 64))
    store.put_run(replace(a, key="e" * 64, run_id=one_field))

    found = [c for c in candidates(a, store)
             if c.run.key in ("f" * 64, "e" * 64)]
    examined(len(found), "candidates whose order is checked")
    assert len(found) >= 2, (
        f"only {len(found)} candidate(s); with fewer than two, any order is sorted and this "
        f"test cannot fail")
    counts = {c.run.run_id: len(c.shared) for c in found}
    assert len(set(counts.values())) > 1, (
        f"every candidate shares the same number of fields ({counts}), so a share-count "
        f"ordering is indistinguishable from an id ordering here")

    ids = [c.run.run_id for c in found]
    assert ids == sorted(ids), f"candidates are not in run-id order: {ids}"
    assert ids[0] == one_field


def test_the_matchable_fields_are_all_declared_by_the_emitter(examined):
    """None of them is something this console inferred, counted or derived.

    `received_at` is the one deliberately absent: two runs arriving close together share
    nothing about themselves, and time-proximity is the first thing that becomes a similarity
    score when nobody is looking.
    """
    examined(len(MATCHABLE), "matchable fields declared")
    #: `pipeline` left the set: the stored field stays unread.
    assert set(MATCHABLE) == {"run_id", "declared_stages"}
    assert "received_at" not in MATCHABLE
    for field, label in MATCHABLE.items():
        assert "score" not in label.lower() and "%" not in label
        assert label.startswith("the same "), label


def test_the_comparison_format_is_named():
    assert COMPARISON_FORMAT == "onetrace-console/comparison/0.1"
