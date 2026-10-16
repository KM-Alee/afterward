"""Commitment phrases on model speech. This reduces risk. It is not a guarantee."""

from __future__ import annotations

# Phrases from AFTERWARD-TECH T9. Matching them does not make the guard perfect.
COMMITMENT_PHRASES: tuple[str, ...] = (
    "we accept",
    "i accept",
    "agreed",
    "go ahead",
    "it's a deal",
    "we agree",
)


def commitment_tripped(transcript: str) -> bool:
    """True when model speech contains a commitment phrase. Not a proof of safety."""
    lowered = transcript.lower()
    return any(phrase in lowered for phrase in COMMITMENT_PHRASES)
