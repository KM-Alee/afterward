# Showcase: presenter script

A guided tour of the Malik case, about 8 minutes. The tour walks the real website page by page
with a spotlight and a short narration card. Every effect it shows is a real database change made
by the real engine. Where the outside world is normally simulated, **you play that role live** and
the real model answers.

Honest-claims rule: say only what the screen shows. Do not say it finds every account, that a
photo is a certified copy, that the speech guard is perfect, that delivery is exactly-once, or
that a phone call was made. The call room is a browser call.

## Before you go on

1. Open the app, sign in with the demo passcode. On the landing page a **Start the guided tour**
   pill appears (signed-in only). You can also open **Showcase** and press **Start the guided tour**.
2. Check the model tag. On each live moment the card shows **Live model** when an OpenAI key is
   configured on the server, and **Recorded model output** when it is not (or when the live call
   failed). Never say "live" over a recorded tag; the card says which it was.
3. Rehearse once end to end. The tour's second page resets the case (**Reset to the start**).
   Reset is safe at any time and only touches the demo case.
4. Use Chrome or Edge if you want the **Speak** button (browser speech input). Without it the card
   is typing only. The projector toggle on the desk helps in a big room.
5. The card shows the stop count ("5 / 21") and a row of progress dots; **Exit** is always at its
   top right. The card docks in the corner that hides the least of the highlighted area. Keys: Right arrow = next, Left arrow = back, Esc = exit. The tour position survives page changes
   and reloads. **Next** on a stop that was not run runs it silently so the next page is not empty.

## 30-second pitch

> When someone dies, the family has to tell dozens of organisations, one by one, and then
> work out whether each "done" is really done. Afterward takes the family's wishes once,
> finds candidate accounts from sources they grant, asks the people who actually know what
> depends on what, and writes to each organisation only after the family approves that exact
> request. When an organisation replies, we check the reply against the approved plan, not the
> company's word. It follows up by itself, hands legal and government steps back to a person,
> and answers "did you finish everything?" honestly: not yet, and here is why.

## The tour, stop by stop

Stops marked **LIVE** turn the card into an input. Press **Use suggested line** to fill the
exact line below, or say your own. Ctrl+Enter sends.

| # | Page | Stop | What you do |
|---|---|---|---|
| 1 | Landing | A family tells it once | Next |
| 2 | Landing | Four honest steps | Next |
| 3 | Landing | What it does not claim | Next |
| 4 | Showcase | Start from a clean case | **Reset to the start** |
| 5 | Family page | **LIVE: you are Sara** | say or type the intake line |
| 6 | Finding accounts | Where may we look? | Next |
| 7 | Finding accounts | Candidates, not conclusions | **Search her inbox** |
| 8 | Finding accounts | What we did not search | Next |
| 9 | Finding accounts | Only the family decides | **Sara decides** |
| 10 | Case desk | **LIVE: you are Amina** | say or type her answer |
| 11 | Case desk | Approve the exact plan | **Sara approves** |
| 12 | Case desk | The job runner sends | **Send the requests** |
| 13 | Provider console | **LIVE: you are Northline** | type the reply |
| 14 | Case desk | "Done" was not done | Next |
| 15 | Case desk | Sara: call them for me | **Choose "Call them"** |
| 16 | Call room | **LIVE: you are the Northline rep** | talk to the agent |
| 17 | Case desk | +14 days, by itself | **Move 14 days on** |
| 18 | Finding accounts | A person does these | **Prepare the hand-back** |
| 19 | Proofs | 14 proof cases | Next |
| 20 | Case desk | Did we finish everything? | **Ask it** |
| 21 | Showcase | Not everything. That is the point. | Finish |

### Landing (stops 1 to 3, 30 s)
- **Say:** the pitch. "Everything you will see is a real database row. The fakes are Gmail,
  Telegram, the organisations and, if no key is set, the model. Every card says which."
- **Audience sees:** a spotlight moving over the hero, the four steps and the honest limits.

### Stop 4: reset (10 s)
- **Click:** Reset to the start. **Audience sees:** "Clean case seeded."

### Stop 5, LIVE: you are Sara (50 s)
- **Say/type exactly:** *My dad Yusuf Malik died on 3 March 2026. I'm Sara, his daughter, handling
  things. Keep Mum's phone and Dad's voicemail, stop the bills nobody needs.*
  (The shorter line, *My dad Yusuf died on 3 March. Keep Mum's phone and Dad's voicemail, stop the
  bills nobody needs.*, works too: with no year, the date on file is kept and the card says so.)
