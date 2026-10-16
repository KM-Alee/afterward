"""Fictional Malik demo: voice-note scripts, forwarded mail and photographed letters.

Every name, address and amount here is invented. Nothing in this module is a real person
or a real message.
"""

from dataclasses import dataclass
from datetime import date

from app.ai.schemas import DependencyOut, DocOut, HouseholdMemberOut, IntakeOut, QuotedStr
from app.contracts import Channel, ImageInput
from app.conversation.dependency import ProviderFacts, dependency_messages
from app.conversation.intake import intake_messages
from app.conversation.session import Conversation, Invite, Outbound
from app.discovery.candidates import email_messages, photo_messages
from app.discovery.vault import VaultCipher
from app.fakes.ai import FakeAI

SARA_SCRIPT = (
    "My dad, Yusuf Malik, passed away on the 3rd of March. "
    "I'm his daughter Sara, I'm sorting things out. "
    "I want to stop the bills that don't matter, but keep Mum's phone, "
    "and… his voicemail. I can't lose that."
)
AMINA_SCRIPT = (
    "Yes, that's my number now. Crescent Bank sends me my codes on it. "
    "And his voice is on the voicemail."
)
SARA_OGG = b"FICTIONAL-DEMO-OGG-SARA"
AMINA_OGG = b"FICTIONAL-DEMO-OGG-AMINA"
INVITE_TOKEN = "amina-demo-invite"
PHOTO_MIME = "image/jpeg"

NORTHLINE = ProviderFacts(
    name="Northline Mobile",
    short="Northline",
    recipient="bereavement@northline.example",
    documents=("death certificate (photo)",),
    account_ref="4417",
    account_label="mobile line ending 4417",
    consequence=(
        "Northline will update the account holder; Yusuf's online account login may stop working"
    ),
)
CRESCENT = ProviderFacts(
    name="Crescent Bank",
    short="Crescent Bank",
    recipient="bereavement@crescentbank.example",
    documents=("death certificate (certified copy)",),
    account_ref="0932",
    account_label="current account ending 0932",
    consequence="",
)
PROVIDERS = {"Northline Mobile": NORTHLINE, "Crescent Bank": CRESCENT}
ALLOWED_RECIPIENTS = (NORTHLINE.recipient, CRESCENT.recipient)
SERVICE_LABELS = {
    "4417": "Mobile line ending 4417",
    "2290": "Mobile line ending 2290",
    "0932": "Current account ending 0932",
    "CP-77120": "Electricity, 14 Orchard Row",
    "SB-88213": "Streaming subscription",
    "FL-5531": "Membership FL-5531",
    "HW-20418": "Water, 14 Orchard Row",
    "ML-6610": "Policy letter",
    "PB-3017": "Book club subscription",
}
FAMILY_CONFIRMED = {"4417", "CP-77120", "SB-88213", "FL-5531", "HW-20418", "PB-3017"}


@dataclass(frozen=True)
class DemoEmail:
    """One clearly labelled fictional forward."""

    evidence: str
    body: str
    document: DocOut


@dataclass(frozen=True)
class DemoPhoto:
    """Synthetic stand-in bytes for a photographed bill or letter. Not a real image."""

    evidence: str
    label: str
    image: bytes
    document: DocOut


@dataclass
class MalikResult:
    """What the scripted conversation produced on fakes."""

    conversation: Conversation
    sent: list[Outbound]
    cipher: VaultCipher


def demo_repackager(command: list[str], ogg: bytes) -> bytes:
    """Stand in for ffmpeg. It still requires the copy-audio argument list."""
    if command[command.index("-c:a") + 1] != "copy":
        raise RuntimeError("demo repackager expected a copy command")
    return b"FICTIONAL-DEMO-WEBM-" + ogg


def sara_intake() -> IntakeOut:
    return IntakeOut(
        deceased_name=QuotedStr(value="Yusuf Malik", quote="My dad, Yusuf Malik, passed away"),
        date_of_death=QuotedStr(value="3rd of March", quote="on the 3rd of March"),
        speaker_name=QuotedStr(value="Sara", quote="I'm his daughter Sara"),
        stated_role=QuotedStr(
            value="his daughter, sorting things out",
            quote="I'm his daughter Sara, I'm sorting things out",
        ),
        household_members=[
            HouseholdMemberOut(name="Mum", relationship="mother", quote="keep Mum's phone")
        ],
        intent_keep=[
            QuotedStr(value="Mum's phone", quote="keep Mum's phone"),
            QuotedStr(value="Dad's voicemail", quote="his voicemail"),
        ],
        intent_stop=[
            QuotedStr(value="bills nobody needs", quote="stop the bills that don't matter")
        ],
        intent_protect=[QuotedStr(value="his voicemail", quote="I can't lose that")],
        missing_fields=[],
    )


