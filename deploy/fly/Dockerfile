# The hosted read-only demo of onetrace-console. Built from the repository root:
#
#   docker build -f deploy/fly/Dockerfile -t onetrace-console-demo .
#
# What it serves is built into the image: the demo store's runs, recorded at build time by its
# builder (or taken from deploy/fly/kept/, with the explanations kept there), delivered, checked and
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
# deploy/fly/ as a whole, so the build reads deploy/fly/kept/ where the repository holds it; a COPY
# naming that folder alone would fail the build where it does not.
COPY deploy/fly/ ./deploy/fly/

# The pinned install (tools/install_pinned.py: every wheel checked against requirements.lock).
RUN python tools/install_pinned.py

RUN printf '#!/bin/sh\nexec python -m onetrace_console "$@"\n' > /usr/local/bin/onetrace-console \
    && chmod +x /usr/local/bin/onetrace-console

# The demo's store, built now, then made read-only: owned by root, readable by every user (the
# serving user reads it, and checks it against its build record at start), no write bit anywhere. The
# configuration file and the code are root's too. Where deploy/fly/kept/ is there, the build takes its
# runs, as its build record vouches for them, and keeps the explanations under it
# (deploy/fly/kept/README.md); where it is not, the runs are recorded now and none is kept. The public
# site's links into the demo (deploy/fly/site_links.txt): a listed comparison page this build names
# anew gets a page at its old name that sends a reader on.
RUN if [ -d deploy/fly/kept ]; then \
        python -m onetrace_console demo --public --build /srv/onetrace-demo \
            --runs-from /app/deploy/fly/kept --explanations /app/deploy/fly/kept \
            --site-links /app/deploy/fly/site_links.txt; \
    else \
        python -m onetrace_console demo --public --build /srv/onetrace-demo; \
    fi \
    && chown -R root:root /srv/onetrace-demo /etc/onetrace-console /app \
    && chmod -R a+rX,a-w /srv/onetrace-demo /etc/onetrace-console

# The serving user: not root, no home, no shell, owning nothing it serves.
RUN useradd --no-create-home --uid 10001 --shell /usr/sbin/nologin demo

# Compare's cache (public.json's `compare_cache`): the one folder the serving user writes, beside the
# built store and outside its build record; the store itself stays root's and read-only. A machine
# started from the image starts with it empty.
RUN mkdir /srv/onetrace-demo-compared && chown demo /srv/onetrace-demo-compared
USER demo

EXPOSE 8080

# Plain HTTP inside the machine; the host's proxy ends TLS in front of it.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]

CMD ["python", "-m", "onetrace_console", "serve"]
