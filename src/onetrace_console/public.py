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

#: What a public page's footer says its mode is.
FOOTER_MODE = "Read-only demo"


def _script_hash() -> str:
    """The CSP hash of the one inline script the pages carry, computed from the script itself."""
    from onetrace_console.viewer.page import PRINT_SCRIPT
    body = PRINT_SCRIPT.removeprefix("<script>").removesuffix("</script>")
    return "'sha256-" + base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode() + "'"


def content_security_policy() -> str:
    """Nothing loads but the console's own stylesheet and fonts, the pages' own `<style>`, inline
    images, and the one script whose hash is named. No form may post, no page may frame it."""
    return ("default-src 'none'; style-src 'self' 'unsafe-inline'; font-src 'self'; "
            f"img-src 'self' data:; script-src {_script_hash()}; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'")


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
    return (files("onetrace_console") / "reference_demo" / "trust.json").read_bytes()


def start_refusal(config, store_root: Path) -> Refusal | None:
    """Why a public console must not start with this configuration and store, or None."""
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
                       f"demo's test key.",
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
