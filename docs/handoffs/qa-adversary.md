# Slice handoff: qa-adversary

Owner: QA adversary
Branch: slice/qa-adversary
Commit: branch tip (tests and this handoff)
Updated: 2026-10-17 00:46 PKT

## What works

`make ci` is red only because of the 12 `tests/qa` findings below. Ruff is clean.
The other 191 tests passed, including the previous 179. No production code was edited.
No live OpenAI, Gmail, Telegram, WhatsApp, or Twilio. No SQLite.

Checks that passed, with a regression test where one was added:

- Email text does not add a recipient, and a model "close" on a transfer plan is not resolved (`test_email_text_cannot_add_a_recipient`).
- A reply the model marks ambiguous stays open, not completed (`test_ambiguous_reply_is_not_completion`).
- Revoked consent cancels a queued `send_request` before any send (`test_revoked_consent_blocks_a_queued_send`).
- An invalid mailbox token sets monitoring to interrupted and then blocks that send (`test_expired_mailbox_token_interrupts_monitoring_and_blocks_the_send`).
- A running job whose lease has expired is leased again; the case row remains (`test_expired_lease_is_retaken_and_the_case_row_remains`).
- FitLife's seeded window is 10 business days. Inside a 14-calendar-day offset, follow-up 1 is due and follow-up 2 is not (`test_fitlife_ten_business_days_is_one_followup_inside_fourteen_calendar_days`, `test_seeded_fitlife_window_is_ten_business_days`).
- The desk asks to move the Northline line to Amina and labels Sara as handling the estate, stated. It does not say executor (`test_desk_keeps_northline_as_a_transfer_and_sara_stated`).
- A phone photo the model calls a certified copy is stored as `photo` (`test_phone_photo_stays_a_photo`).
- An April invoice whose service period is February is needs review, not a dispute (`test_april_invoice_for_february_service_is_not_a_dispute`).
- `/status` and the default JSON log line do not contain a database URL, a traceback, or the words secret, token, or password (`tests/qa/test_secrets.py`).
- Engine plan revision still voids the database approval (existing `tests/engine/test_plans.py`).
- `CallRoom.report_offered_terms` still voids and discards queued audio when called directly (existing `tests/call/test_room.py`). The call-room HTTP path does not do that. See finding 2.

## What is stubbed

Nothing in this slice. The findings are open defects. They are not marked done.

Observation without a separate test: the demo desk already shows "Mailbox disconnected" and "A FitLife follow-up may not have sent" before the clock moves. Those strings are static on the board. Finding 8 is the missing send.

## How to test it

```
make ci
```

Result on 2026-10-17 00:46 PKT: Ruff passed, 203 collected, 12 failed, 191 passed.
Every failure is under `tests/qa/`. Re-run that directory with:

```
uv run --frozen pytest tests/qa
```

Not verified: a live mailbox, a real worker process kill, realtime audio, or the deployed proof panel. The kill test simulates the provider accepting and then the worker raising before the action row is saved.

## Known risks

Ranked findings. Each has a failing test. Do not weaken the assertion.

1. **High. A crash after a successful send sends a second copy.**
   `tests/qa/test_chaos.py::test_worker_killed_after_send_reconciles_without_a_second_copy`
   Location: `app/mail/outbound.py` `_send_email`.
   Reproduction: the mailbox stores the message, then raises. The action stays `pending`. Running the send again delivers a second copy.
   Expected: status `uncertain`, then one Sent search reconciles it. One message.
   Actual: two `SentRecord`s and status `sent`.

2. **High. The call room speaks the old acceptance after the representative changes the price.**
   `tests/qa/test_call_room.py::test_call_room_discards_acceptance_when_the_representative_changes_terms`
   Location: `app/call/router.py` typed turn and `/api/calls/{token}/continue`.
   Reproduction: approve 12 months at $30, queue the sentence, post "Sorry, that offer is now 12 months at $35 a month.", then continue.
   Expected: approval void, queued audio discarded, nothing played.
   Actual: the played clip is "The Malik family accepts 12 months at $30 a month...".

3. **High. After terms change, the new offer cannot be approved.**
   `tests/qa/test_call_room.py::test_changed_terms_can_be_approved_without_speaking_the_old_sentence`
   Location: `app/call/acceptance.py` `approve`.
   Reproduction: approve the $30 hash, `report_offered_terms` for $35 (this voids and discards), then `approve` the new hash.
   Expected: the old approval is void and the new hash can be approved. Only the $35 sentence plays.
   Actual: `ValueError: That approval is void`. The void flag blocks the new yes.

