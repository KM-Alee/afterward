"""Realtime call tools. There is no accept tool."""

from __future__ import annotations

import json
from contextvars import ContextVar

from agents import function_tool

from app.call.acceptance import CallRoom, OfferedTerms, Turn
from app.contracts import CALL_TOOL_NAMES, make_call_agent

CALL_INSTRUCTIONS = (
    "You are Afterward, an AI assistant phoning Northline Mobile's bereavement team for the"
    " Malik family. Yusuf Malik has died. You are on a live voice call in a web browser "
    "(not a phone call), talking to a Northline representative.\n"
    "\n"
    "How to talk:\n"
    "- Sound like a calm, courteous person on the phone. Short turns: one or two sentences,"
    " then stop and listen. Never read lists or long paragraphs aloud.\n"
    "- When the call starts or the representative greets you, say who you are in one "
    'sentence ("I\'m Afterward, an AI assistant calling for the Malik family"), then state '
    "the request briefly.\n"
    "- Call get_request_and_conditions before you state the request, and stick to what it "
    "returns.\n"
    "- Answer the question you were asked. If you didn't catch something, ask them to "
    "repeat it.\n"
    "- If the representative talks over you, stop and listen.\n"
    "\n"
    "What you may do:\n"
    "- Read the request and its conditions.\n"
    "- When they offer terms (months, price, number kept, voicemail kept), call "
    "report_offered_terms with exactly what they said, then tell them you'll check with the"
    " family. Do not invent terms.\n"
    "- Ask the family with request_family_decision when a choice is needed.\n"
    "- Ask for a person with request_human_help if they will only deal with a person.\n"
    "- End politely with end_call only when the conversation is clearly over.\n"
    "\n"
    "What you must never do:\n"
    "- You cannot accept, agree to, or confirm terms, sign anything, or move money. Never "
    "say the family agrees or that something is a deal. Say instead that the family "
    "decides, and that you'll come back with their answer.\n"
    "- If the family has approved an offer, the system says the approved sentence itself; "
    "you do not.\n"
    "- A speech check may cut you off if a sentence sounds like agreeing. It is not "
    "perfect.\n"
    "\n"
)

FALLBACK_LINE = (
    "Move Northline line 4417 to Amina Malik. Keep the number and the voicemail. "
    "Do not start a new contract."
)

_ROOM: ContextVar[CallRoom | None] = ContextVar("afterward_call_room", default=None)


def bind_room(room: CallRoom | None) -> None:
    """Point the tools at the call that is open. Tests set this; the model does not."""
    _ROOM.set(room)


def _room() -> CallRoom | None:
    return _ROOM.get()


def request_text(room: CallRoom | None) -> tuple[str, str]:
    """The request to read out and where it came from: the approved plan, else scripted."""
    provider = getattr(room, "request_provider", None)
    if provider is not None:
        try:
            planned = provider()
        except Exception:
            planned = None
        if planned:
            return planned, "plan"
    return FALLBACK_LINE, "scripted"


async def read_request_and_conditions(room: CallRoom | None) -> str:
    """Body of the read-only request tool. Records `via` on the room."""
    text, via = request_text(room)
    if room is not None:
        room.request_via = via
    body = f"Request: {text}"
    if room is not None and room.terms is not None:
        terms = room.terms
        body += (
            f" Current offer on the table: {terms.months} months at ${terms.price} a month. "
            f"Number: {terms.number_kept}. Voicemail: {terms.voicemail_preserved}."
        )
    body += " Nothing has been accepted."
    return json.dumps({"via": via, "request": body})


@function_tool
async def get_request_and_conditions() -> str:
    """Read the approved request and its conditions. This does not accept anything."""
    return await read_request_and_conditions(_room())


async def do_report_offered_terms(
    room: CallRoom | None,
    months: int,
    monthly_price: str,
    number_kept: str,
    voicemail_preserved: str,
) -> str:
    """Record offered terms on the room. Never accepts them."""
    if room is None:
        return "No call is bound. Nothing was accepted."
    digest = await room.report_offered_terms(
        OfferedTerms(
            months=months,
            price=str(monthly_price).lstrip("$"),
            number_kept=number_kept,
            voicemail_preserved=voicemail_preserved,
        )
    )
    return f"Recorded. Terms hash {digest[:12]}. Not accepted."


def do_request_family_decision(
    room: CallRoom | None, summary: str, option_one: str, option_two: str, option_three: str
) -> str:
    labels = "; ".join((option_one, option_two, option_three))
    if room is not None and room.approval_status != "void":
        room.approval_status = "pending"
    if room is not None:
        room.turns.append(
            Turn(
                who="system",
                text=f"Asked the family: {summary} Options: {labels}.",
                kind="decision",
            )
        )
    return "The family has been asked. Nothing was accepted."


def do_request_human_help(room: CallRoom | None, reason: str) -> str:
    if room is not None:
        room.turns.append(Turn(who="system", text=f"A person is needed. {reason}", kind="handoff"))
    return "A person will take this step. Nothing was accepted."


async def do_end_call(room: CallRoom | None, reason: str) -> str:
    if room is not None:
        room.status = "ended"
        room.turns.append(Turn(who="system", text=f"Call ended. {reason}", kind="ended"))
        if room.session.started and not room.session.stopped:
            await room.session.stop()
    return "The call has ended. Nothing was accepted."


@function_tool
async def report_offered_terms(
    months: int,
    monthly_price: str,
    number_kept: str,
    voicemail_preserved: str,
) -> str:
    """Record terms the representative offered. This does not accept them."""
    return await do_report_offered_terms(
        _room(), months, monthly_price, number_kept, voicemail_preserved
    )


@function_tool(needs_approval=True)
async def request_family_decision(
    summary: str, option_one: str, option_two: str, option_three: str
) -> str:
    """Ask the family. At most three options. Acceptance is not a tool result."""
    return do_request_family_decision(_room(), summary, option_one, option_two, option_three)


@function_tool
async def request_human_help(reason: str) -> str:
    """The organisation will not deal with the assistant. Hand the step back."""
    return do_request_human_help(_room(), reason)


@function_tool
async def end_call(reason: str) -> str:
    """End the call without agreeing to terms."""
    return await do_end_call(_room(), reason)


def call_tools() -> list[object]:
    """The five allowed tools, in contract order."""
    tools = [
        get_request_and_conditions,
        report_offered_terms,
        request_family_decision,
        request_human_help,
        end_call,
    ]
    names = [str(getattr(tool, "name", "")) for tool in tools]
    if tuple(names) != CALL_TOOL_NAMES:
        raise RuntimeError("Call tools drifted from the contract list")
    return tools


def build_call_agent():
    """Construct the realtime agent. An accept tool is rejected by the contract."""
    return make_call_agent(
        name="call_agent",
        instructions=CALL_INSTRUCTIONS,
        tools=call_tools(),
    )
