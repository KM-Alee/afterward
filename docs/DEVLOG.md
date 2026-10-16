# Development log

Append only, newest at the bottom. Times are PKT.
Format: `- YYYY-MM-DD HH:MM PKT [agent] what changed / why / next`

- 2026-10-16 20:27 PKT [Foundation] Started workflow scaffold and documented ownership, safety gates and source contracts / enable isolated overnight agent work without building features / verify tooling, CI, image and publish v0.0.1.
- 2026-10-16 20:36 PKT [Foundation] Finished repository scaffold, isolated Postgres tests, redacted JSON logging, CI/image workflows, worktree guards and agent briefs; local CI 31 passed, fast suite 28 passed, pre-commit clean and Docker health/DB/log smoke verified / provide a safe parallel development workflow / push main and v0.0.1, inspect Actions; lead implements shared product foundation before launching A–D.
- 2026-10-16 20:41 PKT [Foundation] Added mandatory frontend-first Claude branch guide, UX review record, ownership and tool support / user requires polished mock UX approval before parallel development / Claude creates mocks on slice/frontend-mockup; user reviews; lead freezes Python foundation; only then launch A–D.
- 2026-10-16 20:42 PKT [Foundation] Frontend-first workflow checks pass (32 full / 29 fast); original CI and v0.0.1 GHCR publish succeeded / preserve immutable release and user UX review gate / push planning follow-up, then user starts Claude via docs/FRONTEND-FIRST.md.
- 2026-10-16 21:45 PKT [Frontend UX] Built the standalone prototype on slice/frontend-mockup: original identity and SVG logo masters, tokens/components, desk, family view, call room, provider console, proof panel, entry and style guide with a replayable local mock story; UX.md, DESIGN-GUIDE.md, REVIEW.md and 24 screenshots; e2e 31/31, axe clean in both themes, focus and overflow checks pass, make ci 32 passed / pre-commit clean / give the user a reviewable, honest mock before parallel work / user reviews and explicitly approves or requests changes; no A/B/C/D launch.
