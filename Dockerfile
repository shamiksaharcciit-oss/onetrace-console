# The console as a container the customer runs.
#
# THE CONTAINER RULING, AS BUILT HERE
# ------------------------------------
# The customer runs it. No shared back end: this image talks to nothing but the one
# volume mounted into it and the local processes it starts (the verifier, the SDK's
# verbs -- both subprocesses, never a network call; see onetrace_console/checks.py and
# compare.py). No network access assumed at runtime: verified below with
# `docker run --network none`. Nothing sent home: no telemetry, no update check, no
# outbound call anywhere in this image's own code. Anchoring opt-in: SDK 0.1.2 has no
# anchoring mechanism (see the operator README's non-claims) -- nothing to opt into yet.
#
# ONE ORGANISATION PER INSTALL. There is no user or tenant model in this codebase at all
# -- one running container is one installation, full stop, and sign-in is a later work
# order (see the README). That is a property of what does not exist yet, not a setting.
#
# BUILD TIME MAY REACH PyPI; RUNTIME MUST NOT.
# The two `pip install` layers below are the only place this build touches a network, and
# both are hash-pinned (`--require-hashes`): a byte that does not match the pin fails the
# build outright, the same guarantee `requirements.lock` already gives outside a container.
# Verified with `--network none` further down, not merely asserted here.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

# No .pyc write-back into a read-only layer's cache paths; no telemetry or version-check
# chatter from pip during the build.
#
# ONETRACE_CONSOLE_CONFIG is the only environment variable this console reads at runtime:
# host, port, the store's root, and every upload-hardening limit
# all come from the one file it names. Everything else below is build-time only.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src \
    ONETRACE_CONSOLE_CONFIG=/etc/onetrace-console/config.json

WORKDIR /app

# Only what installing and running need -- not the test suite, not the archived reports,
# not the SDK's own exam/ fixtures (those are fetched by a developer's own venv, never by
# this image). Copied before the source so an unrelated source edit does not bust pip's
# build-layer cache.
COPY requirements.lock ./
COPY tools/install_pinned.py ./tools/install_pinned.py
COPY src/ ./src/
COPY LICENSE ./LICENSE
# The container's own configuration: it listens on every interface
# INSIDE the container, so a published port reaches it, and serves TLS itself from a
# certificate the operator mounts at /etc/onetrace-console/tls/ -- it refuses to start
# until one is there. Sign-in stays on; a container without it is refused (option 3).
# config/default.json stays the schema's defaults, for everything outside the container.
COPY config/container.json /etc/onetrace-console/config.json

# The one authoritative install command (tools/install_pinned.py's own docstring explains
# --report and why --force-reinstall is there). Installed as root because site-packages
# needs root to write to; the running process drops to a non-root user below, well before
# any network or file-system access happens.
RUN python tools/install_pinned.py

# The console's OWN `onetrace-console` command (its `admin create`) -- found
# missing by actually running it inside a built image, not assumed present because
# `PYTHONPATH=/app/src` already lets `python -m onetrace_console` work on its own.
# A plain shim, not `pip install .`: this package's own `dependencies` list needs an
# index to resolve, and a real `pip install` of a local project needs a build backend
# the slim base image does not carry -- both would touch the network a second,
# unpinned way. The shim is
# exactly what a real entry point already does: exec the same interpreter, same
# module, same argv.
RUN printf '#!/bin/sh\nexec python -m onetrace_console "$@"\n' > /usr/local/bin/onetrace-console \
    && chmod +x /usr/local/bin/onetrace-console

# A non-root user. The store's mountpoint is created and owned by it now, while the
# filesystem underneath is still writable at build time -- `docker run -v` on top of an
# existing directory keeps that directory's ownership, but only if it already has one.
RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin console \
    && mkdir -p /data \
    && chown -R console:console /data /app
USER console

# Read-only root filesystem (`docker run --read-only`) means /tmp is read-only too unless
# the operator also gives it a tmpfs (`--tmpfs /tmp`) -- documented in the README's run
# command, not assumed silently, because checks.py and compare.py both use
# `tempfile.TemporaryDirectory()` for a materialised run while it is being checked or
# compared. VOLUME below is the ONE writable mount the order asks for; /tmp is a second,
# necessary one but it is ephemeral scratch space, not data -- nothing under it needs to
# survive a restart, so it is not part of the data volume.
VOLUME ["/data"]
EXPOSE 8080

# Over TLS, as the console serves it (B5). The probe reaches the container's own listener
# on its own loopback, so it does not verify the operator's certificate against a name --
# it asks only whether the console answers. The port mapping (`-p 127.0.0.1:8080:8080`, or
# none at all) is the operator's choice, made at `docker run`, not baked in here.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import ssl, urllib.request as u; u.urlopen('https://127.0.0.1:8080/health', timeout=3, context=ssl._create_unverified_context()).read()"]

CMD ["python", "-m", "onetrace_console", "serve"]
