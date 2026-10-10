"""The operator README names every folder the console keeps data in.

"Where the data lives" listed only `/data/store/` and `/data/pages/`. It now gives the full layout,
what isn't stored, how to back up, restore and reset, and the exact `sha256sum` command a delivery's
`SHA256SUMS` is made with. The checks here:

- **From the code:** every folder name the source joins under the store root, or under the store
  itself, is named in the README's storage section.
- **From a running console:** every folder a real console creates after an upload and a compare is
  named there too. Key- and digest-named folders are cut at the name: `pages/runs/<key>/` counts as
  `pages/runs/`.
- **What isn't stored, and the backup, restore and reset steps,** are stated.
- **The delivery command** is taken from the README and run, with a `bash` that passed a control
  (never PATH's: on Windows that is the WSL launcher), on a committed run folder; the delivery it
  makes is stored. A `./`-prefixed path stays refused, and the README says so.

Its limit: a folder made under a name built at run time from data the code doesn't hold as a
string -- none exists today -- is seen only by the running-console check, and only if those runs
reach it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import make_tar
from tests.test_diff_sdk_text_layer import _forged_pair, _tar
from tests.test_serve import _post

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "onetrace_console"
README = REPO / "OPERATOR_README.md"
RUN = REPO / "tests" / "fixtures" / "r11" / "two-minimal-nodes"


def _section() -> str:
    """The README's storage section, from its heading to the next top-level heading."""
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    start = text.index("## Where the data lives")
    end = text.find("\n## ", start + 5)
    return text[start:end if end != -1 else len(text)]


def _named(folder: str) -> bool:
    return f"`{folder}/" in _section() or f" {folder}/" in _section()


#: How the source names a folder under the store root (`serve.py`) or under the store (`store.py`).
_UNDER_ROOT = re.compile(r'store_root\s*/\s*(?:"([a-z_]+)"|([A-Z_]+_DIRNAME))')
_UNDER_STORE = re.compile(r'self\.root\s*/\s*"([a-z_]+)"')


def _folders_in_source() -> set[str]:
    serve = (SRC / "serve.py").read_text(encoding="utf-8")
    constants = dict(re.findall(r'^([A-Z_]+_DIRNAME)\s*=\s*"([a-z_]+)"', serve, re.M))
    found = set()
    for literal, constant in _UNDER_ROOT.findall(serve):
        found.add(literal or constants[constant])
    found |= {f"store/{name}" for name in _UNDER_STORE.findall(
        (SRC / "store.py").read_text(encoding="utf-8"))}
    return found


def test_every_folder_the_source_creates_is_named_in_the_readme(examined):
    folders = _folders_in_source()
    examined(len(folders), "folders the source creates")
    assert {"store", "pages", "access_log", "accounts", "tokens", "store/objects", "store/runs",
            "store/comparisons", "store/decision_exports"} <= folders, folders
    missing = sorted(f for f in folders if not _named(f))
    assert not missing, f"the README's storage section does not name: {missing}"


_KEYLIKE = re.compile(r"^[0-9a-f]{2}$|^[0-9a-f]{64}(\.[a-z]+)?$")


def test_every_folder_a_running_console_creates_is_named_in_the_readme(server, files, tmp_path,
                                                                        examined):
    base, root = server
    assert _post(base, "/v1/runs", make_tar(files))[0] == 200
    (tmp_path / "pair").mkdir()
    a, b = _forged_pair(tmp_path / "pair")
    keys = [json.loads(_post(base, "/v1/runs", _tar(d))[1])["run_key"] for d in (a, b)]
    assert _post(base, f"/compare?a={keys[0]}&b={keys[1]}")[0] == 200
    seen = set()
    for d in root.rglob("*"):
        if not d.is_dir():
            continue
        parts = []
        for part in d.relative_to(root).parts:
            if _KEYLIKE.match(part):
                break
            parts.append(part)
        if parts:
            seen.add("/".join(parts))
    examined(len(seen), "folders a running console created")
    assert {"store", "store/objects", "store/runs", "pages", "pages/runs", "access_log"} <= seen, seen
    missing = sorted(f for f in seen if not _named(f))
    assert not missing, f"the running console made folders the README doesn't name: {missing}"


