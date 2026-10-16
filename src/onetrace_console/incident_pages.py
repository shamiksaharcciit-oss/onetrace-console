"""The Incidents page, the per-rule lists, and the incident blocks on the other pages.

    The list: grouped by rule. Each group shows its count with its denominator. Each incident
    shows the rule id, the quoted field, the run or pair, and a link to the evidence page.
    Home gets one count per rule, each linking to exactly that rule's list. The Execution and
    Diff pages show the incidents raised from them. It shows no colour except on the verdict
    words as the reports give them, no trend and no recommendation.

TWO COUNTS PER GROUP, AND BOTH EQUAL THEIR LIST
-----------------------------------------------
The order's example of a group's count is *"3 of 41 runs"*, and a group can also hold more
incidents than runs -- one run can trip a rule twice. So each group shows **both**: how many
runs it touches out of the runs stored, and how many incidents it holds. The page it links to
lists exactly those incidents, and a test compares both numbers with what is on that page.
Showing one number and linking to a list of the other is how a count stops meaning anything.

NO COLOUR EXCEPT ON THE REPORT'S OWN VERDICT WORDS
--------------------------------------------------
The quoted field is rendered inside `<pre>` with no class of its own. The only `data-verdict`
attribute on these pages is on a group's rule id, carrying the rule id itself -- not a
severity, because there is no severity. Nothing here is coloured by how bad it is, because
nothing here knows.
"""
from __future__ import annotations

from onetrace_console.viewer.page import fingerprint_html, fingerprints_in_text
from onetrace_console.words import escape, verbatim, verbatim_rows, generated_footer

from onetrace_console.incidents import (NOT_BUILT, RULE_TABLE_DIGEST, RULES, Incident,
                                        by_rule, derive, rule_table_digest)
from onetrace_console.store import Store

INCIDENTS = "incidents.html"

#: The marker for the block this console splices onto a page that shows a run. Deliberately
#: not `incidents`: the viewer's case page already uses that name for its own section.
RAISED = "incidents-raised"



def _code_spans(text: str) -> str:
    """A rule's text, escaped, with each `backticked` name (a field, a value as stored) drawn as code:
    the name of a thing in the record, not the page's own words."""
    import re
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escape(text))

def rule_href(rule_id: str) -> str:
    return f"incidents-{rule_id.lower()}.html"


#: Each rule's chip, in the page's own words (an extension's rule: its id).
RULE_CHIP = {"I-CONTRADICTS": "Contradicts itself", "I-HEADER-DISAGREES": "Header disagrees",
             "I-COULD-NOT-CHECK": "Couldn't check", "I-RUNID-REUSED": "Run id reused"}
INCIDENT_DIR = "incidents"
LIST_COLUMNS = ("Incident", "Run", "Pipeline", "Raised")
FOUND_LEAD = ("The console's own run of the verifier over the stored record, as it wrote it: its "
              "summary, one fix line for each failing row, and its rows.")
#: The published errors page, as a reader opens it: the verifier names its source, errors.md;
#: the page with the same sections is errors.html.
ERRORS_PAGE = "https://oneproof.dev/onetrace/errors.html"
ERRORS_SOURCE = "https://oneproof.dev/onetrace/errors.md"
WHICH_NONE = "The report names no failing row, so no file is named here."
#: The caution where a signature or an anchor holds over records that contradict themselves.
CAUTION = ("{what} {covers} the chain head as recorded. {they} {do} not make a changed output file "
           "match its receipt again.")


def incident_href(incident: Incident) -> str:
    """One incident's own page, from the site's root: its rule and its id's first 16 characters.
    Drawn for the console's own rules' incidents only."""
    return f"{INCIDENT_DIR}/{incident.rule.lower()}-{incident.id[:16]}.html"


def rule_chip(rule_id: str) -> str:
    from onetrace_console import tones
    words = RULE_CHIP.get(rule_id, rule_id)
    return f'<span class="pill {tones.tone(tones.INCIDENT, rule_id)}">{escape(words)}</span>'


def _raised_at(incident: Incident, store: Store) -> str:
    """When the incident was raised: when this console's check of its run ran, as the stored
    report records it; "" where there is none."""
    from onetrace_console.pages import _envelope
    if incident.subject_kind != "run":
        return ""
    try:
        envelope = _envelope(store.get_run(incident.subject), store, required=False)
    except Exception:  # noqa: BLE001 - no time read, none said
        return ""
    ran = envelope.get("ran_at") if isinstance(envelope, dict) else None
    return ran if isinstance(ran, str) else ""


