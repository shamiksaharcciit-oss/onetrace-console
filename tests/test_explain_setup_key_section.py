"""The Set up Explain page's key section reads as one thing.

With a key stored, the model form shows no key field, and its Save keeps the stored key, as it already did with no
key given; the page says so beside the button. The key section below has "New key" and Replace (secondary) in one
row, and Remove (destructive) on its own row under "Remove the stored key", at least 16 px from Replace. With no key
stored, the model form keeps its key field; with a keychain that can't be read, or no keychain, as before. In each of
the four states the page has exactly one key field, or none.
"""

from __future__ import annotations

import re

import pytest

from onetrace_console import explain_keychain as K
from onetrace_console import explain_setup as S

KEY_FIELD = re.compile(r'<input type="password" name="key"')
MODEL = {"provider": "anthropic", "name": "a-model", "base_url": "", "key_source": "keyring"}


def _drawn(monkeypatch, state: str) -> str:
    monkeypatch.setattr(S, "no_keychain", lambda: "keyring is not installed" if state == "no keychain" else None)

    def stored(provider, base_url):
        if state == "locked":
            raise K.Unreadable("the keychain is locked", "KeyringLocked")
        return state == "stored"

    monkeypatch.setattr(K, "stored", stored)
    return S._model_form(MODEL)


@pytest.mark.parametrize(
    "state, fields", [("none", 1), ("stored", 1), ("locked", 1), ("no keychain", 0)], ids=lambda x: str(x)
)
def test_each_state_has_one_key_field_or_none(monkeypatch, state, fields, examined):
    examined(1, f"the page, {state}")
    assert len(KEY_FIELD.findall(_drawn(monkeypatch, state))) == fields


def test_with_a_key_stored_the_model_form_has_no_key_field_and_says_save_keeps_it(monkeypatch, examined):
    drawn = _drawn(monkeypatch, "stored")
    model = re.search(r'<form[^>]*data-setup-form="model".*?</form>', drawn, re.S).group(0)
    examined(2, "the model form")
    assert not KEY_FIELD.search(model)
    assert "Save keeps the stored key." in model


def test_new_key_and_replace_are_one_row_and_remove_stands_apart(monkeypatch, examined):
    drawn = _drawn(monkeypatch, "stored")
    key = re.search(r'<form[^>]*data-setup-form="key".*?</form>', drawn, re.S).group(0)
    remove = re.search(r'<div data-setup="remove-key">.*?</div>', drawn, re.S).group(0)
    examined(3, "the key section")
    assert "New key" in key and 'class="btn-secondary"' in key and ">Replace<" in key
    assert "Remove the stored key" in remove and 'class="btn-destructive"' in remove and ">Remove<" in remove
    assert drawn.index('data-setup-form="key"') < drawn.index('data-setup="remove-key"')
    #: One row: the key form is a row; Remove's block is 16 px or more below it.
    assert re.search(r'form\[data-setup-form="key"\]\{[^}]*flex-direction:row', S.SETUP_CSS)
    gap = re.search(r'\[data-setup="remove-key"\]\{[^}]*margin-top:(\d+)px', S.SETUP_CSS)
    assert gap and int(gap.group(1)) >= 16


def test_with_no_key_stored_the_model_form_keeps_its_key_field(monkeypatch, examined):
    drawn = _drawn(monkeypatch, "none")
    model = re.search(r'<form[^>]*data-setup-form="model".*?</form>', drawn, re.S).group(0)
    examined(1, "the model form")
    assert KEY_FIELD.search(model) and "Save keeps the stored key." not in drawn
