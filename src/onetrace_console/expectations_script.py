"""The one script a run's "Check against an expectations file" needs on a local console, apart so the
content policy can name it without loading the page.

The button sends `POST /expectations?run=<key>` to this console with the session's CSRF token from its
cookie, and the file's path as the JSON body `{"path": ...}`; the same guards as the benchmark mark
(`_enforce_role`, `_check_action_csrf`). On success the page is loaded again, drawn with the rows; a
refusal is said beside the button, in the console's words. Named by hash in the local console's
Content-Security-Policy only; no public page carries it. Without the script the button and the field
stay hidden.
"""
EXPECTATIONS_SCRIPT = (
    "<script>document.querySelectorAll('button[data-expectations-after-post]').forEach(function(b){"
    "b.hidden=false;var p=b.parentNode,s=p.querySelector('[data-expectations-after-said]'),"
    "l=p.querySelector('[data-expectations-after-field]'),n=p.querySelector('[data-expectations-after-path]');"
    "if(l){l.hidden=false}"
    "b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/),h={'Content-Type':'application/json'};"
    "if(m){h['X-CSRF-Token']=decodeURIComponent(m[1])}b.disabled=true;"
    "fetch(b.getAttribute('data-expectations-after-post'),{method:'POST',credentials:'same-origin',headers:h,"
    "body:JSON.stringify({path:n?n.value:''})})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok){location.reload();return}"
    "b.disabled=false;if(s){s.textContent=String(x.j.error||'Not checked')}},"
    "function(){b.disabled=false;if(s){s.textContent='The console could not be reached.'}})})})</script>")
