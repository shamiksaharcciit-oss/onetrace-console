"""Record every member of a set of release artifacts, by path and sha256.

WHY THIS EXISTS
---------------
The release artifacts are rebuilt after project ids are removed, and the rebuild must
**list every member that differs** from the files built at
`dae64ce`. Those files live in `onetrace-public/dist/`, and `onetrace-public` is regenerated
from scratch by `tools/export_public.py` on every run -- so the rebuild overwrites them. A
comparison with bytes that no longer exist is not a comparison.

So the baseline is recorded before the rebuild, not reconstructed after it. `baselines/
dae64ce.json` is the committed record; the bytes themselves are kept outside every repository
(a 4.8 MB build artifact does not belong in git history) and are only needed to say *what*
changed inside a differing member, not *which* members differ.

WHAT IT DOES NOT DO
-------------------
It does not classify a difference. Each difference is to be confirmed as a removed
process id, a new test or a README line, and that reading needs the new files in front of it.
Writing that classifier now, against no data, would be exactly the untested-hypothesis habit
the review warned against -- so it is written when there is something to run it on.

Usage:
    python tools/artifact_manifest.py baselines/dae64ce.json <file> [<file> ...]
    python tools/artifact_manifest.py --check baselines/dae64ce.json <file> [<file> ...]

`--check` recomputes and compares instead of writing, so a manifest can be re-proved against
the files it claims to describe.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tarfile
import zipfile
from pathlib import Path

FORMAT = "onetrace-console/artifact-manifest/0.1"


def members(path: Path) -> list[dict]:
    """Every FILE member: path, sha256, size. Directories are not members."""
    out: list[dict] = []
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                if not info.is_dir():
                    blob = z.read(info)
                    out.append({"path": info.filename,
                                "sha256": hashlib.sha256(blob).hexdigest(),
                                "size": len(blob)})
    else:
        # Streamed: `getmembers()` then `extractfile()` is random access on a gzip stream, so
        # tarfile re-decompresses from the start for every member (measured: minutes, not
        # seconds, for 728 members).
        with tarfile.open(path, "r|gz") as t:
            for m in t:
                if m.isfile():
                    f = t.extractfile(m)
                    blob = f.read() if f else b""
                    out.append({"path": m.name,
                                "sha256": hashlib.sha256(blob).hexdigest(),
                                "size": len(blob)})
    out.sort(key=lambda d: d["path"])
    return out


def describe(paths: list[Path], note: str = "") -> dict:
    return {
        "format": FORMAT,
        "note": note,
        "artifacts": [
            {
                "file": p.name,
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "size": p.stat().st_size,
                "members": members(p),
            }
            for p in sorted(paths, key=lambda q: q.name)
        ],
    }


def dumps(manifest: dict) -> bytes:
    """Sorted keys, LF, trailing newline: a manifest that diffs cleanly."""
    return (json.dumps(manifest, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode("utf-8")


def main(argv: list[str]) -> int:
    check = argv and argv[0] == "--check"
    if check:
        argv = argv[1:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    out, files = Path(argv[0]), [Path(a) for a in argv[1:]]
    missing = [f for f in files if not f.is_file()]
    if missing:
        print(f"not there: {missing}")
        return 2

    built = describe(files, note="" if check else _NOTE)
    if not check:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(dumps(built))
        total = sum(len(a["members"]) for a in built["artifacts"])
        print(f"{out}: {len(built['artifacts'])} artifacts, {total} members recorded")
        for a in built["artifacts"]:
            print(f"  {len(a['members']):>4} members  {a['sha256'][:16]}…  {a['file']}")
        return 0

    have = json.loads(out.read_bytes().decode("utf-8"))
    built["note"] = have.get("note", "")
    same = dumps(built) == dumps(have)
    print(f"{out}: {'MATCHES' if same else 'DIFFERS FROM'} the files given")
    if not same:
        h = {a["file"]: a for a in have["artifacts"]}
        for a in built["artifacts"]:
            was = h.get(a["file"])
            if not was:
                print(f"  not in the manifest at all: {a['file']}")
            elif was["sha256"] != a["sha256"]:
                print(f"  {a['file']}: manifest {was['sha256']}, computed {a['sha256']}")
        return 1
    return 0


_NOTE = (
    "The four onetrace / onetrace-verify release files built by standards at "
    "onetrace-sdk-bootstrap HEAD dae64ce, recorded member by member before the rebuild "
    "that removes project ids. The bytes are kept outside every repository; this "
    "manifest is what makes 'list every member that differs' answerable afterwards. Nothing "
    "here was modified, uploaded or re-pinned."
)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
