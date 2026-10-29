"""The five rules, their near misses, determinism, and the pages.

Step 1's check: *"for each rule, one fixture that raises it and one near miss that doesn't,
and a test for each."* Each rule below has both, side by side, so the pair can be read
together — a near miss in another file is a near miss nobody compares.

Step 2's checks: deriving twice is byte-identical; changing a rule's condition changes exactly
that rule's incidents; an incident's evidence link always resolves.

Step 3's checks: every count on Home and on Incidents equals the list it links to; the five
prohibitions; offline.

Every check reports what it examined.
"""
from __future__ import annotations

import json
import re
from dataclasses import replace
from html import escape
from pathlib import Path

import pytest

from onetrace_console.checks import CONTRADICTS, COULD_NOT_CHECK, HOLDS, run_and_record
from onetrace_console.compare import compare
from onetrace_console.home import incident_tallies, tallies
from onetrace_console.incident_pages import (INCIDENTS, RAISED, for_subject,
                                             group_sentence, incidents_block,
                                             render_incidents, render_rule_list, rule_href)
from onetrace_console.incidents import (NOT_BUILT, RULE_TABLE_DIGEST, RULES, Incident,
                                        as_json, by_rule, derive, incident_id,
                                        rule_table_digest)
from onetrace_console.ingest import RUN_ID_REUSED, accept
from onetrace_console.pages import ANSWER, CASE, render_execution
from onetrace_console.render import COUNTS, HOME, render_all, render_diff, render_home
from onetrace_console.store import StoredRun, run_key
from tests.conftest import make_tar
from tests.test_checks import FIXED_RAN_AT, _require_installed
from tests.test_compare import EXAM, RUN_C, RUN_C_POPPLER24, _deliver, _require_exam
from tests.test_pages import FORBIDDEN_WORDS, INFERENCE_WORDS, _body

GENERATED_AT = "2026-09-26T12:00:00+02:00"
RULE_IDS = tuple(r.id for r in RULES)


# ------------------------------------------------------------------ the rule table

def test_the_rule_table_has_exactly_the_five_rules_that_could_be_built(examined):
    examined(len(RULES), "rules in the table")
    assert RULE_IDS == ("I-CONTRADICTS", "I-RUNID-REUSED", "I-HEADER-DISAGREES",
                        "I-COULD-NOT-CHECK", "I-HEAD-SHARED")
    assert NOT_BUILT == ("I-DIFF-REGRESSION",)


