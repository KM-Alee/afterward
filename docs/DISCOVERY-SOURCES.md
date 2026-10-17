# Where the account list comes from

Status: **design proposal, 2026-10-17 08:30 PKT.** Not built. Nothing here changes a frozen
contract; the changes it needs are proposed as CR-lead-2 in [CONTRACTS.md](CONTRACTS.md).
Mock: [design/frontend/onboarding.html](../design/frontend/onboarding.html).

## 1. The problem

The nine accounts on the demo desk are typed into `app/web/state.py` (`_demo_board`). The
scripted demo (`app/conversation/demo_malik.py`) pretends discovery already happened: six
forwards and four photos are loaded into `FakeAI` and replayed. The live Telegram path never
runs discovery. So today nobody can say *why* an account is on the list.

The rule this design adds: **an account candidate exists only because of a source the family
supplied or started.** Every candidate points at that source. No source, no candidate.

## 2. Sources

A *source* is one thing the family gave us or one search the family started. Code creates it
from a family action (an upload, a forward, a button). The model never creates a source.

| # | Source kind | Who starts it | What Afterward does | What Afterward never does |
|---|---|---|---|---|
| S1 | **Forwarded email** | A family member forwards to the case address | Reads that one message (`ingest_email`) | Follow links in it, log in anywhere |
| S2 | **Photo or scan** (bill, letter, statement) | A family member sends it in Telegram or uploads it | Vision extraction; form forced to `photo` | Treat it as a certified copy |
| S3 | **Household inbox** the family controls (Gmail OAuth by its owner) | The inbox owner connects it and taps *Search* | Code-built search, headers only first; reads a message in full only after the owner ticks it | Read unticked messages, send from it without a send approval, search outside the stated scope |
| S4 | **Mail export the family holds** (e.g. a Google Takeout `.mbox` released to a trusted contact) | The person who received it uploads the file | Same two-step scan as S3, parsed in code from the file | Ask how they got it beyond a stated note, treat their note as verified |
| S5 | **Bank or card statement** (PDF or photo) | A family member uploads it | Lists recurring payees as candidates (one statement → many) | Read balances into the plan, move money |
| S6 | **Locator or registry the family runs** (policy locator, unclaimed-money search, pension tracing) | The family member who is entitled to run it, on the official site | Prepares a copy sheet and opens the official link; records "started by Sara on …"; reads the result letter when it is forwarded or photographed | Submit the form, create an account there, search as the deceased |
| S7 | **Said by the family** ("he had a gym membership") | Voice note or text | Proposes a candidate with the quote as evidence | Mark it confirmed because a family member said it |

### His own mailbox, connected by a family member (decided 2026-10-17)

A family member may connect **Yusuf's own mailbox** with access they already hold: a
provider legacy-contact route, delegation he set up, or his sign-in on a device they keep.
Afterward does not ask for or store his password; the family member completes Google's
consent screen themselves.

- They must state their authority first ("I'm his executor"). It is stored as **stated**,
  never verified. No statement, no connection (`AuthorityMissing`).
- Scope is `gmail.readonly`. The connection can never send (`can_send` is False), and
  Afterward never changes his settings, password or recovery details.
- Same two-step search as S3: code-built scope, headers first, read only what that family
  member ticks.
- Coverage moves "Yusuf's own inbox" from *not searched* to a searched line naming who
  connected it and their stated authority.

### What is never a source

- **Afterward signing in as Yusuf on its own**, or using a password the family typed into chat.
- **Government, court, tax or credit-file systems.** We do not query them. Where an official
  service exists (UK Tell Us Once, a pension tracing service, a credit-file request by the
  executor), it is a hand-back step (§6), and its result letter returns as S1 or S2.
- **Web scraping or people-search sites.**

## 3. The household inbox search (S3), and why it works for the connected demo Gmail

The demo already holds a working refresh token for one Gmail account (the family mailbox in
DEVLOG 02:23). That account plays the household inbox: a real inbox the family owns. This is
the path that turns the hardcoded nine into nine found by a real search.

1. **Scope, built by code from the case, not by the model.**
   `("Yusuf Malik" OR "Y Malik" OR "14 Orchard Row") (bill OR invoice OR statement OR renewal
   OR "direct debit" OR membership OR policy OR subscription OR "your account") newer_than:3y`,
   plus any organisation names the family typed. The query string is shown to the family.
2. **Headers first.** `messages.list(q)` then `messages.get(format=metadata)` for From,
   Subject and Date only. Nothing goes to the model. Results are grouped by sender.
3. **The owner ticks what to read.** Only ticked messages are fetched in full and passed to the
   existing `ingest_email`. Unticked ones are counted, not read.
4. **Candidates** get `origin="household_inbox"`, `source_id`, and the message id as evidence.
5. **Coverage line:** "Searched Sara's household inbox for mail naming Yusuf or 14 Orchard Row
   since Oct 2023: 37 matches, 9 read with your OK, 28 not read."

