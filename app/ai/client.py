"""Agents SDK client. Tests inject a runner. An empty API key never opens a socket."""

from __future__ import annotations

import asyncio
import io
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict

from app.ai.prompts import PROMPTS
from app.ai.schemas import DependencyOut, DocOut, IntakeOut, ReplyOut, StatementOut
from app.ai.verify import force_photo_form
from app.config import Settings
from app.contracts import (
    AIRole,
    ChatMessage,
    ContractError,
    ImageInput,
    SpeechChunk,
    Transcript,
    configure_agents_sdk,
    make_structured_agent,
)
from app.engine.errors import AIUnavailable, CrisisPaused

FAST_MODEL = "gpt-6-luna"
ACCURATE_MODEL = "gpt-6.1-sol"
UPGRADE_MODEL = "gpt-6-astra"


def _named_audio(audio: bytes, name: str) -> io.BytesIO:
    """Give raw bytes a filename so the transcription API can see the type."""
    handle = io.BytesIO(audio)
    handle.name = name
    return handle


CARE_RESPONSE = (
    "I'm glad you said something. If you might be in crisis, please contact local "
    "emergency services or findahelpline.com. I will pause until you choose to continue."
)
CONSEQUENTIAL_TOOLS = frozenset({"propose_decision", "record_dependency_answer"})
_CRISIS = re.compile(
    r"\b(kill myself|suicide|suicidal|end my life|want to die|do not want to live)\b",
    re.IGNORECASE,
)


class FamilyConversationOut(BaseModel):
    """Short reply plus an optional proposal. The proposal grants nothing."""

    model_config = ConfigDict(extra="forbid")

    reply: str
    proposal: str | None = None


ROLE_SCHEMAS: dict[str, type[BaseModel]] = {
    "intake": IntakeOut,
    "family_conversation": FamilyConversationOut,
    "dependency": DependencyOut,
    "reply_reader": ReplyOut,
    "document_reader": DocOut,
}

# document_reader can also read a statement; it needs its own agent for that output type.
EXTRA_ROLE_SCHEMAS: dict[str, type[BaseModel]] = {"document_reader": StatementOut}
STATEMENT_AGENT = "statement_reader"

Runner = Callable[..., Awaitable[BaseModel | dict[str, object]]]


def tool_grants_permission(tool_name: str) -> bool:
    """Consequential tools pause for the engine. None of them grant permission."""
    del tool_name
    return False


def screen_crisis(text: str) -> bool:
    """True when the person's words should pause admin and return the care template."""
    return _CRISIS.search(text) is not None


def output_missing_quote(output: object) -> bool:
    """A populated field with no quote fails the quote-required guardrail."""
    if isinstance(output, ReplyOut):
        for commitment in output.commitments:
            if not commitment.evidence_quote.strip():
                return True
            if any(not fact.evidence_quote.strip() for fact in commitment.facts):
                return True
        return False
    if isinstance(output, IntakeOut):
        fields = (
            output.deceased_name,
            output.date_of_death,
            output.speaker_name,
            output.stated_role,
        )
        return any(field.value and not (field.quote or "").strip() for field in fields)
    if isinstance(output, DependencyOut):
        return not output.evidence_quote.strip()
    return False


@dataclass
class ToolHooks:
    """Read-only case facts and proposal sinks injected by the application.

    Nothing here approves anything. Without a provider a tool says so; it never invents data.
    """

    case_facts: Callable[[str], dict[str, object]] | None = None
    account_facts: Callable[[str], dict[str, object]] | None = None
    on_proposal: Callable[[str, dict[str, object]], None] | None = None
    proposals: list[tuple[str, dict[str, object]]] = field(default_factory=list)


NOT_AVAILABLE = "not available: no case data source is connected to this tool"


def _short(value: object, limit: int = 400) -> str:
    return " ".join(str(value or "").split())[:limit]


def tool_get_case_status(hooks: ToolHooks, case_ref: str) -> str:
    """Read-only case facts from the injected provider."""
    if hooks.case_facts is None:
        return NOT_AVAILABLE
    try:
        facts = hooks.case_facts(_short(case_ref, 64))
    except Exception:
        return "not available: case facts could not be read"
    return json.dumps(facts, default=str)


def tool_get_account(hooks: ToolHooks, account_ref: str) -> str:
    """Read-only account dimensions from the injected provider."""
    if hooks.account_facts is None:
        return NOT_AVAILABLE
    try:
        facts = hooks.account_facts(_short(account_ref, 128))
    except Exception:
        return "not available: account facts could not be read"
    return json.dumps(facts, default=str)


def _record_proposal(hooks: ToolHooks, kind: str, payload: dict[str, object]) -> str:
    if hooks.on_proposal is None:
        return NOT_AVAILABLE
    try:
        hooks.on_proposal(kind, payload)
    except Exception:
        return "not available: the proposal could not be recorded"
    hooks.proposals.append((kind, payload))
    return "Proposed to the family. Nothing is approved, sent or changed."


