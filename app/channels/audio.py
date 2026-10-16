"""Repackage Telegram/WhatsApp Opus notes to webm without re-encoding, then transcribe."""

import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from app.channels.errors import AudioRepackageError
from app.contracts import AIClient, Transcript

Runner = Callable[[list[str], bytes], bytes]


def ffmpeg_repackage_command(source: str, dest: str) -> list[str]:
    """ffmpeg arguments that copy the audio stream. There is no output codec."""
    return ["ffmpeg", "-y", "-i", source, "-c:a", "copy", dest]


def repackage_ogg_to_webm(ogg: bytes, *, runner: Runner | None = None) -> bytes:
    """Turn `.ogg` bytes into `.webm` bytes. `runner` replaces the subprocess in tests."""
    if runner is not None:
        return runner(ffmpeg_repackage_command("in.ogg", "out.webm"), ogg)
    with tempfile.TemporaryDirectory(prefix="afterward-audio-") as directory:
        source = Path(directory) / "in.ogg"
        dest = Path(directory) / "out.webm"
        source.write_bytes(ogg)
        command = ffmpeg_repackage_command(str(source), str(dest))
        try:
            subprocess.run(command, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise AudioRepackageError("ffmpeg could not repackage the voice note") from exc
        if not dest.is_file():
            raise AudioRepackageError("ffmpeg did not write a webm file")
        return dest.read_bytes()


async def transcribe_ogg(
    ai: AIClient,
    ogg: bytes,
    *,
    prompt: str = "",
    keywords: Sequence[str] = (),
    runner: Runner | None = None,
) -> Transcript:
    """Repackage then ask the AI client. The transcript is data, not a permission."""
    webm = repackage_ogg_to_webm(ogg, runner=runner)
    return await ai.transcribe(webm, mime="audio/webm", prompt=prompt, keywords=keywords)
