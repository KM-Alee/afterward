# Slice handoff: foundation

Owner: Codex setup
Branch: main
Updated: 2026-10-16 20:36 PKT

## What works

Python 3.13 / uv frozen dependencies and production requirements; Postgres 17 compose;
health and safe status routes; secret-safe config; redacted JSON stdout, including
startup; pre-commit; push/PR CI and versioned GHCR image workflow; guarded worktree
and merge scripts; agent instructions/briefs, ownership, logs and ADRs.

## What is stubbed

Frontend-first sequence is now required: one Claude mock branch, explicit user UX
approval, then shared Python contract revision 1, then A/B/C/D. No mock pages or
new worktrees were created by setup. See docs/FRONTEND-FIRST.md.

All product features, tables, Python protocols, AI schemas, fakes, demo data,
OAuth/model/webhook/e2e helpers and the proof runner. Contract revision 0 documents
source boundaries; lead implementation/revision 1 is required before Phase 2.
The optional fastn integration is planned only, no credentials or SDK configured.

## How to test it

- make setup && make db-up && make ci: passed, 32 tests (real PostgreSQL).
- make test-fast: passed, 29 tests, 3 DB tests deselected.
- uv run --frozen pre-commit run --all-files: all hooks passed.
- gitleaks dir on staged tracked-tree export and git --all history: no leaks.
- git grep --cached for credential-like patterns: no matches.
- docker build -t afterward:0.0.1 .: passed.
- docker run -p 8000:8000 with the local compose network/database: health returned
  ok true; status DB reachable true; startup and request log lines parsed as JSON.
  Smoke container stopped afterward; development Postgres is left running.
- Disposable-repository tests prove failed CI leaves main untouched, a green
  rebased slice receives a --no-ff merge, and ignored private files are not copied.

## Known risks

The initial main/tag CI runs and v0.0.1 test/publish workflow succeeded:
https://github.com/KM-Alee/afterward/actions/runs/38925400952 and
https://github.com/KM-Alee/afterward/actions/runs/38925401202.
The frontend-first planning follow-up is a separate main commit; v0.0.1 is retained. No Alternate Clouds
service was deployed by this setup task. GHCR package visibility must be public
before that platform pulls it. External APIs/model availability are not probed.
The planned Stand-In source at /home/claude/standin is absent on this machine.
Human OAuth/account setup remains in docs/START-HERE.md. No real secrets were read,
generated or stored. The operator-only secret generator was deliberately not run.
The source T4/T8 prose leaves some exact types unresolved; lead resolves and
publishes them centrally before parallel feature implementation, preserving the
frozen safety requirements. No product agents were launched in this setup task.

## Files touched

See docs/FILES-CREATED.md for the file list, including the subsequent frontend-first
guide, approval record, command and empty handoff. README.md was updated;
source specs were relocated under docs/, with the authorized fastn plan appended.
