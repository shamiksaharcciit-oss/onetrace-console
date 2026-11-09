"""The setup page, `/explain/setup`: how Explain is set up, in three steps, on a local console only.

It is a guide, with one form (console 0.7.0): the provider, the model's name, `base_url` and the key, and
Save, which writes the [model] table of the file the page names (`explain_config_write`) and keeps the
key in this user's keychain (`explain_keychain`), never in the file; a GET writes nothing. What it reads
of onetrace-explain's configuration is what the console already reads to say which model an
explanation is being sent to (`explain.configured_model`): the [model] table's `provider` and
`name`, never `base_url`, `params` or the key (tests/test_explain_setup.py holds it to that, with a
value planted in each). It shows the file's path, the variable `key_env` names, and whether that
variable is set in the environment the console started from -- "set" or "not set", never its value,
with the restart line where it is not (console 0.6.1 item 8). A public console has no setup page and no
link to one.

What it says is true of onetrace-explain as the console measures it (`explain.MEASURED`): the kinds
it always sends, the two command-line flags that add or hold back, that the console's Explain
button passes neither, and that its `openai` provider takes an OpenAI-compatible server on this
machine.
"""
from __future__ import annotations

import os
from pathlib import Path

from onetrace_console.words import escape

PATH = "/explain/setup"
LINK = "Set up Explain"
TITLE = "Set up Explain"
INTRO = ("Explain asks a model you choose for a suggestion about a comparison, beside what the console "
         "checked. It is optional. This page shows how it is set up; its form saves your choice to "
         "onetrace-explain's configuration.")
STEPS = ("Pick a model", "Choose what it sees", "Turn it on")
SET_HERE = "Set your model here."
#: The kinds every packet holds, in words, as onetrace-explain 0.1.0 builds it.
ALWAYS_SENT = (
    "the comparison's verdict, and where the runs first differ",
    "each stage's name, its result, and the stages it reads from",
    "each stage's instrument: its id, kind, version and configuration fingerprint",
    "each stage's outcome class",
    "each input's and output's name, digest and size in bytes, and whether it differs",
    "each setting that differs, with both values",
    "where the comparison holds them: its --for result, its end outputs, the inputs that differ, "
    "and a mask's digest",
)
STAYS = ("whole run folders", "signatures and keys", "runs outside this comparison",
         "anything on a public console")
OPTIONAL = (("--include-text", "adds the kept text of each output that differs, up to 8 KiB each. Prompts "
             "and documents are kept text, so this sends them."),
            ("--redact NAME", "sends the setting NAME by its name and digests only, never its value."))
BUTTON_USES = ("The console's Explain button prepares the packet and sends nothing; its Send button, named with "
               "the address, sends the kinds above, and the kept text only where \"Include the kept text of "
               "outputs that differ\" beside it is ticked (--include-text). It never passes --redact: to hold a "
               "value back, run onetrace-explain yourself with the flag.")
#: The install line beside the console (console 0.7.0): onetrace-explain 0.3, which reads the key from the
#: keychain, with its keyring extra. Never a dependency of the console.
INSTALL = 'pip install "onetrace-explain[keyring]>=0.3"'
#: Where the key is (console 0.7.0): the keychain or the variable; the console reads the keychain only to
#: say whether a key is stored.
WHERE_THE_KEY_IS = ("The key stays with you: in this user's keychain, kept with the form below, or in the variable "
                    "your configuration names. onetrace-explain reads it there when it sends. The console keeps and "
                    "shows no key, and reads the keychain only to say whether one is stored.")
#: The form (console 0.7.0).
PROVIDERS = (("anthropic", "anthropic"), ("openai", "openai: any OpenAI-compatible address, one on this machine too"))
FORM_HEAD = "Set it here"
FIELD_PROVIDER = "Provider"
FIELD_NAME = "Model name"
FIELD_BASE_URL = "base_url (the address; needed for openai)"
FIELD_KEY = "Key (none needed for a server on this machine)"
SAVE = "Save"
SAVED = "Saved: {path} now says, in its [model] table:"
KEPT_REST = "Every other line of the file is as it was."
CHOOSE = "Choose anthropic or openai."
NAME_NEEDED = "Give the model's name."
BASE_NEEDED = "An openai provider needs its address, base_url."
BASE_FORM = "base_url is an address starting http:// or https://."
NOT_SAVED = "Not saved: {why}."
#: The key's state, for the provider the file names (console 0.7.0): its presence only, never its value.
KEY_STORED = "A key is stored for this provider."
KEY_NONE = "No key stored."
KEY_UNREADABLE = "The keychain could not be read ({why}): unlock it, and load this page again."
REPLACE = "Replace"
REMOVE = "Remove"
FIELD_NEW_KEY = "New key"
REPLACED = "The key for this provider is replaced in the keychain."
REMOVED = "The key for this provider is removed from the keychain."
NO_MODEL_YET = "Save a model first: the key is kept for the provider the file names."
NOT_DONE = "Nothing changed: {why}."
#: A key no request can carry (onetrace-explain 0.3's own rule): refused before it reaches the keychain.
UNSENDABLE = ("the key holds a line end, another control character or a character outside ASCII, which no "
              "request can carry: paste it again without it")
