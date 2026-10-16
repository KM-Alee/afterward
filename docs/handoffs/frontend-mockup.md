# Slice handoff: frontend-mockup

Owner: Claude (frontend UX prototype)
Branch: slice/frontend-mockup
Commit: branch head (pages last changed in 1303226; this handoff and the docs follow)
Updated: 2026-10-16 21:45 PKT

**State: review. Awaiting explicit user approval.** Not approved, not merged. Do not launch
A/B/C/D on the strength of this handoff.

## What works

- Standalone prototype in `design/frontend/` (HTML/CSS/vanilla JS, no build step, no remote
  requests): entry/access (`index.html`), case desk (`desk.html`), family view (`family.html`),
  call room (`call.html`), provider console (`provider.html`), proof panel (`proofs.html`) and
  visual style guide (`style.html`).
- Original identity: SVG masters for symbol, wordmark (outlined Newsreader), lockups (horizontal,
  stacked), compact mark, light/dark/mono variants, app icons, favicon set, PNG exports.
- Design system: tokens (light, dark, projector), base, components, page layouts; self-hosted
  OFL fonts with licence files; original icon sprite.
- A replayable mock store shared across tabs drives the whole connected story (steps 1–12) and
  the side scenarios; the Story guide can set up any step.
- Documentation: `UX.md` (experience first), `DESIGN-GUIDE.md` (system + Agent D implementation
  guide), `REVIEW.md` (preview, flows, screenshots, verification, open questions), 24 screenshots.

## What is stubbed

Everything behind the interface is simulated and labelled as such: transcripts, AI readings,
sends, the call (no microphone, no TTS), latency figures and proof results (default "not run";
illustrative states are opt-in). "Change", "Fix something" and the plan editor only announce
that they aren't built. No Python, routes, contracts, models or dependencies were touched.

## How to test it

- Preview: `python3 -m http.server 8080 --bind 127.0.0.1 --directory design/frontend`.
- `make ci`: lint clean, 32 passed (2026-10-16 21:45 PKT, local Postgres up).
- `uv run --frozen pre-commit run --all-files`: all hooks passed, including gitleaks.
- Browser checks (headless Chromium via Playwright, scripts not committed): end-to-end
  click-through 31/31; axe-core 0 violations on 13 states in light and dark; every tab stop shows
  focus; no horizontal overflow from 320 to 1920 px including projector mode; reduced motion honoured.
- Not verified: real screen readers, Firefox/Safari, physical devices or a projector.

## Known risks

- No contract change requests. The prototype invents no backend contract; DESIGN-GUIDE §9.3 maps
  mock fields to the existing T4 tables only as guidance for D and the lead.
- Open UX questions for the user are listed in REVIEW.md §7.
- D must copy assets into `static/` (its own path); anything shared goes through the lead.

## Files touched

- `design/frontend/**` (new)
- `docs/handoffs/frontend-mockup.md` (this file)
- `docs/STATUS.md` (Frontend UX row only)
- `docs/DEVLOG.md` (appended entry)
