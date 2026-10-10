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
        items = "".join(_incident_item(i, store) for i in mine)
        groups.append(
            f'<section data-group="{escape(rule.id, quote=True)}">'
            f"<h2>{escape(group_sentence(rule.id, mine, total, unit=rule.unit))}</h2>"
            f'<p data-section="words">{escape(rule.words)}. '
            f'Raised when {_code_spans(rule.condition)}. '
            f'<a href="{escape(rule_href(rule.id), quote=True)}">this rule\'s list</a></p>'
            + _notes((extra_notes or {}).get(rule.id, ()))
            + (f'<ul class="plain">{items}</ul>' if mine else
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
        f'<p data-section="rule-table">Rule table digest: '
        f'<span class="mono">{escape(digest_text)}</span>. Rules not built: '
        f'</p><ul class="plain" data-section="not-built">{not_built}</ul>',
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
    items = "".join(_incident_item(i, store) for i in mine)
    body = [
        f"<h1>{escape(group_sentence(rule_id, mine, total, unit=rule.unit))}</h1>",
        f'<p data-section="words">{escape(rule.words)}. Raised when '
        f"{_code_spans(rule.condition)}. Source: {_code_spans(rule.source)}, field "
        f"{_code_spans(rule.field)}.</p>",
        _notes((extra_notes or {}).get(rule_id, ())),
        underived_note(store),
        (f'<ul class="plain" data-group="{escape(rule_id, quote=True)}">{items}</ul>'
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
