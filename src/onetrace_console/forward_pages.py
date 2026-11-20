"""Trace forwarding's setup page (console 0.9), from the Settings gear: the destinations, add, edit, turn off, remove,
a header's value kept in the keychain, and Send a test trace.

A local console's only, an admin's (`roles`): a public console and a static export draw no row and serve no route.
Every change goes to the audit log, where it is on, by destination and field, never a value. A header's value is never
drawn: a variable's header says whether the variable is set, and a keychain's says whether a value is stored, with
Replace and Remove; the field that takes one is write-only.
"""

from __future__ import annotations

import os
from pathlib import Path

from onetrace_console import forwarding as F
from onetrace_console.words import escape

PATH = "/forwarding/setup"
REL = "forwarding/setup"
TITLE = "Forwarding traces"
NOT_EVIDENCE = "A trace is a view of a record, never evidence."
INTRO = (
    "Each run this console takes in is sent once, as one trace, to each destination that is on: onetrace's own export "
    "of the run, the same as onetrace export otel, with one attribute, onetrace.console.check, the console's result "
    "for it, and, where the link back to this console is on, onetrace.console_url. No input or output value, error "
    "text or path is sent. Nothing a destination answers is used."
)
#: The link back to the console (`forwarding.console_url`), off and on.
LINK_OFF = (
    "The link back to this console is off: no trace carries onetrace.console_url. To turn it on, set "
    "forwarding.console_url in the configuration file to the address people open this console at, such as "
    "https://onetrace.example.org, and start the console again."
)
LINK_ON = (
    "The link back to this console is on: each trace's root span carries onetrace.console_url, the run's page, "
    "{page}. It is a pointer, never a claim: the record is checked by onetrace-verify, not by the tool that shows "
    "the link."
)
RETRIES = (
    "A network error, a 429 or a 5xx is tried again after a wait that doubles, up to {n} tries in all; "
    "any other answer stops that run's entry, and the reason is shown here."
)
#: Which variables a destination may name: those made for forwarding (`forwarding.FORWARD_PREFIX`).
VARIABLES_NAMED = (
    "A destination's key comes from a variable whose name starts with ONETRACE_FORWARD_, or from the keychain: the "
    "console reads no other variable for forwarding, so none of its own settings can be sent."
)
NONE_YET = "No destination yet: add one below."
REFUSED = "refused"
ADD_HEAD = "Add a destination"
EDIT = "Save changes"
ADD = "Add"
TURN_OFF = "Turn off"
TURN_ON = "Turn on"
REMOVE = "Remove"
REMOVE_SURE = "Yes, remove this destination, its queue and its stored values"
TEST = "Send a test trace"
REPLACE = "Replace"
STORE = "Store"
REMOVE_VALUE = "Remove the value"
TEST_SAID = "The test trace, one span named {span} and no run data, was answered {status}."
TEST_NOT = "The test trace was not sent: {why}."
SAVED = "Saved: {name}: {fields}."
ADDED = "Added: {name}."
REMOVED = "Removed: {name}."
VALUE_STORED = "{header}'s value is stored in the keychain."
VALUE_REMOVED = "{header}'s value is removed from the keychain."
NOT_SAVED = "Not saved: {why}."
GO_TO_FIELD = "Go to the field"
RUNS_WORDS = {"all": "every run", "agree": "only runs whose records agree"}


def field_id(form: str, name: str) -> str:
    """The id of field `name` in the form `form` ("add", or a destination's id): the error's link points to it."""
    return f"fwd-{form}-{name}"


def _error(form: str, name: str, refused: tuple[str, str] | None) -> tuple[str, str]:
    """(the field's attributes, the message under it) where `refused` (field, message) is about this field."""
    fid = field_id(form, name)
    if refused is None or refused[0] != name:
        return f' id="{fid}"', ""
    return (
        f' id="{fid}" aria-invalid="true" aria-describedby="{fid}-error"',
        f'<span class="field-error" id="{fid}-error" role="alert">{escape(refused[1])}</span>',
    )


