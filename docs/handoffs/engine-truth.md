# Slice handoff: engine-truth

Owner: Agent A
Branch: slice/engine-truth
Commit: 9d1a5e6eb71332f8fb2e808b8009dd54707af9ea
Updated: 2026-10-17 00:16 PKT

## What works

Deterministic engine on contract revision 1. `make ci` is green (95 passed, Ruff clean). The 14 AFTERWARD.md §10.4 proofs pass on FakeAI through `run_proofs()` and `POST /api/proofs/run`.

- Jobs: `FOR UPDATE SKIP LOCKED` lease, expired-lease reclaim, idempotency (`ON CONFLICT`), retries, case clock (`clock_offset_s`), business days, and `preflight()` which cancels with a recorded reason.
- Plans: hash of action, conditions, documents and recipient. A new version voids open and approved approvals. `approve()` compare-and-sets `(plan_id, version, hash)` and raises `StalePlan` (409). Close and transfer require a dependency row.
- Outcome check: bool / max_int / enum, latest message wins, ambiguous is missing, unauthorised changes, completion only with provider evidence and every condition matched.
- Money: dispute proposed only when `service_period_start > closure_effective_date`. Statuses cover needs review, likely error, refund promised, issued awaiting receipt, received, and balance owed. A balance is never auto-disputed.
- Four-dimension snapshot and a code-written "did you finish everything?" summary.
- Policy: gentle asks before follow-ups; steady allows follow-ups and routine sends; quiet, hold, stop, and deadline-during-quiet.
- Actions: pending → sent / uncertain → reconciled / failed. Uncertain sends are not retried unless Sent search proves they never left, and then only once.
- Extraction: email is data; "will" is not done unless the quote also records completion; "subject to" is conditional; bad quotes become ambiguous and are dropped; each fact needs its own quote; `account_hint` must match one account ref.
- Dependencies: memory → `voicemail_preserved`; access → `number_kept` plus a link when the number matches an account ref.
- AI client: Agents SDK agents for intake, family_conversation, dependency, reply_reader, document_reader via `make_structured_agent` and `configure_agents_sdk`. Fast model `gpt-6-luna`, accurate `gpt-6.1-sol`, upgrade `gpt-6-astra`. Crisis and quote guardrails, `needs_approval` on `propose_decision` and `record_dependency_answer`. Retries and timeouts. No API key means no socket. Phone photos are forced to `photo`.

Import from `app.engine` (`outcome_check`, `approve`, `preflight`, `lease_due`, `run_proofs`, `router`) and `app.ai.client.AgentsSDKClient`. Reply mail should call `app.engine.pipeline.process_reply`.

## What is stubbed

- Live transcription, speech, and `Runner.run` are not used. Without an API key, `structured`, `transcribe` and `speak_stream` raise `AIUnavailable`. Tests inject a runner or FakeAI.
- Conversation `SQLAlchemySession` can be constructed on `postgresql+psycopg` with `create_tables=False`. The SDK memory tables are not created and are not in the frozen schema.
- Tool bodies return `proposal_only` or `read_only`. They do not read the case or grant permission. `tool_grants_permission` is always false.
- Job kinds are stored, leased and preflighted. This slice does not send Gmail, Telegram or calendar events. Agent C and Agent B own those executors.
- `family_conversation` uses a slice-local `FamilyConversationOut` because `app/ai/schemas.py` has no frozen output model for that agent. It was not added to the frozen schema.
- `app/main.py` does not mount the router. `make proof` is still the Makefile placeholder. `scripts/openai_probe.py` was not added; both are outside this slice.

## How to test it

`make ci` on this worktree: Ruff clean, 95 passed, no network. The proof test calls `run_proofs(session)` and `POST /api/proofs/run` on a FastAPI app that includes `app.engine.proofs.router`.

Not verified: a live OpenAI call, a mounted route inside `app.main`, or SDK memory tables under a real conversation.

## Known risks

No contract change is required to merge. If Agent B needs a shared conversation output schema, the lead can promote `FamilyConversationOut` in a later revision. Until then it stays in `app/ai/client.py`.

`preflight()` cancels gentle follow-ups (`approval_required`) even when the original send was approved. Steady follow-ups run when that approval is still valid. Hold cancels outbound jobs and leaves monitoring jobs runnable.

The proofs router commits through its default session dependency. Tests override that dependency. The lead should mount `app.engine.proofs.router` without editing this slice's modules.

## Files touched

`app/engine/`, `app/ai/client.py`, `app/ai/prompts.py`, `app/ai/verify.py`, `app/demo/fixtures/`, `tests/engine/`, `tests/proofs/`, this handoff, the Engine & Truth row in `docs/STATUS.md`, and one appended `docs/DEVLOG.md` line.
