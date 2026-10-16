---
name: channels-conversation
description: "Agent B: Channels & Conversation; implement only this slice after the lead freezes Python contracts."
tools: Read, Glob, Grep, Edit, Write, Bash
---

Read AGENTS.md, CONTRIBUTING-AGENTS.md and the three docs fully first.
Use worktree ../afterward-channels-conversation, branch slice/channels-conversation. Obey ownership and
handoff requirements. Source brief from IMPLEMENTATION.md Phase 2 follows.
References to shared files do not grant ownership; send changes to the lead.

### Agent B: Channels & Conversation *(everything the family touches)*
**Owns:** `app/channels/`, `app/conversation/`, `app/discovery/`, `tests/channels/`, `tests/conversation/`

**Builds:**
1. **Gateway**, plus the **Telegram adapter:**
   - webhook with secret-header check, and polling-mode fallback;
   - inline keyboards (≤3 options, short `callback_data` tokens), `answerCallbackQuery`;
   - `getFile` voice and photo download; `sendVoice` (opus).
2. **WhatsApp adapter:** raw-challenge verify, `X-Hub-Signature-256` check, interactive reply buttons (≤3, titles ≤20 characters), media download, and a 24-hour-window guard.
3. **Audio:** ffmpeg repackaging `.ogg` → `.webm` (no re-encode), then transcription via the `AIClient`.
4. **Conversation agent:**
   - **tell-it-once intake** (with the confirmation card and "stated" role labels);
   - **routing:** question / dependency answer / decision via free text, always read back as buttons / commands (`status`, `quiet`, `hold`, `stop`, `resume`, `help`) / crisis (care template, findahelpline.com, pause) / polite off-topic decline;
   - **dependency question flow,** including the **household invite** (`/start <token>` deep link joins Amina);
   - decision cards and approval cards with exact recipient, action, conditions, documents and consequence;
   - the "did you finish everything?" reply, worded warmly from Agent A's summary;
   - the **weekly digest** (skips quiet days).
5. **Discovery:** forwarded emails and photos → `DocOut` via vision → candidate accounts, merged only on a matching reference; the **coverage panel** data (sources searched / not searched, unconfirmed candidates, where else to look). No "looks complete".
6. **Document vault intake:** type and **form** (a photo is never a certified copy), field extraction, mismatch flags, and encryption via the vault helper.
7. **Demo content:** the Malik case's forwarded emails and photographed letters (clearly labelled demo images), and the sample voice-note scripts.

**Done when:**
- recorded Telegram and WhatsApp payloads parse correctly;
- signature tests pass;
- on fakes, a scripted conversation goes from Sara's voice note → confirmed intake → 9 candidates with coverage → Amina's dependency answer → revised plan → approval card.

---
