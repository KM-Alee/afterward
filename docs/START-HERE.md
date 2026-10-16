# Operator setup before development

Deadline: 17 Oct 2026, 12:00 PKT code/deploy freeze; 12:45 submission. The agent
workflow can run on fakes while external accounts are prepared. Do not paste secrets
into chat, issue comments or logs. Configure them directly in Alternate Clouds.

## Accounts and human-only steps

| Item | Human prepares | Non-secret confirmation to share |
|---|---|---|
| GitHub | Repository access; Actions enabled with workflow package-write permission; GHCR package made public after its first build | Repository URL; image visibility; successful build link |
| Alternate Clouds | Login, project, funded/quota-ready account, managed Postgres and app service on port 8000; confidential attempt if available | Public app URL; DB variable exists yes/no; attestation pass/fail |
| OpenAI | API project/key and funded model access; independent of a ChatGPT subscription | API access ready yes/no; later probe results without values |
| Telegram | BotFather bot; token stored privately; two Telegram accounts/phones for Sara and Amina | Bot username |
| Google | Two team-controlled Gmail accounts; Cloud project; Gmail/Calendar APIs enabled; OAuth consent Testing with both test users; Desktop OAuth client | Both demo mailbox addresses; APIs/consent ready yes/no |
| WhatsApp (optional) | Meta developer app, test number, verified recipient phones, messaging token/app secret and webhook configuration | Phone number ID or skip |
| fastn (stretch) | fastn account and connected demo Google account; confirm tool availability/scopes and any quota/cost | Connection ready; no credentials |
| Stand-In | Supply accessible source repository/path and reuse rights | Repository/path and commit; planned /home/claude/standin is absent here |
| Submission | Team identities/contact details; both Discord memberships; dashboard/Discord screenshots; video host; human-written LinkedIn post and teammate reshare | Required links and non-secret metadata |

Agents can install dependencies and write scripts. They cannot complete human
account creation, CAPTCHA/phone verification, browser OAuth consent, billing,
account approvals or app-policy approval for you. Their environment also needs
network access and any organization policy approval. Never infer reachability
from having a key configured. Meta policy/token details are checked in setup,
not assumed from the planning document.

## Machine and automation prerequisites

- A machine that stays on overnight; reliable network; enough disk for Docker images.
- Git with push access, uv, GNU make and Docker Engine + Compose. The pinned
  gitleaks pre-commit hook runs in Docker; Linux merge script uses flock.
- Agents need access to this checkout and sibling worktree directories.
- Each worktree runs make setup. One shared local compose Postgres is sufficient;
  test sessions use distinct schemas. No production database in automated tests.
- GitHub Actions publishes with its ephemeral GITHUB_TOKEN; no registry password
  belongs in source. Actions must be allowed to write packages.
- Do not hand all agents production credentials. Default tests have no external
  network and use shared fakes once the lead implements them.

## Start sequence

1. Run make setup, make db-up and make ci. Check health/status locally.
2. Start one Claude frontend session on slice/frontend-mockup using FRONTEND-FIRST.md.
   Review the polished mock pages and their connected flows. The user explicitly
   approves; only the lead records approval in FRONTEND-APPROVAL.md. No A/B/C/D yet.
3. After UX approval, the lead completes Phase 1 shared models/contracts/schemas/fakes
   and publishes contract revision 1 with a commit SHA. Current stubs are not enough.
   Only then launch A/B/C/D in separate worktrees with their .claude/agents briefs. Feature
   owners stay inside CONTRIBUTING-AGENTS.md. No auto-launch is performed by setup.
4. Hello checkpoint: publish v0.0.1 image, make package public, deploy on Alternate
   Clouds, verify health/status and record the real attestation outcome.
5. Integrated checkpoint: operator performs Google consent with the implemented
   helper and configures all T14 environment variables; lead runs actual model,
   mail and phone smoke checks. google_auth.py/openai_probe.py/set_webhooks.py are
   placeholders now: invoking them does not configure anything.
6. Lead merges A → C → B → D through make merge; QA reports with failing tests;
   lead fixes. Rehearse at 08:00–10:00. No new features after 09:30.
7. Final tagged image before 12:00 freeze; record tag/SHA and submit by 12:45.

The operator can explicitly run `uv run python scripts/make_secrets.py` in a
private terminal to obtain VAULT_KEY, DEMO_PASSCODE, TELEGRAM_WEBHOOK_SECRET and
WHATSAPP_VERIFY_TOKEN. Never capture its output in project logs, CI or chat.
Do not rotate VAULT_KEY during the event. All .env.example entries are empty;
app configuration reads the process environment only.

Live demo, 17 Oct 2026: mail and calendar go through the connected Fastn
Gmail and Calendar accounts. Both family and providers roles use that one
address. The chosen mailbox is now `pabloman414@gmail.com`, with Gmail API and
Calendar API enabled on project `mehu-511820`. The one-time laptop consent
finished, and both refresh-token fields hold that token.
The app does not call Fastn yet; this records the operator choice.
No n8n deployment is required. See IMPLEMENTATION.md planning addendum and ADR-009.

The Gmail client in `mehu-511820` is a Web client. Its authorized redirect
URI `http://localhost:8765/` exists only so this laptop can finish the
one-time browser consent. Google returns a refresh token to that local page.
The running app, including a later deploy, sends and reads mail with that
token. It does not send anyone to `localhost:8765`, and the deployed host
does not need that address to be reachable.

