"""Deterministic model double. Missing fixtures raise; they never invent a grant."""

import hashlib
import json
from collections.abc import AsyncIterator, Sequence

from pydantic import BaseModel

from app.contracts import (
    AIRole,
    ChatMessage,
    FakeFixtureMissing,
    ImageInput,
    SpeechChunk,
    Transcript,
)


def fixture_key(
    role: str,
    schema_name: str,
    messages: Sequence[ChatMessage],
    images: Sequence[ImageInput] | None,
) -> str:
    """Stable key for one structured call. Image bytes are hashed, not stored in the key text."""
    payload = {
        "images": [hashlib.sha256(image.data).hexdigest() for image in images or ()],
        "messages": [message.model_dump() for message in messages],
        "role": role,
        "schema": schema_name,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode()).hexdigest()


class FakeAI:
    """Recorded transcripts, structured outputs and speech, keyed by the request."""

    def __init__(self) -> None:
        self.transcripts: dict[str, str] = {}
        self.structured_outputs: dict[str, BaseModel] = {}
        self.spoken: list[str] = []

    def register_transcript(self, audio: bytes, text: str) -> None:
        self.transcripts[hashlib.sha256(audio).hexdigest()] = text

    def register_structured(
        self,
        role: AIRole,
        schema: type[BaseModel],
        messages: Sequence[ChatMessage],
        result: BaseModel,
        images: Sequence[ImageInput] | None = None,
    ) -> str:
        key = fixture_key(role, schema.__name__, messages, images)
        self.structured_outputs[key] = result
        return key

    async def transcribe(
        self,
        audio: bytes,
        *,
        mime: str,
        prompt: str = "",
        keywords: Sequence[str] = (),
    ) -> Transcript:
        del mime, prompt, keywords
        key = hashlib.sha256(audio).hexdigest()
        if key not in self.transcripts:
            raise FakeFixtureMissing("No recorded transcript for this audio")
        return Transcript(text=self.transcripts[key], language="en")

    async def structured(
        self,
        role: AIRole,
        schema: type[BaseModel],
        messages: Sequence[ChatMessage],
        images: Sequence[ImageInput] | None = None,
    ) -> BaseModel:
        key = fixture_key(role, schema.__name__, messages, images)
        if key not in self.structured_outputs:
            raise FakeFixtureMissing("No recorded structured output for this input")
        result = self.structured_outputs[key]
        return schema.model_validate(result.model_dump())

    async def speak_stream(
        self,
        text: str,
        *,
        voice: str | None = None,
        audio_format: str = "pcm",
    ) -> AsyncIterator[SpeechChunk]:
        del voice
        self.spoken.append(text)
        yield SpeechChunk(audio=text.encode(), audio_format=audio_format)