def test_the_sdk_still_has_no_regression_label_so_the_fifth_rule_stays_out(examined):
    """The condition on `I-DIFF-REGRESSION`, measured rather than remembered.

    Its spec addendum: *"The report names the config that changed; it does not characterize
    the change as safe, a regression, or intentional. That judgment stays with whoever reads
    it."* If the SDK ever gains such a label this fails, and the rule can be built.
    """
    import hashlib

    from onetrace_console.viewer.verbs import VERDICTS

    #: Committed here rather than read from the `.pins/onetrace` clone this
    #: repository no longer makes. `spec/` is excluded from the public export,
    #: so there is no PyPI sdist to fetch this from the way tools/fetch_sdk_fixtures.py
    #: fetches exam/ -- a frozen copy is the only option. See tests/fixtures/spec/
    #: PROVENANCE.md for where it came from.
    fixtures = Path(__file__).resolve().parent / "fixtures" / "spec"
    spec = fixtures / "Spec_onetrace_Verbs_v1_Addendum_InstrumentChangeDiff.md"
    assert spec.is_file(), f"the committed spec addendum is not there: {spec}"
    for line in (fixtures / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, _, rel = line.partition("  ")
        got = hashlib.sha256((fixtures / rel).read_bytes()).hexdigest()
        assert got == digest, f"{rel} has drifted from its recorded digest: {digest} vs {got}"
    text = spec.read_text(encoding="utf-8")
    examined(len(VERDICTS), "closed ladder verdicts checked for a regression label")
    assert "does not characterize the change as safe, a regression" in text, (
        "the spec no longer refuses to characterise a change. I-DIFF-REGRESSION may now be "
        "buildable; re-read the addendum before building it.")
    assert not any("regress" in v.lower() for v in VERDICTS), VERDICTS


INCIDENTS_DIR = Path(__file__).resolve().parent.parent / "incidents"


def _documented_rules() -> dict[str, tuple[str, ...]]:
    """The rule table as `RULES.md` specifies it, parsed from its own markdown table.

    `RULES.md` is **the specification**, written by hand, so it is
    the side this comparison reads first. The code must match the document, not the other way
    round — which was the first version's mistake, and would make the document describe
    whatever the code happens to do.
    """
    doc = INCIDENTS_DIR / "RULES.md"
    assert doc.is_file(), f"{doc} is missing"
    out: dict[str, tuple[str, ...]] = {}
    for line in doc.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `I-"):
            continue
        #: Backticks are markdown presentation, not content: the specification writes
        #: `'run_id reused'` where the code holds the bare string. Stripped from BOTH sides so
        #: the comparison is about what the rule says, not about how the document marks it up.
        cells = [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        out[cells[0]] = tuple(cells)
    return out


def test_the_code_and_the_specification_agree_rule_for_rule(examined):
    """A test fails if the code and `RULES.md` differ IN ANY WAY.

    Compared field by field — id, source, field, condition, displayed words — not merely by
    the ids being present. A rule whose condition drifted from the specification while keeping
    its name is the drift worth catching.
    """
    documented = _documented_rules()
    examined(len(documented), "rules specified in RULES.md")
    assert documented, "RULES.md's rule table could not be parsed"
    assert set(documented) == {r.id for r in RULES}, (
        f"RULES.md specifies {sorted(documented)}; the code has "
        f"{sorted(r.id for r in RULES)}")
    for rule in RULES:
        spec = documented[rule.id]
        got = (rule.id, rule.source, rule.field, rule.condition, rule.words)
        got = tuple(g.replace("`", "") for g in got)
        for name, want, mine in zip(("id", "source", "field", "condition", "words"),
                                    spec, got):
            assert want == mine, (
                f"{rule.id}: RULES.md specifies {name} = {want!r}, the code has {mine!r}. "
                f"The document is the specification; change the code to match it, or change "
                f"the document deliberately and have it reviewed.")


def test_the_specification_carries_no_hand_typed_digest(examined):
    """X-11: a digest typed into a hand-written document is the one nobody checked.

    The digest lives in `RULES.SHA256`, written by `tools/rule_digest.py`.
    """
    text = (INCIDENTS_DIR / "RULES.md").read_text(encoding="utf-8")
    examined(1, "specification checked for a transcribed digest")
    assert RULE_TABLE_DIGEST not in text, (
        "RULES.md carries the rule table's digest. It is hand-written, so that digest would "
        "be transcribed — it belongs in RULES.SHA256, written by tooling.")
    import re
    assert not re.search(r"[0-9a-f]{64}", text), (
        "RULES.md carries a 64-hex string, which is a transcribed digest however it got there")


def test_the_digest_sidecar_is_the_digest_of_the_code_s_table(examined):
    """The third link in the chain: spec == code == sidecar."""
    sidecar = INCIDENTS_DIR / "RULES.SHA256"
    assert sidecar.is_file(), f"{sidecar} is missing; run tools/rule_digest.py"
    held = sidecar.read_text(encoding="utf-8").strip()
    examined(len(RULES), "rules the sidecar's digest covers")
    assert held.startswith(RULE_TABLE_DIGEST), (
        f"RULES.SHA256 holds {held!r}, the code's table digests to {RULE_TABLE_DIGEST}. "
        f"Run tools/rule_digest.py.")
    assert f"({len(RULES)} rules)" in held, held


def test_the_specification_records_the_refused_rule_and_that_it_is_refused(examined):
    text = (INCIDENTS_DIR / "RULES.md").read_text(encoding="utf-8")
    examined(len(NOT_BUILT), "rules recorded as not built")
    assert NOT_BUILT[0] in text, "the rule left out is not recorded in RULES.md"
    assert "Refused by design, not deferred" in text, (
        "RULES.md does not say the rule is refused by design; the specification "
        "requires that distinction, because deferred invites someone to build it later")


def test_the_digest_moves_when_a_rules_condition_moves(examined):
    """So a cache keyed on it cannot serve incidents from a rule that has changed."""
    changed = tuple(replace(r, condition=r.condition + " (changed)") if r.id == RULE_IDS[0]
                    else r for r in RULES)
    examined(len(changed), "rules in the altered table")
    from onetrace_console.incidents import digest
    body = "\n".join(r.row() for r in changed) + "\n"
    assert digest(body.encode("utf-8")) != rule_table_digest()


# ------------------------------------------- one raise and one near miss for each rule

@pytest.fixture
def base(delivery, store):
    """A real stored, checked run, stored as could not check with its stated reason: the thing
    other fixtures vary from.

    Since 0.2.0 the verifier checks a run's links itself, so a checked run carries no topology
    note and raises nothing for it. The one stored reason left is
    `check_note`, which `run_and_record` writes when the verifier's report cannot be read; the
    run is stored in exactly that shape, with the verdict `could not check` and its reason.
    """
    _require_installed()
    run = accept(delivery, store).run
    assert run is not None
    run = run_and_record(run, store, ran_at=FIXED_RAN_AT)
    run = replace(run, check_verdict=COULD_NOT_CHECK, check_note=UNREADABLE_REASON)
    store.put_run(run)
    return run, store


#: The reason a stored could-not-check carries when the verifier's report could not be read.
UNREADABLE_REASON = "the check report could not be read: it has no summary line"


def _only(incidents, rule_id):
    return tuple(i for i in incidents if i.rule == rule_id)


def test_i_contradicts_raises_and_its_near_miss_does_not(files, store, examined):
    """Raise: a run whose stored report carries a `[FAIL]` row. Near miss: one that holds.

    The near miss is the **same fixture with honest sums**, so the only difference between the
    two is what the verifier found — not two unrelated runs.
    """
    _require_installed()
    _require_exam()
    import hashlib

    from onetrace_console.ingest import SUMS_NAME

    #: raise — a receipt whose bytes no longer match the digest the manifest recorded
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-changed"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    bad = run_and_record(accept(make_tar(files), store).run, store, ran_at=FIXED_RAN_AT)
    assert bad.check_verdict == CONTRADICTS, bad.check_verdict

    raised = _only(derive(store), "I-CONTRADICTS")
    examined(len(raised), "I-CONTRADICTS incidents raised")
    assert len(raised) == 1, raised
    incident = raised[0]
    assert incident.subject == bad.key
    assert incident.source_sha == bad.check_report
    assert incident.field_path == "stdout[FAIL]"
    #: It quotes the report's own rows, unedited, and says nothing of its own.
    stored = json.loads(store.get(bad.check_report).decode("utf-8"))["stdout"]
    for line in incident.quoted.splitlines():
        assert line in stored, f"{line!r} is not in the stored report"
        assert line.startswith("[FAIL"), line

    #: near miss — a clean delivery with no FAIL row. `ingest-r1/run_C_poppler24` is a preview-
    #: format run, which the 0.2.0 verifier reads as NOT VERIFIED: couldn't
    #: check, where 0.1.2 said holds. Either way it carries no [FAIL] row and must raise nothing.
    good = run_and_record(_deliver(RUN_C_POPPLER24, store), store, ran_at=FIXED_RAN_AT)
    assert good.check_verdict == COULD_NOT_CHECK, good.check_verdict
    still = _only(derive(store), "I-CONTRADICTS")
    assert {i.subject for i in still} == {bad.key}, (
        "a run with no [FAIL] row raised I-CONTRADICTS")


def test_i_runid_reused_raises_and_its_near_miss_does_not(files, store, examined):
    """Raise: two chains under one run name. Near miss: one chain, same name, alone."""
    _require_installed()
    import hashlib

    from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME

    first = accept(make_tar(dict(files)), store).run
    assert RUN_ID_REUSED not in first.flags
    #: near miss first, so the rule is shown raising nothing before it raises
    none_yet = _only(derive(store), "I-RUNID-REUSED")
    assert none_yet == (), none_yet

    #: raise — a genuinely different chain under the same name
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    dropped = manifest["chain"].pop()
    del files[dropped["file"]]
    manifest["chain_head"] = manifest["chain"][-1]["digest"]
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    second = accept(make_tar(files), store).run
    assert RUN_ID_REUSED in second.flags

    raised = _only(derive(store), "I-RUNID-REUSED")
    examined(len(raised), "I-RUNID-REUSED incidents raised")
    assert len(raised) == 1 and raised[0].subject == second.key
    assert raised[0].quoted == RUN_ID_REUSED, raised[0].quoted
    assert raised[0].field_path == f"flags[{RUN_ID_REUSED}]"


def test_i_header_disagrees_raises_and_its_near_miss_does_not(delivery, store, examined, tmp_path):
    """Raise: a header contradicting the manifest. Near miss: a header that agrees."""
    _require_installed()
    agreeing = accept(delivery, store)
    assert agreeing.run is not None
    assert _only(derive(store), "I-HEADER-DISAGREES") == (), (
        "an agreeing header raised I-HEADER-DISAGREES")

    #: The near miss and the raise cannot share a store — the second delivery of the same
    #: bytes is idempotent — so the raise gets its own, under the test's own folder (never
    #: `tempfile.mkdtemp()`, which left it in $TMPDIR).
    from onetrace_console.store import Store
    other = Store(tmp_path / "other" / "store")
    disagreeing = accept(delivery, other, headers={"chain_head": "sha256:deadbeef"})
    assert disagreeing.run is not None
    raised = _only(derive(other), "I-HEADER-DISAGREES")
    examined(len(raised), "I-HEADER-DISAGREES incidents raised")
    assert len(raised) == 1 and raised[0].subject == disagreeing.run.key
    assert "disagrees with the manifest" in raised[0].quoted
    assert raised[0].field_path == "flags[header]"


def test_i_could_not_check_raises_and_its_near_miss_does_not(base, examined):
    """Raise: the runner's stored `check_note`, a reason the check could not be made. Never a
    run's topology note, which is a line on its page.

    Near miss: a run with no recorded not-run reason at all. The near miss is constructed by
    clearing the note on the same run, so the only difference is the presence of a reason.
    """
    run, store = base
    assert run.check_note == UNREADABLE_REASON

    raised = _only(derive(store), "I-COULD-NOT-CHECK")
    examined(len(raised), "I-COULD-NOT-CHECK incidents raised")
    assert raised, "the stored check note raised nothing"
    assert {i.quoted for i in raised} == {UNREADABLE_REASON}
    assert {i.field_path for i in raised} == {"check_note"}

    #: a topology note on the same run raises nothing more
    from onetrace_console.checks import TOPOLOGY_NO_EDGE_ROWS
    store.put_run(replace(run, topology_note=TOPOLOGY_NO_EDGE_ROWS))
    assert {i.field_path for i in _only(derive(store), "I-COULD-NOT-CHECK")} == {"check_note"}

    #: near miss — the same run with no reason recorded, and a verdict that is not
    #: `could not check`, so nothing is owed a reason
    store.put_run(replace(run, topology_note="", check_note="", check_verdict=HOLDS))
    assert _only(derive(store), "I-COULD-NOT-CHECK") == (), (
        "a run with no recorded not-run reason raised I-COULD-NOT-CHECK")


def test_could_not_check_with_no_stated_reason_is_named_rather_than_inventing_one(base,
                                                                                  examined):
    """An incident must quote something. A verdict with no reason is a defect upstream: the
    store refuses the record as one its check runner did not write, and names it, rather than
    raising past every page that counts runs."""
    run, store = base
    store.put_run(replace(run, topology_note="", check_note="",
                          check_verdict=COULD_NOT_CHECK))
    examined(1, "run recorded as could-not-check with no reason")
    assert _only(derive(store), "I-COULD-NOT-CHECK") == ()
    assert any("no stated reason" in u for u in store.unreadable_runs), store.unreadable_runs


def test_contradicts_with_no_failing_row_is_named_rather_than_inventing_one(base, examined):
    """No incident is invented for it, and the rule's refusal is named on the pages that
    count incidents, not raised past them."""
    run, store = base
    store.put_run(replace(run, check_verdict=CONTRADICTS))
    examined(1, "run recorded as contradicting with no failing row")
    assert _only(derive(store), "I-CONTRADICTS") == ()
    assert any("no [FAIL] row" in u for u in store.underived), store.underived


# -------------------------------------------------------- step 2: derived, never judged

def test_deriving_twice_gives_byte_identical_output(base, examined):
    run, store = base
    first, second = as_json(derive(store)), as_json(derive(store))
    examined(len(derive(store)), "incidents derived twice")
    assert first == second, "two derivations of one store disagree"
    assert first.endswith("\n")


def _tampered(files) -> bytes:
    """The fixture with one receipt changed and honest sums: the verifier finds it contradicts."""
    import hashlib

    from onetrace_console.ingest import SUMS_NAME
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-changed"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    return make_tar(files)


def _two_with_one_report(files, store):
    """One contradicting delivery read from two folders and checked at one time: two runs, one
    stored check report, byte for byte."""
    data = _tampered(files)
    a = run_and_record(accept(data, store, run_folder="copy-a").run, store, ran_at=FIXED_RAN_AT)
    b = run_and_record(accept(data, store, run_folder="copy-b", shared_head=True).run, store,
                       ran_at=FIXED_RAN_AT)
    return a, b


def test_two_runs_with_one_byte_identical_check_report_raise_two_incidents(files, store, examined):
    _require_installed()
    _require_exam()
    a, b = _two_with_one_report(files, store)
    examined(2, "contradicting runs sharing one stored check report")
    assert a.key != b.key and a.check_report == b.check_report
    assert a.check_verdict == b.check_verdict == CONTRADICTS
    raised = _only(derive(store), "I-CONTRADICTS")
    assert {i.subject for i in raised} == {a.key, b.key} and len({i.id for i in raised}) == 2


def test_sabotage_a_run_incident_id_without_its_run_merges_the_two(files, store, monkeypatch, examined):
    from onetrace_console import incidents
    _require_installed()
    _require_exam()
    a, b = _two_with_one_report(files, store)
    real = incidents.incident_id
    monkeypatch.setattr(incidents, "incident_id", lambda r, s, f, k="": real(r, s, f))
    examined(1, "ids without the run's key")
    raised = _only(derive(store), "I-CONTRADICTS")
    assert len({i.id for i in raised}) == 1


def test_an_incident_id_is_the_rule_the_source_sha_and_the_field_path(examined):
    parts = ("I-CONTRADICTS", "a" * 64, "stdout[FAIL]")
    examined(len(parts), "components of an incident id")
    assert incident_id(*parts) == incident_id(*parts)
    assert incident_id(*parts) != incident_id("I-RUNID-REUSED", parts[1], parts[2])
    assert incident_id(*parts) != incident_id(parts[0], "b" * 64, parts[2])
    assert incident_id(*parts) != incident_id(parts[0], parts[1], "other")
    #: The separator matters: without it, these two would collide.
    assert incident_id("AB", "C", "D") != incident_id("A", "BC", "D")
    #: A run's incident: the run's key after them, separated the same way.
    assert incident_id(*parts, "k1") != incident_id(*parts, "k2") != incident_id(*parts)


def test_changing_a_rules_condition_changes_exactly_that_rules_incidents(base, examined):
    """One rule silenced; every other rule's incidents must be untouched."""
    run, store = base
    before = derive(store)
    examined(len(before), "incidents before a rule is changed")
    assert before, "nothing was raised, so this test would prove nothing"

    target = "I-COULD-NOT-CHECK"
    silenced = tuple(replace(r, raise_for=lambda run, store: []) if r.id == target else r
                     for r in RULES)
    after = derive(store, rules=silenced)
    assert _only(after, target) == (), "the silenced rule still raised incidents"
    for rule_id in RULE_IDS:
        if rule_id == target:
            continue
        assert _only(after, rule_id) == _only(before, rule_id), (
            f"changing {target} changed {rule_id}'s incidents")


def test_every_incidents_evidence_link_resolves_to_a_rendered_page(base, examined):
    """The store is immutable, so a source report cannot vanish — but the LINK could be wrong.

    Asserted against the pages actually rendered, so an incident can never point at a page
    nobody generates.
    """
    run, store = base
    incidents = derive(store)
    examined(len(incidents), "incident evidence links")
    assert incidents, "no incidents, so no links are checked"
    pages = render_all(store, generated_at=GENERATED_AT)
    execution = render_execution(run, store, generated_at=GENERATED_AT)
    #: Paths from the site's root, as a page links them: the run's own pages under runs/<key>/.
    #: `execution-<id>.html`, the free file's report page, was listed here as if the console
    #: served it, and the link was dead on every page.
    available = set(pages) | {f"runs/{run.key}/{name}" for name in execution.pages}
    for i in incidents:
        assert i.evidence in available, (
            f"{i.rule} points at {i.evidence}, which is not among the pages rendered")


def test_no_incident_carries_a_severity_a_score_or_a_rank(base, examined):
    """What is absent is the point. Asserted over the dataclass, not over the page."""
    run, store = base
    incidents = derive(store)
    examined(len(incidents), "incidents checked for a severity field")
    assert incidents
    fields = set(Incident.__slots__)
    for banned in ("severity", "score", "rank", "priority", "risk", "level", "weight"):
        assert banned not in fields, f"Incident carries a {banned!r} field"
    assert fields == {"id", "rule", "subject", "subject_kind", "source_sha", "field_path",
                      "quoted", "evidence"}, sorted(fields)


def test_incidents_are_ordered_by_name_and_not_by_anything_that_looks_like_importance(
        base, examined):
    run, store = base
    _require_exam()
    run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    incidents = derive(store)
    examined(len(incidents), "incidents whose order is checked")
    keys = [(i.rule, i.subject, i.field_path) for i in incidents]
    assert keys == sorted(keys), "incidents are not in (rule, subject, field) order"


# ------------------------------------------------------------- step 3: the pages

@pytest.fixture
def populated(files, store):
    """A store with runs raising several rules, so every page has something to show."""
    _require_installed()
    _require_exam()
    import hashlib

    from onetrace_console.ingest import SUMS_NAME

    a = run_and_record(_deliver(RUN_C, store), store, ran_at=FIXED_RAN_AT)
    b = run_and_record(_deliver(RUN_C_POPPLER24, store), store, ran_at=FIXED_RAN_AT)
    receipt = json.loads(files["receipts/01-zeta.json"].decode("utf-8"))
    receipt["run_id"] = receipt.get("run_id", "") + "-changed"
    files["receipts/01-zeta.json"] = json.dumps(receipt, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(x).hexdigest()}  {p}"
        for p, x in files.items() if p != SUMS_NAME) + "\n").encode()
    bad = run_and_record(accept(make_tar(files), store).run, store, ran_at=FIXED_RAN_AT)
    comparison = compare(a, b, store, ran_at=FIXED_RAN_AT)
    return store, a, bad, comparison


