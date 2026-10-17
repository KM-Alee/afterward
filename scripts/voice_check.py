"""Check the live voice setup in one command. Prints status and a config echo, no secrets.

Run: uv run --frozen --env-file .env python scripts/voice_check.py

It mints an ephemeral Realtime client secret through the same server code the call room
uses (POST /v1/realtime/client_secrets) and reports whether the key, the realtime model and
the transcription model are accepted. The ephemeral value is never printed.
The browser then talks to OpenAI over WebRTC; the full audio path is only checked by
opening the call room in a browser.
"""

import asyncio
import sys

from app.call import webrtc
from app.config import Settings


async def main() -> int:
    settings = Settings.from_env()
    if not settings.openai_api_key.get_secret_value():
        print("FAIL: no OpenAI key in the environment (OPENAI_API_KEY).")
        return 2
    config = webrtc.build_session_config(settings)
    vad = config["audio"]["input"]["turn_detection"]
    print("requested model        :", config["model"])
    print("requested transcription:", config["audio"]["input"]["transcription"]["model"])
    print("voice                  :", config["audio"]["output"]["voice"])
    print("turn detection         :", vad)
    print("tools                  :", [tool["name"] for tool in config["tools"]])
    try:
        minted = await webrtc.mint_client_secret(settings)
    except webrtc.SessionError as exc:
        print(f"FAIL: could not mint a session (status {exc.status}): {exc.message}")
        return 1
    print("OK: client secret minted (value hidden), expires_at", minted["expires_at"])
    print("session model          :", minted["model"])
    print("transcription model    :", minted["transcribe_model"])
    if minted["transcribe_model"] != config["audio"]["input"]["transcription"]["model"]:
        print("NOTE: the configured transcription model was refused; the fallback was used.")
        print("      Set REALTIME_TRANSCRIBE_MODEL to a model your project can use.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