def tool_propose_decision(hooks: ToolHooks, summary: str) -> str:
    """Record a proposed decision for the family. Never approves."""
    return _record_proposal(hooks, "decision", {"summary": _short(summary)})


def tool_record_dependency_answer(hooks: ToolHooks, kind: str, statement: str) -> str:
    """Record a proposed dependency answer. Code turns it into conditions later."""
    return _record_proposal(
        hooks, "dependency", {"kind": _short(kind, 32), "statement": _short(statement)}
    )


def _message_text(messages: Sequence[ChatMessage]) -> str:
    return "\n".join(message.content for message in messages)


def _load_sdk():
    from agents import (
        GuardrailFunctionOutput,
        ModelSettings,
        function_tool,
        input_guardrail,
        output_guardrail,
    )
    from agents.retry import ModelRetryBackoffSettings, ModelRetrySettings

    return {
        "GuardrailFunctionOutput": GuardrailFunctionOutput,
        "ModelSettings": ModelSettings,
        "function_tool": function_tool,
        "input_guardrail": input_guardrail,
        "output_guardrail": output_guardrail,
        "ModelRetrySettings": ModelRetrySettings,
        "ModelRetryBackoffSettings": ModelRetryBackoffSettings,
    }


def build_agents(settings: Settings, hooks: ToolHooks | None = None):
    """Construct the five structured agents. Guardrails and approvals are attached here."""
    sdk = _load_sdk()
    tracing = bool(settings.agents_tracing and settings.openai_api_key.get_secret_value())
    configure_agents_sdk(tracing=tracing)

    @sdk["input_guardrail"](name="crisis")
    def crisis_guardrail(context, agent, incoming):
        del context, agent
        text = incoming if isinstance(incoming, str) else str(incoming)
        tripped = screen_crisis(text)
        return sdk["GuardrailFunctionOutput"](
            output_info={"care": CARE_RESPONSE} if tripped else None,
            tripwire_triggered=tripped,
        )

    @sdk["output_guardrail"](name="quote_required")
    def quote_guardrail(context, agent, output):
        del context, agent
        missing = output_missing_quote(output)
        return sdk["GuardrailFunctionOutput"](
            output_info={"missing_quote": missing},
            tripwire_triggered=missing,
        )

    hk = hooks if hooks is not None else ToolHooks()

    @sdk["function_tool"](needs_approval=False)
    def get_case_status(case_ref: str) -> str:
        """Read facts for a case reference. The engine supplies them; this does not decide."""
        return tool_get_case_status(hk, case_ref)

    @sdk["function_tool"](needs_approval=False)
    def get_account(account_ref: str) -> str:
        """Read an account's status dimensions. This cannot change the account."""
        return tool_get_account(hk, account_ref)

    @sdk["function_tool"](needs_approval=True)
    def propose_decision(summary: str) -> str:
        """Propose a family decision. This does not approve a plan or send anything."""
        return tool_propose_decision(hk, summary)

    @sdk["function_tool"](needs_approval=True)
    def record_dependency_answer(kind: str, statement: str) -> str:
        """Propose a dependency answer. Code turns it into conditions. This grants nothing."""
        return tool_record_dependency_answer(hk, kind, statement)

    retry = sdk["ModelRetrySettings"](
        max_retries=2,
        backoff=sdk["ModelRetryBackoffSettings"](
            initial_delay=0.2,
            max_delay=2,
            multiplier=2,
            jitter=False,
        ),
    )
    agents = {}
    for role, schema in ROLE_SCHEMAS.items():
        model = settings.llm_accurate_model if role == "reply_reader" else settings.llm_fast_model
        agent = make_structured_agent(
            name=role,
            instructions=PROMPTS[role],
            output_type=schema,
            model=model,
        )
        agent.model_settings = sdk["ModelSettings"](timeout=20, retry=retry)
        agents[role] = agent
    statement = make_structured_agent(
        name=STATEMENT_AGENT,
        instructions=PROMPTS[STATEMENT_AGENT],
        output_type=StatementOut,
        model=settings.llm_fast_model,
    )
    statement.model_settings = sdk["ModelSettings"](timeout=20, retry=retry)
    agents[STATEMENT_AGENT] = statement
    agents["intake"].input_guardrails = [crisis_guardrail]
    agents["intake"].output_guardrails = [quote_guardrail]
    agents["family_conversation"].input_guardrails = [crisis_guardrail]
    agents["family_conversation"].tools = [
        get_case_status,
        get_account,
        propose_decision,
        record_dependency_answer,
    ]
    agents["family_conversation"].handoffs = [agents["dependency"]]
    agents["dependency"].tools = [get_account]
    agents["dependency"].output_guardrails = [quote_guardrail]
    agents["reply_reader"].output_guardrails = [quote_guardrail]
    return agents


