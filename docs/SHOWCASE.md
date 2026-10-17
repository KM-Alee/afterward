# Showcase: presenter script

A 7-minute walk through the Malik case. Every step on `/showcase` runs the real engine on
real Postgres rows. What is simulated is only the outside world: Gmail, Telegram, the
providers and the model readings. The page says which is which under every step, and so
should you.

Honest-claims rule: say only what the page shows. Do not say it finds every account, that a
photo is a certified copy, that the speech guard is perfect, that delivery is exactly-once, or
that a phone call was made. The call room is a browser call.

## Before you go on

1. Open the app, sign in with the demo passcode, open **Showcase** (`/showcase`).
2. Press **Reset to the start**. The case now holds only the pre-onboarding state: the
   Malik family (Sara, Amina), five declared providers and one inbox Sara has granted. There
   are no accounts, plans or mail yet. Open the **Case desk** in a second tab.
3. Rehearse once end to end, then reset again. Reset is safe at any time and only touches the
   demo case.
4. Use the projector toggle on the desk. Keep the Telegram log (the dropdown under each step)
   closed unless asked.

The steps cannot be skipped: each one needs the one before. **Run next step** always runs the
first step not done.

## 30-second pitch

> When someone dies, the family has to tell dozens of organisations, one by one, and then
> work out whether each "done" is really done. Afterward takes the family's wishes once,
> finds candidate accounts from sources they grant, asks the people who actually know what
> depends on what, and writes to each organisation only after the family approves that exact
> request. When an organisation replies, we check the reply against the approved plan, not the
> company's word. It follows up by itself, hands legal and government steps back to a person,
> and answers "did you finish everything?" honestly: not yet, and here is why.

## The walk-through (about 7 minutes)

Times are a guide. Each beat is one press of **Run next step** unless noted.

### 0:00 Start (30 s)
- **Say:** the pitch above. "Everything you will see is a real database row. The only fakes
  are Gmail, Telegram, the providers and the model's reading. Each step lists both."
- **Click:** nothing yet. Show the empty rail and the pre-onboarding note.

### 0:30 Step 1, "Sara states it once" (40 s)
- **Click:** Run next step.
- **Audience sees:** Sara's voice-note transcript, a summary card, and "2 unsupported claims
  dropped for lacking a quote".
- **Say:** "Sara says it once. The system keeps a fact only if her own words support it. Two
  things the reading offered had no matching words, so they were removed. Her role is recorded
  as *stated by her*, never as 'executor'."
- **Wow:** the quote check. The model proposes; code decides.

### 1:10 Step 2, "Find candidate accounts" (50 s)
- **Click:** Run next step. Then open **Finding accounts** from the links.
- **Audience sees:** 9 candidates, all *Unconfirmed*; "7 inbox headers listed, 5 read, 2 never
  read" and which two (the cousin's note and a pizza flyer); the search query shown in full;
  the "Not searched, by design" list.
- **Say:** "Headers first. Sara ticks what may be read; the cousin's message and the flyer were
  never opened. The query is built by code from the case, so the AI can narrow it but never
  widen it. Nothing here is called *his* yet. And we do not claim this list is complete."
- **Wow:** honest coverage.

### 1:55 Step 3, "Family confirms" (30 s)
- **Click:** Run next step.
- **Audience sees:** "6 of 9 confirmed; 1 not his, 1 shared, 2 left unconfirmed".
- **Say:** "Only the family's buttons change ownership. 2290 is Amina's own line on the same
  bill, so it is left out. The joint bank account is flagged, not guessed. The policy letter
  with the hidden name stays unconfirmed, and we will count it that way at the end."

### 2:25 Step 4, "Amina's answer" (50 s)  *the theme moment*
- **Click:** Run next step.
- **Audience sees:** Amina's quote; "plan v1 (transfer, no conditions) became v2 with two
  conditions: number kept, voicemail preserved"; two refusals.
- **Say:** "Amina is asked who still uses the line. Her answer, *the bank sends my codes there
  and his voice is on the voicemail*, becomes plan conditions. Code writes the conditions, not
  the model. Notice two refusals: the first draft could not be approved because nobody had
  answered the dependency question, and a card built from the old draft was refused as stale."
- **Wow:** a family member's knowledge changes the plan, and the system enforces it from here on.

### 3:15 Steps 5 to 7, approve, Steady, send (60 s)
- **Click:** Run next step three times, narrating briefly.
- **Audience sees:** four approvals on exact plan hashes; "Steady"; "4 requests sent by the job
  runner", each with a `Ref AW-1042-…` footer and a follow-up date.
- **Say:** "Sara approves four specific requests: recipient, conditions, documents. Only four
  accounts have an email route and a confirmed owner. The bank, the water company and the book
  club are not emailed. Steady means a follow-up may run without asking, but only inside a plan
  that is still approved. The send itself goes through the durable job runner, which re-checks
  the approval and the recipient at send time. Gmail is simulated here, so nothing left this
  machine."
- **Open:** the desk. Four accounts show "Request sent".

