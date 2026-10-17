"""Discovery in the chat: nothing is searched until a button, ticks are owner-only,
candidates stay unconfirmed until a suggestion button, and wording never claims completeness."""

import json
from datetime import UTC, datetime

import pytest

from app.contracts import ImageInput, MailMessage
from app.conversation.demo_malik import (
    ALLOWED_RECIPIENTS,
    NORTHLINE,
    PHOTO_MIME,
    PROVIDERS,
    _doc,
    demo_photos,
    register_malik_fixtures,
    run_malik_script,
    sara_intake,
)
from app.conversation.session import Conversation, MemberRecord
from app.discovery.candidates import email_messages, photo_messages
from app.discovery.household import HouseholdScan
from app.discovery.vault import VaultCipher
from app.fakes import FakeAI, FakeChannel
from app.fakes.mailbox import FakeMailbox

SARA, AMINA, STRANGER = "1001", "2002", "9999"
BOX = "household@example.test"
BANNED = ("complete", "everything", "nothing else", "every account", "all found", "found them")

BODIES = {
    "m1": ("Northline Mobile <billing@northline.example>", "Your bill", "Yusuf Malik line 4417"),
    "m2": ("City Power <bills@citypower.example>", "Your statement", "Yusuf Malik CP-77120"),
    "m3": ("Crescent Bank <no-reply@crescentbank.example>", "Statement", "Yusuf Malik 0932"),
}
DOCS = {
    "m1": ("Northline Mobile", "4417"),
    "m2": ("City Power", "CP-77120"),
    "m3": ("Crescent Bank", "0932"),
}


def _mailbox() -> FakeMailbox:
    box = FakeMailbox()
    for gid, (sender, subject, text) in BODIES.items():
        box.inject(
            MailMessage(
                mailbox=BOX,
                gmail_id=gid,
                thread_id=f"t-{gid}",
                rfc_message_id=f"<{gid}@x>",
                from_addr=sender,
                to_addrs=[BOX],
                subject=subject,
                latest_text=text,
                full_text=text,
                received_at=datetime(2026, 4, 1, tzinfo=UTC),
            )
        )
    return box


def _conversation(*, account_of="household", authority="", with_scan=True, **kw):
    ai = FakeAI()
    for gid, (provider, ref) in DOCS.items():
        ai.register_structured(
            "document_reader",
            _doc_type(),
            email_messages(BODIES[gid][2]),
            _doc(
                doc_type="bill",
                form="scan",
                provider=provider,
                account_reference=ref,
                quote=BODIES[gid][2],
                name="Yusuf Malik",
            ),
        )
    scan = (
        HouseholdScan(
            client=_mailbox(),
            mailbox=BOX,
            owner=SARA,
            names=("Yusuf Malik",),
            account_of=account_of,
            stated_authority=authority,
        )
        if with_scan
        else None
    )
    conv = Conversation(
        ai,
        providers=PROVIDERS,
        allowed_recipients=ALLOWED_RECIPIENTS,
        line=NORTHLINE,
        scan=scan,
        discovery=True,
        connect_url="https://afterward.example/connect/gmail/start",
        **kw,
    )
    conv.state.intake_confirmed = True
    conv.state.owner_sender = SARA
    conv.state.members[SARA] = MemberRecord(SARA, "Sara Malik", "owner", "daughter")
    conv.state.members[AMINA] = MemberRecord(AMINA, "Amina Malik", "household", "wife")
    return conv


def _doc_type():
    from app.ai.schemas import DocOut

    return DocOut


def _no_claims(text: str) -> None:
    lowered = text.lower()
    assert not any(word in lowered for word in BANNED), text


