# Frontend prototype: review pack

**State: ready for user review. Not approved.** Only the user can approve, and only the lead
records it in docs/FRONTEND-APPROVAL.md. Nothing here starts A/B/C/D.

- Branch: `slice/frontend-mockup` (worktree `../afterward-frontend-mockup`)
- Pages and assets last changed in commit `1303226`; documentation commits follow it. Review the branch head.
- Remote: https://github.com/KM-Alee/afterward/tree/slice/frontend-mockup

## 1. How to preview

From the repository root of the worktree:

```sh
python3 -m http.server 8080 --bind 127.0.0.1 --directory design/frontend
```

Open http://127.0.0.1:8080/. No build step, no network access, no credentials. Everything is
fictional and every interaction changes only local state in your browser (`localStorage`).

- **Fastest path:** on the start page choose **Start from the beginning**, or open the
  **Story guide** (hatched bar at the top of every page) and use **Set up and open** on any step.
- **Two tabs:** open the desk in one tab and the family view in another. Approvals made as
  Sara appear on the desk immediately (this stands in for the real WebSocket updates).
- **Reset:** Story guide → **Reset to the start**.
- **Theme:** the bar's Auto / Light / Dark buttons. **Projector:** desk → **Projector mode**.
- Passcode form: any value enters; `wrong` and `offline` show the error and retry states.

## 2. Design rationale (short)

- **First light.** A half-disc on a horizon, with arcs carrying one message outward. Linen paper,
  pine ink, one warm dawn accent. Calm and plain, never celebratory. See DESIGN-GUIDE.md §1.
- **Evidence looks different from interface.** Providers' words and family voice notes are set in
  Newsreader serif; the interface is Atkinson Hyperlegible (chosen for older readers and projectors).
- **The desk is a ledger, not a dashboard.** One focal "Now" panel shows *Requested → Northline
  says → Afterward concludes*; accounts are rows with four dimensions; the timeline carries
  evidence labels. No grid of equal cards.
- **The family view is a feed of chat cards.** One "Needs you" area at the top, at most three
  choices per card, consequences written into the options.
- **Simulation is visible.** A diagonal hatch and the word "Simulated" mark every fake send,
  transcript, call, timing and preview result.

## 3. Completed flows

Core story (each step is reachable from the Story guide):

