"""Care response. Admin waits until the person chooses to continue."""

from app.contracts import Option

CARE_TEXT = (
    "I'm really sorry you're carrying this. You don't have to handle the admin right now. "
    "If you need someone to talk to, findahelpline.com can help you find local support. "
    "I'll pause the admin conversation until you choose to continue."
)

CONTINUE = Option(id="continue_admin", label="Continue")

PAUSED_TEXT = (
    "The admin conversation is paused. I'm here if you want to talk to someone; "
    "findahelpline.com can help you find local support. "
    "Choose continue when you want to pick the admin back up."
)