def amina_dependency() -> DependencyOut:
    return DependencyOut(
        kind="access",
        statement=AMINA_SCRIPT,
        linked_provider="Crescent Bank",
        linked_number="4417",
        evidence_quote=AMINA_SCRIPT,
    )


def _doc(
    *,
    doc_type: str,
    form: str,
    provider: str,
    account_reference: str,
    quote: str,
    name: str | None,
    confidence: str = "high",
) -> DocOut:
    return DocOut(
        doc_type=doc_type,
        form=form,  # type: ignore[arg-type]
        name=name,
        date_of_death=None,
        certificate_number=None,
        provider=provider,
        account_reference=account_reference,
        amounts=[],
        billing_period=None,
        quotes=[quote],
        confidence=confidence,  # type: ignore[arg-type]
    )


def demo_emails() -> tuple[DemoEmail, ...]:
    """Six fictional forwards. The sixth repeats account 4417 so the merge stays at nine."""
    rows = (
        (
            "Forwarded email: Northline bill",
            "FICTIONAL DEMO — not a real message.\n"
            "From: billing@northline.example\n"
            "Yusuf Malik, line ending 4417. Amount due $40 for March 2026.",
            _doc(
                doc_type="bill",
                form="scan",
                provider="Northline Mobile",
                account_reference="4417",
                quote="line ending 4417",
                name="Yusuf Malik",
            ),
        ),
        (
            "Forwarded email: Crescent statement",
            "FICTIONAL DEMO — not a real message.\n"
            "From: statements@crescentbank.example\n"
            "Y. Malik, account ending 0932. This may be a joint account.",
            _doc(
                doc_type="bank_statement",
                form="scan",
                provider="Crescent Bank",
                account_reference="0932",
                quote="account ending 0932",
                name="Y. Malik",
                confidence="low",
            ),
        ),
        (
            "Forwarded email: StreamBox",
            "FICTIONAL DEMO — not a real message.\n"
            "From: help@streambox.example\n"
            "Yusuf Malik, subscription SB-88213.",
            _doc(
                doc_type="subscription",
                form="scan",
                provider="StreamBox",
                account_reference="SB-88213",
                quote="SB-88213",
                name="Yusuf Malik",
            ),
        ),
        (
            "Forwarded email: FitLife",
            "FICTIONAL DEMO — not a real message.\n"
            "From: members@fitlife.example\n"
            "Yusuf Malik, membership FL-5531.",
            _doc(
                doc_type="membership",
                form="scan",
                provider="FitLife Gym",
                account_reference="FL-5531",
                quote="FL-5531",
                name="Yusuf Malik",
            ),
        ),
        (
            "Forwarded email: Paperleaf Books",
            "FICTIONAL DEMO — not a real message.\n"
            "From: club@paperleaf.example\n"
            "Yusuf Malik, book club PB-3017. Web form only.",
            _doc(
                doc_type="subscription",
                form="scan",
                provider="Paperleaf Books",
                account_reference="PB-3017",
                quote="PB-3017",
                name="Yusuf Malik",
            ),
        ),
        (
            "Forwarded email: Northline receipt",
            "FICTIONAL DEMO — not a real message.\n"
            "From: billing@northline.example\n"
            "Receipt for Yusuf Malik, line ending 4417.",
            _doc(
                doc_type="receipt",
                form="scan",
                provider="Northline Mobile",
                account_reference="4417",
                quote="line ending 4417",
                name="Yusuf Malik",
            ),
        ),
    )
    return tuple(DemoEmail(evidence, body, document) for evidence, body, document in rows)