### 4:15 Step 8, "Replies are checked" (70 s)  *the core*
- **Click:** Run next step. Open the **Case desk**; the latest outcome is Northline.
- **Audience sees:** Northline said *"Request complete. Transferred… new 24-month plan at $28.00…
  Voicemail will be reset"*. The desk shows it **not accepted**: voicemail condition violated,
  "not in the plan: new contract, price change", "number kept was not stated". StreamBox and City
  Power are *Done*. City Power's refund is *issued, awaiting receipt*. A lookalike sender asking
  for the will and bank details is *held*.
- **Say:** "Northline says done. It is not. The reply is read into structured commitments, every
  quote is checked against the text, and the result is compared with the plan Sara approved.
  Voicemail reset breaks her condition; a 24-month contract was never approved. StreamBox is done
  because its reply carries the evidence the plan needs. City Power promised a refund and issued
  it, but we have no statement showing it arrived, so it stays *awaiting receipt*, never
  *received*. The message from a lookalike address asking for the will was stored and held; nothing
  was disclosed."
- **Wow:** the wrong outcome caught, side by side. Say "one wrong outcome caught, one lookalike held".

### 5:25 Step 9, "Call them for me" (50 s)
- **Click:** Run next step. Then open the **Call room** and play Northline yourself or hand the
  keyboard to a judge: offer "12 months at $30 and we keep the voicemail".
- **Audience sees:** Sara chose *Call them for me*; the guard blocking acceptance wording; the
  honest note that a paraphrase can slip past a wording guard.
- **Say:** "The agent can ask questions and report what it hears. It cannot accept. It has no tool
  that accepts. If you offer new terms, they are reported to Sara as a decision. The wording guard
  is a heuristic; the real protection is structural. This is a browser call, not a phone call."
- **Wow:** the agent cannot accept on a call.

### 6:15 Step 10, "+14 days" (35 s)
- **Click:** Run next step.
- **Audience sees:** "Clock moved +14 days; 1 follow-up sent (FitLife), the others cancelled
  because they were answered."
- **Say:** "Fourteen days did not pass; we moved the demo clock. The job runner woke on its own.
  FitLife never replied, so a follow-up went out in the same thread under the same approved plan.
  Northline, StreamBox and City Power had already answered, so their follow-ups were cancelled.
  Exactly one follow-up fired."
- **Wow:** follow-up runs by itself, and knows when not to.

### 6:50 Step 11, "Hand-back" (30 s)
- **Click:** Run next step.
- **Audience sees:** the bank needs a *certified copy* and Sara holds a *photo*; two no-email
  providers get a prepared hand-off; a policy locator is prepared; probate, certified copies and
  government steps are listed as the family's.
- **Say:** "We prepare; a person does the legal, government and tax steps. A phone photo is never a
  certified copy. We never file, sign or move money."

### 7:20 Step 12, "Did you finish?" (25 s)
- **Click:** Run next step. Open **Did we finish?** on the desk if you wish.
- **Audience sees:** "Not everything. Only 1 of 8 accounts is done with written evidence", with
  buckets: confirmed, promised, handed to you, unconfirmed, and the list of what was not searched.
- **Say:** "That is the honest answer, counted from the rows. Stated once, four requests sent,
  one wrong outcome caught, one lookalike held, one refund tracked as issued, not received. We never
  say we found everything."

## Wow moments to land

1. **Dependency changes the plan** (step 4), with two refusals.
2. **The wrong "done" is caught** (step 8), with the exact violated conditions.
3. **The agent cannot accept on a call** (step 9).
4. **Honest coverage** (steps 2 and 12): what was read, what was not, what was never searched.
5. **The follow-up runs by itself** (step 10), and cancels itself when no longer needed.

## What is real and what is simulated

| Real (code and database) | Simulated (labelled on the page) |
|---|---|
| Header-first inbox search, tick-to-read, discovery tools, candidate sync | Sara's Gmail: an in-memory mailbox with 8 invented messages |
| Quote verification of every extracted fact | The model readings (voice notes, photos, replies) are registered fixtures; no model call is made |
| Versioned plans, hashed approvals, stale and dependency refusals | Telegram: the chat lines are a labelled log |
| Durable job runner: lease, preflight, retries, case clock | The provider replies are typed text, not real organisations |
| Recipient check, held lookalike mail, outcome check, money rules | The clock jump: no days passed |
| Email and hand-off actions, follow-ups, audit events, finish counts | Phone calls: none are made |

Mailbox sends go to an in-memory mailbox by design, so the showcase works offline and on stage.
Nothing is sent to a real provider.

## Likely judge questions

**Is the model doing the work or are you faking it?** On this page the model's readings are
registered fixtures, and we say so under each step. Everything around them is the real code path:
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

**What if something breaks on stage?** Press **Reset to the start** and replay; every step is
repeatable. Typed turns work in the call room if audio fails. The step log under each step is a
fallback to read from.

## Notes for the operator

- The live app's background worker also runs due jobs. If two instances share one database, the
  worker that leases a job first runs it. For a clean run, use one instance, or one whose mailbox
  is the in-memory one.
- The showcase keeps its progress in the `desk_snapshots` row `showcase`. The desk's own
  "Reset demo" returns to the classic seeded Malik board and ends the showcase until you reset it.
- The Telegram log and the simulated mailbox live in server memory; a server restart clears them.
  The database rows stay, and the remaining steps still run.