- **Audience sees:** the real model's reading as a card: who, when, her role as *stated by her*,
  each keep and stop with the quote that supports it, and a counter of claims dropped for lacking
  a quote. Tagged **Live model** (or **Recorded model output**).
- **Say:** "She says it once. The model proposes; code keeps a fact only if her own words contain
  the quote. Her role is recorded as stated, never as 'executor'."
- **Fallback:** without a key the card shows the recorded reading of the scripted voice note, and
  says "No model key is configured".

### Stops 6 to 9: finding accounts (2 min)
- **Stop 7, Search her inbox:** the candidate list fills in with a pop animation. **Audience
  sees:** "9 candidate accounts found from 7 inbox headers and 4 photos; nothing is called his
  yet", two messages never read, and the query built by code.
- **Stop 8:** the coverage panel: what was searched, what was not, by design.
- **Stop 9, Sara decides:** "6 of 9 confirmed; 1 not his, 1 shared, 2 left unconfirmed".
- **Say:** "Headers first. Sara ticks what may be read; the cousin's note and the flyer were never
  opened. Candidates stay Unconfirmed until the family decides. We do not claim this list is
  complete, and the page lists what we did not search."

### Stop 10, LIVE: you are Amina (60 s)  *the theme moment*
- **Say/type exactly:** *That's my number, the bank sends my codes there, and his voice is on the
  voicemail.*
- **Audience sees:** her quote, then the plan diff animate: **Plan v1** (transfer, no conditions)
  to **Plan v2** with *+ Number kept* and *+ Voicemail kept*, and "Crescent Bank 0932 depends on
  this number". The desk behind it shows Northline now "With family: approve the revised plan".
- **Say:** "Amina knows what depends on the line. The model reads her answer; code decides the
  conditions. A transfer cannot be approved until someone has answered this question, and a card
  built from the old draft is refused as stale."
- **Variation:** say only "his voice is on the voicemail" and the plan gets only the voicemail
  condition. The conditions always follow the words.
- **Fallback:** without a key the recorded two-part answer is used and labelled.

### Stops 11 and 12: approve and send (45 s)
- **Approve:** four approvals on exact plan hashes. **Send:** the job runner sends four requests
  (Autopilot Steady is set on the way), each with a follow-up date.
- **Say:** "Sara approves a specific request: recipient, conditions, documents, bound to a hash.
  The runner re-checks the approval and recipient at send time. Gmail is simulated; nothing left
  this machine."

### Stop 13, LIVE: you are Northline (60 s)  *the core*
- **Type exactly:** *Done — line moved to Mrs Malik on a new 24-month plan, voicemail will be reset.*
- **Audience sees:** your text on the provider console, then a card with one row per plan
  condition: **Holding** (the transfer), **Not stated** (number kept), **Broken** (voicemail kept,
  with the quote *voicemail will be reset*), **Not approved** (a new 24-month contract), and the
  verdict **Not done: needs the family's decision**.
- **Say:** "Northline says done. The reader turns it into commitments, code checks every quote
  against the text, and compares with the plan Sara approved. 'Done' is not the company's word."
- **Try:** a clean reply that satisfies the plan (new holder, number kept, voicemail kept, with
  evidence) to show the opposite: a different verdict. Reset to play again.
- **Fallback:** without a key the recorded Northline reply is shown (not your text), labelled.
  The StreamBox and City Power replies and a lookalike sender arrive in the same step.

### Stop 14: the desk (30 s)
- **Audience sees:** Northline's quote beside what the plan allows, "Not done. Broken: voicemail
  kept." StreamBox and City Power are Done with their evidence; City Power's refund is *issued,
  awaiting receipt*; a lookalike sender asking for the will was held and nothing was disclosed.

### Stop 15 and 16, LIVE: you are the representative (90 s)
- **Stop 15, Choose "Call them":** the family's choice; the agent's lines pass through the guard
  and the acceptance wording is blocked. **Say:** "A paraphrase can slip past a wording guard.
  The protection is structural: the agent has no tool that accepts."
- **Stop 16:** the real call room. Join the call and talk (or type if audio fails). Offer
  *"12 months at $30 and we keep the voicemail"* and try to get the agent to say yes. It reports
  the offer to Sara; it does not accept. **It is a browser call, not a phone call.**

### Stop 17: +14 days (35 s)
- **Audience sees:** "Clock moved +14 days; 1 follow-up sent (FitLife), the others cancelled
  because they were answered."
- **Say:** "Fourteen days did not pass; we moved the demo clock. The runner woke on its own and
  followed up only where nobody had answered."

### Stops 18 to 20: hand-back, proofs, the honest answer (90 s)
- **Hand-back:** the bank needs a certified copy and Sara holds a photo; no-email providers get a
  prepared hand-off; probate, certified copies and government steps are the family's. We never
  file, sign or move money.
