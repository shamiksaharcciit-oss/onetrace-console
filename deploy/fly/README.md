# The hosted read-only demo

A live onetrace-console that anyone can open and nobody can change. It serves the demo store's
runs and their comparisons, recorded when the image is built, with a banner on every page. Every
write is refused before its body is read, and the access log goes to the machine's output.

The files here:

- `Dockerfile`: the image, built from the repository root.
- `public.json`: the console's configuration inside the image (`"public": true`, port 8080).
- `fly.toml`: the Fly.io service: port 8080, HTTPS only, the `/health` check, and machines that
  stop when idle.

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