def _incident_table(incidents: tuple[Incident, ...], store: Store, up: str = "") -> str:
    """A rule's incidents as rows: its chip (linked to the incident's own page), the run (linked to
    its page), its pipeline, and when it was raised."""
    from onetrace_console.overview import pipelines
    from onetrace_console.words import run_named, scroll_region, time_html
    label = {r.key: p.label for p in pipelines(store) for r in p.runs}
    #: Only the console's own rules' incidents have a page of their own; an extension's incident
    #: (a onedoor decision) is named by its kind and keeps its link to the record it came from.
    own = {r.id for r in RULES}
    rows = []
    for i in incidents:
        run = (f'<a href="{up}runs/{escape(i.subject)}/case.html">{run_named(store, i.subject)}</a>'
               if i.subject_kind == "run" else
               f'{escape(i.subject_kind)} <span class="mono">{escape(i.subject[:12])}</span>'
               + ("" if i.rule in own else
                  f' · <a href="{escape(up + i.evidence, quote=True)}">the report it came from</a>'))
        chip = (f'<a href="{up}{incident_href(i)}">{rule_chip(i.rule)}</a>' if i.rule in own
                else rule_chip(i.rule))
        raised = _raised_at(i, store)
        rows.append(f'<tr data-incident="{escape(i.id[:12], quote=True)}">'
                    f'<td>{chip}</td>'
                    f"<td>{run}</td><td>{escape(label.get(i.subject, ''))}</td>"
                    f'<td class="value">{time_html(raised) if raised else "not recorded"}</td></tr>')
    head = "".join(f"<th>{c}</th>" for c in LIST_COLUMNS)
    return scroll_region(f'<table class="board" data-section="incident-rows"><thead><tr>{head}</tr>'
                         f"</thead><tbody>{''.join(rows)}</tbody></table>", "The incidents", "incidents")


def _found(envelope: dict, incident: Incident) -> str:
    """"What the verifier found": the summary, the fix lines and the rows, each its own block,
    each as the verifier wrote it and drawn by the run page's rule for the verifier's rows: control
    characters shown, a line past NAME_CAP cut with what was left out said (the whole report stays
    in the store). A fix line's address of the published errors page is kept whole and linked.
    Where a record broke the rows apart, the whole output, escaped, with the viewer's note."""
    import re as _re

    from onetrace_console.incidents import WHOLE_OUTPUT
    from onetrace_console.viewer.page import _escape_rows
    from onetrace_console.words import scroll_region
    stderr = str(envelope.get("stderr", "")).replace("\r\n", "\n").splitlines()
    summary = [line for line in stderr if line and not line.startswith("fix ")]
    fixes = [line for line in stderr if line.startswith("fix ")]

    def linked(line: str) -> str:
        """The line by the rows' rule; its closing errors-page address kept whole, as the verifier
        wrote it, and linked to the published page a reader can read, errors.html, at the same
        section."""
        found = _re.match(r"(.*; see )https://oneproof\.dev/onetrace/errors\.md#([A-Za-z0-9_-]+)$", line, _re.S)
        if found is None:
            return _escape_rows(line)
        code = found.group(2)
        return (_escape_rows(found.group(1))
                + f'<a href="{ERRORS_PAGE}#{code}">{escape(ERRORS_SOURCE)}#{escape(code)}</a>')
    if incident.field_path == WHOLE_OUTPUT:
        rows = _quoted(incident)
    else:
        out = str(envelope.get("stdout", "")).replace("\r\n", "\n")
        rows = scroll_region(f'<pre class="term" data-found="rows">{_escape_rows(out)}</pre>',
                             "The verifier's rows", "found-rows")
    return ('<section data-section="found"><h2>What the verifier found</h2>'
            f'<p class="note">{escape(FOUND_LEAD)}</p>'
            + "".join(f'<pre class="term" data-found="summary">{_escape_rows(line)}</pre>' for line in summary)
            + "".join(f'<p class="fix" data-found="fix"><code>{linked(line)}</code></p>' for line in fixes)
            + rows + "</section>")


