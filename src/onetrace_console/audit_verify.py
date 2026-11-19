"""Check an onetrace-console audit log: `python audit_verify.py <folder> [--checkpoint <seq>:<digest>] [--heads <file>]`.

One file of the standard library alone, so it can be copied out of the console and run by any Python 3.10 or later,
with nothing installed. `onetrace-console audit verify` runs the same code.

The folder is the log's (`<store_root>/audit_log/`) or an export of it (`audit export`). It checks:

- every entry's line: JSON, its fields there;
- `seq` runs from 1 with no gap, across the segments, and the segments are numbered with none missing;
- each entry's `prev` is `"sha256:"` and the sha256 of the previous entry's line as stored, without its newline; the
  first entry's is null;
- `HEAD.json` names the last entry's `seq` and digest, its segment and that segment's size;
- with `--checkpoint`, or a `CHECKPOINT` file in the folder, that the entry at that `seq` has that digest: an entry
  up to the newest checkpoint held cannot be cut or edited unseen;
- with `--heads`, or a `heads.jsonl` file in the folder, the heads written off the store's volume on every append:
  each must be an entry of the chain, and the newest the chain's last entry. This shows a cut tail, and a chain
  written again from its first entry;
- with a `SHA256SUMS` file in the folder, every file it names, and that it names every file.

One line per check, `[PASS]` or `[FAIL]`, the check and what was found; exit 0 when every check passed, 1 otherwise,
2 for a usage error.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

FIELDS = ("seq", "at", "actor", "event", "object", "detail", "prev")
_SEGMENT = re.compile(r"(\d{6})\.jsonl")
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


#: Deeper than this, a line is said as not an entry before it is parsed: the verifier reads files it did not write,
#: and the standard library's parser recurses (the console's own reader bounds JSON the same way).
MAX_DEPTH = 64


def _too_deep(data: bytes) -> bool:
    """Whether `data` nests arrays or objects deeper than MAX_DEPTH, counted outside strings."""
    depth, in_string, escaped = 0, False, False
    for c in data:
        if in_string:
            if escaped:
                escaped = False
            elif c == 0x5C:
                escaped = True
            elif c == 0x22:
                in_string = False
        elif c == 0x22:
            in_string = True
        elif c in (0x5B, 0x7B):
            depth += 1
            if depth > MAX_DEPTH:
                return True
        elif c in (0x5D, 0x7D):
            depth -= 1
    return False


def _parse(data: bytes):
    """`data` as JSON, or ValueError: nested past MAX_DEPTH, or not JSON."""
    if _too_deep(data):
        raise ValueError(f"nested deeper than {MAX_DEPTH}")
    return json.loads(data)


def _digest(line: bytes) -> str:
    return "sha256:" + hashlib.sha256(line).hexdigest()


def _rows_for_sums(folder: Path) -> list[tuple[str, str, str]]:
    sums = folder / "SHA256SUMS"
    if not sums.is_file():
        return []
    named: dict[str, str] = {}
    for line in sums.read_text(encoding="utf-8").splitlines():
        if line.strip():
            want, _, name = line.partition("  ")
            named[name.strip()] = want.strip()
    present = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {"SHA256SUMS"}
    bad = sorted(n for n, want in named.items() if not (folder / n).is_file() or _sha(folder / n) != want)
    unnamed = sorted(present - set(named))
    if bad or unnamed:
        said = []
        if bad:
            said.append(f"differs or missing: {', '.join(bad)}")
        if unnamed:
            said.append(f"not named: {', '.join(unnamed)}")
        return [("FAIL", "SHA256SUMS", "; ".join(said))]
    return [("PASS", "SHA256SUMS", f"{len(named)} files, each as named, and none unnamed")]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(folder, checkpoint: str | None = None, heads=None) -> list[tuple[str, str, str]]:
    """The checks' rows, each (outcome, check, what was found)."""
    folder = Path(folder)
    rows: list[tuple[str, str, str]] = []
    if checkpoint is None and (folder / "CHECKPOINT").is_file():
        checkpoint = (folder / "CHECKPOINT").read_text(encoding="utf-8").strip()
    if heads is None and (folder / "heads.jsonl").is_file():
        heads = folder / "heads.jsonl"

    segments = sorted((int(m.group(1)), p) for p in folder.iterdir() if (m := _SEGMENT.fullmatch(p.name)))
    if not segments:
        return [("FAIL", "segments", f"no NNNNNN.jsonl segment in {folder}")]
    numbers = [n for n, _ in segments]
    missing = sorted(set(range(numbers[0], numbers[-1] + 1)) - set(numbers))
    if numbers[0] != 1 or missing:
        gaps = ([f"before {numbers[0]:06d}"] if numbers[0] != 1 else []) + [f"{n:06d}" for n in missing]
        rows.append(("FAIL", "segments", f"{len(segments)} present; missing: {', '.join(gaps)}"))
    else:
        rows.append(("PASS", "segments", f"{len(segments)}, numbered 000001 to {numbers[-1]:06d} with none missing"))

    chain: list[tuple[int, str]] = []
    problems: list[str] = []
    prev: str | None = None
    want_seq = 1
    last_size = 0
    for _n, path in segments:
        data = path.read_bytes()
        last_size = len(data)
        for i, line in enumerate(data.split(b"\n")):
            if not line:
                continue
            where = f"{path.name} line {i + 1}"
            try:
                entry = _parse(line)
            except ValueError:
                problems.append(f"{where}: not JSON")
                prev = None
                continue
            if not isinstance(entry, dict) or [k for k in FIELDS if k not in entry]:
                problems.append(f"{where}: not an entry (its fields are {', '.join(FIELDS)})")
                continue
            if entry["seq"] != want_seq:
                problems.append(f"{where}: seq {entry['seq']!r} where {want_seq} comes next")
            if entry["prev"] != prev:
                problems.append(f"{where}: prev {entry['prev']!r} is not the previous line's digest {prev!r}")
            prev = _digest(line)
            chain.append((entry["seq"], prev))
            want_seq = (entry["seq"] if isinstance(entry["seq"], int) else want_seq) + 1
    if problems:
        shown = "; ".join(problems[:5]) + (f"; and {len(problems) - 5} more" if len(problems) > 5 else "")
        rows.append(("FAIL", "chain", shown))
    else:
        rows.append(("PASS", "chain", f"{len(chain)} entries, seq 1 to {len(chain)}, each prev its line's digest"))

    last = chain[-1] if chain else (0, None)
    head_path = folder / "HEAD.json"
    try:
        head = _parse(head_path.read_bytes())
        named = (head.get("seq"), head.get("head"), head.get("segment"), head.get("segment_size"))
        found = (last[0], last[1], numbers[-1], last_size)
        if named == found:
            rows.append(("PASS", "HEAD.json", f"seq {last[0]}, {last[1]}"))
        else:
            rows.append(("FAIL", "HEAD.json", f"names seq, head, segment, size {named}; the segments give {found}"))
    except (OSError, ValueError, AttributeError) as e:
        rows.append(("FAIL", "HEAD.json", f"could not be read: {type(e).__name__}"))

    digests = dict(chain)
    if checkpoint:
        seq_text, _, want = checkpoint.partition(":")
        if not (seq_text.isdigit() and _DIGEST.fullmatch(want)):
            rows.append(("FAIL", "checkpoint", f"{checkpoint!r} is not <seq>:sha256:<64 hex>"))
        elif digests.get(int(seq_text)) == want:
            rows.append(("PASS", "checkpoint", f"the entry at seq {seq_text} has the digest held"))
        elif int(seq_text) not in digests:
            rows.append(
                ("FAIL", "checkpoint", f"no entry at seq {seq_text}: the chain ends at {last[0]}, cut after it")
            )
        else:
            rows.append(("FAIL", "checkpoint", f"the entry at seq {seq_text} is {digests[int(seq_text)]}, not {want}"))

    if heads is not None:
        try:
            held = [_parse(x) for x in Path(heads).read_bytes().splitlines() if x.strip()]
            pairs = [(h["seq"], h["head"]) for h in held]
        except (OSError, ValueError, KeyError, TypeError) as e:
            rows.append(("FAIL", "heads", f"{heads} could not be read: {type(e).__name__}"))
        else:
            strangers = [s for s, d in pairs if digests.get(s) != d]
            newest = max(pairs) if pairs else None
            if strangers:
                rows.append(
                    (
                        "FAIL",
                        "heads",
                        f"{len(strangers)} of {len(pairs)} heads are not entries of this chain (first at seq "
                        f"{strangers[0]}): it was edited, or written again",
                    )
                )
            elif newest is not None and newest != last:
                rows.append(("FAIL", "heads", f"the newest head is seq {newest[0]}; the chain ends at {last[0]}"))
            elif newest is None:
                rows.append(("FAIL", "heads", "no head is held"))
            else:
                rows.append(("PASS", "heads", f"{len(pairs)} heads, each an entry of the chain, the newest its last"))

    rows.extend(_rows_for_sums(folder))
    return rows


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    usage = "usage: audit_verify.py <folder> [--checkpoint <seq>:<digest>] [--heads <file>]"
    opts: dict[str, str] = {}
    rest: list[str] = []
    while argv:
        a = argv.pop(0)
        if a in ("--checkpoint", "--heads") and argv:
            opts[a] = argv.pop(0)
        elif a.startswith("-"):
            print(usage, file=sys.stderr)
            return 2
        else:
            rest.append(a)
    if len(rest) != 1 or not Path(rest[0]).is_dir():
        print(usage, file=sys.stderr)
        return 2
    rows = verify(rest[0], opts.get("--checkpoint"), opts.get("--heads"))
    for outcome, check, detail in rows:
        print(f"[{outcome}] {check} -- {detail}")
    return 0 if all(r[0] == "PASS" for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
