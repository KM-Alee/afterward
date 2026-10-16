"""ffmpeg repackages ogg to webm with stream copy, then the AI client transcribes."""

import shutil
import subprocess
from pathlib import Path

import pytest

from app.channels.audio import ffmpeg_repackage_command, repackage_ogg_to_webm, transcribe_ogg
from app.fakes import FakeAI


def test_ffmpeg_command_copies_audio():
    command = ffmpeg_repackage_command("in.ogg", "out.webm")
    assert command[:4] == ["ffmpeg", "-y", "-i", "in.ogg"]
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[-1] == "out.webm"
    assert "libopus" not in command
    assert "libvorbis" not in command
    assert "aac" not in command


def test_repackage_invokes_the_copy_command(monkeypatch):
    recorded: dict[str, list[str]] = {}

    def fake_run(command, check, capture_output):
        del check, capture_output
        recorded["command"] = list(command)
        Path(command[-1]).write_bytes(b"\x1a\x45\xdf\xa3")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("app.channels.audio.subprocess.run", fake_run)
    assert repackage_ogg_to_webm(b"ogg-bytes").startswith(b"\x1a\x45\xdf\xa3")
    command = recorded["command"]
    assert command[command.index("-c:a") + 1] == "copy"
    assert "libopus" not in command


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_ffmpeg_subprocess_repackages_without_reencode(tmp_path):
    source = tmp_path / "tone.ogg"
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=48000:cl=mono",
            "-t",
            "0.2",
            "-c:a",
            "libopus",
            str(source),
        ],
        capture_output=True,
    )
    if completed.returncode != 0:
        pytest.skip("ffmpeg has no lavfi or libopus support for the subprocess test")
    webm = repackage_ogg_to_webm(source.read_bytes())
    assert webm.startswith(b"\x1a\x45\xdf\xa3")


class RecordingAI(FakeAI):
    def __init__(self) -> None:
        super().__init__()
        self.seen: dict[str, object] | None = None

    async def transcribe(self, audio, *, mime, prompt="", keywords=()):
        self.seen = {"mime": mime, "prompt": prompt, "keywords": tuple(keywords), "audio": audio}
        return await super().transcribe(audio, mime=mime, prompt=prompt, keywords=keywords)


@pytest.mark.asyncio
async def test_transcribe_uses_repackaged_webm_without_network():
    ai = RecordingAI()
    webm = b"webm-from-runner"

    def runner(command, ogg):
        assert command[command.index("-c:a") + 1] == "copy"
        assert ogg == b"ogg-bytes"
        return webm

    ai.register_transcript(webm, "Hello from the note")
    transcript = await transcribe_ogg(
        ai,
        b"ogg-bytes",
        prompt="case context",
        keywords=("Yusuf",),
        runner=runner,
    )
    assert transcript.text == "Hello from the note"
    assert ai.seen is not None
    assert ai.seen["mime"] == "audio/webm"
    assert ai.seen["audio"] == webm
    assert ai.seen["keywords"] == ("Yusuf",)
