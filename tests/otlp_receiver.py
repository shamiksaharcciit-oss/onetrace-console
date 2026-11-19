"""A recording OTLP/HTTP receiver on loopback, for the forwarding tests: no backend, no key, no network.

`Receiver()` listens on 127.0.0.1 on a port of its own and keeps every request it is sent (its method, path, headers
and body). It answers each `POST /v1/traces` from `answers`, a list of statuses taken in order (200 once the list is
spent); the status `RESET` closes the connection without an answer, as a network failure does. `delay` holds each
answer back that many seconds, as a slow destination does. `log` writes one line per request, without its headers'
values: the path, the content type, the body's size and sha256.
"""

from __future__ import annotations

import hashlib
import socket
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RESET = -1


@dataclass
class Request:
    method: str
    path: str
    headers: dict
    body: bytes


class Receiver:
    def __init__(self, answers: list[int] | None = None, delay: float = 0.0) -> None:
        self.requests: list[Request] = []
        self.answers = list(answers or [])
        self.delay = delay
        self._lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:  # noqa: D102 - quiet
                pass

            def do_POST(self) -> None:  # noqa: N802 - the standard library's name
                n = int(self.headers.get("Content-Length", "0") or "0")
                body = self.rfile.read(n)
                with outer._lock:
                    outer.requests.append(Request("POST", self.path, dict(self.headers.items()), body))
                    status = outer.answers.pop(0) if outer.answers else 200
                if outer.delay:
                    time.sleep(outer.delay)
                if status == RESET:
                    self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
                    self.close_connection = True
                    self.connection.close()
                    return
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.endpoint = f"http://127.0.0.1:{self.port}"
        self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def __enter__(self) -> Receiver:
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self._thread.join(timeout=5)

    def traces(self) -> list[Request]:
        with self._lock:
            return [r for r in self.requests if r.path.endswith("/v1/traces")]

    def wait_for(self, n: int, timeout: float = 20.0) -> list[Request]:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = self.traces()
            if len(got) >= n:
                return got
            time.sleep(0.05)
        return self.traces()

    def log(self) -> str:
        """One line per request, without any header's value."""
        out = []
        for r in self.requests:
            ctype = r.headers.get("Content-Type", "")
            out.append(
                f"{r.method} {r.path} content-type={ctype} bytes={len(r.body)} "
                f"sha256={hashlib.sha256(r.body).hexdigest()} header names={sorted(r.headers)}"
            )
        return "\n".join(out) + "\n"