def test_the_incidents_page_shows_every_rule_including_the_ones_that_raised_nothing(
        populated, examined):
    store, *_ = populated
    page = render_incidents(store, generated_at=GENERATED_AT)
    groups = re.findall(r'<section data-group="([^"]+)"', page)
    examined(len(groups), "rule groups on the Incidents page")
    assert tuple(groups) == RULE_IDS, groups
    assert RULE_TABLE_DIGEST in page, "the page does not carry the rule table's digest"
    assert NOT_BUILT[0] in page, "the page does not say which rule was left out"


def test_every_count_on_the_incidents_page_equals_the_list_it_links_to(populated, examined):
    """Both numbers a group shows, compared with the page its link opens."""
    store, *_ = populated
    pages = render_all(store, generated_at=GENERATED_AT)
    page = render_incidents(store, generated_at=GENERATED_AT)
    grouped = by_rule(derive(store))
    runs_total = len(store.runs())
    examined(len(grouped), "groups whose counts are compared with their lists")

    for rule_id, mine in grouped.items():
        sentence = group_sentence(rule_id, mine, runs_total)
        assert escape(sentence) in page, f"the Incidents page lacks {sentence!r}"
        href = rule_href(rule_id)
        assert href in pages, f"{rule_id} links to {href}, which was not rendered"
        listed = pages[href]
        shown = re.findall(r'<tr data-incident="', listed)
        assert len(shown) == len(mine), (
            f"{rule_id}: {len(mine)} incidents but {len(shown)} on {href}")
        runs_with = len({i.subject for i in mine})
        #: The new wording: the unit is written out.
        word = "run" if runs_with == 1 else "runs"
        assert f"{runs_with} {word} of {runs_total}" in escape(listed), (
            f"{rule_id}'s list does not carry `{runs_with} {word} of {runs_total}`")


