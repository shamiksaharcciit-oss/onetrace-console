"""The one script the explain panel's buttons need, apart so the content policy can name it
without loading the panel.

Each button sends its own request to this console, with the session's CSRF token from its cookie.
Explain and Send answer at once (202) and the work goes on: the script then reads the press's state
from the console each second (`GET /explain/state`), says it in the panel's running line, and
reloads the page when the press has ended. Show the packet and Run answer when done, and the page
is reloaded. A refusal (a press while one runs, or any other) is said in the panel, in the console's
words. Named by hash in the local console's Content-Security-Policy only
(`public.content_security_policy`); no public page carries it.
"""
EXPLAIN_SCRIPT = (
    "<script>(function(){var s=document.querySelector('section[data-section=explain]');if(!s)return;"
    "var c=s.getAttribute('data-c');"
    "function line(n){var p=s.querySelector('[data-explain='+n+']');if(!p){p=document.createElement('p');"
    "p.setAttribute('data-explain',n);var at=s.querySelector('[data-explain=buttons]');"
    "if(at){s.insertBefore(p,at)}else{s.appendChild(p)}}return p}"
    "function started(){s.querySelectorAll('[data-explain=failed],[data-explain=unreached],[data-explain=refused],"
    "[data-explain=asks],[data-explain=refused-press]').forEach(function(e){e.remove()});poll()}"
    "function poll(){fetch('/explain/state?c='+encodeURIComponent(c),{credentials:'same-origin'})"
    ".then(function(r){return r.json()}).then(function(t){if(!t.running){location.reload();return}"
    "line('running').textContent=t.words+', started '+t.started+' ('+t.elapsed+' s so far).';"
    "setTimeout(poll,1000)},function(){setTimeout(poll,2000)})}"
    "s.querySelectorAll('button[data-explain-post]').forEach(function(b){"
    "b.hidden=false;b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/);b.disabled=true;"
    "fetch(b.getAttribute('data-explain-post'),{method:'POST',credentials:'same-origin',"
    "headers:m?{'X-CSRF-Token':decodeURIComponent(m[1])}:{}})"
    ".then(function(r){if(r.status===202){started();return}if(r.ok){location.reload();return}"
    "return r.json().then(function(j){b.disabled=false;line('refused-press').textContent=j.error},"
    "function(){b.disabled=false;line('refused-press').textContent='The console answered '+r.status+'.'})},"
    "function(){b.disabled=false})})});"
    "if(s.querySelector('[data-explain=running]'))poll()})()</script>")
