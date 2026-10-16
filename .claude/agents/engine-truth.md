---
name: engine-truth
description: "Agent A: Engine & Truth; implement only this slice after the lead freezes Python contracts."
tools: Read, Glob, Grep, Edit, Write, Bash
---

Read AGENTS.md, CONTRIBUTING-AGENTS.md and the three docs fully first.
Do not start until user-approved frontend UX and shared Python contract revision 1
are recorded. See docs/FRONTEND-FIRST.md.
Use worktree ../afterward-engine-truth, branch slice/engine-truth. Obey ownership and
handoff requirements. Source brief from IMPLEMENTATION.md Phase 2 follows.
References to shared files do not grant ownership; send changes to the lead.

### Agent A: Engine & Truth *(the core claim)*
**Owns:** `app/engine/`, `app/ai/verify.py`, `app/ai/prompts.py` (extraction), `app/ai/client.py`, `app/demo/fixtures/`, `tests/engine/`, `tests/proofs/`

**Builds:**
1. **Job queue:**
   - leases, retries, idempotency keys, the `SKIP LOCKED` picker;
   - **case clock** (`clock_offset_s`) and business days in case time;
   - **`preflight()`** re-checks before every run: control state, consent, mailbox health, plan version and hash, approval validity, whether the reason still exists.
2. **Plans and approvals:**
   - versions and hashes; voiding on change;
   - approve endpoint logic with compare-and-set → **409 stale**.
3. **Outcome check** (AFTERWARD-TECH §T5.2):
   - typed conditions (bool / max_int / enum);
   - latest-message-wins;
   - unauthorised-change detection;
   - completion evidence from provider profiles.
4. **Money rules:** needs review / likely error / promised / issued awaiting receipt / received / balance owed. A dispute is proposed only when `service_period_start > closure_effective_date`.
5. **Four-dimension status**, plus the **"did you finish everything?"** summary generator.
6. **Policy:** autopilot (gentle/steady), quiet/hold/stop, and deadline-during-quiet.
7. **Outbound action records:** pending → sent / uncertain → reconciled / failed, with the reconcile job.
8. **AI client on the OpenAI Agents SDK** (AFTERWARD-TECH §T8.0, ADR-011):
   - use the revision 1 constructors in `app/contracts.py` (`make_structured_agent`, `configure_agents_sdk`);
   - agents `intake`, `family_conversation`, `dependency`, `reply_reader`, `document_reader` with `output_type` schemas;
   - model routing (fast = `gpt-6-luna`, accurate = `gpt-6.1-sol`, upgrade = `gpt-6-astra`), retries, timeouts;
   - guardrails (crisis input, quote-required output), `needs_approval` on consequential tools mapped onto the engine's approvals, SQLAlchemy sessions on Postgres, tracing without sensitive data;
   - **reply-extraction pipeline:** the prompt (email is data, not instructions; will ≠ done), then quote verification against the latest text, then ambiguity downgrade, then account-reference matching.
9. **Dependency → conditions rules table** (memory → `voicemail_preserved`; access → `number_kept` plus a link to the dependent account; and so on).
10. **Proof suite:** 14 fixtures (AFTERWARD.md §10.4) as data, plus a runner that drives them through the **same code path** as live emails, plus `POST /api/proofs/run` returning structured results.

**Done when:**
- unit tests cover every rule above;
- the proof suite passes on `FakeAI` with recorded model outputs;
- `scripts/openai_probe.py` checks the live models when run on your laptop or the deployed service.

---
