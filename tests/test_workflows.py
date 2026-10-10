"""The Actions workflows, and the hosted demo's base image, read as GitHub and Docker will read them.

1. Every workflow under `.github/workflows/` uses the `runner` context only where GitHub makes it
   available -- a step's `with`, `env` or `if` -- and never puts an expression inside a `run:`
   script. A workflow that broke the first rule was rejected whole by GitHub, before any job ran
   ("Unrecognized named-value: 'runner'", a job-level `env`); the second keeps a value from being
   pasted into a shell script as code.
2. `deploy/fly/Dockerfile` names its base image by digest, so a rebuild cannot take another image
   under the same tag.

The workflows are read by their indentation, enough for the shapes they use; there is no YAML
library in the suite's pins. Each rule has its own sabotage below.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"
DOCKERFILE = REPO / "deploy" / "fly" / "Dockerfile"

_KEY = re.compile(r'^([A-Za-z0-9_.-]+|"[^"]*"|\'[^\']*\'):(?:\s+(.*))?$')
_EXPRESSION = re.compile(r"\$\{\{(.*?)\}\}")
#: The step keys where GitHub makes the runner context available.
RUNNER_ALLOWED = {"with", "env", "if"}


def lines_with_expressions(text: str) -> list[tuple[int, list[str], str]]:
    """Each line holding `${{`: its number, the keys it sits under (a block scalar's lines under
    the key that opened it), and the line."""
    found: list[tuple[int, list[str], str]] = []
    stack: list[tuple[int, str]] = []
    block: tuple[int, list[str]] | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        indent = len(raw) - len(raw.lstrip(" "))
        if block is not None:
            if not raw.strip() or indent > block[0]:
                if "${{" in raw:
                    found.append((number, block[1], raw))
                continue
            block = None
        body = raw.strip()
        if not body or body.startswith("#"):
            continue
        while body.startswith("- "):
            body = body[2:].lstrip()
            indent = len(raw) - len(body)
        key = _KEY.match(body)
        if key is None:
            path = [k for _, k in stack]
        else:
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, key.group(1).strip("\"'")))
            path = [k for _, k in stack]
            if (key.group(2) or "").strip() in ("|", "|-", "|+", ">", ">-", ">+"):
                block = (indent, path)
                continue
        if "${{" in raw:
            found.append((number, path, raw))
    return found


def problems(text: str) -> list[str]:
    """Where a workflow's expressions break either rule, as `line N: what`."""
    out = []
    for number, path, raw in lines_with_expressions(text):
        step_key = path[path.index("steps") + 1] if "steps" in path[:-1] else None
        if step_key == "run":
            out.append(f"line {number}: an expression inside a run: script")
            continue
        for expression in _EXPRESSION.findall(raw):
            if re.search(r"\brunner\.", expression) and step_key not in RUNNER_ALLOWED:
                out.append(f"line {number}: the runner context under {'.'.join(path)}, where "
                           f"GitHub does not make it available")
    return out


def _workflows() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


def test_every_workflow_uses_the_runner_context_only_where_it_exists(examined):
    files = _workflows()
    examined(len(files), "workflow files")
    assert len(files) >= 1, files   # the public tree has one workflow; this repository has more
    found = {f.name: problems(f.read_text(encoding="utf-8")) for f in files}
    assert found == {f.name: [] for f in files}, found


def test_every_workflow_expression_is_read(examined):
    """The reader is not blind: every `${{` in each file is one of the lines it returns."""
    total = 0
    for f in _workflows():
        text = f.read_text(encoding="utf-8")
        lines = {n for n, _, _ in lines_with_expressions(text)}
        want = {n for n, line in enumerate(text.splitlines(), 1) if "${{" in line}
        assert lines == want, (f.name, sorted(want - lines))
        total += len(want)
    examined(total, "expressions read")
    assert total > 0


_JOB = """\
name: planted
on: push
jobs:
  planted:
    runs-on: ubuntu-24.04
{job_env}    steps:
      - name: one
        run: |
          echo start
{run_line}      - name: keep
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          path: ${{{{ runner.temp }}}}/out
        if: ${{{{ always() && runner.os == 'Linux' }}}}
"""


def test_the_planted_forms_are_caught_and_the_allowed_ones_are_not(examined):
    """The sabotage: a job-level env reading the runner context (the form GitHub rejected), and an
    expression inside a run script, are each named; the step's `with` and `if` are not."""
    clean = _JOB.format(job_env="", run_line="")
    job_env = _JOB.format(job_env="    env:\n      OUT: ${{ runner.temp }}/out\n", run_line="")
    in_run = _JOB.format(job_env="", run_line="          echo ${{ github.sha }}\n")
    in_one_line_run = clean.replace("        run: |\n          echo start\n",
                                    "        run: echo ${{ github.ref }}\n")
    examined(4, "planted workflows")
    assert problems(clean) == []
    assert problems(job_env) == ["line 7: the runner context under jobs.planted.env.OUT, where "
                                 "GitHub does not make it available"], problems(job_env)
    assert problems(in_run) == ["line 10: an expression inside a run: script"], problems(in_run)
    assert problems(in_one_line_run) == ["line 8: an expression inside a run: script"], \
        problems(in_one_line_run)


# ------------------------------------------------------------------ the base image, by digest

_FROM = re.compile(r"^FROM\s+(\S+)", re.M)


def unpinned(dockerfile: str) -> list[str]:
    """Every FROM image not named by digest."""
    return [image for image in _FROM.findall(dockerfile)
            if not re.search(r"@sha256:[0-9a-f]{64}$", image)]


def test_the_demo_image_names_its_base_by_digest(examined):
    text = DOCKERFILE.read_text(encoding="utf-8")
    examined(len(_FROM.findall(text)), "FROM lines")
    assert _FROM.findall(text), "no FROM line"
    assert unpinned(text) == []


@pytest.mark.parametrize("image", ["python:3.12-slim", "python:latest", "python",
                                   "python:3.12-slim@sha256:f77ac9e4"])
def test_a_base_image_by_tag_alone_is_caught(image, examined):
    """The sabotage: the digest taken off, or cut short."""
    text = DOCKERFILE.read_text(encoding="utf-8")
    planted = _FROM.sub(f"FROM {image}", text, count=1)
    examined(1, "planted FROM")
    assert unpinned(planted) == [image]
