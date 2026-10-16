---
name: mail-integrations
description: "Agent C: Mail & Integrations; implement only this slice after the lead freezes Python contracts."
tools: Read, Glob, Grep, Edit, Write, Bash
---

Read AGENTS.md, CONTRIBUTING-AGENTS.md and the three docs fully first.
Do not start until user-approved frontend UX and shared Python contract revision 1
are recorded. See docs/FRONTEND-FIRST.md.
Use worktree ../afterward-mail-integrations, branch slice/mail-integrations. Obey ownership and
handoff requirements. Source brief from IMPLEMENTATION.md Phase 2 follows.
References to shared files do not grant ownership; send changes to the lead.

### Agent C: Mail & Integrations *(real email in and out)*
**Owns:** `app/mail/`, `app/integrations/`, `app/demo/provider_variants.py`, `scripts/google_auth.py` (finish), `tests/mail/`

**Builds:**
1. **Gmail client:**
   - refresh-token auth per mailbox;
   - **history-based polling** with a `messages.list` fallback;
   - `messages.get` with full MIME decoding;
   - `users.messages.send` with `threadId`, `In-Reply-To` and `References`;
   - footer with the disclosure and `Ref AW-<case>-<action>`;
   - `in:sent` search for reconciliation.
2. **Parsing:**
   - **latest-text extraction** (strip `>` quotes and "On … wrote:" blocks; hash the rest);
   - matching to case and account via thread → exact From / Reply-To → plus-tag;
   - **recipient check** (`approved` / `unapproved` / `reply_to_mismatch`);
   - an unsorted tray for unmatched messages.
3. **Inbound pipeline glue:** a new message → Agent A's extraction pipeline → outcome check → events. Uses Agent A's interfaces; stubbed until merge.
4. **Outbound effects:** `send_request` and `followup` executors that use Agent A's action records; hand-off steps for web-form and phone-only providers.
5. **Mailbox health:** last-poll age, token validity → `monitoring = interrupted` → a family notice through the `EventBus`.
6. **Provider console backend:** send a reply **as a demo provider** through the providers mailbox into the right thread, with the display name "Northline Mobile (demo)". Variants include:
   - the Northline "complete, new 24-month plan, voicemail will reset" reply;
   - acknowledgement;
   - probate-blocked;
   - certified-copy request;
   - April-invoice-for-February;
   - refund issued;
   - `Reply-To` mismatch;
   - a request for the will from an unknown address.

   Free-text replies are also supported.
7. **Calendar** (stretch inside this slice): `events.insert` with reminders, via action records.

**Done when:**
- MIME and quote-stripping tests pass on real-world sample emails (Gmail, Outlook-style quoting);
- the `FakeMailbox` end-to-end flow (send → provider-variant reply → match → extraction call → state change) passes;
- the live mail smoke script (`scripts/mail_smoke.py`) is ready for Checkpoint 2.

---
