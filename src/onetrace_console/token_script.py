"""The one script a model step's tokenizer picker and the Settings page's Remove need on a local
console, apart so the content policy can name it without loading the page.

The picker sends the picked file's bytes as they are, `POST /model-tokenizers?digest=<the record's
tokenizer.digest>&name=<the file's name>`; Remove sends `POST /model-tokenizers/remove?digest=<digest>`, each
with the session's CSRF token from its cookie, under the same guards as the console's other presses
(`_enforce_role`, `_check_action_csrf`). On success only the button's own section is replaced, with the
same section of the page the console has drawn again: the Tokenizers page's (`data-tokenizer-section`: the steps
that ask and the kept tokenizers), or the step's own section where the picker is; the page doesn't move, and the
section's status line says what was done, announced to a screen reader. Where the section can't be read, the page
is loaded again. A refusal is said beside the button, in the console's words. Each button is bound once, however
many pickers a page holds. Named by hash in the local console's Content-Security-Policy only; no
public page carries it. Without the script the picker and the buttons stay hidden.
"""

#: What a section's status line says after a press, in place.
KEPT = "The tokenizer is kept; this step's tokens are read with it."
REMOVED = "The tokenizer is removed."

TOKEN_SCRIPT = (
    "<script>(function(){function h(){var m=document.cookie.match(/(?:^|; )onetrace_csrf=([^;]*)/),"
    "x={'Content-Type':'application/octet-stream'};if(m){x['X-CSRF-Token']=decodeURIComponent(m[1])}return x}"
    "function said(b,t){var s=b.parentNode.querySelector('[data-tokenizer-said]')||document.querySelector('[data-tokenizer-said]');"
    "if(s){s.textContent=t}}"
    "function swap(b,t){var sec=b.closest('[data-tokenizer-section]')||b.closest('section[data-section]'),y=window.scrollY;"
    "var sel=!sec?'':sec.hasAttribute('data-tokenizer-section')?'[data-tokenizer-section]':"
    "'section[data-section=\"'+sec.getAttribute('data-section')+'\"]';"
    "fetch(location.href,{credentials:'same-origin',cache:'no-store'}).then(function(r){return r.text()})"
    ".then(function(x){var n=sel&&new DOMParser().parseFromString(x,'text/html').querySelector(sel);"
    "if(!n){location.reload();return}n=document.importNode(n,true);sec.replaceWith(n);bind(n);window.scrollTo(0,y);"
    "var s=n.querySelector('[data-tokenizer-said]');if(s){setTimeout(function(){s.textContent=t},50)}},"
    "function(){location.reload()})}"
    "function send(b,url,body,t){b.disabled=true;fetch(url,{method:'POST',credentials:'same-origin',headers:h(),body:body})"
    ".then(function(r){return r.json().then(function(j){return{ok:r.ok,j:j}},"
    "function(){return{ok:false,j:{error:'the console answered '+r.status}}})})"
    ".then(function(x){if(x.ok){swap(b,t);return}b.disabled=false;said(b,String(x.j.error||'Not done'))},"
    "function(){b.disabled=false;said(b,'The console could not be reached.')})}"
    "function once(b){if(b.hasAttribute('data-tokenizer-bound'))return false;b.setAttribute('data-tokenizer-bound','');return true}"
    "function bind(root){root.querySelectorAll('button[data-tokenizer-post]').forEach(function(b){if(!once(b))return;"
    "var d=b.parentNode,l=d.querySelector('[data-tokenizer-pick-field]'),f=d.querySelector('[data-tokenizer-file]');"
    "b.hidden=false;if(l){l.hidden=false}b.addEventListener('click',function(){"
    "if(!f||!f.files.length){said(b,'Pick a file first.');return}var p=f.files[0];"
    "send(b,b.getAttribute('data-tokenizer-post')+'&name='+encodeURIComponent(p.name),p,'" + KEPT + "')})});"
    "root.querySelectorAll('button[data-tokenizer-remove]').forEach(function(b){if(!once(b))return;b.hidden=false;"
    "b.addEventListener('click',function(){send(b,b.getAttribute('data-tokenizer-remove'),'','" + REMOVED + "')})})}"
    "bind(document)})()</script>"
)
