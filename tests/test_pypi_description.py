"""PyPI's description of the console: the README, with its relative images and links made absolute.

PyPI shows the description without the repository around it, so a relative image there is a broken
image and a relative link a broken link. `pyproject.toml`'s `readme` names PYPI_DESCRIPTION.md: the
README with each relative image under `https://raw.githubusercontent.com/<repository>/v<version>/`
and each relative link under `https://github.com/<repository>/blob/v<version>/`, and nothing else
changed. <repository> is the public repository, and v<version> the release tag the release's
`main` commit is tagged with: every image the description shows loads from that base, and names a
screenshot the export ships.
"""
from __future__ import annotations

import email
import os
import re
import subprocess
import sys
import tarfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: A Markdown image or link whose target is relative: no scheme, not a fragment, not rooted.
RELATIVE = re.compile(r"(!?)(\[[^\]]*\]\()(?![a-z][a-z0-9+.-]*:|#|/)([^)\s]+)(\))")
#: An image's base: the repository (OWNER/NAME) and the release tag.
IMAGE_BASE = re.compile(r"https://raw\.githubusercontent\.com/([^\s)]+?)/(v\d[^/\s)]*)/")
#: A Markdown image's absolute target.
ABSOLUTE_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
#: The public repository's address, the one exact form in which this file names it.
PUBLIC_ADDRESS = "github.com/shamiksaharcciit-oss/onetrace-console"
#: The public repository the description's images and links name (OWNER/NAME).
PUBLIC_REPOSITORY = PUBLIC_ADDRESS.removeprefix("github.com/")
#: The token the description held until the public repository's name was confirmed. It is built
#: from two halves, so this file holds no copy of it.
PLACEHOLDER = "@PUBLIC_" + "REPOSITORY@"
#: Where the README's images live. The export ships this folder whole (tools/test_export_public.py),
#: so a tracked file under it is in the export.
SCREENSHOTS = "docs/screenshots/"


def _version() -> str:
    return re.search(r'^version\s*=\s*"([^"]+)"', (REPO / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M).group(1)


def _tracked() -> set[str]:
    return set(filter(None, subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                                           check=True).stdout.split("\0")))


def image_base() -> str:
    """The base every image in the description loads from: the public repository at the release tag."""
    return f"https://raw.githubusercontent.com/{PUBLIC_REPOSITORY}/v{_version()}/"


def image_problems(description: str, shipped: set[str]) -> list[str]:
    """What is wrong with the description's absolute images; empty when each is under image_base()
    and names a screenshot in `shipped`."""
    base, images = image_base(), ABSOLUTE_IMAGE.findall(description)
    wrong = [] if images else ["the description shows no image"]
    for url in images:
        path = url[len(base):]
        if not url.startswith(base):
            wrong.append(f"{url} is not under {base}")
        elif not path.startswith(SCREENSHOTS) or path not in shipped:
            wrong.append(f"{path} is not a screenshot the export ships")
    return wrong


def placeholder_left(files: dict[str, bytes]) -> list[str]:
    """The files that still hold a copy of the placeholder."""
    return sorted(p for p, data in files.items() if PLACEHOLDER.encode() in data)


def expected(readme: str, repository: str, tag: str) -> str:
    image = f"https://raw.githubusercontent.com/{repository}/{tag}/"
    link = f"https://github.com/{repository}/blob/{tag}/"
    return RELATIVE.sub(lambda m: m.group(1) + m.group(2) + (image if m.group(1) else link) + m.group(3)
                        + m.group(4), readme)


def drift(readme: str, description: str) -> list[str]:
    """What is wrong with the description, read against the README; empty when it is right."""
    bases = set(IMAGE_BASE.findall(description))
    if len(bases) != 1:
        return [f"the description's images should share one repository and tag: {sorted(bases)}"]
    (repository, tag), = bases
    wrong = []
    if tag != f"v{_version()}":
        wrong.append(f"the images point at {tag}, not this version's tag v{_version()}")
    if description != expected(readme, repository, tag):
        wrong.append("PYPI_DESCRIPTION.md is not the README with only its relative images and links made "
                     "absolute: run python3 tools/pypi_description.py")
    return wrong


def test_pyproject_s_readme_is_the_pypi_description():
    assert re.search(r'^readme\s*=\s*"PYPI_DESCRIPTION\.md"', (REPO / "pyproject.toml").read_text(encoding="utf-8"),
                     re.M)


