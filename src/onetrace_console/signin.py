"""Sign-in step 2: TLS, local accounts, sessions, CSRF -- the pieces `serve.py` wires
together, kept separate so each is testable without a live server. Standard library only.
"""

from __future__ import annotations

import secrets
import ssl
from html import escape
from http.cookies import SimpleCookie
from pathlib import Path

SESSION_COOKIE = "onetrace_session"
CSRF_COOKIE = "onetrace_csrf"
CSRF_FIELD = "csrf_token"


class InsecureListenerError(RuntimeError):
    """Refuses to start: sign-in is on, and this listener would send passwords and
    session cookies over the network in clear text.
    """


def refuse_if_insecure(config) -> None:
    """The listener refusal, as its own test target: called once, early, from `main()`.

    With `sign_in.enabled` false, this never raises -- sign-in isn't happening at all,
    so there is nothing to protect. With it true: either the console is bound to
    loopback (an operator's own TLS-terminating proxy is expected to sit in front of
    it), or both `sign_in.tls_cert_path` and
    `sign_in.tls_key_path` are configured (checked as a pair already, in
    `config.py`'s own validation) so this process serves HTTPS itself. Anything else
    -- a non-loopback host with no TLS configured -- is refused outright.
    """
    if not config.sign_in.get("enabled"):
        return
    loopback = config.host in ("127.0.0.1", "localhost", "::1")
    #: The escape hatch that lets a cookie be non-`Secure` (for a
    #: console behind an operator's own TLS-terminating proxy, reached over HTTPS
    #: by the browser but reached in plain HTTP by this process itself) is refused
    #: outright the moment the listener is not loopback -- it exists for exactly
    #: one shape (loopback behind a local proxy), never for a directly
    #: network-reachable listener, TLS-terminating or not.
    if config.sign_in.get("insecure_cookie_for_local_dev") and not loopback:
        raise InsecureListenerError(
            f"refusing to start: sign_in.insecure_cookie_for_local_dev is true and "
            f"this console would listen on {config.host!r}, not loopback. That flag "
            f"exists only for a loopback listener sitting behind a local, "
            f"HTTPS-terminating reverse proxy -- never for a listener a client can "
            f"reach directly."
        )
    tls_configured = bool(config.sign_in.get("tls_cert_path")) and bool(config.sign_in.get("tls_key_path"))
    if loopback or tls_configured:
        return
    raise InsecureListenerError(
        f"refusing to start: sign_in.enabled is true and this console would listen on "
        f"{config.host!r}, not loopback, with no TLS certificate configured "
        f"(sign_in.tls_cert_path / sign_in.tls_key_path both empty). Passwords and "
        f"session cookies must never cross the network in clear text -- either "
        f"configure both TLS keys, or bind host to loopback behind your own "
        f"TLS-terminating proxy."
    )


def build_ssl_context(config) -> ssl.SSLContext | None:
    """`None` if TLS isn't configured (nothing to wrap the socket with); a real,
    loaded `SSLContext` otherwise. Never called unless `refuse_if_insecure` has
    already passed -- this does not re-check the loopback/no-TLS combination.
    """
    cert = config.sign_in.get("tls_cert_path")
    key = config.sign_in.get("tls_key_path")
    if not cert or not key:
        return None
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    #: Explicit rather than relying on OpenSSL's own build-time
    #: default (which drifts across versions and distributions): TLS 1.0 and 1.1
    #: are refused outright, never negotiated.
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(Path(cert)), keyfile=str(Path(key)))
    return ctx


def cookies_secure(config) -> bool:
    """`Secure` on every session cookie whenever sign-in is on, not
    only when this process itself terminates TLS -- a console behind an
    operator's own TLS-terminating proxy listens on plain loopback HTTP, but the
    browser still reaches it over HTTPS, so the cookie must still say `Secure`.
    The only way to get `False` here is the explicit
    `sign_in.insecure_cookie_for_local_dev` escape hatch, which `refuse_if_insecure`
    already refuses to start at all outside a loopback listener.
    """
    return not config.sign_in.get("insecure_cookie_for_local_dev")


def parse_cookies(header: str | None) -> dict[str, str]:
    jar = SimpleCookie()
    if header:
        jar.load(header)
    return {k: v.value for k, v in jar.items()}


