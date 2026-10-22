# Running the console: an operator's guide

This is the console as a container you run for a team. No shared back end, no account with
anyone, no data that leaves the machine it runs on.

## What this is not (read this before the rest)

- **One organisation per install.** There is no user or tenant model in this codebase at all
  -- one running container is one installation, full stop. This is not a setting you turn on;
  it is what the code does not yet have. (There is exactly one configuration FILE, below,
  which is the literal sense in which this is also true of configuration.)
- **Sign-in is on by default, and a fresh install serves nothing until you
  create an account.** Local mode, with no configuration file named, has no sign-in: see
  "Local mode" below. `admin create` inside the container, then TLS (an operator-supplied
  certificate, below) or a loopback listener behind your own TLS-terminating proxy, is
  required before this console will serve a single page. See "Signing in," below.
  - **Never expose it directly to the internet without TLS.** Passwords and session
    cookies must never cross the network in clear text; the console refuses to start
    a non-loopback, plain-HTTP listener with sign-in on.
- **Signatures and anchors are checked as `onetrace-verify` 0.2.1 checks them.** A valid signature
  reads as trusted only for a key in the trust file you configure (`trust_file`, below); without
  one, it reads "Signed, key not trusted". The console never makes, edits or guesses a trust file.
  An anchor shows that the record existed by the anchored time, not that the run was correct.
- **Output files are checked only when a run carries them.** When a run's folder holds
  `artifacts/`, the console runs the verifier with `--require-artifacts`, and each output file is
  checked against the digest its receipt records. A run delivered without `artifacts/` is shown as
  the verifier says: held, with its output files not checked.
- **What a receipt says of its own coverage is its own account.** Whether every declared
  step left a receipt, and whether a step skipped items, is read from the receipts' own
  coverage fields; no check confirms it.

## Local mode: the open-source console on your own machine

With **no configuration file named** (`ONETRACE_CONSOLE_CONFIG` absent from the environment),
`onetrace-console serve` starts in **local mode**. Set but blank, it
refuses to start: that is a file someone meant to name.

- it listens on **127.0.0.1:8080 only**, whatever else the defaults say -- nothing on another
  machine can reach it;
- there is **no sign-in**: anyone who can use this machine's loopback can read and write
  every page and route;
- in place of sign-in, a browser guard: it answers only requests naming its own loopback
  address (`127.0.0.1`, `localhost` or `[::1]` with its port) as their Host, and refuses a
  write that says it comes from another web origin -- so a web page you open cannot post to
  it, and a hostile name pointed at 127.0.0.1 cannot read it;
- it refuses a store that was set up with sign-in (one holding accounts), rather than serve
  it open;
- the store is `./store`, under the directory you start it from;
- it says all of this, with its address and its store, once it is listening.

To serve beyond this machine, name a configuration file: it is the only way to set another
host or port, and with sign-in on it must also pass the plain-HTTP refusal
below. The container image always names one (`/etc/onetrace-console/config.json`), so it
never runs in local mode.

## Building the image

```
docker build -t onetrace-console .
```

The base image is pinned by digest (`python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`),
and `onetrace` and `onetrace-verify` are installed with
`pip install --require-hashes` — see `requirements.lock`. The only network
access this build performs is fetching the seven packages `requirements.lock` pins from PyPI
(`onetrace`, `onetrace-verify`, and the five its `[crypto]` extra needs), each hash-checked; a
byte that does not match the pin fails the build outright. **Nothing at runtime reaches the
network at all** — see "No shared back end," below, and its own proof.

## Configuration

**One file, mounted read-only. Its path is the only environment variable this console
reads**. The image ships a default at
`/etc/onetrace-console/config.json`, with `ONETRACE_CONSOLE_CONFIG` already pointing at it —
`docker run` with no further flags works out of the box. Every key it may hold, and what it
means:

```json
{
  "host": "127.0.0.1",
  "port": 8080,
  "store_root": "/data",
  "max_request_body": 67108864,
  "max_members": 512,
  "max_member_size": 16777216,
  "max_total_extracted_size": 67108864,
  "request_timeout_seconds": 30.0,
  "sign_in": {
    "enabled": true,
    "tls_cert_path": "",
    "tls_key_path": "",
    "session_idle_timeout_seconds": 1800,
    "session_absolute_timeout_seconds": 43200,
    "rate_limit_max_attempts_per_account": 10,
    "rate_limit_max_attempts_per_client": 20,
    "rate_limit_window_seconds": 300,
    "rate_limit_max_concurrent_hashes": 2,
    "insecure_cookie_for_local_dev": false
  }
}
```

