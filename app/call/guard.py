"""Commitment phrases on model speech. This reduces risk. It is not a guarantee."""

from __future__ import annotations

import re

# Phrases from AFTERWARD-TECH T9 ("we accept", "agreed", "go ahead"), matched in context so
# ordinary call manners ("please go ahead", "nothing has been agreed") don't cut the agent off.
# Matching them does not make the guard perfect.
COMMITMENT_PHRASES: tuple[str, ...] = (
    "we accept",
    "i accept",
    "agreed",
    "go ahead",
    "it's a deal",
    "we agree",
)

_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(we|i)\s+(accept|agree)\b",
        r"\b(it'?s|that'?s)\s+a\s+deal\b",
        r"\bdeal\s*[.!]",
        r"(^|[.!?]\s+)agreed\b",  # "Agreed." as an answer
        r"\b(?:we|i)\s+(?:have\s+)?agreed\b",
        r"\bgo\s+ahead\s+(?:with|and)\b",  # "go ahead with the plan", "go ahead and set it up"
        r"\b(?:yes|yeah|ok(?:ay)?|sure),?\s+go\s+ahead\b",
        r"\bplease\s+(?:proceed|process)\b",
        r"\bwe(?:'ll| will)\s+take\s+it\b",
    )
)


def commitment_tripped(transcript: str) -> bool:
    """True when model speech sounds like agreeing to terms. Not a proof of safety."""
    return any(pattern.search(transcript) for pattern in _PATTERNS)