| # | Step | Where | What to look for |
|---|---|---|---|
| 1 | Sara's voice note becomes the case | Family · Sara | Transcript labelled simulated; "as you've told me"; That's right / Fix something |
| 2 | 9 candidates, 3 need ownership | Family · Sara; desk Coverage | Per-candidate "Whose is this?" (3 choices); "This list isn't complete" |
| 3 | Amina answers | Family · Amina | Simulated voice note or typed answer; "Here's what I understood" with shared service / access / memory; no approve buttons for Amina |
| 4 | Plan v1 → v2 | Family · Sara; desk | Struck-through v1, v2 on dawn; Crescent "don't close" |
| 5 | Specific approval | Family · Sara | Exact address and source, documents with form (photo), consequence, fallback, plan v2 + hash |
| 6 | Northline "complete" | Provider console | Prepared variants with purpose; simulated send confirmation |
| 7 | Not done | Desk | Verdict "Not done"; voicemail violated, 24-month plan unauthorised, number not stated; quote highlights |
| 8 | Call decision | Family · Sara | Exactly three options with consequences |
| 9 | Offer on the call | Call room | AI disclosure; hold to talk / Space; agent pauses: "Checking with the family" |
| 10 | Sara approves T1 | Family (or the call room's prototype shortcut) | Card bound to terms T1 + hash; acceptance queued in the call room |
| 11 | Terms change | Call room | "Acceptance audio for T1 discarded before playing"; T1 void; Sara's card shows "This changed. Here's why." with a disabled button |
| 12 | Re-approval | Family → call room | Acceptance spoken from the server template with T2 terms; "Not done yet" until written confirmation |

Side scenarios: written confirmation → resolved with evidence (provider console);
**+14 days** fires exactly one FitLife follow-up; **delivery uncertain** → Sent-folder check →
reconciled; **monitoring interrupted** on desk and family; **April invoice for February service**
→ needs review, no dispute; **refund issued** → awaiting receipt (both money items visible);
**incomplete coverage**; **"Did you finish everything?"** answered from current state with the
"haven't searched" caveat. Also: unknown-address email asking for the will is held; certified-copy
request shows "requirement unmet"; free-text provider replies become "needs review (ambiguous)".

## 4. Screenshots and tested sizes

All in `screenshots/` (captured with headless Chromium from the served pages):

| File | Size | Shows |
|---|---|---|
| 01-entry-desktop | 1440×900 | Start page, passcode form |
| 02-desk-not-done-desktop | 1440×900 | Desk after Northline's reply |
| 03-desk-not-done-projector-1280x720 | 1280×720, projector mode | Same at projector size |
| 04-desk-ledger-desktop | 1440×900 | Four-dimension ledger |
| 05-desk-banners-desktop | 1440×900 | Monitoring interrupted + delivery uncertain |
| 06-desk-resolved-dark | 1440×900, dark | Resolved with written evidence |
| 07-desk-tablet / 08-desk-phone | 820×1180 / 390×844 | Narrow desk: Now first, ledger as cards |
| 09–15 family-* | 390×844 | Intake, Amina's question, plan change, approval, not done, stale approval, finished summary |
| 16-call-acceptance-ready / 17-call-approval-void | 1440×900 | Call room before and after the terms change |
| 18-call-phone | 390×844 | Call room on a phone |
| 19-provider-console | 1440×900 | Console with the contradictory reply selected |
| 20-proofs-not-run / 21-proofs-illustrative | 1440×900 | Honest default and illustrative states |
| 22/23-style-guide | 1440×900 | Style guide and logo usage |
| 24-family-dark-phone | 390×844, dark | Decision card in dark mode |

## 5. Verification performed

Automated with Playwright + headless Chromium against the served directory. The scripts were
run from a scratch directory and are not committed (adding them to the repo was declined
during this session); they can be added under `design/frontend/checks/` on request.

| Check | Result |
|---|---|
| End-to-end click-through of steps 1–12 and side scenarios using real clicks and keyboard, across separate tabs | 31/31 assertions pass, no console or page errors |
| axe-core 4.10 (wcag2a, wcag2aa, wcag21a/aa, wcag22aa, best-practice) on 13 page states × light and dark | 0 violations after fixes (found and fixed: missing h1 on family view, a sticky composer overlapping buttons, two low-contrast labels on the style guide) |
| Keyboard: Tab through every page; each stop checked for a visible focus indicator | 7 pages, 24–46 stops each, all visible; skip link is the first stop |
| Horizontal overflow and clipped content | 0 px at 320, 390, 768, 1024, 1280, 1440 and 1920 on all 8 pages, plus the desk in projector mode at 1024×768 and 1280×720 (found and fixed several implicit-grid overflows) |
| Reduced motion (`prefers-reduced-motion: reduce`) | Durations resolve to 0; orb animation stops |
| Contrast | Every token pair used for text ≥ 4.5:1, boundaries ≥ 3:1, both themes (live table on style.html) |
| Logo at small sizes | Favicon and compact mark rendered at 16/24/32/48 px on light and dark grounds and inspected |

**Not verified** (please weigh accordingly):

- Real screen readers (NVDA, VoiceOver, TalkBack): only the semantic structure and live regions
  were checked, not spoken output.
- Real devices, touch hardware, a physical projector, Firefox and Safari. Only Chromium was used.
- Browser-tab rendering of the favicon (PNG renders were inspected instead).
- Colour-blindness simulation and greyscale print, beyond the design rule that colour is never the only signal.
- `make ci` and pre-commit results are recorded in the handoff.

## 6. Known limitations

- The mock "AI" is scripted: free text in the provider console and call room isn't interpreted
  (and says so). Amina's typed answer is read the same way as the scripted one.
- "Change", "Fix something" and the plan editor are not built; they announce that instead.
- Only the Northline storyline is deep. Crescent Bank, Meridian Life and the second Northline line
  have ownership questions but no further flow.
- Quiet / Hold / Stop change banners and copy; they don't block mock actions.
- Case time advances by small fixed amounts per action, so timestamps are plausible, not exact.
- Mock state lives in `localStorage`; a private window starts fresh each time.

## 7. Remaining UX questions for the user

1. **Decision emphasis.** On the "not done" card the first option ("Ask them to keep the voicemail,
   no contract") is styled as primary, as the safe recommendation. Keep that, or make all three equal?
2. **Routine approvals.** After the Northline approval, the three routine closures (City Power,
   StreamBox, FitLife) appear as one card with three separate approvals. Is that the right moment?
3. **Projector mode.** Should the deployed desk start in projector mode, or keep it as a toggle?
4. **Persona switch.** The family view lets a reviewer switch between Sara and Amina. In production
   each person only sees their own cards. Confirm the web fallback needs no switch.
5. **Wordmark case.** The wordmark is lowercase ("afterward") for warmth; product copy uses "Afterward".
   Happy with that pairing?
6. **Dark mode** follows the system setting by default. Keep, or force light for the demo?

## 8. For Agent D (after approval only)

Read DESIGN-GUIDE.md §9 ("Implementation guide for Agent D"). In short: copy the CSS, fonts,
icons and brand assets into `static/` unchanged; turn the page scripts' template strings into
Jinja2 partials; replace the mock store with server state and WebSocket updates; remove the
prototype bar, Story guide, shortcuts and scenario toggles; keep every behaviour listed in §9.4;
propose any material UX change to the user first.