4. **High. An approved contradictory reply crashes the outcome check.**
   `tests/qa/test_claims.py::test_contradictory_complete_is_checked_and_not_resolved`
   Location: `app/mail/inbound.py` `_maybe_extract` and `app/engine/outcome.py` `outcome_check`.
   Reproduction: send the Northline request, ingest `nl_contradictory` with no test doubles on `verify_reply` or `outcome_check`.
   Expected: recipients unchanged, verdict not `resolved`, account not transferred.
   Actual: `AttributeError: 'dict' object has no attribute 'key'`. `verify_reply` is called with one argument, so its real signature never runs. The ORM plan is passed straight into `outcome_check`.

5. **High. "This will be completed" is marked resolved.**
   `tests/qa/test_claims.py::test_will_be_completed_is_not_marked_done`
   Location: `app/ai/verify.py` `apply_wording_guards`, then `app/engine/pipeline.py`.
   Reproduction: model status `completed`, quote "This will be completed next week. cancellation_confirmation", plan evidence is that phrase, no conditions.
   Expected: not done. "will" is not completion. Account not closed.
   Actual: verdict `resolved`, action `completed`. The guard skips the downgrade because the quote also contains "completed".

6. **High. A job payload can waive hold, quiet, and interrupted monitoring.**
   `test_hold_cannot_be_waived_by_a_job_payload_flag`
   `test_quiet_cannot_be_waived_by_a_job_payload_flag`
   `test_interrupted_monitoring_cannot_be_waived_by_a_job_payload_flag`
   Location: `app/engine/jobs.py` `preflight` via `_flag`.
   Reproduction: case on hold with `payload.outbound = false`; quiet with `touches_family = false` on a digest; monitoring interrupted with `requires_mailbox = false` on a send.
   Expected: cancelled with `hold`, `quiet`, or `mailbox_unhealthy`.
   Actual: `PreflightResult(ok=True)` in all three.

7. **High. The family's hold command does not stop a queued send.**
   `tests/qa/test_claims.py::test_family_hold_stops_a_queued_organisation_send`
   Location: `app/conversation/session.py` `handle_text("hold")` and `app/engine/jobs.py` `preflight`.
   Reproduction: preflight allows a send, then the conversation handles "hold", then preflight runs again.
   Expected: the queued send is cancelled with `hold`.
   Actual: hold only changes an in-memory `Controls` object. The case row stays active and the job still passes.

8. **High. The +14 day desk clock does not send the one FitLife follow-up.**
   `tests/qa/test_demo.py::test_plus_14_days_sends_exactly_one_fitlife_followup`
   Location: `app/web/router.py` `advance_clock`.
   Reproduction: sign in, POST `advance_days=14` on the demo case.
   Expected: the date moves to 20 Mar 2026 and exactly one FitLife follow-up is sent. FitLife's window is 10 business days, so the second follow-up is not due yet. That math passes in `test_fitlife_ten_business_days_is_one_followup_inside_fourteen_calendar_days`.
   Actual: the date moves and `mailbox.sent` is empty.

9. **High. A new dependency answer leaves the old family approval in force.**
   `tests/qa/test_claims.py::test_plan_change_voids_the_earlier_family_approval`
   Location: `app/conversation/session.py` `_dependency_answer` and `_approve`.
   Reproduction: Sara approves the Northline card, Amina then answers with only the voicemail (plan loses `number_kept`), Sara is shown the new card.
   Expected: `approval_choice` is cleared so the new plan needs a new yes. The engine path does void database approvals.
   Actual: `approval_choice` stays `approve_plan` after the plan content changes.

10. **Medium. Gentle follow-ups are cancelled instead of asked.**
    `tests/qa/test_claims.py::test_gentle_followup_asks_instead_of_vanishing`
    Location: `app/engine/policy.py` `decide` and `app/engine/jobs.py` `preflight`.
    Reproduction: default Gentle case, valid approval, FitLife-style follow-up.
    Expected: the family is asked (a decision row) or the already-approved follow-up stays runnable. Gentle's table says Ask, not a silent drop.
    Actual: job `cancelled` with `approval_required`. No `Decision` row.

## Files touched

- `tests/qa/` failing and passing regression tests
- `docs/handoffs/qa-adversary.md`
- `docs/STATUS.md` QA row only
- `docs/DEVLOG.md` one appended line