def set_cookie_header(name: str, value: str, *, http_only: bool, secure: bool, max_age: int | None = None) -> str:
    """One `Set-Cookie` header value. `SameSite=Strict` and (when `secure`) `Secure`
    are always present -- never optional flags a caller could forget to pass.
    """
    parts = [f"{name}={value}", "Path=/", "SameSite=Strict"]
    if http_only:
        parts.append("HttpOnly")
    if secure:
        parts.append("Secure")
    if max_age is not None:
        parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def clear_cookie_header(name: str, *, secure: bool) -> str:
    parts = [f"{name}=", "Path=/", "SameSite=Strict", "Max-Age=0"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def new_csrf_form_token() -> str:
    """A pre-auth CSRF token for the sign-in FORM itself -- there is no session yet to
    hang a synchronizer token off, so this is the double-submit-cookie pattern: the
    same value goes into a cookie and a hidden form field; `POST /signin` checks they
    match. Never `HttpOnly` (the form must be able to read it back... in fact it
    doesn't need to; the value is embedded server-side when the page is rendered, so
    it never needs JS access at all -- kept non-HttpOnly only because the cookie and
    the rendered field must demonstrably be independent channels for the check to
    mean anything).
    """
    return secrets.token_urlsafe(32)


def render_signin_page(*, csrf_token: str, error: str | None = None) -> str:
    """The local accounts' sign-in page, in the console's frame (`_frame`): its theme and its column."""
    error_html = f'<p data-section="error">{escape(error)}</p>\n' if error else ""
    return _frame(
        "Sign in",
        f"""<h1>Sign in</h1>
{error_html}<form method="post" action="/signin">
<input type="hidden" name="{CSRF_FIELD}" value="{escape(csrf_token, quote=True)}">
<label>Username <input type="text" name="username" autocomplete="username"></label>
<label>Password <input type="password" name="password" autocomplete="current-password"></label>
<button class="btn-primary" data-busy="Signing in…" type="submit">Sign in</button>
</form>""",
    )


def parse_signin_form(body: bytes) -> dict[str, str]:
    from urllib.parse import parse_qsl

    return dict(parse_qsl(body.decode("utf-8", errors="replace")))


def render_signed_out_page(entra_sign_out: str | None) -> str:
    """After sign-out through Entra ID: the console's session is ended; Entra's own sign-out is offered
    (its end-session endpoint), as signing out of the console does not sign anyone out of Microsoft."""
    if entra_sign_out:
        offer = "<p>You are still signed in to Microsoft in this browser.</p>\n" + _button_to(
            entra_sign_out, "Sign out of Microsoft too", busy="Signing out of Microsoft…", section="entra-sign-out"
        )
    else:
        offer = "<p>Microsoft's own sign-out could not be reached; you are still signed in to Microsoft here.</p>"
    return _frame(
        "Signed out",
        "<h1>You're signed out of onetrace</h1>\n"
        '<p data-section="signed-out">You\'re signed out of onetrace in this browser.</p>\n'
        f'{offer}\n<p><a href="/signin">Sign in again</a></p>',
    )


def _frame(title: str, body: str) -> str:
    """Sign-in through Entra ID's pages: the console's stylesheet and theme (the saved choice applied
    before the first paint, as every page does), in the shell's main column. No navigation: no one is
    signed in yet to use it."""
    from onetrace_console.busy_script import BUSY_SCRIPT
    from onetrace_console.frame import STYLESHEET, THEME_HEAD_SCRIPT

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
{THEME_HEAD_SCRIPT}<link rel="stylesheet" href="{STYLESHEET}"></head>
<body>
<div class="shell"><main><div class="cp">
<header data-frame><div class="brand">onetrace</div></header>
{body}
</div></main></div>
{BUSY_SCRIPT}
</body></html>
"""


def _button_to(
    action: str,
    words: str,
    *,
    busy: str,
    primary: bool = False,
    fields: dict[str, str] | None = None,
    section: str = "",
) -> str:
    """A button that goes somewhere: a GET form, in the console's button styles (`frame.BUTTON_CSS`), whose press
    starts work and says so (`busy_script`)."""
    hidden = "".join(
        f'<input type="hidden" name="{escape(k, quote=True)}" value="{escape(v, quote=True)}">'
        for k, v in (fields or {}).items()
    )
    marked = f' data-section="{section}"' if section else ""
    if primary:
        button = f'<button class="btn-primary" data-busy="{escape(busy, quote=True)}" type="submit">'
    else:
        button = f'<button class="btn-secondary" data-busy="{escape(busy, quote=True)}" type="submit">'
    return f'<form method="get" action="{escape(action, quote=True)}"{marked}>{hidden}{button}{escape(words)}</button></form>'


def render_oidc_signin_page(next_path: str) -> str:
    """Sign-in through Entra ID: one button, to the flow's start, carrying where to return."""
    return _frame(
        "Sign in",
        "<h1>Sign in</h1>\n"
        "<p>This console signs you in with your organisation's Microsoft account.</p>\n"
        + _button_to(
            "/signin/oidc/start",
            "Sign in with Microsoft",
            busy="Signing in…",
            primary=True,
            fields={"next": next_path or "/"},
            section="oidc-start",
        ),
    )


def render_oidc_refused_page(reason: str, *, no_role: bool = False) -> str:
    """A sign-in through Entra ID refused, saying why in the console's own words; or, with `no_role`,
    the person signed in at Microsoft holds no onetrace role."""
    title = "No role in onetrace" if no_role else "Sign-in refused"
    section = "no-role" if no_role else "signin-refused"
    return _frame(
        title,
        f"<h1>{escape(title)}</h1>\n"
        f'<p data-section="{section}">{escape(reason)}</p>\n'
        + _button_to("/signin", "Start again", busy="Opening the sign-in page…"),
    )


def render_signed_in_page(next_path: str) -> str:
    """After the callback: the session's cookies are set on this answer, and the page moves on to the
    path recorded before the flow. A redirect would not do: the browser arrived from Microsoft's site, and
    a `SameSite=Strict` cookie is not sent on the request a cross-site redirect makes."""
    target = escape(next_path, quote=True)
    return _frame(
        "Signed in",
        f'<meta http-equiv="refresh" content="0;url={target}">\n'
        f'<p data-section="signed-in">Signed in. <a href="{target}">Continue</a></p>',
    )


def flow_cookie_header(value: str, *, secure: bool, max_age: int) -> str:
    """The sign-in flow's cookie: `SameSite=Lax`, so it reaches the callback a navigation from Microsoft
    makes; `HttpOnly`; only under the flow's own path."""
    from onetrace_console.oidc_flow import FLOW_COOKIE, FLOW_COOKIE_PATH

    parts = [f"{FLOW_COOKIE}={value}", f"Path={FLOW_COOKIE_PATH}", "SameSite=Lax", "HttpOnly", f"Max-Age={max_age}"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