def test_what_is_not_stored_and_how_to_back_up_restore_and_reset_are_stated(examined):
    section = " ".join(_section().split())
    examined(1, "storage section read")
    for needed in ("Sign-in sessions are held in memory", "onetrace-staging-", "onetrace-compare-",
                   "### Backing up", "### Restoring", "### Resetting to empty"):
        assert needed in section, f"the storage section does not state {needed!r}"


def _delivery_command() -> str:
    text = README.read_text(encoding="utf-8").replace("\r\n", "\n")
    block = re.search(r"### Making a delivery\n.*?```bash\n(.*?)```", text, re.S)
    assert block, "the README gives no ```bash block under '### Making a delivery'"
    return block.group(1)


def _bash_candidates() -> list[list[str]]:
    """Where a bash that can run the README's command is looked for. **`shutil.which("bash")` is
    deliberately absent:** on Windows, `bash` on PATH is the WSL launcher, which starts, then
    cannot open a Windows path (canary's F17; the Windows run of 1727d05 hit it here). So Git
    Bash is named by its path -- the default install, then beside the `git` on PATH -- and POSIX
    hosts use /bin/bash."""
    if os.name != "nt":
        return [[p] for p in ("/bin/bash", "/usr/bin/bash")]
    found = [r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe"]
    git = shutil.which("git")
    if git:
        root = Path(git).resolve().parent.parent      # <Git>\cmd\git.exe or <Git>\bin\git.exe
        found += [str(root / "bin" / "bash.exe"), str(root / "usr" / "bin" / "bash.exe")]
    return [[p] for p in dict.fromkeys(found)]


def _bash_that_runs_the_readme(probe: Path, candidates: list[list[str]]):
    """The first candidate that passes the control, and a line per candidate tried.

    **The control is the real property, not "a shell exists":** run a script, by its own path
    (as the test does), from a folder holding one known file, with GNU `find -printf` (as the
    README does), and require that file's name back. WSL's launcher answers and exits 0, then
    runs nothing -- so answering is not enough."""
    probe.mkdir(parents=True, exist_ok=True)
    (probe / "known-file").write_bytes(b"x")
    control = probe.parent / f"{probe.name}-control.sh"
    control.write_text("find . -type f -printf '%P\\n'\n", encoding="utf-8", newline="\n")
    tried = []
    for cand in candidates:
        try:
            r = subprocess.run([*cand, str(control)], cwd=probe, capture_output=True, text=True,
                               timeout=60)
            said = f"exit {r.returncode}, printed {r.stdout.strip()!r}"
            if r.returncode == 0 and r.stdout.strip() == "known-file":
                tried.append(f"{' '.join(cand)}: {said} -- used")
                return cand, tried
        except (OSError, subprocess.TimeoutExpired) as e:
            said = f"{type(e).__name__}: {e}"
        tried.append(f"{' '.join(cand)}: {said} -- not used")
    return None, tried


def _require_bash(probe: Path, candidates: list[list[str]] | None = None) -> list[str]:
    """A bash that passed the control, or a FAILURE naming every candidate -- never a skip: a
    skipped check of the README's command is one whose examined population is zero."""
    chosen, tried = _bash_that_runs_the_readme(probe, _bash_candidates() if candidates is None
                                               else candidates)
    if chosen is None:
        pytest.fail("no bash that can run the README's command was found; tried:\n"
                    + "\n".join(tried))
    return chosen


def test_the_readme_s_delivery_command_makes_a_delivery_the_console_stores(tmp_path, store,
                                                                         examined):
    from onetrace_console.ingest import accept
    bash = _require_bash(tmp_path / "bash-probe")
    folder = tmp_path / "run_folder"
    shutil.copytree(RUN, folder)
    script = tmp_path / "make_delivery.sh"
    script.write_text(_delivery_command(), encoding="utf-8", newline="\n")
    proc = subprocess.run([*bash, str(script)], cwd=folder, capture_output=True, text=True,
                          timeout=120)
    examined(1, "README command run")
    assert proc.returncode == 0, proc.stderr
    tar = tmp_path / "run.tar"
    assert tar.is_file(), "the command did not write ../run.tar"
    sums = (folder / "SHA256SUMS").read_text(encoding="utf-8")
    assert "./" not in sums, "the command writes ./ paths, which the console refuses"
    result = accept(tar.read_bytes(), store)
    assert result.__class__.__name__ == "Accepted", getattr(result, "rows", result)


def test_the_readme_says_dot_slash_paths_are_refused(examined):
    text = " ".join(README.read_text(encoding="utf-8").split())
    examined(1, "README read")
    assert "`./`" in text and "refused" in text[text.index("### Making a delivery"):][:2500]


# ---------------------------------------------------------------------------------------------
# Which bash runs the README's command. On Windows, `bash` on PATH is the WSL launcher (canary's
# F17): it answers, then cannot open a Windows path. So the bash is chosen from explicit
# candidates and qualified by a control that runs a script the way the real test does.

def _fake_bash(tmp_path, name: str, body: str) -> list[str]:
    """A stand-in bash, as a Python script, so these tests run on every host."""
    fake = tmp_path / f"{name}.py"
    fake.write_text(body, encoding="utf-8")
    return [sys.executable, str(fake)]


#: Answers like a bash that works: lists the files under its working folder, as the control asks.
_WORKS = "import os\nfor r, _, fs in os.walk('.'):\n    [print(os.path.relpath(os.path.join(r, f), '.').replace(os.sep, '/')) for f in fs]\n"
#: Answers like WSL's launcher here: starts, exits 0, and runs nothing.
_WSL_LIKE = "import sys\nsys.exit(0)\n"


def test_a_bash_that_starts_but_cannot_run_the_script_is_not_used(tmp_path):
    wsl_like, works = _fake_bash(tmp_path, "wsl_like", _WSL_LIKE), _fake_bash(tmp_path, "works", _WORKS)
    chosen, tried = _bash_that_runs_the_readme(tmp_path / "probe", [wsl_like, works])
    assert chosen == works, tried
    assert "not used" in tried[0] and "used" in tried[1], tried


def test_no_bash_that_can_run_the_script_is_a_failure_naming_what_was_tried(tmp_path):
    wsl_like = _fake_bash(tmp_path, "wsl_like", _WSL_LIKE)
    missing = [str(tmp_path / "no-such-bash")]
    try:
        _require_bash(tmp_path / "probe", [wsl_like, missing])
        outcome = "returned"
    except pytest.skip.Exception as e:   # a skip would hide that the README's command never ran
        outcome = f"skipped: {e}"
    except pytest.fail.Exception as e:
        outcome = f"failed: {e}"
    assert outcome.startswith("failed: "), outcome
    assert "wsl_like.py" in outcome and "no-such-bash" in outcome, outcome


def test_the_bash_on_path_is_never_consulted(tmp_path, monkeypatch):
    real_which = shutil.which

    def which(name, *a, **kw):
        assert name != "bash", "shutil.which('bash') was consulted"
        return real_which(name, *a, **kw)
    monkeypatch.setattr(shutil, "which", which)
    candidates = _bash_candidates()
    assert candidates and all(c and c[0] != "bash" for c in candidates), candidates


def test_the_delivery_test_takes_its_bash_from_the_control():
    """On Linux PATH's bash works, so a revert to `shutil.which("bash")` in the delivery test
    would pass here and fail only on Windows. This catches it on every host."""
    source = Path(__file__).read_text(encoding="utf-8")
    body = source.split("def test_the_readme_s_delivery_command_makes_a_delivery_the_console_stores(",
                        1)[1].split("\ndef ", 1)[0]
    assert "_require_bash(" in body and 'which("bash")' not in body
