# Frontend prototype: review pack

**State:** the user reviewed revision 2 and asked for it to be merged (2026-10-16). Further UX
changes go to the user.

- Branch: `slice/frontend-mockup`, merged into `main`.
- Preview: `python3 -m http.server 8080 --bind 127.0.0.1 --directory design/frontend`, then open
  http://127.0.0.1:8080/. No build, no network, fictional data, nothing sent.

## How to try it

- **Start the story** on the start page, or use **Story** in the top bar to jump to any step.
- Open the desk and the family app in two tabs: actions in one appear in the other.
- Passcode: anything works; `wrong` and `offline` show the error states.

## What changed in revision 2

Less text, no page scrolling, clearer flow. Details in UX.md "Revision 2" and DESIGN-GUIDE §10.
Original light theme, logo and navigation kept.

## Flows covered

Sara's voice note → 9 candidates → Amina's answer → plan change → specific approval →
Northline's "done" → **not done** → call → offer → Sara approves → offer changes, approval void,
queued acceptance discarded → re-approval → acceptance in the approved wording → written
confirmation. Also: +14 days fires one FitLife follow-up; a lost send is checked and reconciled;
mailbox disconnected; February bill needs review; refund pending; suspicious email held;
certified copy needed; "Where are we?" summary.

## Checks run (headless Chromium, Playwright)

| Check | Result |
|---|---|
| End-to-end click-through of the whole story and the extra states, across tabs | 34/34 pass, no page errors |
| One screen, no page scroll | Fits at 1920×1080, 1440×900, 1366×768, 1024×768, 1280×720 projector; family app at 390×844 |
| axe-core (WCAG 2.0–2.2 A/AA + best practice), 13 page states and 10 open drawers, light and dark | 0 violations |
| Keyboard | Every tab stop shows focus; drawers take focus and return it on close |
| Reduced motion | Animations off |

Not checked: real screen readers, Firefox/Safari, real phones or a real projector.
`make ci` and pre-commit results are in the handoff.

## Known limitations

- Scripted mock: free text isn't understood (it's marked for review); "Change" and "Fix
  something" aren't built.
- At 1280×720 in projector mode the nav wraps to two lines, so "Now" scrolls inside its panel.
- Phones scroll normally on the desk, call room, provider console and proofs; only the family app
  is phone-first.

## Screenshots

`screenshots/01`–`17`: start, family (phone and desktop, including the changed-offer card and
the summary sheet), desk (normal, projector, account drawer, banners, dark), call room, provider
console, proofs and style guide.

## For Agent D

Follow DESIGN-GUIDE §9 and §10. Copy CSS, fonts, icons and brand assets into `static/`; turn the
page scripts' templates into Jinja partials; replace the mock store with server state and
WebSocket updates; remove the prototype bar, Story dialog, demo shortcuts and failure toggles.
