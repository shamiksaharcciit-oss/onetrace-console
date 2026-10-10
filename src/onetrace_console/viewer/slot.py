"""The fingerprint slot's text, and the one-liner a reader types. Imports nothing.

Kept apart from `fingerprint.py` so the renderer can print the slot and the command without
importing a module that can hash: "the renderer cannot compute a fingerprint" stays a
property of what `page.py` can reach (`viewer/tests/test_structure.py`).
"""
from __future__ import annotations

OPEN, CLOSE = "<!--fingerprint-->", "<!--/fingerprint-->"
ZEROS = "0" * 64
SLOT = OPEN + ZEROS + CLOSE

#: What a reader types, with `{file}` replaced by the page's file name.
STANDALONE_CHECK = (
    'python3 -c "import hashlib,re,sys;b=open(sys.argv[1],\'rb\').read();'
    'm=re.findall(rb\'<!--fingerprint-->([0-9a-f]{{64}})<!--/fingerprint-->\',b);'
    'assert len(m)==1,\'expected exactly one fingerprint\';'
    'z=b.replace(b\'<!--fingerprint-->\'+m[0],b\'<!--fingerprint-->\'+b\'0\'*64);'
    'print(\'matches\' if hashlib.sha256(z).hexdigest()==m[0].decode() else \'DOES NOT MATCH\')" '
    '{file}')
