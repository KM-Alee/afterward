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
5. **Call room** (`/call/{token}`), ported from Stand-In (`/home/claude/standin`):
   - push-to-talk → `gpt-transcribe` → `CallTurnOut` (structured actions; the model can't accept) → guard → `gpt-4o-mini-tts` **pcm streaming** → WebAudio;
   - **offered terms become `Fact`s** → outcome check → **decision card to Sara's chat** (via the `EventBus` → Agent B's gateway);
   - acceptance only from the server template;
   - **suspended on new representative speech**; terms hash re-checked before audio plays; obsolete audio discarded;
   - typed fallback;
   - per-stage latency capture.
6. **Landing page** with the demo passcode; `/status` page styling.

**Done when:**
- pages render with fake data;
- WebSocket events update live;
- call-room tests pass: the model can't accept; changed terms void the approval before acceptance; obsolete audio is discarded; a typed turn works end to end on fakes.

---
