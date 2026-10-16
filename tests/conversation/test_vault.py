"""Vault intake forces a phone photo to stay a photo and encrypts the bytes."""

from datetime import date

from cryptography.fernet import Fernet

from app.ai.schemas import DocOut
from app.config import Settings
from app.discovery.vault import VaultCipher, intake_document, mismatch_message, names_conflict


def _statement() -> DocOut:
    return DocOut(
        doc_type="bank_statement",
        form="certified_copy_held",
        name="Jane Roe",
        date_of_death="4 March 2026",
        certificate_number=None,
        provider="Crescent Bank",
        account_reference="0932",
        amounts=["$10.00"],
        billing_period="February 2026",
        quotes=["4 March 2026"],
        confidence="low",
    )


def test_phone_photo_is_never_a_certified_copy():
    key = Fernet.generate_key()
    cipher = VaultCipher(key)
    image = b"FICTIONAL-DEMO-CERTIFICATE-PHOTO"
    item = intake_document(
        doc=_statement(),
        raw_form="certified_copy_held",
        image=image,
        cipher=cipher,
        source="phone_photo",
        case_date=date(2026, 3, 3),
        deceased_name="Yusuf Malik",
        expected_type="death_certificate",
    )
    assert item.form == "photo"
    assert item.doc_type == "bank_statement"
    assert "form_overridden_photo" in item.mismatch_flags
    assert "date_of_death_mismatch" in item.mismatch_flags
    assert "name_mismatch" in item.mismatch_flags
    assert "type_mismatch" in item.mismatch_flags
    assert image not in item.blob
    assert cipher.decrypt(item.blob) == image
    assert mismatch_message(item) == "This looks like a bank statement, not the certificate."
    assert names_conflict("Y. Malik", "Yusuf Malik") is False


def test_missing_vault_key_stays_in_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cipher = VaultCipher(Settings().vault_key.get_secret_value())
    assert cipher.generated is True
    token = cipher.encrypt(b"FICTIONAL")
    assert cipher.decrypt(token) == b"FICTIONAL"
    assert list(tmp_path.iterdir()) == []
    assert "key=hidden" in repr(cipher)
