# Frontend first: Claude branch guide

This is the required next stage. Do not launch A/B/C/D yet. The user wants to
review a carefully considered, polished mock experience before parallel development.
This document is a guide; the workflow setup task does not build these pages.

## Sequence and release gates

1. Workflow scaffold on main (complete).
2. One Claude session builds the frontend prototype on **slice/frontend-mockup**,
   worktree **../afterward-frontend-mockup**. Human account setup can continue.
3. Claude demonstrates the mock flows and records its UX decisions. The user reviews,
   requests changes as needed, and explicitly approves. Silence is not approval.
   Only the lead records that approval and the reviewed commit in
   [FRONTEND-APPROVAL.md](FRONTEND-APPROVAL.md).
4. Lead merges the approved mock branch through make merge, implements shared
   product models/contracts/AI schemas/fakes, and publishes contract revision 1.
5. Only after **both** the UX approval and the shared-code contract gate are met,
   create A/B/C/D worktrees from the resulting main commit. D implements the approved
   design and production behavior; all slices use the same names and user flows.
6. Integrate A → C → B → D, then independent QA, rehearsal and final release.

No timetable can override these gates. Aim for a focused 45–60 minute first mock
pass and short review iterations; reduce optional surfaces if time is tight. Freeze
remains 17 Oct 2026 12:00 PKT; submission 12:45. No new features after 09:30.

## Branch commands (when the user starts Claude)

From main:

```sh
make worktree SLICE=frontend-mockup
cd ../afterward-frontend-mockup
make setup
```

Claude owns **design/frontend/** only, its handoff file, its STATUS row and appended
DEVLOG entries. It may read public tracked specs and source. It must not edit app/,
shared contracts, database models, runtime routes, CI, dependencies or other slices.
Keep the main FastAPI shell at health/status only during this prototype stage.

Use standalone HTML/CSS/vanilla JS with synthetic fixture data. Prefer no frontend
build step or remote dependency; this keeps the approved design portable into the
planned Jinja2/vanilla JS app. Prototype interactions change local mock state only.
No real API calls, OAuth, mail/chat sends, microphone uploads or secrets. Label all
mock integrations, data, transcripts, proof results and latency as simulated.

Suggested files, created by Claude later:

- design/frontend/index.html: navigation and scenario launcher.
- design/frontend/desk.html, family.html, call.html, provider.html, proofs.html.
- design/frontend/assets/: shared styling, icons and interaction helpers.
- design/frontend/fixtures/: fictional case and scenario data.
- design/frontend/UX.md: flow map, design rationale, page/state inventory and responsive rules.
- design/frontend/REVIEW.md: preview instructions, tested flows, screenshots/locations,
  remaining questions, keyboard/mobile issues and exact commit for review.

Once the pages exist, preview only their directory (never serve the repository root):

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory design/frontend
```

## UX brief: think through the experience before styling

Read AFTERWARD.md fully, especially §§4, 7, 8.3, 10, 11 and 14.2. Start by writing
in UX.md who each page serves, the decisions they must make, the primary action,
state transitions and failure paths. Establish a deliberate visual direction,
typographic hierarchy, spacing, color/contrast and reusable cards/banners/buttons.
Aim for calm, distinct and polished; avoid a generic dashboard full of equal cards.
Use findahelpline.com only as the specified support destination, not as a live call.
If a frontend design skill is available, use it; otherwise state that limitation
and proceed with the product brief rather than inventing a nonexistent skill.

Design and demonstrate:

- **Desk:** projector-readable case summary and plan; clear four-dimension account
  status; requested/provider evidence/outcome comparison; readable timeline;
  monitoring-interrupted and delivery-uncertain banners; labelled demo case clock.
- **Family:** phone-first intake confirmation, candidate coverage, dependency answer,
  changed plan, specific approval and fresh-decision cards. Limit choices to three.
  Approval must make recipient, action, conditions, disclosure and consequence clear.
- **Call room:** AI disclosure, simulated-provider label, push-to-talk affordance,
  typed fallback, listening/thinking/speaking states, decision pause, changed terms,
  voided approval and discarded obsolete audio. No real recording or TTS is needed.
- **Provider console:** fictional provider/thread selection, reply variants, custom
  reply input and visible simulated send confirmation; no actual messages sent.
- **Proof panel:** honest mock pass/fail/error/pending states and fixture evidence,
  clearly labelled preview data. Do not present 14 real tests as passed.
- **Entry/access screens:** passcode form appearance only, clear role navigation,
  empty/loading/error/retry states and straightforward paths back to the case.

The mock must allow a reviewer to click through the core story: Sara intake →
candidates → Amina dependency → revised plan → approval → contradictory Northline
reply → not done → call decision → changed terms invalidate approval → re-approval.
Also show February-service April bill as needs review, issued refund awaiting
receipt, incomplete coverage, and the honest "did you finish everything?" summary.
Mock time advancement must be explicitly labelled; no unsupported success claims.

## Review bar and handoff

Check desktop/projector and phone widths, keyboard-only use, visible focus,
legible contrast, button labels, long text, reduced motion and accessible state
announcements. Do not rely on color alone. Review copy for English, sensitivity,
stated roles, photo/certified-copy distinction and simulated-call disclosure.
Keep fictional names/provider labels consistent across all pages.

Run make ci and pre-commit without changing the shell. Record browser checks,
representative screenshots and any tools unavailable in REVIEW.md. Write
[the handoff](handoffs/frontend-mockup.md), update the Frontend UX row to review,
and append DEVLOG. Ask the user to review the actual pages; do not self-approve.
A pretty screenshot alone is insufficient: demonstrate the connected mock flows.

After explicit approval is recorded, the lead runs `make merge SLICE=frontend-mockup`
from clean main. The script rebases and runs CI; the human UX gate remains a separate
lead responsibility and must never be inferred from automated tests.

After approval, D owns implementation inside its existing paths. The lead handles
moving any shared assets/contracts or registering routes. Preserve approved UX;
propose material UX changes to the user instead of silently redesigning it.

## Ready-to-paste Claude brief

> Read AGENTS.md, the three docs, and docs/FRONTEND-FIRST.md fully. Work only on
> slice/frontend-mockup in ../afterward-frontend-mockup. Think through the UX and
> create polished standalone mock pages under design/frontend/ using fictional
> data and local simulated interactions. Build no backend features or live
> integrations. Demonstrate the specified flows/states, verify desktop/phone and
> keyboard use, write UX.md/REVIEW.md and the handoff, then stop for my review.
> Do not launch the parallel implementation agents or claim approval yourself.
