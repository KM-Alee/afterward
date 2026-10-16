# Afterward: Implementation plan

*Companion to [AFTERWARD.md](AFTERWARD.md) (what we build) and [AFTERWARD-TECH.md](AFTERWARD-TECH.md) (how it's built).*

**Shape of the plan (updated by the team):** workflow setup → **one Claude
frontend mock branch and explicit user UX approval** → lead product foundation
and frozen Python contracts → **four large parallel agent slices** → integration,
independent QA and rehearsal. The frontend-first gate is mandatory.

```
Setup    workflow scaffold on main (complete)
UX       CLAUDE: slice/frontend-mockup, polished standalone mock pages
Review   USER: review actual flows and explicitly approve before parallel work
Phase 0  YOU: accounts, keys, phones (can run alongside UX work)
Phase 1  LEAD: shared product foundation + Python contract revision 1
Phase 2  A / B / C / D IN PARALLEL, only after UX approval + contract gate
Phase 3  LEAD: integrate A → C → B → D and deploy       ← checkpoint with you
Phase 4  QA reports failing tests; LEAD fixes
Phase 5  Rehearse; freeze 12:00 PKT, submit 12:45 PKT on 17 Oct 2026
```

Read [the dedicated branch/UX guide](FRONTEND-FIRST.md). The approval record is
[FRONTEND-APPROVAL.md](FRONTEND-APPROVAL.md). Do not start A/B/C/D on the strength
of scaffold completion alone. D builds the approved frontend rather than creating
a different design during parallel implementation.

---

## Timeline at a glance (PKT)

The overnight times below are the original estimates, not permission to skip a
gate. Insert the frontend-first prototype and user review **before Phase 1/2**;
recalculate the remaining work after approval. Aim for a 45–60 minute first UX pass;
cut optional scope if needed. Freeze/submission remain fixed.

| Time | You (and teammate) | Me (lead) | Agents |
|---|---|---|---|
| 20:00–21:15 | **Phase 0 setup** | Phase 1 foundation and contracts, CI, hello image | — |
| ~21:15 | **Checkpoint 1:** run the hello deploy (5 min) | Verify `/health`, DB connection, attestation | — |
| 21:15–01:45 | Teammate: demo content, video script, PDF draft. You: rest or help test the bot | Review agent output, keep contracts stable, unblock | **A, B, C, D in parallel** |
| 01:45–03:45 | **Checkpoint 2 (~03:00):** first real deploy, set variables, phone smoke test (20 min) | Merge, integrate, full-story test on fakes, deploy v0.1 | — |
| 03:45–05:45 | Sleep | Fix integration bugs | **QA agent** runs adversarial review and chaos checks |
| 05:45–08:00 | Sleep | Apply QA fixes, deploy v0.2, proof panel green | — |
| 08:00–10:00 | **Checkpoint 3:** live rehearsal ×3 on phones and venue Wi-Fi | Fix only what rehearsal finds; latency measured | — |
| 10:00–12:00 | Video, PDF, screenshots (dashboard, Discord), LinkedIn post **written by you**, teammate reshares | README, credits, final tag | — |
| 12:00 | **Freeze** | Final image tag recorded | — |
| 12:45 | **Submit** | | |

---

## Phase 0: what you set up (≈60–75 min, two people in parallel)

**Rule for secrets:** never paste keys into this chat. Keys go **straight into Alternate Clouds variables** (Checkpoint 1 and 2 give you the exact commands). I only need the **non-secret confirmations** marked 📨.

### 0.1 GitHub (5 min): you
1. Create the repo **`KM-Alee/afterward`** (public is simplest for judges).
2. Tell me 📨 "repo created". I'll attach it to this session with push access, then push the foundation and the CI workflow.
3. After the first CI run: **GitHub → your profile → Packages → `afterward` → Package settings → Change visibility → Public.** (GHCR images are private by default, and Alternate Clouds can't pull private images.)

### 0.2 Alternate Clouds (10 min): you
1. Install and log in to the CLI:
   ```bash
   npm i -g @alternatefutures/acc
   acc login
   acc whoami
   acc projects create --name afterward
   ```
2. Create Postgres:
   ```bash
   acc templates list -c DATABASE
   acc services create --kind template --template <postgres-template-id> --name afterward-db -y
   acc services env list afterward-db
   ```
3. 📨 Tell me: the Postgres template you used, and whether `env list` shows a `DATABASE_URL` (don't paste its value).

### 0.3 OpenAI (2 min): you
- Have the API key ready for Checkpoint 1. Make sure the account has credit.
- Nothing to send me.

### 0.4 Telegram (10 min): you
1. In Telegram, open **@BotFather** → `/newbot` → name **Afterward (demo)** → username e.g. `afterward_demo_bot`.
2. Keep the token for Checkpoint 2.
3. `/setprivacy` → Disable (not strictly needed for direct chats, but harmless).
4. 📨 Send me the **bot username**.
5. Install Telegram on **two phones**: Sara (presenter) and Amina (teammate).

### 0.5 WhatsApp Cloud API test number (20 min): teammate
1. Go to developers.facebook.com → **Create app** → type **Business** → add the **WhatsApp** product.
2. In **WhatsApp → API Setup**, note the **test phone number** and its **Phone number ID**.
3. **Add recipients:** verify both team phones (each receives a code in WhatsApp). Up to 5 recipients are allowed.
4. **Token:** create a **System User** in Business Settings and generate a token with `whatsapp_business_messaging` permission. The dashboard's temporary token is a fallback only.
5. **App secret:** App settings → Basic → App secret. Keep it for Checkpoint 2.
6. 📨 Tell me "WhatsApp ready" plus the **Phone number ID**. That ID is not a secret.
7. *If this takes more than 30 minutes, stop.* WhatsApp is the first thing we cut; Telegram is the demo channel.

### 0.6 Google: two demo mailboxes and API access (20 min): teammate
1. Create two Gmail accounts:
   - **Family mailbox:** e.g. `afterward.malik.demo@gmail.com`
   - **Providers mailbox:** e.g. `afterward.providers.demo@gmail.com`
2. In **console.cloud.google.com**, create the project `afterward` and enable the **Gmail API** and the **Google Calendar API**.
3. Set up the **OAuth consent screen**: External, Testing, and add **both demo Gmail addresses as test users**.
4. **Credentials → Create OAuth client ID → Desktop app.** Download the JSON and keep it on your laptop only.
5. Later (after the foundation is pushed), run `python scripts/google_auth.py --client client_secret.json` **twice**, once signed in as each mailbox. It prints a refresh token each time; keep both for Checkpoint 2.
6. 📨 Tell me both **email addresses**.

### 0.7 Generate app secrets (2 min): you, after the foundation is pushed
- Run `python scripts/make_secrets.py`. It prints `VAULT_KEY`, `DEMO_PASSCODE`, `TELEGRAM_WEBHOOK_SECRET` and `WHATSAPP_VERIFY_TOKEN`.
- Keep them for Checkpoint 2.

### 0.8 Handbook items (5 min): both
- Both teammates in the **Alternate Futures Discord** with the required display names. Take the screenshot now while you remember.
- Confirm the team name and both full names and emails for the PDF.

### 0.9 Optional: link this chat to your computer
- If you open this chat in the Claude desktop app and link it to your computer, I can run the `acc` commands, `google_auth.py` and the live end-to-end tests **on your laptop** myself, so checkpoints take minutes.
- This matters because my build environment **can't reach** OpenAI, Telegram or Google directly. The agents build against recorded fixtures and fakes, and live verification happens on Alternate Clouds or your laptop.

**📨 Summary of what I need back:** "repo created" · Postgres template plus whether `DATABASE_URL` exists · bot username · WhatsApp Phone number ID (or "skip WhatsApp") · both demo email addresses · whether you've linked the computer.

---

## Phase 1: foundation and contracts (lead, ≈60 min, runs while you do Phase 0)

The point of this slice: **freeze the shared contracts** so four agents can build in parallel without stepping on each other.

**Delivers (committed to `main` before any agent starts):**

| Area | Files | Content |
|---|---|---|
| Config | `app/config.py` | Every variable from AFTERWARD-TECH §T14; secrets hidden when printed |
| Database | `app/db.py`, `app/models.py` | **All tables** from AFTERWARD-TECH §T4, enums, indexes; `create_all` plus a simple migration-on-boot |
| Contracts | `app/contracts.py` | `AIClient` (transcribe, structured(role, schema, messages, images), speak_stream; backed by the OpenAI Agents SDK), `CallSession` (realtime call engine over a transport: browser or phone), `Mailbox` (poll, get, send, search_sent), `Channel` (§T6), `Clock` (`case_now(case)`), `EventBus` (`publish(case_id, kind, payload)` → events table and WebSocket fan-out) |
| AI schemas | `app/ai/schemas.py` | `IntakeOut`, `DependencyOut`, `DocOut`, `ReplyOut`/`CommitmentOut`/`Fact`, `CallTurnOut`, all strict |
| Fakes | `app/fakes/` | `FakeAI` (deterministic, fixture-keyed), `FakeMailbox` (in-memory threads and Sent), `FakeChannel` (records sends, injects updates), `FakeClock` |
| Demo data | `app/demo/seed.py` (skeleton) | The Malik case, 5 demo providers with profiles and plus-address recipients, account references |
| App shell | `app/main.py` | FastAPI app, lifespan worker stub, `/health`, `/status`, passcode middleware, static mount |
| Tooling | `tests/conftest.py` | Local **Postgres for tests** (real Postgres, not SQLite, because the queue uses `SKIP LOCKED`) |
| | `Dockerfile` | python:3.13-slim + ffmpeg |
| | `.github/workflows/build.yml` | tests → build → push `ghcr.io/km-alee/afterward:<tag>` |
| | `.gitleaks.toml`, `.env.example` | |
| | `scripts/make_secrets.py`, `scripts/google_auth.py`, `scripts/openai_probe.py` | |
| Rules | `CONTRIBUTING-AGENTS.md` | Who owns which directories; contract change process; definition of done |

**Hello image:** tag `v0.0.1` → CI builds and pushes → you deploy it at **Checkpoint 1**.

### Checkpoint 1 (≈21:15, 5 minutes for you)
```bash
acc services create --kind docker --name afterward-app \
  --image ghcr.io/km-alee/afterward:0.0.1 --port 8000 --confidential \
  --env DATABASE_URL=<from afterward-db> --env APP_ENV=prod -y
acc services logs afterward-app --tail 100
acc attest <serviceId> --verify
```
- 📨 Send me: the **public URL**, whether `/health` and `/status` load (`/status` shows the database connection), and the **attest result** (pass / fail).
- If `--confidential` fails, re-run without it, and we state that honestly.

---

## Phase 2: four agents in parallel (original estimate ≈21:15–01:45)

**Start gate:** user-approved frontend mock merged from slice/frontend-mockup,
approval recorded by the lead, shared product foundation implemented and Python
contract revision 1 published. Until both gates pass, do not launch these slices.

Each agent:
- works in its **own git worktree and branch**;
- **owns specific directories** and does not edit the others' (contract changes go through me);
- must finish with **green tests** and a short handoff note (what works, what's stubbed, what to watch).

Every agent receives AFTERWARD.md, AFTERWARD-TECH.md, this plan, `CONTRIBUTING-AGENTS.md`, and its slice brief below.

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
8. **AI client on the OpenAI Agents SDK** (AFTERWARD-TECH §T8.0):
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

### Agent C: Mail & Integrations *(real email in and out)*
**Owns:** `app/mail/`, `app/integrations/`, `app/demo/provider_variants.py`, `scripts/google_auth.py` (finish), `tests/mail/`

**Builds:**
1. **Gmail client:**
   - refresh-token auth per mailbox;
   - **history-based polling** with a `messages.list` fallback;
   - `messages.get` with full MIME decoding;
   - `users.messages.send` with `threadId`, `In-Reply-To` and `References`;
   - footer with the disclosure and `Ref AW-<case>-<action>`;
   - `in:sent` search for reconciliation.
2. **Parsing:**
   - **latest-text extraction** (strip `>` quotes and "On … wrote:" blocks; hash the rest);
   - matching to case and account via thread → exact From / Reply-To → plus-tag;
   - **recipient check** (`approved` / `unapproved` / `reply_to_mismatch`);
   - an unsorted tray for unmatched messages.
3. **Inbound pipeline glue:** a new message → Agent A's extraction pipeline → outcome check → events. Uses Agent A's interfaces; stubbed until merge.
4. **Outbound effects:** `send_request` and `followup` executors that use Agent A's action records; hand-off steps for web-form and phone-only providers.
5. **Mailbox health:** last-poll age, token validity → `monitoring = interrupted` → a family notice through the `EventBus`.
6. **Provider console backend:** send a reply **as a demo provider** through the providers mailbox into the right thread, with the display name "Northline Mobile (demo)". Variants include:
   - the Northline "complete, new 24-month plan, voicemail will reset" reply;
   - acknowledgement;
   - probate-blocked;
   - certified-copy request;
   - April-invoice-for-February;
   - refund issued;
   - `Reply-To` mismatch;
   - a request for the will from an unknown address.

   Free-text replies are also supported.
7. **Calendar** (stretch inside this slice): `events.insert` with reminders, via action records.

**Done when:**
- MIME and quote-stripping tests pass on real-world sample emails (Gmail, Outlook-style quoting);
- the `FakeMailbox` end-to-end flow (send → provider-variant reply → match → extraction call → state change) passes;
- the live mail smoke script (`scripts/mail_smoke.py`) is ready for Checkpoint 2.

---

### Agent D: Web, Desk & Call room *(what judges see)*
**Owns:** `app/web/`, `app/call/`, `static/`, `tests/web/`, `tests/call/`. Loads the **frontend-design** skill if available.

**Design input:** the user-approved mock in `design/frontend/`, its UX.md/REVIEW.md,
and the lead's FRONTEND-APPROVAL record. Implement that design; do not redesign it
independently. Escalate material UX changes to the user.

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
5. **Call room** (`/call/{token}`) on the OpenAI Agents SDK realtime stack (AFTERWARD-TECH §T9):
   - `RealtimeAgent` on `gpt-realtime-2.1`, server-side WebSocket; browser audio relayed through our server;
   - tools `get_request_and_conditions`, `report_offered_terms`, `request_family_decision` (`needs_approval`), `request_human_help`, `end_call`; **no accept tool**;
   - **offered terms become `Fact`s** → outcome check → **decision card to Sara's chat** (via the `EventBus` → Agent B's gateway);
   - acceptance only as a server-built sentence synthesised with `gpt-4o-mini-tts`, model audio suppressed while it plays;
   - realtime output guardrail as the commitment guard (cancels the response; player stops on `audio_interrupted`);
   - **suspended on new representative speech**; terms hash re-checked before audio plays; obsolete audio discarded;
   - typed fallback via `send_message`; per-stage latency from SDK events;
   - stretch: Twilio Media Streams transport for a real outbound call to the provider's approved number (`PHONE_CALLS_ENABLED`).
6. **Landing page** with the demo passcode; `/status` page styling.

**Done when:**
- pages render with fake data;
- WebSocket events update live;
- call-room tests pass: the model can't accept; changed terms void the approval before acceptance; obsolete audio is discarded; a typed turn works end to end on fakes.

---

### Lead during Phase 2
- Keeps contracts stable and answers agents' contract-change requests (each one applied once, centrally, and broadcast to all agents).
- Reviews each agent's diff for overclaims and safety rules (no model output can widen permissions, no secrets in logs).
- Pre-writes the **full-story integration test** (the 6-minute demo as an automated test on fakes) so Phase 3 starts with a target.

---

## Phase 3: integration and first real deploy (lead, ≈01:45–03:45)

1. **Merge order:** A → C → B → D. After each merge: full test suite, then the proof suite on fakes.
2. **Wire the real implementations:** OpenAI `AIClient`, Gmail `Mailbox`, Telegram and WhatsApp `Channel`s behind the contracts; worker loops in the lifespan.
3. **Full-story test green on fakes:**
   - Sara's voice note → intake → candidates → Amina's dependency → plan v2 → approval;
   - send → Northline's contradictory reply → **not done** → decision → call → terms change voids approval → re-approval → template acceptance;
   - clock +14 days → FitLife follow-up;
   - City Power April-for-February bill → needs review;
   - refund issued → awaiting receipt;
   - "did you finish everything?".
4. **Tag `v0.1.0`** → CI → image.

### Checkpoint 2 (≈03:00, ~20 minutes for you)
1. Set the variables (exact list from AFTERWARD-TECH §T14; I'll give you a ready list of `acc services env set …` lines with blanks):
   - `OPENAI_API_KEY`;
   - Telegram token and webhook secret;
   - WhatsApp token, app secret, verify token, phone number ID;
   - Google client ID and secret plus both refresh tokens;
   - `VAULT_KEY`, `DEMO_PASSCODE`, `PUBLIC_BASE_URL`, both mailbox addresses.
2. Deploy:
   ```bash
   acc services deploy <serviceId> --image ghcr.io/km-alee/afterward:0.1.0
   python scripts/set_webhooks.py            # Telegram setWebhook + prints the WhatsApp webhook URL to paste into Meta
   python scripts/openai_probe.py --remote   # asks the deployed /status to probe all four models
   python scripts/mail_smoke.py --remote     # send + receive one email between the two demo mailboxes
   ```
3. **Phone smoke test:** send the bot a voice note from Sara's phone; Amina joins via the invite link; tap one button.
4. 📨 Send me the outputs (no secrets are printed).

---

## Phase 4: QA agent and fixes (≈03:45–08:00)

### QA agent: Adversarial reviewer *(fresh eyes, hasn't seen the build)*
**Gets:** the repo, both specs and the deployed URL (if reachable), plus fakes. **Doesn't get:** the agents' reasoning.

**Does:**
1. **Reads the claims** in AFTERWARD.md §11 and §15 and tries to break each one in code: permission widening via email content, approvals surviving a plan change, ambiguous replies marked done, duplicate sends, quiet/hold leaks, secrets in logs.
2. **Chaos checks:** kills the worker right after a send (→ uncertain → reconciled); restarts mid-case; revokes consent with a queued job; expired mailbox token → monitoring interrupted.
3. **Demo-consistency audit:** every line of the 6-minute script is checked against actual behaviour and configured intervals (AFTERWARD.md §14.1).
4. **Output:** a ranked findings list with failing tests attached. **No fixes**; the lead fixes, so the reviewer stays independent.

**Lead:** fixes in severity order → `v0.2.0` → proof panel green on the deployed URL → latency measured from venue-like Wi-Fi.

---

## Phase 5: rehearsal, freeze and submit (08:00–12:45)

### Checkpoint 3: rehearsal ×3 (08:00–10:00)
- Run AFTERWARD.md §14.2 exactly, timed, on the real phones and the deployed URL.
- After each run, list the rough edges. I fix only those (no new features after 09:30).
- Do one run with a **teammate playing the judge**, who improvises provider replies and call lines, to make sure nothing is scripted to a single path.

### 10:00–12:00
- **Me:**
  - README (setup, architecture diagram, honest claims, **credits**, demo login);
  - final tag `v1.0.0` and its image;
  - record the image tag and commit SHA for the PDF.
- **You:**
  - the 2–3 minute video (cold open on the caught contradiction, per AFTERWARD.md §14.3);
  - PDF;
  - screenshots (Alternate Clouds dashboard, Discord);
  - **the LinkedIn post, written by you** (I won't draft it); the teammate reshares.

**12:00 freeze. No deploys after this. 12:45 submit.** Keep the service running until the closing ceremony.

---

## Cut list (in this order, if we fall behind)
1. WhatsApp adapter (Telegram carries the demo).
2. Calendar.
3. Weekly digest.
4. Spoken replies to the family.
5. Family web view polish.
6. Confidential mode (deploy standard, state it honestly).

**Never cut:** outcome check · plan versions and approval voiding · Northline contradiction flow · proof panel · deployment on Alternate Clouds.

## Risks specific to this plan
| Risk | Mitigation |
|---|---|
| The build environment can't reach OpenAI, Telegram or Google | Agents build against contracts, fakes and recorded payloads. Live checks happen at Checkpoints 2–3 (or on your laptop if linked). |
| Merge conflicts between agents | Directory ownership, frozen contracts, one merge order. |
| An agent drifts into overclaims or extra features | Each brief has a definition of done, and the lead reviews diffs against AFTERWARD.md §11. |
| Checkpoints slip because you're asleep | Checkpoint 2 is the only night one (~03:00). If you can't make it, I continue on fakes and we deploy at 08:00, which is tighter but workable. |

## Planning addendum: external MCP service (16 Oct 2026)

Requested by the team: use fastn MCP only where it adds a working secondary
integration. No n8n dependency for this build. Direct Gmail/Calendar APIs remain
the baseline; do not move critical mail/reconciliation onto unverified tools.

- Owner: C in app/integrations/; lead owns dependencies, config, contracts and wiring.
- Start only after the core story and 14 proof tests pass. Time-box to 45 minutes;
  no new features after 09:30 PKT, and never delay the 12:00 freeze.
- Deliver one useful tool-backed integration: an explicitly approved calendar
  reminder OR an opt-in status-only spreadsheet mirror (no bodies or documents).
- Human prerequisite: fastn account and connected demo Google account. The lead
  verifies the exact tool ID, input schema, scopes, auth/expiry, runtime-client
  compatibility and any price/quota before accepting the adapter.
- The model may propose the operation; code resolves an allowlisted tool and fixed
  destinations from approved state, rechecks permission and reserves an action
  record before execution. No arbitrary discovery-and-execute or flow management.
- Tests: fake MCP responses, rejected unknown tool/destination, revoked consent,
  expired auth and uncertain delivery. A real demo-account smoke check is required
  before claiming it works. Audit tool kind/action ID only; never OAuth values.
- Done when: one real approved operation is evidenced, deterministic tests pass,
  README names fastn/MCP and the handoff states limits. Otherwise omit the feature
  and state that it is not integrated. Do not create a cosmetic MCP claim.
- Setup scaffold adds no fastn SDK, credentials or endpoint; the lead later records
  any required env variables/dependencies through the contract change process.

See [ADR-009](DECISIONS.md#adr-009-optional-external-mcp-integration).
