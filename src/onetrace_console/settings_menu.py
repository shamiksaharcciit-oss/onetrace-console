"""The settings button at the top right (console 0.6.1 item 13): Explain and neighbours, set up there.

Turning on Explain and neighbours is setup, not navigation, so it is under a gear button at the top
right of every page a local console fills as it serves it, in place of the sidebar's "Set up Explain"
link. The gear opens a small menu, one row per feature, each linking to its setup page (whose addresses
are unchanged) and saying its state, from the same checks those pages use:

- "Explain: on, <model> (<provider>)", "Explain: not set up" or "Explain: key not found"; where the
  configuration keeps its key in the keychain (console 0.7.0), "Explain: key stored", "Explain: no key
  stored" or "Explain: the keychain can't be read (<its type>)";
- "Neighbours: on, <model>", "Neighbours: off" or "Neighbours: extra not installed".

A dot on the gear says that something set up has stopped working -- the variable `key_env` names is not
set, no key is stored in the keychain where the table says `key_source = "keyring"` (console 0.7.0), or a
turned-on local model's file is missing -- never that something is not set up, which is a
choice. Nothing of a key's value is read or drawn: whether its variable is set, and no more.

The menu is the browser's own popover (`popover`, `popovertarget`), with no script: the button is a
real button named "Settings", and the menu closes on Esc and on a click outside. A public console and a
static export draw no gear; a sealed page (a run's pages) keeps the frame its seal covers.
"""
from __future__ import annotations

from dataclasses import dataclass

from onetrace_console.words import escape

MENU_ID = "settings-menu"
NAME = "Settings"
BROKEN = "A setup has stopped working; the menu says which."


@dataclass(frozen=True)
class Row:
    feature: str           # "explain" or "neighbours"
    words: str
    href: str
    state: str             # "on", "off" (not set up, or not installed) or "broken"


def explain_row() -> Row:
    """Explain's row, from the checks its setup page and panel use (`explain`)."""
    from onetrace_console import explain
    from onetrace_console.explain_setup import PATH
    m = explain.model_config()
    if explain.command() is None or m is None:
        return Row("explain", "Explain: not set up", PATH, "off")
    if m.get("key_source") == "keyring":
        #: Read before key_env, as onetrace-explain 0.3 reads it.
        return _keychain_row(m)
    status = explain.key_status()
    if status is not None and not status["set"]:
        return Row("explain", "Explain: key not found", PATH, "broken")
    return Row("explain", f"Explain: on, {m['name']} ({m['provider']})", PATH, "on")


KEY_STORED = "Explain: key stored"
NO_KEY_STORED = "Explain: no key stored"
UNREADABLE = "Explain: the keychain can't be read ({kind})"


def _keychain_row(m: dict) -> Row:
    """The row where the table keeps its key in the keychain (console 0.7.0), in three states, as
    onetrace-explain 0.3 tells them apart: a key stored for the provider and base_url the table names, none
    stored, or the keychain can't be read (locked, keyring missing, no keychain), by its error's type. Only
    the key's presence is read."""
    from onetrace_console import explain_keychain as K
    from onetrace_console.explain_setup import PATH
    try:
        stored = K.stored(str(m["provider"]), str(m.get("base_url") or ""))
    except K.Unavailable as e:
        return Row("explain", UNREADABLE.format(kind=e.kind or type(e).__name__), PATH, "broken")
    return Row("explain", KEY_STORED, PATH, "on") if stored else Row("explain", NO_KEY_STORED, PATH, "broken")


def neighbours_row(store) -> Row:
    """Neighbours' row, from the checks its setup page uses (`neighbours`, `neighbours.settings`). A
    turned-on local model's files are checked for being there, not hashed: that is done before use."""
    from onetrace_console import neighbours
    from onetrace_console.neighbours.pages import PATH
    href = f"/{PATH}"
    setting = None
    if store is not None:
        from onetrace_console.neighbours import settings
        setting = settings.read(store)
    if not neighbours.installed():
        return Row("neighbours", "Neighbours: extra not installed", href, "broken" if setting else "off")
    if setting is None:
        return Row("neighbours", "Neighbours: off", href, "off")
    chosen = setting["embedder"]
    if chosen.get("kind") == "endpoint":
        return Row("neighbours", f"Neighbours: on, {chosen.get('model', '')} (your endpoint)", href, "on")
    from onetrace_console.neighbours import embedder
    model = embedder.MODELS.get(chosen.get("model", ""))
    if model is None:
        return Row("neighbours", f"Neighbours: on, {chosen.get('model', '')}: not a model this console has",
                   href, "broken")
    where = embedder.folder(embedder.models_root(store), model)
    if not all((where / p).is_file() for p in model.files):
        return Row("neighbours", f"Neighbours: on, {model.name}: a model file is missing", href, "broken")
    return Row("neighbours", f"Neighbours: on, {model.name}", href, "on")


