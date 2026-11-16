# Running the console: an operator's guide

This is the console as a container you run for a team. No shared back end, no account with
anyone, no data that leaves the machine it runs on.

## What this is not (read this before the rest)

- **One organisation per install.** One running container is one installation, full stop. It
  has people, from its own accounts (local sign-in) or from one Microsoft Entra ID tenant
  (`sign_in.oidc.tenant_id`), and with Entra ID three console roles (`viewer`, `investigator`,
  `admin`); it has no teams and no tenants beyond that one, so every person signed in sees every
  run. This is not a setting you turn on; it is what the code does not yet have. (There is
  exactly one configuration FILE, below.)
- **Sign-in is on by default, and a fresh install serves nothing until you
  create an account.** Local mode, with no configuration file named, has no sign-in: see
  "Local mode" below. `admin create` inside the container, then TLS (an operator-supplied
  certificate, below) or a loopback listener behind your own TLS-terminating proxy, is
  required before this console will serve a single page. See "Signing in," below.
  - **Never expose it directly to the internet without TLS.** Passwords and session
    cookies must never cross the network in clear text; the console refuses to start
    a non-loopback, plain-HTTP listener with sign-in on.
- **Signatures and anchors are checked as `onetrace-verify` 0.8.0 checks them.** A valid signature
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

## Neighbours by input: an optional extra, local only

`onetrace-console[neighbours]` adds neighbours by input to a **local** console: other runs of the same
configuration whose kept inputs are near a run's own, and, on a comparison of two such runs, a nearness
ladder beside the exact one. An embedding model reads the runs' kept inputs and kept outputs to do it;
each embedding batch is recorded as a onetrace run of its own.

Install it beside the console's own pins:

```
python tools/install_pinned.py
python -m pip install --require-hashes -r requirements-neighbours.lock
```

- **Local only.** A public console has none of it: no page, no route and no word of it, and it refuses to
  start beside a store that holds neighbours' files. The container image installs no extra.
- **Off by default.** Installed and off, every page is drawn exactly as without the extra. It is turned on
  at `/neighbours/setup` on the console, by naming the embedder and confirming the words that name it;
  turning it on and off is an admin's where sign-in is on.
- **What turning it on fetches.** With one of the two local models, that model's pinned files, once, from
  huggingface.co at the pinned revision, each checked against its pinned sha256 before it is kept. Nothing else
  is fetched, and no text leaves the machine. With an embedding endpoint you name instead, the kept inputs and
  outputs are sent to that endpoint, and nothing is fetched.
- **What the ladder's two fixed readings mean.** "1.00 by the record": the two runs' digests for that file are
  equal, so nothing is embedded there. "≥ 0.9995, digests differ": the digests are not equal and the
  embedder's number rounds to 1.000. Neither is a judgement that two runs did the same thing.

What it is not, word for word as the setup page says it:

- Similarity of inputs is a suggestion for which runs to compare, and a drop in the nearness ladder is a suggestion of where to look; neither is evidence of anything and neither is a verdict.
- The embedder reads kept inputs; the console says so, and the feature is off by default.
- Nothing about hosted embedders: none is offered.
- No fitted threshold: the similarity is shown as a number, ordered, with no cut-off claimed to mean "the same".

The setup page, `/neighbours/setup`, names the models, their pinned revisions and what is fetched.

## Building the image

```
docker build -t onetrace-console .
```

The base image is pinned by digest (`python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`),
and `onetrace` and `onetrace-verify` are installed with
`pip install --require-hashes` — see `requirements.lock`. The only network
access this build performs is fetching the eight packages `requirements.lock` pins from PyPI
(`onetrace`, `onetrace-verify`, the five its `[crypto]` extra needs, and `pyjwt`), each hash-checked; a
byte that does not match the pin fails the build outright. **At runtime the console reaches
the network only for what you turn on:** sign-in through Microsoft Entra ID (its discovery
document, signing keys and token endpoint, "Signing in through Microsoft Entra ID," below);
neighbours, when you turn them on (the embedder's files from huggingface.co, each checked
against its pinned sha256, and an embedding endpoint you name); and Explain, whose
`onetrace-explain` sends a packet to the model you name when you press Send. With none of them
on, nothing at runtime reaches the network — see "No shared back end," below, and its proof.

