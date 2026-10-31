"""The operator README says in words what the container image leaves out, and the image's files bear it out.

"Nothing leaves the container" says the image includes neither onetrace-explain nor the `[neighbours]`
extra. That holds while each Dockerfile installs `requirements.lock` alone, through
`tools/install_pinned.py`, and the lock pins neither. Each rule has its own sabotage below.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
DOCKERFILES = ["Dockerfile", "deploy/fly/Dockerfile"]
CLAUSE = ("The image includes neither onetrace-explain nor the `[neighbours]` extra: both Dockerfiles install "
          "`requirements.lock` alone, which pins neither.")
#: The distributions the clause says the image leaves out: the command, and the extra's three.
LEFT_OUT = ("onetrace-explain", "onetrace_explain", "onnxruntime", "tokenizers", "numpy")


def clause_problems(readme: str, dockerfiles: dict[str, str], lock: str) -> list[str]:
    out = []
    section = readme.replace("\r\n", "\n").split("\n## Nothing leaves the container\n", 1)
    if len(section) != 2 or CLAUSE not in " ".join(section[1].split("\n## ", 1)[0].split()):
        out.append("OPERATOR_README.md: \"Nothing leaves the container\" does not hold the clause")
    for name, text in dockerfiles.items():
        installs = [l.strip() for l in text.splitlines() if re.match(r"\s*RUN\b.*\b(pip|install_pinned)\b", l)]
        if installs != ["RUN python tools/install_pinned.py"]:
            out.append(f"{name} installs {installs}, not requirements.lock alone")
    out += [f"requirements.lock pins {d}" for d in LEFT_OUT if re.search(rf"^{re.escape(d)}\s*==", lock, re.M | re.I)]
    return out


def _read() -> tuple[str, dict[str, str], str]:
    return ((REPO / "OPERATOR_README.md").read_text(encoding="utf-8"),
            {n: (REPO / n).read_text(encoding="utf-8") for n in DOCKERFILES},
            (REPO / "requirements.lock").read_text(encoding="utf-8"))


def test_the_operator_readme_says_what_the_image_leaves_out_and_the_image_bears_it_out(examined):
    readme, dockerfiles, lock = _read()
    examined(1 + len(dockerfiles) + 1, "files: the operator README, the Dockerfiles and the lock")
    assert clause_problems(readme, dockerfiles, lock) == []


@pytest.mark.parametrize("planted", ["readme", "dockerfile", "lock"])
def test_sabotage_each_rule_is_caught(planted, examined):
    readme, dockerfiles, lock = _read()
    if planted == "readme":
        readme = readme.replace("The image includes neither onetrace-explain", "The image can include onetrace-explain")
    elif planted == "dockerfile":
        dockerfiles["Dockerfile"] = dockerfiles["Dockerfile"].replace(
            "RUN python tools/install_pinned.py", "RUN python tools/install_pinned.py\nRUN pip install onetrace-explain")
    else:
        lock += "\nonetrace-explain==0.1.0 \\\n    --hash=sha256:" + "0" * 64 + "\n"
    examined(1, f"planted {planted}")
    assert clause_problems(readme, dockerfiles, lock) != []
