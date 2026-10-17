# Submission pack — Agentika 2.0, NaSCon'26

Deadline **12:45 PKT, 17 Oct 2026**. No code or deployment changes after submission.
Everything in [brackets] is for you to fill in. The LinkedIn post is written by the team
(project rule), so it is not drafted here.

## Checklist (in this order)

| # | Item | Who | Status |
|---|---|---|---|
| 1 | App live on Alternate Clouds, `/status` green | lead | in progress |
| 2 | Final git tag + image tag recorded (below) | lead | `v0.2.3` |
| 3 | Screenshot: Alternate Clouds dashboard showing service + deployment status (no env values visible) | you | |
| 4 | Screenshot: both teammates in the Alternate Futures Discord server | both | |
| 5 | 2–3 min video (unlisted YouTube or Drive), script below; no keys or passcode on screen | you | |
| 6 | LinkedIn post written by you; teammate reshares; copy both links | both | |
| 7 | Submission PDF (template below) with all links | you | |
| 8 | Keep the cloud service running until the closing ceremony | — | |

## PDF template

**Team KMForge** — names, emails, Discord usernames and the WhatsApp contact are in
`submission/team-details.md` (local only, git-ignored, since this repo is public).

**Project:** Afterward
**One-liner:** You tell it once. Afterward tells every organisation, follows up for months,
and checks each "done" against what the family actually approved.

**Problem and audience.** After a death, a family has to notify dozens of organisations —
phone, bank, utilities, subscriptions, insurers — repeat the same story each time, and
chase replies for months (13 months on average, about 20 with probate). Worse, organisations
say "done" when they did something else: a line "transferred" onto a new 24-month contract,
a voicemail wiped. Audience: the bereaved family member handling the estate, and the
household members whose phone, voicemail or logins depend on the deceased's accounts.

**Where the human comes in, and why.**
- The family states intent once (a Telegram voice note); the AI turns it into a plan.
- Household members answer "what could disappear?" questions (does anyone still use this
  number? does it receive bank login codes?) — only they know, and their answers change the plan.
- Every account is confirmed by the family; every request and every new term is approved
  explicitly. The AI can propose but cannot approve, accept terms, sign, move money or
  file legal/government paperwork — those are prepared and handed back to a person.
- On a voice call the agent can hear and record an offer but cannot accept it; the family
  decides, and only a server-built approved sentence is spoken.

**What makes it different.** Provider replies become structured commitments checked against
the family's approved plan and conditions; "done" means evidence plus every condition holding.
Honest coverage (what was searched and what wasn't — no "we found everything"). Durable
follow-ups that run by themselves for months.

**Built with**
- Custom code: Python 3.13, FastAPI, Jinja, PostgreSQL 17 (durable jobs, versioned approvals,
  audit events, encrypted documents), deployed on **Alternate Clouds** (Akash compute).
- OpenAI via the **Agents SDK**: structured agents (intake, dependency answers, reply reading,
  documents/vision, discovery agent with code-bound tools), **Realtime API over WebRTC** for
  the live voice call, transcription, text-to-speech.
- Models (as configured on the deployment; confirm with `/status`): [`gpt-6-luna`
  (fast/accurate), `gpt-transcribe` (voice notes), `gpt-realtime-2.1` (voice call),
  `gpt-4o-mini-transcribe` (call transcription), `gpt-4o-mini-tts` (speech)].
- APIs: Telegram Bot API, Gmail API, Google Calendar API, OpenAI API.
- MCP: none required by the product; [fastn used / not used — pick one].
- WhatsApp is not in this build.

**Links**
- Live deployment: [https://afterward-app-app.alternatefutures.ai]
- Judge login: demo passcode [passcode — put it only in the PDF]
- Telegram bot: [https://t.me/afterwardai_bot]
- GitHub: https://github.com/KM-Alee/afterward
- Release: git tag `v0.2.3`, image `ghcr.io/km-alee/afterward:0.2.3`
- Video: [link]
- LinkedIn post: [link] — reshare: [link]
- Presenter script / guided tour: `docs/SHOWCASE.md` in the repo

**Honest limits.** Fictional demo family; simulated parts are labelled (provider mailbox,
recorded model output when no key). The browser call is not a phone call. The speech check
reduces the risk of an implied agreement; it is not a guarantee. We never claim to find every
account. Legal, tax and government steps are prepared, not filed.

## Video script (≈2:30) — follows the 12-stop guided tour

Record the live deployment (or the laptop app) from Showcase → **Start the guided tour**.
Hide the passcode field and any dashboard env values. Full spoken lines are in `docs/SHOWCASE.md`.

1. **0:00–0:15 Paperwork after a death** — the problem in one sentence; press "Start a fresh case".
2. **0:15–0:35 You are Sara** — type/say the voice note; the summary appears with her quotes.
3. **0:35–0:55 Accounts found, and not found** — accounts from the inbox she allowed, and what was *not* searched.
4. **0:55–1:05 Sara confirms each one.**
5. **1:05–1:25 You are Amina** — "I still use that number, my bank codes go to it" → plan v1 becomes v2.
6. **1:25–1:35 Approve, send, keep checking.**
7. **1:35–1:55 You are Northline** — "Done — new 24-month plan, voicemail will reset."
8. **1:55–2:05 Done, but not really** — conditions broken; verdict: not done.
9. **2:05–2:20 Talk to the agent** — offer "12 months at $30"; it notes it and says the family decides.
10. **2:20–2:35 Two weeks later, by itself → people do the legal steps → "Did we finish everything?"**

LinkedIn screenshots (fictional demo data, page-only) are in `submission/screenshots/` — local
only; skim each before posting.

## Before 12:45

- Do not run `acc services deploy` after submitting.
- Rotate the cloud database password after the event (it was printed in a terminal once).
