"""The one script the Compare buttons on a local console's "Choose run B" page need, apart so the
content policy can name it without loading the page.

Each button sends `POST /compare` for its pair to this console, with the session's CSRF token from
its cookie -- the same request the row shows as text, and the same guards (`_enforce_role`,
`_check_action_csrf`) as any other -- then opens the comparison page the console answers with. A
refusal is said on its own line under the request, in the console's own words with a full stop
put at its end where it has none, and the button is offered again.
Named by hash in the local console's Content-Security-Policy only (`public.content_security_policy`);
no public page carries it. Without the script the button stays hidden and the request stays shown.
"""
COMPARE_SCRIPT = (
    "<script>document.querySelectorAll('button[data-compare-post]').forEach(function(b){"
    "b.hidden=false;var s=b.parentNode.querySelector('[data-compare-said]');"
    "function said(t){t=String(t).trim();return /[.!?\\u2026]$/.test(t)?t:t+'.'}"
    "b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/);b.disabled=true;"
    "if(s){s.textContent='Comparing\\u2026'}"
    "fetch(b.getAttribute('data-compare-post'),{method:'POST',credentials:'same-origin',"
    "headers:m?{'X-CSRF-Token':decodeURIComponent(m[1])}:{}})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok&&x.j.pages&&x.j.pages.diff){location.href=x.j.pages.diff;return}"
    "b.disabled=false;if(s){s.textContent=said(x.j.error||x.j.answer||'Not compared')}},"
    "function(){b.disabled=false;if(s){s.textContent='The console could not be reached.'}})})})</script>")


#: A static export (console 0.7.0): a Compare control shown disabled, with one line, as the first-run-to-leave
#: control is (`bisect_page.exported`).
NEEDS_CONSOLE = "Needs a running console."
_LIVE = __import__("re").compile(r'<button type="button" hidden data-compare-post="[^"]*">([^<]*)</button>')
_SAID = __import__("re").compile(r'<span data-compare-said[^>]*></span>')


def exported(page: str) -> str:
    """A page as a static export shows it: each Compare button disabled, with "Needs a running console.";
    no script that reads the session's CSRF cookie, and no line about the session's token."""
    from onetrace_console.choose_pages import HOW_EXPORTED, HOW_LOCAL
    page = page.replace(COMPARE_SCRIPT, "").replace(HOW_LOCAL, HOW_EXPORTED)
    page = _LIVE.sub(lambda m: f'<button type="button" disabled data-compare-needs-console>{m.group(1)}</button> '
                               f'<span data-needs-console>{NEEDS_CONSOLE}</span>', page)
    return _SAID.sub("", page)