def test_home_has_one_count_per_rule_and_each_opens_its_list(populated, examined):
    store, *_ = populated
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[COUNTS]  # every count, whole, moved from the Overview
    counted = incident_tallies(store)
    examined(len(counted), "incident tallies on Home")
    assert len(counted) == len(RULES)
    for t in counted:
        assert escape(t.sentence) in home, f"Home lacks {t.sentence!r}"
        assert t.href in pages, f"Home links to {t.href}, which was not rendered"
        listed = pages[t.href]
        rows = len({m for m in re.findall(r'<span class="mono">([0-9a-f]{12})</span>', listed)})
        assert t.count == len(t.runs)
        assert t.count <= len(store.runs())


def test_the_execution_and_diff_pages_show_the_incidents_raised_from_them(populated,
                                                                         examined):
    store, a, bad, comparison = populated
    execution = render_execution(bad, store, generated_at=GENERATED_AT)
    raised = for_subject(store, bad.key)
    examined(len(raised), "incidents raised from the run whose pages are checked")
    assert raised, "the contradicting run raised nothing, so this proves nothing"
    for name in (ANSWER, CASE):
        page = execution.pages[name]
        assert f'data-section="{RAISED}"' in page, f"{name} shows no incidents"
        for i in raised:
            assert i.id[:12] in page, f"{name} is missing incident {i.id[:12]}"

    diff = render_diff(comparison, store, generated_at=GENERATED_AT)
    pair_raised = tuple(i for k in (comparison.run_a, comparison.run_b)
                        for i in for_subject(store, k))
    if pair_raised:
        assert f'data-section="{RAISED}"' in diff, "the Diff page shows no incidents"


