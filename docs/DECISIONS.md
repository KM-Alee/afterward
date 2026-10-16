# Decisions

Only the lead accepts ADR changes. Alternatives and reasons below come from AFTERWARD-TECH §T19.

## ADR-001: Connectors

- Date: 2026-10-16
- Decision: Direct Gmail and Calendar APIs
- Alternatives: fastn MCP connectors
- Reason: The handbook doesn't require fastn. Direct APIs give us threads, history polling and Sent search, which reconciliation needs. *Optional MCP angle (stretch, ~1 h):* expose Afterward's read-only case tools as an MCP server, so a family's own assistant can ask "what's still open?".

## ADR-002: Voice architecture

- Date: 2026-10-16
- Decision: Transcription → reasoning → validation → speech
- Alternatives: Realtime speech-to-speech
- Reason: Every spoken word passes the validator and guard; acceptance is a template.

## ADR-003: Live demo channel

- Date: 2026-10-16
- Decision: Telegram primary, WhatsApp secondary
- Alternatives: WhatsApp only
- Reason: WhatsApp's 24-hour window and test-number limits make it fragile for a live demo; the same gateway serves both.

## ADR-004: Telephony

- Date: 2026-10-16
- Decision: Browser call room (simulated provider)
- Alternatives: Twilio phone calls
- Reason: Twilio trials can't call Pakistan; it would need a paid account plus a streaming bridge.

## ADR-005: Storage of documents

- Date: 2026-10-16
- Decision: Encrypted in Postgres
- Alternatives: Container volume
- Reason: Survives redeploys regardless of the platform's volume behaviour.

## ADR-006: Google auth

- Date: 2026-10-16
- Decision: Refresh tokens from a local script into env vars
- Alternatives: In-app OAuth redirect
- Reason: Fewer moving parts on the deployed URL tonight.

## ADR-007: Extraction model

- Date: 2026-10-16
- Decision: `gpt-6.1-sol` (accuracy)
- Alternatives: `gpt-6-luna` everywhere
- Reason: The outcome check is our core claim; we spend a few cents per email for accuracy, and keep Luna where latency matters.

## ADR-008: Front end

- Date: 2026-10-16
- Decision: Server HTML + vanilla JS
- Alternatives: React/Next
- Reason: No build step; faster and safer overnight.

## ADR-009: Optional external MCP integration

- Date: 2026-10-16
- Decision: Keep direct Gmail/Calendar APIs as the baseline. Time-box one fastn MCP
  integration for an approved calendar reminder OR a status-only spreadsheet mirror,
  after the core story and proof suite pass. No n8n service for the overnight build.
- Alternatives: Rewrite core workflows in n8n; route critical Gmail operations through
  an unverified connector; add MCP without a user-facing purpose.
- Reason: User requested a useful external MCP service. fastn may reduce secondary
  connector/auth work; critical approvals, queueing and reconciliation stay in Python.
  This is a stretch plan, not an implemented or verified capability.
- Sources: [fastn docs](https://docs.fastn.ai/),
  [fastn MCP](https://github.com/fastn-ai/fastn-mcp),
  [n8n MCP](https://n8n.io/mcp/).

## ADR-010: Frontend UX approval before parallel development

- Date: 2026-10-16
- Decision: Claude creates polished standalone mock pages on slice/frontend-mockup;
  user reviews and explicitly approves the UX before shared-foundation completion
  and launch of A/B/C/D. Lead records approval; D implements the approved design.
- Alternatives: Design during D's parallel slice; launch backend slices before UX review.
- Reason: The user wants the experience considered and reviewed before implementation
  fans out. Separate mock data and local interactions keep review independent of
  live integrations and do not implement backend features during workflow setup.