For the demo, the six fictional provider emails are seeded into that inbox once (sent from the
providers role, as the provider console already does), so the search finds them for real.
The four photos are sent as real Telegram photos. The duplicate Northline 4417 still merges,
so the count stays nine, and now each tile can say where it came from.

Extra scope needed: `gmail.readonly` is already covered by `gmail.modify`. No new consent.

## 4. The discovery agent: it combs, proposes and suggests

A discovery agent (Agents SDK, `gpt-6-luna`) works through the sources the family has granted.
It looks for accounts, links evidence across sources, and suggests to the family what to look at
next and what they might want. It runs after each new source arrives and when the family asks
"anything else?".

**The agent can only reach what the family granted.** Code binds every tool call to the case
and to the source rows the family created. The model never supplies a case id, a mailbox, a
date window or a URL. The agent can make a search narrower. It cannot make it wider.

### Tools

| Tool | What it does | Bound by code |
|---|---|---|
| `search_inbox_headers(terms[], sender?)` | Header search in a connected household inbox or uploaded export | Always ANDed with the case scope (his name or address, the granted window). Returns From, Subject, Date and an id. No bodies |
| `ask_to_read(message_ids[], why)` | Asks the inbox owner to tick messages to read | `needs_approval`: becomes a tick list on the family's card. Nothing is read until the owner ticks it |
| `read_message(message_id)` | Latest text of one message | Only ids the owner ticked. Quoted history removed. The text is marked as evidence, not instructions |
| `list_documents()` / `document_fields(doc_id)` | Fields already extracted from photos, statements and forwards | Only this case's vault. Read-only |
| `statement_payees(doc_id)` | Recurring payees on an uploaded statement | Payee, reference, amount, date. No balance goes to the plan |
| `provider_profile(name)` | The provider directory: category, track, accepted channel, usual evidence | Data lookup. Unknown names return `unknown`, never a guessed address |
| `locator_catalogue()` | Locators for the case's country and whether each was started | Data. The agent can suggest one; it cannot run one |
| `propose_candidate(provider, account_ref?, evidence_ids[], why)` | Adds or merges a candidate in `proposed` | Rejected unless every evidence id belongs to a granted source. Ownership is never set |
| `suggest_to_family(kind, text, why, evidence_ids[])` | A suggestion card, at most three buttons | `kind` is `where_to_look`, `run_locator`, `which_account`, `what_matters` or `prepare_handback`. The family decides; nothing runs |

The agent has **no tool** to confirm ownership, plan, send, add a recipient, browse the web,
open a link from a message, log in, or start a locator. Calls are capped per run (for example
40 header searches, 20 read requests). Each call is an audit event with kind and ids, not
content.

### What it suggests (demo examples, all from the fictional fixtures)

- *Linking evidence:* "The Northline bill photo shows two lines, 4417 and 2290. Whose is 2290?"
  → [Yusuf's] [Mum's] [Not sure]
- *Where to look:* "Crescent Bank emails mention monthly statements. A photo of one statement
  usually shows direct debits I can't see from email." → [Send a statement] [Later]
- *A locator:* "There's a Meridian Life letter. A policy locator can check for other policies;
  insurers answer the beneficiary directly." → [Prepare it for me] [Not now]
- *Something they may want:* "Paperleaf renews on 2 Nov. Do you want that stopped before it
  charges?" → [Yes, put it first] [No]. And the F4 questions: "Could his email hold photos or
  documents you'll want before anything is closed?"
- *Hand-back prompts:* "Probate is often needed before banks close an account. Want the
  checklist for applying?" → [Show me] [Not now]

### Guards

- Message bodies, photos and statements are untrusted. An email that says "forward this to …"
  or "mark complete" is evidence that such a sentence exists, nothing more. The output schema has
  no field that could carry an address or a state change.
- Suggestions never claim coverage: the schema has no "done" or "all found" kind, and a check
  rejects suggestion text containing "all", "every", "complete" or "nothing else".
- One suggestion card at a time, quiet hours respected, and "Stop suggesting" turns it off.

## 5. Candidate life cycle

```
proposed ──(family taps "Yes, his")──▶ confirmed ──▶ planning
   │ ├────(family taps "Not his")─────▶ removed (kept in audit, never planned)
   │ └────(family taps "Shared / not sure")──▶ needs_check (flag, not planned)
   └── new evidence merges in; state stays where the family put it
```

- Only `confirm_refs` (a family button) changes ownership. Model output has no ownership field.
- Merge only on an identical, non-empty account reference. **Two unreferenced documents never
  merge.** (Today `candidate_from_doc` turns a missing reference into the string
  `"unreferenced"`, so two such documents do merge. That is a bug to fix with a test.)