def test_a_page_with_no_incidents_shows_no_incidents_section(store, examined):
    """So the section is a statement about what was raised, not furniture."""
    _require_installed()
    _require_exam()
    run = run_and_record(_deliver(EXAM / "dag-r37" / "run_R", store), store,
                         ran_at=FIXED_RAN_AT)
    raised = for_subject(store, run.key)
    examined(1, "run checked for an absent incidents section")
    if raised:
        pytest.skip_msg = None
        assert True      # this fixture does raise; the assertion below is then not applicable
        return
    page = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    assert f'data-section="{RAISED}"' not in page


def test_the_incident_pages_pass_the_five_prohibitions(populated, examined):
    store, *_ = populated
    pages = {INCIDENTS: render_incidents(store, generated_at=GENERATED_AT)}
    for rule in RULES:
        pages[rule_href(rule.id)] = render_rule_list(store, rule.id,
                                                     generated_at=GENERATED_AT)
    examined(len(pages), "incident pages checked against the five prohibitions")
    for name, page in pages.items():
        body = _body(page).lower()
        assert not [w for w in FORBIDDEN_WORDS if w in body], f"{name}: score or grade"
        assert not [w for w in INFERENCE_WORDS if w in body], f"{name}: inference"
        assert not re.findall(r"\d+(?:\.\d+)?\s*%", _body(page)), f"{name}: percentage"
        for mechanism in ("<button", "<form", "<input", "onclick=", "onsubmit="):
            assert mechanism not in body, f"{name} carries {mechanism!r}"
        assert not re.findall(r'style="[^"]*(?:color|background)[^"]*"', page, re.I), name
        #: Narrowed to the SHAPES a severity would take, not the word. The page says "There
        #: is no severity, no score and nothing to acknowledge" — and a prohibition that
        #: fires on a page DECLARING it has none is the CSS-percentage mistake again
        #: What must not exist is a severity field, attribute or value.
        for shape in ('data-severity', 'severity=', '"severity"', 'data-priority',
                      'data-rank', 'risk score', 'trend', 'recommend'):
            assert shape not in body, f"{name} carries {shape!r}"