#: What the page says of the keychain where the key can be kept there (console 0.7.0), in these words.
KEYCHAIN_WORDS = ("The key is kept by your operating system's keychain, under this user's login. Anyone who can "
                  "run code as this user can read it, as with an environment variable. The console stores no key.")
#: No keychain (console 0.7.0): keyring not importable in the console's Python, or no keychain that works.
KEYRING_EXTRA = '"onetrace-explain[keyring]"'
NO_KEYCHAIN = "No keychain here: {why}."
NO_KEYCHAIN_PYTHON = "This console runs from:"
NO_KEYCHAIN_INSTALL = "To keep the key in this user's keychain, install the keychain's extra into that Python:"
NO_KEYCHAIN_TODAY = "Until then, set the key in the variable key_env names, as in the example above."
PROMISES = ("A claim without a cite in the record is left out.",
            "An explanation never changes a verdict, an exit code or a CI gate.",
            "Every explanation is recorded as its own run.")

#: The setup page's look, in the console's stylesheet (`frame.stylesheet`).
SETUP_CSS = """
.cp .setup ol.steps{display:flex;flex-wrap:wrap;gap:8px 18px;list-style:none;margin:0 0 18px;padding:0}
.cp .setup ol.steps a{color:var(--accent)}
.cp .setup section.step{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-ctl);
  padding:14px 16px;margin:0 0 16px}
.cp .setup section.step h2{margin:0 0 10px}
.cp .setup .choices{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:12px}
.cp .setup .choice{border:1px solid var(--line-strong);border-radius:var(--r-ctl);padding:10px 12px;min-width:0}
.cp .setup .choice h3{margin:0 0 6px;font-size:14px}
.cp .setup .label{margin:10px 0 4px;font-size:var(--fs-small);letter-spacing:.06em;text-transform:uppercase;
  color:var(--ink-muted)}
.cp .setup ul{margin:0;padding-left:20px}
.cp .setup code{overflow-wrap:anywhere}
.cp .setup form[data-setup-form]{display:flex;flex-direction:column;gap:10px;max-width:32rem}
.cp .setup .setup-field{display:flex;flex-direction:column;gap:4px;min-width:0}
.cp .setup .setup-field :is(input,select){width:100%;min-width:0;max-width:100%}
.cp .setup form[data-setup-form] button{align-self:flex-start}
"""


def config_path() -> Path:
    """The file onetrace-explain reads, as it finds it: ONETRACE_EXPLAIN_CONFIG, or its default."""
    return Path(os.environ.get("ONETRACE_EXPLAIN_CONFIG") or Path.home() / ".config" / "onetrace" / "explain.toml")


def _as_written(text: str) -> str:
    """A path of this machine, or the model it names, as written, to be copied: `verbatim`, so a
    Windows path's backslashes are shown as they are (a record's word shows each one doubled)."""
    from onetrace_console.words import verbatim
    return verbatim(text)


def _code_block(text: str) -> str:
    """An example to copy, its lines as lines (`verbatim`, as a layer shown as written)."""
    from onetrace_console.words import verbatim
    return f"<pre><code>{verbatim(text)}</code></pre>"


