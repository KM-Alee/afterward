"""Agents SDK client. Tests inject a runner. An empty API key never opens a socket."""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from pydantic import BaseModel, ConfigDict

from app.ai.prompts import PROMPTS
from app.ai.schemas import DependencyOut, DocOut, IntakeOut, ReplyOut
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


def build_agents(settings: Settings):
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

    @sdk["function_tool"](needs_approval=False)
    def get_case_status(case_ref: str) -> str:
        """Read a case reference. The engine supplies facts. This does not decide them."""
        return f"read_only:{case_ref}"

    @sdk["function_tool"](needs_approval=False)
    def get_account(account_ref: str) -> str:
        """Read an account reference. This cannot change the account."""
        return f"read_only:{account_ref}"

    @sdk["function_tool"](needs_approval=True)
    def propose_decision(summary: str) -> str:
        """Propose a family decision. This does not approve a plan or send anything."""
        del summary
        return "proposal_only"

    @sdk["function_tool"](needs_approval=True)
    def record_dependency_answer(kind: str, statement: str) -> str:
        """Propose a dependency answer. Code turns it into conditions. This grants nothing."""
        del kind, statement
        return "proposal_only"

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
        self.agents = build_agents(self._settings)

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
        del audio, mime, prompt, keywords
        raise AIUnavailable("no_api_key")

    async def structured(
        self,
        role: AIRole,
        schema: type[BaseModel],
        messages: Sequence[ChatMessage],
        images: Sequence[ImageInput] | None = None,
    ) -> BaseModel:
        if role not in ROLE_SCHEMAS:
            raise ContractError("Unknown AI role")
        if schema is not ROLE_SCHEMAS[role]:
            raise ContractError("Schema does not match the role")
        if role in {"intake", "family_conversation"} and screen_crisis(_message_text(messages)):
            raise CrisisPaused()
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                raw = await asyncio.wait_for(
                    self._invoke(role, messages, images),
                    timeout=self.timeout_s,
                )
                if isinstance(raw, schema):
                    parsed = raw
                else:
                    payload = raw if isinstance(raw, dict) else raw.model_dump()
                    parsed = schema.model_validate(payload)
                if role == "document_reader" and images:
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
        del text, voice
        raise AIUnavailable("no_api_key")
        yield SpeechChunk(audio=b"", audio_format=audio_format)

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

    async def _invoke(self, role: str, messages: Sequence[ChatMessage], images):
        if self._runner is not None:
            return await self._runner(role, messages, images)
        if not self._settings.openai_api_key.get_secret_value():
            raise AIUnavailable("no_api_key")
        from agents import RunConfig, Runner

        result = await Runner.run(
            self.agents[role],
            input=[{"role": message.role, "content": message.content} for message in messages],
            run_config=RunConfig(trace_include_sensitive_data=False, tracing_disabled=True),
        )
        return result.final_output
