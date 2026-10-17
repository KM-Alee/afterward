# Showcase: presenter script

A 4-minute guided tour of the Malik case in 12 stops. The tour walks the real website page by page
with a spotlight and one short sentence per stop. Every effect is a real database change made by
the real engine. Where the outside world is normally simulated, **you play that role live** and
the real model answers.

Honest-claims rule: say only what the screen shows. Never say it finds every account, that a
photo is a certified copy, that the speech check is a guarantee, that delivery is exactly-once, or
that a phone call was made. The call room is a browser call, not a phone call.

## Before you go on

1. Sign in with the demo passcode. On the landing page press **Start the guided tour**
   (signed-in only). It is also on the **Showcase** page.
2. Check the model tag on each live card: **Live model** (a key is configured) or **Recorded model
   output**. Never say "live" over a recorded tag.
3. Rehearse once. Stop 1 resets the case; reset is safe at any time and only touches the demo case.
4. Use Chrome or Edge for the **Speak** button; otherwise type. Keys: Right = next, Left = back,
   Esc = exit. **Next** on a stop you did not run runs it silently, so the next page is never empty.

## 2-minute autoplay for the video

Sign in, open `/showcase`, press **Play the 2-minute demo** (or open `/showcase?autoplay=1`). It
resets the demo case, then walks all 12 stops across the pages by itself (about 2:30): the real
steps run, the three live lines are typed with a typewriter effect and sent to the live endpoints,
and each stop is narrated in a lower-third caption.

- Voice: server speech when a model key is configured (`POST /api/showcase/narrate`), else the
  browser voice, else timed captions only. Nothing is claimed beyond what the screen shows.
- The model tag stays visible: **Live model** with a key, **Recorded model output** without.
- Call room: no microphone is opened; it is narrated as a browser call, not a phone call.
- Keys: `h` hides the small controls and progress bar for recording, `p` pause/resume, `s` skip,
  `Esc` exit. Respects reduced-motion. Record at 1920x1080 with browser zoom at 100%.

## 20-second pitch

> When someone dies, a family has to tell dozens of organisations, then work out whether each
> "done" is really done. Afterward takes the family's wishes once, finds possible accounts only
> where they allow, asks the right person what depends on what, and writes only after the family
> approves the exact request. Every reply is checked against that approval, it follows up by
> itself, hands legal steps back to a person, and answers "did you finish?" honestly.

## The tour, stop by stop

Live stops turn the card into an input. **Use suggested line** fills the exact line; Ctrl+Enter sends.

| # | Page | Stop (tag) | Click / do |
|---|---|---|---|
| 1 | Landing | Paperwork after a death | **Start a fresh case** |
| 2 | Family page | You are Sara (LIVE) | say or type the line |
| 3 | Finding accounts | Accounts found, and not found | **Search her inbox** |
| 4 | Finding accounts | Sara confirms each one | **Sara decides** |
| 5 | Case desk | You are Amina (LIVE) | say or type the line |
| 6 | Case desk | Approve, send, keep checking | **Approve and send** |
| 7 | Provider console | You are Northline (LIVE) | type the line |
| 8 | Case desk | Done, but not really | Next |
| 9 | Call room | Talk to the agent (LIVE) | **Sara asks for a call**, then talk |
| 10 | Case desk | Two weeks later, by itself | **Move 14 days on** |
| 11 | Finding accounts | People do the legal steps | **Prepare the hand-back** |
| 12 | Case desk | Did we finish everything? | **Ask it** |

### 1. Paperwork after a death (20 s)
- **Click:** Start a fresh case. **Say:** "A family should not chase twenty companies while
  grieving. Everything you see is a real database row; Gmail, Telegram and the companies are
  simulated, and each card says which." **See:** "Clean case seeded."

### 2. You are Sara (30 s)
- **Type/say exactly:** *My dad Yusuf Malik died on 3 March 2026. I'm Sara, his daughter, handling
  things. Keep Mum's phone and Dad's voicemail, stop the bills nobody needs.*
- **Say:** "She says it once. The model proposes; code keeps a fact only if her own words back it."
- **See:** the reading as a card: who, when, each keep and stop with its supporting quote, tagged
  **Live model** or **Recorded model output**. Without a key the recorded reading is shown.

### 3. Accounts found, and not found (35 s)
- **Click:** Search her inbox. **See:** 9 candidate accounts, all Unconfirmed, two messages never
  read, and the coverage panel listing what was not searched.
