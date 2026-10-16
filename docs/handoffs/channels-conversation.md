# Slice handoff: channels-conversation

Owner: Agent B
Branch: slice/channels-conversation
Updated: 2026-10-17 00:13 PKT

## What works

Family channels, conversation, discovery and vault intake on contract revision 1.
No frozen contract was edited. `make ci`: Ruff clean, 93 passed, real Postgres for
the existing database tests, no network.

- Telegram: `X-Telegram-Bot-Api-Secret-Token` checked in constant time, empty secret
  fails closed, inline keyboards (`d:<id>:<n>`, at most 64 bytes), `answerCallbackQuery`,
  `getFile` voice and photo download, `sendVoice` as `audio/ogg`, `sendChatAction`
  typing, and `getUpdates` polling fallback.
- WhatsApp: raw `hub.challenge`, `X-Hub-Signature-256` over the raw body, interactive
  reply buttons (max 3, title ≤ 20), media download with the bearer token, and a
  24-hour window guard. A bad signature raises `WebhookRejected` and returns no events.
- Audio: `ffmpeg -y -i in.ogg -c:a copy out.webm`, then `AIClient.transcribe` with
  `audio/webm`. The subprocess test ran on this machine because ffmpeg is installed.
- Conversation: tell-it-once confirmation card with a stated role, commands
  (`status`, `quiet`, `hold`, `stop`, `resume`, `help`), crisis care text with
  findahelpline.com and a pause, polite off-topic decline, free-text decisions read
  back as buttons, `/start <token>` joins Amina as household, dependency rules revise
  plan data, and an approval card with recipient, action, conditions, documents and
  consequence. "Did you finish everything?" only rephrases a summary dict.
- Weekly digest returns nothing on a quiet day, during `quiet_until`, or when the
  case is stopped.
- Discovery merges candidates only when `account_ref` matches. Coverage lists sources
  searched, sources not searched, unconfirmed candidates and where else to look.
- Vault: phone photos are stored as `photo`, mismatch flags are recorded, and the
  blob is Fernet ciphertext. A missing `VAULT_KEY` generates a key in memory only.
- Demo: Sara's and Amina's voice-note scripts, six labelled fictional forwards and
  four synthetic photo stand-ins. The fake script runs Sara's note → confirmed intake
  → 9 candidates with coverage → Amina's answer → revised plan data → approval card.
  Model text cannot add a recipient.

## What is stubbed

- No routes in `app/main.py`. The lead should mount `POST /webhooks/telegram`,
  `GET/POST /webhooks/whatsapp`, and call `TelegramChannel.show_typing` while a note
  is transcribed.
- Conversation, plan, approval and vault state are in memory. Agent A owns plan
  hashes, approval compare-and-set, jobs and the Postgres rows. This slice does not
  insert `plans`, `approvals` or `documents`.
- `HttpxTransport` is the live HTTP client and was not called. No live Telegram,
  WhatsApp or OpenAI traffic.
- Demo "photos" are labelled byte stand-ins, not rendered images. Vision is the
  recorded `DocOut` on `FakeAI`.
- The weekly digest is a pure function. It is not a `digest` job.
- Outside the WhatsApp 24-hour window the adapter refuses free-form sends. Utility
  templates are not registered.
- Routing is deterministic code. Intake, dependency and document extraction use
  `AIClient.structured`. The Agents SDK `family_conversation` tool loop stays with
  Agent A's client.
- Quiet, hold and stop update in-memory controls. Agent A's policy module should
  apply the same meanings to the case row.

## How to test it

- `make ci` from this worktree: Ruff clean, 93 passed.
- `uv run --frozen pytest tests/channels tests/conversation`: recorded payloads,
  signature failures, the Malik script and the vault round trip.
- ffmpeg was present, so `test_ffmpeg_subprocess_repackages_without_reencode` ran.
  If ffmpeg is absent, that test skips; argument construction still runs.
- Live Telegram, WhatsApp and OpenAI were not called.

## Known risks

- Webhook secrets and the vault key must be set by the operator in the environment.
  Tests use obvious fake secrets and an in-memory Fernet key. Nothing was read from
  `.env` or `private/`.
- A generated vault key cannot decrypt data after the process exits. Production
  needs a stable `VAULT_KEY`.
- Household approve taps are refused here, but the engine must still bind approval
  to the plan version and hash. This card is not that compare-and-set.
- Two Northline references stay separate. A duplicate `4417` forward collapses to
  one candidate and does not confirm ownership.
- No contract change is requested.

## Files touched

`app/channels/`, `app/conversation/`, `app/discovery/`, `tests/channels/`,
`tests/conversation/`, this handoff, the Channels & Conversation row in
`docs/STATUS.md`, and one appended `docs/DEVLOG.md` line.
