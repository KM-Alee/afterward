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
- Operator note, 2026-10-17: for this demo, Gmail and Calendar go through the
  connected Fastn accounts. The demo mailbox is now `pabloman414@gmail.com`
  on project `mehu-511820`, where Gmail API and Calendar API are enabled.
  The local consent is done. Both mailbox fields hold that refresh token.
  The Web client's `http://localhost:8765/` redirect is only for that
  laptop consent. A deploy uses the refresh token and does not need that
  redirect to be public.

## ADR-010: Frontend UX approval before parallel development

- Date: 2026-10-16
- Decision: Claude creates polished standalone mock pages on slice/frontend-mockup;
  user reviews and explicitly approves the UX before shared-foundation completion
  and launch of A/B/C/D. Lead records approval; D implements the approved design.
- Alternatives: Design during D's parallel slice; launch backend slices before UX review.
- Reason: The user wants the experience considered and reviewed before implementation
  fans out. Separate mock data and local interactions keep review independent of
  live integrations and do not implement backend features during workflow setup.

## ADR-011: OpenAI Agents SDK and realtime voice calls

- Date: 2026-10-16
- Decision: Run all model work through the OpenAI Agents SDK (Responses API): agents with
  structured outputs, tools, guardrails, `needs_approval`, SQLAlchemy sessions and tracing.
  Provider calls use an Agents SDK `RealtimeAgent` on `gpt-realtime-2.1`, relayed through
  our server, for the browser call room and (stretch) real outbound phone calls via Twilio
  Media Streams. Keep `gpt-transcribe`, `gpt-6-luna`, `gpt-6.1-sol` (upgrade: `gpt-6-astra`)
  and `gpt-4o-mini-tts` for exact approved wording.
- Alternatives: Chained STT → LLM → TTS call engine (previous); GPT-Live `gpt-live-1` with
  direct SIP calling; hand-rolled Responses calls without the SDK.
- Reason: User asked for current OpenAI voice and agent tooling, and for agents that place
  calls. The SDK gives approvals, guardrails and tracing natively. Relaying audio through our
  server keeps the core guarantees: no model-chosen acceptance, server-played approved
  wording, discarded obsolete audio. GPT-Live has no documented verbatim control and its SIP
  audio bypasses our server; revisit once that is verified. The engine stays the authority:
  SDK approvals are the flow, versioned approvals and execution-time checks decide.
- Status: architecture decision; not implemented or verified. Requires adding `openai-agents`
  as a dependency and contract revision 1 (CR-lead-1 in CONTRACTS.md).
- Sources: [Voice agents](https://developers.openai.com/api/docs/guides/voice-agents),
  [Telephony and SIP](https://developers.openai.com/api/docs/guides/realtime-sip),
  [Agents SDK realtime guide](https://openai.github.io/openai-agents-python/realtime/guide/),
  [Human-in-the-loop](https://openai.github.io/openai-agents-python/human_in_the_loop/).