- **Say:** "Only where Sara allowed. We do not claim this list is complete, and the page says what
  we did not search."

### 4. Sara confirms each one (15 s)
- **Click:** Sara decides. **See:** "6 of 9 confirmed; 1 not his, 1 shared, 2 left unconfirmed".
- **Say:** "Only the family can say which accounts were his."

### 5. You are Amina (40 s), the theme moment
- **Type/say exactly:** *That's my number, the bank sends my codes there, and his voice is on the
  voicemail.*
- **See:** Plan v1 become Plan v2 with *+ Number kept* and *+ Voicemail kept*.
- **Say:** "Amina knows what depends on that line. Her answer changes the plan."
- **Variation:** say only the voicemail part and only that condition is added.

### 6. Approve, send, keep checking (25 s)
- **Click:** Approve and send. **See:** four approvals, four requests sent, each with a follow-up date.
- **Say:** "Sara approves one exact request. Afterward sends it and keeps checking. Gmail is
  simulated; nothing left this machine."

### 7. You are Northline (40 s)
- **Type exactly:** *Done — line moved to Mrs Malik on a new 24-month plan, voicemail will be reset.*
- **See:** one row per promised condition, with **Broken** (voicemail kept) and **Not approved**
  (a new 24-month contract), and "Not done: needs the family's decision".
- **Say:** "Northline says done. We compare it to what the family approved."
- **Fallback:** without a key the recorded Northline reply is shown, labelled.

### 8. Done, but not really (15 s)
- **See:** Northline's quote beside what the plan allows. StreamBox and City Power are done with
  evidence; a lookalike sender asking for the will was held.

### 9. Talk to the agent (45 s)
- **Click:** Sara asks for a call, then join the call and talk (or type if audio fails). Offer
  *"12 months at $30 and we keep the voicemail"* and try to get a yes.
- **Say:** "It reports your offer to Sara; it has no way to accept. This is a browser call, not a
  phone call. Our speech check helps but is not a guarantee; the protection is that there is no
  accept tool."

### 10. Two weeks later, by itself (20 s)
- **Click:** Move 14 days on. **See:** one follow-up sent (FitLife), the others cancelled
  because they were answered. **Say:** "We moved the demo clock; no days really passed."

### 11. People do the legal steps (15 s)
- **Click:** Prepare the hand-back. **Say:** "Probate, certified copies and government forms are
  prepared and handed back. We never file, sign or move money."

### 12. Did we finish everything? (20 s)
- **Click:** Ask it. **See:** "Not everything. Only 1 of 8 accounts is done with written evidence",
  counted from saved rows, plus what was not searched.
- **Say (close):** "That honesty is the point. AI proposes, code decides, the family approves, and
  every reply is checked."

## Wow moments to land

1. Amina's answer changes the plan (stop 5).
2. A wrong "done" is caught (stops 7 and 8).
3. The agent cannot accept on a call (stop 9).
4. The follow-up fires by itself (stop 10).
5. The honest "not everything" (stop 12).

## Likely judge questions

**Is the model doing the work or is it faked?** At the three live stops (2, 5, 7) the real model
reads what you typed and the card says **Live model**. With no key it says **Recorded model
output**. The rules around it (quote check, approval, sending, reply check) are real code.

**How do you know a company really did it?** "Done" needs a reply with the evidence the approved
plan asks for. A promise stays *promised*, a refund stays *issued, awaiting receipt*, and an
unclear reply is *not accepted*.

**What stops the AI agreeing to something on a call?** It has no accept tool. Acceptance only comes
from a server-built sentence bound to terms the family approved. The wording check is a help, not
a guarantee.

**Do you find every account?** No, and we show it. Findings stay unconfirmed until the family
decides, and the coverage list shows what was not searched.

**Did you make a phone call? Can it sign or pay?** No phone call was made; the call room is a
browser call. It never signs, moves money or files forms; it prepares and hands back. Delivery is
not claimed to be exactly-once.

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

## Notes for the operator

- The live app's background worker also runs due jobs. If two instances share one database, the
  worker that leases a job first runs it. For a clean run, use one instance, or one whose mailbox
  is the in-memory one.
- The showcase keeps its progress in the `desk_snapshots` row `showcase`, and the tour position and
  live cards in the row `showcase_tour`. The desk's own
  "Reset demo" returns to the classic seeded Malik board and ends the showcase until you reset it.
- The Telegram log and the simulated mailbox live in server memory; a server restart clears them.
  The database rows stay, and the remaining steps still run.
