"""Document intake and Fernet encryption. A missing key stays in memory and is never written."""

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

from cryptography.fernet import Fernet

from app.ai.schemas import DocOut

_MONTHS = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


@dataclass
class VaultItem:
    """One encrypted document plus the fields and mismatch flags the family should see."""

    doc_type: str
    form: str
    fields: dict[str, object]
    mismatch_flags: list[str] = field(default_factory=list)
    blob: bytes = b""
    sha256: str = ""


class VaultCipher:
    """Fernet helper. Generated keys are kept on the instance only."""

    def __init__(self, key: str | bytes | None = None) -> None:
        material = _material(key)
        self.generated = material is None
        raw = Fernet.generate_key() if material is None else material
        self._fernet = Fernet(raw)

    def __repr__(self) -> str:
        return "VaultCipher(key=hidden)"

    def encrypt(self, plaintext: bytes) -> bytes:
        return self._fernet.encrypt(plaintext)

    def decrypt(self, token: bytes) -> bytes:
        return self._fernet.decrypt(token)


def intake_document(
    *,
    doc: DocOut,
    raw_form: str,
    image: bytes,
    cipher: VaultCipher,
    source: str,
    case_date: date | None = None,
    deceased_name: str | None = None,
    expected_type: str | None = None,
) -> VaultItem:
    """Store type, form and fields. A phone photo is never a certified copy."""
    form = "photo" if source == "phone_photo" else doc.form
    flags: list[str] = []
    if source == "phone_photo" and raw_form != "photo":
        flags.append("form_overridden_photo")
    if case_date is not None and _dates_conflict(doc.date_of_death, case_date):
        flags.append("date_of_death_mismatch")
    if names_conflict(doc.name, deceased_name):
        flags.append("name_mismatch")
    if expected_type and doc.doc_type and _norm(doc.doc_type) != _norm(expected_type):
        flags.append("type_mismatch")
    return VaultItem(
        doc_type=doc.doc_type,
        form=form,
        fields={
            "name": doc.name,
            "date_of_death": doc.date_of_death,
            "certificate_number": doc.certificate_number,
            "provider": doc.provider,
            "account_reference": doc.account_reference,
            "amounts": list(doc.amounts),
            "billing_period": doc.billing_period,
            "quotes": list(doc.quotes),
            "confidence": doc.confidence,
        },
        mismatch_flags=flags,
        blob=cipher.encrypt(image),
        sha256=hashlib.sha256(image).hexdigest(),
    )


def mismatch_message(item: VaultItem) -> str | None:
    """A short explanation when the photo is not the document we expected."""
    if "type_mismatch" in item.mismatch_flags and item.doc_type == "bank_statement":
        return "This looks like a bank statement, not the certificate."
    if "form_overridden_photo" in item.mismatch_flags:
        return "This is a phone photo, so it is not a certified copy."
    if "date_of_death_mismatch" in item.mismatch_flags:
        return "The date on this document does not match the date on the case."
    return None


def names_conflict(extracted: str | None, deceased: str | None) -> bool:
    """True when the names share no real word. Initials alone do not count as a clash."""
    if not extracted or not deceased:
        return False
    left = {token for token in _tokens(extracted) if len(token) >= 2}
    right = {token for token in _tokens(deceased) if len(token) >= 2}
    return not bool(left & right)


def _material(key: str | bytes | None) -> bytes | None:
    if key is None:
        return None
    if isinstance(key, str):
        stripped = key.strip()
        if not stripped:
            return None
        return stripped.encode()
    if not key:
        return None
    return key


def _tokens(value: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", value.lower())


def _norm(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


def _dates_conflict(extracted: str | None, case_date: date) -> bool:
    parsed = _parse_loose_date(extracted)
    return parsed is not None and parsed != case_date


def _parse_loose_date(value: str | None) -> date | None:
    if not value:
        return None
    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", value.strip())
    if iso:
        return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    text = value.lower().replace(",", " ")
    match = re.search(r"(\d{1,2})\s+([a-z]+)\s+(\d{4})", text)
    if match and match.group(2) in _MONTHS:
        return date(int(match.group(3)), _MONTHS[match.group(2)], int(match.group(1)))
    match = re.search(r"([a-z]+)\s+(\d{1,2})\s+(\d{4})", text)
    if match and match.group(1) in _MONTHS:
        return date(int(match.group(3)), _MONTHS[match.group(1)], int(match.group(2)))
    return None
