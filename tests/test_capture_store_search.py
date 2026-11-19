"""The capture store's app tells search engines what the demo's does: its Overview is indexable, with its canonical
address from its own setting, and every other page carries `noindex`.

The capture store is built as its image builds it (`demo --public --build --captures`, here `build_public` with its
builder) and served as a public console with `ONETRACE_CONSOLE_PUBLIC_URL` set to its own address, as the deploy guide
says for both apps.
"""

from __future__ import annotations

import re

import pytest

from tests.test_capture_store import built  # noqa: F401 - the fixture, requested by name
from tests.test_folder_load import _Console
from tests.test_public_mode import _config
from tests.test_search_engines import CANONICAL, NOINDEX, _get

OWN = "https://captures.example.org"


@pytest.fixture(scope="module")
def served_captures(built, tmp_path_factory):  # noqa: F811
    tmp = tmp_path_factory.mktemp("captures-served")
    config = _config(tmp, built["folder"])
    port = __import__("json").loads(config.read_text(encoding="utf-8"))["port"]
    c = _Console(tmp, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config), "ONETRACE_CONSOLE_PUBLIC_URL": OWN})
    try:
        c.until("onetrace-console serving on")
        yield f"http://127.0.0.1:{port}", built
    finally:
        c.proc.terminate()
        c.proc.wait(timeout=30)


def test_the_capture_store_s_overview_is_indexable_with_its_own_canonical(served_captures, examined):
    base, _built = served_captures
    examined(2, "addresses of the Overview")
    for path in ("/", "/home.html"):
        status, _kind, page = _get(base, path)
        assert status == 200 and CANONICAL.search(page).group(1) == OWN + "/", path
    _status, _kind, overview = _get(base, "/")
    assert NOINDEX not in overview


def test_every_other_capture_store_page_carries_noindex(served_captures, examined):
    base, built = served_captures
    others = [rel for rel in built["pages"] if rel != "home.html"]
    examined(len(others), "pages")
    for rel in others:
        status, kind, page = _get(base, "/" + rel)
        assert status == 200 and kind.startswith("text/html") and page.count(NOINDEX) == 1, rel
        assert not re.search(r'rel="canonical"', page), rel
