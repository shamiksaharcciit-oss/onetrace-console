"""The build context holds what every Dockerfile copies, and nothing the export never ships.

`.dockerignore` leaves everything out and lets back in each COPY source. This reads every tracked
`Dockerfile`, takes the sources of its COPY and ADD lines, and applies `.dockerignore`'s own rules
(a pattern matches a path or any folder above it; `*` stays within one path segment, `**` crosses
them; the last pattern that matches decides, `!` letting a path back in) to every tracked file:
- every file a COPY source names, or holds, reaches the build;
- `.dockerignore` names no path under the export's `NEVER`, so it carries no internal name;
- no tracked file under `NEVER` reaches the build.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

try:
    from tools.export_public import NEVER
except ImportError:   # the public tree has no export tool, and its never-ship files are already absent
    NEVER = ()

REPO = Path(__file__).resolve().parent.parent


def tracked() -> list[str]:
    return [p for p in subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                                      check=True).stdout.split("\0") if p]


def patterns(text: str) -> list[tuple[bool, re.Pattern]]:
    """[(is an exception, compiled pattern)] in file order."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        keep = line.startswith("!")
        body = line[1:] if keep else line
        body = body.strip("/")
        rx = "".join(".*" if tok == "**" else "[^/]*" if tok == "*" else "[^/]" if tok == "?" else re.escape(tok)
                     for tok in re.findall(r"\*\*|\*|\?|[^*?]+", body))
        out.append((keep, re.compile(rx + r"\Z")))
    return out


def in_context(path: str, rules) -> bool:
    """Whether `path` reaches the build: the last rule matching it, or a folder above it, decides."""
    parts = path.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]
    included = True
    for keep, rx in rules:
        if any(rx.match(p) for p in prefixes):
            included = keep
    return included


def copy_sources(dockerfile: str) -> list[str]:
    """The context paths a Dockerfile's COPY and ADD lines read (a copy from another stage reads none)."""
    out = []
    for line in dockerfile.splitlines():
        words = line.strip().split(None, 1)
        if len(words) < 2 or words[0].upper() not in ("COPY", "ADD"):
            continue
        rest = words[1].strip()
        args = json.loads(rest) if rest.startswith("[") else rest.split()
        flags = [a for a in args if a.startswith("--")]
        if any(f.startswith("--from=") for f in flags):
            continue
        out += [a.lstrip("./").rstrip("/") or "." for a in [a for a in args if not a.startswith("--")][:-1]]
    return out


def dockerfiles() -> dict[str, str]:
    return {p: (REPO / p).read_text(encoding="utf-8") for p in tracked() if p.rsplit("/", 1)[-1] == "Dockerfile"}


def test_there_are_dockerfiles_and_each_copies_something():
    found = dockerfiles()
    assert "Dockerfile" in found and "deploy/fly/Dockerfile" in found, sorted(found)
    assert all(copy_sources(text) for text in found.values()), found


def test_every_copy_source_of_every_dockerfile_reaches_the_build(examined):
    rules = patterns((REPO / ".dockerignore").read_text(encoding="utf-8"))
    files = tracked()
    missing, checked = [], 0
    for name, text in sorted(dockerfiles().items()):
        for src in copy_sources(text):
            held = [f for f in files if f == src or f.startswith(src + "/")]
            assert held, f"{name}: COPY {src} names no tracked file"
            for f in held:
                checked += 1
                if not in_context(f, rules):
                    missing.append(f"{name}: COPY {src} -> {f}")
    examined(checked, "tracked files a COPY line reads")
    assert not missing, missing


def test_the_dockerignore_names_no_path_the_export_never_ships():
    named = [line.strip() for line in (REPO / ".dockerignore").read_text(encoding="utf-8").splitlines()
             if line.strip() and not line.startswith("#")]
    bare = [n.lstrip("!").strip("/") for n in named]
    hits = [n for n, b in zip(named, bare) for never in NEVER
            if b == never.rstrip("/") or b.startswith(never) or never.startswith(b + "/")]
    assert not hits, hits


def test_nothing_the_export_never_ships_reaches_the_build():
    rules = patterns((REPO / ".dockerignore").read_text(encoding="utf-8"))
    leaked = [f for f in tracked() if f.startswith(tuple(NEVER)) and in_context(f, rules)]
    assert not leaked, leaked