def _which(envelope: dict) -> str:
    """"Which file, and how": built only from the report's failing rows -- each row's file and the
    check that failed there, with its detail, as the verifier's --json rows give them. The JSON
    rows carry a record's words unescaped, so each is drawn as a record word: its control characters
    shown, cut past NAME_CAP with what was left out said."""
    from onetrace_console.bounded_json import load_json_bounded
    from onetrace_console.viewer.model import NAME_CAP
    from onetrace_console.viewer.page import _named, _rest

    def word(text: str) -> str:
        return _named(text) + _rest(text, whole=False)
    rows = []
    try:
        doc = load_json_bounded(str((envelope.get("rows_json") or {}).get("stdout", "")), "rows")
        rows = [r for r in doc.get("rows", []) if isinstance(r, dict) and r.get("result") == "FAIL"]
    except Exception:  # noqa: BLE001 - no rows read, none named
        rows = []
    items = []
    for r in rows:
        name, detail = str(r.get("name", "")), str(r.get("detail", ""))
        path, _, check = name.partition(": ")
        items.append(f'<li data-fail-row><code>{word(path)}</code>'
                     + (f" — {word(check)}" if check else "")
                     #: Capped as every record word is, then each fingerprint in it short.
                     + (f": {fingerprints_in_text(detail[:NAME_CAP])}{_rest(detail, whole=False)}"
                        if detail else "") + "</li>")
    body = f'<ul class="plain">{"".join(items)}</ul>' if items else f"<p>{escape(WHICH_NONE)}</p>"
    return f'<section data-section="which"><h2>Which file, and how</h2>{body}</section>'


def _caution(answers: dict[str, str]) -> str:
    """The amber caution, only where a signature or an anchor holds over records that contradict
    themselves: neither makes a changed output file match its receipt again."""
    signed, anchored = answers.get("signed") == "yes", answers.get("anchored") == "yes"
    if answers.get("records-agree") != "no" or not (signed or anchored):
        return ""
    what = ("The signature and the anchor" if signed and anchored
            else "The signature" if signed else "The anchor")
    both = signed and anchored
    said = CAUTION.format(what=what, covers="cover" if both else "covers", they="They" if both else "It",
                          do="do" if both else "does")
    return f'<p data-section="caution" data-state="couldnt-check">{escape(said)}</p>'


def _four_answers(run, store: Store, generated_at: str) -> tuple[str, dict[str, str]]:
    """The run page's own four answers, drawn as its head draws them, and {rung: state} for each
    of its rungs; ("", {}) where the run's page could not be drawn."""
    import tempfile
    from pathlib import Path

    from onetrace_console.pages import _model
    from onetrace_console.run_head import _rungs
    if store.missing(run):
        return "", {}
    with tempfile.TemporaryDirectory(prefix="onetrace-incident-") as tmp:
        try:
            model = _model(run, store, generated_at, Path(tmp) / "run", require_report=False)
        except Exception:  # noqa: BLE001 - the store's three answers are drawn instead
            return "", {}
    return _rungs(model), {r.key: r.state for r in model.ladder}


