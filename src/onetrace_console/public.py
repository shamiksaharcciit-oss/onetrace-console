"""The read-only public mode: a demo of the console that anyone may open and nobody can change.

Switched on by one configuration key, `"public": true`, or by `onetrace-console demo --public`,
which sets the same key; never a default. A public console:

- refuses every write before it reads a byte of the body: one check at the top of `do_POST`,
  ahead of the routing, so a route added later is refused too (`REFUSAL`, status 403);
- serves the pages its store already holds and never draws one again -- they are drawn once,
  when the store is built (`onetrace-console demo --public --build <folder>`), and nothing is
  checked, compared or rendered while it serves;
- carries the banner on every page, through the frame (`frame.py`);
- sends the security headers below on every response, its one inline script allowed by hash;
- writes its access log to standard output, one line per request, and nothing to disk, so its
  store can be owned by another user and read-only;
- refuses to start beside sign-in, the onedoor extension, a trust file other than the demo's,
  or a store that holds accounts or tokens -- each said in words, with its fix.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: The answer to every write. Plain words: what this is, and where to go instead.
REFUSAL = ("This is a read-only demo of onetrace-console. Nothing can be uploaded or changed "
           "here. Install it to try your own runs: pip install onetrace-console.")

#: The banner every page carries in public mode, in the release's own wording.
BANNER = "A read-only demo of onetrace-console. Install it:"
BANNER_COMMAND = "pip install onetrace-console"
#: What the demo's runs are: said on every page, as the README says it. The count is the
#: builder's own pipeline list, never a typed word (`banner_runs`).
BANNER_RUNS = ("Its runs come from {count} small example pipelines, recorded when this demo "
               "was built, with no network calls and no hosted model.")
#: A count as the page's words say it.
COUNT_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten")

#: What a public page's footer says its mode is.
FOOTER_MODE = "Read-only demo"


def count_word(n: int) -> str:
    return COUNT_WORDS[n] if n < len(COUNT_WORDS) else str(n)


def banner_runs() -> str:
    """The banner's sentence on the demo's runs, its count read from the demo's builder."""
    from onetrace_console.demo_store import pipeline_names
    return BANNER_RUNS.format(count=count_word(len(pipeline_names())))


def _script_hash(script: str) -> str:
    """The CSP hash of one inline script, computed from the script itself."""
    body = script.removeprefix("<script>").removesuffix("</script>")
    return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'"


def inline_scripts() -> tuple[str, ...]:
    """Every inline script a page may carry: the print helper on the viewer's pages, the
    Overview's relative times, the watched folder's notice, and the theme switch's two."""
    from onetrace_console.frame import THEME_HEAD_SCRIPT, THEME_SCRIPT
    from onetrace_console.viewer.page import PRINT_SCRIPT
    from onetrace_console.words import RELATIVE_TIME_SCRIPT, WATCH_SCRIPT
    return (PRINT_SCRIPT, RELATIVE_TIME_SCRIPT, WATCH_SCRIPT, THEME_HEAD_SCRIPT, THEME_SCRIPT)


