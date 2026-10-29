"""What neighbours draw: the setup page that turns them on, a run's "Runs with near inputs", and the
nearness ladder on a comparison of two neighbours. A local console's only; with the extra absent or on
a public console, nothing here is ever called (`neighbours.exists`), and no page names the feature.

The setup page turns the feature on in two steps, with no script: choose the embedder, then confirm the
words that name it (`settings.confirmation`). Both are plain forms posted to the console itself, each
carrying the session's CSRF token where there is a session, as sign-out's form does.
"""
from __future__ import annotations

from urllib.parse import quote

from onetrace_console.words import escape

PATH = "neighbours/setup"
TITLE = "Neighbours by input"
INTRO = ("Neighbours suggest earlier runs of the same configuration whose kept inputs are near this run's, "
         "and, on a comparison of two of them, the step where they part in meaning. An embedding model reads "
         "the kept inputs and kept outputs to say how near they are. It is optional and off until you turn "
         "it on here.")
WHAT_IS_READ = ("Only kept inputs, and the kept outputs of a run that keeps inputs, are embedded: never a "
                "digest, a setting or any part of a record. A run that kept nothing has no neighbours.")
FETCH = ("The default model's files are fetched once from huggingface.co, at the pinned revision, when you "
         "confirm: a GET with no token, each file checked by its sha256 before it is used, and a mismatch "
         "refused by the file's name. After the files are fetched, embedding makes no network calls.")
ENDPOINT = ("Or name an OpenAI-compatible embedding endpoint of your own. Kept inputs and kept outputs are "
            "then sent to it; no key is sent, and what it does not say of itself is recorded as not observed.")
RECORDED = "Each embedding batch is recorded as a onetrace run of its own, with a model-call record per text."
LABEL = "suggested by an embedding model you turned on; the comparison itself is exact"
LADDER_TITLE = "Nearness ladder: the embedder's view"
LADDER_LABEL = ("Per step, how near the two runs' kept inputs and kept outputs are, as an embedding model you "
                "turned on reads them. 1.00 by the record where the digests are equal: nothing is embedded "
                "there. The exact ladder, the short answer and every verdict are unchanged.")
LADDER_COLUMNS = ("Step", "Input nearness", "Output nearness", "Drop", "Exact difference at this step")
LARGEST = "largest drop"
NOT_KEPT = "not kept"
BY_RECORD = "1.00 by the record"
#: An embedder's number that rounds to 1.000 where the digests differ: never 1.000, which reads like
#: the record's equality.
NEAR_ONE = "≥ 0.9995, digests differ"
KEPT_NOTHING = "This run kept no input, so it has no neighbours."
NONE_NEAR = "No other run of this configuration kept the same inputs."
OFF = "Neighbours by input are off."
TURN_ON = "Turn them on"
ON_WITH = "Neighbours are on, with {who}."
TURN_OFF = "Turn neighbours off"
CONFIRM = "Confirm and turn on"
CHOOSE = "Continue"


def _number(n) -> str:
    from onetrace_console.neighbours.nearness import BY_RECORD as RECORD
    if n is None:
        return f'<span data-nearness="not-kept">{escape(NOT_KEPT)}</span>'
    if n.how == RECORD:
        return f'<span data-nearness="record">{escape(BY_RECORD)}</span>'
    said = _three(n.value)
    if float(said) >= 1.0:
        #: The digests differ (an equal pair is the record's, above): said so, never as 1.000.
        return f'<span data-nearness="embedder" data-near-one>{escape(NEAR_ONE)}</span>'
    return f'<span data-nearness="embedder">{said}</span>'


def _three(x: float) -> str:
    """An embedder's number to three places, so one just short of 1 never reads as the record's 1.00;
    a value that rounds to zero is 0.000, never -0.000."""
    said = f"{x:.3f}"
    return "0.000" if said == "-0.000" else said


def _fp(digest: str) -> str:
    from onetrace_console.viewer.page import fingerprint_html
    return fingerprint_html(digest)


# ------------------------------------------------------------------------------ the run page

