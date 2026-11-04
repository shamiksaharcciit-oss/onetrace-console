"""The console's local tokenizers setting, `tokenizers` in its configuration file: each a folder the
person names and the files in it (`token_text` decodes with them). A relative folder is read from the
file's own folder, and an entry not of that form is refused, as every key of the file is.
"""
from __future__ import annotations

import json

import pytest


def test_the_setting_names_a_folder_and_its_files_read_from_the_file_s_folder(tmp_path, examined):
    from onetrace_console.config import load
    path = tmp_path / "console.json"
    path.write_text(json.dumps({"tokenizers": [{"folder": "models/tok", "files": ["tokenizer.json"]}]}))
    got = load(path).tokenizers
    examined(1, "tokenizers setting")
    assert got == [{"folder": str(tmp_path / "models/tok"), "files": ["tokenizer.json"]}]


@pytest.mark.parametrize("value", [
    {"folder": "x", "files": ["tokenizer.json"]},
    [{"folder": "x"}],
    [{"folder": "x", "files": []}],
    [{"folder": "x", "files": ["../tokenizer.json"]}],
    [{"folder": "x", "files": ["/etc/tokenizer.json"]}],
    [{"folder": "x", "files": ["a.json", "a.json"]}],
    [{"folder": "x", "files": ["tokenizer.json"], "url": "https://example.invalid"}],
])
def test_a_tokenizers_setting_not_of_that_form_is_refused(tmp_path, value, examined):
    from onetrace_console.config import ConfigError, load
    path = tmp_path / "console.json"
    path.write_text(json.dumps({"tokenizers": value}))
    examined(1, "malformed tokenizers setting")
    with pytest.raises(ConfigError, match="tokenizers"):
        load(path)