def _field(
    label: str,
    name: str,
    value: str = "",
    kind: str = "text",
    extra: str = "",
    *,
    form: str = "add",
    refused: tuple[str, str] | None = None,
) -> str:
    attrs, said = _error(form, name, refused)
    return (
        f'<label class="field">{escape(label)} <input type="{kind}" name="{name}" value="{escape(value)}" '
        f'autocomplete="off"{attrs}{extra}>{said}</label>'
    )


def _select(
    label: str, name: str, options: dict, chosen: str, *, form: str = "add", refused: tuple[str, str] | None = None
) -> str:
    attrs, said = _error(form, name, refused)
    opts = "".join(
        f'<option value="{escape(v)}"{" selected" if v == chosen else ""}>{escape(w)}</option>'
        for v, w in options.items()
    )
    return f'<label class="field">{escape(label)} <select name="{name}"{attrs}>{opts}</select>{said}</label>'


def _form(action: str, inner: str, button: str, style: str = "secondary", data: str = "") -> str:
    """A form of this page: `style` is one of the console's three button styles (`primary`, `secondary`,
    `destructive`)."""
    from onetrace_console.frame import CSRF_SLOT

    return (
        f'<form method="post" action="{PATH}" data-forwarding="{escape(data or action)}">{CSRF_SLOT}'
        f'<input type="hidden" name="action" value="{escape(action)}">{inner}'
        f'<button class="btn-{style}" type="submit" data-busy="Working…">{escape(button)}</button></form>'
    )


def _header_lines(d: F.Destination) -> str:
    out = []
    for h in d.headers:
        state = F.key_state(d, h)
        where = (
            f"from the variable <code>{escape(h.key_env)}</code>: {escape(state)}"
            if h.key_env
            else f"from the keychain: {escape(state)}"
        )
        forms = ""
        if h.keyring:
            hidden = f'<input type="hidden" name="id" value="{d.id}"><input type="hidden" name="header" value="{escape(h.name)}">'
            forms = _form(
                "key",
                hidden + _field("New value", "value", "", "password"),
                REPLACE if state == "stored" else STORE,
                data="key",
            )
            if state == "stored":
                forms += _form("key-remove", hidden, REMOVE_VALUE, "destructive", data="key-remove")
        out.append(f'<li data-header="{escape(h.name)}"><code>{escape(h.name)}</code> {where}{forms}</li>')
    return f'<ul class="plain" data-forwarding="headers">{"".join(out)}</ul>' if out else "<p>No headers.</p>"


def _state_lines(store_root, d: F.Destination) -> str:
    st = F.status(store_root, d.id)
    q = F.queued(store_root, d.id)
    waiting = sum(1 for e in q if e.get("state") == "queued")
    stopped = [e for e in q if e.get("state") == "stopped"]
    last_send = st.get("last_send")
    lines = [
        f"<li>Last send: {escape(last_send) if last_send else 'none yet'}.</li>",
        f"<li>Queued: {waiting}.</li>",
    ]
    if st.get("last_failure"):
        lines.append(
            f'<li data-forwarding="last-failure">Last failure: {escape(st["last_failure"])}, '
            f"at {escape(st.get('last_failure_at', ''))}.</li>"
        )
    if stopped:
        lines.append(
            f'<li data-forwarding="stopped">Stopped: {len(stopped)}, the last because '
            f"{escape(str(stopped[-1].get('last', '')))}.</li>"
        )
    if d.encoding == "protobuf" and not F.protobuf_installed():
        lines.append(
            '<li data-forwarding="extra-missing">Protobuf needs the [otlp] extra, which is not installed in the Python '
            f"this console runs from: <code>{escape(F.INSTALL)}</code></li>"
        )
    return f'<ul class="plain" data-forwarding="state">{"".join(lines)}</ul>'


