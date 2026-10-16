# Agent instructions

Afterward is a bereavement administration case manager for Agentika 2.0, NaSCon’26.
The family shares intent once through Telegram, with WhatsApp as a secondary channel.
Human dependency answers shape conditional plans and explicit approvals.
AI proposes structured records; deterministic code controls permission and outcomes.
Provider replies must satisfy the approved plan before an account is marked resolved.
PostgreSQL holds durable jobs, versioned approvals, audit events and encrypted documents.
Python 3.13/FastAPI serves HTML, JSON and the simulated browser call room.
OpenAI provides transcription, reasoning, vision and speech behind shared interfaces.
Direct Gmail/Calendar APIs are baseline; optional fastn MCP is a secondary integration.
Code freezes at 12:00 PKT on 17 Oct 2026; submission is 12:45 PKT that day.


Read fully: [product](docs/AFTERWARD.md), [technical design](docs/AFTERWARD-TECH.md),
[implementation](docs/IMPLEMENTATION.md), [ownership](CONTRIBUTING-AGENTS.md), and
[frozen contracts](docs/CONTRACTS.md).

## HARD RULES

- No secrets in code, logs, tests, commits, screenshots or chat. Never read private/,
  .env or .env.* files, or client_secret*.json. Do not generate secrets as an agent;
  the operator explicitly invokes scripts/make_secrets.py and transfers output privately.
- AI proposes, code decides. Model output can never add recipients or widen permissions.
- Honest claims only: follow AFTERWARD.md §11. No complete-discovery promise, certified
  photo claim, perfect speech guard, exactly-once external delivery or real-phone-call claim.
- Never sign, move money or impersonate; never close/transfer without dependency checks.
- English only. Never draft the LinkedIn post; the humans write it.
- Never edit outside your owned directories; use the map below and the documented
  per-row log/handoff exceptions. Route shared changes through the lead.
- Never change frozen contracts. Append a proposal to docs/CONTRACTS.md instead;
  only the lead edits interfaces, AI schemas, DB tables and shared fakes.
- Never force-push main. Do not force-push other branches either; hand off locally
  rebased work to the lead. Never bypass a failed quality gate.
- No product work in the setup scaffold. Complete the frontend-first review in docs/FRONTEND-FIRST.md. Launch parallel
  feature work only after explicit user UX approval AND lead-published Python contract revision 1.

## Ownership map

| Slice | Owned paths | Branch |
|---|---|---|
| Foundation / lead | root tooling/docs, .github/, .claude/, scripts except C's scripts, app/main.py, app/config.py, app/logging.py, app/db.py, app/models.py, app/contracts.py, app/ai/schemas.py, app/fakes/, app/demo/seed.py, tests/conftest.py, tests/foundation/ | main; optional slice/foundation |
| Frontend UX (before Phase 2) | design/frontend/ only; own handoff, STATUS row and DEVLOG append | slice/frontend-mockup |
| A Engine & Truth | app/engine/, app/ai/verify.py, app/ai/prompts.py (extraction), app/ai/client.py, app/demo/fixtures/, tests/engine/, tests/proofs/ | slice/engine-truth |
| B Channels & Conversation | app/channels/, app/conversation/, app/discovery/, tests/channels/, tests/conversation/ | slice/channels-conversation |
| C Mail & Integrations | app/mail/, app/integrations/, app/demo/provider_variants.py, scripts/google_auth.py, tests/mail/ | slice/mail-integrations |
| D Web/Desk/Call room | app/web/, app/call/, static/, tests/web/, tests/call/ | slice/web-desk-call |
| QA | tests/qa/, docs/handoffs/qa-adversary.md findings only; no production fixes | slice/qa-adversary |


Exceptions and shared-file requests are detailed in CONTRIBUTING-AGENTS.md.
Only update your own STATUS row and handoff; append DEVLOG and contract proposals.

## Frontend-first start gate

Before A/B/C/D: follow [the branch guide](docs/FRONTEND-FIRST.md). One Claude
session owns design/frontend/ on slice/frontend-mockup, builds polished standalone
mock flows with no live integrations, and stops for explicit user review. Only the
lead records user approval in docs/FRONTEND-APPROVAL.md. After approval, the lead
publishes shared Python contracts/models/schemas/fakes revision 1. Only then launch
parallel slices. D implements the approved design; material UX changes go to the user.
This prototype stage is permitted before Python product contracts exist; it must
not invent or modify backend contracts. No mock pages are built in workflow setup.

## Commands

- `make setup`: frozen uv environment, pre-commit hook, production requirements export.
- `make db-up` / `make db-down`: local Postgres 17; down retains its volume.
- `make run`: health/status shell on port 8000, or the later integrated application.
- `make test`: offline external services, real Postgres for marked DB tests.
- `make test-fast`: no network or DB/slow tests; run setup first to populate uv's cache.
- `make lint` / `make fmt`: Ruff checks / fixes and formatting.
- `make proof`: clearly labelled placeholder until Agent A supplies the real proof runner.
- `make ci`: lint and all non-live tests; requires reachable DATABASE_URL_TEST.
- `make worktree SLICE=frontend-mockup`: create the required first UX prototype branch.
- `make worktree SLICE=engine-truth`: create ../afterward-engine-truth on slice/engine-truth.
- `make merge SLICE=engine-truth`: lead only; rebase, setup and CI before --no-ff merge.
- `uv run --frozen pre-commit run --all-files`: formatting, hygiene and secret scan.

## Code style and testing

Python 3.13, type annotations at module boundaries, short docstrings, explicit error
states and Ruff's checked rules. Avoid import-time network calls and hidden side
effects. Keep secrets as SecretStr; status responses use an explicit allowlist.
Logs go through app/logging.py; event kind and IDs by default. Never place bodies,
transcripts or raw exceptions in event names or IDs. LOG_TRANSCRIPTS defaults false.
Every product rule gets a unit test, including deny paths and stale/race conditions.
External services only via fakes in app/fakes/ in default tests. Use synthetic recorded
payloads for webhook contract tests; never record tokens or real personal data.
Use @pytest.mark.db and the schema fixtures for Postgres; never use SQLite.
Mark deliberate live tests network, run only with --live and explicit operator setup.
Do not weaken, skip or change assertions just to get green. No secret prints on failure.

## Git workflow and definition of done

One worktree per slice at ../afterward-<slice>, branch slice/<slice> from main.
Use the canonical slice names in scripts/agent_worktree.sh. Run make setup there;
ignored files and credentials are not copied. All worktrees share the compose DB
but each test session has its own schema. Override DATABASE_URL_TEST externally if needed.
Make small commits with feat/fix/test/docs/chore and the slice name, e.g.
`test(engine-truth): cover stale approval`. Rebase on main before handoff.
Before done: tests green, Ruff clean, own handoff written, own STATUS row updated,
and a DEVLOG entry appended. State what is stubbed and what was not verified.
Lead merges A → C → B → D; QA starts from the integrated result and only reports.
Checkpoints: hello deploy ~21:15, integrated deploy ~03:00, rehearsals 08:00–10:00.
No new features after 09:30. Freeze at 12:00 PKT; submit by 12:45 PKT, 17 Oct 2026.

## Stop and ask the lead/operator

- A contract change is needed: append the proposed change, stop dependent work.
- A secret is needed: ask the operator to configure it through the platform, never paste it.
- A decision changes product behaviour: explain alternatives and wait for a decision.
- Tests cannot be made green within 30 minutes: report the failing test and evidence.

Continue independent owned work while awaiting answers; never bypass these boundaries.