@pytest.mark.asyncio
async def test_card_after_intake_has_three_short_buttons_and_searches_nothing():
    conv = _conversation()
    conv.state.intake_confirmed = False
    conv.state.intake = sara_intake()
    replies = await conv.handle_button(SARA, "confirm_intake")
    card = next(r for r in replies if r.kind == "discovery_offer")
    assert card.text == (
        "Where should I look for his accounts? Nothing is searched until you choose."
    )
    assert [o.label for o in card.options] == ["Search an inbox", "Photos/forwards", "Later"]
    assert all(len(o.label) <= 20 for o in card.options)
    assert conv.scan is not None and conv.scan.searches == 0


@pytest.mark.asyncio
async def test_find_accounts_text_and_slash_command_offer_the_card():
    conv = _conversation()
    for text in ("find accounts", "/find", "Find his accounts."):
        replies = await conv.handle_text(SARA, text)
        assert [r.kind for r in replies] == ["discovery_offer"]


@pytest.mark.asyncio
async def test_no_scan_explains_how_to_connect_and_reads_nothing():
    conv = _conversation(with_scan=False)
    replies = await conv.handle_button(SARA, "disc:inbox")
    assert replies[0].kind == "discovery_no_inbox"
    assert "read-only" in replies[0].text
    assert "https://afterward.example/connect/gmail/start" in replies[0].text
    assert conv.state.candidates == []


@pytest.mark.asyncio
async def test_search_lists_numbered_headers_only():
    conv = _conversation()
    replies = await conv.handle_button(SARA, "disc:inbox")
    listing = replies[0]
    assert listing.kind == "discovery_headers"
    assert "1. " in listing.text and "3. " in listing.text
    assert "Your bill" in listing.text
    assert "line 4417" not in listing.text  # bodies are not shown
    assert [o.label for o in listing.options] == ["Read all 3", "Not now"]
    assert conv.scan.read == set()
    assert conv.state.candidates == []


@pytest.mark.asyncio
async def test_tick_by_a_non_owner_is_denied_and_nothing_is_read():
    conv = _conversation()
    await conv.handle_button(SARA, "disc:inbox")
    for who in (AMINA, STRANGER):
        replies = await conv.handle_text(who, "read 1 3")
        assert replies[0].kind == "discovery_not_owner"
    replies = await conv.handle_button(AMINA, "disc:readall")
    assert replies[0].kind == "discovery_not_owner"
    assert conv.scan.ticked == set() and conv.scan.read == set()
    assert conv.state.candidates == []


@pytest.mark.asyncio
async def test_non_owner_cannot_start_the_search():
    conv = _conversation()
    replies = await conv.handle_button(AMINA, "disc:inbox")
    assert replies[0].kind == "discovery_not_owner"
    assert conv.scan.searches == 0


@pytest.mark.asyncio
async def test_bad_numbers_read_nothing():
    conv = _conversation()
    await conv.handle_button(SARA, "disc:inbox")
    replies = await conv.handle_text(SARA, "read 7 9")
    assert replies[0].kind == "discovery_bad_numbers"
    assert conv.scan.read == set()


@pytest.mark.asyncio
async def test_read_ticked_makes_unconfirmed_candidates_and_only_buttons_confirm():
    conv = _conversation()
    await conv.handle_button(SARA, "disc:inbox")
    replies = await conv.handle_text(SARA, "read 1 3")
    assert conv.scan.read == {"m1", "m3"}  # message 2 was not ticked, so not read
    refs = {c.account_ref for c in conv.state.candidates}
    assert refs == {"4417", "0932"}
    assert all(c.ownership == "unconfirmed" for c in conv.state.candidates)
    assert all(c.origin == "household_inbox" for c in conv.state.candidates)
    assert all(c.evidence.startswith("Inbox message from") for c in conv.state.candidates)
    summary = next(r for r in replies if r.kind == "discovery_summary")
    assert "2 possible accounts" in summary.text
    assert "Household inbox: 3 messages about accounts, 2 read with your OK, 1 not read" in (
        summary.text
    )
    _no_claims(summary.text)
    card = next(r for r in replies if r.kind == "suggestion")
    assert len(card.options) <= 3 and all(len(o.label) <= 20 for o in card.options)

    # free text cannot confirm anything
    await conv.handle_text(SARA, "yes that is his, confirm 4417")
    assert all(c.ownership == "unconfirmed" for c in conv.state.candidates)

    # a stranger's button press changes nothing
    refused = await conv.handle_button(STRANGER, card.options[0].id)
    assert refused[0].kind == "suggestion_refused"
    assert all(c.ownership == "unconfirmed" for c in conv.state.candidates)

    # the family's button confirms exactly that account
    answered = await conv.handle_button(SARA, card.options[0].id)
    assert answered[0].kind == "suggestion_answered"
    assert sum(c.ownership == "confirmed" for c in conv.state.candidates) == 1

    # the same button twice does not act twice
    again = await conv.handle_button(SARA, card.options[0].id)
    assert again[0].kind == "suggestion_stale"