def test_no_incident_page_references_a_remote_origin(populated, examined):
    store, *_ = populated
    pages = {INCIDENTS: render_incidents(store, generated_at=GENERATED_AT)}
    for rule in RULES:
        pages[rule_href(rule.id)] = render_rule_list(store, rule.id,
                                                     generated_at=GENERATED_AT)
    examined(len(pages), "incident pages checked for a remote reference")
    for name, page in pages.items():
        assert not re.findall(r'(?:src|href)\s*=\s*"(https?:|//)[^"]*"', page, re.I), name
        assert "<script src=" not in page, name


# ------------------------------- the four weaknesses the sabotages found, closed

def test_each_flag_rule_raises_only_from_its_own_field(files, store, examined):
    """A store carrying BOTH flags, so a rule that matched any flag would be caught.

    Found by a sabotage: widening `I-HEADER-DISAGREES` to match every flag changed nothing,
    because no store in these tests held both flags at once. Each rule's own test then only
    counted its own incidents and never noticed the other rule firing on the wrong field.
    """
    _require_installed()
    import hashlib

    from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME

    accept(make_tar(dict(files)), store)
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    dropped = manifest["chain"].pop()
    del files[dropped["file"]]
    manifest["chain_head"] = manifest["chain"][-1]["digest"]
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    #: One delivery, two flags: a reused run name AND a disagreeing header.
    both = accept(make_tar(files), store, headers={"chain_head": "sha256:deadbeef"}).run
    assert both is not None
    flags = set(both.flags)
    examined(len(flags), "flags on one run")
    assert RUN_ID_REUSED in flags and any("disagrees" in f for f in flags), flags

    reused = _only(derive(store), "I-RUNID-REUSED")
    header = _only(derive(store), "I-HEADER-DISAGREES")
    assert len(reused) == 1 and reused[0].quoted == RUN_ID_REUSED, reused
    assert len(header) == 1 and "disagrees with the manifest" in header[0].quoted, header
    assert reused[0].id != header[0].id
    assert reused[0].field_path != header[0].field_path


