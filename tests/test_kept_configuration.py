"""The configuration comparison shows a step's kept configuration's values, not only a changed fingerprint.

On onetrace 0.8.0's own vectors (`tests/format_04_item8/`): A11 keeps step `a`'s configuration whole; A18 keeps the
same step's in part, its `overlap` left out; A02 keeps none.

- Where both steps kept theirs, each key is an item with both values, after the fingerprint.
- A key left out of a file kept in part reads "not recorded", never "same".
- Nothing is drawn from a kept file whose bytes don't match its recorded digest, or whose rows the verifier FAILs, or
  where either step kept none.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent / "format_04_item8" / "accept"


def _step(folder: Path, file: str = "receipts/01-a.json", rows=()):
    from onetrace_console.config_compare import Step, node_id

    receipt = json.loads((folder / file).read_text(encoding="utf-8"))
    return Step(node_id(receipt), receipt, file, lambda path: (folder / path).read_bytes(), tuple(rows))


def test_both_kept_each_key_is_an_item_with_both_values(examined):
    from onetrace_console import config_compare as cc

    items = cc.kept_configuration(
        _step(HERE / "A11-empty-config-expectations"), _step(HERE / "A18-config-kept-partial"), None
    )
    examined(len(items), "kept keys")
    assert [(i.name, i.word, i.reference, i.this) for i in items] == [
        ("kept configuration chunk_size", cc.ITEM_SAME, "512", "512"),
        ("kept configuration overlap", cc.NOT_RECORDED, "64", ""),
    ]


def test_a_changed_value_is_named_with_both_values(tmp_path, examined):
    from onetrace_console import config_compare as cc

    changed = tmp_path / "changed"
    shutil.copytree(HERE / "A11-empty-config-expectations", changed)
    raw = b'{"chunk_size":"1024","overlap":"64"}'
    (changed / "config" / "01-a" / "config.json").write_bytes(raw)
    receipt = json.loads((changed / "receipts" / "01-a.json").read_text(encoding="utf-8"))
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    receipt["config_kept"] = {**receipt["config_kept"], "digest": digest, "bytes": str(len(raw))}
    receipt["instrument"]["config_digest"] = digest
    (changed / "receipts" / "01-a.json").write_text(json.dumps(receipt), encoding="utf-8")
    ref, mine = _step(HERE / "A11-empty-config-expectations"), _step(changed)
    items = cc.config_fingerprint(ref, mine, None) + cc.kept_configuration(ref, mine, None)
    assert cc.ITEMS.index(cc.kept_configuration) == cc.ITEMS.index(cc.config_fingerprint) + 1
    examined(len(items), "items")
    assert [(i.name, i.word) for i in items] == [
        ("configuration fingerprint", cc.ITEM_DIFFERS),
        ("kept configuration chunk_size", cc.ITEM_DIFFERS),
        ("kept configuration overlap", cc.ITEM_SAME),
    ]
    assert (items[1].reference, items[1].this) == ("512", "1024")


def test_nothing_is_drawn_from_a_file_that_does_not_match_or_that_fails(tmp_path, examined):
    from onetrace_console import config_compare as cc

    bent = tmp_path / "bent"
    shutil.copytree(HERE / "A11-empty-config-expectations", bent)
    (bent / "config" / "01-a" / "config.json").write_bytes(b'{"chunk_size":"9","overlap":"64"}')
    examined(3, "steps")
    assert cc.kept_config(_step(bent)) is None
    failing = [{"name": "receipts/01-a.json: config_kept file", "result": "FAIL", "detail": "planted"}]
    assert cc.kept_config(_step(HERE / "A11-empty-config-expectations", rows=failing)) is None
    assert (
        cc.kept_configuration(_step(HERE / "A02-closed-recorder"), _step(HERE / "A11-empty-config-expectations"), None)
        == []
    )
