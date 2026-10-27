""""Repeat the check" names each evidence file by its name alone.

The stored report keeps the verifier's command as it ran, with the trust file's path on this
console's machine. A page shows that file -- and a time-stamp authority's certificate and roots --
by name, as the receipt page's command does: the path says nothing a reader can use, and shows how
the console's machine is laid out. The record itself is unchanged.
"""
from __future__ import annotations

import re
from html import unescape

import pytest

from tests.test_runs_list import demo  # noqa: F401


@pytest.mark.parametrize("given, shown", [
    (("onetrace-verify", "--trust", "/srv/onetrace-demo/trust.json", "MANIFEST.json"),
     ("onetrace-verify", "--trust", "trust.json", "MANIFEST.json")),
    (("onetrace-verify", "--json", "--trust", "C:\\onetrace\\keys\\trust.json", "--tsa-cert", "tsa/cert.pem",
      "--tsa-root", "/etc/tsa/root-a.pem", "--tsa-root", "root-b.pem", "MANIFEST.json"),
     ("onetrace-verify", "--json", "--trust", "trust.json", "--tsa-cert", "cert.pem",
      "--tsa-root", "root-a.pem", "--tsa-root", "root-b.pem", "MANIFEST.json")),
    (("onetrace-verify", "MANIFEST.json"), ("onetrace-verify", "MANIFEST.json")),
], ids=["posix", "windows-and-relative", "none"])
def test_each_evidence_file_is_shown_by_its_name(given, shown, examined):
    from onetrace_console.pages import shown_command
    examined(1, "command")
    assert shown_command(given) == shown


def test_no_page_of_the_demo_names_where_it_was_built(demo, examined):
    """The demo's checks ran with its trust file copied beside the run and named relative to it;
    its pages show the name."""
    from onetrace_console.pages import _envelope
    store, pages = demo
    folder = str(pages.parent.parent)
    runs = store.runs()
    for run in runs:
        command = _envelope(run, store, required=False)["command"]
        assert command[command.index("--trust") + 1] == "../evidence/trust.json", \
            "the stored report keeps the command as it ran"
    shown = 0
    for page in sorted(pages.rglob("*.html")):
        html = page.read_text(encoding="utf-8")
        assert folder not in unescape(html), page.relative_to(pages)
        for said in re.findall(r"<summary>Repeat the check</summary>.*?<code[^>]*>(.*?)</code>", html, re.S):
            assert "--trust trust.json" in unescape(said), (page.relative_to(pages), said)
            shown += 1
    examined(shown, "Repeat the check commands")
    assert shown >= len(runs)