def tokenizers_row(store) -> Row:
    """The tokenizers this console keeps (`token_upload`), each removable on its page."""
    from pathlib import Path

    from onetrace_console import token_upload
    n = len(token_upload.kept(Path(store.root))) if store is not None else 0
    words = "Tokenizers: none kept" if n == 0 else f"Tokenizers: {n} kept"
    return Row("tokenizers", words, f"/{token_upload.PATH}", "on" if n else "off")


def rows(store) -> list[Row]:
    return [explain_row(), neighbours_row(store), tokenizers_row(store)]


GEAR_SVG = ('<svg class="gear-mark" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">'
            '<path fill="currentColor" d="M19.4 13a7.6 7.6 0 0 0 0-2l2.1-1.6-2-3.5-2.5 1a7.4 7.4 0 0 0-1.7-1L15 3h-4'
            'l-.4 2.9a7.4 7.4 0 0 0-1.7 1l-2.5-1-2 3.5L6.6 11a7.6 7.6 0 0 0 0 2l-2.1 1.6 2 3.5 2.5-1a7.4 7.4 0 0 0 1.7 1'
            'L11 21h4l.4-2.9a7.4 7.4 0 0 0 1.7-1l2.5 1 2-3.5zM13 15.5a3.5 3.5 0 1 1 0-7 3.5 3.5 0 0 1 0 7z"/></svg>')


def menu(store) -> str:
    """The gear and its menu, as a local console fills it into a page it serves."""
    got = rows(store)
    broken = any(r.state == "broken" for r in got)
    dot = (f'<span class="dot" data-frame="settings-dot" title="{escape(BROKEN)}"></span>'
           f'<span class="visually-hidden">: {escape(BROKEN)}</span>') if broken else ""
    items = "".join(f'<li><a href="{escape(r.href)}" data-setting="{r.feature}" data-state="{r.state}">'
                    f"{escape(r.words)}</a></li>" for r in got)
    return (f'<div class="settings" data-frame="settings">'
            f'<button type="button" class="gear" popovertarget="{MENU_ID}" aria-label="{NAME}" '
            f'data-frame="gear"{" data-broken" if broken else ""}>{GEAR_SVG}{dot}</button>'
            f'<div id="{MENU_ID}" popover data-frame="settings-menu"><p class="settings-head">{escape(NAME)}</p>'
            f'<ul class="plain">{items}</ul></div></div>')


#: The gear's look: fixed at the top right, in the theme's own ink and lines; the menu under it.
SETTINGS_CSS = """
.settings{position:fixed;top:10px;right:14px;z-index:30}
.settings .gear{display:inline-flex;align-items:center;position:relative;font:inherit;color:var(--ink);
  background:var(--surface);border:1px solid var(--line-strong);border-radius:var(--r-ctl);padding:5px 7px;
  cursor:pointer}
.settings .gear:hover{background:var(--surface-sunk)}
.settings .gear:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.settings .gear .dot{position:absolute;top:-4px;right:-4px;width:10px;height:10px;border-radius:50%;
  background:var(--cc-ink);border:2px solid var(--surface)}
.settings .visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.settings [popover]{position:fixed;inset:auto;top:52px;right:14px;margin:0;min-width:min(300px,calc(100vw - 28px));
  max-width:calc(100vw - 28px);background:var(--surface);color:var(--ink);border:1px solid var(--line-strong);
  border-radius:var(--r-ctl);padding:8px 0}
.settings .settings-head{margin:0 14px 6px;font-size:var(--fs-small);color:var(--ink-muted)}
.settings [popover] ul{list-style:none;margin:0;padding:0}
.settings [popover] a{display:block;padding:7px 14px;color:var(--accent);overflow-wrap:anywhere}
.settings [popover] a:focus-visible{outline:2px solid var(--accent);outline-offset:-2px}
.settings [popover] a[data-state=broken]{color:var(--cc-ink);font-weight:600}
"""