def save(form: dict) -> tuple[int, str, list[str] | None]:
    """Save, from the form: (the status, what the page says, the [model] lines written or None)."""
    import re as _re
    from onetrace_console import explain_config_write as W
    from onetrace_console import explain_keychain as K
    from onetrace_console.oserror import said as os_said
    action = form.get("action", "save")
    if action in ("replace", "remove"):
        return _key_action(action, form.get("key", ""))
    provider = form.get("provider", "")
    name = form.get("name", "").strip()
    base_url = form.get("base_url", "").strip()
    key = form.get("key", "")
    if provider not in dict(PROVIDERS):
        return 400, CHOOSE, None
    if not name:
        return 400, NAME_NEEDED, None
    if base_url and not _re.match(r"https?://[^\s]+$", base_url):
        return 400, BASE_FORM, None
    if provider == "openai" and not base_url:
        return 400, BASE_NEEDED, None
    model = {"provider": provider, "name": name, "base_url": base_url}
    keep: tuple[str, ...] = ("key_env",)
    if key and unsendable(key):
        return 400, NOT_SAVED.format(why=UNSENDABLE), None
    if key:
        try:
            K.store(provider, base_url, key)
        except K.Unavailable as e:
            return 400, NOT_SAVED.format(why=str(e)), None
        model["key_source"], keep = "keyring", ()
    else:
        try:
            if K.stored(provider, base_url):
                #: A key is kept for this provider already: the file goes on reading it there.
                model["key_source"], keep = "keyring", ()
        except K.Unavailable as e:
            #: A keychain that is there and can't be read (locked) refuses, as a Save with a key does;
            #: no keyring, or no keychain, leaves the key to the variable key_env names, as before.
            if isinstance(e, K.Unreadable):
                return 400, NOT_SAVED.format(why=str(e)), None
    path = config_path()
    try:
        lines = W.write(path, model, keep=keep)
    except W.Unsafe as e:
        return 400, str(e), None
    except OSError as e:
        return 400, NOT_SAVED.format(why=os_said(e)), None
    return 200, SAVED.format(path=path), lines


def unsendable(key: str) -> bool:
    """A key no request header can carry as given, as onetrace-explain 0.3 tells one: a control character
    (a line end, a tab, NUL, DEL) or a character outside printable ASCII. Only this answer leaves here."""
    return any(ord(c) < 0x20 or ord(c) > 0x7E for c in key)


def _key_action(action: str, key: str) -> tuple[int, str, list[str] | None]:
    """Replace or Remove: the key for the provider and base_url the file names."""
    from onetrace_console import explain, explain_config_write as W
    from onetrace_console import explain_keychain as K
    from onetrace_console.oserror import said as os_said
    m = explain.model_config()
    if m is None:
        return 400, NO_MODEL_YET, None
    provider, base_url = str(m["provider"]), str(m.get("base_url") or "")
    try:
        if action == "remove":
            K.remove(provider, base_url)
            return 200, REMOVED, None
        if not key:
            return 400, NOT_DONE.format(why="give the new key"), None
        if unsendable(key):
            return 400, NOT_DONE.format(why=UNSENDABLE), None
        K.store(provider, base_url, key)
    except K.Unavailable as e:
        return 400, NOT_DONE.format(why=str(e)), None
    model = {"provider": provider, "name": str(m["name"]), "base_url": base_url, "key_source": "keyring"}
    try:
        lines = W.write(config_path(), model)
    except W.Unsafe as e:
        return 400, str(e), None
    except OSError as e:
        return 400, NOT_SAVED.format(why=os_said(e)), None
    return 200, REPLACED, lines


def _key_state(model: dict | None) -> str:
    """Whether a key is stored for the provider the file names, with Replace and Remove where one is:
    its presence only, read from the keychain; nothing where no model is named or keyring is absent."""
    from onetrace_console import explain_keychain as K
    from onetrace_console.frame import CSRF_SLOT
    if model is None:
        return ""
    try:
        has = K.stored(str(model["provider"]), str(model.get("base_url") or ""))
    except K.Unavailable as e:
        #: A keychain that is there and can't be read (locked) is said by its type; no keyring, or no
        #: keychain, shows no key line.
        if not isinstance(e, K.Unreadable):
            return ""
        why = e.kind or type(e).__name__
        return f'<p data-setup="key-state" data-key="unreadable">{escape(KEY_UNREADABLE.format(why=why))}</p>'
    if not has:
        return f'<p data-setup="key-state" data-key="none">{escape(KEY_NONE)}</p>'
    return (f'<p data-setup="key-state" data-key="stored">{escape(KEY_STORED)}</p>'
            f'<form method="post" action="/explain/setup" data-setup-form="key">{CSRF_SLOT}'
            f'<label class="setup-field"><span>{escape(FIELD_NEW_KEY)}</span>'
            f'<input type="password" name="key" autocomplete="new-password" spellcheck="false" required></label>'
            f'<button type="submit" name="action" value="replace">{escape(REPLACE)}</button></form>'
            f'<form method="post" action="/explain/setup" data-setup-form="remove">{CSRF_SLOT}'
            f'<button type="submit" name="action" value="remove">{escape(REMOVE)}</button></form>')


