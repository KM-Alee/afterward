# Slice handoff: web-desk-call

Owner: Agent D
Branch: slice/web-desk-call
Commit: included in the feat(web-desk-call) commit on this branch
Updated: 2026-10-17 00:06 PKT

## What works

- Landing page with a demo passcode form. The passcode is not hard-coded; tests use `fixture-passcode`. A wrong or empty value is rejected.
- Desk at `/desk/{case_id}`: plan, four-dimension account drawers, outcome side by side (Holding / Broken / Not stated / Not approved, the approved mock's labels), timeline with evidence labels, call transcript, measured typed-turn latency when a turn exists, demo clock +14 and +35 days, mailbox-disconnected and delivery-uncertain banners, and the attestation badge with the AFTERWARD.md §8.6 boundary note. Confidential compute is labelled not verified.
- Live event stream at `/ws/cases/{case_id}`. A published event reaches a signed-in subscriber. Payloads go through the contract secrecy check.
- Proof panel at `/proofs` lists the 14 cases. Running them reports not-run unless `app.engine.proofs.run_proofs` or `app.demo.fixtures.proofs.run_proofs` is importable. It does not invent passes.
- Provider console at `/provider/{token}`: choose a provider, a ready-made variant or free text, and post. Sending uses `FakeMailbox`.
- Family view at `/family/{token}`: the Northline "not done" card (three choices) and the same timeline as the desk.
- Call room at `/call/{token}` on `CallSession`. Tools are the five contract tools via `make_call_agent`. There is no accept tool. Acceptance audio is the server-built sentence. A terms change voids approval and discards queued audio before playback. New representative speech suspends acceptance. The terms hash is checked again before play. A typed turn works end to end on `FakeCallSession`. Tests do not open a socket to OpenAI.
- `/status` is not registered here. `app/web/templates/status.html` is the styled template for the lead. The JSON `/status` route stays in `app/main.py`.
- Routers: `app.web.router` and `app.call.router`. `create_surface_app` in `app/web/factory.py` is what the tests mount. `app.main` is unchanged.

## What is stubbed

- The desk, family view and provider console read an in-memory Malik snapshot, not Postgres rows. Agent A's engine is not merged, so there is no live plan or outcome-check query.
- The WebSocket hub is in-process. It is not yet subscribed to `SqlEventBus` after commit. The lead can forward committed `EventRecord`s into `LiveHub.publish`.
- `make_call_agent` builds the realtime agent, and the tools are real function tools, but the browser does not open an OpenAI realtime socket. Audio relay uses `FakeCallSession` only.
- The acceptance sentence is queued as text. `gpt-4o-mini-tts` is not called.
- The commitment guard is a phrase check in `app/call/guard.py`. It is not attached as an SDK output guardrail, because `make_call_agent` does not take guardrails and the contract file is frozen. The page says the check is not a guarantee.
- Phone dial returns 403 while `phone_calls_enabled` is false. No Twilio call is placed.
- The proof panel stays not-run until Agent A exports `run_proofs`.
- Provider variants live in `app/web/state.py` because `app/demo/provider_variants.py` belongs to Agent C.

## How to test it

`make ci` on this worktree: Ruff clean, 69 passed, no network tests. Postgres was up for the foundation DB tests. Call-room tests use `FakeCallSession` and do not open a socket to OpenAI.

Pages were checked with FastAPI `TestClient`, including empty cases, unknown tokens, a wrong passcode, a refused clock step, an empty provider reply, and a WebSocket event. A browser was not used.

## Known risks

- Phase 3 must mount both routers and set `app.state.surface` (or let the first request build one). The demo passcode should come from `Settings.demo_passcode` at that mount. This slice does not read `.env`.
- Until the hub is tied to `SqlEventBus`, desk events from the engine will not appear on the socket by themselves.
- The demo snapshot shows the Northline contradiction together with the monitoring and delivery-uncertain banners. Those were separate moments in the prototype.
- Token URLs are generated per process. They are not durable across restarts.

## UX changes not made

- Chip words stay the mock's Holding, Broken, Not stated and Not approved. They were not renamed to matched / violated / missing.
- The style guide page was not ported.
- The family view is the current "not done" card and timeline, not every story card (intake, candidates, Amina's question, the approval card, the later voided-offer card).
- There is no "View as Amina" switch and no autopilot or pause control that changes behaviour. The prototype failure toggles and the "make the next send fail" checkbox were left out, as the design guide asked.
- The theme control sits in the header. The hatched prototype bar and Story guide were not carried over.
- The call room shows Hold to talk and the typed field on the ready screen as well as after Join, so the fallback is on the page before the call starts.
- Coverage copy is shorter than the prototype's full search list.
- Account detail stays in the drawer. The style guide's wide dimension table was not added as a second layout.

## Files touched

`app/web/`, `app/call/`, `static/`, `tests/web/`, `tests/call/`, this handoff, the Web/Desk/Call room row in `docs/STATUS.md`, and one appended `docs/DEVLOG.md` line.