def render_incident_page(incident: Incident, store: Store, *, generated_at: str) -> str:
    """One incident: the run it was raised on and its rule, when it was raised, the run's four
    answers as its own page draws them, the caution where it applies, what the verifier found and
    which file and how. No re-check: this console has no such action."""
    from onetrace_console import tones
    from onetrace_console.overview import pipelines
    from onetrace_console.pages import _envelope, run_answers
    from onetrace_console.render import _document, _limit_sentence
    from onetrace_console.viewer.sentences import template
    from onetrace_console.words import named, time_html
    up = "../"
    run = store.get_run(incident.subject) if incident.subject_kind == "run" else None
    label = next((p.label for p in pipelines(store) for r in p.runs if run and r.key == run.key), "")
    who = (f'<a href="{up}runs/{run.key}/case.html"><span class="mono" data-words="record">'
           f"{named(run.run_id)}</span></a>" if run else
           f'<span class="mono">{escape(incident.subject[:12])}</span>')
    raised = _raised_at(incident, store)
    parts = [
        f'<p class="crumbs" data-section="crumbs"><a href="{up}{INCIDENTS}">Incidents</a> / '
        f"{who}</p>",
        f'<div class="title"><h1><span class="mono" data-words="record">'
        f"{named(run.run_id) if run else escape(incident.subject[:12])}</span>"
        + (f" · {escape(label)}" if label else "") + f"</h1>{rule_chip(incident.rule)}</div>",
        f'<p data-section="raised">{escape(incident.rule)} · raised when this console checked the run'
        + (f", {time_html(raised)}" if raised else "") + "</p>",
    ]
    envelope = None
    if run is not None:
        strip, answers = _four_answers(run, store, generated_at)
        if not strip:   # the run page's own answers could not be drawn: the store's, as the lists read them
            answers = run_answers(run, store)
            names = {"records-agree": "rung.records-agree", "signed": "rung.signed", "anchored": "rung.anchored",
                     "approved": "rung.approved"}
            strip = ('<ul class="seals">' + "".join(
                f'<li data-head-rung="{k}" data-state="{v}"><span class="q">{escape(template(names[k]))}</span> '
                f'<span class="pill {tones.tone(tones.RUNG, v)}">'
                f'{escape(template("rung.state." + v.replace("-", "_")))}</span></li>'
                for k, v in answers.items()) + "</ul>")
        parts.append(strip.replace('<ul class="seals">', '<ul class="seals" data-section="answers">', 1))
        parts.append(_caution(answers))
        try:
            envelope = _envelope(run, store, required=False)
        except Exception:  # noqa: BLE001 - said below
            envelope = None
    if isinstance(envelope, dict) and incident.rule == "I-CONTRADICTS":
        parts.append('<div class="io">' + _found(envelope, incident) + _which(envelope) + "</div>")
    else:
        parts.append('<section data-section="quoted"><h2>What the record says</h2>'
                     + _quoted(incident) + "</section>")
    parts.append(f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>')
    parts.append(generated_footer(generated_at))
    body = '<div class="cp" data-view="incident">' + "".join(p for p in parts if p) + "</div>"
    return _document(f"{RULE_CHIP.get(incident.rule, incident.rule)} · "
                     f"{run.run_id if run else incident.subject[:12]}", body)


def _incident_item(incident: Incident, store: Store | None = None, up: str = "") -> str:
    """One incident: its rule, the run or pair, the quoted field, and the evidence link. A run is
    named by its run id and short key where the store is given; a pair by its key.
    `up` is the way from the page that shows it to the site's root -- `""` on a page at the
    root, `../../` on a run's own pages -- since the evidence is a path from the root."""
    from onetrace_console.words import run_named
    subject = (run_named(store, incident.subject)
               if store is not None and incident.subject_kind == "run"
               else f'<span class="mono">{escape(incident.subject[:12])}</span>')
    return (
        f'<li data-incident="{escape(incident.id[:12], quote=True)}">'
        f'<span class="mono" data-rule="{escape(incident.rule, quote=True)}">'
        f"{escape(incident.rule)}</span> — "
        f"{escape(incident.subject_kind)} {subject}, field "
        f'<span class="mono">{escape(incident.field_path)}</span>'
        + _quoted(incident)
        + f'<a href="{escape(up + incident.evidence, quote=True)}">the report it came from</a>'
        f"</li>")


def _quoted(incident: Incident) -> str:
    """The quoted field: the report's rows, one per line -- or, where a record broke the rows
    apart (30bv §3.3), the whole output, every character escaped, with the viewer's note."""
    from onetrace_console.incidents import WHOLE_OUTPUT
    if incident.field_path != WHOLE_OUTPUT:
        return f'<pre data-quoted="report">{verbatim_rows(incident.quoted)}</pre>'
    from onetrace_console.viewer.page import TEXT_CAP
    from onetrace_console.viewer.sentences import template
    text = incident.quoted
    more = (" " + template("text.more").format(n=str(len(text) - TEXT_CAP))
            if len(text) > TEXT_CAP else "")
    return (f'<p data-section="rows-unreadable">{escape(template("rows.unreadable"))}</p>'
            f'<pre data-quoted="report" data-rows="unreadable">{escape(text[:TEXT_CAP])}'
            f'{escape(more)}</pre>')


def group_sentence(rule_id: str, incidents: tuple[Incident, ...], runs_total: int,
                  unit: str = "run") -> str:
    """`I-CONTRADICTS — 2 runs of 11, 3 incidents across those 2 runs`.

        One number per group, with its denominator, and its unit written out in words (for
        example "3 runs of 41"). Add a second number only if it counts a **different unit**,
        also written out (for example "5 nodes across those 3 runs"). If both numbers count
        the same unit, drop the second.

    Runs is the unit of the first number for every built-in rule; `unit` lets the onedoor
    extension's rules say "decisions" instead, without this reading as a run count they
    are not. Incidents are a different unit, so the second is allowed — and it is
    omitted when it would say the same thing as the first, which is the case whenever
    each subject raised exactly one incident.
    """
    runs_with = len({i.subject for i in incidents})
    runs_word = unit if runs_with == 1 else unit + "s"
    first = f"{runs_with} {runs_word} of {runs_total}"
    if len(incidents) == runs_with:
        #: One incident per subject: a second number would repeat the first in different words.
        return f"{rule_id} — {first}"
    word = "incident" if len(incidents) == 1 else "incidents"
    return (f"{rule_id} — {first}, {len(incidents)} {word} across those "
            f"{runs_with} {runs_word}")


def _notes(notes: tuple[str, ...]) -> str:
    """A rule's "couldn't check" lines: rows it could not raise from, each named."""
    return "".join(f'<p data-state="couldnt-check">{escape(n)}</p>' for n in notes)


def render_incidents(store: Store, *, generated_at: str,
                     extra_rules: tuple = (), extra_incidents: tuple = (),
                     extra_totals: dict = None, extra_notes: dict = None) -> str:
    """The Incidents page: every rule, in the rule table's order, including empty ones.

    `extra_rules`/`extra_incidents` are the extension's hook, passed by the caller only when the
    onedoor extension is enabled -- empty by default, so a disabled console renders
    exactly what it always has. `extra_totals` maps a rule's `unit` (e.g. `"decision"`)
    to its denominator, for rules whose subject is not a run. `extra_notes` maps a rule
    id to its "couldn't check" lines.
    """
    from onetrace_console.render import _document, _limit_sentence, underived_note

    rules = RULES + tuple(extra_rules)
    incidents = derive(store, rules=rules, extra_incidents=tuple(extra_incidents))
    grouped = by_rule(incidents, rules=rules)
    totals = {"run": len(store.runs()), **(extra_totals or {})}

    groups = []
    for rule in rules:
        mine = grouped[rule.id]
        total = totals.get(rule.unit, 0)
        groups.append(
            f'<section data-group="{escape(rule.id, quote=True)}">'
            f"<h2>{escape(group_sentence(rule.id, mine, total, unit=rule.unit))}</h2>"
            f'<p data-section="words">{escape(rule.words)}. '
            f'Raised when {_code_spans(rule.condition)}. '
            f'<a href="{escape(rule_href(rule.id), quote=True)}">this rule\'s list</a></p>'
            + _notes((extra_notes or {}).get(rule.id, ()))
            + (_incident_table(mine, store) if mine else
               f'<p data-section="none">This rule raised nothing from the {total} '
               f"{rule.unit}{'s' if total != 1 else ''} stored.</p>")
            + "</section>")

    not_built = "".join(f"<li>{escape(r)}</li>" for r in NOT_BUILT)
    digest_text = RULE_TABLE_DIGEST if not extra_rules else rule_table_digest(rules)
    body = [
        "<h1>Incidents</h1>",
        '<p data-section="what">An incident records that a stored report says a specific '
        "thing. It is raised by a named rule, quotes the report's own field, and links to "
        "it. There is no severity, no score and nothing to acknowledge.</p>",
        underived_note(store),
        "".join(groups),
        f'<div data-section="rule-table">Rule table digest: '
        f'{fingerprint_html(digest_text)}. Rules not built: '
        f'</div><ul class="plain" data-section="not-built">{not_built}</ul>',
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>',
        generated_footer(generated_at),
    ]
    body = ['<div class="cp">', *body, "</div>"]  # the console's page skin (item 12)
    return _document("Incidents", "\n".join(body))


def render_rule_list(store: Store, rule_id: str, *, generated_at: str,
                     extra_rules: tuple = (), extra_incidents: tuple = (),
                     extra_totals: dict = None, extra_notes: dict = None) -> str:
    """One rule's list: exactly the incidents that rule raised, and nothing else."""
    from onetrace_console.render import _document, _limit_sentence, underived_note

    rules = RULES + tuple(extra_rules)
    mine = by_rule(derive(store, rules=rules, extra_incidents=tuple(extra_incidents)),
                   rules=rules)[rule_id]
    rule = next(r for r in rules if r.id == rule_id)
    total = {"run": len(store.runs()), **(extra_totals or {})}.get(rule.unit, 0)
    body = [
        f"<h1>{escape(group_sentence(rule_id, mine, total, unit=rule.unit))}</h1>",
        f'<p data-section="words">{escape(rule.words)}. Raised when '
        f"{_code_spans(rule.condition)}. Source: {_code_spans(rule.source)}, field "
        f"{_code_spans(rule.field)}.</p>",
        _notes((extra_notes or {}).get(rule_id, ())),
        underived_note(store),
        (f'<div data-group="{escape(rule_id, quote=True)}">{_incident_table(mine, store)}</div>'
         if mine else f'<p data-section="none">This rule raised nothing from the '
                      f"{total} {rule.unit}{'s' if total != 1 else ''} stored.</p>"),
        f'<p class="limit" data-section="limit">{escape(_limit_sentence())}</p>',
        generated_footer(generated_at),
    ]
    body = ['<div class="cp">', *body, "</div>"]  # the console's page skin (item 12)
    return _document(f"Incidents — {rule_id}", "\n".join(body))


def incidents_block(html_text: str, incidents: tuple[Incident, ...], total: int,
                    store: Store | None = None, *, up: str) -> str:
    """Splice a run's or pair's incidents into a page that shows it.

    Spliced for the same reason the preview label is: the Execution pages are the viewer's and
    `answer.html` is frozen. The anchor is asserted, so a page that cannot carry its incidents
    raises rather than showing none — showing none would read as *there are none*.

    `total` is every incident the rules raised from the stored runs when the page is
    generated: the count's denominator, in its own unit. These pages are
    sealed and not re-rendered when a later run arrives, so the sentence says the total is
    as of this page's generation rather than presenting it as live.
    """
    import re

    if not incidents:
        return html_text
    #: `incidents-raised`, NOT `incidents`. The viewer's case page already carries its own
    #: `data-section="incidents"` — a named-but-absent section — so an idempotence
    #: guard on that name saw the viewer's section, decided the block was already there, and
    #: silently rendered nothing. The page then said it had no incidents while holding two.
    #: Found by a test asserting the ids were present, not by reading the markup.
    if f'data-section="{RAISED}"' in html_text:
        return html_text
    main = re.search(r"<main\b[^>]*>", html_text)
    if main is None:
        raise ValueError(
            "cannot show incidents on this page: it has no <main> to place them after. A "
            "page that silently showed none would read as a page with none.")
    if total < len(incidents):
        raise ValueError(f"{len(incidents)} incidents cannot be out of {total}: a denominator "
                         "smaller than its count is not one")
    #: `up`: the way from this page to the site's root, for both links: a bare
    #: `incidents.html` on a run's or a pair's page named a page one or two folders down.
    items = "".join(_incident_item(i, store, up) for i in incidents)
    word = "incident" if total == 1 else "incidents"
    block = (f'<section data-section="{RAISED}"><h2>{len(incidents)} of the {total} {word} '
             f"raised from stored runs when this page was generated came from this page's "
             f'reports</h2><ul class="plain">{items}</ul>'
             f'<p><a href="{up}{INCIDENTS}">all incidents</a></p></section>')
    at = main.end()
    #: Inside the console's page skin where the page has one (item 12), at the same place: first.
    skin = re.match(r'\s*<div class="cp">', html_text[at:])
    if skin:
        at += skin.end()
    #: After the preview label where the page carries one: it sits directly after <main>,
    #: above everything a reader is about to read. Under 0.2.0 a preview run raises
    #: I-COULD-NOT-CHECK, so a page can now carry both.
    from onetrace_console.preview import LABEL
    labelled = re.match(r'\s*<p data-preview="' + re.escape(LABEL) + r'"[^>]*>.*?</p>', html_text[at:], re.S)
    if labelled:
        at += labelled.end()
    return html_text[:at] + "\n" + block + html_text[at:]


def for_subject(store: Store, subject_key: str) -> tuple[Incident, ...]:
    """Every incident whose subject is this run or comparison."""
    return tuple(i for i in derive(store) if i.subject == subject_key)