def no_keychain() -> str | None:
    """Why no key can be kept in a keychain here, or None where one works (a locked one works)."""
    from onetrace_console import explain_keychain as K
    try:
        K._keyring()
    except K.Unavailable as e:
        return str(e)
    return None


def _no_keychain(why: str) -> str:
    """The page's words where there is no keychain: why, the Python, its install line, today's way."""
    import sys
    from onetrace_console.neighbours.pages import _install_named
    from onetrace_console.words import verbatim
    return (f'<div data-setup="no-keychain"><p>{escape(NO_KEYCHAIN.format(why=why))}</p>'
            f'<p>{escape(NO_KEYCHAIN_PYTHON)} <code>{verbatim(sys.executable or "(not known)")}</code></p>'
            f'<p>{escape(NO_KEYCHAIN_INSTALL)}</p>'
            f'<pre><code>pip install {escape(KEYRING_EXTRA)}</code></pre>'
            + _install_named(verbatim, KEYRING_EXTRA)
            + f'<p>{escape(NO_KEYCHAIN_TODAY)}</p></div>')


def _form(model: dict | None, *, keychain: bool = True) -> str:
    """The form: the provider chosen and the name as the file has them; base_url and the key empty (the
    page shows no base_url, and never a key). No key field where there is no keychain (`keychain`)."""
    from onetrace_console.frame import CSRF_SLOT
    chosen = (model or {}).get("provider")
    options = "".join(f'<option value="{v}"{" selected" if v == chosen else ""}>{escape(w)}</option>'
                      for v, w in PROVIDERS)
    name = escape(str((model or {}).get("name") or ""), quote=True)
    return (f'<form method="post" action="/explain/setup" data-setup-form="model">{CSRF_SLOT}'
            f'<label class="setup-field"><span>{escape(FIELD_PROVIDER)}</span>'
            f'<select name="provider">{options}</select></label>'
            f'<label class="setup-field"><span>{escape(FIELD_NAME)}</span>'
            f'<input type="text" name="name" value="{name}" autocomplete="off" spellcheck="false" required></label>'
            f'<label class="setup-field"><span>{escape(FIELD_BASE_URL)}</span>'
            f'<input type="url" name="base_url" placeholder="http://127.0.0.1:8080/v1" autocomplete="off" '
            f'spellcheck="false"></label>'
            + (f'<label class="setup-field"><span>{escape(FIELD_KEY)}</span>'
               f'<input type="password" name="key" autocomplete="new-password" spellcheck="false"></label>'
               if keychain else "")
            + f'<button type="submit" name="action" value="save">{escape(SAVE)}</button></form>')


def _said(said: str, written: list[str] | None) -> str:
    if not said:
        return ""
    from onetrace_console.words import verbatim
    out = f'<p data-setup="said" role="status">{verbatim(said)}</p>'
    if written:
        out += (f'<pre data-setup="written"><code>{verbatim("".join(written))}</code></pre>'
                f'<p>{escape(KEPT_REST)}</p>')
    return f'<section class="step" data-section="setup-said">{out}</section>'


def _model_form(model: dict | None) -> str:
    """The form, and the key's state; where there is no keychain, the form without its key field, and
    the page's words on it."""
    why = no_keychain()
    if why is not None:
        return _form(model, keychain=False) + _no_keychain(why)
    return (_form(model) + f'<p data-setup="keychain-words">{escape(KEYCHAIN_WORDS)}</p>'
            + _key_state(model))


