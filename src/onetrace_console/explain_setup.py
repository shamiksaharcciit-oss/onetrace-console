"""The setup page, `/explain/setup`: how Explain is set up, in three steps, on a local console only.

It is a guide, and it changes nothing: no form, no button, nothing it sends or saves. What it reads
of onetrace-explain's configuration is what the console already reads to say which model an
explanation is being sent to (`explain.configured_model`): the [model] table's `provider` and
`name`, never `key_env`, `base_url`, `params` or the key (tests/test_explain_setup.py holds it to
that, with a value planted in each). Where no model is named, it shows the file's path. A public
console has no setup page and no link to one.

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
         "checked. It is optional. This page shows how it is set up, and changes nothing.")
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
BUTTON_USES = ("The console's Explain button passes neither flag: it sends the kinds above and nothing more. "
               "To send text, or to hold a value back, run onetrace-explain yourself with the flag.")
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


def body(store) -> str:
    """The page's content, read-only: the three steps. `store` names the comparisons whose Show the
    packet previews the request."""
    from onetrace_console import explain
    path = str(config_path())
    model = explain.configured_model()
    named = model != explain.UNNAMED_MODEL
    installed = explain.command() is not None
    steps = "".join(f'<li><a href="#step-{n}">{n} · {escape(w)}</a></li>' for n, w in enumerate(STEPS, start=1))
    provider = (f'<p data-setup="model">onetrace-explain\'s configuration names <code>{_as_written(model)}</code>.</p>'
                if named else
                f'<p data-setup="model">No model is named in <code>{_as_written(path)}</code>. {escape(SET_HERE)}</p>')
    one = (f'<section class="step" id="step-1" data-step="1"><h2>1 · {escape(STEPS[0])}</h2><div class="choices">'
           f'<div class="choice" data-choice="provider"><h3>Your model provider</h3>{provider}'
           "<p>The key stays in your own environment, in the variable your configuration names: "
           "onetrace-explain reads it there when it sends, and the console never reads, keeps or shows it.</p>"
           + _code_block('[model]\nprovider = "anthropic"\nname = "<model name>"\nkey_env = "<the variable holding your key>"')
           + "</div>"
           '<div class="choice" data-choice="this-machine"><h3>On this machine</h3>'
           "<p>onetrace-explain's <code>openai</code> provider takes any OpenAI-compatible address, a model "
           "server on this machine included, with no key. The request then goes to this machine only.</p>"
           + _code_block('[model]\nprovider = "openai"\nname = "<model name>"\nbase_url = "http://127.0.0.1:<port>/v1"\nkey_env = ""')
           + "</div></div></section>")
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
             f"<li>{_code_block('pip install onetrace-explain')}</li>"
             f"<li>Set <code>[model]</code> in <code>{_as_written(path)}</code>, as in step 1.</li>"
             "<li>Set your key in your own environment, in the variable <code>key_env</code> names.</li></ol>"
             + (f'<p data-setup="installed">onetrace-explain is installed with this console.</p>' if installed else
                f'<p data-setup="installed">{escape(explain.NOT_INSTALLED)}</p>')
             + "</section>")
    return (f'<div class="setup" data-section="explain-setup"><h1>{escape(TITLE)}</h1><p>{escape(INTRO)}</p>'
            f'<ol class="steps" aria-label="The three steps">{steps}</ol>{one}{two}{three}</div>')


def page(store) -> str:
    """The whole page, its frame empty for the server to fill as it does every page's."""
    from onetrace_console.render import _document
    return _document(TITLE, f'<div class="cp">{body(store)}</div>')