def demo_photos() -> tuple[DemoPhoto, ...]:
    """Four fictional photo stand-ins. One model guess claims a certified copy; code will not."""
    rows = (
        (
            "Photo of a bill: Northline 2290",
            "FICTIONAL DEMO IMAGE: photo of a Northline bill, line ending 2290. "
            "Name not shown. Not a real photograph.",
            b"FICTIONAL-DEMO-PHOTO-2290",
            _doc(
                doc_type="bill",
                form="photo",
                provider="Northline Mobile",
                account_reference="2290",
                quote="line ending 2290",
                name=None,
                confidence="low",
            ),
        ),
        (
            "Photo of a bill: City Power",
            "FICTIONAL DEMO IMAGE: photo of a City Power bill, CP-77120, 14 Orchard Row. "
            "Not a real photograph.",
            b"FICTIONAL-DEMO-PHOTO-CP-77120",
            _doc(
                doc_type="bill",
                form="photo",
                provider="City Power",
                account_reference="CP-77120",
                quote="CP-77120",
                name="Yusuf Malik",
            ),
        ),
        (
            "Photo of a bill: Harbor Water",
            "FICTIONAL DEMO IMAGE: photo of a Harbor Water bill, HW-20418. Not a real photograph.",
            b"FICTIONAL-DEMO-PHOTO-HW-20418",
            _doc(
                doc_type="bill",
                form="photo",
                provider="Harbor Water",
                account_reference="HW-20418",
                quote="HW-20418",
                name="Yusuf Malik",
            ),
        ),
        (
            "Photo of a letter: Meridian Life",
            "FICTIONAL DEMO IMAGE: photo of a Meridian Life letter, ML-6610. "
            "Name partly hidden. Not a real photograph.",
            b"FICTIONAL-DEMO-PHOTO-ML-6610",
            _doc(
                doc_type="letter",
                form="certified_copy_held",
                provider="Meridian Life",
                account_reference="ML-6610",
                quote="ML-6610",
                name=None,
                confidence="low",
            ),
        ),
    )
    return tuple(
        DemoPhoto(evidence, label, image, document) for evidence, label, image, document in rows
    )


def register_malik_fixtures(ai: FakeAI) -> None:
    """Record the model outputs the script will request. Missing keys still raise."""
    ai.register_transcript(demo_repackager(["ffmpeg", "-c:a", "copy"], SARA_OGG), SARA_SCRIPT)
    ai.register_transcript(demo_repackager(["ffmpeg", "-c:a", "copy"], AMINA_OGG), AMINA_SCRIPT)
    ai.register_structured("intake", IntakeOut, intake_messages(SARA_SCRIPT), sara_intake())
    ai.register_structured(
        "dependency", DependencyOut, dependency_messages(AMINA_SCRIPT), amina_dependency()
    )
    for email in demo_emails():
        ai.register_structured(
            "document_reader", DocOut, email_messages(email.body), email.document
        )
    for photo in demo_photos():
        ai.register_structured(
            "document_reader",
            DocOut,
            photo_messages(photo.label),
            photo.document,
            images=[ImageInput(data=photo.image, mime=PHOTO_MIME)],
        )


def malik_conversation(ai: FakeAI) -> Conversation:
    return Conversation(
        ai,
        providers=PROVIDERS,
        allowed_recipients=ALLOWED_RECIPIENTS,
        line=NORTHLINE,
        invites={
            INVITE_TOKEN: Invite(
                token=INVITE_TOKEN,
                name="Amina Malik",
                stated_role="his wife; lives in the family home",
            )
        },
        case_date=date(2026, 3, 3),
        runner=demo_repackager,
    )


async def run_malik_script(ai: FakeAI, channel: Channel) -> MalikResult:
    """Sara's voice note through the Northline approval card, on fakes only."""
    register_malik_fixtures(ai)
    conversation = malik_conversation(ai)
    cipher = VaultCipher(None)
    sent: list[Outbound] = []
    sara = "1001"
    amina = "2002"

    async def emit(items: list[Outbound]) -> None:
        sent.extend(items)
        for item in items:
            if item.options:
                await channel.send_buttons(item.to, item.text, item.options)
            else:
                await channel.send_text(item.to, item.text)

    await emit(await conversation.handle_voice(sara, SARA_OGG))
    await emit(await conversation.handle_button(sara, "confirm_intake"))
    for email in demo_emails():
        await conversation.ingest_forward(email.body, email.evidence)
    for photo in demo_photos():
        await conversation.ingest_picture(
            image=photo.image,
            mime=PHOTO_MIME,
            label=photo.label,
            evidence=photo.evidence,
            cipher=cipher,
        )
    conversation.apply_labels(SERVICE_LABELS)
    conversation.confirm_refs(FAMILY_CONFIRMED)
    await emit([conversation.coverage_outbound(sara)])
    await emit(await conversation.handle_text(amina, f"/start {INVITE_TOKEN}"))
    await emit(conversation.ask_dependency(amina))
    await emit(await conversation.handle_voice(amina, AMINA_OGG))
    return MalikResult(conversation=conversation, sent=sent, cipher=cipher)
