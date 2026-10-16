"""Honest coverage. There is no field for looking complete."""

from dataclasses import dataclass

from app.discovery.candidates import Candidate

NOT_SEARCHED = (
    "Yusuf's own inbox (no access, by design)",
    "Other email addresses he used",
    "Paper post that hasn't been photographed",
    "Anything paid in cash",
)

WHERE_ELSE = (
    "Bank statements: look for direct debits",
    "Post arriving over the next few weeks",
    "App-store subscriptions on his phone",
)


@dataclass(frozen=True)
class Coverage:
    """Sources searched, sources skipped, unconfirmed candidates, and where else to look."""

    searched: tuple[str, ...]
    not_searched: tuple[str, ...]
    unconfirmed: tuple[str, ...]
    where_else: tuple[str, ...]


def coverage_panel(
    candidates: list[Candidate], *, emails: int, photos: int, manual: int = 0
) -> Coverage:
    """Build the panel from what was actually ingested. The list stays open."""
    if manual == 0:
        manual_line = "Accounts Sara added by hand (none yet)"
    else:
        manual_line = f"{manual} accounts added by hand"
    unconfirmed = tuple(item.service_label for item in candidates if item.ownership != "confirmed")
    return Coverage(
        searched=(
            f"{emails} emails Sara forwarded",
            f"{photos} photos of bills and letters",
            manual_line,
        ),
        not_searched=NOT_SEARCHED,
        unconfirmed=unconfirmed,
        where_else=WHERE_ELSE,
    )


def render_coverage(coverage: Coverage, *, emails: int, photos: int, total: int) -> str:
    """Short chat line. It counts what we found and does not say the search is finished."""
    pending = len(coverage.unconfirmed)
    return (
        f"From the {emails} emails and {photos} photos you sent, "
        f"I found {total} possible accounts. "
        f"{pending} need you to confirm whose they are. "
        "Paper-only accounts won't show up here; "
        "bank statements are the best place to look for more."
    )