@pytest.mark.asyncio
async def test_read_all_button_reads_every_listed_message_only_after_the_tap():
    conv = _conversation()
    await conv.handle_button(SARA, "disc:inbox")
    assert conv.scan.read == set()
    await conv.handle_button(SARA, "disc:readall")
    assert conv.scan.read == {"m1", "m2", "m3"}
    assert len(conv.state.candidates) == 3


@pytest.mark.asyncio
async def test_one_suggestion_card_at_a_time_then_the_next_after_an_answer():
    conv = _conversation()
    await conv.handle_button(SARA, "disc:inbox")
    replies = await conv.handle_button(SARA, "disc:readall")
    assert sum(r.kind == "suggestion" for r in replies) == 1
    first = next(r for r in replies if r.kind == "suggestion")
    nxt = await conv.handle_button(SARA, first.options[2].id)  # shared / not sure
    assert [r.kind for r in nxt].count("suggestion") == 1
    assert nxt[0].kind == "suggestion_answered"
    assert any(c.ownership == "needs_check" for c in conv.state.candidates)


@pytest.mark.asyncio
async def test_his_own_mailbox_requires_authority_and_is_named_in_coverage():
    conv = _conversation(account_of="deceased", authority="Sara holds his phone and password")
    await conv.handle_button(SARA, "disc:inbox")
    replies = await conv.handle_button(SARA, "disc:readall")
    summary = next(r for r in replies if r.kind == "discovery_summary")
    assert "Yusuf's own inbox, connected read-only" in summary.text
    assert "Sara holds his phone and password" in summary.text
    assert all(c.origin == "deceased_inbox" for c in conv.state.candidates)
    assert conv.state.coverage is not None
    assert all("no access" not in item for item in conv.state.coverage.not_searched)
    _no_claims(summary.text)
    with pytest.raises(PermissionError):
        HouseholdScan(
            client=_mailbox(),
            mailbox=BOX,
            owner=SARA,
            names=("Yusuf Malik",),
            account_of="deceased",
        )


@pytest.mark.asyncio
async def test_later_and_photos_buttons_do_nothing_hidden():
    conv = _conversation()
    later = await conv.handle_button(SARA, "disc:later")
    assert later[0].kind == "discovery_later"
    photos = await conv.handle_button(SARA, "disc:photos")
    assert photos[0].kind == "discovery_photos"
    assert conv.scan.searches == 0


@pytest.mark.asyncio
async def test_photo_becomes_a_granted_source_and_prompts_a_suggestion():
    conv = _conversation(with_scan=False)
    ai = conv.ai
    register_malik_fixtures(ai)
    photo = next(p for p in demo_photos() if p.document.account_reference == "2290")
    await conv.ingest_picture(
        image=photo.image,
        mime=PHOTO_MIME,
        label=photo.label,
        evidence="photo:1",
        cipher=VaultCipher(None),
    )
    replies = await conv.photo_discovery(SARA, photo.label)
    assert "photo:1" in conv.tools.evidence
    assert replies and replies[0].kind == "suggestion"
    assert all(c.ownership == "unconfirmed" for c in conv.state.candidates)