def run_section(run, store, *, up: str = "../../") -> str:
    """The run page's neighbours, under "What changed?": the count, each near input with its number and
    Compare; or why there are none. "" where the feature does not exist here, or is off."""
    from onetrace_console import neighbours
    if not neighbours.here():
        return ""
    from onetrace_console.neighbours.nearness import suggestions
    head = '<section data-section="neighbours" class="neighbours">'
    #: Off, the run's page is exactly the page drawn without the extra: nothing until a person turns
    #: neighbours on, at /neighbours/setup.
    got = suggestions(run, store)
    if got is None:
        return ""
    if got.kept_nothing:
        return head + f'<h2>{escape(heading(0))}</h2><p data-neighbours="kept-nothing">{escape(KEPT_NOTHING)}</p></section>'
    rows = "".join(_row(r, run, store, up) for r in got.rows)
    #: The Compare buttons' one script, once, where a row has a button (`compare_script`).
    from onetrace_console.compare_script import COMPARE_SCRIPT
    script = COMPARE_SCRIPT if "data-compare-post=" in rows else ""
    body = (f'<table class="timeline" data-neighbours="rows"><thead><tr><th>Run</th><th>Near input</th>'
            f'<th>Similarity</th><th></th></tr></thead><tbody>{rows}</tbody></table>' if got.rows
            else f'<p data-neighbours="none">{escape(NONE_NEAR)}</p>')
    from onetrace_console.words import scroll_region
    return (head + f'<h2 data-neighbours="count">{escape(heading(got.runs))}</h2>'
            f'<p class="note" data-neighbours="group">Same configuration: {_fp(got.signature)}</p>'
            + (scroll_region(body, heading(got.runs), "neighbours") if got.rows else body) + script + "</section>")


def heading(n: int) -> str:
    return f"Runs with near inputs (same configuration): {n}"


def _row(r, run, store, up: str) -> str:
    from onetrace_console.what_changed import held
    from onetrace_console.words import run_named
    c = held(store, r.other.key, run.key) or held(store, run.key, r.other.key)
    if c is not None:
        act = f'<a href="{up}diff/{escape(c.key)}.html" data-neighbours="open">Compare</a>'
    else:
        act = (f'<button type="button" hidden data-compare-post="/compare?a={escape(r.other.key)}&amp;b={escape(run.key)}">'
               f'Compare</button><span data-compare-said></span>')
    return (f'<tr data-neighbour="{escape(r.other.key)}"><td><a href="{up}runs/{escape(r.other.key)}/case.html">'
            f"{run_named(store, r.other.key)}</a></td><td><code>{escape(r.step)}</code> · "
            f'<code>{escape(r.name)}</code></td><td class="value">{_number(r.near)}</td>'
            f'<td><span class="note">{escape(LABEL)}</span> {act}</td></tr>')


# ------------------------------------------------------------------------------ the comparison page

def ladder_section(comparison, store) -> str:
    """The nearness ladder beside the exact one, in its own columns; "" where the two runs are not
    neighbours here."""
    from onetrace_console import neighbours
    if not neighbours.here():
        return ""
    from onetrace_console.neighbours.nearness import ladder, largest_drop
    rungs = ladder(comparison, store)
    if not rungs:
        return ""
    mark = largest_drop(rungs)
    head = "".join(f"<th>{escape(c)}</th>" for c in LADDER_COLUMNS)
    rows = []
    for i, r in enumerate(rungs):
        drop = "" if r.drop is None else _three(r.drop)
        marked = i == mark
        named_in = f' <span class="note">least near: <code>{escape(r.input_name)}</code></span>' if r.input_name else ""
        named_out = f' <span class="note">least near: <code>{escape(r.output_name)}</code></span>' if r.output_name else ""
        facts = ("; ".join(escape(f) for f in r.facts) if marked else "")
        rows.append(f'<tr data-rung="{escape(r.step)}"{" data-largest-drop" if marked else ""}>'
                    f"<td><code>{escape(r.step)}</code></td><td class=\"value\">{_number(r.inputs)}{named_in}</td>"
                    f'<td class="value">{_number(r.outputs)}{named_out}</td>'
                    f'<td class="value">{escape(drop)}'
                    + (f' <span class="pill neu" data-largest>{escape(LARGEST)}</span>' if marked else "")
                    + f'</td><td data-facts>{facts}</td></tr>')
    from onetrace_console.words import scroll_region
    table = (f'<table class="timeline" data-section="nearness-ladder"><thead><tr>{head}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table>')
    return (f'<section data-section="nearness" class="nearness"><h2>{escape(LADDER_TITLE)}</h2>'
            f'<p class="note">{escape(LADDER_LABEL)}</p>' + scroll_region(table, LADDER_TITLE, "nearness")
            + "</section>")


# ------------------------------------------------------------------------------ the setup page

def _csrf(token: str | None) -> str:
    from onetrace_console.signin import CSRF_FIELD
    return f'<input type="hidden" name="{CSRF_FIELD}" value="{escape(token, quote=True)}">' if token else ""


