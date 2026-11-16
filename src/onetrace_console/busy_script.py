"""Every button that starts work shows that it is working, from one shared rule.

A button that starts work carries `data-busy="<the work in progress>"` ("Sending…", "Comparing…"); an instant one (the
theme switch, Copy, the settings gear) carries none. On a local console, `BUSY_SCRIPT`, on every page the console
fills (`frame.fill`) and on the sign-in page, makes a press of one, within the same task:

- the button disabled, with `aria-busy="true"`, its label the work in progress, and a small spinner beside it (still
  under `prefers-reduced-motion`, the label carrying it alone);
- the other buttons in the same form, or in the same `data-busy-scope`, disabled too, so Cancel can't race Remove;
- a form's own press still posted as the button would have posted it (its name and value kept in a hidden field);
- after 5 s, where nothing hands over to a progress view (`data-busy-handover`), a line under it saying what it waits
  for and the seconds elapsed ("Waiting for the comparison: 12 s"): no percentage, no estimate.

The busy state always ends: on an error answer or a failed request (a fetch the press started), the button comes back
enabled with its own label, and the page's own script says the error beside it; on a successful answer that leaves the
page as it was, after 3 s; on the browser's Back (`pageshow`), no button is left busy. A second press of a busy button
does nothing. Without script, every form posts as before.

A small action's form that names its section (`data-in-place="<id>"`) posts with `fetch`, and
only that section is replaced, with the same section of the page the console answers: one drawing, so the two never
differ. The page doesn't move (its scroll position kept), focus returns to the pressed button (or the field) of
the same name in the new section, and the
section's status line (`data-status`, `aria-live="polite"`) is set again so a screen reader says it. An answer
without the section is drawn as a whole page, as a form's own post would. Without script the form posts as before,
its action ending `#<id>`, so the answer opens at the section. Named by hash in the local console's Content-Security-Policy
only; a public console's pages carry none of it, and its policy is unchanged.
"""

BUSY_CSS = """
.busy-spin{display:inline-block;width:.8em;height:.8em;margin-left:.45em;vertical-align:-.1em;border-radius:50%;
  border:2px solid var(--line-strong);border-top-color:var(--accent);animation:busy-spin .8s linear infinite}
@keyframes busy-spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){.busy-spin{animation:none;border-top-color:var(--line-strong)}}
[data-busy-wait-line]{display:block;margin-top:4px;font-size:var(--fs-small);color:var(--ink-muted)}
"""

BUSY_SCRIPT = (
    "<script>(function(){"
    "var leaving=false;window.addEventListener('beforeunload',function(){leaving=true});"
    "function scope(b){return b.closest('[data-busy-scope]')||b.form||b.parentNode}"
    "function start(b){if(b.getAttribute('aria-busy')==='true')return;"
    "b.setAttribute('data-busy-was',b.textContent);b.textContent=b.getAttribute('data-busy');"
    "b.setAttribute('aria-busy','true');"
    "var s=document.createElement('span');s.className='busy-spin';s.setAttribute('aria-hidden','true');"
    "s.setAttribute('data-busy-spin','');b.after(s);"
    "scope(b).querySelectorAll('button').forEach(function(o){if(!o.disabled){o.disabled=true;"
    "o.setAttribute('data-busy-off','')}});b.disabled=true;"
    "if(!b.hasAttribute('data-busy-handover')){var t0=Date.now(),w=b.getAttribute('data-busy-wait')||'the console';"
    "b._busyTimer=setInterval(function(){var n=Math.floor((Date.now()-t0)/1000);if(n<5)return;"
    "var l=b.parentNode.querySelector('[data-busy-wait-line]');if(!l){l=document.createElement('span');"
    "l.setAttribute('data-busy-wait-line','');l.setAttribute('role','status');s.after(l)}"
    "l.textContent='Waiting for '+w+': '+n+' s'},250)}}"
    "function end(b){if(b.getAttribute('aria-busy')!=='true')return;clearInterval(b._busyTimer);"
    "b.textContent=b.getAttribute('data-busy-was');b.removeAttribute('aria-busy');"
    "var p=b.parentNode;p.querySelectorAll('[data-busy-spin],[data-busy-wait-line]').forEach(function(x){x.remove()});"
    "scope(b).querySelectorAll('[data-busy-off]').forEach(function(o){o.disabled=false;"
    "o.removeAttribute('data-busy-off')});b.disabled=false}"
    "window.onetraceBusy={start:start,end:end};var current=null;"
    "var f=window.fetch;window.fetch=function(){var b=current;current=null;var p=f.apply(this,arguments);"
    "if(b){p.then(function(r){if(!r.ok){end(b)}else{setTimeout(function(){if(!leaving&&b.isConnected)end(b)},3000)}},"
    "function(){end(b)})}return p};"
    "document.addEventListener('click',function(e){var b=e.target.closest&&e.target.closest('button[data-busy]');"
    "if(!b||b.type==='submit')return;if(b.getAttribute('aria-busy')==='true'){e.preventDefault();"
    "e.stopImmediatePropagation();return}current=b;setTimeout(function(){start(b)},0)},true);"
    "document.addEventListener('submit',function(e){var b=e.submitter;if(!b||!b.hasAttribute('data-busy'))return;"
    "if(b.getAttribute('aria-busy')==='true'){e.preventDefault();return}"
    "if(b.name){var h=document.createElement('input');h.type='hidden';h.name=b.name;h.value=b.value;"
    "h.setAttribute('data-busy-name','');b.form.appendChild(h)}start(b)},true);"
    "document.addEventListener('submit',function(e){var f=e.target,id=f.getAttribute&&f.getAttribute('data-in-place');"
    "if(!id||e.defaultPrevented||!window.DOMParser)return;var s=document.getElementById(id);if(!s)return;"
    "e.preventDefault();var b=e.submitter,y=window.scrollY,d=new FormData(f),a=document.activeElement,"
    "fq=b&&b.name?'[name=\"'+b.name+'\"][value=\"'+b.value+'\"]':a&&a.name&&f.contains(a)?'[name=\"'+a.name+'\"]':'';"
    "if(b&&b.name&&!d.has(b.name))d.append(b.name,b.value);"
    "f.querySelectorAll('[data-busy-name]').forEach(function(x){x.remove()});"
    "fetch(f.getAttribute('action'),{method:'POST',body:new URLSearchParams(d),credentials:'same-origin'})"
    ".then(function(r){return r.text().then(function(t){var doc=new DOMParser().parseFromString(t,'text/html'),"
    "n=doc.getElementById(id);if(!n){document.open();document.write(t);document.close();return}"
    "n=document.importNode(n,true);s.replaceWith(n);window.scrollTo(0,y);"
    "var g=fq&&n.querySelector(fq);if(g&&g.type!=='hidden')g.focus({preventScroll:true});"
    "var st=n.querySelector('[data-status]');if(st){var w=st.textContent;st.textContent='';"
    "setTimeout(function(){st.textContent=w},50)}})},function(){if(b)end(b)})},false);"
    "window.addEventListener('pageshow',function(){"
    "document.querySelectorAll('button[aria-busy=\"true\"]').forEach(end);"
    "document.querySelectorAll('button[data-busy-off]').forEach(function(o){o.disabled=false;"
    "o.removeAttribute('data-busy-off')})})"
    "})()</script>"
)


def unless_needed(page: str) -> str:
    """`page` less the script where no button that starts work is left in it (a static export's page, its presses
    taken out)."""
    return page if "data-busy=" in page else page.replace(BUSY_SCRIPT, "")
