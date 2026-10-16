# Parallel development ownership

Read [AGENTS.md](AGENTS.md), all three source docs and [contracts](docs/CONTRACTS.md)
fully before starting. Freeze: **2026-10-17 12:00 PKT**. Submission: **12:45 PKT**.

| Slice | Owned paths | Branch |
|---|---|---|
| Foundation / lead | root tooling/docs, .github/, .claude/, scripts except C's scripts, app/main.py, app/config.py, app/logging.py, app/db.py, app/models.py, app/contracts.py, app/ai/schemas.py, app/fakes/, app/demo/seed.py, tests/conftest.py, tests/foundation/ | main; optional slice/foundation |
| A Engine & Truth | app/engine/, app/ai/verify.py, app/ai/prompts.py (extraction), app/ai/client.py, app/demo/fixtures/, tests/engine/, tests/proofs/ | slice/engine-truth |
| B Channels & Conversation | app/channels/, app/conversation/, app/discovery/, tests/channels/, tests/conversation/ | slice/channels-conversation |
| C Mail & Integrations | app/mail/, app/integrations/, app/demo/provider_variants.py, scripts/google_auth.py, tests/mail/ | slice/mail-integrations |
| D Web/Desk/Call room | app/web/, app/call/, static/, tests/web/, tests/call/ | slice/web-desk-call |
| QA | tests/qa/, docs/handoffs/qa-adversary.md findings only; no production fixes | slice/qa-adversary |


Documentation exceptions: each agent edits only its own STATUS row and handoff file,
appends DEVLOG entries at the bottom, and may append a contract change request.
It cannot edit frozen contract text, another slice's state/log entry, or accepted ADRs.
Resolve documentation conflicts by preserving both chronological entries; never
replace another agent's status. All other cross-directory edits go to the lead.

The source briefs mention shared paths outside their ownership (A's probe script,
C's new mail_smoke.py, B's demo assets and D's main route wiring). The owning slice
provides the implementation proposal or content in its handoff; the lead applies
shared changes. Runtime routes are registered centrally in Phase 3. Never edit
app/main.py from a feature slice.

Before launch: the lead completes Python contracts, models, schemas and fakes,
then publishes revision 1 and a foundation commit SHA. Scaffold completion is not
that start signal. Each agent uses make worktree and make setup in its own checkout.
Use the dependency fakes; no production accounts or real personal data in tests.

Handoff: green make ci, clean Ruff, own handoff written, own STATUS row updated and
an appended DEVLOG entry. Rebase on main; do not push a rewritten branch with force.
The lead integrates **A → C → B → D**, running the full suite after every merge.
QA reports ranked findings with failing regression tests and never fixes production code.

No new features after 09:30 PKT; fixes and rehearsal only. No code or deployment
changes after 12:00 PKT; submit by 12:45. Keep the service alive through closing.
