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

## Deploy

From the repository root, signed in to Fly.io with `fly auth login`:

```
fly apps create <app-name>
fly deploy --config deploy/fly/fly.toml --dockerfile deploy/fly/Dockerfile -a <app-name>
```

A custom domain is added with `fly certs add <your-domain> -a <app-name>`, plus the DNS record
Fly.io names. To keep one machine always on, change the two lines `fly.toml` marks.
