"""The container's TLS configuration, checked against a real container, not assumed from the Dockerfile.

    Tests: a real `docker run` with a mounted test certificate reaches /health over TLS from the
    host; without a certificate, it refuses to start with its fix: line.

What this does, in order, printing each result as measured:

1. makes a throwaway self-signed test certificate (openssl), in a temporary folder, never reused;
2. builds this tree's image as `onetrace-console:tls-check` (local only; nothing is pushed);
3. runs it with the certificate mounted at /etc/onetrace-console/tls and its port published to
   the host's loopback only, then asks the host for `https://127.0.0.1:<port>/health` (the test
   certificate is self-signed, so the check is of the connection, not the name), and asks for
   plain `http://` too, which must be refused, and waits for the image's own HEALTHCHECK to
   read `healthy`;
4. runs it again with no certificate mounted: it must exit 1, say which file is missing, carry
   a `fix:` line, and print no traceback;
5. removes both containers, their volumes and the image.

Exit 0 only if every check holds. Needs Docker and openssl; the pytest suite does not.

    python tools/container_tls_check.py [--port 18443]
"""
from __future__ import annotations

import argparse
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "onetrace-console:tls-check"


def run(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=check)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18443)
    args = parser.parse_args(argv)
    held = []

    def said(ok: bool, what: str) -> None:
        held.append(ok)
        print(f"{'HOLDS ' if ok else 'FAILS '} {what}", flush=True)

    with tempfile.TemporaryDirectory(prefix="onetrace-tls-check-") as tmp:
        tls = Path(tmp) / "tls"
        tls.mkdir()
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-keyout", str(tls / "key.pem"),
            "-out", str(tls / "cert.pem"), "-days", "1", "-nodes", "-subj", "/CN=localhost")
        # The container runs as a non-root user; a mounted key must be readable by it.
        for f in tls.iterdir():
            f.chmod(0o644)
        print(f"test certificate made in {tls}", flush=True)

        build = run("docker", "build", "-q", "-t", IMAGE, str(ROOT), check=False)
        said(build.returncode == 0, f"the image builds ({build.stdout.strip() or build.stderr[-300:]})")
        if build.returncode:
            return 1
        try:
            # --- with a certificate: reachable over TLS from the host, and only over TLS
            run("docker", "run", "-d", "--name", "tls-check-with", "--read-only",
                "--tmpfs", "/tmp:rw,size=64m", "-v", "tls-check-data:/data",
                "-v", f"{tls}:/etc/onetrace-console/tls:ro",
                "-p", f"127.0.0.1:{args.port}:8080", IMAGE)
            unverified = ssl._create_unverified_context()
            answer = None
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"https://127.0.0.1:{args.port}/health",
                                                timeout=3, context=unverified) as r:
                        answer = (r.status, r.read())
                        break
                except (urllib.error.URLError, ConnectionError, OSError):
                    time.sleep(1)
            said(answer == (200, b"ok\n"),
                 f"with a mounted certificate, the host reaches /health over TLS: {answer}")
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{args.port}/health", timeout=3) as r:
                    plain = f"answered {r.status}"
            except Exception as e:  # noqa: BLE001 - any refusal is the expected outcome
                plain = f"refused ({type(e).__name__})"
            said(plain.startswith("refused"), f"plain HTTP is not served: {plain}")
            #: The image's own HEALTHCHECK, over TLS inside the container: its first probe runs
            #: after the 30 s interval, so it is waited for, up to two intervals and a retry.
            state = ""
            for _ in range(100):
                state = run("docker", "inspect", "-f", "{{.State.Health.Status}}",
                            "tls-check-with", check=False).stdout.strip()
                if state in ("healthy", "unhealthy"):
                    break
                time.sleep(1)
            said(state == "healthy", f"its own HEALTHCHECK reads: {state or 'not reported'}")

            # --- without a certificate: refuses to start, in words, with its fix line
            run("docker", "run", "--name", "tls-check-without", "--read-only",
                "--tmpfs", "/tmp:rw,size=64m", "-v", "tls-check-data2:/data", IMAGE, check=False)
            code = run("docker", "inspect", "-f", "{{.State.ExitCode}}", "tls-check-without",
                       check=False).stdout.strip()
            logs = run("docker", "logs", "tls-check-without", check=False)
            text = logs.stdout + logs.stderr
            said(code == "1", f"without a certificate it exits 1 (exit code {code})")
            said("refusing to start: no TLS certificate at /etc/onetrace-console/tls/cert.pem"
                 in text, "it says which file is missing")
            said("\nfix: " in text, "it carries a fix: line")
            said("Traceback" not in text, "it prints no traceback")
            print("        its words: " + " | ".join(line for line in text.splitlines() if line),
                  flush=True)
        finally:
            for name in ("tls-check-with", "tls-check-without"):
                run("docker", "rm", "-f", name, check=False)
            run("docker", "volume", "rm", "tls-check-data", "tls-check-data2", check=False)
            run("docker", "rmi", IMAGE, check=False)
    print("all hold" if all(held) else "NOT ALL HOLD", flush=True)
    return 0 if all(held) else 1


if __name__ == "__main__":
    raise SystemExit(main())