def _destination(store_root, d: F.Destination, refused: Change | None = None) -> str:
    ident = f'<input type="hidden" name="id" value="{d.id}">'
    #: A refused edit of this destination: its fields as they were sent, the message by the field it is about.
    mine = (
        refused
        if refused is not None and refused.form.get("action") == "edit" and refused.form.get("id") == d.id
        else None
    )
    sent = mine.form if mine is not None else {}
    why = (mine.field, mine.why) if mine is not None and mine.field else None
    edit = _form(
        "edit",
        ident
        + _field("Name", "name", sent.get("name", d.name), form=d.id, refused=why)
        + _field(
            "Endpoint (https, or http on this machine)",
            "endpoint",
            sent.get("endpoint", d.endpoint),
            form=d.id,
            refused=why,
        )
        + _select(
            "Encoding",
            "encoding",
            {"json": "JSON", "protobuf": "protobuf"},
            sent.get("encoding", d.encoding),
            form=d.id,
            refused=why,
        )
        + _select("Which runs", "runs", RUNS_WORDS, sent.get("runs", d.runs), form=d.id, refused=why),
        EDIT,
        "primary",
    )
    toggle = _form("toggle", ident, TURN_OFF if d.enabled else TURN_ON)
    test = _form("test", ident, TEST)
    remove = _form(
        "remove",
        ident
        + f'<label class="field"><input type="checkbox" name="sure" value="yes" required> {escape(REMOVE_SURE)}</label>',
        REMOVE,
        "destructive",
    )
    on = "on" if d.enabled else "off"
    refused_why = d.refused()
    if refused_why:
        #: Kept before forwarding read only its own variables: said, never sent to, and only removed.
        return (
            f'<section class="step" data-destination="{d.id}" data-on="refused"><h2>{escape(d.name)} · {escape(REFUSED)}</h2>'
            f'<p data-forwarding="refused">{escape(refused_why)}</p>'
            f'{_header_lines(d)}<div class="actions">{remove}</div></section>'
        )
    return (
        f'<section class="step" data-destination="{d.id}" data-on="{on}"><h2>{escape(d.name)} · {on}</h2>'
        f"<p><code>{escape(d.endpoint)}/v1/traces</code>, {escape(d.encoding)}, {escape(RUNS_WORDS[d.runs])}.</p>"
        f'{_header_lines(d)}{_state_lines(store_root, d)}{edit}<div class="actions">{toggle}{test}{remove}</div></section>'
    )


def _add_form(refused: Change | None = None) -> str:
    #: A refused add: every field as it was sent, but the keychain value, which is never drawn; the message by the field
    #: it is about.
    mine = refused if refused is not None and refused.form.get("action") == "add" else None
    sent = mine.form if mine is not None else {}
    why = (mine.field, mine.why) if mine is not None and mine.field else None
    return (
        f'<section class="step" data-forwarding="add"><h2>{escape(ADD_HEAD)}</h2>'
        + _form(
            "add",
            _field("Name", "name", sent.get("name", ""), refused=why)
            + _field(
                "Endpoint (https, or http on this machine)", "endpoint", sent.get("endpoint", ""), "url", refused=why
            )
            + _select(
                "Encoding",
                "encoding",
                {"json": "JSON", "protobuf": "protobuf"},
                sent.get("encoding", "json"),
                refused=why,
            )
            + _select("Which runs", "runs", RUNS_WORDS, sent.get("runs", "all"), refused=why)
            + _field("Header name (as x-api-key; leave empty for none)", "header", sent.get("header", ""), refused=why)
            + _select(
                "Its value is in",
                "where",
                {"env": "an environment variable", "keyring": "the keychain"},
                sent.get("where", "env"),
                refused=why,
            )
            + _field(
                "The variable's name (for an environment variable: it starts with ONETRACE_FORWARD_)",
                "key_env",
                sent.get("key_env", ""),
                refused=why,
            )
            + _field(
                "The value (for the keychain: typed once, stored, never shown)", "value", "", "password", refused=why
            ),
            ADD,
            "primary",
        )
        + "</section>"
    )


def link_line(console_url: str) -> str:
    """Whether each trace links back to this console, and how to turn the link on where it is off."""
    if not console_url:
        return f'<p data-forwarding="link">{escape(LINK_OFF)}</p>'
    page = F.run_page(console_url, "RUN").replace("/RUN/", "/<run key>/")
    return f'<p data-forwarding="link" data-link="on">{escape(LINK_ON.format(page=page))}</p>'


