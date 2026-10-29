"""The one script a run's "Mark as benchmark" and its undo need on a local console, apart so the
content policy can name it without loading the page.

The button sends `POST /benchmark?run=<key>&mark=yes|no` to this console with the session's CSRF
token from its cookie, and the note, where one is typed, as the JSON body `{"note": ...}`; the same
guards as Compare (`_enforce_role`, `_check_action_csrf`). On success the page is loaded again, drawn
with the mark; a refusal is said beside the button, in the console's words. Named by hash in the
local console's Content-Security-Policy only; no public page carries it. Without the script the
button and the note stay hidden.
"""
BENCHMARK_SCRIPT = (
    "<script>document.querySelectorAll('button[data-benchmark-post]').forEach(function(b){"
    "b.hidden=false;var p=b.parentNode,s=p.querySelector('[data-benchmark-said]'),"
    "l=p.querySelector('[data-benchmark-note]'),n=p.querySelector('[data-benchmark-note-input]');"
    "if(l){l.hidden=false}"
    "b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/),h={'Content-Type':'application/json'};"
    "if(m){h['X-CSRF-Token']=decodeURIComponent(m[1])}b.disabled=true;"
    "fetch(b.getAttribute('data-benchmark-post'),{method:'POST',credentials:'same-origin',headers:h,"
    "body:JSON.stringify({note:n?n.value:''})})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok){location.reload();return}"
    "b.disabled=false;if(s){s.textContent=String(x.j.error||'Not marked')}},"
    "function(){b.disabled=false;if(s){s.textContent='The console could not be reached.'}})})})</script>")