Keep the localhost redirect on the client so a new token can be minted from
a laptop. Copy the client id, client secret, and refresh token into the
host environment when deploying. Add a public redirect URI only if a future
login page on the deployed host must run the browser consent itself. The
current mail code does not. The Cloudflare tunnel address is for Telegram
and is a different setting from this Gmail redirect.

## Temporary public URL (17 Oct 2026, about 02:00 PKT)

This is a laptop tunnel, not the deploy. It stops when `cloudflared` or the
app process stops, and the address changes the next time the tunnel starts.

1. Local Postgres was already up. `.env` had no `DATABASE_URL`, so the app was
   started with `postgresql+psycopg://afterward@127.0.0.1:5432/afterward` plus
   the other values already in `.env`. The app does not load `.env` by itself.
2. `uvicorn app.main:app` listens on `127.0.0.1:8000`.
3. `cloudflared tunnel --url http://127.0.0.1:8000` printed
   `https://haven-dave-normal-expo.trycloudflare.com`. That value is
   `PUBLIC_BASE_URL` in the local env.
4. Telegram `setWebhook` points at `${PUBLIC_BASE_URL}/webhooks/telegram` and
   sends the existing webhook secret. The bot is `@afterwardai_bot`.

Checked through that URL: `/health` and `/status` (database reachable), desk
login, family, call room, provider console, and the proof run (14 pass, 0
fail). A webhook with no secret got 401. A signed text update got 200 and the
intake card. The same update id a second time returned without calling the
model again. A button press got 200. One synthetic Gmail message,
subject "Afterward live check", was sent and then found in the inbox through
Fastn. The running app still cannot send that mail itself until a Google
refresh token is in the environment.

The webhook now accepts text, buttons, voice notes and photos. A file that is
not a picture is refused in one sentence and is not stored. A failed Telegram
send is logged as `channel.send` and does not fail the webhook. The live
conversation uses the Malik date, 3 March 2026, so a matching quote is shown
as that date rather than the whole sentence.

## Alternate Clouds deploy (not done yet)

Status at 03:30 PKT, 17 Oct: `acc` is signed in to project `afterward`. The project
has one service, `afterward-db`, and it is stopped. There is no app service, so
nothing is deployed. The laptop tunnel is still the only public URL. The current
work on `main` is not pushed, and a GitHub service builds the pushed branch.

Operator steps. Type secret values only into the dashboard, never into chat, a
shell command line or a commit:

1. Commit and push `main` once tests are green, so the build includes this work.
2. Start `afterward-db` in the dashboard, or run `acc services deploy afterward-db`.
3. Create the app service from the GitHub repository on branch `main`. It builds
   from the `Dockerfile` and listens on port **8000**. Set the service port to 8000.
4. Link the database: `acc services link <app-service> afterward-db`. Set
   `DATABASE_URL` to the linked connection string in the dashboard.
5. In the dashboard, set the variables by name: `APP_ENV`, `PUBLIC_BASE_URL`,
   `OPENAI_API_KEY`, `LLM_FAST_MODEL`, `LLM_ACCURATE_MODEL`, `STT_MODEL`, `TTS_MODEL`,
   `REALTIME_MODEL`, `AGENTS_TRACING=false`, `TELEGRAM_BOT_TOKEN`,
   `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_MODE=webhook`, `GOOGLE_CLIENT_ID`,
   `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN_FAMILY`,
   `GOOGLE_REFRESH_TOKEN_PROVIDERS`, `FAMILY_MAILBOX`, `PROVIDERS_MAILBOX`,
   `VAULT_KEY`, `DEMO_PASSCODE`, `PHONE_CALLS_ENABLED=false`. Leave the WhatsApp
   and Twilio entries empty.
6. Click **Rebuild**, then **Deploy**. Wait for the deploy to show running.
7. Set `PUBLIC_BASE_URL` to the service URL the dashboard shows. Redeploy so the
   family links in Telegram messages use it.
8. Point Telegram at the deploy: call `setWebhook` with
   `url=<PUBLIC_BASE_URL>/webhooks/telegram` and the same webhook secret. Do it
   from a private shell that does not echo the token.
9. Check `/health`, `/status` (`db_reachable: true`, `mail: configured`), the desk
   login, and **Run proofs** (14 pass). Only then call it deployed.

## One-story demo path (6 minutes)

Press **Reset demo** on the desk first. Then:

1. Telegram, Sara: send the story once (voice or text). Press Confirm.
2. Telegram, Amina: open the invite (`/start amina-demo-invite`). She is asked
   about line 4417 straight away. Her answer changes the plan, and the desk shows
   it as the new plan version.
3. Telegram, Sara: press Approve. The request goes out by Gmail, one Calendar
   reminder is added, and the desk shows "Waiting for Northline's written reply".
4. Provider console: send "Done, but changed" as Northline. The desk shows the
   reply beside the plan: voicemail kept Broken, no new contract Broken, number
   Not stated. It is not done. Sara gets a Telegram note with the family-card link.
5. Call room: join and offer "$30". The agent replies through the live realtime
   model (text) and cannot accept. Sara approves that exact offer on the family
   card. Change it to "$35": the old approval is void and its sentence is not
   spoken. Approve again, press continue, and only the fixed sentence plays.
6. Desk: +14 days sends one FitLife follow-up and finds it in Sent. Run proofs:
   14 cases. "Did we finish?" gives the honest answer.
