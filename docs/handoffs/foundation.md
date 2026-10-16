# Slice handoff: foundation

Owner: Lead
Branch: main
Updated: 2026-10-16 23:39 PKT

## What works

Contract revision 1 is implemented on main, after the ADR-011 fast-forward.

- `app/models.py`: all 19 product tables, string-backed enums, UUID keys, the demo-only clock-offset check, and unique idempotency keys.
- `app/db.py`: `create_all` plus boot revision `contract-rev-1`.
- `app/contracts.py`: Channel, Mailbox, AIClient, Clock, EventBus, CallSession, and Agents SDK constructors (`make_structured_agent`, `make_call_agent`). No accept tool.
- `app/ai/schemas.py`: strict Intake, Dependency, Doc, Reply and realtime tool schemas. `CallTurnOut` is gone.
- `app/fakes/`: FakeAI, FakeMailbox, FakeChannel, FakeClock, FakeCallSession.
- `app/demo/seed.py`: Malik case `AW-1042`, five declared providers, nine account references.
- Dependency `openai-agents` plus SQLAlchemy asyncio (greenlet). No asyncpg.
- `make test`: 54 passed, real Postgres, no network.

## What is stubbed

The case engine, channels, mail, web, call room and proof runner. `app/ai/client.py` is still Agent A's real client. The lifespan boots the schema and does not run the job worker. The Malik seed is day-0 candidates, not the mid-demo story. `make proof` is still the placeholder.

## How to test it

- `make test` (Postgres from `make db-up`): 54 passed.
- `uv run --offline --frozen ruff check .` and `ruff format --check .`: clean.
- Live OpenAI, Gmail, Telegram, WhatsApp and Twilio were not called.

## Known risks

Revision 1 types are frozen. Slices must import them. `EventBus.publish` does not commit; subscribers run after commit. Phone calls stay off unless `PHONE_CALLS_ENABLED` is set. A browser call is not a phone call. The status route's database probe can create the product tables in the database named by `DATABASE_URL` because boot migration runs in the app lifespan. No secrets were read or written.

## Files touched

Phase 1 product foundation under `app/models.py`, `app/db.py`, `app/contracts.py`, `app/ai/schemas.py`, `app/fakes/`, `app/demo/seed.py`, `app/main.py`, `tests/foundation/`, `pyproject.toml`, `uv.lock`, `requirements.txt`, `.env.example`, `docs/CONTRACTS.md`, and the engine and web agent briefs so they follow ADR-011.