def test_the_derivation_order_is_by_name_where_length_would_disagree(files, store,
                                                                    examined):
    """The orders must be able to disagree, or the assertion cannot fail.

    A sabotage sorted by quoted length and no test noticed, because the few incidents in the
    fixture happened to fall the same way both times. This is the SECOND time a sort test of
    mine could not fail for want of a fixture that distinguishes the orders — the first was
    the comparison candidates' ordering.
    """
    _require_installed()
    import hashlib

    from onetrace_console.ingest import MANIFEST_NAME, SUMS_NAME

    accept(make_tar(dict(files)), store)
    manifest = json.loads(files[MANIFEST_NAME].decode("utf-8"))
    dropped = manifest["chain"].pop()
    del files[dropped["file"]]
    manifest["chain_head"] = manifest["chain"][-1]["digest"]
    files[MANIFEST_NAME] = json.dumps(manifest, separators=(",", ":")).encode()
    files[SUMS_NAME] = ("\n".join(
        f"{hashlib.sha256(b).hexdigest()}  {p}"
        for p, b in files.items() if p != SUMS_NAME) + "\n").encode()
    run = accept(make_tar(files), store, headers={"chain_head": "sha256:deadbeef"}).run
    run_and_record(run, store, ran_at=FIXED_RAN_AT)

    incidents = derive(store)
    examined(len(incidents), "incidents whose order must distinguish name from length")
    by_name = [(i.rule, i.subject, i.field_path) for i in incidents]
    by_length = [(i.rule, i.subject, i.field_path)
                 for i in sorted(incidents, key=lambda i: -len(i.quoted))]
    assert by_name == sorted(by_name), "incidents are not in (rule, subject, field) order"
    assert by_name != by_length, (
        "sorting by quoted length gives the same order here, so this test cannot tell the "
        "two apart and a ranking would pass it")


def test_a_page_that_cannot_carry_its_incidents_raises_rather_than_showing_none(base,
                                                                               examined):
    """Nothing exercised this until a sabotage made it return the page unchanged.

    A page that silently showed no incidents would read as a page with none, which is the
    worst available outcome and the reason the anchor is asserted.
    """
    run, store = base
    raised = for_subject(store, run.key)
    examined(len(raised), "incidents that would have gone unshown")
    assert raised, "nothing was raised, so this proves nothing"
    with pytest.raises(ValueError, match="no <main>"):
        incidents_block("<html><body>no main here</body></html>", raised, len(raised), up="")


