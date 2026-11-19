"""The README's "Running the tests" holds the public workflow's steps, exactly.

The workflow (`.github/workflows/test.yml` in the public repository, `tools/public/test.yml` before
export) is how the suite is run; the README gives the same steps to run it by hand. This test reads
both and fails if they drift apart:

- the README's commands are the workflow's `run:` commands, in order, each word for word (a folded
  `>-` command joined by spaces, as GitHub joins it);
- the README exports the workflow's job `env:`, every name with its value, and nothing else but the
  variables GitHub provides that the commands use (`RUNNER_TEMP`);
- the README names the workflow's Python version.

The workflow is read by its indentation, enough for the shapes it uses; there is no YAML library in
the suite's pins. Each rule has its own sabotage below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
#: The workflow before export, then where the export puts it.
WORKFLOW_PLACES = (REPO / "tools" / "public" / "test.yml", REPO / ".github" / "workflows" / "test.yml")
README = REPO / "README.md"
HEADING = "### Running the tests"
#: A variable a command uses: $NAME or ${NAME}.
_VARIABLE = re.compile(r"\$\{?([A-Z_][A-Z0-9_]*)")


def workflow_path() -> Path:
    for path in WORKFLOW_PLACES:
        if path.is_file():
            return path
    raise AssertionError(f"no public workflow at {[str(p.relative_to(REPO)) for p in WORKFLOW_PLACES]}")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


#: The workflow's jobs, each with its README block: the suite, then the browser tests alone.
JOBS = ("test", "browser")


def _job(text: str, job: str) -> str:
    """The lines of one job of the workflow (`  <job>:` to the next job), or the whole text where it has no jobs."""
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln == f"  {job}:"), None)
    if start is None:
        return "" if any(ln.rstrip() == "jobs:" for ln in lines) else text
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].strip() and len(lines[i]) - len(lines[i].lstrip(" ")) == 2
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def read_workflow(text: str, job: str = "test") -> dict:
    """{"python": the setup step's python-version, "env": the job's env, "commands": each run command}, of one job."""
    lines = _job(text, job).splitlines()
    python, env, commands = None, {}, []
    i = 0
    while i < len(lines):
        raw = lines[i]
        indent = len(raw) - len(raw.lstrip(" "))
        body = raw.strip()
        if body == "env:" and indent == 4:
            i += 1
            while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > indent):
                if lines[i].strip():
                    name, _, value = lines[i].strip().partition(":")
                    env[name.strip()] = _unquote(value)
                i += 1
            continue
        m = re.match(r"python-version:\s*(.+)$", body)
        if m:
            python = _unquote(m.group(1))
        m = re.match(r"(?:- )?run:\s*(.*)$", body)
        if m:
            style = m.group(1).strip()
            if style in ("|", ">-", ">"):
                block = []
                i += 1
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip(" ")) > indent):
                    if lines[i].strip():
                        block.append(lines[i].strip())
                    i += 1
                commands += block if style == "|" else [" ".join(block)]
                continue
            if style:  # an empty `run:` opens a mapping (`defaults: run: shell:`), not a command
                commands.append(style)
        i += 1
    return {"python": python, "env": env, "commands": commands}


def read_section(text: str, nth: int = 0) -> dict:
    """{"text": the section, "env": its exports, "commands": the other lines of its `nth` bash block}."""
    start = text.find("\n" + HEADING + "\n")
    if start < 0:
        raise AssertionError(f"the README has no {HEADING!r}")
    rest = text[start + len(HEADING) + 2 :]
    end = re.search(r"^#{1,3} ", rest, re.M)
    section = rest[: end.start()] if end else rest
    blocks = re.findall(r"^```bash\n(.*?)^```", section, re.M | re.S)
    if len(blocks) <= nth:
        raise AssertionError(f"{HEADING!r} has no ```bash block number {nth + 1}")
    block = blocks[nth]
    env, commands = {}, []
    for line in block.splitlines():
        if not line.strip():
            continue
        if line.startswith("export "):
            for pair in re.findall(r'([A-Z_][A-Z0-9_]*)=("[^"]*"|\'[^\']*\'|\S+)', line[len("export ") :]):
                env[pair[0]] = _unquote(pair[1])
        else:
            commands.append(line.strip())
    return {"text": section, "env": env, "commands": commands}


def drift(workflow_text: str, readme_text: str) -> list[str]:
    """Each way the README's section and the workflow differ; empty where they match."""
    flow, readme = read_workflow(workflow_text), read_section(readme_text)
    found = []
    if not flow["commands"]:
        found.append("the workflow has no run command")
    if readme["commands"] != flow["commands"]:
        found.append(f"commands: the README {readme['commands']!r}, the workflow {flow['commands']!r}")
    for name, value in flow["env"].items():
        if readme["env"].get(name) != value:
            found.append(f"env {name}: the README {readme['env'].get(name)!r}, the workflow {value!r}")
    provided = {v for c in flow["commands"] for v in _VARIABLE.findall(c)} - set(flow["env"])
    for name in sorted(set(readme["env"]) - set(flow["env"])):
        if name not in provided:
            found.append(f"env {name}: the README sets it; the workflow neither sets nor uses it")
    for name in sorted(provided - set(readme["env"])):
        found.append(f"env {name}: a command uses it and the README does not set it")
    if not flow["python"] or flow["python"] not in readme["text"]:
        found.append(f"Python: the workflow's {flow['python']!r} is not named in the section")
    #: The browser job: its own commands (those the suite's job does not run), in order, are the README's second block;
    #: its env and Python are the suite's.
    browser = read_workflow(workflow_text, "browser")
    if browser["commands"]:
        own = [c for c in browser["commands"] if c not in flow["commands"]]
        second = read_section(readme_text, 1)
        if second["commands"] != own:
            found.append(f"browser job commands: the README {second['commands']!r}, the workflow {own!r}")
        if browser["env"] != flow["env"] or browser["python"] != flow["python"]:
            found.append("browser job: its env or Python is not the suite's")
    return found


