"""The one script a model step's tokenizer picker and the Settings page's Remove need on a local
console, apart so the content policy can name it without loading the page.

The picker sends the picked file's bytes as they are, `POST /model-tokenizers?digest=<the record's
tokenizer.digest>&name=<the file's name>`; Remove sends `POST /model-tokenizers/remove?digest=<digest>`, each
with the session's CSRF token from its cookie, under the same guards as the console's other presses
(`_enforce_role`, `_check_action_csrf`). On success the page is loaded again; a refusal is said beside the
button, in the console's words. Named by hash in the local console's Content-Security-Policy only; no
public page carries it. Without the script the picker and the buttons stay hidden.
"""
TOKEN_SCRIPT = (
    "<script>(function(){function h(){var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/),"
    "x={'Content-Type':'application/octet-stream'};if(m){x['X-CSRF-Token']=decodeURIComponent(m[1])}return x}"
    "function said(b,t){var s=b.parentNode.querySelector('[data-tokenizer-said]')||document.querySelector('[data-tokenizer-said]');"
    "if(s){s.textContent=t}}"
    "function send(b,url,body){b.disabled=true;fetch(url,{method:'POST',credentials:'same-origin',headers:h(),body:body})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok){location.reload();return}b.disabled=false;said(b,String(x.j.error||'Not done'))},"
    "function(){b.disabled=false;said(b,'The console could not be reached.')})}"
    "document.querySelectorAll('button[data-tokenizer-post]').forEach(function(b){"
    "var d=b.parentNode,l=d.querySelector('[data-tokenizer-pick-field]'),f=d.querySelector('[data-tokenizer-file]');"
    "b.hidden=false;if(l){l.hidden=false}b.addEventListener('click',function(){"
    "if(!f||!f.files.length){said(b,'Pick a file first.');return}var p=f.files[0];"
    "send(b,b.getAttribute('data-tokenizer-post')+'&name='+encodeURIComponent(p.name),p)})});"
    "document.querySelectorAll('button[data-tokenizer-remove]').forEach(function(b){b.hidden=false;"
    "b.addEventListener('click',function(){send(b,b.getAttribute('data-tokenizer-remove'),'')})})})()</script>")
