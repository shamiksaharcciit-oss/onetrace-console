# The hosted read-only demo of onetrace-console. Built from the repository root:
#
#   docker build -f deploy/fly/Dockerfile -t onetrace-console-demo .
#
# What it serves is built into the image: the reference demo's two runs, delivered, checked and
# compared, and every page drawn with the public banner (`onetrace-console demo --public --build`).
# The built store is owned by root and not writable, and the console runs as another user, so a
# write the code did not intend fails at the operating system as well. Every machine started from
# the image serves exactly that store; nothing is checked, compared or drawn at start.
#
# Build time reaches PyPI through the hash-pinned install only; the running console calls out to
# nothing. No secret is needed at build or at run.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# ONETRACE_CONSOLE_CONFIG is the only environment variable the console reads: it names the one
# configuration file, deploy/fly/public.json, baked in below. Host and port live in that file.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    ONETRACE_CONSOLE_CONFIG=/etc/onetrace-console/public.json

WORKDIR /app

COPY requirements.lock ./
COPY tools/install_pinned.py ./tools/install_pinned.py
COPY src/ ./src/
COPY LICENSE ./LICENSE
COPY deploy/fly/public.json /etc/onetrace-console/public.json

# The pinned install (tools/install_pinned.py: every wheel checked against requirements.lock).
RUN python tools/install_pinned.py

RUN printf '#!/bin/sh\nexec python -m onetrace_console "$@"\n' > /usr/local/bin/onetrace-console \
    && chmod +x /usr/local/bin/onetrace-console

# The demo's store, built now, then made read-only: owned by root, no write bit anywhere. The
# configuration file and the code are root's too.
RUN python -m onetrace_console demo --public --build /srv/onetrace-demo \
    && chown -R root:root /srv/onetrace-demo /etc/onetrace-console /app \
    && chmod -R a-w /srv/onetrace-demo /etc/onetrace-console

# The serving user: not root, no home, no shell, owning nothing it serves.
RUN useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin demo
USER demo

EXPOSE 8080

# Plain HTTP inside the machine; the host's proxy ends TLS in front of it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]

CMD ["python", "-m", "onetrace_console", "serve"]