| key | meaning |
|---|---|
| `host`, `port` | where the console listens **inside** the container — `127.0.0.1` in every default and example here; publishing further is the operator's own `-p` choice, never this file's |
| `store_root` | where the store and rendered pages live (`/data` — the one mounted volume) |
| `max_request_body` | an upload over this many bytes is refused **before** it is read |
| `max_members` | an archive with more members than this is refused |
| `max_member_size`, `max_total_extracted_size` | per-member and total declared size limits, checked from the archive's own headers before any content is read — the archive-bomb guard |
| `request_timeout_seconds` | a request whose body has not finished arriving within this many seconds is abandoned |
| `access_log_max_segment_bytes` | the console's own access log rotates to a new chained segment once the current one would exceed this many bytes |
| `sign_in.enabled` | **on by default.** Every route except `GET /health`, the sign-in page and sign-out requires a principal: a browser session (`viewer`) or a bearer token (`ingester`, see "Ingester tokens," below). Turning it off is an explicit choice a config file must make, and the console logs a warning at every start-up while it is off. Local mode has none. |
| `trust_file` | a path to an `onetrace-trust/0.1` file listing the signing keys you trust; absent by default. Set, every check runs the verifier with `--trust` and that file; absent, a valid signature reads "Signed, key not trusted". A file the verifier can't read is shown as its own FAIL row. |
| `public` | `false` by default. `true` makes a read-only public demo: every write is refused before its body is read, the pages are served as they were built and never drawn again, and every page carries a banner. It refuses to start beside sign-in, the decisions extension (configuration key `extensions.onedoor`), a trust file other than the demo's, or a store holding accounts or tokens. Its store is built with `onetrace-console demo --public --build <folder>`; `deploy/fly/` serves one. |
| `sign_in.tls_cert_path`, `sign_in.tls_key_path` | a PEM certificate and key. **Required together if `host` is not loopback** -- the console refuses to start otherwise, rather than serve sign-in over plain HTTP on a non-loopback listener |
| `sign_in.session_idle_timeout_seconds`, `sign_in.session_absolute_timeout_seconds` | a signed-in session expires after this much inactivity, or this long regardless of activity, whichever comes first (defaults: 30 minutes, 12 hours) |
| `sign_in.rate_limit_max_attempts_per_account`, `sign_in.rate_limit_max_attempts_per_client`, `sign_in.rate_limit_window_seconds` | sign-in attempts are throttled per account and per client address, independently, over the same rolling window |
| `sign_in.rate_limit_max_concurrent_hashes` | a global cap (default 2) on how many password checks may be hashing (scrypt, 128 MiB each) at the same time, independent of which account or client is asking -- a request that cannot get a slot gets `503`, never queued |
| `sign_in.insecure_cookie_for_local_dev` | **default `false`, and the only way to get a non-`Secure` session cookie.** Refused outright unless `host` is loopback -- it exists solely for a loopback listener sitting behind your own local, HTTPS-terminating proxy. Logged loudly at start-up when set. |

**Creating the first (and every) account.** There is no web sign-up page — "whoever
reaches the first-run page first becomes admin" is a takeover race, not a feature. **A
fresh install serves no pages at all until this has been run once.** Create an account
from inside the container:

```
docker exec -i <container> onetrace-console admin create alice
```

