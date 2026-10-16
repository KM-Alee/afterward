# Afterward: UX design (prototype)

Status: **prototype for review**. Everything here uses fictional data and local
simulated interactions. Nothing in the prototype sends messages or calls an API,
and it doesn't record audio or authenticate anyone. This document comes first:
the pages implement it, and [DESIGN-GUIDE.md](DESIGN-GUIDE.md) describes how they look.

Sources: docs/AFTERWARD.md (§§4, 7, 8.3, 10, 11, 14), AFTERWARD-TECH.md (T5, T9, T10),
FRONTEND-FIRST.md. Where this document makes a choice the specs leave open, it says so
under "Decisions" so the reviewer can overrule it.

---

## 1. Who each surface serves

| Surface | File | Person | Context | What they must accomplish | Primary action |
|---|---|---|---|---|---|
| Entry and access | `index.html` | Judges, the team, reviewers | Laptop, first visit | Understand what Afterward is in one screen, enter the demo passcode, pick the right surface, or follow the story | **Enter** (passcode), then **Open the desk** |
| Case desk | `desk.html` | Judges on a projector; Sara at a desk | Shared screen, 3–6 m away | See what the family asked for, what each organisation said, and whether it matches. See what is waiting and on whom. | Read; **advance the demo clock** (demo only) |
| Family view | `family.html` | **Sara** (case owner, handling the estate, *stated*); **Amina** (household member) | Phone, often one-handed, often tired or upset | Confirm facts, answer "what could disappear?", approve or decline one specific thing at a time | The single card at the top (≤3 choices) |
| Call room | `call.html` | A judge playing the Northline representative | Laptop with a microphone (simulated here) | Talk to the AI agent, offer or change terms, hear what it will and won't agree to | **Hold to talk** (or type) |
| Provider console | `provider.html` | A judge playing any demo provider | Laptop | Reply to Afterward's request as Northline, City Power and the others; choose a prepared reply or write one | **Send reply (simulated)** |
| Proof panel | `proofs.html` | Judges | Projector | See the 14 adversarial cases, their inputs, what's required and the (mock) result | **Run preview** |
| Style guide | `style.html` | Agent D, the team | Laptop | Reuse the identity and components exactly | — |

Every page carries the same thin **prototype bar** across the top: "Prototype · fictional
family · nothing is sent", the current story step, and the **Story guide**.

## 2. Information hierarchy per surface

**Desk (projector-first).** Readable from the back of a room. One focal panel, not a grid of
equal cards.

1. **Case spine** (left column): who died and when, Sara's stated role, the family's intent
   in their own words, autopilot level, the Quiet / Hold / Stop control and the **demo case
   clock**. The spine never scrolls away on wide screens.
2. **Banners** (top of main column), only when true: *Monitoring interrupted*, *Delivery
   uncertain*, *Case on hold*. Each says what is affected and what happens next.
3. **Now**: the one account that needs attention, shown as **Requested → Provider says →
   Afterward concludes**. The provider's words appear as a verified quote; each condition
   carries an explicit verdict (holding, violated, not stated, unauthorised change).
4. **Accounts ledger**: one row per account with the four status dimensions (Service,
   Money, Documents, Next step) plus conditions. Rows, not cards, so they scan as a ledger.
5. **Coverage** ("what we searched, what we didn't"). There is no "looks complete" button.
6. **Timeline** (right column on wide screens): every event, with an evidence label.
7. **Call** transcript and per-turn timing (labelled simulated), and the honest
   "Did you finish everything?" summary.

**Family (phone-first).** One thing at a time.

1. The **active card** at the top: the single decision or question that needs this person.
2. Below it, a quiet feed of what Afterward has done, newest first.
3. A short **status line**: "3 things in progress · nothing needs you" when nothing is waiting.
4. Controls (Quiet / Hold / Stop) live behind a "Pause or stop" link, never as competing
   buttons on a card.

**Call room.** The representative needs to know who they are talking to, when they can
speak, and what state the agent is in.

1. A permanent **disclosure strip**: "You're speaking with Afterward, an AI assistant acting
   for the Malik family. Simulated provider call: browser only, not a phone call."
2. The **agent state** (idle, listening, thinking, speaking, waiting for the family).
3. The **Hold to talk** control with a typed fallback directly beneath it.
4. The transcript, then the terms under discussion and their approval status.

**Provider console.** Choose provider → thread → reply → send. Prepared replies are listed
with their purpose ("contradicts the plan", "acknowledgement only"), so a judge can choose
one deliberately or write their own.

## 3. Navigation

- **Entry** offers two routes: *Open a surface* (role cards) and *Follow the story* (the
  connected 12-step journey plus five side scenarios).
- The **prototype bar** on every page links all surfaces and opens the **Story guide**, a
  dialog listing every step with **Set up and open**. That replays the mock state to just
  before the step and opens the right page. This lets a reviewer jump to any moment without
  clicking through from the start.
