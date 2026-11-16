"""`deploy/fly/captures/`: the capture store's own Fly app, from the demo's image (round fb, part 4).

1. `captures/fly.toml` is the demo's service (its port, HTTPS, `/health`, idle machines stopped) and builds the demo's
   own Dockerfile with `ONETRACE_DEMO_STORE = "captures"`; like every file in `deploy/fly/`, it names no app, region,
   organisation or domain (`test_deploy_fly.scan`).
2. The Dockerfile builds the capture store where that argument says so (`demo --public --build ... --captures`), and the
   demo otherwise, as before; any other value fails the build.
3. The image's command, run here as the image runs it: the capture store built into the folder `public.json` names,
   then `onetrace-console serve` on it, its build record checked at start; `/health` answers, and a comparison
   shows the token-level section.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEPLOY = REPO / "deploy" / "fly"
CAPTURES = DEPLOY / "captures"


def test_the_captures_app_is_the_demo_s_service_building_the_capture_store(examined):
    demo = tomllib.loads((DEPLOY / "fly.toml").read_text(encoding="utf-8"))
    captures = tomllib.loads((CAPTURES / "fly.toml").read_text(encoding="utf-8"))
    examined(2, "fly.toml files")
    assert captures["http_service"] == demo["http_service"]
    assert captures["build"] == {"args": {"ONETRACE_DEMO_STORE": "captures"}}
    assert (
        captures["http_service"]["auto_stop_machines"] == "stop"
        and captures["http_service"]["min_machines_running"] == 0
    )


def test_the_dockerfile_builds_the_store_its_argument_names(examined):
    text = (DEPLOY / "Dockerfile").read_text(encoding="utf-8")
    examined(1, "Dockerfile")
    assert "\nARG ONETRACE_DEMO_STORE=demo\n" in text
    assert 'if [ "$ONETRACE_DEMO_STORE" = captures ]; then' in text
    assert "python -m onetrace_console demo --public --build /srv/onetrace-demo --captures;" in text
    assert 'elif [ "$ONETRACE_DEMO_STORE" != demo ]; then' in text
    #: The demo's two builds stay as they were.
    assert "--runs-from /app/deploy/fly/kept --explanations /app/deploy/fly/kept" in text
    assert text.index("ARG ONETRACE_DEMO_STORE") < text.index('"$ONETRACE_DEMO_STORE" = captures')


def _port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_the_image_s_command_with_captures_builds_and_starts(tmp_path, examined):
    from tests.http_limits import limit
    from tests.test_checks import _require_installed

    _require_installed()
    env = {
        **{k: v for k, v in os.environ.items() if k != "ONETRACE_CONSOLE_CONFIG"},
        "PYTHONPATH": str(REPO / "src"),
        "TMPDIR": str(tmp_path),
    }
    built = tmp_path / "srv" / "onetrace-demo"
    got = subprocess.run(
        [sys.executable, "-B", "-m", "onetrace_console", "demo", "--public", "--build", str(built), "--captures"],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
        timeout=1800,
    )
    assert got.returncode == 0, got.stderr[-2000:]
    #: public.json as the image has it, its paths and port moved here.
    config = json.loads((DEPLOY / "public.json").read_text(encoding="utf-8"))
    port = _port()
    config.update(
        host="127.0.0.1",
        port=port,
        store_root=str(built / "store"),
        trust_file=str(built / "trust.json"),
        compare_cache=str(tmp_path / "compared"),
    )
    (tmp_path / "compared").mkdir()
    (tmp_path / "public.json").write_text(json.dumps(config), encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-B", "-m", "onetrace_console", "serve"],
        env={**env, "ONETRACE_CONSOLE_CONFIG": str(tmp_path / "public.json")},
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + limit(120)
        while True:
            try:
                health = urllib.request.urlopen(base + "/health", timeout=limit(10)).read()
                break
            except OSError:
                assert proc.poll() is None, proc.stdout.read().decode()[-2000:]
                assert time.monotonic() < deadline, "the console did not answer /health"
                time.sleep(0.2)
        comparisons = urllib.request.urlopen(base + "/comparisons.html", timeout=limit(30)).read().decode()
        diffs = sorted(set(re.findall(r'href="/?(diff/[0-9a-f]{64}\.html)"', comparisons)))
        pages = [urllib.request.urlopen(f"{base}/{d}", timeout=limit(30)).read().decode() for d in diffs]
    finally:
        proc.terminate()
        proc.wait(timeout=60)
    examined(len(diffs), "the capture store's comparisons, served")
    assert health.strip() == b"ok"
    assert len(diffs) == 2 and all('data-section="token-levels"' in p for p in pages)


def test_the_readme_says_how_the_capture_store_s_app_is_deployed_and_in_which_order(examined):
    readme = (DEPLOY / "README.md").read_text(encoding="utf-8")
    section = readme[readme.index("## The capture store's app") :]
    examined(1, "the README's section")
    captures_deploy = (
        "fly deploy --config deploy/fly/captures/fly.toml --dockerfile deploy/fly/Dockerfile -a <captures-app-name> "
        "--env ONETRACE_CONSOLE_DEMO_URL=https://<the demo's address>"
    )
    demo_deploy = (
        "fly deploy --config deploy/fly/fly.toml --dockerfile deploy/fly/Dockerfile -a <app-name> "
        "--env ONETRACE_CONSOLE_CAPTURES_URL=https://<the capture store's address>"
    )
    assert captures_deploy in section and demo_deploy in section
    #: The capture store's app first, so the demo's line answers once it is drawn.
    assert section.index(captures_deploy) < section.index(demo_deploy)
    assert "postdeploy_080_captures.ps1 -Base" in section and "postdeploy_080.ps1 -Base" in section
    assert "its name and its domain are yours" in section.lower()