def test_the_readme_s_test_steps_are_the_public_workflow_s(examined):
    flow = read_workflow(workflow_path().read_text(encoding="utf-8"))
    assert drift(workflow_path().read_text(encoding="utf-8"), README.read_text(encoding="utf-8")) == []
    examined(len(flow["commands"]) + len(flow["env"]), "workflow commands and env names compared with the README")


@pytest.mark.parametrize(
    "where, old, new, said",
    [
        ("workflow", "python tools/install_pinned.py", "python tools/install_pinned.py --all", "commands"),
        ("readme", "python tools/install_pinned.py\n", "", "commands"),
        (
            "readme",
            "python tools/fetch_wheel_cache.py --check\npython tools/fetch_wheel_cache.py\n",
            "python tools/fetch_wheel_cache.py\npython tools/fetch_wheel_cache.py --check\n",
            None,
        ),
        ("readme", "--check\npython tools/fetch_wheel_cache.py\n", "--check\n", "commands"),
        ("readme", " -rsxX", "", "commands"),
        ("workflow", 'PYTHONUTF8: "1"', 'PYTHONUTF8: "0"', "env PYTHONUTF8"),
        ("readme", " PYTHONDONTWRITEBYTECODE=1", "", "env PYTHONDONTWRITEBYTECODE"),
        ("readme", 'export RUNNER_TEMP="$(mktemp -d)"\n', "", "env RUNNER_TEMP"),
        ("readme", "export PYTHONPATH=src", "export PYTHONPATH=src HOME=/tmp", "env HOME"),
        ("workflow", '"3.12.10"', '"3.12.11"', "Python"),
        ("workflow", "python tools/browser_ran.py", "python tools/browser_ran.py --any", "browser job commands"),
        ("readme", "python -m playwright install --with-deps chromium\n", "", "browser job commands"),
    ],
)
def test_drift_either_way_is_caught(where, old, new, said):
    flow_text = workflow_path().read_text(encoding="utf-8")
    readme_text = README.read_text(encoding="utf-8")
    if where == "workflow":
        assert old in flow_text
        flow_text = flow_text.replace(old, new, 1)
    else:
        section = read_section(readme_text)["text"]
        if said is None:
            # the planted swap's own precondition: the README holds the order the workflow has
            old, new = new, old
        assert old in section, old
        readme_text = readme_text.replace(section, section.replace(old, new, 1), 1)
    found = drift(flow_text, readme_text)
    if said is None:
        assert any(f.startswith("commands") for f in found), found
    else:
        assert any(f.startswith(said) for f in found), found


def test_a_step_added_to_the_workflow_is_caught():
    flow_text = workflow_path().read_text(encoding="utf-8")
    #: At the end of the suite's job, before the browser job begins; and at the end of the browser job.
    step = "\n      - name: One more\n        run: python tools/one_more.py\n"
    added = flow_text.replace("\n  browser:\n", step + "\n  browser:\n", 1)
    assert added != flow_text
    found = drift(added, README.read_text(encoding="utf-8"))
    assert any(f.startswith("commands") for f in found), found
    found = drift(flow_text.rstrip("\n") + "\n" + step, README.read_text(encoding="utf-8"))
    assert any(f.startswith("browser job commands") for f in found), found


def test_a_readme_without_the_section_is_caught():
    with pytest.raises(AssertionError, match="no '### Running the tests'"):
        drift(workflow_path().read_text(encoding="utf-8"), "# onetrace-console\n\n## Install\n")