- The mock state is shared across pages through `localStorage` (one key). A change made in
  one tab (Sara approves on her phone view) appears in another (the desk) through the
  `storage` event. This stands in for the WebSocket updates the real desk will have.
- Every state can be reset from the Story guide. Nothing persists outside the browser.

## 4. The connected journey (core story)

| # | Step | Surface | Who acts | Transition |
|---|---|---|---|---|
| 1 | Sara's voice note becomes the case | Family (Sara) | Sara confirms the summary card | `intake_pending → intake_confirmed` |
| 2 | Candidate coverage: 9 possible accounts, 3 need ownership confirmation | Family (Sara), Desk | Sara reviews | `candidates_found → candidates_reviewed` |
| 3 | Amina is asked about the 4417 line | Family (Amina) | Amina sends a (simulated) voice note, then confirms what Afterward understood | `dependency_asked → dependency_answered` |
| 4 | The plan visibly changes: v1 → v2 | Family (Sara), Desk | Afterward proposes, code applies the rules | Northline: *hold for dependency check* → *transfer to Amina if number and voicemail kept, no new contract*. Crescent Bank: *don't close; may be joint* |
| 5 | Specific approval for Northline (plan v2) | Family (Sara) | Sara approves | `approval_open → approved → request_sent (simulated)` |
| 6 | Northline replies "complete", with a 24-month plan and a voicemail reset | Provider console | Judge sends | `request_sent → outcome_reported` |
| 7 | Afterward says **not done** | Desk, Family | — | `outcome_reported → needs_decision` (2 violations, 1 not stated) |
| 8 | Sara chooses **Call them for me** | Family (Sara) | Sara decides | `needs_decision → call_requested` |
| 9 | The rep offers new terms; the agent pauses | Call room | Judge speaks or types | `call_live → decision_pause` (terms T1: 12 months at $30) |
| 10 | Sara approves terms T1 | Family (Sara) | Sara approves | `decision_pause → acceptance_ready (bound to T1)` |
| 11 | The rep changes the terms before acceptance is spoken | Call room | Judge presses talk | approval for T1 **void**, queued acceptance audio **discarded**, terms T2 → new decision |
| 12 | Sara re-approves T2; acceptance comes from the server template | Family → Call room | Sara approves, agent speaks the template | `acceptance_spoken`, waiting for written confirmation |

Optional ending: Northline's written confirmation (provider console) marks the service
resolved *only* because the reply states every condition. Any other reply leaves it open.

**Side scenarios** (reachable at any point from the Story guide or the desk):

- **Clock +14 days**: FitLife's 10-business-day window passes, exactly one follow-up fires.
- **Delivery uncertain**: that follow-up's send times out; the desk shows *delivery
  uncertain*, then *reconciled* after a Sent-folder search. No blind retry.
- **Monitoring interrupted**: mailbox access expires; desk and family both show it.
- **City Power final bill**: an April invoice for **February** service is **needs review**,
  never disputed automatically.
- **Refund issued**: City Power's refund is **issued, awaiting receipt evidence** until a
  statement shows it.
- **"Did you finish everything?"**: answered from the current mock state on both surfaces.

## 5. States every surface handles

| State | How it looks | Where shown in the prototype |
|---|---|---|
| Loading | Skeleton rows with a text label ("Loading the case…"); never a bare spinner | Entry (after passcode), desk first paint, proof run |
| Empty | Short explanation and the next useful action, with a small horizon illustration | Family feed before intake; provider thread list for a provider with no open request; proofs "not run" |
| Error | What failed, what is safe, what to do. No raw exception text | Passcode rejected; provider send failure (simulated); proof error row |
| Retry | A button with what retry will do ("Try the connection again"), attempt count | Entry error state; proof error row |
| Blocked | Which requirement or rule blocks it and who can unblock it | Provider console before the request is approved; Amina trying to approve; account blocked on probate (fixture) |
| Stale | "This changed. Here's the new version." The old card stays visible but disabled, with the reason and time | Approval for terms T1 after the rep changes terms; double-decision attempt |
| Uncertain | A distinct state, not an error: "may have been sent; checking the Sent folder" | FitLife follow-up |
| Interrupted | A banner on desk and family, with what is not being watched | Monitoring interrupted |
| Success | Only when evidence supports it, and with its evidence label | Northline written confirmation (optional ending) |

## 6. Phone, desktop and projector behaviour

| Width | Layout |
|---|---|
| < 480 px (phone) | Single column, 16 px gutters, cards full width, buttons stacked full width, 48 px touch targets. Desk becomes a vertical reading order: banners → Now → ledger rows as stacked "account cards" → timeline. |
| 480–1023 px | Single column with wider measure; desk ledger keeps rows, Next step wraps under the account name. |
| 1024–1599 px (desktop) | Desk: spine (280 px) + main; timeline below main. Family: phone column centred with a context panel on the right. |
| ≥ 1600 px or **Projector mode** | Desk: spine + main + timeline as three columns. Projector mode raises the root size to 20 px, increases contrast (darker ink, heavier rules), hides secondary metadata and enlarges status icons. |

