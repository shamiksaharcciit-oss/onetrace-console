"""A public console never decodes a model step's tokens: decoding there would publish the model's
output text. With a tokenizer named that matches the record exactly, a public console's step page still
shows the step and the ids only, as it did before, and reads no tokenizer file at all.
"""
from __future__ import annotations

import re

from tests.test_token_text import IDS, _digest, _folder, _tokenizer_json, step_page


def test_a_public_console_shows_the_step_and_the_ids_and_no_text(tmp_path, monkeypatch, examined):
    from onetrace_console import token_text
    files = {"tokenizer.json": _tokenizer_json()}
    named = ((_folder(tmp_path, files), ("tokenizer.json",)),)
    local = step_page(_digest(files), named)
    assert 'class="token-text"' in local, "the same record and tokenizer decode on a local console"
    read = []
    real = token_text.hashed
    monkeypatch.setattr(token_text, "hashed", lambda *a: read.append(a) or real(*a))
    page = step_page(_digest(files), named, public=True)
    examined(len(IDS), "steps on a public page")
    assert read == [], "a public console reads no tokenizer file"
    assert 'class="token-text"' not in page and "data-token-text" not in page and "data-appears" not in page
    assert "decoded with tokenizer" not in page and "cannot be shown" not in page
    rows = re.findall(r'data-decode-step="(\d+)"><td[^>]*>\d+</td><td[^>]*><code>(\d+)</code></td></tr>', page)
    assert rows == [(str(i), t) for i, t in enumerate(IDS)]


def test_a_public_render_holds_no_tokenizer(examined):
    from onetrace_console.frame import rendering, tokenizers
    examined(1, "public render")
    with rendering(onedoor=False, sign_in=False, public=True, tokenizers=(("/models/tok", ("tokenizer.json",)),)):
        assert tokenizers() == ()
    with rendering(onedoor=False, sign_in=False, tokenizers=(("/models/tok", ("tokenizer.json",)),)):
        assert tokenizers() == (("/models/tok", ("tokenizer.json",)),)
