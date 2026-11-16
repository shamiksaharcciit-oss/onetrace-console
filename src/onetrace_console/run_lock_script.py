"""The one script "Load as not closed" needs on a local console's Runs page, apart so the content policy can
name it without loading the page.

The button sends `POST /runs/load-not-closed?folder=<name>` to this console, with the session's CSRF token from
its cookie where there is one. On success the page is loaded again, drawn with the run; a refusal is said
beside the button, in the console's words. Named by hash in the local console's Content-Security-Policy only;
no public page carries it. Without the script the button stays hidden.
"""

LOAD_NOT_CLOSED_SCRIPT = (
    "<script>document.querySelectorAll('button[data-load-not-closed]').forEach(function(b){"
    "b.hidden=false;var s=b.parentNode.querySelector('[data-load-not-closed-said]');"
    "b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/),h={};"
    "if(m){h['X-CSRF-Token']=decodeURIComponent(m[1])}b.disabled=true;"
    "fetch(b.getAttribute('data-load-not-closed'),{method:'POST',credentials:'same-origin',headers:h})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok){location.reload();return}"
    "b.disabled=false;if(s){s.textContent=String(x.j.error||'Not loaded')}},"
    "function(){b.disabled=false;if(s){s.textContent='The console could not be reached.'}})})})</script>"
)
