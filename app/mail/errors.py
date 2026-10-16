"""Mail failures. Messages name the rule and never include mailbox contents."""


class MailError(Exception):
    """A mail rule failed closed."""


class HistoryExpired(MailError):
    """The Gmail history cursor is too old. The poller must list recent mail."""


class DeliveryUncertain(MailError):
    """The send may have left the mailbox. Reconcile before sending again."""


class MailboxNotConfigured(MailError):
    """This process has no refresh token for that mailbox."""


class FooterMissing(MailError):
    """The outbound text does not contain the visible reconciliation marker."""