Type (or pipe) the password, then Enter. The password is read from **stdin only** — never
a command-line argument (visible in `ps` and shell history) and never an environment
variable (visible to every other process sharing the container's environment). It must be
at least 12 characters (OWASP's own length recommendation); there are no other composition
rules.

**Ingester tokens.** A machine credential for `POST /v1/runs` / `POST /v1/decisions`,
never a browser session — a bearer token grants `ingester` and nothing else; a signed-in
session never grants `ingester` either. Created and revoked the same way, inside the
container:

```
docker exec -i <container> onetrace-console token create ci-pipeline
#   token id: 1a2b3c4d5e6f7890
#   token (shown once, store it now): <a long random string>

docker exec -i <container> onetrace-console token revoke 1a2b3c4d5e6f7890
```

The raw token is printed **exactly once** — it is stored only as a hash and cannot be
recovered afterward, only revoked and replaced with a new one. Send it as
`Authorization: Bearer <token>`:

```
curl -H "Authorization: Bearer <token>" --data-binary @run.tar http://127.0.0.1:8080/v1/runs
```

An unknown key, or a file that is not valid JSON, is **refused outright** — the console will
not start rather than silently ignore a typo in your configuration. Omitting a key uses its
default, shown above.

**To override any value:** mount your own file over the image's default, read-only:

```
docker run -d \
  --name onetrace-console \
  --network none \
  --read-only --tmpfs /tmp:rw,size=64m \
  -v onetrace-console-data:/data \
  -v ./my-config.json:/etc/onetrace-console/config.json:ro \
  onetrace-console
```

`store_root` in your file should still be `/data` (or wherever you mount the data volume) —
this file configures behaviour, not where the volume goes; the volume mount itself is still a
`docker run -v`, not a config key.

## Running it

**The container serves HTTPS itself, and needs a certificate to start.**
Its configuration listens on every interface *inside* the container, with sign-in on, and
names a certificate and key it does not ship: `/etc/onetrace-console/tls/cert.pem` and
`/etc/onetrace-console/tls/key.pem`. Mount a folder holding your PEM certificate and its
private key there:

```
docker run -d \
  --name onetrace-console \
  --network none \
  --read-only --tmpfs /tmp:rw,size=64m \
  -v onetrace-console-data:/data \
  -v "$PWD/tls":/etc/onetrace-console/tls:ro \
  onetrace-console
```

Without a certificate it does not start. It exits with, for example:

```
refusing to start: no TLS certificate at /etc/onetrace-console/tls/cert.pem (sign_in.tls_cert_path)
fix: mount a PEM certificate and its private key at sign_in.tls_cert_path and sign_in.tls_key_path -- in the container, with docker run -v <a folder holding cert.pem and key.pem>:/etc/onetrace-console/tls:ro -- or run the console behind your own TLS-terminating proxy (OPERATOR_README.md).
```

**Only to try it on your own machine,** a throwaway self-signed certificate will do. Your
browser will warn about it, and it is no use to anyone else:

```
mkdir tls
openssl req -x509 -newkey rsa:2048 -keyout tls/key.pem -out tls/cert.pem -days 30 -nodes -subj "/CN=localhost"
```

**There is no container without sign-in.** A console that anyone who can reach its port can
read and write is local mode (`python -m onetrace_console serve` with no configuration file,
on your own machine, on loopback only), not this container. To look around without
installing anything, use the hosted read-only demo.

**Behind your own TLS-terminating proxy instead.** If your team terminates TLS elsewhere,
mount a configuration of your own at `/etc/onetrace-console/config.json` that keeps `host` at
`127.0.0.1` and leaves both `sign_in.tls_*` paths empty. Then run your proxy in the
console's own network namespace (`docker run --network container:onetrace-console …`),
forwarding to `http://127.0.0.1:8080`, and publish the proxy's port rather than the
console's. The console refuses a non-loopback listener with sign-in on and no TLS, so the
proxy is the only way in. Its session cookies stay `Secure`, because the browser reaches it
over HTTPS.

Every flag here is load-bearing, not decoration:

- **`--network none`.** This console never needs the network at runtime — it checks stored
  runs and compares them locally, calling the verifier and the SDK's own verbs as
  subprocesses, never over a socket. Verified directly: with this flag set, an attempt from
  inside the running container to reach PyPI or a public DNS resolver both fail outright
  (`Temporary failure in name resolution`, `Network is unreachable`).
- **`--read-only --tmpfs /tmp`.** The root filesystem is read-only; nothing this image runs
  needs to write anywhere except the one data volume and scratch space while a run is being
  checked or compared (`tempfile.TemporaryDirectory()`, cleaned up when the check or compare
  finishes). That scratch space needs *somewhere* writable, which is what the tmpfs is for —
  it is ephemeral, and nothing under it needs to survive a restart, so it is deliberately not
  part of the one data volume.
- **`-v onetrace-console-data:/data`.** The one data volume. This is where
  the store and the rendered pages both live — see "Where the data lives," below.

**Reaching the console.** Without `-p`, the console is reachable only from inside its own
container (which is what running it under `--network none` means). To reach it from the host, add `-p 127.0.0.1:8080:8080` to the run
command above and open `https://127.0.0.1:8080/`. The port mapping is entirely the
operator's choice, made here, not baked into the image. **`--network none` and `-p` cannot be combined** — publishing a port needs a
network to publish it on. Choose one: run isolated and reach it with `docker exec` (a shell
inside the container), or drop `--network none`
and publish the port to `127.0.0.1` only. Publishing to `0.0.0.0` with sign-in on and no
TLS configured is refused outright at start-up (see "Signing in").

**Health.** `GET https://127.0.0.1:8080/health` inside the container returns `200 ok`; the
image's own `HEALTHCHECK` polls it over TLS every 30 seconds. `docker ps` shows `(healthy)`
once it has passed.

## Signing in

Sign-in is on by default. A fresh install has no accounts and no tokens, so it
serves nothing until you create one (see "Creating the first (and every) account,"
above). Three roles:

| Role | Granted by | Can reach |
|---|---|---|
| `viewer` | a signed-in browser session | every rendered page, `POST /compare` |
| `ingester` | a bearer token | `POST /v1/runs`, `POST /v1/decisions` -- nothing else |
| `admin` | (account management; CLI-only in this build) | everything `viewer` can, plus account/token management |

Never mixed: a bearer token never grants `viewer`, and a browser session never
grants `ingester`. `GET /health`,
the sign-in page, and sign-out are the only unauthenticated routes.

**TLS.** With sign-in on, the console either serves HTTPS itself (set both
`sign_in.tls_cert_path` and `sign_in.tls_key_path` to a PEM certificate and key
mounted into the container) or must be bound to loopback behind your own
TLS-terminating reverse proxy. It refuses to start otherwise -- passwords and
session cookies must never cross the network in clear text. TLS 1.0/1.1 are never
negotiated (an explicit `TLSv1_2` floor).

## Using it

With sign-in on (the default), every route below needs a credential: an ingester
token for the two `POST` routes that deliver data, a signed-in browser session (with
its own CSRF token, for `/compare`) for everything else. See "Signing in."

```
# Ingest a run (a tar of MANIFEST.json + its receipts + SHA256SUMS -- the same shape
# tests/conftest.py's `delivery` fixture builds):
curl -H "Authorization: Bearer <token>" --data-binary @run.tar http://127.0.0.1:8080/v1/runs

# Compare two ingested runs, by the run_key each ingest returned -- from a browser,
# signed in, with its own CSRF token. No page carries a compare form: under
# Comparisons, "Choose two runs" lists each pipeline's runs, and run A's page shows
# this request, both keys filled in, for each pair not compared yet.
curl -X POST -b "onetrace_session=<cookie>; onetrace_csrf=<cookie>" \
  -H "X-CSRF-Token: <same value as the onetrace_csrf cookie>" \
  "http://127.0.0.1:8080/compare?a=<run_key>&b=<run_key>"

# Everything rendered is served as plain HTML, to a signed-in session:
curl -b "onetrace_session=<cookie>" http://127.0.0.1:8080/home.html
curl -b "onetrace_session=<cookie>" http://127.0.0.1:8080/incidents.html
```

With `sign_in.enabled` set to `false` explicitly, every route above answers with no
credential at all -- the console logs a warning at every
start-up while this is the case.

The Overview (`home.html`) labels its pipelines P1, P2 … by first arrival. Runs that arrive in
the same second are ordered by run name, and two with the same name by run key, so the order is the
same every time the same runs are loaded.

### Making a delivery

A delivery is one run folder as a tar, with a `SHA256SUMS` inside it that lists every other file
in the folder, once each. Run this from inside the run folder; it writes `SHA256SUMS` there and the
tar beside the folder, as `../run.tar`:

```bash
find . -type f ! -name SHA256SUMS -printf '%P\0' | LC_ALL=C sort -z | xargs -0 sha256sum > SHA256SUMS
find . -type f -printf '%P\0' | LC_ALL=C sort -z | tar --null -T - -cf ../run.tar
```

`sha256sum` writes `<hash> *<path>` (binary mode, Git for Windows' default) or `<hash>  <path>`
(text mode, `--text`); the console reads both, and nothing else. `%P` writes each path relative to
the folder, without the `./` that `sha256sum $(find . -type f)` would put in front of it: a path
written `./receipts/01-a.json` names no file in the tar, so a `SHA256SUMS` written that way is
refused. A path listed twice is refused too, naming both lines.

There is no `curl` inside the image itself (a slim Python base does not ship one); if you are
proving something from inside the container rather than the host, use `python -c
"import urllib.request as u; print(u.urlopen('http://127.0.0.1:8080/...').read())"` the same way.

## Where the data lives

There is no database: no SQLite and no other kind. Everything durable is plain files, written in
binary and never rewritten in place (`store.py`), under one folder, the **store root**
(`store_root`): `/data`, the one mounted volume, in the container; `./store` under the folder it was
started from, in local mode. As `serve.py` lays it out:

| Folder | What it holds |
|---|---|
| `store/` | the store itself |
| `store/objects/` | every received file (receipts, manifest, output files, `SHA256SUMS`) and every check or compare report, each kept once under its own sha256 in `store/objects/<first two hex>/`, never overwritten |
| `store/runs/` | one record per stored run: its folder listing (path to object), its verdict and the report it came from |
| `store/comparisons/` | one record per comparison |
| `store/drift/` | one record per drift report: what `onetrace drift` wrote over a pipeline's runs (`drift.json`, `drift.txt`, kept as objects) and its exit |
| `store/x/` | the explanations, one folder per comparison, `x/<first 16 hex of its key>/`: its full key (`key`), the two runs laid out (`a/`, `b/`), the report `onetrace-explain` reads (`r/`), and each explanation, check and verdict of its record that a person asked for on the comparison's page (local mode) |
| `store/decision_exports/` | one record per decision export, when the decisions extension (configuration key `extensions.onedoor`) is on |
| `pages/` | the rendered HTML, derived from `store/` and redrawn on every start, upload and compare: `pages/runs/<run key>/` for each run's pages, `pages/diff/` for each comparison's, `pages/incidents/` for each incident's own page |
| `access_log/` | the access log: `NNNNNN.jsonl` segments, each entry chained to the one before, and `HEAD.json` |
| `accounts/` | sign-in accounts, in sign-in mode only (local mode refuses to start on a store that holds them) |
| `tokens/` | ingester tokens, in sign-in mode only |

**Path lengths on Windows.** With long paths off, Windows opens a path of 259 characters at most.
The console's own files fit a `store_root` of up to 164 characters, as measured from its deepest,
`pages/runs/<run key>/authorization.html`. An explanation fits a `store_root` of up to 140
characters: on Windows with long paths off, where the folder is longer, the comparison's page says
so and Explain does not run `onetrace-explain`. With long paths on, neither limit applies.

`pages/` is *derived* from `store/` -- deterministically, by this console's own rendering -- but
both are kept in the one volume rather than treating `pages/` as disposable, because losing it would
mean every page re-rendering from a cold start before the console can answer anything.

**Not data, but shipped beside the code:** the console serves IBM Plex Sans and Mono itself,
from `src/onetrace_console/static/fonts/`, at `/static/fonts/<name>` -- no page loads a font from
another host. They come from the npm releases `@ibm/plex-sans` 1.1.0 and `@ibm/plex-mono` 2.5.0,
under the SIL Open Font License 1.1, whose text ships beside them as `static/fonts/OFL.txt`
(`static/fonts/FONTS.md` records each file's sha256).

**What isn't stored:**
- Sign-in sessions are held in memory, and end when the console stops.
- An upload in progress is staged in the system temp folder (`onetrace-staging-*`), and a comparison
  works in one too (`onetrace-compare-*`); both are removed when the request finishes.

### Backing up

Stop the console first, so nothing is half-written (the store's own writes are atomic, see
`store.py`'s `_atomic_write`, so for the container this is optional), then archive the whole store
root. The container:

```
docker run --rm -v onetrace-console-data:/data -v "$PWD":/backup \
  python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f \
  tar czf /backup/onetrace-console-backup.tar.gz -C /data .
```

Local mode, from the folder the console was started in: `tar -czf store-backup.tgz -C store .`

`pages/` need not be backed up -- it can always be redrawn from `store/` -- but taking the whole
store root is simpler than a restore that regenerates one from the other.

### Restoring

With the console stopped, extract the archive into a fresh, empty store root: for the container,
a fresh named volume (`docker run --rm -v <new volume>:/data -v "$PWD":/backup <the same image>
tar xzf /backup/onetrace-console-backup.tar.gz -C /data`); in local mode, an empty `store`
folder (`mkdir store && tar -xzf store-backup.tgz -C store`). Then start the console against it.

### Resetting to empty

Stop the console and delete the store root -- in local mode the `store` folder; for the container,
remove the container, then `docker volume rm onetrace-console-data`. The next start makes a new,
empty store, and Home reads 0 runs stored. This also deletes accounts, tokens and the access log.

### What re-rendering costs

Every ingest, every comparison and every start-up re-renders the lists and the Overview, and
the Overview reads every stored run's receipts each time. Nothing is cached between renders,
so that work grows with the number of runs the store holds. It has not been measured at a large store, so plan for an ingest to
take longer as the store grows.

## Nothing leaves the container

No telemetry, no update check, no call to anything outside the container at runtime. Every
subprocess this console starts (the verifier, the SDK's own `diff`/`localize` verbs) runs
locally against files already on disk; none of them opens a network connection, and
`--network none` above is the proof that nothing could even if something tried to.

