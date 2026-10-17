"""Live check of the call-room voice path. Prints event types and counters only.

Run: uv run --frozen --env-file .env python scripts/voice_check.py
It speaks one generated sentence into a real realtime session, as the provider would,
and reports whether the model heard it, answered, and sent audio back.
"""

import asyncio
import collections
import sys

from app.call.acceptance import CallRoom
from app.call.realtime_session import OpenAIRealtimeSession
from app.config import Settings

LINE = "Hello, you're through to Northline bereavement. How can I help you today?"


async def tts_pcm(settings: Settings, text: str) -> bytes:
    from app.ai.client import AgentsSDKClient

    parts = []
    async for chunk in AgentsSDKClient(settings).speak_stream(text, audio_format="pcm"):
        parts.append(chunk.audio)
    return b"".join(parts)


async def main() -> int:
    settings = Settings.from_env()
    if not settings.openai_api_key.get_secret_value():
        print("No OpenAI key in the environment.")
        return 2
    seen: collections.Counter[str] = collections.Counter()
    session = OpenAIRealtimeSession(settings)
    room = CallRoom(session=session)
    session.attach_room(room)
    original = session._handle

    async def spy(event):
        kind = str(getattr(event, "type", ""))
        if kind == "raw_model_event":
            kind = "raw:" + str(getattr(getattr(event, "data", None), "type", ""))
            inner = getattr(getattr(event, "data", None), "data", None)
            if isinstance(inner, dict) and inner.get("type"):
                kind += ":" + str(inner["type"])
                if inner.get("type") == "error":
                    print("SERVER ERROR:", str(inner.get("error"))[:300])
        seen[kind] += 1
        if kind == "error":
            print(
                "ERROR EVENT:",
                type(getattr(event, "error", None)).__name__,
                str(getattr(event, "error", ""))[:300],
            )
        await original(event)

    session._handle = spy
    await room.start()
    print("connected:", session.stats["connected"] or session.started)
    pcm = await tts_pcm(settings, LINE)
    print("speaking", len(pcm), "bytes of PCM (", round(len(pcm) / 48000, 1), "s )")
    step = 4800  # 100 ms at 24 kHz, 16-bit
    for i in range(0, len(pcm), step):
        await room.on_representative_speech()
        await session.relay_audio_in(pcm[i : i + step])
        await asyncio.sleep(0.1)
    silence = b"\x00\x00" * 2400
    for _ in range(15):
        await session.relay_audio_in(silence)
        await asyncio.sleep(0.1)
    for _ in range(150):
        await asyncio.sleep(0.1)
        if session.stats["audio_out_chunks"] and any(
            t.who == "agent" and t.kind == "model" for t in room.turns
        ):
            await asyncio.sleep(2)
            break
    print("stats:", {k: v for k, v in session.stats.items()})
    print("event types:", dict(seen.most_common()))
    print("transcript:")
    for turn in room.turns:
        print(f"  [{turn.who}/{turn.kind or turn.via}] {turn.text[:160]}")
    await session.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
