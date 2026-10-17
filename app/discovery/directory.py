"""Provider directory, tracks and locators. Tracks come from data, never from the model."""

import re
from dataclasses import dataclass

ORDINARY = "ordinary"
FINANCIAL = "financial"
INSURANCE = "insurance_pension"
HANDBACK = "handback"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class DirectoryEntry:
    """What we know about one organisation. A missing entry is `unknown`, not a guess."""

    name: str
    category: str
    track: str


# Fictional demo organisations. Real entries are added per country as data.
DIRECTORY: dict[str, DirectoryEntry] = {
    entry.name.lower(): entry
    for entry in (
        DirectoryEntry("Northline Mobile", "mobile", ORDINARY),
        DirectoryEntry("City Power", "electricity", ORDINARY),
        DirectoryEntry("Harbor Water", "water", ORDINARY),
        DirectoryEntry("StreamBox", "streaming", ORDINARY),
        DirectoryEntry("FitLife Gym", "membership", ORDINARY),
        DirectoryEntry("Paperleaf Books", "subscription", ORDINARY),
        DirectoryEntry("Crescent Bank", "bank", FINANCIAL),
        DirectoryEntry("Meridian Life", "life insurance", INSURANCE),
    )
}

# Legal, government, tax and court bodies. Afterward prepares; a person does the step.
_HANDBACK_WORDS = (
    "tax",
    "revenue",
    "probate",
    "court",
    "registry",
    "register office",
    "registrar",
    "benefit",
    "social security",
    "passport",
    "licence",
    "license",
    "dvla",
    "hmrc",
    "irs",
    "fbr",
    "nadra",
    "tell us once",
    "council",
)
# Whole words only, so "First Insurance" does not match "irs" and "Syntax" does not match "tax".
_HANDBACK_RE = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in _HANDBACK_WORDS) + r")s?\b")
_FINANCIAL_WORDS = ("bank", "building society", "credit card", "loan", "mortgage")
_INSURANCE_WORDS = ("insurance", "assurance", "pension", "life cover")

_ACTIONS: dict[str, frozenset[str]] = {
    ORDINARY: frozenset({"plan", "send_with_approval"}),
    FINANCIAL: frozenset({"notify_with_approval"}),
    INSURANCE: frozenset({"notify_with_approval", "prepare_packet"}),
    HANDBACK: frozenset({"prepare_packet", "family_marked_done"}),
    UNKNOWN: frozenset({"plan"}),
}


def lookup(provider: str) -> DirectoryEntry | None:
    return DIRECTORY.get(provider.strip().lower())


def track_for(provider: str) -> str:
    """Directory first, then cautious keyword rules. Government wins over everything else."""
    name = provider.strip().lower()
    if not name:
        return UNKNOWN
    if _HANDBACK_RE.search(name):
        return HANDBACK
    entry = DIRECTORY.get(name)
    if entry is not None:
        return entry.track
    if any(word in name for word in _INSURANCE_WORDS):
        return INSURANCE
    if any(word in name for word in _FINANCIAL_WORDS):
        return FINANCIAL
    return UNKNOWN


def allowed_actions(*, ownership: str, track: str) -> frozenset[str]:
    """Nothing is allowed until the family confirms. Hand-back steps never get a send."""
    if ownership != "confirmed":
        return frozenset()
    return _ACTIONS.get(track, frozenset())


def filter_actions(*, ownership: str, track: str, proposed: list[str]) -> list[str]:
    """Drop any model-proposed action the track does not allow."""
    allowed = allowed_actions(ownership=ownership, track=track)
    return [action for action in proposed if action in allowed]


@dataclass(frozen=True)
class Locator:
    """An official search the family runs themselves. We prepare; we never submit."""

    id: str
    name: str
    finds: str
    result_goes_to: str
    fictional: bool = True


LOCATORS: tuple[Locator, ...] = (
    Locator(
        "policy",
        "Policy locator (demo)",
        "Asks insurers whether he held a life policy.",
        "Insurers reply to the beneficiary directly.",
    ),
    Locator(
        "unclaimed",
        "Unclaimed money search (demo)",
        "Dormant accounts and unclaimed property.",
        "Results go to the person who searched.",
    ),
)

HANDBACK_STEPS: dict[str, str] = {
    "copies": (
        "Certified copies of the death certificate: order them from the register office. "
        "A phone photo is never a certified copy."
    ),
    "probate": (
        "Probate (the grant): banks often need it before closing an account. "
        "A person applies; Afterward lists what the application asks for and does not file it."
    ),
    "government": (
        "Government offices: tax, benefits, passport and licence. You tell them through the "
        "official service. Afterward prepares the reference numbers and does not file anything."
    ),
    "claim": (
        "Insurance claim: the beneficiary files it with the insurer. Afterward can send a "
        "notification once you approve it; the claim itself is yours."
    ),
}
