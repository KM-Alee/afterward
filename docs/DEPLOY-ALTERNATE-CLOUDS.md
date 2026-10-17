# Deploying Afterward on Alternate Clouds

Researched 17 Oct 2026 ~10:30 PKT. Everything below marked (verified) comes from `acc 1.10.0 --help` or read-only
`acc` list commands. Public docs (docs.alternatefutures.ai) were only reachable as an index page, so
runtime behaviour (WebSocket, health checks, instance limits) is **unverified** and must be proven by the smoke test.
No cloud resource was created and no secret was set while writing this.

## State found (read-only)

- CLI: `acc` 1.10.0 (npm `@alternatefutures/acc`), logged in as the operator, active project `afterward`.
- Service `afterward-db`: type DATABASE, template `postgres` (PostgreSQL 17 Alpine), **stopped**.
  Hostnames `afterward-db-app.alternatefutures.ai`. Its env holds PGDATA/POSTGRES_DB/POSTGRES_USER/POSTGRES_PASSWORD.
- No app service, no deployments. Credits: $4.99. Regions: us-east, us-west, eu, asia (all available).
  Pricing per region shows no median yet; real cost is only visible after deploy via `acc billing usage`.

## Architecture

```
Telegram / browser / Google --HTTPS--> [afterward app service, 1 instance, port 8000]
                                              |  DATABASE_URL (internal link)
                                              v
                                      [afterward-db  postgres 17]
```

One app container runs web, `/ws/calls/{token}` WebSocket, and the in-process job worker (`supervise` in
`app/main.py` lifespan). It must be exactly one instance: a second one would run a second job runner and
double-send. `acc services deploy` has no replica flag and a service has one active deployment, so one
instance is the default (verified by absence of any scale option). Never click "deploy" on a second
service pointing at the same DB. Do not split a worker service: the code has no separate worker entrypoint.

## Two ways to create the app service

A. Docker image from GHCR (recommended; no build on the platform). `.github/workflows/build.yml` publishes the
   image; make the GHCR package public (needed, the platform pulls it anonymously):
   `acc services create --kind docker --name afterward-app --image ghcr.io/<owner>/<repo>:<tag> --port 8000`
B. GitHub build (what START-HERE.md describes): needs the GitHub App installed in the dashboard.
   `acc services create --kind github --name afterward-app --repo <owner>/<repo> --branch main --github-installation <id> --env PORT=8000`
   (`--port` is documented only for `--kind docker`; for github set the port in the dashboard.)

Pin to a tag or SHA, not `latest`, so rollback is possible.

## Commands, in order

Run from the repo; every secret goes through a pipe or the dashboard, never an argument or chat.

```
acc whoami && acc billing balance
acc services deploy afterward-db --region eu -y         # start DB; use the region you pick for the app too
acc services create --kind docker --name afterward-app --image ghcr.io/<owner>/<repo>:<tag> --port 8000 --region eu --spend budget --budget-total 4
acc services link afterward-app afterward-db --alias DB  # prints/exposes connection info as env on the app
acc services env list afterward-app                      # LOOK AT THE NAMES (not values) to see how the link exposed the DB URL
```

`DATABASE_URL`: the app reads that one name and accepts `postgres://`, `postgresql://` or `postgresql+psycopg://`.
If the link exposes differently-named variables (DB_*), set `DATABASE_URL` in the dashboard from them (UNVERIFIED which names appear).
Check whether the DB needs `?sslmode=` (UNVERIFIED).

Non-secret variables (safe on the command line):

```
for kv in APP_ENV=production TELEGRAM_MODE=webhook AGENTS_TRACING=false PHONE_CALLS_ENABLED=false PORT=8000; do
  acc services env set afterward-app "${kv%%=*}" "${kv#*=}"; done
# plus LLM_FAST_MODEL LLM_ACCURATE_MODEL STT_MODEL TTS_MODEL REALTIME_MODEL FAMILY_MAILBOX PROVIDERS_MAILBOX (model/mailbox names, not secrets)
```

Secrets (type in the dashboard, or pipe from a private source; `acc env set` puts the value in shell history, so use the dashboard):
`OPENAI_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET
GOOGLE_REFRESH_TOKEN_FAMILY GOOGLE_REFRESH_TOKEN_PROVIDERS VAULT_KEY DEMO_PASSCODE`.
`acc secrets set <name> --stdin` ("Store a runtime secret for this project", verified) exists but whether it is injected
into a service as an env var is UNVERIFIED; the dashboard env editor is the known path. The full name list is in
`deploy/alternate-clouds.env.names`. Leave WHATSAPP_*, TWILIO_*, FASTN_* empty. VAULT_KEY must be the same value forever.

```
acc services deploy afterward-app -y
acc services info afterward-app     # note the public URL
acc services logs afterward-app --tail 100
```

Then set `PUBLIC_BASE_URL=<that https URL>` (dashboard), redeploy, and:

1. `curl <url>/health` then `<url>/status` (db_reachable true). `init_db` runs at boot, so migrations need no step.
2. Telegram: `setWebhook` with `url=<PUBLIC_BASE_URL>/webhooks/telegram` and the `secret_token` equal to TELEGRAM_WEBHOOK_SECRET, from a private shell.
3. Google: nothing to register for the baseline. The refresh tokens are already minted; `/connect/gmail/callback` only matters if
   you re-run consent through the deployed app, in which case add `<PUBLIC_BASE_URL>/connect/gmail/callback` as an authorized redirect URI on the Web client.
4. Open the call room link and confirm the WebSocket upgrade works (UNVERIFIED on this platform; if the proxy refuses `wss://`,
   ask the hackathon staff, there is no CLI switch).

## Health check, logs, rollback, cost

- Health: the Dockerfile now has a `HEALTHCHECK` on `/health`. `acc` shows no health-path option; the platform probe is UNVERIFIED.
- Logs: `acc services logs afterward-app --tail N`; deployment history: `acc deployments list --service afterward-app --all`; shell: `acc ssh afterward-app`.
- Rollback: `acc services deploy afterward-app --image ghcr.io/<owner>/<repo>:<previous-tag> -y` (the `--image` flag switches a docker service, verified).
  `acc services close afterward-app` stops it.
- Cost: only $4.99 credit. Use `--spend budget --budget-total <usd>` or `--stop-days`, check `acc billing usage` after the first hour.
  The DB must stay up for the app to boot into live mode; stop both with `acc services close` after judging.
- Region: choose one region for DB and app (lower latency); `asia` is closest to PKT but has fewer online nodes (5).
- Confidential mode (`--confidential`, `acc attest <id>`) is optional; START-HERE.md asks to record the attestation outcome.

## Dockerfile changes (this task)

`CMD` now honours `$PORT` (default 8000), passes `--proxy-headers --forwarded-allow-ips='*'` so https URLs behind the proxy are right,
runs `--workers 1` explicitly, and a Python-based `HEALTHCHECK` was added. Non-root user was already present. `docker build -t afterward:check .` succeeds.
Not verified: running the container end to end against a database.
