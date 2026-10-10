"""Write a SHA256SUMS sidecar for a fixture directory. Digests are computed, never typed
(X-11): this is the one place that writes `tests/fixtures/r11/SHA256SUMS`.

Usage:
    python tools/hash_fixture.py <directory> <sidecar-path>
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root, out = Path(argv[0]), Path(argv[1])
    lines = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            rel = p.relative_to(root).as_posix()
            lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel}")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{out}: {len(lines)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