@pytest.mark.asyncio
async def test_dependency_question_follows_the_flagged_shared_line():
    conv = _conversation()
    from app.discovery.candidates import Candidate

    conv.state.candidates.append(
        Candidate("4417", "Northline Mobile", "line 4417", "Yusuf", "household_inbox")
    )
    out = conv.ask_dependency(AMINA)
    assert "4417" in out[0].text and "Northline Mobile" in out[0].text
    assert conv.line.account_ref == "4417"


@pytest.mark.asyncio
async def test_state_round_trips_through_json_after_the_malik_script():
    result = await run_malik_script(FakeAI(), FakeChannel())
    before = result.conversation
    blob = json.loads(json.dumps(before.export_state()))
    fresh = Conversation(
        FakeAI(), providers=PROVIDERS, allowed_recipients=ALLOWED_RECIPIENTS, line=NORTHLINE
    )
    fresh.load_state(blob)
    a, b = before.state, fresh.state
    assert b.intake == a.intake and b.intake_confirmed and b.owner_sender == a.owner_sender
    assert b.members == a.members and b.candidates == a.candidates
    assert b.plan == a.plan and b.approval == a.approval
    assert b.photos_ingested == a.photos_ingested
    # an approval after restart still works exactly once
    first = await fresh.handle_button(SARA, "approve_plan")
    assert first[0].kind == "approval_recorded"
    second = await fresh.handle_button(SARA, "approve_plan")
    assert second[0].kind == "already_decided"


@pytest.mark.asyncio
async def test_damaged_snapshot_is_skipped_not_fatal():
    fresh = Conversation(
        FakeAI(), providers=PROVIDERS, allowed_recipients=ALLOWED_RECIPIENTS, line=NORTHLINE
    )
    fresh.load_state({"intake": {"nonsense": 1}, "plan": {"items": 3}, "members": 5})
    assert fresh.state.intake is None and fresh.state.plan is None
    assert fresh.state.intake_confirmed is False


def test_unused_imports_guard():
    assert ImageInput and photo_messages


@pytest.mark.asyncio
async def test_statement_photo_lists_payees_as_unconfirmed_candidates():
    from app.ai.schemas import PayeeLine, StatementOut
    from app.contracts import ChatMessage
    from app.discovery.candidates import STATEMENT_SYSTEM

    conv = _conversation(with_scan=False)
    image = b"FICTIONAL-STATEMENT"
    conv.ai.register_structured(
        "document_reader",
        _doc_type(),
        photo_messages("bank statement"),
        _doc(
            doc_type="statement",
            form="photo",
            provider="Crescent Bank",
            account_reference="0932",
            quote="statement",
            name="Yusuf Malik",
        ),
        images=[ImageInput(data=image, mime=PHOTO_MIME)],
    )
    conv.ai.register_structured(
        "document_reader",
        StatementOut,
        [
            ChatMessage(role="system", content=STATEMENT_SYSTEM),
            ChatMessage(role="user", content="statement photo"),
        ],
        StatementOut(
            lines=[
                PayeeLine(
                    payee="StreamBox",
                    reference="SB-88213",
                    amount="9.99",
                    date="2026-02-01",
                    quote="STREAMBOX SB-88213",
                )
            ]
        ),
        images=[ImageInput(data=image, mime=PHOTO_MIME)],
    )
    item = await conv.ingest_picture(
        image=image,
        mime=PHOTO_MIME,
        label="bank statement",
        evidence="photo:1",
        cipher=VaultCipher(None),
    )
    await conv.photo_discovery(
        SARA, "bank statement", doc_type=item.doc_type, image=image, mime=PHOTO_MIME
    )
    refs = {c.account_ref: c for c in conv.state.candidates}
    assert refs["SB-88213"].ownership == "unconfirmed"
    assert refs["SB-88213"].origin == "statement"