Projector mode is a toggle on the desk (remembered locally) so a presenter can switch it
on with any screen size, because projectors often run at 1280 × 720.

## 7. Accessibility and interaction decisions

- **Never colour alone.** Every status has an icon shape and a word: holding ✓ (check),
  violated ✕ (cross), not stated ? (question), unauthorised + (plus), review ! (bang).
- **Contrast**: body text ≥ 7:1 on paper in light mode; all text ≥ 4.5:1; large text and UI
  boundaries ≥ 3:1. The style guide computes the ratios from the live tokens.
- **Focus**: a 3 px dawn-coloured outline offset 2 px on every interactive element
  (`:focus-visible`), never removed.
- **Keyboard**: skip link on every page; logical tab order; Story guide is a native
  `<dialog>`; the call room's talk button works with Space/Enter held and has a toggle
  mode for people who can't hold a key.
- **Announcements**: one polite `aria-live` region per page announces state changes
  ("Approval recorded", "Terms changed: approval void"). Urgent blocking changes use
  `role="alert"` once, not repeatedly.
- **Decisions**: at most three buttons per card, matching WhatsApp's limit. The first is
  never pre-selected; "Accept anyway" and similar consequential options state the
  consequence in the button's description.
- **Language**: plain, warm, short. "Yusuf", not "the deceased". Roles always say
  *stated*. No exclamation marks, no celebration of completion.
- **Reduced motion**: all transitions drop to instant; the speaking/listening rings in the
  call room become static with a text label.
- **Long content**: names, quotes and account references wrap; nothing truncates a
  provider quote, because the quote is the evidence.

## 8. Honesty rules applied to the interface

- Every simulated thing is labelled at the point of use: *Simulated send*, *Transcribed
  (simulated)*, *Simulated provider call*, *Mock result*, *Simulated timing*.
- There is no "everything found" or "looks complete" control. Coverage always lists what
  was **not** searched.
- A photo is labelled "photo", never "certified copy".
- Free text typed into the provider console is not interpreted by the mock. It is shown
  as *needs review (ambiguous)* with an explanation, because there is no model here.
- The proof panel's default state is **not run**. Preview states are labelled
  *Illustrative*.
- The family never sees "done" without the evidence label that supports it.

## 9. Decisions made here (please review)

1. **Typeface pairing**: Newsreader (serif) for headings and *quoted evidence*;
   Atkinson Hyperlegible Next for interface text. Quotes in serif read as "someone else's
   words", which separates evidence from interface.
2. **Desk composition**: spine + focal "Now" panel + ledger, instead of a card grid.
3. **Family web view** is a feed of cards, not an imitation Telegram client. Each card
   notes its channel ("Arrives in Telegram") so it's clear the same card goes to chat.
4. **Amina's voice note** is simulated with a scripted transcript; she can also type.
5. **Household members can't approve**: Amina sees a clear "Sara approves requests for
   this case" instead of approval buttons.
6. **Proof panel** defaults to *not run*; illustrative mixed results are opt-in.

## 10. Open questions for the reviewer

See REVIEW.md, "Remaining UX questions".

---

## Revision 2 (user feedback: less text, no scrolling, better flow)

Supersedes the layout parts of §§2, 3 and 6 above. The flows, states and honesty rules are unchanged.

- **One screen per surface.** Pages never scroll on laptop and desktop screens (checked at
  1920×1080, 1440×900, 1366×768, 1024×768 and 1280×720 projector). Long lists scroll inside their
  own panel; detail opens in a **drawer** (side panel) or a **sheet** (bottom panel).
- **Family:** one "Needs you" card at a time, with a pager when there are more (urgent ones first).
  A dock opens three sheets: **Earlier** (finished cards as one-line rows that expand),
  **Where are we?** (the honest summary) and **Pause** (quiet / hold / stop, plus support).
- **Desk:** a header with the demo clock and buttons for *Did we finish?*, *Coverage* and *Case*
  (people, intent, autopilot, pause, demo failures); "Now" and an account tile grid on the left;
  an Activity / Call tab panel on the right. Tapping an account opens its four dimensions,
  plan, conditions and provider profile in a drawer.
- **Call room:** stage (state, line chips, talk button, typed fallback) beside the transcript.
  Timing opens in a drawer. Sara's pending decision appears as a floating demo card.
- **Provider console:** organisation tabs, reply chips and message on the left; the thread on the right.
- **Proofs:** compact two-column list; each case opens in a drawer.
- **Prototype bar:** one slim line with the next story step, a Story button and the theme switch.
- **Copy:** shorter, plainer sentences throughout ("Northline says it's done. It isn't.").