def body(store_root, said: str = "", refused: Change | None = None, console_url: str = "") -> str:
    try:
        dests = F.read(store_root)
        unreadable = ""
    except (OSError, ValueError) as e:
        dests, unreadable = (
            [],
            f'<p data-forwarding="unreadable">The destinations file can\'t be read ({type(e).__name__}).</p>',
        )
    lead = (
        f'<p class="lead" data-forwarding="not-evidence"><strong>{escape(NOT_EVIDENCE)}</strong></p>'
        f"<p>{escape(INTRO)}</p><p>{escape(RETRIES.format(n=F.MAX_ATTEMPTS))}</p>"
        f'<p data-forward="variables">{escape(VARIABLES_NAMED)}</p>{link_line(console_url)}'
    )
    #: Where a refusal is about one field, the line says so and links to it; the field says it too.
    at = ""
    if refused is not None and refused.field and refused.form.get("action") in ("add", "edit"):
        form = "add" if refused.form.get("action") == "add" else refused.form.get("id", "")
        at = f' <a href="#{field_id(form, refused.field)}">{escape(GO_TO_FIELD)}</a>'
    told = f'<p class="said" role="status" data-forwarding="said">{escape(said)}{at}</p>' if said else ""
    listed = "".join(_destination(store_root, d, refused) for d in dests) or f"<p>{escape(NONE_YET)}</p>"
    return f"<h1>{escape(TITLE)}</h1>{lead}{told}{unreadable}{listed}{_add_form(refused)}"


def page(store_root, said: str = "", refused: Change | None = None, console_url: str = "") -> str:
    """The page, saying `said`; with `refused`, a refused press: its form drawn again as it was sent (but a keychain
    value), the message by its field. `console_url`: `forwarding.console_url`, for the link's line."""
    from onetrace_console.render import _document

    return _document(
        TITLE, f'<div class="cp" data-page="forwarding">{body(store_root, said, refused, console_url)}</div>'
    )


# ------------------------------------------------------------------------------------------------- the changes


class Change:
    """What one press did: its status, its words, and for the audit log the destination and the fields (never a
    value)."""

    def __init__(
        self,
        status: int,
        said: str,
        destination: str = "",
        fields: list[str] | None = None,
        *,
        field: str | None = None,
        why: str = "",
        form: dict | None = None,
    ) -> None:
        self.status, self.said, self.destination, self.fields = status, said, destination, fields or []
        #: A refusal: the field it is about (or None), its words, and the form as it was sent (the keychain value
        #: dropped: never drawn).
        self.field, self.why = field, why
        self.form = {k: v for k, v in (form or {}).items() if k != "value"}


def _header_from(form: dict) -> list[dict]:
    name = (form.get("header") or "").strip()
    if not name:
        return []
    if form.get("where") == "keyring":
        return [{"name": name, "key_source": "keyring"}]
    return [{"name": name, "key_env": (form.get("key_env") or "").strip()}]


def plan(store_root, form: dict) -> Change:
    """What a press would change, for the audit log before it is made: Change(0, "", destination, fields); or, where
    the press would be refused, the refusal (status 400), so nothing is recorded that is not done."""
    action = form.get("action", "")
    did = form.get("id") or ""
    try:
        dests = F.read(store_root)
    except (OSError, ValueError) as e:
        return Change(400, NOT_SAVED.format(why=f"the destinations file can't be read ({type(e).__name__})"))
    now = next((x for x in dests if x.id == did), None)
    try:
        if action == "add":
            fields = {k: form.get(k, "") for k in ("name", "endpoint", "encoding", "runs")}
            F.destination({**fields, "id": "0" * 16, "headers": _header_from(form)})
            if len(dests) >= F.MOST_DESTINATIONS:
                raise F.Refused(f"at most {F.MOST_DESTINATIONS} destinations")
            return Change(0, "", "new", list(F.FIELDS) + (["a header's value"] if form.get("value") else []))
        if now is None:
            raise F.Refused("no such destination")
        if action == "edit":
            kept = now.as_json()
            fields = {k: form[k] for k in ("name", "endpoint", "encoding", "runs") if k in form}
            F.destination({**kept, **fields})
            return Change(0, "", did, [k for k in fields if fields[k] != kept[k]])
        if action == "toggle":
            return Change(0, "", did, ["enabled"])
        if action == "remove":
            if form.get("sure") != "yes":
                raise F.Refused("tick the box to remove it")
            return Change(0, "", did, ["removed"])
        if action in ("key", "key-remove"):
            header = next((h for h in now.headers if h.name == form.get("header")), None)
            if header is None or not header.keyring:
                raise F.Refused("no such header kept in the keychain")
            if action == "key" and not form.get("value"):
                raise F.Refused("type the value")
            return Change(0, "", did, [f"{header.name}'s value in the keychain"])
        if action == "test":
            return Change(0, "", did, [])
    except F.Refused as e:
        return Change(400, NOT_SAVED.format(why=str(e)), field=e.field, why=str(e), form=form)
    return Change(400, NOT_SAVED.format(why="not a change this page makes"))


