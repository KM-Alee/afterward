"""Generate secrets only on an explicit human invocation; never run this in CI."""

import secrets

from cryptography.fernet import Fernet


def main() -> None:
    """Print directly for the operator to transfer into platform environment variables."""
    print("VAULT_KEY=" + Fernet.generate_key().decode())
    for name in ("DEMO_PASSCODE", "TELEGRAM_WEBHOOK_SECRET", "WHATSAPP_VERIFY_TOKEN"):
        print(name + "=" + secrets.token_urlsafe(32))


if __name__ == "__main__":
    main()