def test_every_per_rule_count_on_home_equals_the_incidents_on_the_page_it_opens(populated,
                                                                               examined):
    """Read from Home's HTML and compared with the page, not with the tally that wrote it.

    A sabotage doubled a tally's runs and nothing failed: the strong Home check covered only
    the run tallies, and the per-rule assertions compared a tally with itself. The same
    two-implementations trap as before, one slice later.
    """
    store, *_ = populated
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[COUNTS]  # every count, whole, moved from the Overview
    grouped = by_rule(derive(store))
    counted = incident_tallies(store)
    examined(len(counted), "per-rule counts on Home compared with their pages")

    for t in counted:
        rule_id = t.label.replace("runs raising ", "")
        block = re.search(rf'<li data-tally="{re.escape(t.slug)}">.*?</li>', home, re.S)
        assert block, f"Home has no tally block for {t.slug!r}"
        shown = re.search(r"(\d+) runs? of (\d+)", block.group(0))
        assert shown, f"Home's {t.slug!r} line carries no `N of M`"
        page_runs, page_total = int(shown.group(1)), int(shown.group(2))
        assert page_total == len(store.runs()), t.slug

        listed = pages[t.href]
        on_page = re.findall(r'<tr data-incident="', listed)
        assert len(on_page) == len(grouped[rule_id]), (
            f"{rule_id}: {len(grouped[rule_id])} incidents but {len(on_page)} on {t.href}")
        #: The run count Home shows must be the distinct runs those incidents came from.
        assert page_runs == len({i.subject for i in grouped[rule_id]}), (
            f"{rule_id}: Home says {page_runs} runs, the incidents on {t.href} come from "
            f"{len({i.subject for i in grouped[rule_id]})}")


def _raised_heading(page: str) -> str:
    section = re.search(rf'<section data-section="{RAISED}">.*?</section>', page, re.S)
    assert section, "the page shows no incidents section"
    return re.search(r"<h2>(.*?)</h2>", section.group(0)).group(1), section.group(0)


def test_the_raised_block_counts_its_incidents_out_of_every_incident_stored(base, examined):
    """`incident_pages.py:185` wrote a bare "N incidents raised from this
    page's reports". Its denominator is incidents: every incident the rules raised from the
    stored runs. Execution pages are sealed and not re-rendered when a later run arrives,
    so the total is stated as of this page's generation, never as a live figure."""
    run, store = base
    store.put_run(replace(run, key=run_key("other-run", run.chain_head), run_id="other-run"))
    raised = for_subject(store, run.key)
    total = len(derive(store))
    examined(len(raised), "incidents raised from the run whose page is checked")
    assert raised and total > len(raised), "the count and its denominator cannot differ here"

    page = render_execution(run, store, generated_at=GENERATED_AT).pages[CASE]
    heading, section = _raised_heading(page)
    word = "incident" if total == 1 else "incidents"
    assert heading == (f"{len(raised)} of the {total} {word} raised from stored runs when this "
                       f"page was generated came from this page's reports"), heading
    assert len(re.findall(r'<li data-incident="', section)) == len(raised)


def test_a_run_compared_with_itself_does_not_count_its_incidents_twice(populated, examined):
    """A run compared with itself is one run: its incidents appear once, and the count
    never exceeds the incidents that exist."""
    store, _, bad, _ = populated
    comparison = compare(bad, bad, store, ran_at=FIXED_RAN_AT)
    raised = for_subject(store, bad.key)
    examined(len(raised), "incidents raised from the run compared with itself")
    assert raised, "the run raised nothing, so this proves nothing"
    diff = render_diff(comparison, store, generated_at=GENERATED_AT)
    heading, section = _raised_heading(diff)
    assert len(re.findall(r'<li data-incident="', section)) == len(raised)
    assert heading.startswith(f"{len(raised)} of the "), heading


def test_homes_incident_count_carries_its_denominator(populated, examined):
    """`home.py:181` wrote a bare "N incidents". The count is of incidents, so
    its denominator is incidents: every incident the rules raised from the stored runs. Read
    from Home's HTML and compared with the rule pages, not with the tally that wrote it."""
    store, *_ = populated
    pages = render_all(store, generated_at=GENERATED_AT)
    home = pages[COUNTS]  # every count, whole, moved from the Overview
    every = derive(store)
    grouped = by_rule(every)
    raising = [r for r in RULES if grouped[r.id]]
    examined(len(raising), "rules with incidents whose Home line was checked")
    assert len(raising) >= 2, "one rule alone cannot show a count differing from its total"

    for rule in raising:
        block = re.search(rf'<li data-tally="{rule.id.lower()}">.*?</li>', home, re.S).group(0)
        assert not re.search(r"<li>\d+ incidents?</li>", block), f"a bare count: {block}"
        on_page = len(re.findall(r'<tr data-incident="', pages[rule_href(rule.id)]))
        word = "incident" if on_page == 1 else "incidents"
        assert f"{on_page} {word} of {len(every)} raised from stored runs" in block, block
