# The hosted read-only demo

A live onetrace-console that anyone can open and nobody can change. It serves the demo store's
runs and their comparisons, recorded when the image is built, with a banner on every page. Every
write is refused before its body is read, and the access log goes to the machine's output. The one
thing it does on request is Compare: two runs of one pipeline, compared on the machine and kept in
`/srv/onetrace-demo-compared`, within the bounds `public.json` names (each can be lowered there, not
raised).

The files here:

- `Dockerfile`: the image, built from the repository root.
- `public.json`: the console's configuration inside the image (`"public": true`, port 8080, Compare's
  cache folder and bounds, and `Fly-Client-IP` as the header that names a visitor's address).
- `fly.toml`: the Fly.io service: port 8080, HTTPS only, the `/health` check, and machines that
  stop when idle.
- `postdeploy_080.ps1`: the demo's checks after a deploy, read-only.
- `captures/`: the capture store's own app (below): its `fly.toml` and its checks after a deploy.

Nothing here names an app, a region, an organisation, a token or a domain. Those are set by
whoever deploys, on their own machine.

## Try it locally

```
docker build -f deploy/fly/Dockerfile -t onetrace-console-demo .
docker run --rm -p 127.0.0.1:8080:8080 onetrace-console-demo
```

Then open http://127.0.0.1:8080/. Without Docker, `onetrace-console demo --public` serves the
same read-only demo from a temporary folder.

## Kept explanations

A public console presses nothing, so it asks onetrace-explain for nothing. It shows the explanations
its build kept, read-only, on each comparison's page: each with its label, its model, its claims with
their cites, and the claims dropped with the reason, and no button. An explanation belongs to the two
runs it explains, byte for byte, and each build records the demo's runs anew, so it is kept in two
builds:

1. `onetrace-console demo --public --build <first>` records the runs.
2. On a local console of those runs (`onetrace-console <first>/runs --trust <first>/trust.json
   --compare A B`), Explain is pressed with your own model. The command writes its records in the
   store's `x/<16 hex>/r/explain/`.
3. `onetrace-console demo --public --build <second> --runs-from <first> --explanations <that r folder>`
   takes the first build's runs, where its build record vouches for every byte, and keeps each
   explanation whose record verifies and whose two runs are a comparison this build holds. Every other
   file is refused, with its reason printed, and never shown. The build record vouches for each one
   kept.

Without `--explanations`, each comparison's page says "Explanations are not set up on this demo."

The Dockerfile here uses `kept/` where it is there: its build line is step 3, with `--runs-from
/app/deploy/fly/kept --explanations /app/deploy/fly/kept`, so the image serves `kept/runs/` and the
four explanations under `kept/explain/`, and every other comparison's page says they are not set
up. Its build record is `kept/BUILD_RECORD.json`, over `kept/runs/` and `kept/trust.json` only; the
record the first build wrote is beside it, unchanged (`kept/README.md`). Where `kept/` is not there,
the Dockerfile builds as before: the runs recorded at build time and no explanation kept.

## Deploy

From the repository root, signed in to Fly.io with `fly auth login`:

```
fly apps create <app-name>
fly deploy --config deploy/fly/fly.toml --dockerfile deploy/fly/Dockerfile -a <app-name>
```

A custom domain is added with `fly certs add <your-domain> -a <app-name>`, plus the DNS record
Fly.io names. To keep one machine always on, change the two lines `fly.toml` marks.

The machine's size is yours to choose when you deploy. One comparison measured a peak of about
71 MB for the console and the commands it runs, and two run at once at most.

## The capture store's app

The capture store (P10's runs whose model calls are captured at L3 and L2, example data) is served by
a second app, beside the demo: the same image, built with the capture store in place of the demo
(`deploy/fly/captures/fly.toml` sets the build argument `ONETRACE_DEMO_STORE = "captures"`), served
read-only as the demo is, its build record checked at start. Its name and its domain are yours, as
the demo's are: nothing here names them.

The two apps link to each other, read-only, by an address each is given at deploy: the demo's
comparisons page has the line "Token-level examples (L2 and L3): <the capture store's address>"
(`ONETRACE_CONSOLE_CAPTURES_URL`), and the capture store's Overview one line back to the demo
(`ONETRACE_CONSOLE_DEMO_URL`). Without its address, an app draws no line.

Search engines are asked to index each app's Overview only: every other page it serves carries
`noindex`, and `/robots.txt` lets them crawl so they can read it. A run page's address changes with
each new build, so an old one answers 404 and drops out of search; nothing is redirected. Given its
own address (`ONETRACE_CONSOLE_PUBLIC_URL`), an app's Overview names it as its canonical address;
without it, no canonical is drawn.

Deploy the capture store's app first, then the demo, so the demo's line answers once it is drawn.
From the repository root:

```
fly apps create <captures-app-name>
fly deploy --config deploy/fly/captures/fly.toml --dockerfile deploy/fly/Dockerfile -a <captures-app-name> --env ONETRACE_CONSOLE_DEMO_URL=https://<the demo's address> --env ONETRACE_CONSOLE_PUBLIC_URL=https://<the capture store's address>
.\deploy\fly\captures\postdeploy_080_captures.ps1 -Base https://<the capture store's address> -Demo https://<the demo's address>
fly deploy --config deploy/fly/fly.toml --dockerfile deploy/fly/Dockerfile -a <app-name> --env ONETRACE_CONSOLE_CAPTURES_URL=https://<the capture store's address> --env ONETRACE_CONSOLE_PUBLIC_URL=https://<the demo's address>
fly ssh sftp get /srv/onetrace-demo/BUILD_RECORD.json .\BUILD_RECORD.json -a <app-name>
.\deploy\fly\postdeploy_080.ps1 -Base https://<the demo's address> -BuildRecord .\BUILD_RECORD.json -SiteLinks .\deploy\fly\site_links.txt -Captures https://<the capture store's address>
```

The demo's checks read their counts (its comparisons, its kept explanations, its closed and not closed runs) from
the build record of the build deployed, copied out of the app as above; none is written in the script.

Its custom domain is added as the demo's is, with `fly certs add <its domain> -a <captures-app-name>`
and the DNS record Fly.io names.