class AgentsSDKClient:
    """AIClient on the Agents SDK. `runner` replaces the network in tests."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runner: Runner | None = None,
        timeout_s: float = 20.0,
        max_retries: int = 2,
        retry_sleep_s: float = 0.0,
        session_engine: object | None = None,
    ) -> None:
        self._settings = settings or Settings()
        self._runner = runner
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.retry_sleep_s = retry_sleep_s
        self._session_engine = session_engine
        self.hooks = ToolHooks()
        self.agents = build_agents(self._settings, self.hooks)

    @property
    def case_facts(self) -> Callable[[str], dict[str, object]] | None:
        return self.hooks.case_facts

    @case_facts.setter
    def case_facts(self, provider: Callable[[str], dict[str, object]] | None) -> None:
        """Inject the read-only case facts provider used by get_case_status."""
        self.hooks.case_facts = provider

    def model_for(self, role: AIRole) -> str:
        """Fast for conversation and vision. Accurate for reply extraction. Upgrade is separate."""
        if role == "reply_reader":
            return self._settings.llm_accurate_model
        return self._settings.llm_fast_model

    def upgrade_model(self) -> str:
        """The drop-in accuracy upgrade. It is not selected unless a caller asks for it."""
        return UPGRADE_MODEL

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str,
        prompt: str = "",
        keywords: Sequence[str] = (),
    ) -> Transcript:
        key = self._settings.openai_api_key.get_secret_value()
        if not key:
            raise AIUnavailable("no_api_key")
        from openai import OpenAI

        suffix = "webm" if "webm" in mime else "ogg"
        file_obj = _named_audio(audio, f"note.{suffix}")
        client = OpenAI(api_key=key, timeout=self.timeout_s)

        def _call() -> object:
            kwargs: dict[str, object] = {
                "model": self._settings.stt_model,
                "file": file_obj,
                "languages": ["en"],
            }
            if prompt:
                kwargs["prompt"] = prompt
            if keywords:
                kwargs["keywords"] = list(keywords)
            return client.audio.transcriptions.create(**kwargs)  # type: ignore[arg-type]

        raw = await asyncio.to_thread(_call)
        text = raw if isinstance(raw, str) else str(getattr(raw, "text", "") or "")
        return Transcript(text=text, language="en")

    async def structured(
        self,
        role: AIRole,
        schema: type[BaseModel],
        messages: Sequence[ChatMessage],
        images: Sequence[ImageInput] | None = None,
    ) -> BaseModel:
        if role not in ROLE_SCHEMAS:
            raise ContractError("Unknown AI role")
        if schema is not ROLE_SCHEMAS[role] and schema is not EXTRA_ROLE_SCHEMAS.get(role):
            raise ContractError("Schema does not match the role")
        if role in {"intake", "family_conversation"} and screen_crisis(_message_text(messages)):
            raise CrisisPaused()
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = await asyncio.wait_for(
                    self._invoke(role, messages, images, schema),
                    timeout=self.timeout_s,
                )
                if isinstance(raw, schema):
                    parsed = raw
                else:
                    payload = raw if isinstance(raw, dict) else raw.model_dump()
                    parsed = schema.model_validate(payload)
                if role == "document_reader" and images and isinstance(parsed, DocOut):
                    parsed = force_photo_form(parsed)
                return parsed
            except (CrisisPaused, ContractError):
                raise
            except Exception as exc:
                last = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(self.retry_sleep_s)
        raise AIUnavailable("structured_failed") from last

    async def speak_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        audio_format: str = "pcm",
    ) -> AsyncIterator[SpeechChunk]:
        key = self._settings.openai_api_key.get_secret_value()
        if not key:
            raise AIUnavailable("no_api_key")
        from openai import OpenAI

        chosen = "opus" if audio_format == "opus" else "pcm"
        client = OpenAI(api_key=key, timeout=self.timeout_s)
        spoken = voice or self._settings.tts_voice

        def _call() -> bytes:
            speech = client.audio.speech.create(
                model=self._settings.tts_model,
                voice=spoken,
                input=text,
                response_format=chosen,  # type: ignore[arg-type]
            )
            return speech.read()

        audio = await asyncio.to_thread(_call)
        yield SpeechChunk(audio=audio, audio_format=chosen)

    def conversation_session(self, session_id: str):
        """Build a Postgres SQLAlchemy session. Construction does not call OpenAI."""
        from agents.extensions.memory.sqlalchemy_session import SQLAlchemySession
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = self._session_engine
        if engine is None:
            from app.config import postgres_url

            raw = self._settings.database_url.get_secret_value()
            if not raw:
                raise AIUnavailable("no_database")
            engine = create_async_engine(postgres_url(raw))
            self._session_engine = engine
        return SQLAlchemySession(session_id, engine=engine, create_tables=False)

    async def _invoke(
        self,
        role: str,
        messages: Sequence[ChatMessage],
        images,
        schema: type[BaseModel] | None = None,
    ):
        if self._runner is not None:
            return await self._runner(role, messages, images)
        if not self._settings.openai_api_key.get_secret_value():
            raise AIUnavailable("no_api_key")
        from agents import RunConfig, Runner

        key = STATEMENT_AGENT if schema is StatementOut else role
        result = await Runner.run(
            self.agents[key],
            input=[{"role": message.role, "content": message.content} for message in messages],
            run_config=RunConfig(trace_include_sensitive_data=False, tracing_disabled=True),
        )
        return result.final_output