def test_the_description_is_the_readme_with_only_its_relative_targets_made_absolute():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    description = (REPO / "PYPI_DESCRIPTION.md").read_text(encoding="utf-8")
    assert RELATIVE.findall(readme), "the premise: the README has relative images"
    assert drift(readme, description) == []
    assert not RELATIVE.findall(description)


def test_drift_is_caught():
    readme = "# x\n\n![a](docs/a.png) and [b](B.md) and [c](https://example.org/c)\n"
    good = expected(readme, "owner/name", f"v{_version()}")
    assert drift(readme, good) == []
    assert drift(readme + "a new line\n", good)                                 # README edited, not regenerated
    assert drift(readme, good.replace("owner/name", "other/name", 1))           # two bases
    assert drift(readme, good.replace(f"v{_version()}", "v9.9.9"))              # another release's tag
    assert drift(readme, readme)                                                 # nothing made absolute


def test_each_image_in_the_description_is_a_shipped_screenshot_at_the_release_tag(examined):
    description = (REPO / "PYPI_DESCRIPTION.md").read_text(encoding="utf-8")
    shipped = {p for p in _tracked() if p.startswith(SCREENSHOTS) and (REPO / p).is_file()}
    assert examined(len(ABSOLUTE_IMAGE.findall(description)), "images in PYPI_DESCRIPTION.md") == 3
    assert image_problems(description, shipped) == []


def test_no_copy_of_the_placeholder_is_left_in_the_tree(examined):
    files = {p: (REPO / p).read_bytes() for p in _tracked() if (REPO / p).is_file()}
    examined(len(files), "tracked files searched for the placeholder")
    assert placeholder_left(files) == []


def test_a_missing_screenshot_and_a_left_over_placeholder_are_caught():
    shipped = {"docs/screenshots/a.png"}
    good = f"![a]({image_base()}docs/screenshots/a.png)\n"
    assert image_problems(good, shipped) == []
    assert image_problems(good.replace("a.png", "gone.png"), shipped)                # a missing screenshot
    assert image_problems(good.replace(PUBLIC_REPOSITORY, PLACEHOLDER), shipped)     # the placeholder left in
    assert image_problems(good.replace(f"v{_version()}", "v9.9.9"), shipped)         # another release's tag
    assert image_problems(good.replace("docs/screenshots/", "docs/"), {"docs/a.png"})  # not a screenshot
    assert image_problems("no image\n", shipped)
    assert placeholder_left({"a": b"ok", "b": b"x " + PLACEHOLDER.encode()}) == ["b"]


def test_each_readme_image_is_a_tracked_file():
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    tracked = set(subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                                 check=True).stdout.split("\0"))
    images = [m.group(3) for m in RELATIVE.finditer(readme) if m.group(1)]
    assert images and [i for i in images if i not in tracked] == []


def test_a_built_sdist_s_description_has_no_relative_image_or_link(tmp_path):
    """Built from a copy of the tracked files, as a release is, so the build writes nothing here."""
    tracked = subprocess.run(["git", "ls-files", "-z"], cwd=REPO, capture_output=True, text=True,
                             check=True).stdout.split("\0")
    tree = tmp_path / "tree"
    for rel in filter(None, tracked):
        if (REPO / rel).is_file():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes((REPO / rel).read_bytes())
    dist = tmp_path / "dist"
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    subprocess.run([sys.executable, "-c", "import sys; from setuptools import build_meta as b; "
                    "print(b.build_sdist(sys.argv[1]))", str(dist)], cwd=tree, check=True,
                   capture_output=True, env=clean)
    (sdist,) = dist.glob("onetrace_console-*.tar.gz")
    with tarfile.open(sdist) as t:
        (info,) = [m for m in t.getmembers() if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")]
        metadata = email.message_from_bytes(t.extractfile(info).read())
    body = metadata.get_payload()
    assert metadata["Description-Content-Type"] == "text/markdown"
    #: The README's first image, its alt text as the README gives it, made absolute.
    alt = re.search(r"!\[([^\]]*)\]\(docs/screenshots/overview\.png\)",
                    (REPO / "README.md").read_text(encoding="utf-8")).group(1)
    assert f"![{alt}](https://raw.githubusercontent.com/" in body
    assert RELATIVE.findall(body) == []
    assert PLACEHOLDER not in body
    shipped = {p for p in _tracked() if p.startswith(SCREENSHOTS)}
    assert image_problems(body, shipped) == []
