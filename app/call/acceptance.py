"""Server-built acceptance. The model has no accept path."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field

from app.call.guard import commitment_tripped
from app.contracts import CallEvent, CallEventKind, CallSession, CallTransport

DISCLOSURE = (
    "I'm Afterward, an AI assistant calling on behalf of the Malik family. "
    "This is a browser call, not a phone call."
)


@dataclass(frozen=True)
class OfferedTerms:
    """Terms a representative offered. They are not an acceptance."""

    months: int
    price: str
    number_kept: str
    voicemail_preserved: str


@dataclass
class Turn:
    """One transcript line. `template` turns are the server sentence, not model speech."""

    who: str
    text: str
    via: str = ""
    kind: str = ""


def offered_terms_from_text(text: str, current: OfferedTerms | None) -> OfferedTerms | None:
    """Read a months-and-price offer out of representative speech. Other lines stay turns."""
    if current is None:
        return None
    months = re.search(r"(\d+)\s*month", text, re.IGNORECASE)
    price = re.search(r"\$(\d+)", text)
    if months is None or price is None:
        return None
    return OfferedTerms(
        int(months.group(1)),
        price.group(1),
        current.number_kept,
        current.voicemail_preserved,
    )


def hash_terms(terms: OfferedTerms) -> str:
    """Stable hash of the offered terms. Approval is bound to this value."""
    raw = json.dumps(
        {
            "months": terms.months,
            "price": terms.price,
            "number_kept": terms.number_kept,
            "voicemail_preserved": terms.voicemail_preserved,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def build_acceptance_sentence(terms: OfferedTerms) -> str:
    """Words the server will speak. The model does not write this sentence."""
    return (
        f"The Malik family accepts {terms.months} months at ${terms.price} a month, "
        "keeping the number and the existing voicemail."
    )


@dataclass
class CallRoom:
    """One browser call. Acceptance audio plays only after a fresh terms-hash check."""

    session: CallSession
    terms: OfferedTerms | None = None
    terms_hash: str | None = None
    approved_hash: str | None = None
    approval_status: str = "none"
    sentence: str | None = None
    turns: list[Turn] = field(default_factory=list)
    latency: list[dict[str, object]] = field(default_factory=list)
    guard_trips: list[str] = field(default_factory=list)
    acceptance_played: bool = False
    status: str = "ready"

    async def start(self) -> None:
        if self.session.started and not self.session.stopped:
            return
        await self.session.start(CallTransport.browser)
        self.status = "live"
        if not any(turn.kind == "disclosure" for turn in self.turns):
            self.turns.append(Turn(who="agent", text=DISCLOSURE, kind="disclosure"))

    async def report_offered_terms(self, terms: OfferedTerms) -> str:
        """Store offered terms. A new hash voids an earlier approval before any playback."""
        new_hash = hash_terms(terms)
        changed = self.approval_status == "approved" and self.approved_hash != new_hash
        self.terms = terms
        self.terms_hash = new_hash
        if changed:
            await self.void_for_terms_change()
            return new_hash
        self.turns.append(
            Turn(
                who="system",
                text=(f"Offered {terms.months} months at ${terms.price} a month. Not accepted."),
                kind="terms",
            )
        )
        return new_hash

    def approve(self, terms_hash: str) -> None:
        """Bind a family approval to the current hash. This does not play audio."""
        if self.terms is None or terms_hash != self.terms_hash:
            raise ValueError("Approval does not match the current terms")
        self.approved_hash = terms_hash
        self.approval_status = "approved"
        self.sentence = build_acceptance_sentence(self.terms)

    async def queue_acceptance(self) -> None:
        """Queue the server sentence while playback is suspended."""
        if self.approval_status != "approved" or self.terms is None or self.sentence is None:
            return
        if self.approved_hash != self.terms_hash or hash_terms(self.terms) != self.approved_hash:
            await self.void_for_terms_change()
            return
        await self.session.suspend_acceptance()
        await self.session.play_approved_sentence(self.sentence)

    async def void_for_terms_change(self) -> None:
        """Drop the approval and any queued clip before that clip can play."""
        self.approval_status = "void"
        self.approved_hash = None
        await self.session.discard_queued_acceptance()
        self.sentence = None
        self.acceptance_played = False
        self.turns.append(
            Turn(
                who="system",
                text=(
                    "The offer changed, so the earlier approval is void. "
                    "The queued acceptance was discarded and was not spoken."
                ),
                kind="discarded",
            )
        )

    async def discard_obsolete(self) -> None:
        """Drop queued acceptance audio that must not be played."""
        await self.session.discard_queued_acceptance()
        self.acceptance_played = False
        self.turns.append(
            Turn(
                who="system",
                text="Queued acceptance audio was discarded and was not spoken.",
                kind="discarded",
            )
        )

    async def on_representative_speech(self) -> None:
        """New representative speech suspends acceptance until the hash is checked again."""
        await self.session.suspend_acceptance()

    async def try_play_acceptance(self) -> bool:
        """Re-check the terms hash immediately before playback."""
        if (
            self.approval_status != "approved"
            or self.terms is None
            or self.sentence is None
            or self.approved_hash != self.terms_hash
            or hash_terms(self.terms) != self.approved_hash
        ):
            await self.session.discard_queued_acceptance()
            return False
        await self.session.resume_acceptance()
        if self.sentence not in self.session.played:
            await self.session.play_approved_sentence(self.sentence)
        self.acceptance_played = self.sentence in self.session.played
        if self.acceptance_played:
            self.turns.append(Turn(who="agent", text=self.sentence, kind="template"))
        return self.acceptance_played

    async def screen_model_speech(self, text: str) -> bool:
        """Stop model speech that sounds like an agreement. The check is not perfect."""
        if not commitment_tripped(text):
            self.turns.append(Turn(who="agent", text=text, kind="model"))
            return False
        self.guard_trips.append("commitment")
        await self.session.discard_queued_acceptance()
        self.acceptance_played = False
        if hasattr(self.session, "push_event"):
            self.session.push_event(
                CallEvent(
                    kind=CallEventKind.guardrail_tripped,
                    payload={"rule": "commitment"},
                )
            )
        self.turns.append(
            Turn(
                who="system",
                text=(
                    "The speech check stopped a possible agreement. "
                    "It reduces risk and is not a guarantee. Nothing was accepted."
                ),
                kind="guard",
            )
        )
        return True

    async def handle_typed_turn(self, text: str) -> None:
        """Typed text enters the same session. It suspends acceptance and does not accept."""
        started = time.monotonic()
        await self.start()
        await self.on_representative_speech()
        await self.session.send_typed_turn(text)
        self.turns.append(Turn(who="rep", text=text, via="typed"))
        offered = offered_terms_from_text(text, self.terms)
        if offered is not None and hash_terms(offered) != self.terms_hash:
            await self.report_offered_terms(offered)
        elapsed = max(0, round((time.monotonic() - started) * 1000))
        rep_turns = sum(1 for turn in self.turns if turn.who == "rep")
        self.latency.append({"turn": rep_turns, "client_total_ms": elapsed, "via": "typed"})
        if hasattr(self.session, "push_event"):
            self.session.push_event(
                CallEvent(
                    kind=CallEventKind.latency,
                    payload={"client_total_ms": elapsed, "via": "typed"},
                )
            )
