"""The container check's live-folder step, run here as the image runs it.

The image names its public demo's configuration in ONETRACE_CONSOLE_CONFIG for every process. The
step starts a local console on a watched folder inside that image; under that variable it read the
public configuration, refused to load a folder ("a public console loads nothing at start"), and
exited -- the container's main process -- so the step's script was killed with it: exit 137, an empty
watch.txt. The step now starts it without the image's configuration.

This test takes the step's own two commands out of .github/workflows/container-check.yml -- the
container's command and the script the step runs inside it -- and runs them here with the image's
configuration in ONETRACE_CONSOLE_CONFIG (its public.json, pointed at a demo built as the image
builds it), a folder of this test's own and a free port in place of /tmp/w and 8090. Not on Windows:
the container's command is a POSIX shell's.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_public_mode import _clean_env, built  # noqa: F401

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "container-check.yml"

pytestmark = pytest.mark.skipif(os.name == "nt", reason="the container's command is a POSIX shell's")


def _step() -> tuple[str, str]:
    """(the container's shell command, the script run in it), as the workflow writes them."""
    text = WORKFLOW.read_text(encoding="utf-8")
    step = text[text.index("- name: In the image, a watched folder's new run appears with no restart"):]
    command = re.search(r"--entrypoint sh \"\$IMAGE\" -c \\\n\s*'([^']*)'", step).group(1)
    script = re.search(r"<<'PYEOF'[^\n]*\n(.*?)\n\s*PYEOF\n", step, re.S).group(1)
    indent = re.match(r"\s*", script).group(0)
    script = "\n".join(line[len(indent):] if line.startswith(indent) else line for line in script.split("\n"))
    return command, script


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_the_watch_step_s_console_starts_in_the_image_s_environment_and_shows_the_late_run(
        built, tmp_path, examined):  # noqa: F811
    command, script = _step()
    folder, port = tmp_path / "w", str(_free_port())
    config = json.loads((REPO / "deploy" / "fly" / "public.json").read_text(encoding="utf-8"))
    config.update(store_root=str(built / "store"), trust_file=str(built / "trust.json"))
    image_config = tmp_path / "public.json"
    image_config.write_text(json.dumps(config), encoding="utf-8")
    here = lambda s: s.replace("/tmp/w", folder.as_posix()).replace("8090", port)  # noqa: E731
    env = {**_clean_env(), "ONETRACE_CONSOLE_CONFIG": str(image_config),
           "PYTHONPATH": str(REPO / "src"), "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}"}
    console = subprocess.Popen(["sh", "-c", here(command)], env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT)
    try:
        step = subprocess.run([sys.executable, "-u", "-"], input=here(script), text=True,
                              capture_output=True, env=env, timeout=240)
    finally:
        console.kill()
        said = console.communicate(timeout=30)[0].decode("utf-8", "replace")
    examined(1, "the watch step, run here")
    assert step.returncode == 0 and "RESULT: the run appeared on the Overview" in step.stdout, (
        step.stdout[-800:], step.stderr[-800:], said[-800:])
