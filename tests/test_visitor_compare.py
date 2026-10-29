"""Compare on the public demo (`visitor_compare`): the one thing a public console does on request.

1. Only two run ids of the build, of one pipeline, and nothing else: an unknown id, a path, two
   pipelines, the same run, a third field, a field twice, anything after `/compare`, and a body over
   the limit are each refused with the reason, and nothing is compared.
2. A pair the build compared is served as built and a pair compared before is served from the cache:
   nothing runs. A new pair is compared into the cache, never into the built store, and its page
   says it was made at a visitor's request with no explanation kept. The build record still holds.
3. The limiter: one in flight per address with a small queue; a bound on those running at once; a
   per-minute bound for the whole console, over which the answer is "busy" at once and nothing is
   queued; an address is held only while its request is in flight or waiting.
4. A comparison a verb did not finish in time is not kept.
5. No header is read but Content-Length and the configured address header; the log line holds the
   pair and the time taken, and no address.
6. Every other page is unchanged by a visitor's comparison, and no other POST answers.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from onetrace_console import visitor_compare as vc

PAIR_NEW = ("p1-02-baseline-set2", "p1-09-candidate-set3")
PAIR_BUILT = ("p1-02-baseline-set2", "p1-08-candidate-set2")


# ------------------------------------------------------------------------ 1. the request

@pytest.mark.parametrize("query, body, words", [
    ("a=x", b"a=p1-02-baseline-set2&b=p1-08-candidate-set2", "nothing after /compare"),
    ("", b"a=p1-02-baseline-set2&b=p1-08-candidate-set2&c=1", "a field other than a and b: c"),
    ("", b"a=p1-02-baseline-set2&a=p1-03-baseline-set3&b=p1-08-candidate-set2", "a exactly once"),
    ("", b"a=p1-02-baseline-set2", "b exactly once"),
    ("", b"a=..%2Fruns&b=p1-08-candidate-set2", "a is a path"),
    ("", b"a=p1-02-baseline-set2&b=C%3A%5Cx", "b is a path"),
    ("", b"\xff\xfe", "not a form"),
])
def test_a_request_that_is_not_two_run_ids_is_refused_with_the_reason(query, body, words, examined):
    examined(1, "request")
    with pytest.raises(vc.Refused, match=words):
        vc.read_pair(query, body)


@pytest.fixture(scope="module")
def demo(shared_demo):
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    return folder, Store(folder / "store" / "store")


@pytest.mark.parametrize("a, b, words", [
    ("no-such-run", "p1-08-candidate-set2", "holds no run named"),
    ("p1-02-baseline-set2", "p5-33-pump-offset-changed", "different pipelines"),
    ("p1-02-baseline-set2", "p1-02-baseline-set2", "the same run"),
])
def test_ids_the_build_does_not_pair_are_refused(demo, a, b, words, examined):
    _folder, store = demo
    examined(1, "pair")
    with pytest.raises(vc.Refused, match=words):
        vc.resolve(store, a, b)


def test_two_runs_of_one_pipeline_are_taken(demo, examined):
    _folder, store = demo
    a, b = vc.resolve(store, *PAIR_NEW)
    examined(1, "pair")
    assert (a.run_id, b.run_id) == PAIR_NEW


# ------------------------------------------------------------------------ 3. the limiter

def test_one_in_flight_per_address_with_a_small_queue(examined):
    limiter = vc.Limiter(per_minute=100, running=10, queue=1, wait_seconds=0.2)
    got = []
    with limiter.slot("10.0.0.1") as first:
        with limiter.slot("10.0.0.2") as other:
            got.append(other)
        t = threading.Thread(target=lambda: got.append(limiter.slot("10.0.0.1").__enter__()))
        t.start()
        time.sleep(0.05)
        #: One in flight and one waiting: a third from the same address is busy at once.
        started = time.monotonic()
        with limiter.slot("10.0.0.1") as third:
            got.append(third)
        quick = time.monotonic() - started
        t.join()
    examined(4, "slots asked for")
    assert first is True and got[0] is True       # another address is not held up
    assert got[1] is False and quick < 0.1         # the third: busy, nothing queued
    assert got[2] is False                         # the waiting one: its wait ran out
    assert limiter.addresses() == set()


def test_a_waiting_request_runs_when_the_one_before_it_ends(examined):
    limiter = vc.Limiter(per_minute=100, running=10, queue=1, wait_seconds=5)
    order = []

    def second():
        with limiter.slot("10.0.0.1") as ok:
            order.append(("second", ok))
    with limiter.slot("10.0.0.1"):
        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.1)
        order.append(("first done", True))
    t.join()
    examined(2, "requests from one address")
    assert order == [("first done", True), ("second", True)]


def test_running_at_once_is_bounded_for_the_whole_console(examined):
    limiter = vc.Limiter(per_minute=100, running=1, queue=2, wait_seconds=0.1)
    with limiter.slot("10.0.0.1") as a:
        with limiter.slot("10.0.0.2") as b:
            pass
    examined(2, "slots")
    assert (a, b) == (True, False)


def test_over_the_minute_s_bound_the_answer_is_busy_and_nothing_is_queued(examined):
    now = [1000.0]
    limiter = vc.Limiter(per_minute=3, running=10, queue=2, wait_seconds=5, clock=lambda: now[0])
    got = []
    for i in range(3):
        with limiter.slot(f"10.0.0.{i}") as ok:
            got.append(ok)
    started = time.monotonic()
    with limiter.slot("10.0.0.9") as over:
        got.append(over)
    quick = time.monotonic() - started
    now[0] += vc.WINDOW_SECONDS
    with limiter.slot("10.0.0.9") as later:
        got.append(later)
    examined(len(got), "slots asked for")
    assert got == [True, True, True, False, True] and quick < 0.1
    assert limiter.addresses() == set()


def test_sabotage_a_limiter_with_no_minute_bound_lets_every_request_run(examined):
    limiter = vc.Limiter(per_minute=10 ** 6, running=10, queue=2, wait_seconds=1)
    got = []
    for i in range(30):
        with limiter.slot(f"10.0.0.{i}") as ok:
            got.append(ok)
    examined(len(got), "slots")
    assert all(got)


# ------------------------------------------------------------------------ 5. headers

def test_only_the_named_headers_can_be_read(examined):
    from email.message import Message
    from onetrace_console.serve import OnlyHeaders
    m = Message()
    m["Content-Length"] = "10"
    m["Cookie"] = "onetrace_session=abc"
    m["Fly-Client-IP"] = "10.1.2.3"
    only = OnlyHeaders(m, {"content-length"})
    examined(4, "header reads")
    assert only.get("Content-Length") == "10"
    for read in (lambda: only.get("Cookie"), lambda: only["Fly-Client-IP"], lambda: "Cookie" in only,
                 lambda: only.items()):
        with pytest.raises(PermissionError):
            read()


# ------------------------------------------------------------------- the served console

def _post(base: str, body: bytes, *, path: str = "/compare", headers: dict | None = None):
    req = urllib.request.Request(base + path, data=body, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded", **(headers or {})})

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(req, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8")


@pytest.fixture(scope="module")
def served(shared_cli_demo, tmp_path_factory):
    """A public console over the demo as the image builds it, its Compare cache in a folder of its
    own, as the image would name one."""
    from tests.test_folder_load import _Console
    from tests.test_public_mode import _config, _tree
    tmp = tmp_path_factory.mktemp("visitor")
    built = shared_cli_demo["folder"]
    cache = tmp / "compared"
    config = _config(tmp, built, compare_cache=str(cache))
    port = json.loads(config.read_text(encoding="utf-8"))["port"]
    before = _tree(built)
    c = _Console(tmp, "serve", env={"ONETRACE_CONSOLE_CONFIG": str(config)})
    try:
        c.until("onetrace-console serving on")
        yield f"http://127.0.0.1:{port}", built, cache, c, before
    finally:
        c.stop()


def _output(c) -> list[str]:
    """Everything the console has printed so far: its start lines and its access log."""
    import queue
    while True:
        try:
            line = c._queue.get(timeout=1.0)
        except queue.Empty:
            return [line.rstrip("\n") for line in c.lines]
        if line is None:
            return [line.rstrip("\n") for line in c.lines]
        c.lines.append(line)


def _form(a: str, b: str) -> bytes:
    return f"a={a}&b={b}".encode("ascii")


def test_a_new_pair_is_compared_into_the_cache_and_served(served, examined):
    from tests.test_public_mode import _tree
    base, built, cache, c, before = served
    status, headers, _ = _post(base, _form(*PAIR_NEW), headers={"Cookie": "onetrace_session=x",
                                                                "X-Anything": "y"})
    examined(1, "visitor comparison")
    assert status == 303, (status, headers)
    location = headers["Location"]
    assert location.startswith("/diff/") and (cache / "pages" / location.lstrip("/")).is_file()
    with urllib.request.urlopen(base + location, timeout=30) as r:
        page = r.read().decode("utf-8")
    assert 'data-visitor-made' in page and "No explanation is kept for it." in page
    assert 'data-frame="banner"' in page
    assert _tree(built) == before, "a visitor's comparison changed the built folder"


def test_the_same_pair_again_runs_nothing(served, examined):
    base, _built, cache, c, _before = served
    first = _post(base, _form(*PAIR_NEW))
    files = {p.as_posix(): p.stat().st_mtime_ns for p in cache.rglob("*") if p.is_file()}
    again = _post(base, _form(*PAIR_NEW))
    examined(2, "requests for one pair")
    assert first[0] == again[0] == 303 and first[1]["Location"] == again[1]["Location"]
    assert {p.as_posix(): p.stat().st_mtime_ns for p in cache.rglob("*") if p.is_file()} == files
    lines = [json.loads(line) for line in _output(c) if line.startswith('{"at"') and '"compare"' in line]
    assert lines[-1]["outcome"] == "held" and lines[-1]["compare"] == {"a": PAIR_NEW[0], "b": PAIR_NEW[1]}


def test_a_pair_the_build_compared_is_served_as_built(served, examined):
    base, built, cache, _c, _before = served
    status, headers, _ = _post(base, _form(*PAIR_BUILT))
    examined(1, "request")
    assert status == 303
    assert (built / "store" / "pages" / headers["Location"].lstrip("/")).is_file()
    assert not (cache / "pages" / headers["Location"].lstrip("/")).exists()


def test_a_refusal_is_a_page_with_the_reason(served, examined):
    base, *_ = served
    status, _h, page = _post(base, _form("p1-02-baseline-set2", "p5-33-pump-offset-changed"))
    examined(1, "request")
    assert status == 400 and "different pipelines" in page and 'data-frame="banner"' in page


def test_a_body_over_the_limit_is_refused_unread(served, examined):
    from tools import container_check
    base, *_ = served
    examined(1, "request")
    assert container_check.compare_problems(*container_check.raw_post(base, "/compare")) == []


def test_the_log_holds_the_pair_and_the_time_and_no_address(served, examined):
    from tools import container_check
    _base, _built, _cache, c, _before = served
    lines = _output(c)
    compares = [json.loads(line) for line in lines if '"compare"' in line and line.startswith("{")]
    examined(len(compares), "Compare's log lines")
    assert compares
    for entry in compares:
        assert set(entry) == container_check.COMPARE_FIELDS and isinstance(entry["ms"], int)
    assert "127.0.0.1" not in "\n".join(line for line in lines if line.startswith("{"))
    assert container_check.log_problems(lines) == []


def test_every_other_page_is_unchanged_and_no_other_post_answers(served, examined):
    """The one exception: after visitors' comparisons, every built page is the bytes it was, and every
    other POST is refused unread (tests/test_public_mode.py holds each route)."""
    from tools import container_check
    from tests.test_public_mode import _tree
    base, built, _cache, _c, before = served
    examined(len(container_check.ROUTES) + 1, "routes and the built folder")
    assert _tree(built) == before
    for route in container_check.ROUTES:
        assert container_check.refusal_problems(*container_check.raw_post(base, route)) == [], route


def test_the_picker_is_on_each_pipeline_s_page_with_its_own_runs(served, examined):
    from onetrace_console.store import Store
    base, built, *_ = served
    store = Store(built / "store" / "store")
    from onetrace_console.overview import pipelines
    seen = 0
    for p in pipelines(store):
        page = (built / "store" / "pages" / f"pipeline-{p.label.lower()}.html").read_text(encoding="utf-8")
        if len(p.runs) < 2:
            assert "data-visitor-compare" not in page
            continue
        form = page.split("<form", 1)[1].split("</form>", 1)[0]
        assert 'method="post" action="/compare"' in form
        options = sorted(set(__import__("re").findall(r'<option value="([^"]+)"', form)))
        assert options == sorted(r.run_id for r in p.runs), p.label
        seen += 1
    examined(seen, "pipeline pages with a picker")


# ------------------------------------------------------------------------ 4. timeout

def test_a_comparison_a_verb_did_not_finish_is_not_kept(shared_demo, tmp_path, monkeypatch, examined):
    from onetrace_console import compare as compare_mod
    from onetrace_console.store import Store
    folder = shared_demo["folder"]
    base = Store(folder / "store" / "store")
    #: A pair the build did not compare, so the verbs run.
    a, b = vc.resolve(base, "p9-47-torque-tool-firmware-changed", "p9-48-torque-one-bolt-low")
    real = compare_mod._run_verb

    def slow(verb, *args, **kwargs):
        run = real(verb, *args, **kwargs)
        from dataclasses import replace
        return replace(run, note="timed out")
    monkeypatch.setattr(compare_mod, "_run_verb", slow)
    examined(1, "comparison stopped")
    with pytest.raises(vc.Refused) as e:
        vc.make(base, tmp_path / "compared", a, b, timeout=1)
    assert e.value.status == 504 and "nothing was kept" in str(e.value)
    assert not list((tmp_path / "compared" / "store" / "comparisons").glob("*.json"))
    assert not (tmp_path / "compared" / "pages").exists()


def test_a_cache_that_cannot_be_written_is_said(tmp_path, examined):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    examined(1, "cache")
    with pytest.raises(vc.Refused) as e:
        vc.cache_store(blocker / "compared")
    assert e.value.status == 503 and "cannot keep a comparison" in str(e.value)


def test_the_build_record_does_not_cover_the_cache(shared_demo, tmp_path, examined):
    from onetrace_console.demo_store import check_build_record
    from tests.conftest import demo_copy
    folder = demo_copy(shared_demo, tmp_path / "demo")
    (folder / "store" / "compared" / "pages" / "diff").mkdir(parents=True)
    (folder / "store" / "compared" / "pages" / "diff" / "x.html").write_text("made by a visitor")
    examined(2, "build record checks")
    assert check_build_record(folder) == []
    (folder / "store" / "pages" / "planted.html").write_text("x")
    assert check_build_record(folder) == ["store/pages/planted.html was added"]


def test_many_requests_at_once_each_find_the_cache_writable(tmp_path, examined):
    """Each request's write check is a file of its own: with one shared file, two requests at once
    removed each other's and one was told the cache could not be written (seen in a burst)."""
    root = tmp_path / "compared"
    errors, start = [], threading.Barrier(24)

    def take():
        start.wait()
        for _ in range(20):
            try:
                vc.cache_store(root)
            except vc.Refused as e:
                errors.append(str(e))
    threads = [threading.Thread(target=take) for _ in range(24)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    examined(24 * 20, "write checks at once")
    assert errors == []
    assert [p.name for p in (root / "store").iterdir() if p.name.startswith(".write-check")] == []


# ------------------------------------------------------------------ the demo's configuration

BOUNDS = {"compare_per_minute": "PER_MINUTE", "compare_running": "RUNNING", "compare_queue": "QUEUE",
          "compare_wait_seconds": "WAIT_SECONDS", "compare_verb_seconds": "TIMEOUT_SECONDS"}


def test_each_bound_is_a_key_the_configuration_can_lower_and_not_raise(tmp_path, examined):
    from onetrace_console.config import Config, ConfigError, _from_mapping
    shipped = Config()
    examined(len(BOUNDS) * 2, "bounds set lower and higher")
    for key, constant in BOUNDS.items():
        assert getattr(shipped, key) == getattr(vc, constant), key
        lower = type(getattr(shipped, key))(1)
        assert getattr(_from_mapping({"public": True, key: lower}, source="t"), key) == lower
        with pytest.raises(ConfigError, match="can be lowered, not raised"):
            _from_mapping({"public": True, key: getattr(shipped, key) + 1}, source="t")


def test_the_address_header_is_read_only_where_named_and_only_on_a_public_console(examined):
    from email.message import Message
    from onetrace_console.config import Config, ConfigError, _from_mapping
    m = Message()
    m["Fly-Client-IP"] = "10.1.2.3"
    examined(4, "address choices and configurations")
    named = _from_mapping({"public": True, "compare_client_header": "Fly-Client-IP"}, source="t")
    assert vc.client_address(named, m, "172.16.0.1") == "10.1.2.3"
    assert vc.client_address(named, Message(), "172.16.0.1") == "172.16.0.1"
    #: Not named: the header is never asked for (a header object that refuses every read holds it).
    from onetrace_console.serve import OnlyHeaders
    assert vc.client_address(Config(public=True), OnlyHeaders(m, set()), "172.16.0.1") == "172.16.0.1"
    with pytest.raises(ConfigError, match="compare_client_header is set and public is not true"):
        _from_mapping({"compare_client_header": "Fly-Client-IP"}, source="t")


def test_the_demo_s_image_names_its_cache_and_the_address_header(examined):
    import json
    from onetrace_console.config import _from_mapping
    from tests.test_folder_load import REPO
    data = json.loads((REPO / "deploy" / "fly" / "public.json").read_text(encoding="utf-8"))
    config = _from_mapping(data, source="public.json")
    docker = (REPO / "deploy" / "fly" / "Dockerfile").read_text(encoding="utf-8")
    examined(2, "files of the image")
    assert config.compare_cache == "/srv/onetrace-demo-compared"
    assert config.compare_client_header == "Fly-Client-IP"
    line = "RUN mkdir /srv/onetrace-demo-compared && chown demo /srv/onetrace-demo-compared"
    assert docker.count(line) == 1
    #: After the build's chmod (the store read-only) and once the user exists; the store not given away.
    assert docker.index("chmod -R a+rX,a-w /srv/onetrace-demo") < docker.index("useradd") < docker.index(line)
    assert "chown demo /srv/onetrace-demo " not in docker and "chown -R demo" not in docker


def test_a_changed_byte_in_the_store_is_still_refused_beside_the_cache(shared_demo, tmp_path, examined):
    from onetrace_console.demo_store import check_build_record
    from tests.conftest import demo_copy
    folder = demo_copy(shared_demo, tmp_path / "demo")
    (folder / "store" / "compared" / "store").mkdir(parents=True)
    (folder / "store" / "compared" / "store" / "x.json").write_text("{}")
    one = next(p for p in sorted((folder / "store" / "store" / "runs").glob("*.json")))
    one.write_bytes(one.read_bytes() + b" ")
    examined(1, "build record check")
    rel = one.relative_to(folder).as_posix()
    assert check_build_record(folder) == [f"{rel} was changed"]
