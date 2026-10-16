# Afterward

Hackathon workflow scaffold for Agentika 2.0 / NaSCon’26. **Only `/health` and
`/status` are implemented.** Product modules, OAuth/probe helpers, fakes, schemas
and tables are explicitly empty stubs. `make proof` is a placeholder.

Read [product](docs/AFTERWARD.md), [architecture](docs/AFTERWARD-TECH.md),
[implementation plan](docs/IMPLEMENTATION.md), [agent rules](AGENTS.md),
[ownership](CONTRIBUTING-AGENTS.md), and [operator setup](docs/START-HERE.md).

## Local workflow

Install uv, Git, Docker Engine with Compose, and GNU make. Gitleaks uses its official Docker pre-commit hook; no Go installation is needed.
Linux merge serialization uses flock. uv installs Python 3.13 when needed.

```sh
make setup
make db-up
make ci
make run
```

Open http://localhost:8000/health and http://localhost:8000/status.
`make test-fast` runs without service/network access after setup.
`uv run --frozen pre-commit run --all-files` runs all commit checks.
`make fmt` fixes formatting. `make db-down` stops Postgres and retains its volume.

The local database uses loopback-only trust authentication with no password.
Production must use the managed service's authenticated database URL. Default dev
and test URLs target localhost:5432/afterward, and tests create/drop a fresh UUID
schema per session. Use DATABASE_URL_TEST to select a dedicated test database whose
role can create schemas; never point tests at a production database. Test failures
must not print DSNs. @pytest.mark.db is mandatory for DB tests; db_connection and
db_session roll back each test. Queue concurrency tests can use db_engine directly
and must clean their committed test data. Live tests are opt-in via --live.

No dotenv file is loaded by app or Makefile. Set variables in the process environment;
.env.example lists names only. Do not ask an agent to read real local credential files.
If changing the local port, set AFTERWARD_PG_PORT for Compose and both database URLs
in your shell to the same port. Compose always uses --env-file /dev/null.

## Parallel agents

**Required first stage:** one Claude session builds polished standalone mock pages
on slice/frontend-mockup. Follow [the frontend branch guide](docs/FRONTEND-FIRST.md).
The user reviews and explicitly approves the actual UX; the lead records approval.
Then the lead implements shared Python contracts, DB tables, strict AI schemas
and deterministic fakes, publishing contract revision 1. Only after both gates
pass may A/B/C/D start. D implements the approved design. Scaffold completion
alone does not authorize parallel product development.

```sh
make worktree SLICE=frontend-mockup
# Then open Claude in ../afterward-frontend-mockup and use the guide's brief.
```

```sh
make worktree SLICE=engine-truth
# In ../afterward-engine-truth:
make setup
make test-fast
```

Canonical slices: foundation, frontend-mockup, engine-truth, channels-conversation, mail-integrations,
web-desk-call, qa-adversary. Worktrees copy tracked files only, no secrets. Every
worktree needs its own uv environment and hooks installed through make setup.
The lead integrates A → C → B → D from clean main:

```sh
make merge SLICE=engine-truth
```

This rebases the clean slice, runs setup and CI there, and merges with --no-ff only
if verification succeeds and branch tips have not moved. Conflicts stop for manual
lead resolution. It never pushes, deletes worktrees or rewrites main. QA writes
findings/failing tests only. Shared logs are docs/STATUS.md and append-only DEVLOG.md.

## Image and CI

Pushes/PRs run Ruff, real Postgres tests and gitleaks. Tags such as v0.0.1 run tests
and secret scans before publishing **ghcr.io/km-alee/afterward:0.0.1** using
GITHUB_TOKEN. Only versioned release tags are accepted: never latest or main.
Make the GHCR package public before Alternate Clouds pulls it.

```sh
docker build -t afterward:0.0.1 .
docker run --rm -p 8000:8000 afterward:0.0.1
```

`/status` reports model IDs, configured channel modes and a bounded real DB probe;
it does not assert models, mailboxes or channels are working. With no DATABASE_URL,
DB reachability is false. Runtime emits structured JSON to stdout (acc services logs),
with request ID, case ID and event kind. Free-form messages, bodies and exceptions
are suppressed by default. LOG_TRANSCRIPTS=true opts into text logging while
credential redaction stays active. Never put user text into event kinds or IDs.

## Architecture and honest scope

Python 3.13 + FastAPI, Postgres 17/SQLAlchemy/psycopg, OpenAI, direct Telegram,
WhatsApp, Gmail and Calendar APIs, Jinja2/vanilla JS, ffmpeg and Fernet. AI proposes;
code decides. The call room uses an OpenAI realtime voice agent in the browser; real phone calls are a stretch and are only claimed when made.
Follow [honest claims](docs/AFTERWARD.md#11-safety-privacy-and-honest-claims).
The optional fastn MCP integration is a time-boxed secondary calendar or status
mirror task after the core demo passes. It is not installed or implemented here.

Code freeze: **17 Oct 2026, 12:00 PKT**. Submission: **12:45 PKT**. No deploys after
freeze; keep the service running through the closing ceremony. No real judge login
exists in this scaffold. Operators later set DEMO_PASSCODE privately and include it
in the submission PDF, never this repository.

## Credits

FastAPI, uvicorn, SQLAlchemy, psycopg, Pydantic, httpx, OpenAI Python SDK, Google API
Python Client, google-auth, google-auth-oauthlib, cryptography, python-multipart,
Jinja2, PostgreSQL, uv, pytest, pytest-asyncio, Ruff, pre-commit, gitleaks and Docker.
ffmpeg licensing depends on the distribution/build (LGPL/GPL components); retain
its notices when distributing. Planned voice-engine reuse credits our earlier
Stand-In project once imported; no Stand-In implementation is included yet.
