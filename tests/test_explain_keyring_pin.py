"""The pin (console 0.7.0): the console depends on neither onetrace-explain nor keyring, and its docs and
install line name `onetrace-explain[keyring]>=0.3` beside the console: the README's install sentence, and
the Set up Explain page's step 3."""
from __future__ import annotations

import re
from html import unescape
from pathlib import Path

import pytest

from tests.keychain import planted_key_searched  # noqa: F401
from tests.test_explain_panel import pair  # noqa: F401
from tests.test_explain_setup import _get, _main, local  # noqa: F401

#: Every file each test here writes is searched for the planted key afterwards (tests/keychain.py).
pytestmark = pytest.mark.usefixtures("planted_key_searched")

REPO = Path(__file__).resolve().parent.parent
LINE = 'pip install "onetrace-explain[keyring]>=0.3"'
NAMES = re.compile(r"onetrace[-_.]explain|\bkeyring\b", re.I)


def test_the_console_depends_on_neither(examined):
    files = {n: (REPO / n).read_text(encoding="utf-8")
             for n in ("pyproject.toml", "requirements.lock", "src/onetrace_console/requirements.lock")}
    examined(len(files), "dependency files")
    assert [n for n, t in files.items() if NAMES.search(t)] == []


@pytest.mark.parametrize("name", ["README.md", "PYPI_DESCRIPTION.md"])
def test_each_readme_gives_the_line_beside_the_console(name, examined):
    text = (REPO / name).read_text(encoding="utf-8")
    examined(1, name)
    install = text.split("## Upgrading", 1)[0]
    assert install.index("pip install onetrace-console") < install.index(f"`{LINE}`"), install[:1500]


def test_the_setup_page_s_step_3_gives_the_line(local, examined):
    base, _, _, _, _ = local
    _, page = _get(f"{base}/explain/setup")
    step = re.search(r'<section class="step" id="step-3".*?</section>', _main(page), re.S).group(0)
    blocks = [unescape(b) for b in re.findall(r"<pre><code>(.*?)</code></pre>", step, re.S)]
    examined(len(blocks), "install lines")
    assert blocks == [LINE]