## Configuration

**One file, mounted read-only. Its path is the environment variable this console reads for
its configuration, `ONETRACE_CONSOLE_CONFIG`**. The others it reads: the variable
`sign_in.oidc.client_secret_env` names, which holds Entra ID's client secret; `https_proxy` and
`no_proxy`, for Entra ID's addresses; `ONETRACE_EXPLAIN_CONFIG`, where onetrace-explain's own
configuration is (and whether the variable that configuration names for its key is set, never its
value); `ONETRACE_CONSOLE_INSTALL_REPORT`, where a pinned install's report is; and, for the hosted
demo and the capture store's apps only, `ONETRACE_CONSOLE_DEMO_URL` and
`ONETRACE_CONSOLE_CAPTURES_URL`; and, while the demo records its runs, `TRACEPARENT` and
`ONETRACE_RUN_ID`, as onetrace's own recorder does. A process the console starts gets its environment. The image ships a default at
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
  "extensions": {
    "onedoor": false
  },
  "max_decision_rows": 100000,
  "max_decision_line_length": 262144,
  "access_log_max_segment_bytes": 5242880,
  "sign_in": {
    "enabled": true,
    "tls_cert_path": "",
    "tls_key_path": "",
    "session_idle_timeout_seconds": 1800,
    "session_absolute_timeout_seconds": 43200,
    "max_sessions_per_account": 3,
    "rate_limit_max_attempts_per_client": 20,
    "rate_limit_window_seconds": 300,
    "rate_limit_max_attempts_per_device": 5,
    "rate_limit_max_attempts_per_pair": 5,
    "rate_limit_pair_window_seconds": 900,
    "rate_limit_max_attempts_per_account": 100,
    "rate_limit_account_window_seconds": 3600,
    "rate_limit_max_concurrent_hashes": 2,
    "insecure_cookie_for_local_dev": false,
    "public_url": "",
    "trusted_proxies": [],
    "method": "local",
    "oidc": {
      "tenant_id": "",
      "client_id": "",
      "client_certificate": "",
      "client_secret_env": "",
      "session_max_hours": 8
    }
  },
  "trust_file": null,
  "tsa_cert": null,
  "tsa_roots": [],
  "public": false,
  "compare_cache": null,
  "compare_client_header": null,
  "compare_per_minute": 20,
  "compare_running": 2,
  "compare_queue": 2,
  "compare_wait_seconds": 20.0,
  "compare_verb_seconds": 30,
  "tracing": {},
  "tokenizers": [],
  "close_call_margin": 1.0
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
| `sign_in.enabled` | **on by default.** Every route except those that need no principal ("Signing in," below) requires a principal: a browser session (`viewer`) or a bearer token (`ingester`, see "Ingester tokens," below). Turning it off is an explicit choice a config file must make, and the console logs a warning at every start-up while it is off. Local mode has none. |
| `trust_file` | a path to an `onetrace-trust/0.1` file listing the signing keys you trust; absent by default. Set, every check runs the verifier with `--trust` and that file; absent, a valid signature reads "Signed, key not trusted". A file the verifier can't read is shown as its own FAIL row. |
| `tokenizers` | a local console's tokenizers, for showing a model step's token as text: a list of `{"folder": "<path>", "files": ["tokenizer.json", ...]}`, each a folder you name and the files in it that make the tokenizer; a relative folder is read from this file's folder. Empty by default. A step's token ids are decoded only where the named files, hashed as named, give the record's `tokenizer.digest` exactly; named files that hash to another digest are refused. The console never downloads a tokenizer, and a public console reads none. |
| `public` | `false` by default. `true` makes a read-only public demo: every write is refused before its body is read, the pages are served as they were built and never drawn again, and every page carries a banner. It refuses to start beside sign-in, the decisions extension (configuration key `extensions.onedoor`), a trust file other than the demo's, or a store holding accounts or tokens. Its store is built with `onetrace-console demo --public --build <folder>`; `deploy/fly/` serves one. |
| `sign_in.tls_cert_path`, `sign_in.tls_key_path` | a PEM certificate and key. **Required together if `host` is not loopback** -- the console refuses to start otherwise, rather than serve sign-in over plain HTTP on a non-loopback listener |
| `sign_in.session_idle_timeout_seconds`, `sign_in.session_absolute_timeout_seconds` | a signed-in session expires after this much inactivity, or this long regardless of activity, whichever comes first (defaults: 30 minutes, 12 hours) |
| `sign_in.max_sessions_per_account` | default `3`: an account's live sessions at most. A sign-in beyond it ends that account's oldest session, whose cookie then gets the sign-in page. At least 1. |
| `sign_in.rate_limit_max_attempts_per_client`, `sign_in.rate_limit_window_seconds` | default 20 in 300 s: sign-in attempts from one client address, across accounts, over a rolling window |
| `sign_in.rate_limit_max_attempts_per_device`, `sign_in.rate_limit_max_attempts_per_pair`, `sign_in.rate_limit_pair_window_seconds` | default 5, 5, 900 s: for an account, an attempt from a browser it signed in from before (its device cookie) counts only in that browser's window; any other counts in its (account, address) pair's window. See "Sign-in lock-out," below. |
| `sign_in.rate_limit_max_attempts_per_account`, `sign_in.rate_limit_account_window_seconds` | default 100 in 3600 s: the account's ceiling, over all addresses, for attempts from browsers it has not signed in from before. `onetrace-console admin unlock <account>` clears it. |
| `sign_in.rate_limit_max_concurrent_hashes` | a global cap (default 2) on how many password checks may be hashing (scrypt, 128 MiB each) at the same time, independent of which account or client is asking -- a request that cannot get a slot gets `503`, never queued |
| `sign_in.public_url` | default empty: the origin your browser opens this console at, as `https://host` or `https://host:port`, where that is not the request's own scheme and `Host` -- behind your own TLS-terminating proxy. With sign-in on, a signed-in write whose `Origin` (or else `Referer`) names any other origin is refused with `403`. Anything but an origin is refused at start. |
| `sign_in.trusted_proxies` | default empty: the proxies in front of this console, as addresses and CIDR ranges (`["127.0.0.1"]`, `["10.0.0.0/8"]`). Only where a request comes from one of them, the sign-in limit's client address is the rightmost `X-Forwarded-For` entry that is not one of them; otherwise it is the connection's own address. Empty, the header is never read. |
| `sign_in.method` | default `local`: how people sign in, one method at a time. `local` is the console's own accounts; `oidc` is Microsoft Entra ID (`sign_in.oidc`), which turns local sign-in off. Switching back is done on the machine: edit this file and restart; `onetrace-console admin` stays the way in. A public console refuses `oidc` at start. See "Sign-in through Microsoft Entra ID". |
| `sign_in.oidc` | read where `sign_in.method` is `oidc`: `tenant_id` and `client_id` (GUIDs, from the app registration; the issuer is derived from the tenant id, never `common` or `organizations`), exactly one client credential, `client_certificate` (a PEM file holding the certificate and its private key, preferred) or `client_secret_env` (the name of the environment variable holding the secret, never the secret itself), and `session_max_hours` (default 8). The redirect URI is `sign_in.public_url` + `/signin/oidc/callback`. |
| `sign_in.insecure_cookie_for_local_dev` | **default `false`, and the only way to get a non-`Secure` session cookie.** Refused outright unless `host` is loopback -- it exists solely for a loopback listener sitting behind your own local, HTTPS-terminating proxy. Logged loudly at start-up when set. |
| `extensions` | default `{"onedoor": false}`: the extensions this console switches on, each a plain true or false. `onedoor` takes decision exports at `POST /v1/decisions`. An unknown name is refused, never read as off. |
| `max_decision_rows`, `max_decision_line_length` | defaults 100000 and 262144: a decision export (`POST /v1/decisions`, with `extensions.onedoor` on) holding more rows, or a longer line, is refused |
| `tsa_cert`, `tsa_roots` | absent by default: the RFC 3161 time-stamp authority you trust, its certificate and the root or roots it chains to (PEM or DER files). Set, every check runs the verifier with them, so a run's RFC 3161 anchor can read Yes; absent, it reads "Couldn't check". |
| `compare_cache`, `compare_client_header` | a public console's Compare: the folder its comparisons are kept in (default: `compared` under the store root), and the request header naming the client's address where a proxy in front of the console sets one (on Fly.io, `Fly-Client-IP`; default: the connection's own address) |
| `compare_per_minute`, `compare_running`, `compare_queue`, `compare_wait_seconds`, `compare_verb_seconds` | a public console's Compare bounds, each at most its default (20, 2, 2, 20.0, 30) so every page's "at most" stays true: new comparisons started a minute for the whole console, comparisons running at once, comparisons waiting per address, how long one waits in seconds, and each verb's time in seconds |
| `close_call_margin` | default 1.0, in nats, above zero: on a model step whose capture holds candidates with log-probabilities (onetrace's hosted form), a position whose chosen token leads the runner-up by at most this much is flagged as a close call, with the first such position and a count. A close call is not an error, and a wide margin is not correctness. |
| `tracing` | empty by default: a local console's link to your own tracing tool, `{"link": "<http(s) address with {trace_id} and, optionally, {span_id}>"}`. Each recorded trace id becomes "Open in your tracing tool"; the console builds the link and never calls it. A public console shows none. |

**Creating the first (and every) account.** There is no web sign-up page — "whoever
reaches the first-run page first becomes admin" is a takeover race, not a feature. **A
fresh install serves no pages at all until this has been run once.** Create an account
from inside the container:

```
docker exec -i <container> onetrace-console admin create alice
```

To sign an account out everywhere (a lost laptop, a shared browser), end all of its sessions:

```
docker exec <container> onetrace-console admin sessions end alice
```

Each of its cookies gets the sign-in page at its next request; a sign-in afterwards works as before.

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
over HTTPS. Set `sign_in.public_url` to the address your browser opens (for example
`"public_url": "https://console.example.com"` under `sign_in`): the console sees the proxy's plain-HTTP
request, and refuses a signed-in write from any origin but that one.
Set `sign_in.trusted_proxies` to `["127.0.0.1"]` too, and have the proxy append the client's
address to `X-Forwarded-For` (in nginx, `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;`):
the console then counts sign-in attempts per client, not all as the proxy's one address.

Every flag here is load-bearing, not decoration:

- **`--network none`.** With neither Entra ID sign-in, neighbours nor Explain on, this console
  needs no network at runtime — it checks stored
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
grants `ingester`. **The routes that need no principal:** `GET /health`, `GET /signin` and `POST /signout`; with local sign-in `POST /signin`; with Entra ID `GET /signin/oidc/start` and `GET /signin/oidc/callback`; and the console's static files under `/static/` (its stylesheet, fonts and icon), which hold no data.

These are the roles with the console's own accounts (`sign_in.method` `local`). With sign-in through
Microsoft Entra ID, the role comes from Entra's app roles: see "Sign-in through Microsoft Entra ID" below.

**TLS.** With sign-in on, the console either serves HTTPS itself (set both
`sign_in.tls_cert_path` and `sign_in.tls_key_path` to a PEM certificate and key
mounted into the container) or must be bound to loopback behind your own
TLS-terminating reverse proxy. It refuses to start otherwise -- passwords and
session cookies must never cross the network in clear text. TLS 1.0/1.1 are never
negotiated (an explicit `TLSv1_2` floor).

**Sign-in lock-out.** A stranger guessing an account's password can't keep its owner out of the
browsers the owner already uses:
- A right password sets a device cookie (`onetrace_device`, `HttpOnly`, `SameSite=Strict`, `Secure`,
  90 days): the account, a random id, and a tag under the device key. It grants nothing on its own;
  only the sign-in limit reads it.
- An attempt with a valid device cookie for the account it names counts only in that browser's window
  (5 wrong in 900 s). Strangers' guesses never touch it.
- Any other attempt counts in its (account, address) pair's window (5 in 900 s) and in the account's
  ceiling over all addresses (100 in 3600 s). A right password resets the pair and the browser's window,
  never the ceiling. A refused attempt never reaches the password check.

While guessing holds an account at its ceiling, a browser it has not signed in from (a new laptop,
cleared cookies) gets `429`: "too many sign-in attempts for this account from new browsers; sign in from
a browser you have used before, or ask an admin". The words and status are the same for a name with no
account. To let new browsers try again, in a running console too:

```
docker exec <container> onetrace-console admin unlock <account>
```

The windows are kept in memory, so a restart clears them.

**The device key** is `accounts/.device_key` in the store, made at first start (mode 0600); back it up
with the accounts. Rotate it when a backup holding it is lost or it may have leaked:

```
docker exec <container> onetrace-console admin device-key rotate
```

Every device cookie then ends, in a running console too, and each browser signs in as a new one. A lost
key does the same: no cookie is valid, and every attempt counts as a new browser's.

## Sign-in through Microsoft Entra ID

With `sign_in.method` `oidc`, people sign in with their organisation's Microsoft account, and the role
each has in the console comes from the app roles your Entra ID administrator assigns. Local sign-in is
off: the sign-in page has one button, Sign in with Microsoft. `onetrace-console admin` on the machine
stays the way in; to go back to the console's own accounts, set `sign_in.method` to `local` in the
configuration file and restart (the console never writes its configuration, and no page changes it). A
public console refuses `oidc` at start.

### The app registration

In the Microsoft Entra admin center, under **App registrations**, **New registration**:

1. **One tenant.** Supported account types: *Accounts in this organizational directory only* (single
   tenant). The console derives its issuer from your tenant id alone,
   `https://login.microsoftonline.com/<tenant id>/v2.0`, and refuses `common`, `organizations` and
   `consumers`.
2. **The redirect URI.** Platform *Web*: `<sign_in.public_url>/signin/oidc/callback`, for example
   `https://onetrace.example.org/signin/oidc/callback`. `sign_in.public_url` is the origin your
   browser opens the console at; the console needs it set for `oidc`.
3. **The three app roles**, under **App roles** (or `appRoles` in the manifest), each allowed for
   *Users/Groups*, with these values exactly:

   ```json
   "appRoles": [
     {"allowedMemberTypes": ["User"], "displayName": "onetrace viewer", "value": "onetrace.viewer",
      "description": "Reads runs and comparisons.", "isEnabled": true, "id": "<a new GUID>"},
     {"allowedMemberTypes": ["User"], "displayName": "onetrace investigator", "value": "onetrace.investigator",
      "description": "Also starts comparisons, Explain and checks.", "isEnabled": true, "id": "<a new GUID>"},
     {"allowedMemberTypes": ["User"], "displayName": "onetrace admin", "value": "onetrace.admin",
      "description": "Also changes the console's settings.", "isEnabled": true, "id": "<a new GUID>"}
   ]
   ```

   Entra puts the roles assigned to the person in the ID token's `roles` claim; the console reads that
   claim alone, never a group, a scope or a directory role.
4. **Assigning groups to roles.** Under **Enterprise applications**, the app, **Users and groups**, **Add
   user/group**: pick a group and one role, and repeat for each group. Where a person is in groups with
   different roles, the highest takes effect. Set **Assignment required?** to *Yes* under **Properties**
   so that Entra itself signs no one in without a role; the console refuses them either way, with "Your
   organisation hasn't given you a role in onetrace. Ask your administrator."
5. **A certificate credential** (preferred). Make a key and a certificate on the console's machine:

   ```
   openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=onetrace-console" \
     -keyout entra.key -out entra.crt
   cat entra.crt entra.key > /etc/onetrace-console/entra.pem && chmod 600 /etc/onetrace-console/entra.pem
   ```

   Upload `entra.crt` (the certificate alone) under **Certificates & secrets**, **Certificates**, and name
   the PEM holding both in `sign_in.oidc.client_certificate`. The console signs a client assertion with
   the key (private_key_jwt) and sends no secret. A client secret works instead: put it in an environment
   variable and name the variable in `sign_in.oidc.client_secret_env`, never the secret itself.

### The configuration

```json
"sign_in": {
  "enabled": true,
  "method": "oidc",
  "public_url": "https://onetrace.example.org",
  "oidc": {
    "tenant_id": "<directory (tenant) id>",
    "client_id": "<application (client) id>",
    "client_certificate": "/etc/onetrace-console/entra.pem",
    "session_max_hours": 8
  }
}
```

The ids are on the registration's **Overview**. The credential is read at start, before anything is
drawn: a file or a variable it can't use is refused by name, and no message, log line or page ever holds
the key, the secret, a code or a token. A session ends at the ID token's expiry, `session_max_hours` or 30 minutes idle
(`sign_in.session_idle_timeout_seconds`), whichever comes first; Sign out, in the settings menu, ends it and offers
Microsoft's own sign-out.

**What the console calls.** Only `login.microsoftonline.com`, for your tenant: the discovery document,
the signing keys and the token endpoint, each with a 10-second limit, through `https_proxy` and
`no_proxy` where they are set. Allow outbound HTTPS to it from the container.

### What each role may do

| Role | Can reach |
|---|---|
| `viewer` (`onetrace.viewer`) | every page of runs and comparisons |
| `investigator` (`onetrace.investigator`) | everything a viewer can, and starting work: Compare and a text diff's Show more, Explain's presses, Mark as benchmark, a check against an expectations file, the tokenizer upload, Load as not closed, the bisect form |
| `admin` (`onetrace.admin`) | everything an investigator can, and the settings: Set up Explain and its Save, the neighbours setup and Turn on or off, a tokenizer's Remove |

The delivery routes (`POST /v1/runs`, `POST /v1/decisions`) take an ingester's bearer token and refuse
every session, as before. Every route declares the role it needs; one with none is refused.

### What this does not claim

- **The console trusts Entra for who someone is.** It checks the ID token's signature against your
  tenant's published keys and its claims (issuer, audience, tenant, times, nonce); who the person is,
  and whether they should have the role, is Entra's word.
- **A role removed in Entra takes effect at the next sign-in**, so within `session_max_hours` at most,
  until the console reads changes as they happen (SCIM, not in this release).
- **Entra's audit log is the record of sign-ins.** The console's access log names each request's account
  (its tenant id and object id); it is not an audit of sign-ins.
- **Every role reads every run.** Scoping runs to teams is not in this release.

## Using it

With sign-in on (the default), every route below needs a credential: an ingester
token for the two `POST` routes that deliver data, a signed-in browser session (with
its own CSRF token, for `/compare`) for everything else. See "Signing in."

```
# Ingest a run (a tar of MANIFEST.json + its receipts + SHA256SUMS -- the same shape
# tests/conftest.py's `delivery` fixture builds):
curl -H "Authorization: Bearer <token>" --data-binary @run.tar http://127.0.0.1:8080/v1/runs

# Compare two ingested runs, by the run_key each ingest returned -- from a browser,
# signed in, with its own CSRF token. Under Comparisons, "Choose two runs" lists each
# pipeline's runs; on run A's page each pair not compared yet has a Compare button, which
# sends this request with the session's CSRF token and opens the comparison, and beside it
# the request itself, both keys filled in, to send by hand as below. No form posts it.
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
| `store/beside/` | what was kept beside a run, one record per run that has any: the decision export (`decisions.jsonl`, with its `.sha256`) and the permit issuers (`permit-issuers.json`) found beside its folder, and its trace (OTLP/JSON: `traces/<run folder>.json` given beside it, or `onetrace export otel` of the run), each kept as an object |
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
so and Explain does not run `onetrace-explain`. With long paths on, the console's own files have no
such limit, but an explanation still needs a `store_root` of 195 characters or fewer: Windows starts
no program in a working folder of more than 258 characters, long paths on or off, and Explain starts
the verifier in a folder 63 characters below `store_root`.

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

The store root holds `accounts/`, with the device key (`accounts/.device_key`): back up the whole
root, and keep the archive as you keep the accounts.

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

No telemetry, no update check, no call to anything outside the container at runtime, but one you
configure: with sign-in through Microsoft Entra ID, the calls to your tenant's sign-in endpoints that
"Sign-in through Microsoft Entra ID" lists. Every
subprocess this console starts (the verifier, the SDK's own `diff`/`localize` verbs) runs
locally against files already on disk; none of them opens a network connection, and
`--network none` above is the proof that nothing could even if something tried to.
A console that signs people in through Entra ID needs those calls, so it can't run with `--network none`.

The image includes neither onetrace-explain nor the `[neighbours]` extra: both Dockerfiles
install `requirements.lock` alone, which pins neither. So Explain and neighbours by input, the
console's three network calls you choose, are not in the image.