def _model_line(m) -> str:
    return (f"<code>{escape(m.repo)}</code> at revision <code>{escape(m.revision)}</code>, {escape(m.pooling)} "
            f"pooling, L2-normalised; licence {escape(m.licence)}")


def setup_page(store, *, query: dict | None = None, said: str = "", csrf: str | None = None) -> str:
    """The setup page: what neighbours are and are not, the setting as it is, and the form that turns it on
    (or off). `query`: the embedder chosen, for the confirmation step."""
    from onetrace_console.neighbours import NON_CLAIMS, settings
    from onetrace_console.neighbours.embedder import ALTERNATE, DEFAULT, MODELS, Refused
    q = {k: (v[0] if isinstance(v, list) else v) for k, v in (query or {}).items()}
    setting = settings.read(store)
    parts = [f"<h1>{escape(TITLE)}</h1>", f"<p>{escape(INTRO)}</p>", f"<p>{escape(WHAT_IS_READ)}</p>",
             f"<p>{escape(RECORDED)}</p>",
             '<section data-section="non-claims"><h2>What this is not</h2><ul>'
             + "".join(f"<li>{escape(c)}</li>" for c in NON_CLAIMS) + "</ul></section>"]
    if said:
        parts.append(f'<p data-neighbours="said" role="status">{escape(said)}</p>')
    if setting is not None:
        e = setting["embedder"]
        who = (f"the endpoint {e['base_url']} (model {e['model']})" if e.get("kind") == "endpoint"
               else f"{MODELS[e['model']].repo} at revision {MODELS[e['model']].revision}")
        parts.append(f'<section data-section="setting"><h2>Now</h2><p data-neighbours="on">'
                     f'{escape(ON_WITH.format(who=who))}</p><p class="note">Confirmed: '
                     f'<q>{escape(setting["confirmed"])}</q>, by {escape(setting["who"])}, {escape(setting["when"])}.</p>'
                     f'<form method="post" action="/neighbours/off">{_csrf(csrf)}'
                     f'<button type="submit">{escape(TURN_OFF)}</button></form></section>')
        return "".join(parts)
    chosen = None
    if q.get("embedder"):
        try:
            chosen = settings.choose(q)
        except Refused as e:
            parts.append(f'<p data-neighbours="refused" role="alert">{escape(str(e))}</p>')
    if chosen is not None:
        words = settings.confirmation(chosen)
        hidden = "".join(f'<input type="hidden" name="{k}" value="{escape(str(q.get(k, "")), quote=True)}">'
                         for k in ("embedder", "base_url", "model"))
        parts.append(f'<section data-section="confirm"><h2>Confirm</h2><p data-neighbours="confirmation">'
                     f'{escape(words)}</p><form method="post" action="/neighbours/on">{_csrf(csrf)}{hidden}'
                     f'<input type="hidden" name="confirmed" value="{escape(words, quote=True)}">'
                     f'<button type="submit">{escape(CONFIRM)}</button> <a href="/{PATH}">Back</a></form></section>')
        return "".join(parts)
    d, a = MODELS[DEFAULT], MODELS[ALTERNATE]
    parts.append(
        f'<section data-section="choose"><h2>Turn neighbours on</h2><p data-neighbours="off">{escape(OFF)}</p>'
        f"<p>{escape(FETCH)}</p>"
        f'<form method="get" action="/{PATH}"><fieldset><legend>The embedder</legend>'
        f'<p><label><input type="radio" name="embedder" value="{DEFAULT}" checked> The default: {_model_line(d)}</label></p>'
        f'<p><label><input type="radio" name="embedder" value="{ALTERNATE}"> The alternate: {_model_line(a)}</label></p>'
        f'<p><label><input type="radio" name="embedder" value="endpoint"> {escape(ENDPOINT)}</label></p>'
        f'<p><label>Endpoint <input type="url" name="base_url" placeholder="http://127.0.0.1:8000/v1"></label> '
        f'<label>Model <input type="text" name="model" maxlength="200"></label></p></fieldset>'
        f'<button type="submit">{escape(CHOOSE)}</button></form></section>')
    return "".join(parts)


def document(store, **kw) -> str:
    """The setup page as a whole document, its frame empty for the server to fill as every page's is."""
    from onetrace_console.render import _document
    return _document(TITLE, f'<div class="cp setup">{setup_page(store, **kw)}</div>')


def setup_href(**query) -> str:
    return f"/{PATH}" + ("?" + "&".join(f"{k}={quote(str(v))}" for k, v in query.items()) if query else "")