- A merge adds evidence and sources; it never moves the state forward.
- Every candidate lists every source that supports it ("Household inbox · Photo of a bill").

## 6. Tracks: what each category is allowed to become

The category comes from the **provider profile** (data), not from the model. Unknown providers
get `ordinary` only after the family confirms; until then nothing is planned at all.

| Track | Examples | After family confirms | Can Afterward send? | Can it finish the step? |
|---|---|---|---|---|
| `ordinary` | Phone, power, water, streaming, gym, books | Plan → approval → send → outcome check | Yes, with a current approval, to approved recipients | Yes, when the reply satisfies the plan |
| `financial` | Bank, card, loan | Notification letter only | Yes, notification only, with approval | Closure stays **blocked** on the requirement the bank states (e.g. grant of probate) |
| `insurance_pension` | Life policy, workplace pension | Notification letter; claim packet prepared | Notification only, with approval | No. The claim is filed by the beneficiary; Afterward hands back the packet |
| `handback` | Tax, benefits, licence, passport, probate, court, Tell Us Once, certified copies | A prepared step: what's needed, a copy sheet, the official link | **No send action exists for this track** | No. The family taps "I did this" and forwards the confirmation |

Code rules (each gets a unit test with its deny path):

1. `allowed_actions(candidate)` is empty unless `ownership == "confirmed"`.
2. For `handback`, the only actions are `prepare_packet` and `family_marked_done`. A model plan
   item proposing a send for a handback item is dropped and logged as
   `plan.item_rejected.handback_only`.
3. A `certified_copy` or `original` requirement is never satisfied by a vault item with
   `form="photo"`. The item stays blocked with the hand-back "Post or take in a certified copy".
4. "Blocked until probate" unblocks only when a family member uploads the grant **and** taps
   that it is the grant, and the form satisfies the profile. A provider saying "received" is
   not enough.
5. `family_marked_done` is labelled *stated by Sara*, never *evidenced*, until a confirmation
   letter arrives and is read.
6. Locator results (S6) create candidates in `proposed`, labelled "possible policy". A locator
   reporting no match is recorded as "No match reported by <service> on <date>", never as
   "no policy exists".

## 7. Coverage, computed from sources

`coverage_panel` takes the source rows instead of two counters.

- **Searched:** one line per source with its scope and counts.
- **Started, waiting:** locators the family started; result not back.
- **Not searched, by design:** Yusuf's own inbox and phone, government and court records,
  his credit file (unless the executor requests it), anything paid in cash, paper post not
  photographed.
- **Not run yet:** catalogue locators for the case's country that nobody has started.
- **Needs you:** proposed candidates still unconfirmed.
- **Where else to look:** bank statements (direct debits), app-store subscriptions, post over
  the next weeks.

There is still no `complete` field, no "looks complete" button, and the chat summary never says
"all", "every" or "complete". A test already guards this for the panel; extend it to the
onboarding page copy.

## 8. Locator catalogue (data, per country)

Each entry: name, operator, what it can find, who may run it, cost, what it asks for, how the
result comes back, official URL. Shown only for the case's country. Examples to verify before
listing as real (the demo uses one fictional, labelled locator):

- US: NAIC Life Insurance Policy Locator (insurers reply to the beneficiary); state unclaimed
  property searches.
- UK: Tell Us Once (via the registrar; hand-back), Death Notification Service (banks),
  My Lost Account (dormant accounts), Pension Tracing Service.
- Pakistan: not researched yet; the page says so instead of showing nothing.

## 9. Onboarding flow

Telegram stays the main channel; cards keep the three-button limit. The web page
(`/family/onboarding`) is the full view of the same state.

1. After the intake summary is confirmed: *"Where should I look for his accounts? Nothing is
   searched until you choose."* [Search my inbox] [Send photos or forwards] [Later]
2. Inbox: connect (if not connected) → show query → headers list → tick → read → candidates.
3. Photos and forwards: any time; each reply says what was found and that it is unconfirmed.
4. Locators: the page lists the country's catalogue with "Prepare" → copy sheet → official link
   → "I started it".
5. Confirm: one card per candidate, three buttons: *Yes, his* / *Not his* / *Shared or not sure*.
6. Coverage card closes the step and stays reachable; new sources can be added any time.

## 10. Demo changes (after the freeze window allows it)

- `_demo_board` tiles get their origin from the candidate list instead of fixed strings.
- `register_malik_fixtures` stays for offline tests; the live demo uses S3 on the connected
  Gmail plus real Telegram photos.
- The fictional "Policy locator (demo)" shows *Started by Sara, waiting*, so the hand-back state
  is visible without inventing a result.

## 11. Honest claims for the pitch

Say: "Afterward only lists accounts from things the family gave it or searches the family ran,
and shows what it did not search." Don't say: "finds all his accounts", "connects to his
email", "checks government records", "files probate/tax/claims".