def content_security_policy(*, local: bool = False) -> str:
    """Nothing loads but the console's own stylesheet and fonts, the pages' own `<style>`, inline
    images, and the scripts whose hashes are named. No form may post, no page may frame it. A
    script runs only by its exact hash: never `'unsafe-inline'`, never another host.

    `local`: the console on this machine, which also lets the watched folder's notice ask the
    console itself what it has taken in (`connect-src 'self'`). Nothing else differs."""
    from onetrace_console.explain_script import EXPLAIN_SCRIPT
    #: The explanation panel's buttons are a local console's only: a public one has no button and
    #: refuses every POST, so its policy does not name their script.
    hashes = " ".join(_script_hash(s) for s in inline_scripts() + ((EXPLAIN_SCRIPT,) if local else ()))
    return ("default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            f"img-src 'self' data:; script-src {hashes}; "
            + ("connect-src 'self'; " if local else "")
            + "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


def security_headers() -> tuple[tuple[str, str], ...]:
    """Sent on every response in public mode."""
    return (("X-Frame-Options", "DENY"),
            ("X-Content-Type-Options", "nosniff"),
            ("Cross-Origin-Resource-Policy", "same-origin"),
            ("Referrer-Policy", "no-referrer"),
            ("Strict-Transport-Security", "max-age=31536000"),
            ("Content-Security-Policy", content_security_policy()))


@dataclass(frozen=True)
class Refusal:
    message: str
    fix: str


def demo_trust_bytes() -> bytes:
    """The packaged demo's trust file, the only one a public console may name."""
    from importlib.resources import files
    return (files("onetrace_console") / "demo_store" / "trust.json").read_bytes()


#: A public console that can't read its own store or build record: refused in one line, never a
#: traceback, so the host's log stays the access log and nothing else.
UNREADABLE = ("public is true and {path} cannot be read ({why}). A public console checks the demo "
              "it serves against the build record before it starts, and can't check what it can't read.")
UNREADABLE_FIX = ("make the demo's folder readable, not writable, by the user the console runs as "
                  "(chmod -R a+rX,a-w <folder>), or build it again with onetrace-console demo "
                  "--public --build <folder>.")


def start_refusal(config, store_root: Path) -> Refusal | None:
    """Why a public console must not start with this configuration and store, or None. A file it
    can't read while checking is a refusal like any other, never an exception."""
    try:
        return _start_refusal(config, store_root)
    except OSError as e:
        return Refusal(UNREADABLE.format(path=e.filename or store_root,
                                         why=e.strerror or type(e).__name__), UNREADABLE_FIX)


def _start_refusal(config, store_root: Path) -> Refusal | None:
    from onetrace_console.serve import ACCOUNTS_DIRNAME, PAGES_DIRNAME, TOKENS_DIRNAME
    if config.sign_in.get("enabled"):
        return Refusal("public is true and sign_in.enabled is true. A public console has no "
                       "accounts and no sign-in.",
                       "set sign_in.enabled to false, or remove public.")
    if config.extensions.get("onedoor"):
        return Refusal("public is true and extensions.onedoor is true. A public console serves "
                       "the demo's runs only.",
                       "set extensions.onedoor to false, or remove public.")
    trust = config.trust_file
    try:
        same = trust is not None and Path(trust).read_bytes() == demo_trust_bytes()
    except OSError:
        same = False
    if not same:
        return Refusal(f"public is true and trust_file is {trust!r}, which is not the packaged "
                       f"demo's trust file. A public console serves the demo, signed with the "
                       f"demo's key.",
                       "name the trust.json that onetrace-console demo --public --build wrote "
                       "beside the store.")
    held = [name for name in (ACCOUNTS_DIRNAME, TOKENS_DIRNAME)
            if any((store_root / name).glob("*.json"))]
    if held:
        return Refusal(f"public is true and the store at {store_root} holds "
                       f"{' and '.join(held)}. A public console never serves a store set up "
                       f"for sign-in or delivery.",
                       "serve a store built for the demo with onetrace-console demo --public "
                       "--build <folder>.")
    if not (store_root / PAGES_DIRNAME / "home.html").is_file():
        return Refusal(f"public is true and the store at {store_root} has no pages drawn. A "
                       f"public console serves the pages its store was built with and draws "
                       f"none itself.",
                       "build the store first with onetrace-console demo --public --build "
                       "<folder>, and name its store folder as store_root.")
    from onetrace_console.demo_store import check_build_record
    problems = check_build_record(Path(trust).parent)
    if problems:
        return Refusal(f"public is true and the demo built beside {trust} is not the one its "
                       f"builder recorded: {'; '.join(problems[:5])}"
                       f"{' and more' if len(problems) > 5 else ''}. A public console serves "
                       f"only the demo exactly as it was built.",
                       "build it again with onetrace-console demo --public --build <folder>.")
    return None


class StdoutAccessLog:
    """The access log of a public console: one JSON line per request on standard output, which
    the host keeps, and nothing on disk. Same `append` as `access_log.AccessLog`."""

    def __init__(self, stream=None):
        self._stream = stream
        self._lock = threading.Lock()

    def append(self, *, principal: str, method: str, path: str, status: int) -> None:
        line = json.dumps({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                           "principal": principal, "method": method, "path": path,
                           "status": status}, ensure_ascii=False)
        stream = self._stream or sys.stdout
        with self._lock:
            stream.write(line + "\n")
            stream.flush()
