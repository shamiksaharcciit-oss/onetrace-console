"""A run compared with itself.

    A run compared with itself (`a=K&b=K`): answer "the same run" plainly, never 500.

Nothing is compared and nothing is stored: there is no second run to find a difference in, and
a stored comparison of a run with itself would be a row in every "compared" count that
compared nothing.
"""
from __future__ import annotations

import json

from tests.conftest import make_tar


def test_a_run_compared_with_itself_is_the_same_run(server, files):
    from onetrace_console.serve import SAME_RUN
    from onetrace_console.store import Store
    from tests.test_serve import _post

    base, store_root = server
    status, body = _post(base, "/v1/runs", make_tar(files))
    assert status == 200, body
    key = json.loads(body)["run_key"]
    status, body = _post(base, f"/compare?a={key}&b={key}")
    assert status == 200, body[:300]
    assert json.loads(body) == {"same_run": True, "run_key": key, "answer": SAME_RUN}
    assert SAME_RUN.startswith("the same run")
    assert not list(Store(store_root / "store").comparisons()), "nothing was stored"
    assert not list((store_root / "pages").glob("diff/*.html")), "no Diff page was drawn"
