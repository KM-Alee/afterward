# Slice handoff: mail-integrations

Owner: Agent C
Branch: slice/mail-integrations
Commit: feat(mail-integrations) on this branch; the SHA is the commit that adds this file
Updated: 2026-10-17 00:14 PKT

## What works

- `GmailMailbox` implements `Mailbox`: history poll, `newer_than:7d` fallback when the cursor is missing or expired, full MIME decode, send with `threadId` / `In-Reply-To` / `References`, and `in:sent` search for the visible footer marker. Refresh-token credentials are per mailbox in `app/integrations/google.py`.
- Latest-text extraction strips `>` quotes, Gmail `On … wrote:` blocks (including a wrapped address) and Outlook header blocks. The message row stores the latest text and the SHA-256 of the full body. `extract_text` also returns the hash of the remainder.
- Matching order is thread, then exact From / Reply-To, then a plus-tag on the same domain as an approved recipient. Recipient check is `approved`, `unapproved` or `reply_to_mismatch`. Mail with no case stays in an in-process unsorted tray; mail on a known case with no single account is stored and listed by `unsorted_for`.
- Inbound glue calls `app.engine.outcome.outcome_check` and `app.ai.verify.verify_reply` (or `verify_quotes` / `verify`) only when those callables exist, and only for an approved match to one account. A proposal that names another address does not change `approved_recipients`. A contradictory "complete" reply does not mark the account resolved.
- `execute_send_request` and `execute_followup` use action records. The visible footer is `Prepared by Afterward, an AI assistant, on behalf of <owner name> (as stated).` plus `Ref AW-<case>-<action>`. A timeout becomes `uncertain`; reconciliation searches Sent, retries once, then leaves the action `uncertain`. Web-form and phone-only providers become an action of kind `handoff` and are not emailed. Hold, stop and interrupted monitoring do not send.
- Mailbox health sets `monitoring` to `interrupted` when the token is missing or the last poll is older than 10 minutes, and publishes one family `monitoring` event. The payload is the reason code only.
- Provider console replies send through the providers mailbox into the existing thread, with display names such as `Northline Mobile (demo)`. Variants: `nl_contradictory`, `nl_ack`, `probate_blocked`, `nl_certified`, `cp_april_feb`, `cp_refund`, `reply_to_mismatch`, `spoof_will`, plus free text. Bodies that exist in `design/frontend/fixtures/case.js` are copied. Addresses are fictional `.example` addresses.
- Calendar stretch: `calendar_insert` actions call `events.insert` with reminder overrides through the same executor.

## What is stubbed

- No live Gmail, Calendar or OAuth call is made by the tests. `scripts/google_auth.py` prints a refresh token only when the operator runs it.
- `app.engine.outcome.outcome_check` and `app.ai.verify` are still empty on this branch. Ingest stores the message and records extraction as `unavailable` until Agent A adds those functions. It does not invent a verdict.
- `scripts/mail_smoke.py` is not in the shared scripts directory. The function is `app.mail.smoke.mail_smoke`. The proposed script is below.
- fastn MCP is not connected. The worker loop is not registered in `app/main.py`. The history cursor is returned to the caller; this slice does not add a table for it.
- Consent and plan-hash preflight stay with Agent A. This slice refuses send on hold, stop and interrupted monitoring.

## How to test it

`make ci` on this worktree: Ruff clean, 84 passed (foundation plus `tests/mail`). No network. Postgres was the compose database.

Not verified: a real Gmail send, history expiry against Google, or the OAuth browser flow.

## Proposed scripts/mail_smoke.py

The lead can place this at `scripts/mail_smoke.py`. It reads tokens from the environment and prints ids only.

```python
"""Send one family email and one providers reply. Prints ids, never tokens."""

import argparse
import asyncio

from app.config import Settings
from app.integrations.google import gmail_mailbox_for
from app.mail.smoke import mail_smoke


def main() -> int:
    parser = argparse.ArgumentParser(description="Send and reconcile one demo email.")
    parser.add_argument(
        "--remote",
        action="store_true",
        help="Accepted for Checkpoint 2. Tokens still come from the environment.",
    )
    parser.parse_args()
    settings = Settings.from_env()
    family = gmail_mailbox_for(settings, "family")
    providers = gmail_mailbox_for(settings, "providers")
    result = asyncio.run(
        mail_smoke(
            family,
            providers,
            family_address=settings.family_mailbox,
            providers_address=settings.providers_mailbox,
        )
    )
    print({"thread_id": result["thread_id"], "reconciled": result["reconciled"]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`mail_smoke` confirms the family send is in Sent. It does not wait for the providers reply to arrive in the family inbox.

## Known risks

- No contract change. If Gmail rewrites the providers-mailbox From to the bare account address, a live reply can match by thread and still be `unapproved`, because seed approves the plus-address and the fictional `.example` address, not the bare mailbox. Extraction will not run until that From is an approved recipient. Suggested lead follow-up, not a contract revision: when `providers_mailbox` is set, also record that bare address on the demo profiles, or send with a plus alias Gmail will keep.
- Fake delivery uses the fictional approved From so the desk story matches the mock. The providers mailbox send itself uses the providers address plus the demo display name.
- The email action is marked `failed` when the provider does not accept email, and a sibling `handoff` action is marked `sent`. The hand-off is the step that reached a person.

## Files touched

- `app/mail/` (parse, gmail, match, inbound, outbound, health, calendar, smoke)
- `app/integrations/google.py`
- `app/demo/provider_variants.py`
- `scripts/google_auth.py`
- `tests/mail/`
- `docs/handoffs/mail-integrations.md`, the Mail & Integrations row in `docs/STATUS.md`, one appended `docs/DEVLOG.md` line