def body(store, *, said: str = "", written: list[str] | None = None) -> str:
    """The page's content: the three steps, the form in the first. `store` names the comparisons whose
    Show the packet previews the request; `said` and `written`, what a Save did."""
    from onetrace_console import explain
    path = str(config_path())
    model = explain.configured_model()
    named = model != explain.UNNAMED_MODEL
    installed = explain.command() is not None
    steps = "".join(f'<li><a href="#step-{n}">{n} · {escape(w)}</a></li>' for n, w in enumerate(STEPS, start=1))
    provider = (f'<p data-setup="model">onetrace-explain\'s configuration names <code>{_as_written(model)}</code>.</p>'
                f'<p data-setup="file">It reads <code>{_as_written(path)}</code>.</p>'
                if named else
                f'<p data-setup="model">No model is named in <code>{_as_written(path)}</code>. {escape(SET_HERE)}</p>')
    #: The variable `key_env` names, and whether it is set where the console started: never its value
    #: (console 0.6.1 item 8).
    provider += explain.key_lines(explain.key_status())
    one = (f'<section class="step" id="step-1" data-step="1"><h2>1 · {escape(STEPS[0])}</h2><div class="choices">'
           f'<div class="choice" data-choice="provider"><h3>Your model provider</h3>{provider}'
           f"<p>{escape(WHERE_THE_KEY_IS)}</p>"
           + _code_block('[model]\nprovider = "anthropic"\nname = "<model name>"\nkey_env = "<the variable holding your key>"')
           + "</div>"
           '<div class="choice" data-choice="this-machine"><h3>On this machine</h3>'
           "<p>onetrace-explain's <code>openai</code> provider takes any OpenAI-compatible address, a model "
           "server on this machine included, with no key. The request then goes to this machine only.</p>"
           + _code_block('[model]\nprovider = "openai"\nname = "<model name>"\nbase_url = "http://127.0.0.1:<port>/v1"\nkey_env = ""')
           + "</div></div>"
           f'<div class="choice" data-choice="form"><h3>{escape(FORM_HEAD)}</h3>'
           + _model_form(explain.model_config()) + "</div></section>")
    stays = "".join(f"<li>{escape(x)}</li>" for x in STAYS)
    sent = "".join(f"<li>{escape(x)}</li>" for x in ALWAYS_SENT)
    flags = "".join(f"<li><code>{escape(f)}</code> {escape(w)}</li>" for f, w in OPTIONAL)
    comparisons = sorted(store.comparisons(), key=lambda c: c.key) if store is not None else []
    links = "".join(f'<li><a href="/diff/{escape(c.key)}.html#explain" class="mono">{escape(c.key[:12])}</a></li>'
                    for c in comparisons)
    preview = ("<p>On a comparison's page, <strong>Show the packet</strong> shows the request exactly as it would "
               "be sent, and sends nothing.</p>"
               + (f'<details data-setup="comparisons"><summary>Choose a comparison ({len(comparisons)})</summary>'
                  f'<ul class="plain">{links}</ul></details>' if comparisons else
                  "<p>This console holds no comparison yet.</p>"))
    two = (f'<section class="step" id="step-2" data-step="2"><h2>2 · {escape(STEPS[1])}</h2>'
           f'<p class="label">Always stays with you</p><ul data-setup="stays">{stays}</ul>'
           f'<p class="label">Sent to the model</p><ul data-setup="sent">{sent}</ul>'
           f'<p class="label">Only when you pass the flag</p><ul data-setup="optional">{flags}</ul>'
           f'<p data-setup="button-uses">{escape(BUTTON_USES)}</p>'
           f'<p class="label">Preview the exact request</p>{preview}</section>')
    promises = "".join(f"<li>{escape(p)}</li>" for p in PROMISES)
    three = (f'<section class="step" id="step-3" data-step="3"><h2>3 · {escape(STEPS[2])}</h2>'
             f'<ul data-setup="promises">{promises}</ul>'
             '<p class="label">Then, yourself</p><ol data-setup="todo">'
             f"<li>{_code_block(INSTALL)}</li>"
             f"<li>Set <code>[model]</code> in <code>{_as_written(path)}</code>, as in step 1.</li>"
             "<li>Keep your key in this user's keychain with the form in step 1, or set it in your own "
             "environment, in the variable <code>key_env</code> names.</li></ol>"
             + (f'<p data-setup="installed">onetrace-explain is installed with this console.</p>' if installed else
                f'<p data-setup="installed">{escape(explain.NOT_INSTALLED)}</p>')
             + "</section>")
    return (f'<div class="setup" data-section="explain-setup"><h1>{escape(TITLE)}</h1><p>{escape(INTRO)}</p>'
            f'{_said(said, written)}'
            f'<ol class="steps" aria-label="The three steps">{steps}</ol>{one}{two}{three}</div>')


def page(store, *, said: str = "", written: list[str] | None = None) -> str:
    """The whole page, its frame empty for the server to fill as it does every page's."""
    from onetrace_console.render import _document
    return _document(TITLE, f'<div class="cp">{body(store, said=said, written=written)}</div>')
