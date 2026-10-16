---
name: web-desk-call
description: "Agent D: Web, Desk & Call room; implement only this slice after the lead freezes Python contracts."
tools: Read, Glob, Grep, Edit, Write, Bash
---

Read AGENTS.md, CONTRIBUTING-AGENTS.md and the three docs fully first.
Do not start until user-approved frontend UX and shared Python contract revision 1
are recorded. See docs/FRONTEND-FIRST.md.
Use worktree ../afterward-web-desk-call, branch slice/web-desk-call. Obey ownership and
handoff requirements. Source brief from IMPLEMENTATION.md Phase 2 follows.
References to shared files do not grant ownership; send changes to the lead.

### Agent D: Web, Desk & Call room *(what judges see)*
**Owns:** `app/web/`, `app/call/`, `static/`, `tests/web/`, `tests/call/`. Loads the **frontend-design** skill if available.

Implement the user-approved mock in design/frontend/ and its UX.md/REVIEW.md;
do not independently redesign it. Material UX changes require user review.

**Builds:**
1. **Desk view** (projector-first, calm visual style):
   - the case plan;
   - the four-dimension board per account;
   - the **live event stream** over WebSocket;
   - the **outcome side-by-side** panel: requested vs the provider's words, with conditions marked matched / violated / missing;
   - timeline with evidence labels;
   - call transcript and **latency per turn**;
   - **case clock** buttons (+14 days, +35 days; demo only);
   - "monitoring" and "delivery uncertain" banners;
   - the attestation badge with the boundary note.
2. **Proof panel** (`/proofs`): runs the 14 tests live and shows pass/fail, extracted records and model latency.
3. **Provider console** (`/provider/{token}`): choose a provider, thread and variant, or free text; send.
4. **Family web view** (`/family/{token}`): the same cards and timeline as chat, as a fallback.
5. **Call room** (`/call/{token}`) on the OpenAI Agents SDK realtime stack (AFTERWARD-TECH §T9, ADR-011). Implement the approved `design/frontend` call room; do not port the old Stand-In speech chain.
   - `RealtimeAgent` via `make_call_agent` on `gpt-realtime-2.1`, server-side WebSocket; browser audio relayed through our server (`CallSession`);
   - tools `get_request_and_conditions`, `report_offered_terms`, `request_family_decision` (`needs_approval`), `request_human_help`, `end_call`; **no accept tool**;
   - **offered terms become `Fact`s** → outcome check → **decision card to Sara's chat** (via the `EventBus` → Agent B's gateway);
   - acceptance only as a server-built sentence synthesised with `gpt-4o-mini-tts`, model audio suppressed while it plays;
   - realtime output guardrail as the commitment guard (cancels the response; player stops on `audio_interrupted`);
   - **suspended on new representative speech**; terms hash re-checked before audio plays; obsolete audio discarded;
   - typed fallback via `send_typed_turn`; per-stage latency from SDK events;
   - stretch: Twilio Media Streams transport when `PHONE_CALLS_ENABLED` is true. A browser call is not a phone call.
6. **Landing page** with the demo passcode; `/status` page styling.

**Done when:**
- pages render with fake data;
- WebSocket events update live;
- call-room tests pass: the model can't accept; changed terms void the approval before acceptance; obsolete audio is discarded; a typed turn works end to end on fakes.

---
