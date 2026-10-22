"""The one script the explain panel's buttons need, apart so the content policy can name it
without loading the panel.

Each button sends its own request to this console, with the session's CSRF token from its cookie,
then reloads the page. Named by hash in the local console's Content-Security-Policy only
(`public.content_security_policy`); no public page carries it.
"""
EXPLAIN_SCRIPT = (
    "<script>document.querySelectorAll('button[data-explain-post]').forEach(function(b){"
    "b.hidden=false;b.addEventListener('click',function(){"
    "var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/);b.disabled=true;"
    "fetch(b.getAttribute('data-explain-post'),{method:'POST',credentials:'same-origin',"
    "headers:m?{'X-CSRF-Token':decodeURIComponent(m[1])}:{}})"
    ".then(function(){location.reload()},function(){b.disabled=false})})})</script>")