def apply(store_root, form: dict) -> Change:
    """Make the change a press asks for. A header's value, typed once, goes to the keychain and nowhere else."""
    from onetrace_console import forward_keys

    action, did = form.get("action", ""), form.get("id") or ""
    try:
        if action == "add":
            fields = {k: form.get(k, "") for k in ("name", "endpoint", "encoding", "runs")}
            fields["headers"] = _header_from(form)
            d, _ = F.save(store_root, None, fields)
            if form.get("value") and d.headers and d.headers[0].keyring:
                forward_keys.store(d.id, d.headers[0].name, form["value"])
            return Change(200, ADDED.format(name=d.name), d.id, list(F.FIELDS))
        if action == "edit":
            fields = {k: form[k] for k in ("name", "endpoint", "encoding", "runs") if k in form}
            d, changed = F.save(store_root, did, fields)
            return Change(200, SAVED.format(name=d.name, fields=", ".join(changed) or "nothing changed"), d.id, changed)
        if action == "toggle":
            now = next((x for x in F.read(store_root) if x.id == did), None)
            if now is None:
                raise F.Refused("no such destination")
            d, changed = F.save(store_root, did, {"enabled": not now.enabled})
            return Change(200, SAVED.format(name=d.name, fields="on" if d.enabled else "off"), d.id, changed)
        if action == "remove":
            if form.get("sure") != "yes":
                raise F.Refused("tick the box to remove it")
            gone = F.remove(store_root, did)
            for h in gone.headers:
                if h.keyring:
                    try:
                        forward_keys.remove(gone.id, h.name)
                    except forward_keys.Unavailable:
                        pass
            return Change(200, REMOVED.format(name=gone.name), gone.id, ["removed"])
        if action in ("key", "key-remove"):
            kd = next((x for x in F.read(store_root) if x.id == did), None)
            kh = next((x for x in kd.headers if x.name == form.get("header")), None) if kd else None
            if kd is None or kh is None or not kh.keyring:
                raise F.Refused("no such header kept in the keychain")
            where = [f"{kh.name}'s value in the keychain"]
            if action == "key":
                if not form.get("value"):
                    raise F.Refused("type the value")
                forward_keys.store(kd.id, kh.name, form["value"])
                return Change(200, VALUE_STORED.format(header=kh.name), kd.id, where)
            forward_keys.remove(kd.id, kh.name)
            return Change(200, VALUE_REMOVED.format(header=kh.name), kd.id, where)
        if action == "test":
            td = next((x for x in F.read(store_root) if x.id == did), None)
            if td is None:
                raise F.Refused("no such destination")
            try:
                answer = F.send(td, F.test_trace(), timeout=10.0)
            except F.KeyMissing as e:
                return Change(200, TEST_NOT.format(why=str(e)), td.id)
            if answer.status <= 0:
                return Change(200, TEST_NOT.format(why=answer.reason), td.id)
            return Change(200, TEST_SAID.format(span=F.TEST_SPAN, status=answer.reason), td.id)
    except F.Refused as e:
        return Change(400, NOT_SAVED.format(why=str(e)), field=e.field, why=str(e), form=form)
    except forward_keys.Unavailable as e:
        return Change(503, NOT_SAVED.format(why=f"the keychain can't be used here ({e.kind or type(e).__name__})"))
    return Change(400, NOT_SAVED.format(why="not a change this page makes"))


def root_of(store) -> Path:
    """The store root forwarding keeps its files under: the folder the store's own folder is in. A team's view of the
    store has no root, by design (`team_view`); forwarding is the whole console's, so a view reads none of it."""
    if store is None or not hasattr(store, "root"):
        return Path(os.devnull)
    return Path(store.root).parent
