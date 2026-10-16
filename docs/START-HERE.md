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

fastn is optional: test one approved calendar reminder or status-only mirror,
behind code-controlled permissions and action records, after core proofs pass.
Time-box to 45 minutes and drop it if unverified. No n8n deployment is required.
See IMPLEMENTATION.md planning addendum and ADR-009.