- **Proofs:** 14 adversarial cases; each shows whether the model output was live or recorded.
- **Did we finish everything?** "Not everything. Only 1 of 8 accounts is done with written
  evidence", counted from rows, plus what was not searched. **Say:** "That is the honest answer."

### Stop 21: close (10 s)
- "AI proposes, code decides, the family approves, and every reply is checked."

## Wow moments to land

1. **Dependency changes the plan** (stop 10), with two refusals.
2. **The wrong "done" is caught** (stops 13 and 14), with the exact violated conditions.
3. **The agent cannot accept on a call** (stops 15 and 16).
4. **Honest coverage** (stops 3, 8 and 20): what was read, what was not, what was never searched.
5. **The follow-up runs by itself** (stop 17), and cancels itself when no longer needed.

## What is real and what is simulated

| Real (code and database) | Simulated (labelled on the page) |
|---|---|
| Header-first inbox search, tick-to-read, discovery tools, candidate sync | Sara's Gmail: an in-memory mailbox with 8 invented messages |
| Quote verification of every extracted fact | The model, when no key is set: readings are recorded fixtures and are tagged **Recorded model output**. With a key, the three LIVE stops call the real model and are tagged **Live model** |
| Versioned plans, hashed approvals, stale and dependency refusals | Telegram: the chat lines are a labelled log |
| Durable job runner: lease, preflight, retries, case clock | The provider replies are typed text, not real organisations |
| Recipient check, held lookalike mail, outcome check, money rules | The clock jump: no days passed |
| Email and hand-off actions, follow-ups, audit events, finish counts | Phone calls: none are made |

Mailbox sends go to an in-memory mailbox by design, so the showcase works offline and on stage.
Nothing is sent to a real provider.

## Likely judge questions

**Is the model doing the work or are you faking it?** At the three live stops the real model reads
what you just said or typed, and the card is tagged **Live model**. If no key is configured the
card says **Recorded model output** and shows a recorded reading instead. The other steps use
recorded readings and say so. Everything around them is the real code path:
the quote check, plan hash, approval, job runner, recipient check and outcome check. The proof
panel runs the adversarial cases against the reply reader, and it labels whether a live model or a
stand-in ran.

**How do you know an organisation really did it?** Done means a reply that carries the completion
evidence the plan needs and satisfies every approved condition. A promise is *promised*, a refund
is *issued, awaiting receipt* until a statement shows it, and an ambiguous reply is *not accepted*.

**What stops the AI approving something on a call?** There is no accept tool. Acceptance is a
server-built sentence bound to the exact terms the family approved. If the terms change mid-call,
the approval is voided. The wording guard on free speech reduces risk; it is not perfect, and we
do not claim it is.

**Do you find every account?** No, and we show it. Candidates stay unconfirmed until the family
decides. The coverage list shows what was read, what was not, and what we never search (his own
inbox unless the family has a legitimate way in, government and court records, credit files).

**Can it impersonate the family or sign things?** No. Emails say an AI assistant prepared them on
behalf of the family member, with a visible reference. We never sign, never move money, and never
file probate, tax or government forms. We prepare and hand back.

**Is delivery guaranteed?** No. Sends are recorded as actions, an uncertain send is reconciled
against the Sent folder, and we do not claim exactly-once delivery.

**Which countries?** The engine is country-neutral; provider profiles are data. The demo uses a
fictional, labelled provider set and USD.

**Did you make a phone call?** No. The call room is a browser call. We only say a phone call
happened if one really did.

**What about privacy?** Only ticked messages are read, headers first. Confidential compute covers
our side only; it does not extend to the AI provider, chat platforms or recipients, and we say so.
Deleting our data does not delete what organisations already received.

**What if something breaks on stage?** Press Esc to leave the tour, then **Reset to the start** and
start the tour again. If the model is slow or down, the live stop falls back to the recorded reading
and says so. Typed turns work in the call room if audio fails. The step list on `/showcase` still
runs the same steps one at a time (**Run next step**) and is a fallback to read from.

## Notes for the operator

- The live app's background worker also runs due jobs. If two instances share one database, the
  worker that leases a job first runs it. For a clean run, use one instance, or one whose mailbox
  is the in-memory one.
- The showcase keeps its progress in the `desk_snapshots` row `showcase`, and the tour position and
  live cards in the row `showcase_tour`. The desk's own
  "Reset demo" returns to the classic seeded Malik board and ends the showcase until you reset it.
- The Telegram log and the simulated mailbox live in server memory; a server restart clears them.
  The database rows stay, and the remaining steps still run.
